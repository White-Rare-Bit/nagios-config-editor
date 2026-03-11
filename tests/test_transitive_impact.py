"""Tests for transitive impact analysis (Issue #17)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from stable_keys import generate_stable_key


@pytest.fixture
def transitive_app():
    """Create app with template inheritance chains for transitive impact testing."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    (test_config_path / "templates.cfg").write_text("""
define host {
    name            template-A
    register        0
    check_command   check-host-alive
}

define host {
    name            template-B
    use             template-A
    register        0
}

define host {
    name            flat-template
    register        0
    check_command   check-host-alive
}
""")

    # 3 concrete hosts use template-B (which uses template-A)
    # So template-A has transitive impact: template-B + 3 concrete = 4
    (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   host1
    use         template-B
    alias       Host 1
    address     10.0.0.1
}

define host {
    host_name   host2
    use         template-B
    alias       Host 2
    address     10.0.0.2
}

define host {
    host_name   host3
    use         template-B
    alias       Host 3
    address     10.0.0.3
}

define host {
    host_name   flat1
    use         flat-template
    alias       Flat 1
    address     10.0.1.1
}

define host {
    host_name   flat2
    use         flat-template
    alias       Flat 2
    address     10.0.1.2
}

define host {
    host_name   flat3
    use         flat-template
    alias       Flat 3
    address     10.0.1.3
}
""")

    (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
""")

    (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    monday          00:00-24:00
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True
    yield app
    shutil.rmtree(test_dir, ignore_errors=True)


def _find_stable_key(client, obj_type, name_attr, name_value):
    """Find stable key for an object by type and attribute name."""
    resp = client.get("/api/objects")
    assert resp.status_code == 200  # noqa: PLR2004
    for obj in resp.get_json():
        if obj.get("object_type") == obj_type:
            if obj.get("attributes", {}).get(name_attr) == name_value:
                return generate_stable_key(
                    obj["source_file"], obj["object_type"], obj["display_name"]
                )
    return None


class TestTransitiveImpact:
    """Test that transitive impact through intermediate templates is calculated correctly."""

    def test_transitive_count_through_intermediate(self, transitive_app):
        """template-A → template-B → 3 hosts: transitive_count should be 4."""
        client = transitive_app.test_client()
        key = _find_stable_key(client, "host", "name", "template-A")
        assert key is not None, "Could not find template-A"

        resp = client.get(f"/api/object-references?key={key}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        assert "transitive_summary" in data, \
            f"Expected transitive_summary for template-A, got keys: {list(data.keys())}"

        ts = data["transitive_summary"]
        assert ts["transitive_count"] == 4, \
            f"Expected transitive_count=4 (template-B + 3 hosts), got {ts['transitive_count']}"  # noqa: PLR2004
        assert "template-B" in ts["intermediate_templates"], \
            f"Expected template-B in intermediate_templates, got {ts['intermediate_templates']}"

    def test_no_transitive_when_flat(self, transitive_app):
        """flat-template → 3 hosts directly: no intermediate templates, so no transitive_summary."""
        client = transitive_app.test_client()
        key = _find_stable_key(client, "host", "name", "flat-template")
        assert key is not None, "Could not find flat-template"

        resp = client.get(f"/api/object-references?key={key}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        assert "transitive_summary" not in data, \
            f"Expected no transitive_summary for flat (direct-only) template, got: {data.get('transitive_summary')}"

    def test_transitive_with_cycle_protection(self):
        """Template chain with a cycle should not infinite loop and should return valid counts."""
        test_dir = tempfile.mkdtemp()
        try:
            test_config_path = Path(test_dir) / "nagios"
            test_config_path.mkdir()

            # cycle-A uses cycle-B, cycle-B uses cycle-A
            (test_config_path / "templates.cfg").write_text("""
define host {
    name            cycle-A
    use             cycle-B
    register        0
    check_command   check-host-alive
}

define host {
    name            cycle-B
    use             cycle-A
    register        0
    check_command   check-host-alive
}

define host {
    host_name   cycle-host
    use         cycle-A
    alias       Cycle Host
    address     10.0.0.1
}
""")

            (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
""")

            (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    monday          00:00-24:00
}
""")

            app = create_app(config_path=str(test_config_path))
            app.config["TESTING"] = True
            client = app.test_client()

            key = _find_stable_key(client, "host", "name", "cycle-A")
            assert key is not None, "Could not find cycle-A"

            # Should complete without hanging (cycle protection)
            resp = client.get(f"/api/object-references?key={key}")
            assert resp.status_code == 200  # noqa: PLR2004
            data = resp.get_json()

            # Should have members (cycle-B is a direct inheritor, cycle-host inherits)
            # The key assertion is that this doesn't hang
            assert "members" in data
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
