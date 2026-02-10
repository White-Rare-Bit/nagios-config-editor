"""Tests for health check endpoint."""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from file_operations import edit_object_in_file
from git_service import GitService
from nagios_model import REQUIRED_FIELDS


@pytest.fixture
def health_check_app():
    """Create Flask app with test config for health check tests."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    # Create config with a contact that references a non-existent notification command
    (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    notify-host-by-email
    command_line    /usr/bin/printf "%b" "Host alert"
}

define command {
    command_name    check-host-alive
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}
""")

    (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-host-by-email
    service_notification_commands   nonexistent-notify-command
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}

define contact {
    contact_name                    oncall
    host_notification_commands      notify-host-by-email,nonexistent-cmd
    service_notification_commands   notify-host-by-email
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}
""")

    (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24 Hours A Day, 7 Days A Week
    sunday          00:00-24:00
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True

    yield app

    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def health_client(health_check_app):
    return health_check_app.test_client()


def test_health_check_detects_missing_notification_commands(health_client):
    """Health check should detect non-existent host/service notification commands on contacts."""
    resp = health_client.get("/api/health-check")
    assert resp.status_code == 200  # noqa: PLR2004
    data = resp.json

    # Find issues about the non-existent service_notification_commands
    cmd_issues = [i for i in data["issues"] if i["type"] == "missing_command"]
    missing_cmds = [i["message"] for i in cmd_issues]

    # Should detect the nonexistent-notify-command
    assert any("nonexistent-notify-command" in msg for msg in missing_cmds), \
        f"Expected missing_command for 'nonexistent-notify-command', got issues: {cmd_issues}"


def test_health_check_valid_notification_commands_no_false_positive(health_client):
    """Health check should NOT flag valid notification commands."""
    resp = health_client.get("/api/health-check")
    data = resp.json

    cmd_issues = [i for i in data["issues"] if i["type"] == "missing_command"]
    missing_cmds = [i["message"] for i in cmd_issues]

    # notify-host-by-email exists, should NOT be flagged
    assert not any("notify-host-by-email" in msg for msg in missing_cmds), \
        "False positive: valid command 'notify-host-by-email' flagged as missing"


def test_health_check_detects_missing_cmd_in_comma_separated_list(health_client):
    """Health check should detect a missing command even when it appears in a comma-separated list."""
    resp = health_client.get("/api/health-check")
    assert resp.status_code == 200  # noqa: PLR2004
    data = resp.json

    cmd_issues = [i for i in data["issues"] if i["type"] == "missing_command"]
    missing_cmds = [i["message"] for i in cmd_issues]

    # The 'oncall' contact has host_notification_commands = notify-host-by-email,nonexistent-cmd
    # The second command in the comma-separated list is invalid and should be detected
    assert any("nonexistent-cmd" in msg for msg in missing_cmds), \
        f"Expected missing_command for 'nonexistent-cmd' in comma-separated list, got issues: {cmd_issues}"

    # The issue message should reference ONLY 'nonexistent-cmd', not the entire comma-separated string
    oncall_cmd_issues = [i for i in cmd_issues if i["object"] == "oncall"]
    assert len(oncall_cmd_issues) == 1, \
        f"Expected exactly 1 missing command issue for 'oncall', got {len(oncall_cmd_issues)}: {oncall_cmd_issues}"
    assert oncall_cmd_issues[0]["message"] == "References non-existent command: nonexistent-cmd", \
        f"Expected precise error for 'nonexistent-cmd', got: {oncall_cmd_issues[0]['message']}"


def test_gitignore_references_correct_staging_dir():
    """Generated .gitignore should reference .staging/ not .nagios_staging/."""
    test_dir = tempfile.mkdtemp()
    try:
        gs = GitService(test_dir)
        gs.init_repo()
        gitignore_path = os.path.join(test_dir, ".gitignore")
        assert os.path.exists(gitignore_path), ".gitignore should be created"
        content = Path(gitignore_path).read_text()
        assert ".staging/" in content, f".gitignore should contain '.staging/', got:\n{content}"
        assert ".nagios_staging/" not in content, \
            f".gitignore should NOT contain '.nagios_staging/', got:\n{content}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_health_check_detects_hosts_without_services():
    """Health check should detect hosts that have no services assigned."""
    test_dir = tempfile.mkdtemp()
    try:
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       monitored-host
    alias           Has Services
    address         10.0.0.1
}

define host {
    host_name       lonely-host
    alias           No Services
    address         10.0.0.2
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               monitored-host
    service_description     PING
    check_command           check_ping
}
""")

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_ping
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        no_service_issues = [i for i in data["issues"]
                             if i["type"] == "host_without_services"]

        # lonely-host should be flagged
        flagged_hosts = [i["object"] for i in no_service_issues]
        assert "lonely-host" in flagged_hosts, \
            f"Expected 'lonely-host' flagged, got: {flagged_hosts}"

        # monitored-host should NOT be flagged
        assert "monitored-host" not in flagged_hosts, \
            "False positive: 'monitored-host' has services but was flagged"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_health_check_hostgroup_services_not_flagged():
    """Hosts with services via hostgroup_name should NOT be flagged."""
    test_dir = tempfile.mkdtemp()
    try:
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "config.cfg").write_text("""
define host {
    host_name       grouped-host
    alias           In Hostgroup
    address         10.0.0.3
    hostgroups      web-servers
}

define hostgroup {
    hostgroup_name  web-servers
    alias           Web Servers
}

define service {
    hostgroup_name          web-servers
    service_description     HTTP
    check_command           check_http
}

define command {
    command_name    check_http
    command_line    /usr/lib/nagios/plugins/check_http -H $HOSTADDRESS$
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.get("/api/health-check")
        data = resp.json

        no_service_issues = [i for i in data["issues"]
                             if i["type"] == "host_without_services"]
        flagged_hosts = [i["object"] for i in no_service_issues]

        assert "grouped-host" not in flagged_hosts, \
            "False positive: 'grouped-host' has services via hostgroup but was flagged"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_required_fields_host_includes_address():
    """REQUIRED_FIELDS for host should include 'address' (or template fallback)."""
    host_fields = REQUIRED_FIELDS.get("host", [])
    # address should be listed (possibly in an OR tuple with 'use')
    flat = []
    for f in host_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert "address" in flat, \
        f"'address' should be in host REQUIRED_FIELDS, got: {host_fields}"


def test_required_fields_service_includes_check_command():
    """REQUIRED_FIELDS for service should include 'check_command'."""
    svc_fields = REQUIRED_FIELDS.get("service", [])
    flat = []
    for f in svc_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert "check_command" in flat, \
        f"'check_command' should be in service REQUIRED_FIELDS, got: {svc_fields}"


def test_required_fields_contact_includes_notification_fields():
    """REQUIRED_FIELDS for contact should include notification fields."""
    contact_fields = REQUIRED_FIELDS.get("contact", [])
    flat = []
    for f in contact_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert "host_notification_commands" in flat or "notification_commands" in flat, \
        f"Contact REQUIRED_FIELDS should include notification commands, got: {contact_fields}"


def test_edit_object_uses_atomic_write(tmp_path):
    """edit_object_in_file should write atomically (temp file + rename)."""
    cfg = tmp_path / "test.cfg"
    cfg.write_text("""define host {
    host_name       test-host
    alias           Test
    address         1.2.3.4
}
""")
    result = edit_object_in_file(
        str(cfg), 1,
        {"host_name": "test-host", "alias": "Updated", "address": "1.2.3.4"},
        "host",
    )
    assert result.success, f"Edit failed: {result.error}"
    content = cfg.read_text()
    assert "Updated" in content
    # File should still exist and be valid (atomic write doesn't leave partial files)
    assert "define host" in content


class TestCheckCommandInheritance:
    """Test that services missing check_command are detected even through inheritance."""

    @pytest.fixture
    def app_with_missing_check_cmd(self):
        """Config where a service inherits but never gets check_command."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}
""")

        (test_config_path / "templates.cfg").write_text("""
define service {
    name                    no-cmd-template
    register                0
    max_check_attempts      3
    contact_groups          admins
}

define service {
    name                    has-cmd-template
    register                0
    max_check_attempts      3
    check_command           check_http
    contact_groups          admins
}
""")

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       test-host
    address         10.0.0.1
    max_check_attempts 5
    contact_groups  admins
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name    admin
    host_notification_commands  check-host-alive
    service_notification_commands check-host-alive
    host_notification_period    24x7
    service_notification_period 24x7
}
define contactgroup {
    contactgroup_name admins
    members           admin
}
define timeperiod {
    timeperiod_name 24x7
    monday          00:00-24:00
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               test-host
    service_description     Missing Check Command
    use                     no-cmd-template
}

define service {
    host_name               test-host
    service_description     Has Check Command
    use                     has-cmd-template
}

define service {
    host_name               test-host
    service_description     Direct Check Command
    check_command           check_http
    max_check_attempts      3
    contact_groups          admins
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_service_missing_check_command_through_inheritance(self, app_with_missing_check_cmd):
        """Service inheriting from template without check_command is flagged."""
        client = app_with_missing_check_cmd.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        missing_cmd_issues = [i for i in data["issues"]
                              if i["type"] == "missing_check_command"]

        # "Missing Check Command" service should be flagged
        flagged_names = [i["object"] for i in missing_cmd_issues]
        assert any("Missing Check Command" in n for n in flagged_names)

        # "Has Check Command" and "Direct Check Command" should NOT be flagged
        assert not any("Has Check Command" in n for n in flagged_names)
        assert not any("Direct Check Command" in n for n in flagged_names)


class TestCommandArgValidation:
    """Test that check_command argument count mismatches are detected."""

    @pytest.fixture
    def app_with_arg_mismatch(self):
        """Config with argument count mismatches."""
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
    command_name    check_procs
    command_line    $USER1$/check_procs -w $ARG1$ -c $ARG2$ -s $ARG3$
}
""")

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       test-host
    address         10.0.0.1
    max_check_attempts 5
    contact_groups  admins
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name    admin
    host_notification_commands  check_ping
    service_notification_commands check_ping
    host_notification_period    24x7
    service_notification_period 24x7
}
define contactgroup {
    contactgroup_name admins
    members           admin
}
define timeperiod {
    timeperiod_name 24x7
    monday          00:00-24:00
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               test-host
    service_description     Correct Args
    check_command           check_ping!100!500
    max_check_attempts      3
    contact_groups          admins
}

