# ES Modules Migration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert all 41 JS files from IIFE + window globals to native ES modules with explicit import/export. Drop the Explorer namespace entirely.

**Architecture:** Big-bang conversion — all files change in one pass. No build step. Native browser `<script type="module">`. Explorer namespace replaced with individual function exports and a centralized action registry.

**Tech Stack:** Vanilla ES modules (no bundler, no TypeScript)

**Design doc:** `docs/plans/2026-03-11-es-modules-migration-design.md`

---

## Conventions Used Throughout

**Pattern for converting a file:**
1. Remove IIFE wrapper if present (`(function() { ... })()` or `(function(Explorer) { ... })(window.Explorer)`)
2. Remove `'use strict'` (ES modules are strict by default)
3. Remove all `window.X = X` assignments
4. Add `export` to each public function/const
5. Add `import { ... } from './...'` at top for each cross-file reference
6. For explorer files: remove all `Explorer.` prefixes from function definitions AND call sites within the same module; use imports for cross-module calls

**Circular imports:** Several explorer modules have circular import relationships (e.g., `app.js` ↔ `badge-issues.js`). This is safe in ES modules because all cross-references occur inside function bodies (not at top-level evaluation time). Document with `// circular` comment on the import line.

**Handling inline `onclick` in generated HTML:** `commit-dialog.js` generates HTML with `onclick="functionName()"`. These need the functions on `window`. Solution: keep targeted `window.X = X` assignments ONLY for functions referenced in generated HTML onclick handlers. Mark with `// onclick handler — must be global`.

---

## Task 1: Move app.js into js/ directory

**Files:**
- Move: `static/app.js` → `static/js/app.js`

**Step 1: Move the file**
```bash
git mv static/app.js static/js/app.js
```

**Step 2: Update base.html reference (will be fully updated in Task 12, but keep it working)**
In `templates/base.html`, change line 1959:
```html
<!-- old -->
<script src="{{ url_for('static', filename='app.js') }}"></script>
<!-- new -->
<script src="{{ url_for('static', filename='js/app.js') }}"></script>
```

**Step 3: Commit**
```bash
git add -A && git commit -m "move app.js into js/ directory for consistent import paths"
```

---

## Task 2: Convert standalone leaf modules (no project imports)

These files import nothing from other project files. Convert them first.

**Files:**
- `static/js/app.js` (moved in Task 1)
- `static/js/base-state.js`
- `static/js/session-manager.js`
- `static/js/stable-key.js`
- `static/js/shared/pagination.js`
- `static/js/docs-data.js`
- `static/js/dependencies-config.js`

### static/js/app.js

No IIFE. Export all public functions. Remove `window._globalKeydownAdded` flag.

```javascript
// ADD at top:
export function escapeHtml(text) { ... }  // was: function escapeHtml(text)
export function escapeRegex(str) { ... }
export function generateUniqueId() { ... }
export function formatDate(dateStr, useRelative) { ... }
export function setButtonLoading(buttonOrSelector, isLoading, loadingText) { ... }
export function copyToClipboard(text) { ... }
export function reloadConfig() { ... }
export function createBackup() { ... }
export function handleGlobalKeydown(e) { ... }
```

No `window.X =` assignments to remove (currently bare globals, not explicitly assigned to window — but bare globals in a module are module-scoped, so this just works).

### static/js/base-state.js

Remove `window.baseState` assignment. Export the object.

```javascript
// REMOVE: window.baseState = { ... };
// REPLACE WITH:
export const baseState = {
    commitContextLines: 3,
    diffData: null,
    referenceData: null,
    gitResultNeedsReload: false,
    gitOnlyChanges: null,
    gitOnlyContextLines: 3,
    currentRefData: null,
    pendingCommitMessage: ''
};
```

### static/js/session-manager.js

Remove 5 `window.X` assignments (lines 78-82). Add `export` to each function.

```javascript
export function getSessionId() { ... }
export function getUserIdentity() { ... }
export function setUserIdentity(name, email) { ... }
export function hasUserIdentity() { ... }
export function getStagingHeaders() { ... }
// REMOVE lines 78-82 (window assignments)
```

### static/js/stable-key.js

Remove IIFE (lines 7, 67). Remove `window.StableKey` assignment. Export the object.

```javascript
// REMOVE IIFE wrapper
// REMOVE: (function() { ... global.StableKey = ... })();
// REPLACE WITH:
const SEPARATOR = '|';
function build(obj) { ... }
function parse(key) { ... }
function findObject(key, objects) { ... }
export const StableKey = { SEPARATOR, build, parse, findObject };
```

### static/js/shared/pagination.js

Remove `window.renderPagination` assignment (line 89). Add export.

```javascript
export function renderPagination(options) { ... }
// REMOVE: window.renderPagination = renderPagination;
```

### static/js/docs-data.js

Remove `window.NAGIOS_OBJECT_REFERENCE` and `window.NAGIOS_INHERITANCE_REFERENCE` assignments.

```javascript
export const NAGIOS_OBJECT_REFERENCE = { ... };
export const NAGIOS_INHERITANCE_REFERENCE = { ... };
```

### static/js/dependencies-config.js

Remove IIFE (lines 8, 680). Remove `window.DepsConfig` assignment (line 668). Export.

```javascript
// REMOVE IIFE wrapper and 'use strict'
export const DepsConfig = { LAYOUT_CONFIG, edgeCategories, viewModePresets, ... };
```

**Commit:**
```bash
git add -A && git commit -m "convert standalone leaf JS modules to ES module exports"
```

---

## Task 3: Convert core modules with one level of imports

