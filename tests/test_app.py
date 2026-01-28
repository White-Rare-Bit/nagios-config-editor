"""
Tests for app.py - Flask Application Routes and Helper Functions
"""

import pytest
import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHelperFunctions:
    """Tests for helper functions - now delegated to NagiosService."""

    def test_get_name_field(self):
        """Test NAME_FIELDS constant."""
        from nagios_model import NAME_FIELDS

        assert NAME_FIELDS.get('host', 'name') == 'host_name'
        assert NAME_FIELDS.get('service', 'name') == 'service_description'
        assert NAME_FIELDS.get('contact', 'name') == 'contact_name'
        assert NAME_FIELDS.get('contactgroup', 'name') == 'contactgroup_name'
        assert NAME_FIELDS.get('command', 'name') == 'command_name'
        assert NAME_FIELDS.get('timeperiod', 'name') == 'timeperiod_name'
        assert NAME_FIELDS.get('hostgroup', 'name') == 'hostgroup_name'
        assert NAME_FIELDS.get('servicegroup', 'name') == 'servicegroup_name'
        assert NAME_FIELDS.get('unknown', 'name') == 'name'

    def test_transform_name_simple_replace(self):
        """Test NagiosService.transform_name with simple string replacement."""
        from nagios_service import NagiosService

        service = NagiosService('test_config')
        result = service.transform_name('test-server-01', 'test', 'prod')
        assert result == 'prod-server-01'

    def test_transform_name_prefix(self):
        """Test NagiosService.transform_name with prefix."""
        from nagios_service import NagiosService

        service = NagiosService('test_config')
        result = service.transform_name('server-01', prefix='prod-')
        assert result == 'prod-server-01'

    def test_transform_name_suffix(self):
        """Test NagiosService.transform_name with suffix."""
        from nagios_service import NagiosService

        service = NagiosService('test_config')
        result = service.transform_name('server', suffix='-01')
        assert result == 'server-01'

    def test_transform_name_prefix_and_suffix(self):
        """Test NagiosService.transform_name with both prefix and suffix."""
        from nagios_service import NagiosService

        service = NagiosService('test_config')
        result = service.transform_name('server', prefix='prod-', suffix='-01')
        assert result == 'prod-server-01'

    def test_transform_name_regex(self):
        """Test NagiosService.transform_name with regex pattern."""
        from nagios_service import NagiosService

        service = NagiosService('test_config')
        result = service.transform_name('server-001', r'-\d+', '-new', use_regex=True)
        assert result == 'server-new'

    def test_transform_name_invalid_regex(self):
        """Test NagiosService.transform_name with invalid regex."""
        from nagios_service import NagiosService

        service = NagiosService('test_config')
        result = service.transform_name('test', r'[invalid', '', use_regex=True)
        assert result is None

    def test_transform_name_combined(self):
        """Test NagiosService.transform_name with find/replace and prefix/suffix."""
        from nagios_service import NagiosService

        service = NagiosService('test_config')
        result = service.transform_name('old-server', 'old', 'new', prefix='prod-', suffix='-01')
        assert result == 'prod-new-server-01'

    def test_update_references(self):
        """Test NagiosService.update_references function."""
        from nagios_service import NagiosService
        from nagios_model import NagiosObject

        service = NagiosService('test_config')
        objects = [
            NagiosObject(
                object_type='service',
                attributes={'host_name': 'old-server', 'service_description': 'HTTP'}
            ),
            NagiosObject(
                object_type='service',
                attributes={'host_name': 'old-server,other-server', 'service_description': 'SSH'}
            ),
            NagiosObject(
                object_type='hostgroup',
                attributes={'members': 'old-server,server2,server3'}
            )
        ]

        count = service.update_references(objects, 'old-server', 'new-server')

        assert count == 3
        assert objects[0].attributes['host_name'] == 'new-server'
        assert objects[1].attributes['host_name'] == 'new-server,other-server'
        assert objects[2].attributes['members'] == 'new-server,server2,server3'


class TestFlaskRoutes:
    """Tests for Flask API routes."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client with temporary config."""
        import app as flask_app_module

        # Create a temp directory for this test
        temp_dir = tempfile.mkdtemp(prefix='nagios_flask_test_')

        # Create minimal config files
        hosts_content = '''define host {
    host_name       test-host
    alias           Test Host
    address         127.0.0.1
    check_command   check-host-alive
}

define host {
    host_name       test-host-02
    alias           Test Host 02
    address         127.0.0.2
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

        commands_content = '''define command {
    command_name    check-host-alive
    command_line    $USER1$/check_ping -H $HOSTADDRESS$
}

