// Run: node --test ~/dotfiles/herdr/tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseList } from "../accounts/accounts.js";
import {
  STATE_KEY, SWITCHED_AT_KEY, ANNOUNCED_KEY, readConfig, isStale, pollState, limitAnnouncement, refresh, tick,
} from "../accounts/core.js";

const FIXTURE = readFileSync(new URL("../accounts/fixtures/cswap-list.json", import.meta.url), "utf8");
const SHIPPED_CONFIG_TEXT = readFileSync(new URL("../accounts/config.json", import.meta.url), "utf8");
const CONFIG = {
  autoSwitch: false,
  pollSeconds: 60,
  resumeAfterSwitch: true,
  resumePrompt: "keep working",
  resumeDelaySeconds: 35,
  confirmSwitch: true,
  roomPercent: 90,
  suggestOrder: "soonest-weekly-reset",
};
const HOME = "/Users/test";
const APP_HOME = "/Users/test/.config/herdr-app";
const MARKER_DIR = `${HOME}/.local/state/claude-limit-stops`;
const SECOND = 1000;
const MINUTE = 60 * SECOND;
const T0 = Date.parse("2026-11-23T13:00:00Z");
const RESET = "2026-11-25T09:00:00Z";
const NEXT_RESET = "2026-12-02T09:00:00Z";
// The same reset as RESET, as a later reading may report it.
const RESET_JITTER = "2026-11-25T09:00:00.400Z";

const ok = (stdout) => ({ code: 0, stdout, stderr: "" });
// One `cswap list --json` account with a 7-day window, and its whole payload.
const account = (number, pct, resetsAt, fields = {}) => ({
  number, email: `a${number}@example.com`, active: false, usageStatus: "ok",
  usage: { sevenDay: { pct, resetsAt } }, usageAgeSeconds: 60, ...fields,
});
const list = (accounts) => JSON.stringify({ schemaVersion: 1, activeAccountNumber: 1, accounts });
const marker = (session, message, at) => ({ session_id: session, terminal: `t-${session}`, cwd: "/x", error: "rate_limit", message, at });
// What resume.js's marker read prints: "<path>RS<contents>RS" per file.
const markerOutput = (markers) => markers.map((m) => `${MARKER_DIR}/${m.session_id}.json\x1e${JSON.stringify(m)}\x1e`).join("");
const stateOf = (accounts, markers = [], polledAt = T0) => ({ view: parseList(list(accounts), CONFIG), error: null, markers, polledAt });

const WEEKLY_MARKER = marker("s1", "You've hit your weekly limit · resets Nov 25", "2026-11-23T12:00:00Z");
const PLAIN_MARKER = marker("s2", "Usage limit reached", "2026-11-23T12:00:00Z");
const ERROR_ENVELOPE = JSON.stringify({ schemaVersion: 1, error: { type: "AccountNotFoundError", message: "Account 9 not found" } });
const FULL = [account(1, 100, RESET, { active: true }), account(2, 20, "2026-11-28T09:00:00Z")];
const NEAR = [account(1, 97, RESET, { active: true }), account(2, 20, "2026-11-28T09:00:00Z")];
const FULL_JITTER = [account(1, 100, RESET_JITTER, { active: true }), account(2, 20, "2026-11-28T09:00:00Z")];
const FULL_NEXT_WEEK = [account(1, 100, NEXT_RESET, { active: true }), account(2, 20, "2026-11-28T09:00:00Z")];
// Account 2 active with room: the state right after a switch away from account 1.
const SWITCHED = [account(1, 100, RESET), account(2, 20, "2026-11-28T09:00:00Z", { active: true })];
const ROOM = [account(1, 20, RESET, { active: true })];

/** Herdr's functions for core.js. exec answers `cswap list` with `list` and the marker read with
 *  `markers`; an Error answer rejects. `store` is shared() and setShared(); pass one store to two
 *  fakes to stand for the tab bar and the panel. */
function fakeDeps({ list: listAnswer = ok(FIXTURE), markers = ok(markerOutput([WEEKLY_MARKER])), store = new Map(), configText = SHIPPED_CONFIG_TEXT } = {}) {
  const deps = {
    clock: T0, calls: [], sets: [], toasts: [], sounds: [], reads: [], store, duringExec: () => {},
    home: HOME,
    appHome: APP_HOME,
    exec: async (cmd, args) => {
      deps.calls.push([cmd, ...args]);
      deps.duringExec();
      const answer = cmd === "/bin/sh" ? markers : listAnswer;
      if (answer instanceof Error) throw answer;
      return answer;
    },
    readTextFile: async (path) => {
      deps.reads.push(path);
      return configText;
    },
    shared: (key) => deps.store.get(key),
    setShared: (key, value) => {
      deps.sets.push(key);
      deps.store.set(key, value);
      return null;
    },
    notify: (n) => {
      deps.toasts.push(n);
      return "toast-id";
    },
    playSound: (sound) => {
      deps.sounds.push(sound);
      return null;
    },
    now: () => deps.clock,
  };
  return deps;
}

