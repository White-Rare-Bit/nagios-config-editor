"""Tests for health check endpoint."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from app.file_operations import edit_object_in_file
from app.git_service import GitService
from app.nagios_model import REQUIRED_FIELDS
from app.stable_keys import generate_stable_key
from app.inheritance import build_template_lookup
from app.routes.health_checks import run_all_checks


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
    assert "nonexistent-cmd" in oncall_cmd_issues[0]["message"], \
        f"Expected 'nonexistent-cmd' in message, got: {oncall_cmd_issues[0]['message']}"


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


def test_health_check_exclusion_crosses_hostgroup_boundary():
    """!host in host_name should also exclude from hostgroup expansion (check 10)."""
    test_dir = tempfile.mkdtemp()
    try:
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "config.cfg").write_text("""
define host {
    host_name       web-01
    alias           Web 01
    address         10.0.0.1
    hostgroups      web-servers
}

define host {
    host_name       web-02
    alias           Web 02
    address         10.0.0.2
    hostgroups      web-servers
}

define hostgroup {
    hostgroup_name  web-servers
    alias           Web Servers
}

define service {
    host_name               !web-01
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

        # web-01 is excluded via !web-01, so it should be flagged as having no services
        assert "web-01" in flagged_hosts, \
            f"Expected 'web-01' flagged (excluded via !), got: {flagged_hosts}"

        # web-02 gets the service via hostgroup, should NOT be flagged
        assert "web-02" not in flagged_hosts, \
            "False positive: 'web-02' has services via hostgroup but was flagged"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_required_fields_host_only_requires_host_name():
    """REQUIRED_FIELDS for host should only require host_name per Nagios spec."""
    host_fields = REQUIRED_FIELDS.get("host", [])
    flat = []
    for f in host_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert "host_name" in flat
    # Per spec: address defaults to host_name, others can be inherited
    assert "address" not in flat
    assert "max_check_attempts" not in flat


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


def test_required_fields_contact_only_requires_contact_name():
    """REQUIRED_FIELDS for contact should only require contact_name per Nagios spec."""
    contact_fields = REQUIRED_FIELDS.get("contact", [])
    flat = []
    for f in contact_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert "contact_name" in flat
    assert len(flat) == 1, f"Only contact_name should be required, got: {contact_fields}"


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
    """Apply staging should include validation result."""
    test_dir = os.path.realpath(tempfile.mkdtemp())
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

        session_id = "test-session"
        headers = {"X-Session-Id": session_id}

        # Get objects to find stable key
        resp = client.get("/api/objects")
        assert resp.status_code == 200  # noqa: PLR2004
        objects = resp.json
        assert len(objects) > 0
        obj = objects[0]
        name = obj.get("display_name") or obj.get("name") or ""
        stable_key = f"{obj['source_file']}|{obj['object_type']}|{name}"

        # Edit via shadow copy API
        resp = client.post("/api/objects/update", json={
            "stable_key": stable_key,
            "attributes": {**obj["attributes"], "alias": "Modified"},
        }, headers=headers)
        assert resp.status_code == 200  # noqa: PLR2004

        # Apply
        resp = client.post("/api/staging/apply")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        # Response should include a validation field
        assert "validation" in data, \
            f"Response should include 'validation', got keys: {list(data.keys())}"
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

        # Services with same description on different hostgroups — NOT duplicates
        (test_config_path / "services.cfg").write_text("""
define service {
    hostgroup_name        linux-hosts
    service_description   CPU Load
    check_command         check-host-alive
}

define service {
    hostgroup_name        windows-hosts
    service_description   CPU Load
    check_command         check-host-alive
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

    def test_services_on_different_hosts_not_duplicate(self, app_with_duplicates):
        """Services with same description on different hostgroups are NOT duplicates."""
        client = app_with_duplicates.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        dup_issues = [i for i in data["issues"]
                      if i["type"] == "duplicate"]
        flagged = [(i["object_type"], i["object"]) for i in dup_issues]

        assert not any(t == "service" for t, _ in flagged), \
            f"False positive: services with same name on different hosts flagged as duplicate: {flagged}"


def test_service_retry_interval_zero_flagged():
    """Service with retry_interval=0 should be flagged (Nagios requires > 0 for services)."""
    test_dir = tempfile.mkdtemp()
    try:
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "config.cfg").write_text("""
define host {
    host_name       web-01
    alias           Web 01
    address         10.0.0.1
    retry_interval  0
}

define service {
    host_name               web-01
    service_description     HTTP
    check_command           check_http
    retry_interval          0
}

define service {
    host_name               web-01
    service_description     PING
    check_command           check_http
    retry_interval          5
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
        data = resp.get_json()

        retry_issues = [i for i in data["issues"]
                        if i["type"] == "invalid_retry_interval"]

        # Service with retry_interval=0 should be flagged
        assert len(retry_issues) == 1, \
            f"Expected 1 retry_interval issue (service only), got {len(retry_issues)}: {retry_issues}"
        assert retry_issues[0]["object_type"] == "service"

        # Host with retry_interval=0 should NOT be flagged
        host_retry_issues = [i for i in retry_issues if i["object_type"] == "host"]
        assert len(host_retry_issues) == 0, \
            "Host retry_interval=0 should not be flagged"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


class TestDuplicateSeverityByType:
    """Duplicate services are warnings (first definition wins), hosts remain errors."""

    @pytest.fixture
    def app_with_dup_services(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       dup-host
    alias           First
    address         10.0.0.1
}

define host {
    host_name       dup-host
    alias           Second
    address         10.0.0.2
}

define host {
    host_name       web-01
    alias           Web
    address         10.0.0.3
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               web-01
    service_description     HTTP
    check_command           check_http
}

define service {
    host_name               web-01
    service_description     HTTP
    check_command           check_http
}
""")

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_http
    command_line    /usr/lib/nagios/plugins/check_http -H $HOSTADDRESS$
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_duplicate_service_is_warning(self, app_with_dup_services):
        """Duplicate service definitions should be warnings, not errors."""
        client = app_with_dup_services.test_client()
        resp = client.get("/api/health-check")
        data = resp.get_json()

        dup_service_issues = [i for i in data["issues"]
                              if i["type"] == "duplicate" and i["object_type"] == "service"]
        assert len(dup_service_issues) > 0, "Expected duplicate service issues"
        for issue in dup_service_issues:
            assert issue["severity"] == "warning", \
                f"Duplicate service should be warning, got {issue['severity']}"
            assert "first definition wins" in issue["message"]

    def test_duplicate_host_is_error(self, app_with_dup_services):
        """Duplicate host definitions should remain errors."""
        client = app_with_dup_services.test_client()
        resp = client.get("/api/health-check")
        data = resp.get_json()

        dup_host_issues = [i for i in data["issues"]
                           if i["type"] == "duplicate" and i["object_type"] == "host"]
        assert len(dup_host_issues) > 0, "Expected duplicate host issues"
        for issue in dup_host_issues:
            assert issue["severity"] == "error", \
                f"Duplicate host should be error, got {issue['severity']}"


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
            for field in ["suggested_name", "type", "attributes", "object_keys", "count", "attr_count"]:
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
    """Tests for /api/object-references?key=<stable_key> endpoint."""

    def _find_stable_key(self, client, object_type, name):
        """Find the stable key of an object by type and name."""
        resp = client.get("/api/objects")
        for obj in resp.json:
            if obj["object_type"] == object_type and obj.get("name") == name:
                return generate_stable_key(
                    obj["source_file"], obj["object_type"], obj["display_name"]
                )
        return None

    def test_host_outgoing_references(self, ref_client):
        """Host web-01 uses generic-host template -> outgoing reference to template."""
        key = self._find_stable_key(ref_client, "host", "web-01")
        assert key is not None, "Could not find host web-01"

        resp = ref_client.get(f"/api/object-references?key={key}")
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
        key = self._find_stable_key(ref_client, "host", "web-01")
        assert key is not None, "Could not find host web-01"

        resp = ref_client.get(f"/api/object-references?key={key}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        incoming = data["incoming"]
        # The HTTP service references web-01 via host_name
        host_name_refs = [r for r in incoming if r["field"] == "host_name"]
        assert len(host_name_refs) >= 1, \
            f"Expected incoming host_name reference from HTTP service, got: {incoming}"

    def test_host_members(self, ref_client):
        """Host web-01 is member of hostgroup web-servers -> member_of."""
        key = self._find_stable_key(ref_client, "host", "web-01")
        assert key is not None, "Could not find host web-01"

        resp = ref_client.get(f"/api/object-references?key={key}")
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
        key = self._find_stable_key(ref_client, "hostgroup", "web-servers")
        assert key is not None, "Could not find hostgroup web-servers"

        resp = ref_client.get(f"/api/object-references?key={key}")
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
        key = self._find_stable_key(ref_client, "command", "check-host-alive")
        assert key is not None, "Could not find command check-host-alive"

        resp = ref_client.get(f"/api/object-references?key={key}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        incoming = data["incoming"]
        # generic-host template uses check-host-alive as check_command
        check_cmd_refs = [r for r in incoming if r["field"] == "check_command"]
        assert len(check_cmd_refs) >= 1, \
            f"Expected incoming check_command reference from template, got: {incoming}"

    def test_parent_hosts_none_for_non_host(self, ref_client):
        """Non-host objects should have parent_hosts=None."""
        key = self._find_stable_key(ref_client, "command", "check-host-alive")
        assert key is not None, "Could not find command check-host-alive"

        resp = ref_client.get(f"/api/object-references?key={key}")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.json

        assert data["parent_hosts"] is None, \
            f"Expected parent_hosts=None for command, got: {data['parent_hosts']}"

    def test_invalid_key_returns_404(self, ref_client):
        """Non-existent stable key should return 404."""
        resp = ref_client.get("/api/object-references?key=nonexistent.cfg|host|fake")
        assert resp.status_code == 404  # noqa: PLR2004

    def test_missing_key_returns_400(self, ref_client):
        """Missing key parameter should return 400."""
        resp = ref_client.get("/api/object-references")
        assert resp.status_code == 400  # noqa: PLR2004


# ============================================================
# Issue #5: Duplicate dependency semantic comparison
# ============================================================

class TestDuplicateDependencySemantics:
    """Test that reordered CSV values in dependencies are detected as duplicates."""

    @pytest.fixture
    def app_with_deps(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   hostA
    alias       Host A
    address     10.0.0.1
}

define host {
    host_name   hostB
    alias       Host B
    address     10.0.0.2
}

define host {
    host_name   hostC
    alias       Host C
    address     10.0.0.3
}
""")

        (test_config_path / "deps.cfg").write_text("""
define hostdependency {
    dependent_host_name   hostA
    host_name             hostB,hostC
}

define hostdependency {
    dependent_host_name   hostA
    host_name             hostC,hostB
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

    def test_reordered_csv_detected_as_duplicate(self, app_with_deps):
        """Dependencies with host_name=A,B and host_name=B,A should be detected as duplicates."""
        client = app_with_deps.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        dup_dep_issues = [i for i in data["issues"] if i["type"] == "duplicate_dependency"]
        assert len(dup_dep_issues) >= 1, \
            f"Expected at least 1 duplicate_dependency, got: {dup_dep_issues}"

    def test_different_hosts_not_flagged(self, app_with_deps):
        """Dependencies with different actual host sets should NOT be flagged."""
        client = app_with_deps.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        # Only the reordered pair should be flagged, not false positives
        dup_dep_issues = [i for i in data["issues"] if i["type"] == "duplicate_dependency"]
        assert len(dup_dep_issues) <= 1, \
            f"Too many duplicate_dependency issues, possible false positive: {dup_dep_issues}"


# ============================================================
# Issue #9: Wildcard handling in health checks
# ============================================================

class TestWildcardHandling:
    """Test that * wildcards in CSV lists are not flagged as missing references."""

    @pytest.fixture
    def app_with_wildcards(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   real-host
    alias       Real Host
    address     10.0.0.1
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-host-by-email
    service_notification_commands   notify-service-by-email
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name             *,!real-host
    service_description   Wildcard Service
    check_command         check-host-alive
    contacts              *
}

define service {
    host_name             real-host
    service_description   Normal Service
    check_command         check-host-alive
    contacts              admin
}
""")

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
define command {
    command_name    notify-host-by-email
    command_line    /usr/bin/printf "%b" "Host alert"
}
define command {
    command_name    notify-service-by-email
    command_line    /usr/bin/printf "%b" "Service alert"
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

    def test_wildcard_in_csv_not_flagged_as_orphan(self, app_with_wildcards):
        """Service with host_name '*,!host2' should NOT flag * as orphan."""
        client = app_with_wildcards.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        orphan_issues = [i for i in data["issues"] if i["type"] == "orphan_service"]
        orphan_messages = [i["message"] for i in orphan_issues]
        assert not any("*" in msg for msg in orphan_messages), \
            f"Wildcard * should not be flagged as orphan service: {orphan_messages}"

    def test_wildcard_contacts_not_flagged_as_missing(self, app_with_wildcards):
        """Object with contacts '*' should NOT flag * as a missing contact."""
        client = app_with_wildcards.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        missing_contact_issues = [i for i in data["issues"] if i["type"] == "missing_contact"]
        missing_messages = [i["message"] for i in missing_contact_issues]
        assert not any("*" in msg for msg in missing_messages), \
            f"Wildcard * should not be flagged as missing contact: {missing_messages}"


# ============================================================
# Issue #3: Required field validation through inheritance
# ============================================================

class TestRequiredFieldInheritance:
    """Test that required fields are validated through inheritance chains."""

    @pytest.fixture
    def app_with_templates(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "templates.cfg").write_text("""
define host {
    name                    good-template
    register                0
    address                 10.0.0.1
    contact_groups          admins
    max_check_attempts      5
}

define host {
    name                    empty-template
    register                0
}
""")

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       good-host
    use             good-template
    alias           Good Host
}

define host {
    host_name       bad-host
    use             empty-template
    alias           Bad Host
}
""")

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      check-host-alive
    service_notification_commands   check-host-alive
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}
""")

        (test_config_path / "contactgroups.cfg").write_text("""
define contactgroup {
    contactgroup_name   admins
    alias               Admins
    members             admin
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

    def test_required_field_resolved_through_inheritance(self, app_with_templates):
        """Host inheriting address + contact_groups from template should NOT be flagged."""
        client = app_with_templates.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        missing_req = [
            i for i in data["issues"]
            if i["type"] == "missing_required_field" and i["object"] == "good-host"
        ]
        assert len(missing_req) == 0, \
            f"good-host should have no missing required fields (inherited from template): {missing_req}"

    def test_required_field_missing_despite_template(self, app_with_templates):
        """Host inheriting from empty template should only be flagged for truly missing required fields."""
        client = app_with_templates.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        missing_req = [
            i for i in data["issues"]
            if i["type"] == "missing_required_field" and i["object"] == "bad-host"
        ]
        # Per spec, only host_name is required; address defaults to host_name,
        # max_check_attempts and contacts can be inherited
        # bad-host has host_name defined, so no required field should be missing
        assert len(missing_req) == 0, \
            f"bad-host with host_name should have no missing required fields per spec, got: {missing_req}"

    def test_or_group_satisfied_by_one(self, app_with_templates):
        """Host with contact_groups but no contacts should NOT be flagged for contacts OR-group."""
        client = app_with_templates.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        # good-host has contact_groups via template, no contacts directly
        missing_req = [
            i for i in data["issues"]
            if i["type"] == "missing_required_field"
            and i["object"] == "good-host"
            and ("contacts" in i["message"] or "contact_groups" in i["message"])
        ]
        assert len(missing_req) == 0, \
            f"good-host should satisfy contacts OR-group via contact_groups: {missing_req}"


# ============================================================
# Issue #18: Old inheritance API error reporting
# ============================================================

class TestInheritanceApiErrors:
    """Test that the inheritance chain API reports template errors."""

    @pytest.fixture
    def app_with_missing_template(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   broken-host
    use         nonexistent-template
    alias       Broken Host
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
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_old_inheritance_api_reports_errors(self, app_with_missing_template):
        """Chain with missing template should include errors in response."""
        client = app_with_missing_template.test_client()
        resp = client.get("/api/inheritance/host/broken-host")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        assert "errors" in data, f"Expected 'errors' in response, got keys: {list(data.keys())}"
        assert len(data["errors"]) > 0, "Expected at least one error for missing template"
        assert any("nonexistent-template" in e for e in data["errors"]), \
            f"Expected error mentioning 'nonexistent-template', got: {data['errors']}"


# ============================================================
# Issue #6: Services bound to empty hostgroups
# ============================================================

class TestServiceOnEmptyHostgroup:
    """Test detection of services bound to hostgroups with no members."""

    @pytest.fixture
    def app_with_empty_hg(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hostgroups.cfg").write_text("""
define hostgroup {
    hostgroup_name  empty-group
    alias           Empty Group
}

define hostgroup {
    hostgroup_name  populated-group
    alias           Populated Group
    members         real-host
}
""")

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   real-host
    alias       Real Host
    address     10.0.0.1
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    hostgroup_name        empty-group
    service_description   Service on Empty
    check_command         check-host-alive
}

define service {
    hostgroup_name        populated-group
    service_description   Service on Populated
    check_command         check-host-alive
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

    def test_service_on_empty_hostgroup_flagged(self, app_with_empty_hg):
        """Service bound to empty-group should be flagged."""
        client = app_with_empty_hg.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        empty_hg_issues = [i for i in data["issues"] if i["type"] == "service_on_empty_hostgroup"]
        assert len(empty_hg_issues) >= 1, \
            f"Expected at least 1 service_on_empty_hostgroup issue, got {len(empty_hg_issues)}"
        assert any("empty-group" in i["message"] for i in empty_hg_issues)

    def test_service_on_populated_hostgroup_not_flagged(self, app_with_empty_hg):
        """Service bound to populated-group should NOT be flagged."""
        client = app_with_empty_hg.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        empty_hg_issues = [i for i in data["issues"] if i["type"] == "service_on_empty_hostgroup"]
        assert not any("populated-group" in i["message"] for i in empty_hg_issues), \
            f"populated-group should not be flagged: {empty_hg_issues}"


# ============================================================
# Issue #7: Redundant escalation contacts
# ============================================================

class TestRedundantEscalationContacts:
    """Test detection of escalation contacts that match base contacts."""

    @pytest.fixture
    def app_with_escalations(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-host
    service_notification_commands   notify-svc
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}

define contact {
    contact_name                    oncall
    host_notification_commands      notify-host
    service_notification_commands   notify-svc
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}
""")

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   esc-host
    alias       Escalation Host
    address     10.0.0.1
    contacts    admin,oncall
}
""")

        (test_config_path / "escalations.cfg").write_text("""
