# L10 — `static/js/explorer/badge-issues.js` — MODIFY

## Purpose
Add `?candidate=1` to health-check calls. Remove `pendingEdits`-based staged issue computation. In candidate mode, the server health-check endpoint analyzes candidate objects directly, so all issues come from the server — no client-side staged issue overlay needed.

No live configuration is mutated by this module. All API calls (`/api/health-check`, `/api/smart-grouping/suggest`) are read-only. The `?candidate=1` suffix directs the server to analyze the candidate directory (Palo Alto model: copy config to candidate, edit candidate, apply candidate to live) rather than the running config.

## Removal Audit
- `let stagedIssues = []` module state → REMOVED. No client-side staged issues.
- `computeStagedIssues()` that reads `state.pendingEdits` → REMOVED. In candidate mode, the health-check endpoint analyzes candidate objects directly, so all issues come from the server.
- `updateStagedIssuesUI()` → REMOVED. Server issues are the only issues.
- `resolveWarningsFromStagedTemplateEdits()` → REMOVED. Server health-check already accounts for template edits in candidate.
- `buildEditedTemplatesMap()` → REMOVED. No client-side pending edits to analyze.
- `collectTemplateChainFields()` → REMOVED. Only used by `resolveWarningsFromStagedTemplateEdits()`.
- `parseMissingFields()` → REMOVED. Only used by `resolveWarningsFromStagedTemplateEdits()`.
- `Explorer.stagedIssues` getter → REMOVED. No client-side staged issues.
- `Explorer.computeStagedIssues` export → REMOVED.
- `Explorer.updateStagedIssuesUI` export → REMOVED.
- References to `state.pendingEdits` → REMOVED.
- References to `state.stagedObjectDeletions` → REMOVED.

**Key insight**: The entire staged issues system exists because the old staging model kept changes client-side, requiring client-side issue computation. In candidate mode, the server has all changes, so health-check returns accurate issues directly.

### Detailed Line-by-Line Staging References

**`stagedIssues` array and all references:**
| Line | Reference | Action |
|------|-----------|--------|
| 16 | `let stagedIssues = []` module-level variable declaration | REMOVE |
| 111 | `stagedIssues = []` reset at start of `computeStagedIssues()` | REMOVE with function |
| 181 | `stagedIssues.push({ ... })` adding broken reference issue | REMOVE with function |
| 211 | `stagedIssues.forEach(issue => { ... })` iterating in `updateStagedIssuesUI()` | REMOVE with function |
| 349-353 | `Object.defineProperty(Explorer, 'stagedIssues', { get: function() { return stagedIssues; } })` getter export | REMOVE |

**`issue.staged` property checks:**
| Line | Reference | Action |
|------|-----------|--------|
| 191 | `staged: true` property set on pushed issue objects | REMOVE with function |
| 205 | `if (issue.staged)` check in `updateStagedIssuesUI()` to filter staged issues from `state.issuesByObject` | REMOVE with function |
| 316 | `if (issue.staged \|\| issue.type !== 'notification_gap')` skip check in `resolveWarningsFromStagedTemplateEdits()` | REMOVE with function |

**`stagedObjectDeletions.has()` calls:**
| Line | Reference | Action |
|------|-----------|--------|
| 149 | `if (state.stagedObjectDeletions.has(o.global_index)) {return;}` skip deleted objects in `computeStagedIssues()` | REMOVE with function |

**`Explorer.stagedIssues` exposed property:**
| Line | Reference | Action |
|------|-----------|--------|
| 349-353 | `Object.defineProperty(Explorer, 'stagedIssues', { get: ... })` | REMOVE entire property definition |

**`computeStagedIssues()` function (lines 110-199):**
| Line | Reference | Action |
|------|-----------|--------|
| 110 | `function computeStagedIssues()` declaration | REMOVE entire function |
| 113 | `state.pendingEdits.size === 0` early return check | REMOVE with function |
| 116 | `updateStagedIssuesUI()` call on early return | REMOVE with function |
| 121 | `resolveWarningsFromStagedTemplateEdits()` call | REMOVE with function |
| 125 | `for (const [idx, edit] of state.pendingEdits)` iteration over pending edits | REMOVE with function |
| 147-198 | All reference-checking logic within `computeStagedIssues()` | REMOVE with function |
| 345 | `Explorer.computeStagedIssues = computeStagedIssues` export | REMOVE |

**`updateStagedIssuesUI()` function (lines 202-231):**
| Line | Reference | Action |
|------|-----------|--------|
| 202 | `function updateStagedIssuesUI()` declaration | REMOVE entire function |
| 204-208 | Loop clearing staged issues from `state.issuesByObject` via `issue.staged` check | REMOVE with function |
| 210-215 | Loop adding new staged issues to `state.issuesByObject` | REMOVE with function |
| 218-230 | Badge and validation summary updates (`filterIssues`, badge update, `updateValidationSummary`, `updateSuggestionsBadge`) | MIGRATE to `refreshIssueBadges()` (see Change 8) |
| 346 | `Explorer.updateStagedIssuesUI = updateStagedIssuesUI` export | REMOVE |

