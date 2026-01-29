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

## Typography System

The application uses a semantic typography token system to provide consistent type scaling and hierarchy. All font-size values must use tokens (zero hardcoded px or rem values allowed except in token definitions).

### Architecture

```
tokens.css (Typography Tokens)
    |
    +-- Individual Property Tokens
    |   (--nbe-font-size-*, --nbe-font-weight-*, --nbe-line-height-*)
    |
    +-- Semantic Typography Tokens
        (--nbe-typography-{role}-{property})
            |
            v
    All CSS Files (Token Consumers)
        |
        +-- Standard Elements: Use semantic tokens
        |   (headings, labels, buttons, body text)
        |
        +-- Edge Cases: Use individual size tokens
            (single property changes without weight/line-height)
```

**Data Flow:**
1. `tokens.css` defines individual property tokens (size, weight, line-height)
2. `tokens.css` defines semantic tokens combining all three properties for common roles
3. CSS files consume via `var(--nbe-typography-{role}-*)` for standard elements
4. CSS files use `var(--nbe-font-size-*)` for edge cases (icon sizes, single-property adjustments)

### Design Decisions

#### Semantic Typography Tokens Over Direct Size Values

**Decision:** Create composite tokens grouping font-size, font-weight, and line-height under semantic role names (h1, h2, body, label, etc.).

**Rationale:** Standard UI elements (headings, labels, buttons) require all three properties to define complete typographic style. Semantic tokens provide single source of truth for each role, ensuring consistency across the application. Individual size tokens still available for edge cases where only font-size changes without affecting weight/line-height.

#### Individual Properties Over CSS Shorthand

**Decision:** Define semantic tokens as separate properties (font-size, font-weight, line-height) rather than CSS shorthand (font: 600 16px/1.2 var(--nbe-font-sans)).

**Rationale:** Individual properties enable flexible consumption patterns. Components can use all three properties for complete styling or cherry-pick individual properties when needed. Shorthand would force consumers to override unwanted properties. Individual properties are more explicit and self-documenting.

#### Bundled Web Fonts Over System Fonts

**Decision:** Bundle Inter and JetBrains Mono as woff2 files served from static/vendor/fonts/, with system font fallbacks.

**Rationale:** System fonts vary dramatically across platforms (San Francisco on macOS, Segoe UI on Windows, Ubuntu on Linux). Bundled fonts ensure identical rendering and spacing across all operating systems, preventing layout shifts or readability issues. WOFF2 format provides optimal compression (smaller than TTF/OTF). System fallbacks retained for graceful degradation if font fails to load.

#### Icon Size Namespace Separation

**Decision:** Create separate `--nbe-font-size-icon-*` tokens (24px, 32px, 48px, 64px) outside main typography scale.

**Rationale:** Icon sizes serve decorative/visual purposes rather than text hierarchy. They scale in larger increments (24px jumps) compared to text scale (1-2px increments). Separate namespace prevents confusion between text sizing and icon sizing, making token purpose explicit.

### Token Architecture

**Semantic Token Pattern:**
```css
/* Composite token for complete role definition */
--nbe-typography-h1-size: var(--nbe-font-size-2xl);
--nbe-typography-h1-weight: var(--nbe-font-weight-semibold);
--nbe-typography-h1-line-height: var(--nbe-line-height-tight);

/* Usage: Apply all three properties */
.dialog-title {
    font-size: var(--nbe-typography-h1-size);
    font-weight: var(--nbe-typography-h1-weight);
    line-height: var(--nbe-typography-h1-line-height);
}
```

**When to use semantic tokens:**
- Standard UI elements with all three properties defined (headings, labels, body text, buttons)
- Ensures consistency across similar elements (all H2 headings share same size/weight/line-height)
- Single source of truth for each role's complete typographic style

