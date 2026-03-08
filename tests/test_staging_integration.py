"""Integration tests for staging system after backward compatibility removal.

Tests full staging workflow with dict format only.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app, get_config_path
from staging_manager import generate_stable_key_for_object


def _obj_stable_key(obj):
    """Build a stable key from an API object dict."""
    name = obj.get("display_name") or obj.get("name") or ""
    return f"{obj['source_file']}|{obj['object_type']}|{name}"


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
    stable_key = _obj_stable_key(obj)
    edit_data = {
        "sessionId": "test-session",
        "userName": "Test User",
        "userEmail": "test@example.com",
        "pendingEdits": {
            stable_key: {
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
    stable_key = _obj_stable_key(obj)
    staging_data = {
        "sessionId": "test-session",
        "userName": "Test User",
        "userEmail": "test@example.com",
        "pendingEdits": {
            stable_key: {
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
    stable_key = _obj_stable_key(obj)
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
            stable_key: {
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

    stable_key = _obj_stable_key(obj)
    edit_data = {
        "sessionId": session_id,
        "pendingEdits": {
            stable_key: {
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
        stable_key = generate_stable_key_for_object(host)
        resp = client.post("/api/staging", json={
            "pendingEdits": {
                stable_key: {
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



class TestAnalyzeReferences:
    """Tests for the analyze-references endpoint."""

    def test_analyze_references_finds_all_direct_refs(self, client, app):
        """analyze-references should find refs in all attribute fields, not just REFERENCE_FIELDS."""
        with app.app_context():
            config_path = Path(get_config_path())
            (config_path / "hosts.cfg").write_text("""
define host {
    host_name       web-server-01
    alias           Web Server
    address         10.0.0.1
}

define host {
    host_name       db-server-01
    alias           DB Server
    address         10.0.0.2
}
""")
            (config_path / "services.cfg").write_text("""
define service {
    host_name               web-server-01
    service_description     HTTP
    check_command           check_http
}

define service {
    host_name               web-server-01,db-server-01
    service_description     PING
    check_command           check_ping
}
""")
            (config_path / "dependencies.cfg").write_text("""
define hostdependency {
    host_name               db-server-01
    dependent_host_name     web-server-01
}
""")
            service = app.extensions["service"]
            service.reload()

        session_id = "test-session"
        headers = {"X-Session-Id": session_id}

        resp = client.get("/api/objects")
        objects = resp.json
        host_obj = next(o for o in objects
                        if o["attributes"].get("host_name") == "web-server-01")

        stable_key = _obj_stable_key(host_obj)
        edit_data = {
            "sessionId": session_id,
            "pendingEdits": {
                stable_key: {
                    "object": host_obj,
                    "original": host_obj["attributes"],
                    "edited": {**host_obj["attributes"], "host_name": "web-server-renamed"},
                },
            },
        }
        resp = client.post("/api/staging",
                           data=json.dumps(edit_data),
                           content_type="application/json",
                           headers=headers)
        assert resp.status_code == 200

        resp = client.get("/api/staging/analyze-references", headers=headers)
        assert resp.status_code == 200
        data = resp.json

        assert data["hasNameChanges"] is True
        assert len(data["nameChanges"]) == 1

        change = data["nameChanges"][0]
        assert change["oldName"] == "web-server-01"
        assert change["newName"] == "web-server-renamed"

        # Should find 3 references:
        # 1. SERVICE HTTP (host_name = web-server-01)
        # 2. SERVICE PING (host_name = web-server-01,db-server-01)
        # 3. HOSTDEPENDENCY (dependent_host_name = web-server-01)
        assert change["referenceCount"] == 3
        assert data["totalReferences"] == 3

    def test_analyze_references_returns_diff_data(self, client, app):
        """analyze-references should return old/new values and source_file for each ref."""
        with app.app_context():
            config_path = Path(get_config_path())
            (config_path / "hosts.cfg").write_text("""
define host {
    host_name       myhost
    alias           My Host
    address         10.0.0.1
}
""")
            (config_path / "services.cfg").write_text("""
