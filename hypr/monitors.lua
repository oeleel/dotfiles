-- See https://wiki.hypr.land/Configuring/Basics/Monitors/
-- List current monitors and supported resolutions with: hyprctl monitors all

-- Restored 2026-08-18 from the pre-quattro monitors.conf, which the
-- omarchy-upgrade-to-quattro migration dropped when it regenerated this file
-- as a stock template. Without these rules both panels fall back to their
-- first EDID mode -- 59.95Hz on the KTC and 60Hz on the MSI.

-- GTK apps render at 1x. Omarchy's stock template ships 2, which doubles GTK
-- chrome on these scale-1 panels; this machine deliberately ran 1 pre-quattro.
local omarchy_gdk_scale = 1
local omarchy_monitor_scale = "auto"

hl.env("GDK_SCALE", tostring(omarchy_gdk_scale))

-- Fallback for any panel not named below (e.g. a hotplugged display).
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = omarchy_monitor_scale })

-- Physical layout: MSI on the left, KTC (primary) on the right, TOP edges
-- level (both at y = 0). Top-aligned rather than bottom-aligned so the two
-- 32px bars sit on one continuous line across the seam and the cursor keeps
-- its height crossing left-to-right along the top. The 360px dead zone
-- therefore sits along the bottom of the MSI.
-- Both panels are pinned to their highest available mode.
hl.monitor({ output = "HDMI-A-1", mode = "1920x1080@144", position = "0x0",    scale = 1 })  -- MSI G241, secondary
hl.monitor({ output = "DP-3",     mode = "2560x1440@180", position = "1920x0", scale = 1 })  -- KTC H27T22S, primary

-- Portrait/rotated secondary monitor (transform: 1 = 90°, 3 = 270°).
-- hl.monitor({ output = "DP-2", mode = "preferred", position = "auto", scale = 1, transform = 1 })
