# L09 — `static/js/git.js` — MODIFY

**Layer:** 09 — Page-Level JavaScript
**Action:** MODIFY
**Path:** `static/js/git.js`
**Dependencies:** L06-candidate-api.md (provides `CandidateApi`), L13-git-css.md (renames CSS classes)
**Goal:** Replace staging diff/preview with candidate diff. Update internal variable names and API calls. Preserve all user-facing labels exactly as they are today.

## Purpose
Replace staging diff/preview with candidate diff. Update internal terminology (variable names, function names, comments, CSS class references). **User-facing label text must remain unchanged** (Commandment 2).

## Removal Audit
- `stagingInfo` variable → RENAMED to `candidateInfo`. Same purpose: holds diff data.
- `buildStagingPreviewHtml(staging)` → RENAMED to `buildCandidatePreviewHtml(info)`. Reads from candidate diff structure.
- `ApiClient.get('/api/staging/diff')` → `CandidateApi.getDiff()`.
- CSS classes `git-staging-preview-*` → Renamed to `git-candidate-preview-*` (in L13).

### Detailed Line-by-Line Staging References

**`buildStagingPreviewHtml()` function (lines 101-118):**
| Line | Reference | Action |
|------|-----------|--------|
| 99 | `// Builds HTML for the staging preview section showing pending staged changes.` comment | REPLACE with candidate terminology in comment |
| 101 | `function buildStagingPreviewHtml(staging)` declaration | RENAME to `buildCandidatePreviewHtml(info)` |
| 102 | `!staging \|\| !staging.hasStagedChanges \|\| !staging.stagedChanges` guard | REPLACE with `!info \|\| !info.totalCount \|\| !info.changes` |
| 105 | `staging.stagedChanges.map(c => ...)` iteration | REPLACE with `info.changes.map(c => ...)` |
| 111 | `staging.totalStagedCount` count display | REPLACE with `info.totalCount` |

**`git-staging-preview-*` CSS class references (lines 107-115):**
| Line | Reference | Action |
|------|-----------|--------|
| 107 | `class="git-staging-preview"` container div | RENAME to `git-candidate-preview` |
| 108 | `class="git-staging-preview-header"` header div | RENAME to `git-candidate-preview-header` |
| 111 | `class="git-staging-preview-count"` count badge | RENAME to `git-candidate-preview-count` |
| 113 | `class="git-staging-preview-list"` list element | RENAME to `git-candidate-preview-list` |
| 114 | `class="git-staging-preview-note"` note div | RENAME to `git-candidate-preview-note` |
| 115 | `class="git-staging-preview-commit"` commit button | RENAME to `git-candidate-preview-commit` |
| 189 | `class="git-staging-preview-wrapper"` wrapper div | RENAME to `git-candidate-preview-wrapper` |

**`/api/staging/diff` endpoint call (line 48):**
| Line | Reference | Action |
|------|-----------|--------|
| 48 | `ApiClient.get('/api/staging/diff', { silent: true })` | REPLACE with `CandidateApi.getDiff()` |

**`stagingInfo` / `stagingResult` variables:**
| Line | Reference | Action |
|------|-----------|--------|
| 25 | `let stagingInfo = null` declaration | RENAME to `let candidateInfo = null` |
| 46 | `const [statusResult, stagingResult] = await Promise.all(...)` destructure | RENAME to `candidateResult` |
| 59 | `stagingInfo = stagingResult.data \|\| {}` assignment | RENAME to `candidateInfo = candidateResult.data \|\| {}` |
| 156 | `const hasStagedChanges = stagingInfo && stagingInfo.hasStagedChanges` check | RENAME + REPLACE: `const hasCandidateChanges = candidateInfo && candidateInfo.totalCount > 0` |
| 159 | `!gitStatus.has_changes && !hasStagedChanges` guard | REPLACE with `!hasCandidateChanges` |
| 174 | `const stagingPreviewHtml = buildStagingPreviewHtml(stagingInfo)` call | RENAME both function and variable |
| 178 | `!gitStatus.has_changes && hasStagedChanges` guard | REPLACE with `hasCandidateChanges` |
| 181 | `${stagingPreviewHtml}` interpolation | RENAME variable |
| 189 | `${stagingPreviewHtml ? ...}` conditional rendering | RENAME variable |

