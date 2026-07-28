#!/usr/bin/env bash
# Claude Code statusLine — model · dir · git/worktree · context · 5h & 7d usage
# Reads the statusLine JSON payload on stdin (Claude Code >= 2.1).

input=$(cat)

# ---- extract everything in one jq pass ----
IFS=$'\t' read -r model cwd ctx_pct ctx_used ctx_size h5_pct h5_reset d7_pct d7_reset < <(
  echo "$input" | jq -r '
    [ (.model.display_name // "?")
    , (.cwd // .workspace.current_dir // "?")
    , (.context_window.used_percentage // 0)
    , ((.context_window.total_input_tokens // 0) + (.context_window.total_output_tokens // 0))
    , (.context_window.context_window_size // 0)
    , (.rate_limits.five_hour.used_percentage // -1)
    , (.rate_limits.five_hour.resets_at // 0)
    , (.rate_limits.seven_day.used_percentage // -1)
    , (.rate_limits.seven_day.resets_at // 0)
    ] | @tsv'
)

now=$(date +%s)

# ---- colors ----
R=$'\033[0m'; DIM=$'\033[2m'
C_MODEL=$'\033[38;5;209m'   # warm orange
C_DIR=$'\033[36m'          # cyan
C_GIT=$'\033[32m'          # green
C_CTX=$'\033[38;5;245m'    # grey
SEP="${DIM}│${R} "

# ---- helpers ----
human() { # humanize a token count -> 1M / 40k / 512
  local n=$1
  if   (( n >= 1000000 )); then printf '%d.%dM' $((n/1000000)) $(((n%1000000)/100000))
  elif (( n >= 1000    )); then printf '%dk' $((n/1000))
  else printf '%d' "$n"; fi
}

fmt_dur() { # seconds -> 1d5h / 4h12m / 45m / now
  local s=$1
  (( s <= 0 )) && { printf 'now'; return; }
  local d=$((s/86400)) h=$(((s%86400)/3600)) m=$(((s%3600)/60))
  if   (( d > 0 )); then printf '%dd%dh' "$d" "$h"
  elif (( h > 0 )); then printf '%dh%dm' "$h" "$m"
  else printf '%dm' "$m"; fi
}

thr_color() { # pick color by utilization
  local p=$1
  if   (( p >= 80 )); then printf '\033[31m'   # red
  elif (( p >= 50 )); then printf '\033[33m'   # yellow
  else printf '\033[32m'; fi                   # green
}

bar() { # bar PCT WIDTH -> filled/empty blocks
  local pct=$1 width=${2:-8} i filled out=""
  (( pct < 0 )) && pct=0
  filled=$(( (pct*width + 50) / 100 ))
  (( filled > width )) && filled=width
  for ((i=0; i<width; i++)); do
    (( i < filled )) && out+="█" || out+="░"
  done
  printf '%s' "$out"
}

# ---- directory: collapse $HOME, then keep last 2 components ----
case "$cwd" in
  "$HOME")   dir_display="~" ;;
  "$HOME"/*) dir_display="~/${cwd#"$HOME"/}" ;;
  *)         dir_display="$cwd" ;;
esac
dir_display=$(awk -F'/' '{ if (NF<=2) print $0; else print "…/" $(NF-1) "/" $NF }' <<<"$dir_display")

# ---- git branch + worktree ----
git_seg=""
branch=$(git -C "$cwd" --no-optional-locks branch --show-current 2>/dev/null)
if [ -n "$branch" ]; then
  git_seg="${C_GIT} ${branch}${R}"
  gdir=$(git -C "$cwd" rev-parse --absolute-git-dir 2>/dev/null)
  cdir=$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  if [ -n "$cdir" ] && [ "$gdir" != "$cdir" ]; then
    wt=$(basename "$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)")
    git_seg="${git_seg} ${DIM}⌂${wt}${R}"
  fi
fi

# ---- model (trim verbose " context") ----
model_disp="${model/ context)/)}"

# ---- context segment ----
ctx_seg="${C_CTX}ctx ${ctx_pct}% $(human "$ctx_used")/$(human "$ctx_size")${R}"

# ---- rate-limit segment builder ----
limit_seg() { # label pct reset
  local label=$1 pct=$2 reset=$3
  [ "$pct" = "-1" ] && return
  local col; col=$(thr_color "$pct")
  local reset_txt=""
  (( reset > 0 )) && reset_txt=" ${DIM}↻$(fmt_dur $((reset-now)))${R}"
  printf '%s%s %s%s %d%%%s%s' "$DIM" "$label" "$col" "$(bar "$pct" 8)" "$pct" "$R" "$reset_txt"
}
h5_seg=$(limit_seg "5h" "$h5_pct" "$h5_reset")
d7_seg=$(limit_seg "7d" "$d7_pct" "$d7_reset")

# ---- assemble ----
out="${C_MODEL}◆ ${model_disp}${R}${SEP}${C_DIR}${dir_display}${R}"
[ -n "$git_seg" ] && out="${out}${git_seg}"
out="${out}${SEP}${ctx_seg}"
[ -n "$h5_seg" ]  && out="${out}${SEP}${h5_seg}"
[ -n "$d7_seg" ]  && out="${out}${SEP}${d7_seg}"

printf '%s' "$out"
