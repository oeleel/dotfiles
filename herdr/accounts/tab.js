// The Accounts button in the tab bar (tabs-leo), next to Files and Changes.
// Pure: no `herdr` import. herdr-remod copies it into tabs-leo. Lane T (tab bar) owns this file.

import { activeAtLimit, markersSince, windowWord, formatCountdown } from "./accounts.js";

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

const LABEL = "Accounts";
const WAITING_TIP = "No account usage yet: the first cswap poll has not finished";
const NO_ACTIVE_TIP = "cswap reports no active account";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const model = (pct, level, tip) => Object.freeze({ label: LABEL, pct, level, tip });

// The window with the highest known percent; 7d wins a tie, since cswap's order puts it first.
function highest(windows) {
  return windows.filter((w) => w.pct !== null).reduce((top, w) => (top && top.pct >= w.pct ? top : w), null);
}

/** The button's model when the config, the poll or the model itself failed, so the tab bar still
 *  draws the button. `error` is an Error or a message. */
export function errorModel(error) {
  return model(null, "error", error?.message ?? String(error));
}

/** The button's model from the shared AccountsState (core.js), config and the last switch time.
 *  switchedAt: ms epoch, or null or undefined when no switch was recorded (every marker counts).
 *  config is read only when state holds a view. */
export function tabModel(state, config, switchedAt, nowMs) {
  if (!state) return model(null, "none", WAITING_TIP);
  if (!state.view) return state.error ? errorModel(state.error) : model(null, "none", WAITING_TIP);
  const row = state.view.rows.find((r) => r.active);
  if (!row) return model(null, "ok", [NO_ACTIVE_TIP, state.error].filter(Boolean).join(" · "));
  const top = highest(row.windows);
  const limit = activeAtLimit(state.view, markersSince(state.markers, switchedAt ?? 0));
  const level = limit ? "limit" : top && top.pct >= config.roomPercent ? "near" : "ok";
  const pct = top ? `${Math.round(top.pct)}%` : null;
  const tip = [
    `Account ${row.number}`,
    row.label,
    top && `${top.name} ${pct}`,
    top?.resetsAtMs != null && `resets ${formatCountdown(top.resetsAtMs - nowMs)}`,
    limit && `hit its ${windowWord(limit.window)} limit`,
    limit?.stopped && `${plural(limit.stopped, "agent")} stopped`,
    row.note,
    state.error,
  ];
  return model(pct, level, tip.filter(Boolean).join(" · "));
}
