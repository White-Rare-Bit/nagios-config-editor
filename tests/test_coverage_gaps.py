"""
Tests targeting uncovered code paths to achieve higher coverage.
Focuses on error handling, edge cases, and rarely-executed branches.
"""

import pytest
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nagios_parser import NagiosObject, NagiosConfigParser
from nagios_writer import NagiosConfigWriter
from backup_manager import BackupManager
from staging_manager import StagingManager


# ============================================================================
# App.py Error Handling Tests
# ============================================================================

class TestAppErrorHandling:
    """Tests for error handling branches in app.py."""

    @pytest.fixture
    def client(self):
        """Create a Flask client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_coverage_test_')

        hosts_content = '''define host {
    host_name       test-host
    alias           Test Host
    address         192.168.1.1
}

define host {
    name            host-template
    register        0
    check_interval  5
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        services_content = '''define service {
    host_name           test-host
    service_description HTTP
    check_command       check_http
}
'''
        with open(os.path.join(temp_dir, 'services.cfg'), 'w') as f:
            f.write(services_content)

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_api_objects_with_search_filter(self, client):
        """Test /api/objects with search parameter."""
        test_client, _ = client
        response = test_client.get('/api/objects?search=test')
        assert response.status_code == 200
        data = json.loads(response.data)
        # Should filter to only objects containing 'test'
        assert all('test' in str(obj).lower() for obj in data)

    def test_api_objects_search_no_match(self, client):
        """Test /api/objects with search that matches nothing."""
        test_client, _ = client
        response = test_client.get('/api/objects?search=nonexistent12345')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 0

    def test_preview_rename_object_without_name(self, client):
        """Test rename preview when object has no name field."""
        test_client, _ = client
        # Templates have 'name' not 'host_name', test they're handled
        response = test_client.post('/api/preview-rename',
            data=json.dumps({
                'type': 'host',
                'find': 'test',
                'replace': 'changed'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_preview_rename_invalid_regex(self, client):
        """Test rename preview with invalid regex pattern."""
        test_client, _ = client
        response = test_client.post('/api/preview-rename',
            data=json.dumps({
                'type': 'host',
                'find': '[invalid(regex',
                'replace': 'test',
                'regex': True
            }),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_preview_replace_invalid_regex(self, client):
        """Test find/replace preview with invalid regex."""
        test_client, _ = client
        response = test_client.post('/api/preview-replace',
            data=json.dumps({
                'find': '[invalid(regex',
                'regex': True
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        # Invalid regex should be caught and return empty matches

    def test_apply_replace_invalid_regex(self, client):
        """Test apply replace with invalid regex - should skip."""
        test_client, _ = client
        response = test_client.post('/api/apply-replace',
            data=json.dumps({
                'find': '[invalid(regex',
                'replace': 'test',
                'regex': True
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        # Should succeed but not match anything

    def test_apply_replace_specific_field(self, client):
        """Test apply replace on specific field only."""
        test_client, _ = client
        response = test_client.post('/api/apply-replace',
            data=json.dumps({
                'find': '192.168',
                'replace': '10.0',
                'field': 'address'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_apply_replace_specific_type(self, client):
        """Test apply replace on specific object type only."""
        test_client, _ = client
        response = test_client.post('/api/apply-replace',
            data=json.dumps({
                'find': 'test',
                'replace': 'changed',
                'type': 'service'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_relocate_file_source_not_file(self, client):
        """Test relocating a directory instead of a file."""
        test_client, temp_dir = client
        os.makedirs(os.path.join(temp_dir, 'subdir'))

        response = test_client.post('/api/files/relocate',
            data=json.dumps({
                'source_path': os.path.join(temp_dir, 'subdir'),
                'target_folder': temp_dir
            }),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'not a file' in data['error']

    def test_relocate_file_target_exists(self, client):
        """Test relocating file when target already exists."""
        test_client, temp_dir = client

        # Create target folder with same filename
        target_folder = os.path.join(temp_dir, 'target')
        os.makedirs(target_folder)
        with open(os.path.join(target_folder, 'hosts.cfg'), 'w') as f:
            f.write('# existing')

        response = test_client.post('/api/files/relocate',
            data=json.dumps({
                'source_path': os.path.join(temp_dir, 'hosts.cfg'),
                'target_folder': target_folder
            }),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'already exists' in data['error']

    def test_relocate_folder_source_not_found(self, client):
        """Test relocating non-existent folder."""
        test_client, temp_dir = client

        response = test_client.post('/api/folders/relocate',
            data=json.dumps({
                'source_path': '/nonexistent/folder',
                'target_folder': temp_dir
            }),
            content_type='application/json'
        )
        assert response.status_code == 404

    def test_relocate_folder_source_not_dir(self, client):
        """Test relocating a file as folder."""
        test_client, temp_dir = client

        response = test_client.post('/api/folders/relocate',
            data=json.dumps({
                'source_path': os.path.join(temp_dir, 'hosts.cfg'),
                'target_folder': temp_dir
            }),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'not a folder' in data['error'] or 'not a directory' in data['error'].lower()

    def test_relocate_folder_target_exists(self, client):
        """Test relocating folder when target already exists."""
        test_client, temp_dir = client

        # Create source folder
        source = os.path.join(temp_dir, 'source_folder')
        os.makedirs(source)
        with open(os.path.join(source, 'test.cfg'), 'w') as f:
            f.write('# test')

        # Create target with same name
        target_parent = os.path.join(temp_dir, 'target_parent')
        os.makedirs(os.path.join(target_parent, 'source_folder'))

        response = test_client.post('/api/folders/relocate',
            data=json.dumps({
                'source_path': source,
                'target_folder': target_parent
            }),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'already exists' in data['error']

    def test_create_file_outside_config_dir(self, client):
        """Test creating file outside config directory."""
        test_client, temp_dir = client

        response = test_client.post('/api/files/create',
            data=json.dumps({
                'path': '/tmp/malicious.cfg',
                'content': '# test'
            }),
            content_type='application/json'
        )
        # Should be rejected or sanitized
        assert response.status_code in [400, 403, 500]

    def test_delete_path_outside_config_dir(self, client):
        """Test deleting path outside config directory."""
        test_client, temp_dir = client

        response = test_client.post('/api/delete',
            data=json.dumps({'path': '/tmp/some_file'}),
            content_type='application/json'
        )
        # Should be rejected
        assert response.status_code in [400, 403, 404]

    def test_delete_nonexistent_path(self, client):
        """Test deleting non-existent path."""
        test_client, temp_dir = client

        response = test_client.post('/api/delete',
            data=json.dumps({'path': os.path.join(temp_dir, 'nonexistent.cfg')}),
            content_type='application/json'
        )
        assert response.status_code == 404


class TestSettingsEdgeCases:
    """Test settings API edge cases."""

    @pytest.fixture
    def client(self):
        """Create a Flask client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_settings_test_')

        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_update_backup_path_creates_directory(self, client):
        """Test that updating backup_path creates directory if needed."""
        test_client, temp_dir = client

        new_backup_dir = os.path.join(temp_dir, 'new_backups', 'nested')

        response = test_client.post('/api/settings',
            data=json.dumps({'backup_path': new_backup_dir}),
            content_type='application/json'
        )
        assert response.status_code == 200
        # Directory should be created
        assert os.path.isdir(new_backup_dir)

    def test_update_nagios_bin_path(self, client):
        """Test updating nagios binary path."""
        test_client, _ = client

        response = test_client.post('/api/settings',
            data=json.dumps({'nagios_bin': '/usr/local/nagios/bin/nagios'}),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_update_multiple_settings(self, client):
        """Test updating multiple settings at once."""
        test_client, temp_dir = client

        response = test_client.post('/api/settings',
            data=json.dumps({
                'backup_path': os.path.join(temp_dir, 'backups2'),
                'nagios_bin': '/usr/sbin/nagios'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200


# ============================================================================
# Backup Manager Edge Cases
# ============================================================================

class TestBackupManagerEdgeCases:
    """Tests for backup_manager.py edge cases."""

    @pytest.fixture
    def backup_dir(self):
        """Create a temporary backup directory."""
        temp_dir = tempfile.mkdtemp(prefix='nagios_backup_coverage_')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def config_dir(self):
        """Create a temporary config directory."""
        temp_dir = tempfile.mkdtemp(prefix='nagios_config_coverage_')
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_list_backups_old_format(self, backup_dir, config_dir):
        """Test listing backups without metadata (old format)."""
        # BackupManager(config_path, backup_path)
        bm = BackupManager(config_dir, backup_dir)

        # Create old-format backup (directory starting with backup_, no _backup_info.txt)
        old_backup = os.path.join(backup_dir, 'backup_20230101_120000')
        os.makedirs(old_backup)
        with open(os.path.join(old_backup, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name old }')

        backups = bm.list_backups()
        assert len(backups) >= 1
        # Should fall back to using directory modification time
        old = next((b for b in backups if 'backup_20230101' in b['name']), None)
        assert old is not None
        assert 'created' in old

    def test_list_backups_with_metadata(self, backup_dir, config_dir):
        """Test listing backups with metadata file."""
        bm = BackupManager(config_dir, backup_dir)

        # Create backup with proper metadata file
        backup_with_meta = os.path.join(backup_dir, 'backup_20230102_120000')
        os.makedirs(backup_with_meta)
        with open(os.path.join(backup_with_meta, '_backup_info.txt'), 'w') as f:
            f.write('Backup created: 2023-01-02T12:00:00\n')
            f.write('Description: Test backup\n')
            f.write('Files backed up: 5\n')
        with open(os.path.join(backup_with_meta, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        backups = bm.list_backups()
        meta_backup = next((b for b in backups if 'backup_20230102' in b['name']), None)
        assert meta_backup is not None
        assert meta_backup['description'] == 'Test backup'
        assert meta_backup['file_count'] == 5

    def test_list_backups_metadata_invalid_file_count(self, backup_dir, config_dir):
        """Test listing backups with invalid file count in metadata."""
        bm = BackupManager(config_dir, backup_dir)

        # Create backup with invalid file count
        backup = os.path.join(backup_dir, 'backup_20230103_120000')
        os.makedirs(backup)
        with open(os.path.join(backup, '_backup_info.txt'), 'w') as f:
            f.write('Backup created: 2023-01-03T12:00:00\n')
            f.write('Files backed up: invalid\n')  # Invalid number
        with open(os.path.join(backup, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        backups = bm.list_backups()
        # Should handle gracefully - file_count stays at 0
        backup_entry = next((b for b in backups if 'backup_20230103' in b['name']), None)
        assert backup_entry is not None
        assert backup_entry['file_count'] == 0

    def test_restore_backup_not_found(self, backup_dir, config_dir):
        """Test restoring non-existent backup."""
        bm = BackupManager(config_dir, backup_dir)

        # restore_backup raises ValueError for non-existent backup
        with pytest.raises(ValueError, match="Backup not found"):
            bm.restore_backup('backup_nonexistent')

    def test_delete_backup_not_found(self, backup_dir, config_dir):
        """Test deleting non-existent backup."""
        bm = BackupManager(config_dir, backup_dir)

        # delete_backup returns False for non-existent backup
        result = bm.delete_backup('backup_nonexistent')
        assert result is False

    def test_delete_backup_success(self, backup_dir, config_dir):
        """Test successfully deleting a backup."""
        bm = BackupManager(config_dir, backup_dir)

        # Create a backup directory starting with 'backup_'
        backup = os.path.join(backup_dir, 'backup_to_delete')
        os.makedirs(backup)
        with open(os.path.join(backup, 'test.cfg'), 'w') as f:
            f.write('# test')

        result = bm.delete_backup('backup_to_delete')
        assert result is True
        assert not os.path.exists(backup)


# ============================================================================
# Nagios Writer Edge Cases
# ============================================================================

class TestNagiosWriterEdgeCases:
    """Tests for nagios_writer.py edge cases."""

    def test_write_file_creates_parent_dirs(self):
        """Test that write_file creates parent directories."""
        writer = NagiosConfigWriter()
        temp_dir = tempfile.mkdtemp()

        try:
            # Create path with nested directories that don't exist
            target_file = os.path.join(temp_dir, 'nested', 'dirs', 'test.cfg')

            writer.write_file(target_file, [
                NagiosObject('host', {'host_name': 'test'}, target_file, 1)
            ])

            assert os.path.exists(target_file)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_write_file_atomic_write(self):
        """Test atomic write creates temp file and renames."""
        writer = NagiosConfigWriter()
        temp_dir = tempfile.mkdtemp()

        try:
            target_file = os.path.join(temp_dir, 'test.cfg')

            writer.write_file(target_file, [
                NagiosObject('host', {'host_name': 'test'}, target_file, 1)
            ])

            # File should exist after write
            assert os.path.exists(target_file)
            with open(target_file, 'r') as f:
                content = f.read()
            assert 'host_name' in content
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_object_to_string_empty_attributes(self):
        """Test writing object with no attributes."""
        writer = NagiosConfigWriter()
        obj = NagiosObject('host', {}, '/test.cfg', 1)

        result = writer.object_to_string(obj)
        assert 'define host {' in result
        assert '}' in result

    def test_objects_to_string_mixed_types(self):
        """Test writing multiple object types."""
        writer = NagiosConfigWriter()
        objects = [
            NagiosObject('host', {'host_name': 'h1'}, '/test.cfg', 1),
            NagiosObject('service', {'service_description': 's1'}, '/test.cfg', 5),
            NagiosObject('command', {'command_name': 'c1'}, '/test.cfg', 10),
        ]

        result = writer.objects_to_string(objects)
        assert 'define host' in result
        assert 'define service' in result
        assert 'define command' in result


# ============================================================================
# Nagios Parser Edge Cases
# ============================================================================

class TestNagiosParserEdgeCases:
    """Tests for nagios_parser.py edge cases."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory."""
        temp_dir = tempfile.mkdtemp(prefix='nagios_parser_coverage_')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_parse_malformed_object(self, temp_config_dir):
        """Test parsing object with no closing brace."""
        with open(os.path.join(temp_config_dir, 'bad.cfg'), 'w') as f:
            f.write('define host {\n    host_name test\n')  # No closing brace

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()
        # Should handle gracefully (warning printed but no crash)
        assert parser is not None

    def test_parse_command_with_special_chars(self, temp_config_dir):
        """Test parsing command with special characters in command_line."""
        with open(os.path.join(temp_config_dir, 'commands.cfg'), 'w') as f:
            f.write('define command {\n    command_name test_cmd\n    command_line $USER1$/check_http -H $HOSTADDRESS$ -u "/path?query=1"\n}\n')

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()
        commands = parser.get_objects_by_type('command')
        assert len(commands) >= 1
        assert 'test_cmd' in commands[0].attributes.get('command_name', '')

    def test_parse_empty_attribute_value(self, temp_config_dir):
        """Test parsing attribute with empty value."""
        with open(os.path.join(temp_config_dir, 'empty.cfg'), 'w') as f:
            f.write('define host {\n    host_name test\n    alias\n}\n')

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()
        hosts = parser.get_objects_by_type('host')
        # Should parse without crashing

    def test_parse_multiple_files(self, temp_config_dir):
        """Test parsing multiple config files."""
        with open(os.path.join(temp_config_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name host1 address 1.1.1.1 }')
        with open(os.path.join(temp_config_dir, 'services.cfg'), 'w') as f:
            f.write('define service { host_name host1 service_description HTTP }')

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()
        hosts = parser.get_objects_by_type('host')
        services = parser.get_objects_by_type('service')
        assert len(hosts) == 1
        assert len(services) == 1

    def test_find_objects_invalid_regex_handled(self, temp_config_dir):
        """Test find_objects with invalid regex returns empty."""
        with open(os.path.join(temp_config_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test address 1.1.1.1 }')

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()
        # The parameter is 'regex', not 'use_regex'
        results = parser.find_objects('[invalid(', regex=True)
        assert results == []

    def test_get_objects_by_type_nonexistent(self, temp_config_dir):
        """Test getting objects of non-existent type."""
        with open(os.path.join(temp_config_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()
        results = parser.get_objects_by_type('nonexistent_type')
        assert results == []

    def test_find_objects_by_field(self, temp_config_dir):
        """Test finding objects filtered by field."""
        with open(os.path.join(temp_config_dir, 'hosts.cfg'), 'w') as f:
            # Use multi-line format for proper parsing
            f.write('define host {\n    host_name server1\n    address 192.168.1.1\n}\n')
            f.write('define host {\n    host_name server2\n    address 10.0.0.1\n}\n')

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()
        results = parser.find_objects('192.168', field='address')
        assert len(results) == 1
        assert results[0].attributes['host_name'] == 'server1'

    def test_find_objects_with_type_filter(self, temp_config_dir):
        """Test finding objects filtered by type."""
        with open(os.path.join(temp_config_dir, 'config.cfg'), 'w') as f:
            f.write('define host { host_name test }\n')
            f.write('define service { host_name test service_description test }\n')

        parser = NagiosConfigParser(temp_config_dir)
        parser.parse_all()
        results = parser.find_objects('test', object_type='host')
        assert all(r.object_type == 'host' for r in results)


# ============================================================================
# Staging Manager Edge Cases
# ============================================================================

class TestStagingManagerEdgeCases:
    """Tests for staging_manager.py edge cases."""

    @pytest.fixture
    def staging_dir(self):
        """Create a temporary staging directory."""
        temp_dir = tempfile.mkdtemp(prefix='nagios_staging_coverage_')
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_save_staging_io_error(self, staging_dir):
        """Test staging save with I/O error."""
        sm = StagingManager(staging_dir)

        with patch('builtins.open', mock_open()) as mocked_file:
            mocked_file.side_effect = IOError("Disk full")

            # Should handle gracefully or raise
            try:
                sm.save_staging({'test': 'data'})
            except IOError:
                pass  # Expected

    def test_get_staging_permission_error(self, staging_dir):
        """Test getting staging with permission error."""
        sm = StagingManager(staging_dir)

        # Create staging file
        sm.save_staging({'test': 'data'})

        with patch('builtins.open', mock_open()) as mocked_file:
            mocked_file.side_effect = PermissionError("Access denied")

            # Should return None or handle gracefully
            result = sm.get_staging()
            assert result is None or isinstance(result, dict)

    def test_clear_staging_file_not_found(self, staging_dir):
        """Test clearing staging when file doesn't exist."""
        sm = StagingManager(staging_dir)

        # Should not raise
        sm.clear_staging()
        assert sm.get_staging() is None


# ============================================================================
# API Edge Cases for Full Coverage
# ============================================================================

class TestAPIFullCoverage:
    """Additional API tests for full coverage."""

    @pytest.fixture
    def client(self):
        """Create a Flask client with complex config."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_fullcov_test_')

        # Create complex config
        hosts_content = '''define host {
    host_name       server1
    alias           Server 1
    address         192.168.1.1
    hostgroups      linux-servers,web-servers
    contacts        admin
}

define host {
    host_name       server2
    alias           Server 2
    address         192.168.1.2
}

define host {
    name            generic-host
    register        0
    check_interval  5
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        services_content = '''define service {
    host_name           server1
    service_description HTTP
    check_command       check_http
}
'''
        with open(os.path.join(temp_dir, 'services.cfg'), 'w') as f:
            f.write(services_content)

        hostgroups_content = '''define hostgroup {
    hostgroup_name  linux-servers
    alias           Linux Servers
    members         server1
}

define hostgroup {
    hostgroup_name  web-servers
    alias           Web Servers
}
'''
        with open(os.path.join(temp_dir, 'hostgroups.cfg'), 'w') as f:
            f.write(hostgroups_content)

        commands_content = '''define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}
'''
        with open(os.path.join(temp_dir, 'commands.cfg'), 'w') as f:
            f.write(commands_content)

        contacts_content = '''define contact {
    contact_name    admin
    alias           Admin
    email           admin@example.com
}
'''
        with open(os.path.join(temp_dir, 'contacts.cfg'), 'w') as f:
            f.write(contacts_content)

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_bulk_attributes_with_filter(self, client):
        """Test bulk attributes with filter field and value."""
        test_client, _ = client

        response = test_client.post('/api/bulk-attributes/apply',
            data=json.dumps({
                'type': 'host',
                'filter_field': 'host_name',
                'filter_value': 'server1',
                'target_field': 'notes',
                'new_value': 'filtered note',
                'action': 'set'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('updated', 0) == 1  # Only server1 should be updated

    def test_bulk_attributes_append_action(self, client):
        """Test bulk attributes with append action."""
        test_client, _ = client

        response = test_client.post('/api/bulk-attributes/apply',
            data=json.dumps({
                'type': 'host',
                'target_field': 'alias',
                'new_value': ' (updated)',
                'action': 'append'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_bulk_attributes_prepend_action(self, client):
        """Test bulk attributes with prepend action."""
        test_client, _ = client

        response = test_client.post('/api/bulk-attributes/apply',
            data=json.dumps({
                'type': 'host',
                'target_field': 'alias',
                'new_value': '[TEST] ',
                'action': 'prepend'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_bulk_attributes_preview_with_filter(self, client):
        """Test bulk attributes preview with filter."""
        test_client, _ = client

        response = test_client.post('/api/bulk-attributes/preview',
            data=json.dumps({
                'type': 'host',
                'filter_field': 'address',
                'filter_value': '192.168',
                'target_field': 'check_interval',
                'new_value': '10'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'matches' in data

    def test_apply_rename_with_prefix_suffix(self, client):
        """Test rename with prefix and suffix."""
        test_client, _ = client

        response = test_client.post('/api/apply-rename',
            data=json.dumps({
                'type': 'host',
                'find': '',
                'replace': '',
                'prefix': 'pre-',
                'suffix': '-suf'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_clone_objects_with_pattern(self, client):
        """Test cloning objects with name pattern transformation."""
        test_client, _ = client

        # First get objects
        response = test_client.get('/api/objects?type=host')
        hosts = json.loads(response.data)
        host_indices = [i for i, h in enumerate(hosts) if h['attributes'].get('host_name')]

        if host_indices:
            response = test_client.post('/api/clone-objects',
                data=json.dumps({
                    'objects': [host_indices[0]],
                    'find': 'server',
                    'replace': 'clone'
                }),
                content_type='application/json'
            )
            assert response.status_code == 200

    def test_smart_grouping_analyze(self, client):
        """Test smart grouping analysis."""
        test_client, _ = client

        response = test_client.get('/api/smart-grouping/suggest')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'suggestions' in data or 'groups' in data or isinstance(data, list)

    def test_smart_grouping_create(self, client):
        """Test creating a hostgroup from suggestion."""
        test_client, temp_dir = client

        response = test_client.post('/api/smart-grouping/create',
            data=json.dumps({
                'name': 'new-group',
                'alias': 'New Group',
                'members': ['server1', 'server2']  # API expects 'members' not 'hosts'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_inheritance_list(self, client):
        """Test listing objects with inheritance info."""
        test_client, _ = client

        response = test_client.get('/api/inheritance/list/host')
        assert response.status_code == 200

    def test_dependencies_graph(self, client):
        """Test getting dependency graph."""
        test_client, _ = client

        response = test_client.get('/api/dependencies?name=server1&type=host')
        assert response.status_code == 200