define hostescalation {
    host_name           esc-host
    contacts            admin
    first_notification  2
    last_notification   5
}
""")

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
define command {
    command_name    notify-host
    command_line    /usr/bin/true
}
define command {
    command_name    notify-svc
    command_line    /usr/bin/true
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

    def test_redundant_escalation_flagged(self, app_with_escalations):
        """Escalation with contacts subset of base should be flagged."""
        client = app_with_escalations.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        redundant = [i for i in data["issues"] if i["type"] == "redundant_escalation_contacts"]
        assert len(redundant) >= 1, \
            f"Expected at least 1 redundant_escalation_contacts issue, got {len(redundant)}"

    def test_redundant_escalation_is_info(self, app_with_escalations):
        """Redundant escalation contacts should be info severity."""
        client = app_with_escalations.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        redundant = [i for i in data["issues"] if i["type"] == "redundant_escalation_contacts"]
        for issue in redundant:
            assert issue["severity"] == "info"


# ============================================================
# Issue #14: Escalation coverage gaps
# ============================================================

class TestEscalationCoverageGaps:
    """Test detection of gaps in escalation notification ranges."""

    @pytest.fixture
    def app_with_gap(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   gap-host
    alias       Gap Host
    address     10.0.0.1
    contacts    admin
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-host
    service_notification_commands   notify-host
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}
""")

        (test_config_path / "escalations.cfg").write_text("""
define hostescalation {
    host_name           gap-host
    contacts            admin
    first_notification  1
    last_notification   3
}

define hostescalation {
    host_name           gap-host
    contacts            admin
    first_notification  8
    last_notification   0
}
""")

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
define command {
    command_name    notify-host
    command_line    /usr/bin/true
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

    def test_escalation_gap_detected(self, app_with_gap):
        """Gap between notification 3 and 8 should be flagged."""
        client = app_with_gap.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        gap_issues = [i for i in data["issues"] if i["type"] == "escalation_coverage_gap"]
        assert len(gap_issues) >= 1, \
            f"Expected at least 1 escalation_coverage_gap, got {len(gap_issues)}"

    def test_contiguous_escalation_no_gap(self):
        """Contiguous escalations should NOT be flagged."""
        test_dir = tempfile.mkdtemp()
        try:
            test_config_path = Path(test_dir) / "nagios"
            test_config_path.mkdir()

            (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   ok-host
    alias       OK Host
    address     10.0.0.1
    contacts    admin
}
""")

            (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-host
    service_notification_commands   notify-host
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}
""")

            (test_config_path / "escalations.cfg").write_text("""
define hostescalation {
    host_name           ok-host
    contacts            admin
    first_notification  1
    last_notification   3
}

define hostescalation {
    host_name           ok-host
    contacts            admin
    first_notification  4
    last_notification   0
}
""")

            (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
define command {
    command_name    notify-host
    command_line    /usr/bin/true
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
            resp = client.get("/api/health-check")
            assert resp.status_code == 200  # noqa: PLR2004
            data = resp.get_json()

            gap_issues = [i for i in data["issues"] if i["type"] == "escalation_coverage_gap"]
            assert len(gap_issues) == 0, \
                f"Contiguous escalations should have no gaps: {gap_issues}"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================
# Issue #16: Notification period vs criticality mismatch
# ============================================================

class TestNotificationPeriodCriticality:
    """Test detection of critical services with non-24x7 notification periods."""

    @pytest.fixture
    def app_with_critical_service(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   crit-host
    alias       Critical Host
    address     10.0.0.1
    contacts    admin
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-host
    service_notification_commands   notify-host
    host_notification_period        24x7
    service_notification_period     24x7
    host_notification_options       d,u,r
    service_notification_options    w,u,c,r
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               crit-host
    service_description     Critical SVC
    check_command           check-host-alive
    check_interval          1
    max_check_attempts      2
    notification_period     workhours
    contacts                admin
}

define service {
    host_name               crit-host
    service_description     Normal SVC
    check_command           check-host-alive
    check_interval          10
    max_check_attempts      5
    notification_period     workhours
    contacts                admin
}
""")

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
define command {
    command_name    notify-host
    command_line    /usr/bin/true
}
""")

        (test_config_path / "timeperiods.cfg").write_text("""
define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    monday          00:00-24:00
}

define timeperiod {
    timeperiod_name workhours
    alias           Work Hours
    monday          09:00-17:00
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_critical_service_non_24x7_flagged(self, app_with_critical_service):
        """Critical service (low interval + low attempts) with workhours should be flagged."""
        client = app_with_critical_service.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        mismatch = [i for i in data["issues"] if i["type"] == "notification_period_mismatch"]
        flagged_names = [i["object"] for i in mismatch]
        assert any("Critical SVC" in name for name in flagged_names), \
            f"Expected Critical SVC flagged, got: {flagged_names}"

    def test_normal_service_non_24x7_not_flagged(self, app_with_critical_service):
        """Normal service (high interval + high attempts) with workhours should NOT be flagged."""
        client = app_with_critical_service.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        mismatch = [i for i in data["issues"] if i["type"] == "notification_period_mismatch"]
        flagged_names = [i["object"] for i in mismatch]
        assert not any("Normal SVC" in name for name in flagged_names), \
            f"Normal SVC should not be flagged: {flagged_names}"


# ============================================================
# Issue #10: Host reachability SPOF
# ============================================================

class TestHostReachability:
    """Test detection of single-point-of-failure parent hosts."""

    @pytest.fixture
    def app_with_spof(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   router1
    alias       Router 1
    address     10.0.0.1
}

define host {
    host_name   child1
    alias       Child 1
    address     10.0.0.2
    parents     router1
}

define host {
    host_name   child2
    alias       Child 2
    address     10.0.0.3
    parents     router1
}

define host {
    host_name   child3
    alias       Child 3
    address     10.0.0.4
    parents     router1
}

define host {
    host_name   dual-parent-child
    alias       Dual Parent Child
    address     10.0.0.5
    parents     router1,child1
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

    def test_spof_detected(self, app_with_spof):
        """router1 is sole parent for 3+ hosts — should be flagged as SPOF."""
        client = app_with_spof.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        spof_issues = [i for i in data["issues"] if i["type"] == "reachability_spof"]
        assert len(spof_issues) >= 1, \
            f"Expected at least 1 reachability_spof, got {len(spof_issues)}"
        assert any("router1" in i["object"] for i in spof_issues)

    def test_non_sole_parent_not_flagged(self, app_with_spof):
        """child1 is a parent for dual-parent-child but not sole, and has <3 children — should NOT be SPOF."""
        client = app_with_spof.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        spof_issues = [i for i in data["issues"] if i["type"] == "reachability_spof"]
        assert not any("child1" == i["object"] for i in spof_issues), \
            f"child1 should not be SPOF: {spof_issues}"


# ============================================================
# Issue #15: Dependency period mismatch
# ============================================================

class TestDependencyPeriodMismatch:
    """Test detection of dependency_period vs check_period mismatches."""

    @pytest.fixture
    def app_with_dep_period(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   dep-host
    alias       Dep Host
    address     10.0.0.1
    check_period workhours
}

define host {
    host_name   master-host
    alias       Master Host
    address     10.0.0.2
}
""")

        (test_config_path / "deps.cfg").write_text("""
define hostdependency {
    dependent_host_name   dep-host
    host_name             master-host
    dependency_period     nighthours
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
    timeperiod_name workhours
    alias           Work Hours
    monday          09:00-17:00
}

define timeperiod {
    timeperiod_name nighthours
    alias           Night Hours
    monday          17:00-09:00
}

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

    def test_dependency_period_mismatch_flagged(self, app_with_dep_period):
        """dependency_period=nighthours vs check_period=workhours should be flagged."""
        client = app_with_dep_period.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        mismatch = [i for i in data["issues"] if i["type"] == "dependency_period_mismatch"]
        assert len(mismatch) >= 1, \
            f"Expected at least 1 dependency_period_mismatch, got {len(mismatch)}"

    def test_matching_periods_not_flagged(self):
        """dependency_period matching check_period should NOT be flagged."""
        test_dir = tempfile.mkdtemp()
        try:
            test_config_path = Path(test_dir) / "nagios"
            test_config_path.mkdir()

            (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   dep-host
    alias       Dep Host
    address     10.0.0.1
    check_period workhours
}

define host {
    host_name   master-host
    alias       Master Host
    address     10.0.0.2
}
""")

            (test_config_path / "deps.cfg").write_text("""
define hostdependency {
    dependent_host_name   dep-host
    host_name             master-host
    dependency_period     workhours
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
    timeperiod_name workhours
    alias           Work Hours
    monday          09:00-17:00
}

define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    monday          00:00-24:00
}
""")

            app = create_app(config_path=str(test_config_path))
            app.config["TESTING"] = True
            client = app.test_client()
            resp = client.get("/api/health-check")
            assert resp.status_code == 200  # noqa: PLR2004
            data = resp.get_json()

            mismatch = [i for i in data["issues"] if i["type"] == "dependency_period_mismatch"]
            assert len(mismatch) == 0, \
                f"Matching periods should not be flagged: {mismatch}"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================
# Issue #25: Inheritance depth warnings
# ============================================================

class TestInheritanceDepth:
    """Test detection of deep inheritance chains."""

    def test_deep_chain_flagged(self):
        """Inheritance chain deeper than 5 should be flagged."""
        test_dir = tempfile.mkdtemp()
        try:
            test_config_path = Path(test_dir) / "nagios"
            test_config_path.mkdir()

            # Create a chain 7 deep: t1 -> t2 -> ... -> t6 -> concrete
            templates = []
            for i in range(1, 7):
                use_line = f"    use             tmpl-{i - 1}" if i > 1 else ""
                templates.append(f"""
define host {{
    name            tmpl-{i}
    register        0
    check_command   check-host-alive
{use_line}
}}""")

            (test_config_path / "templates.cfg").write_text("\n".join(templates))

            (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   deep-host
    use         tmpl-6
    alias       Deep Host
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
            resp = client.get("/api/health-check")
            assert resp.status_code == 200  # noqa: PLR2004
            data = resp.get_json()

            deep_issues = [i for i in data["issues"] if i["type"] == "deep_inheritance"]
            assert len(deep_issues) >= 1, \
                f"Expected at least 1 deep_inheritance issue, got {len(deep_issues)}"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_shallow_chain_not_flagged(self):
        """Inheritance chain of 2-3 should NOT be flagged."""
        test_dir = tempfile.mkdtemp()
        try:
            test_config_path = Path(test_dir) / "nagios"
            test_config_path.mkdir()

            (test_config_path / "templates.cfg").write_text("""
define host {
    name            base-tmpl
    register        0
    check_command   check-host-alive
}

define host {
    name            child-tmpl
    use             base-tmpl
    register        0
}
""")

            (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name   shallow-host
    use         child-tmpl
    alias       Shallow Host
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
            resp = client.get("/api/health-check")
            assert resp.status_code == 200  # noqa: PLR2004
            data = resp.get_json()

            deep_issues = [i for i in data["issues"] if i["type"] == "deep_inheritance"]
            assert len(deep_issues) == 0, \
                f"Shallow chain should not be flagged: {deep_issues}"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


class TestCfgDirCoverage:
    """Test check_cfg_dir_coverage flags directories not in nagios.cfg cfg_dir."""

    @pytest.fixture
    def cfg_dir_app(self):
        """Config with two directories but nagios.cfg only listing one."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        # Create two subdirectories with .cfg files
        covered = test_config_path / "covered"
        covered.mkdir()
        uncovered = test_config_path / "uncovered"
        uncovered.mkdir()

        (covered / "hosts.cfg").write_text("""
define host {
    host_name       test-host
    address         10.0.0.1
    max_check_attempts 5
    contact_groups  admins
}
""")

        (uncovered / "services.cfg").write_text("""
define service {
    host_name           test-host
    service_description Uncovered Service
    check_command       check_http
    max_check_attempts  3
    contact_groups      admins
}
""")

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_http
    command_line    /usr/lib/nagios/plugins/check_http -H $HOSTADDRESS$
}
define command {
    command_name    notify-host-by-email
    command_line    /usr/bin/printf "%b" "Host alert"
}
define command {
    command_name    notify-by-email
    command_line    /usr/bin/printf "%b" "Service alert"
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-host-by-email
    service_notification_commands   notify-by-email
    host_notification_period        24x7
    service_notification_period     24x7
}
define contactgroup {
    contactgroup_name   admins
    members             admin
}
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
""")

        # nagios.cfg only lists the covered directory
        (test_config_path / "nagios.cfg").write_text(
            f"cfg_dir={covered}\n"
            f"cfg_file={test_config_path / 'commands.cfg'}\n"
            f"cfg_file={test_config_path / 'contacts.cfg'}\n"
        )

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        # Point nagios_cfg at our test nagios.cfg
        app.extensions["server_config"].paths.nagios_cfg = str(
            test_config_path / "nagios.cfg"
        )
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_cfg_dir_coverage_flags_uncovered_directory(self, cfg_dir_app):
        """Directory not listed in cfg_dir should be flagged."""
        client = cfg_dir_app.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        cfg_issues = [i for i in data["issues"] if i["type"] == "cfg_dir_gap"]
        flagged_dirs = [i["file"] for i in cfg_issues]
        # The "uncovered" directory should be flagged
        assert any(d.endswith("/uncovered") for d in flagged_dirs), \
            f"Expected 'uncovered' dir flagged, got: {flagged_dirs}"
        # The "covered" directory should NOT be flagged
        assert not any(d.endswith("/covered") for d in flagged_dirs), \
            f"'covered' dir should not be flagged, got: {flagged_dirs}"


class TestUndefinedMacros:
    """Test check_undefined_macros flags $USERn$ not in resource.cfg."""

    @pytest.fixture
    def macro_app(self):
        """Config with commands using $USER1$ and $USER2$, only $USER1$ defined."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}
define command {
    command_name    check_custom
    command_line    $USER2$/check_custom -H $HOSTADDRESS$
}
define command {
    command_name    notify-host-by-email
    command_line    /usr/bin/printf "%b" "Host alert"
}
define command {
    command_name    notify-by-email
    command_line    /usr/bin/printf "%b" "Service alert"
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

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name           test-host
    service_description HTTP
    check_command       check_http
    max_check_attempts  3
    contact_groups      admins
}
""")

        (test_config_path / "contacts.cfg").write_text("""
define contact {
    contact_name                    admin
    host_notification_commands      notify-host-by-email
    service_notification_commands   notify-by-email
    host_notification_period        24x7
    service_notification_period     24x7
}
define contactgroup {
    contactgroup_name   admins
    members             admin
}
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
""")

        # resource.cfg only defines $USER1$
        resource_path = test_config_path / "resource.cfg"
        resource_path.write_text("$USER1$=/usr/lib/nagios/plugins\n")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        app.extensions["server_config"].paths.resource_cfg = str(resource_path)
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_defined_macro_not_flagged(self, macro_app):
        """$USER1$ is defined in resource.cfg and should not be flagged."""
        client = macro_app.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        macro_issues = [i for i in data["issues"] if i["type"] == "undefined_macro"]
        flagged_macros = [i["message"] for i in macro_issues]
        assert not any("$USER1$" in m for m in flagged_macros)

    def test_undefined_macro_flagged(self, macro_app):
        """$USER2$ is NOT defined in resource.cfg and should be flagged."""
        client = macro_app.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        macro_issues = [i for i in data["issues"] if i["type"] == "undefined_macro"]
        flagged_macros = [i["message"] for i in macro_issues]
        assert any("$USER2$" in m for m in flagged_macros)


class TestImpliedInheritanceHealthChecks:
    """Test that health checks use implied inheritance for contact resolution."""

    @pytest.fixture
    def app_service_inherits_contacts_from_host(self):
        """Config where a service has no contacts but its host does (implied inheritance)."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_ping
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
    alias           24x7
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
    sunday          00:00-24:00
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

        # Host has contacts; service does not (should inherit via implied inheritance)
        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       web-server
    alias           Web Server
    address         10.0.0.1
    contacts        admin
    check_command   check_ping
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               web-server
    service_description     HTTP
    check_command           check_ping
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_service_inheriting_contacts_from_host_not_flagged(self, app_service_inherits_contacts_from_host):
        """Service with no contacts that inherits from host should NOT be flagged."""
        client = app_service_inherits_contacts_from_host.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        missing_contact_issues = [i for i in data["issues"]
                                  if i["type"] == "missing_contacts"]
        flagged_names = [i["object"] for i in missing_contact_issues]

        # The HTTP service should NOT be flagged because it inherits contacts from web-server host
        assert "HTTP" not in flagged_names, \
            f"False positive: service 'HTTP' inherits contacts from host but was flagged. Issues: {missing_contact_issues}"

    @pytest.fixture
    def app_service_null_cancels_contacts(self):
        """Config where a service explicitly cancels inherited contacts with null."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_ping
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
    alias           24x7
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
    sunday          00:00-24:00
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

        # Host has contacts, but service template cancels them with null
        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       web-server
    alias           Web Server
    address         10.0.0.1
    contacts        admin
    check_command   check_ping
}
""")

        (test_config_path / "templates.cfg").write_text("""
