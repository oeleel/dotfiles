// Run: node --test ~/dotfiles/herdr/tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseList } from "../accounts/accounts.js";
import { tabModel, errorModel } from "../accounts/tab.js";

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
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const NOW = Date.parse("2026-11-23T13:00:00Z");
const WEEK_RESET = new Date(NOW + 2 * DAY + 10 * HOUR).toISOString();
const FIVE_HOUR_RESET = new Date(NOW + 3 * HOUR + 12 * MINUTE).toISOString();
const INSTALL_HINT = "cswap is not installed: run uv tool install claude-swap, then cswap add";

// `cswap list --json` usage windows for the active account.
const weekly = (pct) => ({ sevenDay: { pct, resetsAt: WEEK_RESET } });
const both = (weekPct, fiveHourPct) => ({ ...weekly(weekPct), fiveHour: { pct: fiveHourPct, resetsAt: FIVE_HOUR_RESET } });
// The shared AccountsState (core.js) for one active Ultra account with these windows.
const state = (usage, fields = {}) => ({
  view: parseList(JSON.stringify({
    schemaVersion: 1,
    activeAccountNumber: 1,
    accounts: [{ number: 1, email: "main@example.com", active: true, usageStatus: "ok", usage, usageAgeSeconds: 60, plan: { label: "Ultra" } }],
  }), CONFIG),
  error: null,
  markers: [],
  polledAt: NOW,
  ...fields,
});
const WEEKLY_MARKER = { session_id: "s1", terminal: "t5n", cwd: "/x", error: "rate_limit", message: "You've hit your weekly limit · resets Nov 25", at: new Date(NOW - HOUR).toISOString() };
const SWITCHED_BEFORE_MARKER = NOW - 2 * HOUR;
const SWITCHED_AFTER_MARKER = NOW - 30 * MINUTE;
const MARKED_STATE = state(weekly(40), { markers: [WEEKLY_MARKER] });
const FAILED_STATE = { view: null, error: INSTALL_HINT, markers: [], polledAt: NOW };

test("test_tab_model_without_state_waits_with_no_data", () => {
  const model = tabModel(undefined, CONFIG, null, NOW);

  assert.deepEqual(model, { label: "Accounts", pct: null, level: "none", tip: "No account usage yet: the first cswap poll has not finished" });
});

test("test_tab_model_under_room_percent_is_ok_with_the_weekly_percent", () => {
  const model = tabModel(state(both(23, 10)), CONFIG, null, NOW);

  assert.deepEqual(model, { label: "Accounts", pct: "23%", level: "ok", tip: "Account 1 · main@example.com · 7d 23% · resets 2d10h" });
});

test("test_tab_model_at_room_percent_is_near", () => {
  const model = tabModel(state(both(90, 10)), CONFIG, null, NOW);

  assert.deepEqual({ pct: model.pct, level: model.level }, { pct: "90%", level: "near" });
});

test("test_tab_model_full_window_is_limit", () => {
  const model = tabModel(state(weekly(100)), CONFIG, null, NOW);

  assert.deepEqual(model, { label: "Accounts", pct: "100%", level: "limit", tip: "Account 1 · main@example.com · 7d 100% · resets 2d10h · hit its weekly limit" });
});

test("test_tab_model_limit_stop_marker_after_the_switch_is_limit", () => {
  const model = tabModel(MARKED_STATE, CONFIG, SWITCHED_BEFORE_MARKER, NOW);

  assert.deepEqual(model, { label: "Accounts", pct: "40%", level: "limit", tip: "Account 1 · main@example.com · 7d 40% · resets 2d10h · hit its weekly limit · 1 agent stopped" });
});

test("test_tab_model_without_a_switch_time_counts_every_marker", () => {
  const model = tabModel(MARKED_STATE, CONFIG, undefined, NOW);

  assert.equal(model.level, "limit");
});

test("test_tab_model_ignores_a_marker_older_than_the_switch", () => {
  const model = tabModel(MARKED_STATE, CONFIG, SWITCHED_AFTER_MARKER, NOW);

  assert.deepEqual(model, { label: "Accounts", pct: "40%", level: "ok", tip: "Account 1 · main@example.com · 7d 40% · resets 2d10h" });
});

test("test_tab_model_failed_poll_is_error_with_the_reason", () => {
  const model = tabModel(FAILED_STATE, CONFIG, null, NOW);

  assert.deepEqual(model, { label: "Accounts", pct: null, level: "error", tip: INSTALL_HINT });
});

test("test_tab_model_ultra_with_only_a_weekly_window_shows_it", () => {
  const model = tabModel(state(weekly(40)), CONFIG, null, NOW);

  assert.deepEqual({ pct: model.pct, tip: model.tip }, { pct: "40%", tip: "Account 1 · main@example.com · 7d 40% · resets 2d10h" });
});

test("test_tab_model_five_hour_window_above_the_weekly_sets_the_percent", () => {
  const model = tabModel(state(both(23, 60)), CONFIG, null, NOW);

  assert.deepEqual({ pct: model.pct, level: model.level, tip: model.tip }, { pct: "60%", level: "ok", tip: "Account 1 · main@example.com · 5h 60% · resets 3h12m" });
});

test("test_error_model_shows_a_thrown_error_as_error", () => {
  const model = errorModel(new Error("not built: tick"));

  assert.deepEqual(model, { label: "Accounts", pct: null, level: "error", tip: "not built: tick" });
});
