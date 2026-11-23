// Run: node --test ~/dotfiles/herdr/tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { chmod, mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { MARKER_DIR, readMarkers, loadSessionTerminals, resumeTargets, resumeAll } from "../accounts/resume.js";

const START = "Sun Nov 22 21:07:05 2026";
const LATER = "Sun Nov 22 22:19:19 2026";
const PROMPT = "keep working";
const PS_CALL = ["/usr/bin/env", "TZ=UTC", "LC_ALL=C", "ps", "-E", "-o", "pid=", "-o", "lstart=", "-o", "command="];

const marker = (fields) => ({
  session_id: "s1",
  terminal: "t9z",
  cwd: "/Users/leo/repo",
  error: "rate_limit",
  message: "You've hit your weekly limit · resets Nov 25",
  at: "2026-11-23T17:00:00Z",
  ...fields,
});
const agent = (address, status) => ({ address, status, pane: "p1", app: "claude-code" });
const record = (fields) => ({ kind: "interactive", procStart: START, startedAt: 1, ...fields });
const target = (fields) => ({ marker: marker(fields), terminal: fields.terminal ?? "t9z" });

async function tempHome() {
  const home = await mkdtemp(join(tmpdir(), "resume-test-"));
  await mkdir(join(home, MARKER_DIR), { recursive: true });
  await mkdir(join(home, ".claude/sessions"), { recursive: true });
  return home;
}
const markerPath = (home, session) => join(home, MARKER_DIR, `${session}.json`);
const writeMarker = (home, m) => writeFile(markerPath(home, m.session_id), JSON.stringify(m));
const writeRecord = (home, r) => writeFile(join(home, ".claude/sessions", `${r.pid}.json`), JSON.stringify(r));

/** A stand-in for Herdr's exec: answers `ps` with `stdout` and records those calls; runs every
 *  other program (the registry read) for real. */
function fakePs(stdout) {
  const calls = [];
  const exec = async (cmd, args) => {
    if (cmd !== "/usr/bin/env") return realExec(cmd, args);
    calls.push([cmd, ...args]);
    return { code: 0, stdout, stderr: "" };
  };
  return { exec, calls };
}

/** A stand-in for Herdr's hc that answers every call with `result` and records it. */
function fakeHc(result) {
  const calls = [];
  const hc = async (args) => {
    calls.push(args);
    return result;
  };
  return { hc, calls };
}
/** A stand-in for Herdr's hc that answers a send to each terminal with its own result. */
const hcByTerminal = (results) => async ([, terminal]) => results[terminal];
const hcThatCannotStart = async () => { throw new Error("spawn hc ENOENT"); };
const SENT = { code: 0, stdout: "", stderr: "" };
const rmDenied = async () => ({ code: 1, stdout: "", stderr: "rm: Permission denied\n" });
const shMissing = async () => ({ code: 127, stdout: "", stderr: "sh: not found\n" });

/** Runs the real program, as Herdr's exec does, so the test sees what rm really removes. */
async function realExec(cmd, args) {
  try {
    const { stdout, stderr } = await promisify(execFile)(cmd, args);
    return { code: 0, stdout, stderr };
  } catch (e) {
    return { code: e.code ?? 1, stdout: e.stdout ?? "", stderr: e.stderr ?? "" };
  }
}

test("test_read_markers_returns_an_empty_list_without_the_folder", async () => {
  const home = await mkdtemp(join(tmpdir(), "resume-test-"));

  const markers = await readMarkers(realExec, home);

  assert.deepEqual(markers, []);
});

test("test_read_markers_reads_a_marker_the_hook_wrote", async () => {
  const home = await tempHome();
  await writeMarker(home, marker({ session_id: "s1" }));
  await writeMarker(home, marker({ session_id: "s2", terminal: null, cwd: null }));

  const markers = await readMarkers(realExec, home);

  assert.deepEqual(markers, [
    marker({ session_id: "s1" }),
    marker({ session_id: "s2", terminal: null, cwd: null }),
  ]);
});

test("test_read_markers_skips_unreadable_and_invalid_files", async () => {
  const home = await tempHome();
  await writeFile(markerPath(home, "half"), "{half-written");
  await writeFile(markerPath(home, "renamed"), JSON.stringify(marker({ session_id: "other" })));
  await writeFile(markerPath(home, "no-error"), JSON.stringify(marker({ session_id: "no-error", error: undefined })));
  await writeFile(markerPath(home, "bad-terminal"), JSON.stringify(marker({ session_id: "bad-terminal", terminal: "" })));
  await writeFile(join(home, MARKER_DIR, ".s3.AbC123"), JSON.stringify(marker({ session_id: "s3" })));
  await writeMarker(home, marker({ session_id: "s1" }));

  const markers = await readMarkers(realExec, home);

  assert.deepEqual(markers, [marker({ session_id: "s1" })]);
});

test("test_read_markers_skips_a_file_it_cannot_read", async () => {
  const home = await tempHome();
  await writeMarker(home, marker({ session_id: "locked" }));
  await chmod(markerPath(home, "locked"), 0o000);
  await writeMarker(home, marker({ session_id: "s1" }));

  const markers = await readMarkers(realExec, home);

  assert.deepEqual(markers, [marker({ session_id: "s1" })]);
});

