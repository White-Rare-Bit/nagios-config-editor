# L10 — `static/js/dependencies.js` — MODIFY

## Purpose
Add candidate session detection and `?candidate=1` suffix to dependency graph data fetch.

No live configuration is mutated by this module. The `/api/dependencies` call is a read-only `GET` request that returns graph node/edge data. The `?candidate=1` suffix directs the server to return dependency data from the candidate directory rather than the running config (Palo Alto model: copy config to candidate, edit candidate, apply candidate to live).

## Removal Audit
No staging references (`pendingEdits`, `stagedObjectDeletions`, `saveStagedChanges`) exist in this file. Only the candidate suffix addition is needed for accurate graph data.

## Changes

**1. Add candidate suffix to dependency fetch** (line 1164):
```javascript
// Check for active candidate session before fetching
const sessionResult = await CandidateApi.getSession();
const suffix = sessionResult.data?.active ? '?candidate=1' : '';
const response = await fetch(`/api/dependencies${suffix}`);
```

Note: This file is a standalone page module (not part of the Explorer IIFE), so it does not have access to `Explorer.state.candidateActive`. It must check via `CandidateApi.getSession()` directly.

## UI Visual Parity

The following UI elements must remain visually identical after migration:

- **Cytoscape graph canvas**: Same layout, same node/edge rendering, same colors and icons.
- **Graph controls**: Same view mode presets, quick view presets, edge category toggles.
- **Node/edge styling**: Driven by `dependencies-config.js` — unchanged.

No CSS classes are added, removed, or renamed. No DOM structure changes.

## Audit Logging

This module is read-only — it calls `GET /api/dependencies`, which is a non-mutating endpoint. No audit logging is required for read-only operations. The backend dependencies endpoint logs its own execution through the application logging system.

## Error Handling

Existing error handling is preserved:

| Function | Error Handling | Status |
|----------|---------------|--------|
| `loadAllData()` | `try/catch` with `console.error('Error loading data:', error)` | PRESERVED |
| `loadGraphState()` | `try/catch` with `console.error('Error loading graph state:', e)` | PRESERVED |

The new `CandidateApi.getSession()` call is wrapped in the existing `try/catch` — if it fails, the suffix defaults to empty string (non-candidate mode), which is a safe fallback.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Import or reference CandidateApi for session detection | [ ] |
| 2 | Add `CandidateApi.getSession()` call in `loadAllData()` | [ ] |
| 3 | Add `?candidate=1` suffix to `/api/dependencies` fetch (line 1164) | [ ] |
| 4 | `npm run lint:js` passes | [ ] |
| 5 | Playwright validation passes (see below) | [ ] |

## Verification
- Dependencies page loads without errors
- Graph reflects candidate objects when candidate session is active
- Graph reflects running config objects when no candidate session
- `npm run lint:js` passes
- `python3 -m ruff check` passes (no Python in this file, verify no cross-file breakage)
- No console errors in browser devtools

## Playwright Validation

**Test: Dependencies page loads with graph**
1. Navigate to dependencies page
2. Wait for graph to render (Cytoscape canvas visible)
3. Assert nodes are present in the graph

**Test: Dependencies graph updates in candidate mode**
1. Start a candidate session (via API or UI)
2. Navigate to dependencies page
3. Assert graph loads with candidate data
4. Assert no console errors

**Test: No console errors on page load**
1. Navigate to dependencies page
2. Wait for full load
3. Assert no `console.error` messages related to dependencies

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Module is read-only. `?candidate=1` reads candidate directory data. No mutations. |
| 2 | UI visual parity | COMPLIANT | Graph rendering, controls, and styling unchanged. See "UI Visual Parity" section. |
| 3 | Full audit logging | COMPLIANT | Read-only GET request — no audit logging needed. Backend logs its own execution. See "Audit Logging" section. |
| 4 | Proper error handling | COMPLIANT | Existing try/catch blocks preserved. CandidateApi failure falls back safely. See "Error Handling" section. |
| 5 | Dead code deletion | N/A | No staging-specific code exists in this file to remove. |
| 6 | Full functionality migration | COMPLIANT | Dependency graph functionality fully preserved — only data source changes (candidate vs live). |
| 7 | Palo Alto candidate model | COMPLIANT | `?candidate=1` suffix follows copy-edit-apply model. Graph shows candidate state. |
| 8 | Change tracking document | COMPLIANT | See "Change Tracking" section with 5 items. |
| 9 | Complete planning before implementation | COMPLIANT | This plan fully specifies all changes before any code changes. |
| 10 | Linting enforcement | COMPLIANT | `npm run lint:js` required in verification and change tracking (item 4). |
| 11 | Playwright validation | COMPLIANT | Three Playwright test scenarios defined in "Playwright Validation" section. |
