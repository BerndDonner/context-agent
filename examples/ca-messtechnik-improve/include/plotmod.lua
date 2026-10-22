-- plotmod.lua
--
-- v1.0 -- Cartesian plot helper for ConTeXt / LuaMetaTeX
--
-- Object API only. Each plot instance owns its full state and its render layers.
-- Only "placement" is supported for label positioning; no legacy aliases remain.
-- The public API is intentionally small:
--   local p = require("plotmod")
--   local plot = p.create_plot()
--   plot:set_window{...}
--   plot:define_ticks{...}
--   plot:define_labels{...}
--   plot:add_grid{...}
--   plot:add_axes{...}
--   plot:add_function{...}
--   plot:add_point(...)
--   plot:add_tex_label(...)
--   local f = plot:compile_function_1_1("sin(x)")
--   local mp_code = plot:render()

local plotmod = {}

local function fail(msg)
  error("plotmod: " .. msg, 2)
end

local function deepcopy(obj)
  if type(obj) ~= "table" then
    return obj
  end
  local out = {}
  for k, v in pairs(obj) do
    out[k] = deepcopy(v)
  end
  return out
end

local function tonumber_strict(v, name)
  local n = tonumber(v)
  if not n then
    fail(("expected numeric value for '%s', got %s"):format(name, tostring(v)))
  end
  return n
end

local function parse_dim(dim)
  if type(dim) == "number" then
    return dim
  end
  if type(dim) ~= "string" then
    fail("dimension must be a string like '1cm' or a number")
  end
  local sp = tex.sp(dim)
  return sp / 65781.76
end

local function fmt_num(x)
  if math.abs(x) < 1e-12 then
    x = 0
  end
  return string.format("%.8f", x)
end

local function nearly_equal(a, b, eps)
  eps = eps or 1e-9
  return math.abs(a - b) <= eps
end

local function mp_quote(s)
  s = tostring(s)
  s = s:gsub('"', '\\"')
  return '"' .. s .. '"'
end

local function normalize_axis_window(minv, maxv, axis_name)
  minv = tonumber_strict(minv, axis_name .. "min")
  maxv = tonumber_strict(maxv, axis_name .. "max")
  if minv > maxv then
    fail(axis_name .. "min must be <= " .. axis_name .. "max")
  end
  if not (minv <= 0 and 0 <= maxv) then
    fail(axis_name .. " range must satisfy " .. axis_name .. "min <= 0 <= " .. axis_name .. "max")
  end
  return minv, maxv
end

local function axis_length(minv, maxv)
  return maxv - minv
end

local function normalize_placement(value, default_value)
  value = value or default_value
  if value == nil then
    return nil
  end
  local key = tostring(value):lower():gsub("-", "_")
  local map = {
    center = "center",
    centre = "center",
    top = "top",
    bottom = "bottom",
    bot = "bottom",
    left = "left",
    lft = "left",
    right = "right",
    rt = "right",
    top_left = "top_left",
    ulft = "top_left",
    top_right = "top_right",
    urt = "top_right",
    bottom_left = "bottom_left",
    llft = "bottom_left",
    bottom_right = "bottom_right",
    lrt = "bottom_right",
  }
  local normalized = map[key]
  if not normalized then
    fail(
      "invalid placement '" .. tostring(value) ..
      "' (allowed: center, top, bottom, left, right, top_left, top_right, bottom_left, bottom_right)"
    )
  end
  return normalized
end

local function placement_to_mp_command(placement)
  local map = {
    center = "label",
    top = "label.top",
    bottom = "label.bot",
    left = "label.lft",
    right = "label.rt",
    top_left = "label.ulft",
    top_right = "label.urt",
    bottom_left = "label.llft",
    bottom_right = "label.lrt",
  }
  return map[placement] or fail("internal error: unsupported placement '" .. tostring(placement) .. "'")
end

