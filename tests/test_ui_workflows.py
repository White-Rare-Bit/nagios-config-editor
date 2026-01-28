"""
Integration tests that simulate actual UI workflows.

These tests verify that the API calls made by the frontend actually work
correctly end-to-end, including:
- Drag-drop moving objects between files
- Editing object attributes
- Creating new objects
- Deleting objects
- Viewing changes in git
- Committing changes
- Discarding changes

Each test simulates the exact sequence of API calls the frontend makes.
"""

import pytest
import os
import sys
import json
import subprocess
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def git_config_dir(tmp_path):
    """Create a temporary config directory with git initialized."""
    config_dir = tmp_path / "nagios-config"
    config_dir.mkdir()

    # Create some config files
    hosts_cfg = config_dir / "hosts.cfg"
    hosts_cfg.write_text("""define host {
    host_name       web-server-01
    alias           Web Server 01
    address         192.168.1.10
    use             linux-server
}

define host {
    host_name       db-server-01
    alias           Database Server 01
    address         192.168.1.20
    use             linux-server
}
""")

    services_cfg = config_dir / "services.cfg"
    services_cfg.write_text("""define service {
    host_name               web-server-01
    service_description     HTTP
    check_command           check_http
    use                     generic-service
}

define service {
    host_name               web-server-01
    service_description     SSH
    check_command           check_ssh
    use                     generic-service
}
""")

    templates_cfg = config_dir / "templates.cfg"
    templates_cfg.write_text("""define host {
    name            linux-server
    register        0
}

define service {
    name            generic-service
    register        0
}
""")

    # Initialize git
    subprocess.run(["git", "init"], cwd=config_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=config_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=config_dir, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=config_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=config_dir, capture_output=True)

    return config_dir


@pytest.fixture
def app_client(git_config_dir):
    """Create a Flask test client with the git config directory."""
    import app as flask_app

    # Create a fresh app instance with test config
    test_app = flask_app.create_app(config_path=str(git_config_dir))
    test_app.config['TESTING'] = True
    client = test_app.test_client()

    yield client, git_config_dir