**Files:**
- `static/js/ui-notifications.js` (imports from app.js)
- `static/js/git-ui.js` (imports from app.js, base-state.js)
- `static/js/api-client.js` (imports from ui-notifications.js, session-manager.js)

### static/js/ui-notifications.js

```javascript
// ADD:
import { escapeHtml } from './app.js';

export function showToast(message, type, duration) { ... }
export function showConfirmDialog(options) { ... }
// REMOVE: window.showToast = showToast; window.showConfirmDialog = showConfirmDialog;
```

### static/js/git-ui.js

```javascript
// ADD:
import { escapeHtml } from './app.js';
import { baseState } from './base-state.js';

export function showGitRunningPanel(title, command) { ... }
export function showGitOperationResult(title, command, success, message) { ... }
export function closeGitResultPanel() { ... }
export function closeGitResultOverlay() { ... }
// REMOVE: window.X = X (lines 100-103)
```

### static/js/api-client.js

Remove IIFE (lines 9, 129). Remove `'use strict'`.

```javascript
// ADD:
import { showToast } from './ui-notifications.js';
import { getStagingHeaders } from './session-manager.js';

// REMOVE IIFE wrapper
async function handleResponse(response, options) { ... }  // private (module scope)
export async function get(url, options) { ... }
export async function post(url, data, options) { ... }
export async function del(url, options) { ... }

// Also export as namespace for backward compat in callers:
export const ApiClient = { get, post, del };
// REMOVE old window/IIFE return pattern
```

**Note:** Export both individual functions AND the `ApiClient` object. Most callers use `ApiClient.get()` — easier to keep that pattern than rewrite every call site. Callers do `import { ApiClient } from './api-client.js'`.

**Commit:**
```bash
git add -A && git commit -m "convert core dependent modules to ES imports"
```

---

## Task 4: Convert complex core modules (commit-dialog.js, base.js)

**Files:**
- `static/js/commit-dialog.js`
- `static/js/base.js`

### static/js/commit-dialog.js

This file has 14 `window.X` assignments (lines 870-883) AND generates HTML with `onclick="functionName()"` handlers. Functions referenced in onclick MUST stay on window.

```javascript
// ADD:
import { baseState } from './base-state.js';
import { getUserIdentity, hasUserIdentity } from './session-manager.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { showGitRunningPanel, showGitOperationResult, closeGitResultOverlay } from './git-ui.js';
import { ApiClient } from './api-client.js';
import { escapeHtml } from './app.js';

// Export all public functions:
export function handleCommitClick() { ... }
export function showGlobalCommitDialog() { ... }
export function closeGlobalCommitDialog() { ... }
export function discardGlobalChanges() { ... }
export function applyGlobalCommit() { ... }
// ... (all 14 functions)

// onclick handler — must be global (referenced in generated HTML)
window.discardGlobalChanges = discardGlobalChanges;
window.closeGlobalCommitDialog = closeGlobalCommitDialog;
window.applyGlobalCommit = applyGlobalCommit;
window.updateGlobalContextLines = updateGlobalContextLines;
window.updateGitOnlyContextLines = updateGitOnlyContextLines;
window.discardGitChanges = discardGitChanges;
window.applyGitCommit = applyGitCommit;
```

**Alternative (better):** Replace onclick attributes in the generated HTML with data-action attributes and handle them in base.js event delegation. This eliminates the need for window globals entirely. If time permits, do this; otherwise the window assignments above are the safe path.

### static/js/base.js

Remove IIFE around DebugLogger (lines 19-81). This file is the most complex — it imports from nearly every core module AND references Explorer functions for undo/commit UI.

```javascript
// ADD:
import { escapeHtml, generateUniqueId, formatDate, handleGlobalKeydown, reloadConfig, createBackup } from './app.js';
import { baseState } from './base-state.js';
import { getSessionId, getUserIdentity, setUserIdentity, hasUserIdentity } from './session-manager.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { ApiClient } from './api-client.js';
import { closeGitResultPanel } from './git-ui.js';
import { handleCommitClick, closeGlobalCommitDialog } from './commit-dialog.js';

// REMOVE IIFE around DebugLogger
export const DebugLogger = { debug, info, warning, error };
export function escapeJs(text) { ... }
export function pluralize(count, singular, plural) { ... }
export function updateNavCommitButton(changeCount) { ... }
export function updateUndoButton(count) { ... }
export function updateCommitUI() { ... }
// ... other public functions

// REMOVE: window.DebugLogger = DebugLogger; etc.
```

**Explorer references in base.js:** Lines ~172, 175, 188, 241 reference `Explorer.undoLastAction()`, `Explorer.getTotalStagedCount()`, `Explorer.getUndoCount()`, `Explorer.buildTree()`. These become lazy imports or a registration pattern:

```javascript
// At top of base.js:
let explorerCallbacks = null;

export function registerExplorerCallbacks(callbacks) {
    explorerCallbacks = callbacks;
}

// In handleUndoClick:
if (explorerCallbacks?.undoLastAction) {
    await explorerCallbacks.undoLastAction();
}
```

Then in `explorer/main.js`:
```javascript
import { registerExplorerCallbacks } from '../base.js';
import { undoLastAction, getTotalStagedCount, getUndoCount } from './data-loading.js';
import { buildTree } from './app.js';

registerExplorerCallbacks({ undoLastAction, getTotalStagedCount, getUndoCount, buildTree });
```

This avoids base.js importing from explorer (which would create a circular dependency between core and explorer layers).

**Commit:**
```bash
git add -A && git commit -m "convert commit-dialog.js and base.js to ES modules"
```

---

## Task 5: Convert page modules

