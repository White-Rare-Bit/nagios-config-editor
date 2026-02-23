# Resizable Panels Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add resizable and collapsible left/right panels with progressive badge labels and localStorage persistence.

**Architecture:** Custom `PanelResizer` IIFE module in the Explorer namespace. Drag handles are flex items between panels. `ResizeObserver` sets tier CSS classes that drive badge text updates. Collapse pills are absolutely positioned buttons on the handles.

**Tech Stack:** Vanilla JS (IIFE pattern), CSS custom properties, `ResizeObserver`, `localStorage`

---

### Task 1: Add CSS Variables for Resize Infrastructure

**Files:**
- Modify: `static/css/tokens.css:220-223` (Layout section)

**Step 1: Add resize/panel CSS variables to tokens.css**

In `static/css/tokens.css`, after the existing `--nbe-panel-width` line (222), add new variables:

```css
    --nbe-panel-width: 320px;
    --nbe-panel-width-right: 440px;
    --nbe-panel-min-width: 200px;
    --nbe-panel-max-width-pct: 50;
    --nbe-resize-handle-width: 6px;
    --nbe-panel-tier-compact: 280;
    --nbe-panel-tier-medium: 400;
    --nbe-tree-width: 240px;
```

Note: `--nbe-panel-tier-compact` and `--nbe-panel-tier-medium` are unitless numbers used only by JS (CSS vars as a single source of truth). `--nbe-tree-width` already exists at line 223; keep it.

**Step 2: Verify no syntax errors**

Run: `python3 app.py &` then open `http://localhost:8080` — confirm page loads normally.

**Step 3: Commit**

```bash
git add static/css/tokens.css
git commit -m "feat(resize): add CSS variables for panel resize infrastructure"
```

---

### Task 2: Add Badge Tier Data to Constants

**Files:**
- Modify: `static/js/explorer/constants.js:27-49` (after TEMPLATE_BADGES), `:155-161` (getTypeBadge)

**Step 1: Add tier mappings after TEMPLATE_BADGES (line 49)**

In `static/js/explorer/constants.js`, after the `TEMPLATE_BADGES` object (line 49), add:

```javascript
    // Progressive badge tiers: compact (narrowest) → medium → full (widest)
    const TYPE_BADGE_TIERS = {
        host:               { compact: 'HOST',     medium: 'HOST',        full: 'HOST' },
        hostgroup:          { compact: 'HOSTGRP',  medium: 'HOSTGROUP',   full: 'HOSTGROUP' },
        service:            { compact: 'SVC',      medium: 'SERVICE',     full: 'SERVICE' },
        servicegroup:       { compact: 'SVCGRP',   medium: 'SERVICEGRP',  full: 'SERVICEGROUP' },
        contact:            { compact: 'CONT',     medium: 'CONTACT',     full: 'CONTACT' },
        contactgroup:       { compact: 'CONTGRP',  medium: 'CONTACTGRP',  full: 'CONTACTGROUP' },
        command:            { compact: 'CMD',      medium: 'COMMAND',     full: 'COMMAND' },
        timeperiod:         { compact: 'TP',       medium: 'TIMEPERIOD',  full: 'TIMEPERIOD' },
        servicedependency:  { compact: 'SVCDEP',   medium: 'SVCDEP',      full: 'SERVICEDEPENDENCY' },
        hostdependency:     { compact: 'HOSTDEP',  medium: 'HOSTDEP',     full: 'HOSTDEPENDENCY' },
        serviceescalation:  { compact: 'SVCESC',   medium: 'SVCESC',      full: 'SERVICEESCALATION' },
        hostescalation:     { compact: 'HOSTESC',  medium: 'HOSTESC',     full: 'HOSTESCALATION' }
    };

    const TEMPLATE_BADGE_TIERS = {
        host:       { compact: 'HOSTTMPL',  medium: 'HOSTTMPL',  full: 'HOST TEMPLATE' },
        service:    { compact: 'SVCTMPL',   medium: 'SVCTMPL',   full: 'SERVICE TEMPLATE' },
        contact:    { compact: 'CONTTMPL',  medium: 'CONTTMPL',  full: 'CONTACT TEMPLATE' },
        command:    { compact: 'CMDTMPL',   medium: 'CMDTMPL',   full: 'COMMAND TEMPLATE' },
        timeperiod: { compact: 'TPTMPL',    medium: 'TPTMPL',    full: 'TIMEPERIOD TEMPLATE' }
    };

    // Right panel tab label tiers
    const TAB_LABEL_TIERS = {
        files:       { compact: 'Files', medium: 'Files',       full: 'Files' },
        suggestions: { compact: 'Sugg',  medium: 'Suggestions', full: 'Suggestions' },
        validation:  { compact: 'Valid', medium: 'Validation',  full: 'Validation' }
    };
```

