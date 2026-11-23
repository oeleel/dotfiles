// The Accounts button in the tab bar (tabs-leo), next to Files and Changes.
// Pure: no `herdr` import. herdr-remod copies it into tabs-leo. Lane T (tab bar) owns this file.

/**
 * @typedef {{
 *   label: "Accounts", pct: string | null,
 *   level: "none" | "ok" | "near" | "limit" | "error",
 *   tip: string
 * }} TabModel
 * pct: the active account's highest window percent, rounded ("23%"), or null with no data.
 * level: none (no state yet), error (no view and an error), limit (activeAtLimit), near (a window
 *   at or above config.roomPercent), ok.
 * tip: the hover text, for example "Account 1 · main@example.com · 7d 23% · resets 2d10h", or the
 *   error.
 */

/** The button's model from the shared AccountsState (core.js), config and the last switch time. */
export function tabModel(state, config, switchedAt, nowMs) { throw new Error("not built: tabModel"); }
