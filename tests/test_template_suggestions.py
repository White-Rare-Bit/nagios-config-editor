"""Tests for /api/analysis/template-suggestions endpoint."""

import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from staging_manager import generate_stable_key_for_object


@pytest.fixture
def template_suggestion_app():
    """Create Flask app with config designed to produce template suggestions.

    Creates 4 services with identical non-identity attributes (check_command,
    max_check_attempts, contact_groups) but different host_name and
    service_description. Also creates objects that should be excluded:
    a template (register=0), a service using 'use', timeperiods, and commands.
    """
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_ping
    command_line    $USER1$/check_ping -H $HOSTADDRESS$ -w $ARG1$ -c $ARG2$
}

define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}

define command {
    command_name    notify-by-email
    command_line    /usr/bin/printf "%b" "Notification"
}
""")

    (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
    sunday          00:00-24:00
}

define timeperiod {
    timeperiod_name workhours
    alias           Work Hours
    monday          08:00-17:00
    tuesday         08:00-17:00
    wednesday       08:00-17:00
    thursday        08:00-17:00
    friday          08:00-17:00
}
""")

    (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-by-email
    service_notification_commands   notify-by-email
    host_notification_period        24x7
    service_notification_period     24x7
}

define contactgroup {
    contactgroup_name   admins
    members             admin
}
""")

    (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       web-server-1
    alias           Web Server 1
    address         10.0.0.1
    max_check_attempts  5
    contact_groups  admins
}

define host {
    host_name       web-server-2
    alias           Web Server 2
    address         10.0.0.2
    max_check_attempts  5
    contact_groups  admins
}

define host {
    host_name       web-server-3
    alias           Web Server 3
    address         10.0.0.3
    max_check_attempts  5
    contact_groups  admins
}

define host {
    host_name       db-server-1
    alias           DB Server 1
    address         10.0.1.1
    max_check_attempts  5
    contact_groups  admins
}
""")

    # 4 services with identical non-identity attributes (should produce a suggestion)
    # Plus 1 service using a template (should be excluded)
    # Plus 1 template (should be excluded)
    (test_config_path / "services.cfg").write_text("""
define service {
    name                    base-service-template
    register                0
    max_check_attempts      3
    check_command           check_ping!100!500
    contact_groups          admins
}

define service {
    host_name               web-server-1
    service_description     PING
    check_command           check_ping!100!500
    max_check_attempts      3
    contact_groups          admins
}

define service {
    host_name               web-server-2
    service_description     PING
    check_command           check_ping!100!500
    max_check_attempts      3
    contact_groups          admins
}

define service {
    host_name               web-server-3
    service_description     PING
    check_command           check_ping!100!500
    max_check_attempts      3
    contact_groups          admins
}

define service {
    host_name               db-server-1
    service_description     PING
    check_command           check_ping!100!500
    max_check_attempts      3
    contact_groups          admins
}

define service {
    host_name               web-server-1
    service_description     HTTP
    use                     base-service-template
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True

    yield app

    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(template_suggestion_app):
    return template_suggestion_app.test_client()


@pytest.fixture
def service(template_suggestion_app):
    return template_suggestion_app.extensions["service"]


class TestTemplateSuggestions:
    """Test template consolidation suggestion API endpoint."""

    def test_endpoint_returns_200(self, client):
        """Endpoint exists and returns 200."""
        response = client.get("/api/analysis/template-suggestions")
        assert response.status_code == 200  # noqa: PLR2004
        data = response.get_json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_suggestion_structure(self, client):
        """Each suggestion has required fields."""
        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        for s in data["suggestions"]:
            assert "type" in s, "Suggestion missing 'type'"
            assert "suggested_name" in s, "Suggestion missing 'suggested_name'"
            assert "attributes" in s, "Suggestion missing 'attributes'"
            assert "object_keys" in s, "Suggestion missing 'object_keys'"
            assert "count" in s, "Suggestion missing 'count'"
            assert "attr_count" in s, "Suggestion missing 'attr_count'"

    def test_minimum_three_objects(self, client):
        """Suggestions require at least 3 objects with matching signatures."""
        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        for s in data["suggestions"]:
            assert s["count"] >= 3, f"Suggestion has only {s['count']} objects, need at least 3"  # noqa: PLR2004

    def test_excludes_templated_objects(self, client, service):
        """Objects already using a template should not appear in suggestions."""
        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        all_suggested_keys = set()
        for s in data["suggestions"]:
            all_suggested_keys.update(s["object_keys"])

        for obj in service.get_objects():
            if generate_stable_key_for_object(obj) in all_suggested_keys:
                assert "use" not in obj.attributes, \
                    f"Object {obj.get_name()} already uses a template but is in suggestion"

    def test_excludes_templates(self, client, service):
        """Templates (register=0) should not appear in suggestions."""
        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        all_suggested_keys = set()
        for s in data["suggestions"]:
            all_suggested_keys.update(s["object_keys"])

        for obj in service.get_objects():
            if generate_stable_key_for_object(obj) in all_suggested_keys:
                assert obj.attributes.get("register", "1") != "0", \
                    f"Template {obj.get_name()} should not be in suggestions"

    def test_excludes_timeperiods_and_commands(self, client):
        """Timeperiod and command types should not get template suggestions."""
        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        for s in data["suggestions"]:
            assert s["type"] not in ("timeperiod", "command"), \
                f"Got suggestion for {s['type']} which should be excluded"

    def test_sorted_by_impact(self, client):
        """Suggestions are sorted by impact score (count * attr_count) descending."""
        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        if len(data["suggestions"]) < 2:  # noqa: PLR2004
            pytest.skip("Need at least 2 suggestions to test sorting")

        for i in range(len(data["suggestions"]) - 1):
            current = data["suggestions"][i]
            next_s = data["suggestions"][i + 1]
            current_impact = current["count"] * current["attr_count"]
            next_impact = next_s["count"] * next_s["attr_count"]
            assert current_impact >= next_impact, \
                f"Suggestions not sorted by impact: {current_impact} < {next_impact}"

    def test_identity_fields_excluded(self, client):
        """Identity fields like host_name should not be in shared attributes."""
        identity_fields = {
            "host_name", "service_description", "name", "contact_name",
            "alias", "address", "hostgroup_name", "servicegroup_name",
            "contactgroup_name", "command_name", "timeperiod_name",
        }

        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        for s in data["suggestions"]:
            for field in identity_fields:
                assert field not in s["attributes"], \
                    f"Identity field '{field}' should not be in shared attributes"

    def test_finds_service_suggestion(self, client):
        """Should find a suggestion for the 4 services with identical attributes."""
        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        service_suggestions = [s for s in data["suggestions"] if s["type"] == "service"]
        assert len(service_suggestions) >= 1, \
            f"Expected at least 1 service suggestion, got {len(service_suggestions)}"

        # Should have found the group of 4 services with matching attributes
        found = False
        for s in service_suggestions:
            if s["count"] >= 4:  # noqa: PLR2004
                found = True
                assert "check_command" in s["attributes"]
                assert "max_check_attempts" in s["attributes"]
                assert "contact_groups" in s["attributes"]
        assert found, \
            f"Expected a service suggestion with 4+ objects, got: {service_suggestions}"

    def test_host_suggestion_possible(self, client):
        """Should find host suggestions when 3+ hosts share attributes."""
        response = client.get("/api/analysis/template-suggestions")
        data = response.get_json()

        # Our config has 4 hosts, 3 of which share max_check_attempts=5, contact_groups=admins
        # (all 4 do actually, so we expect a suggestion for hosts too)
        host_suggestions = [s for s in data["suggestions"] if s["type"] == "host"]
        assert len(host_suggestions) >= 1, \
            f"Expected at least 1 host suggestion, got {len(host_suggestions)}"