**`resolveWarningsFromStagedTemplateEdits()` function (lines 310-336):**
| Line | Reference | Action |
|------|-----------|--------|
| 310 | `function resolveWarningsFromStagedTemplateEdits()` declaration | REMOVE entire function |
| 311 | `buildEditedTemplatesMap()` call | REMOVE with function |
| 315-335 | Warning resolution logic checking `state.issuesByObject` | REMOVE with function |

**`buildEditedTemplatesMap()` function (lines 241-253):**
| Line | Reference | Action |
|------|-----------|--------|
| 241 | `function buildEditedTemplatesMap()` declaration | REMOVE entire function |
| 243 | `for (const [idx, edit] of state.pendingEdits)` iteration | REMOVE with function |

**`collectTemplateChainFields()` function (lines 272-302):**
| Line | Reference | Action |
|------|-----------|--------|
| 272 | `function collectTemplateChainFields(obj, editedTemplates)` declaration | REMOVE — only used by `resolveWarningsFromStagedTemplateEdits()` |

**`parseMissingFields()` function (lines 258-266):**
| Line | Reference | Action |
|------|-----------|--------|
| 258 | `function parseMissingFields(message)` declaration | REMOVE — only used by `resolveWarningsFromStagedTemplateEdits()` |

**Other staging references:**
| Line | Reference | Action |
|------|-----------|--------|
| 6 | `* Client-side only: staged issue detection (broken references from pending edits).` doc comment | REMOVE comment line |
| 48 | `* (health-check load, undo, staging changes) to keep the badge in sync.` doc comment | UPDATE — remove "staging changes", replace with "candidate changes" |
| 109 | `// Compute issues that would result from staged changes` comment | REMOVE with function |
| 120 | `// Bug 017: Check if staged template edits resolve existing warnings` comment | REMOVE with function |
| 201 | `// Update the issues UI with staged issues` comment | REMOVE with function |
| 203 | `// Clear staged issues from state.issuesByObject first` comment | REMOVE with function |
| 210 | `// Add new staged issues to map` comment | REMOVE with function |
| 234 | `// Bug 017: Resolve warnings when staged template edits provide missing fields` section header | REMOVE |
| 238 | `* Build a map of template names to their staged edit data.` doc comment | REMOVE with function |
| 270 | `* including any staged edits to those templates.` doc comment | REMOVE with function |
| 305-307 | Doc comment about staged template edits resolving warnings | REMOVE with function |
| 338 | `// Export to Explorer namespace` section | UPDATE — remove staging exports |

## Changes

**1. Add candidate suffix to health-check calls** (lines 24-27, 63-66):
```javascript
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/health-check${suffix}`);
```

**2. Add candidate suffix to smart-grouping suggest** (line 70):
```javascript
const suggestResult = await ApiClient.get(`/api/smart-grouping/suggest${suffix}`, { silent: true });
```

**3. Remove `computeStagedIssues()` function** (lines 110-199) and all related code.

**4. Remove `resolveWarningsFromStagedTemplateEdits()` function** (lines 310-336).

**5. Remove `buildEditedTemplatesMap()` function** (lines 241-253).

**6. Remove `collectTemplateChainFields()` function** (lines 272-302).

**7. Remove `parseMissingFields()` function** (lines 258-266).

**8. Extract badge refresh logic into `refreshIssueBadges()`** — The useful UI update logic from `updateStagedIssuesUI()` lines 217-230 (calling `Explorer.filterIssues()`, updating `#issuesSectionBadge`, `Explorer.updateValidationSummary()`, and `Explorer.updateSuggestionsBadge()`) must survive. Extract into a new function:
```javascript
function refreshIssueBadges() {
    Explorer.filterIssues();

    const badge = document.getElementById('issuesSectionBadge');
    if (badge) {
        badge.textContent = state.groupedErrors.length;
        badge.style.display = state.groupedErrors.length > 0 ? 'inline-flex' : 'none';
    }

    Explorer.updateValidationSummary();
    Explorer.updateSuggestionsBadge();
}
```
Export as `Explorer.refreshIssueBadges = refreshIssueBadges;`

**9. Remove `Explorer.stagedIssues` getter export** (lines 349-353).

**10. Remove `Explorer.computeStagedIssues` and `Explorer.updateStagedIssuesUI` exports** (lines 345-346).

**11. Simplify `loadIssuesForBadges()`** — Just fetches from server, no staged overlay. Error handling preserved: existing `try/catch` blocks with `console.error` remain unchanged.