class TestDragDropMoveWorkflow:
    """Tests for the drag-drop move object workflow."""

    def test_move_service_to_different_file(self, app_client):
        """
        Simulate: User drags a service from services.cfg to hosts.cfg

        Expected:
        1. POST /api/staging saves the move
        2. GET /api/staging/diff shows the change
        3. Git diff shows only services.cfg and hosts.cfg modified
        4. Object is removed from services.cfg and added to hosts.cfg
        """
        client, config_dir = app_client
        session_id = "test-session-123"

        # First, get the current objects to find one to move
        response = client.get('/api/objects')
        assert response.status_code == 200
        objects = response.get_json()

        # Find the HTTP service
        http_service = None
        for obj in objects:
            if obj.get('object_type') == 'service' and obj.get('name') == 'HTTP':
                http_service = obj
                break

        assert http_service is not None, "HTTP service not found"

        # Simulate drag-drop: POST /api/staging with stagedMoves
        staging_data = {
            "sessionId": session_id,
            "userName": "Test User",
            "userEmail": "test@test.com",
            "pendingEdits": [],
            "stagedMoves": [
                [http_service['global_index'], {
                    "originalFile": http_service['source_file'],
                    "targetFile": str(config_dir / "hosts.cfg"),
                    "object": {
                        "source_file": http_service['source_file'],
                        "line_number": http_service['line_number'],
                        "object_type": http_service['object_type'],
                        "attributes": http_service['attributes'],
                        "global_index": http_service['global_index'],
                        "name": http_service['name'],
                        "display_name": http_service.get('display_name', http_service['name'])
                    },
                    "insertPosition": 0
                }]
            ],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        response = client.post(
            '/api/staging',
            json=staging_data,
            headers={'X-Session-Id': session_id}
        )
        assert response.status_code == 200, f"Staging save failed: {response.get_json()}"

        # Commit the changes (moves are applied on commit, not on staging save)
        response = client.post(
            '/api/staging/commit',
            json={},
            headers={'X-Session-Id': session_id, 'Content-Type': 'application/json'}
        )
        assert response.status_code == 200, f"Commit failed: {response.get_json()}"

        # Verify git status shows only services.cfg and hosts.cfg modified
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=config_dir,
            capture_output=True,
            text=True
        )
        modified_files = [line.split()[-1] for line in result.stdout.strip().split('\n') if line]

        # Filter out backup directories that may be created during test
        cfg_files = [f for f in modified_files if f.endswith('.cfg')]
        assert len(cfg_files) == 2, f"Expected 2 cfg files modified, got {len(cfg_files)}: {cfg_files}"
        assert "services.cfg" in cfg_files, f"services.cfg should be modified: {cfg_files}"
        assert "hosts.cfg" in cfg_files, f"hosts.cfg should be modified: {cfg_files}"

        # Verify the object was actually moved
        services_content = (config_dir / "services.cfg").read_text()
        hosts_content = (config_dir / "hosts.cfg").read_text()

        # HTTP service should NOT be in services.cfg anymore (check for its unique check_command)
        assert "check_http" not in services_content, "HTTP service (check_http) should be removed from services.cfg"

        # HTTP service SHOULD be in hosts.cfg now
        assert "check_http" in hosts_content, "HTTP service (check_http) should be added to hosts.cfg"

        # GET /api/staging/diff should show the changes
        response = client.get('/api/staging/diff')
        assert response.status_code == 200
        diff_data = response.get_json()

        assert diff_data.get('hasGitChanges'), "Should report git changes"
        assert len(diff_data.get('gitChanges', [])) == 2, "Should show 2 files changed"

    def test_move_preserves_other_objects(self, app_client):
        """
        Verify that moving one object doesn't affect other objects in the files.
        """
        client, config_dir = app_client
        session_id = "test-session-456"

        # Get original file contents for comparison
        original_services = (config_dir / "services.cfg").read_text()
        original_hosts = (config_dir / "hosts.cfg").read_text()

        # Count objects before
        assert original_services.count("define service") == 2
        assert original_hosts.count("define host") == 2

        # Get objects
        response = client.get('/api/objects')
        objects = response.get_json()

        # Find HTTP service
        http_service = next(obj for obj in objects if obj.get('name') == 'HTTP')

        # Move it
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [
                [http_service['global_index'], {
                    "originalFile": http_service['source_file'],
                    "targetFile": str(config_dir / "hosts.cfg"),
                    "object": {
                        "source_file": http_service['source_file'],
                        "line_number": http_service['line_number'],
                        "object_type": http_service['object_type'],
                        "attributes": http_service['attributes'],
                        "global_index": http_service['global_index'],
                        "name": http_service['name']
                    }
                }]
            ],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Commit the changes (moves are applied on commit, not on staging save)
        response = client.post(
            '/api/staging/commit',
            json={},
            headers={'X-Session-Id': session_id, 'Content-Type': 'application/json'}
        )
        assert response.status_code == 200, f"Commit failed: {response.get_json()}"

        # Verify counts
        new_services = (config_dir / "services.cfg").read_text()
        new_hosts = (config_dir / "hosts.cfg").read_text()

        # services.cfg should have 1 service now (SSH remains)
        assert new_services.count("define service") == 1, "services.cfg should have 1 service"
        assert "service_description     SSH" in new_services, "SSH service should remain"

        # hosts.cfg should have 2 hosts + 1 service now
        assert new_hosts.count("define host") == 2, "hosts.cfg should still have 2 hosts"
        assert new_hosts.count("define service") == 1, "hosts.cfg should have 1 service"


class TestEditObjectWorkflow:
    """Tests for the edit object workflow."""

    def test_edit_host_attribute(self, app_client):
        """
        Simulate: User edits a host's address in the object editor.

        Expected:
        1. POST /api/staging saves the edit
        2. Only that file is modified in git
        3. Only that attribute is changed
        """
        client, config_dir = app_client
        session_id = "test-edit-session"

        # Get objects
        response = client.get('/api/objects')
        objects = response.get_json()

        # Find web-server-01
        host = next(obj for obj in objects if obj.get('name') == 'web-server-01')

        # Edit the address
        edited_attrs = dict(host['attributes'])
        edited_attrs['address'] = '10.0.0.100'

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [
                [host['global_index'], {
                    "original": host['attributes'],
                    "edited": edited_attrs,
                    "object": {
                        "source_file": host['source_file'],
                        "line_number": host['line_number'],
                        "object_type": host['object_type']
                    }
                }]
            ],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify only hosts.cfg is modified
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=config_dir,
            capture_output=True,
            text=True
        )
        modified_files = [line.split()[-1] for line in result.stdout.strip().split('\n') if line]

        assert modified_files == ["hosts.cfg"], f"Only hosts.cfg should be modified: {modified_files}"

        # Verify the change
        hosts_content = (config_dir / "hosts.cfg").read_text()
        assert "10.0.0.100" in hosts_content
        assert "192.168.1.10" not in hosts_content  # Old address should be gone


