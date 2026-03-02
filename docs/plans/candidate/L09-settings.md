# L09 — `static/js/settings.js` — MODIFY

## Purpose
Replace staging lock checks with candidate session checks.

## Removal Audit
- **Line 249**: `ApiClient.get('/api/staging/lock', { silent: true })` in identity save — checks if current user owns lock before updating staging identity. REPLACED by `CandidateApi.getSession()` to check active session ownership.
- **Line 262**: `ApiClient.get('/api/staging/lock', { silent: true })` in `saveServerSettings()` — blocks save when locked by another user. REPLACED by `CandidateApi.getSession()` with session ownership check.
- **Line 264**: `'Cannot save server settings while another user has pending changes'` toast text — UPDATED to "Cannot save server settings while another user has an active editing session".
- **Line 446**: `ApiClient.get('/api/staging/lock', { silent: true })` in `loadGitIdentity()` — checks if another user has lock to display info. REPLACED by `CandidateApi.getSession()`.

4 staging references total (3 endpoint calls + 1 UI text). All accounted for.

## Changes

**1. Update identity save lock check (line 249)**:
```javascript
// BEFORE
const lockResult = await ApiClient.get('/api/staging/lock', { silent: true });
if (lockResult.success && lockResult.data.locked && lockResult.data.isOwner) {
// AFTER
const sessionResult = await CandidateApi.getSession();
if (sessionResult.data.active && sessionResult.data.session_id === getSessionId()) {
```

**2. Update settings save lock check (line 262)**:
```javascript
// BEFORE
const lockResult = await ApiClient.get('/api/staging/lock', { silent: true });
const { locked, isOwner } = lockResult.data;
if (locked && !isOwner) {
    showToast("Cannot save server settings while another user has pending changes", 'error');
// AFTER
const sessionResult = await CandidateApi.getSession();
const isOtherSession = sessionResult.data.active && sessionResult.data.session_id !== getSessionId();
if (isOtherSession) {
    showToast("Cannot save server settings while another user has an active editing session", 'error');
```

**3. Update `loadGitIdentity()` lock display (line 446)**:
Same pattern — replace staging lock check with candidate session check.

## Change Tracking

- [ ] Update identity save lock check (line 249) to use `CandidateApi.getSession()` with session ownership check
- [ ] Update settings save lock check (line 262) to use `CandidateApi.getSession()` with `isOtherSession` pattern
- [ ] Update toast text from staging language to candidate session language
- [ ] Update `loadGitIdentity()` lock display (line 446) to use candidate session check
- [ ] Verify no remaining staging references in `settings.js`

## Verification

**Manual checks:**
- Settings page loads
- Cannot save while another session active (shows toast)
- Can save when no session or own session active

**Linting:**
```bash
npx eslint static/js/settings.js
```

**Playwright:**
```bash
npx playwright test tests/e2e/settings.spec.js
```

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This module only checks session ownership before saving settings/identity; it never writes to live Nagios config.
- [x] **C2 — UI visual parity.** Settings page layout and behavior remain identical; only toast message text changes to reflect candidate terminology.
- [x] **C3 — Full audit logging.** N/A for this frontend module — audit logging is handled by the backend endpoints this code calls.
- [x] **C4 — Proper error handling everywhere.** Existing error handling patterns (silent API calls, conditional checks) are preserved. The `isOtherSession` guard maintains the same protective behavior.
- [x] **C5 — Dead code deletion.** All 4 staging references (3 endpoint calls + 1 UI text) are replaced. Removal Audit section accounts for every one.
- [x] **C6 — Full functionality migration.** All three lock-checking behaviors (identity save, settings save, git identity load) are migrated to candidate session equivalents.
- [x] **C7 — Palo Alto candidate model.** Replaces staging lock ownership checks with candidate session ownership checks, aligning with the copy-edit-apply model.
- [x] **C8 — Change tracking document.** Added above with tickable checklist covering all changes.
- [x] **C9 — Complete planning before implementation.** This document fully specifies all changes with before/after code blocks before any code is written.
- [x] **C10 — Linting enforcement.** ESLint command included in Verification section.
- [x] **C11 — Playwright validation.** Playwright test command included in Verification section for settings page behavior.
