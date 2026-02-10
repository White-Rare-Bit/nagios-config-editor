"""Integration tests exercising all four inheritance features together.

Tests the end-to-end path: config files -> parser -> inheritance resolution
-> API endpoints, using the Flask test client and real config files that
exercise:
  1. Templates with ! important values
  2. Objects with + additive values
  3. Objects with null cancellation
  4. Services that rely on implied inheritance from hosts
  5. Host escalations that inherit from hosts
"""

import base64
import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app


@pytest.fixture
def app():
    """Create Flask app with config exercising all inheritance features."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    # Templates file
    (test_config_path / "templates.cfg").write_text("""
define host {
    name                    base-host
    register                0
    max_check_attempts      5
    notification_interval   30
    contacts                base-contact
    notification_period     24x7
}

define host {
    name                    important-host
    register                0
    check_command           !check-host-alive
}

define service {
    name                    base-service
    register                0
    max_check_attempts      3
    check_interval          5
}

define contact {
    contact_name            base-contact
    alias                   Base Contact
    host_notification_commands      notify-host
    service_notification_commands   notify-service
    host_notification_period        24x7
    service_notification_period     24x7
}

define command {
    command_name    notify-host
    command_line    /usr/bin/printf "Host notification"
}

define command {
    command_name    notify-service
    command_line    /usr/bin/printf "Service notification"
}

define command {
    command_name    check-host-alive
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}

define command {
    command_name    check_ping
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}

