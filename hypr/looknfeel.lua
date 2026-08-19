-- Appearance overrides.
--
-- Restored 2026-08-18 from the pre-quattro looknfeel.conf, discarded by the
-- omarchy-upgrade-to-quattro migration. Without it the desktop came back with
-- Omarchy's stock 5/10 gaps, square corners and blur OFF -- i.e. none of the
-- glass look, which is the compositor half of the effect whose alpha half
-- lives in omarchy/shell.toml. Both halves are required.

hl.config({
  general = {
    gaps_in = 3,
    gaps_out = 6,
  },

  decoration = {
    rounding = 8,

    -- Fewer, wider passes than stock: this is what frosts the bar and the
    -- shell popouts, via the layer_rule blur block in hyprland.lua.
    blur = {
      enabled = true,
      size = 4,
      passes = 3,
    },
  },
})

-- Snappier, longer-tailed window motion than stock easeOutQuint.
hl.curve("easeOutExpo", { type = "bezier", points = { { 0.16, 1 }, { 0.3, 1 } } })
hl.animation({ leaf = "windows",    enabled = true, speed = 3.8, bezier = "easeOutExpo" })
hl.animation({ leaf = "windowsIn",  enabled = true, speed = 4,   bezier = "easeOutExpo", style = "popin 90%" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 1.8, bezier = "linear",      style = "popin 92%" })
hl.animation({ leaf = "border",     enabled = true, speed = 5,   bezier = "easeOutExpo" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 4.5, bezier = "easeOutExpo", style = "slide" })

-- Terminals sit further back than everything else.
o.window({ class = "^(Alacritty|dropdown-terminal)$" }, { opacity = "0.84 0.78" })
o.window({ tag = "default-opacity" }, { opacity = "0.92 0.88" })