**`hasStagedChanges` / `totalStagedCount` properties:**
| Line | Reference | Action |
|------|-----------|--------|
| 102 | `staging.hasStagedChanges` property access | REPLACE with `info.totalCount > 0` |
| 111 | `staging.totalStagedCount` property access | REPLACE with `info.totalCount` |
| 156 | `stagingInfo.hasStagedChanges` property access | REPLACE with `candidateInfo.totalCount > 0` |

**Other staging text references:**
| Line | Reference | Action |
|------|-----------|--------|
| 110 | `'Pending Staged Changes'` label text | **KEEP AS-IS** — user-facing label, must not change (Commandment 2) |
| 114 | `'These changes have not been written to disk yet.'` note text | KEEP (still accurate for candidate) |
| 146 | `// Renders the git status view with file changes and staging preview.` comment | UPDATE comment terminology |
| 177 | `// Only staged changes, no filesystem changes` comment | UPDATE comment terminology |
| 187 | `// Mixed view with files and optional staging preview` comment | UPDATE comment terminology |

## Changes

**1. Replace staging diff fetch with error handling (line 46-59)**:
```javascript
// BEFORE
const [statusResult, stagingResult] = await Promise.all([
    ApiClient.get('/api/git/status', { silent: true }),
    ApiClient.get('/api/staging/diff', { silent: true })
]);
// ...
stagingInfo = stagingResult.data || {};

// AFTER
const [statusResult, candidateResult] = await Promise.all([
    ApiClient.get('/api/git/status', { silent: true }),
    CandidateApi.getDiff()
]);
// ...
candidateInfo = candidateResult.data || {};
if (candidateResult.error) {
    console.error('Failed to load candidate diff:', candidateResult.error);
}
```

**2. Rename state variable (line 25, 59)**:
```javascript
// BEFORE
let stagingInfo = null;
stagingInfo = stagingResult.data || {};
// AFTER
let candidateInfo = null;
candidateInfo = candidateResult.data || {};
```

**3. Rewrite `buildStagingPreviewHtml()`** → `buildCandidatePreviewHtml()`:
```javascript
/**
 * Builds HTML for the candidate preview section showing pending changes.
 */
function buildCandidatePreviewHtml(info) {
    if (!info || !info.totalCount || !info.changes) {
        return '';
    }
    const items = info.changes.map(c => `<li>${escapeHtml(c.label)}</li>`).join('');
    return `
        <div class="git-candidate-preview">
            <div class="git-candidate-preview-header">
                <i class="fa-solid fa-layer-group"></i>
                <span>Pending Staged Changes</span>
                <span class="git-candidate-preview-count">${info.totalCount}</span>
            </div>
            <ul class="git-candidate-preview-list">${items}</ul>
            <div class="git-candidate-preview-note">These changes have not been written to disk yet.</div>
            <button class="git-candidate-preview-commit" data-action="commit">Review &amp; Commit</button>
        </div>
    `;
}
```
Note: The user-facing label `"Pending Staged Changes"` is preserved exactly as in the current code (Commandment 2). Only CSS class names and internal variable/function names change.

**4. Update `renderGitStatus()` references**:
```javascript
// BEFORE
const hasStagedChanges = stagingInfo && stagingInfo.hasStagedChanges;
const stagingPreviewHtml = buildStagingPreviewHtml(stagingInfo);
// AFTER
const hasCandidateChanges = candidateInfo && candidateInfo.totalCount > 0;
const candidatePreviewHtml = buildCandidatePreviewHtml(candidateInfo);
```

**5. Update wrapper class in renderGitStatus() (line 189)**:
```javascript
// BEFORE
${stagingPreviewHtml ? `<div class="git-staging-preview-wrapper">${stagingPreviewHtml}</div>` : ''}
// AFTER
${candidatePreviewHtml ? `<div class="git-candidate-preview-wrapper">${candidatePreviewHtml}</div>` : ''}
```

## Change Tracking

