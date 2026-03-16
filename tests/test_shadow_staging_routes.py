"""Integration tests for shadow-copy-based staging routes."""

import json
import os
import shutil
import tempfile

import pytest

from app import create_app


@pytest.fixture
def shadow_app(tmp_path):
    """Create Flask app with isolated config and shadow dirs for testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "hosts.cfg").write_text(
        "define host {\n    host_name   web-01\n    alias       Web Server 01\n    address     10.0.0.1\n}\n"
    )
    (config_dir / "services.cfg").write_text(
        "define service {\n    host_name           web-01\n    service_description HTTP\n    check_command       check_http\n}\n"
    )

    shadow_dir = tmp_path / "shadow"

    application = create_app(config_path=str(config_dir))
    application.config["TESTING"] = True

    # Point shadow manager at our temp shadow dir
    sm = application.extensions["shadow"]
    sm.config_path = str(config_dir)
    sm.shadow_base_path = str(shadow_dir)

    return application


@pytest.fixture
def shadow_client(shadow_app):
    """Flask test client with shadow app."""
    return shadow_app.test_client()


@pytest.fixture
def shadow_with_changes(shadow_app):
    """Create a shadow with modifications and return (app, client)."""
    client = shadow_app.test_client()
    with shadow_app.app_context():
        sm = shadow_app.extensions["shadow"]
        sm.create_shadow("test-session", "Test User", "test@example.com")

        # Modify a file in shadow
        shadow_hosts = sm.shadow_path("hosts.cfg")
        with open(shadow_hosts, "w") as f:
            f.write(
                "define host {\n    host_name   web-01\n    alias       Web Server 01 MODIFIED\n    address     10.0.0.1\n}\n"
            )

    return shadow_app, client


class TestGetStaging:
    """GET /api/staging returns changed files or empty state."""

    def test_no_shadow_returns_empty(self, shadow_client):
        resp = shadow_client.get("/api/staging")
        assert resp.status_code == 200
        data = resp.json
        assert data["success"] is True
        assert data["data"]["changes"] == []
        assert data["data"]["totalCount"] == 0

    def test_with_changes_returns_files(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.get("/api/staging")
        assert resp.status_code == 200
        data = resp.json
        assert data["success"] is True
        assert len(data["data"]["changes"]) >= 1
        paths = [c["path"] for c in data["data"]["changes"]]
        assert "root_0/hosts.cfg" in paths


class TestDeleteStaging:
    """DELETE /api/staging destroys shadow."""

    def test_destroy_existing_shadow(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.delete("/api/staging")
        assert resp.status_code == 200
        assert resp.json["success"] is True

        # Shadow should be gone
        with app.app_context():
            sm = app.extensions["shadow"]
            assert not sm.has_shadow()

    def test_destroy_no_shadow_succeeds(self, shadow_client):
        resp = shadow_client.delete("/api/staging")
        assert resp.status_code == 200
        assert resp.json["success"] is True


class TestStagingInfo:
    """GET /api/staging/info returns counts."""

    def test_no_shadow_returns_zeros(self, shadow_client):
        resp = shadow_client.get("/api/staging/info")
        assert resp.status_code == 200
        data = resp.json["data"]
        assert data["totalCount"] == 0
        assert data["undoCount"] == 0
        assert data["changedFiles"] == 0

    def test_with_changes_returns_counts(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.get("/api/staging/info")
        assert resp.status_code == 200
        data = resp.json["data"]
        assert data["changedFiles"] >= 1
        assert data["undoCount"] == 0


class TestApplyStaging:
    """POST /api/staging/apply copies files and destroys shadow."""

    def test_apply_copies_changes(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.post("/api/staging/apply")
        assert resp.status_code == 200
        assert resp.json["success"] is True

        # Shadow should be gone after apply
        with app.app_context():
            sm = app.extensions["shadow"]
            assert not sm.has_shadow()

            # Original file should have the modification
            orig_hosts = os.path.join(sm.config_path, "hosts.cfg")
            with open(orig_hosts) as f:
                content = f.read()
            assert "MODIFIED" in content

    def test_apply_creates_empty_folder(self, shadow_with_changes):
        app, client = shadow_with_changes
        with app.app_context():
            sm = app.extensions["shadow"]
            new_dir = os.path.join(sm.shadow_cfg_dirs[0], "emptyfolder")
            os.makedirs(new_dir)
            original_root = list(sm.get_root_map().values())[0]

        resp = client.post("/api/staging/apply")
        assert resp.status_code == 200
        assert resp.json["success"] is True

        # Empty folder should exist in original
        assert os.path.isdir(os.path.join(original_root, "emptyfolder"))

    def test_apply_no_shadow_succeeds(self, shadow_client):
        resp = shadow_client.post("/api/staging/apply")
        assert resp.status_code == 200
        assert resp.json["success"] is True


class TestStagingUndo:
    """POST /api/staging/undo restores from snapshot."""

    def test_undo_no_shadow_fails(self, shadow_client):
        resp = shadow_client.post(
            "/api/staging/undo",
            headers={"X-Session-Id": "test-session"},
        )
        assert resp.status_code == 200
        # No shadow means nothing to undo
        assert resp.json["success"] is False

    def test_undo_with_snapshot(self, shadow_with_changes):
        app, client = shadow_with_changes

        # Create a snapshot by modifying another file
        with app.app_context():
            sm = app.extensions["shadow"]
            shadow_svc = sm.shadow_path("services.cfg")
            sm.snapshot_files(["services.cfg"], "modify services")
            with open(shadow_svc, "w") as f:
                f.write("define service {\n    host_name web-01\n    service_description HTTPS\n}\n")

        # Undo should restore
        resp = client.post(
            "/api/staging/undo",
            headers={"X-Session-Id": "test-session"},
        )
        assert resp.status_code == 200
        assert resp.json["success"] is True


class TestStagingLock:
    """GET /api/staging/lock returns lock status."""

    def test_no_shadow_returns_unlocked(self, shadow_client):
        resp = shadow_client.get("/api/staging/lock")
        assert resp.status_code == 200
        data = resp.json["data"]
        assert data["locked"] is False

    def test_with_shadow_returns_locked(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.get("/api/staging/lock")
        assert resp.status_code == 200
        data = resp.json["data"]
        assert data["locked"] is True
        assert data["session_id"] == "test-session"


class TestBreakLock:
    """POST /api/staging/lock/break destroys shadow."""

    def test_break_lock_destroys_shadow(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.post("/api/staging/lock/break")
        assert resp.status_code == 200
        assert resp.json["success"] is True

        with app.app_context():
            sm = app.extensions["shadow"]
            assert not sm.has_shadow()


class TestStagingDiff:
    """GET /api/staging/diff returns file diffs."""

    def test_no_shadow_returns_empty(self, shadow_client):
        resp = shadow_client.get("/api/staging/diff")
        assert resp.status_code == 200
        assert resp.json["data"]["files"] == []

    def test_with_changes_returns_diffs(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.get("/api/staging/diff")
        assert resp.status_code == 200
        files = resp.json["data"]["files"]
        assert len(files) >= 1
        # Find hosts.cfg diff
        hosts_diff = next((f for f in files if f["path"] == "root_0/hosts.cfg"), None)
        assert hosts_diff is not None
        assert "diff" in hosts_diff
        assert "MODIFIED" in hosts_diff["diff"]["diff_text"]

    def test_diff_headers_use_display_path(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.get("/api/staging/diff")
        files = resp.json["data"]["files"]
        hosts_diff = next((f for f in files if "hosts.cfg" in f["path"]), None)
        diff_text = hosts_diff["diff"]["diff_text"]
        # Diff headers should NOT contain root_0
        assert "a/root_0/" not in diff_text
        assert "b/root_0/" not in diff_text

    def test_changed_files_include_display_path(self, shadow_with_changes):
        app, client = shadow_with_changes
        resp = client.get("/api/staging/diff")
        files = resp.json["data"]["files"]
        hosts_diff = next((f for f in files if "hosts.cfg" in f["path"]), None)
        assert hosts_diff is not None
        assert "display_path" in hosts_diff
        # display_path uses original dir basename, not root_0
        assert not hosts_diff["display_path"].startswith("root_0")
        assert "hosts.cfg" in hosts_diff["display_path"]


class TestFolderUndo:
    """Undo support for folder creation."""

    def test_undo_removes_created_folder(self, shadow_with_changes):
        app, client = shadow_with_changes
        with app.app_context():
            sm = app.extensions["shadow"]
            shadow_root = sm.shadow_cfg_dirs[0]
            new_dir = os.path.join(shadow_root, "undome")
            rel_path = os.path.relpath(new_dir, sm._config_dir)
            sm.snapshot_files([], f"create folder {rel_path}", dir_paths=[rel_path])
            os.makedirs(new_dir)

            assert os.path.isdir(new_dir)
            assert sm.get_undo_count() == 1

        resp = client.post(
            "/api/staging/undo",
            headers={"X-Session-Id": "test-session"},
        )
        assert resp.json["success"] is True

        with app.app_context():
            sm = app.extensions["shadow"]
            assert not os.path.isdir(new_dir)


class TestChangedFilesNewDir:
    """get_changed_files detects new empty directories."""

    def test_new_empty_folder_detected(self, shadow_with_changes):
        app, client = shadow_with_changes
        with app.app_context():
            sm = app.extensions["shadow"]
            # Create empty folder in shadow
            new_dir = os.path.join(sm.shadow_cfg_dirs[0], "newsubdir")
            os.makedirs(new_dir)

        resp = client.get("/api/staging/diff")
        files = resp.json["data"]["files"]
        dir_entry = next((f for f in files if "newsubdir" in f.get("display_path", f["path"])), None)
        assert dir_entry is not None
        assert dir_entry["status"] == "added"
        assert dir_entry.get("is_dir") is True
