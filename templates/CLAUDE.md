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

**JS** (before `</body>`): Bootstrap JS → `app.js` → `base-state.js` → `session-manager.js` → `ui-notifications.js` → `git-ui.js` → `api-client.js` → `commit-dialog.js` → `lock-manager.js` → `base.js` → `{% block scripts %}`

Page scripts can rely on all the above being loaded.

## Global Components (base.html)

**Navbar**: Page links, undo button (`#navUndoBtn`), commit button (`#navCommitBtn`), reload config. Active page set via `request.endpoint`.

**Lock Banner** (`#lockBanner`): Shown when another user holds staging lock.

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