| # | Task | Description | Status |
|---|------|-------------|--------|
| 1 | Rename state variable | `stagingInfo` → `candidateInfo` (line 25) | [ ] |
| 2 | Replace API call | `ApiClient.get('/api/staging/diff')` → `CandidateApi.getDiff()` (line 48) | [ ] |
| 3 | Add error logging | Log `candidateResult.error` if candidate diff fetch fails (after line 59) | [ ] |
| 4 | Rename destructured var | `stagingResult` → `candidateResult` (line 46) | [ ] |
| 5 | Rename assignment | `stagingInfo = stagingResult.data` → `candidateInfo = candidateResult.data` (line 59) | [ ] |
| 6 | Rename function | `buildStagingPreviewHtml` → `buildCandidatePreviewHtml` (line 101) | [ ] |
| 7 | Replace guard clause | Use `!info.totalCount \|\| !info.changes` instead of staging properties (line 102) | [ ] |
| 8 | Replace iteration | Use `info.changes.map(...)` instead of `staging.stagedChanges.map(...)` (line 105) | [ ] |
| 9 | Rename CSS class | `git-staging-preview` → `git-candidate-preview` (line 107) | [ ] |
| 10 | Rename CSS class | `git-staging-preview-header` → `git-candidate-preview-header` (line 108) | [ ] |
| 11 | Keep label text | `'Pending Staged Changes'` — **DO NOT CHANGE** (line 110, Commandment 2) | [ ] |
| 12 | Rename CSS class | `git-staging-preview-count` → `git-candidate-preview-count` (line 111) | [ ] |
| 13 | Replace count source | `staging.totalStagedCount` → `info.totalCount` (line 111) | [ ] |
| 14 | Rename CSS class | `git-staging-preview-list` → `git-candidate-preview-list` (line 113) | [ ] |
| 15 | Rename CSS class | `git-staging-preview-note` → `git-candidate-preview-note` (line 114) | [ ] |
| 16 | Keep note text | `'These changes have not been written to disk yet.'` — DO NOT CHANGE (line 114) | [ ] |
| 17 | Rename CSS class | `git-staging-preview-commit` → `git-candidate-preview-commit` (line 115) | [ ] |
| 18 | Rename local var | `hasStagedChanges` → `hasCandidateChanges` (line 156) | [ ] |
| 19 | Replace property access | `stagingInfo.hasStagedChanges` → `candidateInfo.totalCount > 0` (line 156) | [ ] |
| 20 | Replace guard | `!hasStagedChanges` → `!hasCandidateChanges` (line 159) | [ ] |
| 21 | Rename local var | `stagingPreviewHtml` → `candidatePreviewHtml` (line 174) | [ ] |
| 22 | Replace guard | `hasStagedChanges` → `hasCandidateChanges` (line 178) | [ ] |
| 23 | Rename interpolation | `${stagingPreviewHtml}` → `${candidatePreviewHtml}` (line 181) | [ ] |
| 24 | Rename CSS class | `git-staging-preview-wrapper` → `git-candidate-preview-wrapper` (line 189) | [ ] |
| 25 | Rename conditional | `${stagingPreviewHtml ? ...}` → `${candidatePreviewHtml ? ...}` (line 189) | [ ] |
| 26 | Update comment | Line 99: update to candidate terminology | [ ] |
| 27 | Update comment | Line 146: update to candidate terminology | [ ] |
| 28 | Update comment | Line 177: update to candidate terminology | [ ] |
| 29 | Update comment | Line 187: update to candidate terminology | [ ] |
| 30 | Run ESLint | `npm run lint:js` passes on modified file | [ ] |

## Verification

### Manual Verification
- Git page loads without errors
- Candidate changes preview section shown when a candidate session is active
- The preview header displays **"Pending Staged Changes"** (unchanged user-facing label)
- The note text displays **"These changes have not been written to disk yet."** (unchanged)
- The "Review & Commit" button works and triggers commit dialog
- Git page with no candidate session shows clean state or file changes only
- No console errors

