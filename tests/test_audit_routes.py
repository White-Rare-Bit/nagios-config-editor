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
