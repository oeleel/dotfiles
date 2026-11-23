#!/usr/bin/env bash
# PreToolUse hook on Skill: keeps third-party design skills out of n2o work. Under ~/N2O the
# n2o-kit skills (framework-page, diagram, how-it-works) own page design, and the taste skill's
# house rules and Stop gate (one section per screen, no captions under visuals, its own copy
# voice) contradict them. Blocks only Claude's own Skill calls; a typed /<skill> still runs.
set -uo pipefail
readonly N2O_ROOT="$HOME/N2O"
readonly BLOCKED_SKILLS=" design-taste-frontend "

input="$(cat 2>/dev/null || true)"
skill="$(printf '%s' "$input" | jq -r '.tool_input.skill // empty' 2>/dev/null || true)"
skill="${skill#/}"
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)"

[[ -z $skill || $BLOCKED_SKILLS != *" $skill "* ]] && exit 0
case "${cwd:-$PWD}/" in
  "$N2O_ROOT"/*) ;;
  *) exit 0 ;;
esac

jq -n --arg s "$skill" '{hookSpecificOutput: {
  hookEventName: "PreToolUse",
  permissionDecision: "deny",
  permissionDecisionReason: "\($s) is off under ~/N2O: the n2o-kit skills (framework-page, diagram, how-it-works) own page design here. Leo can type /\($s) to run it anyway."
}}'
