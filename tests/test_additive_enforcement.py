"""Tests for additive inheritance whitelist enforcement."""

from dataclasses import dataclass, field

import pytest

from app.inheritance import build_template_lookup, resolve_inherited_attrs


@dataclass
class _Obj:
    object_type: str
    attributes: dict = field(default_factory=dict)
    source_file: str = "test.cfg"

    def get_name(self):
        from app.nagios_model import NAME_FIELDS
        nf = NAME_FIELDS.get(self.object_type)
        return self.attributes.get(nf) if nf else self.attributes.get("name")


def test_plus_on_supported_field_is_additive():
    """+ on contacts (a supported field) should prepend template value."""
    tmpl = _Obj("service", {"name": "base", "register": "0", "contacts": "admin"})
    child = _Obj("service", {"service_description": "HTTP", "use": "base", "contacts": "+oncall"})
    lookup = build_template_lookup([tmpl, child])
    resolved = resolve_inherited_attrs(child, lookup)
    assert resolved["contacts"] == "admin,oncall"


def test_plus_on_unsupported_field_is_literal():
    """+ on notes (not a supported field) should be treated as literal value."""
    tmpl = _Obj("service", {"name": "base", "register": "0", "notes": "base notes"})
    child = _Obj("service", {"service_description": "HTTP", "use": "base", "notes": "+extra"})
    lookup = build_template_lookup([tmpl, child])
    resolved = resolve_inherited_attrs(child, lookup)
    # + should NOT be treated as additive — the literal value "+extra" overrides
    assert resolved["notes"] == "+extra"


def test_plus_on_check_command_is_literal():
    """+ on check_command should be literal (not additive)."""
    tmpl = _Obj("service", {"name": "base", "register": "0", "check_command": "check_ping"})
    child = _Obj("service", {"service_description": "HTTP", "use": "base", "check_command": "+check_http"})
    lookup = build_template_lookup([tmpl, child])
    resolved = resolve_inherited_attrs(child, lookup)
    assert resolved["check_command"] == "+check_http"


# Fields Nagios documents as supporting additive (+) inheritance, written out by
# hand rather than read from ADDITIVE_FIELDS, so a field dropped from (or never
# wired into) the resolver's whitelist makes this fail.
_ADDITIVE_BY_TYPE = {
    "host": ["parents", "hostgroups", "contact_groups", "contacts"],
    "service": ["host_name", "hostgroup_name", "servicegroups", "contact_groups", "contacts"],
    "hostgroup": ["members", "hostgroup_members"],
    "servicegroup": ["members", "servicegroup_members"],
    "contactgroup": ["members", "contactgroup_members"],
    "contact": ["contactgroups", "host_notification_commands", "service_notification_commands"],
    "hostescalation": ["contacts", "contact_groups"],
    "serviceescalation": ["contacts", "contact_groups"],
    "hostdependency": ["host_name", "hostgroup_name"],
    "servicedependency": ["host_name", "hostgroup_name"],
}


@pytest.mark.parametrize("obj_type,field", [
    (t, f) for t, fields in _ADDITIVE_BY_TYPE.items() for f in fields
])
def test_plus_merges_with_template_value(obj_type, field):
    tmpl = _Obj(obj_type, {"name": "base", "register": "0", field: "from-template"})
    child = _Obj(obj_type, {"use": "base", field: "+from-child"})
    resolved = resolve_inherited_attrs(child, build_template_lookup([tmpl, child]))
    assert resolved[field] == "from-template,from-child"