define service {
    name                    no-contacts-template
    register                0
    contacts                null
    contact_groups          null
}
""")

        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               web-server
    service_description     Nullified Contacts
    check_command           check_ping
    use                     no-contacts-template
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_service_with_null_contacts_still_inherits_from_host(self, app_service_null_cancels_contacts):
        """Service with 'contacts null' template still gets implied inheritance from host."""
        client = app_service_null_cancels_contacts.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        missing_contact_issues = [i for i in data["issues"]
                                  if i["type"] == "missing_contacts"]
        flagged_names = [i["object"] for i in missing_contact_issues]

        # null cancels template inheritance but not implied inheritance from host.
        # Since the host has contacts, the service should NOT be flagged.
        assert "Nullified Contacts" not in flagged_names, \
            f"False positive: 'Nullified Contacts' still inherits contacts from host via implied inheritance"

    @pytest.fixture
    def app_service_no_contacts_anywhere(self):
        """Config where neither service nor host has contacts."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / "nagios"
        test_config_path.mkdir()

        (test_config_path / "commands.cfg").write_text("""
define command {
    command_name    check_ping
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

        # Host has NO contacts
        (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       bare-host
    alias           No Contacts Host
    address         10.0.0.1
    check_command   check_ping
}
""")

        # Service has NO contacts either
        (test_config_path / "services.cfg").write_text("""
define service {
    host_name               bare-host
    service_description     No Contacts Service
    check_command           check_ping
}
""")

        app = create_app(config_path=str(test_config_path))
        app.config["TESTING"] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_service_and_host_both_without_contacts_flagged(self, app_service_no_contacts_anywhere):
        """Service with no contacts whose host also has no contacts SHOULD be flagged."""
        client = app_service_no_contacts_anywhere.test_client()
        resp = client.get("/api/health-check")
        assert resp.status_code == 200  # noqa: PLR2004
        data = resp.get_json()

        missing_contact_issues = [i for i in data["issues"]
                                  if i["type"] == "missing_contacts"]
        flagged_names = [i["object"] for i in missing_contact_issues]

        # Both host and service should be flagged since neither has contacts
        assert "No Contacts Service" in flagged_names, \
            f"Expected 'No Contacts Service' to be flagged, got: {flagged_names}"
        assert "bare-host" in flagged_names, \
            f"Expected 'bare-host' to be flagged, got: {flagged_names}"


