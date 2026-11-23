// Accounts state shared by two mods: the tab bar (tabs-leo, always running, shows the Accounts
// button) and the accounts panel (runs only after it was first shown). Herdr starts a mod copy
// the first time it shows, so the tab bar does the polling; the panel polls only when the shared
// state is stale (the tab bar is missing or broken). One shared announced-id keeps the limit
// toast and sound to one per limit event across both mods.
//
// No `herdr` import: Herdr's functions come in `deps`, so node --test can load it.
// herdr-remod copies this file, accounts.js and resume.js into tabs-leo as they are.
// Lane P (core and panel) owns this file.

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
 * polledAt: ms epoch of the poll.
 */

/**
 * @typedef {{
 *   exec: Function, home: string, appHome: string, readTextFile: Function,
 *   shared: Function, setShared: Function, notify: Function, playSound: Function,
 *   now: () => number
 * }} Deps
 */

/** config.json from `${appHome}/mods/accounts/config.json`, validated by loadConfig. Throws with
 *  the path when the file is missing or invalid. */
export async function readConfig(deps) { throw new Error("not built: readConfig"); }

/** True when `state` is missing or older than config.pollSeconds, so this copy should poll. */
export function isStale(state, config, nowMs) { throw new Error("not built: isStale"); }

/** Runs `cswap list --json` and reads the markers. Never throws: a failure goes in `error`.
 *  cswap not installed (exit 127) gives the install hint. */
export async function pollState(deps, config) { throw new Error("not built: pollState"); }

/** The limit to announce now, or null: the active account is at its limit (activeAtLimit with
 *  markersSince(state.markers, switchedAt)) and this event's id differs from `announced`.
 *  Returns { id, title, body }. */
export function limitAnnouncement(state, config, switchedAt, announced) { throw new Error("not built: limitAnnouncement"); }

/** One timer tick for either mod: poll when stale, publish to STATE_KEY, announce once
 *  (notify + playSound("blocked"), then setShared(ANNOUNCED_KEY, id)). Never throws. */
export async function tick(deps, config) { throw new Error("not built: tick"); }
