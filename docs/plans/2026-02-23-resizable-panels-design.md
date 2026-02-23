# Resizable Panels with Progressive Labels and Collapse Toggle

**Date:** 2026-02-23
**Status:** Approved

## Overview

Add resizable and collapsible left (tree) and right (workspace) panels with:
- Full-edge drag handles for resizing
- Pill-shaped collapse/expand toggles centered on panel edges
- Progressive badge label expansion (3 tiers based on panel width)
- localStorage persistence of layout state

## Panels

**Left panel** (tree/explorer) and **right panel** (workspace) are resizable and collapsible. The center pane (object editor) uses `flex: 1` and always fills remaining space.

## Approach

Custom JS `PanelResizer` module + CSS classes. No third-party dependencies. `ResizeObserver` triggers tier changes. CSS transitions handle collapse animations.

## Drag Handles

- Invisible `<div class="panel-resize-handle">` overlays on each panel's inner edge
- ~6px wide, absolutely positioned, full panel height, `z-index` above content
- Cursor: `col-resize` on the entire handle
- `mousedown` → `mousemove` (on `document`) → `mouseup` drag cycle
- Panel width clamped: `min: 200px`, `max: 50vw`
- Transparent overlay during drag to prevent iframe/selection interference
- `requestAnimationFrame` for smooth updates
- No CSS transition during active drag (re-added after mouseup)

## Collapse Pill Toggle

**Appearance:**
- Pill-shaped `<button>`, ~28px tall, ~14px wide
- Rounded corners (full border-radius)
- Subtle background matching border color, slight elevation (box-shadow)
- Small chevron arrow (`<`/`>`) indicating collapse direction
- Hover: more prominent background, cursor pointer

**Positioning:**
- Absolutely positioned relative to resize handle container
- `top: 50%; transform: translateY(-50%)` for vertical centering
- Sits on top of the resize handle

**Behavior:**
- **Collapse:** Panel animates to `width: 0` (~200ms ease). Content `overflow: hidden`. Pill remains visible.
- **Collapsed state:** Only pill visible, flush against edge. Chevron flips direction. Center pane expands.
- **Expand:** Panel animates back to previous stored width. Chevron flips back.
- Pill and drag handle coexist: clicking pill collapses, dragging edge resizes.

**Accessibility:**
- `<button>` element with `aria-label="Collapse left panel"` / `"Expand left panel"`

## Progressive Badge Labels (3 Tiers)

Driven by CSS classes on the panel container, set by `ResizeObserver`:

| Panel Width | CSS Class | Tier |
|---|---|---|
| < 280px | `panel-tier-compact` | Compact |
| 280–400px | `panel-tier-medium` | Medium |
| > 400px | `panel-tier-full` | Full |

### Left Panel: Object Type Badges

| Type | Compact | Medium | Full |
|---|---|---|---|
| host | HOST | HOST | HOST |
| hostgroup | HOSTGRP | HOSTGROUP | HOSTGROUP |
| service | SVC | SERVICE | SERVICE |
| servicegroup | SVCGRP | SERVICEGRP | SERVICEGROUP |
| contact | CONT | CONTACT | CONTACT |
| contactgroup | CONTGRP | CONTACTGRP | CONTACTGROUP |
| command | CMD | COMMAND | COMMAND |
| timeperiod | TP | TIMEPERIOD | TIMEPERIOD |
| servicedependency | SVCDEP | SVCDEP | SERVICEDEPENDENCY |
| hostdependency | HOSTDEP | HOSTDEP | HOSTDEPENDENCY |
| serviceescalation | SVCESC | SVCESC | SERVICEESCALATION |
| hostescalation | HOSTESC | HOSTESC | HOSTESCALATION |
| host (template) | HOSTTMPL | HOSTTMPL | HOST TEMPLATE |
| service (template) | SVCTMPL | SVCTMPL | SERVICE TEMPLATE |
| contact (template) | CONTTMPL | CONTTMPL | CONTACT TEMPLATE |
| command (template) | CMDTMPL | CMDTMPL | COMMAND TEMPLATE |
| timeperiod (template) | TPTMPL | TPTMPL | TIMEPERIOD TEMPLATE |

Each badge element gets `data-badge-compact`, `data-badge-medium`, `data-badge-full` attributes. On tier change, all badges in the panel get their `textContent` updated from the matching attribute (batch DOM update).

### Right Panel: Tab Labels

| Compact | Medium | Full |
|---|---|---|
| Files | Files | Files |
| Sugg | Suggestions | Suggestions |
| Valid | Validation | Validation |

Object type badges in suggestions/validation content also follow the panel's tier.

## Persistence

**localStorage key:** `nbe-panel-layout`

```json
{
  "leftWidth": 320,
  "rightWidth": 440,
  "leftCollapsed": false,
  "rightCollapsed": false
}
```

Saved on: drag end, collapse toggle click. Restored on: page load (before first paint to avoid layout flash).

## Edge Cases

- **Window resize:** If panel width exceeds new 50vw max, clamp it down
- **Both panels collapsed:** Center gets full width, both pills visible at edges
- **Double-click resize handle:** Reset panel to default width (nice-to-have)

## Files Changed

| File | Change |
|---|---|
| `static/js/explorer/panel-resizer.js` | **New** — PanelResizer module |
| `static/js/explorer/constants.js` | Add `typeBadgeTiers` and `tabLabelTiers` mappings |
| `static/js/explorer/app.js` | Initialize PanelResizer, update badge rendering with data attributes |
| `static/css/explorer.css` | Resize handle styles, pill toggle styles, panel transitions, tier classes |
| `templates/explorer.html` | Add resize handle elements and pill toggle buttons |
| `static/css/tokens.css` | CSS variables for handle/pill colors |