/** Another copy publishes `state` while this copy's poll runs. */
function publishDuringPoll(deps, state) {
  deps.duringExec = () => deps.store.set(STATE_KEY, state);
}

const sharedThatThrows = () => {
  throw new Error("shared state unavailable");
};

test("test_read_config_reads_the_accounts_mod_config", async () => {
  const deps = fakeDeps();

  const config = await readConfig(deps);

  assert.deepEqual({ config, reads: deps.reads }, { config: CONFIG, reads: [`${APP_HOME}/mods/accounts/config.json`] });
});

test("test_read_config_names_the_path_when_the_file_is_missing", async () => {
  const deps = fakeDeps({ configText: null });

  const reading = readConfig(deps);

  await assert.rejects(reading, { message: `config.json not found at ${APP_HOME}/mods/accounts/config.json` });
});

test("test_read_config_names_the_path_for_a_bad_value", async () => {
  const deps = fakeDeps({ configText: JSON.stringify({ ...CONFIG, pollSeconds: 5 }) });

  const reading = readConfig(deps);

  await assert.rejects(reading, { message: `config.json: "pollSeconds" is 5: must be a whole number of seconds from 10 to 3600 (${APP_HOME}/mods/accounts/config.json)` });
});

test("test_read_config_names_the_path_for_text_that_is_not_json", async () => {
  const deps = fakeDeps({ configText: "{" });

  const reading = readConfig(deps);

  await assert.rejects(reading, /^Error: config\.json at \/Users\/test\/\.config\/herdr-app\/mods\/accounts\/config\.json is not JSON: /);
});

test("test_is_stale_without_a_state", () => {
  const state = undefined;

  const stale = isStale(state, CONFIG, T0);

  assert.equal(stale, true);
});

test("test_is_stale_false_for_a_state_younger_than_poll_seconds", () => {
  const state = stateOf(ROOM, [], T0);

  const stale = isStale(state, CONFIG, T0 + 30 * SECOND);

  assert.equal(stale, false);
});

test("test_is_stale_true_at_poll_seconds", () => {
  const state = stateOf(ROOM, [], T0);

  const stale = isStale(state, CONFIG, T0 + MINUTE);

  assert.equal(stale, true);
});

test("test_is_stale_true_for_a_tick_that_fires_a_little_early", () => {
  const state = stateOf(ROOM, [], T0);

  const stale = isStale(state, CONFIG, T0 + MINUTE - 5);

  assert.equal(stale, true);
});

test("test_is_stale_true_for_a_state_from_the_future", () => {
  const state = stateOf(ROOM, [], T0 + MINUTE);

  const stale = isStale(state, CONFIG, T0);

  assert.equal(stale, true);
});

test("test_is_stale_true_without_a_poll_time", () => {
  const state = { view: null, error: "old shape", markers: [] };

  const stale = isStale(state, CONFIG, T0);

  assert.equal(stale, true);
});

test("test_poll_state_reads_the_accounts_and_markers", async () => {
  const deps = fakeDeps();

  const state = await pollState(deps, CONFIG);

  assert.deepEqual(
    { rows: state.view.rows.map((r) => r.number), error: state.error, markers: state.markers, polledAt: state.polledAt },
    { rows: [1, 2, 3, 4], error: null, markers: [WEEKLY_MARKER], polledAt: T0 },
  );
});

test("test_poll_state_runs_cswap_list_with_both_config_variables_unset", async () => {
  const deps = fakeDeps();

  await pollState(deps, CONFIG);

  assert.deepEqual(deps.calls[0], ["/usr/bin/env", "-u", "CLAUDE_CONFIG_DIR", "-u", "CLAUDE_SECURESTORAGE_CONFIG_DIR", `${HOME}/.local/bin/cswap`, "list", "--json"]);
});

test("test_poll_state_gives_the_install_hint_when_cswap_is_missing", async () => {
  const deps = fakeDeps({ list: { code: 127, stdout: "", stderr: "env: /Users/test/.local/bin/cswap: No such file or directory" } });

  const state = await pollState(deps, CONFIG);

  assert.deepEqual(
    { view: state.view, error: state.error },
    { view: null, error: "cswap is not installed: run uv tool install claude-swap, then cswap add" },
  );
});

