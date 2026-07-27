#!/usr/bin/env bash
# Super+Backspace = "delete to start of line", macOS Cmd+Backspace style,
# dispatched per-focused-window because the right keystroke differs by app:
#
#   * terminals / TUIs (Claude Code, shells): Ctrl+U  (readline unix-line-discard)
#   * GUI text fields:                        Shift+Home then Delete (select to
#                                             line start + delete the selection)
#
# Bound in bindings.conf. This replaces the old global keyd rule
# (/etc/keyd/default.conf: [meta] backspace = macro(S-home delete)), which was
# GUI-only and did nothing useful in terminals. keyd now passes Super+Backspace
# through to Hyprland, and this script routes it by window class.
#
# Add a terminal's window class to the case below if it isn't matched.

cls=$(hyprctl activewindow -j 2>/dev/null | python3 -c '
import json, sys
try:
    print((json.load(sys.stdin) or {}).get("class", ""))
except Exception:
    print("")
')

shopt -s nocasematch
case "$cls" in
  Alacritty | *ghostty* | kitty | foot | footclient | *wezterm* | *konsole* \
  | *gnome.Terminal* | *tilix* | *xterm* | *urxvt* | *rxvt* | st | contour | *terminator* )
    # Terminal: Ctrl+U deletes to start of line.
    hyprctl dispatch sendshortcut "CTRL,U,activewindow" >/dev/null 2>&1
    ;;
  *)
    # GUI: select to line start, then delete (macOS Cmd+Backspace behavior).
    hyprctl dispatch sendshortcut "SHIFT,home,activewindow" >/dev/null 2>&1
    hyprctl dispatch sendshortcut ",delete,activewindow"     >/dev/null 2>&1
    ;;
esac
