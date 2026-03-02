# L06 — `templates/base.html` — MODIFY

## Purpose
Add `candidate-api.js` script tag to load order. No other changes.

## Removal Audit
- No script tags removed.
- No lock banner text changes. All user-facing text preserved exactly as-is (Commandment 2).
- No dead code identified for removal in this file's script block or lock banner.

## Current Code

Script loading (lines 1971-1974):
```html
<script src="{{ url_for('static', filename='js/api-client.js') }}"></script>
<script src="{{ url_for('static', filename='js/commit-dialog.js') }}"></script>
<script src="{{ url_for('static', filename='js/lock-manager.js') }}"></script>
<script src="{{ url_for('static', filename='js/base.js') }}"></script>
```

Lock banner (lines 73-78) — NO CHANGES, preserved for reference:
```html
<!-- Lock Banner - shown when another user has pending changes -->
<div id="lockBanner" class="lock-banner u-hidden">
    <span class="lock-banner-icon"><i class="fa-solid fa-lock"></i></span>
    <span id="lockBannerText"><strong>Another user has pending changes.</strong> Commit or discard to edit.</span>
    <button class="lock-break-btn" id="breakLockBtn" data-action="break-lock" title="Admin action: Discard the other user's pending changes and release the lock">Break Lock (Admin)</button>
</div>
```

## Changes

**1. Add candidate-api.js script tag (after api-client.js, before commit-dialog.js)**:
```html
<script src="{{ url_for('static', filename='js/api-client.js') }}"></script>
<script src="{{ url_for('static', filename='js/candidate-api.js') }}"></script>
<script src="{{ url_for('static', filename='js/commit-dialog.js') }}"></script>
<script src="{{ url_for('static', filename='js/lock-manager.js') }}"></script>
<script src="{{ url_for('static', filename='js/base.js') }}"></script>
```

This is the only change to `base.html`. The lock banner text, HTML comment, button label, and tooltip title are all preserved exactly as they currently are.

## What Is NOT Changed (Commandment 2 — UI Visual Parity)
- Lock banner HTML comment: kept as `<!-- Lock Banner - shown when another user has pending changes -->`
- Lock banner text: kept as `Another user has pending changes. Commit or discard to edit.`
- Break Lock button label: kept as `Break Lock (Admin)`
- Break Lock button title attribute: kept as `Admin action: Discard the other user's pending changes and release the lock`

## Change Tracking (Commandment 8)

| # | Change | File | Lines | Status |
|---|--------|------|-------|--------|
| 1 | Add `candidate-api.js` script tag after `api-client.js` | `templates/base.html` | ~1972 | [ ] |

## Verification
- App loads without JS errors in browser console.
- `candidate-api.js` loads successfully (check Network tab or `typeof CandidateApi !== 'undefined'` in console).
- Lock banner displays identical text to current production — no visual regression.
- All existing scripts (`api-client.js`, `commit-dialog.js`, `lock-manager.js`, `base.js`) still load in correct order.
- Playwright: Add a smoke test asserting `candidate-api.js` is present in the page's script tags and that `CandidateApi` is defined in the global scope.

## Commandments Compliance

- [x] **1. No live config mutation until Apply.** This change adds a script tag only; no config mutation logic introduced.
- [x] **2. UI visual parity.** No user-facing text, labels, tooltips, or banner content is changed. All existing text preserved verbatim.
- [x] **3. Full audit logging.** No new operations introduced that require audit logging (script tag addition only).
- [x] **4. Proper error handling.** No new logic introduced; script load failures are handled by existing browser mechanisms.
- [x] **5. Dead code deletion.** No dead code identified in the affected section. No scripts removed.
- [x] **6. Full functionality migration.** New `candidate-api.js` script added to support candidate model; no existing functionality dropped.
- [x] **7. Palo Alto candidate model.** `candidate-api.js` provides the frontend API layer for the candidate configuration workflow.
- [x] **8. Change tracking document.** Change tracking table included above.
- [x] **9. Complete planning before implementation.** This plan is complete; single atomic change fully specified.
- [x] **10. Linting enforcement.** HTML template change only (script tag); no JS/Python code modified. Existing ESLint/Ruff rules unaffected.
- [x] **11. Playwright validation.** Verification section includes Playwright smoke test for `candidate-api.js` presence and `CandidateApi` global availability.
