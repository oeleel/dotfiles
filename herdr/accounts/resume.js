// Limit-stop markers and the resume after an account switch.
//
// claude/hooks/limit-stop-marker.sh writes one marker per session that a usage limit stopped:
// ~/.local/state/claude-limit-stops/<session_id>.json =
//   { session_id, terminal: HC_TERMINAL_ID | null, cwd, error, message, at: ISO time }.
// No `herdr` import; Herdr's exec and hc are passed in. Lane 2 (limit stop) owns this file.

export const MARKER_DIR = ".local/state/claude-limit-stops";

/** @typedef {{ session_id: string, terminal: string | null, cwd: string, error: string, message: string, at: string }} Marker */
/** @typedef {{ marker: Marker, terminal: string }} Target */

/** Every readable marker under `${home}/${MARKER_DIR}`. A missing folder is an empty list. */
export async function readMarkers(home) { throw new Error("not built: readMarkers"); }

/** Markers whose terminal is a live agent in `agents` (Herdr's agents()) with status idle or
 *  done. A marker with terminal null is matched through `sessionTerminals`
 *  (Map session_id -> terminal address). */
export function resumeTargets(markers, agents, sessionTerminals) { throw new Error("not built: resumeTargets"); }

/** Sends `prompt` to each target with `hc send <terminal> <prompt> --if idle`, deletes its marker,
 *  and returns one { terminal, session_id, ok, detail } per target. */
export async function resumeAll(targets, { hc, home, prompt }) { throw new Error("not built: resumeAll"); }