**Step 2: Expose tier data on Explorer.constants**

In the `Explorer.constants` object (starts ~line 59), add these properties alongside the existing `typeBadges` and `templateBadges`:

```javascript
        typeBadgeTiers: TYPE_BADGE_TIERS,
        templateBadgeTiers: TEMPLATE_BADGE_TIERS,
        tabLabelTiers: TAB_LABEL_TIERS,
```

**Step 3: Add helper function for tiered badge text**

After the existing `Explorer.getTypeBadge` function (~line 161), add:

```javascript
    /**
     * Get badge text for a specific tier.
     * @param {string} objectType - e.g. 'host', 'service'
     * @param {boolean} isTemplate - whether this is a template
     * @param {'compact'|'medium'|'full'} tier - the display tier
     * @returns {string} badge text for the given tier
     */
    Explorer.getTypeBadgeTier = function(objectType, isTemplate, tier) {
        const c = Explorer.constants;
        if (isTemplate && c.templateBadgeTiers[objectType]) {
            return c.templateBadgeTiers[objectType][tier] || c.templateBadges[objectType] || objectType;
        }
        if (c.typeBadgeTiers[objectType]) {
            return c.typeBadgeTiers[objectType][tier] || c.typeBadges[objectType] || objectType;
        }
        return objectType;
    };
```

**Step 4: Verify page still loads**

Refresh `http://localhost:8080` — confirm explorer loads without console errors.

**Step 5: Commit**

```bash
git add static/js/explorer/constants.js
git commit -m "feat(resize): add badge tier data and getTypeBadgeTier helper"
```

---

### Task 3: Update Badge Rendering with Data Attributes

**Files:**
- Modify: `static/js/explorer/app.js:727-773` (renderTreeItem function)
- Modify: `static/js/explorer/app.js:549-561` (renderStagedCreation function)

**Step 1: Update renderTreeItem to include data attributes**

In `static/js/explorer/app.js`, the `renderTreeItem` function (line 727). Find the line that creates `typeLabel` (line 739):

```javascript
    const typeLabel = Explorer.getTypeBadge(obj.object_type, isTemplate);
```

After it, add tier data:

```javascript
    const badgeCompact = Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'compact');
    const badgeMedium = Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'medium');
    const badgeFull = Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'full');
```

Then update both badge `<span>` elements in the template (lines 752 and 770). Replace the existing badge spans:

**Line 752** (deleted items) — change from:
```javascript
            ${showType ? '' : `<span class="tree-item-type type-${obj.object_type}" title="${obj.object_type}">${typeLabel}</span>`}
```
To:
```javascript
            ${showType ? '' : `<span class="tree-item-type type-${obj.object_type}" title="${obj.object_type}" data-badge-compact="${badgeCompact}" data-badge-medium="${badgeMedium}" data-badge-full="${badgeFull}">${typeLabel}</span>`}
```

**Line 770** (normal items) — same change: add the three `data-badge-*` attributes to the existing `<span>`.

**Step 2: Update renderStagedCreation (~line 559)**

Find line 559:
```javascript
            <span class="tree-item-type type-${creation.object_type}" title="${Explorer.escapeHtml(creation.object_type)}">${Explorer.getTypeBadge(creation.object_type)}</span>
```

