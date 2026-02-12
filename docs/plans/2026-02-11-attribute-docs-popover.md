# Attribute Docs Popover — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show inline documentation popovers when hovering attribute names in the object editor, with a link that opens the docs page scrolled to the exact directive.

**Architecture:** A singleton popover element rendered once in the DOM, repositioned on hover. Lookup uses the existing `NAGIOS_OBJECT_REFERENCE` data from `docs-data.js`. The docs page gains deep-link support (`#type/directive`) with scroll-to-and-highlight.

**Tech Stack:** Vanilla JS (IIFE pattern matching existing codebase), CSS animations

---

### Task 1: Load docs-data.js on the explorer page

**Files:**
- Modify: `templates/explorer.html:289-312` (scripts block)

**Step 1: Add the script tag**

In `templates/explorer.html`, add `docs-data.js` before the explorer modules in the `{% block scripts %}` block. It must load before `object-editor.js` since that's where the popover logic will live.

Add this line immediately after `{% block scripts %}`:

```html
<!-- Docs reference data for attribute popovers -->
<script src="{{ url_for('static', filename='js/docs-data.js') }}"></script>
```

The full block opening becomes:

```html
{% block scripts %}
<!-- Docs reference data for attribute popovers -->
<script src="{{ url_for('static', filename='js/docs-data.js') }}"></script>
<!-- Explorer Modules (load order matters: namespace first, then utilities, then core, then features) -->
<script src="{{ url_for('static', filename='js/explorer/main.js') }}"></script>
```

**Step 2: Verify it loads**

Run the app (`python3 app.py`), open the explorer page, open browser console, type `window.NAGIOS_OBJECT_REFERENCE` and confirm it's populated.

**Step 3: Commit**

```bash
git add templates/explorer.html
git commit -m "feat: load docs-data.js on explorer page for attribute popovers"
```

---

### Task 2: Add popover HTML and CSS

**Files:**
- Modify: `static/css/explorer.css` (append after line 3904, end of file)

**Step 1: Add popover CSS**

Append the following to the end of `static/css/explorer.css`:

```css
/* =========================================================================
   Attribute Docs Popover
   ========================================================================= */

.attr-docs-popover {
    position: fixed;
    z-index: calc(var(--nbe-z-dropdown) + 10);
    width: 320px;
    max-height: 280px;
    overflow-y: auto;
    background: var(--nbe-dark-bg-elevated);
    border: 1px solid var(--nbe-dark-border-primary);
    border-radius: var(--nbe-radius-md);
    box-shadow: var(--nbe-shadow-md);
    padding: 12px;
    pointer-events: auto;
    opacity: 0;
    transform: translateY(4px);
    transition: opacity 0.15s ease, transform 0.15s ease;
}

.attr-docs-popover.visible {
    opacity: 1;
    transform: translateY(0);
}

.attr-docs-popover.above {
    transform: translateY(-4px);
}

.attr-docs-popover.above.visible {
    transform: translateY(0);
}

.attr-docs-popover .attr-docs-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
}

.attr-docs-popover .attr-docs-name {
    font-family: var(--nbe-font-mono);
    font-size: var(--nbe-typography-body-size);
    color: var(--nbe-dark-accent-primary);
    font-weight: 600;
}

.attr-docs-popover .attr-docs-badge {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 3px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.attr-docs-popover .attr-docs-badge--required {
    background: rgba(239, 68, 68, 0.15);
    color: var(--nbe-dark-accent-danger);
}

.attr-docs-popover .attr-docs-badge--optional {
    background: rgba(255, 255, 255, 0.08);
    color: var(--nbe-dark-text-secondary);
}

.attr-docs-popover .attr-docs-format {
    font-size: 12px;
    color: var(--nbe-dark-text-secondary);
    margin-bottom: 8px;
}

.attr-docs-popover .attr-docs-format code {
    font-family: var(--nbe-font-mono);
    color: var(--nbe-dark-text-primary);
}

.attr-docs-popover .attr-docs-desc {
    font-size: 13px;
    line-height: 1.5;
    color: var(--nbe-dark-text-primary);
    margin-bottom: 8px;
}

.attr-docs-popover .attr-docs-link {
    display: inline-block;
    font-size: 12px;
    color: var(--nbe-dark-accent-primary);
    text-decoration: none;
    opacity: 0.8;
    transition: opacity 0.15s;
}

.attr-docs-popover .attr-docs-link:hover {
    opacity: 1;
    text-decoration: underline;
}

/* Make attr-name show pointer cursor when docs are available */
.attr-name.has-docs {
    cursor: help;
}

.attr-name.has-docs:hover {
    text-decoration: underline;
    text-decoration-style: dotted;
    text-underline-offset: 3px;
}
```

