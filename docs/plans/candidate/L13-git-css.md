# L13 — `static/css/git.css` — MODIFY

**Layer:** 13 — CSS Cleanup
**Action:** MODIFY
**Path:** `static/css/git.css`
**Dependencies:** L09-git.md (renames CSS class references in git.js from `git-staging-preview-*` to `git-candidate-preview-*`)
**Goal:** Delete all dead staging CSS selectors. Rename the staging preview section classes to candidate equivalents with identical visual properties. No visual change to the user.

---

## Purpose

Remove dead staging CSS classes from `static/css/git.css` and replace the staging preview section with candidate preview equivalents. The visual appearance of the git page preview section must remain identical (Commandment 2: UI visual parity). Class names change from `git-staging-preview-*` to `git-candidate-preview-*` to match the candidate model terminology (Commandment 7).

## Removal Audit

### Group A: Already-Dead Code (no JS or HTML consumers exist today)

These selectors have ZERO references in any JavaScript or HTML template file. They are dead code in the current codebase, not just "dead after L09 changes." Verified via `grep -rn` across `static/js/` and `templates/`.

| Line | Selector | Status |
|------|----------|--------|
| 338 | `.git-file-item.staged-item` | DEAD — delete |
| 342 | `.git-file-item.staged-item:hover` | DEAD — delete |
| 346 | `.git-status-badge.staged` | DEAD — delete |
| 351 | `.staged-item-type` | DEAD — delete |
| 362 | `.staged-item-name` | DEAD — delete |
| 367 | `.staged-item-arrow` | DEAD — delete |
| 372 | `.staged-item-target` | DEAD — delete |
| 377 | `.staged-item-from` | DEAD — delete |
| 461 | `.staged-detail-view` | DEAD — delete |
| 466 | `.staged-detail-header` | DEAD — delete |
| 476 | `.staged-detail-row` | DEAD — delete |
| 483 | `.staged-detail-label` | DEAD — delete |
| 489 | `.staged-detail-value` | DEAD — delete |
| 495 | `.staged-detail-from` | DEAD — delete |
| 499 | `.staged-detail-to` | DEAD — delete |
| 503 | `.staged-detail-note` | DEAD — delete |

**16 selectors, ~75 lines deleted. No candidate equivalents needed — these have no consumers and L09-git.md does not introduce new DOM elements using equivalent classes.**

### Group B: Staging Preview Classes (renamed to candidate equivalents)

These selectors ARE referenced in `static/js/git.js` (lines 107-189). After L09-git.md renames them to `git-candidate-preview-*`, the old names become dead and the new names must exist with identical visual properties.

| Line | Old Selector | New Selector | Action |
|------|-------------|-------------|--------|
| 738 | `.git-staging-preview-wrapper` | `.git-candidate-preview-wrapper` | RENAME — identical properties |
| 744 | `.git-staging-preview` | `.git-candidate-preview` | RENAME — identical properties |
| 752 | `.git-staging-preview-header` | `.git-candidate-preview-header` | RENAME — identical properties |
| 762 | `.git-staging-preview-count` | `.git-candidate-preview-count` | RENAME — identical properties |
| 772 | `.git-staging-preview-list` | `.git-candidate-preview-list` | RENAME — identical properties |
| 778 | `.git-staging-preview-list li` | `.git-candidate-preview-list li` | RENAME — identical properties |
| 784 | `.git-staging-preview-list li::before` | `.git-candidate-preview-list li::before` | RENAME — identical properties |
| 790 | `.git-staging-preview-note` | `.git-candidate-preview-note` | RENAME — identical properties |
| 797 | `.git-staging-preview-commit` | `.git-candidate-preview-commit` | RENAME — identical properties |
| 809 | `.git-staging-preview-commit:hover` | `.git-candidate-preview-commit:hover` | RENAME — identical properties |

**10 selectors renamed. Every CSS property value preserved exactly.**

