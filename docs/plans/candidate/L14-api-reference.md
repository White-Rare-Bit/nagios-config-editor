# L14 — `.claude/API_REFERENCE.md` — MODIFY

**Layer:** 14 — Reference Documentation
**Action:** MODIFY
**Path:** `.claude/API_REFERENCE.md`
**Dependencies:** L01 (CandidateManager), L03 (routes/candidate.py), L12-staging-manager.md (staging deletion), L12-nagios-service.md (apply method removal)
**Goal:** Replace all staging API documentation with candidate API documentation, reflecting the Palo Alto candidate configuration model.

---

## Architecture

This plan modifies a reference documentation file only. No code changes. The API_REFERENCE.md documents backend service APIs used by route handlers. The staging system's `StagingManager` API surface is replaced by `CandidateManager`; the `NagiosService` apply methods are removed; all other service APIs remain unchanged.

No live config mutation occurs in this file (documentation only). No UI changes. No audit logging changes. This plan produces zero executable code.

---

## Removal Audit

The following sections are **removed** from `.claude/API_REFERENCE.md`:

| Section | Line Range (approx) | Reason |
|---------|---------------------|--------|
| `StagingManager` table header + description | 32-34 | Replaced by CandidateManager |
| `get_staging()` | 38 | No equivalent — candidate uses git, not JSON staging files |
| `save_staging(data)` | 39 | No equivalent — candidate commits directly |
| `save_staging_atomic(data, session_id, lock)` | 40 | No equivalent |
| `clear_staging()` | 41 | Replaced by `discard()` |
| `has_staging()` | 42 | Replaced by `has_session()` |
| `get_staging_info()` | 43 | Replaced by `get_session_info()` |
| `get_lock_owner()` | 44 | Replaced by `get_session_info()` (includes session_id) |
| `can_modify(session_id)` | 45 | Preserved — same name on CandidateManager |
| `validate_or_acquire_lock(session_id)` | 46 | Replaced by `init_session()` |
| `get_lock_status(session_id)` | 47 | Replaced by `get_session_info()` |
| `get_empty_staging_structure()` | 48 | No equivalent — no staging JSON structure |
| `migrate_staging_schema(data)` | 49 | No equivalent — no schema migration needed |
| `add_to_undo_stack(...)` | 50 | Replaced by git commits (automatic per operation) |
| `peek_undo_stack()` | 51 | Replaced by `_get_undo_count()` |
| `pop_undo_stack()` | 52 | Replaced by `undo()` (git reset) |
| `get_undo_stack_count()` | 53 | Replaced by `_get_undo_count()` |
| `clear_undo_stack()` | 54 | No equivalent — undo stack is git history |
| `compute_file_checksum(path)` | 55 | Replaced by `_file_checksum()` (internal) |
| `compute_base_checksums(paths)` | 56 | Replaced by checksums in `.session.json` |
| `update_base_checksums(paths)` | 57 | No equivalent — checksums stored at session init |
| `detect_conflicts()` | 58 | Preserved — same name on CandidateManager |
| `stage_file_creation(path)` | 59 | Replaced by `create_file()` (direct file op) |
| `stage_file_deletion(path)` | 60 | Replaced by `delete_file()` |
| `stage_file_move(src, tgt)` | 61 | Replaced by `move_file()` |
| `stage_folder_creation(path)` | 62 | Replaced by `create_folder()` |
| `stage_folder_deletion(path)` | 63 | Replaced by `delete_folder()` |
| `stage_folder_move(src, tgt)` | 64 | Replaced by `move_folder()` |
| `unstage_operation(op_id, op_type)` | 65 | No equivalent — use undo instead |
| `get_total_staged_count()` | 66 | Replaced by `_get_undo_count()` |

The following `NagiosService` methods are **removed** (dead code per L12-nagios-service.md):

