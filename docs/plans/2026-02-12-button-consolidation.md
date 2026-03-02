# Button Style Consolidation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace all custom button classes with the `.nbe-btn` design system so every button in the app uses a single, consistent styling system.

**Architecture:** The `.nbe-btn` system in `tokens.css` already has the right variants (primary/secondary/danger/info/ghost) and sizes (xs/sm/md/lg). Most pages already use it. This plan migrates the ~15 remaining custom button classes in `explorer.css`, `base.html`, and JS files, then deletes the dead CSS. One design system gap to fill: `.nbe-btn--dark.nbe-btn--info`.

**Tech Stack:** CSS (tokens.css, explorer.css, base.html inline), HTML templates, JavaScript (commit-dialog.js, analysis.js, analysis-issues.js, git.js)

**Scope exclusions (stay as-is):**
- `.commit-btn` / `.undo-btn` — navbar buttons with unique behavior (orange gradient, disabled↔active toggle)
- `.nav-btn` / `.lock-break-btn` — navbar context, white-on-dark header
- `.card-issue-btn` — severity indicator badge, not an action button
- `.add-attr-btn` — dashed-border "+" UX pattern, visually distinct from action buttons
- `.quick-view-btn` (dependencies) — toggle/tab pattern
- `.identity-required-btn` — one-time `<a>` tag modal
- Tab toggles and filter chips

---

### Task 1: Add `.nbe-btn--dark.nbe-btn--info` variant

**Files:**
- Modify: `static/css/tokens.css:983-997`

**Step 1: Add the dark info variant**

After `.nbe-btn--dark.nbe-btn--danger` (line 988), add:

```css
.nbe-btn--dark.nbe-btn--info {
    background: var(--nbe-primary);
    color: var(--nbe-text-inverse);
    border: none;
}
```