## Changes

### Task 1: Delete Group A dead code (lines 338-381, 461-511)

Delete the following rule blocks entirely (~75 lines):

```css
/* DELETE lines 338-381: staged-item and staged-detail selectors */
.git-file-item.staged-item { ... }
.git-file-item.staged-item:hover { ... }
.git-status-badge.staged { ... }
.staged-item-type { ... }
.staged-item-name { ... }
.staged-item-arrow { ... }
.staged-item-target { ... }
.staged-item-from { ... }

/* DELETE lines 461-511: staged-detail selectors */
.staged-detail-view { ... }
.staged-detail-header { ... }
.staged-detail-row { ... }
.staged-detail-label { ... }
.staged-detail-value { ... }
.staged-detail-from { ... }
.staged-detail-to { ... }
.staged-detail-note { ... }
```

### Task 2: Rename Group B preview section (lines 738-811)

Rename every `git-staging-preview` to `git-candidate-preview` in the section comment and all selector names. Property values remain exactly the same. Update section comment from "Staging Preview" to "Candidate Preview".

**Before:**
```css
/* ============================================================================
   Staging Preview
   ============================================================================ */

.git-staging-preview-wrapper {
    width: 100%;
    flex-shrink: 0;
    border-bottom: 1px solid var(--nbe-dark-border-primary);
}

.git-staging-preview {
    padding: var(--nbe-space-md) var(--nbe-space-xl);
    background: var(--nbe-dark-accent-alpha-10);
    border: 1px solid var(--nbe-dark-accent-alpha-30);
    border-radius: var(--nbe-radius-lg);
    margin: var(--nbe-space-md) var(--nbe-space-lg);
}

.git-staging-preview-header {
    display: flex;
    align-items: center;
    gap: var(--nbe-space-sm);
    font-weight: 600;
    font-size: var(--nbe-font-size-md);
    color: var(--nbe-dark-accent-primary);
    margin-bottom: var(--nbe-space-sm);
}

.git-staging-preview-count {
    background: var(--nbe-dark-accent-primary);
    color: var(--nbe-dark-bg-primary);
    font-size: var(--nbe-font-size-xs-plus);
    font-weight: 700;
    padding: 2px 7px;
    border-radius: var(--nbe-radius-pill);
    margin-left: var(--nbe-space-xs);
}

.git-staging-preview-list {
    list-style: none;
    margin: 0 0 var(--nbe-space-sm) 0;
    padding: 0;
}

.git-staging-preview-list li {
    padding: 3px 0;
    font-size: var(--nbe-font-size-base);
    color: var(--nbe-dark-text-primary);
}

.git-staging-preview-list li::before {
    content: "\2022";
    color: var(--nbe-dark-accent-primary);
    margin-right: var(--nbe-space-sm);
}

.git-staging-preview-note {
    font-size: var(--nbe-font-size-sm);
    color: var(--nbe-dark-text-secondary);
    font-style: italic;
    margin-bottom: var(--nbe-space-sm);
}

.git-staging-preview-commit {
    padding: var(--nbe-space-xs-plus) var(--nbe-space-md);
    background: var(--nbe-dark-accent-alpha-20);
    color: var(--nbe-dark-accent-primary);
    border: none;
    border-radius: var(--nbe-radius-md);
    font-size: var(--nbe-font-size-sm);
    font-weight: 500;
    cursor: pointer;
    transition: background var(--nbe-transition-fast);
}

.git-staging-preview-commit:hover {
    background: var(--nbe-dark-accent-alpha-30);
}
```

