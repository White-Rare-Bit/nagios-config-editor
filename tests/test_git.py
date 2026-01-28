"""
Tests for Git API endpoints in app.py
"""

import pytest
import os
import sys
import json
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def flask_app_with_git():
    """Create a Flask test client with a git-enabled temp directory."""
    import app as flask_app_module

    temp_dir = tempfile.mkdtemp(prefix='nagios_git_test_')

    # Create minimal config files
    hosts_content = '''define host {
    host_name       test-host
    alias           Test Host
    address         127.0.0.1
}
'''
    with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
        f.write(hosts_content)

    # Configure the app
    flask_app_module.config['backup_path'] = os.path.join(temp_dir, 'backups')
    test_app = flask_app_module.create_app(config_path=temp_dir)
    test_app.config['TESTING'] = True

    with test_app.test_client() as client:
        yield client, temp_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


def init_git_repo(path):
    """Initialize a git repository in the given path."""
    subprocess.run(['git', 'init'], cwd=path, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=path, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=path, capture_output=True, check=True)


def make_initial_commit(path):
    """Make an initial commit with all files."""
    subprocess.run(['git', 'add', '-A'], cwd=path, capture_output=True, check=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=path, capture_output=True, check=True)


class TestGitStatus:
    """Tests for /api/git/status endpoint."""

    def test_status_not_a_repo(self, flask_app_with_git):
        """Test git status when directory is not a git repository."""
        client, temp_dir = flask_app_with_git

        response = client.get('/api/git/status')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['is_repo'] is False
        assert 'error' in data

    def test_status_clean_repo(self, flask_app_with_git):
        """Test git status when repository has no changes."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        response = client.get('/api/git/status')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['is_repo'] is True
        assert data['has_changes'] is False
        assert data['files'] == []
        assert 'branch' in data

    def test_status_with_modified_file(self, flask_app_with_git):
        """Test git status when repository has modified files."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Modify a file
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# Modified\n')

        response = client.get('/api/git/status')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['is_repo'] is True
        assert data['has_changes'] is True
        assert len(data['files']) == 1
        assert data['files'][0]['path'] == 'hosts.cfg'
        assert data['files'][0]['status'] == 'modified'

    def test_status_with_untracked_file(self, flask_app_with_git):
        """Test git status when repository has untracked files."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Create a new untracked file
        with open(os.path.join(temp_dir, 'new_file.cfg'), 'w') as f:
            f.write('define host { host_name new-host }')

        response = client.get('/api/git/status')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['has_changes'] is True
        assert any(f['path'] == 'new_file.cfg' and f['status'] == 'untracked' for f in data['files'])


class TestGitDiff:
    """Tests for /api/git/diff endpoint."""

    def test_diff_modified_file(self, flask_app_with_git):
        """Test getting diff for a modified file."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Modify a file
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# New comment\n')

        response = client.post('/api/git/diff',
                               data=json.dumps({'file': 'hosts.cfg'}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert 'diff' in data
        assert '# New comment' in data['diff']

    def test_diff_no_file_specified(self, flask_app_with_git):
        """Test diff endpoint without specifying a file returns all changes."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Modify a file
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# All changes diff test\n')

        response = client.post('/api/git/diff',
                               data=json.dumps({}),
                               content_type='application/json')
        data = json.loads(response.data)

        # Should return 200 with diff for all changes
        assert response.status_code == 200
        assert 'diff' in data
        assert '# All changes diff test' in data['diff']

    def test_diff_untracked_file(self, flask_app_with_git):
        """Test getting diff for an untracked file."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Create a new untracked file
        new_content = 'define host { host_name new-host }'
        with open(os.path.join(temp_dir, 'new_file.cfg'), 'w') as f:
            f.write(new_content)

        response = client.post('/api/git/diff',
                               data=json.dumps({'file': 'new_file.cfg'}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        # For untracked files, should show file content
        assert 'diff' in data


class TestGitCommit:
    """Tests for /api/git/commit endpoint."""

    def test_commit_changes(self, flask_app_with_git):
        """Test committing changes."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Modify a file
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# Modified for commit test\n')

        response = client.post('/api/git/commit',
                               data=json.dumps({
                                   'message': 'Test commit',
                                   'user_name': 'Test User',
                                   'user_email': 'test@example.com'
                               }),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['success'] is True
        assert 'commit_hash' in data
        assert len(data['commit_hash']) > 0

    def test_commit_no_message(self, flask_app_with_git):
        """Test commit without a message."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)

        response = client.post('/api/git/commit',
                               data=json.dumps({}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 400
        assert 'error' in data

    def test_commit_nothing_to_commit(self, flask_app_with_git):
        """Test commit when there are no changes."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        response = client.post('/api/git/commit',
                               data=json.dumps({
                                   'message': 'Empty commit',
                                   'user_name': 'Test User',
                                   'user_email': 'test@example.com'
                               }),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['success'] is False
        assert 'Nothing to commit' in data.get('error', '') or 'nothing to commit' in data.get('message', '').lower()

    def test_commit_auto_init(self, flask_app_with_git):
        """Test commit with auto_init when not a git repo."""
        client, temp_dir = flask_app_with_git

        # Don't initialize git - test auto_init
        response = client.post('/api/git/commit',
                               data=json.dumps({
                                   'message': 'Initial commit',
                                   'auto_init': True,
                                   'user_name': 'Test User',
                                   'user_email': 'test@example.com'
                               }),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['success'] is True
        assert data['initialized'] is True
        assert 'commit_hash' in data

        # Verify git was initialized
        assert os.path.isdir(os.path.join(temp_dir, '.git'))

        # Verify .gitignore was created with correct content
        gitignore_path = os.path.join(temp_dir, '.gitignore')
        assert os.path.exists(gitignore_path)
        with open(gitignore_path, 'r') as f:
            gitignore_content = f.read()
        assert 'backups/' in gitignore_content
        assert '.nagios_staging/' in gitignore_content

    def test_commit_without_auto_init_not_repo(self, flask_app_with_git):
        """Test commit without auto_init when not a git repo."""
        client, temp_dir = flask_app_with_git

        # Don't initialize git
        response = client.post('/api/git/commit',
                               data=json.dumps({
                                   'message': 'Test commit',
                                   'auto_init': False,
                                   'user_name': 'Test User',
                                   'user_email': 'test@example.com'
                               }),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 400
        assert 'error' in data


class TestGitDiscard:
    """Tests for /api/git/discard endpoint."""

    def test_discard_modified_file(self, flask_app_with_git):
        """Test discarding changes to a modified file."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Read original content
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'r') as f:
            original_content = f.read()

        # Modify a file
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# This should be discarded\n')

        response = client.post('/api/git/discard',
                               data=json.dumps({'file': 'hosts.cfg'}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['success'] is True

        # Verify file was restored
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'r') as f:
            restored_content = f.read()
        assert restored_content == original_content

    def test_discard_untracked_file(self, flask_app_with_git):
        """Test discarding an untracked file (should delete it)."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make initial commit
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Create a new untracked file
        new_file_path = os.path.join(temp_dir, 'untracked.cfg')
        with open(new_file_path, 'w') as f:
            f.write('define host { host_name untracked }')

        response = client.post('/api/git/discard',
                               data=json.dumps({'file': 'untracked.cfg'}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['success'] is True

        # Verify file was deleted
        assert not os.path.exists(new_file_path)

    def test_discard_no_file_specified(self, flask_app_with_git):
        """Test discard without specifying a file."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)

        response = client.post('/api/git/discard',
                               data=json.dumps({}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 400
        assert 'error' in data

    def test_discard_path_traversal_attempt(self, flask_app_with_git):
        """Test that path traversal attempts are blocked."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)

        response = client.post('/api/git/discard',
                               data=json.dumps({'file': '../../../etc/passwd'}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 400
        assert 'error' in data


class TestGitLog:
    """Tests for /api/git/log endpoint."""

    def test_log_not_a_repo(self, flask_app_with_git):
        """Test git log when directory is not a git repository."""
        client, temp_dir = flask_app_with_git

        response = client.get('/api/git/log')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['is_repo'] is False
        assert data['commits'] == []

    def test_log_empty_repo(self, flask_app_with_git):
        """Test git log when repository has no commits."""
        client, temp_dir = flask_app_with_git

        # Initialize git but don't commit
        init_git_repo(temp_dir)

        response = client.get('/api/git/log')
        data = json.loads(response.data)

        assert response.status_code == 200
        # Either no commits message or empty list
        assert data.get('commits') == [] or 'No commits' in data.get('message', '')

    def test_log_with_commits(self, flask_app_with_git):
        """Test git log when repository has commits."""
        client, temp_dir = flask_app_with_git

        # Initialize git and make commits
        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Make another commit
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# Second change\n')
        subprocess.run(['git', 'add', '-A'], cwd=temp_dir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Second commit'], cwd=temp_dir, capture_output=True)

        response = client.get('/api/git/log')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['is_repo'] is True
        assert len(data['commits']) == 2
        assert data['commits'][0]['message'] == 'Second commit'
        assert data['commits'][1]['message'] == 'Initial commit'
        assert 'hash' in data['commits'][0]
        assert 'hash_short' in data['commits'][0]
        assert 'author' in data['commits'][0]
        assert 'date' in data['commits'][0]

    def test_log_with_limit(self, flask_app_with_git):
        """Test git log with limit parameter."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Make more commits
        for i in range(3):
            with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
                f.write(f'\n# Change {i}\n')
            subprocess.run(['git', 'add', '-A'], cwd=temp_dir, capture_output=True)
            subprocess.run(['git', 'commit', '-m', f'Commit {i}'], cwd=temp_dir, capture_output=True)

        response = client.get('/api/git/log?limit=2')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert len(data['commits']) == 2


class TestGitRestore:
    """Tests for /api/git/restore endpoint."""

    def test_restore_to_commit(self, flask_app_with_git):
        """Test restoring to a previous commit."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Read original content
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'r') as f:
            original_content = f.read()

        # Make a change and commit
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# New content that will be reverted\n')
        subprocess.run(['git', 'add', '-A'], cwd=temp_dir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Change to revert'], cwd=temp_dir, capture_output=True)

        # Get the first commit hash
        result = subprocess.run(['git', 'log', '--format=%H', '-1', '--skip=1'],
                                cwd=temp_dir, capture_output=True, text=True)
        first_commit = result.stdout.strip()

        # Restore to first commit
        response = client.post('/api/git/restore',
                               data=json.dumps({'commit': first_commit}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['success'] is True

        # Verify content was restored
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'r') as f:
            restored_content = f.read()
        assert restored_content == original_content

    def test_restore_invalid_commit(self, flask_app_with_git):
        """Test restore with invalid commit hash."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        response = client.post('/api/git/restore',
                               data=json.dumps({'commit': 'invalidhash123'}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 404
        assert 'error' in data

    def test_restore_no_commit_specified(self, flask_app_with_git):
        """Test restore without specifying commit."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)

        response = client.post('/api/git/restore',
                               data=json.dumps({}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 400
        assert 'error' in data

    def test_restore_stashes_uncommitted_changes(self, flask_app_with_git):
        """Test that restore stashes uncommitted changes."""
        client, temp_dir = flask_app_with_git

        init_git_repo(temp_dir)
        make_initial_commit(temp_dir)

        # Make uncommitted change
        with open(os.path.join(temp_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# Uncommitted change\n')

        # Get current commit
        result = subprocess.run(['git', 'log', '--format=%H', '-1'],
                                cwd=temp_dir, capture_output=True, text=True)
        commit_hash = result.stdout.strip()

        response = client.post('/api/git/restore',
                               data=json.dumps({'commit': commit_hash}),
                               content_type='application/json')
        data = json.loads(response.data)

        assert response.status_code == 200
        assert data['success'] is True
        assert data['had_uncommitted_changes'] is True
        assert data['stashed'] is True


class TestGitPage:
    """Tests for the /git page route."""

    def test_git_page_loads(self, flask_app_with_git):
        """Test that the git page loads successfully."""
        client, temp_dir = flask_app_with_git

        response = client.get('/git')

        assert response.status_code == 200
        assert b'Git' in response.data
