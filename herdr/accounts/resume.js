// Limit-stop markers and the resume after an account switch.
//
// claude/hooks/limit-stop-marker.sh writes one marker per session that a usage limit stopped:
// ~/.local/state/claude-limit-stops/<session_id>.json =
//   { session_id, terminal: HC_TERMINAL_ID | null, cwd, error, message, at: ISO time }.
// The hook deletes it when the session next finishes a turn normally (Stop).
// No `herdr` import; Herdr's exec and hc are passed in. Lane 2 (limit stop) owns this file.
// Herdr denies a mod's fs calls outside ~/.config/herdr-app, so every file read and delete here
// goes through exec, which runs programs with the user's real environment.

export const MARKER_DIR = ".local/state/claude-limit-stops";

const REGISTRY = ".claude/sessions";
// Claude Code records procStart as ps prints it in UTC and English ("Sun Nov 22 21:07:05 2026").
const PS_ENV = ["TZ=UTC", "LC_ALL=C"];
// macOS ps: -E appends the environment to the command, one line per process.
const PS_ARGS = ["ps", "-E", "-o", "pid=", "-o", "lstart=", "-o", "command="];
const PS_LINE = /^\s*(\d+)\s+(\S+\s+\S+\s+\d+\s+[\d:]+\s+\d{4})\s+(.*)$/;
const TERMINAL_VAR = /(?:^|\s)HC_TERMINAL_ID=(\S+)/g;
// The hook names a marker after its session id and accepts only these characters.
const SESSION_ID = /^[A-Za-z0-9_-]+$/;
// Typing into a working agent would queue the prompt as a new message. Every other status is
// resumable: Claude Code 2.1.330 reports a turn that an API error ended as `error`, which
// agents() has no word for (the shipped agents mod counts it as blocked), and `hc send` itself
// refuses a terminal that waits on a person.
const BUSY = "working";
const RM = "/bin/rm";
const SH = "/bin/sh";
// RS (0x1e): valid JSON text cannot hold a raw control character, so it cannot split a file.
const SEP = "\x1e";
// Prints "<path>RS<contents>RS" for each regular *.json file in "$1", in glob order. A missing
// folder or no match leaves the pattern unexpanded, which -f skips. A file deleted after the -f
// test prints empty contents, which fail to parse. Dot files (the hook's temp files) never match.
const READ_JSON_FILES =
  'for f in "$1"/*.json; do [ -f "$f" ] || continue; printf "%s\\036" "$f"; cat "$f" 2>/dev/null; printf "\\036"; done';

/** @typedef {{ session_id: string, terminal: string | null, cwd: string | null, error: string, message: string, at: string }} Marker */
/** @typedef {{ marker: Marker, terminal: string }} Target */

const squash = (s) => s.replace(/\s+/g, " ").trim();
const isText = (v) => typeof v === "string" && v !== "";

/** A marker the hook wrote, under the file name it chose. */
const isMarker = (m, file) =>
  m !== null && typeof m === "object" &&
  isText(m.session_id) && SESSION_ID.test(m.session_id) && file === `${m.session_id}.json` &&
  (m.terminal === null || isText(m.terminal)) &&
  (m.cwd === null || typeof m.cwd === "string") &&
  isText(m.error) && typeof m.message === "string" && isText(m.at);

/** Every *.json file in `dir` that parses, as [{ name, value }] sorted by file name, from one
 *  exec call. Unreadable and half-written files are skipped: the next poll sees them settled. */
