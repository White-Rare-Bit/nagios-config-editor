# L07 — `static/js/explorer/main.js` — MODIFY

## Purpose
Replace staging state fields with candidate state. Remove all client-side staging Maps/Sets.

## Removal Audit
State fields being removed and their candidate equivalents:
- `pendingEdits` (Map) → REMOVED. Edits go directly to server via CandidateApi.editObject(). No client-side cache needed.
- `stagedMoves` (Map) → REMOVED. Moves go to server via CandidateApi.moveObjects().
- `stagedCreations` (Array) → REMOVED. Creates go to server via CandidateApi.createObject().
- `stagedObjectDeletions` (Set) → REMOVED. Deletes go to server via CandidateApi.deleteObjects().
- `stagedCreationDeletions` (Set) → REMOVED. No longer needed (no client-side creations to delete).
- `newFiles` (Set) → REMOVED. File creates go to server via CandidateApi.createFile().
- `stagedFileCreations` (Array) → REMOVED. Server-side via CandidateApi.
- `stagedFileDeletions` (Array) → REMOVED. Server-side via CandidateApi.
- `stagedFileMoves` (Array) → REMOVED. Server-side via CandidateApi.
- `stagedFolderCreations` (Array) → REMOVED. Server-side via CandidateApi.
- `stagedFolderDeletions` (Array) → REMOVED. Server-side via CandidateApi.
- `stagedFolderMoves` (Array) → REMOVED. Server-side via CandidateApi.
- `undoStack` (Array) → REMOVED. Undo managed server-side via git reset.
- `selectedStagedIndices` (Set) → REMOVED. No client-side staged creations to select.
- `currentStagingOwner` → REMOVED. Session ownership tracked server-side.

State fields being ADDED:
- `candidateActive` (boolean) → Whether a candidate session exists for this user
- `candidateDiff` (object|null) → Cached diff from CandidateApi.getDiff() for UI badges

State fields KEPT unchanged:
- All core data, selection, UI state, tab state, center pane state, analysis, folder state, config, session, autocomplete, pending actions, metadata fields stay as-is.

## Current Code (lines 19-106)
The full Explorer.state object with all staging fields as shown in main.js.

## Changes

**1. Remove staging state block (lines 26-45)**:
Replace the entire staging data section with candidate state:

```javascript
// BEFORE (lines 24-45)
    // Selection (uses stable keys)
    selectedKeys: new Set(),
    selectedStagedIndices: new Set(),

    // Staging data - Object operations
    pendingEdits: new Map(),
    stagedMoves: new Map(),
    stagedCreations: [],
    stagedObjectDeletions: new Set(),
    stagedCreationDeletions: new Set(),
    newFiles: new Set(),

    // Staging data - File/folder operations (true staging)
    stagedFileCreations: [],
    stagedFileDeletions: [],
    stagedFileMoves: [],
    stagedFolderCreations: [],
    stagedFolderDeletions: [],
    stagedFolderMoves: [],

    // Undo support
    undoStack: [],

// AFTER
    // Selection (uses stable keys)
    selectedKeys: new Set(),

    // Candidate session state
    candidateActive: false,
    candidateDiff: null,
```

**2. Remove currentStagingOwner (line 92)**:
```javascript
// BEFORE
    sessionId: null,
    currentStagingOwner: null,
    isEditingLocked: false,
// AFTER
    sessionId: null,
    isEditingLocked: false,
```

**3. Update isNewObject comment (line 51, now renumbered)**:
The `isNewObject` and `newObjectStagedIndex` fields remain but `newObjectStagedIndex` is renamed:
```javascript
// BEFORE
    isNewObject: false,
    newObjectStagedIndex: null,
// AFTER
    isNewObject: false,
    newObjectKey: null,  // stable key of newly created object
```

## Change Tracking

- [ ] Remove `pendingEdits` (Map) from state
- [ ] Remove `stagedMoves` (Map) from state
- [ ] Remove `stagedCreations` (Array) from state
- [ ] Remove `stagedObjectDeletions` (Set) from state
- [ ] Remove `stagedCreationDeletions` (Set) from state
- [ ] Remove `newFiles` (Set) from state
- [ ] Remove `stagedFileCreations` (Array) from state
- [ ] Remove `stagedFileDeletions` (Array) from state
- [ ] Remove `stagedFileMoves` (Array) from state
- [ ] Remove `stagedFolderCreations` (Array) from state
- [ ] Remove `stagedFolderDeletions` (Array) from state
- [ ] Remove `stagedFolderMoves` (Array) from state
- [ ] Remove `undoStack` (Array) from state
- [ ] Remove `selectedStagedIndices` (Set) from state
- [ ] Remove `currentStagingOwner` from state
- [ ] Add `candidateActive` (boolean) to state
- [ ] Add `candidateDiff` (object|null) to state
- [ ] Rename `newObjectStagedIndex` to `newObjectKey`

## Verification
- `npm run lint:js` passes
- `python3 -m ruff check .` passes (no Python in this file, but verify no side-effects)
- Explorer loads without JS errors
- `Object.keys(Explorer.state)` in console shows no `staged*` or `pending*` fields
- Playwright: verify Explorer initializes and renders the file tree after state migration

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This file only changes client-side state initialization. No config writes occur; candidate edits go to the server, and nothing is written to live config until Apply.
- [x] **C2 — UI visual parity.** State field changes are invisible to the user. The UI renders identically; only internal data structures change.
- [ ] **C3 — Full audit logging.** N/A — This is a client-side JS state file. No server operations occur here. Audit logging is the responsibility of the CandidateApi endpoints this state feeds into.
- [x] **C4 — Proper error handling.** State initialization uses safe defaults (`false`, `null`). Error handling for operations using this state is in the respective modules.
- [x] **C5 — Dead code deletion.** All 15 staging state fields are explicitly removed. The Removal Audit documents every field and its disposition.
- [x] **C6 — Full functionality migration.** Every removed field has a documented candidate equivalent (server-side via CandidateApi). `newObjectStagedIndex` is migrated to `newObjectKey`.
- [x] **C7 — Palo Alto candidate model.** Client-side staging Maps/Sets replaced with `candidateActive` and `candidateDiff` — all edits go to the server-side candidate copy.
- [x] **C8 — Change tracking document.** Change Tracking section added above with tickable checklist for every change.
- [x] **C9 — Complete planning before implementation.** This file is part of the L07 planning layer; no code changes until the full plan is approved.
- [x] **C10 — Linting enforcement.** Verification section includes `npm run lint:js` check.
- [x] **C11 — Playwright validation.** Verification section includes Playwright check that Explorer initializes and renders after state migration.
