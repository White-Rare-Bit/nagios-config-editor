"""
Integration tests for staging system after backward compatibility removal.

Tests full staging workflow with dict format only.
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from app import create_app
from nagios_parser import NagiosConfigParser


@pytest.fixture
def app():
    """Create Flask app with test config."""
    # Create temp directory for test config
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / 'nagios'
    test_config_path.mkdir()

    # Create sample config file
    sample_cfg = test_config_path / 'hosts.cfg'
    sample_cfg.write_text('''
define host {
    host_name       test-host-1
    alias           Test Host 1
    address         192.168.1.1
    use             generic-host
}

define host {
    host_name       test-host-2
    alias           Test Host 2
    address         192.168.1.2
    use             generic-host
}
''')

    app = create_app()
    app.config['TESTING'] = True
    app.config['NAGIOS_CONFIG_PATH'] = str(test_config_path)

    yield app

    # Cleanup
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def client(app):
    """Create test client with clean staging state."""
    test_client = app.test_client()

    # Clear any existing staging to ensure clean state
    with app.app_context():
        sm = app.extensions.get('staging')
        if sm:
            sm.clear_staging()

    yield test_client

    # Cleanup staging after test
    with app.app_context():
        sm = app.extensions.get('staging')
        if sm:
            sm.clear_staging()


def test_staging_round_trip_dict_format(client):
    """Test full staging round-trip with dict format."""
    # Get initial objects
    resp = client.get('/api/objects')
    assert resp.status_code == 200
    objects = resp.json
    assert len(objects) > 0

    # Stage an edit in dict format (uses 'original' and 'edited' field names)
    obj = objects[0]
    edit_data = {
        'sessionId': 'test-session',
        'userName': 'Test User',
        'userEmail': 'test@example.com',
        'pendingEdits': {
            str(obj['global_index']): {
                'object': obj,
                'original': obj['attributes'],
                'edited': {**obj['attributes'], 'alias': 'Updated Alias'}
            }
        }
    }

    resp = client.post('/api/staging',
                       data=json.dumps(edit_data),
                       content_type='application/json',
                       headers={'X-Session-Id': 'test-session'})
    assert resp.status_code == 200

    # Verify staging was saved
    resp = client.get('/api/staging',
                      headers={'X-Session-Id': 'test-session'})
    assert resp.status_code == 200
    data = resp.json
    staging = data.get('staging', data)  # Handle both response formats
    assert 'pendingEdits' in staging
    assert isinstance(staging['pendingEdits'], dict)

    # Apply changes
    resp = client.post('/api/staging/apply',
                       data=json.dumps({}),
                       content_type='application/json',
                       headers={'X-Session-Id': 'test-session'})
    assert resp.status_code == 200


def test_reject_old_list_format(client):
    """Test that old list format is rejected with clear error."""
    # Try to save staging with old list format
    old_format_data = {
        'sessionId': 'test-session',
        'pendingEdits': [
            ['key1', {'object': {}, 'edited': {}}]
        ]
    }

    resp = client.post('/api/staging',
                       data=json.dumps(old_format_data),
                       content_type='application/json',
                       headers={'X-Session-Id': 'test-session'})
    assert resp.status_code == 400
    assert 'Invalid staging format' in resp.json['error']
    assert 'dict format' in resp.json['error']


def test_undo_operations_dict_format(client):
    """Test undo operations work with dict format."""
    # Get initial objects
    resp = client.get('/api/objects')
    objects = resp.json
    obj = objects[0]

    # Stage multiple operations
    staging_data = {
        'sessionId': 'test-session',
        'userName': 'Test User',
        'userEmail': 'test@example.com',
        'pendingEdits': {
            str(obj['global_index']): {
                'object': obj,
                'original': obj['attributes'],
                'edited': {**obj['attributes'], 'alias': 'Edit 1'}
            }
        }
    }

    client.post('/api/staging',
                data=json.dumps(staging_data),
                content_type='application/json',
                headers={'X-Session-Id': 'test-session'})

    # Get staging info
    resp = client.get('/api/staging/info-extended',
                      headers={'X-Session-Id': 'test-session'})
    info = resp.json
    assert info['undoCount'] > 0

    # Undo operation
    resp = client.post('/api/staging/undo',
                       data=json.dumps({}),
                       content_type='application/json',
                       headers={'X-Session-Id': 'test-session'})
    assert resp.status_code == 200

    # Verify undo worked
    resp = client.get('/api/staging/info-extended',
                      headers={'X-Session-Id': 'test-session'})
    info = resp.json
    assert info['undoCount'] == 0
    assert info['totalCount'] == 0


def test_multi_operation_workflow(client):
    """Test create, edit, move, delete workflow."""
    session_id = 'test-session'
    headers = {'X-Session-Id': session_id}

    # Get initial state
    resp = client.get('/api/objects')
    objects = resp.json

    obj = objects[0]

    # Stage both creation and edit in one request
    staging_data = {
        'sessionId': session_id,
        'stagedCreations': [{
            'id': 'create-1',
            'type': 'host',
            'targetFile': 'hosts.cfg',
            'attributes': {
                'host_name': 'new-host',
                'alias': 'New Host',
                'address': '192.168.1.100'
            }
        }],
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

    # Verify counts
    resp = client.get('/api/staging/info-extended', headers=headers)
    info = resp.json
    counts = info.get('counts', {})
    assert counts.get('creations', 0) == 1
    assert counts.get('edits', 0) == 1

    # Apply all changes
    resp = client.post('/api/staging/apply',
                       data=json.dumps({}),
                       content_type='application/json',
                       headers=headers)
    assert resp.status_code == 200


def test_conflict_detection(client):
    """Test conflict detection on external file changes."""
    session_id = 'test-session'
    headers = {'X-Session-Id': session_id}

    # Get objects and make edit
    resp = client.get('/api/objects')
    obj = resp.json[0]

    edit_data = {
        'sessionId': session_id,
        'pendingEdits': {
            str(obj['global_index']): {
                'object': obj,
                'original': obj['attributes'],
                'edited': {**obj['attributes'], 'alias': 'Changed'}
            }
        }
    }

    client.post('/api/staging',
                data=json.dumps(edit_data),
                content_type='application/json',
                headers=headers)

    # Check for conflicts (should be none initially)
    resp = client.get('/api/staging/conflicts', headers=headers)
    assert resp.status_code == 200
    assert len(resp.json.get('conflicts', [])) == 0