define service {
    host_name               test-host
    service_description     Too Few Args
    check_command           check_ping!100
    max_check_attempts      3
    contact_groups          admins
}

define service {
    host_name               test-host
    service_description     Too Many Args
    check_command           check_http!extra_arg
    max_check_attempts      3
    contact_groups          admins
}

define service {
    host_name               test-host
    service_description     No Args Needed
    check_command           check_http
    max_check_attempts      3
    contact_groups          admins
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_argument_count_mismatch(self, app_with_arg_mismatch):
        """Services with wrong argument count are flagged."""
        client = app_with_arg_mismatch.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        arg_issues = [i for i in data["issues"]
                      if i["type"] == "command_arg_mismatch"]

        flagged_names = [i["object"] for i in arg_issues]

        # "Too Few Args" and "Too Many Args" should be flagged
        assert any("Too Few Args" in n for n in flagged_names)
        assert any("Too Many Args" in n for n in flagged_names)

        # "Correct Args" and "No Args Needed" should NOT be flagged
        assert not any("Correct Args" in n for n in flagged_names)
        assert not any("No Args Needed" in n for n in flagged_names)


class TestTemplateConflictDetection:
    """Test that conflicting attributes from multi-template inheritance are warned."""

    @pytest.fixture
    def app_with_template_conflicts(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "templates.cfg").write_text("""
define host {
    name                    fast-check
    register                0
    check_interval          1
    max_check_attempts      3
}

define host {
    name                    slow-check
    register                0
    check_interval          10
    max_check_attempts      5
}

define host {
    name                    no-conflict
    register                0
    address                 0.0.0.0
}
""")

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       conflicting-host
    address         10.0.0.1
    use             fast-check,slow-check
    contact_groups  admins
}

