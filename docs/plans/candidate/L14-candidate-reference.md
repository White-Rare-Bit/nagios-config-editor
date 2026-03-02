# L14 — `.claude/CANDIDATE_REFERENCE.md` — CREATE

## Purpose
Create comprehensive candidate system reference documentation, replacing STAGING_REFERENCE.md. This document defines the authoritative reference for the Palo Alto-style candidate configuration system.

## Changes
Create `.claude/CANDIDATE_REFERENCE.md` with these sections:

### 1. Overview — The Palo Alto Candidate Model

The candidate configuration system is based on the **Palo Alto Networks methodology**: copy the running config to a candidate directory, edit the candidate, then apply the candidate back to the running config.

**Core invariant — No live config mutation until Apply:** Nothing is written to the live Nagios configuration until the user explicitly clicks Apply in the commit menu. All edits operate exclusively on the `.candidate/` copy. The running config directory remains untouched throughout the entire editing session. This is the foundational safety guarantee of the system.

- File-copy model: running config copied to `.candidate/` directory at session start
- Git repo initialized inside `.candidate/` for undo tracking (each action = one commit)
- All edits modify candidate files directly — never the running config
- Apply = copy candidate back to running config, then remove `.candidate/`
- Discard = delete `.candidate/` directory, running config unchanged

This replaces the old delta-based staging system (`staging_manager.py`, `StagingManager`, `staging.json`), which tracked changes as in-memory dicts (`pendingEdits`, `stagedMoves`, etc.) and applied them in phases. The candidate model operates on real files, eliminating phase-ordering bugs and enabling immediate per-operation validation.

### 2. Session Lifecycle

```
NO SESSION ──(init_session)──> ACTIVE ──(apply)──> NO SESSION
     ^                           |
     |                           v
     └──(discard)── RESTORE_PENDING <──(backup restore into candidate)
```

- **Start**: `init_session(session_id)` — copy running config to `.candidate/`, init git repo, write `.session.json` with baseline checksums, create initial "baseline" commit
- **Edit**: Modify files in `.candidate/` via CandidateManager methods, each action = git commit with descriptive message
- **Undo**: `git reset --hard HEAD~1` — reverts last commit, cleans empty directories
- **Apply**: Conflict check, optional reference update, pre-apply backup, copy `.candidate/` to running config, remove `.candidate/`
- **Discard**: `shutil.rmtree(.candidate/)` — abandons all changes
- **Stale session cleanup**: On startup, discard sessions older than threshold

State transitions tracked via `state` field in `.session.json` (`active` or `restore_pending`).

### 3. CandidateManager API

All methods return `OperationResult(success: bool, error: str = None, data: Any = None)`.

**Session lifecycle:**
- `init_session(session_id, user_name, user_email)` — creates candidate copy
- `has_session()` — returns `True` if `.candidate/` exists
- `get_session_info()` — returns session metadata including undo count
- `can_modify(session_id)` — checks session ownership
- `discard()` — removes `.candidate/` directory
- `get_session_state()` — returns `"active"`, `"restore_pending"`, or `""`
- `set_restore_pending()` — sets state to `"restore_pending"`

**Object operations (all follow the lock/validate/operate/parse-verify/commit pattern):**
- `edit_object(file_path, line_number, new_attrs, obj_type, ...)` — modifies object in candidate
- `delete_object(file_path, line_number, ...)` — deletes object from candidate
- `create_object(file_path, obj_type, attrs, ...)` — adds object to candidate
- `move_object(source_file, source_line, target_file, ...)` — moves object between files in candidate

**Bulk operations (single git commit for batch):**
- `bulk_edit(edits, description)` — edits multiple objects (sorted by file, reverse line order)
- `bulk_move(moves, description)` — moves multiple objects (always appends to target)
- `bulk_delete(deletes, description)` — deletes multiple objects (sorted reverse line order)

**Analysis:**
- `analyze_references()` — finds name changes since baseline, identifies cross-reference impacts
- `get_diff()` — returns file-level change summary + unified diff
- `get_file_diff(relative_path, context_lines)` — returns file-specific unified diff
- `get_structured_diff()` — per-object structured diff for commit dialog
- `detect_conflicts()` — compares baseline checksums to current running config

