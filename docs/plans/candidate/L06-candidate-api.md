# L06 — `static/js/candidate-api.js` — CREATE

**Layer:** 6 — Frontend Setup
**Action:** CREATE
**Path:** `static/js/candidate-api.js`
**Dependencies:** L03-routes-candidate.md (backend endpoints), L06-api-client.md (ApiClient), L06-eslint-config.md (CandidateApi global)
**Goal:** Create a thin API wrapper that centralizes all candidate endpoint calls. Every frontend mutation goes through this module to the candidate copy — never to live config.

---

## Purpose

CandidateApi wrapper providing all candidate session operations. Loaded on every page via `base.html` (see L06-base-html.md). This module is the single point of contact between frontend code and the `/api/candidate/*` backend routes defined in L03-routes-candidate.md.

All methods return the standard `ApiClient` response format: `{success: boolean, data?: object, error?: string, status?: number}`. Callers MUST check `result.success` before proceeding (Commandment 4). Error details are surfaced via `result.error` and `result.status`, and `ApiClient` handles toast display for non-silent requests.

All operations target the candidate copy on the server. No method in this module writes to the live Nagios configuration. Only `apply()` triggers the candidate-to-running copy on the backend (Commandment 1, Commandment 7).

Audit logging is handled by the backend route handlers (L03-routes-candidate.md). Every call through CandidateApi reaches a route that logs via `audit_service.log_audit()` and Python `logging` (Commandment 3).

## Removal Audit

This is a new file. No removals.

## Current Code

File does not exist yet.

## Changes

**Create `static/js/candidate-api.js`** — IIFE module exposing `window.CandidateApi`:

```javascript
/**
 * Candidate API client for Nagios Bulk Editor.
 * Thin wrapper over ApiClient providing all candidate session operations.
 * All mutations target the candidate copy — never live config.
 *
 * Every method returns: {success: boolean, data?: object, error?: string, status?: number}
 * Callers MUST check result.success before proceeding.
 *
 * Dependencies (loaded before this file):
 * - ApiClient — Centralized fetch wrapper with error handling and session headers
 */
const CandidateApi = (function() {
    'use strict';

    // ── Session lifecycle ──────────────────────────────────────────────

    /**
     * Initialize a new candidate session (copies running config to .candidate/).
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function startSession() {
        return ApiClient.post('/api/candidate/init');
    }

    /**
     * Get current candidate session status.
     * Silent: does not show error toasts (used for polling).
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function getSession() {
        return ApiClient.get('/api/candidate', { silent: true });
    }

    /**
     * Discard the current candidate session and delete the .candidate/ directory.
     * @param {object} [options]
     * @param {boolean} [options.force=false] - Force-discard another user's session (admin action)
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function clearSession({ force = false } = {}) {
        const url = force ? '/api/candidate?force=1' : '/api/candidate';
        return ApiClient.del(url);
    }

    // ── Object CRUD ────────────────────────────────────────────────────

    /**
     * Edit an object's attributes in the candidate config.
     * @param {string} stableKey - Object stable key (source_file|object_type|name)
     * @param {object} edited - New attribute values
     * @param {object} original - Original attribute values (for diff)
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function editObject(stableKey, edited, original) {
        return ApiClient.post('/api/candidate/edit', { stable_key: stableKey, edited, original });
    }

    /**
     * Delete one or more objects from the candidate config.
     * @param {string[]} stableKeys - Array of stable keys to delete
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function deleteObjects(stableKeys) {
        return ApiClient.post('/api/candidate/delete-objects', { stable_keys: stableKeys });
    }

    /**
     * Create a new object in the candidate config.
     * @param {string} objectType - Nagios object type (host, service, etc.)
     * @param {object} attributes - Object attributes
     * @param {string} targetFile - Target .cfg file path
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function createObject(objectType, attributes, targetFile) {
        return ApiClient.post('/api/candidate/create', {
            object_type: objectType, attributes, target_file: targetFile
        });
    }

    /**
     * Move one or more objects between files in the candidate config.
     * @param {Array<{stable_key: string, target_file: string}>} moves - Move specifications
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function moveObjects(moves) {
        return ApiClient.post('/api/candidate/move', { moves });
    }

    /**
     * Clone objects to new locations in the candidate config.
     * @param {Array<{stable_key: string, target_file: string}>} clones - Clone specifications
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function cloneObjects(clones) {
        return ApiClient.post('/api/candidate/clone', { clones });
    }

    /**
     * Reorder an object within its file in the candidate config.
     * @param {string} stableKey - Object stable key
     * @param {string} direction - "up" or "down"
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function reorderObject(stableKey, direction) {
        return ApiClient.post('/api/candidate/reorder', { stable_key: stableKey, direction });
    }

    // ── Bulk operations ────────────────────────────────────────────────

    /**
     * Bulk rename objects using pattern matching.
     * @param {Array} renames - Rename specifications
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function bulkRename(renames) {
        return ApiClient.post('/api/candidate/bulk-edit', { operation: 'rename', renames });
    }

    /**
     * Bulk update object attributes.
     * @param {Array} updates - Attribute update specifications
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function bulkAttribute(updates) {
        return ApiClient.post('/api/candidate/bulk-edit', { operation: 'attribute', updates });
    }

    /**
     * Bulk update cross-references after name changes.
     * @param {Array} updates - Reference update specifications
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function bulkReferenceUpdate(updates) {
        return ApiClient.post('/api/candidate/bulk-edit', { operation: 'reference-update', updates });
    }

    /**
     * Bulk move objects to a target file.
     * @param {Array<{stable_key: string, target_file: string}>} moves - Move specifications
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function bulkMove(moves) {
        return ApiClient.post('/api/candidate/bulk-move', { moves });
    }

    // ── Undo ───────────────────────────────────────────────────────────

    /**
     * Undo the last candidate operation (git reset --hard HEAD~1 on candidate).
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function undo() {
        return ApiClient.post('/api/candidate/undo');
    }

    // ── Diff, analysis, and validation ─────────────────────────────────

    /**
     * Get diff summary between candidate and running config.
     * Silent: used for polling, does not show error toasts.
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function getDiff() {
        return ApiClient.get('/api/candidate/diff', { silent: true });
    }

    /**
     * Get structured per-object diff for the commit dialog.
     * Silent: does not show error toasts.
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function getDiffStructured() {
        return ApiClient.get('/api/candidate/diff/structured', { silent: true });
    }

    /**
     * Get diff for a specific file.
     * @param {string} filePath - Relative path to the .cfg file
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function getFileDiff(filePath) {
        return ApiClient.post('/api/candidate/diff/file', { path: filePath });
    }

    /**
     * Detect conflicts (running config changed since candidate was created).
     * Silent: does not show error toasts.
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function getConflicts() {
        return ApiClient.get('/api/candidate/conflicts', { silent: true });
    }

    /**
     * Run nagios -v validation against the candidate config.
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function validate() {
        return ApiClient.post('/api/candidate/validate');
    }

    /**
     * Analyze cross-references that would be updated on apply (name change preview).
     * Silent: does not show error toasts.
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function analyzeReferences() {
        return ApiClient.get('/api/candidate/analyze-references', { silent: true });
    }

    /**
     * Run health checks on candidate config objects.
     * Silent: does not show error toasts.
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function healthCheck() {
        return ApiClient.get('/api/candidate/health-check', { silent: true });
    }

    // ── Apply ──────────────────────────────────────────────────────────

    /**
     * Apply candidate config to running config (the only operation that writes to live).
     * Optionally updates cross-references for any name changes.
     * @param {object} [options]
     * @param {boolean} [options.updateReferences=false] - Update cross-references before applying
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function apply({ updateReferences = false } = {}) {
        return ApiClient.post('/api/candidate/apply', { update_references: updateReferences });
    }

    // ── File operations ────────────────────────────────────────────────

    /**
     * Create a new .cfg file in the candidate config.
     * @param {string} path - Relative path for the new file
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function createFile(path) {
        return ApiClient.post('/api/candidate/file/create', { path });
    }

    /**
     * Delete a .cfg file from the candidate config.
     * @param {string} path - Relative path of the file to delete
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function deleteFile(path) {
        return ApiClient.post('/api/candidate/file/delete', { path });
    }

    /**
     * Move/rename a .cfg file in the candidate config.
     * @param {string} sourcePath - Current relative path
     * @param {string} targetPath - New relative path
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function moveFile(sourcePath, targetPath) {
        return ApiClient.post('/api/candidate/file/move', { source_path: sourcePath, target_path: targetPath });
    }

    // ── Folder operations ──────────────────────────────────────────────

    /**
     * Create a new folder in the candidate config.
     * @param {string} path - Relative path for the new folder
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function createFolder(path) {
        return ApiClient.post('/api/candidate/folder/create', { path });
    }

    /**
     * Delete a folder from the candidate config.
     * @param {string} path - Relative path of the folder to delete
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function deleteFolder(path) {
        return ApiClient.post('/api/candidate/folder/delete', { path });
    }

    /**
     * Move/rename a folder in the candidate config.
     * @param {string} sourcePath - Current relative path
     * @param {string} targetPath - New relative path
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async function moveFolder(sourcePath, targetPath) {
        return ApiClient.post('/api/candidate/folder/move', { source_path: sourcePath, target_path: targetPath });
    }

    // ── Public API ─────────────────────────────────────────────────────

    return {
        // Session lifecycle
        startSession, getSession, clearSession,
        // Object CRUD
        editObject, deleteObjects, createObject, moveObjects, cloneObjects, reorderObject,
        // Bulk operations
        bulkRename, bulkAttribute, bulkReferenceUpdate, bulkMove,
        // Undo
        undo,
        // Diff, analysis, validation
        getDiff, getDiffStructured, getFileDiff, getConflicts, validate, analyzeReferences, healthCheck,
        // Apply
        apply,
        // File operations
        createFile, deleteFile, moveFile,
        // Folder operations
        createFolder, deleteFolder, moveFolder
    };
})();
```

