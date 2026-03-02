# L09 — `static/js/lock-manager.js` — MODIFY

## Purpose
Rewrite to poll candidate session status instead of staging lock.

## Removal Audit
- **Line 26**: `ApiClient.get('/api/staging/lock', { silent: true })` in `checkLockStatus()` — REPLACED by `CandidateApi.getSession()`.
- **Line 95**: `ApiClient.post('/api/staging/lock/break', {}, { silent: true })` in `breakLock()` — REPLACED by `ApiClient.post('/api/candidate/session/break', ...)`.
- **Line 116**: `showToast('Lock broken - staging cleared', 'success')` UI text — UPDATED to candidate-appropriate text (e.g., "Session broken successfully").

3 staging references total. All accounted for.

## Changes

**1. Rewrite `checkLockStatus()` (line 25)**:
```javascript
// BEFORE
const result = await ApiClient.get('/api/staging/lock', { silent: true });
// AFTER
const result = await CandidateApi.getSession();
```
Update field mapping:
```javascript
// BEFORE
baseState.isEditingLocked = result.data.locked && !result.data.isOwner;
baseState.lockOwner = result.data.owner;
baseState.lockUserName = result.data.userName;
baseState.lockUserEmail = result.data.userEmail;
// AFTER
const session = result.data;
const isOtherUser = session.active && session.session_id !== getSessionId();
baseState.isEditingLocked = isOtherUser;
baseState.lockOwner = session.session_id;
baseState.lockUserName = session.user_name || '';
baseState.lockUserEmail = session.user_email || '';
```

**2. Update banner text (line 69)**:
```javascript
// BEFORE
"has pending changes. Commit or discard to edit."
// AFTER
"has an active editing session. Wait for them to finish or break the lock."
```

**3. Rewrite `breakLock()` (line 95)**:
```javascript
// BEFORE
ApiClient.post('/api/staging/lock/break', {}, { silent: true })
// AFTER
ApiClient.post('/api/candidate/session/break', {}, { silent: true })
```

## Change Tracking

- [ ] Rewrite `checkLockStatus()` to call `CandidateApi.getSession()` instead of `/api/staging/lock`
- [ ] Update field mapping from staging lock fields to candidate session fields
- [ ] Update banner text from staging language to candidate session language
- [ ] Rewrite `breakLock()` to call `/api/candidate/session/break` instead of `/api/staging/lock/break`
- [ ] Update toast text in `breakLock()` to candidate-appropriate wording
- [ ] Verify no remaining staging references in `lock-manager.js`

## Verification

**Manual checks:**
- Lock banner appears when another session is active
- Break lock clears the other session
- Lock banner hides after break

**Linting:**
```bash
npx eslint static/js/lock-manager.js
```

**Playwright:**
```bash
npx playwright test tests/e2e/lock-manager.spec.js
```

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This module only polls session status and breaks locks; it never writes to live config.
- [x] **C2 — UI visual parity.** Banner behavior and layout remain identical; only text content changes to reflect candidate terminology.
- [x] **C3 — Full audit logging.** N/A for this frontend module — audit logging is handled by the backend endpoints (`/api/candidate/session/break`) that this code calls.
- [x] **C4 — Proper error handling everywhere.** Existing error handling (silent API calls, fallback states) is preserved. No new unhandled paths introduced.
- [x] **C5 — Dead code deletion.** All 3 staging references are replaced, not left behind. Removal Audit section accounts for every one.
- [x] **C6 — Full functionality migration.** Lock status polling, banner display, and break-lock functionality are all migrated to candidate equivalents.
- [x] **C7 — Palo Alto candidate model.** Replaces staging lock polling with candidate session polling, aligning with the copy-edit-apply model.
- [x] **C8 — Change tracking document.** Added above with tickable checklist covering all changes.
- [x] **C9 — Complete planning before implementation.** This document fully specifies all changes with before/after code blocks before any code is written.
- [x] **C10 — Linting enforcement.** ESLint command included in Verification section.
- [x] **C11 — Playwright validation.** Playwright test command included in Verification section for lock-manager UI behavior.