**File/folder operations:**
- `create_file(file_path)` / `delete_file(file_path)` / `move_file(source, target)`
- `create_folder(path)` / `delete_folder(path)` / `move_folder(source, target)`

**Validation and apply:**
- `validate(nagios_bin)` — runs `nagios -v` on candidate config
- `apply(update_references)` — copies candidate to running config (the ONLY operation that writes to live config)
- `undo()` — reverts last action via `git reset --hard HEAD~1`

### 4. Path Translation

The frontend always works with running-config paths. The route layer translates transparently:

- Frontend sends running-config paths in all requests
- Routes translate incoming paths via `cm.to_candidate_path(running_path)`
- Operations execute on candidate paths
- Responses normalize back via `cm.to_running_path(candidate_path)`
- Objects returned from candidate-aware endpoints always have running-config paths

```python
# Incoming: running config path from frontend
file_path = data.get("file_path")
candidate_path = cm.to_candidate_path(file_path)
# ... operate on candidate_path ...
# Outgoing: normalize back to running path
response_path = cm.to_running_path(candidate_path)
```

### 5. Concurrency

- `fcntl.flock` file lock at `<running_config_path>/.candidate.lock` — process-safe
- One active session at a time (enforced by lock + session check)
- Lock includes session_id, user_name, user_email, timestamp
- Session status: `GET /api/candidate` returns lock status and session info
- Force-discard: `DELETE /api/candidate?force=1` breaks another user's session (logged with breaker identity)

Lock check pattern (every mutation route):
```python
cm = get_candidate_manager()
session_id = request.headers.get("X-Session-Id", "")
if not cm.can_modify(session_id):
    return jsonify({"error": "Session is locked by another user"}), 423
```

### 6. Error Handling

All errors must have proper error handling — no silent failures, no swallowed exceptions.

**HTTP status codes:**
| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Invalid input (missing fields, bad paths) |
| 404 | Resource not found or no candidate session |
| 409 | Conflict (external modifications detected) |
| 423 | Session locked by another user |
| 500 | Internal error |

**Per-operation parse verification:**
After each object mutation, the entire candidate directory is re-parsed via `NagiosConfigParser(self._candidate_path).parse_all()`. If parsing fails (indicating the edit corrupted config file syntax), the change is reverted via `git checkout -- .` and an error is returned immediately. This catches corruption at edit time, not at apply time.

**Apply failure handling:**
If `cm.apply()` fails mid-copy (some files copied, others not):
- The candidate directory is **preserved** (not cleaned up) for retry
- The running config is partially updated — service parser is reloaded to reflect reality
- Response includes `failedPhase`, `applied` count, `errors` list, `candidatePreserved: true`
- User can retry apply or discard the session

**Error response format:**
```python
return jsonify({"error": "descriptive message"}), <status_code>
```

### 7. Audit Logging

All operations must be logged through both the audit logging system (`audit_service.py`) and the application logging system (`logging.getLogger(__name__)`).

**Audit log format** (JSONL via `log_audit()`):
```
AUDIT txn=a1b2c3d4 user="admin@example.com" action=edit type=host name=web01 field=address op=modify from=10.0.0.1 to=10.0.0.2
```

**Transaction ID:** Each apply generates a `txn = uuid.uuid4().hex[:8]` that groups all audit entries from that operation.

**Per-operation audit entries at apply time:**
| Action type | Audit fields |
|-------------|-------------|
| edit | `action="edit", user, txn, type, name, field, op, from_val, to_val` |
| move | `action="move", user, txn, type, name, op="move", from_val, to_val` |
| create | `action="create", user, txn, type, name, op="create"` |
| delete | `action="delete", user, txn, type, name, op="delete"` |
| file_create | `action="create", user, txn, op="file_create", path` |
| file_delete | `action="delete", user, txn, op="file_delete", path` |
| file_move | `action="move", user, txn, op="file_move", path` |
| folder_create | `action="create", user, txn, op="folder_create", path` |
| folder_delete | `action="delete", user, txn, op="folder_delete", path` |
| folder_move | `action="move", user, txn, op="folder_move", path` |

