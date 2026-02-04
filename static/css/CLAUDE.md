# CLAUDE.md

## Overview

Design tokens, component styles, and page-specific CSS for the Nagios Bulk Editor UI.

## Index

| File                    | Contents (WHAT)                                                                                      | Read When (WHEN)                                                 |
| ----------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `tokens.css`            | Design system tokens (light + dark themes), component variants (.nbe-btn, .nbe-tabs), color palettes | Changing design tokens, adding theme variants, styling components |
| `explorer.css`          | Three-pane explorer layout (tree, editor, workspace), dark theme unified styling                     | Modifying explorer UI, changing pane layouts, fixing dark theme  |
| `style.css`             | Global component styles (cards, tables, buttons), object rows, code highlighting                     | Styling app-wide components, fixing cross-page UI                |
| `git.css`               | Git page: file list, diff viewer, staging preview                                                    | Modifying git page styles, changing diff display                 |
| `backups.css`           | Backup list, restore modal                                                                           | Styling backup page, changing backup UI                          |
| `dependencies.css`      | Graph view: legend, zoom controls, node/edge styles                                                  | Modifying dependency graph visualization                         |
| `audit_log.css`         | Audit log table, filter chips                                                                        | Styling audit log page, changing log display                     |
| `inheritance.css`       | Inheritance tree visualization                                                                       | Modifying inheritance display, styling tree layout               |
| `settings.css`          | Settings page forms and sections                                                                     | Styling settings page, changing config UI                        |
| `objects.css`           | Legacy object browser page                                                                           | Maintaining legacy object browser                                |
| `bulk-rename.css`       | Bulk rename page styling                                                                             | Styling bulk rename UI                                           |
| `bulk-attributes.css`   | Bulk attribute editing page                                                                          | Styling bulk attribute editor                                    |
| `find-replace.css`      | Find/replace page styling                                                                            | Styling search/replace UI                                        |
| `smart-grouping.css`    | Smart grouping suggestions page                                                                      | Styling smart grouping UI                                        |
| `validate.css`          | Validation page styling                                                                              | Styling validation output display                                |
| `health-check.css`      | Health check page styling                                                                            | Styling health check results                                     |
| `forms.css`             | Form component styles                                                                                | Styling forms, input elements                                    |

## Dark Theme System

The dark theme uses a token-based architecture for the explorer page (three-pane layout: tree, editor, workspace).

### Architecture

1. **Token Definition** (tokens.css): `--nbe-dark-*` tokens define all dark theme colors and component variants
2. **Token Consumption** (explorer.css): All explorer panes reference `var(--nbe-dark-*)` tokens
3. **Naming Pattern**: `--nbe-dark-{category}-{variant}` (e.g., `--nbe-dark-bg-primary`, `--nbe-dark-text-secondary`)

### Token Categories

All tokens defined in tokens.css with WCAG AA contrast ratios (4.5:1 for text, 3:1 for UI components):