define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    sunday          00:00-24:00
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
}
""")

    # Hosts file — uses additive and null
    (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name               web-01
    alias                   Web Server 01
    address                 10.0.0.1
    use                     base-host
    contact_groups          +ops-team
}

define host {
    host_name               web-02
    alias                   Web Server 02
    address                 10.0.0.2
    use                     base-host
    notification_period     null
}

define host {
    host_name               web-03
    alias                   Web Server 03
    address                 10.0.0.3
    use                     base-host,important-host
}
""")

    # Services file — relies on implied inheritance
    (test_config_path / "services.cfg").write_text("""
define service {
    host_name               web-01
    service_description     PING
    check_command           check_ping
    use                     base-service
}

define service {
    host_name               web-02
    service_description     PING
    check_command           check_ping
    use                     base-service
    contacts                svc-contact
}
""")

    # Escalations file — implied inheritance from host
    (test_config_path / "escalations.cfg").write_text("""
define hostescalation {
    host_name               web-01
    first_notification      3
    last_notification       5
    notification_interval   60
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True

    yield app

    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


class TestInheritanceIntegration:
    """End-to-end tests for all four inheritance features working together."""

    def _get_inheritance(self, client, obj_type, name):
        """Helper to get inheritance chain by building the stable key.

        Looks up the object in /api/objects to find its source_file and
        display_name, then constructs the base64 stable key for the
        /api/templates/inheritance/<key> endpoint.
        """
        resp = client.get("/api/objects")
        data = resp.get_json()
        for obj in data:
            if obj.get("object_type") != obj_type:
                continue
            attrs = obj.get("attributes", {})
            # Match by primary name field or template name
            if (attrs.get("host_name") == name or
                    attrs.get("name") == name or
                    attrs.get("service_description") == name):
                source = obj.get("source_file", "")
                display = obj.get("display_name", name)
                key = base64.b64encode(
                    f"{source}|{obj_type}|{display}".encode(),
                ).decode()
                return client.get(f"/api/templates/inheritance/{key}")
        return None

    def _get_inheritance_for_service(self, client, host_name, svc_desc):
        """Helper to get inheritance for a service identified by host + description."""
        resp = client.get("/api/objects")
        data = resp.get_json()
        for obj in data:
            if obj.get("object_type") != "service":
                continue
            attrs = obj.get("attributes", {})
            if (attrs.get("host_name") == host_name and
                    attrs.get("service_description") == svc_desc):
                source = obj.get("source_file", "")
                display = obj.get("display_name", "")
                key = base64.b64encode(
                    f"{source}|service|{display}".encode(),
                ).decode()
                return client.get(f"/api/templates/inheritance/{key}")
        return None

    # ------------------------------------------------------------------
    # Feature 1: Additive (+) inheritance
    # ------------------------------------------------------------------

    def test_additive_contact_groups_resolved(self, client):
        """web-01 uses base-host, has +ops-team — additive contact_groups."""
        resp = self._get_inheritance(client, "host", "web-01")
        assert resp is not None and resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        inherited = data.get("inherited", {})
        # contacts from base-host template
        assert "contacts" in inherited
        assert inherited["contacts"]["value"] == "base-contact"
        # contact_groups was additive: base had none, so just ops-team
        assert "contact_groups" in inherited
        assert "ops-team" in inherited["contact_groups"]["value"]

    def test_additive_preserves_other_inherited_attrs(self, client):
        """web-01 should still inherit max_check_attempts etc. from base-host."""
        resp = self._get_inheritance(client, "host", "web-01")
        assert resp is not None and resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        inherited = data.get("inherited", {})
        assert inherited["max_check_attempts"]["value"] == "5"
        assert inherited["notification_interval"]["value"] == "30"
        assert inherited["notification_period"]["value"] == "24x7"

    # ------------------------------------------------------------------
    # Feature 2: Null cancellation
    # ------------------------------------------------------------------

    def test_null_cancels_notification_period(self, client):
        """web-02 sets notification_period null — should NOT appear in inherited."""
        resp = self._get_inheritance(client, "host", "web-02")
        assert resp is not None and resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        inherited = data.get("inherited", {})
        assert "notification_period" not in inherited

    def test_null_preserves_other_inherited_attrs(self, client):
        """web-02 should still inherit max_check_attempts etc. from base-host."""
        resp = self._get_inheritance(client, "host", "web-02")
        assert resp is not None and resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        inherited = data.get("inherited", {})
        assert inherited["max_check_attempts"]["value"] == "5"
        assert inherited["contacts"]["value"] == "base-contact"

    # ------------------------------------------------------------------
    # Feature 3: Important (!) values
    # ------------------------------------------------------------------

    def test_important_check_command_in_chain(self, client):
        """web-03 uses base-host,important-host which has !check-host-alive."""
        resp = self._get_inheritance(client, "host", "web-03")
        assert resp is not None and resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        inherited = data.get("inherited", {})
        # check_command should be resolved from the important-host template
        assert "check_command" in inherited
        assert inherited["check_command"]["value"] == "check-host-alive"

    def test_important_value_source_tracked(self, client):
        """The important check_command should track its source template."""
        resp = self._get_inheritance(client, "host", "web-03")
        assert resp is not None and resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        inherited = data.get("inherited", {})
        assert inherited["check_command"]["source"] == "important-host"

    def test_multi_template_chain_includes_both(self, client):
        """web-03 uses base-host,important-host — both should be in the chain."""
        resp = self._get_inheritance(client, "host", "web-03")
        assert resp is not None and resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        chain = data.get("chain", [])
        chain_names = [
            entry.get("name") or entry.get("attributes", {}).get("name", "")
            for entry in chain
        ]
        assert "base-host" in chain_names
        assert "important-host" in chain_names

    # ------------------------------------------------------------------
    # Feature 4: Implied inheritance (tested via health check endpoint)
    # ------------------------------------------------------------------

    def test_health_check_no_false_positive_missing_contacts(self, client):
        """Health check should not flag web-01 PING service for missing contacts.

        The PING service on web-01 has no contacts directly, but should inherit
        from web-01's host contacts via implied inheritance (resolve_all_attrs).
        """
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        issues = data.get("issues", [])
        missing_contact_issues = [
            i for i in issues
            if i.get("type") == "missing_contacts"
            and "PING" in str(i.get("object", ""))
            and "web-01" in str(i.get("object", ""))
        ]
        assert len(missing_contact_issues) == 0, (
            f"False positive: {missing_contact_issues}"
        )

    def test_service_with_direct_contacts_not_flagged(self, client):
        """web-02 PING service has direct contacts — should not be flagged."""
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        issues = data.get("issues", [])
        missing_contact_issues = [
            i for i in issues
            if i.get("type") == "missing_contacts"
            and "PING" in str(i.get("object", ""))
            and "web-02" in str(i.get("object", ""))
        ]
        assert len(missing_contact_issues) == 0, (
            f"False positive on direct contacts: {missing_contact_issues}"
        )

    # ------------------------------------------------------------------
    # Template inheritance endpoint: services
    # ------------------------------------------------------------------

    def test_service_template_chain(self, client):
        """Service PING on web-01 should have base-service in its template chain."""
        resp = self._get_inheritance_for_service(client, "web-01", "PING")
        assert resp is not None and resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        inherited = data.get("inherited", {})
        assert inherited["max_check_attempts"]["value"] == "3"
        assert inherited["check_interval"]["value"] == "5"

    # ------------------------------------------------------------------
    # Host escalation implied inheritance (via health check)
    # ------------------------------------------------------------------

    def test_escalation_inherits_contact_groups_from_host(self, client):
        """Host escalation for web-01 should not be flagged as missing contact_groups.

        The escalation has no direct contact_groups, but should inherit from
        web-01 via implied inheritance.
        """
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        issues = data.get("issues", [])
        # The host escalation should not have missing_contacts issues
        # because it inherits contact_groups from the host via implied inheritance
        escalation_contact_issues = [
            i for i in issues
            if i.get("type") == "missing_contacts"
            and i.get("object_type") == "hostescalation"
            and "web-01" in str(i.get("object", ""))
        ]
        assert len(escalation_contact_issues) == 0, (
            f"Escalation missing contacts false positive: {escalation_contact_issues}"
        )

    # ------------------------------------------------------------------
    # Combinatorial: all features on same config
    # ------------------------------------------------------------------

    def test_no_template_resolution_errors(self, client):
        """None of the objects should produce template resolution errors."""
        for host in ("web-01", "web-02", "web-03"):
            resp = self._get_inheritance(client, "host", host)
            assert resp is not None and resp.status_code == 200  # noqa: PLR2004
            data = resp.get_json()
            errors = data.get("errors", [])
            assert errors == [], f"Errors for {host}: {errors}"

    def test_health_check_returns_valid_structure(self, client):
        """Health check should return well-formed response with summary."""
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()
        assert "issues" in data
        assert "summary" in data
        summary = data["summary"]
        assert "total_issues" in summary
        assert "errors" in summary
        assert "warnings" in summary