**Files:**
- `static/js/backups.js`
- `static/js/logs.js`
- `static/js/git.js`
- `static/js/settings.js`
- `static/js/docs.js`
- `static/js/dependencies.js`

Each page module follows the same pattern: add imports for the core modules it uses, export its public functions (or keep them module-private if only used internally), remove any IIFE wrappers.

### static/js/backups.js

```javascript
import { getUserIdentity } from './session-manager.js';
import { ApiClient } from './api-client.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { renderPagination } from './shared/pagination.js';

// All functions become module-scoped (no exports needed — only called from HTML data-action)
// But any functions referenced in HTML onclick MUST be on window
```

### static/js/logs.js

```javascript
import { ApiClient } from './api-client.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { escapeHtml } from './app.js';
import { renderPagination } from './shared/pagination.js';
```

### static/js/git.js

```javascript
import { ApiClient } from './api-client.js';
import { escapeHtml } from './app.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { getUserIdentity } from './session-manager.js';
import { showGitRunningPanel } from './git-ui.js';
import { showResultPanel } from './commit-dialog.js';
import { renderPagination } from './shared/pagination.js';
```

### static/js/settings.js

Remove IIFE (line 4) and `'use strict'`.

```javascript
import { ApiClient } from './api-client.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
```

### static/js/docs.js

Remove IIFE (lines 2, 749) and `'use strict'`.

```javascript
import { NAGIOS_OBJECT_REFERENCE, NAGIOS_INHERITANCE_REFERENCE } from './docs-data.js';
import { ApiClient } from './api-client.js';
import { escapeHtml } from './app.js';

// DocsPage namespace — keep as export for the inline onclick in docs.html
export const DocsPage = { toggleFolder, selectType, selectAppDoc, handleTreeSearch };
// onclick handler — must be global (docs.html template has oninput="DocsPage.handleTreeSearch()")
window.DocsPage = DocsPage;
```

**Better alternative:** Convert the `oninput="DocsPage.handleTreeSearch(this.value)"` in `templates/docs.html` to use event delegation or inline module script. Then remove `window.DocsPage`.

### static/js/dependencies.js

Remove IIFE and `'use strict'`.

```javascript
import { DepsConfig } from './dependencies-config.js';
// Cytoscape and Dagre are loaded as vendor globals — access via window.cytoscape
```

**Note:** Check each page module for functions called via `onclick` in templates or generated HTML. Any such functions need `window.X = X` or, preferably, conversion to data-action delegation.

**Commit:**
```bash
git add -A && git commit -m "convert page modules to ES imports"
```

---

## Task 6: Create explorer/state.js and convert explorer leaf modules

**Files:**
- Create: `static/js/explorer/state.js` (extracted from main.js)
- Modify: `static/js/explorer/constants.js`
- Modify: `static/js/explorer/ui-utils.js`
- Modify: `static/js/explorer/panel-resizer.js`
- Modify: `static/js/explorer/drag-drop.js`

### NEW: static/js/explorer/state.js

Extract `Explorer.state` from main.js into its own module:

```javascript
export const state = {
    allObjects: [],
    allFiles: [],
    allFolders: [],
    selectedKeys: new Set(),
    editedObject: null,
    newObject: null,
    openTabs: [],
    activeTabKey: null,
    contextTarget: null,
    currentView: 'file',
    searchQuery: '',
    expandedFolders: new Set(),
    expandedFiles: new Set(),
    changedFilesMap: {},
    metadataLoaded: false,
    // ... (copy all state properties from main.js Explorer.state)
};
```

### static/js/explorer/constants.js

Remove IIFE (lines 8, 288).

```javascript
// No imports needed (data-driven from API)

export const constants = {
    typeLabels: {},
    nameFields: {},
    REQUIRED_FIELDS: {},
    // ... (all constant properties)
};

export function applyMetadata(data) { ... }
export function isObjectTemplate(obj) { ... }
export function getTypeBadge(type) { ... }
export function getTypeBadgeTier(type, tier) { ... }
export function stripPrefix(value) { ... }
export function checkDuplicateName(name, type, objects, excludeKey) { ... }
```

### static/js/explorer/ui-utils.js

Remove IIFE (lines 11, 163).

```javascript
import { showToast as globalShowToast } from '../ui-notifications.js';

export function switchTabs(container, tabName) { ... }
export const icons = { ... };
export function getIcon(name) { ... }
export function updateBadge(selector, count) { ... }
export function explorerShowToast(message, type) { ... }  // renamed from Explorer.showToast
export function extractFileName(path) { ... }
export function toRelativePath(path) { ... }
export function toDisplayPath(path) { ... }
export function handleApiError(result, context) { ... }
```

### static/js/explorer/panel-resizer.js

Remove IIFE (lines 7, 430).

```javascript
import { constants } from './constants.js';

export function refreshPanelTiers() { ... }
export function initPanelResizer() { ... }
```

### static/js/explorer/drag-drop.js

Remove IIFE (lines 8, 32).

```javascript
export function cleanupDragState() { ... }
```

**Commit:**
```bash
git add -A && git commit -m "create explorer/state.js and convert explorer leaf modules"
```

---

## Task 7: Convert explorer data/state modules

**Files:**
- `static/js/explorer/data-loading.js`
- `static/js/explorer/state-management.js`
- `static/js/explorer/tab-manager.js`
- `static/js/explorer/relations-loader.js`

### static/js/explorer/data-loading.js

Remove IIFE (lines 8, 304).

