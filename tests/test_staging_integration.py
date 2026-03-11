"""Integration tests for shadow copy staging workflow.

Tests the full shadow copy lifecycle through the Flask API:
create shadow -> mutations via API -> diff/undo/apply -> verify.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app


@pytest.fixture
def shadow_app():
    """Create Flask app with isolated temp config for shadow copy testing."""
    # Use realpath to resolve symlinks (macOS: /var -> /private/var)
    # so paths match what NagiosParser produces.
    test_dir = os.path.realpath(tempfile.mkdtemp())
    config_path = Path(test_dir) / "nagios"
    config_path.mkdir()

    (config_path / "hosts.cfg").write_text("""\
define host {
    host_name       test-host-1
    alias           Test Host 1
    address         192.168.1.1
    use             generic-host
}

define host {
    host_name       test-host-2
    alias           Test Host 2
    address         192.168.1.2
    use             generic-host
}
""")

    (config_path / "services.cfg").write_text("""\
define service {
    host_name             test-host-1
    service_description   HTTP
    check_command         check_http
}
""")

    app = create_app(config_path=str(config_path))
    app.config["TESTING"] = True

    yield app

    # Cleanup: destroy shadow if still active, then remove temp dir
    with app.app_context():
        sm = app.extensions.get("shadow")
        if sm and sm.has_shadow():
            sm.destroy_shadow()
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(shadow_app):
    """Flask test client."""
    return shadow_app.test_client()


def _get_host_object(client, hostname):
    """Get a host object dict by host_name from the API."""
    resp = client.get("/api/objects")
    assert resp.status_code == 200
    objects = resp.json
    return next(o for o in objects if o["attributes"].get("host_name") == hostname)


class TestShadowEditApplyWorkflow:
    """Test: create shadow -> edit via API -> verify diff -> apply -> verify original updated."""

    def test_shadow_lock_records_user_identity(self, client, shadow_app):
        """First mutation records user identity from headers in lock.json."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        resp = client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Identity Test"},
        }, headers={
            "X-Session-Id": "session-identity",
            "X-User-Name": "Alice",
            "X-User-Email": "alice@example.com",
        })
        assert resp.status_code == 200

        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            lock = sm.get_lock_status()
            assert lock["locked"] is True
            assert lock["user_name"] == "Alice"
            assert lock["user_email"] == "alice@example.com"

    def test_edit_via_api_shows_in_diff(self, client, shadow_app):
        """Editing an object creates a shadow and shows a diff."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        resp = client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Updated Alias"},
        }, headers={"X-Session-Id": "session-1"})
        assert resp.status_code == 200

        # Shadow should now exist
        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            assert sm.has_shadow()

        # Diff should show the change
        resp = client.get("/api/staging/diff")
        assert resp.status_code == 200
        files = resp.json["data"]["files"]
        assert len(files) > 0
        diff_text = files[0]["diff"]["diff_text"]
        assert "Updated Alias" in diff_text

    def test_apply_writes_to_original_config(self, client, shadow_app):
        """Apply copies shadow changes back to the original config directory."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        # Edit
        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Applied Alias"},
        }, headers={"X-Session-Id": "session-1"})

        # Apply
        resp = client.post("/api/staging/apply")
        assert resp.status_code == 200
        assert resp.json["success"] is True

        # Shadow destroyed after apply
        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            assert not sm.has_shadow()

        # Verify original config file updated
        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            content = Path(sm.config_path).joinpath("hosts.cfg").read_text()
            assert "Applied Alias" in content
            assert "Test Host 1" not in content  # Old alias replaced

    def test_applied_changes_visible_in_api(self, client, shadow_app):
        """After apply, the objects API reflects the changes."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "API Visible"},
        }, headers={"X-Session-Id": "session-1"})

        client.post("/api/staging/apply")

        # Re-fetch from API
        updated = _get_host_object(client, "test-host-1")
        assert updated["attributes"]["alias"] == "API Visible"

    def test_create_object_then_apply(self, client, shadow_app):
        """Creating a new object via API then applying writes it to disk."""
        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            config_path = sm.config_path

        # Find the target file path from an existing object
        obj = _get_host_object(client, "test-host-1")
        target_file = obj["source_file"]

        resp = client.post("/api/objects/create", json={
            "target_file": target_file,
            "object_type": "host",
            "attributes": {
                "host_name": "new-host",
                "alias": "Brand New Host",
                "address": "10.0.0.99",
            },
        }, headers={"X-Session-Id": "session-1"})
        assert resp.status_code == 200

        # Apply
        resp = client.post("/api/staging/apply")
        assert resp.status_code == 200

        # Verify written to original
        content = Path(config_path).joinpath("hosts.cfg").read_text()
        assert "new-host" in content
        assert "Brand New Host" in content

    def test_delete_object_then_apply(self, client, shadow_app):
        """Deleting an object via API then applying removes it from disk."""
        obj = _get_host_object(client, "test-host-2")
        key = generate_stable_key_for_object_dict(obj)

        resp = client.post("/api/objects/delete", json={
            "stable_key": key,
        }, headers={"X-Session-Id": "session-1"})
        assert resp.status_code == 200

        # Apply
        resp = client.post("/api/staging/apply")
        assert resp.status_code == 200

        # Verify removed from API
        resp = client.get("/api/objects")
        hostnames = [o["attributes"].get("host_name") for o in resp.json]
        assert "test-host-2" not in hostnames


class TestShadowUndoWorkflow:
    """Test: create shadow -> edit -> undo -> verify reverted."""

    def test_undo_reverts_edit(self, client, shadow_app):
        """Undo after an edit restores the original content."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        # Edit
        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Will Be Undone"},
        }, headers={"X-Session-Id": "session-1"})

        # Verify edit took effect in shadow
        edited = _get_host_object(client, "test-host-1")
        assert edited["attributes"]["alias"] == "Will Be Undone"

        # Undo
        resp = client.post("/api/staging/undo",
                           headers={"X-Session-Id": "session-1"})
        assert resp.status_code == 200

        # Verify reverted
        reverted = _get_host_object(client, "test-host-1")
        assert reverted["attributes"]["alias"] == "Test Host 1"

    def test_undo_count_decrements(self, client, shadow_app):
        """Undo count goes down after each undo."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        # Two edits
        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Edit 1"},
        }, headers={"X-Session-Id": "session-1"})

        # Re-fetch object (key may have changed if alias is in display name)
        obj2 = _get_host_object(client, "test-host-1")
        key2 = generate_stable_key_for_object_dict(obj2)

        client.post("/api/objects/update", json={
            "stable_key": key2,
            "attributes": {**obj2["attributes"], "alias": "Edit 2"},
        }, headers={"X-Session-Id": "session-1"})

        resp = client.get("/api/staging/info")
        info = resp.json["data"]
        assert info["undoCount"] == 2

        # Undo once
        client.post("/api/staging/undo", headers={"X-Session-Id": "session-1"})
        resp = client.get("/api/staging/info")
        assert resp.json["data"]["undoCount"] == 1

    def test_no_changes_after_full_undo(self, client, shadow_app):
        """After undoing all edits, diff should show no changed files."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Temporary Edit"},
        }, headers={"X-Session-Id": "session-1"})

        client.post("/api/staging/undo", headers={"X-Session-Id": "session-1"})

        resp = client.get("/api/staging/diff")
        files = resp.json["data"]["files"]
        # No changed files after full undo
        assert len(files) == 0


