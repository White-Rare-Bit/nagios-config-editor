"""Tests for /api/metadata endpoint and nagios_model metadata constants."""

import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from nagios_model import (
    DEFAULT_ATTRIBUTES,
    GROUP_STRUCTURE,
    NAME_FIELDS,
    NOTIFICATION_OPTIONS,
    OBJECT_TYPE_LABELS,
    REFERENCE_FIELDS,
    VALID_ATTRIBUTES,
)


@pytest.fixture
def app():
    test_dir = tempfile.mkdtemp()
    cfg_path = Path(test_dir) / "nagios"
    cfg_path.mkdir()
    (cfg_path / "hosts.cfg").write_text("""
define host {
    host_name       test-host
    alias           Test
    address         1.2.3.4
}
""")
    application = create_app(config_path=str(cfg_path))
    application.config["TESTING"] = True
    yield application
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


class TestModelConstants:
    """Verify new constants exist and are well-formed."""

    def test_valid_attributes_covers_all_types(self):
        for obj_type in NAME_FIELDS:
            assert obj_type in VALID_ATTRIBUTES, f"Missing VALID_ATTRIBUTES for {obj_type}"
            assert isinstance(VALID_ATTRIBUTES[obj_type], list)
            assert len(VALID_ATTRIBUTES[obj_type]) > 0

    def test_valid_attributes_include_name_fields(self):
        for obj_type, name_field in NAME_FIELDS.items():
            attrs = VALID_ATTRIBUTES[obj_type]
            assert name_field in attrs or "name" in attrs, \
                f"{name_field} not in VALID_ATTRIBUTES[{obj_type}]"

    def test_object_type_labels_covers_all_types(self):
        for obj_type in NAME_FIELDS:
            assert obj_type in OBJECT_TYPE_LABELS

    def test_default_attributes_covers_all_types(self):
        for obj_type in NAME_FIELDS:
            assert obj_type in DEFAULT_ATTRIBUTES
            assert isinstance(DEFAULT_ATTRIBUTES[obj_type], dict)

    def test_notification_options_structure(self):
        assert "host_notification_options" in NOTIFICATION_OPTIONS
        assert "service_notification_options" in NOTIFICATION_OPTIONS
        assert "host_failure_criteria" in NOTIFICATION_OPTIONS
        assert "service_failure_criteria" in NOTIFICATION_OPTIONS
        assert "notification_option_attrs" in NOTIFICATION_OPTIONS

    def test_group_structure_covers_group_types(self):
        for group_type in ("hostgroup", "servicegroup", "contactgroup"):
            assert group_type in GROUP_STRUCTURE
            gs = GROUP_STRUCTURE[group_type]
            assert "name_attr" in gs
            assert "member_attrs" in gs
            assert "member_of_attr" in gs


class TestMetadataEndpoint:
    """Test GET /api/metadata."""

    def test_returns_all_metadata(self, client):
        resp = client.get("/api/metadata")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json
        assert data["success"] is True
        meta = data["data"]
        assert "name_fields" in meta
        assert "required_fields" in meta
        assert "reference_fields" in meta
        assert "valid_attributes" in meta
        assert "object_type_labels" in meta
        assert "default_attributes" in meta
        assert "notification_options" in meta
        assert "group_structure" in meta

    def test_name_fields_matches_model(self, client):
        resp = client.get("/api/metadata")
        meta = resp.json["data"]
        assert meta["name_fields"] == NAME_FIELDS

    def test_reference_fields_matches_model(self, client):
        resp = client.get("/api/metadata")
        meta = resp.json["data"]
        for key, val in REFERENCE_FIELDS.items():
            assert key in meta["reference_fields"]
            assert meta["reference_fields"][key] == val

    def test_valid_attributes_matches_model(self, client):
        resp = client.get("/api/metadata")
        meta = resp.json["data"]
        assert meta["valid_attributes"] == VALID_ATTRIBUTES

    def test_required_fields_serialization(self, client):
        """Tuples in REQUIRED_FIELDS become arrays in JSON."""
        resp = client.get("/api/metadata")
        meta = resp.json["data"]
        service_reqs = meta["required_fields"]["service"]
        assert ["host_name", "hostgroup_name"] in service_reqs
