# CSS

Design tokens in `tokens.css`, component styles, and page-specific CSS.

## Files

| File | Contents |
|------|----------|
| `tokens.css` | Material Design tokens (light + dark), `.nbe-btn` system, `.nbe-tabs`, typography scale |
| `dark-page.css` | Shared Bootstrap dark overrides, activated by `.nbe-dark-page` body class |
| `explorer.css` | Three-pane explorer layout, dark theme styling |
| `forms.css` | Shared form styles (form-section, form-group) |
| `git.css` | Git page: file list, diff viewer |
| `backups.css` | Backup list, restore modal |
| `dependencies.css` | Graph view: legend, zoom, node/edge styles |
| `logs.css` | Logs page: table, filter chips, badges |
| `inheritance.css` | Inheritance tree visualization |
| `settings.css` | Settings page forms |
| `bulk-rename.css` | Bulk rename page |
| `validate.css` | Validation output display |
| `docs.css` | Docs page: prose, callouts, directive table |

## Color System

All colors are **Material Design** based. Tokens defined in `tokens.css`, no hardcoded colors in page CSS files.

## Dark Theme

Token-based. Dark pages use `{% block body_class %} nbe-dark-page{% endblock %}` in their template to activate shared overrides in `dark-page.css`. Page-specific dark rules remain in each page's CSS file.

**Load order**: Bootstrap → FontAwesome → `tokens.css` → `forms.css` → `dark-page.css` → `style.css` → page CSS

**Naming**: `--nbe-dark-{category}-{variant}` — categories: `bg`, `text`, `border`, `accent`, `input`, `btn`, `tab`, `validation`, `prose`.

**Dark pages**: Explorer, Git, Backups, Logs, Settings, Validate, Dependencies, Docs

## Button System

Base class `.nbe-btn` with modifiers. All defined in `tokens.css`.

**Emphasis (MD3 hierarchy, high → low)**: `--filled`, `--tonal`, `--outlined`, `--text`
**Color role**: `--danger` (destructive actions, any emphasis level)
**Sizes**: `--xs`, `--sm`, (default), `--lg`
**Modifiers**: `--icon` (square), `--full` (width:100%), `.nbe-btn-group`
**Dark theme**: Add `--dark` (e.g. `.nbe-btn--dark.nbe-btn--filled`)
**Loading state**: Set `data-loading="true"` in JS

## Spacing Tokens

`2xs`=2px · `xs`=4px · `xs-plus`=6px · `sm`=8px · `sm-plus`=10px · `md`=12px · `lg`=16px · `lg-plus`=20px · `xl`=24px · `2xl`=32px

## Typography Tokens

Semantic groups in `tokens.css`, each with `-size`, `-weight`, `-line-height` variants:

`h1` (20px) · `h2` (16px) · `h3` (14px) · `label` (12px/600) · `body` (13px) · `secondary` (12px) · `muted` (10px) · `code` (12px/mono) · `badge` (10px/600) · `button` (13px) · `button-sm` (12px) · `input` (13px)

**Fonts**: Inter (`--nbe-font-sans`), JetBrains Mono (`--nbe-font-mono`) — both bundled as woff2.
