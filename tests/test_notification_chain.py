"""Tests for notification chain validation (SAFETY-2)."""

import pytest
import tempfile
import shutil
from pathlib import Path
from app import create_app


@pytest.fixture
def app_with_notification_gaps():
    """Config with various notification chain problems."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / 'nagios'
    test_config_path.mkdir()

    (test_config_path / 'commands.cfg').write_text('''
define command {
    command_name    notify-by-email
    command_line    /usr/bin/mail -s "Alert" $CONTACTEMAIL$
}
define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}
''')

    (test_config_path / 'timeperiods.cfg').write_text('''
define timeperiod {
    timeperiod_name 24x7
    monday          00:00-24:00
    tuesday         00:00-24:00
    wednesday       00:00-24:00
    thursday        00:00-24:00
    friday          00:00-24:00
    saturday        00:00-24:00
    sunday          00:00-24:00
}
''')

    (test_config_path / 'contacts.cfg').write_text('''
define contact {
    name                           empty-template
    register                       0
}

define contact {
    contact_name                   broken-contact
    use                            empty-template
}

define contact {
    contact_name                   working-contact
    host_notification_commands     notify-by-email
    service_notification_commands  notify-by-email
    host_notification_period       24x7
    service_notification_period    24x7
}

define contact {
    contact_name                   missing-svc-cmd
    host_notification_commands     notify-by-email
    host_notification_period       24x7
    service_notification_period    24x7
}

define contactgroup {
    contactgroup_name   broken-group
    members             broken-contact
}

define contactgroup {
    contactgroup_name   working-group
    members             working-contact
}

define contactgroup {
    contactgroup_name   mixed-group
    members             working-contact,broken-contact
}
''')

    (test_config_path / 'hosts.cfg').write_text('''
define host {
    host_name           host-with-broken-contacts
    address             10.0.0.1
    max_check_attempts  5
    contact_groups      broken-group
    check_command       check-host-alive
}

define host {
    host_name           host-with-working-contacts
    address             10.0.0.2
    max_check_attempts  5
    contact_groups      working-group
    check_command       check-host-alive
}
''')

    (test_config_path / 'services.cfg').write_text('''
define service {
    host_name               host-with-broken-contacts
    service_description     Broken Service
    check_command           check_http
    max_check_attempts      3
    contact_groups          broken-group
}

define service {
    host_name               host-with-working-contacts
    service_description     Working Service
    check_command           check_http
    max_check_attempts      3
    contact_groups          working-group
}

define service {
    host_name               host-with-working-contacts
    service_description     Missing Svc Cmd Service
    check_command           check_http
    max_check_attempts      3
    contacts                missing-svc-cmd
}
''')

    app = create_app(config_path=str(test_config_path))
    app.config['TESTING'] = True
    yield app
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app_with_notification_gaps):
    return app_with_notification_gaps.test_client()


class TestNotificationChainValidation:
    """Test end-to-end notification chain tracing."""

    def test_detects_contact_missing_notification_commands(self, client):
        """Contact without notification commands through chain is flagged."""
        resp = client.get('/api/health-check')
        assert resp.status_code == 200
        data = resp.get_json()

        chain_issues = [i for i in data['issues']
                        if i['type'] == 'notification_gap']

        # broken-contact (inherits from empty-template) should cause issues
        messages = ' '.join(i['message'] for i in chain_issues)
        assert 'broken-contact' in messages

    def test_working_chain_not_flagged(self, client):
        """Fully configured notification chain is not flagged."""
        resp = client.get('/api/health-check')
        data = resp.get_json()

        chain_issues = [i for i in data['issues']
                        if i['type'] == 'notification_gap']

        # working-contact should not appear in any gap messages
        working_messages = [i for i in chain_issues
                            if 'working-contact' in i['message']
                            and 'Working Service' in i.get('object', '')]
        assert len(working_messages) == 0

    def test_detects_missing_service_notification_commands(self, client):
        """Contact with host commands but no service commands flagged for services."""
        resp = client.get('/api/health-check')
        data = resp.get_json()

        chain_issues = [i for i in data['issues']
                        if i['type'] == 'notification_gap']

        messages = ' '.join(i['message'] for i in chain_issues)
        assert 'missing-svc-cmd' in messages
