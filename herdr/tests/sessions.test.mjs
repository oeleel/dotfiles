// Run: node --test ~/dotfiles/herdr/tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseProcesses, sessionNames, loadSessionNames } from "../agents-menu/sessions.js";

const START = "Sun Nov 22 21:07:05 2026";
const LATER = "Sun Nov 22 22:19:19 2026";

const proc = (start, terminal) => ({ start, terminal });
const record = (fields) => ({ kind: "interactive", procStart: START, startedAt: 1, ...fields });

test("test_parse_processes_reads_pid_start_and_terminal", () => {
  const stdout = ` 6571 ${START}     claude COLORTERM=truecolor HC_TERMINAL_ID=t5n HOME=/Users/leo\n`;

  const procs = parseProcesses(stdout);

  assert.deepEqual([...procs], [[6571, proc(START, "t5n")]]);
});

test("test_parse_processes_prefers_the_environment_over_a_prompt_argument", () => {
  const stdout = `12881 ${START}     claude say HC_TERMINAL_ID=t9z HOME=/Users/leo HC_TERMINAL_ID=t5d\n`;

  const procs = parseProcesses(stdout);

  assert.equal(procs.get(12881).terminal, "t5d");
});

test("test_parse_processes_squashes_a_padded_day", () => {
  const stdout = `  42 Mon Nov  2 09:00:00 2026     claude HC_TERMINAL_ID=t1\n`;

  const procs = parseProcesses(stdout);

  assert.equal(procs.get(42).start, "Mon Nov 2 09:00:00 2026");
});

test("test_parse_processes_gives_null_outside_herdr", () => {
  const stdout = ` 7000 ${START}     claude HOME=/Users/leo\n`;

  const procs = parseProcesses(stdout);

  assert.equal(procs.get(7000).terminal, null);
});

test("test_session_names_maps_an_interactive_session_to_its_terminal", () => {
  const records = [record({ pid: 6571, name: "firehose-1c" })];
  const procs = new Map([[6571, proc(START, "t5n")]]);

  const names = sessionNames(records, procs);

  assert.deepEqual([...names], [["t5n", "firehose-1c"]]);
});

test("test_session_names_skips_a_record_whose_process_is_gone", () => {
  const records = [record({ pid: 56671, name: "7be8165d" })];
  const procs = new Map();

  const names = sessionNames(records, procs);

  assert.equal(names.size, 0);
});

test("test_session_names_skips_a_reused_pid", () => {
  const records = [record({ pid: 6571, name: "stale-session" })];
  const procs = new Map([[6571, proc(LATER, "t5n")]]);

  const names = sessionNames(records, procs);

  assert.equal(names.size, 0);
});

test("test_session_names_skips_a_background_job_in_its_starters_terminal", () => {
  const records = [record({ pid: 56668, kind: "bg", jobId: "09a529d8", name: "Overnight runs" })];
  const procs = new Map([[56668, proc(START, "t4m")]]);

  const names = sessionNames(records, procs);

  assert.equal(names.size, 0);
});

test("test_session_names_names_a_parked_session_by_its_job", () => {
  const records = [
    record({ pid: 5540, name: "firehose-70", parkedJobId: "09a529d8" }),
    record({ pid: 56668, kind: "bg", jobId: "09a529d8", name: "Overnight runs" }),
  ];
  const procs = new Map([[5540, proc(START, "t4m")], [56668, proc(START, "t4m")]]);

  const names = sessionNames(records, procs);

  assert.deepEqual([...names], [["t4m", "Overnight runs"]]);
});

test("test_session_names_keeps_its_own_name_when_the_job_is_gone", () => {
  const records = [record({ pid: 5540, name: "firehose-70", parkedJobId: "09a529d8" })];
  const procs = new Map([[5540, proc(START, "t4m")]]);

  const names = sessionNames(records, procs);

  assert.deepEqual([...names], [["t4m", "firehose-70"]]);
});

test("test_session_names_lets_the_newest_session_in_a_terminal_win", () => {
  const records = [
    record({ pid: 2, name: "newer", startedAt: 200 }),
    record({ pid: 1, name: "older", startedAt: 100 }),
  ];
  const procs = new Map([[1, proc(START, "t1")], [2, proc(START, "t1")]]);

  const names = sessionNames(records, procs);

  assert.deepEqual([...names], [["t1", "newer"]]);
});

test("test_load_session_names_reads_the_registry_and_asks_ps_once", async () => {
  const home = await mkdtemp(join(tmpdir(), "sessions-test-"));
  await mkdir(join(home, ".claude/sessions"), { recursive: true });
  await writeFile(join(home, ".claude/sessions/6571.json"), JSON.stringify(record({ pid: 6571, name: "firehose-1c" })));
  await writeFile(join(home, ".claude/sessions/6571.key"), "not a record");
  await writeFile(join(home, ".claude/sessions/9.json"), "{half-written");
  const calls = [];
  const exec = async (cmd, args) => {
    calls.push([cmd, ...args]);
    return { stdout: ` 6571 ${START}     claude HC_TERMINAL_ID=t5n\n`, stderr: "", code: 0 };
  };

  const names = await loadSessionNames(exec, home);

  assert.deepEqual([...names], [["t5n", "firehose-1c"]]);
  assert.deepEqual(calls, [["/usr/bin/env", "TZ=UTC", "LC_ALL=C", "ps", "-E", "-o", "pid=", "-o", "lstart=", "-o", "command=", "-p", "6571"]]);
});