test("test_read_markers_reads_a_home_with_a_space_in_its_path", async () => {
  const home = await tempHome();
  const spaced = join(home, "Leo Lee");
  await mkdir(join(spaced, MARKER_DIR), { recursive: true });
  await writeMarker(spaced, marker({ session_id: "s1" }));

  const markers = await readMarkers(realExec, spaced);

  assert.deepEqual(markers, [marker({ session_id: "s1" })]);
});

test("test_read_markers_fails_loudly_when_the_shell_does_not_run", async () => {
  const run = readMarkers(shMissing, "/h");

  await assert.rejects(run, /reading \/h\/\.local\/state\/claude-limit-stops\/\*\.json: \/bin\/sh exited 127: sh: not found/);
});

test("test_load_session_terminals_maps_a_live_session_to_its_terminal", async () => {
  const home = await tempHome();
  await writeRecord(home, record({ pid: 6571, sessionId: "s1" }));
  await writeFile(join(home, ".claude/sessions/6571.key"), "not a record");
  await writeFile(join(home, ".claude/sessions/9.json"), "{half-written");
  await writeFile(join(home, ".claude/sessions/10.json"), "null");
  const { exec, calls } = fakePs(` 6571 ${START}     claude COLORTERM=truecolor HC_TERMINAL_ID=t5n HOME=/Users/leo\n`);

  const terminals = await loadSessionTerminals(exec, home);

  assert.deepEqual([...terminals], [["s1", "t5n"]]);
  assert.deepEqual(calls, [[...PS_CALL, "-p", "6571"]]);
});

test("test_load_session_terminals_prefers_the_environment_over_a_prompt_argument", async () => {
  const home = await tempHome();
  await writeRecord(home, record({ pid: 12881, sessionId: "s1" }));
  const { exec } = fakePs(`12881 ${START}     claude say HC_TERMINAL_ID=t9z HOME=/Users/leo HC_TERMINAL_ID=t5d\n`);

  const terminals = await loadSessionTerminals(exec, home);

  assert.deepEqual([...terminals], [["s1", "t5d"]]);
});

test("test_load_session_terminals_skips_a_reused_pid", async () => {
  const home = await tempHome();
  await writeRecord(home, record({ pid: 6571, sessionId: "s1" }));
  const { exec } = fakePs(` 6571 ${LATER}     claude HC_TERMINAL_ID=t5n\n`);

  const terminals = await loadSessionTerminals(exec, home);

  assert.equal(terminals.size, 0);
});

test("test_load_session_terminals_skips_a_background_job", async () => {
  const home = await tempHome();
  await writeRecord(home, record({ pid: 56668, sessionId: "s1", kind: "bg", jobId: "09a529d8" }));
  const { exec } = fakePs(`56668 ${START}     claude HC_TERMINAL_ID=t4m\n`);

  const terminals = await loadSessionTerminals(exec, home);

  assert.equal(terminals.size, 0);
});

test("test_load_session_terminals_runs_no_ps_for_an_empty_registry", async () => {
  const home = await tempHome();
  const { exec, calls } = fakePs("");

  const terminals = await loadSessionTerminals(exec, home);

  assert.equal(terminals.size, 0);
  assert.deepEqual(calls, []);
});

test("test_resume_targets_keeps_every_agent_that_is_not_working", () => {
  const markers = [marker({ session_id: "s1", terminal: "t1" }), marker({ session_id: "s2", terminal: "t2" }), marker({ session_id: "s3", terminal: "t3" })];
  const agents = [agent("t1", "idle"), agent("t2", "done"), agent("t3", "blocked")];

  const targets = resumeTargets(markers, agents, new Map());

  assert.deepEqual(targets, [
    { marker: markers[0], terminal: "t1" },
    { marker: markers[1], terminal: "t2" },
    { marker: markers[2], terminal: "t3" },
  ]);
});

test("test_resume_targets_skips_a_working_agent", () => {
  const markers = [marker({ terminal: "t1" })];
  const agents = [agent("t1", "working")];

  const targets = resumeTargets(markers, agents, new Map());

  assert.deepEqual(targets, []);
});

test("test_resume_targets_skips_a_terminal_that_is_not_an_agent", () => {
  const markers = [marker({ terminal: "t1" })];
  const agents = [agent("t2", "idle")];

  const targets = resumeTargets(markers, agents, new Map());

  assert.deepEqual(targets, []);
});

test("test_resume_targets_maps_a_marker_without_a_terminal_through_the_sessions", () => {
  const markers = [marker({ session_id: "s1", terminal: null })];
  const agents = [agent("t5n", "done")];

  const targets = resumeTargets(markers, agents, new Map([["s1", "t5n"]]));

  assert.deepEqual(targets, [{ marker: markers[0], terminal: "t5n" }]);
});

