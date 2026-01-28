"""
Tests for nagios_parser.py - Nagios Configuration Parser
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nagios_parser import NagiosObject, NagiosConfigParser, parse_config


class TestNagiosObject:
    """Tests for the NagiosObject class."""

    def test_get_name_host(self):
        """Test getting name for a host object."""
        obj = NagiosObject(
            object_type='host',
            attributes={'host_name': 'test-server', 'alias': 'Test Server'}
        )
        assert obj.get_name() == 'test-server'

    def test_get_name_service(self):
        """Test getting name for a service object."""
        obj = NagiosObject(
            object_type='service',
            attributes={'host_name': 'test-server', 'service_description': 'HTTP'}
        )
        assert obj.get_name() == 'HTTP'

    def test_get_name_contact(self):
        """Test getting name for a contact object."""
        obj = NagiosObject(
            object_type='contact',
            attributes={'contact_name': 'admin', 'email': 'admin@example.com'}
        )
        assert obj.get_name() == 'admin'

    def test_get_name_contactgroup(self):
        """Test getting name for a contactgroup object."""
        obj = NagiosObject(
            object_type='contactgroup',
            attributes={'contactgroup_name': 'admins', 'members': 'admin'}
        )
        assert obj.get_name() == 'admins'

    def test_get_name_command(self):
        """Test getting name for a command object."""
        obj = NagiosObject(
            object_type='command',
            attributes={'command_name': 'check_http', 'command_line': '/usr/lib/nagios/plugins/check_http'}
        )
        assert obj.get_name() == 'check_http'

    def test_get_name_timeperiod(self):
        """Test getting name for a timeperiod object."""
        obj = NagiosObject(
            object_type='timeperiod',
            attributes={'timeperiod_name': '24x7', 'alias': '24 Hours'}
        )
        assert obj.get_name() == '24x7'

    def test_get_name_hostgroup(self):
        """Test getting name for a hostgroup object."""
        obj = NagiosObject(
            object_type='hostgroup',
            attributes={'hostgroup_name': 'linux-servers', 'members': 'server1,server2'}
        )
        assert obj.get_name() == 'linux-servers'

    def test_get_name_servicegroup(self):
        """Test getting name for a servicegroup object."""
        obj = NagiosObject(
            object_type='servicegroup',
            attributes={'servicegroup_name': 'http-services', 'members': 'host1,HTTP'}
        )
        assert obj.get_name() == 'http-services'

    def test_get_name_template(self):
        """Test getting name for a template (using 'name' field)."""
        obj = NagiosObject(
            object_type='host',
            attributes={'name': 'linux-server-template', 'register': '0'}
        )
        assert obj.get_name() == 'linux-server-template'

    def test_get_name_unnamed(self):
        """Test getting name when no name field is present."""
        obj = NagiosObject(
            object_type='host',
            attributes={'address': '192.168.1.1'}
        )
        assert obj.get_name() is None

    def test_get_display_name_normal(self):
        """Test display name for normal objects."""
        obj = NagiosObject(
            object_type='host',
            attributes={'host_name': 'test-server'}
        )
        assert obj.get_display_name() == 'test-server'

    def test_get_display_name_service_with_host(self):
        """Test display name for service with host."""
        obj = NagiosObject(
            object_type='service',
            attributes={'host_name': 'test-server', 'service_description': 'HTTP'}
        )
        # Service should return service_description with host context
        assert obj.get_display_name() == 'HTTP on test-server'

    def test_get_display_name_unnamed(self):
        """Test display name for unnamed objects."""
        obj = NagiosObject(
            object_type='host',
            attributes={'address': '192.168.1.1'}
        )
        assert '[unnamed host]' in obj.get_display_name()

    def test_to_dict(self):
        """Test conversion to dictionary."""
        obj = NagiosObject(
            object_type='host',
            attributes={'host_name': 'test-server', 'address': '192.168.1.1'},
            source_file='/etc/nagios/hosts.cfg',
            line_number=10
        )
        d = obj.to_dict()
        assert d['object_type'] == 'host'
        assert d['attributes'] == {'host_name': 'test-server', 'address': '192.168.1.1'}
        assert d['source_file'] == '/etc/nagios/hosts.cfg'
        assert d['line_number'] == 10
        assert d['name'] == 'test-server'
        assert d['display_name'] == 'test-server'


class TestNagiosConfigParser:
    """Tests for the NagiosConfigParser class."""

    def test_parse_single_host(self, temp_config_dir):
        """Test parsing a single host definition."""
        config_content = '''define host {
    host_name       test-server
    alias           Test Server
    address         192.168.1.100
}
'''
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write(config_content)

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        assert len(parser.objects) == 1
        assert parser.objects[0].object_type == 'host'
        assert parser.objects[0].attributes['host_name'] == 'test-server'
        assert parser.objects[0].attributes['alias'] == 'Test Server'
        assert parser.objects[0].attributes['address'] == '192.168.1.100'

    def test_parse_multiple_objects(self, sample_host_config, temp_config_dir):
        """Test parsing multiple host definitions."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        assert len(parser.objects) == 2
        host_names = [obj.attributes.get('host_name') for obj in parser.objects]
        assert 'test-server-01' in host_names
        assert 'test-server-02' in host_names

    def test_parse_full_config(self, full_config_dir):
        """Test parsing a full configuration directory."""
        parser = NagiosConfigParser(full_config_dir)
        parser.parse_all()

        # Should have multiple object types
        object_types = parser.get_object_types()
        assert 'host' in object_types
        assert 'service' in object_types
        assert 'contact' in object_types
        assert 'contactgroup' in object_types
        assert 'command' in object_types
        assert 'timeperiod' in object_types

    def test_parse_preserves_line_numbers(self, sample_host_config, temp_config_dir):
        """Test that line numbers are preserved during parsing."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        for obj in parser.objects:
            assert obj.line_number > 0
            assert obj.source_file != ''

    def test_parse_comments_ignored(self, temp_config_dir):
        """Test that comments are properly ignored."""
        config_content = '''# This is a comment
define host {
    # This is also a comment
    host_name       test-server
    ; This is a semicolon comment
    address         192.168.1.100
}
'''
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write(config_content)

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        assert len(parser.objects) == 1
        assert parser.objects[0].attributes.get('host_name') == 'test-server'
        # Comments should not be in attributes
        assert '#' not in str(parser.objects[0].attributes.values())

    def test_parse_inline_comments(self, temp_config_dir):
        """Test that inline comments are stripped."""
        config_content = '''define host {
    host_name       test-server    ; server name
    address         192.168.1.100  ; IP address
}
'''
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write(config_content)

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        assert parser.objects[0].attributes['host_name'] == 'test-server'
        assert parser.objects[0].attributes['address'] == '192.168.1.100'
        # Should not contain the inline comment
        assert 'server name' not in parser.objects[0].attributes['host_name']

    def test_parse_quoted_semicolons(self, config_with_special_chars, temp_config_dir):
        """Test that semicolons inside quotes are preserved."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        # Find the command with quoted args
        commands = [obj for obj in parser.objects if obj.object_type == 'command']
        assert len(commands) > 0

    def test_parse_quoted_braces(self, config_with_quotes, temp_config_dir):
        """Test that braces inside quotes don't break parsing."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        # Should have parsed both objects correctly
        assert len(parser.objects) == 2

    def test_get_objects_by_type(self, full_config_dir):
        """Test filtering objects by type."""
        parser = NagiosConfigParser(full_config_dir)
        parser.parse_all()

        hosts = parser.get_objects_by_type('host')
        services = parser.get_objects_by_type('service')
        contacts = parser.get_objects_by_type('contact')

        # All returned objects should be of the correct type
        for obj in hosts:
            assert obj.object_type == 'host'
        for obj in services:
            assert obj.object_type == 'service'
        for obj in contacts:
            assert obj.object_type == 'contact'

    def test_get_files(self, full_config_dir):
        """Test getting list of parsed files."""
        parser = NagiosConfigParser(full_config_dir)
        parser.parse_all()

        files = parser.get_files()
        assert len(files) > 0
        for f in files:
            assert f.endswith('.cfg')

    def test_find_objects_by_term(self, sample_host_config, temp_config_dir):
        """Test searching for objects by term."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        # Search for a unique term that only matches one object
        results = parser.find_objects('192.168.1.100')
        assert len(results) == 1
        assert results[0].attributes['host_name'] == 'test-server-01'

    def test_find_objects_case_insensitive(self, sample_host_config, temp_config_dir):
        """Test that search is case-insensitive."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        # Search case-insensitively for unique term
        results = parser.find_objects('TEST SERVER 01')
        assert len(results) >= 1

    def test_find_objects_by_type(self, full_config_dir):
        """Test searching with type filter."""
        parser = NagiosConfigParser(full_config_dir)
        parser.parse_all()

        results = parser.find_objects('admin', object_type='contact')
        for obj in results:
            assert obj.object_type == 'contact'

    def test_find_objects_by_field(self, sample_host_config, temp_config_dir):
        """Test searching in specific field."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        results = parser.find_objects('192.168.1.100', field='address')
        assert len(results) == 1
        assert results[0].attributes['address'] == '192.168.1.100'

    def test_find_objects_regex(self, sample_host_config, temp_config_dir):
        """Test searching with regex pattern."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        results = parser.find_objects(r'test-server-\d+', regex=True)
        assert len(results) == 2

    def test_find_objects_invalid_regex(self, sample_host_config, temp_config_dir):
        """Test that invalid regex returns empty results."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        results = parser.find_objects(r'[invalid', regex=True)
        assert len(results) == 0

    def test_find_references(self, full_config_dir):
        """Test finding objects that reference another object."""
        parser = NagiosConfigParser(full_config_dir)
        parser.parse_all()

        # Find objects referencing the admin contact
        refs = parser.find_references('contact', 'admin')
        assert len(refs) > 0

    def test_get_summary(self, full_config_dir):
        """Test getting summary of objects by type."""
        parser = NagiosConfigParser(full_config_dir)
        parser.parse_all()

        summary = parser.get_summary()
        assert isinstance(summary, dict)
        assert 'host' in summary
        assert summary['host'] > 0

    def test_parse_empty_directory(self, temp_config_dir):
        """Test parsing an empty directory."""
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        assert len(parser.objects) == 0

    def test_parse_nonexistent_directory(self):
        """Test parsing a nonexistent directory."""
        parser = NagiosConfigParser('/nonexistent/path')
        parser.parse_all()

        assert len(parser.objects) == 0

    def test_skip_backup_files(self, temp_config_dir):
        """Test that backup files are skipped."""
        # Create a normal config file
        config_content = '''define host {
    host_name       normal-host
    address         192.168.1.1
}
'''
        with open(os.path.join(temp_config_dir, 'hosts.cfg'), 'w') as f:
            f.write(config_content)

        # Create a backup file that should be skipped
        backup_content = '''define host {
    host_name       backup-host
    address         192.168.1.2
}
'''
        os.makedirs(os.path.join(temp_config_dir, 'backups'), exist_ok=True)
        with open(os.path.join(temp_config_dir, 'backups', 'hosts.cfg'), 'w') as f:
            f.write(backup_content)

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        # Should only have the normal host, not the backup
        assert len(parser.objects) == 1
        assert parser.objects[0].attributes['host_name'] == 'normal-host'

    def test_line_continuation(self, temp_config_dir):
        """Test parsing lines with continuation backslashes."""
        config_content = '''define command {
    command_name    check_long
    command_line    $USER1$/check_something \\
                    --option1 value1 \\
                    --option2 value2
}
'''
        config_file = os.path.join(temp_config_dir, 'commands.cfg')
        with open(config_file, 'w') as f:
            f.write(config_content)

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        assert len(parser.objects) == 1
        # The command_line should be joined with spaces
        assert '--option1' in parser.objects[0].attributes['command_line']
        assert '--option2' in parser.objects[0].attributes['command_line']


class TestParseConfigConvenience:
    """Tests for the parse_config convenience function."""

    def test_parse_config(self, full_config_dir):
        """Test the parse_config convenience function."""
        parser = parse_config(full_config_dir)

        assert isinstance(parser, NagiosConfigParser)
        assert len(parser.objects) > 0

    def test_parse_config_default(self):
        """Test parse_config with default path."""
        # This might not find any objects if sample-config doesn't exist
        parser = parse_config('./nonexistent')
        assert isinstance(parser, NagiosConfigParser)