| Method | Reason |
|--------|--------|
| `apply_folder_creations(staging_data)` | Candidate does direct file ops, no apply phases |
| `apply_file_creations(staging_data)` | Same |
| `apply_object_deletions(staging_data)` | Same |
| `apply_object_moves(staging_data)` | Same |
| `apply_object_edits(staging_data)` | Same |
| `apply_object_creations(staging_data)` | Same |
| `apply_file_moves(staging_data)` | Same |
| `apply_folder_moves(staging_data)` | Same |
| `apply_file_deletions(staging_data)` | Same |
| `apply_folder_deletions(staging_data)` | Same |
| `get_typed_staging()` | Same |

---

## Changes

**1. Remove entire `StagingManager` section** (lines 32-66) — All staging API documentation is deleted. Every entry has a candidate equivalent or is dead code (see Removal Audit above).

**2. Remove staging-related `NagiosService` methods** from the NagiosService table (lines 19-29) — The 11 `apply_*` and `get_typed_staging()` methods are deleted. All remaining NagiosService methods (parser management, query, CRUD) are preserved unchanged.

**3. Add `CandidateManager` section** after the NagiosService table, documenting the full public API:

```markdown
## CandidateManager

File-copy candidate system: running config copied to `.candidate/`, git repo inside for undo. All edits modify candidate files directly. Apply copies candidate back to running config.

| Function | What | Returns |
|----------|------|---------|
| init_session(session_id, user_name, user_email) | Copy running config to candidate, init git | OperationResult |
| has_session() | Check if candidate directory exists | bool |
| get_session_info() | Get session metadata + undo count | Optional[Dict] |
| can_modify(session_id) | Check if session can modify candidate | bool |
| get_session_state() | Get session state string | str |
| set_restore_pending() | Mark session as restore-pending | OperationResult |
| discard() | Remove candidate directory | OperationResult |
| to_candidate_path(running_path) | Translate running path to candidate | str |
| to_running_path(candidate_path) | Translate candidate path to running | str |
| edit_object(file_path, line_number, new_attrs, obj_type, ...) | Edit object in candidate | OperationResult |
| delete_object(file_path, line_number, ...) | Delete object from candidate | OperationResult |
| create_object(file_path, obj_type, attrs, ...) | Create object in candidate | OperationResult |
| move_object(source_file, source_line, target_file, ...) | Move object between files in candidate | OperationResult |
| bulk_edit(edits, description) | Bulk edit objects (single commit) | OperationResult |
| bulk_move(moves, description) | Bulk move objects (single commit) | OperationResult |
| bulk_delete(deletes, description) | Bulk delete objects (single commit) | OperationResult |
| analyze_references() | Find name changes and affected references | OperationResult |
| undo() | Git reset HEAD~1 | OperationResult |
| create_file(file_path, description) | Create empty .cfg file in candidate | OperationResult |
| delete_file(file_path, description) | Delete file from candidate | OperationResult |
| move_file(source, target, description) | Move/rename file in candidate | OperationResult |
| create_folder(path, description) | Create folder in candidate | OperationResult |
| delete_folder(path, description) | Delete folder from candidate | OperationResult |
| move_folder(source, target, description) | Move/rename folder in candidate | OperationResult |
| get_diff() | File-level diff: candidate vs running | OperationResult |
| get_file_diff(relative_path, context_lines) | Unified diff for single file | OperationResult |
| get_structured_diff() | Per-object structured diff for commit dialog | OperationResult |
| detect_conflicts() | Check running files for external modifications | List[Dict] |
| validate(nagios_bin) | Run nagios -v against candidate | OperationResult |
| apply(update_references) | Copy candidate to running, remove .candidate/ | OperationResult |
```

**4. Update NagiosService table** — Remove the 11 deleted apply/staging methods. The remaining methods are unchanged:

