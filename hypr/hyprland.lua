-- Learn how to configure Hyprland: https://wiki.hypr.land/Configuring/Start/

-- Omarchy's bootstrap keeps path setup out of this user config.
dofile((os.getenv("OMARCHY_PATH") or "/usr/share/omarchy") .. "/default/hypr/bootstrap.lua")

-- Disable all Omarchy default bindings. Add your own in hypr/bindings.lua.
-- omarchy_default_bindings = false
--
-- Or disable only bindings for Omarchy's preinstalled apps/web apps while
-- keeping core window-manager bindings:
-- omarchy_preinstalled_bindings = false

-- Load Omarchy defaults.
require("default.hypr.omarchy")

-- Put your personal overrides in these files. They're loaded after Omarchy's
-- defaults so package updates can improve the defaults without rewriting your
-- ~/.config/hypr files.
require("hypr.monitors")
require("hypr.input")
require("hypr.bindings")
require("hypr.looknfeel")
require("hypr.autostart")

-- Toggle config flags dynamically.
require("default.hypr.toggles")

-- ---------------------------------------------------------------------------
-- Restored 2026-08-18 from the pre-quattro hyprland.conf, discarded by the
-- omarchy-upgrade-to-quattro migration.
-- ---------------------------------------------------------------------------

hl.env("XCURSOR_THEME", "breeze_cursors")

-- Frost. This is the compositor half of the glass look: the shell surfaces are
-- drawn translucent by the alpha tokens in omarchy/shell.toml, and blurred
-- here. Alpha without blur is just flat translucency, so the two ship together.
-- ignore_alpha keeps the blur from bleeding through the fully transparent
-- regions of a layer (the gaps between bar widgets, popup drop shadows).
local shell_surfaces =
  "^omarchy-(bar|menu|notifications|osd|polkit|clipboard|emojis|reminders|keyboard-panel|image-selector)$"
hl.layer_rule({ match = { namespace = shell_surfaces }, blur = true })
hl.layer_rule({ match = { namespace = shell_surfaces }, ignore_alpha = 0.3 })

-- Fixed homes so a workspace always has the same thing on it.
o.window({ class = "^(chromium|Chromium)$" }, { workspace = "1" })
o.window({ class = "^signal$" }, { workspace = "4" })
o.window({ class = "^chrome-discord\\.com.*$" }, { workspace = "4" })
o.window({ class = "^(spotify|Spotify)$" }, { workspace = "5" })

-- Wispr Flow's floating Status readout. It is an always-on-top HUD, not a
-- window: it must never take focus (that would steal keystrokes mid-dictation),
-- never be dimmed by the default-opacity tag, and never pick up rounding,
-- borders, shadow or blur, all of which show as artefacts around its edge.
o.window({ class = "^wispr-flow$", title = "^Status$" }, {
  float = true,
  pin = true,
  no_focus = true,
  border_size = 0,
  rounding = 0,
  no_shadow = true,
  no_blur = true,
  opacity = "1.0 override",
})

-- The Hub is parked out of the way and pulled back with SUPER+U.
o.window({ class = "^wispr-flow$", title = "^Hub$" }, { workspace = "special:wispr silent" })

-- Static rules cannot place the Status bar (it is renamed after it maps), so a
-- small event-driven module pins it bottom-centre instead.
require("hypr.wispr-flow-position")

-- Noctalia's layer rules are deliberately not restored -- it is retired per
-- omarchy/QUATTRO-MIGRATION.md.