**When to use individual size tokens:**
- Single-property adjustments (only changing font-size without affecting weight/line-height)
- Icon sizing (use `--nbe-font-size-icon-*` namespace)
- Edge cases requiring precise control (compact tree nodes, inline badges)

### Typography Token Index

Full list of semantic token groups defined in tokens.css (lines 130-177):

| Token Group | Size | Weight | Line Height | Use Case |
|-------------|------|--------|-------------|----------|
| `--nbe-typography-h1-*` | 20px | 600 | 1.2 (tight) | Page titles, dialog headings |
| `--nbe-typography-h2-*` | 16px | 600 | 1.2 (tight) | Section headings |
| `--nbe-typography-h3-*` | 14px | 600 | 1.5 (normal) | Subsection headings |
| `--nbe-typography-label-*` | 12px | 600 | 1.5 (normal) | Form labels, tree labels |
| `--nbe-typography-body-*` | 13px | 400 | 1.5 (normal) | Body text, paragraphs |
| `--nbe-typography-secondary-*` | 12px | 400 | 1.5 (normal) | Secondary text, captions |
| `--nbe-typography-muted-*` | 10px | 400 | 1.5 (normal) | Muted text, placeholders |
| `--nbe-typography-code-*` | 12px | 400 | 1.6 (relaxed) | Code blocks, monospace |
| `--nbe-typography-badge-*` | 10px | 600 | 1.2 (tight) | Badges, status indicators |
| `--nbe-typography-button-*` | 13px | 500 | 1 | Standard buttons |
| `--nbe-typography-button-sm-*` | 12px | 500 | 1 | Small buttons |
| `--nbe-typography-input-*` | 13px | 400 | 1.5 (normal) | Form inputs, textareas |

**Bundled Fonts:**
- UI Font: Inter (static/vendor/fonts/Inter-*.woff2) with system fallbacks
- Code Font: JetBrains Mono (static/vendor/fonts/JetBrainsMono-*.woff2) with monospace fallbacks

### Invariants

1. **Zero Hardcoded Sizes:** All font-size values MUST use tokens. Hard-coded px or rem values are forbidden (except in token definitions in tokens.css). This ensures single source of truth and enables global adjustments.

2. **Semantic Token Priority:** Standard UI elements (headings, labels, body text, buttons) MUST use semantic tokens (`--nbe-typography-*`) setting all three properties. Individual size tokens are for edge cases only.

3. **Individual Property Pattern:** Semantic tokens MUST use individual property syntax (font-size, font-weight, line-height) rather than CSS shorthand. This enables flexible consumption and explicit self-documentation.

4. **Icon Size Namespace:** Icon sizing MUST use `--nbe-font-size-icon-*` tokens, not typography scale tokens. This maintains semantic separation between text hierarchy and decorative sizing.

5. **Cross-Platform Consistency:** Bundled web fonts (Inter, JetBrains Mono) MUST load before system fallbacks. This ensures identical rendering across macOS, Windows, and Linux.

### Tradeoffs

#### Semantic Tokens Over Hardcoded Values

**Cost:** Higher initial implementation effort. Required creating comprehensive semantic token set and migrating all existing font-size declarations.

**Benefit:** Single source of truth enables global adjustments. Changing one semantic token updates all consumers. Consistent hierarchy across application (all H2 headings share same styling). Maintenance cost drops dramatically.

#### Individual Properties Over CSS Shorthand

**Cost:** More verbose CSS (three property declarations instead of one shorthand). Slightly larger file size.

**Benefit:** Flexible consumption patterns. Components can use all three properties or cherry-pick. More explicit and self-documenting. Easier to override individual properties without affecting others.

#### Bundled Fonts Over System Fonts

**Cost:** Additional HTTP requests (4 woff2 files, ~200KB total). Slight delay before fonts load (FOUT/FOIT risk).

**Benefit:** Identical rendering across all platforms. No layout shifts from font metric differences. Consistent spacing and readability. Professional appearance with modern typefaces. System fallbacks provide graceful degradation.
