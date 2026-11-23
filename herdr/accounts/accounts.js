// Claude accounts panel: pure logic over `cswap list --json` and `cswap switch --json`.
//
// No `herdr` import, so node --test can load it (the pattern of agents-menu/sessions.js).
// Contract: the plan "switch Claude accounts from a Herdr panel, on claude-swap" and the
// sample output in fixtures/cswap-list.json. Field names follow cswap's json_output.py.
// Lane 1 (panel) owns this file.

/** @typedef {{ name: "5h" | "7d", pct: number | null, resetsAtMs: number | null }} Window */
/**
 * @typedef {{
 *   number: number, label: string, email: string, plan: string | null, active: boolean,
 *   status: string, windows: Window[], stale: boolean, ageSeconds: number | null,
 *   hasRoom: boolean, atLimit: boolean, note: string | null
 * }} Row
 */
/** @typedef {{ activeNumber: number | null, rows: Row[], duplicateWarnings: string[] }} ListView */
/** @typedef {{ row: Row, window: "5h" | "7d" | null, stopped: number }} Limit */
/** @typedef {{ ok: boolean, to: number | null, message: string, warnings: string[] }} SwitchResult */

const SCHEMA_VERSION = 1;
// A window is spent at 100%: Claude Code refuses requests until it resets.
const FULL_PERCENT = 100;
// Claude Code caches the Keychain login for 30 s (zhn=30000 in 2.1.330), so a resume sent
// sooner reaches a session that still holds the old account.
const KEYCHAIN_CACHE_SECONDS = 30;
const MAX_RESUME_DELAY_SECONDS = 600;
// cswap serves from its own cache for 180 s, so polling faster than this buys nothing.
const MIN_POLL_SECONDS = 10;
const MAX_POLL_SECONDS = 3600;
const SUGGEST_ORDERS = ["soonest-weekly-reset"];
const CSWAP_PATH = ".local/bin/cswap";
// cswap follows both variables; a value inherited from the app's environment would point it
// at another config.
const CSWAP_ENV = ["-u", "CLAUDE_CONFIG_DIR", "-u", "CLAUDE_SECURESTORAGE_CONFIG_DIR"];
// cswap's JSON keys for the two windows, in the order the panel shows them.
const WINDOW_KEYS = [["sevenDay", "7d"], ["fiveHour", "5h"]];
const WINDOW_WORDS = { "7d": "weekly", "5h": "5-hour" };
const SWITCH_OK_REASONS = ["switched", "already-active", "activated"];
const SNIPPET_CHARS = 200;

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

// Each key's check answers true, or what a good value looks like.
const CONFIG_KEYS = {
  autoSwitch: (v) => v === false || (v === true ? "auto-switch is not built (Leo chose a Switch button only, plan D3); set it to false" : "must be false"),
  pollSeconds: (v) => isInteger(v, MIN_POLL_SECONDS, MAX_POLL_SECONDS) || `must be a whole number of seconds from ${MIN_POLL_SECONDS} to ${MAX_POLL_SECONDS}`,
  resumeAfterSwitch: (v) => typeof v === "boolean" || "must be true or false",
  resumePrompt: (v) => (typeof v === "string" && v.trim() !== "") || "must be a non-empty string",
  resumeDelaySeconds: (v) => isNumber(v, KEYCHAIN_CACHE_SECONDS, MAX_RESUME_DELAY_SECONDS) || `must be from ${KEYCHAIN_CACHE_SECONDS} (Claude Code's Keychain cache) to ${MAX_RESUME_DELAY_SECONDS} seconds`,
  confirmSwitch: (v) => typeof v === "boolean" || "must be true or false",
  roomPercent: (v) => (isNumber(v, 0, FULL_PERCENT) && v > 0) || `must be above 0 and at most ${FULL_PERCENT}`,
  suggestOrder: (v) => SUGGEST_ORDERS.includes(v) || `must be one of ${SUGGEST_ORDERS.join(", ")}`,
};

const isNumber = (v, min, max) => typeof v === "number" && Number.isFinite(v) && v >= min && v <= max;
const isInteger = (v, min, max) => Number.isInteger(v) && isNumber(v, min, max);
const isObject = (v) => typeof v === "object" && v !== null && !Array.isArray(v);
// JSON for strings and objects; NaN and Infinity, which JSON prints as null, by name.
const show = (v) => (typeof v === "number" ? String(v) : JSON.stringify(v) ?? String(v));
const snippet = (s) => (s.length > SNIPPET_CHARS ? `${s.slice(0, SNIPPET_CHARS)}...` : s);