local function apply_placement_offset(x, y, placement, distance)
  local d = parse_dim(distance or "0mm")
  if placement == "top" then
    return x, y + d
  elseif placement == "bottom" then
    return x, y - d
  elseif placement == "left" then
    return x - d, y
  elseif placement == "right" then
    return x + d, y
  elseif placement == "top_left" then
    return x - d, y + d
  elseif placement == "top_right" then
    return x + d, y + d
  elseif placement == "bottom_left" then
    return x - d, y - d
  elseif placement == "bottom_right" then
    return x + d, y - d
  elseif placement == "center" then
    return x, y
  else
    fail("internal error: unsupported placement '" .. tostring(placement) .. "'")
  end
end

local function normalize_label_axis_spec(axis_spec, axis_name)
  local placement_default = (axis_name == "x") and "bottom" or "left"
  local placement = normalize_placement(axis_spec.placement, placement_default)
  return {
    placement = placement,
    distance = axis_spec.distance or "2mm",
  }
end

local function tick_half_length(kind)
  if kind == "major" then
    return 4
  else
    return 2
  end
end

local function normalize_axis_end_options(axis_spec)
  axis_spec = axis_spec or {}
  local positive_end = axis_spec.positive_end or {}
  local negative_end = axis_spec.negative_end or {}

  return {
    label_distance = axis_spec.label_distance or "4mm",
    positive_end = {
      arrow_gap = positive_end.arrow_gap or "2.5mm",
      suppress_terminal_tick = (positive_end.suppress_terminal_tick == true),
    },
    negative_end = {
      arrow_gap = negative_end.arrow_gap or "0mm",
      suppress_terminal_tick = (negative_end.suppress_terminal_tick == true),
    },
  }
end

local function axis_value_is_terminal(value, minv, maxv, end_name)
  if end_name == "positive" then
    return nearly_equal(value, maxv)
  elseif end_name == "negative" then
    return nearly_equal(value, minv)
  else
    fail("internal error: invalid axis end name")
  end
end

local function terminal_tick_is_visible(value, minv, maxv, axis_opts)
  if axis_value_is_terminal(value, minv, maxv, "positive") then
    return not axis_opts.positive_end.suppress_terminal_tick
  end
  if axis_value_is_terminal(value, minv, maxv, "negative") then
    return not axis_opts.negative_end.suppress_terminal_tick
  end
  return true
end

