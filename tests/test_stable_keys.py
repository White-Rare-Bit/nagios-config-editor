"""Tests for stable key generation and uniqueness."""

import base64
import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from staging_manager import generate_stable_key_for_object, parse_stable_key


def test_parse_stable_key_with_pipe_in_name():
    """parse_stable_key should handle names containing pipe characters."""
    result = parse_stable_key("servers/hosts.cfg|host|my|special|host")
    assert result is not None
    assert result["source_file"] == "servers/hosts.cfg"
    assert result["object_type"] == "host"
    assert result["name"] == "my|special|host"


@pytest.fixture
def app_with_duplicate_services():
    """Create app with services that share service_description."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    services_cfg = test_config_path / "services.cfg"
    services_cfg.write_text("""
define service {
    hostgroup_name    linux-hosts
    service_description    PING
    use    local-service
    check_command    check_ping!100.0,20%!500.0,60%
}

define service {
    hostgroup_name    windows-hosts
    service_description    PING
    use    local-service
    check_command    check_ping!200.0,40%!600.0,80%
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True

    yield app

    shutil.rmtree(test_dir, ignore_errors=True)


def test_duplicate_service_descriptions_get_unique_keys(app_with_duplicate_services):
    """Services with same service_description on different hosts must have unique stable keys."""
    with app_with_duplicate_services.app_context():
        from routes.helpers import get_service
        service = get_service()
        services = [o for o in service.get_objects() if o.object_type == "service"]

        assert len(services) == 2
        key1 = generate_stable_key_for_object(services[0])
        key2 = generate_stable_key_for_object(services[1])
        assert key1 != key2, f"Keys must differ but both are: {key1}"
        # Keys should contain the display name with host context
        assert "linux-hosts" in key1
        assert "windows-hosts" in key2


def test_find_object_by_stable_key_with_display_name(app_with_duplicate_services):
    """find_object_by_stable_key should resolve keys that use display_name."""
    with app_with_duplicate_services.app_context():
        from routes.helpers import get_service
        service = get_service()
        services = [o for o in service.get_objects() if o.object_type == "service"]

        key1 = generate_stable_key_for_object(services[0])
        key2 = generate_stable_key_for_object(services[1])

        result1 = service.find_object_by_stable_key(key1)
        result2 = service.find_object_by_stable_key(key2)

        assert result1 is not None, f"Should find object for key: {key1}"
        assert result2 is not None, f"Should find object for key: {key2}"
        # They should find different objects
        assert result1[0] != result2[0], "Should find different objects"


def test_apply_staged_edits_by_stable_key(app):
    """Virtual tree should apply edits keyed by stable key."""
    with app.app_context():
        from routes.staging import _apply_staged_edits_to_virtual
        virtual_objects = [
            {"source_file": "hosts.cfg", "object_type": "host",
             "display_name": "webserver", "name": "webserver",
             "attributes": {"host_name": "webserver", "address": "1.1.1.1"},
             "global_index": 0, "_staged_status": None},
            {"source_file": "hosts.cfg", "object_type": "host",
             "display_name": "dbserver", "name": "dbserver",
             "attributes": {"host_name": "dbserver", "address": "2.2.2.2"},
             "global_index": 1, "_staged_status": None},
        ]
        pending_edits = {
            "hosts.cfg|host|dbserver": {
                "edited": {"address": "3.3.3.3"},
                "object": {"source_file": "hosts.cfg", "object_type": "host",
                           "display_name": "dbserver"}
            }
        }
        edited = _apply_staged_edits_to_virtual(virtual_objects, pending_edits)
        assert virtual_objects[1]["attributes"]["address"] == "3.3.3.3"
        assert virtual_objects[1]["_staged_status"] == "edited"
        assert virtual_objects[0]["attributes"]["address"] == "1.1.1.1"
        assert 1 in edited


def test_apply_staged_deletions_by_stable_key(app):
    """Virtual tree should apply deletions keyed by stable key."""
    with app.app_context():
        from routes.staging import _apply_staged_deletions_to_virtual
        virtual_objects = [
            {"source_file": "hosts.cfg", "object_type": "host",
             "display_name": "webserver", "name": "webserver",
             "attributes": {"host_name": "webserver"},
             "global_index": 0, "_staged_status": None},
            {"source_file": "hosts.cfg", "object_type": "host",
             "display_name": "dbserver", "name": "dbserver",
             "attributes": {"host_name": "dbserver"},
             "global_index": 1, "_staged_status": None},
        ]
        staged_deletions = ["hosts.cfg|host|dbserver"]
        deleted = _apply_staged_deletions_to_virtual(virtual_objects, staged_deletions)
        assert virtual_objects[1]["_staged_status"] == "deleted"
        assert virtual_objects[0]["_staged_status"] is None
        assert 1 in deleted


def test_build_composite_actions_with_stable_key_edits(app):
    """_build_composite_actions should accept stable-key-keyed pendingEdits."""
    with app.app_context():
        from routes.helpers import get_service
        service = get_service()
        objects = service.get_objects()
        if not objects:
            pytest.skip("No objects in sample config")

        obj = objects[0]
        key = generate_stable_key_for_object(obj)

        staging_data = {
            "pendingEdits": {
                key: {
                    "object": {
                        "source_file": obj.source_file,
                        "object_type": obj.object_type,
                        "display_name": obj.get_display_name(),
                    },
                    "original": dict(obj.attributes),
                    "edited": {**obj.attributes, "alias": "test_alias"},
                }
            },
            "stagedMoves": {},
            "stagedObjectDeletions": [],
            "stagedCreations": [],
        }
        actions = service._build_composite_actions(staging_data)
        assert len(actions) == 1
        assert actions[0].action_type == "edit"
        assert actions[0].final_attrs.get("alias") == "test_alias"


def test_build_composite_actions_with_stable_key_deletions(app):
    """_build_composite_actions should accept stable-key stagedObjectDeletions."""
    with app.app_context():
        from routes.helpers import get_service
        service = get_service()
        objects = service.get_objects()
        if not objects:
            pytest.skip("No objects in sample config")

        obj = objects[0]
        key = generate_stable_key_for_object(obj)

        staging_data = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedObjectDeletions": [key],
            "stagedCreations": [],
        }
        actions = service._build_composite_actions(staging_data)
        assert len(actions) == 1
        assert actions[0].action_type == "delete"


def test_inheritance_api_resolves_correct_service(app_with_duplicate_services):
    """GET /api/templates/inheritance/<key> should find the right service by display_name."""
    with app_with_duplicate_services.app_context():
        from routes.helpers import get_service
        service = get_service()
        services = [o for o in service.get_objects() if o.object_type == "service"]

        # Build a stable key for the second service (windows-hosts PING)
        key2 = generate_stable_key_for_object(services[1])
        encoded_key = base64.b64encode(key2.encode()).decode()

        client = app_with_duplicate_services.test_client()
        resp = client.get(f"/api/templates/inheritance/{encoded_key}")
        # Should not 404 — must find the object
        assert resp.status_code != 404, f"Should find object for key: {key2}"