**After:**
```css
/* ============================================================================
   Candidate Preview
   ============================================================================ */

.git-candidate-preview-wrapper {
    width: 100%;
    flex-shrink: 0;
    border-bottom: 1px solid var(--nbe-dark-border-primary);
}

.git-candidate-preview {
    padding: var(--nbe-space-md) var(--nbe-space-xl);
    background: var(--nbe-dark-accent-alpha-10);
    border: 1px solid var(--nbe-dark-accent-alpha-30);
    border-radius: var(--nbe-radius-lg);
    margin: var(--nbe-space-md) var(--nbe-space-lg);
}

.git-candidate-preview-header {
    display: flex;
    align-items: center;
    gap: var(--nbe-space-sm);
    font-weight: 600;
    font-size: var(--nbe-font-size-md);
    color: var(--nbe-dark-accent-primary);
    margin-bottom: var(--nbe-space-sm);
}

.git-candidate-preview-count {
    background: var(--nbe-dark-accent-primary);
    color: var(--nbe-dark-bg-primary);
    font-size: var(--nbe-font-size-xs-plus);
    font-weight: 700;
    padding: 2px 7px;
    border-radius: var(--nbe-radius-pill);
    margin-left: var(--nbe-space-xs);
}

.git-candidate-preview-list {
    list-style: none;
    margin: 0 0 var(--nbe-space-sm) 0;
    padding: 0;
}

.git-candidate-preview-list li {
    padding: 3px 0;
    font-size: var(--nbe-font-size-base);
    color: var(--nbe-dark-text-primary);
}

.git-candidate-preview-list li::before {
    content: "\2022";
    color: var(--nbe-dark-accent-primary);
    margin-right: var(--nbe-space-sm);
}

.git-candidate-preview-note {
    font-size: var(--nbe-font-size-sm);
    color: var(--nbe-dark-text-secondary);
    font-style: italic;
    margin-bottom: var(--nbe-space-sm);
}

.git-candidate-preview-commit {
    padding: var(--nbe-space-xs-plus) var(--nbe-space-md);
    background: var(--nbe-dark-accent-alpha-20);
    color: var(--nbe-dark-accent-primary);
    border: none;
    border-radius: var(--nbe-radius-md);
    font-size: var(--nbe-font-size-sm);
    font-weight: 500;
    cursor: pointer;
    transition: background var(--nbe-transition-fast);
}

.git-candidate-preview-commit:hover {
    background: var(--nbe-dark-accent-alpha-30);
}
```

### Task 3: Verify no remaining staging references

After changes:
```bash
grep -n "staging\|staged" static/css/git.css
```
Expected: zero matches.

## Change Tracking

| # | Task | Description | Status |
|---|------|-------------|--------|
| 1 | Delete Group A dead code | Remove `.staged-item-*`, `.staged-detail-*`, `.git-file-item.staged-item`, `.git-status-badge.staged` (lines 338-381, 461-511, ~75 lines) | [ ] |
| 2 | Rename preview section comment | Change `Staging Preview` to `Candidate Preview` in section header (line 735) | [ ] |
| 3 | Rename `.git-staging-preview-wrapper` | Change to `.git-candidate-preview-wrapper` (line 738) | [ ] |
| 4 | Rename `.git-staging-preview` | Change to `.git-candidate-preview` (line 744) | [ ] |
| 5 | Rename `.git-staging-preview-header` | Change to `.git-candidate-preview-header` (line 752) | [ ] |
| 6 | Rename `.git-staging-preview-count` | Change to `.git-candidate-preview-count` (line 762) | [ ] |
| 7 | Rename `.git-staging-preview-list` | Change to `.git-candidate-preview-list` (line 772) | [ ] |
| 8 | Rename `.git-staging-preview-list li` | Change to `.git-candidate-preview-list li` (line 778) | [ ] |
| 9 | Rename `.git-staging-preview-list li::before` | Change to `.git-candidate-preview-list li::before` (line 784) | [ ] |
| 10 | Rename `.git-staging-preview-note` | Change to `.git-candidate-preview-note` (line 790) | [ ] |
| 11 | Rename `.git-staging-preview-commit` | Change to `.git-candidate-preview-commit` (line 797) | [ ] |
| 12 | Rename `.git-staging-preview-commit:hover` | Change to `.git-candidate-preview-commit:hover` (line 809) | [ ] |
| 13 | Verify zero staging references | Run `grep -n "staging\|staged" static/css/git.css` and confirm zero matches | [ ] |