**Step 2: Commit**

```bash
git add static/css/explorer.css
git commit -m "feat: add CSS for attribute docs popover"
```

---

### Task 3: Implement popover logic in object-editor.js

**Files:**
- Modify: `static/js/explorer/object-editor.js`

This is the main implementation task. All popover logic lives in `object-editor.js` inside its existing IIFE.

**Step 1: Add the directive lookup function**

Add this after the `highlightCommandSyntax` function (after line ~446), before `renderCenterAttributes`:

```javascript
// =========================================================================
// Attribute Docs Popover
// =========================================================================

var docsPopoverEl = null;
var docsPopoverShowTimer = null;
var docsPopoverHideTimer = null;
var docsPopoverCurrentAttr = null;

/**
 * Look up a directive in NAGIOS_OBJECT_REFERENCE for the given object type.
 * Handles aliases like "obsess_over_host|obsess" by splitting on "|".
 * Also checks _template_directives for common template attrs (name, use, register).
 */
function lookupDirective(objectType, attrName) {
    var ref = window.NAGIOS_OBJECT_REFERENCE;
    if (!ref) return null;

    var lower = attrName.toLowerCase();

    // Check type-specific directives first
    var typeData = ref[objectType];
    if (typeData && typeData.directives) {
        for (var i = 0; i < typeData.directives.length; i++) {
            var d = typeData.directives[i];
            var names = d.name.split('|');
            for (var j = 0; j < names.length; j++) {
                if (names[j].trim().toLowerCase() === lower) return d;
            }
        }
    }

    // Check template directives (name, use, register)
    var tmpl = ref._template_directives;
    if (tmpl && tmpl.directives) {
        for (var i = 0; i < tmpl.directives.length; i++) {
            var d = tmpl.directives[i];
            var names = d.name.split('|');
            for (var j = 0; j < names.length; j++) {
                if (names[j].trim().toLowerCase() === lower) return d;
            }
        }
    }

    return null;
}
```

**Step 2: Add the popover creation and positioning functions**

Add immediately after the lookup function:

```javascript
/**
 * Create the singleton popover element (once).
 */
function ensurePopoverElement() {
    if (docsPopoverEl) return docsPopoverEl;
    docsPopoverEl = document.createElement('div');
    docsPopoverEl.className = 'attr-docs-popover';
    docsPopoverEl.id = 'attrDocsPopover';
    document.body.appendChild(docsPopoverEl);

    // Keep popover open when mouse is over it
    docsPopoverEl.addEventListener('mouseenter', function() {
        clearTimeout(docsPopoverHideTimer);
    });
    docsPopoverEl.addEventListener('mouseleave', function() {
        scheduleHidePopover();
    });

    // Dismiss on Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && docsPopoverEl.classList.contains('visible')) {
            hideDocsPopover();
        }
    });

    return docsPopoverEl;
}

/**
 * Position the popover relative to the target element.
 * Default below, flip above if not enough room.
 */
function positionPopover(targetEl) {
    var el = ensurePopoverElement();
    var rect = targetEl.getBoundingClientRect();
    var gap = 8;

    // Temporarily show off-screen to measure
    el.style.left = '-9999px';
    el.style.top = '-9999px';
    el.classList.add('visible');
    var popoverHeight = el.offsetHeight;
    el.classList.remove('visible');

    var spaceBelow = window.innerHeight - rect.bottom - gap;
    var placeAbove = spaceBelow < popoverHeight && rect.top > popoverHeight + gap;

    el.classList.toggle('above', placeAbove);

    if (placeAbove) {
        el.style.top = (rect.top - popoverHeight - gap) + 'px';
    } else {
        el.style.top = (rect.bottom + gap) + 'px';
    }

    // Align left edge with attr-name, clamp to viewport
    var left = rect.left;
    var maxLeft = window.innerWidth - 340; // 320px width + 20px margin
    if (left > maxLeft) left = maxLeft;
    if (left < 8) left = 8;
    el.style.left = left + 'px';
}

/**
 * Show the docs popover for a directive.
 */
function showDocsPopover(targetEl, directive, objectType) {
    var el = ensurePopoverElement();

    var badgeClass = directive.required ? 'attr-docs-badge--required' : 'attr-docs-badge--optional';
    var badgeText = directive.required ? 'Required' : 'Optional';

    // Build the deep link: /docs#objectType/directiveName
    // Use the first alias for the link (before any "|")
    var directiveName = directive.name.split('|')[0].trim();
    var docsHref = '/docs#' + encodeURIComponent(objectType) + '/' + encodeURIComponent(directiveName);

    el.innerHTML =
        '<div class="attr-docs-header">' +
            '<code class="attr-docs-name">' + Explorer.escapeHtml(directive.name) + '</code>' +
            '<span class="attr-docs-badge ' + badgeClass + '">' + badgeText + '</span>' +
        '</div>' +
        '<div class="attr-docs-format">Format: <code>' + Explorer.escapeHtml(directive.format) + '</code></div>' +
        '<div class="attr-docs-desc">' + Explorer.escapeHtml(directive.description) + '</div>' +
        '<a class="attr-docs-link" href="' + docsHref + '" target="_blank">View in docs \u2192</a>';

    positionPopover(targetEl);

    // Trigger transition
    requestAnimationFrame(function() {
        el.classList.add('visible');
    });
}

/**
 * Hide the popover immediately.
 */
function hideDocsPopover() {
    clearTimeout(docsPopoverShowTimer);
    clearTimeout(docsPopoverHideTimer);
    docsPopoverCurrentAttr = null;
    if (docsPopoverEl) {
        docsPopoverEl.classList.remove('visible');
    }
}

/**
 * Schedule hiding the popover after a grace period.
 */
function scheduleHidePopover() {
    clearTimeout(docsPopoverHideTimer);
    docsPopoverHideTimer = setTimeout(hideDocsPopover, 200);
}
```

