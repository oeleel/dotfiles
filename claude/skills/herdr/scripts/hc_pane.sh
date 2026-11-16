#!/usr/bin/env bash
# Open or close a split pane in the Herdr desktop app, next to the calling terminal.
#
# The app has no split command. It keeps its layout in the `herdr-app` document
# (spaces -> tabs -> root row -> blocks), so a split is a new block in the caller's row.
# The write is version-checked by the core: a concurrent layout change fails it loudly.
#
#   hc_pane.sh open  <name> [--weight 0.4] -- <command...>
#   hc_pane.sh close <name>
set -euo pipefail

readonly DOC_NAME="herdr-app"
readonly DEFAULT_WEIGHT="0.4"

die() { echo "hc_pane: $*" >&2; exit 1; }

rpc() { # rpc <method> <params-json>  -> prints .result, dies on .error
  local reply
  reply=$(jq -cn --arg m "$1" --argjson p "$2" '{jsonrpc:"2.0",id:1,method:$m,params:$p}' | hc connect)
  jq -e 'has("error") | not' >/dev/null <<<"$reply" || die "$1 failed: $(jq -c .error <<<"$reply")"
  jq -c .result <<<"$reply"
}

doc_get() { rpc doc.get "$(jq -cn --arg n "$DOC_NAME" '{name:$n}')"; }

doc_set() { # doc_set <version> <value-json>
  rpc doc.set "$(jq -cn --arg n "$DOC_NAME" --argjson v "$1" --argjson val "$2" '{name:$n,version:$v,value:$val}')" >/dev/null
}

[[ -n "${HC_TERMINAL_ID:-}" ]] || die "HC_TERMINAL_ID is empty: this shell is not a Herdr app terminal"
readonly SELF="$HC_TERMINAL_ID"

cmd="${1:-}"; name="${2:-}"
[[ -n "$cmd" && -n "$name" ]] || die "usage: hc_pane.sh open <name> [--weight W] -- <command...> | close <name>"
shift 2

case "$cmd" in
open)
  weight="$DEFAULT_WEIGHT"
  if [[ "${1:-}" == "--weight" ]]; then weight="${2:?--weight needs a value}"; shift 2; fi
  [[ "${1:-}" == "--" ]] || die "open: put -- before the command"
  shift
  [[ $# -gt 0 ]] || die "open: no command given"

  doc=$(doc_get)
  # The caller must be a direct child of its tab's root row; a nested layout is not handled.
  jq -e --arg s "$SELF" '[.value.spaces[].tabs[] | select(any(.root.children[]; .content.terminal == $s))] | length == 1' \
    >/dev/null <<<"$doc" || die "terminal $SELF is not a direct block of exactly one tab; open the split by hand"

  addr=$(hc run --bg --json --name "$name" --no-notify --keep -- "$@" | jq -r .address)
  [[ -n "$addr" && "$addr" != "null" ]] || die "hc run did not return a terminal address"

  block_id="p$(uuidgen | tr -d - | tr 'A-F' 'a-f')"
  value=$(jq -c --arg s "$SELF" --arg t "$addr" --arg id "$block_id" --argjson w "$weight" '
    .value | .spaces |= map(.tabs |= map(
      if any(.root.children[]; .content.terminal == $s) then
        .root.children |= (map(
          if .content.terminal == $s then
            ((.size.weight // 1.0) as $mine
             | (.size = {weight: ($mine * (1 - $w))}),
               {content: {terminal: $t}, id: $id, size: {weight: ($mine * $w)}, type: "block"})
          else . end))
      else . end))' <<<"$doc")
  if ! doc_set "$(jq .version <<<"$doc")" "$value"; then
    hc kill "$addr" >/dev/null 2>&1 || true
    hc rm "$addr" >/dev/null 2>&1 || true
    die "layout write failed; the new terminal was removed"
  fi
  jq -cn --arg a "$addr" --arg n "$name" --arg b "$block_id" '{address:$a,name:$n,block:$b}'
  ;;
close)
  info=$(hc get "$name" --json) || die "no terminal named $name"
  addr=$(jq -r .address <<<"$info")
  parent=$(jq -r .parent <<<"$info")
  [[ "$parent" == "$SELF" ]] || die "terminal $name ($addr) has parent $parent, not $SELF: not yours to close"

  doc=$(doc_get)
  # Give the removed block's width back to its left neighbour (right one if it is first).
  value=$(jq -c --arg t "$addr" '
    .value | .spaces |= map(.tabs |= map(
      if any(.root.children[]; .content.terminal == $t) then
        .root.children |= (
          (map(.content.terminal == $t) | index(true)) as $i
          | (.[$i].size.weight // 0) as $w
          | (if $i > 0 then $i - 1 else 1 end) as $n
          | (if length > 1 then .[$n].size = {weight: ((.[$n].size.weight // 1.0) + $w)} else . end)
          | del(.[$i]))
      else . end))' <<<"$doc")
  doc_set "$(jq .version <<<"$doc")" "$value"
  hc kill "$addr" >/dev/null 2>&1 || true
  hc rm "$addr" >/dev/null 2>&1 || true
  jq -cn --arg a "$addr" '{closed:$a}'
  ;;
*)
  die "unknown command: $cmd"
  ;;
esac