class TestSessionLocking:
    """Test: shadow lock prevents other sessions from modifying."""

    def test_second_session_blocked(self, client, shadow_app):
        """A second session cannot edit while first session holds the lock."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        # First session creates shadow
        resp = client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Session 1 Edit"},
        }, headers={"X-Session-Id": "session-1"})
        assert resp.status_code == 200

        # Second session tries to edit — should be blocked (423)
        resp = client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Session 2 Edit"},
        }, headers={"X-Session-Id": "session-2"})
        assert resp.status_code == 423

    def test_lock_status_shows_owner(self, client, shadow_app):
        """Lock status API shows the session owner."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Lock Test"},
        }, headers={"X-Session-Id": "session-owner"})

        resp = client.get("/api/staging/lock")
        assert resp.status_code == 200
        data = resp.json["data"]
        assert data["locked"] is True
        assert data["session_id"] == "session-owner"


class TestBreakLock:
    """Test: break lock destroys shadow copy."""

    def test_break_lock_destroys_shadow(self, client, shadow_app):
        """Breaking the lock destroys the shadow and allows new sessions."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        # Create shadow via edit
        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Before Break"},
        }, headers={"X-Session-Id": "session-1"})

        # Break lock
        resp = client.post("/api/staging/lock/break")
        assert resp.status_code == 200
        assert resp.json["success"] is True

        # Shadow should be gone
        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            assert not sm.has_shadow()

    def test_after_break_new_session_can_edit(self, client, shadow_app):
        """After breaking lock, a different session can create a new shadow."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        # Session 1 creates shadow
        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Session 1"},
        }, headers={"X-Session-Id": "session-1"})

        # Break lock
        client.post("/api/staging/lock/break")

        # Session 2 should now be able to edit (re-fetch object since service reloaded)
        obj2 = _get_host_object(client, "test-host-1")
        key2 = generate_stable_key_for_object_dict(obj2)
        resp = client.post("/api/objects/update", json={
            "stable_key": key2,
            "attributes": {**obj2["attributes"], "alias": "Session 2"},
        }, headers={"X-Session-Id": "session-2"})
        assert resp.status_code == 200

    def test_break_discards_unsaved_changes(self, client, shadow_app):
        """Breaking lock discards changes — original config unchanged."""
        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            original_content = Path(sm.config_path).joinpath("hosts.cfg").read_text()

        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Discarded Edit"},
        }, headers={"X-Session-Id": "session-1"})

        client.post("/api/staging/lock/break")

        # Original config should be unchanged
        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            current_content = Path(sm.config_path).joinpath("hosts.cfg").read_text()
            assert current_content == original_content