**Step 3: Add hover listeners to attribute name spans**

Modify the `renderCenterAttributes` function. After the line `container.innerHTML = Object.entries(...)...join('');` block (around line 511), add event listeners. Insert this code right before the `requestAnimationFrame` call that auto-sizes textareas (line ~515):

```javascript
// Attach docs popover hover listeners to attr-name spans
container.querySelectorAll('.attr-name').forEach(function(nameEl) {
    var attrName = nameEl.textContent;
    var directive = lookupDirective(objectType, attrName);
    if (directive) {
        nameEl.classList.add('has-docs');

        nameEl.addEventListener('mouseenter', function() {
            clearTimeout(docsPopoverHideTimer);
            clearTimeout(docsPopoverShowTimer);
            docsPopoverShowTimer = setTimeout(function() {
                docsPopoverCurrentAttr = attrName;
                showDocsPopover(nameEl, directive, objectType);
            }, 300);
        });

        nameEl.addEventListener('mouseleave', function() {
            clearTimeout(docsPopoverShowTimer);
            scheduleHidePopover();
        });
    }
});
```

**Step 4: Dismiss popover on scroll**

Add this after the `renderCenterAttributes` function definition (before `filterCommaValueSuggestions`):

```javascript
// Dismiss docs popover when attributes scroll
(function() {
    var centerBody = document.querySelector('.center-body');
    if (centerBody) {
        centerBody.addEventListener('scroll', hideDocsPopover);
    } else {
        // Defer until DOM ready
        document.addEventListener('DOMContentLoaded', function() {
            var cb = document.querySelector('.center-body');
            if (cb) cb.addEventListener('scroll', hideDocsPopover);
        });
    }
})();
```

**Step 5: Verify manually**

Run the app, open the explorer, select a host object. Hover over `host_name` — the popover should appear after 300ms with the description, format, required badge, and "View in docs" link. Moving to the popover should keep it open. Moving away should dismiss after 200ms.

**Step 6: Commit**

```bash
git add static/js/explorer/object-editor.js
git commit -m "feat: add attribute docs popover on hover in object editor"
```

---

### Task 4: Add deep-link support to docs page

**Files:**
- Modify: `static/js/docs.js:254-266` (renderDirectiveRow — add row IDs)
- Modify: `static/js/docs.js:349-362` (hash handling — parse directive segment)
- Modify: `static/css/docs.css` (append highlight animation)

**Step 1: Add IDs to directive rows**

In `docs.js`, modify `renderDirectiveRow` (line 254) to add an `id` attribute to each `<tr>`. The directive name may contain `|` for aliases — use the first name as the ID.

Replace the current `renderDirectiveRow` function:

