# CLAUDE.md

## Overview

Page-specific JavaScript modules for Nagios Bulk Editor UI.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ---- | --------------- | ---------------- |
| `api-client.js` | Centralized fetch wrapper with error handling, staging headers, toast integration | Changing API call patterns or error handling |
| `audit-log.js` | Audit log filtering, pagination, event type display | Modifying audit log UI or filters |
| `backups.js` | Backup page list/restore/delete UI, modal dialogs | Adding backup management features |
| `base.js` | Session/lock management, toast notifications, global commit dialog, staging state, git operations UI | Modifying lock UI, commit workflow, or toast behavior |
| `bulk-attributes.js` | Bulk attribute editing multi-select, batch updates | Modifying bulk attribute operations |
| `bulk-rename.js` | Bulk rename pattern-based renaming, preview | Changing bulk rename UI |
| `dependencies.js` | D3 dependency graph, edge categories, quick view presets, zoom/pan, legend, object type filtering | Changing graph visualization, adding relationship types, or modifying presets |
| `find-replace.js` | Find/replace search, preview, bulk replacement | Modifying search or replace logic |
| `git.js` | Git page file list, diff viewer, commit/discard UI, tab switching | Modifying git page UI or diff display |
| `health-check.js` | Config health checks display (orphans, circular deps) | Adding health check rules |
| `inheritance.js` | Inheritance tree visualization, template hierarchy | Changing inheritance display |
| `objects.js` | Legacy object browser search, syntax highlighting, edit modal | Maintaining legacy object browser page |
| `reorganize.js` | File/folder restructuring page UI | Changing reorganization UI |
| `settings.js` | Settings page identity config, git preferences, config path management | Adding settings fields or validation |
| `smart-grouping.js` | Smart grouping auto-suggest based on patterns | Modifying grouping logic |
| `validate.js` | Nagios validation (nagios -v) output display | Modifying validation UI |
| `README.md` | Dependency graph edge category system, quick view expansion rules architecture (forward/backward/atType/stopAt), adding new presets | Understanding graph relationship mapping, adding new Nagios relationship types, or creating quick view presets |

## Dependency Graph Documentation

See `README.md` for complete architecture documentation:
- Edge category system (relationship fields → edge categories → presets)
- Quick view expansion rules (declarative rule structure for type-aware traversal)
- Adding new Nagios relationship types or quick view presets
