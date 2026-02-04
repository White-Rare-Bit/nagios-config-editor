# Templates Documentation

Flask Jinja2 templates for Nagios Bulk Editor frontend. All pages extend `base.html` for consistent layout and global components.

## Template Hierarchy

```
base.html (master template - 2496 lines)
  ├─ explorer.html (Object Explorer - 3-pane layout)
  ├─ dependencies.html (Graph View - Cytoscape.js)
  ├─ audit_log.html (Audit log viewer)
  ├─ backups.html (Backup management)
  ├─ git.html (Git operations)
  ├─ settings.html (Config + identity)
  ├─ find_replace.html (Bulk find/replace)
  ├─ bulk_rename.html (Bulk rename)
  ├─ bulk_attributes.html (Bulk attribute editor)
  ├─ reorganize.html (File reorganization)
  ├─ smart_grouping.html (Smart grouping suggestions)
  ├─ inheritance.html (Template inheritance analysis)
  ├─ validate.html (Nagios -v validation)
  ├─ health_check.html (Config health check)
  └─ objects.html (Simple object browser - deprecated)
```

## base.html Blocks

Extend `base.html` and override these blocks:

| Block | Purpose | Required |
|-------|---------|----------|
| `title` | Page `<title>` tag | No (defaults to "Nagios Bulk Editor") |
| `extra_css` | Page-specific CSS files | No |
| `content` | Main page content | Yes |
| `scripts` | Page-specific JS files | No |

### Example Template Pattern

```jinja2
{% extends "base.html" %}

{% block title %}Page Name - Nagios Bulk Editor{% endblock %}

{% block extra_css %}
<link href="{{ url_for('static', filename='css/page.css') }}" rel="stylesheet">
{% endblock %}

{% block content %}
<div class="page-container">
    <!-- Page content here -->
</div>
{% endblock %}

{% block scripts %}
<script src="{{ url_for('static', filename='js/page.js') }}"></script>
{% endblock %}
```

## CSS Load Order

Defined in `base.html` `<head>`:

1. **Bootstrap CSS** (`vendor/css/bootstrap.min.css`)
2. **FontAwesome** (`vendor/css/fontawesome.min.css`)
3. **Design Tokens** (`css/tokens.css`) - CSS variables (`--nbe-*`)
4. **Form Styles** (`css/forms.css`) - Shared form components
5. **Global Styles** (`style.css`) - Minimal global overrides
6. **Page Styles** (via `{% block extra_css %}`)

Use design tokens from `tokens.css` instead of hard-coded colors/spacing:

```css
/* Good */
background: var(--nbe-primary);
padding: var(--nbe-space-md);

/* Avoid */
background: #006fcc;
padding: 12px;
```

## JavaScript Load Order

Defined in `base.html` before `</body>`:

1. **Bootstrap JS** (`vendor/js/bootstrap.bundle.min.js`)
2. **Global Utils** (`app.js`) - escapeHtml, formatDate, debounce, keyboard shortcuts
3. **API Client** (`js/api-client.js`) - Fetch wrapper with staging headers
4. **Base Module** (`js/base.js`) - Session, lock management, commit dialog, toasts
5. **Page Scripts** (via `{% block scripts %}`)

Page scripts can rely on `app.js`, `api-client.js`, and `base.js` globals being loaded.

## Global Components in base.html

### Navbar (lines 15-65)

- Links to all pages
- **Undo button** (`#navUndoBtn`) - Ctrl+Z, disabled by default
- **Commit button** (`#navCommitBtn`) - Stages → disk, disabled when no changes
- **Settings** link
- **Keyboard shortcuts** button (?)
- **Reload config** button

Active page highlighted via `{% if request.endpoint == 'pages.explorer' %}active{% endif %}`.

### Lock Banner (lines 68-72)

`#lockBanner` - Shown when another user has staging lock. Managed by `base.js`.

### Flash Messages (lines 75-84)

Flask's `get_flashed_messages()` renders Bootstrap alerts. Categories: `success`, `danger`, `warning`, `info`.

### Toast Container (line 90)

`#toastContainer` - Managed by `showToast()` in `base.js`. Use for transient notifications:

```javascript
showToast('Operation complete', 'success');
showToast('Validation failed', 'danger');
```

### Global Dialogs

| Dialog | ID | Purpose |
|--------|-----|---------|
| Commit Dialog | `#globalCommitOverlay` | Shows staged changes, confirmation before apply |
| Confirm Dialog | `#confirmDialogOverlay` | Generic yes/no confirmation via `showConfirmDialog()` |
| Git Result Panel | `#gitResultOverlay` | Terminal-style git command output |
| Identity Dialog | `#identityRequiredOverlay` | Blocks usage until user sets name/email |
| Keyboard Shortcuts | `#keyboardShortcutsOverlay` | Help dialog (press `?`) |

All dialogs use overlay pattern: `.{name}-overlay` contains `.{name}-dialog`.

## Event Delegation Pattern

