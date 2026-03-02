# Cyclomatic Complexity Refactoring — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce cyclomatic complexity of 33 functions (complexity > 20) to ≤ 20, using helper extraction — no behavioral changes.

**Branch:** New branch `refactor/reduce-complexity` from `eslint-stylelint-config`

**Strategy:** Extract helpers within each file. No new files. No cross-file moves. Each task = one file, one commit. Run `python3 -m pytest tests/ -v` after each task to verify no regressions. Verify complexity with `npx eslint --rule '{"complexity": ["error", 20]}' <file> 2>&1 | grep complexity`.

**Common Patterns:**
- **Type dispatch chains** → handler maps: `const handlers = { type1: fn1, ... }; handlers[type]?.()`
- **HTML section builders** → extract `buildXxxSection()` helpers returning HTML strings
- **Sequential data phases** → extract `addXxxToTree()` / `collectXxxSuggestions()` per phase
- **Validation chains** → extract `validateXxx()` returning early on failure

---

### Task 1: dependencies.js (3 functions: 86, 52, 29)

**`addAllConnectedRecursively` (86) — lines 306-665**
- Root cause: 9-branch type dispatch (host/service/hostgroup/etc.) with nested edge loops
- Fix: Extract type handler map + shared `traverseEdgesAndAdd(nodeId, labels, reversed)` helper
- Extract: `expandHost()`, `expandService()`, `expandHostgroup()`, `expandServicegroup()`, `expandContact()`, `expandContactgroup()`, `expandDependency(reversed, normal)` (reused for 4 dep types), `expandCommand()`, `expandTimeperiod()`
- Main becomes: `const handler = typeHandlers[startType]; if (handler) handler(startNodeId); else { addTemplates(startNodeId); addObjectDependencies(startNodeId); }`

**`calculateOrganizedPositions` (52) — lines 687-850**
- Root cause: BFS tree build + subtree width calc + layout positioning all in one function
- Fix: Extract `buildBfsTree()`, `calcSubtreeWidths()`, `positionNodes()`

**`_expandWithRulesImpl` (29) — lines 1650-1719**
- Root cause: While-loop with rule merging + dual edge traversal
- Fix: Extract `resolveRulesForNode(node, rules)`, `followForwardEdges(...)`, `followBackwardEdges(...)`

**Verify:** `npx eslint --rule '{"complexity": ["error", 20]}' static/js/dependencies.js 2>&1 | grep complexity` → 0

**Commit:** `refactor: reduce cyclomatic complexity in dependencies.js`

---

### Task 2: explorer/file-operations.js (6 functions: 45, 38, 34, 30, 29, 29)

**`handleFolderDrop` (45) — lines 1237-1336**
- Fix: Extract `handleFolderOnFolderDrop()`, `handleFileOnFolderDrop()`, `validateFolderMove()`, `updateFolderReferences()`

**`renderFileItem` (38) — lines 455-528**
- Fix: Extract `computeFileState()`, `buildFileClasses()`, `renderFileActionButton()`, `renderStagedIndicator()`

**`renderTargetPane` (34) — lines 248-370**
- Fix: Extract per-phase adders: `addObjectFiles()`, `addExistingFolders()`, `addStagedCreations()`, `addStagedMoves()`, `addNewFiles()`

**`handleFileDrop` (30) — lines 980-1076**
- Fix: Extract `handleStagedCreationsDrop()`, `handleRegularObjectsDrop()`, `getMaxLineInFile()`

**`renderFolder` (29) — lines 365-459**
- Fix: Extract `getFolderStats()`, `getFolderStagedStatus()`, `renderFolderActionButton()`, `renderFolderBadge()`

**`renderFileObjects` (29) — lines 602-730**
- Fix: Extract `buildFileItemsList()`, `renderExistingObject()`, `renderPendingObject()`, `renderStagedCreation()`

**Verify:** `npx eslint --rule '{"complexity": ["error", 20]}' static/js/explorer/file-operations.js 2>&1 | grep complexity` → 0

**Commit:** `refactor: reduce cyclomatic complexity in file-operations.js`

---

### Task 3: commit-dialog.js (4 functions: 50, 34, 26, 25)

**`buildGlobalCommitDialogHtml` (50) — lines 64-187**
- Fix: Extract `normalizeStagingData()`, `buildCommitHeaderSection()`, `buildExternalChangesSection()`, `buildCommitFooterSection()`

**`applyGlobalCommit` (34) — lines 1339-1395**
- Fix: Extract `validateCommitInput()`, `hasGuiStagingChanges()`, `applyGuiStagingIfNeeded()`

**`updateGlobalContextLines` (26) — lines 1193-1250**
- Fix: Extract `extractStagingArrays()`, `hasAnyFileOperations()`, `restoreExpansionState()`

**`discardGlobalChanges` (25) — lines 1256-1306**
- Fix: Extract `getStagingCounts()`, `buildCountSummary()`, `handleDiscardResult()`

**Verify:** `npx eslint --rule '{"complexity": ["error", 20]}' static/js/commit-dialog.js 2>&1 | grep complexity` → 0

**Commit:** `refactor: reduce cyclomatic complexity in commit-dialog.js`

