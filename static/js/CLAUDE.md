# CLAUDE.md

## Core Modules

| File | What | When |
| ---- | ---- | ---- |
| `api-client.js` | Fetch wrapper with error handling, staging headers, {success, data, error} format | Changing API patterns or error handling |
| `base.js` | Session/lock management, toast notifications, commit dialog, git operations UI, DebugLogger | Modifying lock UI, commit workflow, or notifications |

## Page-Specific Modules

| File | What | When |
| ---- | ---- | ---- |
| `audit-log.js` | Audit log filtering, pagination | Modifying audit log page |
| `backups.js` | Backup list/restore/delete UI | Modifying backup page |
| `bulk-attributes.js` | Bulk attribute editing, batch updates | Modifying bulk attribute page |
| `bulk-rename.js` | Pattern-based bulk rename, preview | Modifying bulk rename page |
| `dependencies.js` | D3 graph visualization, edge categories, quick view presets | Modifying dependency graph page (see README.md) |
| `find-replace.js` | Search, preview, bulk replacement | Modifying find/replace page |
| `git.js` | File list, diff viewer, commit/discard UI | Modifying git page |
| `health-check.js` | Config health checks (orphans, circular deps) | Modifying health check page |
| `inheritance.js` | Inheritance tree visualization | Modifying inheritance page |
| `objects.js` | Legacy object browser, syntax highlighting | Maintaining legacy objects page |
| `reorganize.js` | File/folder restructuring UI | Modifying reorganize page |
| `settings.js` | Identity config, git preferences, config paths | Modifying settings page |
| `smart-grouping.js` | Auto-suggest grouping patterns | Modifying smart grouping page |
| `validate.js` | Nagios -v output display | Modifying validate page |

## Explorer Modules

See `explorer/CLAUDE.md` for modular explorer architecture (tree, editor, file panes, staging).

## Additional Documentation

`README.md` - Dependency graph edge category system, quick view expansion rules