test("test_poll_state_reports_an_error_envelope", async () => {
  const deps = fakeDeps({ list: { code: 1, stdout: ERROR_ENVELOPE, stderr: "" } });

  const state = await pollState(deps, CONFIG);

  assert.deepEqual({ view: state.view, error: state.error }, { view: null, error: "cswap list: AccountNotFoundError: Account 9 not found" });
});

test("test_poll_state_reports_an_exit_without_output", async () => {
  const deps = fakeDeps({ list: { code: 2, stdout: "", stderr: "Traceback: KeyError\n" } });

  const state = await pollState(deps, CONFIG);

  assert.deepEqual({ view: state.view, error: state.error }, { view: null, error: "cswap list exited 2: Traceback: KeyError" });
});

test("test_poll_state_keeps_the_view_when_the_marker_read_fails", async () => {
  const deps = fakeDeps({ markers: { code: 1, stdout: "", stderr: "sh: permission denied\n" } });

  const state = await pollState(deps, CONFIG);

  assert.deepEqual(
    { rows: state.view.rows.length, markers: state.markers, error: state.error },
    { rows: 4, markers: [], error: `limit-stop markers: reading ${MARKER_DIR}/*.json: /bin/sh exited 1: sh: permission denied` },
  );
});

test("test_poll_state_never_throws_when_exec_rejects", async () => {
  const deps = fakeDeps({ list: new Error("spawn failed"), markers: new Error("spawn failed") });

  const state = await pollState(deps, CONFIG);

  assert.deepEqual(
    { view: state.view, markers: state.markers, error: state.error },
    { view: null, markers: [], error: "spawn failed; limit-stop markers: spawn failed" },
  );
});

test("test_poll_state_is_json_safe", async () => {
  const deps = fakeDeps();

  const state = await pollState(deps, CONFIG);

  assert.deepEqual(JSON.parse(JSON.stringify(state)), state);
});

test("test_limit_announcement_names_the_limit_and_suggests_an_account", () => {
  const state = { view: parseList(FIXTURE, CONFIG), error: null, markers: [], polledAt: T0 };

  const announcement = limitAnnouncement(state, CONFIG, 0, null);

  assert.deepEqual(announcement, {
    id: "1:7d:2026-11-25T09:00:00.000Z",
    title: "Account 1 hit its weekly limit",
    body: "Suggested: account 3 (third@example.com).",
  });
});

test("test_limit_announcement_counts_the_stopped_agents", () => {
  const state = stateOf(FULL, [WEEKLY_MARKER, PLAIN_MARKER]);

  const announcement = limitAnnouncement(state, CONFIG, 0, null);

  assert.equal(announcement.title, "Account 1 hit its weekly limit · 2 agents stopped");
});

test("test_limit_announcement_keeps_the_id_when_cswap_catches_up_with_a_marker", () => {
  const markerFirst = stateOf(NEAR, [WEEKLY_MARKER]);
  const cswapFull = stateOf(FULL_JITTER, [WEEKLY_MARKER]);

  const first = limitAnnouncement(markerFirst, CONFIG, 0, null);
  const later = limitAnnouncement(cswapFull, CONFIG, 0, null);

  assert.equal(later.id, first.id);
});

test("test_limit_announcement_keeps_the_id_when_the_marker_names_no_window", () => {
  const markerFirst = stateOf(NEAR, [PLAIN_MARKER]);
  const cswapFull = stateOf(FULL, [PLAIN_MARKER]);

  const first = limitAnnouncement(markerFirst, CONFIG, 0, null);
  const later = limitAnnouncement(cswapFull, CONFIG, 0, null);

  assert.equal(later.id, first.id);
});

test("test_limit_announcement_gives_null_for_the_announced_event", () => {
  const state = stateOf(FULL);

  const announcement = limitAnnouncement(state, CONFIG, 0, "1:7d:2026-11-25T09:00:00.000Z");

  assert.equal(announcement, null);
});

test("test_limit_announcement_gives_a_new_id_after_the_window_resets", () => {
  const state = stateOf(FULL_NEXT_WEEK);

  const announcement = limitAnnouncement(state, CONFIG, 0, "1:7d:2026-11-25T09:00:00.000Z");

  assert.equal(announcement.id, "1:7d:2026-12-02T09:00:00.000Z");
});

test("test_limit_announcement_gives_null_after_a_switch_whose_markers_are_older", () => {
  const state = stateOf(SWITCHED, [WEEKLY_MARKER]);
  const switchedAt = Date.parse(WEEKLY_MARKER.at) + MINUTE;

  const announcement = limitAnnouncement(state, CONFIG, switchedAt, null);

  assert.equal(announcement, null);
});

