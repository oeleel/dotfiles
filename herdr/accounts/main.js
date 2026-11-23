// Claude accounts in the right panel stack, opened from the tab bar's Accounts button: each
// account's usage from claude-swap (cswap), a banner when the active account hits its limit, and
// a Switch button. A switch replaces the default login, so every Claude Code session moves to
// the new account on its next request; the panel then sends the resume prompt to the agents the
// limit stopped. The tab bar (tabs-leo) keeps the shared state fresh and announces limits. This
// panel renders that state; its own tick (core.js) polls and announces only when the tab bar has
// not.

import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { agents, theme, openOverlay, notify, playSound, exec, hc, home, appHome, readTextFile, checking, nextCommand, shared, setShared, run } from "herdr";
import { cswapCommand, switchBlocker, suggest, parseSwitch, formatCountdown } from "./accounts.js";
import { readMarkers, loadSessionTerminals, resumeTargets, resumeAll } from "./resume.js";
import { STATE_KEY, SWITCHED_AT_KEY, readConfig, tick, refresh, stateLimit, limitTitle } from "./core.js";

const MOD = "accounts";
const SWITCH_TIMEOUT_MS = 60_000;
// The confirm dialog's Yes runs `accounts.switch-<N>`. nextCommand() hands over only the
// command's name, so the account number rides in it. The prefix is optional because the
// delivered form (with or without "accounts.") is not confirmed.
const SWITCH_COMMAND = /^(?:accounts\.)?switch-(\d+)$/;
const CONFIRM_SIZE = { width: 440, height: 240 };
// The panel column is 368 px (min 280); under this, each row shows its number and weekly percent.
const NARROW_PX = 160;
// The bar grows with the panel up to this, so the reset countdown keeps its room at 280 px.
const BAR_MAX_PX = 140;
// Signs in to a throwaway config folder, so adding an account never moves the live login.
const ADD_SCRIPT = `mods/${MOD}/add-account.sh`;
const ADD_TAB_NAME = "Add Claude account";
// The empty part of a bar: a faint foreground shows on every row background (t.raised matched
// the active row's t.selected and hid the track).
const TRACK_ALPHA = "26";
const FULL_PERCENT = 100;

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const message = (e) => e?.message ?? String(e);
// The shared AccountsState (core.js), or null before any copy has polled.
const accountsState = () => shared(STATE_KEY) ?? null;
const switchedAt = () => Number(shared(SWITCHED_AT_KEY)) || 0;

export default class Accounts extends View {
  init(_props, cx) {
    this.config = null;
    this.configError = null;
    this.ticking = false;
    this.switching = null;
    this.width = Infinity;
    this.deps = { exec, home: home(), appHome: appHome(), readTextFile, shared, setShared, notify, playSound, now: () => Date.now() };
    // check runs init for real: no cswap, no marker reads (resume.js), no shared writes, no timers.
    if (checking()) return;
    cx.spawn(async (cx) => {
      try {
        this.config = await readConfig(this.deps);
      } catch (e) {
        this.configError = message(e);
        console.log(`accounts: ${this.configError}`);
        cx.notify();
        return;
      }
      cx.notify();
      this.tick(cx);
      cx.timer.every(this.config.pollSeconds * 1000, (cx) => this.tick(cx));
    });
    cx.spawn(async (cx) => {
      for (;;) {
        const command = await nextCommand();
        const m = SWITCH_COMMAND.exec(command);
        if (!m) {
          console.log(`accounts: unknown command ${JSON.stringify(command)}`);
          continue;
        }
        // Its own task: a switch waits resumeDelaySeconds before it resumes agents.
        cx.spawn((cx) => this.switchTo(Number(m[1]), cx));
      }
    });
  }

  // Polls only when the tab bar has not kept the shared state fresh. A publish re-renders every
  // mod, so this needs no cx.notify().
  tick(cx) {
    if (checking() || this.ticking || !this.config) return;
    this.ticking = true;
    cx.spawn(async () => {
      try {
        await tick(this.deps, this.config);
      } finally {
        this.ticking = false;
      }
    });
  }

  // Polls now and publishes, so the tab bar and this panel show the switch at once.
  refresh(cx) {
    if (checking() || !this.config) return;
    cx.spawn(() => refresh(this.deps, this.config));
  }

  // The stopped agents a switch would resume now, by name, for the confirm dialog.
  async stoppedAgents() {
    const markers = await readMarkers(exec, home());
    if (!markers.length) return [];
    const live = agents();
    const targets = resumeTargets(markers, live, await loadSessionTerminals(exec, home()));
    return targets.map((target) => {
      const a = live.find((x) => x.address === target.terminal);
      return a ? `${a.space_name} · ${a.tab_name}` : target.terminal;
    });
  }

