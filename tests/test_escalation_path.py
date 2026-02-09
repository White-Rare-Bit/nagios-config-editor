"""Tests for escalation path visualization (DOMAIN-7)."""

import shutil
import tempfile
from pathlib import Path

import pytest
from app import create_app


@pytest.fixture
def app_with_escalations():
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}
define command {
    command_name    notify-by-email
    command_line    /usr/bin/mail $CONTACTEMAIL$
}
""")

    (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    monday          00:00-24:00
}
""")

    (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name    admin
    host_notification_commands     notify-by-email
    service_notification_commands  notify-by-email
    host_notification_period       24x7
    service_notification_period    24x7
}
define contact {
    contact_name    manager
    host_notification_commands     notify-by-email
    service_notification_commands  notify-by-email
    host_notification_period       24x7
    service_notification_period    24x7
}
define contactgroup {
    contactgroup_name   admins
    members             admin
}
define contactgroup {
    contactgroup_name   managers
    members             manager
}
""")

    (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       web-01
    address         10.0.0.1
    max_check_attempts 5
    contact_groups  admins
    check_command   check_http
}
""")

    (test_config_path / "services.cfg").write_text("""
define service {
    host_name           web-01
    service_description HTTP
    check_command       check_http
    max_check_attempts  3
    contact_groups      admins
}
""")

    (test_config_path / "escalations.cfg").write_text("""
define serviceescalation {
    host_name               web-01
    service_description     HTTP
    contact_groups          managers
    first_notification      3
    last_notification       5
    notification_interval   30
}

define serviceescalation {
    host_name               web-01
    service_description     HTTP
    contact_groups          managers,admins
    first_notification      6
    last_notification       0
    notification_interval   60
}

define hostescalation {
    host_name               web-01
    contact_groups          managers
    first_notification      2
    last_notification       0
    notification_interval   15
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True
    yield app
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app_with_escalations):
    return app_with_escalations.test_client()


class TestEscalationPath:
    """Test escalation path API."""

    def test_service_escalation_path(self, client):
        """Service escalation path includes base contacts and escalation levels."""
        resp = client.get("/api/escalation-path/service/web-01/HTTP")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "base_contacts" in data
        assert "escalations" in data

        # Base contacts should include admin (via admins group)
        base_names = [c["name"] for c in data["base_contacts"]]
        assert "admin" in base_names

        # Should have 2 escalation levels
        assert len(data["escalations"]) == 2
        # First escalation starts at notification 3
        esc1 = data["escalations"][0]
        assert esc1["first_notification"] == 3
        # Second at notification 6
        esc2 = data["escalations"][1]
        assert esc2["first_notification"] == 6

    def test_host_escalation_path(self, client):
        """Host escalation path works correctly."""
        resp = client.get("/api/escalation-path/host/web-01")
        assert resp.status_code == 200
        data = resp.get_json()

        assert len(data["escalations"]) == 1
        assert data["escalations"][0]["first_notification"] == 2

        esc_contacts = [c["name"] for c in data["escalations"][0]["contacts"]]
        assert "manager" in esc_contacts

    def test_nonexistent_object(self, client):
        """Nonexistent object returns 404."""
        resp = client.get("/api/escalation-path/host/nonexistent")
        assert resp.status_code == 404
