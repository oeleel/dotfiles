-- Wispr Flow "flow bar" placement.
--
-- The dictation HUD (class `wispr-flow`, title `Status`) is ONE persistent
-- floating window, and Wispr maps it as `Flow Status Indicator`, renaming it to
-- `Status` only afterwards. Static window rules are evaluated once, at map
-- time, so a `move` rule never matches it -- placement has to react to the
-- later rename. The decoration rules in hyprland.lua are dynamic and DO
-- re-apply on a title change, which is why only the position lives here.
--
-- Pinning is part of the same job: unpinned, the bar stays on whichever
-- workspace it was born on and "disappears" the moment you switch. The
-- `pin = true` window rule is an unreliable backstop for the same map-order
-- reason, so pin from here as well.
--
-- History: this was `wispr-flow-position.sh`, a socat + python listener on
-- Hyprland's event socket, until 2026-08-19. The quattro/Lua migration left it
-- silently dead -- under Hyprland 0.56 `hyprctl dispatch movewindowpixel
-- exact ...` no longer parses (dispatch args are Lua now), the script sent its
-- errors to /dev/null, and the bar was left wherever Hyprland centred it.
-- Hyprland's own Lua event API replaces the script outright: no socat, no
-- python fork per event, and no silent failures.

-- Window-TOP offset from the monitor's bottom edge (px). 350 => y=1090 on a
-- 1440px-tall monitor, which is the spot picked interactively.
local MARGIN_FROM_BOTTOM = 350

-- Always park the bar on this monitor (connector name, see `hyprctl monitors`),
-- whichever monitor Wispr opens it on. Set to nil to leave it wherever it opened.
local PRIMARY_MONITOR = "DP-3"

-- Sub-pixel drift is not worth a dispatch; anything larger is a real move.
local POSITION_TOLERANCE = 2

local FLOW_BAR = { class = "wispr-flow", title = "Status" }

local function selector(win)
  return "address:" .. win.address
end

local function place(win)
  local mon = (PRIMARY_MONITOR and hl.get_monitor(PRIMARY_MONITOR)) or win.monitor
  if not mon then
    return
  end

  -- `action = "on"` rather than the default toggle, so this stays idempotent
  -- however many events fire for one window.
  hl.dispatch(hl.dsp.window.pin({ window = selector(win), action = "on" }))

  -- A pixel move alone will not reassign the window to another monitor's
  -- workspace (it then renders on the wrong output), so hop workspaces first
  -- when the bar opened on the wrong monitor.
  local on_target = win.monitor ~= nil and win.monitor.name == mon.name
  if not on_target and mon.active_workspace then
    hl.dispatch(hl.dsp.window.move({
      window = selector(win),
      workspace = tostring(mon.active_workspace.id),
      follow = false,
    }))
  end

  -- Monitor geometry is reported in physical pixels; layout coordinates are
  -- logical, so divide the size (but not the origin) by the scale.
  local x = mon.x + math.floor((mon.width / mon.scale - win.size.x) / 2)
  local y = mon.y + math.floor(mon.height / mon.scale) - MARGIN_FROM_BOTTOM

  local settled = math.abs(win.at.x - x) <= POSITION_TOLERANCE
    and math.abs(win.at.y - y) <= POSITION_TOLERANCE
  if on_target and settled then
    return
  end

  hl.dispatch(hl.dsp.window.move({ window = selector(win), x = x, y = y }))
end

local function place_flow_bar()
  for _, win in ipairs(hl.get_windows(FLOW_BAR)) do
    place(win)
  end
end

-- Window events carry the window that fired them; anything that is not clearly
-- another app's window falls through to a rescan rather than being dropped.
local function on_window_event(win)
  if type(win) ~= "table" or win.class == nil or win.class == "wispr-flow" then
    place_flow_bar()
  end
end

hl.on("window.open", on_window_event)
hl.on("window.title", on_window_event)

-- Re-place after anything that can move or forget the bar: a monitor coming or
-- going, a config reload, and login (where the bar does not exist yet, so this
-- is only a no-op safety net for a Hyprland restart under a running Wispr).
hl.on("monitor.layout_changed", place_flow_bar)
hl.on("monitor.added", place_flow_bar)
hl.on("config.reloaded", place_flow_bar)
hl.on("hyprland.start", place_flow_bar)
