// Accounts state shared by two mods: the tab bar (tabs-leo, always running, shows the Accounts
// button) and the accounts panel (runs only after it was first shown). Herdr starts a mod copy
// the first time it shows, so the tab bar does the polling; the panel polls only when the shared
// state is stale (the tab bar is missing or broken). One shared announced-id keeps the limit
// toast and sound to one per limit event across both mods.
//
// No `herdr` import: Herdr's functions come in `deps`, so node --test can load it.
// herdr-remod copies this file, accounts.js and resume.js into tabs-leo as they are.
// Lane P (core and panel) owns this file.

import { loadConfig, cswapCommand, parseList, switchBlocker, suggest, activeAtLimit, markersSince, windowWord } from "./accounts.js";
import { readMarkers } from "./resume.js";

// Herdr shared() keys. shared() is saved, and setShared() re-renders every mod.
export const STATE_KEY = "accounts.state";
export const SWITCHED_AT_KEY = "accounts.switchedAt";
export const ANNOUNCED_KEY = "accounts.announced";

/**
 * @typedef {{
 *   view: import("./accounts.js").ListView | null,
 *   error: string | null,
 *   markers: import("./resume.js").Marker[],
 *   polledAt: number
 * }} AccountsState
 * view: the parsed `cswap list --json` (parseList), or null when the poll failed.
 * error: why the poll or the marker read failed, or null.
 * markers: every limit-stop marker (readMarkers).
 * polledAt: ms epoch of the poll (when it started).
 */

/**
 * @typedef {{
 *   exec: Function, home: string, appHome: string, readTextFile: Function,
 *   shared: Function, setShared: Function, notify: Function, playSound: Function,
 *   now: () => number
 * }} Deps
 */

// The accounts mod's config, which the tab bar reads too.
const CONFIG_FILE = "mods/accounts/config.json";
// cswap list may fetch usage for every account before it answers.
const LIST_TIMEOUT_MS = 60_000;
// /usr/bin/env exits 127 when it cannot find the program: cswap is not installed yet.
const NOT_FOUND_EXIT = 127;
const INSTALL_HINT = "cswap is not installed: run uv tool install claude-swap, then cswap add";
// Each copy ticks every pollSeconds and polledAt is taken when a poll starts, so the copy that
// polled last sees an age of about pollSeconds on its next tick. A timer that fires a few ms
// early must still find that state stale, or the poller would skip every other tick.
const TICK_SLACK_MS = 1_000;
const MINUTE_MS = 60_000;

const message = (e) => e?.message ?? String(e);
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const isObject = (v) => typeof v === "object" && v !== null && !Array.isArray(v);
// The window with the highest reading; windows lists 7d first, and the sort keeps it first on a tie.
const fullest = (windows) => [...windows].sort((a, b) => (b.pct ?? -1) - (a.pct ?? -1))[0];

/** config.json from `${appHome}/mods/accounts/config.json`, validated by loadConfig. Throws with
 *  the path when the file is missing or invalid. */
export async function readConfig(deps) {
  const path = `${deps.appHome}/${CONFIG_FILE}`;
  const text = await deps.readTextFile(path);
  if (text === null) throw new Error(`config.json not found at ${path}`);
  let raw;
  try {
    raw = JSON.parse(text);
  } catch (e) {
    throw new Error(`config.json at ${path} is not JSON: ${message(e)}`);
  }
  try {
    return loadConfig(raw);
  } catch (e) {
    throw new Error(`${message(e)} (${path})`);
  }
}

/** True when `state` is missing or older than config.pollSeconds, so this copy should poll.
 *  "Older" allows TICK_SLACK_MS for a timer that fires early. A state with no usable polledAt,
 *  or one from the future (the clock went back), is stale too. */
export function isStale(state, config, nowMs) {
  if (!isObject(state) || !Number.isFinite(state.polledAt)) return true;
  const age = nowMs - state.polledAt;
  return age < 0 || age >= config.pollSeconds * 1000 - TICK_SLACK_MS;
}

async function readList(deps, config) {
  try {
    const [cmd, args] = cswapCommand(deps.home, ["list", "--json"]);
    const r = await deps.exec(cmd, args, { timeout: LIST_TIMEOUT_MS });
    // A missing cswap prints only to stderr ("env: ...: No such file or directory").
    if (r.code === NOT_FOUND_EXIT) throw new Error(INSTALL_HINT);
    if (r.code !== 0 && !r.stdout.trim()) throw new Error(`cswap list exited ${r.code}: ${r.stderr.trim() || "no output"}`);
    return { view: parseList(r.stdout, config), error: null };
  } catch (e) {
    return { view: null, error: message(e) };
  }
}