```markdown
## NagiosService

| Function | What | Returns |
|----------|------|---------|
| get_objects() | Return all parsed objects | List[NagiosObject] |
| find_object_by_index(idx) | Get object by global index | Optional[NagiosObject] |
| find_object_by_stable_key(key) | Get object by stable key | Optional[Tuple[int, NagiosObject]] |
| search_objects(query, type, field, regex) | Search objects | List[NagiosObject] |
| get_object_stats() | Get counts by type and file | Dict |
| get_name_field(object_type) | Get name field for object type | str |
| transform_name(name, find, replace, prefix, suffix, regex) | Transform name with find/replace/prefix/suffix | Optional[str] |
| update_references(objects, old_name, new_name) | Update all references when object renamed | int (count updated) |
| create_object(target_file, obj_type, attrs, after_block_line) | Create new object | OperationResult |
| update_object(file, line, attrs, type) | Update object in place | OperationResult |
| delete_object(file, line) | Delete object | OperationResult |
| move_object(src_file, src_line, tgt_file, type, attrs, insert_line) | Move object between files | OperationResult |
| reload() | Force parser reload | NagiosConfigParser |
```

**5. Preserve GitService, BackupManager, and OperationResult sections** — These are unchanged by the candidate migration.

---

## Error Handling Documentation

The updated API_REFERENCE.md must document error return conventions for CandidateManager methods:
- All mutation methods return `OperationResult(success=False, error="...")` on failure
- Path safety violations return descriptive error messages via `is_safe_path()`
- Parse verification failures include "reverted" in the error message
- Lock contention returns `OperationResult(False, "A candidate session already exists")`

---

## Verification

```bash
# No stale staging references
grep -i "staging" .claude/API_REFERENCE.md
# Expected: zero matches (or only in historical context comments)

# CandidateManager section exists
grep "CandidateManager" .claude/API_REFERENCE.md
# Expected: section header found

# All deleted methods are gone
grep "apply_folder_creations\|apply_file_creations\|apply_object_deletions\|get_typed_staging\|StagingManager" .claude/API_REFERENCE.md
# Expected: zero matches

# All key CandidateManager methods documented
grep "init_session\|has_session\|can_modify\|discard\|to_candidate_path\|edit_object\|detect_conflicts\|validate\|apply" .claude/API_REFERENCE.md
# Expected: all found

# Lint check (documentation file, no code to lint, but verify no syntax issues)
python3 -c "open('.claude/API_REFERENCE.md').read()" && echo "File readable"
```

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | This plan modifies documentation only. The documented CandidateManager API enforces: all edits target `.candidate/`, only `apply()` copies to running config. |
| 2 | UI visual parity | COMPLIANT | No UI changes. Documentation-only modification. |
| 3 | Full audit logging | COMPLIANT | No code changes to audit. The documented `apply()` method triggers audit logging as specified in L03-routes-candidate.md. |
| 4 | Proper error handling | COMPLIANT | Error return conventions documented for CandidateManager methods (OperationResult pattern preserved). |
| 5 | Dead code deletion | COMPLIANT | Removal audit above maps every deleted StagingManager and NagiosService method to its candidate replacement or confirms it is dead code with no replacement needed. |
| 6 | Full functionality migration | COMPLIANT | Removal audit above confirms every StagingManager function has a candidate equivalent or is intentionally dropped (with rationale). No functionality dropped on the floor. |
| 7 | Palo Alto candidate model | COMPLIANT | Documentation explicitly describes the file-copy candidate model: copy to `.candidate/`, edit directly, apply copies back to running. |
| 8 | Change tracking document | COMPLIANT | L00-migration-inventory.md tracks this file at section 4.2 (templates/docs/api-reference.html) and references this L-plan as `[covered]`. |
| 9 | Complete planning before implementation | COMPLIANT | This is a documentation plan. No code changes. All referenced code plans (L01, L03, L12) are already complete. |
| 10 | Linting enforcement | N/A | Documentation-only change. No Python or JavaScript code to lint. |
| 11 | Playwright validation | N/A | Documentation reference file. No UI behavior to validate with Playwright. If the in-app API reference page (`templates/docs/api-reference.html`) is updated separately (covered by L13-doc-text-updates.md), Playwright can verify that page renders correctly. |
