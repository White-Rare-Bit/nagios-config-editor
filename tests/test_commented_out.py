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