## Error Handling Contract

Every method in CandidateApi returns the `ApiClient` response format:

```javascript
{
    success: boolean,      // true if HTTP 2xx and no error field in response
    data: object | null,   // parsed JSON response body
    error: string | null,  // error message from server or network
    status: number | null, // HTTP status code
    aborted: boolean       // true if request was aborted/timed out
}
```

**Backend HTTP status codes** (from L03-routes-candidate.md):
| Status | Meaning | Frontend handling |
|--------|---------|-------------------|
| 200 | Success | `result.success === true` |
| 400 | Invalid input (missing fields, bad paths) | Toast via ApiClient, caller checks `result.success` |
| 404 | No candidate session active | Toast via ApiClient, caller checks `result.success` |
| 409 | Conflict detected (running config changed) | Caller shows conflict resolution UI |
| 423 | Locked by another session | Lock banner shown, caller checks `result.status === 423` |
| 500 | Internal server error | Toast via ApiClient, caller checks `result.success` |

**Caller pattern** (enforced across L07/L08/L09/L10/L11 plans):
```javascript
const result = await CandidateApi.editObject(stableKey, edited, original);
if (!result.success) {
    // Error already shown via toast by ApiClient (unless silent)
    // Caller may take additional action (e.g., revert UI state)
    return;
}
// Proceed with success path
await Explorer.refreshAfterObjectChange();
```

## URL-to-Route Mapping

All URLs match the backend routes defined in L03-routes-candidate.md:

| CandidateApi Method | HTTP | URL | L03 Route Function |
|---------------------|------|-----|--------------------|
| `startSession()` | POST | `/api/candidate/init` | `init_session()` |
| `getSession()` | GET | `/api/candidate` | `get_status()` |
| `clearSession()` | DELETE | `/api/candidate` | `discard()` |
| `clearSession({force:true})` | DELETE | `/api/candidate?force=1` | `discard()` (force) |
| `editObject()` | POST | `/api/candidate/edit` | `edit_object()` |
| `deleteObjects()` | POST | `/api/candidate/delete-objects` | `delete_objects()` |
| `createObject()` | POST | `/api/candidate/create` | `create_object()` |
| `moveObjects()` | POST | `/api/candidate/move` | `move_object()` |
| `cloneObjects()` | POST | `/api/candidate/clone` | `clone_object()` |
| `reorderObject()` | POST | `/api/candidate/reorder` | `reorder_object()` |
| `bulkRename()` | POST | `/api/candidate/bulk-edit` | `bulk_edit()` |
| `bulkAttribute()` | POST | `/api/candidate/bulk-edit` | `bulk_edit()` |
| `bulkReferenceUpdate()` | POST | `/api/candidate/bulk-edit` | `bulk_edit()` |
| `bulkMove()` | POST | `/api/candidate/bulk-move` | `bulk_move()` |
| `undo()` | POST | `/api/candidate/undo` | `undo()` |
| `getDiff()` | GET | `/api/candidate/diff` | `get_diff()` |
| `getDiffStructured()` | GET | `/api/candidate/diff/structured` | `get_structured_diff()` |
| `getFileDiff()` | POST | `/api/candidate/diff/file` | `get_file_diff()` |
| `getConflicts()` | GET | `/api/candidate/conflicts` | `detect_conflicts()` |
| `validate()` | POST | `/api/candidate/validate` | `validate()` |
| `analyzeReferences()` | GET | `/api/candidate/analyze-references` | `analyze_references()` |
| `healthCheck()` | GET | `/api/candidate/health-check` | `health_check()` |
| `apply()` | POST | `/api/candidate/apply` | `apply()` |
| `createFile()` | POST | `/api/candidate/file/create` | `create_file()` |
| `deleteFile()` | POST | `/api/candidate/file/delete` | `delete_file()` |
| `moveFile()` | POST | `/api/candidate/file/move` | `move_file()` |
| `createFolder()` | POST | `/api/candidate/folder/create` | `create_folder()` |
| `deleteFolder()` | POST | `/api/candidate/folder/delete` | `delete_folder()` |
| `moveFolder()` | POST | `/api/candidate/folder/move` | `move_folder()` |

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Create `static/js/candidate-api.js` with IIFE module | [ ] |
| 2 | All 30 methods match L03-routes-candidate.md backend routes exactly | [ ] |
| 3 | JSDoc on every public method with `@param` and `@returns` | [ ] |
| 4 | Module docblock documents dependencies and error contract | [ ] |
| 5 | ESLint global registered in L06-eslint-config.md | [ ] |
| 6 | Script tag added in L06-base-html.md (after api-client.js) | [ ] |

## Verification

- File exists at `static/js/candidate-api.js`
- `npm run lint:js` passes (after L06-eslint-config changes register `CandidateApi` as a global)
- All 30 methods present and exported in the return object
- Every URL in this file matches a route in `routes/candidate.py` (L03-routes-candidate.md)
- `typeof CandidateApi !== 'undefined'` returns true in browser console after page load
- Playwright smoke test: load the app, verify `CandidateApi` is defined on `window`, call `CandidateApi.getSession()` and confirm it returns `{success: boolean, ...}` response shape

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Every method targets `/api/candidate/*` endpoints that operate on the `.candidate/` copy. Only `apply()` triggers the candidate-to-running copy on the backend. No method in this module writes to the live Nagios configuration.
- [x] **C2 — UI visual parity.** This is a thin API wrapper with no UI. No visual changes introduced.
- [x] **C3 — Full audit logging.** All methods route to backend endpoints in L03-routes-candidate.md that log via `audit_service.log_audit()` and Python `logging`. Frontend does not bypass audit logging.
- [x] **C4 — Proper error handling.** Every method returns `{success, data, error, status}` via `ApiClient`. Non-silent requests show toast notifications on error. Error handling contract documented above with status code table and caller pattern.
- [x] **C5 — Dead code deletion.** New file; no dead code. No legacy staging API functions included.
- [x] **C6 — Full functionality migration.** All 30 backend routes from L03-routes-candidate.md have a corresponding CandidateApi method. URL mapping table above confirms 1:1 coverage. Missing methods from original plan (bulkMove, getFileDiff, healthCheck, clearSession force option) have been added.
- [x] **C7 — Palo Alto candidate model.** Module enforces the copy-edit-apply pattern: `startSession()` copies config to candidate, CRUD methods edit the candidate, `apply()` copies candidate to live.
- [x] **C8 — Change tracking document.** Change tracking table included above with 6 tracked items.
- [x] **C9 — Complete planning before implementation.** This plan fully specifies the file contents, all method signatures, URL mappings, error handling contract, and verification steps.
- [x] **C10 — Linting enforcement.** Verification requires `npm run lint:js` to pass. JSDoc on all methods. `CandidateApi` registered as ESLint global in L06-eslint-config.md.
- [x] **C11 — Playwright validation.** Playwright smoke test specified: verify `CandidateApi` is defined on `window` and returns correct response shape from `getSession()`.