test("test_limit_announcement_counts_markers_written_after_the_switch", () => {
  const state = stateOf(SWITCHED, [WEEKLY_MARKER]);
  const switchedAt = Date.parse(WEEKLY_MARKER.at) - MINUTE;

  const announcement = limitAnnouncement(state, CONFIG, switchedAt, null);

  assert.equal(announcement.title, "Account 2 hit its weekly limit · 1 agent stopped");
});

test("test_limit_announcement_gives_null_without_a_view", () => {
  const state = { view: null, error: "cswap list exited 2: boom", markers: [WEEKLY_MARKER], polledAt: T0 };

  const announcement = limitAnnouncement(state, CONFIG, 0, null);

  assert.equal(announcement, null);
});

test("test_tick_publishes_a_poll_when_there_is_no_state", async () => {
  const deps = fakeDeps();

  await tick(deps, CONFIG);

  assert.deepEqual(
    { rows: deps.store.get(STATE_KEY).view.rows.length, polledAt: deps.store.get(STATE_KEY).polledAt },
    { rows: 4, polledAt: T0 },
  );
});

test("test_tick_skips_the_poll_when_the_state_is_fresh", async () => {
  const deps = fakeDeps({ store: new Map([[STATE_KEY, stateOf(ROOM, [], T0 - 10 * SECOND)]]) });

  await tick(deps, CONFIG);

  assert.deepEqual({ calls: deps.calls, sets: deps.sets }, { calls: [], sets: [] });
});

test("test_tick_announces_a_limit_once_across_polls", async () => {
  const deps = fakeDeps();

  await tick(deps, CONFIG);
  deps.clock = T0 + MINUTE;
  await tick(deps, CONFIG);

  assert.deepEqual(
    { polls: deps.calls.length, toasts: deps.toasts, sounds: deps.sounds, announced: deps.store.get(ANNOUNCED_KEY) },
    {
      polls: 4,
      toasts: [{ title: "Account 1 hit its weekly limit · 1 agent stopped", body: "Suggested: account 3 (third@example.com).", level: "warning" }],
      sounds: ["blocked"],
      announced: "1:7d:2026-11-25T09:00:00.000Z",
    },
  );
});

test("test_tick_announces_once_across_the_tab_bar_and_the_panel", async () => {
  const store = new Map();
  const tabBar = fakeDeps({ store });
  const panel = fakeDeps({ store });

  await tick(tabBar, CONFIG);
  await tick(panel, CONFIG);

  assert.deepEqual({ tabBar: tabBar.toasts.length, panel: panel.toasts.length, panelPolls: panel.calls.length }, { tabBar: 1, panel: 0, panelPolls: 0 });
});

test("test_tick_skips_markers_from_before_the_last_switch", async () => {
  const deps = fakeDeps({
    list: ok(list(SWITCHED)),
    store: new Map([[SWITCHED_AT_KEY, Date.parse(WEEKLY_MARKER.at) + MINUTE]]),
  });

  await tick(deps, CONFIG);

  assert.deepEqual({ toasts: deps.toasts, sounds: deps.sounds }, { toasts: [], sounds: [] });
});

test("test_tick_never_throws", async () => {
  const deps = fakeDeps();
  deps.shared = sharedThatThrows;

  const ticking = tick(deps, CONFIG);

  await assert.doesNotReject(ticking);
});

test("test_refresh_polls_a_fresh_state", async () => {
  const deps = fakeDeps({ store: new Map([[STATE_KEY, stateOf(ROOM, [], T0 - 10 * SECOND)]]) });

  await refresh(deps, CONFIG);

  assert.deepEqual(
    { polls: deps.calls.length, rows: deps.store.get(STATE_KEY).view.rows.length, polledAt: deps.store.get(STATE_KEY).polledAt },
    { polls: 2, rows: 4, polledAt: T0 },
  );
});

test("test_refresh_keeps_a_newer_state_from_another_copy", async () => {
  const deps = fakeDeps();
  const newer = stateOf(SWITCHED, [], T0 + SECOND);
  publishDuringPoll(deps, newer);

  await refresh(deps, CONFIG);

  assert.deepEqual({ state: deps.store.get(STATE_KEY), sets: deps.sets }, { state: newer, sets: [] });
});

test("test_refresh_never_throws", async () => {
  const deps = fakeDeps();
  deps.shared = sharedThatThrows;

  const refreshing = refresh(deps, CONFIG);

  await assert.doesNotReject(refreshing);
});
