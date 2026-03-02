# Candidate Config — Phase 2: App Wiring + Routes

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Register CandidateManager in the app factory, create all candidate API routes, and add candidate-aware analysis helpers.

**Architecture:** Flask blueprint with 19 endpoints. Each route validates input, checks session lock, calls CandidateManager, returns result. Analysis routes gain `?candidate=1` support via a shared helper.

**Tech Stack:** Python, Flask, pytest

**Branch:** `feature/candidate-config` (continuing from Phase 1)

**Prerequisite:** Phase 1 must be complete. Verify before starting.

---

## Key Codebase Facts

| Fact | Detail |
|------|--------|
| **OperationResult import** | `from nagios_model import OperationResult` — there is no `operation_result` module |
| **ServerConfig paths** | `sc.nagios_bin` (NOT `nagios_binary`) |
| **NagiosValidator.validate()** | Returns `ValidationResult` (not `OperationResult`). Call `.to_dict()` and wrap in OperationResult |
| **Health check location** | NOT on NagiosService. Implemented in `routes/health_checks.py:run_all_checks(objects, obj_to_index, template_lookup, config_paths)` |
| **Health check `config_paths`** | `run_all_checks()` expects a **dict** with keys like `nagios_cfg`/`resource_cfg` — NOT a list of file paths [P2-B] |
| **operation_response()** | On success returns `{"success": True}` + `"data"` only if `result.data is not None`. On error returns `{"error": "..."}` without `"success": false` |
| **helpers.py access** | `get_service()`, `get_staging_manager()`, `get_backup_manager()`, `get_server_config()` — all from `current_app.extensions` |
| **Lock check pattern** | `if not cm.can_modify(session_id): return jsonify({...}), 423` |
| **Session ID source** | ALL existing routes read session_id from `request.headers.get("X-Session-Id")` header — NEVER from JSON body [P2-C] |
| **conftest.py fixtures** | `app`, `client`, `service`, `make_app(config_files_dict)` — all create Flask test apps pointed at tmp_path |
| **`ApiClient.del(url, options)`** | Takes NO data parameter. Only `(url, options)`. Body is NEVER sent for DELETE requests. See `api-client.js:124-126` |
| **`get_audit_user_identity()`** | In `routes/helpers.py:95`. Falls back to staging data for user identity |
| **Direct disk-write routes** | `files.py` has `/api/files/relocate`, `/api/folders/relocate`, `/api/delete` — these bypass staging and write to disk directly. Must be PRESERVED |
| **`bulk_ops.py` staging routes** | `api_apply_rename` and `api_move_objects` use `get_staging_manager()` |
| **verify_apply_integrity()** | In `apply_verification.py:329`. Used by staging apply for post-apply verification. Candidate apply should replicate this pattern [P2-G] |

---

## Prerequisites

**Step 1: Verify Phase 1 is complete**

```bash
cd .worktrees/candidate-config
python3 -m pytest tests/ -v
```

Expected: all tests pass including `test_candidate_manager.py`

**Step 2: Verify candidate_manager.py exists**

```bash
python3 -c "from candidate_manager import CandidateManager; print('OK')"
```

Expected: prints `OK`

---

## Task 1: Register CandidateManager in app factory

**Files:**
- Modify: `app.py`
- Modify: `routes/helpers.py`

**Step 1: Add to app.py**

After the staging_manager setup (around line 133), add:

```python
    from candidate_manager import CandidateManager
    candidate_manager = CandidateManager(
        nagios_config_path,
        nagios_cfg=_server_config.nagios_cfg or "",
    )
    if candidate_manager.has_session():
        logger.info("Clearing stale candidate session from previous server run")
        candidate_manager.discard()
```

After the `app.extensions["server_config"]` line, add:

```python
    app.extensions["candidate"] = candidate_manager
```

**Step 2: Add helper**

In `routes/helpers.py`, after `get_staging_manager()`:

```python
def get_candidate_manager():
    """Get the candidate manager."""
    return current_app.extensions["candidate"]
```

**Step 3: Run tests, lint, commit**

Run: `python3 -m pytest tests/ -v`
Expected: all pass

```bash
ruff check app.py routes/helpers.py
ruff format --check app.py routes/helpers.py
git add app.py routes/helpers.py
git commit -m "feat: register CandidateManager in app factory"
```

---

## Task 2: Backend routes for candidate API

**Files:**
- Create: `routes/candidate.py`
- Create: `tests/test_candidate_routes.py`
- Modify: `routes/__init__.py` (register blueprint)

This task creates all API endpoints. Follow the pattern in existing routes but dramatically simpler — each endpoint validates input, checks session lock, calls CandidateManager, returns result.

**Key design decisions baked in:**
- `GET /api/candidate/objects` normalizes `source_file` to running-config paths (so stable keys match)
- All mutation endpoints translate incoming running-config paths to candidate paths via `cm.to_candidate_path()`
- All mutation endpoints read `session_id` from `request.headers.get("X-Session-Id")` header, NOT from JSON body [P2-C]
- `POST /api/candidate/apply` checks for conflicts before applying [P2-D], creates a backup, runs `verify_apply_integrity()` after apply [P2-G], and supports `deferClear`/`validate` flags [P2-H]
- `GET /api/candidate/health-check` calls `run_all_checks()` with a `config_paths` dict (NOT list) [P2-B]
- `POST /api/candidate/validate` uses `sc.nagios_bin` (NOT `sc.paths.nagios_binary`)
- Error responses use `operation_response()` or `jsonify({"error": "..."})` consistently — no `"success": false` in error payloads [P2-K]
- `POST /api/candidate/file/create` enforces `.cfg` extension [P2-I]
- File/folder listings exclude `backups`/`backup` directories [P2-J]

**Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/candidate/init` | POST | Create candidate session |
| `GET /api/candidate` | GET | Get session status |
| `DELETE /api/candidate` | DELETE | Discard candidate session |
| `POST /api/candidate/edit` | POST | Edit object (translates running->candidate path) |
| `POST /api/candidate/delete-objects` | POST | Delete objects |
| `POST /api/candidate/create` | POST | Create object |
| `POST /api/candidate/move` | POST | Move object between files |
| `POST /api/candidate/undo` | POST | Undo last action |
| `GET /api/candidate/objects` | GET | Parse candidate, normalize paths, return objects |
| `GET /api/candidate/files` | GET | List .cfg files in candidate (normalized paths) |
| `GET /api/candidate/folders` | GET | List folders in candidate (normalized paths) |
| `GET /api/candidate/diff` | GET | Get changed files + unified diff |
| `POST /api/candidate/diff/file` | POST | Per-file unified diff |
| `GET /api/candidate/conflicts` | GET | Check for externally modified files |
| `GET /api/candidate/health-check` | GET | Run health checks on candidate objects |
| `POST /api/candidate/validate` | POST | Run nagios -v on candidate |
| `POST /api/candidate/apply` | POST | Apply candidate to running + reload parser + backup |
| `POST /api/candidate/bulk-edit` | POST | Bulk edit with single commit |
| `POST /api/candidate/bulk-move` | POST | Bulk move with single commit |
| `POST /api/candidate/clear` | POST | Clear candidate after deferred apply (for commit flow) |

**Step 1: Write failing route tests**

Create `tests/test_candidate_routes.py`:

```python
"""Tests for candidate API routes."""

import os
import shutil
import tempfile

import pytest

from app import create_app


@pytest.fixture
def config_dir():
    d = tempfile.mkdtemp()
    hosts = os.path.join(d, "hosts.cfg")
    with open(hosts, "w") as f:
        f.write(
            "define host {\n"
            "    host_name    web-01\n"
            "    alias        Web Server\n"
            "    address      10.0.0.1\n"
            "}\n\n"
            "define host {\n"
            "    host_name    web-02\n"
            "    alias        Web Server 2\n"
            "    address      10.0.0.2\n"
            "}\n"
        )
    services = os.path.join(d, "services.cfg")
    with open(services, "w") as f:
        f.write(
            "define service {\n"
            "    host_name            web-01\n"
            "    service_description  HTTP\n"
            "    check_command        check_http\n"
            "}\n"
        )
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def candidate_app(config_dir):
    application = create_app(config_path=config_dir)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(candidate_app):
    return candidate_app.test_client()


class TestSessionLifecycleRoutes:
    def test_init_creates_session(self, client):
        resp = client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},  # [P2-C]
            json={"user_name": "", "user_email": ""},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]

    def test_init_requires_session_header(self, client):
        """session_id must come from X-Session-Id header, not body."""  # [P2-C]
        resp = client.post(
            "/api/candidate/init",
            json={"session_id": "s1"},  # Body only — no header
        )
        assert resp.status_code == 400

    def test_status_when_no_session(self, client):
        resp = client.get("/api/candidate")
        data = resp.get_json()
        assert not data.get("active", False)

    def test_status_after_init(self, client):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.get("/api/candidate")
        data = resp.get_json()
        assert data["active"]

    def test_discard_removes_session(self, client):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.delete(
            "/api/candidate",
            headers={"X-Session-Id": "s1"},
        )
        assert resp.status_code == 200
        status = client.get("/api/candidate").get_json()
        assert not status.get("active", False)

    def test_double_init_fails(self, client):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s2"},
            json={},
        )
        assert resp.status_code in (200, 409, 500)
        data = resp.get_json()
        assert not data.get("success", True) or "already exists" in data.get("error", "")


class TestCandidateObjectRoutes:
    def test_objects_returns_list(self, client):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.get("/api/candidate/objects")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert len(data["data"]) > 0

    def test_source_file_uses_running_path(self, client, config_dir):
        """Candidate objects should have source_file pointing to running config."""
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.get("/api/candidate/objects")
        data = resp.get_json()["data"]
        for obj in data:
            assert "/.candidate/" not in obj["source_file"]

    def test_objects_without_session_returns_404(self, client):
        resp = client.get("/api/candidate/objects")
        assert resp.status_code == 404