test("test_resume_targets_skips_a_marker_without_a_terminal_or_a_session", () => {
  const markers = [marker({ session_id: "s1", terminal: null })];
  const agents = [agent("t5n", "done")];

  const targets = resumeTargets(markers, agents, new Map());

  assert.deepEqual(targets, []);
});

test("test_resume_targets_skips_a_marker_whose_terminal_runs_another_session", () => {
  const markers = [marker({ session_id: "ended", terminal: "t1" })];
  const agents = [agent("t1", "idle")];

  const targets = resumeTargets(markers, agents, new Map([["newer", "t1"]]));

  assert.deepEqual(targets, []);
});

test("test_resume_targets_sends_once_per_terminal_to_the_newest_marker", () => {
  const markers = [
    marker({ session_id: "new", terminal: "t1", at: "2026-11-23T18:00:00Z" }),
    marker({ session_id: "old", terminal: "t1", at: "2026-11-23T17:00:00Z" }),
  ];
  const agents = [agent("t1", "idle")];

  const targets = resumeTargets(markers, agents, new Map());

  assert.deepEqual(targets, [{ marker: markers[0], terminal: "t1" }]);
});

test("test_resume_all_sends_the_prompt_and_removes_the_marker", async () => {
  const home = await tempHome();
  await writeMarker(home, marker({ session_id: "s1" }));
  const { hc, calls } = fakeHc(SENT);

  const results = await resumeAll([target({ session_id: "s1", terminal: "t9z" })], { hc, exec: realExec, home, prompt: PROMPT });

  assert.deepEqual(results, [{ terminal: "t9z", session_id: "s1", ok: true, detail: "sent" }]);
  assert.deepEqual(calls, [["send", "t9z", PROMPT]]);
  assert.equal(existsSync(markerPath(home, "s1")), false);
});

test("test_resume_all_keeps_the_marker_when_the_send_fails", async () => {
  const home = await tempHome();
  await writeMarker(home, marker({ session_id: "s1" }));
  const { hc } = fakeHc({ code: 1, stdout: "", stderr: "t9z is blocked: a person is needed\n" });

  const results = await resumeAll([target({ session_id: "s1", terminal: "t9z" })], { hc, exec: realExec, home, prompt: PROMPT });

  assert.deepEqual(results, [{ terminal: "t9z", session_id: "s1", ok: false, detail: "hc send exited 1: t9z is blocked: a person is needed" }]);
  assert.equal(existsSync(markerPath(home, "s1")), true);
});

test("test_resume_all_reports_an_hc_that_cannot_start", async () => {
  const home = await tempHome();
  await writeMarker(home, marker({ session_id: "s1" }));

  const results = await resumeAll([target({ session_id: "s1", terminal: "t9z" })], { hc: hcThatCannotStart, exec: realExec, home, prompt: PROMPT });

  assert.deepEqual(results, [{ terminal: "t9z", session_id: "s1", ok: false, detail: "hc send did not run: Error: spawn hc ENOENT" }]);
  assert.equal(existsSync(markerPath(home, "s1")), true);
});

test("test_resume_all_answers_each_target_on_its_own", async () => {
  const home = await tempHome();
  await writeMarker(home, marker({ session_id: "s1" }));
  await writeMarker(home, marker({ session_id: "s2" }));
  const hc = hcByTerminal({ t1: { code: 2, stdout: "", stderr: "no terminal t1\n" }, t2: SENT });

  const results = await resumeAll(
    [target({ session_id: "s1", terminal: "t1" }), target({ session_id: "s2", terminal: "t2" })],
    { hc, exec: realExec, home, prompt: PROMPT },
  );

  assert.deepEqual(results, [
    { terminal: "t1", session_id: "s1", ok: false, detail: "hc send exited 2: no terminal t1" },
    { terminal: "t2", session_id: "s2", ok: true, detail: "sent" },
  ]);
  assert.equal(existsSync(markerPath(home, "s1")), true);
  assert.equal(existsSync(markerPath(home, "s2")), false);
});

test("test_resume_all_reports_a_marker_it_could_not_remove", async () => {
  const { hc } = fakeHc(SENT);

  const results = await resumeAll([target({ session_id: "s1", terminal: "t9z" })], { hc, exec: rmDenied, home: "/h", prompt: PROMPT });

  assert.deepEqual(results, [{
    terminal: "t9z",
    session_id: "s1",
    ok: true,
    detail: "sent; /bin/rm /h/.local/state/claude-limit-stops/s1.json exited 1: rm: Permission denied",
  }]);
});

test("test_resume_all_rejects_a_missing_exec", async () => {
  const { hc } = fakeHc(SENT);

  const run = resumeAll([target({})], { hc, home: "/nonexistent", prompt: PROMPT });

  await assert.rejects(run, /exec must be a function, got undefined/);
});

test("test_resume_all_rejects_a_session_id_with_a_path", async () => {
  const { hc, calls } = fakeHc(SENT);

  const run = resumeAll([target({ session_id: "../x" })], { hc, exec: realExec, home: "/nonexistent", prompt: PROMPT });

  await assert.rejects(run, /unsafe session_id "\.\.\/x"/);
  assert.deepEqual(calls, []);
});
