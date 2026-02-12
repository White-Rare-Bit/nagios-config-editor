# Documentation Typography, Layout & Visual Clarity

**Date**: 2026-02-12
**Status**: Draft
**Supersedes**: `2026-02-12-svg-diagrams-design.md` (SVG-only approach replaced with broader improvements)

## Problem

The docs pages use the app's UI typography scale (13px body, 12px tables, compressed heading hierarchy). This is appropriate for dense app interfaces but creates visually monotonous, hard-to-scan documentation. The pages lack visual variety — the only textures are prose, tables, code blocks, and two callout types.

## Design Principles

1. **Docs-specific overrides only** — all changes scoped to `.docs-prose`, app UI unchanged
2. **Reading-optimized typography** — sized for long-form prose, not app UI density
3. **Visual variety through CSS components** — new callout types, step indicators, summary boxes
4. **Strategic SVGs only** — keep existing diagrams, add only where visuals genuinely explain what text cannot
5. **Better cross-linking** — weave references throughout pages, not just at the end

## Part 1: Typography Overrides

All values applied within `.docs-prose` scope in `docs.css`.

### Heading Scale

```css
.docs-prose h2 { font-size: 28px; font-weight: 700; margin: 0 0 20px; }
.docs-prose h3 { font-size: 21px; font-weight: 600; margin: 44px 0 16px; }
.docs-prose h4 { font-size: 17px; font-weight: 600; margin: 28px 0 12px; }
```

Current: h2=20px, h3=16px, h4=14px. The h4-to-body gap is only 1px — barely a heading.

### Body Text

```css
.docs-prose p {
    font-size: 15px;
    color: #b0b0b0;         /* up from #888 — 7.5:1 contrast vs 4.7:1 */
    line-height: 1.75;       /* up from 1.6 */
    margin: 0 0 20px;        /* up from 12px */
}
```

### Lists

```css
.docs-prose ul, .docs-prose ol {
    font-size: 15px;
    color: #b0b0b0;
    line-height: 1.75;
    margin: 0 0 20px;
}

.docs-prose li {
    margin-bottom: 6px;     /* up from 4px */
}
```

### Tables

```css
.docs-prose table { font-size: 14px; margin: 0 0 20px; }
.docs-prose th { padding: 10px 16px; }
.docs-prose td { padding: 10px 16px; color: #b0b0b0; }
```

### Code

```css
.docs-prose code { font-size: 13px; }        /* inline code */
.docs-prose pre { padding: 16px; margin: 0 0 20px; }
.docs-prose pre code { font-size: 13px; line-height: 1.7; }
```

### Layout

```css
.docs-prose {
    max-width: 800px;        /* down from 900px — optimal line length */
    padding: 48px 40px;      /* fix: --nbe-space-xxl was undefined */
    margin: 0 auto;
}
```

### Miscellaneous

```css
.docs-prose hr { margin: 40px 0; }          /* up from 24px */
.docs-prose strong { color: #d4d4d4; }      /* keep as-is */
.docs-prose a { color: #4ec9b0; }           /* keep as-is */

.docs-prose kbd {
    font-size: 13px;                         /* up from 11px */
    padding: 3px 7px;
}
```

### Callouts

Bump internal padding and text size to match new body scale:

```css
.docs-prose .docs-note,
.docs-prose .docs-warning {
    padding: 16px;           /* up from 12px */
    font-size: 15px;         /* match body */
    margin: 0 0 20px;
}
```

## Part 2: New CSS Components

### 2a. Additional Callout Types

Currently only `.docs-note` (blue) and `.docs-warning` (yellow). Add:

**`.docs-tip`** (green) — positive guidance, best practices:
```html
<div class="docs-tip">
    Use <kbd>Ctrl</kbd>+<kbd>Z</kbd> to undo any staging operation instantly.
</div>
```