Replace with:
```javascript
            <span class="tree-item-type type-${creation.object_type}" title="${Explorer.escapeHtml(creation.object_type)}" data-badge-compact="${Explorer.getTypeBadgeTier(creation.object_type, false, 'compact')}" data-badge-medium="${Explorer.getTypeBadgeTier(creation.object_type, false, 'medium')}" data-badge-full="${Explorer.getTypeBadgeTier(creation.object_type, false, 'full')}">${Explorer.getTypeBadge(creation.object_type)}</span>
```

**Step 3: Verify data attributes appear**

Open explorer, right-click a tree item badge, "Inspect Element". Confirm `data-badge-compact`, `data-badge-medium`, `data-badge-full` attributes are present.

**Step 4: Commit**

```bash
git add static/js/explorer/app.js
git commit -m "feat(resize): add badge tier data attributes to tree item rendering"
```

---

### Task 4: Add HTML Resize Handles and Pill Toggles

**Files:**
- Modify: `templates/explorer.html:11-109` (explorer layout)

**Step 1: Add id to tree-panel and insert resize handles**

In `templates/explorer.html`, the explorer layout starts at line 11. We need to:
1. Add `id="treePanel"` to the tree-panel div (line 13)
2. Insert a left resize handle between the tree-panel closing tag and the center-pane
3. Insert a right resize handle between the center-pane closing tag and the right-pane

After the tree-panel closing `</div>` (currently line ~55) and before the center-pane comment, insert:

```html
    <!-- Left Resize Handle -->
    <div class="panel-resize-handle panel-resize-handle--left" id="leftResizeHandle">
        <button class="panel-collapse-pill" id="leftCollapsePill"
                aria-label="Collapse left panel" title="Collapse panel">
            <i class="fa-solid fa-chevron-left"></i>
        </button>
    </div>
```

After the center-pane closing `</div>` (currently line ~106) and before the right-pane comment, insert:

```html
    <!-- Right Resize Handle -->
    <div class="panel-resize-handle panel-resize-handle--right" id="rightResizeHandle">
        <button class="panel-collapse-pill" id="rightCollapsePill"
                aria-label="Collapse right panel" title="Collapse panel">
            <i class="fa-solid fa-chevron-right"></i>
        </button>
    </div>
```

**Step 2: Add panel-resizer.js script tag**

In the scripts block (~line 280-297), add the panel-resizer script **after** `constants.js` (line 281) and **before** `state-management.js` (line 282). It needs to load early so it can apply saved widths before the tree renders:

```html
<script src="{{ url_for('static', filename='js/explorer/panel-resizer.js') }}"></script>
```

**Step 3: Verify page structure**

Refresh page. The handles won't be visible yet (no CSS), but check the DOM in DevTools — confirm `#leftResizeHandle` and `#rightResizeHandle` exist between the panels.

**Step 4: Commit**

```bash
git add templates/explorer.html
git commit -m "feat(resize): add resize handle and pill toggle HTML elements"
```

---

### Task 5: Add CSS for Resize Handles, Pill Toggles, and Tier Classes

**Files:**
- Modify: `static/css/explorer.css:352-369` (after .explorer), `:818-831` (tree-item-type), `:1191-1201` (right-pane)

**Step 1: Add resize handle and pill toggle CSS**

In `static/css/explorer.css`, after the `.explorer` rule (line 358), add:

```css
/* ---- Panel Resize Handles ---- */
.panel-resize-handle {
    width: var(--nbe-resize-handle-width);
    cursor: col-resize;
    position: relative;
    flex-shrink: 0;
    z-index: 10;
    background: transparent;
    transition: background 0.15s ease;
}

.panel-resize-handle:hover {
    background: var(--nbe-dark-accent-primary);
}

.panel-resize-handle.is-dragging {
    background: var(--nbe-dark-accent-primary);
}

/* Collapse pill toggle */
.panel-collapse-pill {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 16px;
    height: 32px;
    border: 1px solid var(--nbe-dark-border-secondary);
    border-radius: 8px;
    background: var(--nbe-dark-bg-elevated);
    color: var(--nbe-dark-text-secondary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    font-size: 8px;
    z-index: 11;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
    opacity: 0;
}

.panel-resize-handle:hover .panel-collapse-pill,
.panel-collapse-pill:focus-visible {
    opacity: 1;
}

.panel-collapse-pill:hover {
    background: var(--nbe-dark-accent-primary);
    color: var(--nbe-dark-text-primary);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}

/* Collapsed panel state — pill always visible */
.panel-resize-handle.panel-collapsed .panel-collapse-pill {
    opacity: 1;
}

/* Drag overlay to prevent selection during resize */
.panel-resize-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 9999;
    cursor: col-resize;
}
```