  askSwitch(number, cx) {
    const view = accountsState()?.view;
    if (!view) return;
    const reason = switchBlocker(view);
    if (reason) {
      notify({ title: reason, level: "error" });
      return;
    }
    if (!this.config.confirmSwitch) {
      cx.spawn((cx) => this.switchTo(number, cx));
      return;
    }
    const row = view.rows.find((r) => r.number === number);
    cx.spawn(async () => {
      let resume;
      if (!this.config.resumeAfterSwitch) resume = "Stopped agents are not resumed (resumeAfterSwitch is off).";
      else {
        try {
          const names = await this.stoppedAgents();
          resume = names.length
            ? `After ${this.config.resumeDelaySeconds} s, "${this.config.resumePrompt}" goes to ${plural(names.length, "stopped agent")}: ${names.join(", ")}.`
            : "No agent is waiting on a limit.";
        } catch (e) {
          resume = `The stopped agents are unknown: ${message(e)}.`;
        }
      }
      openOverlay({
        mod: "confirm",
        kind: "dialog",
        ...CONFIRM_SIZE,
        props: {
          title: `Switch to account ${number}?`,
          detail: `Every Claude Code session moves to account ${number} (${row?.email ?? "unknown"}) on its next request and rebuilds its prompt cache. ${resume}`,
          command: { name: `${MOD}.switch-${number}`, args: {} },
        },
      });
    });
  }

  async switchTo(number, cx) {
    if (checking()) return;
    if (this.switching !== null) {
      notify({ title: `A switch to account ${this.switching} is still running`, level: "warning" });
      return;
    }
    // Checked again here: the dialog may have waited while a poll found a problem.
    const view = accountsState()?.view;
    const reason = view ? switchBlocker(view) : "Switch blocked: cswap has not listed the accounts yet";
    if (reason) {
      notify({ title: reason, level: "error" });
      return;
    }
    this.switching = number;
    cx.notify();
    try {
      const result = await this.runSwitch(number);
      if (!result.ok) {
        notify({ title: `Switch to account ${number} failed`, body: result.message, level: "error" });
        return;
      }
      // Shared, so the tab bar also ignores markers from before the switch.
      setShared(SWITCHED_AT_KEY, Date.now());
      this.refresh(cx);
      const warnings = result.warnings.join("\n");
      if (!this.config.resumeAfterSwitch) {
        notify({ title: `Switched to ${result.to}`, body: warnings || undefined, level: "success" });
        return;
      }
      notify({ title: `Switched to ${result.to}`, body: [`Resuming stopped agents in ${this.config.resumeDelaySeconds} s.`, warnings].filter(Boolean).join("\n"), level: "info" });
      // Sessions keep the old login until Claude Code's Keychain cache expires.
      await cx.sleep(this.config.resumeDelaySeconds * 1000);
      this.reportResume(result.to, await this.resume());
      this.refresh(cx);
    } finally {
      this.switching = null;
      cx.notify();
    }
  }

  async runSwitch(number) {
    const [cmd, args] = cswapCommand(home(), ["switch", String(number), "--json"]);
    try {
      const r = await exec(cmd, args, { timeout: SWITCH_TIMEOUT_MS });
      return parseSwitch(r.stdout, r.code);
    } catch (e) {
      // A timeout may come after cswap changed the login: the next poll shows which is active.
      return { ok: false, to: null, message: `cswap switch did not run or finish: ${message(e)}`, warnings: [] };
    }
  }

  // Targets come only from resumeTargets: a prompt never goes to a terminal the limit did not stop.
  async resume() {
    try {
      const markers = await readMarkers(exec, home());
      const targets = resumeTargets(markers, agents(), await loadSessionTerminals(exec, home()));
      const results = await resumeAll(targets, { hc, exec, home: home(), prompt: this.config.resumePrompt });
      for (const r of results) console.log(`accounts: resume ${r.terminal} (session ${r.session_id}): ${r.ok ? "sent" : "failed"} ${r.detail ?? ""}`);
      return { markers: markers.length, results, error: null };
    } catch (e) {
      console.log(`accounts: resume failed: ${message(e)}`);
      return { markers: 0, results: [], error: message(e) };
    }
  }

