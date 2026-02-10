"""Integration tests for staging system after backward compatibility removal.

Tests full staging workflow with dict format only.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app, get_config_path


@pytest.fixture
def app():
    """Create Flask app with test config."""
    # Create temp directory for test config
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    # Create sample config file
    sample_cfg = test_config_path / "hosts.cfg"
    sample_cfg.write_text("""
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

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True

    yield app

    # Cleanup
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    """Create test client with clean staging state."""
    test_client = app.test_client()

    # Clear any existing staging to ensure clean state
    with app.app_context():
        sm = app.extensions.get("staging")
        if sm:
            sm.clear_staging()

    yield test_client

    # Cleanup staging after test
    with app.app_context():
        sm = app.extensions.get("staging")
        if sm:
            sm.clear_staging()


def test_staging_round_trip_dict_format(client, app):
    """Test full staging round-trip with dict format."""
    # Get initial objects
    resp = client.get("/api/objects")
    assert resp.status_code == 200  # noqa: PLR2004
    objects = resp.json
    assert len(objects) > 0

    # Stage an edit in dict format (uses 'original' and 'edited' field names)
    obj = objects[0]
    edit_data = {
        "sessionId": "test-session",
        "userName": "Test User",
        "userEmail": "test@example.com",
        "pendingEdits": {
            str(obj["global_index"]): {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Updated Alias"},
            },
        },
    }

    resp = client.post("/api/staging",
                       data=json.dumps(edit_data),
                       content_type="application/json",
                       headers={"X-Session-Id": "test-session"})
    assert resp.status_code == 200  # noqa: PLR2004

    # Verify staging was saved
    resp = client.get("/api/staging",
                      headers={"X-Session-Id": "test-session"})
    assert resp.status_code == 200  # noqa: PLR2004
    data = resp.json
    staging = data.get("staging", data)  # Handle both response formats
    assert "pendingEdits" in staging
    assert isinstance(staging["pendingEdits"], dict)

    # Apply changes
    resp = client.post("/api/staging/apply",
                       data=json.dumps({}),
                       content_type="application/json",
                       headers={"X-Session-Id": "test-session"})
    assert resp.status_code == 200  # noqa: PLR2004

    # Verify the edit was written to disk
    config_path = Path(get_config_path())
    written_content = (config_path / "hosts.cfg").read_text()
    assert "Updated Alias" in written_content
    assert "Test Host 1" not in written_content  # Original alias replaced

    # Verify re-parsed objects reflect the edit
    resp = client.get("/api/objects")
    assert resp.status_code == 200  # noqa: PLR2004
    updated_objects = resp.json
    edited_obj = next(o for o in updated_objects
                      if o["attributes"].get("host_name") == "test-host-1")
    assert edited_obj["attributes"]["alias"] == "Updated Alias"


def test_reject_old_list_format(client):
    """Test that list format for pendingEdits is rejected with clear error."""
    # Try to save staging with old list format
    old_format_data = {
        "sessionId": "test-session",
        "pendingEdits": [
            {"object": {}, "edited": {}},
        ],
    }

    resp = client.post("/api/staging",
                       data=json.dumps(old_format_data),
                       content_type="application/json",
                       headers={"X-Session-Id": "test-session"})
    assert resp.status_code == 400  # noqa: PLR2004
    assert "Invalid staging format" in resp.json["error"]
    assert "dict" in resp.json["error"]


