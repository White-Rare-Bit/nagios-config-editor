"""Tests for health check endpoint."""

import json
import os
import pytest
import tempfile
import shutil
from pathlib import Path
from app import create_app
from git_service import GitService
from file_operations import edit_object_in_file, add_object_to_file


@pytest.fixture
def health_check_app():
    """Create Flask app with test config for health check tests."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / 'nagios'
    test_config_path.mkdir()

    # Create config with a contact that references a non-existent notification command
    (test_config_path / 'commands.cfg').write_text('''
define command {
    command_name    notify-host-by-email
    command_line    /usr/bin/printf "%b" "Host alert"
}

define command {
    command_name    check-host-alive
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}
''')

    (test_config_path / 'contacts.cfg').write_text('''
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
''')

    (test_config_path / 'timeperiods.cfg').write_text('''
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
''')

    app = create_app(config_path=str(test_config_path))
    app.config['TESTING'] = True

    yield app

    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def health_client(health_check_app):
    return health_check_app.test_client()


def test_health_check_detects_missing_notification_commands(health_client):
    """Health check should detect non-existent host/service notification commands on contacts."""
    resp = health_client.get('/api/health-check')
    assert resp.status_code == 200
    data = resp.json

    # Find issues about the non-existent service_notification_commands
    cmd_issues = [i for i in data['issues'] if i['type'] == 'missing_command']
    missing_cmds = [i['message'] for i in cmd_issues]

    # Should detect the nonexistent-notify-command
    assert any('nonexistent-notify-command' in msg for msg in missing_cmds), \
        f"Expected missing_command for 'nonexistent-notify-command', got issues: {cmd_issues}"


def test_health_check_valid_notification_commands_no_false_positive(health_client):
    """Health check should NOT flag valid notification commands."""
    resp = health_client.get('/api/health-check')
    data = resp.json

    cmd_issues = [i for i in data['issues'] if i['type'] == 'missing_command']
    missing_cmds = [i['message'] for i in cmd_issues]

    # notify-host-by-email exists, should NOT be flagged
    assert not any('notify-host-by-email' in msg for msg in missing_cmds), \
        f"False positive: valid command 'notify-host-by-email' flagged as missing"


def test_health_check_detects_missing_cmd_in_comma_separated_list(health_client):
    """Health check should detect a missing command even when it appears in a comma-separated list."""
    resp = health_client.get('/api/health-check')
    assert resp.status_code == 200
    data = resp.json

    cmd_issues = [i for i in data['issues'] if i['type'] == 'missing_command']
    missing_cmds = [i['message'] for i in cmd_issues]

    # The 'oncall' contact has host_notification_commands = notify-host-by-email,nonexistent-cmd
    # The second command in the comma-separated list is invalid and should be detected
    assert any('nonexistent-cmd' in msg for msg in missing_cmds), \
        f"Expected missing_command for 'nonexistent-cmd' in comma-separated list, got issues: {cmd_issues}"

    # The issue message should reference ONLY 'nonexistent-cmd', not the entire comma-separated string
    oncall_cmd_issues = [i for i in cmd_issues if i['object'] == 'oncall']
    assert len(oncall_cmd_issues) == 1, \
        f"Expected exactly 1 missing command issue for 'oncall', got {len(oncall_cmd_issues)}: {oncall_cmd_issues}"
    assert oncall_cmd_issues[0]['message'] == 'References non-existent command: nonexistent-cmd', \
        f"Expected precise error for 'nonexistent-cmd', got: {oncall_cmd_issues[0]['message']}"


def test_gitignore_references_correct_staging_dir():
    """Generated .gitignore should reference .staging/ not .nagios_staging/."""
    test_dir = tempfile.mkdtemp()
    try:
        gs = GitService(test_dir)
        gs.init_repo()
        gitignore_path = os.path.join(test_dir, '.gitignore')
        assert os.path.exists(gitignore_path), ".gitignore should be created"
        content = Path(gitignore_path).read_text()
        assert '.staging/' in content, f".gitignore should contain '.staging/', got:\n{content}"
        assert '.nagios_staging/' not in content, \
            f".gitignore should NOT contain '.nagios_staging/', got:\n{content}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_health_check_detects_hosts_without_services():
    """Health check should detect hosts that have no services assigned."""
    test_dir = tempfile.mkdtemp()
    try:
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'hosts.cfg').write_text('''
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
''')

        (test_config_path / 'services.cfg').write_text('''
define service {
    host_name               monitored-host
    service_description     PING
    check_command           check_ping
}
''')

        (test_config_path / 'commands.cfg').write_text('''
define command {
    command_name    check_ping
    command_line    /usr/lib/nagios/plugins/check_ping -H $HOSTADDRESS$
}
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        client = app.test_client()

        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.json

        no_service_issues = [i for i in data['issues']
                             if i['type'] == 'host_without_services']

        # lonely-host should be flagged
        flagged_hosts = [i['object'] for i in no_service_issues]
        assert 'lonely-host' in flagged_hosts, \
            f"Expected 'lonely-host' flagged, got: {flagged_hosts}"

        # monitored-host should NOT be flagged
        assert 'monitored-host' not in flagged_hosts, \
            f"False positive: 'monitored-host' has services but was flagged"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_health_check_hostgroup_services_not_flagged():
    """Hosts with services via hostgroup_name should NOT be flagged."""
    test_dir = tempfile.mkdtemp()
    try:
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'config.cfg').write_text('''
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
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        client = app.test_client()

        resp = client.get('/api/health-check')
        data = resp.json

        no_service_issues = [i for i in data['issues']
                             if i['type'] == 'host_without_services']
        flagged_hosts = [i['object'] for i in no_service_issues]

        assert 'grouped-host' not in flagged_hosts, \
            f"False positive: 'grouped-host' has services via hostgroup but was flagged"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


from nagios_model import REQUIRED_FIELDS


def test_required_fields_host_includes_address():
    """REQUIRED_FIELDS for host should include 'address' (or template fallback)."""
    host_fields = REQUIRED_FIELDS.get('host', [])
    # address should be listed (possibly in an OR tuple with 'use')
    flat = []
    for f in host_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert 'address' in flat, \
        f"'address' should be in host REQUIRED_FIELDS, got: {host_fields}"


def test_required_fields_service_includes_check_command():
    """REQUIRED_FIELDS for service should include 'check_command'."""
    svc_fields = REQUIRED_FIELDS.get('service', [])
    flat = []
    for f in svc_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert 'check_command' in flat, \
        f"'check_command' should be in service REQUIRED_FIELDS, got: {svc_fields}"


def test_required_fields_contact_includes_notification_fields():
    """REQUIRED_FIELDS for contact should include notification fields."""
    contact_fields = REQUIRED_FIELDS.get('contact', [])
    flat = []
    for f in contact_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert 'host_notification_commands' in flat or 'notification_commands' in flat, \
        f"Contact REQUIRED_FIELDS should include notification commands, got: {contact_fields}"


def test_edit_object_uses_atomic_write(tmp_path):
    """edit_object_in_file should write atomically (temp file + rename)."""
    cfg = tmp_path / 'test.cfg'
    cfg.write_text('''define host {
    host_name       test-host
    alias           Test
    address         1.2.3.4
}
''')
    result = edit_object_in_file(
        str(cfg), 1,
        {'host_name': 'test-host', 'alias': 'Updated', 'address': '1.2.3.4'},
        'host'
    )
    assert result.success, f"Edit failed: {result.error}"
    content = cfg.read_text()
    assert 'Updated' in content
    # File should still exist and be valid (atomic write doesn't leave partial files)
    assert 'define host' in content


class TestCheckCommandInheritance:
    """Test that services missing check_command are detected even through inheritance."""

    @pytest.fixture
    def app_with_missing_check_cmd(self):
        """Config where a service inherits but never gets check_command."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'commands.cfg').write_text('''
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}
''')

        (test_config_path / 'templates.cfg').write_text('''
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
''')

        (test_config_path / 'hosts.cfg').write_text('''