  reportResume(to, outcome) {
    if (outcome.error) {
      notify({ title: `Switched to ${to} · resume failed`, body: outcome.error, level: "error" });
      return;
    }
    const sent = outcome.results.filter((r) => r.ok).length;
    const failed = outcome.results.filter((r) => !r.ok).map((r) => `${r.terminal}: ${r.detail}`);
    const skipped = outcome.markers - outcome.results.length;
    const body = [...failed, skipped > 0 ? `${plural(skipped, "stopped agent")} not idle or not found: resume by hand.` : ""].filter(Boolean).join("\n");
    notify({ title: `Switched to ${to} · resumed ${plural(sent, "agent")}`, body: body || undefined, level: body ? "warning" : "success" });
  }

  // cswap's age of the active account's reading, plus the time since the poll.
  ageText(state, now) {
    const ages = state.view.rows.map((r) => r.ageSeconds).filter((a) => a !== null);
    const active = state.view.rows.find((r) => r.active)?.ageSeconds;
    if (active == null && !ages.length) return "";
    const seconds = (active ?? Math.min(...ages)) + (now - state.polledAt) / 1000;
    return seconds < 60 ? "updated just now" : `updated ${formatCountdown(seconds * 1000)} ago`;
  }

  addButton(t) {
    return this.smallButton(t, "add-account", "+ Add", (_e, cx) => {
      cx.stop_propagation();
      if (checking()) return;
      // The tab runs in the interactive shell, which stays open so the result stays readable.
      run("tab.new", { name: ADD_TAB_NAME, argv: ["/bin/bash", `${appHome()}/${ADD_SCRIPT}`] });
    });
  }

  switchButton(t, number, id) {
    return this.smallButton(t, id, "Switch", (_e, cx) => {
      cx.stop_propagation();
      this.askSwitch(number, cx);
    });
  }

  smallButton(t, id, label, onClick) {
    return div()
      .id(id)
      .flex_none()
      .px(6)
      .h(18)
      .rounded(5)
      .border_1()
      .border_color(t.input)
      .text_size(11)
      .text_color(t.foreground)
      .flex()
      .items_center()
      .cursor_pointer()
      .hover((s) => s.bg(t.hover))
      .on_click(onClick)
      .child(label);
  }

  barColor(t, row, w) {
    if (row.stale || w.pct === null) return t.dim;
    if (w.pct >= FULL_PERCENT) return t.blocked;
    return w.pct >= this.config.roomPercent ? t.ansi3 : t.accent;
  }

  windowLine(t, row, w, now) {
    const fill = Math.min(Math.max(w.pct ?? 0, 0), FULL_PERCENT);
    const resets = w.resetsAtMs === null ? "" : `resets ${formatCountdown(w.resetsAtMs - now)}`;
    return h_flex()
      .h(16)
      .pl(14)
      .gap(6)
      .items_center()
      .text_size(11)
      .child(div().w(16).flex_none().text_color(t.dim).child(w.name))
      .child(div().flex_1().max_w(BAR_MAX_PX).h(4).rounded(2).bg(t.foreground + TRACK_ALPHA).child(div().w(`${fill}%`).h(4).rounded(2).bg(this.barColor(t, row, w))))
      .child(div().w(30).flex_none().text_right().text_color(row.stale ? t.dim : t.muted).child(w.pct === null ? "?" : `${Math.round(w.pct)}%`))
      .child(div().flex_1().min_w(0).truncate().text_color(t.dim).child(resets));
  }

  row(t, row, canSwitch, now) {
    const alarm = row.status === "relogin_required" || row.status === "foreign_credential" || row.status === "no_credentials";
    return v_flex()
      .id(`acc-${row.number}`)
      .px(8)
      .py(4)
      .gap(2)
      .flex_none()
      .rounded(8)
      .when(row.active, (el) => el.bg(t.selected))
      .when(row.label !== row.email, (el) => el.tooltip(row.email))
      .child(
        h_flex()
          .h(22)
          .gap(6)
          .items_center()
          .child(div().w(8).flex_none().text_color(t.accent).child(row.active ? "●" : ""))
          .child(div().flex_none().text_color(t.dim).child(String(row.number)))
          .child(div().flex_1().min_w(0).truncate().text_color(row.active ? t.foreground : t.muted).child(row.label))
          .when(Boolean(row.plan), (el) => el.child(div().flex_none().text_size(11).text_color(t.dim).child(row.plan)))
          .when(canSwitch && !row.active && row.status === "ok", (el) => el.child(this.switchButton(t, row.number, `switch-${row.number}`))),
      )
      .children(row.windows.map((w) => this.windowLine(t, row, w, now)))
      .when(Boolean(row.note), (el) => el.child(div().pl(14).text_size(11).text_color(alarm ? t.blocked : t.dim).child(row.note)));
  }

