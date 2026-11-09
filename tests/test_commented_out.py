"""Tests for commented-out object detection and handling."""

from app.nagios_model import NagiosObject
from app.nagios_parser import NagiosConfigParser



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


# --- Write path: moving a commented-out object copies its raw block ---


def test_moving_commented_out_object_keeps_it_commented(tmp_path):
    """Moving uses the raw block text, so the object must arrive still commented
    out, with its commented attributes intact, after apply and a fresh parse."""
    from app import create_app
    config_dir = tmp_path / "nagios"
    config_dir.mkdir()
    (config_dir / "hosts.cfg").write_text("""define host {
    #host_name       old-server
    #address         10.0.0.1
}

define host {
    host_name       live-server
}
""")
    app = create_app(config_path=str(config_dir))
    app.config["TESTING"] = True
    client = app.test_client()
    obj = next(o for o in client.get("/api/objects").json if o.get("is_commented_out"))
    key = f"{obj['source_file']}|{obj['object_type']}|{obj['display_name']}"

    resp = client.post("/api/objects/move", json={
        "stable_key": key, "target_file": str(config_dir / "retired.cfg"),
    }, headers={"X-Session-Id": "s1"})
    assert resp.status_code == 200, resp.json
    assert client.post("/api/staging/apply", headers={"X-Session-Id": "s1"}).json["success"] is True

    moved = NagiosConfigParser(str(config_dir)).parse_all()
    retired = [o for o in moved if o.source_file.endswith("retired.cfg")]
    assert len(retired) == 1
    assert retired[0].is_commented_out is True
    assert retired[0].commented_attributes == {"host_name": "old-server", "address": "10.0.0.1"}
    assert "old-server" not in (config_dir / "hosts.cfg").read_text()




# --- Health check tests ---

from app.inheritance import build_template_lookup
from app.health_checks import run_all_checks


def test_health_check_skips_commented_out_objects(tmp_path):
    """Commented-out objects should not appear in health check issues (except the dedicated check)."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
    #host_name       old-server
    #address         10.0.0.1
}

define host {
    host_name       live-server
    address         10.0.0.2
    check_command   check-host-alive
}

define command {
    command_name    check-host-alive
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    obj_to_index = {id(obj): i for i, obj in enumerate(objects)}
    template_lookup = build_template_lookup(objects)
    issues = run_all_checks(objects, obj_to_index, template_lookup)

    # No issues should reference the commented-out host except the dedicated check
    non_dedicated = [i for i in issues
                     if i["type"] != "commented_out_object"
                     and "old-server" in i.get("object", "")]
    assert non_dedicated == [], \
        f"Commented-out host should only appear in dedicated check, got: {non_dedicated}"


def test_health_check_reports_commented_out_objects(tmp_path):
    """Dedicated check should flag commented-out objects as info."""
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text("""
define host {
    #host_name       old-server
    #address         10.0.0.1
}
""")
    parser = NagiosConfigParser(str(tmp_path))
    objects = parser.parse_all()
    obj_to_index = {id(obj): i for i, obj in enumerate(objects)}
    template_lookup = build_template_lookup(objects)
    issues = run_all_checks(objects, obj_to_index, template_lookup)

    commented = [i for i in issues if i["type"] == "commented_out_object"]
    assert len(commented) == 1
    assert commented[0]["severity"] == "info"
    assert "old-server" in commented[0]["object"]


# --- Integration test ---


def test_api_objects_includes_commented_out_flag(tmp_path):
    """GET /api/objects should include is_commented_out and commented_attributes."""
    test_config_path = tmp_path / "nagios"
    test_config_path.mkdir()
    (test_config_path / "hosts.cfg").write_text("""
define host {
    #host_name       old-server
    #address         10.0.0.1
}

define host {
    host_name       live-server
    address         10.0.0.2
}
""")
    from app import create_app
    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True
    client = app.test_client()

    resp = client.get("/api/objects")
    assert resp.status_code == 200
    objects = resp.json

    commented = [o for o in objects if o.get("is_commented_out")]
    assert len(commented) == 1
    assert commented[0]["commented_attributes"]["host_name"] == "old-server"
    assert commented[0]["display_name"] == "old-server (commented out)"

    live = [o for o in objects if not o.get("is_commented_out")]
    assert len(live) == 1
    assert live[0]["attributes"]["host_name"] == "live-server"