define host {
    host_name       test-host
    address         10.0.0.1
    max_check_attempts 5
    contact_groups  admins
}
''')

        (test_config_path / 'contacts.cfg').write_text('''
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
''')

        (test_config_path / 'services.cfg').write_text('''
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
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_service_missing_check_command_through_inheritance(self, app_with_missing_check_cmd):
        """Service inheriting from template without check_command is flagged."""
        client = app_with_missing_check_cmd.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        missing_cmd_issues = [i for i in data['issues']
                              if i['type'] == 'missing_check_command']

        # "Missing Check Command" service should be flagged
        flagged_names = [i['object'] for i in missing_cmd_issues]
        assert any('Missing Check Command' in n for n in flagged_names)

        # "Has Check Command" and "Direct Check Command" should NOT be flagged
        assert not any('Has Check Command' in n for n in flagged_names)
        assert not any('Direct Check Command' in n for n in flagged_names)


class TestCommandArgValidation:
    """Test that check_command argument count mismatches are detected."""

    @pytest.fixture
    def app_with_arg_mismatch(self):
        """Config with argument count mismatches."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'commands.cfg').write_text('''
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
''')

        (test_config_path / 'hosts.cfg').write_text('''
define host {
    host_name       test-host
    address         10.0.0.1
    max_check_attempts 5
    contact_groups  admins
}
''')

        (test_config_path / 'contacts.cfg').write_text('''
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
''')

        (test_config_path / 'services.cfg').write_text('''
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
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_argument_count_mismatch(self, app_with_arg_mismatch):
        """Services with wrong argument count are flagged."""
        client = app_with_arg_mismatch.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        arg_issues = [i for i in data['issues']
                      if i['type'] == 'command_arg_mismatch']

        flagged_names = [i['object'] for i in arg_issues]

        # "Too Few Args" and "Too Many Args" should be flagged
        assert any('Too Few Args' in n for n in flagged_names)
        assert any('Too Many Args' in n for n in flagged_names)

        # "Correct Args" and "No Args Needed" should NOT be flagged
        assert not any('Correct Args' in n for n in flagged_names)
        assert not any('No Args Needed' in n for n in flagged_names)


class TestTemplateConflictDetection:
    """Test that conflicting attributes from multi-template inheritance are warned."""

    @pytest.fixture
    def app_with_template_conflicts(self):
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'templates.cfg').write_text('''
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
''')

        (test_config_path / 'hosts.cfg').write_text('''
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
''')

        (test_config_path / 'contacts.cfg').write_text('''
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
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_template_attribute_conflicts(self, app_with_template_conflicts):
        """Objects inheriting conflicting attributes from multiple templates get a warning."""
        client = app_with_template_conflicts.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        conflict_issues = [i for i in data['issues']
                           if i['type'] == 'template_conflict']

        # conflicting-host should have conflicts (check_interval, max_check_attempts differ)
        flagged = [i['object'] for i in conflict_issues]
        assert any('conflicting-host' in n for n in flagged)

        # no-conflict-host should NOT be flagged (fast-check and no-conflict don't overlap)
        assert not any('no-conflict-host' in n for n in flagged)


def test_apply_staging_with_validate_flag():
    """Apply staging should include validation result when validate=true."""
    test_dir = tempfile.mkdtemp()
    try:
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'hosts.cfg').write_text('''
define host {
    host_name       test-host
    alias           Test Host
    address         192.168.1.1
}
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        client = app.test_client()

        # Stage an edit
        session_id = 'test-session'
        headers = {'X-Session-Id': session_id, 'Content-Type': 'application/json'}

        # Get objects to find stable key
        resp = client.get('/api/objects')
        assert resp.status_code == 200
        objects = resp.json
        assert len(objects) > 0
        obj = objects[0]

        # Stage an edit
        staging_data = {
            'sessionId': session_id,
            'userName': 'Test User',
            'userEmail': 'test@example.com',
            'pendingEdits': {
                str(obj['global_index']): {
                    'object': obj,
                    'original': obj['attributes'],
                    'edited': {**obj['attributes'], 'alias': 'Modified'}
                }
            }
        }

        resp = client.post('/api/staging',
                           data=json.dumps(staging_data),
                           content_type='application/json',
                           headers=headers)
        assert resp.status_code == 200

        # Apply with validate flag
        resp = client.post('/api/staging/apply', headers=headers, json={
            'validate': True
        })
        assert resp.status_code == 200
        data = resp.json

        # Response should include a validation field
        assert 'validation' in data, \
            f"Response should include 'validation' when validate=true, got keys: {list(data.keys())}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


class TestUnusedCommandDetection:
    """Test that unused commands are detected by health check."""

    @pytest.fixture
    def app_with_unused_commands(self):
        """Config with 4 commands: 2 used, 2 unused."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'commands.cfg').write_text('''
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
''')

        (test_config_path / 'hosts.cfg').write_text('''
