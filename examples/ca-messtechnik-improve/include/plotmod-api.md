# plotmod API

`plotmod.lua` is a Cartesian plot helper for **ConTeXt / LuaMetaTeX**.

This document describes both

- the **stable public API** you should use in documents and scripts, and
- the **internal / not stable API** that exists inside the module but may change without notice.

The goal of this file is practical use: you should be able to open it later, remember the module structure quickly, and copy working patterns from it.

**Lua string escaping:** In the examples below, ConTeXt commands inside quoted Lua
strings need a doubled backslash (for example `"\\m{x}"`). Otherwise Lua either
rejects the escape (`\m`) or silently interprets it as a control character
(`\f`, `\r`). Alternatively use a Lua long string like `[[\m{x}]]`.
The full ConTeXt example in the next section has been compiled with ConTeXt LMTX.


---

## 1. Overview

`plotmod` is an **object API only** module.

A typical use looks like this:

```lua
local p = require("plotmod")
local plot = p.create_plot()

local f_expr = "10*x*exp(-0.25*x)"
local f = plot:compile_function_1_1(f_expr)

plot:set_window{
  xmin = 0, xmax = 8,
  ymin = 0, ymax = 16,
  xunit = "1.15cm",
  yunit = "0.45cm",
}

plot:define_ticks{
  x = { major_step = 1, minor_subdivisions = 1 },
  y = { major_step = 2, minor_subdivisions = 1 },
}

plot:define_labels{
  x = {
    values = {0,1,2,3,4,5,6,7,8},
    formatter = function(v) return "\\m{" .. tostring(v) .. "}" end,
    placement = "bottom",
    distance = "2mm",
  },
  y = {
    values = {0,2,4,6,8,10,12,14,16},
    formatter = function(v) return "\\m{" .. tostring(v) .. "}" end,
    placement = "left",
    distance = "2mm",
  },
}

plot
  :add_grid{ draw_major = true, draw_minor = true }
  :add_axes{
    xlabel = "\\m{t/\\unit{hour}}",
    ylabel = "\\m{\\frac{N}{t}/\\frac{1}{\\unit{hour}}}",
  }
  :add_function{
    expression = f_expr,
    samples = 600,
    clip = "window",
  }
  :add_point(4, 40/math.exp(1))
  :add_tex_label(
    "\\m{\\left(4 \\mid \\frac{40}{e}\\right)}",
    4,
    40/math.exp(1),
    { placement = "top", distance = "8bp" }
  )

local mp_code = plot:render()
```

Typical ConTeXt use:

```tex
\startluacode
userdata = userdata or {}
package.path = "../include/?.lua;" .. package.path
userdata.plotmod = require("plotmod")

local p = userdata.plotmod
local plot = p.create_plot()

local f_expr = "10*x*exp(-0.25*x)"
local f = plot:compile_function_1_1(f_expr)

plot:set_window{
  xmin  = 0,
  xmax  = 8,
  ymin  = 0,
  ymax  = 16,
  xunit = "1.15cm",
  yunit = "0.45cm",
}

plot:define_ticks{
  x = { major_step = 1, minor_subdivisions = 1 },
  y = { major_step = 2, minor_subdivisions = 1 },
}

plot:define_labels{
  x = {
    values = {0,1,2,3,4,5,6,7,8},
    formatter = function(v)
      return "\\m{" .. tostring(v) .. "}"
    end,
    placement = "bottom",
    distance = "2mm",
  },
  y = {
    values = {0,2,4,6,8,10,12,14,16},
    formatter = function(v)
      return "\\m{" .. tostring(v) .. "}"
    end,
    placement = "left",
    distance = "2mm",
  }
}

plot
  :add_grid{ draw_major = true, draw_minor = true }
  :add_axes{
    xlabel = "\\m{t/\\unit{hour}}",
    ylabel = "\\m{\\frac{N}{t}/\\frac{1}{\\unit{hour}}}",
    xaxis = {
      label_distance = "4mm",
      positive_end = {
        arrow_gap = "2.5mm",
        suppress_terminal_tick = true,
      },
      negative_end = {
        suppress_terminal_tick = false,
      },
    },
    yaxis = {
      label_distance = "4mm",
      positive_end = {
        arrow_gap = "2.5mm",
        suppress_terminal_tick = true,
      },
      negative_end = {
        suppress_terminal_tick = false,
      },
    },
  }
  :add_function{
    expression = f_expr,
    samples = 600,
    clip = "window",
  }
  :add_point(4, 40/math.exp(1))
  :add_tex_label(
    "\\m{\\left(4 \\mid \\frac{40}{e}\\right)}",
    4,
    40/math.exp(1),
    {
      placement = "top",
      distance = "8bp",
    }
  )

userdata.plot_code = plot:render()
\stopluacode

\startMPcode
\ctxlua{context(userdata.plot_code)}
\stopMPcode
```