**12. Simplify `loadSuggestionsForBadges()`** — Just fetches from server. Error handling preserved: existing `try/catch` blocks with `console.error` remain unchanged.

**13. Update module doc comment** (lines 1-7):
```javascript
/**
 * Nagios Bulk Editor - Explorer Badge Issues Module
 *
 * Handles badge and issue calculation for the explorer tree.
 * Consumes backend health-check data for all issue types via mapHealthCheckToState.
 * In candidate mode, passes ?candidate=1 so the server analyzes the candidate config.
 */
```

## Cross-Module Caller Impact

The following callers in other modules reference exports being removed. Each is covered by its own L-plan, but documented here for completeness:

| Caller File | Line | Call | Covered By | Action |
|-------------|------|------|------------|--------|
| `state-management.js` | 304-305 | `Explorer.computeStagedIssues()` | L07-state-management.md | REMOVE — replaced by `Explorer.refreshIssueBadges()` after `refreshAfterObjectChange()` |
| `object-editor.js` | 291 | `Explorer.computeStagedIssues()` | L08-object-editor.md | REMOVE — candidate health-check handles issues |
| `object-editor.js` | 292 | `Explorer.refreshCenterPaneIssueBadge()` | L08-object-editor.md | KEEP — export preserved |
| `dialogs.js` | 883, 1056 | `Explorer.computeStagedIssues()` | L08-dialogs.md | REMOVE — candidate health-check handles issues |
| `context-menu.js` | 576 | `Explorer.computeStagedIssues()` | L08-context-menu.md | REMOVE — candidate health-check handles issues |
| `tab-manager.js` | 71 | `Explorer.computeStagedIssues()` | L11-tab-manager.md | REMOVE — guarded by `if (Explorer.computeStagedIssues)` |
| `analysis-issues.js` | 106 | `Explorer.stagedIssues` | L10-analysis-issues.md | REMOVE — `state.allIssues.filter(...)` only |
| `analysis-issues.js` | 420, 572 | `Explorer.computeStagedIssues()` | L10-analysis-issues.md | REMOVE |

## UI Visual Parity

The following UI elements must remain visually identical after migration:

- **Issue count badge** (`#issuesSectionBadge`): Same position, same styling, same numeric count. The badge renders `state.groupedErrors.length` — this is unchanged; only the source of issues changes (server-only vs server+client).
- **Center pane issue badge** (`#centerCardIssue`): Same rendering via `Explorer.updateIssueBadge()` — function is unchanged.
- **Validation summary banner**: Same rendering via `Explorer.updateValidationSummary()` — function is unchanged.
- **Tree node badges**: Same rendering via `Explorer.buildTree()` — unchanged; badges read from `state.issuesByObject` which is still populated by `mapHealthCheckToState()`.
- **Suggestions main badge**: Same rendering via `Explorer.updateSuggestionsBadge()` — unchanged.
- **Section badges** (`#groupingSectionBadge`, `#templatesSectionBadge`, etc.): Same rendering via `Explorer.updateBadge()` — unchanged.

No CSS classes are added, removed, or renamed. No DOM structure changes. Badge colors, positions, and visibility logic are untouched.

## Audit Logging

This module is read-only — it calls `GET /api/health-check` and `GET /api/smart-grouping/suggest`, both of which are non-mutating endpoints. No audit logging is required for read-only operations. The backend health-check endpoint logs its own execution through the application logging system.

## Error Handling

All existing error handling is preserved:

| Function | Error Handling | Status |
|----------|---------------|--------|
| `loadIssuesForBadges()` | `try/catch` with `console.error('Failed to load issues for badges:', e)` | PRESERVED |
| `loadSuggestionsForBadges()` | `try/catch` with `console.error('Failed to load suggestions for badges:', e)` | PRESERVED |
| `refreshCenterPaneIssueBadge()` | Guard: `if (!state.editedObject) return; if (!issueBtn) return;` | PRESERVED |
| `getObjectIdentity()` | Graceful fallback: `nameField ? (obj.attributes[nameField] \|\| '') : (obj.attributes.name \|\| '')` | PRESERVED |