define host {
    host_name       no-conflict-host
    address         10.0.0.2
    use             fast-check,no-conflict
    contact_groups  admins
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name    admin
    host_notification_commands  notify
    service_notification_commands notify
    host_notification_period    24x7
    service_notification_period 24x7
}
define contactgroup {
    contactgroup_name admins
    members           admin
}
define command {
    command_name    notify
    command_line    /bin/true
}
define timeperiod {
    timeperiod_name 24x7
    monday          00:00-24:00
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_template_attribute_conflicts(self, app_with_template_conflicts):
        """Objects inheriting conflicting attributes from multiple templates get a warning."""
        client = app_with_template_conflicts.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        conflict_issues = [i for i in data["issues"]
                           if i["type"] == "template_conflict"]

        # conflicting-host should have conflicts (check_interval, max_check_attempts differ)
        flagged = [i["object"] for i in conflict_issues]
        assert any("conflicting-host" in n for n in flagged)

        # no-conflict-host should NOT be flagged (fast-check and no-conflict don't overlap)
        assert not any("no-conflict-host" in n for n in flagged)


def test_apply_staging_with_validate_flag():
    """Apply staging should include validation result when validate=true."""
    test_dir = tempfile.mkdtemp()
    try:
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       test-host
    alias           Test Host
    address         192.168.1.1
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        client = app.test_client()

        # Stage an edit
        session_id = "test-session"
        headers = {"X-Session-Id": session_id, "Content-Type": "application/json"}

        # Get objects to find stable key
        resp = client.get("/api/objects")
        assert resp.status_code == 200  # noqa: PLR2004
        objects = resp.json
        assert len(objects) > 0
        obj = objects[0]

        # Stage an edit
        staging_data = {
            "sessionId": session_id,
            "userName": "Test User",
            "userEmail": "test@example.com",
            "pendingEdits": {
                str(obj["global_index"]): {
                    "object": obj,
                    "original": obj["attributes"],
                    "edited": {**obj["attributes"], "alias": "Modified"},
                },
            },
        }

        resp = client.post("/api/staging",
                           data=json.dumps(staging_data),
                           content_type="application/json",
                           headers=headers)
        assert resp.status_code == 200  # noqa: PLR2004

        # Apply with validate flag
        resp = client.post("/api/staging/apply", headers=headers, json={
            "validate": True,
        })
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        # Response should include a validation field
        assert "validation" in data, \
            f"Response should include 'validation' when validate=true, got keys: {list(data.keys())}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


class TestUnusedCommandDetection:
    """Test that unused commands are detected by health check."""

    @pytest.fixture
    def app_with_unused_commands(self):
        """Config with 4 commands: 2 used, 2 unused."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}

define command {
    command_name    notify-by-email
    command_line    /usr/bin/printf "%b" "Notification"
}

define command {
    command_name    unused-check
    command_line    $USER1$/check_dummy
}

define command {
    command_name    unused-notify
    command_line    /usr/bin/printf "%b" "Unused"
}
""")

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       test-host
    address         10.0.0.1
    check_command   check-host-alive
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

    def test_detects_unused_commands(self, app_with_unused_commands):
        """Unused commands should be detected; used ones should not."""
        client = app_with_unused_commands.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        unused_cmd_issues = [i for i in data["issues"]
                             if i["type"] == "unused_command"]
        flagged_names = [i["object"] for i in unused_cmd_issues]

        # unused-check and unused-notify should be flagged
        assert "unused-check" in flagged_names, \
            f"Expected 'unused-check' flagged, got: {flagged_names}"
        assert "unused-notify" in flagged_names, \
            f"Expected 'unused-notify' flagged, got: {flagged_names}"

        # check-host-alive and notify-by-email should NOT be flagged
        assert "check-host-alive" not in flagged_names, \
            "False positive: 'check-host-alive' is used but was flagged"
        assert "notify-by-email" not in flagged_names, \
            "False positive: 'notify-by-email' is used but was flagged"

    def test_unused_commands_are_warnings(self, app_with_unused_commands):
        """Unused command issues should have 'warning' severity."""
        client = app_with_unused_commands.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        unused_cmd_issues = [i for i in data["issues"]
                             if i["type"] == "unused_command"]

        assert len(unused_cmd_issues) > 0, "Expected at least one unused_command issue"
        for issue in unused_cmd_issues:
            assert issue["severity"] == "warning", \
                f"Expected severity 'warning', got '{issue['severity']}' for {issue['object']}"


