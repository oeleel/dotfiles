// Run: node --test ~/dotfiles/herdr/tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  loadConfig, cswapCommand, parseList, switchBlocker, suggest, activeAtLimit, markersSince, parseSwitch, formatCountdown,
} from "../accounts/accounts.js";

const FIXTURE = readFileSync(new URL("../accounts/fixtures/cswap-list.json", import.meta.url), "utf8");
const SHIPPED_CONFIG = JSON.parse(readFileSync(new URL("../accounts/config.json", import.meta.url), "utf8"));
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

// One `cswap list --json` account with a 7-day window, and its whole payload.
const account = (number, pct, resetsAt, fields = {}) => ({
  number, email: `a${number}@example.com`, active: false, usageStatus: "ok",
  usage: { sevenDay: { pct, resetsAt } }, usageAgeSeconds: 60, ...fields,
});
const list = (accounts, fields = {}) => JSON.stringify({ schemaVersion: 1, activeAccountNumber: 1, accounts, ...fields });
const switchOutput = (fields) => JSON.stringify({
  schemaVersion: 1, switched: true, from: { number: 1, email: "main@example.com" }, to: { number: 2, email: "alt@example.com" },
  strategy: "direct", reason: "switched", message: "Switched to Account-2 (alt@example.com)", warnings: [], ...fields,
});
const ERROR_ENVELOPE = JSON.stringify({ schemaVersion: 1, error: { type: "AccountNotFoundError", message: "Account 9 not found" } });
const FULL_ACTIVE = account(1, 100, "2026-11-25T09:00:00Z", { active: true });
const WEEKLY_MARKER = { session_id: "s1", terminal: "t5n", cwd: "/x", error: "rate_limit", message: "You've hit your weekly limit · resets Nov 25", at: "2026-11-23T12:00:00Z" };

test("test_parse_list_reads_every_fixture_account", () => {
  const view = parseList(FIXTURE, CONFIG);

  assert.deepEqual(view.rows.map((r) => r.number), [1, 2, 3, 4]);
  assert.equal(view.activeNumber, 1);
});

test("test_parse_list_labels_a_row_by_alias_else_email", () => {
  const view = parseList(FIXTURE, CONFIG);

  assert.deepEqual(view.rows.map((r) => r.label), ["main@example.com", "alt", "third@example.com", "fourth@example.com"]);
});

test("test_parse_list_reads_plan_active_and_age", () => {
  const view = parseList(FIXTURE, CONFIG);

  assert.deepEqual(
    { plan: view.rows[0].plan, active: view.rows[0].active, age: view.rows[0].ageSeconds },
    { plan: "Ultra", active: true, age: 120 },
  );
});

test("test_parse_list_keeps_only_the_windows_cswap_reports", () => {
  const view = parseList(FIXTURE, CONFIG);

  assert.deepEqual(view.rows.map((r) => r.windows.map((w) => w.name)), [["7d"], ["7d", "5h"], ["7d"], []]);
});

test("test_parse_list_reads_a_window_pct_and_reset", () => {
  const view = parseList(FIXTURE, CONFIG);

  assert.deepEqual(view.rows[1].windows[1], { name: "5h", pct: 12, resetsAtMs: Date.parse("2026-11-23T16:00:00+00:00") });
});

test("test_parse_list_marks_a_full_window_at_limit_without_room", () => {
  const view = parseList(FIXTURE, CONFIG);

  assert.deepEqual({ atLimit: view.rows[0].atLimit, hasRoom: view.rows[0].hasRoom }, { atLimit: true, hasRoom: false });
});

test("test_parse_list_gives_room_when_every_window_is_under_room_percent", () => {
  const view = parseList(FIXTURE, CONFIG);

  assert.deepEqual(view.rows.map((r) => r.hasRoom), [false, true, true, false]);
});

test("test_parse_list_gives_no_room_at_room_percent", () => {
  const stdout = list([account(1, 90, "2026-11-25T09:00:00Z")]);

  const view = parseList(stdout, CONFIG);

  assert.equal(view.rows[0].hasRoom, false);
});

test("test_parse_list_gives_no_room_for_an_unknown_pct", () => {
  const stdout = list([account(1, null, "2026-11-25T09:00:00Z")]);

  const view = parseList(stdout, CONFIG);

  assert.equal(view.rows[0].hasRoom, false);
});

test("test_parse_list_notes_the_relogin_fix_with_its_slot", () => {
  const view = parseList(FIXTURE, CONFIG);

  assert.equal(view.rows[3].note, "relogin required: claude auth login, then cswap add --slot 4");
});