def test_template_without_register_0_not_flagged(tmp_path):
    """Templates with 'name' but no register=0 should not be flagged as hosts without services."""
    test_config_path = tmp_path / "nagios"
    test_config_path.mkdir()
    (test_config_path / "templates.cfg").write_text("""
define host {
    name                    generic-host
    check_command           check-host-alive
    notification_period     24x7
    max_check_attempts      3
}

define host {
    host_name       web-01
    alias           Web Server 1
    address         192.168.1.1
    use             generic-host
}
""")
    (test_config_path / "services.cfg").write_text("""
define service {
    host_name               web-01
    service_description     PING
    check_command           check_ping
}
""")
    from app.nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(str(test_config_path))
    objects = parser.parse_all()

    obj_to_index = {id(obj): i for i, obj in enumerate(objects)}
    template_lookup = build_template_lookup(objects)
    issues = run_all_checks(objects, obj_to_index, template_lookup)

    # generic-host should NOT appear as "host without services"
    host_without_svc = [i for i in issues if i["type"] == "host_without_services"]
    assert not any(i["object"] == "generic-host" for i in host_without_svc), \
        "generic-host (template without register=0) should not be flagged"

    # generic-host should NOT appear as "missing template"
    missing_tmpl = [i for i in issues if i["type"] == "missing_template"]
    assert not any("generic-host" in i["message"] for i in missing_tmpl), \
        "generic-host should be recognized as a valid template"