/** Validates config.json (parsed). Every key is required and no other key is allowed.
 *  Throws an Error that names the bad key and value. Returns a frozen copy. */
export function loadConfig(raw) {
  if (!isObject(raw)) throw new Error(`config.json: expected an object, got ${show(raw)}`);
  for (const key of Object.keys(raw)) {
    if (!(key in CONFIG_KEYS)) throw new Error(`config.json: unknown key "${key}" (value ${show(raw[key])}); known keys: ${Object.keys(CONFIG_KEYS).join(", ")}`);
  }
  for (const [key, check] of Object.entries(CONFIG_KEYS)) {
    if (!(key in raw)) throw new Error(`config.json: "${key}" is missing`);
    const verdict = check(raw[key]);
    if (verdict !== true) throw new Error(`config.json: "${key}" is ${show(raw[key])}: ${verdict}`);
  }
  return Object.freeze({ ...raw });
}

/** The command for one cswap call, with CLAUDE_CONFIG_DIR and CLAUDE_SECURESTORAGE_CONFIG_DIR
 *  unset. Returns [command, args] for Herdr's exec. */
export function cswapCommand(home, args) {
  if (typeof home !== "string" || !home.startsWith("/")) throw new Error(`cswapCommand: home must be an absolute path, got ${show(home)}`);
  if (!Array.isArray(args) || !args.every((a) => typeof a === "string")) throw new Error(`cswapCommand: args must be strings, got ${show(args)}`);
  // An absolute path, because the app's PATH may not include ~/.local/bin.
  return ["/usr/bin/env", [...CSWAP_ENV, `${home}/${CSWAP_PATH}`, ...args]];
}

// Parses cswap's stdout, or throws naming the command and what it printed.
function parseJson(stdout, what) {
  try {
    return JSON.parse(stdout);
  } catch {
    throw new Error(`${what} printed no JSON: ${show(snippet(String(stdout).trim()))}`);
  }
}

function errorText(data) {
  const { type, message } = data.error;
  return `${type ?? "error"}: ${message ?? show(data.error)}`;
}

function parseWindow(raw, name, number) {
  if (!isObject(raw)) throw new Error(`cswap list: account ${number} ${name} window is ${show(raw)}, expected an object`);
  const { pct, resetsAt } = raw;
  if (pct !== null && !(typeof pct === "number" && Number.isFinite(pct))) throw new Error(`cswap list: account ${number} ${name} pct is ${show(pct)}, expected a number or null`);
  let resetsAtMs = null;
  if (resetsAt !== undefined && resetsAt !== null) {
    resetsAtMs = Date.parse(resetsAt);
    if (Number.isNaN(resetsAtMs)) throw new Error(`cswap list: account ${number} ${name} resetsAt is ${show(resetsAt)}, expected an ISO time`);
  }
  return Object.freeze({ name, pct, resetsAtMs });
}

function parseWindows(usage, number) {
  if (usage === null || usage === undefined) return [];
  if (!isObject(usage)) throw new Error(`cswap list: account ${number} usage is ${show(usage)}, expected an object or null`);
  return WINDOW_KEYS.filter(([key]) => usage[key] !== undefined).map(([key, name]) => parseWindow(usage[key], name, number));
}

// What a row says when cswap has no usage for it. Each fix is cswap's own advice.
function statusNote(status, account) {
  const n = account.number;
  switch (status) {
    case "ok": return null;
    case "relogin_required": return `relogin required: claude auth login, then cswap add --slot ${n}`;
    case "token_expired": return "token expired: cswap renews it on a later poll";
    case "api_key": return "API key login: no usage limits to show";
    case "keychain_unavailable": return "Keychain locked or denied: unlock it, then wait for the next poll";
    case "foreign_credential": return "the live login belongs to another account: run cswap list in a terminal";
    case "no_credentials": return `no stored login: claude auth login, then cswap add --slot ${n}`;
    case "unavailable": return account.usageError ? `usage unavailable (${account.usageError})` : "usage unavailable";
    // A status newer than this panel: shown by name, and the row never counts as having room.
    default: return `unknown cswap status ${show(status)}`;
  }
}

