# L13 — `static/css/explorer.css` — MODIFY

## Purpose
Rename staging CSS classes to candidate equivalents while preserving all visual styling. Every visual indicator (creation highlight, deletion strikethrough, move warning, count badge, indicator badges) must retain its exact appearance under the new class names. The candidate system still needs these visual indicators to show the user what has changed in the candidate session before Apply.

## Rationale (Commandment 2 — UI Visual Parity)
The staging-to-candidate migration changes the underlying mechanism (client-side state to server-side candidate diff), but the **user-facing visual indicators are still needed**. The `computeCandidateBadges()` function (L07-state-management) and candidate badge rendering (L11-app, L08-file-operations) will apply these CSS classes to DOM elements based on `state.candidateDiff` data. Deleting the visual styles without equivalent replacements would leave the UI with no change indicators — violating UI visual parity.

## Rename Inventory

Every existing staging CSS rule block is renamed, not deleted. The visual properties (colors, opacity, backgrounds, borders, fonts) are preserved exactly.

### Tree item indicators (lines ~897-1070)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.tree-item.staged` | `.tree-item.candidate-modified` | Warning background, 3px warning border-left, opacity 0.8 |
| `.tree-item.staged.selected` | `.tree-item.candidate-modified.selected` | Warning border selected state |
| `.tree-item.staged-creation` | `.tree-item.candidate-created` | Green success background, 3px green border-left |
| `.tree-item.staged-creation:hover` | `.tree-item.candidate-created:hover` | Green success badge hover |
| `.tree-item.staged-creation.selected` | `.tree-item.candidate-created.selected` | Green success badge selected |
| `.tree-item.staged-for-deletion` | `.tree-item.candidate-deleted` | Red error background, opacity 0.7 |
| `.tree-item.staged-for-deletion .tree-item-name` | `.tree-item.candidate-deleted .tree-item-name` | Strikethrough, delete color |
| `.tree-item.staged-for-deletion .tree-item-type` | `.tree-item.candidate-deleted .tree-item-type` | Opacity 0.5 |

### Badges and counts (lines ~1040, ~1103)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.tree-item-staged-badge` | `.tree-item-candidate-badge` | Badge indicator styling |
| `.staged-count` | `.candidate-count` | Green font, weight 600 |

### Workspace object rows (lines ~1923-1931)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.workspace-object-row.pending` | `.workspace-object-row.candidate-modified` | Success background, green border-left |
| `.workspace-object-row.staged-creation` | `.workspace-object-row.candidate-created` | Warning background, warning border-left |

### Folder/file deletion (line ~3094)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.staged-deletion` | `.candidate-deletion` | Opacity 0.6 |

### Move target items (lines ~3144-3152)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.target-object-item.pending` | `.target-object-item.candidate-modified` | Success background, green border-left |
| `.target-object-item.staged-creation` | `.target-object-item.candidate-created` | Warning background, warning border-left |

### Context menu (lines ~3966-3968)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.context-menu.staged-context` | `.context-menu.candidate-context` | Hide non-danger items |

### Workspace tree rows (lines ~5431-5441)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.workspace-tree-row.staged-new` | `.workspace-tree-row.candidate-new` | Green success background |
| `.workspace-tree-row.staged-deletion` | `.workspace-tree-row.candidate-deletion` | Red error background |
| `.workspace-tree-row.staged-move` | `.workspace-tree-row.candidate-move` | Yellow warning background |

### Tree labels (lines ~1804, ~5451-5452)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.tree-label--staged` | `.tree-label--candidate` | Green italic label |
| `.tree-item .tree-label--staged` | `.tree-item .tree-label--candidate` | Green italic label (tree context) |
| `.workspace-tree-row .tree-label--staged` | `.workspace-tree-row .tree-label--candidate` | Green italic label (workspace context) |

### Indicator badges (lines ~5458-5481)

| Old Selector | New Selector | Visual Effect (PRESERVED) |
|---|---|---|
| `.staged-indicator` | `.candidate-indicator` | Base badge: xs font, weight 600, rounded, letter-spacing |
| `.staged-indicator--new` | `.candidate-indicator--new` | Green badge (success background + color) |
| `.staged-indicator--delete` | `.candidate-indicator--delete` | Red badge (error background + danger color) |
| `.staged-indicator--move` | `.candidate-indicator--move` | Amber badge (warning background + color) |

## Changes

**1. Rename all staging CSS selectors to candidate equivalents.**

For each rule block listed above, change only the selector (class name). Do NOT change any CSS property values. The visual styling must remain pixel-identical.

Example transformation:
```css
/* BEFORE */
.tree-item.staged {
    opacity: 0.8;
    background: var(--nbe-dark-warning-bg);
    border-left: 3px solid var(--nbe-dark-accent-warning);
}

/* AFTER */
.tree-item.candidate-modified {
    opacity: 0.8;
    background: var(--nbe-dark-warning-bg);
    border-left: 3px solid var(--nbe-dark-accent-warning);
}
```