**Step 2: Add panel collapse/expand transition CSS**

After the `.tree-panel` rule (line 369), add:

```css
/* Panel collapse transition */
.tree-panel,
.right-pane {
    transition: width 0.2s ease;
    overflow: hidden;
}

.tree-panel.is-collapsing,
.right-pane.is-collapsing {
    transition: width 0.2s ease;
}

.tree-panel.is-dragging,
.right-pane.is-dragging {
    transition: none;
}

.tree-panel.is-collapsed,
.right-pane.is-collapsed {
    width: 0 !important;
    border-width: 0;
}

.tree-panel.is-collapsed > :not(.panel-resize-handle),
.right-pane.is-collapsed > :not(.panel-resize-handle) {
    visibility: hidden;
}
```

**Step 3: Update .tree-item-type to use auto width for tier support**

In `static/css/explorer.css`, find the `.tree-item-type` rule (line 818). Change `width: 66px;` to `min-width: 44px;` so badges can grow with longer tier text:

```css
.tree-item-type {
    font-size: var(--nbe-font-size-xs);
    padding: var(--nbe-space-2xs) 0;
    border-radius: 0;
    margin-left: var(--nbe-space-sm);
    margin-right: var(--nbe-space-md);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    pointer-events: none;
    min-width: 44px;
    text-align: center;
    flex-shrink: 0;
    white-space: nowrap;
}
```

**Step 4: Update .right-pane to remove hardcoded width**

In `static/css/explorer.css`, change the `.right-pane` rule (line 1191). Replace `width: 440px;` with `width: var(--nbe-panel-width-right);` so the JS can override it:

```css
.right-pane {
    --nbe-panel-bg: var(--nbe-dark-surface-at-1);

    position: relative;
    width: var(--nbe-panel-width-right);
    display: flex;
    flex-direction: column;
    background: var(--nbe-panel-bg);
    border-left: 1px solid var(--nbe-dark-border-primary);
    overflow: hidden;
}
```

**Step 5: Verify styles render**

Refresh page. The resize handles should now be visible as thin strips between panels. The pill toggle should appear on hover.

**Step 6: Commit**

```bash
git add static/css/explorer.css static/css/tokens.css
git commit -m "feat(resize): add CSS for resize handles, pill toggles, and panel transitions"
```

---

### Task 6: Create PanelResizer Module

**Files:**
- Create: `static/js/explorer/panel-resizer.js`

**Step 1: Create the PanelResizer module**

Create `static/js/explorer/panel-resizer.js` with this content:

```javascript
/**
 * Nagios Bulk Editor - Panel Resizer Module
 *
 * Handles resizable and collapsible left/right panels with progressive
 * badge label tiers driven by panel width breakpoints.
 */
(function(Explorer) {
    'use strict';

    const STORAGE_KEY = 'nbe-panel-layout';
    const DEFAULT_LEFT_WIDTH = 320;
    const DEFAULT_RIGHT_WIDTH = 440;
    const MIN_WIDTH = 200;
    const TIER_COMPACT = 280;
    const TIER_MEDIUM = 400;

    let leftPanel, rightPanel, centerPane;
    let leftHandle, rightHandle;
    let leftPill, rightPill;
    let currentDrag = null; // { side: 'left'|'right', startX, startWidth }

    // Current layout state
    const layout = {
        leftWidth: DEFAULT_LEFT_WIDTH,
        rightWidth: DEFAULT_RIGHT_WIDTH,
        leftCollapsed: false,
        rightCollapsed: false
    };

    /**
     * Get max panel width (50% of viewport)
     */
    function getMaxWidth() {
        return Math.floor(window.innerWidth * 0.5);
    }

    /**
     * Determine tier from width
     */
    function getTier(width) {
        if (width < TIER_COMPACT) return 'compact';
        if (width < TIER_MEDIUM) return 'medium';
        return 'full';
    }

    /**
     * Save layout to localStorage
     */
    function saveLayout() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
        } catch (e) {
            // localStorage may be full or disabled
        }
    }

    /**
     * Load layout from localStorage
     */
    function loadLayout() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved);
                if (typeof parsed.leftWidth === 'number') layout.leftWidth = parsed.leftWidth;
                if (typeof parsed.rightWidth === 'number') layout.rightWidth = parsed.rightWidth;
                if (typeof parsed.leftCollapsed === 'boolean') layout.leftCollapsed = parsed.leftCollapsed;
                if (typeof parsed.rightCollapsed === 'boolean') layout.rightCollapsed = parsed.rightCollapsed;
            }
        } catch (e) {
            // Use defaults
        }
    }

    /**
     * Clamp width within bounds
     */
    function clampWidth(width) {
        return Math.max(MIN_WIDTH, Math.min(width, getMaxWidth()));
    }

    /**
     * Apply width to a panel and update tier
     */
    function applyWidth(side) {
        const panel = side === 'left' ? leftPanel : rightPanel;
        const width = side === 'left' ? layout.leftWidth : layout.rightWidth;
        const collapsed = side === 'left' ? layout.leftCollapsed : layout.rightCollapsed;

        if (collapsed) {
            panel.classList.add('is-collapsed');
            panel.style.width = '0px';
        } else {
            panel.classList.remove('is-collapsed');
            panel.style.width = width + 'px';
        }

        updateTier(side);
        updatePill(side);
    }

    /**
     * Update badge tier for a panel based on its width
     */
    function updateTier(side) {
        const panel = side === 'left' ? leftPanel : rightPanel;
        const width = side === 'left' ? layout.leftWidth : layout.rightWidth;
        const collapsed = side === 'left' ? layout.leftCollapsed : layout.rightCollapsed;
        const tier = collapsed ? 'compact' : getTier(width);

        // Update tier class on panel
        panel.classList.remove('panel-tier-compact', 'panel-tier-medium', 'panel-tier-full');
        panel.classList.add('panel-tier-' + tier);

        // Update badge text content for left panel
        if (side === 'left') {
            updateBadgesInPanel(panel, tier);
        }

        // Update right panel tab labels
        if (side === 'right') {
            updateTabLabels(tier);
            updateBadgesInPanel(panel, tier);
        }
    }

    /**
     * Update all badge text in a panel to match the given tier
     */
    function updateBadgesInPanel(panel, tier) {
        const attr = 'data-badge-' + tier;
        const badges = panel.querySelectorAll('.tree-item-type[' + attr + ']');
        for (let i = 0; i < badges.length; i++) {
            const newText = badges[i].getAttribute(attr);
            if (newText && badges[i].textContent !== newText) {
                badges[i].textContent = newText;
            }
        }
    }

    /**
     * Update right panel tab labels based on tier
     */
    function updateTabLabels(tier) {
        const c = Explorer.constants;
        if (!c || !c.tabLabelTiers) return;

        const tabs = rightPanel.querySelectorAll('[data-tab]');
        tabs.forEach(function(tab) {
            const tabName = tab.dataset.tab;
            const tiers = c.tabLabelTiers[tabName];
            if (!tiers) return;

            const label = tiers[tier] || tiers.full;
            // Find the text node (after the icon)
            const icon = tab.querySelector('i');
            const badge = tab.querySelector('.nbe-tab-badge');
            // Rebuild text content preserving icon and badge
            if (icon) {
                // Clear text nodes between icon and badge
                let node = icon.nextSibling;
                while (node && node !== badge) {
                    const next = node.nextSibling;
                    if (node.nodeType === Node.TEXT_NODE) {
                        node.remove();
                    }
                    node = next;
                }
                // Insert new text after icon
                const textNode = document.createTextNode(' ' + label + ' ');
                icon.after(textNode);
            }
        });
    }

    /**
     * Update pill toggle appearance
     */
    function updatePill(side) {
        const pill = side === 'left' ? leftPill : rightPill;
        const handle = side === 'left' ? leftHandle : rightHandle;
        const collapsed = side === 'left' ? layout.leftCollapsed : layout.rightCollapsed;
        const icon = pill.querySelector('i');

        if (collapsed) {
            handle.classList.add('panel-collapsed');
            pill.setAttribute('aria-label', 'Expand ' + side + ' panel');
            pill.setAttribute('title', 'Expand panel');
            if (side === 'left') {
                icon.className = 'fa-solid fa-chevron-right';
            } else {
                icon.className = 'fa-solid fa-chevron-left';
            }
        } else {
            handle.classList.remove('panel-collapsed');
            pill.setAttribute('aria-label', 'Collapse ' + side + ' panel');
            pill.setAttribute('title', 'Collapse panel');
            if (side === 'left') {
                icon.className = 'fa-solid fa-chevron-left';
            } else {
                icon.className = 'fa-solid fa-chevron-right';
            }
        }
    }

    /**
     * Toggle panel collapse
     */
    function toggleCollapse(side) {
        const panel = side === 'left' ? leftPanel : rightPanel;

        if (side === 'left') {
            layout.leftCollapsed = !layout.leftCollapsed;
        } else {
            layout.rightCollapsed = !layout.rightCollapsed;
        }

        // Add transition class
        panel.classList.add('is-collapsing');
        applyWidth(side);
        saveLayout();

        // Remove transition class after animation
        setTimeout(function() {
            panel.classList.remove('is-collapsing');
        }, 250);
    }

    /**
     * Start drag resize
     */
    function startDrag(e, side) {
        // Don't start drag if clicking the pill
        if (e.target.closest('.panel-collapse-pill')) return;

        e.preventDefault();
        const panel = side === 'left' ? leftPanel : rightPanel;
        const width = side === 'left' ? layout.leftWidth : layout.rightWidth;

        // If collapsed, expand first
        if ((side === 'left' && layout.leftCollapsed) ||
            (side === 'right' && layout.rightCollapsed)) {
            toggleCollapse(side);
            return;
        }

        currentDrag = { side: side, startX: e.clientX, startWidth: width };

        // Disable transitions during drag
        panel.classList.add('is-dragging');

        // Add overlay to prevent selection
        const overlay = document.createElement('div');
        overlay.className = 'panel-resize-overlay';
        overlay.id = 'panelResizeOverlay';
        document.body.appendChild(overlay);

        // Add dragging indicator to handle
        const handle = side === 'left' ? leftHandle : rightHandle;
        handle.classList.add('is-dragging');

        document.addEventListener('mousemove', onDrag);
        document.addEventListener('mouseup', endDrag);
    }

    /**
     * Handle drag movement
     */
    function onDrag(e) {
        if (!currentDrag) return;

        const { side, startX, startWidth } = currentDrag;
        const delta = e.clientX - startX;
        let newWidth;

        if (side === 'left') {
            newWidth = clampWidth(startWidth + delta);
            layout.leftWidth = newWidth;
            leftPanel.style.width = newWidth + 'px';
            updateTier('left');
        } else {
            // Right panel: dragging left increases width
            newWidth = clampWidth(startWidth - delta);
            layout.rightWidth = newWidth;
            rightPanel.style.width = newWidth + 'px';
            updateTier('right');
        }
    }

    /**
     * End drag resize
     */
    function endDrag() {
        if (!currentDrag) return;

        const side = currentDrag.side;
        const panel = side === 'left' ? leftPanel : rightPanel;
        const handle = side === 'left' ? leftHandle : rightHandle;

        panel.classList.remove('is-dragging');
        handle.classList.remove('is-dragging');

        // Remove overlay
        const overlay = document.getElementById('panelResizeOverlay');
        if (overlay) overlay.remove();

        document.removeEventListener('mousemove', onDrag);
        document.removeEventListener('mouseup', endDrag);

        saveLayout();
        currentDrag = null;
    }

    /**
     * Handle window resize — clamp panels if they exceed max
     */
    function onWindowResize() {
        const max = getMaxWidth();
        if (layout.leftWidth > max) {
            layout.leftWidth = max;
            applyWidth('left');
        }
        if (layout.rightWidth > max) {
            layout.rightWidth = max;
            applyWidth('right');
        }
    }

    /**
     * Handle double-click on resize handle — reset to default width
     */
    function onHandleDoubleClick(e, side) {
        if (e.target.closest('.panel-collapse-pill')) return;
        e.preventDefault();

        if (side === 'left') {
            layout.leftWidth = DEFAULT_LEFT_WIDTH;
        } else {
            layout.rightWidth = DEFAULT_RIGHT_WIDTH;
        }

        applyWidth(side);
        saveLayout();
    }

    /**
     * Re-apply tiers after tree re-render (called by app.js after renderTree)
     */
    Explorer.refreshPanelTiers = function() {
        if (leftPanel) {
            const leftTier = layout.leftCollapsed ? 'compact' : getTier(layout.leftWidth);
            updateBadgesInPanel(leftPanel, leftTier);
        }
        if (rightPanel) {
            const rightTier = layout.rightCollapsed ? 'compact' : getTier(layout.rightWidth);
            updateBadgesInPanel(rightPanel, rightTier);
        }
    };

    /**
     * Initialize the panel resizer
     */
    Explorer.initPanelResizer = function() {
        leftPanel = document.querySelector('.tree-panel');
        rightPanel = document.getElementById('rightPane');
        centerPane = document.getElementById('centerPane');
        leftHandle = document.getElementById('leftResizeHandle');
        rightHandle = document.getElementById('rightResizeHandle');
        leftPill = document.getElementById('leftCollapsePill');
        rightPill = document.getElementById('rightCollapsePill');

        if (!leftPanel || !rightPanel || !leftHandle || !rightHandle) {
            return; // Elements not found, bail out
        }

        // Load saved layout
        loadLayout();

        // Apply initial widths (no transition on first load)
        leftPanel.style.transition = 'none';
        rightPanel.style.transition = 'none';
        applyWidth('left');
        applyWidth('right');

        // Re-enable transitions after initial paint
        requestAnimationFrame(function() {
            requestAnimationFrame(function() {
                leftPanel.style.transition = '';
                rightPanel.style.transition = '';
            });
        });

        // Drag events
        leftHandle.addEventListener('mousedown', function(e) { startDrag(e, 'left'); });
        rightHandle.addEventListener('mousedown', function(e) { startDrag(e, 'right'); });

        // Double-click to reset
        leftHandle.addEventListener('dblclick', function(e) { onHandleDoubleClick(e, 'left'); });
        rightHandle.addEventListener('dblclick', function(e) { onHandleDoubleClick(e, 'right'); });

        // Pill click handlers
        leftPill.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleCollapse('left');
        });
        rightPill.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleCollapse('right');
        });

        // Window resize handler
        window.addEventListener('resize', onWindowResize);

        // Set up ResizeObserver for continuous tier updates
        if (typeof ResizeObserver !== 'undefined') {
            const observer = new ResizeObserver(function(entries) {
                for (const entry of entries) {
                    if (entry.target === leftPanel) {
                        updateTier('left');
                    } else if (entry.target === rightPanel) {
                        updateTier('right');
                    }
                }
            });
            observer.observe(leftPanel);
            observer.observe(rightPanel);
        }
    };

})(window.Explorer);
```