---

## 2. Public API (stable)

Only the API in this section is considered stable.

### 2.1 Module function

#### `plotmod.create_plot()`

Create a new plot object.

```lua
local p = require("plotmod")
local plot = p.create_plot()
```

Returns a new independent plot object.

#### `plot:compile_function_1_1(expr)`

Compile a scalar real-to-real function from an expression string.

This method is intended for functions of the form `x -> y`.

```lua
local f_expr = "6*x/(x^2+9)"
local f = plot:compile_function_1_1(f_expr)

local y = f(3)
```

Typical use:

```lua
local f_expr = "6*x/(x^2+9)"
local g_expr = "-(x^2-2*x-9)/6"

local f = plot:compile_function_1_1(f_expr)
local g = plot:compile_function_1_1(g_expr)

for i = 0, 120 do
  local x = 3 * i / 120
  local y = f(x)
end

plot
  :add_function{ expression = f_expr, samples = 1000, clip = "window" }
  :add_function{ expression = g_expr, samples = 1000, clip = "window" }
```

Notes:

- the expression is compiled in the same environment used by `add_function`
- the variable name is `x`
- the returned value is a normal Lua function callable as `f(x)`

---

### 2.2 Plot methods

### `plot:set_window{...}`

Define the plot window and scaling.

You must call this before ticks, labels, or drawing.

Supported forms:

#### Variant A: explicit units

```lua
plot:set_window{
  xmin = 0,
  xmax = 8,
  ymin = 0,
  ymax = 16,
  xunit = "1.15cm",
  yunit = "0.45cm",
}
```

#### Variant B: common unit

```lua
plot:set_window{
  xmin = -5,
  xmax = 5,
  ymin = -3,
  ymax = 3,
  unit = "8mm",
}
```

#### Variant C: explicit total size

```lua
plot:set_window{
  xmin = -2,
  xmax = 2,
  ymin = -1,
  ymax = 1,
  width = "10cm",
  height = "5cm",
}
```

Rules:

- `xmin <= 0 <= xmax` is required
- `ymin <= 0 <= ymax` is required
- the x-range and y-range must both be non-zero
- use either
  - `unit`, or
  - `xunit` + `yunit`, or
  - `width` + `height`

---

### `plot:define_ticks{...}`

Define tick marks on the x- and y-axis.

You must call `set_window` first.

#### Automatic ticks

```lua
plot:define_ticks{
  x = {
    major_step = 1,
    minor_subdivisions = 1,
  },
  y = {
    major_step = 2,
    minor_subdivisions = 1,
  },
}
```

Meaning:

- `major_step` = spacing of major ticks
- `minor_subdivisions` = number of minor ticks inserted between adjacent major ticks

#### Manual ticks

```lua
plot:define_ticks{
  x = {
    { value = 0, kind = "major" },
    { value = 0.5, kind = "minor" },
    { value = 1, kind = "major" },
  },
  y = {
    { value = 0, kind = "major" },
    { value = 5, kind = "major" },
    { value = 10, kind = "major" },
  },
}
```

Allowed tick kinds:

- `"major"`
- `"minor"`

---

### `plot:define_labels{...}`

Define axis labels for x and y ticks.

You normally call this after `define_ticks`.

#### Automatic labels

```lua
plot:define_labels{
  x = {
    values = {0,1,2,3,4,5,6,7,8},
    formatter = function(v)
      return "\\m{" .. tostring(v) .. "}"
    end,
    placement = "bottom",
    distance = "2mm",
  },
  y = {
    values = {0,2,4,6,8,10,12,14,16},
    formatter = function(v)
      return "\\m{" .. tostring(v) .. "}"
    end,
    placement = "left",
    distance = "2mm",
  },
}
```

