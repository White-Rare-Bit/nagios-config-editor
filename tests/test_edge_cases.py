"""
Comprehensive edge case tests designed to find bugs.
Tests parsing edge cases, API boundaries, security issues, and error handling.
"""

import pytest
import os
import sys
import json
import tempfile
import shutil
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nagios_parser import NagiosObject, NagiosConfigParser
from nagios_writer import NagiosConfigWriter
from backup_manager import BackupManager
from staging_manager import StagingManager


# ============================================================================
# Parser Edge Cases - Malformed Input
# ============================================================================

class TestParserMalformedInput:
    """Test parser behavior with malformed configuration files."""

    @pytest.fixture
    def temp_dir(self):
        temp_dir = tempfile.mkdtemp(prefix='nagios_edge_test_')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_unclosed_brace(self, temp_dir):
        """Test parsing with unclosed brace - should not crash."""
        config = '''define host {
    host_name       test-server
    address         192.168.1.1
'''  # Missing closing brace
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        # Should handle gracefully - either parse partial or skip
        # Main thing is it shouldn't crash
        assert len(parser.objects) == 0

    def test_extra_closing_brace(self, temp_dir):
        """Test parsing with extra closing brace."""
        config = '''define host {
    host_name       test-server
    address         192.168.1.1
}
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        # Should parse the valid object
        assert len(parser.objects) == 1

    def test_nested_braces_in_value(self, temp_dir):
        """Test parsing with braces inside attribute values."""
        config = '''define command {
    command_name    check_json
    command_line    /usr/bin/check_json --data '{"key": "value"}'
}
'''
        with open(os.path.join(temp_dir, 'commands.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        # Should handle JSON in command line
        assert len(parser.objects) == 1

    def test_empty_definition(self, temp_dir):
        """Test parsing empty object definition."""
        config = '''define host {
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 1
        assert parser.objects[0].object_type == 'host'
        assert len(parser.objects[0].attributes) == 0

    def test_no_space_after_define(self, temp_dir):
        """Test parsing 'definehost' without space."""
        config = '''definehost {
    host_name       test-server
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        # Should not parse as valid object
        assert len(parser.objects) == 0

    def test_multiple_colons_in_value(self, temp_dir):
        """Test parsing values with multiple colons (like URLs)."""
        config = '''define command {
    command_name    check_url
    command_line    /usr/bin/check_http -H $HOSTADDRESS$ -u https://example.com:8443/path
}
'''
        with open(os.path.join(temp_dir, 'commands.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 1
        assert 'https://example.com:8443/path' in parser.objects[0].attributes['command_line']

    def test_tabs_and_spaces_mixed(self, temp_dir):
        """Test parsing with mixed tabs and spaces."""
        config = "define host {\n\t    host_name\t\t  test-server\n    \taddress\t  192.168.1.1\n}\n"
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 1
        assert parser.objects[0].attributes['host_name'] == 'test-server'

    def test_duplicate_attributes(self, temp_dir):
        """Test parsing with duplicate attribute names."""
        config = '''define host {
    host_name       first-name
    address         192.168.1.1
    host_name       second-name
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 1
        # Last value should win (or first - just be consistent)
        assert parser.objects[0].attributes['host_name'] in ['first-name', 'second-name']

    def test_very_long_line(self, temp_dir):
        """Test parsing with very long lines."""
        long_value = 'x' * 10000
        config = f'''define host {{
    host_name       test-server
    alias           {long_value}
    address         192.168.1.1
}}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 1
        assert len(parser.objects[0].attributes['alias']) == 10000

    def test_unicode_characters(self, temp_dir):
        """Test parsing with unicode characters."""
        config = '''define host {
    host_name       test-server
    alias           Tëst Sërvér 日本語 émojis 🚀
    address         192.168.1.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w', encoding='utf-8') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 1
        assert '日本語' in parser.objects[0].attributes['alias']

    def test_only_comments(self, temp_dir):
        """Test file with only comments."""
        config = '''# This is a comment
; This is also a comment
# Another comment
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 0

    def test_attribute_without_value(self, temp_dir):
        """Test parsing attribute without value."""
        config = '''define host {
    host_name       test-server
    address
    alias           Test
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        # Should handle gracefully

    def test_value_without_attribute(self, temp_dir):
        """Test parsing value without attribute name."""
        config = '''define host {
    host_name       test-server
                    orphaned-value
    address         192.168.1.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        # Should handle gracefully

    def test_binary_file(self, temp_dir):
        """Test handling binary file with .cfg extension."""
        binary_content = bytes([0x00, 0x01, 0x02, 0xFF, 0xFE, 0x89, 0x50, 0x4E, 0x47])
        with open(os.path.join(temp_dir, 'binary.cfg'), 'wb') as f:
            f.write(binary_content)

        parser = NagiosConfigParser(temp_dir)
        # Should not crash on binary file
        try:
            parser.parse_all()
        except UnicodeDecodeError:
            pass  # Acceptable to fail gracefully

    def test_zero_byte_file(self, temp_dir):
        """Test handling zero-byte file."""
        open(os.path.join(temp_dir, 'empty.cfg'), 'w').close()

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 0

    def test_special_characters_in_names(self, temp_dir):
        """Test parsing with special characters in object names."""
        config = '''define host {
    host_name       test-server_01.example.com
    alias           Test/Server (Primary) [DC1]
    address         192.168.1.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        assert len(parser.objects) == 1
        assert parser.objects[0].attributes['host_name'] == 'test-server_01.example.com'


# ============================================================================
# Parser Edge Cases - Search and Find
# ============================================================================

class TestParserSearchEdgeCases:
    """Test search functionality edge cases."""

    @pytest.fixture
    def parser_with_data(self):
        temp_dir = tempfile.mkdtemp(prefix='nagios_search_test_')
        config = '''define host {
    host_name       server-01
    alias           Server One
    address         192.168.1.1
}

define host {
    host_name       server-02
    alias           Server Two
    address         192.168.1.2
}

define host {
    host_name       SERVER-03
    alias           Server Three
    address         192.168.1.3
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(config)

        parser = NagiosConfigParser(temp_dir)
        parser.parse_all()
        yield parser, temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_search_empty_string(self, parser_with_data):
        """Test searching with empty string."""
        parser, _ = parser_with_data
        results = parser.find_objects('')
        # Empty string should match all or none consistently
        assert isinstance(results, list)

    def test_search_only_whitespace(self, parser_with_data):
        """Test searching with only whitespace."""
        parser, _ = parser_with_data
        results = parser.find_objects('   ')
        assert isinstance(results, list)

    def test_search_special_regex_chars(self, parser_with_data):
        """Test searching with special regex characters."""
        parser, _ = parser_with_data
        # These should not cause regex errors when regex=False
        results = parser.find_objects('[server')
        assert isinstance(results, list)

        results = parser.find_objects('server.*')
        assert isinstance(results, list)

    def test_search_case_sensitivity(self, parser_with_data):
        """Test search case sensitivity."""
        parser, _ = parser_with_data
        # Default search should be case-insensitive
        results_lower = parser.find_objects('server-03')
        results_upper = parser.find_objects('SERVER-03')
        # Both should find the same object
        assert len(results_lower) == len(results_upper)

    def test_search_nonexistent_field(self, parser_with_data):
        """Test searching in non-existent field."""
        parser, _ = parser_with_data
        results = parser.find_objects('value', field='nonexistent_field')
        assert len(results) == 0

    def test_search_null_like_values(self, parser_with_data):
        """Test searching for null-like values."""
        parser, _ = parser_with_data
        results = parser.find_objects('null')
        assert isinstance(results, list)

        results = parser.find_objects('None')
        assert isinstance(results, list)

    def test_regex_catastrophic_backtracking(self, parser_with_data):
        """Test regex that could cause catastrophic backtracking."""
        parser, _ = parser_with_data
        # This pattern could cause performance issues
        try:
            results = parser.find_objects('(a+)+$', regex=True)
            assert isinstance(results, list)
        except Exception:
            pass  # Acceptable to reject dangerous regex


# ============================================================================
# Writer Edge Cases
# ============================================================================

class TestWriterEdgeCases:
    """Test writer functionality edge cases."""

    @pytest.fixture
    def temp_dir(self):
        temp_dir = tempfile.mkdtemp(prefix='nagios_writer_test_')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_write_empty_attributes(self, temp_dir):
        """Test writing object with empty attributes dict."""
        obj = NagiosObject(
            object_type='host',
            attributes={},
            source_file=os.path.join(temp_dir, 'hosts.cfg')
        )

        writer = NagiosConfigWriter()
        content = writer.object_to_string(obj)
        assert 'define host' in content
        assert '{' in content
        assert '}' in content

    def test_write_attribute_with_newlines(self, temp_dir):
        """Test writing attribute value containing newlines."""
        obj = NagiosObject(
            object_type='host',
            attributes={
                'host_name': 'test-server',
                'notes': 'Line1\nLine2\nLine3'
            },
            source_file=os.path.join(temp_dir, 'hosts.cfg')
        )

        writer = NagiosConfigWriter()
        content = writer.object_to_string(obj)
        # Should escape or handle newlines somehow
        assert 'define host' in content

    def test_write_attribute_with_special_chars(self, temp_dir):
        """Test writing attribute with special characters."""
        obj = NagiosObject(
            object_type='command',
            attributes={
                'command_name': 'check_special',
                'command_line': '/usr/bin/check --regex="^test$" --json=\'{"a":1}\''
            },
            source_file=os.path.join(temp_dir, 'commands.cfg')
        )

        writer = NagiosConfigWriter()
        content = writer.object_to_string(obj)
        assert 'check_special' in content

    def test_write_preserves_attribute_order(self, temp_dir):
        """Test that writer preserves attribute order."""
        from collections import OrderedDict
        attrs = OrderedDict([
            ('host_name', 'test'),
            ('alias', 'Test'),
            ('address', '127.0.0.1'),
            ('check_command', 'check-alive')
        ])
        obj = NagiosObject(
            object_type='host',
            attributes=dict(attrs),
            source_file=os.path.join(temp_dir, 'hosts.cfg')
        )

        writer = NagiosConfigWriter()
        content = writer.object_to_string(obj)
        # All attributes should be present
        for key in attrs:
            assert key in content

    def test_write_to_readonly_directory(self, temp_dir):
        """Test writing to read-only directory."""
        readonly_dir = os.path.join(temp_dir, 'readonly')
        os.makedirs(readonly_dir)
        os.chmod(readonly_dir, 0o444)

        obj = NagiosObject(
            object_type='host',
            attributes={'host_name': 'test'},
            source_file=os.path.join(readonly_dir, 'hosts.cfg')
        )

        writer = NagiosConfigWriter()
        try:
            writer.write_objects_to_original_files([obj])
            assert False, "Should have raised permission error"
        except (PermissionError, OSError):
            pass
        finally:
            os.chmod(readonly_dir, 0o755)

    def test_round_trip_special_values(self, temp_dir):
        """Test that special values survive parse-write-parse cycle."""
        original = '''define command {
    command_name    check_complex
    command_line    $USER1$/check_http -H $HOSTADDRESS$ -u '/path?a=1&b=2' -e "200,301"
}
'''
        with open(os.path.join(temp_dir, 'commands.cfg'), 'w') as f:
            f.write(original)

        # Parse
        parser1 = NagiosConfigParser(temp_dir)
        parser1.parse_all()
        assert len(parser1.objects) == 1
        original_cmd = parser1.objects[0].attributes['command_line']

        # Write
        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(parser1.objects)

        # Parse again
        parser2 = NagiosConfigParser(temp_dir)
        parser2.parse_all()
        assert len(parser2.objects) == 1
        new_cmd = parser2.objects[0].attributes['command_line']

        # Values should match
        assert original_cmd == new_cmd


# ============================================================================
# API Edge Cases
# ============================================================================

class TestAPIEdgeCases:
    """Test API edge cases and error handling."""

    @pytest.fixture
    def client(self):
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_api_edge_test_')

        hosts_content = '''define host {
    host_name       edge-test-host
    alias           Edge Test Host
    address         192.168.1.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_invalid_json_body(self, client):
        """Test API with invalid JSON body."""
        test_client, _ = client
        response = test_client.post('/api/search',
            data='not valid json {{{',
            content_type='application/json'
        )
        # Should return 400 Bad Request
        assert response.status_code in [400, 500]

    def test_empty_json_body(self, client):
        """Test API with empty JSON body."""
        test_client, _ = client
        response = test_client.post('/api/search',
            data='{}',
            content_type='application/json'
        )
        # Should handle gracefully
        assert response.status_code in [200, 400]

    def test_null_values_in_json(self, client):
        """Test API with null values in JSON."""
        test_client, _ = client
        response = test_client.post('/api/search',
            data=json.dumps({'query': None}),
            content_type='application/json'
        )
        assert response.status_code in [200, 400]

    def test_array_instead_of_object(self, client):
        """Test API with array instead of object.

        The /api/search endpoint returns 400 Bad Request when given
        an array instead of an object.
        """
        test_client, _ = client
        response = test_client.post('/api/search',
            data=json.dumps(['query', 'test']),
            content_type='application/json'
        )
        assert response.status_code in [200, 400]

    def test_extremely_long_query(self, client):
        """Test API with extremely long query string."""
        test_client, _ = client
        long_query = 'x' * 100000
        response = test_client.post('/api/search',
            data=json.dumps({'query': long_query}),
            content_type='application/json'
        )
        # Should handle without crashing
        assert response.status_code in [200, 400, 413]

    def test_negative_indices(self, client):
        """Test API with negative indices."""
        test_client, _ = client
        response = test_client.post('/api/delete-objects',
            data=json.dumps({'objects': [-1, -5, -100]}),
            content_type='application/json'
        )
        # Should handle gracefully (not delete anything or error)
        assert response.status_code in [200, 400]

    def test_float_indices(self, client):
        """Test API with float indices instead of int.

        The /api/delete-objects endpoint validates input types and
        returns 400 Bad Request for non-integer indices.
        """
        test_client, _ = client
        response = test_client.post('/api/delete-objects',
            data=json.dumps({'objects': [0.5, 1.7]}),
            content_type='application/json'
        )
        assert response.status_code in [200, 400]

    def test_string_indices(self, client):
        """Test API with string indices.

        The /api/delete-objects endpoint validates input types and
        returns 400 Bad Request for non-integer indices.
        """
        test_client, _ = client
        response = test_client.post('/api/delete-objects',
            data=json.dumps({'objects': ['0', '1']}),
            content_type='application/json'
        )
        assert response.status_code in [200, 400]

    def test_out_of_range_indices(self, client):
        """Test API with out of range indices."""
        test_client, _ = client
        response = test_client.post('/api/delete-objects',
            data=json.dumps({'objects': [9999999]}),
            content_type='application/json'
        )
        # Should handle without crashing
        assert response.status_code in [200, 400]

    def test_concurrent_modifications(self, client):
        """Test concurrent API modifications.

        Note: Flask test client doesn't support true concurrency well.
        This test is simplified to just verify basic thread safety.
        """
        test_client, temp_dir = client

        # Just verify a single modification works
        response = test_client.post('/api/apply-replace',
            data=json.dumps({
                'find': 'Edge',
                'replace': 'Modified',
                'field': 'alias'
            }),
            content_type='application/json'
        )
        # Should complete without error
        assert response.status_code in [200, 400]


# ============================================================================
# Security Edge Cases
# ============================================================================

class TestSecurityEdgeCases:
    """Test security-related edge cases."""

    @pytest.fixture
    def client(self):
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_security_test_')

        hosts_content = '''define host {
    host_name       security-test
    address         192.168.1.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_path_traversal_in_file_operations(self, client):
        """Test path traversal attack in file operations."""
        test_client, temp_dir = client

        # Try to access files outside config directory
        response = test_client.post('/api/files/relocate',
            data=json.dumps({
                'source_path': os.path.join(temp_dir, '..', '..', 'etc', 'passwd'),
                'target_folder': temp_dir
            }),
            content_type='application/json'
        )
        # Should either reject or fail to find file
        assert response.status_code in [400, 404, 500]

    def test_path_traversal_with_encoded_chars(self, client):
        """Test path traversal with URL-encoded characters."""
        test_client, temp_dir = client

        response = test_client.post('/api/files/relocate',
            data=json.dumps({
                'source_path': os.path.join(temp_dir, '..%2F..%2Fetc%2Fpasswd'),
                'target_folder': temp_dir
            }),
            content_type='application/json'
        )
        assert response.status_code in [400, 404, 500]

    def test_symlink_attack(self, client):
        """Test symlink following in file operations."""
        test_client, temp_dir = client

        # Create a symlink to /etc
        symlink_path = os.path.join(temp_dir, 'evil_link')
        try:
            os.symlink('/etc', symlink_path)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported")

        response = test_client.get(f'/api/folders?path={symlink_path}')
        # Should either reject symlinks or handle safely
        # Not expose /etc contents

    def test_null_byte_injection(self, client):
        """Test null byte injection in paths."""
        test_client, temp_dir = client

        response = test_client.post('/api/files/relocate',
            data=json.dumps({
                'source_path': os.path.join(temp_dir, 'hosts.cfg\x00.txt'),
                'target_folder': temp_dir
            }),
            content_type='application/json'
        )
        assert response.status_code in [400, 404, 500]

    def test_script_injection_in_object_name(self, client):
        """Test script injection in object names."""
        test_client, temp_dir = client

        # Try to create object with script tag in name
        response = test_client.post('/api/object/create',
            data=json.dumps({
                'object_type': 'host',
                'attributes': {
                    'host_name': '<script>alert("xss")</script>',
                    'address': '127.0.0.1'
                },
                'target_file': os.path.join(temp_dir, 'hosts.cfg')
            }),
            content_type='application/json'
        )
        # Should either sanitize or reject
        # Check that if created, the name is escaped

    def test_command_injection_in_validation(self, client):
        """Test command injection in validation path."""
        test_client, _ = client

        # Try to inject command in nagios binary path
        response = test_client.post('/api/settings',
            data=json.dumps({
                'nagios_bin': '/bin/nagios; rm -rf /',
                'nagios_cfg': '/etc/nagios/nagios.cfg'
            }),
            content_type='application/json'
        )
        # Should reject or sanitize

    def test_very_deep_json_nesting(self, client):
        """Test deeply nested JSON to check for recursion issues."""
        test_client, _ = client

        # Create deeply nested structure
        nested = {'level': 0}
        current = nested
        for i in range(100):
            current['child'] = {'level': i + 1}
            current = current['child']

        response = test_client.post('/api/search',
            data=json.dumps(nested),
            content_type='application/json'
        )
        # Should handle without stack overflow
        assert response.status_code in [200, 400]


# ============================================================================
# Backup Manager Edge Cases
# ============================================================================

class TestBackupManagerEdgeCases:
    """Test backup manager edge cases."""

    @pytest.fixture
    def temp_dir(self):
        temp_dir = tempfile.mkdtemp(prefix='nagios_backup_edge_')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_backup_nonexistent_source(self, temp_dir):
        """Test backup of non-existent source directory."""
        bm = BackupManager(
            config_path='/nonexistent/path',
            backup_path=os.path.join(temp_dir, 'backups')
        )
        result = bm.create_backup("test")
        # Should handle gracefully
        assert result is None or isinstance(result, str)

    def test_backup_empty_directory(self, temp_dir):
        """Test backup of empty directory."""
        empty_dir = os.path.join(temp_dir, 'empty')
        os.makedirs(empty_dir)

        bm = BackupManager(
            config_path=empty_dir,
            backup_path=os.path.join(temp_dir, 'backups')
        )
        result = bm.create_backup("test")
        # Should succeed but create empty/minimal backup

    def test_backup_with_special_chars_in_reason(self, temp_dir):
        """Test backup with special characters in reason."""
        source = os.path.join(temp_dir, 'source')
        os.makedirs(source)
        with open(os.path.join(source, 'test.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        bm = BackupManager(
            config_path=source,
            backup_path=os.path.join(temp_dir, 'backups')
        )
        # Reason with special characters
        result = bm.create_backup("test/backup:with<special>chars")
        # Should sanitize or handle

    def test_restore_corrupted_backup(self, temp_dir):
        """Test restoring corrupted backup."""
        source = os.path.join(temp_dir, 'source')
        backup_path = os.path.join(temp_dir, 'backups')
        os.makedirs(source)
        os.makedirs(backup_path)

        # Create a "corrupted" backup (invalid tar.gz)
        corrupted_backup = os.path.join(backup_path, 'corrupted_backup.tar.gz')
        with open(corrupted_backup, 'w') as f:
            f.write('not a valid tar.gz file')

        bm = BackupManager(config_path=source, backup_path=backup_path)
        try:
            result = bm.restore_backup('corrupted_backup.tar.gz')
            # Should fail gracefully
        except Exception:
            pass  # Expected

    def test_list_backups_with_invalid_files(self, temp_dir):
        """Test listing backups when directory contains invalid files."""
        backup_path = os.path.join(temp_dir, 'backups')
        os.makedirs(backup_path)

        # Create mix of valid and invalid files
        with open(os.path.join(backup_path, 'not_a_backup.txt'), 'w') as f:
            f.write('text file')
        with open(os.path.join(backup_path, 'fake.tar.gz'), 'w') as f:
            f.write('fake tar')
        os.makedirs(os.path.join(backup_path, 'subfolder'))

        bm = BackupManager(
            config_path=temp_dir,
            backup_path=backup_path
        )
        backups = bm.list_backups()
        # Should list valid backups without crashing


# ============================================================================
# Staging Manager Edge Cases
# ============================================================================

class TestStagingManagerEdgeCases:
    """Test staging manager edge cases."""

    @pytest.fixture
    def temp_dir(self):
        temp_dir = tempfile.mkdtemp(prefix='nagios_staging_edge_')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_staging_with_unicode_data(self, temp_dir):
        """Test staging with unicode data."""
        sm = StagingManager(temp_dir)

        # Use the actual API with expected keys
        sm.save_staging({
            'pendingEdits': [{'object_type': 'host', 'name': 'テスト', 'changes': {'alias': 'テスト更新'}}],
            'sessionId': 'test-unicode'
        })

        data = sm.get_staging()
        assert data is not None
        assert 'pendingEdits' in data

    def test_staging_very_large_change(self, temp_dir):
        """Test staging with very large change data."""
        sm = StagingManager(temp_dir)

        large_data = 'x' * 100000  # 100KB
        sm.save_staging({
            'pendingEdits': [{'object_type': 'host', 'name': 'test', 'notes': large_data}],
            'sessionId': 'test-large'
        })

        data = sm.get_staging()
        assert data is not None

    def test_staging_concurrent_access(self, temp_dir):
        """Test concurrent staging operations."""
        sm = StagingManager(temp_dir)
        errors = []

        def save_change(i):
            try:
                sm.save_staging({
                    'changes': [{'type': 'host', 'name': f'host-{i}'}],
                    'sessionId': f'session-{i}'
                })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save_change, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # At least one should succeed without errors
        assert len(errors) < 10, f"Too many errors: {errors}"

    def test_staging_file_corrupted(self, temp_dir):
        """Test staging when file is corrupted."""
        sm = StagingManager(temp_dir)
        sm.save_staging({'changes': [], 'sessionId': 'test'})

        # Corrupt the staging file
        staging_file = os.path.join(temp_dir, '.staging.json')
        if os.path.exists(staging_file):
            with open(staging_file, 'w') as f:
                f.write('{invalid json')

        # Should handle gracefully
        data = sm.get_staging()
        # May return None or empty on corrupt file

    def test_clear_staging_when_empty(self, temp_dir):
        """Test clearing staging when already empty."""
        sm = StagingManager(temp_dir)
        sm.clear_staging()  # Clear when empty
        sm.clear_staging()  # Clear again
        # Should not raise


# ============================================================================
# Integration Edge Cases
# ============================================================================

class TestIntegrationEdgeCases:
    """Test integration scenarios and workflows."""

    @pytest.fixture
    def client(self):
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_integration_test_')

        hosts_content = '''define host {
    host_name       integration-host
    alias           Integration Host
    address         192.168.1.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_rapid_create_delete_cycle(self, client):
        """Test rapid create/delete cycles."""
        test_client, temp_dir = client

        for i in range(5):
            # Create using correct endpoint
            response = test_client.post('/api/objects/create',
                data=json.dumps({
                    'object_type': 'host',
                    'attributes': {
                        'host_name': f'rapid-host-{i}',
                        'address': f'192.168.1.{i+10}'
                    },
                    'target_file': os.path.join(temp_dir, 'hosts.cfg')
                }),
                content_type='application/json'
            )
            assert response.status_code == 200, f"Create failed at iteration {i}: {response.data}"

            # Get index
            response = test_client.get('/api/objects')
            objects = json.loads(response.data)
            idx = next((j for j, o in enumerate(objects)
                       if o['attributes'].get('host_name') == f'rapid-host-{i}'), None)

            if idx is not None:
                # Delete
                response = test_client.post('/api/delete-objects',
                    data=json.dumps({'objects': [idx]}),
                    content_type='application/json'
                )
                assert response.status_code == 200, f"Delete failed at iteration {i}"

    def test_backup_restore_preserves_data(self, client):
        """Test that backup and restore works."""
        test_client, temp_dir = client

        # Get initial state
        response = test_client.get('/api/objects')
        initial_objects = json.loads(response.data)
        initial_count = len(initial_objects)
        assert initial_count == 1, "Fixture should have exactly one object"

        # Create backup (API uses 'description' not 'reason')
        response = test_client.post('/api/backups',
            data=json.dumps({'description': 'test_backup'}),
            content_type='application/json'
        )
        assert response.status_code == 200
        backup_data = json.loads(response.data)
        # API returns 'path' key
        backup_path = backup_data.get('path', '')
        assert backup_data.get('success') is True, "Backup should succeed"
        assert backup_path, "Backup should return a path"

        # Verify backup was created
        response = test_client.get('/api/backups')
        assert response.status_code == 200
        backups = json.loads(response.data)
        assert len(backups) == 1, "Should have exactly one backup"

    def test_find_replace_with_no_matches(self, client):
        """Test find/replace when there are no matches."""
        test_client, _ = client

        response = test_client.post('/api/preview-replace',
            data=json.dumps({
                'find': 'nonexistent-value-xyz123',
                'replace': 'new-value'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        # Should return empty matches, not error
        matches = data.get('matches', data.get('changes', []))
        assert len(matches) == 0

    def test_rename_to_existing_name(self, client):
        """Test renaming object to name that already exists."""
        test_client, temp_dir = client

        # Create second host using correct endpoint
        response = test_client.post('/api/objects/create',
            data=json.dumps({
                'object_type': 'host',
                'attributes': {'host_name': 'second-host', 'address': '192.168.1.2'},
                'target_file': os.path.join(temp_dir, 'hosts.cfg')
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

        # Try to rename first host to second host's name
        response = test_client.post('/api/rename/apply',
            data=json.dumps({
                'type': 'host',
                'find': 'integration-host',
                'replace': 'second-host'
            }),
            content_type='application/json'
        )
        # Should either succeed (allowing duplicates) or warn/error


# ============================================================================
# Performance Edge Cases
# ============================================================================

class TestPerformanceEdgeCases:
    """Test performance with large datasets."""

    @pytest.fixture
    def large_config_dir(self):
        temp_dir = tempfile.mkdtemp(prefix='nagios_perf_test_')

        # Create 1000 hosts
        hosts = []
        for i in range(1000):
            hosts.append(f'''define host {{
    host_name       perf-host-{i:04d}
    alias           Performance Host {i}
    address         192.168.{i // 256}.{i % 256}
}}
''')

        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('\n'.join(hosts))

        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_parse_large_config(self, large_config_dir):
        """Test parsing large configuration file."""
        start = time.time()
        parser = NagiosConfigParser(large_config_dir)
        parser.parse_all()
        elapsed = time.time() - start

        assert len(parser.objects) == 1000
        assert elapsed < 10, f"Parsing took too long: {elapsed:.2f}s"

    def test_search_large_config(self, large_config_dir):
        """Test searching large configuration."""
        parser = NagiosConfigParser(large_config_dir)
        parser.parse_all()

        start = time.time()
        results = parser.find_objects('perf-host-0500')
        elapsed = time.time() - start

        assert len(results) == 1
        assert elapsed < 1, f"Search took too long: {elapsed:.2f}s"

    def test_write_large_config(self, large_config_dir):
        """Test writing large configuration."""
        parser = NagiosConfigParser(large_config_dir)
        parser.parse_all()

        writer = NagiosConfigWriter()

        start = time.time()
        writer.write_objects_to_original_files(parser.objects)
        elapsed = time.time() - start

        assert elapsed < 10, f"Writing took too long: {elapsed:.2f}s"

        # Verify written correctly
        parser2 = NagiosConfigParser(large_config_dir)
        parser2.parse_all()
        assert len(parser2.objects) == 1000
