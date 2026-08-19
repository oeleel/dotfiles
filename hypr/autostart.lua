-- Startup programs.
--
-- Restored 2026-08-18 from the pre-quattro autostart.conf, which the
-- omarchy-upgrade-to-quattro migration discarded. Because this file was left
-- empty, the first reboot after the upgrade came up with none of these running
-- -- no dictation, no Alt+Tab thumbnails, and no morning restore if the machine
-- had been left in night mode.

-- Cursor theme. Paired with XCURSOR_THEME in hyprland.lua; the setcursor call
-- covers clients that read the compositor rather than the environment.
o.exec_on_start("hyprctl setcursor breeze_cursors 24")

-- Wispr Flow dictation. Placement of its floating Status bar is handled by
-- hypr/wispr-flow-position.lua, which is loaded from hyprland.lua and so is
-- already listening before this launches.
o.launch_on_start("wispr-flow")

-- hyprshell (live-thumbnail Alt+Tab) is NOT started: 4.11.0-alpha.1 registers
-- its binds through `hyprctl keyword bind`, which quattro's Lua parser refuses,
-- so the daemon runs but binds nothing. Re-enable once upstream uses eval.
-- o.exec_on_start("~/dotfiles/bin/hyprshell-run")

-- If the machine was shut down mid-night-mode, the state file outlives the
-- reboot; restore day settings (RGB, fans, mouse wake) rather than booting into
-- a half-applied night.
o.exec_on_start("bash -c 'test -f ~/.local/state/goodnight.active && ~/.local/bin/goodnight day'")

-- Deliberately NOT restored:
--   noctalia -- retired per omarchy/QUATTRO-MIGRATION.md now that the quattro
--               bar is confirmed working; running it too would mean two
--               Quickshell instances and two bars.
--   pypr     -- only ever existed for the SUPER+S scratchpad, and that key now
--               belongs to quattro's own built-in scratchpad.
--   omarchy-lock-screen -- quattro's shell owns the lock service itself.