**Structured application logging for apply:**
```python
log.info("Candidate apply started: session_id=%s, txn=%s", session_id, txn)
log.info("Candidate apply completed: session_id=%s, txn=%s, success=%s", session_id, txn, result.success)
log.error("Candidate apply failed: session_id=%s, txn=%s, phase=%s, errors=%s", session_id, txn, failed_phase, errors)
```

**Force-discard logging:** When `DELETE /api/candidate?force=1` breaks another user's session, log the breaker's identity via both `log.warning()` and `log_audit(action="force_discard", user=breaker_session, victim=victim_email)`.

**Audit failure is non-fatal:** If `log_audit()` raises, log a warning and continue. The apply already succeeded.

### 8. Frontend Integration

- `CandidateApi` (candidate-api.js) wraps all `/api/candidate/*` endpoints
- `Explorer.state.candidateActive` tracks whether a session is active
- `Explorer.state.candidateDiff` caches diff data for change count badges
- All mutations call CandidateApi, which sends `X-Session-Id` header, then call `refreshAfterObjectChange()` to reload the object list
- Read endpoints accept `?candidate=1` query param to return objects from the candidate directory instead of running config
- No client-side staging state maps (`pendingEdits`, `stagedMoves`, etc.) — all state lives server-side in the `.candidate/` directory

### 9. API Endpoints

All endpoints under `/api/candidate/*` — see L03-routes-candidate.md for full implementation details.

**Session lifecycle:**
| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/init` | POST | Initialize candidate session |
| `/api/candidate` | GET | Get session status |
| `/api/candidate` | DELETE | Discard session (`?force=1` to break lock) |

**Object operations:**
| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/objects` | GET | Parse candidate, return objects with running-config paths |
| `/api/candidate/files` | GET | List .cfg files in candidate |
| `/api/candidate/folders` | GET | List folders in candidate |
| `/api/candidate/edit` | POST | Edit object attributes |
| `/api/candidate/delete-objects` | POST | Delete objects |
| `/api/candidate/create` | POST | Create object |
| `/api/candidate/move` | POST | Move object between files |
| `/api/candidate/undo` | POST | Undo last action |

**Bulk operations:**
| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/bulk-edit` | POST | Edit multiple objects |
| `/api/candidate/bulk-move` | POST | Move multiple objects |

**Diff, analysis, and validation:**
| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/diff` | GET | File-level changes + unified diff |
| `/api/candidate/diff/structured` | GET | Per-object structured diff (for commit dialog) |
| `/api/candidate/diff/file` | POST | Single-file unified diff |
| `/api/candidate/analyze-references` | GET | Preview cross-reference updates |
| `/api/candidate/conflicts` | GET | Detect external modifications |
| `/api/candidate/health-check` | GET | Run health checks on candidate objects |
| `/api/candidate/validate` | POST | Run `nagios -v` on candidate config |

**Apply:**
| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/apply` | POST | Conflict check, optional reference update, backup, copy to running |

**File/folder operations:**
| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/file/create` | POST | Create .cfg file |
| `/api/candidate/file/delete` | POST | Delete file |
| `/api/candidate/file/move` | POST | Move/rename file |
| `/api/candidate/folder/create` | POST | Create folder |
| `/api/candidate/folder/delete` | POST | Delete folder |
| `/api/candidate/folder/move` | POST | Move/rename folder |

### 10. Commit Workflow

```
User clicks Commit button
    |
CandidateApi.getStructuredDiff() + CandidateApi.analyzeReferences()
    |
Build commit dialog with per-object changes view
    |
User enters commit message + checks "Update references"
    |
POST /api/candidate/apply {update_references: true}
    |
POST /api/git/commit {message, user_name, user_email}
    |
Show git result panel (terminal-style)
    |
Reload page (session cleared by apply)
```

### 11. Stable Keys

Objects identified by stable key `"source_file|object_type|name"` instead of mutable `global_index`:

```python
from nagios_model import generate_stable_key
stable_key = generate_stable_key(obj.source_file, obj.object_type, obj.get_name())
```

Stable keys survive parser reloads and index changes. Helper functions (`generate_stable_key`, `parse_stable_key`, `generate_stable_key_for_object`) live in `nagios_model.py`.

### 12. Verification Model — Continuous vs Post-Apply

The old staging system used `apply_verification.py` for post-apply verification (file-level git diff checks + object-level re-parse). The candidate system replaces this with **continuous per-operation validation**:

- Each object mutation re-parses the entire candidate via `NagiosConfigParser` immediately after the edit
- If parsing fails, the change is auto-reverted via `git checkout -- .`
- This catches corruption at edit time (immediate user feedback) instead of at apply time (delayed discovery)
- Apply is a straightforward file copy of already-validated files — no delta/phase system that could apply wrong changes

**Dead code deletion:** `apply_verification.py` and all references to it are deleted (see L12-apply-verification.md). The staging system's phase-based apply methods in `nagios_service.py` (~960 lines) are also deleted (see L12-nagios-service.md). No post-apply verification code is retained.

## UI Visual Parity

The reference doc must instruct that the `.claude/CANDIDATE_REFERENCE.md` include a statement that the candidate migration preserves visual parity with the existing UI:

- All visual indicators (staged badges, color-coded tree items, strikethrough for deletions, green for creations) remain visually identical
- CSS class names (`staged-creation`, `staged-for-deletion`, `staged-indicator--new`, etc.) are preserved — they describe UI state, not implementation
- The commit dialog layout, diff views, and change summaries maintain the same visual structure
- No gratuitous UI changes during the migration

## Dead Code Deletion

The reference doc must document that the following are fully deleted with no remnants left behind:

| Deleted item | Size | L-Plan |
|-------------|------|--------|
| `staging_manager.py` | 1,697 lines | L12-staging-manager.md |
| `apply_verification.py` | 376 lines | L12-apply-verification.md |
| `routes/staging.py` | 2,207 lines | L04-routes-staging.md |
| `templates/docs/staging-system.html` | - | L13-doc-templates.md |
| `.claude/STAGING_REFERENCE.md` | - | L14-staging-reference.md |
| `nagios_service.py` apply methods | ~960 lines | L12-nagios-service.md |
| Client-side staging state maps | ~175 references | L07/L08/L09/L10/L11 |
| Old staging tests (5 files) | - | L12-test-deletions.md |

Any functionality that has zero use in the candidate system is deleted, not left behind.

## Functionality Migration Completeness

The reference doc must confirm that all functionality from the staging system has been migrated to the candidate system:

| Staging capability | Candidate equivalent | L-Plan |
|-------------------|---------------------|--------|
| `pendingEdits` dict | `cm.edit_object()` with git commit | L01 |
| `stagedMoves` dict | `cm.move_object()` with git commit | L01 |
| `stagedCreations` array | `cm.create_object()` with git commit | L01 |
| `stagedObjectDeletions` set | `cm.delete_object()` with git commit | L01 |
| `stagedFileCreations/Deletions/Moves` | `cm.create_file/delete_file/move_file()` | L01 |
| `stagedFolderCreations/Deletions/Moves` | `cm.create_folder/delete_folder/move_folder()` | L01 |
| Undo stack (UndoStackManager) | Git commits + `git reset --hard HEAD~1` | L01 |
| Conflict detection (ChecksumManager) | Baseline checksums in `.session.json` | L01 |
| Apply phases (object composite, file moves, etc.) | `cm.apply()` file copy | L01 |
| Post-apply verification | Continuous per-operation parse verification | L01 |
| Reference analysis + update | `cm.analyze_references()` + deferred `_update_references()` | L01 |
| Staging diff + commit dialog | `cm.get_structured_diff()` + commit dialog | L01, L09 |
| Lock management | `fcntl.flock` file lock + session check | L01 |
| Backup on apply | `backup_manager.create_backup("pre_candidate_apply")` | L01 |

Nothing is dropped on the floor.

## Linting Enforcement

