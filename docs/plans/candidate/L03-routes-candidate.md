# L03: routes/candidate.py — CREATE

**Layer:** 3 — App Wiring + Routes
**Action:** CREATE
**Path:** `routes/candidate.py`
**Dependencies:** L01 (CandidateManager), L03-routes-helpers.md (get_candidate_manager)
**Goal:** Create Flask blueprint with all candidate API endpoints (~20 routes).

---

## Architecture

All candidate mutation routes follow this pattern:
1. Get session ID from `X-Session-Id` header (never from JSON body)
2. Check `cm.can_modify(session_id)` — return 423 if locked by another session
3. Translate incoming running-config paths to candidate paths via `cm.to_candidate_path()`
4. Perform the operation
5. Return JSON response

All candidate read routes:
1. Check `cm.has_session()` — return 404 if no session
2. Fetch data from candidate
3. Normalize paths back to running equivalents for the frontend

## Blueprint

```python
from flask import Blueprint, jsonify, request
bp = Blueprint("candidate", __name__)
```

## Endpoints

### Session Lifecycle

| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/init` | POST | `init_session()` — requires `X-Session-Id` header |
| `/api/candidate` | GET | `get_status()` — returns session status |
| `/api/candidate` | DELETE | `discard()` — supports `?force=1` to bypass session check |

### Object Operations

| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/objects` | GET | `get_objects()` — parse candidate, normalize paths |
| `/api/candidate/files` | GET | `get_files()` — list .cfg files in candidate |
| `/api/candidate/folders` | GET | `get_folders()` — list folders in candidate |
| `/api/candidate/edit` | POST | `edit_object()` — translates paths |
| `/api/candidate/delete-objects` | POST | `delete_objects()` — translates paths |
| `/api/candidate/create` | POST | `create_object()` — translates paths |
| `/api/candidate/move` | POST | `move_object()` — translates both paths |
| `/api/candidate/undo` | POST | `undo()` |

### Bulk Operations

| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/bulk-edit` | POST | `bulk_edit()` — translates all paths |
| `/api/candidate/bulk-move` | POST | `bulk_move()` — translates all paths |

### Diff, Analysis & Validation

| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/diff` | GET | `get_diff()` — file-level changes + unified diff |
| `/api/candidate/diff/structured` | GET | `get_structured_diff()` — per-object structured changes (see below) |
| `/api/candidate/diff/file` | POST | `get_file_diff()` |
| `/api/candidate/analyze-references` | GET | `analyze_references()` — preview cross-reference updates for pending name changes |
| `/api/candidate/conflicts` | GET | `detect_conflicts()` |
| `/api/candidate/health-check` | GET | `health_check()` — runs run_all_checks on candidate objects |
| `/api/candidate/validate` | POST | `validate()` — runs nagios -v |

### Apply

| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/apply` | POST | `apply()` — conflict check, optional reference update, backup, apply, reload parser |

### File/Folder Operations

| Route | Method | Function |
|-------|--------|----------|
| `/api/candidate/file/create` | POST | `create_file()` — auto-appends .cfg |
| `/api/candidate/file/delete` | POST | `delete_file()` |
| `/api/candidate/file/move` | POST | `move_file()` |
| `/api/candidate/folder/create` | POST | `create_folder()` |
| `/api/candidate/folder/delete` | POST | `delete_folder()` |
| `/api/candidate/folder/move` | POST | `move_folder()` |

## Key Implementation Details

### Session ID handling
```python
session_id = request.headers.get("X-Session-Id", "")
```

### Lock check pattern
```python
cm = get_candidate_manager()
if not cm.can_modify(session_id):
    return jsonify({"error": "Session is locked by another user"}), 423
```

### Path translation pattern
```python
# Incoming: running config path from frontend
file_path = data.get("file_path") or data.get("source_file")
# Translate to candidate path
candidate_path = cm.to_candidate_path(file_path)
```

### Apply endpoint (most complex)
1. Check conflicts via `cm.detect_conflicts()` — return 409 if found
2. Read `update_references` from request body (default `False`)
3. Call `cm.apply(update_references=update_references)` — updates refs if requested, copies candidate to running, removes `.candidate/`
4. Reload main service parser via `get_service().reload()`
5. Write audit log entries (see Audit Logging below)
6. Return success response

No `deferClear` needed. Candidate apply copies files to running config, then clears the candidate directory. If git commit fails after that, files are already on disk — git can still commit them. This is a simpler flow than the staging system's deferred clear.

### Objects endpoint path normalization
```python
# Parse candidate config
from nagios_parser import NagiosConfigParser
parser = NagiosConfigParser(cm.candidate_path)
parser.parse_all()
# Normalize source_file to running paths for the frontend
objects = []
for obj in parser.objects:
    d = obj.to_dict()
    d["source_file"] = cm.to_running_path(obj.source_file)
    objects.append(d)