```javascript
function renderDirectiveRow(directive) {
    var reqBadge = directive.required
        ? '<span class="docs-badge docs-badge--required">Required</span>'
        : '<span class="docs-badge docs-badge--optional">Optional</span>';

    // Use first name (before "|") as the row ID for deep linking
    var primaryName = directive.name.split('|')[0].trim();

    var html = '<tr class="docs-directive-row" id="directive-' + escapeHtml(primaryName) + '">';
    html += '<td class="docs-cell-name"><code>' + escapeHtml(directive.name) + '</code></td>';
    html += '<td class="docs-cell-req">' + reqBadge + '</td>';
    html += '<td class="docs-cell-format"><code>' + escapeHtml(directive.format) + '</code></td>';
    html += '<td class="docs-cell-desc">' + escapeHtml(directive.description) + '</td>';
    html += '</tr>';
    return html;
}
```

The only change is: extracting `primaryName` and adding `id="directive-' + escapeHtml(primaryName) + '"` to the `<tr>`.

**Step 2: Update hash parsing to support `#type/directive`**

Replace the `loadFromHash` function (line 355):

```javascript
function loadFromHash() {
    var hash = window.location.hash.replace('#', '');
    var parts = hash.split('/');
    var typePart = decodeURIComponent(parts[0] || '');
    var directivePart = parts[1] ? decodeURIComponent(parts[1]) : null;

    if (typePart === SPECIAL_INHERITANCE) {
        selectType(SPECIAL_INHERITANCE);
    } else if (typePart && REF[typePart] && typePart !== '_template_directives') {
        selectType(typePart);

        // Scroll to specific directive if provided
        if (directivePart) {
            scrollToDirective(directivePart);
        }
    }
}
```

**Step 3: Add the scroll-to-directive function**

Add this right before `loadFromHash` (before line ~355):

```javascript
function scrollToDirective(directiveName) {
    // Slight delay to ensure content is rendered
    setTimeout(function() {
        var row = document.getElementById('directive-' + directiveName);
        if (row) {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('docs-directive-highlight');
            setTimeout(function() {
                row.classList.remove('docs-directive-highlight');
            }, 2000);
        }
    }, 100);
}
```

**Step 4: Update the `updateHash` function to preserve directive part**

No change needed — `updateHash` only writes `#type` when selecting types via the tree. Deep links with `/directive` are only used for incoming navigation from the popover, so this is fine.

**Step 5: Add the highlight animation CSS**

Append to the end of `static/css/docs.css`:

```css
/* Deep-link highlight animation for directive rows */
.docs-directive-row.docs-directive-highlight {
    animation: docsDirectiveHighlight 2s ease-out forwards;
}

@keyframes docsDirectiveHighlight {
    0% {
        background-color: rgba(99, 179, 237, 0.25);
        box-shadow: inset 3px 0 0 var(--nbe-dark-accent-primary);
    }
    70% {
        background-color: rgba(99, 179, 237, 0.1);
        box-shadow: inset 3px 0 0 var(--nbe-dark-accent-primary);
    }
    100% {
        background-color: transparent;
        box-shadow: none;
    }
}
```

**Step 6: Verify manually**

Navigate to `/docs#host/check_command`. The page should load the host type, scroll to the `check_command` row, and briefly highlight it with a blue flash that fades out.

Then go back to the explorer, hover an attribute, click "View in docs →", and confirm it opens the docs page scrolled to the correct directive.

**Step 7: Commit**

```bash
git add static/js/docs.js static/css/docs.css
git commit -m "feat: add deep-link support for directives on docs page (#type/directive)"
```

---

### Task 5: Handle edge cases and polish

**Files:**
- Modify: `static/js/explorer/object-editor.js`

**Step 1: Dismiss popover when switching objects**

In the `showCenterPaneObject` function (find it by searching for `function showCenterPaneObject`), add `hideDocsPopover()` at the very beginning of the function body, before any other logic.

**Step 2: Handle window resize**

Add this near the scroll dismiss listener (after the scroll listener IIFE from Task 3):

```javascript
window.addEventListener('resize', hideDocsPopover);
```

**Step 3: Verify edge cases manually**

Test these scenarios:
1. Hover an attribute that doesn't exist in docs (e.g. a custom/unrecognized attribute) — no popover should appear, no `cursor: help` style
2. Hover `name`, `use`, `register` — should show template directive docs
3. Hover attributes with aliases like `obsess_over_host` — should match
4. Switch objects while popover is open — popover should dismiss
5. Scroll the attribute list while popover is open — popover should dismiss
6. Popover near bottom of screen — should flip above the attribute name

**Step 4: Commit**

```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: dismiss docs popover on object switch and window resize"
```
