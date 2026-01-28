"""
Critical UI element tests - P0 priority items.

These tests verify the most critical UI behaviors:
1. Drag-drop with correct positioning
2. Commit dialog - view diffs, commit, discard, cancel
3. Inline editing reflects in git
4. Object creation/deletion reflects in git
5. Commit badge shows correct count
"""

import pytest
import os
import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def git_config_dir(tmp_path):
    """Create a test config with git initialized."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create hosts.cfg with multiple hosts in specific order
    hosts_cfg = config_dir / "hosts.cfg"
    hosts_cfg.write_text("""define host {
    host_name       host-alpha
    alias           Alpha Host
    address         192.168.1.1
}

define host {
    host_name       host-beta
    alias           Beta Host
    address         192.168.1.2
}

define host {
    host_name       host-gamma
    alias           Gamma Host
    address         192.168.1.3
}
""")

    # Create services.cfg with services
    services_cfg = config_dir / "services.cfg"
    services_cfg.write_text("""define service {
    host_name               host-alpha
    service_description     HTTP
    check_command           check_http
}

define service {
    host_name               host-alpha
    service_description     SSH
    check_command           check_ssh
}

define service {
    host_name               host-beta
    service_description     PING
    check_command           check_ping
}
""")

    # Initialize git
    subprocess.run(["git", "init"], cwd=config_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=config_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=config_dir, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=config_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=config_dir, capture_output=True)

    return config_dir


@pytest.fixture
def app_client(git_config_dir):
    """Create Flask test client."""
    import app as flask_app

    # Create a fresh app instance with test config
    test_app = flask_app.create_app(config_path=str(git_config_dir))
    test_app.config['TESTING'] = True
    client = test_app.test_client()

    yield client, git_config_dir


# =============================================================================
# DRAG-DROP POSITIONING TESTS
# =============================================================================

class TestDragDropPositioning:
    """Test that drag-drop inserts objects at the correct position."""

    def test_move_object_to_beginning_of_file(self, app_client):
        """Moving an object with insertPosition=0 places it at the start."""
        client, config_dir = app_client
        session_id = "test-pos-begin"

        response = client.get('/api/objects')
        objects = response.get_json()

        # Find the PING service (in services.cfg)
        ping_service = next(o for o in objects if o.get('name') == 'PING')

        # Move to hosts.cfg at position 0 (beginning)
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [[ping_service['global_index'], {
                "originalFile": ping_service['source_file'],
                "targetFile": str(config_dir / "hosts.cfg"),
                "object": {
                    "source_file": ping_service['source_file'],
                    "line_number": ping_service['line_number'],
                    "object_type": ping_service['object_type'],
                    "attributes": ping_service['attributes'],
                    "global_index": ping_service['global_index'],
                    "name": ping_service['name']
                },
                "insertPosition": 0  # Beginning of file
            }]],
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

        # Verify the object is at the beginning of hosts.cfg
        content = (config_dir / "hosts.cfg").read_text()
        lines = content.split('\n')

        # Find first "define" line
        first_define_idx = next(i for i, l in enumerate(lines) if l.strip().startswith('define'))
        first_define_line = lines[first_define_idx]

        # The PING service should be first (since we inserted at position 0)
        # Check that "check_ping" appears before any host definitions
        ping_pos = content.find('check_ping')
        alpha_pos = content.find('host-alpha')

        assert ping_pos < alpha_pos, "PING service should be before host-alpha when inserted at position 0"

    def test_move_object_to_end_of_file(self, app_client):
        """Moving an object without insertPosition places it at the end."""
        client, config_dir = app_client
        session_id = "test-pos-end"

        response = client.get('/api/objects')
        objects = response.get_json()

        # Find the HTTP service
        http_service = next(o for o in objects if o.get('name') == 'HTTP')

        # Move to hosts.cfg without specifying position (should go to end)
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [[http_service['global_index'], {
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
                # No insertPosition = end of file
            }]],
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

        # Verify the object is at the end
        content = (config_dir / "hosts.cfg").read_text()

        # HTTP service should be after all hosts
        http_pos = content.find('check_http')
        gamma_pos = content.find('host-gamma')

        assert http_pos > gamma_pos, "HTTP service should be after host-gamma when appended"

    def test_git_diff_shows_correct_position(self, app_client):
        """Git diff accurately shows where the object was inserted."""
        client, config_dir = app_client
        session_id = "test-diff-pos"

        response = client.get('/api/objects')
        objects = response.get_json()

        ssh_service = next(o for o in objects if o.get('name') == 'SSH')

        # Move SSH service to hosts.cfg
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [[ssh_service['global_index'], {
                "originalFile": ssh_service['source_file'],
                "targetFile": str(config_dir / "hosts.cfg"),
                "object": {
                    "source_file": ssh_service['source_file'],
                    "line_number": ssh_service['line_number'],
                    "object_type": ssh_service['object_type'],
                    "attributes": ssh_service['attributes'],
                    "global_index": ssh_service['global_index'],
                    "name": ssh_service['name']
                }
            }]],
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

        # Get the git diff
        response = client.get('/api/staging/diff')
        diff_data = response.get_json()

        # Find hosts.cfg diff
        hosts_diff = None
        for d in diff_data.get('diffs', []):
            if 'hosts.cfg' in d.get('file_path', ''):
                hosts_diff = d
                break

        assert hosts_diff is not None, "Should have diff for hosts.cfg"

        # Verify diff contains the added service
        diff_text = hosts_diff.get('diff', '')
        assert '+' in diff_text and 'check_ssh' in diff_text, "Diff should show SSH service was added"


# =============================================================================
# COMMIT DIALOG TESTS
# =============================================================================

class TestCommitDialog:
    """Test the commit dialog functionality."""

    def test_staging_diff_returns_file_list(self, app_client):
        """Commit dialog should show list of changed files."""
        client, config_dir = app_client
        session_id = "test-dialog-files"

        # Make a change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-alpha')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "Modified Alpha"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Get diff for dialog
        response = client.get('/api/staging/diff')
        assert response.status_code == 200
        data = response.get_json()

        # Should have git changes
        assert data.get('hasGitChanges') is True
        assert len(data.get('gitChanges', [])) == 1
        assert 'hosts.cfg' in data['gitChanges'][0]['path']

    def test_staging_diff_returns_actual_diff_content(self, app_client):
        """Clicking a file in dialog should show actual diff."""
        client, config_dir = app_client
        session_id = "test-dialog-diff"

        # Make a specific change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-beta')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "address": "10.0.0.99"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Get diff
        response = client.get('/api/staging/diff')
        data = response.get_json()

        # Check actual diff content
        diffs = data.get('diffs', [])
        assert len(diffs) == 1

        diff_content = diffs[0].get('diff', '')
        assert '-' in diff_content and '192.168.1.2' in diff_content, "Diff should show old address removed"
        assert '+' in diff_content and '10.0.0.99' in diff_content, "Diff should show new address added"

    def test_commit_creates_git_commit(self, app_client):
        """Clicking Commit button creates actual git commit."""
        client, config_dir = app_client
        session_id = "test-dialog-commit"

        # Get initial commit count
        result = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=config_dir, capture_output=True, text=True)
        initial_count = int(result.stdout.strip())

        # Make a change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-gamma')

        staging_data = {
            "sessionId": session_id,
            "userName": "Test User",
            "userEmail": "test@test.com",
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "Committed Change"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Click "Commit" - simulated by POST to /api/git/commit
        response = client.post('/api/git/commit', json={
            "message": "Test commit message",
            "user_name": "Test User",
            "user_email": "test@test.com"
        }, headers={'X-Session-Id': session_id})

        assert response.status_code == 200

        # Verify commit was created
        result = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=config_dir, capture_output=True, text=True)
        new_count = int(result.stdout.strip())
        assert new_count == initial_count + 1

        # Verify commit message
        result = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=config_dir, capture_output=True, text=True)
        assert "Test commit message" in result.stdout

    def test_discard_all_restores_files(self, app_client):
        """Clicking Discard All restores all files."""
        client, config_dir = app_client
        session_id = "test-dialog-discard"

        original_content = (config_dir / "hosts.cfg").read_text()

        # Make changes
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-alpha')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "SHOULD BE DISCARDED"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify change was made
        assert "SHOULD BE DISCARDED" in (config_dir / "hosts.cfg").read_text()

        # Click "Discard All"
        response = client.post('/api/git/discard-all', json={}, headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify file restored
        restored = (config_dir / "hosts.cfg").read_text()
        assert restored == original_content
        assert "SHOULD BE DISCARDED" not in restored

    def test_cancel_preserves_changes(self, app_client):
        """Closing dialog without action preserves pending changes."""
        client, config_dir = app_client
        session_id = "test-dialog-cancel"

        # Make changes
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-beta')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "Preserved Change"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # "Cancel" = just close dialog, don't call any endpoint
        # The changes should still be in the file (uncommitted)

        # Verify changes still in file
        assert "Preserved Change" in (config_dir / "hosts.cfg").read_text()

        # Verify there are uncommitted git changes
        response = client.get('/api/staging/diff')
        assert len(response.get_json().get('gitChanges', [])) > 0


# =============================================================================
# COMMIT BADGE COUNT TESTS
# =============================================================================

class TestCommitBadgeCount:
    """Test that the commit badge shows correct count."""

    def test_badge_count_zero_when_clean(self, app_client):
        """Badge shows 0 (or hidden) when no changes."""
        client, config_dir = app_client

        response = client.get('/api/staging/diff')
        data = response.get_json()

        git_changes = data.get('gitChanges', [])
        assert len(git_changes) == 0, "Should have no changes initially"

    def test_badge_count_increases_with_edits(self, app_client):
        """Badge count increases when making edits."""
        client, config_dir = app_client
        session_id = "test-badge-edit"

        # Initial state
        response = client.get('/api/staging/diff')
        initial_count = len(response.get_json().get('gitChanges', []))

        # Make an edit
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-alpha')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "Badge Test"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Check count increased
        response = client.get('/api/staging/diff')
        new_count = len(response.get_json().get('gitChanges', []))
        assert new_count == initial_count + 1

    def test_badge_count_for_move_shows_two_files(self, app_client):
        """Moving object between files shows 2 in badge."""
        client, config_dir = app_client
        session_id = "test-badge-move"

        response = client.get('/api/objects')
        objects = response.get_json()
        service = next(o for o in objects if o.get('name') == 'HTTP')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [[service['global_index'], {
                "originalFile": service['source_file'],
                "targetFile": str(config_dir / "hosts.cfg"),
                "object": {
                    "source_file": service['source_file'],
                    "line_number": service['line_number'],
                    "object_type": service['object_type'],
                    "attributes": service['attributes'],
                    "global_index": service['global_index'],
                    "name": service['name']
                }
            }]],
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

        response = client.get('/api/staging/diff')
        count = len(response.get_json().get('gitChanges', []))
        assert count == 2, "Move should affect 2 files (source and target)"

    def test_badge_count_resets_after_commit(self, app_client):
        """Badge count returns to 0 after commit."""
        client, config_dir = app_client
        session_id = "test-badge-reset"

        # Make a change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-gamma')

        staging_data = {
            "sessionId": session_id,
            "userName": "Test",
            "userEmail": "test@test.com",
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "For Badge Reset Test"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify count > 0
        response = client.get('/api/staging/diff')
        assert len(response.get_json().get('gitChanges', [])) > 0

        # Commit
        client.post('/api/git/commit', json={
            "message": "Test",
            "user_name": "Test",
            "user_email": "test@test.com"
        }, headers={'X-Session-Id': session_id})

        # Verify count = 0
        response = client.get('/api/staging/diff')
        assert len(response.get_json().get('gitChanges', [])) == 0

    def test_badge_count_resets_after_discard(self, app_client):
        """Badge count returns to 0 after discard all."""
        client, config_dir = app_client
        session_id = "test-badge-discard"

        # Make a change
        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-alpha')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "For Badge Discard Test"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Verify count > 0
        response = client.get('/api/staging/diff')
        assert len(response.get_json().get('gitChanges', [])) > 0

        # Discard
        client.post('/api/git/discard-all', json={}, headers={'X-Session-Id': session_id})

        # Verify count = 0
        response = client.get('/api/staging/diff')
        assert len(response.get_json().get('gitChanges', [])) == 0


# =============================================================================
# INLINE EDITING GIT REFLECTION TESTS
# =============================================================================

class TestInlineEditingGitReflection:
    """Test that inline edits are immediately reflected in git."""

    def test_edit_single_attribute_shows_in_git_diff(self, app_client):
        """Editing one attribute shows correct diff."""
        client, config_dir = app_client
        session_id = "test-inline-single"

        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-alpha')

        # Edit just the alias
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "New Alias Value"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Check git diff
        response = client.post('/api/git/diff', json={"file": "hosts.cfg"})
        diff = response.get_json().get('diff', '')

        # Should show the old alias removed and new alias added
        assert '-' in diff and 'Alpha Host' in diff, "Diff should show old alias"
        assert '+' in diff and 'New Alias Value' in diff, "Diff should show new alias"

    def test_edit_preserves_other_attributes(self, app_client):
        """Editing one attribute doesn't change others in the file."""
        client, config_dir = app_client
        session_id = "test-inline-preserve"

        original_content = (config_dir / "hosts.cfg").read_text()

        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-beta')

        # Edit only alias
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[host['global_index'], {
                "original": host['attributes'],
                "edited": {**host['attributes'], "alias": "Modified Beta"},
                "object": {"source_file": host['source_file'], "line_number": host['line_number'], "object_type": host['object_type']}
            }]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        new_content = (config_dir / "hosts.cfg").read_text()

        # host-alpha and host-gamma should be unchanged
        assert "host-alpha" in new_content
        assert "Alpha Host" in new_content  # alpha's alias unchanged
        assert "host-gamma" in new_content
        assert "Gamma Host" in new_content  # gamma's alias unchanged

        # Only host-beta's alias should change
        assert "Modified Beta" in new_content
        assert "Beta Host" not in new_content  # old value gone