This uses the existing `--nbe-primary` blue (#1976D2), matching the current `.btn-refresh` blue.

**Step 2: Verify**

Open the app, check that the validate page "Run Validation" button still works (it already uses `--primary` not `--info`, but confirm no regressions).

**Step 3: Commit**

```bash
git add static/css/tokens.css
git commit -m "feat: add dark info button variant to design system"
```

---

### Task 2: Migrate commit dialog buttons

These are the "Discard All / Cancel / Apply Changes" buttons inside the commit overlay, plus the "Retry Commit / Discard Staging" error buttons.

**Files:**
- Modify: `static/js/commit-dialog.js:179-181, 292-294, 436-439`
- Modify: `templates/base.html` (inline CSS lines 700-748, 1053-1079)

**Step 1: Update commit-dialog.js button classes**

In `commit-dialog.js`, replace the three button lines at ~179-181 (and the identical set at ~292-294):

```js
// OLD:
<button class="btn-discard-all" ...>Discard All</button>
<button class="btn-cancel" ...>Cancel</button>
<button class="btn-apply-commit" ...>Apply Changes</button>

// NEW:
<button class="nbe-btn nbe-btn--dark nbe-btn--danger" ...>Discard All</button>
<button class="nbe-btn nbe-btn--dark" ...>Cancel</button>
<button class="nbe-btn nbe-btn--dark nbe-btn--primary" ...>Apply Changes</button>
```

At ~436-439, replace the retry/discard buttons:

```js
// OLD:
<button class="btn-retry-commit" ...>
<button class="btn-discard-staging" ...>

// NEW:
<button class="nbe-btn nbe-btn--dark nbe-btn--info" ...>
<button class="nbe-btn nbe-btn--dark" ...>
```

Note: The `btn-disabled` class on Apply Changes (line 181, 294) when git is not configured needs to just use the `disabled` attribute which `.nbe-btn` already handles. The current template already adds `disabled` — just remove the fallback `class="btn-disabled"` from the ternary.

**Step 2: Delete dead CSS from base.html**

Remove these CSS blocks from the inline `<style>` in `base.html`:
- `.btn-discard-all` + `:hover` (around lines 700-720)
- `.btn-cancel` + `:hover` (lines 721-732)
- `.btn-apply-commit` + `:hover` + `:focus-visible` + `.btn-disabled` (lines 733-755)
- `.btn-retry-commit` + `:hover` (lines 1053-1067)
- `.btn-discard-staging` + `:hover` (lines 1068-1079)

Also delete from `explorer.css`:
- `.btn-discard-all` + `:hover` + `:focus-visible` (lines 339-356)
- `.btn-apply-commit` + `:hover` + `:focus-visible` (lines 358-376)

**Step 3: Verify**

Open the app, make a staging change, click Commit. Verify:
- "Discard All" = red
- "Cancel" = dark/neutral
- "Apply Changes" = teal
- Disabled state works when git identity not configured

**Step 4: Commit**

```bash
git add static/js/commit-dialog.js templates/base.html static/css/explorer.css
git commit -m "refactor: migrate commit dialog buttons to design system"
```

---

### Task 3: Migrate explorer action bar buttons

**Files:**
- Modify: `templates/explorer.html:44, 195`
- Modify: `static/css/explorer.css` (lines 458-476 `.actions-btn`, lines 1328-1346 `.btn-refresh`)

**Step 1: Update explorer.html**

Line 44 — Select button:
```html
<!-- OLD: -->
<button class="actions-btn" ...>
<!-- NEW: -->
<button class="nbe-btn nbe-btn--dark nbe-btn--sm actions-btn" ...>
```

Keep `.actions-btn` as a hook for the dropdown caret positioning / menu anchor, but strip its visual styling from CSS (leave only non-visual properties like positioning if needed).

Line 195 — Run Validation button:
```html
<!-- OLD: -->
<button class="btn-refresh" ...>Run Validation</button>
<!-- NEW: -->
<button class="nbe-btn nbe-btn--dark nbe-btn--info" ...>Run Validation</button>
```

**Step 2: Clean up explorer.css**

- `.actions-btn` (lines 458-476): Remove all visual properties (background, color, border, padding, border-radius, font-size, cursor). Keep any positioning/layout rules if they exist.
- `.btn-refresh` + `:hover` + `:focus-visible` (lines 1328-1346): Delete entirely.

**Step 3: Verify**

Open explorer. Check Select dropdown button and Run Validation button look correct.

**Step 4: Commit**

```bash
git add templates/explorer.html static/css/explorer.css
git commit -m "refactor: migrate explorer action bar buttons to design system"
```

---

### Task 4: Migrate explorer center pane buttons

**Files:**
- Modify: `templates/explorer.html:81, 88, 142-154`
- Modify: `static/css/explorer.css` (lines 1165-1184, 1237-1258, 1557-1593)

**Step 1: Update explorer.html**

Line 81 — Graph view button:
```html
<!-- OLD: -->
<button class="center-graph-btn" ...>
<!-- NEW: -->
<button class="nbe-btn nbe-btn--dark nbe-btn--ghost nbe-btn--sm center-graph-btn" ...>
```

Keep `.center-graph-btn` for any positioning rules; strip visual CSS.

Line 88 — Discard new object button:
```html
<!-- OLD: -->
<button class="center-close-btn u-hidden" ...>&times;</button>
<!-- NEW: -->
<button class="nbe-btn nbe-btn--dark nbe-btn--danger nbe-btn--icon nbe-btn--sm center-close-btn u-hidden" ...>&times;</button>
```

Lines 142-154 — Workspace toolbar buttons:
```html
<!-- OLD: -->
<button class="workspace-toolbar-btn workspace-toolbar-btn--icon" ...>
<!-- NEW: -->
<button class="nbe-btn nbe-btn--dark nbe-btn--icon nbe-btn--sm workspace-toolbar-btn" ...>
```

**Step 2: Clean up explorer.css**

- `.center-graph-btn` (lines 1237-1258): Remove visual properties (background, color, border, border-radius, padding, font-size, cursor, transition). Keep positioning (position, top, right, z-index) and SVG sizing rules.
- `.center-close-btn` (lines 1165-1184): Same — remove visual, keep positioning.
- `.workspace-toolbar-btn` (lines 1557-1593): Remove visual properties. Keep any layout rules.
- `.workspace-toolbar-btn--icon` (lines 1582-1593): Remove visual properties.

**Step 3: Verify**

Open explorer, select an object. Check the graph button, close button, and new file/folder toolbar buttons look right.

**Step 4: Commit**

```bash
git add templates/explorer.html static/css/explorer.css
git commit -m "refactor: migrate explorer center pane buttons to design system"
```

---

### Task 5: Migrate cleanup/analysis buttons

**Files:**
- Modify: `static/js/explorer/analysis.js:861, 898-907`
- Modify: `static/js/explorer/analysis-issues.js:191`
- Modify: `static/css/explorer.css` (lines 2761-2814 `.cleanup-section-btn`, lines 2962-2989 `.cleanup-action-btn`)

**Step 1: Update analysis.js button classes**

Line 861 — bulk delete button (already has `nbe-btn` but missing `--dark`):
```js
// OLD:
class="cleanup-section-btn nbe-btn nbe-btn--danger nbe-btn--sm"
// NEW:
class="nbe-btn nbe-btn--dark nbe-btn--danger nbe-btn--sm"
```

Lines 898-907 — individual action buttons:
```js
// OLD (Resolve/Create):
class="cleanup-action-btn cleanup-fix-btn"
// NEW:
class="nbe-btn nbe-btn--dark nbe-btn--xs cleanup-fix-btn"

// OLD (Delete):
class="cleanup-action-btn"
// NEW:
class="nbe-btn nbe-btn--dark nbe-btn--danger nbe-btn--xs"
```

Note: Keep `.cleanup-fix-btn` as a hook if needed for non-visual JS selection, but it may not be needed. Check if any JS selects by this class.

**Step 2: Update analysis-issues.js**

Line 191:
```js
// OLD:
class="cleanup-action-btn cleanup-fix-btn"
// NEW:
class="nbe-btn nbe-btn--dark nbe-btn--xs"
```

**Step 3: Clean up explorer.css**

- `.cleanup-section-btn` + all variants (lines 2761-2814): Delete entirely.
- `.cleanup-action-btn` + `.cleanup-fix-btn` (lines 2962-2989): Delete entirely.

**Step 4: Verify**

Open explorer, go to Suggestions/Analysis tab. Check that Resolve, Create, Delete, and Delete All buttons look correct.

**Step 5: Commit**

```bash
git add static/js/explorer/analysis.js static/js/explorer/analysis-issues.js static/css/explorer.css
git commit -m "refactor: migrate cleanup/analysis buttons to design system"
```

---

### Task 6: Migrate quick-apply and discard buttons in explorer

**Files:**
- Modify: `static/css/explorer.css` (lines 3125-3163 `.btn-apply`, `.btn-discard`)

These buttons are defined in CSS but need to verify they're actually used. Search for usage first.

**Step 1: Check usage**

Grep for `btn-apply` and `btn-discard` (exact class, not `.btn-apply-commit`) in JS and HTML files.

If unused → delete the CSS. If used → migrate to `.nbe-btn nbe-btn--dark nbe-btn--sm` / `nbe-btn--ghost` and update the template/JS.

**Step 2: Clean up or migrate**

Delete or migrate based on step 1 findings.

**Step 3: Commit**

```bash
git add static/css/explorer.css
git commit -m "refactor: clean up quick-apply/discard button styles"
```

---

### Task 7: Migrate confirm dialog buttons to use --dark classes

**Files:**
- Modify: `templates/base.html:116-117` (confirm dialog HTML)
- Modify: `templates/base.html` (inline CSS lines 926-950)

**Step 1: Add --dark to confirm dialog button classes**

Lines 116-117:
```html
<!-- OLD: -->
<button class="nbe-btn nbe-btn--secondary nbe-btn--sm" id="confirmDialogCancel">Cancel</button>
<button class="nbe-btn nbe-btn--primary nbe-btn--sm" id="confirmDialogConfirm">Confirm</button>
<!-- NEW: -->
<button class="nbe-btn nbe-btn--dark nbe-btn--sm" id="confirmDialogCancel">Cancel</button>
<button class="nbe-btn nbe-btn--dark nbe-btn--primary nbe-btn--sm" id="confirmDialogConfirm">Confirm</button>
```

Also check if `showConfirmDialog()` in base.js dynamically sets `.nbe-btn--danger` on the confirm button — if so, ensure it also adds `--dark`.

**Step 2: Delete dark override CSS**

Remove from base.html inline styles (lines 926-950):
- `.confirm-dialog-buttons .nbe-btn--secondary` + `:hover`
- `.confirm-dialog-buttons .nbe-btn--primary` + `:hover`
- `.confirm-dialog-buttons .nbe-btn--danger` + `:hover`

These overrides become unnecessary once the buttons use `--dark` classes directly.

**Step 3: Verify**

Trigger a confirm dialog (e.g., delete action). Check Cancel and Confirm/Delete buttons look correct.

**Step 4: Commit**

```bash
git add templates/base.html
git commit -m "refactor: migrate confirm dialog buttons to dark design system"
```

---

### Task 8: Migrate git.js restore button

**Files:**
- Modify: `static/js/git.js:479`

**Step 1: Add --dark to restore button**

```js
// OLD:
class="nbe-btn nbe-btn--secondary nbe-btn--sm"
// NEW:
class="nbe-btn nbe-btn--dark nbe-btn--sm"
```

**Step 2: Verify**

Open git page, check History tab — Restore buttons should look correct.

**Step 3: Commit**

```bash
git add static/js/git.js
git commit -m "refactor: migrate git restore button to dark design system"
```

---

### Task 9: Delete dead `.page-btn` system

**Files:**
- Modify: `templates/base.html` (inline CSS)

**Step 1: Confirm `.page-btn` is unused**

Grep for `page-btn` in all JS and HTML files (excluding CSS definitions in base.html). Should find zero matches.

**Step 2: Delete dead CSS**

Remove from base.html inline styles:
- `.page-sidebar .page-btn` block (lines ~1330-1370)
- `.page-btn` base + `:hover` + `:disabled` + `:focus-visible` (lines ~1507-1533)
- `.page-btn-sm` (line ~1536)
- `.page-btn-block` (line ~1542)
- `.page-btn-primary` + `:hover` (lines ~1547-1555)
- `.page-btn-danger` + `:hover` (lines ~1558-1565)
- `.page-btn.loading` + `::after` + `::before` (lines ~1655-1693)
- `.page-btn-primary.loading::after` (line ~1685)
- `.page-btn-danger.loading::after` (line ~1690)
- `.page-btn-icon` + all variants (lines ~1932-1964)

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "chore: delete unused page-btn CSS system"
```

---

### Task 10: Final audit and visual QA

**Step 1: Grep for any remaining non-design-system button classes**

```bash
grep -rn 'class=.*btn' templates/ static/js/ --include='*.html' --include='*.js' | grep -v 'nbe-btn' | grep -v 'commit-btn' | grep -v 'undo-btn' | grep -v 'nav-btn' | grep -v 'lock-break-btn' | grep -v 'card-issue-btn' | grep -v 'add-attr-btn' | grep -v 'quick-view-btn' | grep -v 'identity-required' | grep -v 'btn-close' | grep -v 'tree-expand-btn' | grep -v 'tree-action-btn' | grep -v 'tree-folder-add-btn' | grep -v 'tree-item-undo-btn' | grep -v 'editor-tab-scroll-btn' | grep -v 'pagination' | grep -v 'new-object-type-btn' | grep -v 'remove-btn'
```

Any remaining custom button classes should be investigated.

**Step 2: Visual QA walkthrough**

Visit every page and check buttons:
- Explorer: Select menu, Run Validation, graph/close/toolbar buttons, cleanup action buttons, "Keep This" in duplicate resolver
- Commit dialog: Discard All / Cancel / Apply Changes
- Git page: Restore buttons, Wipe Git Log
- Backups: Create Backup, Delete, Restore, Delete All Backups
- Settings: Browse, Download, Save, Reset, Select/Cancel in browse dialog
- Audit Log: Clear Log
- Validate: Run Validation
- Dependencies: Fit to View, Hide Connection Labels
- Bulk Rename: Preview, Show Diff, Apply
- Reorganize: Move, Clone, Delete, Select All/None

**Step 3: Final commit if any fixes needed**

```bash
git commit -m "fix: button consolidation visual fixes"
```