```css
.docs-prose .docs-tip {
    padding: 16px;
    margin: 0 0 20px;
    background: rgba(76, 175, 80, 0.08);
    border: 1px solid rgba(76, 175, 80, 0.25);
    border-radius: var(--nbe-radius-md);
    color: #b0b0b0;
    font-size: 15px;
    line-height: 1.75;
}
.docs-prose .docs-tip strong { color: #81c784; }
```

**`.docs-danger`** (red) — destructive or irreversible actions:
```html
<div class="docs-danger">
    Wiping git history is <strong>irreversible</strong>. All previous commits
    are permanently deleted.
</div>
```

```css
.docs-prose .docs-danger {
    padding: 16px;
    margin: 0 0 20px;
    background: rgba(244, 67, 54, 0.08);
    border: 1px solid rgba(241, 76, 76, 0.25);
    border-radius: var(--nbe-radius-md);
    color: #b0b0b0;
    font-size: 15px;
    line-height: 1.75;
}
.docs-prose .docs-danger strong { color: #e57373; }
```

### 2b. Page Summary Box

A "what this page covers" box at the top of longer pages:

```html
<div class="docs-summary">
    <div class="docs-summary-title">On this page</div>
    <ul>
        <li>How staged changes flow from UI to disk</li>
        <li>The 10-phase apply process</li>
        <li>Conflict detection and undo</li>
    </ul>
</div>
```

```css
.docs-summary {
    margin: 0 0 32px;
    padding: 16px 20px;
    background: var(--nbe-dark-bg-secondary);
    border: 1px solid var(--nbe-dark-border-primary);
    border-left: 3px solid var(--nbe-dark-accent-primary);
    border-radius: var(--nbe-radius-md);
}

.docs-summary-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--nbe-dark-accent-primary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}

.docs-summary ul {
    margin: 0;
    padding-left: 20px;
    font-size: 14px;
    color: #b0b0b0;
    line-height: 1.7;
}
```

### 2c. Collapsible Detail Sections

For optional depth — especially useful on backend-services.html where 8 method tables are dumped linearly:

```html
<details class="docs-details">
    <summary>Mutation Methods (6 methods)</summary>
    <table>...</table>
</details>
```

```css
.docs-prose details.docs-details {
    margin: 0 0 20px;
    border: 1px solid var(--nbe-dark-border-primary);
    border-radius: var(--nbe-radius-md);
    overflow: hidden;
}

.docs-prose details.docs-details summary {
    padding: 12px 16px;
    background: var(--nbe-dark-bg-secondary);
    color: var(--nbe-dark-text-primary);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    user-select: none;
    list-style: none;
}

.docs-prose details.docs-details summary::before {
    content: '▶';
    display: inline-block;
    margin-right: 8px;
    font-size: 10px;
    transition: transform 0.15s;
    color: var(--nbe-dark-text-muted);
}

.docs-prose details.docs-details[open] summary::before {
    transform: rotate(90deg);
}

.docs-prose details.docs-details > :not(summary) {
    padding: 0 16px;
}
```

### 2d. Step Indicators

For quick-start and how-to pages — styled numbered steps (replacing plain `### 1. Do This`):

```html
<div class="docs-step">
    <div class="docs-step-number">1</div>
    <div class="docs-step-content">
        <h4>Load Configuration</h4>
        <p>When the app starts, it reads all <code>.cfg</code> files...</p>
    </div>
</div>
```

```css
.docs-step {
    display: flex;
    gap: 16px;
    margin: 0 0 28px;
    padding: 20px;
    background: var(--nbe-dark-bg-secondary);
    border: 1px solid var(--nbe-dark-border-primary);
    border-radius: var(--nbe-radius-md);
}

.docs-step-number {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--nbe-dark-accent-primary);
    color: var(--nbe-dark-bg-primary);
    font-size: 15px;
    font-weight: 700;
}

.docs-step-content h4 {
    margin: 0 0 8px;
    font-size: 17px;
}

.docs-step-content p:last-child {
    margin-bottom: 0;
}
```

## Part 3: SVG Diagram Strategy

