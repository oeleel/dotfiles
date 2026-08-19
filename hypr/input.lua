-- Keep only your personal input overrides here. Uncommented settings below
-- replace Omarchy's defaults.

-- Pointer tuning for the Logitech MX Master 3 (this box has no touchpad).
--
-- accel_profile "flat" was set in the pre-quattro input.conf and was dropped by
-- the omarchy-upgrade-to-quattro migration, which reverted it to libinput's
-- adaptive curve. Flat means cursor travel is a pure linear function of how far
-- the mouse physically moves -- the same swipe always lands in the same place,
-- regardless of how fast you make it. Everything else the old input.conf set
-- (repeat_rate, repeat_delay, numlock_by_default, compose:caps) is already
-- supplied by Omarchy's own defaults, so it is deliberately not repeated here.
--
-- sensitivity is a libinput multiplier in [-1.0, 1.0]; 0 is untouched. Negative
-- slows the pointer. Nudge in ~0.1 steps and reload -- with a flat profile this
-- scales cursor travel uniformly, it does not reintroduce acceleration.
hl.config({
  input = {
    accel_profile = "flat",
    sensitivity = -0.2,
  },
})

-- Keyboard layout and options.
-- See https://wiki.hypr.land/Configuring/Basics/Variables/#input
-- hl.config({
--   input = {
--     -- Use multiple keyboard layouts and switch between them with Left Alt + Right Alt.
--     kb_layout = "us,dk,eu",
--     kb_options = "compose:caps,shift:both_capslock_cancel,grp:alts_toggle",
--
--     -- Use a specific keyboard variant if needed (e.g. intl for international keyboards).
--     kb_variant = "intl",
--
--     -- Change speed of keyboard repeat.
--     repeat_rate = 40,
--     repeat_delay = 250,
--
--     -- Start with numlock on by default.
--     numlock_by_default = true,
--
--     -- Increase sensitivity for mouse/trackpad (default: 0).
--     sensitivity = 0.35,
--
--     -- Turn off mouse acceleration (default: adaptive).
--     accel_profile = "flat",
--
--     touchpad = {
--       -- Use natural (inverse) scrolling.
--       natural_scroll = true,
--
--       -- Use two-finger clicks for right-click instead of lower-right corner.
--       clickfinger_behavior = true,
--
--       -- Control the speed of your scrolling.
--       scroll_factor = 0.4,
--
--       -- Enable the touchpad while typing.
--       disable_while_typing = false,
--
--       -- Left-click-and-drag with three fingers.
--       drag_3fg = 1,
--     },
--   },
-- })

-- App-specific touchpad scroll speeds.
-- o.window("(Alacritty|kitty|foot)", { scroll_touchpad = 1.5 })
-- o.window("com.mitchellh.ghostty", { scroll_touchpad = 0.2 })

-- Enable touchpad gestures for changing workspaces.
-- See https://wiki.hypr.land/Configuring/Advanced-and-Cool/Gestures/
-- hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

-- Enable touchpad gestures for moving focus (helpful on scrolling layout).
-- hl.gesture({ fingers = 3, direction = "left", action = function() hl.dispatch(hl.dsp.focus({ direction = "l" })) end })
-- hl.gesture({ fingers = 3, direction = "right", action = function() hl.dispatch(hl.dsp.focus({ direction = "r" })) end })