class TestUnusedObjectDetection:
    """Test that unused contacts, contactgroups, and timeperiods are detected."""

    @pytest.fixture
    def app_with_unused_objects(self):
        """Config with used and unused contacts, contactgroups, and timeperiods."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}

define command {
    command_name    notify-by-email
    command_line    /usr/bin/printf "%b" "Notification"
}
""")

        (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24 Hours A Day
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
    sunday          00:00-24:00
}

define timeperiod {
    timeperiod_name unused-period
    alias           Unused Time Period
    monday          08:00-17:00
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    used-contact
    host_notification_commands      notify-by-email
    service_notification_commands   notify-by-email
    host_notification_period        24x7
    service_notification_period     24x7
}

define contact {
    contact_name                    unused-contact
    host_notification_commands      notify-by-email
    service_notification_commands   notify-by-email
    host_notification_period        24x7
    service_notification_period     24x7
}
""")

        (test_config_path / "contactgroups.cfg").write_text("""
define contactgroup {
    contactgroup_name   used-cg
    alias               Used Contact Group
    members             used-contact
}

define contactgroup {
    contactgroup_name   unused-cg
    alias               Unused Contact Group
}
""")

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       test-host
    address         10.0.0.1
    check_command   check-host-alive
    contact_groups  used-cg
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               test-host
    service_description     PING
    check_command           check-host-alive
    contact_groups          used-cg
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_unused_contacts(self, app_with_unused_objects):
        """unused-contact should be flagged; used-contact should not."""
        client = app_with_unused_objects.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        unused_contact_issues = [i for i in data["issues"]
                                 if i["type"] == "unused_contact"]
        flagged_names = [i["object"] for i in unused_contact_issues]

        assert "unused-contact" in flagged_names, \
            f"Expected 'unused-contact' flagged, got: {flagged_names}"
        assert "used-contact" not in flagged_names, \
            "False positive: 'used-contact' is referenced by contactgroup but was flagged"

    def test_detects_unused_contactgroups(self, app_with_unused_objects):
        """unused-cg should be flagged; used-cg should not."""
        client = app_with_unused_objects.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        unused_cg_issues = [i for i in data["issues"]
                            if i["type"] == "unused_contactgroup"]
        flagged_names = [i["object"] for i in unused_cg_issues]

        assert "unused-cg" in flagged_names, \
            f"Expected 'unused-cg' flagged, got: {flagged_names}"
        assert "used-cg" not in flagged_names, \
            "False positive: 'used-cg' is assigned to host/service but was flagged"

    def test_detects_unused_timeperiods(self, app_with_unused_objects):
        """unused-period should be flagged; 24x7 should not."""
        client = app_with_unused_objects.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        unused_tp_issues = [i for i in data["issues"]
                            if i["type"] == "unused_timeperiod"]
        flagged_names = [i["object"] for i in unused_tp_issues]

        assert "unused-period" in flagged_names, \
            f"Expected 'unused-period' flagged, got: {flagged_names}"
        assert "24x7" not in flagged_names, \
            "False positive: '24x7' is used by contacts but was flagged"


class TestDuplicateObjectDetection:
    """Test that duplicate object definitions are detected by health check."""

    @pytest.fixture
    def app_with_duplicates(self):
        """Config with duplicate host definitions across files."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts1.cfg").write_text("""
define host {
    host_name       duplicate-host
    alias           First Copy
    address         10.0.0.1
}
""")

        (test_config_path / "hosts2.cfg").write_text("""
define host {
    host_name       duplicate-host
    alias           Second Copy
    address         10.0.0.2
}

define host {
    host_name       unique-host
    alias           Only One
    address         10.0.0.3
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

    def test_detects_duplicate_hosts(self, app_with_duplicates):
        """duplicate-host should be flagged; unique-host should not."""
        client = app_with_duplicates.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        dup_issues = [i for i in data["issues"]
                      if i["type"] == "duplicate"]
        flagged_names = [i["object"] for i in dup_issues]

        assert "duplicate-host" in flagged_names, \
            f"Expected 'duplicate-host' flagged, got: {flagged_names}"
        assert "unique-host" not in flagged_names, \
            "False positive: 'unique-host' is not duplicated but was flagged"

    def test_duplicate_is_error_severity(self, app_with_duplicates):
        """All duplicate issues should have 'error' severity."""
        client = app_with_duplicates.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        dup_issues = [i for i in data["issues"]
                      if i["type"] == "duplicate"]

        assert len(dup_issues) > 0, "Expected at least one duplicate issue"
        for issue in dup_issues:
            assert issue["severity"] == "error", \
                f"Expected severity 'error', got '{issue['severity']}' for {issue['object']}"

    def test_duplicate_reports_files(self, app_with_duplicates):
        """Duplicate issue message should mention the other file(s)."""
        client = app_with_duplicates.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        dup_issues = [i for i in data["issues"]
                      if i["type"] == "duplicate"]

        assert len(dup_issues) >= 2, f"Expected at least 2 duplicate issues (one per copy), got {len(dup_issues)}"  # noqa: PLR2004

        # Each duplicate issue should mention the other file
        for issue in dup_issues:
            # The message should reference at least one other file
            assert "also in" in issue["message"], \
                f"Expected 'also in' in message, got: {issue['message']}"
            # Should mention a .cfg file
            assert ".cfg" in issue["message"], \
                f"Expected a .cfg filename in message, got: {issue['message']}"


# ============================================================
# Comprehensive fixture for new health-check analysis checks
# ============================================================

@pytest.fixture
def comprehensive_health_app():
    """Create Flask app with config designed to trigger every new health check.

    The config includes:
    - A duplicate host (same name in two files)
    - An unused command, contact, contactgroup, timeperiod
    - An orphan host (not referenced by anything)
    - A host without contacts and no template
    - A service with 10+ hosts
    - Templates that some objects use (to test non-false-positives)
    - Objects sharing attributes for template consolidation
    """
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    # Commands: 1 used, 1 unused
    (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_ping
    command_line    $USER1$/check_ping -H $HOSTADDRESS$ -w $ARG1$ -c $ARG2$
}

define command {
    command_name    notify-email
    command_line    /usr/bin/printf "%b" "Notification"
}

define command {
    command_name    unused-cmd
    command_line    /usr/bin/true
}
""")

    # Timeperiods: 1 used, 1 unused
    (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24 Hours
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
    sunday          00:00-24:00
}