```javascript
import { state } from './state.js';
import { constants, applyMetadata } from './constants.js';
import { validateTabs } from './tab-manager.js';  // circular — safe (function-level)
import { loadAllSuggestions } from './analysis.js';  // circular — safe
import { ApiClient } from '../api-client.js';
import { showToast } from '../ui-notifications.js';
import { getSessionId } from '../session-manager.js';

export async function loadObjects() { ... }
export function getStagingHeaders() { ... }  // note: may duplicate session-manager's version
export async function updateBadges() { ... }
export async function loadChangedFiles() { ... }
export async function afterFrontendMutation(options) { ... }
export async function afterServerSync(options) { ... }
export async function clearStagedChanges() { ... }
export async function applyAllStaged() { ... }
export async function undoLastAction() { ... }
export function getUndoCount() { ... }
export function getTotalStagedCount() { ... }
```

**Key change:** Every `Explorer.X()` call to functions in OTHER modules becomes an imported function call. Every `Explorer.state` becomes just `state`.

### static/js/explorer/state-management.js

Remove IIFE (lines 14, 145).

```javascript
import { state } from './state.js';
import { getObjectKeyByIndex } from './main.js';
import { computeStagedIssues } from './badge-issues.js';  // circular — safe
import { buildTree } from './app.js';  // circular — safe
import { renderTargetPane } from './file-operations.js';  // circular — safe
import { syncCenterPaneAfterUndo } from './object-editor.js';  // circular — safe
import { renderTabBar } from './tab-manager.js';

export function isSelectedByIndex(index) { ... }
export function addToSelectionByIndex(index) { ... }
export function removeFromSelectionByIndex(index) { ... }
export function clearSelection() { ... }
export function findObjectByAttributes(attrs) { ... }
export function rebuildUI(options) { ... }
```

### static/js/explorer/tab-manager.js

Remove IIFE (lines 16, 344).

```javascript
import { state } from './state.js';
import { findObjectByKey } from './main.js';
import { checkForChanges, showCenterPaneObject } from './object-editor.js';
import { renderTabBar as selfRenderTabBar } from './tab-manager.js';  // self-reference not needed

export function openTab(obj) { ... }
export function closeTab(key) { ... }
export function activateTab(key) { ... }
export function renderTabBar() { ... }
export function restoreTabs() { ... }
export function validateTabs() { ... }
export function persistTabs() { ... }
export function syncTreeSelection(obj) { ... }
```

### static/js/explorer/relations-loader.js

Remove IIFE (lines 8, 158).

```javascript
import { state } from './state.js';
import { getEffectiveAttributes, getEffectiveName } from './object-editor.js';
import { isObjectTemplate } from './constants.js';
import { parseCommaValues } from './main.js';

export function formatFailureCriteria(obj) { ... }
export function formatEscalationInfo(obj) { ... }
export function buildLocalInheritanceChain(obj, templateNames) { ... }
```

**Commit:**
```bash
git add -A && git commit -m "convert explorer data/state modules to ES imports"
```

---

## Task 8: Convert explorer feature modules (part 1)

**Files:**
- `static/js/explorer/object-editor.js` (1444 lines, ~38 exports)
- `static/js/explorer/file-operations.js` (1316 lines, ~40 exports)

### static/js/explorer/object-editor.js

Remove IIFE (lines 3, 1444).

```javascript
import { state } from './state.js';
import { constants, isObjectTemplate, stripPrefix } from './constants.js';
import { getObjectKey, findObjectByKey, parseCommaValues, escapeHtml } from './main.js';
import { afterFrontendMutation } from './data-loading.js';
import { buildLocalInheritanceChain } from './relations-loader.js';
import { isSelectedByIndex } from './state-management.js';
import { ApiClient } from '../api-client.js';
import { showToast } from '../ui-notifications.js';
import { DebugLogger } from '../base.js';

export function showCenterPaneObject(obj) { ... }
export function hideCenterPaneObject() { ... }
export function syncCenterPaneAfterUndo() { ... }
// ... (all ~38 functions, removing Explorer. prefix from definitions)
```

**Critical:** This file has many internal function calls (functions calling other functions in the same file). All `Explorer.functionName()` calls where `functionName` is defined in THIS file become just `functionName()` (no prefix, no import needed).

### static/js/explorer/file-operations.js

Remove IIFE (lines 8, ~1316).

```javascript
import { state } from './state.js';
import { constants } from './constants.js';
import { getObjectKey, findObjectByKey, escapeHtml } from './main.js';
import { isSelectedByIndex, clearSelection, addToSelectionByIndex } from './state-management.js';
import { afterFrontendMutation } from './data-loading.js';
import { showCenterPaneObject } from './object-editor.js';
import { ApiClient } from '../api-client.js';
import { showToast, showConfirmDialog } from '../ui-notifications.js';

export function navigateToObjectByIndex(index) { ... }
export function selectObjectByName(name) { ... }
// ... (all ~40 functions)
```

**Commit:**
```bash
git add -A && git commit -m "convert object-editor.js and file-operations.js to ES modules"
```

---

## Task 9: Convert explorer feature modules (part 2)

**Files:**
- `static/js/explorer/context-menu.js` (1018 lines, ~24 exports)
- `static/js/explorer/dialogs.js` (1377 lines, ~29 exports)

### static/js/explorer/context-menu.js

Remove IIFE (lines 7, 1018).

```javascript
import { state } from './state.js';
import { constants } from './constants.js';
import { getObjectKey, findObjectByKey, getSelectedIndices, escapeHtml } from './main.js';
import { isSelectedByIndex, clearSelection } from './state-management.js';
import { selectObjectByIndex, updateSelection, switchRightTab } from './app.js';  // circular — safe
import { findDependencies } from './dialogs.js';
import { afterFrontendMutation } from './data-loading.js';
import { showCenterPaneObject } from './object-editor.js';
import { loadImpactAndRelationships } from './impact-section.js';
import { cleanupDragState } from './drag-drop.js';
import { ApiClient } from '../api-client.js';
import { showToast } from '../ui-notifications.js';
import { baseState } from '../base-state.js';

export function handleContextMenu(e) { ... }
export function hideContextMenu() { ... }
export function contextAction(action) { ... }
export function showPreview(obj) { ... }
export function closePreview() { ... }
export function showDialog(title, bodyHtml, onConfirm) { ... }
export function closeDialog() { ... }
export function showBulkAction(action) { ... }
// ... (all ~24 functions)
```