class TestStagingInfoEndpoints:
    """Test staging info and status endpoints."""

    def test_staging_info_empty_when_no_shadow(self, client):
        """Staging info returns zeros when no shadow exists."""
        resp = client.get("/api/staging/info")
        assert resp.status_code == 200
        data = resp.json["data"]
        assert data["totalCount"] == 0
        assert data["undoCount"] == 0
        assert data["changedFiles"] == 0

    def test_staging_info_counts_after_edit(self, client, shadow_app):
        """Staging info shows correct counts after an edit."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Count Test"},
        }, headers={"X-Session-Id": "session-1"})

        resp = client.get("/api/staging/info")
        data = resp.json["data"]
        assert data["totalCount"] >= 1
        assert data["undoCount"] >= 1
        assert data["changedFiles"] >= 1

    def test_clear_staging_destroys_shadow(self, client, shadow_app):
        """DELETE /api/staging destroys the shadow copy."""
        obj = _get_host_object(client, "test-host-1")
        key = generate_stable_key_for_object_dict(obj)

        client.post("/api/objects/update", json={
            "stable_key": key,
            "attributes": {**obj["attributes"], "alias": "Will Be Cleared"},
        }, headers={"X-Session-Id": "session-1"})

        resp = client.delete("/api/staging")
        assert resp.status_code == 200
        assert resp.json["success"] is True

        with shadow_app.app_context():
            sm = shadow_app.extensions["shadow"]
            assert not sm.has_shadow()


class TestMoveObject:
    """Test single-object move via /api/objects/move."""

    def test_move_object_same_file_reorder(self, client, shadow_app):
        """Moving an object earlier in the same file actually moves it."""
        obj = _get_host_object(client, "test-host-2")
        key = generate_stable_key_for_object_dict(obj)

        # Move test-host-2 to before test-host-1 (after_line=0 = beginning of file)
        resp = client.post("/api/objects/move", json={
            "stable_key": key,
            "target_file": obj["source_file"],
            "after_line": 0,
        }, headers={"X-Session-Id": "session-1"})
        assert resp.status_code == 200
        assert resp.json["success"] is True

        # Verify test-host-2 now appears before test-host-1
        resp = client.get("/api/objects?type=host")
        hosts = resp.json
        host_names = [h["attributes"]["host_name"] for h in hosts
                      if h["source_file"].endswith("hosts.cfg")]
        assert host_names.index("test-host-2") < host_names.index("test-host-1")

    def test_move_object_cross_file(self, client, shadow_app):
        """Moving an object to a different file works and removes from source."""
        obj = _get_host_object(client, "test-host-2")
        key = generate_stable_key_for_object_dict(obj)
        source_file = obj["source_file"]

        # Create target file in same directory
        target_file = source_file.replace("hosts.cfg", "hosts2.cfg")

        resp = client.post("/api/objects/move", json={
            "stable_key": key,
            "target_file": target_file,
        }, headers={"X-Session-Id": "session-1"})
        assert resp.status_code == 200
        assert resp.json["success"] is True

        # Verify moved: exists in target, not in source
        resp = client.get("/api/objects?type=host")
        hosts = resp.json
        for h in hosts:
            if h["attributes"]["host_name"] == "test-host-2":
                assert h["source_file"].endswith("hosts2.cfg")
                break
        else:
            pytest.fail("test-host-2 not found after move")

        source_hosts = [h for h in hosts if h["source_file"].endswith("hosts.cfg")
                        and not h["source_file"].endswith("hosts2.cfg")]
        assert all(h["attributes"]["host_name"] != "test-host-2" for h in source_hosts)


class TestBulkOperations:
    """Test bulk rename and move endpoints."""

    def test_apply_rename_renames_objects(self, client, shadow_app):
        """POST /api/apply-rename renames matching objects and updates references."""
        resp = client.post("/api/apply-rename", json={
            "type": "host",
            "find": "test-host",
            "replace": "prod-host",
        }, headers={"X-Session-Id": "session-bulk"})
        assert resp.status_code == 200
        data = resp.json
        assert data["success"] is True
        assert data["renamed"] == 2

        # Verify both hosts were renamed
        resp = client.get("/api/objects?type=host")
        host_names = [h["attributes"]["host_name"] for h in resp.json]
        assert "prod-host-1" in host_names
        assert "prod-host-2" in host_names
        assert "test-host-1" not in host_names

    def test_apply_rename_updates_references(self, client, shadow_app):
        """Renaming a host updates service host_name references."""
        resp = client.post("/api/apply-rename", json={
            "type": "host",
            "find": "test-host-1",
            "replace": "renamed-host",
            "updateReferences": True,
        }, headers={"X-Session-Id": "session-bulk-ref"})
        assert resp.status_code == 200
        data = resp.json
        assert data["renamed"] >= 1
        assert data["references_updated"] >= 1

        # Verify the service now references renamed-host
        resp = client.get("/api/objects?type=service")
        for svc in resp.json:
            if svc["attributes"].get("service_description") == "HTTP":
                assert "renamed-host" in svc["attributes"].get("host_name", "")
                break

    def test_apply_rename_no_matches(self, client, shadow_app):
        """No matches returns success with zero counts."""
        resp = client.post("/api/apply-rename", json={
            "type": "host",
            "find": "nonexistent-pattern",
            "replace": "whatever",
        }, headers={"X-Session-Id": "session-bulk-none"})
        assert resp.status_code == 200
        assert resp.json["renamed"] == 0

    def test_apply_rename_requires_type(self, client):
        """Missing type returns 400."""
        resp = client.post("/api/apply-rename", json={
            "find": "test",
            "replace": "prod",
        }, headers={"X-Session-Id": "session-bulk-err"})
        assert resp.status_code == 400


def generate_stable_key_for_object_dict(obj_dict: dict) -> str:
    """Build a stable key from an API object dict."""
    name = obj_dict.get("display_name") or obj_dict.get("name") or ""
    return f"{obj_dict['source_file']}|{obj_dict['object_type']}|{name}"