### Keep existing (already implemented)
- `architecture.html` — layered architecture diagram
- `data-flow-staging.html` — edit flow + state machine (2 diagrams)
- `frontend-architecture.html` — module hierarchy + color palette
- `staging-system.html` — staging workflow
- `git-integration.html` — git workflow with discard paths
- `backend-services.html` — service map

### Add new (from original plan, only high-value ones)

| # | Page | What | Why it needs a visual |
|---|------|------|----------------------|
| 1 | `explorer-navigation.html` | Three-pane layout with labeled regions | Text says "left pane, center pane, right pane" — a layout diagram makes this instantly clear |
| 2 | `inheritance-viewer.html` | Template chain A → B → C with attribute flow | Inheritance is inherently visual — "first match wins" is hard to explain in text alone |
| 3 | `configuration.html` | Precedence stack: env vars → config file → defaults | Simple 3-layer stack diagram, small and clear |
| 4 | `bulk-operations.html` | Decision flow for bulk actions | Select → branch to Move/Clone/Delete — shows the multi-path decision |

### Skip (from original plan)
- `dependency-graph.html` — the page already describes a graph visualization; a static SVG of a graph is redundant
- `file-folder-management.html` — tree before/after is better shown as styled HTML than SVG
- `editing-objects.html` — editor layout is better explained by just opening the app
- `analysis-tools.html` — taxonomy diagram adds little over a well-structured list
- `api-reference.html` — 60+ endpoints in a tree SVG would be unreadable
- `validation.html` — simple loop, text is sufficient

## Part 4: Content Improvements

### Cross-linking
Add inline references throughout pages, not just at the end. Example:

> Before: "The staging system tracks ten distinct categories of changes:"
> After: "The [staging system](#app/data-flow-staging) tracks ten distinct categories of changes:"

### Page summaries
Add `.docs-summary` boxes to pages longer than ~150 lines:
- staging-system.html
- data-flow-staging.html
- backend-services.html
- git-integration.html
- frontend-architecture.html
- architecture.html

### Collapsible sections
Apply `<details class="docs-details">` to backend-services.html method tables — keep the overview table expanded, collapse individual service method tables.

### Callout upgrades
- Replace `.docs-warning` with `.docs-danger` where the action is truly irreversible (git wipe, discard)
- Add `.docs-tip` for keyboard shortcuts and pro tips scattered throughout

## Implementation Order

### Phase 1: Typography & Layout (CSS only — no template changes)
1. Add docs-specific typography variables to `docs.css`
2. Update `.docs-prose` heading, body, list, table, code, callout, and spacing styles
3. Fix `--nbe-space-xxl` → use explicit `40px`
4. Reduce max-width from 900px to 800px
5. Verify rendering of all 25 pages (font sizes, spacing, no overflow)

### Phase 2: New CSS Components
1. Add `.docs-tip` and `.docs-danger` callout styles
2. Add `.docs-summary` box styles
3. Add `.docs-details` collapsible section styles
4. Add `.docs-step` step indicator styles
5. Verify these render correctly before applying to templates

### Phase 3: Template Content Updates
1. Add `.docs-summary` boxes to 6 longer pages
2. Convert backend-services.html method tables to collapsible `<details>`
3. Upgrade callouts: `.docs-warning` → `.docs-danger` where appropriate, add `.docs-tip` instances
4. Add inline cross-references throughout user guide pages
5. Convert quick-start.html numbered headings to `.docs-step` cards

### Phase 4: New SVG Diagrams (4 diagrams)
1. `explorer-navigation.html` — three-pane layout
2. `inheritance-viewer.html` — template chain
3. `configuration.html` — precedence stack
4. `bulk-operations.html` — decision flow

## Pages That Don't Need Changes

- `overview.html` — short, well-structured, benefits from typography bump only
- `installation.html` — short setup steps, typography bump only
- `keyboard-shortcuts.html` — reference table, typography bump only
- `search-filtering.html` — clear mechanics, typography bump only
- `audit-log.html` — simple page, typography bump only
- `settings.html` — configuration reference, typography bump only
- `contributing.html` — code style guidelines, typography bump only
- `backups.html` — sequential operations, typography bump only
