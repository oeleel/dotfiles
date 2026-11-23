#!/usr/bin/env bash
# StopFailure and Stop hook: records which sessions a usage limit stopped, so the Herdr accounts
# panel (herdr/accounts/resume.js) can send them "keep working" after an account switch.
#
# StopFailure with an accepted error writes ~/.local/state/claude-limit-stops/<session_id>.json =
#   {session_id, terminal: $HC_TERMINAL_ID or null, cwd, error, message, at}.
# Stop means the session finished a turn normally, so its marker no longer applies: delete it.
# Hooks inherit the session's environment, which is where HC_TERMINAL_ID comes from.
#
# Claude Code ignores StopFailure output and exit codes, but a Stop hook's exit 2 blocks the stop
# and its stdout can be read as a decision: always exit 0 and print nothing. Runs on every turn
# end of every session, so it makes one jq call and no other forks on the Stop path.
set -uo pipefail
exec >/dev/null

readonly JQ=/usr/bin/jq
# StopFailure `error` values that mean the account ran out of usage. Claude Code 2.1.330 sends a
# plan limit ("You've hit your weekly limit · resets ...", a 429 with status rejected) as
# rate_limit. Space-separated; the StopFailure matcher in claude/settings.json lists the same
# values joined with "|".
readonly LIMIT_ERRORS=" rate_limit "
readonly MARKER_DIR="$HOME/.local/state/claude-limit-stops"
readonly MESSAGE_CHARS=300
# The session id becomes a file name: letters, digits, "_" and "-" only, so no "/" or "..".
readonly SAFE_ID='^[A-Za-z0-9_-]+$'
readonly SEP=$'\x1f'

input="$(cat 2>/dev/null || true)"
# A non-whitespace separator, so an empty field (no agent_id) does not shift the others.
IFS="$SEP" read -r event session agent error < <(
  printf '%s' "$input" | "$JQ" -r --arg sep "$SEP" \
    '[.hook_event_name, .session_id, .agent_id, .error] | map(. // "" | tostring) | join($sep)' \
    2>/dev/null
)

[[ ${session:-} =~ $SAFE_ID ]] || exit 0
# A subagent's or teammate's stop does not stop the session.
[[ -z ${agent:-} ]] || exit 0
marker="$MARKER_DIR/$session.json"

case "${event:-}" in
  Stop)
    [[ -e $marker ]] && rm -f -- "$marker"
    ;;
  StopFailure)
    [[ $LIMIT_ERRORS == *" ${error:-} "* ]] || exit 0
    mkdir -p "$MARKER_DIR" || exit 0
    # The temp name does not end in .json, so a reader never sees a half-written marker.
    tmp="$(mktemp "$MARKER_DIR/.$session.XXXXXX")" || exit 0
    if printf '%s' "$input" | "$JQ" -c --arg terminal "${HC_TERMINAL_ID:-}" \
      --argjson chars "$MESSAGE_CHARS" '{
        session_id,
        terminal: (if $terminal == "" then null else $terminal end),
        cwd: (.cwd // null),
        error,
        message: ((.last_assistant_message // "") | tostring | .[0:$chars]),
        at: (now | todate)
      }' >"$tmp" 2>/dev/null; then
      mv -f -- "$tmp" "$marker"
    else
      rm -f -- "$tmp"
    fi
    ;;
esac
exit 0