def test_hostgroup_template_with_identity_field_not_flagged_as_missing(tmp_path):
    """Hostgroup templates with register 0 but hostgroup_name set should not
    be flagged as missing. Nagios adds all objects with identity fields to its
    lookup skiplists at parse time, regardless of register 0."""
    test_config_path = tmp_path / "nagios"
    test_config_path.mkdir()
    (test_config_path / "hostgroups.cfg").write_text("""
define hostgroup {
    hostgroup_name  customer-juniper
    alias           customer-juniper
    register        0
}
""")
    (test_config_path / "hosts.cfg").write_text("""
define host {
    host_name       custMVC01
    alias           custMVC01
    address         192.168.1.1
    hostgroups      +customer-juniper
}
""")
    from app.nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(str(test_config_path))
    objects = parser.parse_all()

    obj_to_index = {id(obj): i for i, obj in enumerate(objects)}
    template_lookup = build_template_lookup(objects)
    issues = run_all_checks(objects, obj_to_index, template_lookup)

    missing_hg = [i for i in issues if i["type"] == "missing_hostgroup"]
    assert not any("customer-juniper" in i["message"] for i in missing_hg), \
        "hostgroup template with hostgroup_name and register 0 should not be flagged as missing"


def test_host_inheriting_hostgroups_not_flagged_without_services(tmp_path):
    """A host that inherits hostgroups from its template should not be flagged
    as 'host without services' when services target those inherited hostgroups."""
    test_config_path = tmp_path / "nagios"
    test_config_path.mkdir()
    (test_config_path / "objects.cfg").write_text("""
define host {
    name                    24x7-oncall-host
    hostgroups              template_24x7-oncall-host
    register                0
}

define hostgroup {
    hostgroup_name  template_24x7-oncall-host
    alias           Template 24x7 Oncall Host
}

define host {
    host_name       customer.com
    alias           CUSTOMER NAME
    address         192.168.1.1
    check_command   check-host-alive
    use             24x7-oncall-host
}

define command {
    command_name    check-host-alive
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}

define command {
    command_name    check_ping
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}

define service {
    hostgroup_name          template_24x7-oncall-host
    service_description     PING
    check_command           check_ping
}
""")
    from app.nagios_parser import NagiosConfigParser
    parser = NagiosConfigParser(str(test_config_path))
    objects = parser.parse_all()

    obj_to_index = {id(obj): i for i, obj in enumerate(objects)}
    template_lookup = build_template_lookup(objects)
    issues = run_all_checks(objects, obj_to_index, template_lookup)

    host_no_svc = [i for i in issues if i["type"] == "host_without_services"]
    assert not any(i["object"] == "customer.com" for i in host_no_svc), \
        "host inheriting hostgroups via template should not be flagged as having no services"
