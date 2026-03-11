# JavaScript

All page modules use IIFE pattern. Explorer modules in `explorer/` (see `explorer/CLAUDE.md`).

## Core Modules (loaded on every page)

| File | What |
|------|------|
| `api-client.js` | Fetch wrapper, staging headers, `{success, data, error}` format |
| `base-state.js` | Shared state (lock status, session) |
| `session-manager.js` | Session ID and user identity management |
| `ui-notifications.js` | Toast notifications, flash messages |
| `git-ui.js` | Git result panel UI |
| `commit-dialog.js` | Commit overlay, shadow diff display |
| `base.js` | Initialization, event delegation, keyboard shortcuts, DebugLogger |

## Page Modules

| File | What |
|------|------|
| `logs.js` | Unified log viewer: audit + app tabs, filtering, pagination |
| `backups.js` | Backup list/restore/delete |
| `bulk-rename.js` | Pattern-based bulk rename with preview |
| `dependencies.js` | Cytoscape graph visualization |
| `dependencies-config.js` | Graph layout and style configuration |
| `git.js` | File list, diff viewer, commit/discard |
| `inheritance.js` | Inheritance tree visualization |
| `reorganize.js` | File/folder restructuring, `performBulkOperation()` helper |
| `settings.js` | Identity config, git preferences, config paths |
| `validate.js` | Nagios -v output display |
