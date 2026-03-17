"""Tests for audit log calls in route handlers."""

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app


@pytest.fixture
def audit_app():
    """Create Flask app with isolated temp config for audit testing."""
    test_dir = os.path.realpath(tempfile.mkdtemp())
    config_path = Path(test_dir) / "nagios"
    config_path.mkdir()

    (config_path / "hosts.cfg").write_text("""\
define host {
    host_name       test-host-1
    alias           Test Host 1
    address         192.168.1.1
}
""")

    app = create_app(config_path=str(config_path))
    app.config["TESTING"] = True

    # Override primary_dir so _resolve_stable_key can remap paths to shadow
    with app.app_context():
        server_config = app.extensions.get("server_config")
        if server_config:
            server_config.paths.primary_dir = str(config_path)

    yield app

    with app.app_context():
        sm = app.extensions.get("shadow")
        if sm and sm.has_shadow():
            sm.destroy_shadow()
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def audit_client(audit_app):
    return audit_app.test_client()


def _get_object(client, host_name):
    resp = client.get("/api/objects")
    obj = next(o for o in resp.json if o["attributes"].get("host_name") == host_name)
    # Build stable_key from object data (source_file|object_type|display_name)
    obj["stable_key"] = f"{obj['source_file']}|{obj['object_type']}|{obj['display_name']}"
    return obj


class TestObjectEditAudit:
    def test_object_edit_logs_field_diffs(self, audit_client, caplog):
        obj = _get_object(audit_client, "test-host-1")
        new_attrs = dict(obj["attributes"])
        new_attrs["alias"] = "New Alias"
        new_attrs["address"] = "10.0.0.1"

        # The audit logger has propagate=False so caplog (on root) won't see it.
        # Temporarily enable propagation so caplog captures the audit lines.
        audit_logger = logging.getLogger("audit")
        audit_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO, logger="audit"):
                resp = audit_client.post("/api/objects/update", json={
                    "stable_key": obj["stable_key"],
                    "attributes": new_attrs,
                }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})
        finally:
            audit_logger.propagate = False

        assert resp.status_code == 200

        audit_lines = [r.message for r in caplog.records if r.name == "audit"]
        # Should have one line per changed field (alias and address)
        alias_lines = [l for l in audit_lines if "field=alias" in l]
        address_lines = [l for l in audit_lines if "field=address" in l]
        assert len(alias_lines) == 1
        assert 'from="Test Host 1"' in alias_lines[0]
        assert 'to="New Alias"' in alias_lines[0]
        assert len(address_lines) == 1
        assert "action=object_edit" in address_lines[0]
        assert "type=host" in address_lines[0]
        assert "name=test-host-1" in address_lines[0]

        # All lines should share the same txn
        txn_values = set()
        for line in audit_lines:
            m = re.search(r"txn=(\w+)", line)
            if m:
                txn_values.add(m.group(1))
        assert len(txn_values) == 1

        # file= should show original path, not shadow internal path
        for line in audit_lines:
            assert "file=nagios/hosts.cfg" in line or "file=hosts.cfg" in line
            assert "root_0" not in line


class TestObjectCreateAudit:
    def test_object_create_logs_audit(self, audit_client, caplog):
        obj = _get_object(audit_client, "test-host-1")
        target_file = obj["source_file"]

        audit_logger = logging.getLogger("audit")
        audit_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO, logger="audit"):
                resp = audit_client.post("/api/objects/create", json={
                    "target_file": target_file,
                    "object_type": "host",
                    "attributes": {"host_name": "new-host", "address": "1.2.3.4"},
                }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})
        finally:
            audit_logger.propagate = False

        assert resp.status_code == 200
        audit_lines = [r.message for r in caplog.records if r.name == "audit"]
        assert any("action=object_create" in l and "name=new-host" in l and "type=host" in l for l in audit_lines)
        # Verify file path doesn't leak shadow internals
        for l in audit_lines:
            assert "root_0" not in l


class TestObjectDeleteAudit:
    def test_object_delete_logs_audit(self, audit_client, caplog):
        obj = _get_object(audit_client, "test-host-1")

        audit_logger = logging.getLogger("audit")
        audit_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO, logger="audit"):
                resp = audit_client.post("/api/objects/delete", json={
                    "stable_key": obj["stable_key"],
                }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})
        finally:
            audit_logger.propagate = False

        assert resp.status_code == 200
        audit_lines = [r.message for r in caplog.records if r.name == "audit"]
        assert any("action=object_delete" in l and "name=test-host-1" in l and "type=host" in l for l in audit_lines)
        for l in audit_lines:
            assert "root_0" not in l