test("test_parse_list_shows_last_good_usage_as_stale_without_room", () => {
  const stdout = list([{
    number: 1, email: "a@example.com", active: false, usageStatus: "unavailable", usage: null, usageError: "http-429",
    lastGoodUsage: { sevenDay: { pct: 30, resetsAt: "2026-11-25T09:00:00Z" } }, lastGoodAgeSeconds: 900,
  }]);

  const view = parseList(stdout, CONFIG);

  assert.deepEqual(
    { stale: view.rows[0].stale, pct: view.rows[0].windows[0].pct, room: view.rows[0].hasRoom, age: view.rows[0].ageSeconds, note: view.rows[0].note },
    { stale: true, pct: 30, room: false, age: 900, note: "usage unavailable (http-429)" },
  );
});

test("test_parse_list_names_an_unknown_status", () => {
  const stdout = list([{ number: 1, email: "a@example.com", active: false, usageStatus: "new_state", usage: null }]);

  const view = parseList(stdout, CONFIG);

  assert.equal(view.rows[0].note, 'unknown cswap status "new_state"');
});

test("test_parse_list_keeps_duplicate_account_warnings", () => {
  const stdout = list([account(1, 10, "2026-11-25T09:00:00Z")], { duplicateAccountWarnings: ["Account-1 and Account-3 hold the same credential"] });

  const view = parseList(stdout, CONFIG);

  assert.deepEqual(view.duplicateWarnings, ["Account-1 and Account-3 hold the same credential"]);
});

test("test_parse_list_throws_on_an_error_envelope", () => {
  const stdout = ERROR_ENVELOPE;

  const parse = () => parseList(stdout, CONFIG);

  assert.throws(parse, /cswap list: AccountNotFoundError: Account 9 not found/);
});

test("test_parse_list_throws_on_a_wrong_schema_version", () => {
  const stdout = list([], { schemaVersion: 2 });

  const parse = () => parseList(stdout, CONFIG);

  assert.throws(parse, /schemaVersion is 2/);
});