function parseAccount(account, config) {
  if (!isObject(account)) throw new Error(`cswap list: account entry is ${show(account)}, expected an object`);
  const { number, email, usageStatus: status } = account;
  if (!Number.isInteger(number)) throw new Error(`cswap list: account number is ${show(number)}, expected a whole number`);
  if (typeof email !== "string") throw new Error(`cswap list: account ${number} email is ${show(email)}, expected a string`);
  if (typeof status !== "string") throw new Error(`cswap list: account ${number} usageStatus is ${show(status)}, expected a string`);
  const ok = status === "ok";
  // A row without usage may still carry the last good reading: shown, never decided on.
  const stale = !ok && isObject(account.lastGoodUsage);
  const windows = parseWindows(ok ? account.usage : stale ? account.lastGoodUsage : null, number);
  const ageSeconds = ok ? account.usageAgeSeconds : account.lastGoodAgeSeconds;
  // An unknown pct is no proof of room; an account with no window has nothing to prove it.
  const hasRoom = ok && windows.length > 0 && windows.every((w) => w.pct !== null && w.pct < config.roomPercent);
  const atLimit = ok && windows.some((w) => w.pct !== null && w.pct >= FULL_PERCENT);
  return Object.freeze({
    number,
    label: typeof account.alias === "string" && account.alias !== "" ? account.alias : email,
    email,
    plan: account.plan?.label ?? null,
    active: account.active === true,
    status,
    windows: Object.freeze(windows),
    stale,
    ageSeconds: typeof ageSeconds === "number" ? ageSeconds : null,
    hasRoom,
    atLimit,
    note: statusNote(status, account),
  });
}

/** `cswap list --json` stdout to a ListView. Throws on an error envelope or schemaVersion != 1.
 *  Keeps cswap's top-level `duplicateAccountWarnings` (absent when clean) for switchBlocker. */
export function parseList(stdout, config) {
  const data = parseJson(stdout, "cswap list");
  if (!isObject(data)) throw new Error(`cswap list: printed ${show(data)}, expected an object`);
  if (data.error) throw new Error(`cswap list: ${errorText(data)}`);
  if (data.schemaVersion !== SCHEMA_VERSION) throw new Error(`cswap list: schemaVersion is ${show(data.schemaVersion)}, the panel reads only ${SCHEMA_VERSION}`);
  if (!Array.isArray(data.accounts)) throw new Error(`cswap list: accounts is ${show(data.accounts)}, expected a list`);
  const warnings = data.duplicateAccountWarnings ?? [];
  if (!Array.isArray(warnings)) throw new Error(`cswap list: duplicateAccountWarnings is ${show(warnings)}, expected a list`);
  return Object.freeze({
    activeNumber: Number.isInteger(data.activeAccountNumber) ? data.activeAccountNumber : null,
    rows: Object.freeze(data.accounts.map((a) => parseAccount(a, config))),
    duplicateWarnings: Object.freeze(warnings.map(String)),
  });
}

/** The reason no switch may run now, or null. cswap issue #565: Claude Desktop can relabel
 *  ~/.claude.json, so the live login belongs to another slot, and a switch would save one
 *  account's login into the other's slot. */
export function switchBlocker(view) {
  const foreign = view.rows.filter((r) => r.status === "foreign_credential").map((r) => r.number);
  if (foreign.length) return `Switch blocked: the live login does not match account ${foreign.join(", ")}; run \`cswap list\` in a terminal`;
  if (!view.duplicateWarnings.length) return null;
  // cswap writes "Account-1 and Account-3 hold the same credential ...".
  const named = [...new Set(view.duplicateWarnings.flatMap((w) => [...w.matchAll(/Account-(\d+)/g)].map((m) => m[1])))];
  const which = named.length ? ` (accounts ${named.join(", ")})` : "";
  return `Switch blocked: cswap reports two slots with one login${which}; run \`cswap list\` in a terminal`;
}

const weeklyReset = (row) => row.windows.find((w) => w.name === "7d")?.resetsAtMs ?? Infinity;

/** The account to suggest when the active one is at its limit, or null. "soonest-weekly-reset":
 *  among the other accounts with room and status ok, the one whose 7-day window resets first,
 *  so weekly room that would expire unused goes first; ties go to the lowest number. */
