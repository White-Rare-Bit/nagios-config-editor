"""
Git Service - Centralized git operations for the Nagios Bulk Editor.

Provides a clean interface for all git interactions with:
- Standardized subprocess wrapper with timeout and retry logic
- Thread safety for multi-step mutations
- Structured result types via OperationResult
"""

import os
import time
import shutil
import random
import logging
import multiprocessing
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from nagios_model import OperationResult

logger = logging.getLogger('nagios_bulk_editor.git')

# Timeout presets (seconds)
TIMEOUT_QUERY = 5     # rev-parse, config lookups
TIMEOUT_STATUS = 10   # status, reset, branch
TIMEOUT_MUTATE = 30   # commit, checkout, clean, add, diff

# Transient error patterns that warrant retry
_TRANSIENT_PATTERNS = ('index.lock', 'unable to create', 'cannot lock ref')


@dataclass
class GitRunResult:
    """Raw subprocess output from a git command."""
    stdout: str
    stderr: str
    returncode: int


@dataclass
class GitCommit:
    """Parsed git log entry."""
    hash: str
    hash_short: str
    author: str
    date: str
    message: str
    matches_working_dir: bool = False


@dataclass
class GitFileStatus:
    """Parsed git porcelain status entry."""
    path: str
    status: str
    status_code: str
    staged: bool
    unstaged: bool


@dataclass
class GitStatusResult:
    """Full git status response."""
    is_repo: bool
    branch: Optional[str] = None
    files: List[GitFileStatus] = field(default_factory=list)
    has_changes: bool = False
    error: Optional[str] = None