No error paths are removed or weakened. The removed functions (`computeStagedIssues`, etc.) had no error handling of their own — they were synchronous internal functions.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Add `?candidate=1` suffix to `loadIssuesForBadges()` health-check call | [ ] |
| 2 | Add `?candidate=1` suffix to `loadSuggestionsForBadges()` health-check call | [ ] |
| 3 | Add `?candidate=1` suffix to `loadSuggestionsForBadges()` smart-grouping call | [ ] |
| 4 | Remove `let stagedIssues = []` module state | [ ] |
| 5 | Remove `computeStagedIssues()` function (lines 110-199) | [ ] |
| 6 | Remove `updateStagedIssuesUI()` function (lines 202-231) | [ ] |
| 7 | Remove `resolveWarningsFromStagedTemplateEdits()` function (lines 310-336) | [ ] |
| 8 | Remove `buildEditedTemplatesMap()` function (lines 241-253) | [ ] |
| 9 | Remove `collectTemplateChainFields()` function (lines 272-302) | [ ] |
| 10 | Remove `parseMissingFields()` function (lines 258-266) | [ ] |
| 11 | Extract `refreshIssueBadges()` from useful `updateStagedIssuesUI()` logic | [ ] |
| 12 | Remove `Explorer.computeStagedIssues` export | [ ] |
| 13 | Remove `Explorer.updateStagedIssuesUI` export | [ ] |
| 14 | Remove `Explorer.stagedIssues` getter property | [ ] |
| 15 | Export `Explorer.refreshIssueBadges` | [ ] |
| 16 | Update module doc comment (remove staged issue references) | [ ] |
| 17 | Update `refreshCenterPaneIssueBadge` doc comment (staging → candidate) | [ ] |
| 18 | Remove `// Staged Issues (from pending edits)` section header comment | [ ] |
| 19 | Remove `// Bug 017` section header comment | [ ] |
| 20 | `npm run lint:js` passes | [ ] |
| 21 | Playwright validation passes (see below) | [ ] |

## Verification
- Issue badges update correctly in candidate mode
- Badge counts match server health-check data (no client-side staged issues missing)
- Center pane issue badge updates after health-check load
- Validation summary banner updates correctly
- No reference to `pendingEdits` or `stagedObjectDeletions` remains
- `npm run lint:js` passes
- `npx ruff check` passes (no Python in this file, but verify no cross-file breakage)
- No console errors in browser devtools

## Playwright Validation

Issue badges are visual UI elements that must be validated in a running browser. The following Playwright checks apply:

**Test: Issue badge renders after health-check load**
1. Navigate to explorer page
2. Wait for health-check data to load (badge appears)
3. Assert `#issuesSectionBadge` is visible and has numeric content > 0 (when issues exist)
4. Assert badge has `display: inline-flex` when count > 0

**Test: Issue badge updates in candidate mode**
1. Navigate to explorer page
2. Create a candidate edit that introduces a broken reference (e.g., rename a host referenced by a service)
3. Wait for badge to update
4. Assert `#issuesSectionBadge` count reflects the new issue

**Test: Center pane issue badge updates**
1. Navigate to explorer page, select an object with known issues
2. Assert `#centerCardIssue` badge shows the correct issue info
3. Verify badge content matches `Explorer.getObjectIssue()` output

**Test: No console errors on page load**
1. Navigate to explorer page
2. Wait for full load (badges visible)
3. Assert no `console.error` messages related to badge-issues

These tests validate UI visual parity (Commandment 2) and full functionality migration (Commandment 6).

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Module is read-only. `?candidate=1` directs health-check to analyze candidate directory, not live config. No mutations. |
| 2 | UI visual parity | COMPLIANT | All badge elements, CSS classes, DOM structure, and rendering functions unchanged. See "UI Visual Parity" section. |
| 3 | Full audit logging | COMPLIANT | Module makes only read-only API calls (`GET /api/health-check`, `GET /api/smart-grouping/suggest`). No mutations requiring audit logging. Backend logs its own execution. |
| 4 | Proper error handling | COMPLIANT | All existing `try/catch` blocks and guard clauses preserved. No error paths removed. See "Error Handling" section. |
| 5 | Dead code deletion | COMPLIANT | 7 functions removed: `computeStagedIssues`, `updateStagedIssuesUI`, `resolveWarningsFromStagedTemplateEdits`, `buildEditedTemplatesMap`, `collectTemplateChainFields`, `parseMissingFields`, plus `stagedIssues` array and getter. All are dead code in candidate mode. |
| 6 | Full functionality migration | COMPLIANT | Badge refresh logic from `updateStagedIssuesUI()` (lines 217-230) migrated to new `refreshIssueBadges()` function. All other removed code has no equivalent in candidate mode (server handles it). Cross-module callers documented. |
| 7 | Palo Alto candidate model | COMPLIANT | `?candidate=1` suffix follows copy-edit-apply model. Health-check analyzes candidate directory. |
| 8 | Change tracking document | COMPLIANT | See "Change Tracking" section with 21 items. |
| 9 | Complete planning before implementation | COMPLIANT | This plan fully specifies all changes, removals, migrations, and cross-module impacts before any code changes. |
| 10 | Linting enforcement | COMPLIANT | `npm run lint:js` required in verification. Change tracking item 20. |
| 11 | Playwright validation | COMPLIANT | Four Playwright test scenarios defined in "Playwright Validation" section. |
