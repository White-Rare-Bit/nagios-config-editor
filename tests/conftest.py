"""
Pytest fixtures and configuration for Nagios Bulk Editor tests.
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for test configuration files."""
    temp_dir = tempfile.mkdtemp(prefix='nagios_test_')
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_host_config(temp_config_dir):
    """Create a sample host configuration file."""
    config_content = '''# Sample host configuration

define host {
    host_name                   test-server-01
    alias                       Test Server 01
    address                     192.168.1.100
    check_command               check-host-alive
    max_check_attempts          3
    check_period                24x7
    notification_interval       60
    notification_period         24x7
    contacts                    admin
    contact_groups              admins
}

define host {
    host_name                   test-server-02
    alias                       Test Server 02
    address                     192.168.1.101
    use                         linux-server
    parents                     test-server-01
}
'''
    config_file = os.path.join(temp_config_dir, 'hosts.cfg')
    with open(config_file, 'w') as f:
        f.write(config_content)
    return config_file


@pytest.fixture
def sample_service_config(temp_config_dir):
    """Create a sample service configuration file."""
    config_content = '''# Sample service configuration

define service {
    host_name                   test-server-01
    service_description         HTTP
    check_command               check_http
    max_check_attempts          3
    check_interval              5
    retry_interval              1
    check_period                24x7
    notification_interval       60
    notification_period         24x7
    contacts                    admin
}

define service {
    host_name                   test-server-01
    service_description         SSH
    check_command               check_ssh
    use                         generic-service
}
'''
    config_file = os.path.join(temp_config_dir, 'services.cfg')
    with open(config_file, 'w') as f:
        f.write(config_content)
    return config_file


@pytest.fixture
def sample_contact_config(temp_config_dir):
    """Create a sample contact configuration file."""
    config_content = '''# Sample contact configuration

define contact {
    contact_name                admin
    alias                       System Administrator
    email                       admin@example.com
    service_notification_period 24x7
    host_notification_period    24x7
    service_notification_options w,c,r
    host_notification_options   d,r
    service_notification_commands notify-service-by-email
    host_notification_commands  notify-host-by-email
}

define contactgroup {
    contactgroup_name           admins
    alias                       Administrators
    members                     admin
}
'''
    config_file = os.path.join(temp_config_dir, 'contacts.cfg')
    with open(config_file, 'w') as f:
        f.write(config_content)
    return config_file


@pytest.fixture
def sample_command_config(temp_config_dir):
    """Create a sample command configuration file."""
    config_content = '''# Sample command configuration

define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$ -w 3000.0,80% -c 5000.0,100% -p 5
}

define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}

define command {
    command_name    check_ssh
    command_line    $USER1$/check_ssh -H $HOSTADDRESS$
}
'''
    config_file = os.path.join(temp_config_dir, 'commands.cfg')
    with open(config_file, 'w') as f:
        f.write(config_content)
    return config_file


@pytest.fixture
def sample_timeperiod_config(temp_config_dir):
    """Create a sample timeperiod configuration file."""
    config_content = '''# Sample timeperiod configuration

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

define timeperiod {
    timeperiod_name workhours
    alias           Normal Work Hours
    monday          09:00-17:00
    tuesday         09:00-17:00
    wednesday       09:00-17:00
    thursday        09:00-17:00
    friday          09:00-17:00
}
'''
    config_file = os.path.join(temp_config_dir, 'timeperiods.cfg')
    with open(config_file, 'w') as f:
        f.write(config_content)
    return config_file


@pytest.fixture
def sample_template_config(temp_config_dir):
    """Create a sample template configuration file."""
    config_content = '''# Sample template configuration

define host {
    name                        linux-server
    check_command               check-host-alive
    max_check_attempts          3
    check_period                24x7
    notification_interval       60
    notification_period         24x7
    register                    0
}

define service {
    name                        generic-service
    max_check_attempts          3
    check_interval              5
    retry_interval              1
    check_period                24x7
    notification_interval       60
    notification_period         24x7
    register                    0
}
'''
    config_file = os.path.join(temp_config_dir, 'templates.cfg')
    with open(config_file, 'w') as f:
        f.write(config_content)
    return config_file


@pytest.fixture
def full_config_dir(temp_config_dir, sample_host_config, sample_service_config,
                    sample_contact_config, sample_command_config,
                    sample_timeperiod_config, sample_template_config):
    """Create a complete configuration directory with all object types."""
    return temp_config_dir


@pytest.fixture
def config_with_special_chars(temp_config_dir):
    """Create a config file with special characters and edge cases."""
    config_content = '''# Config with special characters

define command {
    command_name    check_with_args
    command_line    $USER1$/check_nrpe -H $HOSTADDRESS$ -c check_disk -a "warning=20% critical=10%"
}

define host {
    host_name       server-with-semicolon
    alias           Server with ; semicolon in alias
    address         192.168.1.200
    notes           This has a semicolon; in it but it should not be a comment
}

define service {
    host_name           server-with-semicolon
    service_description Disk Space
    check_command       check_with_args!20!10
}
'''
    config_file = os.path.join(temp_config_dir, 'special.cfg')
    with open(config_file, 'w') as f:
        f.write(config_content)
    return config_file


@pytest.fixture
def config_with_quotes(temp_config_dir):
    """Create a config file with quoted strings containing braces."""
    config_content = '''# Config with quoted braces

define command {
    command_name    check_json
    command_line    $USER1$/check_http -H $HOSTADDRESS$ -s "{\\"status\\": \\"ok\\"}"
}

define host {
    host_name       json-server
    alias           JSON Server
    address         192.168.1.201
    notes           Expects JSON response: {"status": "ok"}
}
'''
    config_file = os.path.join(temp_config_dir, 'quotes.cfg')
    with open(config_file, 'w') as f:
        f.write(config_content)
    return config_file


@pytest.fixture
def flask_app():
    """Create a Flask test client."""
    # Import here to avoid issues with module loading
    import app as flask_app_module

    # Create a temp directory for this test
    temp_dir = tempfile.mkdtemp(prefix='nagios_flask_test_')

    # Create minimal config files
    hosts_content = '''define host {
    host_name       test-host
    alias           Test Host
    address         127.0.0.1
}
'''
    with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
        f.write(hosts_content)

    # Create a fresh app instance using the factory
    test_app = flask_app_module.create_app(config_path=temp_dir)
    test_app.config['TESTING'] = True

    with test_app.test_client() as client:
        yield client, temp_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