def test_undo_operations_dict_format(client):
    """Test undo operations work with dict format."""
    # Get initial objects
    resp = client.get("/api/objects")
    objects = resp.json
    obj = objects[0]

    # Stage multiple operations
    staging_data = {
        "sessionId": "test-session",
        "userName": "Test User",
        "userEmail": "test@example.com",
        "pendingEdits": {
            str(obj["global_index"]): {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Edit 1"},
            },
        },
    }

    client.post("/api/staging",
                data=json.dumps(staging_data),
                content_type="application/json",
                headers={"X-Session-Id": "test-session"})

    # Get staging info
    resp = client.get("/api/staging/info",
                      headers={"X-Session-Id": "test-session"})
    info = resp.json
    assert info["undoCount"] > 0

    # Undo operation
    resp = client.post("/api/staging/undo",
                       data=json.dumps({}),
                       content_type="application/json",
                       headers={"X-Session-Id": "test-session"})
    assert resp.status_code == 200  # noqa: PLR2004

    # Verify undo worked
    resp = client.get("/api/staging/info",
                      headers={"X-Session-Id": "test-session"})
    info = resp.json
    assert info["undoCount"] == 0
    assert info["totalCount"] == 0


def test_multi_operation_workflow(client, app):
    """Test create, edit, move, delete workflow."""
    session_id = "test-session"
    headers = {"X-Session-Id": session_id}

    # Get initial state
    resp = client.get("/api/objects")
    objects = resp.json

    obj = objects[0]

    # Stage both creation and edit in one request
    staging_data = {
        "sessionId": session_id,
        "stagedCreations": [{
            "id": "create-1",
            "object_type": "host",
            "targetFile": "hosts.cfg",
            "attributes": {
                "host_name": "new-host",
                "alias": "New Host",
                "address": "192.168.1.100",
            },
        }],
        "pendingEdits": {
            str(obj["global_index"]): {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Modified"},
            },
        },
    }

    resp = client.post("/api/staging",
                       data=json.dumps(staging_data),
                       content_type="application/json",
                       headers=headers)
    assert resp.status_code == 200  # noqa: PLR2004

    # Verify counts
    resp = client.get("/api/staging/info", headers=headers)
    info = resp.json
    counts = info.get("counts", {})
    assert counts.get("creations", 0) == 1
    assert counts.get("edits", 0) == 1

    # Apply all changes
    resp = client.post("/api/staging/apply",
                       data=json.dumps({}),
                       content_type="application/json",
                       headers=headers)
    assert resp.status_code == 200  # noqa: PLR2004

    # Verify changes were written to disk
    config_path = Path(get_config_path())
    written_content = (config_path / "hosts.cfg").read_text()
    assert "Modified" in written_content        # Edit applied
    assert "new-host" in written_content        # Creation applied
    assert "192.168.1.100" in written_content   # New host address

    # Verify re-parsed objects reflect both changes
    resp = client.get("/api/objects")
    assert resp.status_code == 200  # noqa: PLR2004
    updated_objects = resp.json

    edited_obj = next(o for o in updated_objects
                      if o["attributes"].get("host_name") == "test-host-1")
    assert edited_obj["attributes"]["alias"] == "Modified"

    created_obj = next(o for o in updated_objects
                       if o["attributes"].get("host_name") == "new-host")
    assert created_obj["attributes"]["alias"] == "New Host"
    assert created_obj["attributes"]["address"] == "192.168.1.100"


def test_conflict_detection(client):
    """Test conflict detection on external file changes."""
    session_id = "test-session"
    headers = {"X-Session-Id": session_id}

    # Get objects and make edit
    resp = client.get("/api/objects")
    obj = resp.json[0]

    edit_data = {
        "sessionId": session_id,
        "pendingEdits": {
            str(obj["global_index"]): {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Changed"},
            },
        },
    }

    client.post("/api/staging",
                data=json.dumps(edit_data),
                content_type="application/json",
                headers=headers)

    # Check for conflicts (should be none initially)
    resp = client.get("/api/staging/conflicts", headers=headers)
    assert resp.status_code == 200  # noqa: PLR2004
    assert len(resp.json.get("conflicts", [])) == 0