### static/js/explorer/dialogs.js

Remove IIFE (lines 3, 1377).

```javascript
import { state } from './state.js';
import { constants, isObjectTemplate } from './constants.js';
import { getObjectKey, findObjectByKey, escapeHtml } from './main.js';
import { buildStableKey, showCenterPaneObject } from './object-editor.js';
import { afterFrontendMutation } from './data-loading.js';
import { showDialog, closeDialog } from './context-menu.js';  // circular — safe
import { ApiClient } from '../api-client.js';
import { showToast, showConfirmDialog } from '../ui-notifications.js';
import { DebugLogger } from '../base.js';

export function dialogAlert(message) { ... }
export function dialogKvList(items) { ... }
export function dialogFileSelect(files, selected) { ... }
export function dialogInfoText(text) { ... }
export function dialogEntryList(entries) { ... }
export function createNewObject() { ... }
// ... (all ~29 functions)
```

**Commit:**
```bash
git add -A && git commit -m "convert context-menu.js and dialogs.js to ES modules"
```

---

## Task 10: Convert explorer analysis modules

**Files:**
- `static/js/explorer/analysis.js` (~1478 lines, ~32 exports)
- `static/js/explorer/analysis-issues.js` (~572 lines, ~13 exports)
- `static/js/explorer/analysis-suggestions.js` (~487 lines, ~10 exports)
- `static/js/explorer/badge-issues.js` (~100 lines, ~5 exports)
- `static/js/explorer/impact-section.js` (~615 lines, 1 export)

### static/js/explorer/analysis.js

Remove IIFE (lines 3, 1478).

```javascript
import { state } from './state.js';
import { constants, isObjectTemplate } from './constants.js';
import { getObjectKey, escapeHtml } from './main.js';
import { afterFrontendMutation } from './data-loading.js';
import { showDialog, closeDialog } from './context-menu.js';
import { showCenterPaneObject } from './object-editor.js';
import { ApiClient } from '../api-client.js';
import { showToast, showConfirmDialog } from '../ui-notifications.js';
import { DebugLogger } from '../base.js';

export function analyzeAll() { ... }
export function updateValidationSummary() { ... }
export function loadAllSuggestions(force) { ... }
export function mapHealthCheckToState(data) { ... }
// ... (all ~32 functions from lines 1446-1477)
```

### static/js/explorer/analysis-issues.js

Remove IIFE (lines 19, 572).

```javascript
import { state } from './state.js';
import { constants } from './constants.js';
import { escapeHtml } from './main.js';
import { mapHealthCheckToState } from './analysis.js';
import { afterFrontendMutation } from './data-loading.js';
import { showDialog, closeDialog } from './context-menu.js';
import { updateBadge } from './ui-utils.js';
import { buildTree } from './app.js';  // circular — safe
import { ApiClient } from '../api-client.js';
import { showToast } from '../ui-notifications.js';

export function loadIssues() { ... }
export function buildGroupedErrors(issues) { ... }
export function filterIssues() { ... }
// ... (all ~13 functions)
```

### static/js/explorer/analysis-suggestions.js

Remove IIFE (lines 19, 487).

```javascript
import { state } from './state.js';
import { constants } from './constants.js';
import { escapeHtml } from './main.js';
import { mapHealthCheckToState } from './analysis.js';
import { dialogFileSelect, dialogKvList } from './dialogs.js';
import { closeDialog } from './context-menu.js';
import { afterFrontendMutation } from './data-loading.js';
import { ApiClient } from '../api-client.js';
import { showToast } from '../ui-notifications.js';

export function loadTemplateIssues() { ... }
export function loadTemplateSuggestions() { ... }
export function loadGroupingSuggestions() { ... }
// ... (all ~10 functions)
```

### static/js/explorer/badge-issues.js

Remove IIFE (lines 11, 100).

```javascript
import { state } from './state.js';
import { mapHealthCheckToState } from './analysis.js';
import { filterIssues } from './analysis-issues.js';
import { updateBadge } from './ui-utils.js';
import { buildTree, getObjectIssue, getHostListInfo } from './app.js';  // circular — safe
import { updateIssueBadge } from './object-editor.js';
import { ApiClient } from '../api-client.js';

export function loadIssuesForBadges() { ... }
export function loadSuggestionsForBadges() { ... }
export function computeStagedIssues() { ... }
export function updateStagedIssuesUI() { ... }
export function refreshCenterPaneIssueBadge() { ... }
```

### static/js/explorer/impact-section.js

Remove IIFE (lines 8, 615).

```javascript
import { state } from './state.js';
import { constants, isObjectTemplate } from './constants.js';
import { getObjectKey, parseCommaValues, escapeHtml } from './main.js';
import { getEffectiveName, getEffectiveAttributes, buildStableKey, fetchInheritance } from './object-editor.js';
import { getStagedDisplayName } from './app.js';  // circular — safe
import { buildLocalInheritanceChain } from './relations-loader.js';
import { navigateToObjectByIndex, selectObjectByName } from './file-operations.js';
import { ApiClient } from '../api-client.js';

export function loadImpactAndRelationships(obj) { ... }
```

