# MD3 Button Redesign

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace color-coded button variants with an MD3 emphasis hierarchy so buttons communicate importance through visual weight, not just color.

**Architecture:** The `.nbe-btn--dark` system currently has 5 color-coded variants (primary/secondary/danger/info/ghost). This plan replaces 4 of them with MD3 emphasis levels (filled/tonal/outlined/text) and keeps danger as a color role. The filled button switches from white-on-teal to dark-on-teal for readability.

**Tech Stack:** CSS (tokens.css), HTML templates, JavaScript (commit-dialog.js, ui-notifications.js, analysis.js, analysis-issues.js, git.js), CLAUDE.md docs

---

### Task 1: Add new MD3 dark button variants to tokens.css

**Files:**
- Modify: `static/css/tokens.css` (after existing dark button variants)

**Step 1: Add the 4 new variants**

After the existing `.nbe-btn--dark.nbe-btn--ghost:hover` block, add:

```css
/* MD3 Emphasis Hierarchy — Dark Theme */

.nbe-btn--dark.nbe-btn--filled {
    background: var(--nbe-dark-accent-primary);
    color: var(--nbe-dark-bg-primary);
    border: none;
}

.nbe-btn--dark.nbe-btn--filled:hover {
    background: var(--nbe-dark-accent-primary-hover);
}

.nbe-btn--dark.nbe-btn--tonal {
    background: var(--nbe-dark-accent-alpha-20);
    color: var(--nbe-dark-accent-primary);
    border: none;
}

.nbe-btn--dark.nbe-btn--tonal:hover {
    background: var(--nbe-dark-accent-alpha-30);
}

.nbe-btn--dark.nbe-btn--outlined {
    background: transparent;
    color: var(--nbe-dark-text-primary);
    border: 1px solid var(--nbe-dark-border-primary);
}

.nbe-btn--dark.nbe-btn--outlined:hover {
    background: var(--nbe-dark-bg-hover);
    border-color: var(--nbe-dark-border-hover);
}

.nbe-btn--dark.nbe-btn--text {
    background: transparent;
    color: var(--nbe-dark-text-secondary);
    border: none;
}

.nbe-btn--dark.nbe-btn--text:hover {
    color: var(--nbe-dark-text-primary);
}
```

**Step 2: Delete old variants**

Remove these blocks:
- `.nbe-btn--dark.nbe-btn--primary` + hover
- `.nbe-btn--dark.nbe-btn--secondary`
- `.nbe-btn--dark.nbe-btn--info`
- `.nbe-btn--dark.nbe-btn--ghost` + hover

Keep `.nbe-btn--dark.nbe-btn--danger` unchanged.

**Step 3: Verify** — `python3 -m pytest tests/ -v`

**Step 4: Commit**

```bash
git add static/css/tokens.css
git commit -m "feat: replace dark button color variants with MD3 emphasis hierarchy"
```

---

### Task 2: Migrate template buttons (--primary → --filled, --secondary → --outlined)

**Files:**
- Modify: `templates/explorer.html` (lines 267-268: dialog buttons)
- Modify: `templates/dependencies.html` (lines 27-28, 142: graph controls)
- Modify: `templates/settings.html` (lines 59, 70, 86, 97, 142, 150-151, 178, 197, 204-205)
- Modify: `templates/backups.html` (lines 25, 50, 106, 109)
- Modify: `templates/validate.html` (line 22)
- Modify: `templates/reorganize.html` (lines 71, 94, 113, 129-130)
- Modify: `templates/audit_log.html` (line 94)
- Modify: `templates/git.html` (line 46)
- Modify: `templates/bulk_rename.html` (lines 65-67)
- Modify: `templates/base.html` (lines 116-117: confirm dialog)

**Step 1: Global find-replace in templates**

In all `.html` files:
- `nbe-btn--primary` → `nbe-btn--filled`
- `nbe-btn--secondary` → `nbe-btn--outlined`

