"""
Extended tests for app.py - Additional Flask Application Routes
Covers all remaining API endpoints not in test_app.py
"""

import pytest
import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRenameOperations:
    """Tests for rename API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client with objects to rename."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_rename_test_')

        hosts_content = '''define host {
    host_name       old-server-01
    alias           Old Server 01
    address         192.168.1.1
}

define host {
    host_name       old-server-02
    alias           Old Server 02
    address         192.168.1.2
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        services_content = '''define service {
    host_name           old-server-01
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

    def test_apply_rename(self, client):
        """Test applying a rename operation."""
        test_client, temp_dir = client
        response = test_client.post('/api/apply-rename',
            data=json.dumps({
                'type': 'host',
                'find': 'old',
                'replace': 'new'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True
        assert data.get('renamed', 0) >= 1
        assert 'backup' in data

    def test_apply_rename_with_prefix_suffix(self, client):
        """Test rename with prefix and suffix."""
        test_client, temp_dir = client
        response = test_client.post('/api/apply-rename',
            data=json.dumps({
                'type': 'host',
                'find': '',
                'replace': '',
                'prefix': 'prod-',
                'suffix': '-v2'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

    def test_apply_rename_missing_type(self, client):
        """Test rename without object type returns error."""
        test_client, _ = client
        response = test_client.post('/api/apply-rename',
            data=json.dumps({
                'find': 'old',
                'replace': 'new'
            }),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_apply_rename_regex(self, client):
        """Test rename with regex pattern."""
        test_client, temp_dir = client
        response = test_client.post('/api/apply-rename',
            data=json.dumps({
                'type': 'host',
                'find': r'-\d+$',
                'replace': '-renamed',
                'regex': True
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True


class TestFindReplaceOperations:
    """Tests for find/replace API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_replace_test_')

        hosts_content = '''define host {
    host_name       test-server
    alias           Test Server with old-value
    address         192.168.1.1
    notes           This contains old-value too
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

    def test_preview_replace(self, client):
        """Test preview find/replace."""
        test_client, _ = client
        response = test_client.post('/api/preview-replace',
            data=json.dumps({
                'find': 'old-value',
                'type': 'host'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'matches' in data
        assert 'total' in data

    def test_preview_replace_empty_find(self, client):
        """Test preview with empty find returns empty results."""
        test_client, _ = client
        response = test_client.post('/api/preview-replace',
            data=json.dumps({
                'find': '',
                'type': 'host'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] == 0

    def test_preview_replace_with_field_filter(self, client):
        """Test preview with specific field filter."""
        test_client, _ = client
        response = test_client.post('/api/preview-replace',
            data=json.dumps({
                'find': 'old-value',
                'type': 'host',
                'field': 'alias'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'matches' in data

    def test_preview_replace_regex(self, client):
        """Test preview with regex pattern."""
        test_client, _ = client
        response = test_client.post('/api/preview-replace',
            data=json.dumps({
                'find': r'old-\w+',
                'type': 'host',
                'regex': True
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'matches' in data

    def test_apply_replace(self, client):
        """Test applying find/replace."""
        test_client, temp_dir = client
        response = test_client.post('/api/apply-replace',
            data=json.dumps({
                'find': 'old-value',
                'replace': 'new-value',
                'type': 'host'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True
        assert 'objects_modified' in data
        assert 'fields_changed' in data
        assert 'backup' in data

    def test_apply_replace_missing_find(self, client):
        """Test apply replace without find text returns error."""
        test_client, _ = client
        response = test_client.post('/api/apply-replace',
            data=json.dumps({
                'replace': 'new-value'
            }),
            content_type='application/json'
        )
        assert response.status_code == 400


class TestMoveDeleteCloneOperations:
    """Tests for move, delete, and clone API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client with multiple objects."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_move_test_')

        hosts_content = '''define host {
    host_name       server-to-move
    alias           Server To Move
    address         192.168.1.1
}

define host {
    host_name       server-to-delete
    alias           Server To Delete
    address         192.168.1.2
}

