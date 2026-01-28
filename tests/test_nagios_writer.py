"""
Tests for nagios_writer.py - Nagios Configuration Writer
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nagios_parser import NagiosObject
from nagios_writer import NagiosConfigWriter, write_config_file


class TestNagiosConfigWriter:
    """Tests for the NagiosConfigWriter class."""

    def test_object_to_string_basic(self):
        """Test converting a basic object to string."""
        obj = NagiosObject(
            object_type='host',
            attributes={'host_name': 'test-server', 'address': '192.168.1.100'}
        )
        writer = NagiosConfigWriter()
        result = writer.object_to_string(obj)

        assert 'define host {' in result
        assert 'host_name' in result
        assert 'test-server' in result
        assert 'address' in result
        assert '192.168.1.100' in result
        assert result.endswith('}')

    def test_object_to_string_name_fields_first(self):
        """Test that name fields appear first in output."""
        obj = NagiosObject(
            object_type='host',
            attributes={
                'address': '192.168.1.100',
                'host_name': 'test-server',
                'alias': 'Test Server',
                'check_command': 'check-host-alive'
            }
        )
        writer = NagiosConfigWriter()
        result = writer.object_to_string(obj)
        lines = result.split('\n')

        # host_name should come before other attributes
        host_name_line = None
        address_line = None
        for i, line in enumerate(lines):
            if 'host_name' in line:
                host_name_line = i
            if 'address' in line:
                address_line = i

        assert host_name_line is not None
        assert address_line is not None
        assert host_name_line < address_line

    def test_object_to_string_indentation(self):
        """Test custom indentation."""
        obj = NagiosObject(
            object_type='host',
            attributes={'host_name': 'test-server'}
        )
        writer = NagiosConfigWriter(indent='  ')  # 2 spaces
        result = writer.object_to_string(obj)

        lines = result.split('\n')
        # Check that attributes are indented with 2 spaces
        for line in lines[1:-1]:  # Skip first and last lines
            if line.strip():  # Skip empty lines
                assert line.startswith('  ')

    def test_objects_to_string_multiple(self):
        """Test converting multiple objects to string."""
        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'server1'},
                source_file='/etc/nagios/hosts.cfg',
                line_number=1
            ),
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'server2'},
                source_file='/etc/nagios/hosts.cfg',
                line_number=10
            )
        ]
        writer = NagiosConfigWriter()
        result = writer.objects_to_string(objects)

        assert 'server1' in result
        assert 'server2' in result
        # Should have double newlines between objects
        assert '\n\n' in result

    def test_objects_to_string_preserve_order(self):
        """Test that preserve_order maintains line number ordering."""
        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'server2'},
                source_file='/etc/nagios/hosts.cfg',
                line_number=20
            ),
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'server1'},
                source_file='/etc/nagios/hosts.cfg',
                line_number=10
            )
        ]
        writer = NagiosConfigWriter()
        result = writer.objects_to_string(objects, preserve_order=True)

        # server1 should come first (lower line number)
        assert result.index('server1') < result.index('server2')

    def test_objects_to_string_group_by_type(self):
        """Test grouping objects by type when preserve_order is False."""
        objects = [
            NagiosObject(
                object_type='service',
                attributes={'service_description': 'HTTP'},
                source_file='/etc/nagios/services.cfg',
                line_number=1
            ),
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'server1'},
                source_file='/etc/nagios/hosts.cfg',
                line_number=1
            ),
        ]
        writer = NagiosConfigWriter()
        result = writer.objects_to_string(objects, preserve_order=False)

        # When grouped by type, hosts should come before services
        assert result.index('host') < result.index('service')

    def test_write_file(self, temp_config_dir):
        """Test writing objects to a file."""
        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'test-server', 'address': '192.168.1.100'},
                source_file=os.path.join(temp_config_dir, 'hosts.cfg'),
                line_number=1
            )
        ]
        output_file = os.path.join(temp_config_dir, 'output.cfg')

        writer = NagiosConfigWriter()
        writer.write_file(output_file, objects)

        assert os.path.exists(output_file)
        with open(output_file, 'r') as f:
            content = f.read()

        assert 'define host' in content
        assert 'test-server' in content

    def test_write_file_creates_directories(self, temp_config_dir):
        """Test that write_file creates parent directories."""
        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'test-server'},
                source_file='',
                line_number=1
            )
        ]
        output_file = os.path.join(temp_config_dir, 'subdir', 'nested', 'hosts.cfg')

        writer = NagiosConfigWriter()
        writer.write_file(output_file, objects)

        assert os.path.exists(output_file)

    def test_write_file_atomic(self, temp_config_dir):
        """Test that write_file is atomic (no temp files left behind)."""
        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'test-server'},
                source_file='',
                line_number=1
            )
        ]
        output_file = os.path.join(temp_config_dir, 'hosts.cfg')

        writer = NagiosConfigWriter()
        writer.write_file(output_file, objects)

        # Check that no temp files are left
        files = os.listdir(temp_config_dir)
        assert all(not f.startswith('.nagios_') for f in files)

    def test_write_objects_to_original_files(self, temp_config_dir):
        """Test writing objects back to their original files."""
        file1 = os.path.join(temp_config_dir, 'hosts1.cfg')
        file2 = os.path.join(temp_config_dir, 'hosts2.cfg')

        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'server1'},
                source_file=file1,
                line_number=1
            ),
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'server2'},
                source_file=file2,
                line_number=1
            ),
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'server3'},
                source_file=file1,
                line_number=10
            )
        ]

        writer = NagiosConfigWriter()
        results = writer.write_objects_to_original_files(objects)

        assert results[file1] == 2  # Two objects in file1
        assert results[file2] == 1  # One object in file2
        assert os.path.exists(file1)
        assert os.path.exists(file2)

    def test_write_file_overwrites_existing(self, temp_config_dir):
        """Test that write_file overwrites existing content."""
        output_file = os.path.join(temp_config_dir, 'hosts.cfg')

        # Write initial content
        with open(output_file, 'w') as f:
            f.write('old content that should be replaced')

        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'new-server'},
                source_file='',
                line_number=1
            )
        ]

        writer = NagiosConfigWriter()
        writer.write_file(output_file, objects)

        with open(output_file, 'r') as f:
            content = f.read()

        assert 'old content' not in content
        assert 'new-server' in content

    def test_write_special_characters(self, temp_config_dir):
        """Test writing objects with special characters."""
        obj = NagiosObject(
            object_type='command',
            attributes={
                'command_name': 'check_with_args',
                'command_line': '$USER1$/check_nrpe -H $HOSTADDRESS$ -a "arg1 arg2"'
            },
            source_file='',
            line_number=1
        )
        output_file = os.path.join(temp_config_dir, 'commands.cfg')

        writer = NagiosConfigWriter()
        writer.write_file(output_file, [obj])

        with open(output_file, 'r') as f:
            content = f.read()

        assert '$USER1$' in content
        assert '$HOSTADDRESS$' in content
        assert '"arg1 arg2"' in content


class TestWriteConfigFileConvenience:
    """Tests for the write_config_file convenience function."""

    def test_write_config_file(self, temp_config_dir):
        """Test the write_config_file convenience function."""
        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'test-server'},
                source_file='',
                line_number=1
            )
        ]
        output_file = os.path.join(temp_config_dir, 'output.cfg')

        write_config_file(output_file, objects)

        assert os.path.exists(output_file)

    def test_write_config_file_custom_indent(self, temp_config_dir):
        """Test write_config_file with custom indentation."""
        objects = [
            NagiosObject(
                object_type='host',
                attributes={'host_name': 'test-server'},
                source_file='',
                line_number=1
            )
        ]
        output_file = os.path.join(temp_config_dir, 'output.cfg')

        write_config_file(output_file, objects, indent='\t')  # Tab indent

        with open(output_file, 'r') as f:
            content = f.read()

        # Check that tab indentation is used
        assert '\t' in content


class TestRoundTrip:
    """Tests for parsing and writing (round-trip)."""

    def test_round_trip_preserves_data(self, temp_config_dir):
        """Test that parsing and writing preserves object data."""
        from nagios_parser import NagiosConfigParser

        # Create initial config
        config_content = '''define host {
    host_name                   test-server
    alias                       Test Server
    address                     192.168.1.100
    check_command               check-host-alive
    max_check_attempts          3
}
'''
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write(config_content)

        # Parse
        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()

        # Write
        writer = NagiosConfigWriter()
        output_file = os.path.join(temp_config_dir, 'output.cfg')
        writer.write_file(output_file, parser.objects)

        # Parse again
        with open(output_file, 'r') as f:
            new_content = f.read()

        # Key attributes should be preserved
        assert 'test-server' in new_content
        assert 'Test Server' in new_content
        assert '192.168.1.100' in new_content
        assert 'check-host-alive' in new_content
        assert '3' in new_content

    def test_round_trip_multiple_objects(self, full_config_dir):
        """Test round-trip with multiple objects of different types."""
        from nagios_parser import NagiosConfigParser

        # Parse all configs
        parser = NagiosConfigParser(full_config_dir)
        parser.parse_all()
        original_count = len(parser.objects)

        # Write to a single file
        writer = NagiosConfigWriter()
        output_file = os.path.join(full_config_dir, 'combined.cfg')
        writer.write_file(output_file, parser.objects)

        # Parse the output file
        parser2 = NagiosConfigParser(full_config_dir)
        objects = parser2.parse_file(output_file)

        # Should have same number of objects
        assert len(objects) == original_count
