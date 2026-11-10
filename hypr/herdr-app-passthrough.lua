-- Let the Herdr app keep its macOS shortcuts on this desktop.
--
-- herdr-app/keys.json is the macOS keymap plus ALT+1..9 for tabs, and `cmd` is
-- SUPER on Linux. Only this desktop links the file; the MacBook uses Herdr's
-- built-in macOS defaults. Hyprland owns many SUPER chords and consumes them before any client
-- sees them, so the chords below would never reach Herdr.
--
-- Hyprland has no per-window binds. This module wraps `hl.bind` instead: a bind
-- on a listed chord keeps its own action everywhere, except when the Herdr
-- window has focus, where the same chord goes to Herdr. Wrapping (rather than
-- `hl.unbind` plus a restated bind) keeps every Omarchy action defined in one
-- place, upstream, so an Omarchy update cannot drift from a copy here.
--
-- MUST load before `require("default.hypr.omarchy")`: only binds that register
-- after this module are wrapped.
--
-- Chords in keys.json that Hyprland does not bind (SUPER+D, SUPER+B,
-- SUPER+N, CTRL+1..9, ...) reach Herdr without help and are not listed.
--
-- SUPER+1..9 is left out on purpose: it switches workspaces everywhere, also
-- in Herdr. The cmd-1..9 tab.select entries in keys.json are thus dead on
-- Linux; ALT+1..9 selects a Herdr tab by number instead, and CTRL+TAB and
-- SUPER+SHIFT+[ / ] still step between tabs.

local HERDR_WINDOW_CLASS = "herdr-app"

-- A synthetic key needs a separate release. `send_shortcut` can leave the key
-- stuck or repeating (hyprwm/Hyprland discussion 14099); Omarchy's clipboard
-- binds use the same down/up split and the same delay.
local KEY_RELEASE_DELAY_MS = 50

-- Written exactly as Omarchy writes them. `code:N` is a keycode bind:
-- 19 = digit 0, 20 = minus, 21 = equal, 34/35 = left/right bracket.
local PASSTHROUGH_CHORDS = {
  "SUPER + T", -- tab.new            (Hyprland: new tab, sends CTRL+T)
  "SUPER + W", -- tab.close          (close tab: sends CTRL+W)
  "SUPER + P", -- picker             (pseudo window)
  "SUPER + F", -- terminal.search    (full screen)
  "SUPER + C", -- terminal.copy      (universal copy, would send CTRL+C)
  "SUPER + V", -- terminal.paste     (universal paste)
  "SUPER + comma", -- app.settings   (dismiss notification)
  "SUPER + SLASH", -- app.help       (monitor scaling up)
  "SUPER + LEFT", -- line start      (focus left window)
  "SUPER + RIGHT", -- line end       (focus right window)
  "SUPER + BACKSPACE", -- delete to line start
  "SUPER + code:19", -- app.zoom_reset (switch to workspace 10)
  "SUPER + code:20", -- app.zoom_out   (resize window)
  "SUPER + code:21", -- app.zoom_in    (resize window)
  "SUPER + SHIFT + code:21", -- app.zoom_in via "+" (resize window)
  "SUPER + SHIFT + P", -- app.palette       (Google Photos)
  "SUPER + SHIFT + D", -- pane.split:down   (Docker)
  "SUPER + SHIFT + W", -- pane.close        (Typora)
  "SUPER + SHIFT + RETURN", -- pane.zoom    (browser)
  "SUPER + SHIFT + SLASH", -- app.help      (passwords)
  "SUPER + ALT + LEFT", -- pane.go          (move window into group)
  "SUPER + ALT + RIGHT",
  "SUPER + ALT + UP",
  "SUPER + ALT + DOWN",
  "SUPER + ALT + code:34", -- space.prev    (webcam overlay smaller)
  "SUPER + ALT + code:35", -- space.next    (webcam overlay larger)
  "SUPER + SHIFT + ALT + LEFT", -- pane.swap (move workspace to monitor)
  "SUPER + SHIFT + ALT + RIGHT",
  "SUPER + SHIFT + ALT + UP",
  "SUPER + SHIFT + ALT + DOWN",
}

-- "super + Shift+t" -> mods "SHIFT SUPER", key "T". Modifier order and letter
-- case differ between config files, so compare a canonical form.
local function parse_chord(keys)
  local tokens = {}
  for token in keys:gmatch("[^+]+") do
    tokens[#tokens + 1] = token:match("^%s*(.-)%s*$")
  end

  local key = table.remove(tokens)
  for index, mod in ipairs(tokens) do
    tokens[index] = mod:upper()
  end
  table.sort(tokens)

  return { mods = table.concat(tokens, " "), key = key }
end

local function chord_id(chord)
  return chord.mods .. " + " .. chord.key:upper()
end

local passthrough = {}
for _, keys in ipairs(PASSTHROUGH_CHORDS) do
  local chord = parse_chord(keys)
  passthrough[chord_id(chord)] = chord
end

local function herdr_has_focus()
  local window = hl.get_active_window()
  return window ~= nil and window.class == HERDR_WINDOW_CLASS
end

local function send_to_focused_window(chord)
  hl.dispatch(hl.dsp.send_key_state({ mods = chord.mods, key = chord.key, state = "down" }))
  hl.timer(function()
    hl.dispatch(hl.dsp.send_key_state({ mods = chord.mods, key = chord.key, state = "up" }))
  end, { timeout = KEY_RELEASE_DELAY_MS, type = "oneshot" })
end

-- The Lua state survives a config reload, but this module runs again. Keep the
-- real `hl.bind` in a global so a reload wraps it once, not once per reload.
local raw_bind = _G.herdr_app_passthrough_raw_bind or hl.bind
_G.herdr_app_passthrough_raw_bind = raw_bind

hl.bind = function(keys, dispatcher, options)
  local chord = type(keys) == "string" and passthrough[chord_id(parse_chord(keys))] or nil
  if not chord then
    return raw_bind(keys, dispatcher, options)
  end

  return raw_bind(keys, function()
    if herdr_has_focus() then
      send_to_focused_window(chord)
    elseif type(dispatcher) == "function" then
      dispatcher()
    else
      hl.dispatch(dispatcher)
    end
  end, options)
end