#### Manual labels

```lua
plot:define_labels{
  x = {
    { value = 0, text = "\\m{0}" },
    { value = 2, text = "\\m{2}" },
    { value = 4, text = "\\m{4}" },
    placement = "bottom",
    distance = "2mm",
  },
  y = {
    { value = 0, text = "\\m{0}" },
    { value = 5, text = "\\m{5}" },
    { value = 10, text = "\\m{10}" },
    placement = "left",
    distance = "2mm",
  },
}
```

Supported keys:

- `placement`
- `distance`

There is no `align` and no legacy side alias in the stable API.

#### Allowed `placement` values

- `center`
- `top`
- `bottom`
- `left`
- `right`
- `top_left`
- `top_right`
- `bottom_left`
- `bottom_right`

Notes:

- For x labels the natural default is `bottom`
- For y labels the natural default is `left`

---

### `plot:add_grid{...}`

Add grid lines as a layer.

```lua
plot:add_grid{
  draw_major = true,
  draw_minor = true,
}
```

Defaults:

- `draw_major = true`
- `draw_minor = true`

Example:

```lua
plot:add_grid{ draw_major = true, draw_minor = false }
```

---

### `plot:add_axes{...}`

Add axes, tick marks, tick labels, and axis labels as a layer.

```lua
plot:add_axes{
  xlabel = "\\m{x}",
  ylabel = "\\m{y}",
}
```

More complete example:

```lua
plot:add_axes{
  xlabel = "\\m{t/\\unit{hour}}",
  ylabel = "\\m{\\frac{N}{t}/\\frac{1}{\\unit{hour}}}",
  xlabel_placement = "bottom_right",
  ylabel_placement = "top_left",

  xaxis = {
    label_distance = "4mm",
    positive_end = {
      arrow_gap = "2.5mm",
      suppress_terminal_tick = true,
    },
    negative_end = {
      arrow_gap = "0mm",
      suppress_terminal_tick = false,
    },
  },

  yaxis = {
    label_distance = "4mm",
    positive_end = {
      arrow_gap = "2.5mm",
      suppress_terminal_tick = true,
    },
    negative_end = {
      arrow_gap = "0mm",
      suppress_terminal_tick = false,
    },
  },
}
```

Supported top-level keys:

- `xlabel`
- `ylabel`
- `xlabel_placement`
- `ylabel_placement`
- `xaxis`
- `yaxis`

Supported nested keys inside `xaxis` / `yaxis`:

- `label_distance`
- `positive_end.arrow_gap`
- `positive_end.suppress_terminal_tick`
- `negative_end.arrow_gap`
- `negative_end.suppress_terminal_tick`

Notes:

- the axis line is drawn with an arrow toward the positive end
- positive and negative terminal ticks can be suppressed independently
- axis labels also use `placement`

---

### `plot:add_function{...}`

Add a function graph as a layer.

```lua
plot:add_function{
  expression = "10*x*exp(-0.25*x)",
  samples = 600,
  clip = "window",
}
```

Supported keys:

- `expression` — Lua-style expression in variable `x`
- `samples` — number of sample intervals, default `400`
- `clip` — either
  - `"window"`
  - `nil`
  - a rectangle table

Example with custom clipping rectangle:

```lua
plot:add_function{
  expression = "sin(x)",
  samples = 800,
  clip = {
    xmin = -3.14,
    xmax = 3.14,
    ymin = -1.2,
    ymax = 1.2,
  },
}
```

### Expression environment

Inside `expression`, the following are available directly:

- `abs`
- `acos`
- `asin`
- `atan`
- `ceil`
- `cos`
- `exp`
- `floor`
- `log`
- `max`
- `min`
- `pi`
- `sin`
- `sqrt`
- `tan`

Also available:

- `math`

Example:

```lua
plot:add_function{
  expression = "sin(x) + 0.5*cos(2*x)",
  samples = 1000,
  clip = "window",
}
```

Notes:

- invalid or non-finite sample points are skipped
- at least two valid points are required

