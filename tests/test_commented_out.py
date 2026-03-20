"""Tests for commented-out object detection and handling."""

from app.nagios_model import NagiosObject, NAME_FIELDS
from app.nagios_parser import NagiosConfigParser


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


def test_parser_detects_commented_out_object_hash(tmp_path):
    """Parser should detect object with all #-commented attributes."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
    #host_name       old-server
    #alias           Old Server
    #address         10.0.0.1
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    assert len(objects) == 1
    obj = objects[0]
    assert obj.is_commented_out is True
    assert obj.commented_attributes["host_name"] == "old-server"
    assert obj.commented_attributes["address"] == "10.0.0.1"
    assert obj.attributes == {}


def test_parser_detects_commented_out_object_semicolon(tmp_path):
    """Parser should detect object with all ;-commented attributes."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
    ;host_name       old-server
    ;address         10.0.0.1
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    assert len(objects) == 1
    assert objects[0].is_commented_out is True
    assert objects[0].commented_attributes["host_name"] == "old-server"


def test_parser_preserves_raw_block(tmp_path):
    """Parser should store the raw block content for commented-out objects."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
    #host_name       old-server
    #address         10.0.0.1
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    assert "#host_name" in objects[0].raw_block
    assert "#address" in objects[0].raw_block


def test_parser_normal_object_not_commented_out(tmp_path):
    """Normal object with real attributes should not be flagged."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
    host_name       live-server
    address         10.0.0.2
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    assert len(objects) == 1
    assert objects[0].is_commented_out is False
    assert objects[0].commented_attributes == {}
    assert objects[0].raw_block == ""


def test_parser_empty_define_block_not_commented_out(tmp_path):
    """Truly empty define block (no content at all) is not commented-out."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    assert len(objects) == 1
    assert objects[0].is_commented_out is False


def test_parser_mixed_comments_and_attrs_not_commented_out(tmp_path):
    """Object with some commented and some real attributes is NOT commented-out."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
    host_name       live-server
    #old_alias      Old Name
    address         10.0.0.2
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    assert len(objects) == 1
    assert objects[0].is_commented_out is False
    assert objects[0].attributes["host_name"] == "live-server"


# --- Stable key tests ---

from app.stable_keys import generate_stable_key_for_object


def test_stable_key_uses_commented_name():
    """Stable key should use commented-out name, not [unnamed]."""
    obj = NagiosObject(
        object_type="host",
        source_file="/etc/nagios/hosts.cfg",
        is_commented_out=True,
        commented_attributes={"host_name": "old-server"},
    )
    key = generate_stable_key_for_object(obj)
    assert "old-server (commented out)" in key
    assert "[unnamed" not in key


def test_stable_keys_unique_for_multiple_commented_out(tmp_path):
    """Multiple commented-out objects in same file should have unique stable keys."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
    #host_name       server-a
    #address         10.0.0.1
}

define host {
    #host_name       server-b
    #address         10.0.0.2
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    keys = [generate_stable_key_for_object(obj) for obj in objects]
    assert len(set(keys)) == 2, f"Expected 2 unique keys, got: {keys}"


def test_stable_keys_unique_for_malformed_commented_out():
    """Commented-out objects without name field use line_number for uniqueness."""
    obj1 = NagiosObject(
        object_type="host",
        source_file="/etc/nagios/hosts.cfg",
        line_number=10,
        is_commented_out=True,
        commented_attributes={"address": "10.0.0.1"},
    )
    obj2 = NagiosObject(
        object_type="host",
        source_file="/etc/nagios/hosts.cfg",
        line_number=20,
        is_commented_out=True,
        commented_attributes={"address": "10.0.0.2"},
    )
    key1 = generate_stable_key_for_object(obj1)
    key2 = generate_stable_key_for_object(obj2)
    assert key1 != key2


# --- Writer tests ---

from app.nagios_writer import NagiosConfigWriter


def test_writer_preserves_commented_out_object():
    """Writer should output raw_block verbatim for commented-out objects."""
    raw = "    #host_name       old-server\n    #address         10.0.0.1"
    obj = NagiosObject(
        object_type="host",
        is_commented_out=True,
        raw_block=raw,
        commented_attributes={"host_name": "old-server"},
    )
    writer = NagiosConfigWriter()
    output = writer.object_to_string(obj)
    assert "#host_name" in output
    assert "#address" in output
    assert "define host {" in output
    assert "}" in output


def test_writer_round_trips_commented_out_object(tmp_path):
    """Parse -> write -> parse should preserve commented-out object."""
    cfg = tmp_path / "hosts.cfg"
    original = """define host {
    #host_name       old-server
    #alias           Old Server
    #address         10.0.0.1
}
"""
    cfg.write_text(original)
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    assert len(objects) == 1
    assert objects[0].is_commented_out is True

    writer = NagiosConfigWriter()
    output = writer.object_to_string(objects[0])
    assert "#host_name       old-server" in output
    assert "#address         10.0.0.1" in output
