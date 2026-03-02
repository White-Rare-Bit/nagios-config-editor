# L06 — `static/js/api-client.js` — MODIFY

## Purpose
Update the single call from `getStagingHeaders()` to `getSessionHeaders()` and update all related comments. This is a rename-only change — no functionality is added, removed, or altered. Part of the Layer 6 candidate model migration (removing staging terminology from frontend).

## Removal Audit
- `getStagingHeaders()` call — replaced with `getSessionHeaders()`. Same headers returned. No functionality change.
- Three JSDoc comments referencing "staging headers" — updated to "session headers". Documentation-only.
- One dependency comment referencing `getStagingHeaders()` — updated. Documentation-only.

**No functionality removed.** All error handling (`handleResponse`, `handleError`, abort/timeout support, silent mode, error prefixes) is preserved exactly as-is.

## Current Code (line 82)
```javascript
const fetchOptions = {
    method,
    headers: getStagingHeaders(),
    signal: opts.signal
};
```

## Changes

**1. Update header function call (line 82)**:
```javascript
// BEFORE
headers: getStagingHeaders(),
// AFTER
headers: getSessionHeaders(),
```

**2. Update dependency comment (line 7)**:
```javascript
// BEFORE
 * - getStagingHeaders() - Get session/staging headers including Content-Type
// AFTER
 * - getSessionHeaders() - Get session headers including Content-Type
```

**3. Update JSDoc comments (lines 98, 109, 119)**:
```javascript
// BEFORE (3 occurrences)
 * Make a JSON POST request with staging headers.
 * Make a JSON GET request with staging headers.
 * Make a DELETE request with staging headers.
// AFTER
 * Make a JSON POST request with session headers.
 * Make a JSON GET request with session headers.
 * Make a DELETE request with session headers.
```

## Dependency Order
- **Requires**: L06-session-manager.md (defines `getSessionHeaders()` that this file calls)
- **Requires**: L06-eslint-config.md (renames the global from `getStagingHeaders` to `getSessionHeaders`)
- **Required by**: Nothing — this is a leaf consumer of the renamed function

## Verification
- `grep -n "getStagingHeaders\|staging" static/js/api-client.js` returns no matches after changes
- `npm run lint:js` passes (depends on L06-eslint-config.md being applied first)
- All existing error handling paths (`handleResponse`, `handleError`, abort support) are untouched
- Manual: open any page, confirm API calls still include `X-Session-Id` and `Content-Type` headers in DevTools Network tab

## Change Tracking
Tracked in `docs/plans/2026-02-27-candidate-config-index.md` under Layer 6:
- [ ] `static/js/api-client.js` — MODIFY — Update call to `getSessionHeaders`

## Commandments Compliance

- [x] **C1: No live config mutation until Apply.** This file is a frontend fetch wrapper. It does not write to config. Mutation control is enforced server-side. No change to mutation behavior.
- [x] **C2: UI visual parity.** No UI changes. Rename is internal to JavaScript; no visible elements affected.
- [x] **C3: Full audit logging.** Not applicable — this is a client-side JS file. Audit logging is handled by backend routes that this client calls. No audit logging code exists in this file before or after.
- [x] **C4: Proper error handling.** All error handling (`handleResponse`, `handleError`, abort/timeout, silent mode, toast notifications) is preserved exactly as-is. No error paths altered.
- [x] **C5: Dead code deletion.** No dead code introduced. The old `getStagingHeaders` reference is replaced (not left behind). Grep verification confirms zero remaining references.
- [x] **C6: Full functionality migration.** Same headers returned (`Content-Type` + `X-Session-Id`). Same function signature. Same call site. Rename only — no functionality lost or altered.
- [x] **C7: Palo Alto candidate model.** This change is part of Layer 6 (frontend foundation) of the candidate model migration. Removes staging terminology from the API client to align with the new candidate-based architecture.
- [x] **C8: Change tracking document.** Referenced in `docs/plans/2026-02-27-candidate-config-index.md` Layer 6 checklist item.
- [x] **C9: Complete planning before implementation.** All four changes enumerated with exact BEFORE/AFTER, line numbers, and grep verification.
- [x] **C10: Linting enforcement.** Verification includes `npm run lint:js` pass. Depends on L06-eslint-config.md renaming the global declaration.
- [x] **C11: Playwright validation.** Not sensible for this change — it is a single function rename with no behavioral or UI impact. Existing Playwright tests (if any exercise API calls) will continue to pass since request headers are unchanged in content.