---

### `plot:add_point(x, y [, spec])`

Add a point marker as a layer.

```lua
plot:add_point(4, 40/math.exp(1))
```

With explicit pen size:

```lua
plot:add_point(4, 40/math.exp(1), {
  pen = "1bp",
})
```

Supported keys in `spec`:

- `pen`

---

### `plot:add_tex_label(text, x, y [, spec])`

Add a free-standing TeX label as a layer.

```lua
plot:add_tex_label(
  "\\m{\\left(4 \\mid \\frac{40}{e}\\right)}",
  4,
  40/math.exp(1),
  {
    placement = "top",
    distance = "8bp",
  }
)
```

Supported keys:

- `placement`
- `distance`
- `dx`
- `dy`

Example with diagonal placement and fine correction:

```lua
plot:add_tex_label(
  "\\m{A}",
  1,
  2,
  {
    placement = "top_right",
    distance = "2mm",
    dx = "1mm",
    dy = "0.5mm",
  }
)
```

Notes:

- `placement` determines anchor direction like MetaPost label placement
- `distance` applies along the placement direction
- `dx` and `dy` add extra manual correction afterward

---

### `plot:add_raw_mp(code)`

Append raw MetaPost code directly as a layer.

```lua
plot:add_raw_mp("draw ((0,0)--(10,10));")
```

This is the escape hatch if the existing API is not enough.

---

### `plot:render()`

Return the complete MetaPost code for all layers.

```lua
local mp_code = plot:render()
```

Usually this is the normal output path.

---

### `plot:render_image()`

Return the layers wrapped as a MetaPost `image(...)` expression.

```lua
local img = plot:render_image()
```

Useful when you want a picture expression rather than raw sequential code.

---

### `plot:clear_layers()`

Remove all currently collected render layers.

```lua
plot:clear_layers()
```

The plot state remains intact:

- window stays
- ticks stay
- labels stay

Only the render layer list is cleared.

---

### `plot:clone()`

Create a deep copy of the full plot object.

```lua
local plot2 = plot:clone()
plot2:add_point(1, 2)
```

The clone contains:

- copied window state
- copied ticks
- copied labels
- copied layers

Useful for creating variants of the same base plot.

---

## 3. Public API usage patterns

### 3.1 Recommended build order

Recommended order:

1. `create_plot()`
2. `set_window{...}`
3. `define_ticks{...}`
4. `define_labels{...}`
5. add layers with `add_*`
6. `render()` or `render_image()`

### 3.2 State vs layers

The plot object has two conceptual parts:

- **state**
  - window
  - ticks
  - labels
- **layers**
  - grid
  - axes
  - functions
  - points
  - labels
  - raw MetaPost additions

Changing state later does not retroactively rewrite already generated layers. Layers contain emitted MetaPost code at the time they are added.

So this is usually a bad idea:

```lua
plot:add_axes{...}
plot:define_labels{...} -- too late for the already emitted axes layer
```

Prefer to finalize the state first, then add layers.

---

## 4. Internal / not stable API

Everything in this section is **not stable** and may change at any time.

Do not rely on these names in normal documents unless you are prepared to update code later.

### Internal helper functions

These are file-local helpers and not part of the public API:

- `fail`
- `deepcopy`
- `tonumber_strict`
- `parse_dim`
- `fmt_num`
- `nearly_equal`
- `mp_quote`
- `normalize_axis_window`
- `axis_length`
- `normalize_placement`
- `placement_to_mp_command`
- `apply_placement_offset`
- `normalize_label_axis_spec`
- `tick_half_length`
- `normalize_axis_end_options`
- `axis_value_is_terminal`
- `terminal_tick_is_visible`
- `build_ticks_auto`
- `build_ticks_manual`
- `build_labels_auto`
- `build_labels_manual`
- `build_clip_path`
- `compile_function_1_1_factory`

These names are documented here for maintenance only.

---

### Internal Plot methods

These methods exist on plot objects but are considered internal:

- `_emit_grid`
- `_emit_axes`
- `_emit_point`
- `_emit_tex_label`
- `_emit_function`
- `add_layer`
- `world_to_device`
- `device_rect_for_world_rect`
- `make_window_clip_rect`
- `make_custom_clip_rect`