async function readJsonFiles(exec, dir) {
  const r = await exec(SH, ["-c", READ_JSON_FILES, "sh", dir]);
  if (r.code !== 0) throw new Error(`reading ${dir}/*.json: ${SH} exited ${r.code}: ${r.stderr.trim()}`);
  const parts = r.stdout.split(SEP);
  const files = [];
  // The output ends with SEP, so the last part is empty and pairs are (path, contents).
  for (let i = 0; i + 1 < parts.length; i += 2) {
    let value;
    try { value = JSON.parse(parts[i + 1]); } catch { continue; }
    files.push({ name: parts[i].slice(parts[i].lastIndexOf("/") + 1), value });
  }
  return files.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

/** Every valid marker under `${home}/${MARKER_DIR}`, in file name order. A missing folder (no
 *  limit has stopped a session yet) is an empty list. `exec` is Herdr's (or a stand-in). */
export async function readMarkers(exec, home) {
  const files = await readJsonFiles(exec, `${home}/${MARKER_DIR}`);
  return files.filter(({ name, value }) => isMarker(value, name)).map(({ value }) => value);
}

/** `ps` output (PS_ARGS) to Map pid -> { start, terminal }. The environment comes after the
 *  arguments, so the last HC_TERMINAL_ID wins over any copy inside a prompt argument. */
function parseProcesses(stdout) {
  const procs = new Map();
  for (const line of stdout.split("\n")) {
    const m = PS_LINE.exec(line);
    if (!m) continue;
    const terminal = [...m[3].matchAll(TERMINAL_VAR)].at(-1)?.[1] ?? null;
    procs.set(Number(m[1]), { start: squash(m[2]), terminal });
  }
  return procs;
}

/** Map session_id -> Herdr terminal address for the running Claude sessions, from
 *  ~/.claude/sessions/<pid>.json (field `sessionId`) and `ps -E` (HC_TERMINAL_ID), the method of
 *  herdr/agents-menu/sessions.js. A mod cannot import another mod's files, so this keeps its own
 *  copy of that logic. `exec` is Herdr's (or a stand-in). */
export async function loadSessionTerminals(exec, home) {
  const records = (await readJsonFiles(exec, `${home}/${REGISTRY}`))
    .map(({ value }) => value)
    .filter((r) => r !== null && typeof r === "object");
  const pids = records.map((r) => r.pid).filter(Number.isInteger);
  if (!pids.length) return new Map();
  const ps = await exec("/usr/bin/env", [...PS_ENV, ...PS_ARGS, "-p", pids.join(",")]);
  const procs = parseProcesses(ps.stdout);
  const terminals = new Map();
  for (const r of records) {
    const p = procs.get(r.pid);
    // A record left behind by a crash can name a PID that another program uses now.
    if (!p || (r.procStart && p.start !== squash(r.procStart))) continue;
    // Background jobs inherit HC_TERMINAL_ID from the terminal that started them.
    if (r.kind !== "interactive" || !p.terminal || !isText(r.sessionId)) continue;
    terminals.set(r.sessionId, p.terminal);
  }
  return terminals;
}

/** Markers whose terminal is a live agent in `agents` (Herdr's agents()) that is not working.
 *  A marker with terminal null is matched through `sessionTerminals` (Map session_id ->
 *  terminal address). A marker is skipped when its terminal now runs a different Claude session
 *  (the stopped one ended, or /clear started a new one). One target per terminal, the newest. */
export function resumeTargets(markers, agents, sessionTerminals) {
  const status = new Map(agents.map((a) => [a.address, a.status]));
  const running = new Map();
  for (const [session, terminal] of sessionTerminals) running.set(terminal, [...(running.get(terminal) ?? []), session]);
  const byTerminal = new Map();
  for (const marker of markers) {
    const terminal = marker.terminal ?? sessionTerminals.get(marker.session_id);
    if (!terminal || !status.has(terminal) || status.get(terminal) === BUSY) continue;
    if (running.has(terminal) && !running.get(terminal).includes(marker.session_id)) continue;
    const kept = byTerminal.get(terminal);
    if (!kept || kept.marker.at < marker.at) byTerminal.set(terminal, { marker, terminal });
  }
  return [...byTerminal.values()];
}

async function resumeOne({ marker, terminal }, { hc, exec, home, prompt }) {
  const base = { terminal, session_id: marker.session_id };
  let sent;
  try {
    // No `--if idle`: it matches only status idle, and a limit stop leaves the agent at error.
    sent = await hc(["send", terminal, prompt]);
  } catch (e) {
    return { ...base, ok: false, detail: `hc send did not run: ${e}` };
  }
  if (sent.code !== 0) {
    // The marker stays, so the next switch tries this session again.
    return { ...base, ok: false, detail: `hc send exited ${sent.code}: ${(sent.stderr || sent.stdout).trim()}` };
  }
  const path = `${home}/${MARKER_DIR}/${marker.session_id}.json`;
  try {
    const removed = await exec(RM, ["-f", "--", path]);
    if (removed.code !== 0) return { ...base, ok: true, detail: `sent; ${RM} ${path} exited ${removed.code}: ${removed.stderr.trim()}` };
  } catch (e) {
    return { ...base, ok: true, detail: `sent; ${RM} ${path} did not run: ${e}` };
  }
  return { ...base, ok: true, detail: "sent" };
}

/** Sends `prompt` to each target with `hc send <terminal> <prompt>` and returns one
 *  { terminal, session_id, ok, detail } per target, in order. A sent prompt deletes its marker
 *  with `exec` (Herdr's, or a stand-in); a failed one keeps it for the next switch. Targets run
 *  at once, so one terminal that waits on a person's draft does not hold up the others. */
export async function resumeAll(targets, { hc, exec, home, prompt }) {
  if (typeof hc !== "function") throw new Error(`resumeAll: hc must be a function, got ${typeof hc}`);
  if (typeof exec !== "function") throw new Error(`resumeAll: exec must be a function, got ${typeof exec}`);
  // The session id becomes part of a path that rm deletes.
  const bad = targets.find((t) => !SESSION_ID.test(t.marker?.session_id ?? ""));
  if (bad) throw new Error(`resumeAll: unsafe session_id ${JSON.stringify(bad.marker?.session_id)}`);
  return Promise.all(targets.map((t) => resumeOne(t, { hc, exec, home, prompt })));
}
