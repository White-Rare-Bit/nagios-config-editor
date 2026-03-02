# L06 — `static/js/session-manager.js` — MODIFY

## Purpose
Rename `getStagingHeaders` to `getSessionHeaders` to remove staging terminology as part of the candidate-model migration.

## Candidate Model Context
This rename supports the Palo Alto candidate model (Commandment 7). The function provides session identification headers for API requests. Its functionality is unchanged — only the name is updated to reflect that the system now uses candidate-config semantics rather than staging semantics.

## Removal Audit
- `getStagingHeaders()` — renamed to `getSessionHeaders()`. Same functionality, new name. No functionality lost.
- `window.getStagingHeaders` global — renamed to `window.getSessionHeaders`.
- **Note:** `Explorer.getStagingHeaders` in `data-loading.js:81` is a separate duplicate definition; it is dead code and will be removed in L07, not here.

## Cross-File Dependencies
This rename MUST be applied in lockstep with:
- **L06-api-client.md** — updates the single call site (`getStagingHeaders()` at `api-client.js:82`)
- **L06-eslint-config.md** — updates the ESLint global from `getStagingHeaders` to `getSessionHeaders`

All three L06 changes must be applied atomically (same commit) to avoid lint or runtime breakage.

## Live Config Safety
This change is a pure JavaScript function rename. No backend code is modified. No Nagios config files are read, written, or mutated. Compliant with Commandment 1 (no live config mutation until Apply).

## Current Code (lines 57-74)
```javascript
/**
 * Get standard headers for staging API requests.
 * Includes Content-Type and session ID.
 * @returns {object} Headers object for fetch requests
 */
function getStagingHeaders() {
    return {
        'Content-Type': 'application/json',
        'X-Session-Id': getSessionId()
    };
}

// Export to global scope for backward compatibility
window.getSessionId = getSessionId;
window.getUserIdentity = getUserIdentity;
window.setUserIdentity = setUserIdentity;
window.hasUserIdentity = hasUserIdentity;
window.getStagingHeaders = getStagingHeaders;
```

## Changes

**1. Rename function (line 62)**:
```javascript
// BEFORE
function getStagingHeaders() {
// AFTER
function getSessionHeaders() {
```

**2. Update JSDoc (line 58)**:
```javascript
// BEFORE
 * Get standard headers for staging API requests.
// AFTER
 * Get standard headers for API requests requiring session identification.
```

**3. Update global export (line 74)**:
```javascript
// BEFORE
window.getStagingHeaders = getStagingHeaders;
// AFTER
window.getSessionHeaders = getSessionHeaders;
```

**4. Update module docstring (line 5)**:
```javascript
// BEFORE
 * and staging headers for API calls.
// AFTER
 * and session headers for API calls.
```

## Error Handling
No error handling changes required. The function's behavior is identical before and after the rename — it returns a plain object with `Content-Type` and `X-Session-Id` headers. No exceptions are thrown or caught. No silent failures introduced.

## Audit Logging
Not applicable. This is a frontend-only rename with no backend API changes. No new operations are introduced that would require audit logging. Existing audit logging through `audit_service.py` is unaffected.

## Verification
- `npm run lint:js` passes (requires L06-eslint-config.md applied first)
- No references to `getStagingHeaders` remain in this file
- `grep -rn "getStagingHeaders" static/js/session-manager.js` returns zero matches
- `grep -rn "getSessionHeaders" static/js/session-manager.js` returns the new function definition and global export

## Playwright Validation
Not applicable for this change. This is an internal function rename with no user-visible behavior change. No UI text, buttons, or workflows are altered. Existing Playwright tests that exercise API-backed operations will implicitly validate that the renamed function still provides correct headers.

## Change Tracking

- [ ] Rename `getStagingHeaders` to `getSessionHeaders` at line 62
- [ ] Update JSDoc comment at line 58
- [ ] Update `window.getStagingHeaders` export to `window.getSessionHeaders` at line 74
- [ ] Update module docstring at line 5
- [ ] Coordinate with L06-api-client.md (update call site)
- [ ] Coordinate with L06-eslint-config.md (update global definition)
- [ ] Run `npm run lint:js` — passes
- [ ] Run `grep -rn "getStagingHeaders" static/js/session-manager.js` — zero matches

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Pure frontend rename. No config files touched.
- [x] **C2 — UI visual parity.** No user-facing text or visual changes. Internal JS function rename only.
- [x] **C3 — Full audit logging.** N/A — no backend or API changes. Existing audit logging unaffected.
- [x] **C4 — Proper error handling.** No error paths changed. Function returns same object. No silent failures.
- [x] **C5 — Dead code deletion.** Old `getStagingHeaders` name fully replaced; no dead references left in this file. Separate `Explorer.getStagingHeaders` dead code handled by L07.
- [x] **C6 — Full functionality migration.** Identical functionality under new name. Zero functionality lost.
- [x] **C7 — Palo Alto candidate model.** Rename removes staging terminology in support of candidate-config migration.
- [x] **C8 — Change tracking document.** Change tracking checklist included above.
- [x] **C9 — Complete planning before implementation.** This plan fully specifies all changes before any code is modified.
- [x] **C10 — Linting enforcement.** Verification includes `npm run lint:js`. ESLint global updated in companion L06-eslint-config.md.
- [x] **C11 — Playwright validation.** Assessed as not applicable — internal rename with no user-visible behavior change. Existing Playwright tests provide implicit coverage.
