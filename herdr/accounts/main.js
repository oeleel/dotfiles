// Claude accounts in the sidebar: each account's usage from claude-swap (cswap), a banner when
// the active account hits its limit, and a Switch button. A switch replaces the default login,
// so every Claude Code session moves to the new account on its next request; the panel then
// sends the resume prompt to the agents the limit stopped.

import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { agents, theme, openOverlay, notify, playSound, exec, hc, home, appHome, readTextFile, checking, nextCommand } from "herdr";
import { loadConfig, cswapCommand, parseList, switchBlocker, suggest, activeAtLimit, markersSince, windowWord, parseSwitch, formatCountdown } from "./accounts.js";
import { readMarkers, loadSessionTerminals, resumeTargets, resumeAll } from "./resume.js";

const MOD = "accounts";
const CONFIG_FILE = `mods/${MOD}/config.json`;
// cswap list may fetch usage for every account before it answers.
const LIST_TIMEOUT_MS = 60_000;
const SWITCH_TIMEOUT_MS = 60_000;
// The confirm dialog's Yes runs `accounts.switch-<N>`. nextCommand() hands over only the
// command's name, so the account number rides in it. The prefix is optional because the
// delivered form (with or without "accounts.") is not confirmed.
const SWITCH_COMMAND = /^(?:accounts\.)?switch-(\d+)$/;
const CONFIRM_SIZE = { width: 440, height: 240 };
// The sidebar's rail is narrower than this; there each row shows its number and weekly percent.
const NARROW_PX = 160;
const BAR_PX = 56;
const FULL_PERCENT = 100;
// localStorage: the account whose limit was last announced, so a reload does not toast again,
// and when this panel last switched, so markers from before it do not flag the new account.
const ANNOUNCED_KEY = "announced";
const SWITCHED_AT_KEY = "switchedAt";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const message = (e) => e?.message ?? String(e);

async function readConfig() {
  const path = `${appHome()}/${CONFIG_FILE}`;
  const text = await readTextFile(path);
  if (text === null) throw new Error(`config.json not found at ${path}`);
  let raw;
  try {
    raw = JSON.parse(text);
  } catch (e) {
    throw new Error(`config.json at ${path} is not JSON: ${message(e)}`);
  }
  return loadConfig(raw);
}

function limitTitle(limit) {
  const stopped = limit.stopped ? ` · ${plural(limit.stopped, "agent")} stopped` : "";
  return `Account ${limit.row.number} hit its ${windowWord(limit.window)} limit${stopped}`;
}