**Commit:**
```bash
git add -A && git commit -m "convert explorer analysis modules to ES imports"
```

---

## Task 11: Convert explorer/app.js and create action-registry.js

These are the two hub files — app.js is the largest explorer module, and action-registry.js is new.

**Files:**
- Modify: `static/js/explorer/app.js` (1196 lines, ~47 exports)
- Create: `static/js/explorer/action-registry.js`

### static/js/explorer/app.js

Remove IIFE (lines 8, 1195).

```javascript
import { state } from './state.js';
import { constants, isObjectTemplate, getTypeBadge, checkDuplicateName } from './constants.js';
import { getObjectKey, findObjectByKey, getObjectKeyByIndex, parseCommaValues, escapeHtml, escapeJs } from './main.js';
import { isSelectedByIndex, addToSelectionByIndex, removeFromSelectionByIndex, clearSelection, rebuildUI } from './state-management.js';
import { loadObjects, loadChangedFiles, updateBadges, afterFrontendMutation } from './data-loading.js';
import { openTab, closeTab, activateTab, renderTabBar, restoreTabs } from './tab-manager.js';
import { loadIssuesForBadges, loadSuggestionsForBadges } from './badge-issues.js';  // circular — safe
import { loadAllSuggestions } from './analysis.js';
import { showCenterPaneObject, getEffectiveAttributes, getEffectiveName, getNameFieldForObject } from './object-editor.js';
import { navigateToObjectByIndex } from './file-operations.js';
import { showToast, showConfirmDialog } from '../ui-notifications.js';
import { getSessionId } from '../session-manager.js';
import { DebugLogger } from '../base.js';

export function setView(view) { ... }
export function buildTree() { ... }
export function filterTree() { ... }
export function selectObjectByIndex(index) { ... }
export function updateSelection(options) { ... }
export function getStagedDisplayName(obj) { ... }
export function getObjectIssue(obj) { ... }
export function getHostListInfo(obj) { ... }
// ... (all ~47 functions)
```

### NEW: static/js/explorer/action-registry.js

Extract from `Explorer.initEventDelegation()` in main.js. This file imports every handler function from its source module and exports the action map.

```javascript
import { setView, buildTree, filterTree, selectAllVisible, selectObjectByIndex,
         updateSelection, toggleFolder, handleItemClick, closeObjectDetail,
         switchRightTab, toggleActionsMenu, closeActionsMenu,
         toggleSuggestionSection, openInGraphView, navigateToObjectIssue,
         ensureCleanupRendered, highlightAnalysisItem, highlightCleanupItem } from './app.js';
import { showCenterPaneObject, hideCenterPaneObject, toggleSection,
         showAddAttribute, updateAttribute, deleteAttribute, copyAttributeValue,
         showAttrAutocomplete, hideAttrAutocomplete, selectAttrAutocomplete,
         stageCurrentChanges, syncHighlight, hideDocsPopover } from './object-editor.js';
import { contextAction, showPreview, closePreview, handleContextMenu,
         hideContextMenu, viewInGraph, handleDragStart, handleDragEnd } from './context-menu.js';
import { createNewObject, showCenterPaneNewObject, discardNewObject,
         toggleObjectTypeDropdown, selectObjectType, stageNewObjectChanges,
         checkDependenciesAndDelete, selectByType, selectByPattern,
         showBulkRenameDialog, showEditAttributesDialog, runValidation } from './dialogs.js';
import { toggleFolderExpand, selectFolder, toggleFileExpand,
         toggleCreateMenu, showCreateInput, hideCreateInput,
         collapseAllFolders, refreshWorkspace, deleteFile, deleteFolder,
         createNewItem } from './file-operations.js';
import { openTab, closeTab, activateTab } from './tab-manager.js';
import { undoLastAction } from './data-loading.js';
import { loadImpactAndRelationships } from './impact-section.js';
import { analyzeAll, loadAllSuggestions, toggleCleanupSection } from './analysis.js';
import { filterIssues } from './analysis-issues.js';
import { filterTemplateSuggestions, filterGroupingSuggestions } from './analysis-suggestions.js';
import { refreshPanelTiers } from './panel-resizer.js';

// Map data-action attribute values to handler functions
export const actionHandlers = {
    // View & Navigation
    'setView': (e) => setView(e.target.closest('[data-action]').dataset.view),
    'filterTree': () => filterTree(),
    'toggleFolder': (e) => toggleFolder(e),
    'handleItemClick': (e) => handleItemClick(e),
    'selectObjectByIndex': (e) => selectObjectByIndex(parseInt(e.target.closest('[data-action]').dataset.index)),

    // Selection
    'selectAllVisible': () => selectAllVisible(),
    'selectByType': () => selectByType(),
    'selectByPattern': () => selectByPattern(),

    // Object Operations
    'createNewObject': () => createNewObject(),
    'deleteObject': (e) => checkDependenciesAndDelete(),
    'stageCurrentChanges': () => stageCurrentChanges(),
    'discardNewObject': () => discardNewObject(),

    // Context Menu
    'contextAction': (e) => contextAction(e.target.closest('[data-action]').dataset.contextAction),

    // Tabs
    'openTab': (e) => openTab(e),
    'closeTab': (e) => closeTab(e.target.closest('[data-action]').dataset.key),
    'activateTab': (e) => activateTab(e.target.closest('[data-action]').dataset.key),

    // Panels
    'closeObjectDetail': () => closeObjectDetail(),
    'switchRightTab': (e) => switchRightTab(e.target.closest('[data-action]').dataset.tab),
    'toggleActionsMenu': () => toggleActionsMenu(),
    'closeActionsMenu': () => closeActionsMenu(),

    // Analysis
    'analyzeAll': () => analyzeAll(),
    'filterIssues': () => filterIssues(),
    'toggleCleanupSection': (e) => toggleCleanupSection(e),
    'toggleSuggestionSection': (e) => toggleSuggestionSection(e),
    'filterTemplateSuggestions': () => filterTemplateSuggestions(),
    'filterGroupingSuggestions': () => filterGroupingSuggestions(),

    // File Operations
    'toggleFolderExpand': (e) => toggleFolderExpand(e),
    'selectFolder': (e) => selectFolder(e),
    'toggleFileExpand': (e) => toggleFileExpand(e),
    'toggleCreateMenu': () => toggleCreateMenu(),
    'showCreateInput': (e) => showCreateInput(e),
    'hideCreateInput': () => hideCreateInput(),
    'collapseAllFolders': () => collapseAllFolders(),
    'refreshWorkspace': () => refreshWorkspace(),
    'deleteFile': (e) => deleteFile(e),
    'deleteFolder': (e) => deleteFolder(e),
    'createNewItem': (e) => createNewItem(e),

    // ... (complete this from the actual initEventDelegation in main.js lines 199-289)
};
```