test("test_parse_list_throws_on_output_that_is_not_json", () => {
  const stdout = "env: /Users/leo/.local/bin/cswap: No such file or directory";

  const parse = () => parseList(stdout, CONFIG);

  assert.throws(parse, /cswap list printed no JSON: "env: .*No such file/);
});

test("test_parse_list_throws_on_a_bad_reset_time", () => {
  const stdout = list([account(1, 10, "next week")]);

  const parse = () => parseList(stdout, CONFIG);

  assert.throws(parse, /account 1 7d resetsAt is "next week"/);
});

test("test_load_config_accepts_the_shipped_config", () => {
  const raw = SHIPPED_CONFIG;

  const config = loadConfig(raw);

  assert.deepEqual(config, raw);
});

test("test_load_config_rejects_auto_switch_as_not_built", () => {
  const raw = { ...CONFIG, autoSwitch: true };

  const load = () => loadConfig(raw);

  assert.throws(load, /"autoSwitch" is true: auto-switch is not built/);
});

// [behavior, a config change, what the error must say]. Each names the key and the bad value.
const BAD_CONFIGS = [
  ["a_string_auto_switch", { autoSwitch: "false" }, /"autoSwitch" is "false"/],
  ["a_poll_below_the_minimum", { pollSeconds: 5 }, /"pollSeconds" is 5/],
  ["a_fractional_poll", { pollSeconds: 60.5 }, /"pollSeconds" is 60.5/],
  ["a_string_poll", { pollSeconds: "60" }, /"pollSeconds" is "60"/],
  ["a_string_resume_after_switch", { resumeAfterSwitch: "yes" }, /"resumeAfterSwitch" is "yes"/],
  ["an_empty_resume_prompt", { resumePrompt: "  " }, /"resumePrompt" is "  "/],
  ["a_resume_delay_inside_the_keychain_cache", { resumeDelaySeconds: 20 }, /"resumeDelaySeconds" is 20/],
  ["a_resume_delay_over_the_maximum", { resumeDelaySeconds: 900 }, /"resumeDelaySeconds" is 900/],
  ["a_number_confirm_switch", { confirmSwitch: 1 }, /"confirmSwitch" is 1/],
  ["a_zero_room_percent", { roomPercent: 0 }, /"roomPercent" is 0/],
  ["a_room_percent_over_100", { roomPercent: 101 }, /"roomPercent" is 101/],
  ["an_unknown_suggest_order", { suggestOrder: "most-room" }, /"suggestOrder" is "most-room"/],
  ["an_unknown_key", { autoswitch: true }, /unknown key "autoswitch" \(value true\)/],
  ["an_undefined_room_percent", { roomPercent: undefined }, /"roomPercent" is undefined/],
];
for (const [behavior, change, message] of BAD_CONFIGS) {
  test(`test_load_config_rejects_${behavior}`, () => {
    const raw = { ...CONFIG, ...change };

    const load = () => loadConfig(raw);

    assert.throws(load, message);
  });
}

test("test_load_config_rejects_an_absent_key", () => {
  const { roomPercent, ...raw } = CONFIG;

  const load = () => loadConfig(raw);

  assert.throws(load, /"roomPercent" is missing/);
});

test("test_load_config_rejects_a_list", () => {
  const raw = [CONFIG];

  const load = () => loadConfig(raw);

  assert.throws(load, /expected an object/);
});

test("test_cswap_command_unsets_both_config_variables", () => {
  const home = "/Users/leo";

  const command = cswapCommand(home, ["list", "--json"]);

  assert.deepEqual(command, ["/usr/bin/env", ["-u", "CLAUDE_CONFIG_DIR", "-u", "CLAUDE_SECURESTORAGE_CONFIG_DIR", "/Users/leo/.local/bin/cswap", "list", "--json"]]);
});

test("test_cswap_command_rejects_a_relative_home", () => {
  const home = "~";

  const command = () => cswapCommand(home, ["list"]);

  assert.throws(command, /home must be an absolute path, got "~"/);
});

test("test_switch_blocker_allows_the_fixture", () => {
  const view = parseList(FIXTURE, CONFIG);

  const reason = switchBlocker(view);

  assert.equal(reason, null);
});

test("test_switch_blocker_names_a_foreign_credential_account", () => {
  const view = parseList(list([{ number: 1, email: "a@example.com", active: true, usageStatus: "foreign_credential", usage: null }]), CONFIG);

  const reason = switchBlocker(view);

  assert.equal(reason, "Switch blocked: the live login does not match account 1; run `cswap list` in a terminal");
});

test("test_switch_blocker_names_duplicate_accounts", () => {
  const view = parseList(list([account(1, 10, "2026-11-25T09:00:00Z")], { duplicateAccountWarnings: ["Account-1 and Account-3 hold the same credential (a@example.com)"] }), CONFIG);

  const reason = switchBlocker(view);

  assert.equal(reason, "Switch blocked: cswap reports two slots with one login (accounts 1, 3); run `cswap list` in a terminal");
});

test("test_suggest_picks_the_soonest_weekly_reset_with_room", () => {
  const view = parseList(FIXTURE, CONFIG);

  const row = suggest(view, CONFIG);

  assert.equal(row.number, 3);
});

test("test_suggest_skips_an_account_at_room_percent", () => {
  const view = parseList(list([FULL_ACTIVE, account(2, 50, "2026-11-28T00:00:00Z"), account(3, 95, "2026-11-26T00:00:00Z")]), CONFIG);

  const row = suggest(view, CONFIG);

  assert.equal(row.number, 2);
});

test("test_suggest_breaks_a_tie_with_the_lowest_number", () => {
  const view = parseList(list([FULL_ACTIVE, account(3, 10, "2026-11-26T00:00:00Z"), account(2, 50, "2026-11-26T00:00:00Z")]), CONFIG);

  const row = suggest(view, CONFIG);

  assert.equal(row.number, 2);
});

test("test_suggest_puts_an_account_without_a_weekly_reset_last", () => {
  const view = parseList(list([FULL_ACTIVE, account(2, 10, null), account(3, 50, "2026-11-30T00:00:00Z")]), CONFIG);

  const row = suggest(view, CONFIG);

  assert.equal(row.number, 3);
});

test("test_suggest_gives_null_when_no_account_has_room", () => {
  const view = parseList(list([FULL_ACTIVE, account(2, 99, "2026-11-26T00:00:00Z")]), CONFIG);

  const row = suggest(view, CONFIG);

  assert.equal(row, null);
});

test("test_active_at_limit_names_the_full_weekly_window", () => {
  const view = parseList(FIXTURE, CONFIG);

  const limit = activeAtLimit(view, []);

  assert.deepEqual({ number: limit.row.number, window: limit.window, stopped: limit.stopped }, { number: 1, window: "7d", stopped: 0 });
});

test("test_active_at_limit_gives_null_while_the_active_account_has_room", () => {
  const view = parseList(list([account(1, 40, "2026-11-25T09:00:00Z", { active: true })]), CONFIG);

  const limit = activeAtLimit(view, []);

  assert.equal(limit, null);
});

test("test_active_at_limit_trusts_a_marker_over_stale_usage", () => {
  const view = parseList(list([account(1, 40, "2026-11-25T09:00:00Z", { active: true })]), CONFIG);

  const limit = activeAtLimit(view, [WEEKLY_MARKER]);

  assert.deepEqual({ number: limit.row.number, window: limit.window, stopped: limit.stopped }, { number: 1, window: "7d", stopped: 1 });
});

test("test_active_at_limit_gives_null_without_an_active_account", () => {
  const view = parseList(list([account(1, 100, "2026-11-25T09:00:00Z")]), CONFIG);

  const limit = activeAtLimit(view, [WEEKLY_MARKER]);

  assert.equal(limit, null);
});

test("test_markers_since_drops_markers_from_before_the_switch", () => {
  const markers = [{ ...WEEKLY_MARKER, at: "2026-11-23T11:59:00Z" }, { ...WEEKLY_MARKER, session_id: "s2", at: "2026-11-23T12:01:00Z" }];

  const fresh = markersSince(markers, Date.parse("2026-11-23T12:00:00Z"));

  assert.deepEqual(fresh.map((m) => m.session_id), ["s2"]);
});

test("test_markers_since_keeps_a_marker_with_a_bad_time", () => {
  const markers = [{ ...WEEKLY_MARKER, at: "soon" }];

  const fresh = markersSince(markers, Date.parse("2026-11-23T12:00:00Z"));

  assert.equal(fresh.length, 1);
});

test("test_parse_switch_reads_a_switch", () => {
  const stdout = switchOutput({ warnings: ["Claude Desktop is running"] });

  const result = parseSwitch(stdout, 0);

  assert.deepEqual(result, { ok: true, to: 2, message: "Switched to Account-2 (alt@example.com)", warnings: ["Claude Desktop is running"] });
});

test("test_parse_switch_accepts_already_active", () => {
  const stdout = switchOutput({ switched: false, reason: "already-active", message: "Already on Account-2 (alt@example.com)" });

  const result = parseSwitch(stdout, 0);

  assert.deepEqual({ ok: result.ok, to: result.to }, { ok: true, to: 2 });
});

test("test_parse_switch_fails_on_an_error_envelope", () => {
  const stdout = ERROR_ENVELOPE;

  const result = parseSwitch(stdout, 1);

  assert.deepEqual(result, { ok: false, to: null, message: "cswap switch: AccountNotFoundError: Account 9 not found", warnings: [] });
});

test("test_parse_switch_fails_on_a_no_op_reason", () => {
  const stdout = switchOutput({ switched: false, reason: "unmanaged-account", message: "The live login is not managed" });

  const result = parseSwitch(stdout, 0);

  assert.deepEqual({ ok: result.ok, message: result.message }, { ok: false, message: 'cswap switch did not switch (reason "unmanaged-account"): The live login is not managed' });
});

test("test_parse_switch_fails_on_output_that_is_not_json", () => {
  const stdout = "";

  const result = parseSwitch(stdout, 127);

  assert.deepEqual({ ok: result.ok, message: result.message }, { ok: false, message: 'cswap switch printed no JSON: "" (exit 127)' });
});

test("test_parse_switch_fails_on_a_wrong_schema_version", () => {
  const stdout = switchOutput({ schemaVersion: 2 });

  const result = parseSwitch(stdout, 0);

  assert.equal(result.ok, false);
});

test("test_format_countdown_gives_days_and_hours", () => {
  const ms = 2 * DAY + 4 * HOUR + 30 * MINUTE;

  const text = formatCountdown(ms);

  assert.equal(text, "2d4h");
});

test("test_format_countdown_gives_hours_and_minutes", () => {
  const ms = 3 * HOUR + 12 * MINUTE;

  const text = formatCountdown(ms);

  assert.equal(text, "3h12m");
});

test("test_format_countdown_gives_minutes", () => {
  const ms = 45 * MINUTE + 59_000;

  const text = formatCountdown(ms);

  assert.equal(text, "45m");
});

test("test_format_countdown_gives_now_under_a_minute", () => {
  const ms = 59_000;

  const text = formatCountdown(ms);

  assert.equal(text, "now");
});

test("test_format_countdown_gives_now_after_the_reset", () => {
  const ms = -5 * MINUTE;

  const text = formatCountdown(ms);

  assert.equal(text, "now");
});

test("test_format_countdown_rejects_a_missing_time", () => {
  const ms = Number.NaN;

  const format = () => formatCountdown(ms);

  assert.throws(format, /ms is NaN, expected a finite number/);
});