define timeperiod {
    timeperiod_name unused-tp
    alias           Unused Time Period
    monday          08:00-17:00
}
""")

    # Contacts: 1 used, 1 unused
    (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    active-admin
    host_notification_commands      notify-email
    service_notification_commands   notify-email
    host_notification_period        24x7
    service_notification_period     24x7
}

define contact {
    contact_name                    unused-contact
    host_notification_commands      notify-email
    service_notification_commands   notify-email
    host_notification_period        24x7
    service_notification_period     24x7
}
""")

    # Contactgroups: 1 used, 1 unused
    (test_config_path / "contactgroups.cfg").write_text("""
define contactgroup {
    contactgroup_name   active-admins
    alias               Active Admins
    members             active-admin
}

define contactgroup {
    contactgroup_name   unused-cg
    alias               Unused CG
}
""")

    # Templates
    (test_config_path / "templates.cfg").write_text("""
define host {
    name                    base-host-template
    register                0
    max_check_attempts      5
    contact_groups          active-admins
    check_period            24x7
    notification_period     24x7
}

define service {
    name                    base-svc-template
    register                0
    max_check_attempts      3
    contact_groups          active-admins
    check_period            24x7
    notification_period     24x7
}
""")

    # Duplicate host (in file 1)
    (test_config_path / "hosts1.cfg").write_text("""
define host {
    host_name       dup-host
    alias           Duplicate Host Copy 1
    address         10.0.0.1
    use             base-host-template
}
""")

    # Duplicate host (in file 2) + orphan host + host without contacts
    (test_config_path / "hosts2.cfg").write_text("""
define host {
    host_name       dup-host
    alias           Duplicate Host Copy 2
    address         10.0.0.2
    use             base-host-template
}

define host {
    host_name       orphan-host
    alias           Nobody References Me
    address         10.0.0.3
    use             base-host-template
}

define host {
    host_name       no-contacts-host
    alias           No Contacts Defined
    address         10.0.0.4
    max_check_attempts  5
    check_period    24x7
}

define host {
    host_name       referenced-host
    alias           Referenced Host
    address         10.0.0.5
    use             base-host-template
}
""")

    # Many hosts for the long host list service
    host_lines = []
    for i in range(12):
        host_lines.append(f"""
define host {{
    host_name       web{i:02d}
    alias           Web Server {i}
    address         10.1.0.{i+1}
    use             base-host-template
}}""")
    (test_config_path / "webhosts.cfg").write_text("\n".join(host_lines))

    # Services including long host list, orphan detection cases, and no-contacts service
    (test_config_path / "services.cfg").write_text("""
define service {
    host_name               referenced-host
    service_description     PING
    check_command           check_ping!100!500
    use                     base-svc-template
}

define service {
    host_name               web00,web01,web02,web03,web04,web05,web06,web07,web08,web09,web10,web11
    service_description     Long Host List Service
    check_command           check_ping!100!500
    use                     base-svc-template
}

define service {
    host_name               no-contacts-host
    service_description     No Contacts Service
    check_command           check_ping!100!500
    max_check_attempts      3
    check_period            24x7
}
""")

    # 3+ hosts without templates sharing the same attrs (for template consolidation)
    (test_config_path / "consolidation.cfg").write_text("""
define host {
    host_name       cons-host-1
    alias           Consolidation Host 1
    address         10.2.0.1
    max_check_attempts  5
    check_period    24x7
    notification_period 24x7
    contact_groups  active-admins
}

define host {
    host_name       cons-host-2
    alias           Consolidation Host 2
    address         10.2.0.2
    max_check_attempts  5
    check_period    24x7
    notification_period 24x7
    contact_groups  active-admins
}

define host {
    host_name       cons-host-3
    alias           Consolidation Host 3
    address         10.2.0.3
    max_check_attempts  5
    check_period    24x7
    notification_period 24x7
    contact_groups  active-admins
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True

    yield app

    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def comp_client(comprehensive_health_app):
    return comprehensive_health_app.test_client()


def _get_health_issues(client):
    """Helper to get health check issues from the API."""
    resp = client.get("/api/health-check")
    assert resp.status_code == 200  # noqa: PLR2004
    return resp.json


class TestHealthCheckGlobalIndex:
    """All issues should have a global_index field."""

    def test_all_issues_have_global_index(self, comp_client):
        """Every issue dict should contain a 'global_index' key."""
        data = _get_health_issues(comp_client)
        issues = data["issues"]
        assert len(issues) > 0, "Expected at least some issues"

        for issue in issues:
            assert "global_index" in issue, \
                f"Issue missing global_index: {issue}"

    def test_global_index_is_int_or_none(self, comp_client):
        """global_index should be an integer (or None for template_opportunity)."""
        data = _get_health_issues(comp_client)
        for issue in data["issues"]:
            gi = issue.get("global_index")
            if issue["type"] == "template_opportunity":
                # template_opportunity may have None global_index
                continue
            assert gi is None or isinstance(gi, int), \
                f"global_index should be int or None, got {type(gi)}: {issue}"


class TestDuplicateDetectionEnhanced:
    """Duplicate detection should include related_objects."""

    def test_duplicate_includes_related_objects(self, comp_client):
        """Duplicate issues should include a related_objects list."""
        data = _get_health_issues(comp_client)
        dup_issues = [i for i in data["issues"] if i["type"] == "duplicate"]
        assert len(dup_issues) > 0, \
            f"Expected duplicate issues, got types: {set(i['type'] for i in data['issues'])}"

        for issue in dup_issues:
            assert "related_objects" in issue, \
                f"Duplicate issue missing related_objects: {issue}"
            assert isinstance(issue["related_objects"], list), \
                "related_objects should be a list"
            assert len(issue["related_objects"]) >= 2, "related_objects should have >=2 entries for a duplicate"  # noqa: PLR2004

    def test_related_objects_have_required_fields(self, comp_client):
        """Each related_object should have global_index, file, line."""
        data = _get_health_issues(comp_client)
        dup_issues = [i for i in data["issues"] if i["type"] == "duplicate"]
        assert len(dup_issues) > 0

        for issue in dup_issues:
            for ro in issue["related_objects"]:
                assert "global_index" in ro, f"related_object missing global_index: {ro}"
                assert "file" in ro, f"related_object missing file: {ro}"
                assert "line" in ro, f"related_object missing line: {ro}"

    def test_duplicate_is_error_severity(self, comp_client):
        """Duplicate issues should be errors."""
        data = _get_health_issues(comp_client)
        dup_issues = [i for i in data["issues"] if i["type"] == "duplicate"]
        for issue in dup_issues:
            assert issue["severity"] == "error"

    def test_finds_duplicate_host(self, comp_client):
        """Should find dup-host as a duplicate."""
        data = _get_health_issues(comp_client)
        dup_issues = [i for i in data["issues"] if i["type"] == "duplicate"]
        dup_names = [i["object"] for i in dup_issues]
        assert "dup-host" in dup_names, \
            f"Expected 'dup-host' in duplicates, got: {dup_names}"


class TestOrphanDetectionInHealthCheck:
    """Orphan detection should be included in health-check."""

    def test_finds_orphan_host(self, comp_client):
        """orphan-host is not referenced by any service or other object."""
        data = _get_health_issues(comp_client)
        orphan_issues = [i for i in data["issues"] if i["type"] == "orphan"]
        orphan_names = [i["object"] for i in orphan_issues]
        assert "orphan-host" in orphan_names, \
            f"Expected 'orphan-host' flagged, got: {orphan_names}"

    def test_referenced_host_not_orphan(self, comp_client):
        """referenced-host has services, so it should not be flagged."""
        data = _get_health_issues(comp_client)
        orphan_issues = [i for i in data["issues"] if i["type"] == "orphan"]
        orphan_names = [i["object"] for i in orphan_issues]
        assert "referenced-host" not in orphan_names, \
            "False positive: 'referenced-host' is referenced but was flagged as orphan"

    def test_orphan_is_info_severity(self, comp_client):
        """Orphan issues should have 'info' severity."""
        data = _get_health_issues(comp_client)
        orphan_issues = [i for i in data["issues"] if i["type"] == "orphan"]
        for issue in orphan_issues:
            assert issue["severity"] == "info", \
                f"Expected severity 'info', got '{issue['severity']}' for {issue['object']}"

    def test_templates_not_flagged_as_orphans(self, comp_client):
        """Templates (register=0) should not be flagged as orphans."""
        data = _get_health_issues(comp_client)
        orphan_issues = [i for i in data["issues"] if i["type"] == "orphan"]
        orphan_names = [i["object"] for i in orphan_issues]
        assert "base-host-template" not in orphan_names
        assert "base-svc-template" not in orphan_names


class TestNotificationGaps:
    """Hosts/services without contacts, contact_groups, AND no use template."""

    def test_host_without_contacts_flagged(self, comp_client):
        """no-contacts-host has no contacts, no contact_groups, no use -- should be flagged."""
        data = _get_health_issues(comp_client)
        gap_issues = [i for i in data["issues"]
                      if i["type"] == "missing_contacts" and i["object_type"] in ("host", "service")]
        gap_objects = [i["object"] for i in gap_issues]
        assert "no-contacts-host" in gap_objects, \
            f"Expected 'no-contacts-host' flagged, got: {gap_objects}"

    def test_service_without_contacts_flagged(self, comp_client):
        """No Contacts Service has no contacts, no contact_groups, no use -- should be flagged."""
        data = _get_health_issues(comp_client)
        gap_issues = [i for i in data["issues"]
                      if i["type"] == "missing_contacts" and i["object_type"] == "service"]
        gap_objects = [i["object"] for i in gap_issues]
        assert any("No Contacts Service" in o for o in gap_objects), \
            f"Expected 'No Contacts Service' flagged, got: {gap_objects}"

    def test_templated_host_not_flagged(self, comp_client):
        """Hosts that use a template should not be flagged (contacts may come from template)."""
        data = _get_health_issues(comp_client)
        gap_issues = [i for i in data["issues"]
                      if i["type"] == "missing_contacts"
                      and i["object_type"] in ("host", "service")]
        gap_objects = [i["object"] for i in gap_issues]
        # referenced-host uses base-host-template which has contact_groups
        assert "referenced-host" not in gap_objects, \
            "False positive: 'referenced-host' has contacts via template but was flagged"

    def test_notification_gap_is_warning(self, comp_client):
        """Notification gap issues should be warnings."""
        data = _get_health_issues(comp_client)
        gap_issues = [i for i in data["issues"]
                      if i["type"] == "missing_contacts"
                      and i["object_type"] in ("host", "service")]
        for issue in gap_issues:
            assert issue["severity"] == "warning"


class TestLongHostList:
    """Services with 10+ comma-separated hosts in host_name."""

    def test_finds_long_host_list(self, comp_client):
        """Long Host List Service has 12 hosts -- should be flagged."""
        data = _get_health_issues(comp_client)
        long_issues = [i for i in data["issues"] if i["type"] == "long_host_list"]
        assert len(long_issues) > 0, "Expected at least one long_host_list issue"
        names = [i["object"] for i in long_issues]
        assert any("Long Host List" in n for n in names), \
            f"Expected 'Long Host List Service' flagged, got: {names}"

    def test_includes_host_count(self, comp_client):
        """Long host list issues should include host_count."""
        data = _get_health_issues(comp_client)
        long_issues = [i for i in data["issues"] if i["type"] == "long_host_list"]
        assert len(long_issues) > 0
        for issue in long_issues:
            assert "host_count" in issue, \
                f"long_host_list issue missing host_count: {issue}"
            assert issue["host_count"] >= 10, f"host_count should be >= 10, got {issue['host_count']}"  # noqa: PLR2004

    def test_long_host_list_is_info(self, comp_client):
        """Long host list issues should be info severity."""
        data = _get_health_issues(comp_client)
        long_issues = [i for i in data["issues"] if i["type"] == "long_host_list"]
        for issue in long_issues:
            assert issue["severity"] == "info"

    def test_short_host_list_not_flagged(self, comp_client):
        """PING service on single host should NOT be flagged."""
        data = _get_health_issues(comp_client)
        long_issues = [i for i in data["issues"] if i["type"] == "long_host_list"]
        flagged_names = [i["object"] for i in long_issues]
        assert not any("PING" in n for n in flagged_names), \
            "False positive: single-host service flagged as long_host_list"


class TestTemplateConsolidation:
    """Template consolidation detection in health check."""

    def test_finds_template_opportunity(self, comp_client):
        """3 cons-host-* objects share identical attrs -- should suggest template."""
        data = _get_health_issues(comp_client)
        tmpl_issues = [i for i in data["issues"] if i["type"] == "template_opportunity"]
        assert len(tmpl_issues) > 0, \
            f"Expected at least one template_opportunity issue, got types: {set(i['type'] for i in data['issues'])}"

    def test_suggestion_has_required_fields(self, comp_client):
        """Template opportunity should include suggestion dict with required fields."""
        data = _get_health_issues(comp_client)
        tmpl_issues = [i for i in data["issues"] if i["type"] == "template_opportunity"]
        assert len(tmpl_issues) > 0

        for issue in tmpl_issues:
            assert "suggestion" in issue, \
                f"template_opportunity missing suggestion: {issue}"
            suggestion = issue["suggestion"]
            for field in ["suggested_name", "type", "attributes", "object_indices", "count", "attr_count"]:
                assert field in suggestion, \
                    f"suggestion missing field '{field}': {suggestion}"

    def test_suggestion_count_at_least_3(self, comp_client):
        """Template suggestions should have count >= 3."""
        data = _get_health_issues(comp_client)
        tmpl_issues = [i for i in data["issues"] if i["type"] == "template_opportunity"]
        for issue in tmpl_issues:
            assert issue["suggestion"]["count"] >= 3, f"Expected count >= 3, got {issue['suggestion']['count']}"  # noqa: PLR2004

    def test_template_opportunity_is_info(self, comp_client):
        """Template opportunity issues should be info severity."""
        data = _get_health_issues(comp_client)
        tmpl_issues = [i for i in data["issues"] if i["type"] == "template_opportunity"]
        for issue in tmpl_issues:
            assert issue["severity"] == "info"


class TestConstantsEndpoint:
    """Tests for /api/constants endpoint serving domain metadata."""

    def test_constants_returns_name_fields(self, health_client):
        """Endpoint should return name_fields with correct mappings."""
        resp = health_client.get("/api/constants")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        assert "name_fields" in data
        nf = data["name_fields"]
        assert nf["host"] == "host_name"
        assert nf["service"] == "service_description"
        assert nf["command"] == "command_name"

    def test_constants_returns_required_fields(self, health_client):
        """Endpoint should return required_fields with OR conditions as lists."""
        resp = health_client.get("/api/constants")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        assert "required_fields" in data
        rf = data["required_fields"]

        # host should have host_name and address as simple strings
        assert "host_name" in rf["host"]
        assert "address" in rf["host"]

        # host should have at least one OR condition (list within list)
        or_conditions = [r for r in rf["host"] if isinstance(r, list)]
        assert len(or_conditions) >= 1, \
            f"Expected at least one OR condition in host required_fields, got: {rf['host']}"

    def test_constants_returns_reference_fields(self, health_client):
        """Endpoint should return reference_fields with correct target types."""
        resp = health_client.get("/api/constants")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        assert "reference_fields" in data
        ref = data["reference_fields"]
        assert ref["check_command"] == "command"
        assert ref["host_name"] == "host"
        assert ref["use"] is None


# ============================================================
# Object References endpoint tests
# ============================================================

@pytest.fixture
def references_app():
    """Create Flask app with config designed for object-references tests.

    Objects:
    - command: check-host-alive
    - host template: generic-host (register=0, check_command=check-host-alive)
    - hostgroup: web-servers (members: web-01)
    - host: web-01 (use=generic-host, hostgroups=web-servers)
    - service: HTTP on web-01 (check_command=check-host-alive)
    - contact: admin-contact
    - contactgroup: admins (members: admin-contact)
    """
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
""")

    (test_config_path / "templates.cfg").write_text("""
define host {
    name                    generic-host
    register                0
    check_command           check-host-alive
    max_check_attempts      5
    contact_groups          admins
}
""")

    (test_config_path / "hostgroups.cfg").write_text("""
define hostgroup {
    hostgroup_name  web-servers
    alias           Web Servers
    members         web-01
}
""")

    (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       web-01
    alias           Web Server 01
    address         10.0.0.1
    use             generic-host
    hostgroups      web-servers
}
""")

    (test_config_path / "services.cfg").write_text("""