class GitService:
    """Centralized git operations service.

    All public methods return OperationResult. Multi-step mutations
    are serialized via an internal multiprocessing.Lock.
    """

    def __init__(self, config_path: str, op_logger=None):
        self._config_path = config_path
        self._op_logger = op_logger
        self._lock = multiprocessing.Lock()

    @property
    def config_path(self) -> str:
        return self._config_path

    @config_path.setter
    def config_path(self, path: str):
        self._config_path = path

    def _run_git(self, args: List[str], timeout: int = TIMEOUT_STATUS,
                 retry: bool = False, cwd: Optional[str] = None) -> OperationResult:
        """Run a git command with optional retry on transient errors.

        Args:
            args: Git command arguments (without 'git' prefix).
            timeout: Timeout in seconds.
            retry: Whether to retry on transient lock errors.
            cwd: Working directory (defaults to config_path).

        Returns:
            OperationResult with data=GitRunResult.
            - success=True only when returncode == 0
            - success=False when returncode != 0 (error contains stderr/stdout)
            - data always contains GitRunResult for callers that need raw output

        Note:
            Some git commands return non-zero for valid states (e.g., git diff
            returns 1 when differences exist). Callers must handle these cases
            by checking result.data.returncode when result.success is False.
        """
        cmd = ['git'] + args
        work_dir = cwd or self._config_path
        max_attempts = 3 if retry else 1

        for attempt in range(max_attempts):
            try:
                result = subprocess.run(
                    cmd,
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                run_result = GitRunResult(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    returncode=result.returncode
                )

                # Check for transient errors on non-zero return
                if result.returncode != 0 and retry and attempt < max_attempts - 1:
                    combined = result.stderr + result.stdout
                    if any(pat in combined for pat in _TRANSIENT_PATTERNS):
                        delay = (0.1 * (2 ** attempt)) + random.uniform(0, 0.05)
                        if self._op_logger:
                            self._op_logger.warning('git', 'retry',
                                                    params={'cmd': ' '.join(args), 'attempt': attempt + 1})
                        time.sleep(delay)
                        continue

                if self._op_logger:
                    if result.returncode != 0:
                        self._op_logger.warning('git', 'run',
                                                params={'cmd': ' '.join(args)},
                                                error=result.stderr.strip()[:200])

                # Return success=False when returncode != 0
                if result.returncode != 0:
                    error_msg = result.stderr.strip() or result.stdout.strip() or f'Git command failed with returncode {result.returncode}'
                    return OperationResult(success=False, error=error_msg, data=run_result)

                return OperationResult(success=True, data=run_result)

            except subprocess.TimeoutExpired:
                error_msg = f'Git command timed out after {timeout}s: git {" ".join(args)}'
                if self._op_logger:
                    self._op_logger.error('git', 'timeout', params={'cmd': ' '.join(args)})
                return OperationResult(success=False, error=error_msg)
            except FileNotFoundError:
                error_msg = 'Git is not installed or not in PATH'
                if self._op_logger:
                    self._op_logger.error('git', 'not_found')
                return OperationResult(success=False, error=error_msg)
            except Exception as e:
                error_msg = f'Git command failed: {str(e)}'
                if self._op_logger:
                    self._op_logger.error('git', 'exception',
                                          params={'cmd': ' '.join(args)}, error=str(e))
                return OperationResult(success=False, error=error_msg)

    # =========================================================================
    # Query methods (no lock needed)
    # =========================================================================

    def is_repo(self) -> OperationResult:
        """Check if config_path is inside a git working tree.

        Returns OperationResult with data=bool.
        """
        result = self._run_git(['rev-parse', '--is-inside-work-tree'], timeout=TIMEOUT_QUERY)
        if not result.success:
            return OperationResult(success=True, data=False)
        return OperationResult(success=True, data=(result.data.returncode == 0))

    def get_user_identity(self) -> OperationResult:
        """Get configured git user name and email.

        Checks local config first, then global.
        Returns OperationResult with data={'name': ..., 'email': ...} or data=None.
        """
        def get_config(key):
            git_dir = os.path.join(self._config_path, '.git')
            # Try local first
            if os.path.isdir(git_dir):
                r = self._run_git(['config', '--local', key], timeout=TIMEOUT_QUERY)
                if r.success and r.data.returncode == 0 and r.data.stdout.strip():
                    return r.data.stdout.strip()
            # Try global
            r = self._run_git(['config', '--global', key], timeout=TIMEOUT_QUERY)
            if r.success and r.data.returncode == 0 and r.data.stdout.strip():
                return r.data.stdout.strip()
            return None

        name = get_config('user.name')
        email = get_config('user.email')

        if name or email:
            return OperationResult(success=True, data={'name': name, 'email': email})
        return OperationResult(success=True, data=None)

    def get_status(self, excluded_paths: Optional[List[str]] = None) -> OperationResult:
        """Get git status of config directory.

        Returns OperationResult with data=GitStatusResult.
        """
        if excluded_paths is None:
            excluded_paths = ['.backups/', '.backups', '.staging/', '.staging',
                              '.git/', 'backups/', 'backups']

        # Check if inside work tree
        repo_check = self._run_git(['rev-parse', '--is-inside-work-tree'], timeout=TIMEOUT_QUERY)
        if not repo_check.success:
            return OperationResult(success=True, data=GitStatusResult(
                is_repo=False, error=repo_check.error))
        if repo_check.data.returncode != 0:
            return OperationResult(success=True, data=GitStatusResult(
                is_repo=False, error='Not a git repository'))

        # Get current branch
        branch_result = self._run_git(['branch', '--show-current'], timeout=TIMEOUT_QUERY)
        branch = 'HEAD detached'
        if branch_result.success and branch_result.data.returncode == 0:
            branch = branch_result.data.stdout.strip() or 'HEAD detached'

        # D-07: Use -unormal instead of -uall to avoid memory issues on large repos
        # -uall recursively lists every file in untracked directories which can be slow/memory-intensive
        status_result = self._run_git(['status', '--porcelain', '-unormal'], timeout=TIMEOUT_STATUS)
        if not status_result.success:
            return OperationResult(success=False, error=status_result.error)

        files = []
        for line in status_result.data.stdout.split('\n'):
            line = line.rstrip('\r\n')
            if not line or len(line) < 4:
                continue

            staged_status = line[0]
            unstaged_status = line[1]
            filepath = line[3:].strip()

            # Handle renamed files
            if ' -> ' in filepath:
                filepath = filepath.split(' -> ')[1]

            # Strip quotes
            if filepath.startswith('"') and filepath.endswith('"'):
                filepath = filepath[1:-1]

            # Skip excluded paths
            if any(filepath.startswith(exc) or filepath == exc.rstrip('/')
                   for exc in excluded_paths):
                continue

            # Determine overall status
            if staged_status == '?' or unstaged_status == '?':
                status = 'untracked'
                status_code = '?'
            elif staged_status == 'A' or unstaged_status == 'A':
                status = 'added'
                status_code = 'A'
            elif staged_status == 'D' or unstaged_status == 'D':
                status = 'deleted'
                status_code = 'D'
            elif staged_status == 'R':
                status = 'renamed'
                status_code = 'R'
            elif staged_status == 'M' or unstaged_status == 'M':
                status = 'modified'
                status_code = 'M'
            else:
                status = 'changed'
                status_code = staged_status if staged_status != ' ' else unstaged_status

            files.append(GitFileStatus(
                path=filepath,
                status=status,
                status_code=status_code,
                staged=staged_status != ' ' and staged_status != '?',
                unstaged=unstaged_status != ' ' and unstaged_status != '?'
            ))

        return OperationResult(success=True, data=GitStatusResult(
            is_repo=True,
            branch=branch,
            files=files,
            has_changes=len(files) > 0
        ))

    def get_diff(self, filepath: Optional[str] = None, staged: bool = False,
                 full_file: bool = True, context_lines: Optional[int] = None) -> OperationResult:
        """Get git diff for a file or all changes.

        Args:
            filepath: Specific file path, or None for all.
            staged: If True, show staged changes only.
            full_file: If True, show full file context.
            context_lines: Number of context lines (overrides full_file if set).

        Returns OperationResult with data=str (diff output).
        """
        cmd = ['diff', 'HEAD']
        if staged:
            cmd = ['diff', '--staged']
        if context_lines is not None:
            cmd.insert(1, f'-U{context_lines}')
        elif full_file:
            cmd.insert(1, '-U9999')
        if filepath:
            cmd.append('--')
            cmd.append(filepath)

        # Note: git diff returns 0 for no changes, 1 for changes - both are valid
        result = self._run_git(cmd, timeout=TIMEOUT_MUTATE)
        if result.data is None:
            # Subprocess failed completely (timeout, not found, etc.)
            return result
        if result.data.returncode not in (0, 1):
            return OperationResult(success=False, error=result.error or f'Git diff failed with returncode {result.data.returncode}')

        diff_output = result.data.stdout

        # If file is untracked, show contents as a diff
        if filepath and not diff_output:
            status_result = self._run_git(
                ['status', '--porcelain', '--', filepath], timeout=TIMEOUT_QUERY)
            if (status_result.success and
                    status_result.data.stdout.startswith('??')):
                full_path = os.path.join(self._config_path, filepath)
                if os.path.exists(full_path):
                    try:
                        with open(full_path, 'r') as f:
                            content = f.read()
                        lines = content.split('\n')
                        diff_output = f"diff --git a/{filepath} b/{filepath}\n"
                        diff_output += "new file mode 100644\n"
                        diff_output += f"--- /dev/null\n"
                        diff_output += f"+++ b/{filepath}\n"
                        diff_output += f"@@ -0,0 +1,{len(lines)} @@\n"
                        diff_output += '\n'.join('+' + line for line in lines)
                    except Exception:
                        pass

        return OperationResult(success=True, data=diff_output)

    def get_workspace_diff(self, excluded_paths: Optional[List[str]] = None) -> OperationResult:
        """Get workspace diff with parsed file-based structure.

        Used by the staging/diff endpoint. Returns structured diff data.

        Args:
            excluded_paths: Paths to exclude from diff output.

        Returns OperationResult with data=dict containing 'diffs' and 'git_changes'.
        """
        if excluded_paths is None:
            excluded_paths = ['.backups/', '.staging/', '.git/']

        # Get diff of tracked files using patience algorithm
        # Use HEAD to show both staged and unstaged changes (important after git restore)
        # Note: git diff returns 0 for no changes, 1 for changes - both are valid
        result = self._run_git(['diff', 'HEAD', '--patience', '-U3'], timeout=TIMEOUT_MUTATE)
        if result.data is None:
            # Subprocess failed completely (timeout, not found, etc.)
            return result
        if result.data.returncode not in (0, 1):
            # Fall back to plain diff (e.g., no commits yet means no HEAD)
            result = self._run_git(['diff', '--patience', '-U3'], timeout=TIMEOUT_MUTATE)
            if result.data is None:
                return result
            if result.data.returncode not in (0, 1):
                return OperationResult(success=False,
                                       error=f'Git diff failed: {result.data.stderr}')

        diff_output = result.data.stdout
        diffs = []
        git_changes = []
        diff_file_paths = set()

        # Parse unified diff into file-based structure
        current_file = None
        current_lines = []
        current_rel_path = None

        for line in diff_output.split('\n'):
            if line.startswith('diff --git'):
                # Save previous file
                if current_file and current_lines and current_rel_path:
                    if not any(current_rel_path.startswith(exc) for exc in excluded_paths):
                        self._append_diff_entry(diffs, git_changes, diff_file_paths,
                                                current_rel_path, current_lines)

                # Start new file
                parts = line.split(' b/')
                if len(parts) > 1:
                    current_rel_path = parts[-1]
                    current_file = os.path.join(self._config_path, current_rel_path)
                else:
                    current_file = None
                    current_rel_path = None
                current_lines = [line]
            elif current_file:
                current_lines.append(line)

        # Don't forget last file
        if current_file and current_lines and current_rel_path:
            if not any(current_rel_path.startswith(exc) for exc in excluded_paths):
                self._append_diff_entry(diffs, git_changes, diff_file_paths,
                                        current_rel_path, current_lines)

        # Also check for untracked files
        status_result = self._run_git(['status', '--porcelain'], timeout=TIMEOUT_STATUS)
        if status_result.success and status_result.data.returncode == 0:
            for line in status_result.data.stdout.split('\n'):
                if not line:
                    continue
                status_code = line[:2]
                file_path = line[3:]

                if any(file_path.startswith(exc) for exc in excluded_paths):
                    continue
                if file_path in diff_file_paths:
                    continue

                if status_code == '??':
                    if not file_path.endswith('.cfg'):
                        continue
                    full_path = os.path.join(self._config_path, file_path)
                    try:
                        with open(full_path, 'r') as f:
                            content = f.read()
                        content_lines = content.split('\n')
                        diff_lines = [
                            f'diff --git a/{file_path} b/{file_path}',
                            'new file mode 100644',
                            f'--- /dev/null',
                            f'+++ b/{file_path}',
                            f'@@ -0,0 +1,{len(content_lines)} @@'
                        ]
                        diff_lines.extend(['+' + l for l in content_lines])
                        diffs.append({
                            'file_path': file_path,
                            'diff': '\n'.join(diff_lines),
                            'diff_lines': diff_lines,
                            'status': 'added',
                            'change_count': len(content_lines)
                        })
                        git_changes.append({'path': file_path, 'status': 'added'})
                    except Exception:
                        pass

                elif status_code[0] == 'D' and file_path not in diff_file_paths:
                    diffs.append({
                        'file_path': file_path,
                        'diff': f'diff --git a/{file_path} b/{file_path}\ndeleted file',
                        'diff_lines': [f'diff --git a/{file_path} b/{file_path}', 'deleted file'],
                        'status': 'deleted',
                        'change_count': 0
                    })
                    git_changes.append({'path': file_path, 'status': 'deleted'})

        return OperationResult(success=True, data={
            'diffs': diffs,
            'git_changes': git_changes
        })

    def _append_diff_entry(self, diffs, git_changes, diff_file_paths,
                           rel_path, lines):
        """Helper to append a parsed diff entry."""
        additions = sum(1 for l in lines if l.startswith('+') and not l.startswith('+++'))
        deletions = sum(1 for l in lines if l.startswith('-') and not l.startswith('---'))

        status = 'modified'
        if any('new file mode' in l for l in lines):
            status = 'added'
        elif any('deleted file mode' in l for l in lines):
            status = 'deleted'

        diffs.append({
            'file_path': rel_path,
            'diff': '\n'.join(lines),
            'diff_lines': lines,
            'status': status,
            'change_count': additions + deletions
        })
        git_changes.append({'path': rel_path, 'status': status})
        diff_file_paths.add(rel_path)

    def get_log(self, limit: int = 50) -> OperationResult:
        """Get git commit history.

        Uses null-byte separator to avoid parsing issues with pipe characters
        in commit messages.

        Args:
            limit: Maximum number of commits to return (capped at 200).

        Returns OperationResult with data=dict containing 'is_repo', 'commits',
        'matching_commit'.
        """
        limit = min(limit, 200)

        git_dir = os.path.join(self._config_path, '.git')
        if not os.path.isdir(git_dir):
            return OperationResult(success=True, data={
                'is_repo': False,
                'error': 'Not a git repository',
                'commits': []
            })

        # Use %x00 (null byte) as separator - cannot appear in commit messages
        result = self._run_git(
            ['log', f'-{limit}', '--format=%H%x00%an%x00%ai%x00%s'],
            timeout=TIMEOUT_MUTATE
        )

        if result.data is None:
            return result
        # Handle non-zero returncodes - check for "no commits" case first
        if result.data.returncode != 0:
            if 'does not have any commits' in result.data.stderr:
                return OperationResult(success=True, data={
                    'is_repo': True,
                    'commits': [],
                    'message': 'No commits yet'
                })
            return OperationResult(success=False,
                                   error=f'Failed to get log: {result.data.stderr}')

        commits = []
        for line in result.data.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\x00', 3)
            if len(parts) >= 4:
                commits.append(GitCommit(
                    hash=parts[0],
                    hash_short=parts[0][:7],
                    author=parts[1],
                    date=parts[2],
                    message=parts[3]
                ))

        # Check which commit matches current working directory
        matching_commit = None
        head_check = self._run_git(['diff', '--quiet', 'HEAD', '--'], timeout=TIMEOUT_STATUS)
        if head_check.success and head_check.data.returncode == 0:
            # No changes from HEAD
            if commits:
                commits[0].matches_working_dir = True
                matching_commit = commits[0].hash
        else:
            # Check if working dir matches any recent commit (limit to first 20)
            for commit in commits[:20]:
                diff_check = self._run_git(
                    ['diff', '--quiet', commit.hash, '--'], timeout=TIMEOUT_QUERY)
                if diff_check.success and diff_check.data.returncode == 0:
                    commit.matches_working_dir = True
                    matching_commit = commit.hash
                    break

        return OperationResult(success=True, data={
            'is_repo': True,
            'commits': commits,
            'matching_commit': matching_commit
        })

    def has_uncommitted_changes(self) -> OperationResult:
        """Check if there are uncommitted changes.

        Returns OperationResult with data=bool.
        """
        result = self._run_git(['status', '--porcelain'], timeout=TIMEOUT_STATUS)
        if not result.success:
            return result
        return OperationResult(success=True, data=bool(result.data.stdout.strip()))

    # =========================================================================
    # Mutation methods (hold lock for thread safety)
    # =========================================================================

    def init_repo(self) -> OperationResult:
        """Initialize a git repository in config_path.

        Creates .gitignore if it doesn't exist.
        Returns OperationResult with data=GitRunResult.
        """
        with self._lock:
            result = self._run_git(['init'], timeout=TIMEOUT_MUTATE)
            if not result.success:
                return result
            if result.data.returncode != 0:
                return OperationResult(success=False,
                                       error=f'Failed to initialize git: {result.data.stderr}')

            # Create .gitignore
            gitignore_path = os.path.join(self._config_path, '.gitignore')
            if not os.path.exists(gitignore_path):
                with open(gitignore_path, 'w') as f:
                    f.write('# Nagios Bulk Editor - auto-generated .gitignore\n')
                    f.write('backups/\n')
                    f.write('.nagios_staging/\n')
                    f.write('*.bak\n')
                    f.write('*.tmp\n')

            return OperationResult(success=True, data=result.data)

    def commit(self, message: str, files: Optional[List[str]] = None,
               user_name: Optional[str] = None, user_email: Optional[str] = None,
               auto_init: bool = False) -> OperationResult:
        """Stage and commit changes.

        Args:
            message: Commit message.
            files: Specific files to stage, or None/empty for all.
            user_name: Git author name.
            user_email: Git author email.
            auto_init: Initialize repo if not already one.

        Returns OperationResult with data=dict containing commit info.
        """
        # Validate user identity at service boundary
        if not user_name or not user_email:
            return OperationResult(
                success=False,
                error='User identity (name and email) required for git operations'
            )

        with self._lock:
            git_dir = os.path.join(self._config_path, '.git')
            repo_exists = os.path.isdir(git_dir)
            initialized = False

            if not repo_exists:
                if auto_init:
                    init_result = self.init_repo.__wrapped__(self) if hasattr(self.init_repo, '__wrapped__') else self._init_repo_unlocked()
                    if not init_result.success:
                        return init_result
                    initialized = True
                else:
                    return OperationResult(success=False, error='Not a git repository')

            # Stage files
            if files:
                stage_cmd = ['add', '--'] + files
            else:
                stage_cmd = ['add', '-A']

            stage_result = self._run_git(stage_cmd, timeout=TIMEOUT_MUTATE, retry=True)
            if not stage_result.success:
                return stage_result
            if stage_result.data.returncode != 0:
                return OperationResult(success=False,
                                       error=f'Failed to stage files: {stage_result.data.stderr}')

            # Commit with user identity
            commit_cmd = ['-c', f'user.name={user_name}', '-c', f'user.email={user_email}',
                          'commit', '-m', message]
            commit_result = self._run_git(commit_cmd, timeout=TIMEOUT_MUTATE, retry=True)
            if not commit_result.success:
                return commit_result
            if commit_result.data.returncode != 0:
                combined = commit_result.data.stdout + commit_result.data.stderr
                if 'nothing to commit' in combined:
                    return OperationResult(success=False, error='Nothing to commit')
                return OperationResult(success=False,
                                       error=f'Commit failed: {commit_result.data.stderr or commit_result.data.stdout}')

            # Get commit hash
            hash_result = self._run_git(['rev-parse', '--short', 'HEAD'], timeout=TIMEOUT_QUERY)
            commit_hash = ''
            if hash_result.success and hash_result.data.returncode == 0:
                commit_hash = hash_result.data.stdout.strip()
            else:
                # Commit succeeded but couldn't retrieve hash - log warning but don't fail
                logger.warning(
                    "Commit succeeded but failed to retrieve commit hash via rev-parse. "
                    "commit_hash will be empty in response."
                )

            return OperationResult(success=True, data={
                'commit_hash': commit_hash,
                'message': message,
                'output': commit_result.data.stdout,
                'initialized': initialized
            })

    def _init_repo_unlocked(self) -> OperationResult:
        """Initialize repo without acquiring the lock (caller must hold lock)."""
        result = self._run_git(['init'], timeout=TIMEOUT_MUTATE)
        if not result.success:
            return result
        if result.data.returncode != 0:
            return OperationResult(success=False,
                                   error=f'Failed to initialize git: {result.data.stderr}')

        gitignore_path = os.path.join(self._config_path, '.gitignore')
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w') as f:
                f.write('# Nagios Bulk Editor - auto-generated .gitignore\n')
                f.write('backups/\n')
                f.write('.nagios_staging/\n')
                f.write('*.bak\n')
                f.write('*.tmp\n')

        return OperationResult(success=True, data=result.data)

    def discard(self, filepath: str) -> OperationResult:
        """Discard changes to a specific file.

        For untracked files, deletes them. For tracked files, checks out
        the committed version.

        Returns OperationResult with data=dict containing 'action'.
        """
        with self._lock:
            # Check if file is untracked
            status_result = self._run_git(
                ['status', '--porcelain', '--', filepath], timeout=TIMEOUT_QUERY)
            if not status_result.success:
                return status_result

            if status_result.data.stdout.startswith('??'):
                # Untracked file - delete it
                full_path = os.path.join(self._config_path, filepath)
                if os.path.exists(full_path):
                    os.remove(full_path)
                return OperationResult(success=True, data={'action': 'deleted'})

            # Tracked file - checkout to discard
            result = self._run_git(['checkout', '--', filepath], timeout=TIMEOUT_STATUS)
            if not result.success:
                return result
            if result.data.returncode != 0:
                return OperationResult(success=False,
                                       error=f'Failed to discard changes: {result.data.stderr}')

            return OperationResult(success=True, data={'action': 'restored'})

    def discard_all(self) -> OperationResult:
        """Discard all uncommitted changes (reset, checkout, clean).

        Returns OperationResult with data=dict containing 'commands'.
        """
        with self._lock:
            commands_run = []

            # Reset staged changes
            reset_result = self._run_git(['reset', 'HEAD'], timeout=TIMEOUT_STATUS, retry=True)
            commands_run.append({
                'command': 'git reset HEAD',
                'success': reset_result.success and reset_result.data.returncode == 0,
                'output': (reset_result.data.stdout or reset_result.data.stderr) if reset_result.success else reset_result.error
            })

            # Checkout tracked files
            checkout_result = self._run_git(['checkout', '--', '.'], timeout=TIMEOUT_MUTATE, retry=True)
            commands_run.append({
                'command': 'git checkout -- .',
                'success': checkout_result.success and checkout_result.data.returncode == 0,
                'output': (checkout_result.data.stdout or checkout_result.data.stderr) if checkout_result.success else checkout_result.error
            })
            if not checkout_result.success or checkout_result.data.returncode != 0:
                error = checkout_result.error if not checkout_result.success else checkout_result.data.stderr
                return OperationResult(success=False,
                                       error=f'Failed to discard changes: {error}',
                                       data={'commands': commands_run})

            # Clean untracked files
            clean_result = self._run_git(['clean', '-fd'], timeout=TIMEOUT_MUTATE, retry=True)
            commands_run.append({
                'command': 'git clean -fd',
                'success': clean_result.success and clean_result.data.returncode == 0,
                'output': (clean_result.data.stdout or clean_result.data.stderr) if clean_result.success else clean_result.error
            })
            if not clean_result.success or clean_result.data.returncode != 0:
                error = clean_result.error if not clean_result.success else clean_result.data.stderr
                return OperationResult(success=False,
                                       error=f'Failed to clean untracked files: {error}',
                                       data={'commands': commands_run})

            return OperationResult(success=True, data={'commands': commands_run})

    def _try_restore_stash(self, stashed: bool) -> Optional[str]:
        """Attempt to restore stashed changes.

        Args:
            stashed: Whether changes were stashed

        Returns:
            Error message if stash pop failed, None if successful or no stash
        """
        if not stashed:
            return None

        pop_result = self._run_git(['stash', 'pop'], timeout=TIMEOUT_STATUS)
        if not pop_result.success or pop_result.data.returncode != 0:
            pop_err = pop_result.error if not pop_result.success else pop_result.data.stderr
            logger.warning(f"Failed to restore stash: {pop_err}")
            return pop_err
        return None

    def _build_restore_error_with_stash_info(
        self,
        base_error: str,
        stashed: bool,
        stash_pop_error: Optional[str]
    ) -> str:
        """Build error message with stash recovery info.

        Args:
            base_error: The base error message
            stashed: Whether changes were stashed
            stash_pop_error: Error from stash pop attempt, if any

        Returns:
            Error message with stash recovery instructions if applicable
        """
        if not stashed:
            return base_error
        if stash_pop_error:
            return (
                f"{base_error} Your uncommitted changes were stashed but could not be "
                f"automatically restored (error: {stash_pop_error}). "
                "Run 'git stash pop' manually to recover your work."
            )
        return f"{base_error} Your uncommitted changes have been restored from stash."

    def _verify_commit(self, commit_hash: str) -> OperationResult:
        """Verify that a commit exists and get its message.

        Args:
            commit_hash: The commit hash to verify

        Returns:
            OperationResult with data={'exists': bool, 'message': str}
        """
        verify_result = self._run_git(
            ['cat-file', '-t', commit_hash], timeout=TIMEOUT_QUERY)

        if verify_result.data is None:
            return OperationResult(success=False, error=verify_result.error)

        if verify_result.data.returncode != 0 or verify_result.data.stdout.strip() != 'commit':
            return OperationResult(success=False, error='Commit not found')

        # Get commit message
        msg_result = self._run_git(
            ['log', '-1', '--format=%s', commit_hash], timeout=TIMEOUT_QUERY)
        commit_message = ''
        if msg_result.success and msg_result.data and msg_result.data.returncode == 0:
            commit_message = msg_result.data.stdout.strip()

        return OperationResult(success=True, data={
            'exists': True,
            'message': commit_message
        })

    def _stash_changes_if_needed(self, has_changes: bool) -> bool:
        """Stash uncommitted changes if present.

        Args:
            has_changes: Whether there are uncommitted changes

        Returns:
            True if changes were successfully stashed, False otherwise
        """
        if not has_changes:
            return False

        stash_result = self._run_git(
            ['stash', 'push', '-m', 'Auto-stash before restore'],
            timeout=TIMEOUT_MUTATE)
        return stash_result.success and stash_result.data and stash_result.data.returncode == 0

    def _get_file_set_for_commit(self, commit_ref: str) -> OperationResult:
        """Get the set of files in a commit.

        Args:
            commit_ref: The commit reference (e.g., 'HEAD' or a hash)

        Returns:
            OperationResult with data=set of file paths
        """
        result = self._run_git(
            ['ls-tree', '-r', '--name-only', commit_ref], timeout=TIMEOUT_MUTATE)

        if result.data is None:
            return OperationResult(success=False, error=result.error)

        if result.data.returncode != 0:
            return OperationResult(
                success=False,
                error=result.error or result.data.stderr
            )

        files = set(f.strip() for f in result.data.stdout.strip().split('\n') if f.strip())
        return OperationResult(success=True, data=files)

    def _cleanup_extra_files(self, files_to_delete: List[str]) -> List[str]:
        """Delete files that don't exist in target commit and clean up empty directories.

        Args:
            files_to_delete: List of relative file paths to delete

        Returns:
            List of files that were successfully deleted
        """
        deleted_files = []
        directories_to_check = set()

        for file_path in files_to_delete:
            full_path = os.path.join(self._config_path, file_path)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                    deleted_files.append(file_path)
                    parent_dir = os.path.dirname(full_path)
                    while (parent_dir and parent_dir != self._config_path
                           and parent_dir.startswith(self._config_path)):
                        directories_to_check.add(parent_dir)
                        parent_dir = os.path.dirname(parent_dir)
                except OSError:
                    pass

        # Clean up empty directories (deepest first)
        for dir_path in sorted(directories_to_check, key=lambda x: x.count('/'), reverse=True):
            try:
                if os.path.isdir(dir_path) and not os.listdir(dir_path):
                    os.rmdir(dir_path)
            except OSError:
                pass

        return deleted_files

    def restore(self, commit_hash: str) -> OperationResult:
        """Restore working directory to a specific commit.

        Stashes uncommitted changes if present, checks out the target commit's
        files, and deletes files that don't exist in the target commit.

        If restore fails after stashing, attempts to restore the stash automatically.
        Error messages include stash status to help users recover manually if needed.

        Returns OperationResult with data=dict containing restore info.
        """
        with self._lock:
            # Check for uncommitted changes
            status_result = self._run_git(['status', '--porcelain'], timeout=TIMEOUT_STATUS)
            if not status_result.success:
                return status_result
            has_changes = bool(status_result.data.stdout.strip()) if status_result.data else False

            # Verify commit exists and get message
            verify_result = self._verify_commit(commit_hash)
            if not verify_result.success:
                return verify_result
            commit_message = verify_result.data.get('message', '')

            # Stash uncommitted changes if present
            stashed = self._stash_changes_if_needed(has_changes)

            # Get files in HEAD
            head_result = self._get_file_set_for_commit('HEAD')
            if not head_result.success:
                stash_err = self._try_restore_stash(stashed)
                return OperationResult(
                    success=False,
                    error=self._build_restore_error_with_stash_info(
                        f'Failed to list HEAD files: {head_result.error}', stashed, stash_err
                    )
                )
            head_files = head_result.data

            # Get files in target commit
            target_result = self._get_file_set_for_commit(commit_hash)
            if not target_result.success:
                stash_err = self._try_restore_stash(stashed)
                return OperationResult(
                    success=False,
                    error=self._build_restore_error_with_stash_info(
                        f'Failed to list target commit files: {target_result.error}', stashed, stash_err
                    )
                )
            target_files = target_result.data

            files_to_delete = list(head_files - target_files)

            # Checkout files from target commit
            restore_result = self._run_git(
                ['checkout', commit_hash, '--', '.'], timeout=TIMEOUT_MUTATE)
            if restore_result.data is None or restore_result.data.returncode != 0:
                stash_err = self._try_restore_stash(stashed)
                error = restore_result.error or (restore_result.data.stderr if restore_result.data else 'Unknown error')
                return OperationResult(
                    success=False,
                    error=self._build_restore_error_with_stash_info(
                        f'Failed to restore: {error}', stashed, stash_err
                    )
                )

            # Delete files that were added after the target commit
            deleted_files = self._cleanup_extra_files(files_to_delete)

            return OperationResult(success=True, data={
                'commit': commit_hash,
                'message': commit_message,
                'had_uncommitted_changes': has_changes,
                'stashed': stashed,
                'deleted_files': deleted_files
            })

    def clear_history(self, user_name: str, user_email: str) -> OperationResult:
        """Clear all git history and reinitialize with a fresh commit.

        Args:
            user_name: Git author name for the fresh commit.
            user_email: Git author email for the fresh commit.

        Returns OperationResult with data=dict on success.
        """
        with self._lock:
            git_dir = os.path.join(self._config_path, '.git')

            # Remove .git directory
            if os.path.isdir(git_dir):
                shutil.rmtree(git_dir)

            # Initialize new repo
            init_result = self._run_git(['init'], timeout=TIMEOUT_STATUS)
            if not init_result.success or init_result.data.returncode != 0:
                error = init_result.error if not init_result.success else init_result.data.stderr
                return OperationResult(success=False,
                                       error=f'Failed to initialize git: {error}')

            # Add all files
            self._run_git(['add', '-A'], timeout=TIMEOUT_MUTATE)

            # Create initial commit
            commit_result = self._run_git(
                ['-c', f'user.name={user_name}', '-c', f'user.email={user_email}',
                 'commit', '-m', 'Initial commit'],
                timeout=TIMEOUT_MUTATE
            )
            if not commit_result.success or commit_result.data.returncode != 0:
                error = commit_result.error if not commit_result.success else commit_result.data.stderr
                return OperationResult(success=False,
                                       error=f'Failed to create initial commit: {error}')

            return OperationResult(success=True, data={
                'message': 'Git history cleared and reinitialized'
            })
