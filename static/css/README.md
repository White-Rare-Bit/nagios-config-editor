# CSS Architecture — Design Decisions

See `CLAUDE.md` in this directory for the file index, token naming, and button/typography reference.

## Dark Theme: Why Tokens

Center pane had 90+ hard-coded colors. Direct replacement would perpetuate debt with no reusability. Token system (`--nbe-dark-*`) creates single source of truth and enables future theme toggle.

## Why Separate `--nbe-dark-*` Namespace

Existing `--nbe-*` tokens designed for light theme. Overwriting them would break other pages (git, backups, settings). Separate namespace preserves light theme for non-explorer pages.

## Why CSS-Only Migration

HTML changes risk breaking drag-drop, collapsible sections, and other interactive features. CSS-only approach uses specific selectors targeting existing structure.

## Why Component `--dark` Modifiers

`.nbe-btn--dark` and `.nbe-tabs--dark` extend existing components rather than creating new classes. Follows existing BEM-like pattern and creates reusable variants for future dark contexts.

## Typography: Why Semantic Tokens

Standard UI elements need font-size + weight + line-height together. Semantic tokens (`--nbe-typography-h1-*`) provide single source of truth per role. Individual size tokens (`--nbe-font-size-*`) available for edge cases.

## Typography: Why Individual Properties Over Shorthand

Individual properties (font-size, font-weight, line-height) enable flexible consumption. Components can use all three or cherry-pick. Shorthand would force consumers to override unwanted properties.

## Why Bundled Fonts

System fonts vary across platforms. Bundled Inter + JetBrains Mono (woff2) ensure identical rendering. System fallbacks retained for graceful degradation.