define host {
    host_name       test-host
    address         10.0.0.1
    check_command   check-host-alive
}
''')

        (test_config_path / 'contacts.cfg').write_text('''
define contact {
    contact_name                    admin
    host_notification_commands      notify-by-email
    service_notification_commands   notify-by-email
    host_notification_period        24x7
    service_notification_period     24x7
}
''')

        (test_config_path / 'timeperiods.cfg').write_text('''
define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    monday          00:00-24:00
}
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_unused_commands(self, app_with_unused_commands):
        """Unused commands should be detected; used ones should not."""
        client = app_with_unused_commands.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        unused_cmd_issues = [i for i in data['issues']
                             if i['type'] == 'unused_command']
        flagged_names = [i['object'] for i in unused_cmd_issues]

        # unused-check and unused-notify should be flagged
        assert 'unused-check' in flagged_names, \
            f"Expected 'unused-check' flagged, got: {flagged_names}"
        assert 'unused-notify' in flagged_names, \
            f"Expected 'unused-notify' flagged, got: {flagged_names}"

        # check-host-alive and notify-by-email should NOT be flagged
        assert 'check-host-alive' not in flagged_names, \
            f"False positive: 'check-host-alive' is used but was flagged"
        assert 'notify-by-email' not in flagged_names, \
            f"False positive: 'notify-by-email' is used but was flagged"

    def test_unused_commands_are_warnings(self, app_with_unused_commands):
        """Unused command issues should have 'warning' severity."""
        client = app_with_unused_commands.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        unused_cmd_issues = [i for i in data['issues']
                             if i['type'] == 'unused_command']

        assert len(unused_cmd_issues) > 0, "Expected at least one unused_command issue"
        for issue in unused_cmd_issues:
            assert issue['severity'] == 'warning', \
                f"Expected severity 'warning', got '{issue['severity']}' for {issue['object']}"


