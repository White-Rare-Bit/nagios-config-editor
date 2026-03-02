# L06 — `eslint.config.mjs` — MODIFY

## Purpose
Add `CandidateApi` to global definitions, rename `getStagingHeaders` to `getSessionHeaders`. This is a lint-configuration-only change — no runtime behavior is affected.

## Removal Audit
- `getStagingHeaders` global definition (line 27) — renamed to `getSessionHeaders`. Same symbol, new name. Corresponds to the rename in L06-session-manager.md.
- No globals deleted. No functionality lost.

## Current Code (lines 19-27)
```javascript
// api-client.js
ApiClient: "readonly",

// base-state.js
baseState: "readonly",

// session-manager.js
getSessionId: "readonly",
getStagingHeaders: "readonly",
```

## Changes

**1. Rename staging header global (line 27)**:
```javascript
// BEFORE
getStagingHeaders: "readonly",
// AFTER
getSessionHeaders: "readonly",
```

**2. Add CandidateApi global after ApiClient (after line 20)**:
```javascript
// BEFORE
// api-client.js
ApiClient: "readonly",

// base-state.js
// AFTER
// api-client.js
ApiClient: "readonly",

// candidate-api.js
CandidateApi: "readonly",

// base-state.js
```

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Rename `getStagingHeaders` to `getSessionHeaders` in projectGlobals (line 27) | [ ] |
| 2 | Add `CandidateApi: "readonly"` with comment after ApiClient (after line 20) | [ ] |

## Verification
- `npm run lint:js` passes with no `CandidateApi` not-defined errors
- `npm run lint:js` passes with no `getSessionHeaders` not-defined errors
- `grep -n "getStagingHeaders" eslint.config.mjs` returns no matches (old name fully removed)
- `grep -n "CandidateApi" eslint.config.mjs` returns the new global definition

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Not applicable — this file is a lint configuration, not runtime code. No config files are read or written.
- [x] **C2 — UI visual parity.** Not applicable — ESLint config has no UI impact.
- [x] **C3 — Full audit logging.** Not applicable — lint config changes do not involve runtime operations that require audit logging.
- [x] **C4 — Proper error handling.** Not applicable — ESLint config is declarative; no error paths exist.
- [x] **C5 — Dead code deletion.** The `getStagingHeaders` global is not deleted but renamed to `getSessionHeaders`, matching the actual function rename in L06-session-manager.md. No dead definitions remain.
- [x] **C6 — Full functionality migration.** `CandidateApi` global is added for the new `candidate-api.js` file (L06-candidate-api.md). The `getSessionHeaders` rename preserves the existing global under its new name. No globals dropped.
- [x] **C7 — Palo Alto candidate model.** Supports the candidate model by declaring the `CandidateApi` global that the candidate API wrapper exposes.
- [x] **C8 — Change tracking document.** Change tracking table added above with per-item checkboxes.
- [x] **C9 — Complete planning before implementation.** This plan fully specifies both changes with before/after code and exact line numbers. No ambiguity remains.
- [x] **C10 — Linting enforcement.** This plan IS the linting enforcement plan. Changes ensure ESLint recognizes the new `CandidateApi` global and the renamed `getSessionHeaders` global so that `npm run lint:js` passes after L06 changes land.
- [x] **C11 — Playwright validation.** Not applicable — ESLint config changes have no UI surface. Lint pass is verified via CLI (`npm run lint:js`) in the Verification section.
