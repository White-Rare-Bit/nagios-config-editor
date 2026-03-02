# L14 — `static/js/explorer/CLAUDE.md` — MODIFY

## Purpose
Update explorer module descriptions to reflect candidate mode terminology. Remove all staging references from the module index so the documentation accurately describes the post-migration codebase.

## Prerequisite Plans
- L07-main.md (state fields renamed)
- L07-data-loading.md (staging sync/poll replaced)
- L07-state-management.md (staging accessors removed)
- L08-file-operations.md (`afterStagingChange()` removed)
- L08-context-menu.md (`getOrCreatePendingEdit()` removed)
- L06-candidate-api.md (CandidateApi introduced)

## Scope
This plan modifies documentation only. It does NOT touch any JavaScript, Python, CSS, or HTML files. No runtime behavior changes. No UI changes.

## Changes

**1. Update `main.js` description:**
```markdown
<!-- BEFORE -->
| `main.js` | Namespace, state structure (allObjects, selections, staging maps, undo stack) |
<!-- AFTER -->
| `main.js` | Namespace, state structure (allObjects, selections, candidateActive, candidateDiff) |
```
**Rationale:** L07-main.md removes all staging Maps/Sets (`pendingEdits`, `stagedMoves`, `stagedCreations`, etc.) and `undoStack`. Replaces with `candidateActive` (boolean) and `candidateDiff` (object). Documentation must reflect this.

**2. Update `state-management.js` description:**
```markdown
<!-- BEFORE -->
| `state-management.js` | Stable key helpers, pending edit get/set, `refreshAfterObjectChange()` |
<!-- AFTER -->
| `state-management.js` | Stable key helpers, candidate badge computation, `refreshAfterObjectChange()` |
```
**Rationale:** L07-state-management.md removes `getPendingEdit()`, `setPendingEdit()`, `removePendingEdit()`, and all staging accessors. Adds `computeCandidateBadges()` and `hasCandidateChanges()`.

**3. Update `data-loading.js` description:**
```markdown
<!-- BEFORE -->
| `data-loading.js` | API calls, staging sync/polling, initial load |
<!-- AFTER -->
| `data-loading.js` | API calls, candidate session polling, initial load |
```
**Rationale:** L07-data-loading.md removes `saveStagedChanges()`, `loadStagedChanges()`, `startStagingPoll()`. Replaces with `startCandidatePoll()`, `refreshCandidateDiff()`, `applyCandidateChanges()`.

**4. Update `file-operations.js` description:**
```markdown
<!-- BEFORE -->
| `file-operations.js` | Right pane: file tree, navigation, folder ops. Helper: `afterStagingChange()` |
<!-- AFTER -->
| `file-operations.js` | Right pane: file tree, navigation, folder ops via CandidateApi |
```
**Rationale:** L08-file-operations.md removes `afterStagingChange()` and rewrites all file/folder mutation calls to use CandidateApi instead of client-side staging arrays.

**5. Update `context-menu.js` description:**
```markdown
<!-- BEFORE -->
| `context-menu.js` | Right-click menus, bulk actions. Helper: `getOrCreatePendingEdit(obj)` |
<!-- AFTER -->
| `context-menu.js` | Right-click menus, bulk actions via CandidateApi |
```
**Rationale:** L08-context-menu.md removes `getOrCreatePendingEdit()` and rewrites mutation calls to use CandidateApi.

## Dead Code Audit
After this plan is applied, no module description in `static/js/explorer/CLAUDE.md` should reference:
- `staging` (the word, in any form)
- `pendingEdits`, `pendingEdit`, `stagedMoves`, `stagedCreations`, or any `staged*` state field
- `afterStagingChange()` or `getOrCreatePendingEdit()`
- `undo stack` (server-side git undo replaces client-side undo stack)

Modules NOT touched by this plan (no staging references in their descriptions):
- `constants.js` — already generic
- `app.js` — already generic
- `object-editor.js` — already generic
- `dialogs.js` — already generic
- `drag-drop.js` — already generic
- `analysis.js` — already generic
- `analysis-issues.js` — already generic
- `analysis-suggestions.js` — already generic
- `badge-issues.js` — already generic
- `relations-loader.js` — already generic
- `impact-section.js` — already generic
- `ui-utils.js` — already generic

## Verification
- `grep -i "staging" static/js/explorer/CLAUDE.md` returns zero matches
- `grep -i "pendingEdit" static/js/explorer/CLAUDE.md` returns zero matches
- `grep -i "undo stack" static/js/explorer/CLAUDE.md` returns zero matches
- `grep "CandidateApi" static/js/explorer/CLAUDE.md` returns matches in file-operations and context-menu descriptions
- `grep "candidate" static/js/explorer/CLAUDE.md` returns matches in main, state-management, and data-loading descriptions
- Visual diff review: only the 5 table rows listed above change; all other rows remain identical

## Lint Compliance
This plan modifies only a Markdown file. No JavaScript or Python changes, so no ESLint or Ruff checks apply. The Markdown must use consistent table formatting matching the existing file style (pipe-delimited, single space padding).

## Playwright Validation
No Playwright tests required for this plan. This is a documentation-only change with zero runtime impact. The Playwright tests written for L07 and L08 plans validate the actual code changes that this documentation describes.

## Change Tracking
This plan is tracked in L00-migration-inventory.md under Section 2 (JavaScript Frontend). It covers the documentation facet of the explorer module migration. The code changes it documents are covered by:
- L07-main.md, L07-data-loading.md, L07-state-management.md (state and data layer)
- L08-file-operations.md, L08-context-menu.md (UI layer)

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Documentation-only change. No config mutation of any kind. The updated descriptions accurately reflect the candidate model where all edits go to CandidateApi (server-side candidate directory) and nothing touches live config until Apply. |
| 2 | UI visual parity | COMPLIANT | No UI changes. This plan modifies only a Markdown documentation file. |
| 3 | Full audit logging | N/A | Documentation-only change. No operations to audit. |
| 4 | Proper error handling | N/A | Documentation-only change. No code execution paths. |
| 5 | Dead code deletion | COMPLIANT | All stale staging terminology is removed from module descriptions. Dead Code Audit section above enumerates every term that must not survive. No staging references left behind. |
| 6 | Full functionality migration | COMPLIANT | All 5 module descriptions that reference staging concepts are updated. All 12 modules with generic descriptions are verified to need no changes. No module description dropped or overlooked. |
| 7 | Palo Alto candidate model | COMPLIANT | Updated descriptions reference CandidateApi and candidate session polling, reflecting the Palo Alto copy-edit-apply model. |
| 8 | Change tracking document | COMPLIANT | Change Tracking section links this plan to L00-migration-inventory.md and lists all prerequisite L-plans whose code changes this documentation reflects. |
| 9 | Complete planning before implementation | COMPLIANT | All 5 text changes are fully specified with exact before/after content. Rationale provided for each. Verification steps defined. |
| 10 | Linting enforcement | COMPLIANT | Lint Compliance section confirms: Markdown-only change, no ESLint/Ruff applicable. Table formatting follows existing file conventions. |
| 11 | Playwright validation | COMPLIANT | Playwright Validation section confirms: no runtime changes, no tests needed. References L07/L08 Playwright tests that validate the underlying code changes. |
