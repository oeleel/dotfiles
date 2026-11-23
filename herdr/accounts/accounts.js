// Claude accounts panel: pure logic over `cswap list --json` and `cswap switch --json`.
//
// No `herdr` import, so node --test can load it (the pattern of agents-menu/sessions.js).
// Contract: the plan "switch Claude accounts from a Herdr panel, on claude-swap" and the
// sample output in fixtures/cswap-list.json. Lane 1 (panel) owns this file.

/** @typedef {{ name: "5h" | "7d", pct: number | null, resetsAtMs: number | null }} Window */
/**
 * @typedef {{
 *   number: number, label: string, email: string, plan: string | null, active: boolean,
 *   status: string, windows: Window[], ageSeconds: number | null,
 *   hasRoom: boolean, atLimit: boolean, note: string | null
 * }} Row
 */
/** @typedef {{ activeNumber: number | null, rows: Row[] }} ListView */

/** Validates config.json. Throws an Error that names the bad key and value. */
export function loadConfig(raw) { throw new Error("not built: loadConfig"); }

/** The command for one cswap call, with CLAUDE_CONFIG_DIR and CLAUDE_SECURESTORAGE_CONFIG_DIR
 *  unset. Returns [command, args] for Herdr's exec. */
export function cswapCommand(home, args) { throw new Error("not built: cswapCommand"); }

/** `cswap list --json` stdout to a ListView. Throws on an error envelope or schemaVersion != 1. */
export function parseList(stdout, config) { throw new Error("not built: parseList"); }

/** The account to suggest when the active one is at its limit, or null. */
export function suggest(view, config) { throw new Error("not built: suggest"); }

/** The active row and the window at its limit, or null. */
export function activeAtLimit(view, config) { throw new Error("not built: activeAtLimit"); }

/** `cswap switch N --json` stdout and exit code to { ok, to, message }. */
export function parseSwitch(stdout, code) { throw new Error("not built: parseSwitch"); }

/** Milliseconds to "2d4h", "3h12m", "45m" or "now". */
export function formatCountdown(ms) { throw new Error("not built: formatCountdown"); }