# =============================================================================
# OBJECT CREATION/DELETION GIT REFLECTION TESTS
# =============================================================================

class TestObjectCreationDeletionGit:
    """Test that creation and deletion are reflected in git."""

    def test_create_object_shows_in_git_diff(self, app_client):
        """Creating an object shows it added in git diff."""
        client, config_dir = app_client
        session_id = "test-create-git"

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [{
                "object_type": "host",
                "attributes": {
                    "host_name": "new-created-host",
                    "alias": "Newly Created",
                    "address": "10.10.10.10"
                },
                "targetFile": str(config_dir / "hosts.cfg")
            }],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Check git diff
        response = client.post('/api/git/diff', json={"file": "hosts.cfg"})
        diff = response.get_json().get('diff', '')

        # All lines of new object should be additions
        assert '+' in diff and 'new-created-host' in diff
        assert '+' in diff and 'Newly Created' in diff
        assert '+' in diff and '10.10.10.10' in diff

    def test_delete_object_shows_in_git_diff(self, app_client):
        """Deleting an object shows it removed in git diff."""
        client, config_dir = app_client
        session_id = "test-delete-git"

        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-gamma')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [host['global_index']],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Check git diff
        response = client.post('/api/git/diff', json={"file": "hosts.cfg"})
        diff = response.get_json().get('diff', '')

        # All lines of deleted object should be removals
        assert '-' in diff and 'host-gamma' in diff
        assert '-' in diff and 'Gamma Host' in diff

    def test_create_and_delete_in_same_session(self, app_client):
        """Can create and delete objects in the same session."""
        client, config_dir = app_client
        session_id = "test-create-delete"

        response = client.get('/api/objects')
        objects = response.get_json()
        host_to_delete = next(o for o in objects if o.get('name') == 'host-alpha')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [{
                "object_type": "host",
                "attributes": {
                    "host_name": "replacement-host",
                    "alias": "Replacement",
                    "address": "1.1.1.1"
                },
                "targetFile": str(config_dir / "hosts.cfg")
            }],
            "stagedObjectDeletions": [host_to_delete['global_index']],
            "newFiles": []
        }

        client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        content = (config_dir / "hosts.cfg").read_text()

        # Old host should be gone
        assert "host-alpha" not in content

        # New host should exist
        assert "replacement-host" in content

        # Other hosts should remain
        assert "host-beta" in content
        assert "host-gamma" in content