export function suggest(view, config) {
  if (!SUGGEST_ORDERS.includes(config.suggestOrder)) throw new Error(`suggest: suggestOrder is ${show(config.suggestOrder)}, expected one of ${SUGGEST_ORDERS.join(", ")}`);
  const candidates = view.rows.filter((r) => !r.active && r.status === "ok" && r.hasRoom);
  const sorted = [...candidates].sort((a, b) => weeklyReset(a) - weeklyReset(b) || a.number - b.number);
  return sorted[0] ?? null;
}

// Claude Code's stop message names the window: "You've hit your weekly limit · resets ...".
function markerWindow(markers) {
  const text = markers.map((m) => m.message ?? "").join("\n");
  if (/weekly|7-day/i.test(text)) return "7d";
  if (/5-hour|five-hour|session limit/i.test(text)) return "5h";
  return null;
}

/** The active row and the window at its limit, or null. The active account is at its limit
 *  when cswap reports a window at 100%, or when limit-stop markers (resume.js readMarkers)
 *  exist, since cswap's reading can be minutes old. `stopped` counts the markers. */
export function activeAtLimit(view, markers = []) {
  const row = view.rows.find((r) => r.active);
  if (!row) return null;
  // windows lists 7d first: when both are spent, the weekly one is the longer wait.
  const full = row.atLimit ? row.windows.find((w) => w.pct !== null && w.pct >= FULL_PERCENT) : null;
  if (!full && !markers.length) return null;
  return Object.freeze({ row, window: full?.name ?? markerWindow(markers), stopped: markers.length });
}

/** The markers written after `sinceMs` (the panel's last switch): older ones were stopped by
 *  the previous account, so they say nothing about the active one. They still get resumed.
 *  A marker whose `at` does not parse is kept: a false alarm costs less than a missed limit. */
export function markersSince(markers, sinceMs) {
  return markers.filter((m) => {
    const at = Date.parse(m.at);
    return Number.isNaN(at) || at > sinceMs;
  });
}

/** "weekly" or "5-hour" for a window name; "usage" when it is unknown. */
export function windowWord(name) {
  return WINDOW_WORDS[name] ?? "usage";
}

/** `cswap switch N --json` stdout and exit code to { ok, to, message, warnings }. Never throws:
 *  the switch has run (or not) by now, so every failure becomes a message to show. */
export function parseSwitch(stdout, code) {
  const fail = (message, warnings = []) => Object.freeze({ ok: false, to: null, message, warnings });
  let data;
  try {
    data = parseJson(stdout, "cswap switch");
  } catch (e) {
    return fail(`${e.message} (exit ${code})`);
  }
  if (!isObject(data)) return fail(`cswap switch printed ${show(data)} (exit ${code})`);
  if (data.error) return fail(`cswap switch: ${errorText(data)}`);
  if (data.schemaVersion !== SCHEMA_VERSION) return fail(`cswap switch: schemaVersion is ${show(data.schemaVersion)}, the panel reads only ${SCHEMA_VERSION}`);
  if (code !== 0) return fail(`cswap switch exited ${code}: ${data.message ?? show(data)}`);
  const warnings = Array.isArray(data.warnings) ? data.warnings.map(String) : [];
  if (!SWITCH_OK_REASONS.includes(data.reason) || !Number.isInteger(data.to?.number)) {
    return fail(`cswap switch did not switch (reason ${show(data.reason)}): ${data.message ?? ""}`.trim(), warnings);
  }
  return Object.freeze({ ok: true, to: data.to.number, message: data.message ?? `Switched to ${data.to.number}`, warnings });
}

/** Milliseconds to "2d4h", "3h12m", "45m" or "now". */
export function formatCountdown(ms) {
  if (typeof ms !== "number" || !Number.isFinite(ms)) throw new Error(`formatCountdown: ms is ${show(ms)}, expected a finite number`);
  if (ms < MINUTE_MS) return "now";
  const days = Math.floor(ms / DAY_MS);
  const hours = Math.floor((ms % DAY_MS) / HOUR_MS);
  const minutes = Math.floor((ms % HOUR_MS) / MINUTE_MS);
  if (days > 0) return `${days}d${hours}h`;
  if (hours > 0) return `${hours}h${minutes}m`;
  return `${minutes}m`;
}