async function readStops(deps) {
  try {
    return { markers: await readMarkers(deps.exec, deps.home), error: null };
  } catch (e) {
    return { markers: [], error: `limit-stop markers: ${message(e)}` };
  }
}

/** Runs `cswap list --json` and reads the markers. Never throws: a failure goes in `error`.
 *  cswap not installed (exit 127) gives the install hint. */
export async function pollState(deps, config) {
  const polledAt = deps.now();
  const [list, stops] = await Promise.all([readList(deps, config), readStops(deps)]);
  const errors = [list.error, stops.error].filter(Boolean);
  return Object.freeze({ view: list.view, error: errors.length ? errors.join("; ") : null, markers: stops.markers, polledAt });
}

/** The active account's limit in `state` (activeAtLimit), counting only the markers written
 *  after `switchedAt`, or null. Null without a view. */
export function stateLimit(state, switchedAt) {
  if (!isObject(state) || !state.view) return null;
  return activeAtLimit(state.view, markersSince(state.markers ?? [], switchedAt));
}

/** "Account 1 hit its weekly limit · 3 agents stopped", for the toast and the panel's banner. */
export function limitTitle(limit) {
  const stopped = limit.stopped ? ` · ${plural(limit.stopped, "agent")} stopped` : "";
  return `Account ${limit.row.number} hit its ${windowWord(limit.window)} limit${stopped}`;
}

// One limit event: the active account, the window at its limit, and when that window resets.
// A marker often flags the limit before cswap's reading reaches 100%; the window then comes from
// the marker's message, or is the fullest one, so the id holds once cswap catches up. The reset
// is rounded to the minute so that a reading which moves the reset by under 30 s keeps the id
// (assumed: cswap passes Anthropic's resetsAt through raw, and its jitter is not measured).
function limitId(limit) {
  const { row } = limit;
  const w = limit.window ? row.windows.find((x) => x.name === limit.window) : fullest(row.windows);
  const name = limit.window ?? w?.name ?? "usage";
  const reset = typeof w?.resetsAtMs === "number" ? new Date(Math.round(w.resetsAtMs / MINUTE_MS) * MINUTE_MS).toISOString() : "unknown";
  return `${row.number}:${name}:${reset}`;
}

/** The limit to announce now, or null: the active account is at its limit (activeAtLimit with
 *  markersSince(state.markers, switchedAt)) and this event's id differs from `announced`.
 *  Returns { id, title, body }. The id is account number, window and reset minute, so it stays
 *  the same across polls of one event and changes after the window resets. */
export function limitAnnouncement(state, config, switchedAt, announced) {
  const limit = stateLimit(state, switchedAt);
  if (!limit) return null;
  const id = limitId(limit);
  if (id === announced) return null;
  const pick = suggest(state.view, config);
  const body = switchBlocker(state.view) ?? (pick ? `Suggested: account ${pick.number} (${pick.label}).` : `No other account is under ${config.roomPercent}%.`);
  return Object.freeze({ id, title: limitTitle(limit), body });
}

/** Polls now, whatever the age of the shared state, and publishes to STATE_KEY unless another
 *  copy already published a poll that started later. For the panel right after a switch, and
 *  for tick. Never throws. */
export async function refresh(deps, config) {
  try {
    const previous = deps.shared(STATE_KEY);
    const state = await pollState(deps, config);
    // Once per distinct failure, not every poll.
    if (state.error && state.error !== previous?.error) console.log(`accounts: ${state.error}`);
    // A tab bar poll that started before a switch can finish after the panel's poll from after it.
    const latest = deps.shared(STATE_KEY);
    if (isObject(latest) && latest.polledAt > state.polledAt) return;
    deps.setShared(STATE_KEY, state);
  } catch (e) {
    console.log(`accounts: refresh failed: ${message(e)}`);
  }
}

function announce(deps, config) {
  const switchedAt = Number(deps.shared(SWITCHED_AT_KEY)) || 0;
  const a = limitAnnouncement(deps.shared(STATE_KEY), config, switchedAt, deps.shared(ANNOUNCED_KEY) ?? null);
  if (!a) return;
  // Claimed before the toast, so the other mod's tick never announces the same event.
  deps.setShared(ANNOUNCED_KEY, a.id);
  deps.notify({ title: a.title, body: a.body, level: "warning" });
  deps.playSound("blocked");
}

/** One timer tick for either mod: poll when stale, publish to STATE_KEY, announce once
 *  (setShared(ANNOUNCED_KEY, id), then notify + playSound("blocked")). Never throws.
 *  The caller keeps one tick at a time per copy. */
export async function tick(deps, config) {
  try {
    if (isStale(deps.shared(STATE_KEY), config, deps.now())) await refresh(deps, config);
    announce(deps, config);
  } catch (e) {
    console.log(`accounts: tick failed: ${message(e)}`);
  }
}