define service {
    host_name               web-01
    service_description     HTTP
    check_command           check-host-alive
    max_check_attempts      3
    contact_groups          admins
}
""")

    (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin-contact
    host_notification_commands      check-host-alive
    service_notification_commands   check-host-alive
    host_notification_period        24x7
    service_notification_period     24x7
}
""")

    (test_config_path / "contactgroups.cfg").write_text("""
define contactgroup {
    contactgroup_name   admins
    alias               Administrators
    members             admin-contact
}
""")

    (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24 Hours A Day
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
    sunday          00:00-24:00
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True
    yield app
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def ref_client(references_app):
    return references_app.test_client()


class TestObjectReferences:
    """Tests for /api/object-references/<global_index> endpoint."""

    def _find_index(self, client, object_type, name):
        """Find the global_index of an object by type and name."""
        resp = client.get("/api/objects")
        for obj in resp.json:
            if obj["object_type"] == object_type and obj.get("name") == name:
                return obj["global_index"]
        return None

    def test_host_outgoing_references(self, ref_client):
        """Host web-01 uses generic-host template -> outgoing reference to template."""
        idx = self._find_index(ref_client, "host", "web-01")
        assert idx is not None, "Could not find host web-01"

        resp = ref_client.get(f"/api/object-references/{idx}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        outgoing = data["outgoing"]
        # web-01 uses generic-host template, so there should be an outgoing ref via 'use'
        use_refs = [r for r in outgoing if r["field"] == "use"]
        assert len(use_refs) >= 1, \
            f"Expected outgoing 'use' reference to generic-host, got: {outgoing}"
        assert any(r["name"] == "generic-host" for r in use_refs), \
            f"Expected outgoing ref to 'generic-host', got: {use_refs}"

    def test_host_incoming_references(self, ref_client):
        """Host web-01 is referenced by services -> incoming references."""
        idx = self._find_index(ref_client, "host", "web-01")
        assert idx is not None, "Could not find host web-01"

        resp = ref_client.get(f"/api/object-references/{idx}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        incoming = data["incoming"]
        # The HTTP service references web-01 via host_name
        host_name_refs = [r for r in incoming if r["field"] == "host_name"]
        assert len(host_name_refs) >= 1, \
            f"Expected incoming host_name reference from HTTP service, got: {incoming}"

    def test_host_members(self, ref_client):
        """Host web-01 is member of hostgroup web-servers -> member_of."""
        idx = self._find_index(ref_client, "host", "web-01")
        assert idx is not None, "Could not find host web-01"

        resp = ref_client.get(f"/api/object-references/{idx}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        member_of = data["member_of"]
        hg_refs = [r for r in member_of if r["object_type"] == "hostgroup"]
        assert len(hg_refs) >= 1, \
            f"Expected web-01 to be member_of web-servers hostgroup, got: {member_of}"
        assert any(r["name"] == "web-servers" for r in hg_refs), \
            f"Expected member_of 'web-servers', got: {hg_refs}"

    def test_hostgroup_members(self, ref_client):
        """Hostgroup web-servers has web-01 as member -> members list."""
        idx = self._find_index(ref_client, "hostgroup", "web-servers")
        assert idx is not None, "Could not find hostgroup web-servers"

        resp = ref_client.get(f"/api/object-references/{idx}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        members = data["members"]
        host_members = [m for m in members if m["object_type"] == "host"]
        assert len(host_members) >= 1, \
            f"Expected web-01 in members of web-servers, got: {members}"
        assert any(m["name"] == "web-01" for m in host_members), \
            f"Expected 'web-01' in members, got: {host_members}"

    def test_command_incoming_references(self, ref_client):
        """Command check-host-alive is referenced by the template -> incoming."""
        idx = self._find_index(ref_client, "command", "check-host-alive")
        assert idx is not None, "Could not find command check-host-alive"

        resp = ref_client.get(f"/api/object-references/{idx}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        incoming = data["incoming"]
        # generic-host template uses check-host-alive as check_command
        check_cmd_refs = [r for r in incoming if r["field"] == "check_command"]
        assert len(check_cmd_refs) >= 1, \
            f"Expected incoming check_command reference from template, got: {incoming}"

    def test_parent_hosts_none_for_non_host(self, ref_client):
        """Non-host objects should have parent_hosts=None."""
        idx = self._find_index(ref_client, "command", "check-host-alive")
        assert idx is not None, "Could not find command check-host-alive"

        resp = ref_client.get(f"/api/object-references/{idx}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        assert data["parent_hosts"] is None, \
            f"Expected parent_hosts=None for command, got: {data['parent_hosts']}"

    def test_invalid_index_returns_404(self, ref_client):
        """Out-of-range global_index should return 404."""
        resp = ref_client.get("/api/object-references/99999")
        assert resp.status_code == 404  # noqa: PLR2004
