"""Tests for health check endpoint."""

import pytest
import tempfile
import shutil
from pathlib import Path
from app import create_app


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
