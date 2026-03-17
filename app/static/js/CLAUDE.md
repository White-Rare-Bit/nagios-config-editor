# JavaScript

All modules use ES module `import`/`export` syntax. Explorer modules in `explorer/` (see `explorer/CLAUDE.md`).

## Core Modules (loaded on every page)

| File | What |
|------|------|
| `app.js` | Core utilities: `escapeHtml()` |
| `api-client.js` | Fetch wrapper, staging headers, `{success, data, error}` format |
| `base-state.js` | Shared state (lock status, session) |
| `session-manager.js` | Session ID, user identity, staging headers (X-Session-Id, X-User-Name, X-User-Email) |
| `ui-notifications.js` | Toast notifications, confirm dialogs |
| `git-ui.js` | Git result panel UI |
| `lock-manager.js` | Lock status checking, break lock, lock change/break callbacks |
| `stable-key.js` | Stable key encoding/decoding utilities |
| `commit-dialog.js` | Commit overlay, shadow diff display |
| `base.js` | Initialization, event delegation, keyboard shortcuts, DebugLogger |

## Page Modules

| File | What |
|------|------|
| `logs.js` | Unified log viewer: audit + app tabs, filtering, pagination |
| `backups.js` | Backup list/restore/delete |
| `dependencies.js` | Cytoscape graph visualization |
| `dependencies-config.js` | Graph layout and style configuration |
| `git.js` | File list, diff viewer, commit/discard |
| `docs.js` | Documentation page navigation |
| `docs-data.js` | Documentation page data/content |
| `settings.js` | Identity config, git preferences, config paths |
