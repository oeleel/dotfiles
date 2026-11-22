// Claude Code session names by Herdr terminal, for the agents list's hover.
//
// Claude Code registers each running session in ~/.claude/sessions/<pid>.json, with the name
// that other sessions use to message it. The session's process carries HC_TERMINAL_ID, the
// Herdr terminal it runs in, in its environment. herdr-remod copies this file into the
// agents-menu mod as it is.

import { readdir, readFile } from "fs/promises";

const REGISTRY = ".claude/sessions";
// Claude Code records procStart as ps prints it in UTC and English ("Sun Nov 22 21:07:05 2026").
const PS_ENV = ["TZ=UTC", "LC_ALL=C"];
// macOS ps: -E appends the environment to the command, one line per process.
const PS_ARGS = ["ps", "-E", "-o", "pid=", "-o", "lstart=", "-o", "command="];
const PS_LINE = /^\s*(\d+)\s+(\S+\s+\S+\s+\d+\s+[\d:]+\s+\d{4})\s+(.*)$/;
const TERMINAL_VAR = /(?:^|\s)HC_TERMINAL_ID=(\S+)/g;

const squash = (s) => s.replace(/\s+/g, " ").trim();

/** `ps` output (PS_ARGS) to Map pid -> { start, terminal }. The environment comes after the
 *  arguments, so the last HC_TERMINAL_ID wins over any copy inside a prompt argument. */
export function parseProcesses(stdout) {
  const procs = new Map();
  for (const line of stdout.split("\n")) {
    const m = PS_LINE.exec(line);
    if (!m) continue;
    const terminal = [...m[3].matchAll(TERMINAL_VAR)].at(-1)?.[1] ?? null;
    procs.set(Number(m[1]), { start: squash(m[2]), terminal });
  }
  return procs;
}

/** Registry records and live processes to Map terminal address -> session name.
 *  A record counts only while its process runs with the recorded start time: a record left
 *  behind by a crash can name a PID that another program uses now. */
export function sessionNames(records, procs) {
  const live = records.filter((r) => {
    const p = procs.get(r.pid);
    return p && (!r.procStart || p.start === squash(r.procStart));
  });
  const jobs = new Map(live.filter((r) => r.jobId).map((r) => [r.jobId, r]));
  const names = new Map();
  // Oldest first, so the newest session in a terminal wins.
  for (const r of [...live].sort((x, y) => (x.startedAt ?? 0) - (y.startedAt ?? 0))) {
    const terminal = procs.get(r.pid).terminal;
    // Background jobs inherit HC_TERMINAL_ID from the terminal that started them.
    if (r.kind !== "interactive" || !terminal) continue;
    // A parked session hands its work to a background job, and peers message the job.
    const name = (jobs.get(r.parkedJobId) ?? r).name;
    if (name) names.set(terminal, name);
  }
  return names;
}

/** Reads the registry and asks ps about its processes. `exec` is Herdr's (or a stand-in). */
export async function loadSessionNames(exec, home) {
  const dir = `${home}/${REGISTRY}`;
  const records = [];
  for (const file of await readdir(dir)) {
    if (!file.endsWith(".json")) continue;
    // A session that ends between readdir and readFile, or a file mid-write: the next poll sees it.
    try { records.push(JSON.parse(await readFile(`${dir}/${file}`, "utf8"))); } catch { continue; }
  }
  const pids = records.map((r) => r.pid).filter(Number.isInteger);
  if (!pids.length) return new Map();
  const ps = await exec("/usr/bin/env", [...PS_ENV, ...PS_ARGS, "-p", pids.join(",")]);
  return sessionNames(records, parseProcesses(ps.stdout));
}
