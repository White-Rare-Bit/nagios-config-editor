# MD3 Hover State Consistency Plan

**Goal:** Normalize dark-theme hover states to follow MD3 guidelines — single-property background changes for containers, no multi-property hover bloat, no transform/elevation on hover.

**Scope:** Dark theme only. ~35 rules to simplify across `explorer.css`, `audit_log.css`, `settings.css`, `git.css`, `dependencies.css`, and `base.html` inline styles.

**Out of scope:** Buttons (already use MD3 state layer), light theme, opacity-based reveal patterns (showing hidden actions on row hover — these are fine).

---

### Task 1: Simplify multi-property hover rules to background-only

~20 rules change background + border + text color on hover. MD3 containers should only change background.

**Rules to simplify** (keep only `background: var(--nbe-dark-bg-hover)`; remove border-color and color changes):

- `explorer.css` — `.suggestion-item:hover` (remove `border-left-color`)
- `explorer.css` — `.dialog-entry-item:hover` (remove `border-color`)
- `explorer.css` — `.cleanup-detail-item:hover` (remove `border-color`)
- `explorer.css` — `.ancestry-chain-item:hover` (remove `border-color`)
- `explorer.css` — `.suggestion-action:hover` (remove `border-color`)
- `explorer.css` — `.batch-btn:hover` (remove `border-color`, `color`)
- `explorer.css` — `.summary-filter:hover` (remove `color`)
- `explorer.css` — `.git-file-action:hover` in `git.css` (remove `color`)
- `audit_log.css` — `.filter-chip:hover` (remove `color`, `border-color`)
- `audit_log.css` — `.audit-entry:hover` (remove `box-shadow`, keep `border-color` since cards use elevation in MD3)
- `git.css` — `.git-container .page-tab:hover` (remove `color`)

**Verify:** Each element still has adequate hover feedback with background-only change.

---

### Task 2: Remove transform/elevation hover effects

MD3 does not use transform or shadow changes for hover states (that's for focus/dragged states).

- `base.html` — `.identity-required-btn:hover`: Remove `transform: translateY(-1px)` and `box-shadow`. Keep background change.

---

### Task 3: Fix attr-row hover expanding into margins

`explorer.css` — `.attr-row:hover` changes `margin` and `padding` on hover, causing layout shift. Replace with background-only.

---

### Task 4: Audit and verify

Grep for `:hover` rules in dark-theme CSS that change more than one property. Confirm all are either:
- Background-only (containers)
- Color-only (text/icon brightening — acceptable for affordance)
- Opacity-only (reveal hidden actions — acceptable)