class TestUnusedObjectDetection:
    """Test that unused contacts, contactgroups, and timeperiods are detected."""

    @pytest.fixture
    def app_with_unused_objects(self):
        """Config with used and unused contacts, contactgroups, and timeperiods."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'commands.cfg').write_text('''
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}

define command {
    command_name    notify-by-email
    command_line    /usr/bin/printf "%b" "Notification"
}
''')

        (test_config_path / 'timeperiods.cfg').write_text('''
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
''')

        (test_config_path / 'contacts.cfg').write_text('''
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
''')

        (test_config_path / 'contactgroups.cfg').write_text('''
define contactgroup {
    contactgroup_name   used-cg
    alias               Used Contact Group
    members             used-contact
}

define contactgroup {
    contactgroup_name   unused-cg
    alias               Unused Contact Group
}
''')

        (test_config_path / 'hosts.cfg').write_text('''
define host {
    host_name       test-host
    address         10.0.0.1
    check_command   check-host-alive
    contact_groups  used-cg
}
''')

        (test_config_path / 'services.cfg').write_text('''
define service {
    host_name               test-host
    service_description     PING
    check_command           check-host-alive
    contact_groups          used-cg
}
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_unused_contacts(self, app_with_unused_objects):
        """unused-contact should be flagged; used-contact should not."""
        client = app_with_unused_objects.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        unused_contact_issues = [i for i in data['issues']
                                 if i['type'] == 'unused_contact']
        flagged_names = [i['object'] for i in unused_contact_issues]

        assert 'unused-contact' in flagged_names, \
            f"Expected 'unused-contact' flagged, got: {flagged_names}"
        assert 'used-contact' not in flagged_names, \
            f"False positive: 'used-contact' is referenced by contactgroup but was flagged"

    def test_detects_unused_contactgroups(self, app_with_unused_objects):
        """unused-cg should be flagged; used-cg should not."""
        client = app_with_unused_objects.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        unused_cg_issues = [i for i in data['issues']
                            if i['type'] == 'unused_contactgroup']
        flagged_names = [i['object'] for i in unused_cg_issues]

        assert 'unused-cg' in flagged_names, \
            f"Expected 'unused-cg' flagged, got: {flagged_names}"
        assert 'used-cg' not in flagged_names, \
            f"False positive: 'used-cg' is assigned to host/service but was flagged"

    def test_detects_unused_timeperiods(self, app_with_unused_objects):
        """unused-period should be flagged; 24x7 should not."""
        client = app_with_unused_objects.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        unused_tp_issues = [i for i in data['issues']
                            if i['type'] == 'unused_timeperiod']
        flagged_names = [i['object'] for i in unused_tp_issues]

        assert 'unused-period' in flagged_names, \
            f"Expected 'unused-period' flagged, got: {flagged_names}"
        assert '24x7' not in flagged_names, \
            f"False positive: '24x7' is used by contacts but was flagged"


class TestDuplicateObjectDetection:
    """Test that duplicate object definitions are detected by health check."""

    @pytest.fixture
    def app_with_duplicates(self):
        """Config with duplicate host definitions across files."""
        test_dir = tempfile.mkdtemp()
        test_config_path = Path(test_dir) / 'nagios'
        test_config_path.mkdir()

        (test_config_path / 'hosts1.cfg').write_text('''
define host {
    host_name       duplicate-host
    alias           First Copy
    address         10.0.0.1
}
''')

        (test_config_path / 'hosts2.cfg').write_text('''
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
''')

        (test_config_path / 'commands.cfg').write_text('''
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
''')

        (test_config_path / 'timeperiods.cfg').write_text('''
define timeperiod {
    timeperiod_name 24x7
    alias           24x7
    monday          00:00-24:00
}
''')

        app = create_app(config_path=str(test_config_path))
        app.config['TESTING'] = True
        yield app
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_detects_duplicate_hosts(self, app_with_duplicates):
        """duplicate-host should be flagged; unique-host should not."""
        client = app_with_duplicates.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        dup_issues = [i for i in data['issues']
                      if i['type'] == 'duplicate_object']
        flagged_names = [i['object'] for i in dup_issues]

        assert 'duplicate-host' in flagged_names, \
            f"Expected 'duplicate-host' flagged, got: {flagged_names}"
        assert 'unique-host' not in flagged_names, \
            f"False positive: 'unique-host' is not duplicated but was flagged"

    def test_duplicate_is_error_severity(self, app_with_duplicates):
        """All duplicate_object issues should have 'error' severity."""
        client = app_with_duplicates.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        dup_issues = [i for i in data['issues']
                      if i['type'] == 'duplicate_object']

        assert len(dup_issues) > 0, "Expected at least one duplicate_object issue"
        for issue in dup_issues:
            assert issue['severity'] == 'error', \
                f"Expected severity 'error', got '{issue['severity']}' for {issue['object']}"

    def test_duplicate_reports_files(self, app_with_duplicates):
        """Duplicate issue message should mention the other file(s)."""
        client = app_with_duplicates.test_client()
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        dup_issues = [i for i in data['issues']
                      if i['type'] == 'duplicate_object']

        assert len(dup_issues) >= 2, \
            f"Expected at least 2 duplicate issues (one per copy), got {len(dup_issues)}"

        # Each duplicate issue should mention the other file
        for issue in dup_issues:
            # The message should reference at least one other file
            assert 'also in' in issue['message'], \
                f"Expected 'also in' in message, got: {issue['message']}"
            # Should mention a .cfg file
            assert '.cfg' in issue['message'], \
                f"Expected a .cfg filename in message, got: {issue['message']}"