**Step 2: Verify file created correctly**

Check the file was saved: `ls -la static/js/explorer/panel-resizer.js`

**Step 3: Commit**

```bash
git add static/js/explorer/panel-resizer.js
git commit -m "feat(resize): create PanelResizer module with drag, collapse, and tier logic"
```

---

### Task 7: Initialize PanelResizer and Hook Up Badge Refresh

**Files:**
- Modify: `static/js/explorer/main.js:198-213` (Explorer.init)
- Modify: `static/js/explorer/app.js` (after renderTree calls)

**Step 1: Initialize PanelResizer in Explorer.init**

In `static/js/explorer/main.js`, find `Explorer.init` (line 198). Add a call to `Explorer.initPanelResizer()` after the event delegation init (after line 210):

```javascript
    // Initialize panel resizer (must happen after DOM ready, before data load)
    Explorer.initPanelResizer();
```

So the full init becomes:
```javascript
Explorer.init = function(configPath) {
    Explorer.state.configPath = configPath;

    if (typeof getSessionId === 'function') {
        Explorer.state.sessionId = getSessionId();
    } else {
        Explorer.state.sessionId = 'session-' + Math.random().toString(36).substr(2, 9) +
                                   '-' + Date.now().toString(36);
    }

    // Initialize event delegation
    Explorer.initEventDelegation();

    // Initialize panel resizer (must happen after DOM ready, before data load)
    Explorer.initPanelResizer();

    DebugLogger.info('Explorer initialized', { sessionId: Explorer.state.sessionId });
};
```