```css
/* BEFORE */
.tree-item.staged-creation {
    background: var(--nbe-dark-validation-success-bg);
    border-left: 3px solid var(--nbe-success);
}

/* AFTER */
.tree-item.candidate-created {
    background: var(--nbe-dark-validation-success-bg);
    border-left: 3px solid var(--nbe-success);
}
```

```css
/* BEFORE */
.tree-item.staged-for-deletion {
    opacity: 0.7;
    background: var(--nbe-dark-validation-error-bg);
}
.tree-item.staged-for-deletion .tree-item-name {
    text-decoration: line-through;
    color: var(--color-delete);
}
.tree-item.staged-for-deletion .tree-item-type {
    opacity: 0.5;
}

/* AFTER */
.tree-item.candidate-deleted {
    opacity: 0.7;
    background: var(--nbe-dark-validation-error-bg);
}
.tree-item.candidate-deleted .tree-item-name {
    text-decoration: line-through;
    color: var(--color-delete);
}
.tree-item.candidate-deleted .tree-item-type {
    opacity: 0.5;
}
```

```css
/* BEFORE */
.staged-count {
    color: var(--nbe-success);
    font-weight: 600;
}

/* AFTER */
.candidate-count {
    color: var(--nbe-success);
    font-weight: 600;
}
```

```css
/* BEFORE */
.staged-indicator { ... }
.staged-indicator--new { ... }
.staged-indicator--delete { ... }
.staged-indicator--move { ... }

/* AFTER */
.candidate-indicator { ... }
.candidate-indicator--new { ... }
.candidate-indicator--delete { ... }
.candidate-indicator--move { ... }
```

**2. Update CSS comments** to say "Candidate" instead of "Staged":
- `/* Staged for deletion styles */` -> `/* Candidate deletion styles */`
- `/* Staged row indicators */` -> `/* Candidate row indicators */`
- `/* Staged indicator badges */` -> `/* Candidate indicator badges */`

## Cross-Plan Coordination

The following L-plans render DOM elements with these CSS classes and MUST use the new `candidate-*` class names:

| L-Plan | File | Classes Used |
|--------|------|-------------|
| L11-app.md | app.js | `candidate-modified`, `candidate-created`, `candidate-deleted`, `candidate-count`, `tree-item-candidate-badge` |
| L08-file-operations.md | file-operations.js | `candidate-indicator`, `candidate-indicator--new`, `candidate-indicator--delete`, `candidate-indicator--move`, `candidate-new`, `candidate-deletion`, `candidate-move`, `candidate-created`, `candidate-modified` |
| L08-context-menu.md | context-menu.js | `candidate-context` |
| L07-state-management.md | state-management.js | `computeCandidateBadges()` applies classes via tree rebuild |
| L07-data-loading.md | data-loading.js | `refreshCandidateDiff()` triggers badge computation |

**Note:** L11-app.md and L08-file-operations.md currently reference old `staged-*` class names for removal. When implementing, those plans must use the renamed `candidate-*` equivalents from this plan instead.

## Verification
- App loads, all styles correct
- `grep -rn "staged" static/css/explorer.css` returns zero matches (all renamed to `candidate-*`)
- Tree items with candidate changes show correct visual indicators:
  - Modified items: warning background with amber border
  - Created items: green background with green border
  - Deleted items: red background, strikethrough name, reduced opacity
  - Move indicators: amber warning badges
- Candidate count badge in folder tree shows green styled count
- Indicator badges (NEW/DEL/MOV) render with correct color coding
- `npm run lint:js` passes (JS files reference new class names)
- Playwright: visual regression test confirms indicator colors match pre-migration screenshots

## Commandments Compliance

- [x] **1. No live config mutation until Apply.** CSS-only change; no config mutation logic.
- [x] **2. UI visual parity.** All 16+ staging visual indicator CSS rule blocks are RENAMED (not deleted). Every visual property (colors, backgrounds, borders, opacity, strikethrough, font weights) is preserved exactly. The renamed `candidate-*` classes provide identical visual styling to their `staged-*` predecessors.
- [x] **3. Full audit logging.** CSS-only change; no audit logging applicable.
- [x] **4. Proper error handling.** CSS-only change; no error handling applicable.
- [x] **5. Dead code deletion.** Old `staged-*` class names are removed (renamed to `candidate-*`). No orphaned rules remain.
- [x] **6. Full functionality migration.** Every staging visual indicator is migrated to its candidate equivalent. The rename inventory above maps each old selector to its new counterpart 1:1. No indicator is dropped.
- [x] **7. Palo Alto candidate model.** Visual indicators now use `candidate-*` naming consistent with the Palo Alto candidate configuration model.
- [x] **8. Change tracking document.** The rename inventory table above serves as the complete change tracking record with old/new selector mappings.
- [x] **9. Complete planning before implementation.** This plan is fully specified with every selector enumerated before any code changes.
- [x] **10. Linting enforcement.** CSS changes only; JS files referencing new class names must pass `npm run lint:js`. Stylelint must pass on the renamed selectors.
- [x] **11. Playwright validation.** Verification section includes Playwright visual regression test requirement for indicator colors.
