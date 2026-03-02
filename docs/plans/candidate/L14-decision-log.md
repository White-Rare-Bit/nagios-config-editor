# L14 — `.claude/DECISION_LOG.md` — MODIFY

**Layer:** 14 — Documentation Updates
**Action:** MODIFY (append)
**Path:** `.claude/DECISION_LOG.md`
**Dependencies:** All prior layers (L01–L13) must be planned; this documents the architectural decision they implement.

## Purpose
Append a decision entry documenting the migration from the delta-based staging system to the Palo Alto Networks-style candidate config model. The entry must accurately reflect all architectural constraints enforced by the commandments.

## Changes
Append new entry to the decision log:

```markdown
## 2026-02-27: Replace Staging System with Candidate Config

**Decision:** Replace the delta-based staging system (StagingManager) with a file-copy candidate config system (CandidateManager), following the Palo Alto Networks candidate configuration methodology: copy config to candidate, edit candidate, apply candidate to live.

**Context:** The staging system maintained all changes as in-memory deltas (pendingEdits, stagedMoves, stagedCreations, etc.) that were applied in a complex 7-phase batch operation. This caused:
- Cross-file delete bugs due to stale global indices
- Non-idempotent apply (retries created duplicates)
- Complex dual-mode frontend (client-side state overlay on every read)
- Difficult-to-test apply phases with ordering dependencies

**Approach:** File-copy model — running config copied to `.candidate/` directory with an internal git repo. Each edit modifies files directly (git commit per action). Undo = `git reset --hard HEAD~1`. Apply = copy candidate back to running config. No live configuration is mutated until the user explicitly clicks Apply in the commit dialog. All state lives on the server — the frontend holds no staging data structures.

**Constraints:**
- No live config mutation until Apply — the running config directory is read-only until `POST /api/candidate/apply` is invoked
- UI visual parity — the user interface remains visually identical to the prior system; only the underlying data flow changes
- Full audit logging — every candidate operation (edit, delete, create, move, clone, reorder, undo, apply, discard, break-lock) is logged via `audit_service.log_audit()` and application `logger`
- Proper error handling — all operations return `OperationResult`; no silent failures; post-mutation parse verification with auto-revert on corruption
- Dead code deletion — StagingManager, apply_verification.py, routes/staging.py, all client-side staging state (pendingEdits, stagedMoves, stagedCreations, etc.), and ~960 lines of apply phases in nagios_service.py are deleted entirely
- Full functionality migration — every feature of the staging system (edits, moves, creates, deletes, file/folder ops, bulk ops, undo, conflict detection, reference analysis, validation, backup-restore) is reimplemented in the candidate system with equivalent or improved behavior
- Linting enforcement — all Python code must pass Ruff, all JavaScript must pass ESLint before committing
- Playwright validation — Playwright tests validate UI behavior after each migration layer where applicable, ensuring each migrated feature works as expected

**Planning:**
- Complete migration plan set (L00–L14, ~76 plan files) was produced before any implementation begins
- L00-migration-inventory.md serves as the ground-truth change tracking document, enumerating all ~1,300 staging references across 63 files with per-file L-plan coverage
- Every plan file includes a verification section with concrete pass/fail checks

**Trade-offs:**
- (+) Simpler state model — no client-side staging state
- (+) Git-based undo — reliable, unlimited depth
- (+) Each action immediately verifiable (re-parse after edit)
- (+) Apply is trivial file copy, not complex multi-phase batch
- (+) Continuous validation replaces post-apply verification — errors caught at mutation time, not during bulk apply
- (-) Disk I/O for initial config copy (acceptable for typical config sizes)
- (-) Requires fcntl file locking (process-level, not thread-level)

**Affected:** All backend services, all frontend modules, all route files, all test files, all CSS, all HTML templates, all reference documentation. See L00-migration-inventory.md for the complete file-by-file inventory.
```

## Verification
- Entry appended to decision log (not replacing existing entries)
- Decision log is valid markdown
- `grep -c "Palo Alto" .claude/DECISION_LOG.md` returns at least 1
- Entry explicitly mentions: no live mutation until Apply, UI visual parity, audit logging, error handling, dead code deletion, full functionality migration, linting enforcement, Playwright validation
- Entry references L00-migration-inventory.md as the change tracking document
- Entry notes complete planning before implementation
- `python3 -m ruff check .claude/DECISION_LOG.md` — not applicable (markdown file), but markdown is well-formed

## Commandments Compliance

| # | Commandment | Status | How Addressed |
|---|-------------|--------|---------------|
| 1 | No live config mutation until Apply | COMPLIANT | Decision entry explicitly states "No live configuration is mutated until the user explicitly clicks Apply" and lists this as a constraint |
| 2 | UI visual parity | COMPLIANT | Decision entry includes constraint: "UI visual parity — the user interface remains visually identical to the prior system" |
| 3 | Full audit logging | COMPLIANT | Decision entry includes constraint: "Full audit logging — every candidate operation is logged via audit_service.log_audit() and application logger" |
| 4 | Proper error handling | COMPLIANT | Decision entry includes constraint: "Proper error handling — all operations return OperationResult; no silent failures; post-mutation parse verification with auto-revert" |
| 5 | Dead code deletion | COMPLIANT | Decision entry includes constraint listing all dead code to be deleted: StagingManager, apply_verification.py, routes/staging.py, client-side staging state, apply phases |
| 6 | Full functionality migration | COMPLIANT | Decision entry includes constraint: "every feature of the staging system is reimplemented in the candidate system with equivalent or improved behavior" |
| 7 | Palo Alto candidate model | COMPLIANT | Decision entry opens with "following the Palo Alto Networks candidate configuration methodology: copy config to candidate, edit candidate, apply candidate to live" |
| 8 | Change tracking document | COMPLIANT | Decision entry references L00-migration-inventory.md as the ground-truth change tracking document with ~1,300 references across 63 files |
| 9 | Complete planning before implementation | COMPLIANT | Decision entry states "Complete migration plan set (L00–L14, ~76 plan files) was produced before any implementation begins" |
| 10 | Linting enforcement | COMPLIANT | Decision entry includes constraint: "all Python code must pass Ruff, all JavaScript must pass ESLint before committing" |
| 11 | Playwright validation | COMPLIANT | Decision entry includes constraint: "Playwright tests validate UI behavior after each migration layer where applicable" |