**Note:** The exact action names and handler signatures must be copied from the current `Explorer.initEventDelegation()` in main.js. The above is a representative subset — the implementer MUST read main.js lines 199-289 to get the complete list.

**Commit:**
```bash
git add -A && git commit -m "convert explorer/app.js and create action-registry.js"
```

---

## Task 12: Convert explorer/main.js and wire up initialization

**Files:**
- Modify: `static/js/explorer/main.js`

This file becomes the entry point for the explorer page. It sets up event delegation using the action registry and calls init.

```javascript
import { state } from './state.js';
import { StableKey } from '../stable-key.js';
import { escapeHtml, escapeJs } from '../app.js';
import { DebugLogger } from '../base.js';
import { getSessionId } from '../session-manager.js';
import { registerExplorerCallbacks } from '../base.js';
import { actionHandlers } from './action-registry.js';
import { undoLastAction, getTotalStagedCount, getUndoCount, loadObjects, loadChangedFiles, updateBadges } from './data-loading.js';
import { buildTree, setView } from './app.js';
import { restoreTabs } from './tab-manager.js';
import { initPanelResizer } from './panel-resizer.js';

// Utility functions (used by many explorer modules, re-exported for convenience)
export function getObjectKey(obj) { return StableKey.build(obj); }
export function findObjectByKey(key) { return StableKey.findObject(key, state.allObjects); }
export function getSelectedIndices() { ... }
export function getObjectKeyByIndex(index) { ... }
export function groupByType(items) { ... }
export function parseCommaValues(str) { ... }
export function getConfigRootName() { ... }
export { escapeHtml, escapeJs };  // re-export for explorer modules

// Register callbacks for base.js (undo/commit button updates)
registerExplorerCallbacks({ undoLastAction, getTotalStagedCount, getUndoCount, buildTree });

// Event delegation
function initEventDelegation() {
    document.addEventListener('click', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (actionEl) {
            const action = actionEl.dataset.action;
            const handler = actionHandlers[action];
            if (handler) {
                e.preventDefault();
                handler(e);
            }
        }
    });
    // ... (other event types: contextmenu, dragstart, etc.)
}

export async function init(configPath) {
    state.configPath = configPath;
    initEventDelegation();
    initPanelResizer();
    await loadObjects();
    await loadChangedFiles();
    restoreTabs();
    buildTree();
    updateBadges();
}

// Debug console access
if (typeof window !== 'undefined') {
    window.__debug = { state, getObjectKey, findObjectByKey, loadObjects, buildTree };
}
```

**Commit:**
```bash
git add -A && git commit -m "convert explorer/main.js to ES module entry point with action registry"
```

---

## Task 13: Update all templates

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/explorer.html`
- Modify: `templates/dependencies.html`
- Modify: `templates/git.html`
- Modify: `templates/logs.html`
- Modify: `templates/backups.html`
- Modify: `templates/settings.html`
- Modify: `templates/docs.html`

### templates/base.html

Replace lines 1958-1968 (10 script tags + 1 vendor) with:

```html
    <script src="{{ url_for('static', filename='vendor/js/bootstrap.bundle.min.js') }}"></script>
    <script type="module" src="{{ url_for('static', filename='js/base.js') }}"></script>

    {% block scripts %}{% endblock %}