class TestCandidateEditRoutes:
    def test_edit_accepts_running_path(self, client, config_dir):
        """Frontend sends running config paths; backend must translate."""
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        host = next(o for o in objects if o.get("object_type") == "host")
        resp = client.post(
            "/api/candidate/edit",
            headers={"X-Session-Id": "s1"},  # [P2-C]
            json={
                "file_path": host["source_file"],  # Running path
                "line_number": host["line_number"],
                "attributes": {**host["attributes"], "alias": "PathTest"},
                "object_type": "host",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"]

    def test_edit_locked_by_another_session(self, client):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        host = next(o for o in objects if o.get("object_type") == "host")
        resp = client.post(
            "/api/candidate/edit",
            headers={"X-Session-Id": "wrong-session"},  # [P2-C]
            json={
                "file_path": host["source_file"],
                "line_number": host["line_number"],
                "attributes": host["attributes"],
                "object_type": "host",
            },
        )
        assert resp.status_code == 423


class TestCandidateUndoRoute:
    def test_undo_after_edit(self, client):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        host = next(o for o in objects if o.get("object_type") == "host")
        client.post(
            "/api/candidate/edit",
            headers={"X-Session-Id": "s1"},
            json={
                "file_path": host["source_file"],
                "line_number": host["line_number"],
                "attributes": {**host["attributes"], "alias": "Temp"},
                "object_type": "host",
            },
        )
        resp = client.post(
            "/api/candidate/undo",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"]


class TestCandidateDiffRoute:
    def test_diff_after_edit(self, client):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        host = next(o for o in objects if o.get("object_type") == "host")
        client.post(
            "/api/candidate/edit",
            headers={"X-Session-Id": "s1"},
            json={
                "file_path": host["source_file"],
                "line_number": host["line_number"],
                "attributes": {**host["attributes"], "alias": "DiffTest"},
                "object_type": "host",
            },
        )
        resp = client.get("/api/candidate/diff")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert data["data"]["hasChanges"]


class TestCandidateApplyRoute:
    def test_apply_updates_running_config(self, client, config_dir):
        """After candidate apply, GET /api/objects must return updated data."""
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        host = next(o for o in objects if o.get("object_type") == "host")
        client.post(
            "/api/candidate/edit",
            headers={"X-Session-Id": "s1"},
            json={
                "file_path": host["source_file"],
                "line_number": host["line_number"],
                "attributes": {**host["attributes"], "alias": "AfterApply"},
                "object_type": "host",
            },
        )
        resp = client.post(
            "/api/candidate/apply",
            headers={"X-Session-Id": "s1"},  # [P2-C]
            json={},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"]

        # Verify running config was updated via main /api/objects
        running_objects = client.get("/api/objects").get_json()
        # Check the alias was applied
        found = False
        for obj in running_objects:
            if isinstance(obj, dict) and obj.get("attributes", {}).get("alias") == "AfterApply":
                found = True
                break
        assert found, "Running config should reflect applied changes"

    def test_apply_creates_backup(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        client.post(
            "/api/candidate/apply",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        backup_dir = os.path.join(config_dir, "backups")
        if os.path.isdir(backup_dir):
            backups = os.listdir(backup_dir)
            assert any("pre_candidate_apply" in b for b in backups)

    def test_apply_blocked_by_conflicts(self, client, config_dir):
        """Apply should return 409 if running config was modified externally."""  # [P2-D]
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        # Modify running config externally after candidate init
        hosts_file = os.path.join(config_dir, "hosts.cfg")
        with open(hosts_file, "a") as f:
            f.write("\ndefine host {\n    host_name external-change\n    address 1.1.1.1\n}\n")
        resp = client.post(
            "/api/candidate/apply",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        assert resp.status_code == 409
        data = resp.get_json()
        assert "conflicts" in data or "error" in data

    def test_apply_with_defer_clear(self, client, config_dir):
        """deferClear=true should keep candidate directory after apply."""  # [P2-H]
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.post(
            "/api/candidate/apply",
            headers={"X-Session-Id": "s1"},
            json={"deferClear": True},
        )
        assert resp.status_code == 200
        # Candidate session should still exist
        status = client.get("/api/candidate").get_json()
        assert status.get("active", False)


class TestCandidateFileRoutes:
    def test_files_returns_normalized_paths(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.get("/api/candidate/files")
        assert resp.status_code == 200
        data = resp.get_json()
        for f in data["files"]:
            assert "/.candidate/" not in f

    def test_folders_returns_normalized_paths(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.get("/api/candidate/folders")
        assert resp.status_code == 200


class TestCandidateCreateRoute:
    def test_create_object(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        files = client.get("/api/candidate/files").get_json()["files"]
        resp = client.post(
            "/api/candidate/create",
            headers={"X-Session-Id": "s1"},
            json={
                "file_path": files[0],
                "object_type": "host",
                "attributes": {
                    "host_name": "new-host",
                    "alias": "New Host",
                    "address": "10.0.0.99",
                },
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"]


class TestCandidateMoveRoute:
    def test_move_object(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        host = next(o for o in objects if o.get("object_type") == "host")
        files = client.get("/api/candidate/files").get_json()["files"]
        target = next(f for f in files if f != host["source_file"])
        resp = client.post(
            "/api/candidate/move",
            headers={"X-Session-Id": "s1"},
            json={
                "source_file": host["source_file"],
                "source_line": host["line_number"],
                "target_file": target,
                "object_type": "host",
                "attributes": host["attributes"],
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"]


class TestCandidateDeleteObjectsRoute:
    def test_delete_objects(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        svc = next(o for o in objects if o.get("object_type") == "service")
        resp = client.post(
            "/api/candidate/delete-objects",
            headers={"X-Session-Id": "s1"},
            json={
                "objects": [
                    {"file_path": svc["source_file"], "line_number": svc["line_number"]},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"]


class TestCandidateBulkRoutes:
    def test_bulk_edit(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        hosts = [o for o in objects if o.get("object_type") == "host"]
        edits = [
            {
                "file_path": h["source_file"],
                "line_number": h["line_number"],
                "attributes": {**h["attributes"], "alias": f"Bulk-{h['attributes']['host_name']}"},
                "object_type": "host",
            }
            for h in hosts
        ]
        resp = client.post(
            "/api/candidate/bulk-edit",
            headers={"X-Session-Id": "s1"},
            json={
                "edits": edits,
                "description": "Bulk alias update",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"]

    def test_bulk_move(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        objects = client.get("/api/candidate/objects").get_json()["data"]
        host = next(o for o in objects if o.get("object_type") == "host")
        files = client.get("/api/candidate/files").get_json()["files"]
        target = next(f for f in files if f != host["source_file"])
        resp = client.post(
            "/api/candidate/bulk-move",
            headers={"X-Session-Id": "s1"},
            json={
                "moves": [{
                    "source_file": host["source_file"],
                    "source_line": host["line_number"],
                    "target_file": target,
                    "object_type": "host",
                    "attributes": host["attributes"],
                }],
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"]


class TestCandidateFileOperationRoutes:
    def test_create_file(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.post(
            "/api/candidate/file/create",
            headers={"X-Session-Id": "s1"},
            json={
                "file_path": os.path.join(config_dir, "new-test.cfg"),
            },
        )
        assert resp.status_code == 200

    def test_create_file_adds_cfg_extension(self, client, config_dir):
        """File creation auto-appends .cfg if missing."""  # [P2-I]
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.post(
            "/api/candidate/file/create",
            headers={"X-Session-Id": "s1"},
            json={
                "file_path": os.path.join(config_dir, "no-extension"),
            },
        )
        assert resp.status_code == 200
        # Verify the .cfg file was created in candidate
        files = client.get("/api/candidate/files").get_json()["files"]
        assert any("no-extension.cfg" in f for f in files)

    def test_create_file_rejects_bad_filename(self, client, config_dir):
        """Filenames with illegal characters are rejected."""  # [P2-I]
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.post(
            "/api/candidate/file/create",
            headers={"X-Session-Id": "s1"},
            json={
                "file_path": os.path.join(config_dir, 'bad*name.cfg'),
            },
        )
        assert resp.status_code == 400

    def test_delete_file(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        files = client.get("/api/candidate/files").get_json()["files"]
        resp = client.post(
            "/api/candidate/file/delete",
            headers={"X-Session-Id": "s1"},
            json={
                "file_path": files[-1],
            },
        )
        assert resp.status_code == 200

    def test_create_folder(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.post(
            "/api/candidate/folder/create",
            headers={"X-Session-Id": "s1"},
            json={
                "path": os.path.join(config_dir, "newdir"),
            },
        )
        assert resp.status_code == 200

    def test_delete_folder(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        client.post(
            "/api/candidate/folder/create",
            headers={"X-Session-Id": "s1"},
            json={
                "path": os.path.join(config_dir, "deldir"),
            },
        )
        resp = client.post(
            "/api/candidate/folder/delete",
            headers={"X-Session-Id": "s1"},
            json={
                "path": os.path.join(config_dir, "deldir"),
            },
        )
        assert resp.status_code == 200


class TestCandidateConflictsRoute:
    def test_conflicts_none_initially(self, client, config_dir):
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        resp = client.get("/api/candidate/conflicts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert data["data"]["conflicts"] == []


class TestCandidateClearRoute:
    def test_clear_after_deferred_apply(self, client, config_dir):
        """POST /api/candidate/clear removes session after deferred apply."""  # [P2-H]
        client.post(
            "/api/candidate/init",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        client.post(
            "/api/candidate/apply",
            headers={"X-Session-Id": "s1"},
            json={"deferClear": True},
        )
        resp = client.post(
            "/api/candidate/clear",
            headers={"X-Session-Id": "s1"},
            json={},
        )
        assert resp.status_code == 200
        status = client.get("/api/candidate").get_json()
        assert not status.get("active", False)
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_candidate_routes.py -v`
Expected: Failures (routes don't exist yet)

**Step 3: Create `routes/candidate.py`**

```python
"""Candidate config routes."""

import logging
import os
import re

from flask import Blueprint, jsonify, request

from nagios_parser import NagiosConfigParser

from .helpers import (
    get_audit_user_identity,
    get_backup_manager,
    get_candidate_manager,
    get_config_path,
    get_server_config,
    get_service,
    operation_response,
)

logger = logging.getLogger("nagios_bulk_editor.candidate")

candidate_bp = Blueprint("candidate", __name__)


# -- Session lifecycle --


@candidate_bp.route("/api/candidate/init", methods=["POST"])
def candidate_init():
    cm = get_candidate_manager()
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C] [P2-K]
    data = request.get_json() or {}
    result = cm.init_session(
        session_id,
        data.get("user_name", ""),
        data.get("user_email", ""),
    )
    if result.success:
        from audit_service import log_audit
        log_audit(
            "candidate_init",
            user=data.get("user_email", ""),
            session_id=session_id,
        )
    return operation_response(result)


@candidate_bp.route("/api/candidate", methods=["GET"])
def candidate_status():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"active": False})
    info = cm.get_session_info()
    return jsonify({"active": True, "data": info})


@candidate_bp.route("/api/candidate", methods=["DELETE"])
def candidate_discard():
    cm = get_candidate_manager()
    # Force discard (admin break lock) skips session check
    force = request.args.get("force") == "1"
    if not force:
        session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
        if not cm.can_modify(session_id):
            return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    result = cm.discard()
    if result.success:
        from audit_service import log_audit
        identity = get_audit_user_identity()
        log_audit("candidate_discard", user=identity.get("userEmail"))
    return operation_response(result)


# -- Object queries --


@candidate_bp.route("/api/candidate/objects", methods=["GET"])
def get_candidate_objects():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    try:
        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        objects = []
        for i, obj in enumerate(parser.objects):
            d = obj.to_dict()
            d["global_index"] = i
            # Normalize source_file to running config path so stable keys match
            d["source_file"] = cm.to_running_path(d["source_file"])
            objects.append(d)
        logger.info("GET /api/candidate/objects: %d objects", len(objects))
        return jsonify({"success": True, "data": objects})
    except Exception as e:
        logger.error("Failed to parse candidate objects: %s", e)
        return jsonify({"error": str(e)}), 500  # [P2-K]


@candidate_bp.route("/api/candidate/files", methods=["GET"])
def get_candidate_files():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    files = []
    for root, dirs, filenames in os.walk(cm.candidate_path):
        dirs[:] = [  # [P2-J]
            d for d in dirs
            if d not in (".git", "var", "backups", "backup")
            and not d.startswith(".")
        ]
        for filename in filenames:
            if filename.endswith(".cfg"):
                cand_file = os.path.join(root, filename)
                files.append(cm.to_running_path(cand_file))
    return jsonify({"files": sorted(files)})


@candidate_bp.route("/api/candidate/folders", methods=["GET"])
def get_candidate_folders():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    folders = []
    for root, dirs, _files in os.walk(cm.candidate_path):
        dirs[:] = [  # [P2-J]
            d for d in dirs
            if d not in (".git", "var", "backups", "backup")
            and not d.startswith(".")
        ]
        for d in dirs:
            cand_folder = os.path.join(root, d)
            folders.append(cm.to_running_path(cand_folder))
    return jsonify({"folders": sorted(folders)})


# -- Object mutations --


@candidate_bp.route("/api/candidate/edit", methods=["POST"])
def candidate_edit():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    # Frontend sends running-config paths; translate to candidate
    file_path = data.get("file_path", "")
    candidate_file = cm.to_candidate_path(file_path)
    result = cm.edit_object(
        candidate_file,
        data.get("line_number", 0),
        data.get("attributes", {}),
        data.get("object_type", ""),
        inline_comments=data.get("inline_comments"),
        description=data.get("description", ""),
        update_references=data.get("update_references", False),
    )
    if result.success:
        logger.info("Candidate edit: file=%s line=%d type=%s", file_path, data.get("line_number"), data.get("object_type"))
    return operation_response(result)


@candidate_bp.route("/api/candidate/delete-objects", methods=["POST"])
def candidate_delete_objects():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    objects = data.get("objects", [])
    # Translate running paths to candidate paths
    deletes = [
        {
            "file_path": cm.to_candidate_path(obj.get("file_path", "")),
            "line_number": obj.get("line_number", 0),
        }
        for obj in objects
    ]
    result = cm.bulk_delete(deletes, description=data.get("description", ""))
    if result.success:
        logger.info("Candidate delete-objects: %d objects", len(objects))
    return operation_response(result)


@candidate_bp.route("/api/candidate/create", methods=["POST"])
def candidate_create():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    file_path = cm.to_candidate_path(data.get("file_path", ""))
    result = cm.create_object(
        file_path,
        data.get("object_type", ""),
        data.get("attributes", {}),
        after_line=data.get("after_line"),
        inline_comments=data.get("inline_comments"),
        description=data.get("description", ""),
    )
    if result.success:
        logger.info("Candidate create: type=%s file=%s", data.get("object_type"), data.get("file_path"))
    return operation_response(result)


@candidate_bp.route("/api/candidate/move", methods=["POST"])
def candidate_move():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    result = cm.move_object(
        cm.to_candidate_path(data.get("source_file", "")),
        data.get("source_line", 0),
        cm.to_candidate_path(data.get("target_file", "")),
        data.get("object_type", ""),
        data.get("attributes", {}),
        insert_line=data.get("insert_line"),
        description=data.get("description", ""),
    )
    if result.success:
        logger.info("Candidate move: %s -> %s", data.get("source_file"), data.get("target_file"))
    return operation_response(result)


@candidate_bp.route("/api/candidate/undo", methods=["POST"])
def candidate_undo():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    result = cm.undo()
    if result.success:
        logger.info("Candidate undo: %s", result.data.get("description", "") if result.data else "")
    return operation_response(result)


# -- Bulk operations --


@candidate_bp.route("/api/candidate/bulk-edit", methods=["POST"])
def candidate_bulk_edit():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    edits = data.get("edits", [])
    # Translate running paths to candidate paths
    for edit in edits:
        edit["file_path"] = cm.to_candidate_path(edit.get("file_path", ""))
    result = cm.bulk_edit(edits, description=data.get("description", ""))
    if result.success:
        logger.info("Candidate bulk-edit: %d objects", len(edits))
    return operation_response(result)


@candidate_bp.route("/api/candidate/bulk-move", methods=["POST"])
def candidate_bulk_move():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    moves = data.get("moves", [])
    for move in moves:
        move["source_file"] = cm.to_candidate_path(move.get("source_file", ""))
        move["target_file"] = cm.to_candidate_path(move.get("target_file", ""))
    result = cm.bulk_move(moves, description=data.get("description", ""))
    if result.success:
        logger.info("Candidate bulk-move: %d objects", len(moves))
    return operation_response(result)


# -- Diff and conflicts --


@candidate_bp.route("/api/candidate/diff", methods=["GET"])
def candidate_diff():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    result = cm.get_diff()
    return operation_response(result)


@candidate_bp.route("/api/candidate/diff/file", methods=["POST"])
def candidate_file_diff():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    data = request.get_json() or {}
    result = cm.get_file_diff(
        data.get("path", ""),
        context_lines=data.get("context_lines", 3),
    )
    return operation_response(result)


@candidate_bp.route("/api/candidate/conflicts", methods=["GET"])
def candidate_conflicts():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    conflicts = cm.detect_conflicts()
    return jsonify({"success": True, "data": {"conflicts": conflicts}})


# -- File/folder operations --


@candidate_bp.route("/api/candidate/file/create", methods=["POST"])
def candidate_create_file():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    if not file_path:
        return jsonify({"error": "file_path required"}), 400  # [P2-I]
    if not file_path.endswith(".cfg"):  # [P2-I]
        file_path += ".cfg"
    # Validate filename characters  # [P2-I]
    filename = os.path.basename(file_path)
    if re.search(r'[/\\:*?"<>|]', filename):
        return jsonify({"error": 'Filename cannot contain / \\ : * ? " < > |'}), 400
    file_path = cm.to_candidate_path(file_path)
    result = cm.create_file(file_path)
    return operation_response(result)


@candidate_bp.route("/api/candidate/file/delete", methods=["POST"])
def candidate_delete_file():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    file_path = cm.to_candidate_path(data.get("file_path", ""))
    result = cm.delete_file(file_path)
    return operation_response(result)


@candidate_bp.route("/api/candidate/file/move", methods=["POST"])
def candidate_move_file():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    result = cm.move_file(
        cm.to_candidate_path(data.get("source", "")),
        cm.to_candidate_path(data.get("target", "")),
    )
    return operation_response(result)


@candidate_bp.route("/api/candidate/folder/create", methods=["POST"])
def candidate_create_folder():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    path = cm.to_candidate_path(data.get("path", ""))
    result = cm.create_folder(path)
    return operation_response(result)


@candidate_bp.route("/api/candidate/folder/delete", methods=["POST"])
def candidate_delete_folder():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    path = cm.to_candidate_path(data.get("path", ""))
    result = cm.delete_folder(path)
    return operation_response(result)


@candidate_bp.route("/api/candidate/folder/move", methods=["POST"])
def candidate_move_folder():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    data = request.get_json() or {}
    result = cm.move_folder(
        cm.to_candidate_path(data.get("source", "")),
        cm.to_candidate_path(data.get("target", "")),
    )
    return operation_response(result)


# -- Validation and health check --


@candidate_bp.route("/api/candidate/health-check", methods=["GET"])
def candidate_health_check():
    """Run health checks on candidate objects.

    Uses run_all_checks() directly -- NagiosService has no health_check() method.
    config_paths must be a dict with nagios_cfg/resource_cfg keys. [P2-B]
    """
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    try:
        from inheritance import build_template_lookup
        from routes.health_checks import run_all_checks

        parser = NagiosConfigParser(cm.candidate_path)
        parser.parse_all()
        objects = parser.objects
        obj_to_index = {id(obj): i for i, obj in enumerate(objects)}
        template_lookup = build_template_lookup(objects)

        # Build config_paths dict matching what run_all_checks expects  # [P2-B]
        config_paths = {}
        sc = get_server_config()
        if sc:
            # Point to candidate's rewritten nagios.cfg
            candidate_cfg = os.path.join(cm.candidate_path, ".validation-nagios.cfg")
            if os.path.exists(candidate_cfg):
                config_paths["nagios_cfg"] = candidate_cfg
            if hasattr(sc, "resource_cfg") and sc.resource_cfg:
                config_paths["resource_cfg"] = cm.to_candidate_path(sc.resource_cfg)

        issues = run_all_checks(
            objects, obj_to_index, template_lookup,
            config_paths=config_paths,
        )
        summary = {
            "total_issues": len(issues),
            "errors": len([i for i in issues if i["severity"] == "error"]),
            "warnings": len([i for i in issues if i["severity"] == "warning"]),
            "info": len([i for i in issues if i["severity"] == "info"]),
        }
        return jsonify({"success": True, "data": {"issues": issues, "summary": summary}})
    except Exception as e:
        logger.error("Candidate health check failed: %s", e)
        return jsonify({"error": str(e)}), 500  # [P2-K]


@candidate_bp.route("/api/candidate/validate", methods=["POST"])
def candidate_validate():
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    sc = get_server_config()
    # Note: attribute is nagios_bin, NOT nagios_binary
    nagios_bin = sc.nagios_bin if sc else ""
    result = cm.validate(nagios_bin=nagios_bin)
    return operation_response(result)


@candidate_bp.route("/api/candidate/apply", methods=["POST"])
def candidate_apply():
    """Apply candidate config to running config.

    Merged route with: conflict check [P2-D], session header [P2-C],
    post-apply verification [P2-G], deferClear/validate support [P2-H].
    """
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]

    request_data = request.get_json(silent=True) or {}
    defer_clear = request_data.get("deferClear", False)  # [P2-H]
    validate_after = request_data.get("validate", False)  # [P2-H]

    # Check for conflicts before applying  # [P2-D]
    conflicts = cm.detect_conflicts()
    if conflicts:
        return jsonify({
            "error": "Conflicts detected — files have been modified externally",
            "conflicts": conflicts,
            "requiresResolution": True,
        }), 409

    # Create backup BEFORE modifying running config
    bm = get_backup_manager()
    bm.create_backup("pre_candidate_apply")

    # Capture pre-apply state for verification  # [P2-G]
    pre_parser_objects = [obj.to_dict() for obj in get_service().parser.objects]

    # Get diff before apply (for audit log)
    diff_result = cm.get_diff()

    result = cm.apply(keep_candidate=defer_clear)  # [P2-H]
    if result.success:
        # Reload the main service parser so /api/objects sees updated files
        get_service().reload()
        logger.info("Service parser reloaded after candidate apply")

        # Post-apply verification using verify_apply_integrity()  # [P2-G]
        try:
            from apply_verification import verify_apply_integrity

            post_parser_objects = [obj.to_dict() for obj in get_service().parser.objects]
            # Build a minimal staging_data-like dict for verification
            # The candidate diff provides the changed files list
            changed_files = []
            if diff_result and diff_result.success and diff_result.data:
                changed_files = diff_result.data.get("changed_files", [])
            verification = verify_apply_integrity(
                staging_data={},  # Candidate has no staging_data; verification does best-effort
                parsed_objects=post_parser_objects,
                config_path=get_config_path(),
                pre_parser_objects=pre_parser_objects,
            )
            if verification:
                v_status = "passed" if verification["passed"] else "warnings"
                logger.info(
                    "Candidate apply verification: %s (%d objects post-apply, %d files changed)",
                    v_status,
                    len(post_parser_objects),
                    len(changed_files),
                )
            else:
                logger.info(
                    "Candidate apply verified: %d objects in running config",
                    len(post_parser_objects),
                )
        except Exception as e:
            logger.error("Post-apply verification failed: %s", e)

        # Post-apply validation if requested  # [P2-H]
        if validate_after:
            sc = get_server_config()
            nagios_bin = sc.nagios_bin if sc else ""
            if nagios_bin:
                from validator import NagiosValidator
                validator = NagiosValidator(nagios_bin)
                val_result = validator.validate(get_config_path())
                if val_result:
                    logger.info("Post-apply validation: %s", val_result)

        # Audit log
        from audit_service import log_audit
        identity = get_audit_user_identity()
        log_audit(
            "candidate_apply",
            user=identity.get("userEmail"),
            files_changed=len(diff_result.data.get("changed_files", []))
            if diff_result and diff_result.success else 0,
        )
    return operation_response(result)


@candidate_bp.route("/api/candidate/clear", methods=["POST"])
def candidate_clear():
    """Clear candidate session after deferred apply (for commit flow).  # [P2-H]

    Called after a successful git commit when deferClear was used during apply.
    """
    cm = get_candidate_manager()
    if not cm.has_session():
        return jsonify({"error": "No candidate session"}), 404  # [P2-K]
    session_id = request.headers.get("X-Session-Id", "")  # [P2-C]
    if not session_id:
        return jsonify({"error": "X-Session-Id header required"}), 400  # [P2-C]
    if not cm.can_modify(session_id):
        return jsonify({"error": "Locked by another user"}), 423  # [P2-K]
    result = cm.clear_after_commit()
    if result.success:
        from audit_service import log_audit
        identity = get_audit_user_identity()
        log_audit("candidate_clear", user=identity.get("userEmail"))
    return operation_response(result)
```

**Step 4: Register blueprint**

In `routes/__init__.py`, add to imports and registration:

```python
    from .candidate import candidate_bp
    # ...
    app.register_blueprint(candidate_bp)
```

**Step 5: Run tests**

Run: `python3 -m pytest tests/test_candidate_routes.py -v`
Expected: all pass

Run: `python3 -m pytest tests/ -v`
Expected: all pass (no regressions)

**Step 6: Lint and commit**

```bash
ruff check routes/candidate.py tests/test_candidate_routes.py routes/__init__.py
ruff format --check routes/candidate.py tests/test_candidate_routes.py routes/__init__.py
git add routes/candidate.py routes/__init__.py tests/test_candidate_routes.py
git commit -m "feat: candidate API routes with path normalization and parser reload"
```

---

## Task 3: Candidate-aware analysis helpers

Add `get_parser_for_request()` and `get_objects_for_request()` to avoid duplicating analysis routes.

**Files:**
- Modify: `routes/helpers.py`
- Modify: `routes/validation.py` (4 endpoints)
- Modify: `routes/analysis.py` (11 endpoints)
- Modify: `routes/templates.py` (4 endpoints)

**Step 1: Add helpers to `routes/helpers.py`**

```python
def get_parser_for_request():
    """Return appropriate parser based on ?candidate=1 query param.

    Returns (parser, is_candidate) tuple.
    Aborts with 404 if ?candidate=1 is passed but no session exists.  # [P2-E]
    """
    from nagios_parser import NagiosConfigParser

    use_candidate = request.args.get("candidate") == "1"
    if use_candidate:
        cm = get_candidate_manager()
        if cm.has_session():
            parser = NagiosConfigParser(cm.candidate_path)
            parser.parse_all()
            return parser, True
        # Explicit request for candidate but no session — error, don't fallback  # [P2-E]
        from flask import abort
        abort(404, description="Candidate session not active")
    return get_service().parser, False


def get_objects_for_request():
    """Return (objects, is_candidate) where objects is list of NagiosObject.  # [P2-A]

    Returns NagiosObject instances (NOT dicts) because analysis routes call
    .get_name(), .object_type, resolve_inherited_attrs(obj, ...), etc.
    When candidate=1, source_file paths are remapped to running equivalents.
    """
    parser, is_candidate = get_parser_for_request()
    if is_candidate:
        cm = get_candidate_manager()
        # Remap source_file paths to running equivalents for display  # [P2-A]
        for obj in parser.objects:
            obj.source_file = cm.to_running_path(obj.source_file)
    return parser.objects, is_candidate
```

**Step 2: Update each analysis route**

Update these 18 read-only routes (replace `service.get_objects()` or `service.parser` with candidate-aware helpers):

In `routes/analysis.py`:
1. `GET /api/dependencies` — uses `service.get_objects()`
2. `GET /api/inheritance` — uses `service.get_objects()`
3. `GET /api/reference-map` — uses `service.parser.objects`
4. `POST /api/smart-grouping/suggest` — uses `service.get_objects()`
5. `GET /api/duplicate-names` — uses `service.get_objects()`
6. `GET /api/notification-analysis` — uses `service.get_objects()`
7. `GET /api/cleanup-suggestions` — uses `service.get_objects()`
8. `GET /api/object-references/<global_index>` (`routes/analysis.py:1517`) — uses `service.parser`
9. `GET /api/escalation-path/<object_type>/<name>[/<service_desc>]` (`routes/analysis.py:1482`) — uses `service.parser`
10. `GET /api/inheritance/list/<object_type>` — uses `service.get_objects()` [P2-F]
11. `GET /api/templates/issues` — uses `service.get_objects()` [P2-F]

In `routes/validation.py`:
12. `GET /api/summary` — uses `service.get_objects()`
13. `GET /api/health-check` — uses `service.get_objects()`
14. `GET /api/orphans` — uses `service.get_objects()`
15. `GET /api/template-suggestions` — uses `service.get_objects()`

In `routes/templates.py`:
16. `GET /api/templates` — uses `service.get_objects()`
17. `GET /api/inheritance/<key>` — uses `service.get_objects()`
18. `GET /api/validate-use` — uses `service.get_objects()`

**Route 8: `GET /api/object-references/<global_index>`** (`routes/analysis.py:1517`)

Currently:
```python
@bp.route("/api/object-references/<int:global_index>")
def api_object_references(global_index):
    """Return all relationships for an object by global_index."""
    service = get_service()
    p = service.parser
    objects = list(p.objects)
```

Replace with:
```python
@bp.route("/api/object-references/<int:global_index>")
def api_object_references(global_index):
    """Return all relationships for an object by global_index."""
    p, _is_candidate = get_parser_for_request()
    objects = list(p.objects)
```

**Why:** Called from 3 frontend locations (relations-loader.js x2, impact-section.js x1). Without this, selecting an object in candidate mode shows relationships from the running config, not the candidate.

**Route 9: `GET /api/escalation-path/<object_type>/<name>[/<service_desc>]`** (`routes/analysis.py:1482`)

Currently:
```python
@bp.route("/api/escalation-path/<object_type>/<name>")
@bp.route("/api/escalation-path/<object_type>/<name>/<service_desc>")
def api_escalation_path(object_type, name, service_desc=None):
    ...
    service = get_service()
```

Replace `service = get_service()` and `service.parser` / `service.get_objects()` references with:
```python
    p, _is_candidate = get_parser_for_request()
    objects = list(p.objects)
```

**Why:** Not currently called from frontend JS, but is served by the same backend and should be consistent. If a future page links to escalation paths during candidate editing, it would silently use stale data.

**Do NOT change** (mutation routes — candidate has its own endpoints):
- `POST /api/smart-grouping/create` — creates objects directly
- `POST /api/smart-grouping/add-to-group` — modifies objects directly
- `POST /api/validate` — uses nagios binary, candidate has own validate route
- `POST /api/reload` — reloads disk parser, not relevant for candidate

The replacement pattern for each read-only route — change:
```python
service = get_service()
objects = service.get_objects()
```

To:
```python
objects, _is_candidate = get_objects_for_request()
```

Or when the parser itself is needed (not just objects):
```python
p, _is_candidate = get_parser_for_request()
objects = list(p.objects)
```

**Step 3: Run tests, lint, commit**

Run: `python3 -m pytest tests/ -v`

```bash
ruff check routes/helpers.py routes/validation.py routes/analysis.py routes/templates.py
ruff format --check routes/helpers.py routes/validation.py routes/analysis.py routes/templates.py
git add routes/helpers.py routes/validation.py routes/analysis.py routes/templates.py
git commit -m "feat: candidate-aware analysis via get_parser_for_request() helper"
```

---

## Phase Gate: Verification

Before considering Phase 2 complete, ALL of these must pass:

**Step 1: Full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass (existing + candidate_manager + candidate_routes)

**Step 2: Python lint — all modified/created files**

```bash
ruff check app.py routes/helpers.py routes/candidate.py routes/__init__.py routes/validation.py routes/analysis.py routes/templates.py tests/test_candidate_routes.py
ruff format --check app.py routes/helpers.py routes/candidate.py routes/__init__.py routes/validation.py routes/analysis.py routes/templates.py tests/test_candidate_routes.py
```

Expected: 0 errors

**Step 3: Verify old staging system still works**

```bash
python3 -m pytest tests/test_staging_integration.py tests/test_composite_apply.py -v
```

Expected: all pass (old staging untouched)

**Step 4: Verify app starts**

```bash
python3 -c "from app import create_app; app = create_app(); print('OK')"
```

Expected: prints `OK`

**Step 5: Report**

Report: X tests passed, 0 lint errors, Phase 2 complete. Ready for Phase 3 (Frontend).