  compactRow(t, row) {
    const week = row.windows.find((w) => w.name === "7d");
    const mark = week && week.pct !== null ? String(Math.round(week.pct)) : row.note ? "!" : "";
    return h_flex()
      .id(`acc-${row.number}`)
      .h(22)
      .gap(3)
      .flex_none()
      .items_center()
      .justify_center()
      .text_size(11)
      .tooltip(`${row.number} ${row.label}${row.note ? `: ${row.note}` : ""}`)
      .child(div().text_color(row.active ? t.foreground : t.dim).child(`${row.active ? "●" : ""}${row.number}`))
      .child(div().text_color(week ? this.barColor(t, row, week) : t.blocked).child(mark));
  }

  banner(t, view, limit, canSwitch) {
    const pick = suggest(view, this.config);
    const week = pick?.windows.find((w) => w.name === "7d");
    const pickText = pick ? `Try ${pick.number} ${pick.label}${week && week.pct !== null ? ` · 7d ${Math.round(week.pct)}%` : ""}` : `No other account is under ${this.config.roomPercent}%.`;
    return v_flex()
      .mx(6)
      .mt(6)
      .p(8)
      .gap(4)
      .flex_none()
      .rounded(8)
      .bg(t.blocked + "1f")
      .text_size(12)
      .child(div().font_medium().text_color(t.blocked).child(limitTitle(limit)))
      .child(
        h_flex()
          .gap(6)
          .items_center()
          .child(div().flex_1().min_w(0).truncate().text_color(t.foreground).child(pickText))
          .when(Boolean(pick) && canSwitch, (el) => el.child(this.switchButton(t, pick.number, "banner-switch"))),
      );
  }

  line(t, text, color) {
    return div().px(14).pt(8).flex_none().text_size(11.5).text_color(color).child(text);
  }

  render(_cx) {
    const t = theme();
    const narrow = this.width < NARROW_PX;
    const now = Date.now();
    const state = accountsState();
    // Rows wait for the config: their bar colors use roomPercent.
    const view = this.config ? state?.view ?? null : null;
    const limit = view ? stateLimit(state, switchedAt()) : null;
    const blocker = view ? switchBlocker(view) : null;
    const canSwitch = !blocker && this.switching === null;
    // With a view, the error is the marker read's; without one, cswap's.
    const error = state?.error ?? null;
    const errorColor = view ? t.dim : t.blocked;
    const waiting = !state && !this.configError ? "Reading cswap..." : null;
    const rows = view ? view.rows.map((r) => (narrow ? this.compactRow(t, r) : this.row(t, r, canSwitch, now))) : [];
    return v_flex()
      .id("root")
      .on_size_change((size, cx) => {
        if (size.width === this.width) return;
        this.width = size.width;
        cx.notify();
      })
      .size_full()
      .min_h(0)
      .rounded(10)
      .overflow_hidden()
      .bg(t.background)
      .border_1()
      .border_color(t.border)
      .text_color(t.foreground)
      .text_size(12.5)
      .when(!narrow, (el) =>
        el.child(
          h_flex()
            .h(42)
            .flex_none()
            .px(14)
            .gap(8)
            .items_center()
            .border_b(1)
            .border_color(t.border)
            .child(div().font_semibold().text_size(13).child("Accounts"))
            .child(div().flex_1())
            .child(div().text_size(11).text_color(t.dim).child(view ? this.ageText(state, now) : ""))
            .child(this.addButton(t)),
        ),
      )
      .when(narrow && Boolean(limit || this.configError || (error && !view)), (el) => el.child(h_flex().h(22).justify_center().items_center().text_color(t.blocked).child("!")))
      .when(!narrow && Boolean(this.configError), (el) => el.child(this.line(t, this.configError, t.blocked)))
      .when(!narrow && Boolean(error), (el) => el.child(this.line(t, error, errorColor)))
      .when(!narrow && Boolean(waiting), (el) => el.child(this.line(t, waiting, t.dim)))
      .when(!narrow && Boolean(blocker), (el) => el.child(this.line(t, blocker, t.blocked)))
      .when(!narrow && this.switching !== null, (el) => el.child(this.line(t, `Switching to account ${this.switching}...`, t.muted)))
      .when(!narrow && Boolean(limit), (el) => el.child(this.banner(t, view, limit, canSwitch)))
      .child(v_flex().id("acc-list").flex_1().min_h(0).p(narrow ? 0 : 6).overflow_y_scrollbar().children(rows));
  }
}