```

## Deferred Reference Updates

References are NOT updated at edit time. The candidate system preserves the staging system's UX: users see a reference preview at commit time and explicitly opt in before apply.

Flow:
1. User renames an object (e.g., host "web01" → "web02") via `edit_object()` — only the name changes, no cross-references touched
2. User opens commit dialog → dialog calls `GET /api/candidate/analyze-references`
3. Dialog shows: "3 references to web01 will be updated" with the "Update references" checkbox
4. User clicks Apply with checkbox checked → `POST /api/candidate/apply` with `update_references: true`
5. Apply runs `_update_references()` for each name change, commits the ref updates, THEN copies to running

## Structured Diff Endpoint

`GET /api/candidate/diff/structured` returns per-object change data for the commit dialog.

### Implementation
1. Get baseline hash via `cm._get_baseline_hash()`
2. Parse objects at baseline: for each .cfg file in `git ls-tree --name-only <baseline>`, run `git show <baseline>:<file>`, parse with `NagiosConfigParser`
3. Parse objects at HEAD: `NagiosConfigParser(cm.candidate_path).parse_all()`
4. Match objects between baseline and HEAD by `(source_file, object_type, name)` stable key
5. Classify changes per file: additions (HEAD only), removals (baseline only), modifications (both, attrs differ)
6. For modifications, compute field-level diffs: `{field, old_value, new_value}`
7. Normalize all paths to running equivalents for the frontend

### Response Format
```json
{
  "success": true,
  "files": [
    {
      "path": "hosts/web-servers.cfg",
      "status": "modified",
      "additions": [
        {"object_type": "host", "name": "web03", "attributes": {...}}
      ],
      "removals": [
        {"object_type": "host", "name": "old-host", "attributes": {...}}
      ],
      "modifications": [
        {
          "object_type": "host",
          "name": "web01",
          "changed_fields": [
            {"field": "address", "old_value": "10.0.0.1", "new_value": "10.0.0.2"}
          ]
        }
      ]
    }
  ],
  "counts": {
    "files_changed": 3,
    "objects_added": 1,
    "objects_removed": 1,
    "objects_modified": 2,
    "fields_changed": 5
  },
  "file_operations": {
    "files_created": ["new-hosts.cfg"],
    "files_deleted": ["old-hosts.cfg"],
    "files_moved": [{"from": "a.cfg", "to": "b.cfg"}],
    "folders_created": [],
    "folders_deleted": [],
    "folders_moved": []
  }
}
```

### Performance
This endpoint does two full parses of the config. It's only called once when the commit dialog opens, so this is acceptable. For large configs (~5000 objects), expect ~200-500ms.

## Analyze-References Endpoint

`GET /api/candidate/analyze-references` delegates to `cm.analyze_references()` (see L01).

### Implementation
```python
@bp.route("/api/candidate/analyze-references", methods=["GET"])
def analyze_references():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"nameChanges": [], "totalReferences": 0})
    result = cm.analyze_references()
    if not result.success:
        return jsonify({"error": result.error}), 500
    # Normalize paths to running equivalents
    for nc in result.data["nameChanges"]:
        for ref in nc["references"]:
            ref["sourceFile"] = cm.to_running_path(ref["sourceFile"])
    return jsonify(result.data)
```

### Response Format
Matches the staging system's format for frontend compatibility:
```json
{
  "nameChanges": [
    {
      "objectType": "host",
      "oldName": "web01",
      "newName": "web02",
      "referenceCount": 3,
      "references": [
        {
          "objectType": "hostgroup",
          "objectName": "web-servers",
          "field": "members",
          "sourceFile": "hostgroups/web.cfg",
          "oldValue": "web01,web03",
          "newValue": "web02,web03"
        }
      ]
    }
  ],
  "totalReferences": 3
}
```

## Force-Discard Logging

When `DELETE /api/candidate?force=1` is called (breaking another user's session), log the breaker's identity:

```python
if force:
    breaker_session = request.headers.get("X-Session-Id", "unknown")
    victim_info = cm.get_session_info() or {}
    log.warning(
        "Candidate session force-discarded: breaker=%s victim_session=%s victim_user=%s",
        breaker_session,
        victim_info.get("session_id", "unknown"),
        victim_info.get("user_email", "unknown"),
    )
    log_audit(
        action="force_discard",
        user=breaker_session,
        victim=victim_info.get("user_email", ""),
    )