define command {
    command_name    check_http
    command_line    $USER1$/check_http -H $HOSTADDRESS$
}
'''
        with open(os.path.join(temp_dir, 'commands.cfg'), 'w') as f:
            f.write(commands_content)

        # Configure the app
        flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_index_redirect(self, client):
        """Test that index redirects to explorer."""
        test_client, _ = client
        response = test_client.get('/')
        assert response.status_code == 302
        assert '/explorer' in response.location

    def test_explorer_page(self, client):
        """Test explorer page loads."""
        test_client, _ = client
        response = test_client.get('/explorer')
        assert response.status_code == 200

    def test_api_files(self, client):
        """Test /api/files endpoint."""
        test_client, _ = client
        response = test_client.get('/api/files')
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns {'files': [...]}
        assert isinstance(data, dict)
        assert 'files' in data
        files = data['files']
        assert len(files) > 0

    def test_api_objects(self, client):
        """Test /api/objects endpoint."""
        test_client, _ = client
        response = test_client.get('/api/objects')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)

    def test_api_objects_by_type(self, client):
        """Test /api/objects with type filter."""
        test_client, _ = client
        response = test_client.get('/api/objects?type=host')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert all(obj['object_type'] == 'host' for obj in data)

    def test_api_summary(self, client):
        """Test /api/summary endpoint."""
        test_client, _ = client
        response = test_client.get('/api/summary')
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns {'summary': {...}, 'files': [...], 'total_objects': ...}
        assert isinstance(data, dict)
        summary = data.get('summary', data.get('object_counts', {}))
        assert 'host' in summary

    def test_api_search(self, client):
        """Test /api/search endpoint."""
        test_client, _ = client
        response = test_client.post('/api/search',
            data=json.dumps({'query': 'test-host'}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)

    def test_api_backups_list(self, client):
        """Test /api/backups GET endpoint."""
        test_client, _ = client
        response = test_client.get('/api/backups')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)

    def test_api_backups_create(self, client):
        """Test /api/backups POST endpoint."""
        test_client, _ = client
        response = test_client.post('/api/backups',
            data=json.dumps({'description': 'Test backup'}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True
        assert 'path' in data

    def test_api_staging_get_empty(self, client):
        """Test /api/staging GET when empty."""
        test_client, _ = client
        response = test_client.get('/api/staging')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['hasStaging'] is False

    def test_api_staging_save_and_get(self, client):
        """Test /api/staging POST and GET."""
        test_client, _ = client

        # Save staging data
        staging_data = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {'original': {}, 'edited': {}}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        response = test_client.post('/api/staging',
            data=json.dumps(staging_data),
            content_type='application/json',
            headers={'X-Session-Id': 'test-session'}
        )
        assert response.status_code == 200

        # Get staging data
        response = test_client.get('/api/staging')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['hasStaging'] is True

    def test_api_staging_delete(self, client):
        """Test /api/staging DELETE endpoint."""
        test_client, _ = client

        # First save some staging
        staging_data = {
            'sessionId': 'test-session',
            'pendingEdits': [[1, {}]],
            'stagedMoves': [],
            'stagedCreations': []
        }
        test_client.post('/api/staging',
            data=json.dumps(staging_data),
            content_type='application/json',
            headers={'X-Session-Id': 'test-session'}
        )

        # Delete it
        response = test_client.delete('/api/staging')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_api_staging_info(self, client):
        """Test /api/staging/info endpoint."""
        test_client, _ = client
        response = test_client.get('/api/staging/info')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'hasStaging' in data

    def test_api_staging_lock_no_lock(self, client):
        """Test /api/staging/lock GET when no lock held."""
        test_client, _ = client
        response = test_client.get('/api/staging/lock',
            headers={'X-Session-Id': 'test-session'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['locked'] is False
        assert data['owner'] is None
        assert data['isOwner'] is False

    def test_api_staging_lock_with_lock(self, client):
        """Test /api/staging/lock GET when lock is held."""
        test_client, _ = client

        # Create staging to acquire lock
        test_client.post('/api/staging',
            data=json.dumps({
                'sessionId': 'session-A',
                'userName': 'Test User',
                'userEmail': 'test@example.com',
                'pendingEdits': []
            }),
            content_type='application/json',
            headers={'X-Session-Id': 'session-A'})

        # Check lock status from same session
        response = test_client.get('/api/staging/lock',
            headers={'X-Session-Id': 'session-A'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['locked'] is True
        assert data['isOwner'] is True
        assert data['userName'] == 'Test User'
        assert data['userEmail'] == 'test@example.com'

        # Check lock status from different session
        response = test_client.get('/api/staging/lock',
            headers={'X-Session-Id': 'session-B'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['locked'] is True
        assert data['isOwner'] is False

        # Cleanup
        test_client.delete('/api/staging')

    def test_api_staging_lock_break(self, client):
        """Test /api/staging/lock/break POST endpoint."""
        test_client, _ = client

        # Create staging to acquire lock
        test_client.post('/api/staging',
            data=json.dumps({
                'sessionId': 'session-A',
                'userName': 'User A',
                'userEmail': 'a@example.com',
                'pendingEdits': []
            }),
            content_type='application/json',
            headers={'X-Session-Id': 'session-A'})

        # Break lock from different session
        response = test_client.post('/api/staging/lock/break',
            headers={'X-Session-Id': 'session-B'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify lock is released
        response = test_client.get('/api/staging/lock',
            headers={'X-Session-Id': 'session-B'})
        data = json.loads(response.data)
        assert data['locked'] is False

    def test_api_reload(self, client):
        """Test /api/reload endpoint."""
        test_client, _ = client
        response = test_client.post('/api/reload')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

    def test_api_settings_get(self, client):
        """Test /api/settings GET endpoint."""
        test_client, _ = client
        response = test_client.get('/api/settings')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'nagios_config_path' in data

    def test_api_folders(self, client):
        """Test /api/folders endpoint."""
        test_client, _ = client
        response = test_client.get('/api/folders')
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns {'folders': [...]}
        assert isinstance(data, dict)
        assert 'folders' in data

    def test_api_validate_check(self, client):
        """Test /api/validate/check endpoint."""
        test_client, _ = client
        response = test_client.get('/api/validate/check')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'available' in data

    def test_api_dependencies(self, client):
        """Test /api/dependencies endpoint."""
        test_client, _ = client
        response = test_client.get('/api/dependencies?name=test-host&type=host')
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns graph data with nodes and edges
        assert isinstance(data, dict)
        assert 'nodes' in data
        assert 'edges' in data

    def test_api_preview_rename(self, client):
        """Test /api/preview-rename endpoint."""
        test_client, _ = client
        response = test_client.post('/api/preview-rename',
            data=json.dumps({
                'type': 'host',  # API uses 'type' not 'object_type'
                'find': 'test',
                'replace': 'prod'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, (dict, list))

    def test_api_health_check(self, client):
        """Test /api/health-check endpoint."""
        test_client, _ = client
        response = test_client.get('/api/health-check')
        assert response.status_code == 200
        data = json.loads(response.data)
        # Should return analysis data
        assert isinstance(data, dict)


class TestFlaskErrorHandling:
    """Tests for Flask error handling."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_flask_test_')

        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_invalid_json_body(self, client):
        """Test handling of invalid JSON in request body."""
        test_client, _ = client
        response = test_client.post('/api/search',
            data='not valid json',
            content_type='application/json'
        )
        # Should return error status
        assert response.status_code in [400, 500]

    def test_missing_required_fields(self, client):
        """Test handling of missing required fields."""
        test_client, _ = client
        response = test_client.post('/api/preview-rename',
            data=json.dumps({}),  # Missing required fields
            content_type='application/json'
        )
        assert response.status_code in [200, 400]  # May return empty results or error

    def test_backup_restore_nonexistent(self, client):
        """Test restoring nonexistent backup."""
        test_client, _ = client
        response = test_client.post('/api/backups/nonexistent_backup/restore',
                                    content_type='application/json')
        assert response.status_code in [400, 404, 500]

    def test_backup_delete_nonexistent(self, client):
        """Test deleting nonexistent backup."""
        test_client, _ = client
        response = test_client.delete('/api/backups/nonexistent_backup')
        # Should handle gracefully
        assert response.status_code in [200, 404]


class TestBulkOperations:
    """Tests for bulk operation endpoints."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client with multiple objects."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_flask_test_')

        # Create hosts with pattern that can be bulk renamed
        hosts_content = '''define host {
    host_name       web-server-01
    alias           Web Server 01
    address         192.168.1.1
}