local function build_ticks_auto(axis_spec, axis_name, minv, maxv)
  local major = tonumber_strict(axis_spec.major_step, axis_name .. ".major_step")
  if major <= 0 then
    fail(axis_name .. ".major_step must be > 0")
  end

  local subdiv = tonumber_strict(axis_spec.minor_subdivisions or 0, axis_name .. ".minor_subdivisions")
  if subdiv < 0 then
    fail(axis_name .. ".minor_subdivisions must be >= 0")
  end
  subdiv = math.floor(subdiv)

  local out = {}
  local start_major = math.ceil(minv / major) * major
  local eps = 1e-9
  local x = start_major

  while x <= maxv + eps do
    out[#out + 1] = { value = x, kind = "major" }
    if subdiv > 0 then
      local minor_step = major / (subdiv + 1)
      for k = 1, subdiv do
        local mv = x + k * minor_step
        if mv < maxv + eps and mv > minv - eps and mv < x + major - eps then
          out[#out + 1] = { value = mv, kind = "minor" }
        end
      end
    end
    x = x + major
  end

  table.sort(out, function(a, b) return a.value < b.value end)
  return out
end

local function build_ticks_manual(axis_spec)
  local out = {}
  for i = 1, #axis_spec do
    local item = axis_spec[i]
    if type(item) ~= "table" then
      fail("manual tick entry must be a table")
    end
    local kind = item.kind
    if kind ~= "major" and kind ~= "minor" then
      fail("manual tick kind must be 'major' or 'minor'")
    end
    out[#out + 1] = {
      value = tonumber_strict(item.value, "tick.value"),
      kind = kind,
    }
  end
  table.sort(out, function(a, b) return a.value < b.value end)
  return out
end

local function build_labels_auto(axis_spec, axis_name)
  if type(axis_spec.values) ~= "table" then
    fail("automatic label mode requires 'values' list")
  end
  if type(axis_spec.formatter) ~= "function" then
    fail("automatic label mode requires 'formatter' function")
  end

  local items = {}
  for i = 1, #axis_spec.values do
    local v = tonumber_strict(axis_spec.values[i], "label.value")
    items[#items + 1] = {
      value = v,
      text = tostring(axis_spec.formatter(v)),
    }
  end

  local common = normalize_label_axis_spec(axis_spec, axis_name)
  common.items = items
  return common
end

local function build_labels_manual(axis_spec, axis_name)
  local items = {}
  for i = 1, #axis_spec do
    local item = axis_spec[i]
    if type(item) ~= "table" then
      fail("manual label entry must be a table")
    end
    items[#items + 1] = {
      value = tonumber_strict(item.value, "label.value"),
      text = tostring(item.text or ""),
    }
  end

  local common = normalize_label_axis_spec(axis_spec, axis_name)
  common.items = items
  return common
end

local function build_clip_path(self, spec)
  local rect
  if spec == nil or spec == "window" then
    rect = self:make_window_clip_rect()
  elseif type(spec) == "table" then
    rect = self:make_custom_clip_rect(spec)
  else
    fail("clip must be nil, 'window', or a rectangle table")
  end

  return ("((%s,%s)--(%s,%s)--(%s,%s)--(%s,%s)--cycle)"):format(
    fmt_num(rect.x1), fmt_num(rect.y1),
    fmt_num(rect.x2), fmt_num(rect.y1),
    fmt_num(rect.x2), fmt_num(rect.y2),
    fmt_num(rect.x1), fmt_num(rect.y2)
  )
end

local function compile_function_1_1_factory(expr)
  if type(expr) ~= "string" then
    fail("expression must be a string")
  end

  local env = {
    math = math,
    abs = math.abs,
    acos = math.acos,
    asin = math.asin,
    atan = math.atan,
    ceil = math.ceil,
    cos = math.cos,
    exp = math.exp,
    floor = math.floor,
    log = math.log,
    max = math.max,
    min = math.min,
    pi = math.pi,
    sin = math.sin,
    sqrt = math.sqrt,
    tan = math.tan,
  }

  local chunk, err = load("return function(x) return " .. expr .. " end", "plot_expression", "t", env)
  if not chunk then
    fail("invalid expression: " .. tostring(err))
  end

  local fn = chunk()
  if type(fn) ~= "function" then
    fail("expression did not produce a function")
  end
  return fn
end

local Plot = {}
Plot.__index = Plot

function Plot:new()
  return setmetatable({
    state = {
      window = nil,
      ticks = { x = nil, y = nil },
      labels = { x = nil, y = nil },
    },
    layers = {},
  }, self)
end

function Plot:clone()
  local out = Plot:new()
  out.state = deepcopy(self.state)
  out.layers = deepcopy(self.layers)
  return out
end

function Plot:clear_layers()
  self.layers = {}
  return self
end

function Plot:add_layer(code)
  self.layers[#self.layers + 1] = tostring(code)
  return self
end

function Plot:add_raw_mp(code)
  return self:add_layer(code)
end

function Plot:render()
  return table.concat(self.layers, "\n")
end

function Plot:render_image()
  local lines = { "image(" }
  for _, layer in ipairs(self.layers) do
    lines[#lines + 1] = layer
  end
  lines[#lines + 1] = ")"
  return table.concat(lines, "\n")
end

function Plot:set_window(spec)
  if type(spec) ~= "table" then
    fail("set_window expects a table")
  end

  local xmin, xmax = normalize_axis_window(spec.xmin, spec.xmax, "x")
  local ymin, ymax = normalize_axis_window(spec.ymin, spec.ymax, "y")

  local dx = axis_length(xmin, xmax)
  local dy = axis_length(ymin, ymax)

  if dx == 0 then
    fail("x range must not be zero")
  end
  if dy == 0 then
    fail("y range must not be zero")
  end

  local xunit, yunit, width, height

  if spec.unit and (spec.xunit or spec.yunit) then
    fail("use either 'unit' or explicit 'xunit'/'yunit', not both")
  end

  if spec.unit then
    spec = deepcopy(spec)
    spec.xunit = spec.unit
    spec.yunit = spec.unit
  end

  if spec.xunit and spec.yunit then
    xunit = parse_dim(spec.xunit)
    yunit = parse_dim(spec.yunit)
    width = dx * xunit
    height = dy * yunit
  elseif spec.width and spec.height then
    width = parse_dim(spec.width)
    height = parse_dim(spec.height)
    xunit = width / dx
    yunit = height / dy
  else
    fail("window requires either xunit+yunit (or unit) OR width+height")
  end

  self.state.window = {
    xmin = xmin,
    xmax = xmax,
    ymin = ymin,
    ymax = ymax,
    width = width,
    height = height,
    xunit = xunit,
    yunit = yunit,
    origin_x = (-xmin) * xunit,
    origin_y = (-ymin) * yunit,
  }
  return self
end

function Plot:world_to_device(x, y)
  local w = self.state.window
  if not w then
    fail("window not defined")
  end
  return (x - w.xmin) * w.xunit, (y - w.ymin) * w.yunit
end

function Plot:device_rect_for_world_rect(rect)
  local w = self.state.window
  if not w then
    fail("window not defined")
  end
  local xmin = tonumber_strict(rect.xmin, "clip.xmin")
  local xmax = tonumber_strict(rect.xmax, "clip.xmax")
  local ymin = tonumber_strict(rect.ymin, "clip.ymin")
  local ymax = tonumber_strict(rect.ymax, "clip.ymax")
  if xmin > xmax or ymin > ymax then
    fail("invalid clip rectangle")
  end
  local x1, y1 = self:world_to_device(xmin, ymin)
  local x2, y2 = self:world_to_device(xmax, ymax)
  return { x1 = x1, y1 = y1, x2 = x2, y2 = y2 }
end

function Plot:make_window_clip_rect()
  local w = self.state.window
  if not w then
    fail("window not defined")
  end
  return self:device_rect_for_world_rect {
    xmin = w.xmin, xmax = w.xmax,
    ymin = w.ymin, ymax = w.ymax,
  }
end

function Plot:make_custom_clip_rect(spec)
  if type(spec) ~= "table" then
    fail("custom clip spec must be a table")
  end
  return self:device_rect_for_world_rect(spec)
end

function Plot:define_ticks(spec)
  if type(spec) ~= "table" then
    fail("define_ticks expects a table")
  end
  local w = self.state.window
  if not w then
    fail("define window before ticks")
  end

  for _, axis in ipairs({ "x", "y" }) do
    local axis_spec = spec[axis]
    if not axis_spec then
      fail("missing tick definition for axis '" .. axis .. "'")
    end

    local minv = (axis == "x") and w.xmin or w.ymin
    local maxv = (axis == "x") and w.xmax or w.ymax

    if axis_spec.major_step then
      self.state.ticks[axis] = build_ticks_auto(axis_spec, axis, minv, maxv)
    else
      self.state.ticks[axis] = build_ticks_manual(axis_spec)
    end
  end
  return self
end

function Plot:define_labels(spec)
  if type(spec) ~= "table" then
    fail("define_labels expects a table")
  end

  for _, axis in ipairs({ "x", "y" }) do
    local axis_spec = spec[axis]
    if not axis_spec then
      fail("missing label definition for axis '" .. axis .. "'")
    end

    if axis_spec.values then
      self.state.labels[axis] = build_labels_auto(axis_spec, axis)
    else
      self.state.labels[axis] = build_labels_manual(axis_spec, axis)
    end
  end
  return self
end

function Plot:_emit_grid(spec)
  spec = spec or {}
  local w = self.state.window
  local tx = self.state.ticks.x
  local ty = self.state.ticks.y
  if not (w and tx and ty) then
    fail("window and ticks must be defined before drawing grid")
  end

  local draw_major = (spec.draw_major ~= false)
  local draw_minor = (spec.draw_minor ~= false)

  local lines = {}
  lines[#lines + 1] = "pickup pencircle scaled 0.3bp;"

  for _, t in ipairs(tx) do
    if (t.kind == "major" and draw_major) or (t.kind == "minor" and draw_minor) then
      local x, _ = self:world_to_device(t.value, 0)
      lines[#lines + 1] = ("draw ((%s,%s)--(%s,%s));"):format(
        fmt_num(x), fmt_num(0), fmt_num(x), fmt_num(w.height)
      )
    end
  end

  for _, t in ipairs(ty) do
    if (t.kind == "major" and draw_major) or (t.kind == "minor" and draw_minor) then
      local _, y = self:world_to_device(0, t.value)
      lines[#lines + 1] = ("draw ((%s,%s)--(%s,%s));"):format(
        fmt_num(0), fmt_num(y), fmt_num(w.width), fmt_num(y)
      )
    end
  end

  return table.concat(lines, "\n")
end

function Plot:_emit_axes(spec)
  spec = spec or {}
  local w = self.state.window
  local tx = self.state.ticks.x
  local ty = self.state.ticks.y
  local lx = self.state.labels.x
  local ly = self.state.labels.y
  if not (w and tx and ty and lx and ly) then
    fail("window, ticks and labels must be defined before drawing axes")
  end

  local xlabel = spec.xlabel or "\\m{x}"
  local ylabel = spec.ylabel or "\\m{y}"
  local xlabel_placement = normalize_placement(spec.xlabel_placement, "bottom")
  local ylabel_placement = normalize_placement(spec.ylabel_placement, "left")

  local xaxis = normalize_axis_end_options(spec.xaxis)
  local yaxis = normalize_axis_end_options(spec.yaxis)

  local x_pos_arrow_gap = parse_dim(xaxis.positive_end.arrow_gap)
  local y_pos_arrow_gap = parse_dim(yaxis.positive_end.arrow_gap)

  local x_axis_end = math.max(0, w.width - x_pos_arrow_gap)
  local y_axis_end = math.max(0, w.height - y_pos_arrow_gap)

  local lines = {}
  lines[#lines + 1] = "pickup pencircle scaled 0.8bp;"

  lines[#lines + 1] = ("drawarrow ((%s,%s)--(%s,%s));"):format(
    fmt_num(0), fmt_num(w.origin_y), fmt_num(x_axis_end), fmt_num(w.origin_y)
  )
  lines[#lines + 1] = ("drawarrow ((%s,%s)--(%s,%s));"):format(
    fmt_num(w.origin_x), fmt_num(0), fmt_num(w.origin_x), fmt_num(y_axis_end)
  )

  for _, t in ipairs(tx) do
    if terminal_tick_is_visible(t.value, w.xmin, w.xmax, xaxis) then
      local x, y = self:world_to_device(t.value, 0)
      local h = tick_half_length(t.kind)
      lines[#lines + 1] = ("draw ((%s,%s)--(%s,%s));"):format(
        fmt_num(x), fmt_num(y - h), fmt_num(x), fmt_num(y + h)
      )
    end
  end

  for _, t in ipairs(ty) do
    if terminal_tick_is_visible(t.value, w.ymin, w.ymax, yaxis) then
      local x, y = self:world_to_device(0, t.value)
      local h = tick_half_length(t.kind)
      lines[#lines + 1] = ("draw ((%s,%s)--(%s,%s));"):format(
        fmt_num(x - h), fmt_num(y), fmt_num(x + h), fmt_num(y)
      )
    end
  end

  for _, item in ipairs(lx.items) do
    if terminal_tick_is_visible(item.value, w.xmin, w.xmax, xaxis) then
      local x, y = self:world_to_device(item.value, 0)
      x, y = apply_placement_offset(x, y, lx.placement, lx.distance)
      lines[#lines + 1] = ("%s(%s, (%s,%s));"):format(
        placement_to_mp_command(lx.placement), mp_quote(item.text), fmt_num(x), fmt_num(y)
      )
    end
  end

  for _, item in ipairs(ly.items) do
    if terminal_tick_is_visible(item.value, w.ymin, w.ymax, yaxis) then
      local x, y = self:world_to_device(0, item.value)
      x, y = apply_placement_offset(x, y, ly.placement, ly.distance)
      lines[#lines + 1] = ("%s(%s, (%s,%s));"):format(
        placement_to_mp_command(ly.placement), mp_quote(item.text), fmt_num(x), fmt_num(y)
      )
    end
  end

  do
    local x, y = x_axis_end, w.origin_y
    x, y = apply_placement_offset(x, y, xlabel_placement, xaxis.label_distance)
    lines[#lines + 1] = ("%s(%s, (%s,%s));"):format(
      placement_to_mp_command(xlabel_placement), mp_quote(xlabel), fmt_num(x), fmt_num(y)
    )
  end

  do
    local x, y = w.origin_x, y_axis_end
    x, y = apply_placement_offset(x, y, ylabel_placement, yaxis.label_distance)
    lines[#lines + 1] = ("%s(%s, (%s,%s));"):format(
      placement_to_mp_command(ylabel_placement), mp_quote(ylabel), fmt_num(x), fmt_num(y)
    )
  end

  return table.concat(lines, "\n")
end

function Plot:_emit_point(x, y, spec)
  spec = spec or {}
  local dx, dy = self:world_to_device(x, y)
  local pen = spec.pen or "1bp"
  return ("pickup pencircle scaled %s; drawdot (%s,%s);"):format(
    pen, fmt_num(dx), fmt_num(dy)
  )
end

function Plot:_emit_tex_label(text, x, y, spec)
  spec = spec or {}
  local dx, dy = self:world_to_device(x, y)
  local placement = normalize_placement(spec.placement, "top")
  dx, dy = apply_placement_offset(dx, dy, placement, spec.distance or "0mm")
  if spec.dx then dx = dx + parse_dim(spec.dx) end
  if spec.dy then dy = dy + parse_dim(spec.dy) end
  return ("%s(textext(%s), (%s,%s));"):format(
    placement_to_mp_command(placement), mp_quote(text), fmt_num(dx), fmt_num(dy)
  )
end

function Plot:_emit_function(spec)
  if type(spec) ~= "table" then
    fail("add_function expects a table")
  end
  local w = self.state.window
  if not w then
    fail("window must be defined before drawing function")
  end

  local expr = spec.expression
  local samples = tonumber_strict(spec.samples or 400, "samples")
  samples = math.max(2, math.floor(samples))

  local f = compile_function_1_1_factory(expr)
  local points = {}

  for i = 0, samples do
    local x = w.xmin + (w.xmax - w.xmin) * i / samples
    local ok, y = pcall(f, x)
    if ok and type(y) == "number" and y == y and y ~= math.huge and y ~= -math.huge then
      local dx, dy = self:world_to_device(x, y)
      points[#points + 1] = { dx, dy }
    end
  end

  if #points < 2 then
    fail("not enough valid points to draw function")
  end

  local clip_path = build_clip_path(self, spec.clip)
  local lines = {}
  lines[#lines + 1] = "save p, q; path p; picture q;"
  lines[#lines + 1] = "p :="

  local segs = {}
  for _, point in ipairs(points) do
    segs[#segs + 1] = ("(%s,%s)"):format(fmt_num(point[1]), fmt_num(point[2]))
  end

  lines[#lines + 1] = table.concat(segs, "--") .. ";"
  lines[#lines + 1] = "q := image(draw p;);"
  lines[#lines + 1] = ("clip q to %s;"):format(clip_path)
  lines[#lines + 1] = "draw q;"

  return table.concat(lines, "\n")
end

function Plot:compile_function_1_1(expr)
  return compile_function_1_1_factory(expr)
end

function Plot:add_grid(spec)
  return self:add_layer(self:_emit_grid(spec))
end

function Plot:add_axes(spec)
  return self:add_layer(self:_emit_axes(spec))
end

function Plot:add_function(spec)
  return self:add_layer(self:_emit_function(spec))
end

function Plot:add_point(x, y, spec)
  return self:add_layer(self:_emit_point(x, y, spec))
end

function Plot:add_tex_label(text, x, y, spec)
  return self:add_layer(self:_emit_tex_label(text, x, y, spec))
end

function plotmod.create_plot()
  return Plot:new()
end

return plotmod