### Automated Verification
```bash
# No remaining references to old staging API endpoint in git.js
grep -n "api/staging" static/js/git.js
# Expected: zero matches

# No remaining old variable names
grep -n "stagingInfo\|stagingResult\|stagingPreviewHtml\|buildStagingPreviewHtml\|hasStagedChanges" static/js/git.js
# Expected: zero matches

# New candidate variable names present
grep -c "candidateInfo\|candidateResult\|candidatePreviewHtml\|buildCandidatePreviewHtml\|hasCandidateChanges" static/js/git.js
# Expected: >= 10

# User-facing label preserved
grep -n "Pending Staged Changes" static/js/git.js
# Expected: 1 match (the label text)
```

### Linting
```bash
# JavaScript must pass ESLint
npm run lint:js
# git.js must have zero errors and zero warnings
```

### Playwright Validation
After L09-git.md and L13-git-css.md are both applied:

1. **Git page loads with candidate preview visible:**
   - Navigate to the git page while a candidate session is active
   - Assert `.git-candidate-preview` element is visible
   - Assert `.git-candidate-preview-header` contains **"Pending Staged Changes"** (user-facing label preserved)
   - Assert `.git-candidate-preview-count` displays a number
   - Assert `.git-candidate-preview-list` contains at least one `<li>`
   - Assert `.git-candidate-preview-commit` button has text "Review & Commit"

2. **Git page loads without candidate session:**
   - Navigate to the git page with no candidate session active
   - Assert `.git-candidate-preview` element does NOT exist in the DOM
   - Assert the empty state or file list renders correctly

3. **Candidate preview interaction:**
   - Click the "Review & Commit" button in the preview section
   - Assert the commit dialog opens

4. **Error resilience:**
   - If candidate diff API returns an error, the git page should still render the git status (file changes) without crashing
   - Assert no uncaught exceptions in the console

5. **No dead CSS references in DOM:**
   - Assert no elements matching `.git-staging-preview` or `.git-staging-preview-*` exist in the page DOM

## Commandments Compliance

- [x] **1. No live config mutation until Apply.** This file only reads candidate diff data for display. No mutations to live config occur. The preview section is read-only. Writes only happen through `CandidateApi.apply()` in the commit dialog (L09-commit-dialog.md), not here.
- [x] **2. UI visual parity.** All user-facing labels are preserved exactly: `"Pending Staged Changes"` label text (line 110) is NOT renamed. `"These changes have not been written to disk yet."` note text (line 114) is NOT renamed. `"Review & Commit"` button text (line 115) is NOT renamed. Only internal variable names, function names, CSS class names, and code comments change.
- [x] **3. Full audit logging.** This is a client-side display file. All server-side operations it calls (`CandidateApi.getDiff()`, `/api/git/status`) already have audit logging in their respective backend route handlers.
- [x] **4. Proper error handling.** Added explicit `console.error()` logging when `candidateResult.error` is present (Change 1). The existing `statusResult` error handling is preserved. The `CandidateApi.getDiff()` call uses `{ silent: true }` to avoid double-toasting, with manual error logging added. Playwright test 4 validates error resilience.
- [x] **5. Dead code deletion.** All old staging-specific variable names, function names, and API calls are removed. No `stagingInfo`, `stagingResult`, `buildStagingPreviewHtml`, or `/api/staging/diff` references remain after migration.
- [x] **6. Full functionality migration.** Every piece of functionality in the current git.js is migrated: state variable, API fetch, preview HTML builder, render guards, CSS class references, and conditional rendering. Nothing is dropped.
- [x] **7. Palo Alto candidate model.** The API endpoint changes from `/api/staging/diff` to `CandidateApi.getDiff()` which calls `/api/candidate/diff`. Internal variable names use `candidate` terminology. This follows the Palo Alto candidate config model.
- [x] **8. Change tracking document.** 30-item change tracking table provided with per-line granularity and checkbox status.
- [x] **9. Complete planning before implementation.** Full before/after code blocks provided for all changes. Every line reference enumerated. No ambiguous instructions.
- [x] **10. Linting enforcement.** Verification section includes explicit `npm run lint:js` step. Change tracking item 30 requires ESLint pass.
- [x] **11. Playwright validation.** Five Playwright test scenarios specified: preview visible with correct labels, no-session rendering, button interaction, error resilience, and dead CSS reference absence.