export default class Accounts extends View {
  init(_props, cx) {
    this.config = null;
    this.view = null;
    this.polledAt = 0;
    this.listError = null;
    this.markers = [];
    this.markerError = null;
    this.polling = false;
    this.switching = null;
    this.width = Infinity;
    this.announced = localStorage.getItem(ANNOUNCED_KEY);
    this.switchedAt = Number(localStorage.getItem(SWITCHED_AT_KEY)) || 0;
    // check runs init for real: no cswap, no marker reads (resume.js), no timers there.
    if (checking()) return;
    cx.spawn(async (cx) => {
      try {
        this.config = await readConfig();
      } catch (e) {
        this.listError = message(e);
        console.log(`accounts: ${this.listError}`);
        cx.notify();
        return;
      }
      this.poll(cx);
      cx.timer.every(this.config.pollSeconds * 1000, (cx) => this.poll(cx));
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

  // Redraws once per poll: every redraw of a mod redraws the whole window.
  poll(cx) {
    if (checking() || this.polling || !this.config) return;
    this.polling = true;
    cx.spawn(async (cx) => {
      try {
        await Promise.all([this.readList(), this.readStops()]);
      } finally {
        this.polling = false;
      }
      this.announce();
      cx.notify();
    });
  }

  async readList() {
    const [cmd, args] = cswapCommand(home(), ["list", "--json"]);
    let error = null;
    try {
      const r = await exec(cmd, args, { timeout: LIST_TIMEOUT_MS });
      // A missing cswap prints only to stderr ("env: ...: No such file or directory").
      if (r.code !== 0 && !r.stdout.trim()) throw new Error(`cswap list exited ${r.code}: ${r.stderr.trim() || "no output"}`);
      this.view = parseList(r.stdout, this.config);
      this.polledAt = Date.now();
    } catch (e) {
      error = message(e);
    }
    // Once per distinct failure, not every poll.
    if (error && error !== this.listError) console.log(`accounts: ${error}`);
    this.listError = error;
  }

  async readStops() {
    let error = null;
    try {
      this.markers = await readMarkers(exec, home());
    } catch (e) {
      this.markers = [];
      error = `limit-stop markers: ${message(e)}`;
    }
    if (error && error !== this.markerError) console.log(`accounts: ${error}`);
    this.markerError = error;
  }

  limit() {
    return this.view ? activeAtLimit(this.view, markersSince(this.markers, this.switchedAt)) : null;
  }

  // One toast and one sound per limit event: the event ends when the active account has room.
  announce() {
    const limit = this.limit();
    const key = limit ? String(limit.row.number) : null;
    if (key === this.announced) return;
    this.announced = key;
    if (key) localStorage.setItem(ANNOUNCED_KEY, key);
    else localStorage.removeItem(ANNOUNCED_KEY);
    if (!limit) return;
    const pick = suggest(this.view, this.config);
    const reason = switchBlocker(this.view);
    const body = reason ?? (pick ? `Suggested: account ${pick.number} (${pick.label}).` : `No other account is under ${this.config.roomPercent}%.`);
    notify({ title: limitTitle(limit), body, level: "warning" });
    playSound("blocked");
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
    const reason = switchBlocker(this.view);
    if (reason) {
      notify({ title: reason, level: "error" });
      return;
    }
    if (!this.config.confirmSwitch) {
      cx.spawn((cx) => this.switchTo(number, cx));
      return;
    }
    const row = this.view.rows.find((r) => r.number === number);
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
    const reason = this.view ? switchBlocker(this.view) : "Switch blocked: cswap has not listed the accounts yet";
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
      this.switchedAt = Date.now();
      localStorage.setItem(SWITCHED_AT_KEY, String(this.switchedAt));
      this.poll(cx);
      const warnings = result.warnings.join("\n");
      if (!this.config.resumeAfterSwitch) {
        notify({ title: `Switched to ${result.to}`, body: warnings || undefined, level: "success" });
        return;
      }
      notify({ title: `Switched to ${result.to}`, body: [`Resuming stopped agents in ${this.config.resumeDelaySeconds} s.`, warnings].filter(Boolean).join("\n"), level: "info" });
      // Sessions keep the old login until Claude Code's Keychain cache expires.
      await cx.sleep(this.config.resumeDelaySeconds * 1000);
      this.reportResume(result.to, await this.resume());
      this.poll(cx);
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

  ageText(now) {
    const ages = this.view.rows.map((r) => r.ageSeconds).filter((a) => a !== null);
    const active = this.view.rows.find((r) => r.active)?.ageSeconds;
    if (active == null && !ages.length) return "";
    const seconds = (active ?? Math.min(...ages)) + (now - this.polledAt) / 1000;
    return seconds < 60 ? "updated just now" : `updated ${formatCountdown(seconds * 1000)} ago`;
  }

  switchButton(t, number, id) {
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
      .on_click((_e, cx) => {
        cx.stop_propagation();
        this.askSwitch(number, cx);
      })
      .child("Switch");
  }

  barColor(t, row, w) {
    if (row.stale || w.pct === null) return t.dim;
    if (w.pct >= FULL_PERCENT) return t.blocked;
    return w.pct >= this.config.roomPercent ? t.ansi3 : t.accent;
  }

  windowLine(t, row, w, now) {
    const fill = Math.round((BAR_PX * Math.min(Math.max(w.pct ?? 0, 0), FULL_PERCENT)) / FULL_PERCENT);
    const resets = w.resetsAtMs === null ? "" : `resets ${formatCountdown(w.resetsAtMs - now)}`;
    return h_flex()
      .h(16)
      .pl(14)
      .gap(6)
      .items_center()
      .text_size(11)
      .child(div().w(16).flex_none().text_color(t.dim).child(w.name))
      .child(div().w(BAR_PX).h(4).flex_none().rounded(2).bg(t.raised).child(div().w(fill).h(4).rounded(2).bg(this.barColor(t, row, w))))
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

  banner(t, limit, canSwitch) {
    const pick = suggest(this.view, this.config);
    const week = pick?.windows.find((w) => w.name === "7d");
    const pickText = pick ? `Try ${pick.number} ${pick.label}${week && week.pct !== null ? ` · 7d ${Math.round(week.pct)}%` : ""}` : `No other account is under ${this.config.roomPercent}%.`;
    return v_flex()
      .mx(8)
      .mb(6)
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
    return div().px(16).pb(6).flex_none().text_size(11.5).text_color(color).child(text);
  }

  render(_cx) {
    const t = theme();
    const narrow = this.width < NARROW_PX;
    const now = Date.now();
    const limit = this.view && this.config ? this.limit() : null;
    const blocker = this.view ? switchBlocker(this.view) : null;
    const canSwitch = !blocker && this.switching === null;
    const rows = !this.view || !this.config
      ? []
      : this.view.rows.map((r) => (narrow ? this.compactRow(t, r) : this.row(t, r, canSwitch, now)));
    const waiting = !this.view && !this.listError ? "Reading cswap..." : null;
    return v_flex()
      .id("root")
      .on_size_change((size, cx) => {
        if (size.width === this.width) return;
        this.width = size.width;
        cx.notify();
      })
      .size_full()
      .min_h(0)
      .bg(t.chrome)
      .border_t(1)
      .border_color(t.border)
      .text_size(12.5)
      .when(!narrow, (el) =>
        el.child(
          h_flex()
            .px(16)
            .h(41)
            .pt(14)
            .pb(5)
            .flex_none()
            .items_center()
            .justify_between()
            .child(div().text_size(11.5).font_medium().text_color(t.dim).child("Accounts"))
            .child(div().text_size(11).text_color(t.dim).child(this.view ? this.ageText(now) : "")),
        ),
      )
      .when(narrow && Boolean(limit || this.listError), (el) => el.child(h_flex().h(22).justify_center().items_center().text_color(t.blocked).child("!")))
      .when(!narrow && Boolean(this.listError), (el) => el.child(this.line(t, this.listError, t.blocked)))
      .when(!narrow && Boolean(this.markerError), (el) => el.child(this.line(t, this.markerError, t.dim)))
      .when(!narrow && Boolean(waiting), (el) => el.child(this.line(t, waiting, t.dim)))
      .when(!narrow && Boolean(blocker), (el) => el.child(this.line(t, blocker, t.blocked)))
      .when(!narrow && this.switching !== null, (el) => el.child(this.line(t, `Switching to account ${this.switching}...`, t.muted)))
      .when(!narrow && Boolean(limit), (el) => el.child(this.banner(t, limit, canSwitch)))
      .child(v_flex().id("acc-list").flex_1().min_h(0).px(narrow ? 0 : 8).overflow_y_scrollbar().children(rows));
  }
}