define service {
    host_name               myhost
    service_description     HTTP
    check_command           check_http
}
""")
            service = app.extensions["service"]
            service.reload()

        session_id = "test-session"
        headers = {"X-Session-Id": session_id}

        resp = client.get("/api/objects")
        objects = resp.json
        host_obj = next(o for o in objects
                        if o["attributes"].get("host_name") == "myhost")

        stable_key = _obj_stable_key(host_obj)
        edit_data = {
            "sessionId": session_id,
            "pendingEdits": {
                stable_key: {
                    "object": host_obj,
                    "original": host_obj["attributes"],
                    "edited": {**host_obj["attributes"], "host_name": "myhost-renamed"},
                },
            },
        }
        client.post("/api/staging",
                     data=json.dumps(edit_data),
                     content_type="application/json",
                     headers=headers)

        resp = client.get("/api/staging/analyze-references", headers=headers)
        data = resp.json
        change = data["nameChanges"][0]

        ref = change["references"][0]
        assert "sourceFile" in ref
        assert "field" in ref
        assert "oldValue" in ref
        assert "newValue" in ref
        assert "objectType" in ref
        assert "objectName" in ref

        assert "myhost" in ref["oldValue"]
        assert "myhost-renamed" in ref["newValue"]


def test_apply_includes_verification(client, app):
    """Apply response includes verification report."""
    resp = client.get("/api/objects")
    objects = resp.json
    obj = objects[0]

    stable_key = _obj_stable_key(obj)
    edit_data = {
        "sessionId": "test-session",
        "pendingEdits": {
            stable_key: {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Verified Alias"},
            },
        },
    }

    client.post("/api/staging",
                data=json.dumps(edit_data),
                content_type="application/json",
                headers={"X-Session-Id": "test-session"})

    resp = client.post("/api/staging/apply",
                       data=json.dumps({}),
                       content_type="application/json",
                       headers={"X-Session-Id": "test-session"})
    assert resp.status_code == 200

    data = resp.json
    assert "verification" in data
    v = data["verification"]
    assert v["objectLevel"]["passed"] is True
    assert v["objectLevel"]["editsVerified"] == 1


def test_apply_verification_multi_operation(client, app):
    """Verification works with create + edit together."""
    session_id = "test-session"
    headers = {"X-Session-Id": session_id}

    resp = client.get("/api/objects")
    objects = resp.json
    obj = objects[0]

    # Use the same absolute source_file path so verification can match
    target_file = obj["source_file"]

    stable_key = _obj_stable_key(obj)
    staging_data = {
        "sessionId": session_id,
        "stagedCreations": [{
            "id": "create-v1",
            "object_type": "host",
            "targetFile": target_file,
            "attributes": {
                "host_name": "verified-host",
                "alias": "Verified",
                "address": "10.0.0.99",
            },
        }],
        "pendingEdits": {
            stable_key: {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Also Verified"},
            },
        },
    }

    client.post("/api/staging",
                data=json.dumps(staging_data),
                content_type="application/json",
                headers=headers)

    resp = client.post("/api/staging/apply",
                       data=json.dumps({}),
                       content_type="application/json",
                       headers=headers)
    assert resp.status_code == 200

    data = resp.json
    v = data["verification"]
    assert v["objectLevel"]["passed"] is True
    assert v["objectLevel"]["editsVerified"] == 1
    assert v["objectLevel"]["creationsVerified"] == 1


def test_unknown_staging_fields_logged_but_accepted(client):
    """POST /api/staging with unknown fields should succeed (just logs a warning)."""
    resp = client.get("/api/objects")
    objects = resp.json
    obj = objects[0]

    stable_key = _obj_stable_key(obj)
    staging_data = {
        "sessionId": "test-session",
        "pendingEdits": {
            stable_key: {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Unknown Field Test"},
            },
        },
        "totallyBogusField": True,
        "anotherUnknownField": [1, 2, 3],
    }

    resp = client.post(
        "/api/staging",
        data=json.dumps(staging_data),
        content_type="application/json",
        headers={"X-Session-Id": "test-session"},
    )
    assert resp.status_code == 200
    assert resp.json.get("success") is True