```

This runs **before** calling `cm.discard()` (which deletes the session info).

## Audit Logging

The apply endpoint writes structured audit log entries matching the format used by the staging system's `_write_apply_audit_log()` in `routes/staging.py`.

### Transaction ID

Generate a transaction ID to group all audit entries from a single apply:

```python
import uuid
txn = uuid.uuid4().hex[:8]
```

### User Identity

Extract from session info (stored during `init_session`):

```python
from routes.helpers import format_audit_user
session_info = cm.get_session_info()
user = format_audit_user(
    name=session_info.get("user_name", ""),
    email=session_info.get("user_email", ""),
)
```

### Per-Operation Entries

Parse the candidate's git log to extract what changed, then emit one `log_audit()` call per operation. The candidate git history is the source of truth (each commit = one user action).

| Action type | Audit fields |
|-------------|-------------|
| edit | `action="edit", user, txn, type, name, field, op, from_val, to_val` |
| move | `action="move", user, txn, type, name, op="move", from_val=<rel_path>, to_val=<rel_path>` |
| create | `action="create", user, txn, type, name, op="create"` |
| delete | `action="delete", user, txn, type, name, op="delete"` |
| file_create | `action="create", user, txn, op="file_create", path=<rel_path>` |
| file_delete | `action="delete", user, txn, op="file_delete", path=<rel_path>` |
| file_move | `action="move", user, txn, op="file_move", path=<rel_path>` |
| folder_create | `action="create", user, txn, op="folder_create", path=<rel_path>` |
| folder_delete | `action="delete", user, txn, op="folder_delete", path=<rel_path>` |
| folder_move | `action="move", user, txn, op="folder_move", path=<rel_path>` |

### Output Format

Each entry produces a line like:

```
AUDIT txn=a1b2c3d4 user="admin@example.com" action=edit type=host name=web01 field=address op=modify from=10.0.0.1 to=10.0.0.2
```

### Structured Logging for Apply Start/Result

```python
log.info("Candidate apply started: session_id=%s, txn=%s", session_id, txn)
# ... perform apply ...
log.info("Candidate apply completed: session_id=%s, txn=%s, success=%s", session_id, txn, result.success)
```

On failure:
```python
log.error("Candidate apply failed: session_id=%s, txn=%s, phase=%s, errors=%s", session_id, txn, failed_phase, errors)
```

### Error Entries

If errors occurred during apply, emit one audit entry per error:

```python
if errors:
    for error in errors:
        log_audit(action="apply_error", user=user, txn=txn, error=str(error))