All code produced under this plan must pass linting before committing:

- **Python**: Ruff (`ruff check` and `ruff format --check`) — no lint warnings, no formatting violations
- **JavaScript**: ESLint (`npx eslint`) — no errors, no warnings
- **No dirty commits**: Linting is enforced as a gate before every commit during implementation

## Playwright Validation

Playwright tests must validate the migrated UI where it makes sense:

- Session initialization and status display
- Object editing through the candidate system
- Undo functionality
- Commit dialog display with structured diff
- Apply workflow (conflict detection, reference update opt-in)
- Session discard and lock release
- Visual parity checks (badges, color indicators, tree item states)

These tests are written and run incrementally as each layer is implemented, ensuring each migrated part works as expected before proceeding to the next. See `docs/plans/2026-02-18-e2e-playwright-test-plan.md` for the broader testing strategy.

## Change Tracking

The ground-truth migration inventory (`L00-migration-inventory.md`) is the authoritative change tracking document. It enumerates every staging reference across 63 files (~1,300 references) and tracks coverage by L-plan:

- Every Python file with staging references: 22 files, all `[covered]`
- Every JavaScript file with staging references: 25 files, all `[covered]`
- Every CSS file with staging selectors: 2 files, all `[covered]`
- Every HTML template with staging text: 14 files, all `[covered]`
- Critical behavior gaps: 6 identified, all `[resolved]`
- Contradictions: 3 identified, all `[resolved]`

This inventory is maintained and ticked off as implementation proceeds, ensuring nothing is missed.

## Verification

- `.claude/CANDIDATE_REFERENCE.md` exists and is comprehensive
- Referenced by CLAUDE.md (documentation index updated)
- All 11 commandments addressed in the reference content
- Replaces `.claude/STAGING_REFERENCE.md` (which is deleted by L14-staging-reference.md)

---

## Commandments Compliance

| # | Commandment | Status | How addressed |
|---|-------------|--------|---------------|
| 1 | No live config mutation until Apply | COMPLIANT | Section 1 states "Nothing is written to the live Nagios configuration until the user explicitly clicks Apply" as the core invariant. Section 3 confirms `apply()` is the ONLY operation that writes to live config. |
| 2 | UI visual parity | COMPLIANT | "UI Visual Parity" section requires identical visual indicators, preserved CSS class names, and no gratuitous UI changes. |
| 3 | Full audit logging | COMPLIANT | Section 7 documents full audit logging requirements: per-operation audit entries, transaction IDs, structured application logging, force-discard logging, and non-fatal audit failure handling. |
| 4 | Proper error handling | COMPLIANT | Section 6 documents HTTP status codes, per-operation parse verification with auto-revert, apply failure handling with candidate preservation, and the error response format. No silent failures. |
| 5 | Dead code deletion | COMPLIANT | "Dead Code Deletion" section enumerates all files and code blocks deleted with line counts and L-plan references. |
| 6 | Full functionality migration | COMPLIANT | "Functionality Migration Completeness" section maps every staging capability to its candidate equivalent with L-plan references. Explicitly states "Nothing is dropped on the floor." |
| 7 | Palo Alto candidate model | COMPLIANT | Section 1 opens with "based on the Palo Alto Networks methodology: copy the running config to a candidate directory, edit the candidate, then apply the candidate back to the running config." |
| 8 | Change tracking document | COMPLIANT | "Change Tracking" section identifies `L00-migration-inventory.md` as the authoritative change tracking document covering 63 files and ~1,300 references, maintained and ticked off during implementation. |
| 9 | Complete planning before implementation | COMPLIANT | This plan (L14) is part of the complete planning phase. The reference doc it creates is documentation, not implementation code. All 76+ L-plans exist before any code changes begin. |
| 10 | Linting enforcement | COMPLIANT | "Linting Enforcement" section requires Ruff (Python) and ESLint (JavaScript) to pass before every commit. No dirty commits. |
| 11 | Playwright validation | COMPLIANT | "Playwright Validation" section lists specific UI areas to validate with Playwright tests, run incrementally per layer, referencing the broader e2e test plan. |
