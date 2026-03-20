"""Tests for additive inheritance whitelist enforcement."""

from dataclasses import dataclass, field

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
