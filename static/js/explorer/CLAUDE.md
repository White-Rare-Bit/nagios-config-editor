# CLAUDE.md

## Overview

Modular explorer architecture: shared state namespace, tree/editor/file panes, staging operations, UI refresh coordination.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ---- | --------------- | ---------------- |
| `main.js` | Namespace definition, shared state structure (allObjects, staging maps, undo stack, UI state) | Understanding state structure or initialization flow |
| `state-management.js` | Staging persistence, session sync, lock management, centralized refresh function | Modifying staging behavior, lock semantics, or adding refresh coordination |
| `app.js` | Tree rendering, filtering, selection logic, autocomplete, reference/inheritance display | Modifying tree UI, search, or object relationship views |
| `object-editor.js` | Center pane attribute editor, validation, staging edits, create/edit/delete workflows | Changing object editing UI or attribute manipulation |
| `file-operations.js` | Target pane file tree, move/create operations, folder management, drag targets | Modifying file tree or move operations UI |
| `context-menu.js` | Right-click menus, dialogs (rename, clone, delete), preview modal, keyboard shortcuts | Adding context menu items or dialog types |
| `dialogs.js` | Move dialog, create dialog, delete confirmations, bulk operation dialogs | Changing dialog UI or bulk operation flows |
| `data-loading.js` | Initial load, refresh, server sync, pending changes polling | Modifying data loading or sync behavior |
| `drag-drop.js` | Drag-and-drop for objects and files, auto-expand folders, drop zone highlighting | Modifying drag-drop behavior or visual feedback |
| `analysis.js` | Template detection, inheritance analysis, issue detection, suggestions tab | Adding analysis features or suggestion logic |
| `ui-utils.js` | Common UI helpers (formatObjectName, buildBreadcrumb, status badges) | Adding UI formatting utilities |