class TestIdempotency:
    """Tests for idempotent staging operations.

    These tests verify that calling the staging endpoint multiple times
    with the same data doesn't cause duplicate objects.
    """

    def test_move_idempotency(self, app_client):
        """Calling staging POST multiple times with same move doesn't duplicate objects."""
        client, config_dir = app_client
        session_id = "test-move-idempotent"

        # Get the PING service
        response = client.get('/api/objects')
        objects = response.get_json()
        ping_service = next(o for o in objects if o.get('name') == 'PING')

        # Create staging data for move
        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [[
                ping_service['global_index'],
                {
                    "insertPosition": 1.5,
                    "object": {
                        "attributes": ping_service['attributes'],
                        "line_number": ping_service['line_number'],
                        "object_type": "service",
                        "source_file": ping_service['source_file']
                    },
                    "originalFile": ping_service['source_file'],
                    "targetFile": str(config_dir / "hosts.cfg")
                }
            ]],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        # Call staging POST THREE times (simulating multiple saveStagedChanges calls)
        for i in range(3):
            response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
            assert response.status_code == 200

        # Commit the changes (moves are applied on commit, not on staging save)
        response = client.post(
            '/api/staging/commit',
            json={},
            headers={'X-Session-Id': session_id, 'Content-Type': 'application/json'}
        )
        assert response.status_code == 200, f"Commit failed: {response.get_json()}"

        # Check hosts.cfg - PING should appear EXACTLY ONCE
        content = (config_dir / "hosts.cfg").read_text()
        ping_count = content.count("service_description           PING")
        assert ping_count == 1, f"PING service appears {ping_count} times, should be 1"

        # Check services.cfg - PING should be GONE
        services_content = (config_dir / "services.cfg").read_text()
        assert "service_description           PING" not in services_content

    def test_create_idempotency(self, app_client):
        """Calling staging POST multiple times with same creation doesn't duplicate objects."""
        client, config_dir = app_client
        session_id = "test-create-idempotent"

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [],
            "stagedMoves": [],
            "stagedCreations": [{
                "object_type": "host",
                "attributes": {
                    "host_name": "unique-test-host",
                    "alias": "Unique Test",
                    "address": "7.7.7.7"
                },
                "targetFile": str(config_dir / "hosts.cfg")
            }],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        # Call staging POST THREE times
        for i in range(3):
            response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
            assert response.status_code == 200

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Check hosts.cfg - host should appear EXACTLY ONCE
        # Use flexible matching since formatting may vary
        content = (config_dir / "hosts.cfg").read_text()
        import re
        host_count = len(re.findall(r'host_name\s+unique-test-host', content))
        assert host_count == 1, f"unique-test-host appears {host_count} times, should be 1"

    def test_edit_idempotency(self, app_client):
        """Calling staging POST multiple times with same edit doesn't corrupt data."""
        client, config_dir = app_client
        session_id = "test-edit-idempotent"

        response = client.get('/api/objects')
        objects = response.get_json()
        host = next(o for o in objects if o.get('name') == 'host-alpha')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[
                host['global_index'],
                {
                    "original": {"alias": "Alpha Host"},
                    "edited": {"alias": "Edited Alpha"},
                    "object": {
                        "source_file": host['source_file'],
                        "line_number": host['line_number'],
                        "object_type": "host"
                    }
                }
            ]],
            "stagedMoves": [],
            "stagedCreations": [],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        # Call staging POST THREE times
        for i in range(3):
            response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
            assert response.status_code == 200

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Check hosts.cfg - host-alpha should appear EXACTLY ONCE
        # Use flexible matching since formatting may vary
        content = (config_dir / "hosts.cfg").read_text()
        import re
        alpha_count = len(re.findall(r'host_name\s+host-alpha', content))
        assert alpha_count == 1, f"host-alpha appears {alpha_count} times, should be 1"

        # And it should have the edited alias
        assert "Edited Alpha" in content

    def test_combined_operations_idempotency(self, app_client):
        """Multiple operations in staging are all idempotent."""
        import re
        client, config_dir = app_client
        session_id = "test-combined-idempotent"

        response = client.get('/api/objects')
        objects = response.get_json()
        ping_service = next(o for o in objects if o.get('name') == 'PING')
        host_beta = next(o for o in objects if o.get('name') == 'host-beta')

        staging_data = {
            "sessionId": session_id,
            "pendingEdits": [[
                host_beta['global_index'],
                {
                    "original": {"alias": "Beta Host"},
                    "edited": {"alias": "Modified Beta"},
                    "object": {
                        "source_file": host_beta['source_file'],
                        "line_number": host_beta['line_number'],
                        "object_type": "host"
                    }
                }
            ]],
            "stagedMoves": [[
                ping_service['global_index'],
                {
                    "insertPosition": 1.5,
                    "object": {
                        "attributes": ping_service['attributes'],
                        "line_number": ping_service['line_number'],
                        "object_type": "service",
                        "source_file": ping_service['source_file']
                    },
                    "originalFile": ping_service['source_file'],
                    "targetFile": str(config_dir / "hosts.cfg")
                }
            ]],
            "stagedCreations": [{
                "object_type": "host",
                "attributes": {
                    "host_name": "new-combined-host",
                    "alias": "Combined Test",
                    "address": "8.8.8.8"
                },
                "targetFile": str(config_dir / "hosts.cfg")
            }],
            "stagedObjectDeletions": [],
            "newFiles": []
        }

        # Call staging POST FIVE times
        for i in range(5):
            response = client.post('/api/staging', json=staging_data, headers={'X-Session-Id': session_id})
            assert response.status_code == 200

        response = client.post('/api/staging/apply', headers={'X-Session-Id': session_id})
        assert response.status_code == 200

        # Commit the changes (moves are applied on commit, not on staging save)
        response = client.post(
            '/api/staging/commit',
            json={},
            headers={'X-Session-Id': session_id, 'Content-Type': 'application/json'}
        )
        assert response.status_code == 200, f"Commit failed: {response.get_json()}"

        # Verify all operations happened exactly once
        content = (config_dir / "hosts.cfg").read_text()

        # Edit should be applied - Modified Beta should appear
        assert "Modified Beta" in content

        # Count HOST definitions (not services) with host-beta
        # Use multiline regex to find "define host" blocks containing host-beta
        host_beta_count = len(re.findall(r'define host \{[^}]*host_name\s+host-beta[^}]*\}', content, re.DOTALL))
        assert host_beta_count == 1, f"host-beta HOST definition appears {host_beta_count} times, should be 1"

        # Move should result in exactly one PING service in hosts.cfg
        ping_count = len(re.findall(r'service_description\s+PING', content))
        assert ping_count == 1, f"PING service appears {ping_count} times in hosts.cfg, should be 1"

        # Creation should result in exactly one new host - use flexible matching
        new_host_count = len(re.findall(r'host_name\s+new-combined-host', content))
        assert new_host_count == 1, f"new-combined-host appears {new_host_count} times, should be 1"

        # PING should be removed from services.cfg - use flexible matching
        services_content = (config_dir / "services.cfg").read_text()
        services_ping_count = len(re.findall(r'service_description\s+PING', services_content))
        assert services_ping_count == 0, f"PING should not be in services.cfg, found {services_ping_count}"