define host {
    host_name       web-server-02
    alias           Web Server 02
    address         192.168.1.2
}

define host {
    host_name       db-server-01
    alias           DB Server 01
    address         192.168.2.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_preview_rename_multiple(self, client):
        """Test preview rename affecting multiple objects."""
        test_client, _ = client
        response = test_client.post('/api/preview-rename',
            data=json.dumps({
                'type': 'host',  # API uses 'type' not 'object_type'
                'find': 'web-server',
                'replace': 'frontend'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        # Should preview changes for web-server-01 and web-server-02

    def test_bulk_attributes_preview(self, client):
        """Test bulk attributes preview."""
        test_client, _ = client
        response = test_client.post('/api/bulk-attributes/preview',
            data=json.dumps({
                'type': 'host',
                'filter_field': '',
                'filter_value': '',
                'target_field': 'check_interval',
                'new_value': '5',
                'action': 'set'
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)
        assert 'matches' in data


class TestObjectOperations:
    """Tests for individual object operations."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_flask_test_')

        hosts_content = '''define host {
    host_name       test-host
    alias           Test Host
    address         127.0.0.1
}
'''
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write(hosts_content)

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_create_object(self, client):
        """Test creating a new object."""
        test_client, temp_dir = client
        response = test_client.post('/api/objects/create',
            data=json.dumps({
                'object_type': 'host',
                'attributes': {
                    'host_name': 'new-host',
                    'alias': 'New Host',
                    'address': '192.168.1.100'
                },
                'target_file': os.path.join(temp_dir, 'hosts.cfg')
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

    def test_update_object(self, client):
        """Test updating an existing object."""
        test_client, temp_dir = client

        # First get the object to find its details
        response = test_client.get('/api/objects?type=host')
        objects = json.loads(response.data)
        host_obj = next((o for o in objects if o['attributes'].get('host_name') == 'test-host'), None)

        # Must find the object - fail test if not found
        assert host_obj is not None, "Test object 'test-host' not found in fixture"

        response = test_client.post('/api/object/update',
            data=json.dumps({
                'source_file': host_obj['source_file'],
                'line_number': host_obj['line_number'],
                'object_type': host_obj['object_type'],
                'original_attributes': host_obj['attributes'],
                'new_attributes': {
                    'host_name': 'test-host',
                    'alias': 'Updated Test Host',
                    'address': '127.0.0.1'
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 200


class TestFolderOperations:
    """Tests for folder/file operations."""

    @pytest.fixture
    def client(self):
        """Create a Flask test client with folder structure."""
        import app as flask_app_module

        temp_dir = tempfile.mkdtemp(prefix='nagios_flask_test_')

        # Create a subdirectory
        subdir = os.path.join(temp_dir, 'servers')
        os.makedirs(subdir)

        with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
            f.write('define host { host_name test }')

        with open(os.path.join(subdir, 'web.cfg'), 'w') as f:
            f.write('define host { host_name web }')

        test_app = flask_app_module.create_app(config_path=temp_dir)
        test_app.config['TESTING'] = True

        with test_app.test_client() as test_client:
            yield test_client, temp_dir

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_list_folders(self, client):
        """Test listing folders."""
        test_client, _ = client
        response = test_client.get('/api/folders')
        assert response.status_code == 200
        data = json.loads(response.data)
        # API returns {'folders': [...]}
        assert isinstance(data, dict)
        assert 'folders' in data

    def test_create_folder(self, client):
        """Test creating a new folder."""
        test_client, temp_dir = client
        response = test_client.post('/api/folders',
            data=json.dumps({
                'path': os.path.join(temp_dir, 'new_folder')
            }),
            content_type='application/json',
            headers={'X-Session-Id': 'test-session-123'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True

    def test_create_file(self, client):
        """Test creating a new config file."""
        test_client, temp_dir = client
        session_id = 'test-create-file-session'
        response = test_client.post('/api/files/create',
            data=json.dumps({
                'path': os.path.join(temp_dir, 'new_config.cfg')
            }),
            content_type='application/json',
            headers={'X-Session-Id': session_id}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('success') is True