**Step 2: Add refreshPanelTiers call after tree renders**

In `static/js/explorer/app.js`, find the `renderTree` function. Look for the end of the function where the tree HTML is inserted into the DOM. After the tree content is populated, add:

```javascript
    // Update badge tiers after tree re-render
    if (Explorer.refreshPanelTiers) {
        Explorer.refreshPanelTiers();
    }
```

Search for where `treeContent.innerHTML` or similar is set in `renderTree` and add the call after it.

**Step 3: Test the full integration**

1. Refresh `http://localhost:8080`
2. Hover over the edge between left panel and center — cursor should be `col-resize`, pill should appear
3. Drag the edge — left panel should resize smoothly
4. Drag past 280px — badges should change from compact to medium tier
5. Drag past 400px — badges should change to full tier
6. Click the pill — panel should collapse with animation
7. Click the pill again — panel should expand to previous width
8. Same tests for right panel
9. Refresh page — panel widths and collapsed state should persist

**Step 4: Commit**

```bash
git add static/js/explorer/main.js static/js/explorer/app.js
git commit -m "feat(resize): initialize PanelResizer and refresh badge tiers on tree render"
```

---

### Task 8: Polish and Edge Cases

**Files:**
- Modify: `static/css/explorer.css` (if needed)
- Modify: `static/js/explorer/panel-resizer.js` (if needed)

