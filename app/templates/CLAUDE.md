# Templates

All pages extend `base.html`. Override blocks: `title`, `extra_css`, `content`, `scripts`.

## Template Hierarchy

```
base.html
  ├─ explorer.html      (3-pane object explorer)
  ├─ dependencies.html   (Cytoscape graph)
  ├─ logs.html
  ├─ backups.html
  ├─ git.html
  ├─ settings.html
  └─ docs.html
```

## Load Order

**CSS** (in `<head>`): Bootstrap → FontAwesome → `tokens.css` → `forms.css` → `style.css` → `{% block extra_css %}`

**JS** (before `</body>`, ES modules): Bootstrap JS → `base.js` (type="module", imports all core modules via ES imports) → `{% block scripts %}`

Page scripts use `type="module"` and import dependencies directly via ES module syntax.

## Global Components (base.html)

**Navbar**: Page links, undo button (`#navUndoBtn`), commit button (`#navCommitBtn`), reload config. Active page set via `request.endpoint`.

**Toast Container** (`#toastContainer`): Use `showToast(message, category)` from base.js.

**Dialogs** (overlay pattern — `.{name}-overlay` > `.{name}-dialog`):

| ID | Purpose |
|----|---------|
| `#globalCommitOverlay` | Staged changes confirmation |
| `#confirmDialogOverlay` | Generic yes/no via `showConfirmDialog()` |
| `#gitResultOverlay` | Terminal-style git output |
| `#identityRequiredOverlay` | Blocks until user sets name/email |
| `#keyboardShortcutsOverlay` | Help dialog (press `?`) |

## Inline Styles Warning

base.html contains a large inline `<style>` block for dialogs, toasts, commit button, lock banner, and keyboard shortcuts modal. This prevents FOUC. **Do not move to external CSS without testing first-render behavior.**
