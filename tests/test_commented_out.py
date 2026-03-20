"""Tests for commented-out object detection and handling."""

import tempfile
from pathlib import Path

from app.nagios_model import NagiosObject, NAME_FIELDS


def test_nagios_object_has_commented_out_fields():
    """NagiosObject should have is_commented_out, commented_attributes, raw_block fields."""
    obj = NagiosObject(object_type="host")
    assert obj.is_commented_out is False
    assert obj.commented_attributes == {}
    assert obj.raw_block == ""


def test_to_dict_includes_is_commented_out():
    """to_dict() should include is_commented_out flag."""
    obj = NagiosObject(object_type="host", is_commented_out=True)
    d = obj.to_dict()
    assert d["is_commented_out"] is True


def test_to_dict_includes_commented_attributes():
    """to_dict() should include commented_attributes when present."""
    obj = NagiosObject(
        object_type="host",
        is_commented_out=True,
        commented_attributes={"host_name": "old-server", "address": "10.0.0.1"},
    )
    d = obj.to_dict()
    assert d["commented_attributes"] == {"host_name": "old-server", "address": "10.0.0.1"}


def test_display_name_uses_commented_attributes():
    """Commented-out object should use name from commented_attributes."""
    obj = NagiosObject(
        object_type="host",
        is_commented_out=True,
        commented_attributes={"host_name": "old-server", "address": "10.0.0.1"},
    )
    assert obj.get_display_name() == "old-server (commented out)"


def test_display_name_fallback_to_line_number():
    """Commented-out object with no name field falls back to line number."""
    obj = NagiosObject(
        object_type="host",
        is_commented_out=True,
        commented_attributes={"address": "10.0.0.1"},
        line_number=42,
    )
    assert obj.get_display_name() == "[commented-out host@L42]"


def test_display_name_empty_commented_attributes():
    """Commented-out object with empty commented_attributes falls back to line number."""
    obj = NagiosObject(
        object_type="host",
        is_commented_out=True,
        line_number=15,
    )
    assert obj.get_display_name() == "[commented-out host@L15]"