**Step 1: Test edge cases**

1. **Both panels collapsed:** Collapse both left and right. Center should fill full width. Both pills should be visible and clickable.
2. **Window resize while panels open:** Resize browser window. If panel exceeds 50vw, it should clamp.
3. **Double-click handle:** Should reset panel to default width (320px left, 440px right).
4. **Right panel tab labels:** At narrow widths, tabs should show "Files", "Sugg", "Valid". At wider widths, full names.
5. **Rapid drag:** Drag quickly back and forth. Should be smooth, no glitches.
6. **Tree re-render:** Select an object, make an edit, verify badges stay at correct tier after tree refresh.

**Step 2: Fix any issues found during testing**

Address CSS or JS issues discovered. Common things to watch for:
- Badge width overflow at full tier (long names like "SERVICEESCALATION")
- Pill toggle z-index conflicts with context menus
- Tree content scrollbar position after collapse/expand

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(resize): polish resize behavior and fix edge cases"
```

---

## Summary of File Changes

| # | File | Action | Task |
|---|------|--------|------|
| 1 | `static/css/tokens.css` | Modify: add panel resize CSS vars | 1 |
| 2 | `static/js/explorer/constants.js` | Modify: add badge tier data + helper | 2 |
| 3 | `static/js/explorer/app.js` | Modify: add data-badge-* attrs + tier refresh | 3, 7 |
| 4 | `templates/explorer.html` | Modify: add resize handles, pill toggles, script tag | 4 |
| 5 | `static/css/explorer.css` | Modify: resize handle, pill, transition, tier styles | 5 |
| 6 | `static/js/explorer/panel-resizer.js` | Create: PanelResizer module | 6 |
| 7 | `static/js/explorer/main.js` | Modify: init PanelResizer in Explorer.init | 7 |
