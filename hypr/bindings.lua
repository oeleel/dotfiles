-- Personal keybindings.
--
-- Restored 2026-08-18 from the pre-quattro bindings.conf, which the
-- omarchy-upgrade-to-quattro migration discarded when it regenerated this file
-- as an empty template. Only genuine customisations are here -- the ~25 app
-- launcher binds that file also carried were copies of Omarchy's own defaults
-- and are now supplied by `require("default.hypr.omarchy")`, so repeating them
-- would just fork them from upstream.

-- Region screenshot straight to the clipboard, with a reminder of the two
-- different paste chords. Quattro binds PRINT / ALT+PRINT / SUPER+CTRL+PRINT
-- and a capture menu on SUPER+CTRL+C; this is the fast path that skips the
-- menu and never touches disk.
o.bind(
  "ALT + SHIFT + S",
  "Screenshot region to clipboard",
  [[bash -c 'omarchy-capture-screenshot region copy && wl-paste --list-types 2>/dev/null | grep -q image && notify-send "📸 Screenshot copied" "Ctrl+V in apps - Ctrl+Alt+V in terminal TUIs" -t 2500']]
)

-- Swap the active output between headphones and speakers. Pairs with the
-- `audio-swap` bar module, which renders whichever port is currently live.
o.bind("SUPER + A", "Toggle audio output", "audio-toggle-output")

-- Wispr Flow dictation. The Hub window is parked on a special workspace by a
-- rule in hyprland.lua; this is what pulls it back into view. Push-to-talk is
-- separate -- CapsLock is remapped to F13 by keyd, below Hyprland.
o.bind("SUPER + U", "Toggle Wispr Flow window", hl.dsp.workspace.toggle_special("wispr"))

-- Reclaimed from quattro's defaults. Both were bound pre-quattro and the new
-- defaults that took the keys are not wanted here.
hl.unbind("SUPER + CTRL + P") -- quattro default: Power menu
o.bind("SUPER + CTRL + P", "Wallpaper theme", "wall-theme-pick")

hl.unbind("SUPER + SHIFT + W") -- quattro default: Omawrite
o.bind("SUPER + SHIFT + W", "Typora", { launch = "typora --enable-wayland-ime" })

-- Alt+Tab is left on Omarchy's own focus-next/prev.
--
-- Pre-quattro these were unbound so hyprshell could own Alt+Tab with live
-- window thumbnails. hyprshell 4.11.0-alpha.1 registers its binds by shelling
-- out to `hyprctl keyword bind`, and quattro's non-legacy Lua parser rejects
-- that outright ("keyword can't work with non-legacy parsers. Use eval."), so
-- the daemon starts, logs clean, and silently registers nothing. Unbinding
-- here would therefore leave Alt+Tab dead rather than hand it to hyprshell.
-- Restore both unbinds if hyprshell gains `hyprctl eval` support.

-- macOS Cmd+Backspace style "delete to start of line". The right keystroke
-- differs by app -- Ctrl+U in terminals and TUIs, Shift+Home then Delete in GUI
-- text fields -- so this routes on the focused window. keyd passes
-- Super+Backspace through to Hyprland rather than eating it, so this sees it.
--
-- Pre-quattro this called ~/.config/hypr/super-backspace-linekill.sh, which
-- drove `hyprctl dispatch sendshortcut`. Quattro's Lua parser rejects that
-- legacy string form ("')' expected near 'CTRL'"), and the script discarded
-- stderr, so the key silently did nothing. That script is now superseded.
--
-- Lifted from Omarchy's own default/hypr/bindings/clipboard.lua:
--   * the down/up split works around Hyprland leaving synthetic key state
--     stuck or repeating (hyprwm/Hyprland#14099)
--   * terminal detection uses Omarchy's `terminal` window tag rather than a
--     hand-maintained class list, so there is one definition of "terminal"
--     (dynamic tags carry a trailing "*", hence the gsub)
local function send_shortcut_once(mods, key, delay)
  return function()
    hl.dispatch(hl.dsp.send_key_state({ mods = mods, key = key, state = "down" }))
    hl.timer(function()
      hl.dispatch(hl.dsp.send_key_state({ mods = mods, key = key, state = "up" }))
    end, { timeout = delay or 50, type = "oneshot" })
  end
end

local function active_window_is_terminal()
  local window = hl.get_active_window()
  if not window then
    return false
  end
  for _, tag in ipairs(window.tags or {}) do
    if tag:gsub("%*$", "") == "terminal" then
      return true
    end
  end
  return false
end

hl.unbind("SUPER + BACKSPACE") -- quattro default: Toggle window transparency
o.bind("SUPER + BACKSPACE", "Delete to start of line", function()
  if active_window_is_terminal() then
    send_shortcut_once("CTRL", "U")()
  else
    -- Select to line start, then delete the selection. The Delete must land
    -- after SHIFT+Home has been released, or the still-held SHIFT merges into
    -- it and the selection is extended instead of removed.
    send_shortcut_once("SHIFT", "Home")()
    hl.timer(function()
      send_shortcut_once("", "Delete")()
    end, { timeout = 120, type = "oneshot" })
  end
end)

-- Deliberately NOT restored:
--   SUPER + S      -- was `pypr toggle term`; quattro ships its own scratchpad
--   SUPER + GRAVE  -- was Noctalia's window finder; Noctalia is retired