---

### Task 4: explorer/analysis.js (3 functions: 53, 36, 23)

**`collectAllSuggestions` (53) — lines 282-478**
- Fix: Extract one collector per source: `collectErrorSuggestions()`, `collectHealthWarnings()`, `collectTemplateIssueSuggestions()`, `collectCleanupSuggestions()`, `collectNotificationSuggestions()`, `collectTemplateSuggestions()`, `collectGroupingSuggestions()`

**`mapHealthCheckToState` (36) — lines 85-200**
- Fix: Extract issue type handler map: `const issueHandlers = { duplicate: processDuplicate, health_check_warning: processWarning, ... }`

**`renderCleanupSuggestions` (23) — lines 821-920**
- Fix: Extract `renderCleanupGroup()`, `renderCleanupItem()`, `generateGroupBulkButton()`

**Verify:** `npx eslint --rule '{"complexity": ["error", 20]}' static/js/explorer/analysis.js 2>&1 | grep complexity` → 0

**Commit:** `refactor: reduce cyclomatic complexity in analysis.js`

---

### Task 5: explorer/object-editor.js (2 functions: 33, 31)

**`getAttributeSuggestions` (33) — lines 283-378**
- Fix: Extract `getOptionSuggestions(attrName, objectType)` (handles notification/failure/stalking option lookups), `filterDeletedSuggestions()`, `addStagedCreationSuggestions()`

**`showCenterPaneObject` (31) — lines 62-211**
- Fix: Extract `formatIssueBadge(issue, objectName, objectType)`, `updateCenterPaneHeader()`, `initializeCenterPaneSections()`

**Verify:** `npx eslint --rule '{"complexity": ["error", 20]}' static/js/explorer/object-editor.js 2>&1 | grep complexity` → 0

**Commit:** `refactor: reduce cyclomatic complexity in object-editor.js`

---

### Task 6: audit-log.js (3 functions: 31, 28, 25)

**`renderAuditEntry` (31) — lines 408-591**
- Fix: Extract section renderers: `renderEditsSection()`, `renderMovesSection()`, `renderCreationsSection()`, `renderDeletionsSection()`, `computeEntryCounts()`

**`renderActionEntry` (28) — lines 284-406**
- Fix: Extract action config map: `const ACTION_CONFIG = { backup_created: {badge, icon, title}, ... }`, plus `buildActionDetails(entry, action)`

**anonymous filter (25) — line 181**
- Fix: Extract `matchesAuditFilter(entry, activeFilters)` with per-category matchers

**Verify:** `npx eslint --rule '{"complexity": ["error", 20]}' static/js/audit-log.js 2>&1 | grep complexity` → 0

**Commit:** `refactor: reduce cyclomatic complexity in audit-log.js`

---

### Task 7: explorer/dialogs.js + explorer/app.js + explorer/file-operations.js (3 functions)

**dialogs.js anonymous (38) — ~line 835**
- Fix: Extract `validateBulkActionInputs()`, `validateReferenceValues()`

**app.js `navigateToObjectIssue` (28) — lines 1083-1136**
- Fix: Extract `findMatchingSuggestion(issue, hostListInfo, allSuggestions)` with matcher chain

**file-operations.js `handleObjectDrop` (29) — lines 832-930**
- Fix: Extract `handleStagedCreationsDrop()`, `handleObjectReorderDrop()`, `findDropTargetObject()`

**Verify:** All three files show 0 complexity violations at threshold 20.

**Commit:** `refactor: reduce cyclomatic complexity in dialogs.js, app.js, file-operations.js`

---

### Task 8: Remaining functions (complexity 21-25)

Files: `explorer/constants.js` (22), `explorer/data-loading.js` (22), `explorer/relations-loader.js` (19 — skip), `explorer/impact-section.js` (20 — skip), `base.js` (20 — skip), `git.js` (20 — skip), `settings.js` (20 — skip), `ui-notifications.js` (20 — skip), `shared/pagination.js` (19 — skip), `console-shim.js` (18 — skip), `docs.js` (18 — skip), `explorer/analysis.js handleSuggestionAction` (18 — skip).

Only fix functions at 21+:
- `explorer/constants.js` anonymous (22) — Extract metadata mapping helpers
- `explorer/data-loading.js` anonymous (22) — Extract staging sync phases
- `explorer/object-editor.js updateAttribute` (21) — Extract attribute validation
- `explorer/object-editor.js renderInheritanceSection` (22) — Extract section builders

**Verify:** `npx eslint --rule '{"complexity": ["error", 20]}' static/js/ 2>&1 | grep complexity` → 0

**Commit:** `refactor: reduce cyclomatic complexity in remaining files`

---

### Task 9: Add complexity rule to ESLint config + final verification

**Step 1:** Add `"complexity": ["error", 20]` to `eslint.config.mjs` rules section.

**Step 2:** Run `npx eslint static/js/ 2>&1 | tail -3` — expect 72 pre-existing errors only (no new complexity violations).

**Step 3:** Run `python3 -m pytest tests/ -v` — all tests pass.

**Commit:** `chore: add ESLint complexity rule (max 20)`