class TestCreateObjectWorkflow:
    """Tests for the create object workflow."""

    def test_create_new_host(self, app_client):
        """
        Simulate: User creates a new host via the UI.
        """
        client, config_dir = app_client
        session_id = "test-create-session"

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [
                {
                    "object_type": "host",
                    "attributes": {
                        "host_name": "new-server-01",
                        "alias": "New Server",
                        "address": "192.168.1.100",
                        "use": "linux-server"
                    },
                    "targetFile": str(config_dir / "hosts.cfg")
                }
            ],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify the host was created
        hosts_content = (config_dir / "hosts.cfg").read_text()
        assert "host_name" in hosts_content and "new-server-01" in hosts_content
        assert hosts_content.count("define host") == 3  # Original 2 + new 1


class TestDeleteObjectWorkflow:
    """Tests for the delete object workflow."""

    def test_delete_service(self, app_client):
        """
        Simulate: User deletes a service via the UI.
        """
        client, config_dir = app_client
        session_id = "test-delete-session"

        # Get objects
        response = client.get('/api/objects')
        objects = response.get_json()

        # Find SSH service
        ssh_service = next(obj for obj in objects if obj.get('name') == 'SSH')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [ssh_service['global_index']],
            "newFiles": []
        }

        response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify the service was deleted
        services_content = (config_dir / "services.cfg").read_text()
        assert "service_description     SSH" not in services_content
        assert services_content.count("define service") == 1  # Only HTTP remains


class TestCommitWorkflow:
    """Tests for the git commit workflow."""

    def test_commit_changes(self, app_client):
        """
        Simulate: User makes a change, then clicks Commit.
        """
        client, config_dir = app_client
        session_id = "test-commit-session"

        # Get initial commit count
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=config_dir,
            capture_output=True,
            text=True
        )
        initial_commits = int(result.stdout.strip())

        # Make a change (edit a host)
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(obj for obj in objects if obj.get('name') == 'web-server-01')

        edited_attrs = dict(host['attributes'])
        edited_attrs['alias'] = 'Updated Web Server'

        staging_data = {
            "sessionId": session_id,
            "userName": "Test User",
            "userEmail": "test@test.com",
            "pendingEdits": [
                [host['global_index'], {
                    "original": host['attributes'],
                    "edited": edited_attrs,
                    "object": {
                        "source_file": host['source_file'],
                        "line_number": host['line_number'],
                        "object_type": host['object_type']
                    }
                }]
            ],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Now commit via the API (include author info since git config may not be set)
        response = client.post(
            '/api/git/commit',
            json={
                "message": "Test commit from workflow test",
                "user_name": "Test User",
                "user_email": "test@test.com"
            },
            headers={'X-Session-Id': session_id}
        )
        assert response.status_code == 200, f"Commit failed: {response.get_json()}"

        # Verify commit was made
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=config_dir,
            capture_output=True,
            text=True
        )
        new_commits = int(result.stdout.strip())

        assert new_commits == initial_commits + 1, "Should have one more commit"

        # Verify working directory is clean
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=config_dir,
            capture_output=True,
            text=True
        )
        assert result.stdout.strip() == "", "Working directory should be clean after commit"

    def test_commit_clears_staging(self, app_client):
        """
        Verify that committing clears the staging area.
        """
        client, config_dir = app_client
        session_id = "test-commit-clear-session"

        # Make a change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(obj for obj in objects if obj.get('name') == 'db-server-01')

        edited_attrs = dict(host['attributes'])
        edited_attrs['alias'] = 'Modified DB Server'

        staging_data = {
            "sessionId": session_id,
            "userName": "Test User",
            "userEmail": "test@test.com",
            "pendingEdits": [
                [host['global_index'], {
                    "original": host['attributes'],
                    "edited": edited_attrs,
                    "object": {
                        "source_file": host['source_file'],
                        "line_number": host['line_number'],
                        "object_type": host['object_type']
                    }
                }]
            ],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify there are uncommitted git changes (apply wrote to disk)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=config_dir,
            capture_output=True,
            text=True
        )
        assert result.stdout.strip() != "", "Should have uncommitted changes after apply"

        # Commit (with author info)
        response = client.post(
            '/api/git/commit',
            json={
                "message": "Test commit",
                "user_name": "Test User",
                "user_email": "test@test.com"
            },
            headers={'X-Session-Id': session_id}
        )
        assert response.status_code == 200, f"Commit failed: {response.get_json()}"

        # Verify staging is cleared
        response = client.get('/api/staging/info')
        info = response.get_json()
        assert info.get('hasStaging') is False, "Staging should be cleared after commit"