```

### Audit Logging Failure

Audit logging failure is non-fatal. If `log_audit()` raises, log a warning and continue. The apply itself already succeeded at this point.

## Apply Failure Handling

Modeled after `_handle_apply_failure()` in `routes/staging.py`. Handles the case where `cm.apply()` fails mid-way through copying candidate files to the running config.

### Failure Scenarios

The apply copies candidate files to running config one by one. If this fails mid-way:
- Some running config files have been updated, others have not
- The running config is in a partially-applied state
- The candidate directory is **preserved** (not cleaned up) so the user can retry

### Response Format

```python
return jsonify({
    "success": False,
    "error": f"Apply failed: {error_message}. Candidate preserved for retry.",
    "failedPhase": "copy_to_running",  # or "delete_orphans", "cleanup"
    "applied": applied_count,           # number of files successfully copied
    "errors": [str(e) for e in errors],
    "candidatePreserved": True,
}), 500
```

### Parser Reload After Failure

Even on failure, reload the main service parser to reflect any partial changes that did land on disk:

```python
service = get_service()
service.reload()
```

### Candidate Preservation

On failure, the candidate directory is intentionally **preserved**, not cleaned up. This allows:
1. The user can inspect what went wrong
2. The user can retry the apply (the candidate still has the full intended state)
3. The user can discard the session if they want to abandon the changes

### Retry Behavior

The user can retry by calling `POST /api/candidate/apply` again. The apply endpoint re-runs conflict detection before each attempt. If the running config was partially updated, the conflict checker will detect that baseline checksums no longer match for the updated files — but since those files now match the candidate content, the apply will overwrite them again harmlessly.

## Change Tracking

- [ ] Create `routes/candidate.py` with Blueprint
- [ ] **Session Lifecycle routes:**
  - [ ] `POST /api/candidate/init` — init_session()
  - [ ] `GET /api/candidate` — get_status()
  - [ ] `DELETE /api/candidate` — discard() with force support
- [ ] **Object Operations routes:**
  - [ ] `GET /api/candidate/objects` — parse + normalize paths
  - [ ] `GET /api/candidate/files` — list .cfg files
  - [ ] `GET /api/candidate/folders` — list folders
  - [ ] `POST /api/candidate/edit` — translate paths
  - [ ] `POST /api/candidate/delete-objects` — translate paths
  - [ ] `POST /api/candidate/create` — translate paths
  - [ ] `POST /api/candidate/move` — translate both paths
  - [ ] `POST /api/candidate/undo`
- [ ] **Bulk Operations routes:**
  - [ ] `POST /api/candidate/bulk-edit`
  - [ ] `POST /api/candidate/bulk-move`
- [ ] **Diff, Analysis & Validation routes:**
  - [ ] `GET /api/candidate/diff` — file-level + unified diff
  - [ ] `GET /api/candidate/diff/structured` — per-object structured changes
  - [ ] `POST /api/candidate/diff/file`
  - [ ] `GET /api/candidate/analyze-references`
  - [ ] `GET /api/candidate/conflicts`
  - [ ] `GET /api/candidate/health-check`
  - [ ] `POST /api/candidate/validate`
- [ ] **Apply route:**
  - [ ] `POST /api/candidate/apply` — conflict check, backup, apply, reload, audit log
- [ ] **File/Folder Operations routes:**
  - [ ] `POST /api/candidate/file/create`
  - [ ] `POST /api/candidate/file/delete`
  - [ ] `POST /api/candidate/file/move`
  - [ ] `POST /api/candidate/folder/create`
  - [ ] `POST /api/candidate/folder/delete`
  - [ ] `POST /api/candidate/folder/move`
- [ ] Implement force-discard logging (breaker identity)
- [ ] Implement apply audit logging with transaction ID
- [ ] Implement apply failure handling with candidate preservation
- [ ] Register blueprint in app.py

## Verification

```bash
python3 -m pytest tests/test_candidate_routes.py -v
python3 -m ruff check routes/candidate.py
python3 -m ruff format --check routes/candidate.py
```

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** All mutation routes operate on the candidate directory only. The `apply()` endpoint is the sole path that copies candidate to running config, gated by conflict detection and user confirmation.
- [x] **C2 — UI visual parity.** N/A — API routes only; frontend consuming these routes is planned in separate layers. Response formats match staging system equivalents for frontend compatibility.
- [x] **C3 — Full audit logging.** Apply endpoint writes structured audit log entries per operation with transaction IDs. Force-discard logs breaker identity. Apply start/result logged via application logger. Audit logging failure is non-fatal.
- [x] **C4 — Proper error handling.** Lock check returns 423, missing session returns 404, conflicts return 409, apply failures return 500 with preserved candidate. No silent failures — all error paths return explicit error messages and appropriate HTTP status codes.
- [x] **C5 — Dead code deletion.** N/A — this is a new file (CREATE action); no dead code to remove.
- [x] **C6 — Full functionality migration.** All staging system endpoint equivalents are covered: object CRUD, bulk ops, diff, structured diff, reference analysis, conflicts, health check, validate, apply, file/folder ops, undo.
- [x] **C7 — Palo Alto candidate model.** Routes implement copy-edit-apply: init copies config, edit/create/delete/move operate on candidate, apply copies back to running. Path translation ensures frontend sees running-config paths throughout.
- [x] **C8 — Change tracking.** Tickable checklist added above covering all ~26 routes plus supporting features.
- [x] **C9 — Complete planning before implementation.** This document fully specifies all endpoints, patterns, response formats, error handling, audit logging, and failure recovery before any code is written.
- [x] **C10 — Linting enforcement.** Ruff check and format commands included in Verification section.
- [x] **C11 — Playwright validation.** N/A for this backend route layer. Playwright tests will validate the full flow once frontend is connected (L05+). Route-level testing is covered by test_candidate_routes.py (see L03-test-candidate-routes.md).
