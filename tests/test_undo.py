"""Integration tests for the undo system.

Tests the /api/staging/undo endpoint with Flask test client.
Covers list-format and dict-format entries, empty staged lists,
and key/globalIndex matching.
"""
import pytest
from app import create_app


@pytest.fixture
def app_client(tmp_path):
    """Create test app with config directory containing nagios objects."""
    config_dir = tmp_path / "nagios"
    config_dir.mkdir()

    hosts_cfg = config_dir / "hosts.cfg"
    hosts_cfg.write_text(
        "define host {\n"
        "    host_name       web-server-01\n"
        "    alias           Web Server 01\n"
        "    address         192.168.1.1\n"
        "}\n\n"
        "define host {\n"
        "    host_name       db-server-01\n"
        "    alias           DB Server 01\n"
        "    address         192.168.1.2\n"
        "}\n"
    )

    app = create_app(config_path=str(config_dir))
    app.config['TESTING'] = True
    client = app.test_client()
    return client, config_dir


class TestUndoEdit:
    """Tests for undoing edit operations."""

    def test_undo_edit_list_format(self, app_client):
        """Stage edit with list-format entry, undo removes it."""
        client, config_dir = app_client
        session_id = "test-undo-edit"

        # Stage an edit using list-format [globalIndex, {data}]
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[0, {
                "object": {"name": "web-server-01", "object_type": "host"},
                "originalAttributes": {"alias": "Web Server 01"},
                "newAttributes": {"alias": "Changed"}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        response = client.post('/api/staging', json=staging_data,
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify undo stack has an entry
        info = client.get('/api/staging/info-extended',
                          headers={'X-Session-Id': session_id}).get_json()
        assert info['undoStackLength'] == 1

        # Undo the edit
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify pendingEdits is now empty
        staging_resp = client.get('/api/staging',
                                  headers={'X-Session-Id': session_id}).get_json()
        assert staging_resp.get('staging', {}).get('pendingEdits', []) == []

    def test_undo_edit_empty_pending_edits(self, app_client):
        """Undo succeeds (no-op) when pendingEdits is empty."""
        client, config_dir = app_client
        session_id = "test-undo-empty"

        # Stage an edit
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[0, {
                "object": {"name": "web-server-01", "object_type": "host"},
                "originalAttributes": {"alias": "Web Server 01"},
                "newAttributes": {"alias": "Changed"}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data,
                    headers={'X-Session-Id': session_id})

        # Re-save with empty pendingEdits (simulates frontend re-save race)
        staging_data_empty = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data_empty,
                    headers={'X-Session-Id': session_id})

        # Undo should still succeed (no-op since list is empty)
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200
        assert response.get_json()['success'] is True

    def test_undo_multiple_edits_removes_last(self, app_client):
        """Undo removes only the last staged edit."""
        client, config_dir = app_client
        session_id = "test-undo-multiple"

        # Stage first edit
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[0, {
                "object": {"name": "web-server-01", "object_type": "host"},
                "originalAttributes": {"alias": "Web Server 01"},
                "newAttributes": {"alias": "First Edit"}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data,
                    headers={'X-Session-Id': session_id})

        # Stage second edit (both edits now in pendingEdits)
        staging_data2 = {
            "sessionId": session_id,
            "pendingEdits": [
                [0, {
                    "object": {"name": "web-server-01", "object_type": "host"},
                    "originalAttributes": {"alias": "Web Server 01"},
                    "newAttributes": {"alias": "First Edit"}
                }],
                [1, {
                    "object": {"name": "db-server-01", "object_type": "host"},
                    "originalAttributes": {"alias": "DB Server 01"},
                    "newAttributes": {"alias": "Second Edit"}
                }]
            ],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data2,
                    headers={'X-Session-Id': session_id})

        # Undo last edit (second one)
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify first edit remains, second is gone
        staging_resp = client.get('/api/staging',
                                  headers={'X-Session-Id': session_id}).get_json()
        edits = staging_resp.get('staging', {}).get('pendingEdits', [])
        assert len(edits) == 1
        # First edit (globalIndex=0) should remain
        assert edits[0][0] == 0

    def test_undo_edit_globalindex_zero(self, app_client):
        """Undo works correctly for globalIndex=0 (falsy value)."""
        client, config_dir = app_client
        session_id = "test-undo-zero"

        # Stage edit with globalIndex=0
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[0, {
                "object": {"name": "web-server-01", "object_type": "host"},
                "originalAttributes": {"alias": "Web Server 01"},
                "newAttributes": {"alias": "Changed"}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data,
                    headers={'X-Session-Id': session_id})

        # Undo should remove the edit at globalIndex=0
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        staging_resp = client.get('/api/staging',
                                  headers={'X-Session-Id': session_id}).get_json()
        assert staging_resp.get('staging', {}).get('pendingEdits', []) == []


class TestUndoMove:
    """Tests for undoing move operations."""

    def test_undo_move_list_format(self, app_client):
        """Stage move with list-format entry, undo removes it."""
        client, config_dir = app_client
        session_id = "test-undo-move"

        # Create target file
        (config_dir / "other.cfg").write_text("")

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [["host:web-server-01", {
                "object": {"name": "web-server-01", "object_type": "host"},
                "originalFile": str(config_dir / "hosts.cfg"),
                "targetFile": str(config_dir / "other.cfg")
            }]],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        response = client.post('/api/staging', json=staging_data,
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Undo the move
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        # Verify stagedMoves is empty
        staging_resp = client.get('/api/staging',
                                  headers={'X-Session-Id': session_id}).get_json()
        assert staging_resp.get('staging', {}).get('stagedMoves', []) == []

    def test_undo_move_empty_list(self, app_client):
        """Undo move succeeds when stagedMoves is empty."""
        client, config_dir = app_client
        session_id = "test-undo-move-empty"

        (config_dir / "other.cfg").write_text("")

        # Stage a move
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [["host:web-server-01", {
                "object": {"name": "web-server-01", "object_type": "host"},
                "originalFile": str(config_dir / "hosts.cfg"),
                "targetFile": str(config_dir / "other.cfg")
            }]],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data,
                    headers={'X-Session-Id': session_id})

        # Re-save with empty moves
        staging_empty = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_empty,
                    headers={'X-Session-Id': session_id})

        # Undo succeeds even with empty list
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200
        assert response.get_json()['success'] is True


class TestUndoCreation:
    """Tests for undoing creation operations."""

    def test_undo_creation(self, app_client):
        """Stage creation, undo removes it."""
        client, config_dir = app_client
        session_id = "test-undo-creation"

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [{
                "id": "new-host-123",
                "object_type": "host",
                "name": "new-host",
                "targetFile": str(config_dir / "hosts.cfg"),
                "attributes": {"host_name": "new-host", "alias": "New Host"}
            }],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        response = client.post('/api/staging', json=staging_data,
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Undo the creation
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        # Verify stagedCreations is empty
        staging_resp = client.get('/api/staging',
                                  headers={'X-Session-Id': session_id}).get_json()
        assert staging_resp.get('staging', {}).get('stagedCreations', []) == []


class TestUndoDeletion:
    """Tests for undoing deletion operations."""

    def test_undo_deletion(self, app_client):
        """Stage deletion, undo removes it."""
        client, config_dir = app_client
        session_id = "test-undo-deletion"

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [{
                "key": "host:web-server-01",
                "name": "web-server-01",
                "object_type": "host",
                "source_file": str(config_dir / "hosts.cfg")
            }],
            "newFiles": []
        }
        response = client.post('/api/staging', json=staging_data,
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Undo the deletion
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        # Verify stagedObjectDeletions is empty
        staging_resp = client.get('/api/staging',
                                  headers={'X-Session-Id': session_id}).get_json()
        assert staging_resp.get('staging', {}).get('stagedObjectDeletions', []) == []

    def test_undo_deletion_empty_list(self, app_client):
        """Undo deletion succeeds when stagedObjectDeletions is empty."""
        client, config_dir = app_client
        session_id = "test-undo-del-empty"

        # Stage a deletion
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [{
                "key": "host:web-server-01",
                "name": "web-server-01",
                "object_type": "host",
                "source_file": str(config_dir / "hosts.cfg")
            }],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data,
                    headers={'X-Session-Id': session_id})

        # Re-save with empty deletions
        staging_empty = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_empty,
                    headers={'X-Session-Id': session_id})

        # Undo succeeds
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200
        assert response.get_json()['success'] is True


class TestUndoEdgeCases:
    """Edge case tests for undo system."""

    def test_undo_empty_stack(self, app_client):
        """Undo with empty stack returns 400."""
        client, config_dir = app_client
        session_id = "test-undo-empty-stack"

        # Acquire session first
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data,
                    headers={'X-Session-Id': session_id})

        # Undo with empty stack
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 400
        assert 'Nothing to undo' in response.get_json()['error']

    def test_undo_no_session_header(self, app_client):
        """Undo without session header returns 400."""
        client, config_dir = app_client

        response = client.post('/api/staging/undo')
        assert response.status_code == 400

    def test_undo_entry_stores_key_from_globalindex(self, app_client):
        """Undo entry key is derived from globalIndex for list-format entries."""
        client, config_dir = app_client
        session_id = "test-undo-key-gi"

        # Stage edit with list-format (globalIndex=5)
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[5, {
                "object": {"name": "test-obj", "object_type": "host"},
                "originalAttributes": {"alias": "Original"},
                "newAttributes": {"alias": "Changed"}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }
        client.post('/api/staging', json=staging_data,
                    headers={'X-Session-Id': session_id})

        # Verify undo stack has entry with key derived from globalIndex
        info = client.get('/api/staging/info-extended',
                          headers={'X-Session-Id': session_id}).get_json()
        assert info['undoStackLength'] == 1

        # Undo should work (matching by globalIndex-derived key)
        response = client.post('/api/staging/undo',
                               headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        staging_resp = client.get('/api/staging',
                                  headers={'X-Session-Id': session_id}).get_json()
        assert staging_resp.get('staging', {}).get('pendingEdits', []) == []