### Why they are internal

- `_emit_*` methods are implementation helpers that return MetaPost code strings
- low-level geometry helpers may be renamed, moved, or refactored later
- `add_layer` is public in the Lua sense but should be treated as internal structure support

### Maintenance example

If you are maintaining the module itself, this can be useful:

```lua
local plot = p.create_plot()
plot:set_window{ xmin = 0, xmax = 10, ymin = 0, ymax = 10, unit = "1cm" }

local x, y = plot:world_to_device(5, 5)
```

But for ordinary use in documents, prefer the stable public methods.

---

## 5. Supported placement values

The stable placement vocabulary is:

- `center`
- `top`
- `bottom`
- `left`
- `right`
- `top_left`
- `top_right`
- `bottom_left`
- `bottom_right`

The module currently also normalizes some synonyms internally, such as `centre`, `bot`, `lft`, `rt`, `ulft`, `urt`, `llft`, `lrt`, but these should be treated as an internal convenience, not as the preferred public spelling.

Recommended style in documents:

- always use the canonical spellings above
- prefer underscores instead of dashes
- do not depend on shorthand aliases in your own source files

---

## 6. Error behavior

The module fails eagerly with descriptive messages via `error("plotmod: ...")`.

Typical failure cases:

- invalid or missing numeric values
- invalid window range
- using ticks before defining a window
- using labels before defining required state
- invalid `placement`
- invalid function expression
- too few valid sample points for a function

Example:

```lua
plot:set_window{
  xmin = 5,
  xmax = 1,
  ymin = 0,
  ymax = 10,
  unit = "1cm",
}
```

This fails because `xmin` must be `<= xmax`.

---

## 7. Compatibility policy

This section defines the intended compatibility rules for future work.

### Stable API

Only the following are considered stable:

- `plotmod.create_plot`
- `Plot:compile_function_1_1`
- `Plot:set_window`
- `Plot:define_ticks`
- `Plot:define_labels`
- `Plot:add_grid`
- `Plot:add_axes`
- `Plot:add_function`
- `Plot:add_point`
- `Plot:add_tex_label`
- `Plot:add_raw_mp`
- `Plot:render`
- `Plot:render_image`
- `Plot:clear_layers`
- `Plot:clone`

### Not stable

Everything else is not stable, especially:

- all `_emit_*` methods
- all helper functions
- low-level geometry methods
- internal normalization details
- internal state layout

### Change policy

Intended policy going forward:

- additive improvements are preferred over breaking changes
- if the stable public API changes, this should be treated as a **real API change**
- if possible, a migration note or migration script should be provided
- internal APIs may be changed freely when this improves clarity or implementation quality

### Practical rule of thumb

If you are writing normal document code, stay inside the stable API section of this document.

If you touch internal names, you are writing maintenance code and should expect future edits.

---

## 8. Recommended style for future documents

For long-term maintainability, prefer this style:

```lua
local p = require("plotmod")
local plot = p.create_plot()

plot:set_window{ ... }
plot:define_ticks{ ... }
plot:define_labels{ ... }

plot
  :add_grid{ ... }
  :add_axes{ ... }
  :add_function{ ... }
  :add_point(...)
  :add_tex_label(...)

local mp_code = plot:render()
```

Recommendations:

- define state first, then add layers
- use canonical `placement` names only
- prefer table-based configuration over ad-hoc raw MP code
- use `add_raw_mp` only when the normal API is not enough
- use `clone()` when you need plot variants
- keep internal names out of ordinary document sources

---

## 9. Quick reference

### Stable module function

- `create_plot()`

### Stable plot methods

- `compile_function_1_1(expr)`
- `set_window{...}`
- `define_ticks{...}`
- `define_labels{...}`
- `add_grid{...}`
- `add_axes{...}`
- `add_function{...}`
- `add_point(x, y [, spec])`
- `add_tex_label(text, x, y [, spec])`
- `add_raw_mp(code)`
- `render()`
- `render_image()`
- `clear_layers()`
- `clone()`

### Canonical placement values

- `center`
- `top`
- `bottom`
- `left`
- `right`
- `top_left`
- `top_right`
- `bottom_left`
- `bottom_right`
