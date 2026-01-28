# CSS Architecture

## Overview

This directory implements a token-based design system with unified dark theme for the explorer UI. The system was migrated from 90+ hard-coded colors to a centralized token approach to eliminate technical debt and enable future theme flexibility. All explorer panes (tree, editor, workspace) now share a consistent dark theme derived from VS Code Dark+ palette.

## Architecture

```
tokens.css (Design Tokens)
    |
    +-- Light Theme Tokens (existing --nbe-*)
    |
    +-- Dark Theme Tokens (new --nbe-dark-*)
            |
            v
explorer.css (Component Styles)
    |
    +-- Left Pane (.tree-panel)
    |       Uses: --nbe-dark-bg-*, --nbe-dark-text-*
    |
    +-- Center Pane (.center-pane)
    |       Uses: --nbe-dark-bg-*, --nbe-dark-text-*
    |       Migrated: hard-coded #1e1e1e -> tokens
    |
    +-- Right Pane (.workspace-pane)
            Uses: --nbe-dark-bg-*, --nbe-dark-text-*
```

**Data Flow:**
1. `tokens.css` defines token values
2. `explorer.css` consumes via `var(--nbe-dark-*)`
3. Browser renders unified dark theme

## Design Decisions

### Token-First Migration Over Direct Replacement

**Decision:** Create comprehensive `--nbe-dark-*` token system before applying dark theme.

**Rationale:** Center pane had 90+ hard-coded colors. Direct color replacement would perpetuate technical debt with no reusability. Token system creates single source of truth, enabling future theme toggle capability. Higher initial effort but dramatically lower maintenance cost.

### Separate Dark Theme Namespace

**Decision:** Create new `--nbe-dark-*` tokens instead of reusing existing `--nbe-*` tokens.

**Rationale:** Existing tokens designed for light theme. Overwriting them would break other pages (git, backups, settings) that use light theme. Separate namespace preserves light theme for non-explorer pages and allows future theme switching per page.

### Migrate Center Pane During Unification

**Decision:** Replace center pane's hard-coded colors with tokens during dark theme rollout.

**Rationale:** Center pane already had correct visual style but used hard-coded values. Migrating now ensures all three panes share same token source, preventing drift between panes. Reference implementation becomes token-based.

### CSS-Only Migration

**Decision:** Achieve dark theme through CSS changes only, minimal HTML template modifications.

**Rationale:** HTML changes are more invasive and risk breaking functionality. CSS-only approach uses specific selectors targeting existing structure, reducing risk. Adding panel-level classes enables CSS cascade without extensive template refactoring.

### Component Variant Extensions

**Decision:** Extend `.nbe-btn` and `.nbe-tabs` with `--dark` modifiers instead of creating new component classes.

**Rationale:** These components already defined in tokens.css with light styling. Adding `--dark` modifiers follows existing BEM-like pattern, maintains consistency, and creates reusable components for future dark contexts beyond explorer.

## Invariants

1. **Token Usage:** All dark theme colors MUST come from `--nbe-dark-*` tokens. Hard-coded hex values are forbidden in dark theme contexts. This ensures single source of truth and enables global adjustments.

2. **Token Naming Convention:** All dark tokens follow pattern `--nbe-dark-{category}-{variant}` (e.g., `--nbe-dark-bg-primary`, `--nbe-dark-text-secondary`). This maintains discoverability and prevents naming conflicts.

3. **Accessibility:** WCAG AA contrast ratios MUST be maintained: 4.5:1 minimum for text, 3:1 minimum for UI components. Token values derived from center pane already meet these ratios.

4. **Visual Reference:** Center pane's original visual appearance is the reference implementation. Other panes must match its terminal-inspired aesthetic. This ensures visual consistency across all three panes.

5. **Namespace Separation:** Light theme tokens (`--nbe-*`) and dark theme tokens (`--nbe-dark-*`) remain separate. This preserves light theme for pages outside explorer and enables future per-page theme selection.

## Tradeoffs

### Tokens Over Hard-Coded Values

**Cost:** Higher initial implementation effort. Required creating comprehensive token set and systematic migration of all selectors.

**Benefit:** Single source of truth enables global adjustments. Changing one token value updates all consumers. Future theme toggle becomes CSS variable swap instead of massive find-replace. Maintenance cost drops dramatically.

### CSS-Only Over HTML Refactor

**Cost:** Requires more specific CSS selectors. Some duplication in selector specificity to override existing rules.

**Benefit:** Less invasive than HTML changes. Reduces risk of breaking drag-drop, collapsible sections, or other interactive features. Preserves existing functionality while achieving visual goal.

### Full Cleanup Over Partial Migration

**Cost:** More work upfront. Required auditing all 3000+ lines of explorer.css to eliminate every hard-coded color.

**Benefit:** Eliminates all technical debt in one pass. No future confusion about which selectors use tokens vs hard-coded values. Clean foundation for future theme work.

## Token Categories

- **Backgrounds:** `--nbe-dark-bg-{primary|secondary|tertiary|hover|elevated|subtle}`
- **Text:** `--nbe-dark-text-{primary|secondary|muted}`
- **Borders:** `--nbe-dark-border-{primary|secondary|hover}`
- **Accents:** `--nbe-dark-accent-{primary|secondary|warning|danger}`
- **Inputs:** `--nbe-dark-input-{bg|border|border-hover|focus|focus-bg}`
- **Buttons:** `--nbe-dark-btn-*` (used by `.nbe-btn--dark` component variants)
- **Tabs:** `--nbe-dark-tab-*` (used by `.nbe-tabs--dark`, `.nbe-tab--dark` component variants)
- **Alpha Overlays:** `--nbe-dark-accent-alpha-{10|15|20}` (for hover states with transparency)

## Component Variants

Component variants extend base `.nbe-btn` and `.nbe-tabs` classes with dark theme modifiers:

**Buttons:**
- `.nbe-btn--dark` - Base dark button
- `.nbe-btn--dark.nbe-btn--primary` - Primary action (teal accent)
- `.nbe-btn--dark.nbe-btn--danger` - Destructive action (red)
- `.nbe-btn--dark.nbe-btn--ghost` - Transparent button with light text

**Tabs:**
- `.nbe-tabs--dark` - Dark tab container
- `.nbe-tab--dark` - Individual dark tab with hover/active states

Usage: Apply modifier classes to existing components consuming dark theme (currently explorer.css only).
