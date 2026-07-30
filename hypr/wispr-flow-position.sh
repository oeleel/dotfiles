#!/usr/bin/env bash
# Keep the Wispr Flow "flow bar" (class wispr-flow, title "Status") pinned to
# bottom-center. The window maps WITHOUT its final title, so Hyprland's static
# `move` windowrule never matches at open time. Instead we listen to Hyprland's
# event stream and reposition the bar whenever it appears / (re)gains its title.
#
# Decoration rules (border/rounding/shadow/blur/opacity) stay in hyprland.conf:
# those are dynamic and re-apply on title change, so they work fine. Only the
# position needs this listener.
set -uo pipefail

SIG="${HYPRLAND_INSTANCE_SIGNATURE:-}"
[ -z "$SIG" ] && exit 0
SOCK="${XDG_RUNTIME_DIR}/hypr/${SIG}/.socket2.sock"

# Window-top offset from the monitor's bottom edge (px). 350 => y=1090 on a
# 1440px-tall monitor, which is the spot picked interactively.
MARGIN_FROM_BOTTOM=350

# Always pin the flow bar to THIS monitor (by connector name), regardless of which
# monitor Wispr opens it on. Set empty to instead keep it on whatever monitor it
# opened on. Use `hyprctl monitors` to see names.
PRIMARY_MONITOR=DP-3

reposition() {
  python3 - "$MARGIN_FROM_BOTTOM" "$PRIMARY_MONITOR" <<'PY'
import json, subprocess, sys
margin = int(sys.argv[1])
primary_name = sys.argv[2] if len(sys.argv) > 2 else ""
try:
    # Fetch via subprocess (NOT stdin): the heredoc already owns this process's
    # stdin, so a piped `hyprctl | python3 - <<PY` would read nothing.
    clients = json.loads(subprocess.check_output(["hyprctl", "-j", "clients"]))
    mon_list = json.loads(subprocess.check_output(["hyprctl", "-j", "monitors"]))
    mons = {m["id"]: m for m in mon_list}
except Exception:
    sys.exit(0)
# Preferred target monitor: the named primary if present, else fall back per-window.
primary = next((m for m in mon_list if m.get("name") == primary_name), None)
for c in clients:
    if c.get("class") == "wispr-flow" and c.get("title") == "Status":
        addr = c["address"]; w, h = c["size"]
        # Pin so the bar shows on every workspace. The static `pin` windowrule is
        # unreliable here (the window maps before its title is "Status"), so we
        # pin from this listener instead. `pin` dispatch is a TOGGLE, so only
        # fire it when not already pinned to stay idempotent across events.
        if not c.get("pinned"):
            subprocess.run(["hyprctl", "dispatch", "pin", f"address:{addr}"],
                           stdout=subprocess.DEVNULL)
        m = primary or mons.get(c["monitor"])
        if not m:
            continue
        tx = m["x"] + (m["width"] - w) // 2
        ty = m["y"] + m["height"] - margin
        ax, ay = c["at"]
        on_target_mon = (c.get("monitor") == m["id"])
        if on_target_mon and abs(ax - tx) <= 2 and abs(ay - ty) <= 2:
            continue  # right monitor AND right spot; avoid needless churn
        if not on_target_mon:
            # Pixel-moving alone won't reassign the window to the target monitor's
            # workspace (it renders wrong). Move it to that workspace first.
            ws = (m.get("activeWorkspace") or {}).get("id")
            if ws is not None:
                subprocess.run(["hyprctl", "dispatch", "movetoworkspacesilent",
                                f"{ws},address:{addr}"], stdout=subprocess.DEVNULL)
        subprocess.run(["hyprctl", "dispatch", "movewindowpixel",
                        f"exact {tx} {ty},address:{addr}"],
                       stdout=subprocess.DEVNULL)
PY
}

# Position whatever is already open (covers `hyprctl reload`/script relaunch).
reposition

# React to window open + title-change events. movewindowpixel does NOT emit any
# of these, so there is no feedback loop.
socat -U - "UNIX-CONNECT:${SOCK}" 2>/dev/null | while IFS= read -r line; do
  case "$line" in
    openwindow\>\>*wispr-flow*|windowtitlev2\>\>*Status*|windowtitle\>\>*)
      reposition
      ;;
  esac
done
