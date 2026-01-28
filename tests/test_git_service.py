"""
Tests for GitService - centralized git operations.
"""

import os
import sys
import time
import tempfile
import shutil
import subprocess
import threading
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from git_service import (
    GitService, GitRunResult, GitCommit, GitFileStatus, GitStatusResult,
    TIMEOUT_QUERY, TIMEOUT_STATUS, TIMEOUT_MUTATE
)
from nagios_model import OperationResult


@pytest.fixture
def git_dir():
    """Create a temp directory with a git repo and initial commit."""
    temp_dir = tempfile.mkdtemp(prefix='git_service_test_')
    # Create a test file
    with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
        f.write('define host {\n    host_name test-host\n}\n')

    subprocess.run(['git', 'init'], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'],
                   cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test User'],
                   cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(['git', 'add', '-A'], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'],
                   cwd=temp_dir, capture_output=True, check=True)

    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def empty_dir():
    """Create a temp directory without git."""
    temp_dir = tempfile.mkdtemp(prefix='git_service_test_')
    with open(os.path.join(temp_dir, 'hosts.cfg'), 'w') as f:
        f.write('define host {\n    host_name test-host\n}\n')
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def service(git_dir):
    """Create a GitService pointed at git_dir."""
    return GitService(git_dir)


@pytest.fixture
def service_no_repo(empty_dir):
    """Create a GitService pointed at a non-git directory."""
    return GitService(empty_dir)


class TestRunGit:
    """Tests for the _run_git helper."""

    def test_successful_command(self, service):
        result = service._run_git(['rev-parse', '--is-inside-work-tree'])
        assert result.success is True
        assert isinstance(result.data, GitRunResult)
        assert result.data.returncode == 0
        assert result.data.stdout.strip() == 'true'

    def test_failing_command(self, service_no_repo):
        result = service_no_repo._run_git(['rev-parse', '--is-inside-work-tree'])
        # _run_git returns success=False when git command exits with non-zero
        assert result.success is False
        assert result.data.returncode != 0

    def test_timeout(self, service):
        # Use a very short timeout with a slow command
        result = service._run_git(['log', '--all', '--oneline'], timeout=0.001)
        # Either succeeds quickly or times out
        if not result.success:
            assert 'timed out' in result.error

    def test_nonexistent_git(self):
        """Test when git binary is not found."""
        svc = GitService('/nonexistent/path')
        # Monkey-patch to simulate FileNotFoundError
        import unittest.mock as mock
        with mock.patch('subprocess.run', side_effect=FileNotFoundError('git not found')):
            result = svc._run_git(['status'])
            assert result.success is False
            assert 'not installed' in result.error

    def test_retry_on_transient_error(self, service):
        """Test retry logic with a simulated lock error."""
        import unittest.mock as mock
        call_count = [0]
        original_run = subprocess.run

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Simulate index.lock error
                result = mock.Mock()
                result.stdout = ''
                result.stderr = 'fatal: Unable to create index.lock'
                result.returncode = 128
                return result
            return original_run(*args, **kwargs)

        with mock.patch('subprocess.run', side_effect=mock_run):
            result = service._run_git(['status', '--porcelain'], retry=True)
            # Should have retried
            assert call_count[0] >= 2

    def test_no_retry_without_flag(self, service):
        """Test that retry doesn't happen without retry=True."""
        import unittest.mock as mock
        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            result = mock.Mock()
            result.stdout = ''
            result.stderr = 'fatal: Unable to create index.lock'
            result.returncode = 128
            return result

        with mock.patch('subprocess.run', side_effect=mock_run):
            service._run_git(['status'], retry=False)
            assert call_count[0] == 1


class TestIsRepo:
    def test_is_repo_true(self, service):
        result = service.is_repo()
        assert result.success is True
        assert result.data is True

    def test_is_repo_false(self, service_no_repo):
        result = service_no_repo.is_repo()
        assert result.success is True
        assert result.data is False


class TestGetUserIdentity:
    def test_with_configured_identity(self, service, git_dir):
        result = service.get_user_identity()
        assert result.success is True
        assert result.data is not None
        assert result.data['name'] == 'Test User'
        assert result.data['email'] == 'test@test.com'

    def test_without_identity(self, service_no_repo):
        # No git repo, no global config set for this test
        result = service_no_repo.get_user_identity()
        assert result.success is True
        # May return None or global config depending on environment


class TestGetStatus:
    def test_not_a_repo(self, service_no_repo):
        result = service_no_repo.get_status()
        assert result.success is True
        assert result.data.is_repo is False

    def test_clean_repo(self, service):
        result = service.get_status()
        assert result.success is True
        assert result.data.is_repo is True
        assert result.data.has_changes is False
        assert result.data.files == []

    def test_modified_file(self, service, git_dir):
        # Modify a file
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('\n# modified\n')

        result = service.get_status()
        assert result.success is True
        assert result.data.has_changes is True
        assert len(result.data.files) == 1
        assert result.data.files[0].path == 'hosts.cfg'
        assert result.data.files[0].status == 'modified'

    def test_untracked_file(self, service, git_dir):
        with open(os.path.join(git_dir, 'new.cfg'), 'w') as f:
            f.write('new content\n')

        result = service.get_status()
        assert result.success is True
        assert result.data.has_changes is True
        found = [f for f in result.data.files if f.path == 'new.cfg']
        assert len(found) == 1
        assert found[0].status == 'untracked'

    def test_deleted_file(self, service, git_dir):
        os.remove(os.path.join(git_dir, 'hosts.cfg'))

        result = service.get_status()
        assert result.success is True
        assert result.data.has_changes is True
        found = [f for f in result.data.files if f.path == 'hosts.cfg']
        assert len(found) == 1
        assert found[0].status == 'deleted'

    def test_excluded_paths(self, service, git_dir):
        os.makedirs(os.path.join(git_dir, '.backups'), exist_ok=True)
        with open(os.path.join(git_dir, '.backups', 'test.bak'), 'w') as f:
            f.write('backup\n')

        result = service.get_status()
        assert result.success is True
        # .backups/ should be excluded
        paths = [f.path for f in result.data.files]
        assert not any('.backups' in p for p in paths)

    def test_branch_name(self, service):
        result = service.get_status()
        assert result.success is True
        # Should be 'main' or 'master' depending on git config
        assert result.data.branch is not None


class TestGetDiff:
    def test_no_changes(self, service):
        result = service.get_diff()
        assert result.success is True
        assert result.data == ''

    def test_modified_file_diff(self, service, git_dir):
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# new line\n')

        result = service.get_diff(filepath='hosts.cfg')
        assert result.success is True
        assert '# new line' in result.data
        assert '+# new line' in result.data

    def test_untracked_file_diff(self, service, git_dir):
        with open(os.path.join(git_dir, 'newfile.cfg'), 'w') as f:
            f.write('new content\n')

        result = service.get_diff(filepath='newfile.cfg')
        assert result.success is True
        assert 'new file mode' in result.data
        assert '+new content' in result.data

    def test_full_file_context(self, service, git_dir):
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# added\n')

        result = service.get_diff(filepath='hosts.cfg', full_file=True)
        assert result.success is True
        # Full file context shows existing content too
        assert 'host_name' in result.data


class TestGetWorkspaceDiff:
    def test_no_changes(self, service):
        result = service.get_workspace_diff()
        assert result.success is True
        assert result.data['diffs'] == []
        assert result.data['git_changes'] == []

    def test_modified_file(self, service, git_dir):
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# modified\n')

        result = service.get_workspace_diff()
        assert result.success is True
        assert len(result.data['diffs']) == 1
        assert result.data['diffs'][0]['file_path'] == 'hosts.cfg'
        assert result.data['diffs'][0]['status'] == 'modified'

    def test_new_cfg_file(self, service, git_dir):
        with open(os.path.join(git_dir, 'services.cfg'), 'w') as f:
            f.write('define service {\n}\n')

        result = service.get_workspace_diff()
        assert result.success is True
        added = [d for d in result.data['diffs'] if d['status'] == 'added']
        assert len(added) == 1
        assert added[0]['file_path'] == 'services.cfg'

    def test_excludes_non_cfg_untracked(self, service, git_dir):
        with open(os.path.join(git_dir, 'readme.txt'), 'w') as f:
            f.write('not a cfg file\n')

        result = service.get_workspace_diff()
        assert result.success is True
        paths = [d['file_path'] for d in result.data['diffs']]
        assert 'readme.txt' not in paths


class TestGetLog:
    def test_not_a_repo(self, service_no_repo):
        result = service_no_repo.get_log()
        assert result.success is True
        assert result.data['is_repo'] is False

    def test_single_commit(self, service):
        result = service.get_log()
        assert result.success is True
        assert result.data['is_repo'] is True
        assert len(result.data['commits']) == 1
        commit = result.data['commits'][0]
        assert commit.message == 'Initial commit'
        assert commit.author == 'Test User'
        assert len(commit.hash) == 40
        assert len(commit.hash_short) == 7

    def test_multiple_commits(self, service, git_dir):
        # Add more commits
        for i in range(3):
            with open(os.path.join(git_dir, f'file{i}.cfg'), 'w') as f:
                f.write(f'content {i}\n')
            subprocess.run(['git', 'add', '-A'], cwd=git_dir, capture_output=True)
            subprocess.run(['git', 'commit', '-m', f'Commit {i}'],
                           cwd=git_dir, capture_output=True)

        result = service.get_log()
        assert result.success is True
        assert len(result.data['commits']) == 4  # 3 new + initial

    def test_pipe_in_commit_message(self, service, git_dir):
        """Verify that pipe characters in commit messages don't break parsing."""
        msg = 'Fix host|service dependency issue'
        with open(os.path.join(git_dir, 'test.cfg'), 'w') as f:
            f.write('test\n')
        subprocess.run(['git', 'add', '-A'], cwd=git_dir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', msg],
                       cwd=git_dir, capture_output=True)

        result = service.get_log()
        assert result.success is True
        # The commit with pipe should be parsed correctly
        found = [c for c in result.data['commits'] if 'pipe' in c.message.lower() or '|' in c.message]
        assert len(found) == 1
        assert found[0].message == msg

    def test_matching_commit_clean(self, service):
        """When working dir is clean, HEAD should match."""
        result = service.get_log()
        assert result.success is True
        assert result.data['matching_commit'] is not None
        assert result.data['commits'][0].matches_working_dir is True

    def test_matching_commit_dirty(self, service, git_dir):
        """When working dir is dirty, no commit should match."""
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# dirty\n')

        result = service.get_log()
        assert result.success is True
        # HEAD shouldn't match since there are uncommitted changes
        if result.data['commits']:
            assert result.data['commits'][0].matches_working_dir is False

    def test_limit(self, service, git_dir):
        for i in range(5):
            with open(os.path.join(git_dir, f'f{i}.cfg'), 'w') as f:
                f.write(f'{i}\n')
            subprocess.run(['git', 'add', '-A'], cwd=git_dir, capture_output=True)
            subprocess.run(['git', 'commit', '-m', f'C{i}'],
                           cwd=git_dir, capture_output=True)

        result = service.get_log(limit=3)
        assert result.success is True
        assert len(result.data['commits']) == 3

    def test_limit_capped_at_200(self, service):
        result = service.get_log(limit=500)
        assert result.success is True
        # Should work fine, just internally capped


class TestHasUncommittedChanges:
    def test_clean(self, service):
        result = service.has_uncommitted_changes()
        assert result.success is True
        assert result.data is False

    def test_dirty(self, service, git_dir):
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# change\n')

        result = service.has_uncommitted_changes()
        assert result.success is True
        assert result.data is True


class TestInitRepo:
    def test_init_new_repo(self, empty_dir):
        svc = GitService(empty_dir)
        result = svc.init_repo()
        assert result.success is True
        assert os.path.isdir(os.path.join(empty_dir, '.git'))

    def test_creates_gitignore(self, empty_dir):
        svc = GitService(empty_dir)
        svc.init_repo()
        gitignore = os.path.join(empty_dir, '.gitignore')
        assert os.path.exists(gitignore)
        with open(gitignore) as f:
            content = f.read()
        assert 'backups/' in content
        assert '.nagios_staging/' in content

    def test_does_not_overwrite_gitignore(self, empty_dir):
        gitignore = os.path.join(empty_dir, '.gitignore')
        with open(gitignore, 'w') as f:
            f.write('custom content\n')

        svc = GitService(empty_dir)
        svc.init_repo()

        with open(gitignore) as f:
            content = f.read()
        assert content == 'custom content\n'


class TestCommit:
    def test_commit_all(self, service, git_dir):
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# change\n')

        result = service.commit(
            message='Test commit',
            user_name='Test User',
            user_email='test@test.com'
        )
        assert result.success is True
        assert result.data['commit_hash'] != ''
        assert result.data['message'] == 'Test commit'
        assert result.data['initialized'] is False

    def test_commit_specific_files(self, service, git_dir):
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# change\n')
        with open(os.path.join(git_dir, 'other.cfg'), 'w') as f:
            f.write('other\n')

        result = service.commit(
            message='Partial commit',
            files=['hosts.cfg'],
            user_name='Test User',
            user_email='test@test.com'
        )
        assert result.success is True

        # other.cfg should still be uncommitted
        status = service.get_status()
        paths = [f.path for f in status.data.files]
        assert 'other.cfg' in paths

    def test_commit_auto_init(self, empty_dir):
        svc = GitService(empty_dir)
        result = svc.commit(
            message='First commit',
            user_name='Test User',
            user_email='test@test.com',
            auto_init=True
        )
        assert result.success is True
        assert result.data['initialized'] is True
        assert os.path.isdir(os.path.join(empty_dir, '.git'))

    def test_commit_no_repo_no_auto_init(self, service_no_repo):
        result = service_no_repo.commit(
            message='Should fail',
            user_name='Test',
            user_email='test@test.com'
        )
        assert result.success is False
        assert 'Not a git repository' in result.error

    def test_nothing_to_commit(self, service):
        result = service.commit(
            message='Empty commit',
            user_name='Test User',
            user_email='test@test.com'
        )
        assert result.success is False
        assert 'nothing to commit' in result.error.lower()


class TestDiscard:
    def test_discard_modified_file(self, service, git_dir):
        with open(os.path.join(git_dir, 'hosts.cfg'), 'w') as f:
            f.write('modified content\n')

        result = service.discard('hosts.cfg')
        assert result.success is True
        assert result.data['action'] == 'restored'

        # File should be back to original
        with open(os.path.join(git_dir, 'hosts.cfg')) as f:
            content = f.read()
        assert 'test-host' in content

    def test_discard_untracked_file(self, service, git_dir):
        new_file = os.path.join(git_dir, 'new.cfg')
        with open(new_file, 'w') as f:
            f.write('new\n')

        result = service.discard('new.cfg')
        assert result.success is True
        assert result.data['action'] == 'deleted'
        assert not os.path.exists(new_file)


class TestDiscardAll:
    def test_discard_all_changes(self, service, git_dir):
        # Modify existing file
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# change\n')
        # Create new file
        with open(os.path.join(git_dir, 'new.cfg'), 'w') as f:
            f.write('new\n')

        result = service.discard_all()
        assert result.success is True
        assert len(result.data['commands']) == 3

        # All commands should succeed
        for cmd in result.data['commands']:
            assert cmd['success'] is True

        # Working dir should be clean
        status = service.get_status()
        assert status.data.has_changes is False

    def test_discard_all_clean_repo(self, service):
        """Discard all on clean repo should still succeed."""
        result = service.discard_all()
        assert result.success is True


class TestRestore:
    def test_restore_to_previous_commit(self, service, git_dir):
        # Get initial commit hash
        log = service.get_log()
        initial_hash = log.data['commits'][0].hash

        # Make a second commit
        with open(os.path.join(git_dir, 'hosts.cfg'), 'w') as f:
            f.write('modified\n')
        service.commit(message='Second', user_name='Test', user_email='t@t.com')

        # Restore to initial
        result = service.restore(initial_hash)
        assert result.success is True
        assert result.data['commit'] == initial_hash

        # File should be restored
        with open(os.path.join(git_dir, 'hosts.cfg')) as f:
            content = f.read()
        assert 'test-host' in content

    def test_restore_invalid_commit(self, service):
        result = service.restore('deadbeef1234567890abcdef1234567890abcdef')
        assert result.success is False
        assert 'not found' in result.error.lower()

    def test_restore_with_uncommitted_changes(self, service, git_dir):
        log = service.get_log()
        initial_hash = log.data['commits'][0].hash

        # Make a commit, then modify
        with open(os.path.join(git_dir, 'hosts.cfg'), 'w') as f:
            f.write('committed change\n')
        service.commit(message='Second', user_name='Test', user_email='t@t.com')
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('uncommitted\n')

        result = service.restore(initial_hash)
        assert result.success is True
        assert result.data['had_uncommitted_changes'] is True

    def test_restore_deletes_new_files(self, service, git_dir):
        log = service.get_log()
        initial_hash = log.data['commits'][0].hash

        # Add a new file and commit
        with open(os.path.join(git_dir, 'new.cfg'), 'w') as f:
            f.write('new file\n')
        service.commit(message='Add file', user_name='Test', user_email='t@t.com')
        assert os.path.exists(os.path.join(git_dir, 'new.cfg'))

        # Restore to initial (before new.cfg existed)
        result = service.restore(initial_hash)
        assert result.success is True
        assert 'new.cfg' in result.data['deleted_files']
        assert not os.path.exists(os.path.join(git_dir, 'new.cfg'))

    def test_restore_shows_in_workspace_diff(self, service, git_dir):
        """After restore, get_workspace_diff must show the staged changes."""
        log = service.get_log()
        initial_hash = log.data['commits'][0].hash

        # Make a change and commit
        with open(os.path.join(git_dir, 'hosts.cfg'), 'w') as f:
            f.write('modified content\n')
        service.commit(message='Modify', user_name='Test', user_email='t@t.com')

        # Restore to initial
        result = service.restore(initial_hash)
        assert result.success is True

        # get_workspace_diff should show the staged changes (restore uses git checkout
        # which stages files in the index)
        diff_result = service.get_workspace_diff()
        assert diff_result.success is True
        assert len(diff_result.data['diffs']) > 0
        assert any(d['file_path'] == 'hosts.cfg' for d in diff_result.data['diffs'])


class TestClearHistory:
    def test_clear_history(self, service, git_dir):
        # Make multiple commits
        for i in range(3):
            with open(os.path.join(git_dir, f'f{i}.cfg'), 'w') as f:
                f.write(f'{i}\n')
            service.commit(message=f'Commit {i}', user_name='Test', user_email='t@t.com')

        result = service.clear_history(user_name='Test', user_email='t@t.com')
        assert result.success is True

        # Should only have 1 commit now
        log = service.get_log()
        assert len(log.data['commits']) == 1
        assert log.data['commits'][0].message == 'Initial commit'

    def test_clear_history_preserves_files(self, service, git_dir):
        with open(os.path.join(git_dir, 'extra.cfg'), 'w') as f:
            f.write('extra\n')
        service.commit(message='Add extra', user_name='Test', user_email='t@t.com')

        service.clear_history(user_name='Test', user_email='t@t.com')

        # Files should still exist
        assert os.path.exists(os.path.join(git_dir, 'hosts.cfg'))
        assert os.path.exists(os.path.join(git_dir, 'extra.cfg'))


class TestThreadSafety:
    """Test that mutation methods are properly serialized."""

    def test_concurrent_commits_dont_conflict(self, git_dir):
        """Multiple threads trying to commit shouldn't cause lock errors."""
        svc = GitService(git_dir)
        errors = []
        results = []

        def make_change_and_commit(i):
            try:
                filepath = os.path.join(git_dir, f'thread_{i}.cfg')
                with open(filepath, 'w') as f:
                    f.write(f'thread {i}\n')
                result = svc.commit(
                    message=f'Thread {i} commit',
                    user_name='Test',
                    user_email='t@t.com'
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=make_change_and_commit, args=(i,))
                   for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        # At least some should succeed (they're serialized via lock)
        successes = [r for r in results if r.success]
        assert len(successes) >= 1

    def test_concurrent_discard_all(self, git_dir):
        """Multiple discard_all calls shouldn't conflict."""
        svc = GitService(git_dir)

        # Create changes
        with open(os.path.join(git_dir, 'hosts.cfg'), 'a') as f:
            f.write('# change\n')

        errors = []

        def do_discard():
            try:
                svc.discard_all()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_discard) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []


class TestConfigPath:
    def test_config_path_property(self, git_dir):
        svc = GitService(git_dir)
        assert svc.config_path == git_dir

    def test_config_path_setter(self, git_dir, empty_dir):
        svc = GitService(git_dir)
        svc.config_path = empty_dir
        assert svc.config_path == empty_dir

        # is_repo should now return False
        result = svc.is_repo()
        assert result.data is False
