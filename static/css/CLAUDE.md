# CSS

Design tokens in `tokens.css`, component styles, and page-specific CSS.

## Files

| File | Contents |
|------|----------|
| `tokens.css` | Design tokens (light + dark), `.nbe-btn` system, `.nbe-tabs`, typography scale |
| `explorer.css` | Three-pane explorer layout, dark theme styling |
| `forms.css` | Shared form styles (form-section, form-group) |
| `git.css` | Git page: file list, diff viewer |
| `backups.css` | Backup list, restore modal |
| `dependencies.css` | Graph view: legend, zoom, node/edge styles |
| `audit_log.css` | Audit log table, filter chips |
| `inheritance.css` | Inheritance tree visualization |
| `settings.css` | Settings page forms |
| `bulk-rename.css` | Bulk rename page |
| `validate.css` | Validation output display |

## Dark Theme

Token-based, explorer page only. All tokens in `tokens.css`, consumed in `explorer.css`.

**Naming**: `--nbe-dark-{category}-{variant}` — categories: `bg`, `text`, `border`, `accent`, `input`, `btn`, `tab`, `validation`.

**Semantic colors** (`--nbe-success`, `--nbe-danger`, etc.) are NOT dark-converted — they already have sufficient contrast.

## Button System

Base class `.nbe-btn` with modifiers. All defined in `tokens.css`.

**Variants**: `--primary`, `--secondary`, `--danger`, `--info`, `--ghost`
**Sizes**: `--xs`, `--sm`, (default), `--lg`
**Modifiers**: `--icon` (square), `--full` (width:100%), `.nbe-btn-group`
**Dark theme**: Add `--dark` (e.g. `.nbe-btn--dark.nbe-btn--primary`)
**Loading state**: Set `data-loading="true"` in JS

## Typography Tokens

Semantic groups in `tokens.css`, each with `-size`, `-weight`, `-line-height` variants:

`h1` (20px) · `h2` (16px) · `h3` (14px) · `label` (12px/600) · `body` (13px) · `secondary` (12px) · `muted` (10px) · `code` (12px/mono) · `badge` (10px/600) · `button` (13px) · `button-sm` (12px) · `input` (13px)

**Fonts**: Inter (`--nbe-font-sans`), JetBrains Mono (`--nbe-font-mono`) — both bundled as woff2.