`base.js` uses `data-action` attributes for click handlers:

```html
<button data-action="reload-config">Reload</button>
<button data-action="commit">Commit</button>
```

Handlers in `actionHandlers` map (base.js ~line 800):

```javascript
const actionHandlers = {
    'reload-config': handleReloadConfig,
    'commit': handleCommit,
    // ...
};
```

Add new actions by:
1. Adding `data-action="my-action"` to button
2. Implementing handler in page JS
3. Registering in `actionHandlers`

## Page Layout Patterns

### 2-Pane Layout (sidebar + main)

Used by: `git.html`, `settings.html`, `objects.html`, `backups.html`, `audit_log.html`

```html
<div class="page-container">
    <div class="page-sidebar">
        <div class="panel-header">
            <span class="panel-header-title">Sidebar Title</span>
        </div>
        <!-- Sidebar content -->
    </div>
    <div class="page-main">
        <!-- Main content -->
    </div>
</div>
```

### 3-Pane Layout (tree + center + target)

Used by: `explorer.html` only

```html
<div class="explorer">
    <div class="tree-panel"><!-- Left: Object tree --></div>
    <div class="center-panel"><!-- Center: Object editor --></div>
    <div class="right-panel"><!-- Right: File operations --></div>
</div>
```

### Single-Pane Layout

Used by: `find_replace.html`, `bulk_rename.html`, `bulk_attributes.html`, `validate.html`

```html
<div class="container-fluid">
    <!-- Direct content, no sidebar -->
</div>
```

## Common Template Patterns

### Section Headers

```html
<div class="panel-header">
    <span class="panel-header-title">Section Title</span>
</div>
```

### Info Text

```html
<p class="sidebar-info-text">Informational text here</p>
```

### Loading State

```html
<div class="settings-empty">Loading...</div>
```

### Breadcrumb Display

```javascript
// Built dynamically in JS, not template
buildBreadcrumb(filePath); // Returns HTML string
```

## Integration with Static JS

| Template | CSS | JS Module | Purpose |
|----------|-----|-----------|---------|
| explorer.html | explorer.css | js/explorer/*.js (9 modules) | Main object editor |
| dependencies.html | dependencies.css | js/dependencies.js | Graph visualization |
| git.html | git.css | js/git.js | Git operations |
| backups.html | backups.css | js/backups.js | Backup management |
| settings.html | settings.css | js/settings.js | Settings management |
| audit_log.html | audit_log.css | js/audit-log.js | Audit log viewer |
| find_replace.html | find-replace.css | js/find-replace.js | Find/replace operations |
| bulk_rename.html | bulk-rename.css | js/bulk-rename.js | Bulk rename |
| bulk_attributes.html | bulk-attributes.css | js/bulk-attributes.js | Bulk attribute editor |
| validate.html | validate.css | js/validate.js | Validation interface |
| health_check.html | health-check.css | js/health-check.js | Health checks |
| inheritance.html | inheritance.css | js/inheritance.js | Template inheritance |
| reorganize.html | (none) | js/reorganize.js | Reorganization |
| smart_grouping.html | smart-grouping.css | js/smart-grouping.js | Smart grouping |

Explorer uses modular JS in `static/js/explorer/`:
- `main.js` - Namespace, shared state
- `app.js` - Tree rendering, filtering, selection
- `object-editor.js` - Center pane editor
- `file-operations.js` - Target pane file tree
- `context-menu.js` - Right-click menus
- `dialogs.js` - Move/create/delete dialogs
- `data-loading.js` - Data fetching
- `state-management.js` - State persistence
- `drag-drop.js` - Drag-and-drop

## Inline Styles in base.html

Lines 253-2487 contain critical UI styles inline to prevent FOUC (Flash of Unstyled Content). Includes:
- Dialog overlays and modals
- Toast notifications
- Commit button states
- Lock banner
- Keyboard shortcuts modal

**DO NOT** refactor to external CSS without testing first render behavior.

## Jinja2 Filters & Functions

### URL Generation

```jinja2
{{ url_for('pages.explorer') }}
{{ url_for('static', filename='css/explorer.css') }}
```

### Conditional Classes

```jinja2
class="nav-link {% if request.endpoint == 'pages.git' %}active{% endif %}"
```

### Loop Constructs

```jinja2
{% for type in object_types %}
    <a href="{{ url_for('pages.objects', object_type=type) }}">{{ type }}</a>
{% endfor %}
```

### Flash Messages

```jinja2
{% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        {% for category, message in messages %}
            <div class="alert alert-{{ category }}">{{ message }}</div>
        {% endfor %}
    {% endif %}
{% endwith %}
```

## Accessibility

- `role` attributes on interactive regions
- `aria-label`, `aria-describedby` on inputs
- `aria-haspopup`, `aria-expanded` on dropdowns
- `<kbd>` tags for keyboard shortcuts

## Deprecated Templates

`objects.html` - Simple object browser, replaced by `explorer.html`. Kept for reference/fallback.
