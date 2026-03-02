"""Tests for /api/metadata endpoint and nagios_model metadata constants."""

import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from nagios_model import (
    DEFAULT_ATTRIBUTES,
    GROUP_STRUCTURE,
    HOST_SCOPED_TYPES,
    NAME_FIELDS,
    NOTIFICATION_OPTIONS,
    OBJECT_TYPE_LABELS,
    REFERENCE_FIELDS,
    REFERENCE_TRIGGER_ATTRS,
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

    def test_host_scoped_types_is_list(self):
        assert isinstance(HOST_SCOPED_TYPES, list)
        assert HOST_SCOPED_TYPES == ["service", "serviceescalation", "servicedependency"]

    def test_reference_trigger_attrs_is_list(self):
        assert isinstance(REFERENCE_TRIGGER_ATTRS, list)
        for attr in ["use", "host_name", "check_command"]:
            assert attr in REFERENCE_TRIGGER_ATTRS


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

    def test_host_scoped_types_in_metadata(self, client):
        resp = client.get("/api/metadata")
        assert resp.status_code == 200  # noqa: PLR2004
        meta = resp.json["data"]
        assert "host_scoped_types" in meta
        assert meta["host_scoped_types"] == ["service", "serviceescalation", "servicedependency"]

    def test_reference_trigger_attrs_in_metadata(self, client):
        resp = client.get("/api/metadata")
        assert resp.status_code == 200  # noqa: PLR2004
        meta = resp.json["data"]
        assert "reference_trigger_attrs" in meta
        for attr in ["use", "host_name", "check_command"]:
            assert attr in meta["reference_trigger_attrs"]


class TestNewObjectTypeParsing:
    """Test that new object types (hostextinfo, serviceextinfo, module) are recognized."""

    def test_hostextinfo_parsed(self):
        test_dir = tempfile.mkdtemp()
        try:
            from nagios_parser import NagiosConfigParser

            cfg_path = Path(test_dir) / "nagios"
            cfg_path.mkdir()
            (cfg_path / "extinfo.cfg").write_text("""
define hostextinfo {
    host_name       test-host
    notes           Extended info for test host
    icon_image      server.png
}
""")
            parser = NagiosConfigParser(str(cfg_path))
            parser.parse_all()
            ext_objs = [o for o in parser.objects if o.object_type == "hostextinfo"]
            assert len(ext_objs) == 1, f"Expected 1 hostextinfo, got {len(ext_objs)}"
            assert ext_objs[0].attributes.get("host_name") == "test-host"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_module_parsed(self):
        test_dir = tempfile.mkdtemp()
        try:
            from nagios_parser import NagiosConfigParser

            cfg_path = Path(test_dir) / "nagios"
            cfg_path.mkdir()
            (cfg_path / "modules.cfg").write_text("""
define module {
    module_name     nrpe
    module_type     neb
    path            /usr/lib/nagios/nrpe.so
}
""")
            parser = NagiosConfigParser(str(cfg_path))
            parser.parse_all()
            mod_objs = [o for o in parser.objects if o.object_type == "module"]
            assert len(mod_objs) == 1, f"Expected 1 module, got {len(mod_objs)}"
            assert mod_objs[0].attributes.get("module_name") == "nrpe"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_contact_name_not_self_referenced(self):
        """A contact's own contact_name should not be flagged as a missing reference."""
        test_dir = tempfile.mkdtemp()
        try:
            cfg_path = Path(test_dir) / "nagios"
            cfg_path.mkdir()
            (cfg_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    sole-admin
    host_notification_commands      notify-host
    service_notification_commands   notify-service
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}
""")
            (cfg_path / "commands.cfg").write_text("""
define command {
    command_name    notify-host
    command_line    /usr/bin/true
}
define command {
    command_name    notify-service
    command_line    /usr/bin/true
}
""")
            (cfg_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    monday          00:00-24:00
}
""")
            application = create_app(config_path=str(cfg_path))
            application.config["TESTING"] = True
            client = application.test_client()
            resp = client.get("/api/health-check")
            assert resp.status_code == 200  # noqa: PLR2004
            data = resp.get_json()
            missing_contact_issues = [
                i for i in data["issues"]
                if i["type"] == "missing_contact"
                and "sole-admin" in i.get("message", "")
            ]
            assert len(missing_contact_issues) == 0, \
                f"contact_name should not be flagged as missing reference: {missing_contact_issues}"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
