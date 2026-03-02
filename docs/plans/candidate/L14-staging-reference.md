# L14 — `.claude/STAGING_REFERENCE.md` — DELETE

**Layer:** 14 — Documentation
**Action:** DELETE
**Path:** `.claude/STAGING_REFERENCE.md`
**Dependencies:** L14-candidate-reference.md (replacement doc must exist first)
**Goal:** Delete the old staging system reference. All useful content migrated to `.claude/CANDIDATE_REFERENCE.md`.

---

## Purpose

Delete old staging reference documentation. This file documents the delta-based staging system (`staging_manager.py`, `staging.json`, undo stack, checksum-based conflict detection) which is fully replaced by the Palo Alto-style candidate system. The replacement reference is `.claude/CANDIDATE_REFERENCE.md` (created by L14-candidate-reference.md).

## Functionality Migration Audit (Section-by-Section)

Every section in `STAGING_REFERENCE.md` must have an equivalent in `CANDIDATE_REFERENCE.md` or be explicitly marked as dead. Nothing dropped on the floor.

| STAGING_REFERENCE Section | Candidate Equivalent | CANDIDATE_REFERENCE Section | Status |
|---------------------------|---------------------|-----------------------------|--------|
| **Overview** — "true staging, NO changes to disk until Apply" | Candidate copy model: edits go to `.candidate/`, Apply copies back | Section 1 (Overview) | MIGRATED — same guarantee, different mechanism |
| **Overview** — `sm.checksums` (ChecksumManager) | Git-based conflict detection (`cm.detect_conflicts()`) | Section 6 (Conflicts) via L01 | MIGRATED |
| **Overview** — `sm.undo` (UndoStackManager) | Git commits per action, undo = `git reset --hard HEAD~1` | Section 2 (Session Lifecycle — Undo) | MIGRATED |
| **Overview** — `sm.file_ops` (FileOperationsStager) | Direct file ops on `.candidate/` directory | Section 3 (CandidateManager API — File/folder ops) | MIGRATED |
| **State Transitions** — EMPTY/ACTIVE/RESTORE_PENDING | Binary: active/inactive + `restore_pending` flag via `set_restore_pending()` | Section 2 (Session Lifecycle) | MIGRATED — simplified |
| **Lock Management** — session-based, `can_modify()`, 423 status | `fcntl` file lock + session_id check, same `can_modify()` contract | Section 5 (Concurrency) | MIGRATED |
| **Staged Operations** — 10 operation types in `staging.json` | Direct file mutations in candidate dir, each = git commit | Section 3 (CandidateManager API) | MIGRATED — no staging.json needed |
| **Undo Stack** — uuid, type, data, description, timestamp | Git commit log; each commit message = operation description | Section 2 (Session Lifecycle — Undo) | MIGRATED |
| **Conflict Detection** — base checksums, `detect_conflicts()` | Git hash comparison between candidate base and current running config | Section 3 (CandidateManager API — `detect_conflicts()`) | MIGRATED |
| **Apply Phase Order** — 7 ordered phases, composite merging | Single-step: `shutil.copytree(candidate, running)` | Section 3 (CandidateManager API — `apply()`) | DEAD — phase ordering unnecessary in copy model |
| **Stable Keys** — `"source_file\|object_type\|name"`, `generate_stable_key()` | Same stable key format, functions migrated to `nagios_model.py` (L02) | Referenced in CANDIDATE_REFERENCE via CandidateManager API | MIGRATED to nagios_model.py |
| **Commit Workflow** — multi-step UI flow | Same UI flow, endpoints change from `/api/staging/*` to `/api/candidate/*` | Section 6 (Frontend Integration) + L09-commit-dialog.md | MIGRATED |

### Content explicitly marked DEAD (not migrated)

These concepts exist only in the delta-based staging system and have no equivalent in the candidate model:

- **`staging.json`** — no staging state file needed; candidate dir IS the state
- **`CompositeAction` / `_build_composite_actions()`** — no phase merging needed; edits go directly to files
- **`apply_object_composite()`** — replaced by simple file copy
- **`apply_folder_creations/moves/deletions()`** — folders are created/moved/deleted directly in candidate
- **`apply_file_creations/moves/deletions()`** — files are created/moved/deleted directly in candidate
- **`ChecksumManager`** — replaced by git hashing
- **`UndoStackManager`** — replaced by git history
- **`FileOperationsStager`** — replaced by direct candidate file ops
- **`StagingState` enum** — replaced by binary session active/inactive
- **`OperationType` enum** — replaced by git commit messages

## Changes

Delete entire file: `.claude/STAGING_REFERENCE.md`

## Error Handling

Not applicable — this is a file deletion. If the file does not exist at execution time (e.g., already deleted), the step is a no-op. No silent failure: log a warning if file is missing.

## Verification

- [ ] `.claude/STAGING_REFERENCE.md` no longer exists on disk
- [ ] `.claude/CANDIDATE_REFERENCE.md` exists and covers all migrated sections from the audit table above
- [ ] `grep -r "STAGING_REFERENCE" .claude/ docs/ CLAUDE.md` returns no matches (other docs updated in L14-claude-md.md)
- [ ] No broken references from CLAUDE.md (L14-claude-md.md updates the documentation index to reference CANDIDATE_REFERENCE instead)

## Change Tracking

This plan is tracked in L00-migration-inventory.md:
- Section 4.1: `.claude/STAGING_REFERENCE.md` listed as `[covered]` by `L14-staging-reference.md`

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | This plan deletes a reference doc, not code. The constraint carries forward via the candidate system documented in CANDIDATE_REFERENCE.md. |
| 2 | UI visual parity | N/A | Documentation-only change. No UI impact. |
| 3 | Full audit logging | N/A | Reference doc deletion does not require runtime audit logging. No code changes. |
| 4 | Proper error handling | COMPLIANT | Plan specifies: if file missing at execution time, log warning and treat as no-op. No silent failures. |
| 5 | Dead code deletion | COMPLIANT | This plan IS dead code deletion — removing documentation for the defunct staging system. |
| 6 | Full functionality migration | COMPLIANT | Section-by-section migration audit added above. Every section in STAGING_REFERENCE has an explicit disposition: MIGRATED to CANDIDATE_REFERENCE or marked DEAD with justification. Nothing dropped. |
| 7 | Palo Alto candidate model | COMPLIANT | Replacement doc (CANDIDATE_REFERENCE.md) documents the Palo Alto-style copy-edit-apply model. Old staging terminology is removed with this deletion. |
| 8 | Change tracking document | COMPLIANT | Tracked in L00-migration-inventory.md section 4.1. |
| 9 | Complete planning before implementation | COMPLIANT | This plan is part of L14 (documentation layer), fully planned before any implementation begins. Dependency on L14-candidate-reference.md is explicit. |
| 10 | Linting enforcement | N/A | No code changes. Markdown file deletion only. |
| 11 | Playwright validation | N/A | No UI changes to validate. Documentation deletion only. |