@pytest.fixture
def audit_app_multi():
    """App with multiple hosts for bulk operation testing."""
    test_dir = os.path.realpath(tempfile.mkdtemp())
    config_path = Path(test_dir) / "nagios"
    config_path.mkdir()

    (config_path / "hosts.cfg").write_text("""\
define host {
    host_name       host-a
    address         1.1.1.1
}

define host {
    host_name       host-b
    address         2.2.2.2
}

define host {
    host_name       host-c
    address         3.3.3.3
}
""")

    app = create_app(config_path=str(config_path))
    app.config["TESTING"] = True

    with app.app_context():
        server_config = app.extensions.get("server_config")
        if server_config:
            server_config.paths.primary_dir = str(config_path)

    yield app

    with app.app_context():
        sm = app.extensions.get("shadow")
        if sm and sm.has_shadow():
            sm.destroy_shadow()
    shutil.rmtree(test_dir, ignore_errors=True)


class TestBulkDeleteAudit:
    def test_delete_multiple_logs_per_object(self, audit_app_multi, caplog):
        client = audit_app_multi.test_client()
        resp = client.get("/api/objects")
        objects = resp.json
        keys = [
            f"{o['source_file']}|{o['object_type']}|{o['display_name']}"
            for o in objects if o["attributes"].get("host_name") in ("host-a", "host-b")
        ]

        audit_logger = logging.getLogger("audit")
        audit_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO, logger="audit"):
                resp = client.post("/api/objects/delete-multiple", json={
                    "stable_keys": keys,
                }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})
        finally:
            audit_logger.propagate = False

        assert resp.status_code == 200
        audit_lines = [r.message for r in caplog.records if r.name == "audit"]
        delete_lines = [l for l in audit_lines if "action=object_delete" in l]
        assert len(delete_lines) == 2

        # All should share the same txn
        txns = set()
        for l in delete_lines:
            m = re.search(r"txn=(\w+)", l)
            if m:
                txns.add(m.group(1))
        assert len(txns) == 1

        # No shadow path leakage
        for l in delete_lines:
            assert "root_0" not in l


class TestBulkMoveAudit:
    def test_move_objects_logs_per_object(self, audit_app_multi, caplog):
        client = audit_app_multi.test_client()

        # Get objects to move
        resp = client.get("/api/objects")
        objects = resp.json
        keys = []
        for o in objects:
            if o["attributes"].get("host_name") in ("host-a", "host-b"):
                key = f"{o['source_file']}|{o['object_type']}|{o['display_name']}"
                keys.append(key)

        with audit_app_multi.app_context():
            config_path = audit_app_multi.extensions["service"].config_path
        target = os.path.join(config_path, "moved.cfg")

        audit_logger = logging.getLogger("audit")
        audit_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO, logger="audit"):
                resp = client.post("/api/move-objects", json={
                    "stable_keys": keys,
                    "target_file": target,
                }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})
        finally:
            audit_logger.propagate = False

        assert resp.status_code == 200
        audit_lines = [r.message for r in caplog.records if r.name == "audit"]
        move_lines = [l for l in audit_lines if "action=object_move" in l]
        assert len(move_lines) == 2
        assert all("from_file=" in l and "to_file=" in l for l in move_lines)

        # All should share the same txn
        txns = set()
        for l in move_lines:
            m = re.search(r"txn=(\w+)", l)
            if m:
                txns.add(m.group(1))
        assert len(txns) == 1

        # No shadow path leakage
        for l in move_lines:
            assert "root_0" not in l


class TestObjectMoveAudit:
    def test_object_move_logs_audit(self, audit_app, caplog):
        client = audit_app.test_client()
        obj = _get_object(client, "test-host-1")

        with audit_app.app_context():
            config_path = audit_app.extensions["service"].config_path

        # Move to a new file (the service will create it)
        target_file = os.path.join(config_path, "other.cfg")

        audit_logger = logging.getLogger("audit")
        audit_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO, logger="audit"):
                resp = client.post("/api/objects/move", json={
                    "stable_key": obj["stable_key"],
                    "target_file": target_file,
                }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})
        finally:
            audit_logger.propagate = False

        assert resp.status_code == 200
        audit_lines = [r.message for r in caplog.records if r.name == "audit"]
        assert any("action=object_move" in l and "name=test-host-1" in l for l in audit_lines)
        assert any("from_file=" in l and "to_file=" in l for l in audit_lines)
        for l in audit_lines:
            assert "root_0" not in l
