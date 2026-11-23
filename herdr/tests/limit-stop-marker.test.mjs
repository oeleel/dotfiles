// Run: node --test ~/dotfiles/herdr/tests/*.test.mjs
// Runs claude/hooks/limit-stop-marker.sh as Claude Code does: hook JSON on stdin, HOME set to a
// temp folder, and a clean environment so this shell's own HC_TERMINAL_ID does not leak in.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HOOK = join(dirname(fileURLToPath(import.meta.url)), "../../claude/hooks/limit-stop-marker.sh");
const MARKERS = ".local/state/claude-limit-stops";
const SESSION = "00893aaf-19fa-41d2-8238-13269b9b3ca0";
const LIMIT_TEXT = "You've hit your weekly limit · resets Nov 25, 5pm (UTC)";
const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const CLEAN = { status: 0, stdout: "" };

const tempHome = () => mkdtempSync(join(tmpdir(), "limit-stop-test-"));
const markerPath = (home, session = SESSION) => join(home, MARKERS, `${session}.json`);
const readMarker = (home) => JSON.parse(readFileSync(markerPath(home), "utf8"));
const markerFiles = (home) => (existsSync(join(home, MARKERS)) ? readdirSync(join(home, MARKERS)) : []);

const failure = (fields) => ({
  session_id: SESSION,
  transcript_path: "/tmp/t.jsonl",
  cwd: "/Users/leo/repo",
  hook_event_name: "StopFailure",
  error: "rate_limit",
  error_details: "429 Too Many Requests",
  last_assistant_message: LIMIT_TEXT,
  ...fields,
});
const stop = (fields) => ({ session_id: SESSION, cwd: "/Users/leo/repo", hook_event_name: "Stop", stop_hook_active: false, ...fields });

/** Runs the hook; returns what Claude Code would see: the exit code and stdout. */
function runHook(home, input, env = {}) {
  const stdin = typeof input === "string" ? input : JSON.stringify(input);
  const r = spawnSync("bash", [HOOK], { input: stdin, encoding: "utf8", env: { PATH: "/usr/bin:/bin", HOME: home, ...env } });
  return { status: r.status, stdout: r.stdout };
}

function writeMarkerFile(path) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, "{}");
}

test("test_limit_stop_marker_writes_a_marker_for_a_rate_limit_stop", () => {
  const home = tempHome();

  const result = runHook(home, failure(), { HC_TERMINAL_ID: "t9z" });

  assert.deepEqual(result, CLEAN);
  const { at, ...marker } = readMarker(home);
  assert.deepEqual(marker, { session_id: SESSION, terminal: "t9z", cwd: "/Users/leo/repo", error: "rate_limit", message: LIMIT_TEXT });
  assert.match(at, ISO_UTC);
});

test("test_limit_stop_marker_records_a_null_terminal_outside_herdr", () => {
  const home = tempHome();

  const result = runHook(home, failure());

  assert.deepEqual(result, CLEAN);
  assert.equal(readMarker(home).terminal, null);
});

test("test_limit_stop_marker_keeps_the_first_300_characters_of_the_message", () => {
  const home = tempHome();

  const result = runHook(home, failure({ last_assistant_message: "é".repeat(400) }));

  assert.deepEqual(result, CLEAN);
  assert.equal(readMarker(home).message, "é".repeat(300));
});

test("test_limit_stop_marker_ignores_an_unaccepted_error", () => {
  const home = tempHome();

  const result = runHook(home, failure({ error: "server_error" }), { HC_TERMINAL_ID: "t9z" });

  assert.deepEqual(result, CLEAN);
  assert.deepEqual(markerFiles(home), []);
});

test("test_limit_stop_marker_ignores_a_subagent_stop_failure", () => {
  const home = tempHome();

  const result = runHook(home, failure({ agent_id: "a1b2", agent_type: "Explore" }), { HC_TERMINAL_ID: "t9z" });

  assert.deepEqual(result, CLEAN);
  assert.deepEqual(markerFiles(home), []);
});

test("test_limit_stop_marker_deletes_the_marker_on_stop", () => {
  const home = tempHome();
  runHook(home, failure(), { HC_TERMINAL_ID: "t9z" });

  const result = runHook(home, stop(), { HC_TERMINAL_ID: "t9z" });

  assert.deepEqual(result, CLEAN);
  assert.deepEqual(markerFiles(home), []);
});

test("test_limit_stop_marker_keeps_other_sessions_markers_on_stop", () => {
  const home = tempHome();
  runHook(home, failure(), { HC_TERMINAL_ID: "t9z" });

  const result = runHook(home, stop({ session_id: "another-session" }));

  assert.deepEqual(result, CLEAN);
  assert.deepEqual(markerFiles(home), [`${SESSION}.json`]);
});

test("test_limit_stop_marker_writes_nothing_for_a_session_id_with_a_path", () => {
  const home = tempHome();

  const result = runHook(home, failure({ session_id: "../x" }), { HC_TERMINAL_ID: "t9z" });

  assert.deepEqual(result, CLEAN);
  assert.deepEqual(readdirSync(home), []);
});

test("test_limit_stop_marker_deletes_nothing_for_a_session_id_with_a_path", () => {
  const home = tempHome();
  const outside = join(home, ".local/state/x.json");
  writeMarkerFile(outside);
  mkdirSync(join(home, MARKERS));

  const result = runHook(home, stop({ session_id: "../x" }));

  assert.deepEqual(result, CLEAN);
  assert.equal(existsSync(outside), true);
});

test("test_limit_stop_marker_exits_cleanly_on_input_that_is_not_json", () => {
  const home = tempHome();

  const result = runHook(home, "{half-written", { HC_TERMINAL_ID: "t9z" });

  assert.deepEqual(result, CLEAN);
  assert.deepEqual(readdirSync(home), []);
});