## Verification

### Manual Verification
- Git page loads without CSS errors in the console
- Candidate preview section renders with correct styling when a candidate session is active
- Preview container has the accent-tinted background, rounded border, proper spacing
- Count badge renders as a pill with accent background
- Change list items have bullet markers
- Note text is italic and secondary color
- "Review & Commit" button has hover state transition
- Diff viewer, file list, history table, and all non-preview sections are visually unaffected

### Automated Verification
```bash
# No staging/staged references remain
grep -n "staging\|staged" static/css/git.css
# Expected: zero matches

# All new candidate selectors exist
grep -c "git-candidate-preview" static/css/git.css
# Expected: 10 (matching the 10 renamed selectors)
```

### Playwright Validation
After L09-git.md and L13-git-css.md are both applied:

1. **Git page loads with candidate preview visible:**
   - Navigate to the git page while a candidate session is active
   - Assert `.git-candidate-preview` element is visible
   - Assert `.git-candidate-preview-header` contains "Pending Candidate Changes"
   - Assert `.git-candidate-preview-count` displays a number
   - Assert `.git-candidate-preview-list` contains at least one `<li>`

2. **Visual parity check on preview section:**
   - Assert `.git-candidate-preview` has `background` matching `var(--nbe-dark-accent-alpha-10)` (computed as a semi-transparent accent)
   - Assert `.git-candidate-preview` has `border-radius` matching the `--nbe-radius-lg` token
   - Assert `.git-candidate-preview-commit` button is clickable and has a hover state

3. **Git page loads without candidate session:**
   - Navigate to the git page with no candidate session active
   - Assert `.git-candidate-preview` element does NOT exist in the DOM
   - Assert file list and diff viewer render correctly

4. **No dead CSS references in DOM:**
   - Assert no elements matching `.git-staging-preview`, `.staged-item`, `.staged-detail` exist in the page DOM

### Linting
```bash
# CSS file must pass stylelint (if configured) or at minimum have valid syntax
# Verify no syntax errors by loading the git page and checking for CSS parse errors in console
```

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | CSS-only change; does not affect config mutation flow. |
| 2 | UI visual parity | COMPLIANT | All 10 renamed selectors preserve every CSS property value exactly. Before/after CSS blocks are shown in full. No visual change to the user. |
| 3 | Full audit logging | N/A | CSS changes do not involve server operations. No audit log entries needed. |
| 4 | Proper error handling | N/A | CSS changes do not involve error paths. Verification section covers checking for CSS parse errors. |
| 5 | Dead code deletion | COMPLIANT | 16 Group A selectors with zero JS/HTML consumers are deleted entirely. No dead code is renamed or preserved. |
| 6 | Full functionality migration | COMPLIANT | All 10 Group B preview selectors that ARE consumed by git.js are migrated to candidate equivalents with identical visual properties. Nothing dropped. |
| 7 | Palo Alto candidate model | COMPLIANT | All class names use `candidate` terminology replacing `staging`. Section comment updated to "Candidate Preview". |
| 8 | Change tracking document | COMPLIANT | 13-item numbered task checklist provided in Change Tracking section. |
| 9 | Complete planning before implementation | COMPLIANT | Full before/after CSS blocks specified with every property value. No placeholder `{ }` blocks. Every selector enumerated with line numbers. |
| 10 | Linting enforcement | COMPLIANT | Verification section includes linting check. CSS is token-based (no hardcoded colors) per project conventions. |
| 11 | Playwright validation | COMPLIANT | Four Playwright test scenarios specified: preview visible with session, visual parity assertions, no-session rendering, and dead selector absence check. |