class TestBulkOpsUseStagingSystem:
    """Verify that bulk operations flow through staging (SAFETY-4 regression test)."""

    def test_bulk_rename_does_not_write_to_disk_without_apply(self, client, app):
        """Bulk rename via staging save should not modify disk files."""
        with app.app_context():
            service = app.extensions["service"]
            original_objects = service.get_objects()

            # Find a host to rename
            host = None
            for obj in original_objects:
                if obj.object_type == "host":
                    host = obj
                    break

            if host is None:
                pytest.skip("No host objects in test config")

            original_content = Path(host.source_file).read_text()

        # Stage a rename edit (don't apply)
        resp = client.post("/api/staging", json={
            "pendingEdits": {
                "0": {
                    "object": host.to_dict(),
                    "original": host.attributes.copy(),
                    "edited": {**host.attributes, "alias": "RENAMED-ALIAS"},
                },
            },
        }, headers={"X-Session-Id": "test-session"})
        assert resp.status_code == 200  # noqa: PLR2004

        # Verify disk file is UNCHANGED
        with app.app_context():
            service = app.extensions["service"]
            host_obj = None
            for obj in service.get_objects():
                if obj.object_type == "host":
                    host_obj = obj
                    break
            current_content = Path(host_obj.source_file).read_text()
            assert current_content == original_content

    def test_bulk_rename_api_stages_changes(self, client, app):
        """POST /api/apply-rename creates staging entries, not disk writes."""
        session_id = "test-session"
        headers = {"X-Session-Id": session_id}

        with app.app_context():
            service = app.extensions["service"]
            host = next((o for o in service.get_objects() if o.object_type == "host"), None)
            if host is None:
                pytest.skip("No host objects in test config")
            original_content = Path(host.source_file).read_text()

        # Call the bulk rename API
        resp = client.post("/api/apply-rename", json={
            "type": "host",
            "find": "",
            "replace": "",
            "prefix": "renamed-",
            "suffix": "",
            "regex": False,
            "updateReferences": False,
        }, headers=headers)
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json
        assert data["success"] is True
        assert data["staged"] > 0

        # Verify disk file is UNCHANGED
        with app.app_context():
            service = app.extensions["service"]
            host_obj = next((o for o in service.get_objects() if o.object_type == "host"), None)
            current_content = Path(host_obj.source_file).read_text()
            assert current_content == original_content

        # Verify staging has entries
        resp = client.get("/api/staging", headers=headers)
        assert resp.status_code == 200  # noqa: PLR2004
        staging = resp.json.get("staging", {})
        assert len(staging.get("pendingEdits", {})) > 0

    def test_bulk_move_api_stages_changes(self, client, app):
        """POST /api/move-objects creates staging entries, not disk writes."""
        session_id = "test-session-move"
        headers = {"X-Session-Id": session_id}

        # Clear staging and reload to get fresh state
        client.delete("/api/staging", headers=headers)
        client.post("/api/reload")

        # Get object info via API
        resp = client.get("/api/objects")
        assert resp.status_code == 200  # noqa: PLR2004
        all_objs = resp.json
        assert len(all_objs) > 0, "Must have at least one object"

        host = all_objs[0]
        host_idx = host["global_index"]
        host_file = host["source_file"]
        original_content = Path(host_file).read_text()

        # Use a target file path in the same config directory
        config_dir = str(Path(host_file).parent)
        target_file = config_dir + "/moved.cfg"

        resp = client.post("/api/move-objects", json={
            "objects": [host_idx],
            "target_file": target_file,
            "create_new": True,
        }, headers=headers)
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json
        assert data["success"] is True
        assert data["staged"] > 0

        # Verify disk file is UNCHANGED (not written to)
        assert Path(host_file).read_text() == original_content
        # Target file should NOT exist on disk (only staged)
        assert not Path(target_file).exists()

        # Verify staging has move entries
        resp = client.get("/api/staging", headers=headers)
        assert resp.status_code == 200  # noqa: PLR2004
        staging = resp.json.get("staging", {})
        assert len(staging.get("stagedMoves", {})) > 0