```

`base.js` is the entry point — its import chain pulls in app.js, base-state.js, session-manager.js, ui-notifications.js, git-ui.js, api-client.js, commit-dialog.js, stable-key.js. No need for individual script tags.

**Remove** the `shared/pagination.js` script tag — it's imported by the page modules that need it.

### templates/explorer.html

Replace the ~19 script tags with:

```html
{% block scripts %}
<script type="module">
import { init } from '{{ url_for("static", filename="js/explorer/main.js") }}';
init('{{ config_path }}');
</script>
{% endblock %}
```

### templates/dependencies.html

```html
{% block scripts %}
<script src="{{ url_for('static', filename='vendor/js/cytoscape.min.js') }}"></script>
<script src="{{ url_for('static', filename='vendor/js/dagre.min.js') }}"></script>
<script src="{{ url_for('static', filename='vendor/js/cytoscape-dagre.js') }}"></script>
<script type="module" src="{{ url_for('static', filename='js/dependencies.js') }}"></script>
{% endblock %}
```

### templates/git.html

```html
{% block scripts %}
<script type="module" src="{{ url_for('static', filename='js/git.js') }}"></script>
{% endblock %}
```

### templates/logs.html

```html
{% block scripts %}
<script type="module" src="{{ url_for('static', filename='js/logs.js') }}"></script>
{% endblock %}
```

### templates/backups.html

```html
{% block scripts %}
<script type="module" src="{{ url_for('static', filename='js/backups.js') }}"></script>
{% endblock %}
```

### templates/settings.html

```html
{% block scripts %}
<script type="module" src="{{ url_for('static', filename='js/settings.js') }}"></script>
{% endblock %}
```

### templates/docs.html

Replace the `oninput="DocsPage.handleTreeSearch(this.value)"` with a data-action or inline module approach:

```html
{% block scripts %}
<script type="module" src="{{ url_for('static', filename='js/docs.js') }}"></script>
{% endblock %}
```

If the `oninput` is kept, `docs.js` must still assign `window.DocsPage`. Otherwise, convert to event listener inside docs.js.

**Commit:**
```bash
git add -A && git commit -m "update all templates to use ES module script tags"
```

---

## Task 14: Audit and fix inline event handlers

**Files:** All JS files that generate HTML with `onclick`, `oninput`, or similar inline handlers.

**Known locations:**
1. `commit-dialog.js`: onclick handlers in generated commit dialog HTML (discardGlobalChanges, closeGlobalCommitDialog, applyGlobalCommit, updateGlobalContextLines, updateGitOnlyContextLines, discardGitChanges, applyGitCommit)
2. `docs.html`: `oninput="DocsPage.handleTreeSearch(this.value)"`
3. Page modules (backups.js, logs.js, git.js, settings.js): check for any `onclick=` in generated HTML strings

**For each inline handler found:**

**Option A (quick — keep window global):**
```javascript
export function myHandler() { ... }
window.myHandler = myHandler;  // onclick handler — must be global
```

**Option B (better — convert to event delegation):**
Replace `onclick="myHandler()"` with `data-action="myHandler"` and add to the appropriate actionHandlers map (base.js for global actions, action-registry.js for explorer actions).

**Recommendation:** Use Option A for commit-dialog.js (lots of handlers in complex generated HTML). Use Option B for simpler cases like docs.html.

**Step 1:** Search all JS files for `onclick=`, `oninput=`, `onchange=`, `onkeydown=` in template literal strings:
```bash
grep -rn 'on\(click\|input\|change\|keydown\|submit\)=' static/js/ --include="*.js"
```

**Step 2:** For each match, apply Option A or B.

**Step 3:** Search all template files for inline handlers:
```bash
grep -rn 'on\(click\|input\|change\|keydown\|submit\)=' templates/ --include="*.html"
```

**Step 4:** For each match, apply Option A or B.

**Commit:**
```bash
git add -A && git commit -m "fix inline event handlers for ES module compatibility"
```

---

## Task 15: Update documentation

**Files:**
- Modify: `templates/CLAUDE.md` (update load order section)
- Modify: `static/js/CLAUDE.md` (update module architecture)
- Modify: `static/js/explorer/CLAUDE.md` (update Explorer pattern)
- Modify: `CLAUDE.md` (update any JS references)

Update each doc to reflect:
- ES modules replace script tag load order
- Explorer namespace is gone — individual imports
- action-registry.js is the new action dispatch hub
- `window.__debug` for console access
- `registerExplorerCallbacks()` pattern for base.js ↔ explorer communication

**Commit:**
```bash
git add -A && git commit -m "update documentation for ES modules architecture"
```

---

## Task 16: Verification

**No automated JS tests exist.** Verification is manual browser testing.

**Step 1: Start the app**
```bash
python3 app.py
```

**Step 2: Open browser dev console and check for errors on each page**

Check each page for:
- Zero console errors on load
- All interactive features work

| Page | What to test |
|------|-------------|
| Explorer (`/`) | Tree loads, click objects, edit attributes, create/delete objects, context menu, bulk operations, drag-drop, analysis panel, undo, commit dialog |
| Dependencies (`/dependencies`) | Graph renders, search works, node click, layout switching |
| Git (`/git`) | Status loads, diff view, commit, history, branch operations |
| Logs (`/logs`) | Log entries load, tab switching, filtering, pagination |
| Backups (`/backups`) | Backup list loads, create/restore/delete, pagination |
| Settings (`/settings`) | Settings load, save, path browsing |
| Docs (`/docs`) | Tree navigation, search, content rendering |

**Step 3: Check cross-page features**
- Navbar undo button works from any page
- Navbar commit button opens commit dialog from any page
- Keyboard shortcuts work (?, Ctrl+R, Ctrl+B, Esc)
- Toast notifications appear correctly
- Identity dialog appears when needed

**Step 4: Final commit**
```bash
git add -A && git commit -m "ES modules migration complete — all 41 JS files converted"
```

---

## Circular Dependency Map (Reference)

These circular imports are safe because all cross-references are inside function bodies:

```
app.js ←→ badge-issues.js
app.js ←→ analysis-issues.js (via buildTree)
context-menu.js → app.js (selectObjectByIndex, updateSelection)
dialogs.js ←→ context-menu.js (showDialog/closeDialog)
state-management.js → app.js (buildTree)
state-management.js → file-operations.js (renderTargetPane)
data-loading.js → analysis.js (loadAllSuggestions)
```

If any circular import causes runtime issues (unlikely but possible), break the cycle by extracting the shared function into a separate module.

---

## File Count Summary

| Category | Files modified | Files created |
|----------|---------------|---------------|
| Core modules | 10 | 0 |
| Page modules | 7 | 0 |
| Explorer modules | 18 | 2 (state.js, action-registry.js) |
| Templates | 8 | 0 |
| Documentation | 4 | 0 |
| **Total** | **47** | **2** |