**Step 2: Verify** — `python3 -m pytest tests/ -v`

**Step 3: Commit**

```bash
git add templates/
git commit -m "refactor: migrate template buttons to MD3 emphasis classes"
```

---

### Task 3: Migrate JS buttons

**Files:**
- Modify: `static/js/commit-dialog.js` (lines 181, 294: Apply Changes)
- Modify: `static/js/ui-notifications.js` (line 120: dynamic confirm button)
- Modify: `static/js/git.js` (line 479: restore — currently bare `--dark`, no change needed)
- Modify: `static/js/explorer/analysis.js` (line 1112: Keep This → `--outlined`)
- Modify: `static/js/explorer/analysis-issues.js` (line 157: Create All — add `--dark`, change `--primary` → `--filled`)

**Step 1: Update commit-dialog.js**

Lines 181 and 294: `nbe-btn--primary` → `nbe-btn--filled`

**Step 2: Update ui-notifications.js**

Line 120: Change `'nbe-btn--primary'` → `'nbe-btn--filled'` in the dynamic class assignment.

**Step 3: Update analysis.js**

Line 1112: `nbe-btn--secondary` → `nbe-btn--outlined`

**Step 4: Update analysis-issues.js**

Line 157: Change `nbe-btn nbe-btn--primary nbe-btn--xs` → `nbe-btn nbe-btn--dark nbe-btn--filled nbe-btn--xs`

**Step 5: Verify** — `python3 -m pytest tests/ -v`

**Step 6: Commit**

```bash
git add static/js/
git commit -m "refactor: migrate JS buttons to MD3 emphasis classes"
```

---

### Task 4: Migrate --info → --tonal and --ghost → --text

**Files:**
- Modify: `templates/explorer.html` (line 81: graph btn `--ghost` → `--text`, line 195: Run Validation `--info` → `--tonal`)
- Modify: `static/js/commit-dialog.js` (line 436: Retry Commit `--info` → `--tonal`)

**Step 1: Update explorer.html**

- Line 81: `nbe-btn--ghost` → `nbe-btn--text`
- Line 195: `nbe-btn--info` → `nbe-btn--tonal`

**Step 2: Update commit-dialog.js**

- Line 436: `nbe-btn--info` → `nbe-btn--tonal`

**Step 3: Verify** — `python3 -m pytest tests/ -v`

**Step 4: Commit**

```bash
git add templates/explorer.html static/js/commit-dialog.js
git commit -m "refactor: migrate info and ghost buttons to tonal and text"
```

---

### Task 5: Update documentation

**Files:**
- Modify: `static/css/CLAUDE.md` (Button System section)

**Step 1: Update button system docs**

Replace the button system section with:

```markdown
## Button System

Base class `.nbe-btn` with modifiers. All defined in `tokens.css`.

**Emphasis (MD3 hierarchy, high → low)**: `--filled`, `--tonal`, `--outlined`, `--text`
**Color role**: `--danger` (destructive actions, any emphasis level)
**Sizes**: `--xs`, `--sm`, (default), `--lg`
**Modifiers**: `--icon` (square), `--full` (width:100%), `.nbe-btn-group`
**Dark theme**: Add `--dark` (e.g. `.nbe-btn--dark.nbe-btn--filled`)
**Loading state**: Set `data-loading="true"` in JS
```

**Step 2: Commit**

```bash
git add static/css/CLAUDE.md
git commit -m "docs: update button system docs for MD3 emphasis hierarchy"
```

---

### Task 6: Final audit

**Step 1: Grep for any remaining old variant names in dark context**

Search for `nbe-btn--primary`, `nbe-btn--secondary`, `nbe-btn--info`, `nbe-btn--ghost` in all HTML, JS, and CSS files. Any remaining instances should be light-theme only (no `--dark` companion).

**Step 2: Verify tests pass** — `python3 -m pytest tests/ -v`

**Step 3: Commit fixes if any**