class TestDiscardWorkflow:
    """Tests for the discard changes workflow."""

    def test_discard_all_changes(self, app_client):
        """
        Simulate: User makes changes, then clicks Discard All.
        """
        client, config_dir = app_client
        session_id = "test-discard-session"

        # Save original content
        original_hosts = (config_dir / "hosts.cfg").read_text()

        # Make a change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(obj for obj in objects if obj.get('name') == 'web-server-01')

        edited_attrs = dict(host['attributes'])
        edited_attrs['address'] = '1.2.3.4'

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [
                [host['global_index'], {
                    "original": host['attributes'],
                    "edited": edited_attrs,
                    "object": {
                        "source_file": host['source_file'],
                        "line_number": host['line_number'],
                        "object_type": host['object_type']
                    }
                }]
            ],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify change was made
        modified_hosts = (config_dir / "hosts.cfg").read_text()
        assert "1.2.3.4" in modified_hosts

        # Discard all
        response = client.post(
            '/api/git/discard-all',
            json={},
            headers={'X-Session-Id': session_id}
        )
        assert response.status_code == 200, f"Discard failed: {response.get_json()}"

        # Verify files are restored
        restored_hosts = (config_dir / "hosts.cfg").read_text()
        assert restored_hosts == original_hosts, "File should be restored to original"

        # Verify working directory is clean
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=config_dir,
            capture_output=True,
            text=True
        )
        assert result.stdout.strip() == "", "Working directory should be clean after discard"


class TestStagingDiffView:
    """Tests for the staging diff view (what shows in commit dialog)."""

    def test_diff_shows_correct_changes(self, app_client):
        """
        Verify that /api/staging/diff returns accurate change information.
        """
        client, config_dir = app_client
        session_id = "test-diff-session"

        # Make a change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(obj for obj in objects if obj.get('name') == 'web-server-01')

        edited_attrs = dict(host['attributes'])
        edited_attrs['alias'] = 'Changed Alias'

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [
                [host['global_index'], {
                    "original": host['attributes'],
                    "edited": edited_attrs,
                    "object": {
                        "source_file": host['source_file'],
                        "line_number": host['line_number'],
                        "object_type": host['object_type']
                    }
                }]
            ],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Get the diff
        response = client.get('/api/staging/diff')
        assert response.status_code == 200
        diff_data = response.get_json()

        # Should have git changes
        assert diff_data.get('hasGitChanges') is True
        git_changes = diff_data.get('gitChanges', [])
        assert len(git_changes) == 1
        assert 'hosts.cfg' in git_changes[0]['path']

    def test_diff_shows_move_correctly(self, app_client):
        """
        Verify that moving an object shows both source and target files changed.
        """
        client, config_dir = app_client
        session_id = "test-diff-move-session"

        # Get objects
        response = client.get('/api/objects')
        objects = response.get_json()
        http_service = next(obj for obj in objects if obj.get('name') == 'HTTP')

        # Move it
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [
                [http_service['global_index'], {
                    "originalFile": http_service['source_file'],
                    "targetFile": str(config_dir / "hosts.cfg"),
                    "object": {
                        "source_file": http_service['source_file'],
                        "line_number": http_service['line_number'],
                        "object_type": http_service['object_type'],
                        "attributes": http_service['attributes'],
                        "global_index": http_service['global_index'],
                        "name": http_service['name']
                    }
                }]
            ],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        # Commit the changes (moves are applied on commit, not on staging save)
        response = client.post(
            '/api/staging/commit',
            json={},
            headers={'X-Session-Id': session_id, 'Content-Type': 'application/json'}
        )
        assert response.status_code == 200, f"Commit failed: {response.get_json()}"

        # Get the diff
        response = client.get('/api/staging/diff')
        diff_data = response.get_json()

        assert diff_data.get('hasGitChanges') is True
        git_changes = diff_data.get('gitChanges', [])

        # Should show both files changed
        changed_files = [c['path'] for c in git_changes]
        assert any('services.cfg' in f for f in changed_files), f"services.cfg should be in changes: {changed_files}"
        assert any('hosts.cfg' in f for f in changed_files), f"hosts.cfg should be in changes: {changed_files}"


class TestGitPageView:
    """Tests for what the git page shows."""

    def test_git_status_shows_modified_files(self, app_client):
        """
        Verify /api/git/status shows correct modified files.
        """
        client, config_dir = app_client
        session_id = "test-git-status-session"

        # Make a change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(obj for obj in objects if obj.get('name') == 'web-server-01')

        edited_attrs = dict(host['attributes'])
        edited_attrs['alias'] = 'Modified'

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [
                [host['global_index'], {
                    "original": host['attributes'],
                    "edited": edited_attrs,
                    "object": {
                        "source_file": host['source_file'],
                        "line_number": host['line_number'],
                        "object_type": host['object_type']
                    }
                }]
            ],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Check git status API
        response = client.get('/api/git/status')
        assert response.status_code == 200
        status = response.get_json()

        assert status.get('has_changes') is True
        # Check files list for hosts.cfg
        files = status.get('files', [])
        file_paths = [f['path'] for f in files]
        assert 'hosts.cfg' in file_paths, f"hosts.cfg should be in changed files: {file_paths}"