**Backgrounds:**
- `--nbe-dark-bg-primary` (#1e1e1e) - Main background
- `--nbe-dark-bg-secondary` (#2d2d2d) - Cards, inputs
- `--nbe-dark-bg-tertiary` (#252525) - Alternating rows
- `--nbe-dark-bg-hover` (#2a2a2a) - Hover states
- `--nbe-dark-bg-elevated` (#333) - Focus, active states
- `--nbe-dark-bg-subtle` (#383838) - Collapsible headers

**Text:**
- `--nbe-dark-text-primary` (#d4d4d4) - Main text (11.4:1 contrast)
- `--nbe-dark-text-secondary` (#888) - Secondary text (4.7:1 contrast)
- `--nbe-dark-text-muted` (#666) - Muted text (4.5:1 contrast)

**Borders:**
- `--nbe-dark-border-primary` (#404040) - Primary borders
- `--nbe-dark-border-secondary` (#333) - Subtle dividers
- `--nbe-dark-border-hover` (#505050) - Hover states

**Accents:**
- `--nbe-dark-accent-primary` (#4ec9b0) - Primary accent (teal)
- `--nbe-dark-accent-secondary` (#569cd6) - Secondary accent (blue)
- `--nbe-dark-accent-warning` (#ffc107) - Warning accent (yellow)
- `--nbe-dark-accent-danger` (#f14c4c) - Danger accent (red)
- `--nbe-dark-accent-alpha-{10|15|20|30|60}` - Teal with alpha

**Inputs:**
- `--nbe-dark-input-bg` - Input background
- `--nbe-dark-input-border` - Input border
- `--nbe-dark-input-border-hover` - Input border hover
- `--nbe-dark-input-focus` - Input focus border (teal)
- `--nbe-dark-input-focus-bg` - Input focus background

**Buttons** (used by `.nbe-btn--dark` variants):
- `--nbe-dark-btn-bg` / `--nbe-dark-btn-bg-hover` - Default button
- `--nbe-dark-btn-text` / `--nbe-dark-btn-border` - Default text/border
- `--nbe-dark-btn-primary-bg` / `--nbe-dark-btn-primary-hover` - Primary button
- `--nbe-dark-btn-danger-bg` / `--nbe-dark-btn-danger-hover` - Danger button

**Tabs** (used by `.nbe-tabs--dark`, `.nbe-tab--dark`):
- `--nbe-dark-tab-bg` / `--nbe-dark-tab-bg-hover` / `--nbe-dark-tab-active-bg`
- `--nbe-dark-tab-text` / `--nbe-dark-tab-text-hover` / `--nbe-dark-tab-text-active`
- `--nbe-dark-tab-border-active` (teal)

**Validation/Status** (commit dialog, staged items):
- `--nbe-dark-validation-success-{bg|badge}` - Success/new items (green, 0.1/0.2 alpha)
- `--nbe-dark-validation-error-{bg|badge}` - Errors/deletions (red, 0.1/0.2 alpha)
- `--nbe-dark-validation-warning-{bg|badge}` - Warnings/moves (yellow, 0.1/0.2 alpha)
- `--nbe-dark-validation-info-{bg|badge}` - Info state (blue, 0.1/0.2 alpha)

### Component Variants

Defined in tokens.css for use with dark theme:

- `.nbe-btn--dark` + modifiers (`.nbe-btn--primary`, `.nbe-btn--danger`, `.nbe-btn--ghost`)
- `.nbe-tabs--dark` for tab containers
- `.nbe-tab--dark` for individual tabs with hover/active states
- `.nbe-input--dark` for text inputs with focus styling

### Semantic Colors Preserved

The following tokens are NOT converted to dark variants because they have sufficient contrast on dark backgrounds:
- `--nbe-success`, `--nbe-danger`, `--nbe-warning`, `--nbe-primary` (WCAG AA compliant)

### Utility Tokens Preserved

The following tokens are theme-agnostic and shared across light/dark themes:
- Spacing: `--nbe-space-{xs|sm|md|lg|xl|2xl}`
- Border radius: `--nbe-radius-{xs|sm|md|lg|xl|2xl|pill}`
- Typography: `--nbe-font-{sans|mono|size-*}`
- Shadows: `--nbe-shadow-{xs|sm|md|lg|overlay}`
- Z-index: `--nbe-z-{dropdown|sticky|overlay|modal|toast|tooltip}`

### Migration Status

**Complete:** Explorer page (three-pane layout) uses dark theme tokens throughout:
- Left pane (tree): All tree elements, filters, folder/file icons
- Center pane (editor): Object attributes, tabs, validation info, staging badges
- Right pane (workspace): File tree, move targets, drag-drop indicators
- Commit dialog: File-based changes view, reference analysis, context slider
- Shared elements: Toasts, modals, lock banner

**Pattern:** All light tokens (`--nbe-bg-*`, `--nbe-text-*`, `--nbe-border-*`) converted to `--nbe-dark-*` equivalents.

## Button System

All buttons use `.nbe-btn` base class with modifiers. Defined in `tokens.css` lines 648-960.

### Base Usage

```html
<button class="nbe-btn">Default</button>
<button class="nbe-btn nbe-btn--primary">Primary</button>
<button class="nbe-btn nbe-btn--danger">Danger</button>
```

### Variants

| Class | Use Case | Background |
|-------|----------|------------|
| `.nbe-btn` | Default/neutral actions | Light gray |
| `.nbe-btn--primary` | Primary actions (save, apply) | `--nbe-primary` blue |
| `.nbe-btn--secondary` | Secondary actions | White with border |
| `.nbe-btn--danger` | Destructive actions (delete) | `--nbe-danger` red |
| `.nbe-btn--info` | Informational actions | `--nbe-info` blue |
| `.nbe-btn--ghost` | Minimal/inline actions | Transparent |

### Sizes

| Class | Padding | Font Size | Use Case |
|-------|---------|-----------|----------|
| `.nbe-btn--xs` | 2px 6px | 11px | Compact UI, table actions |
| `.nbe-btn--sm` | 4px 10px | 12px | Secondary actions, toolbars |
| (default) | 6px 14px | 13px | Standard buttons |
| `.nbe-btn--lg` | 10px 20px | 15px | Primary page actions |

### Modifiers

| Class | Effect |
|-------|--------|
| `.nbe-btn--icon` | Square button for icons only (equal padding) |
| `.nbe-btn--full` | Full width (`width: 100%`) |
| `.nbe-btn-group` | Horizontal button group (removes gaps) |
| `.nbe-btn-group--vertical` | Vertical button group |

### States

```html
<!-- Disabled -->
<button class="nbe-btn" disabled>Disabled</button>

<!-- Loading (add via JS) -->
<button class="nbe-btn nbe-btn--primary" data-loading="true">Saving...</button>
```

Loading state adds spinner via `::after` pseudo-element.

### Dark Theme

Add `.nbe-btn--dark` for dark backgrounds (explorer page):

```html
<button class="nbe-btn nbe-btn--dark nbe-btn--primary">Dark Primary</button>
```

Dark variants: `.nbe-btn--dark`, `.nbe-btn--dark.nbe-btn--primary`, `.nbe-btn--dark.nbe-btn--danger`, `.nbe-btn--dark.nbe-btn--ghost`

## Typography Token System

Semantic typography tokens provide consistent type scaling and hierarchy across the application. All font-size values MUST use tokens (no hardcoded px or rem values).

### Semantic Typography Token Groups

Composite tokens combining size, weight, and line-height for common text roles:

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

**Usage pattern:**
```css
.dialog-title {
    font-size: var(--nbe-typography-h1-size);
    font-weight: var(--nbe-typography-h1-weight);
    line-height: var(--nbe-typography-h1-line-height);
}
```

### Font Size Scale

Individual size tokens for precise control (use semantic tokens above when possible):

| Token | Value | Use Case |
|-------|-------|----------|
| `--nbe-font-size-3xs` | 8px | Font Awesome icons |
| `--nbe-font-size-2xs` | 9px | Micro text, compact badges |
| `--nbe-font-size-xs` | 10px | Muted text (use `--nbe-typography-muted-*` semantically) |
| `--nbe-font-size-xs-plus` | 11px | Intermediate size |
| `--nbe-font-size-sm` | 12px | Small text (use `--nbe-typography-label-*` semantically) |
| `--nbe-font-size-base` | 13px | Body text (use `--nbe-typography-body-*` semantically) |
| `--nbe-font-size-md` | 14px | Subsection headings (use `--nbe-typography-h3-*` semantically) |
| `--nbe-font-size-lg` | 16px | Section headings (use `--nbe-typography-h2-*` semantically) |
| `--nbe-font-size-xl` | 18px | Large text |
| `--nbe-font-size-2xl` | 20px | Page titles (use `--nbe-typography-h1-*` semantically) |

**Icon sizes** (decorative elements, empty states):
- `--nbe-font-size-icon-sm` (24px)
- `--nbe-font-size-icon-md` (32px)
- `--nbe-font-size-icon-lg` (48px)
- `--nbe-font-size-icon-xl` (64px)

### Line Height Scale

| Token | Value | Use Case |
|-------|-------|----------|
| `--nbe-line-height-tight` | 1.2 | Headings, compact text |
| `--nbe-line-height-normal` | 1.5 | Body text, labels |
| `--nbe-line-height-relaxed` | 1.6 | Code blocks |
| `--nbe-line-height-loose` | 1.8 | Long-form content |

### Letter Spacing Scale

| Token | Value | Use Case |
|-------|-------|----------|
| `--nbe-letter-spacing-tight` | -0.02em | Headings |
| `--nbe-letter-spacing-normal` | 0 | Body text |
| `--nbe-letter-spacing-wide` | 0.02em | Uppercase labels |

### Bundled Fonts

Application uses bundled web fonts for cross-platform consistency:

- **UI Font**: Inter (static/vendor/fonts/Inter-*.woff2) - system fallback to -apple-system, BlinkMacSystemFont, "Segoe UI", etc.
- **Code Font**: JetBrains Mono (static/vendor/fonts/JetBrainsMono-*.woff2) - system fallback to "SFMono-Regular", Consolas, "Liberation Mono", etc.

Font stack tokens:
- `--nbe-font-sans`: Inter with system fallbacks
- `--nbe-font-mono`: JetBrains Mono with system fallbacks