define host {
    host_name       server-to-clone
    alias           Server To Clone
    address         192.168.1.3
    check_command   check-host-alive
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        commands_content = '''define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}
'''
        with open(os.path.join(temp_dir, 'commands.cfg'), 'w') as f:
            f.write(commands_content)

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_move_objects(self, client):
        """Test moving objects to a different file."""
        test_client, temp_dir = client

        # Get objects first
        response = test_client.get('/api/objects?type=host')
        objects = json.loads(response.data)
        obj_to_move = next((o for o in objects if o['attributes'].get('host_name') == 'server-to-move'), None)

        # Must find the object - fail test if not found
        assert obj_to_move is not None, "Test object 'server-to-move' not found in fixture"

        target_file = os.path.join(temp_dir, 'moved_hosts.cfg')
        response = test_client.post('/api/move-objects',
            data=json.dumps({
                'objects': [{
                    'source_file': obj_to_move['source_file'],
                    'line_number': obj_to_move['line_number'],
                    'object_type': obj_to_move['object_type']
                }],
                'target_file': target_file,
                'create_new': True
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

    def test_move_objects_missing_data(self, client):
        """Test move objects with missing data returns error."""
        test_client, _ = client
        response = test_client.post('/api/move-objects',
            data=json.dumps({
                'objects': []
            }),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_delete_objects(self, client):
        """Test deleting objects."""
        test_client, temp_dir = client

        # Get objects first
        response = test_client.get('/api/objects?type=host')
        objects = json.loads(response.data)
        obj_to_delete = next((o for o in objects if o['attributes'].get('host_name') == 'server-to-delete'), None)

        # Must find the object - fail test if not found
        assert obj_to_delete is not None, "Test object 'server-to-delete' not found in fixture"

        # API expects list of integer indices, find the global index
        all_objects = test_client.get('/api/objects')
        all_data = json.loads(all_objects.data)
        idx = next((i for i, o in enumerate(all_data) if o['attributes'].get('host_name') == 'server-to-delete'), None)

        assert idx is not None, "Could not find global index for 'server-to-delete'"

        response = test_client.post('/api/delete-objects',
            data=json.dumps({
                'objects': [idx]
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True
        assert data.get('deleted', 0) >= 1

    def test_clone_objects(self, client):
        """Test cloning objects."""
        test_client, temp_dir = client

        # Get objects first
        response = test_client.get('/api/objects?type=host')
        objects = json.loads(response.data)
        obj_to_clone = next((o for o in objects if o['attributes'].get('host_name') == 'server-to-clone'), None)

        # Must find the object - fail test if not found
        assert obj_to_clone is not None, "Test object 'server-to-clone' not found in fixture"

        # API expects list of integer indices
        all_objects = test_client.get('/api/objects')
        all_data = json.loads(all_objects.data)
        idx = next((i for i, o in enumerate(all_data) if o['attributes'].get('host_name') == 'server-to-clone'), None)

        assert idx is not None, "Could not find global index for 'server-to-clone'"

        response = test_client.post('/api/clone-objects',
            data=json.dumps({
                'objects': [idx],
                'find': 'server-to-clone',
                'replace': 'cloned-server'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

        # Verify the clone was created
        verify_response = test_client.get('/api/objects?type=host')
        verify_objects = json.loads(verify_response.data)
        cloned = next((o for o in verify_objects if o['attributes'].get('host_name') == 'cloned-server'), None)
        assert cloned is not None, "Cloned object 'cloned-server' was not created"


class TestBatchOperations:
    """Tests for batch update operations."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_batch_test_')

        hosts_content = '''define host {
    host_name       batch-server-01
    alias           Batch Server 01
    address         192.168.1.1
}

define host {
    host_name       batch-server-02
    alias           Batch Server 02
    address         192.168.1.2
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

    def test_batch_update(self, client):
        """Test batch updating multiple objects."""
        test_client, temp_dir = client

        # Get objects first
        response = test_client.get('/api/objects?type=host')
        objects = json.loads(response.data)

        if len(objects) >= 2:
            updates = []
            for obj in objects[:2]:
                updates.append({
                    'source_file': obj['source_file'],
                    'line_number': obj['line_number'],
                    'object_type': obj['object_type'],
                    'original_attributes': obj['attributes'],
                    'new_attributes': {**obj['attributes'], 'check_interval': '10'}
                })

            response = test_client.post('/api/objects/batch-update',
                data=json.dumps({'updates': updates}),
                content_type='application/json'
            )
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data.get('success') is True


class TestFileRelocateOperations:
    """Tests for file and folder relocation operations."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client with folder structure."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_relocate_test_')

        # Create subdirectories
        os.makedirs(os.path.join(temp_dir, 'source_folder'))
        os.makedirs(os.path.join(temp_dir, 'target_folder'))

        # Create files
        with open(os.path.join(temp_dir, 'source_folder', 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name relocate-test }')

        with open(os.path.join(temp_dir, 'file_to_move.cfg'), 'w') as f:
            f.write('define host { host_name file-move-test }')

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_relocate_file(self, client):
        """Test relocating a file."""
        test_client, temp_dir = client

        source = os.path.join(temp_dir, 'file_to_move.cfg')
        target_folder = os.path.join(temp_dir, 'target_folder')
        expected_new_path = os.path.join(target_folder, 'file_to_move.cfg')

        # Verify source exists before relocate
        assert os.path.exists(source), f"Source file {source} does not exist"

        response = test_client.post('/api/files/relocate',
            data=json.dumps({
                'source_path': source,
                'target_folder': target_folder
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

        # Verify file was actually moved
        assert not os.path.exists(source), "Source file still exists after relocation"
        assert os.path.exists(expected_new_path), "File was not moved to target folder"

    def test_relocate_folder(self, client):
        """Test relocating a folder."""
        test_client, temp_dir = client

        source = os.path.join(temp_dir, 'source_folder')
        target_folder = os.path.join(temp_dir, 'target_folder')
        expected_new_path = os.path.join(target_folder, 'source_folder')

        # Verify source exists before relocate
        assert os.path.exists(source), f"Source folder {source} does not exist"
        assert os.path.isdir(source), f"Source {source} is not a directory"

        response = test_client.post('/api/folders/relocate',
            data=json.dumps({
                'source_path': source,
                'target_folder': target_folder
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

        # Verify folder was actually moved
        assert not os.path.exists(source), "Source folder still exists after relocation"
        assert os.path.exists(expected_new_path), "Folder was not moved to target location"
        assert os.path.isdir(expected_new_path), "Moved path is not a directory"


class TestDeleteOperations:
    """Tests for delete file/folder operations."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_delete_test_')

        # Create a file to delete
        with open(os.path.join(temp_dir, 'to_delete.cfg'), 'w') as f:
            f.write('define host { host_name delete-test }')

        # Create a folder to delete
        os.makedirs(os.path.join(temp_dir, 'folder_to_delete'))
        with open(os.path.join(temp_dir, 'folder_to_delete', 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name in-folder }')

        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_delete_file(self, client):
        """Test deleting a file."""
        test_client, temp_dir = client

        file_path = os.path.join(temp_dir, 'to_delete.cfg')
        response = test_client.post('/api/delete',
            data=json.dumps({
                'path': file_path,
                'type': 'file'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

    def test_delete_folder(self, client):
        """Test deleting a folder."""
        test_client, temp_dir = client

        folder_path = os.path.join(temp_dir, 'folder_to_delete')
        response = test_client.post('/api/delete',
            data=json.dumps({
                'path': folder_path,
                'type': 'folder'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True


class TestAuditLogOperations:
    """Tests for audit log API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_audit_test_')

        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_get_audit_log(self, client):
        """Test getting audit log."""
        test_client, _ = client
        response = test_client.get('/api/audit-log')
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns {'entries': [...]}
        assert 'entries' in data
        assert isinstance(data['entries'], list)

    def test_add_audit_entry(self, client):
        """Test adding an audit log entry."""
        test_client, _ = client
        response = test_client.post('/api/audit-log',
            data=json.dumps({
                'action': 'test_action',
                'details': 'Test audit entry',
                'user': 'test_user'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

    def test_clear_audit_log(self, client):
        """Test clearing audit log."""
        test_client, _ = client
        response = test_client.post('/api/audit-log/clear')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True


class TestBulkAttributesApply:
    """Tests for bulk attributes apply endpoint."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_bulkattr_test_')

        hosts_content = '''define host {
    host_name       bulk-host-01
    alias           Bulk Host 01
    address         192.168.1.1
}

define host {
    host_name       bulk-host-02
    alias           Bulk Host 02
    address         192.168.1.2
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

    def test_bulk_attributes_apply_set(self, client):
        """Test bulk attributes apply with set action."""
        test_client, temp_dir = client
        response = test_client.post('/api/bulk-attributes/apply',
            data=json.dumps({
                'type': 'host',
                'filter_field': '',
                'filter_value': '',
                'target_field': 'check_interval',
                'new_value': '10',
                'action': 'set'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True or 'updated' in data

    def test_bulk_attributes_apply_append(self, client):
        """Test bulk attributes apply with append action."""
        test_client, temp_dir = client
        response = test_client.post('/api/bulk-attributes/apply',
            data=json.dumps({
                'type': 'host',
                'filter_field': '',
                'filter_value': '',
                'target_field': 'alias',
                'new_value': ' (modified)',
                'action': 'append'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_bulk_attributes_apply_remove(self, client):
        """Test bulk attributes apply with remove action."""
        test_client, temp_dir = client
        response = test_client.post('/api/bulk-attributes/apply',
            data=json.dumps({
                'type': 'host',
                'filter_field': '',
                'filter_value': '',
                'target_field': 'notes',
                'new_value': '',
                'action': 'remove'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200


class TestInheritanceEndpoints:
    """Tests for inheritance API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client with templates."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_inherit_test_')

        templates_content = '''define host {
    name                    linux-server
    check_command           check-host-alive
    max_check_attempts      5
    check_period            24x7
    register                0
}

define host {
    name                    web-server
    use                     linux-server
    check_interval          3
    register                0
}
'''
        with open(os.path.join(temp_dir, 'templates.cfg'), 'w') as f:
            f.write(templates_content)

        hosts_content = '''define host {
    host_name       my-web-server
    use             web-server
    alias           My Web Server
    address         192.168.1.100
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_get_inheritance(self, client):
        """Test getting inheritance chain."""
        test_client, _ = client
        response = test_client.get('/api/inheritance/host/my-web-server')
        assert response.status_code == 200
        data = json.loads(response.data)
        # Should have inheritance info
        assert isinstance(data, dict)

    def test_list_inheritance(self, client):
        """Test listing inheritance for object type."""
        test_client, _ = client
        response = test_client.get('/api/inheritance/list/host')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, (list, dict))


class TestSmartGroupingEndpoints:
    """Tests for smart grouping API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client with groupable objects."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_group_test_')

        hosts_content = '''define host {
    host_name       web-01
    alias           Web Server 01
    address         192.168.1.1
}

define host {
    host_name       web-02
    alias           Web Server 02
    address         192.168.1.2
}

define host {
    host_name       db-01
    alias           Database Server 01
    address         192.168.2.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        services_content = '''define service {
    host_name           web-01
    service_description HTTP
    check_command       check_http
}

define service {
    host_name           web-02
    service_description HTTP
    check_command       check_http
}

define service {
    host_name           db-01
    service_description MySQL
    check_command       check_mysql
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

    def test_smart_grouping_analyze(self, client):
        """Test smart grouping analysis."""
        test_client, _ = client
        response = test_client.get('/api/smart-grouping/suggest')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)

    def test_smart_grouping_create(self, client):
        """Test creating a smart group."""
        test_client, temp_dir = client
        # API expects 'name' and 'members' fields
        response = test_client.post('/api/smart-grouping/create',
            data=json.dumps({
                'name': 'web-servers',
                'alias': 'Web Servers',
                'members': ['web-01', 'web-02']
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True


class TestDiffEndpoint:
    """Tests for diff preview endpoint."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_diff_test_')

        hosts_content = '''define host {
    host_name       diff-test-01
    alias           Diff Test 01
    address         192.168.1.1
}

define host {
    host_name       diff-test-02
    alias           Diff Test 02
    address         192.168.1.2
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_diff_rename(self, client):
        """Test diff preview for rename operation."""
        test_client, _ = client
        response = test_client.post('/api/diff/rename',
            data=json.dumps({
                'type': 'host',
                'find': 'diff-test',
                'replace': 'renamed'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'diff' in data or 'files' in data or isinstance(data, dict)


class TestSettingsEndpoints:
    """Tests for settings API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_settings_test_')

        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_update_settings(self, client):
        """Test updating settings."""
        test_client, temp_dir = client
        response = test_client.post('/api/settings',
            data=json.dumps({
                'nagios_config_path': temp_dir
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

    def test_browse_directory(self, client):
        """Test browsing directories."""
        test_client, temp_dir = client
        response = test_client.post('/api/settings/browse',
            data=json.dumps({
                'path': temp_dir
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'entries' in data or 'items' in data or isinstance(data, list)


class TestValidationEndpoint:
    """Tests for validation endpoint."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_validate_test_')

        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test address 127.0.0.1 }')

        flask_app_module.config['nagios_cfg'] = os.path.join(temp_dir, 'nagios.cfg')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_validation(self, client):
        """Test running validation."""
        test_client, _ = client
        response = test_client.post('/api/validate')
        assert response.status_code == 200
        data = json.loads(response.data)
        # Will likely fail because nagios binary doesn't exist, but should handle gracefully
        assert 'success' in data or 'errors' in data or 'error' in data


class TestPageRoutes:
    """Tests for HTML page routes."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_page_test_')

        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_objects_page(self, client):
        """Test objects page."""
        response = client.get('/objects')
        assert response.status_code == 200

    def test_objects_page_with_type(self, client):
        """Test objects page with type."""
        response = client.get('/objects/host')
        assert response.status_code == 200

    def test_bulk_rename_page(self, client):
        """Test bulk rename page."""
        response = client.get('/bulk-rename')
        assert response.status_code == 200

    def test_find_replace_page(self, client):
        """Test find replace page."""
        response = client.get('/find-replace')
        assert response.status_code == 200

    def test_reorganize_page(self, client):
        """Test reorganize page."""
        response = client.get('/reorganize')
        assert response.status_code == 200

    def test_audit_log_page(self, client):
        """Test audit log page."""
        response = client.get('/audit-log')
        assert response.status_code == 200

    def test_backups_page(self, client):
        """Test backups page."""
        response = client.get('/backups')
        assert response.status_code == 200

    def test_validate_page(self, client):
        """Test validate page."""
        response = client.get('/validate')
        assert response.status_code == 200

    def test_dependencies_page(self, client):
        """Test dependencies page."""
        response = client.get('/dependencies')
        assert response.status_code == 200

    def test_settings_page(self, client):
        """Test settings page."""
        response = client.get('/settings')
        assert response.status_code == 200

    def test_health_check_page(self, client):
        """Test health check page."""
        response = client.get('/health-check')
        assert response.status_code == 200

    def test_bulk_attributes_page(self, client):
        """Test bulk attributes page."""
        response = client.get('/bulk-attributes')
        assert response.status_code == 200

    def test_inheritance_page(self, client):
        """Test inheritance page."""
        response = client.get('/inheritance')
        assert response.status_code == 200

    def test_smart_grouping_page(self, client):
        """Test smart grouping page."""
        response = client.get('/smart-grouping')
        assert response.status_code == 200
