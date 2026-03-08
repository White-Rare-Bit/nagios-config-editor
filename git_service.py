"""Git Service - Centralized git operations for the Nagios Bulk Editor.

Provides a clean interface for all git interactions with:
- Standardized subprocess wrapper with timeout and retry logic
- Thread safety for multi-step mutations
- Structured result types via OperationResult
"""

import logging
import multiprocessing
import os
import random
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from nagios_model import OperationResult

logger = logging.getLogger("nagios_bulk_editor.git")

# Timeout presets (seconds)
TIMEOUT_QUERY = 5     # rev-parse, config lookups
TIMEOUT_STATUS = 10   # status, reset, branch
TIMEOUT_MUTATE = 30   # commit, checkout, clean, add, diff

# Transient error patterns that warrant retry
_TRANSIENT_PATTERNS = ("index.lock", "unable to create", "cannot lock ref")


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
    branch: str | None = None
    files: list[GitFileStatus] = field(default_factory=list)
    has_changes: bool = False
    error: str | None = None


def _parse_log_entries(raw_output: str) -> list[GitCommit]:
    """Parse git log output (null-byte separated) into GitCommit entries.

    Args:
        raw_output: Raw stdout from git log --format=%H%x00%an%x00%ai%x00%s.

    Returns:
        List of GitCommit entries.

    """
    commits = []
    for line in raw_output.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\x00", 3)
        if len(parts) >= 4:  # noqa: PLR2004
            commits.append(GitCommit(
                hash=parts[0],
                hash_short=parts[0][:7],
                author=parts[1],
                date=parts[2],
                message=parts[3],
            ))
    return commits


def _classify_status(staged: str, unstaged: str) -> tuple:
    """Classify git porcelain status codes into human-readable status and code.

    Args:
        staged: The staged (index) status character.
        unstaged: The unstaged (working tree) status character.

    Returns:
        Tuple of (status_label, status_code).

    """
    if staged == "?" or unstaged == "?":
        return "untracked", "?"
    if staged == "A" or unstaged == "A":
        return "added", "A"
    if staged == "D" or unstaged == "D":
        return "deleted", "D"
    if staged == "R":
        return "renamed", "R"
    if staged == "M" or unstaged == "M":
        return "modified", "M"
    return "changed", (staged if staged != " " else unstaged)


class GitService:
    """Centralized git operations service.

    All public methods return OperationResult. Multi-step mutations
    are serialized via an internal multiprocessing.Lock.
    """

    def __init__(self, config_path: str):
        self._config_path = config_path
        self._lock = multiprocessing.Lock()

    @property
    def config_path(self) -> str:
        return self._config_path

    @config_path.setter
    def config_path(self, path: str):
        self._config_path = path

    def _run_git(self, args: list[str], timeout: int = TIMEOUT_STATUS,
                 retry: bool = False, cwd: str | None = None) -> OperationResult:
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
        cmd = ["git"] + args
        work_dir = cwd or self._config_path
        max_attempts = 3 if retry else 1

        for attempt in range(max_attempts):
            try:
                result = subprocess.run(
                    cmd,
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                run_result = GitRunResult(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    returncode=result.returncode,
                )

                # Check for transient errors on non-zero return
                if self._should_retry_transient(result, retry, attempt, max_attempts, args):
                    continue

                return self._build_run_result(result, run_result, args)

            except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:  # noqa: BLE001
                return self._handle_git_exception(e, args, timeout)
        return None  # Unreachable: loop always returns

    def _should_retry_transient(self, result, retry: bool, attempt: int,
                                max_attempts: int, args: list[str]) -> bool:
        """Check if a failed git command should be retried due to transient errors.

        Returns True if the caller should continue to the next retry attempt.
        """
        if result.returncode == 0 or not retry or attempt >= max_attempts - 1:
            return False
        combined = result.stderr + result.stdout
        if any(pat in combined for pat in _TRANSIENT_PATTERNS):
            delay = (0.1 * (2 ** attempt)) + random.uniform(0, 0.05)
            logger.warning("git retry: cmd=%s attempt=%d", " ".join(args), attempt + 1)
            time.sleep(delay)
            return True
        return False

    def _build_run_result(self, result, run_result: GitRunResult,
                          args: list[str]) -> OperationResult:
        """Build OperationResult from a completed subprocess result."""
        if result.returncode != 0:
            logger.warning("git run failed: cmd=%s error=%s", " ".join(args), result.stderr.strip()[:200])

            error_msg = result.stderr.strip() or result.stdout.strip() or f"Git command failed with returncode {result.returncode}"
            return OperationResult(success=False, error=error_msg, data=run_result)

        return OperationResult(success=True, data=run_result)

    def _handle_git_exception(self, exc: Exception, args: list[str],
                              timeout: int) -> OperationResult:
        """Handle exceptions from git subprocess execution."""
        if isinstance(exc, subprocess.TimeoutExpired):
            error_msg = f'Git command timed out after {timeout}s: git {" ".join(args)}'
            logger.error("git timeout: cmd=%s", " ".join(args))
        elif isinstance(exc, FileNotFoundError):
            error_msg = "Git is not installed or not in PATH"
            logger.error("git not found")
        else:
            error_msg = f"Git command failed: {exc!s}"
            logger.error("git exception: cmd=%s error=%s", " ".join(args), str(exc))
        return OperationResult(success=False, error=error_msg)

    # =========================================================================
    # Query methods (no lock needed)
    # =========================================================================

    def is_repo(self) -> OperationResult:
        """Check if config_path is inside a git working tree.

        Returns OperationResult with data=bool.
        """
        result = self._run_git(["rev-parse", "--is-inside-work-tree"], timeout=TIMEOUT_QUERY)
        if not result.success:
            return OperationResult(success=True, data=False)
        return OperationResult(success=True, data=(result.data.returncode == 0))

    def get_status(self, excluded_paths: list[str] | None = None) -> OperationResult:
        """Get git status of config directory.

        Returns OperationResult with data=GitStatusResult.
        """
        if excluded_paths is None:
            excluded_paths = [".backups/", ".backups", ".staging/", ".staging",
                              ".git/", "backups/", "backups"]

        # Check if inside work tree
        repo_check = self._run_git(["rev-parse", "--is-inside-work-tree"], timeout=TIMEOUT_QUERY)
        if not repo_check.success:
            return OperationResult(success=True, data=GitStatusResult(
                is_repo=False, error=repo_check.error))
        if repo_check.data.returncode != 0:
            return OperationResult(success=True, data=GitStatusResult(
                is_repo=False, error="Not a git repository"))

        # Get current branch
        branch_result = self._run_git(["branch", "--show-current"], timeout=TIMEOUT_QUERY)
        branch = "HEAD detached"
        if branch_result.success and branch_result.data.returncode == 0:
            branch = branch_result.data.stdout.strip() or "HEAD detached"

        # D-07: Use -unormal instead of -uall to avoid memory issues on large repos
        # -uall recursively lists every file in untracked directories which can be slow/memory-intensive
        status_result = self._run_git(["status", "--porcelain", "-unormal"], timeout=TIMEOUT_STATUS)
        if not status_result.success:
            return OperationResult(success=False, error=status_result.error)

        files = self._parse_status_lines(status_result.data.stdout, excluded_paths)

        return OperationResult(success=True, data=GitStatusResult(
            is_repo=True,
            branch=branch,
            files=files,
            has_changes=len(files) > 0,
        ))

    def _parse_status_lines(self, raw_output: str,
                            excluded_paths: list[str]) -> list[GitFileStatus]:
        """Parse git status --porcelain output into GitFileStatus entries.

        Args:
            raw_output: Raw stdout from git status --porcelain.
            excluded_paths: Paths to exclude from results.

        Returns:
            List of GitFileStatus entries.

        """
        files = []
        for line in raw_output.split("\n"):
            line = line.rstrip("\r\n")
            if not line or len(line) < 4:  # noqa: PLR2004
                continue

            entry = self._parse_single_status_line(line, excluded_paths)
            if entry is not None:
                files.append(entry)
        return files

    @staticmethod
    def _parse_single_status_line(line: str,
                                  excluded_paths: list[str]) -> GitFileStatus | None:
        """Parse a single git status porcelain line into a GitFileStatus.

        Returns None if the line should be skipped (excluded path).
        """
        staged_status = line[0]
        unstaged_status = line[1]
        filepath = line[3:].strip()

        # Handle renamed files
        if " -> " in filepath:
            filepath = filepath.split(" -> ")[1]

        # Strip quotes
        if filepath.startswith('"') and filepath.endswith('"'):
            filepath = filepath[1:-1]

        # Skip excluded paths
        if any(filepath.startswith(exc) or filepath == exc.rstrip("/")
               for exc in excluded_paths):
            return None

        status, status_code = _classify_status(staged_status, unstaged_status)

        return GitFileStatus(
            path=filepath,
            status=status,
            status_code=status_code,
            staged=staged_status != " " and staged_status != "?",
            unstaged=unstaged_status != " " and unstaged_status != "?",
        )

    def get_diff(self, filepath: str | None = None, staged: bool = False,
                 full_file: bool = True, context_lines: int | None = None) -> OperationResult:
        """Get git diff for a file or all changes.

        Args:
            filepath: Specific file path, or None for all.
            staged: If True, show staged changes only.
            full_file: If True, show full file context.
            context_lines: Number of context lines (overrides full_file if set).

        Returns OperationResult with data=str (diff output).

        """
        cmd = ["diff", "HEAD"]
        if staged:
            cmd = ["diff", "--staged"]
        if context_lines is not None:
            cmd.insert(1, f"-U{context_lines}")
        elif full_file:
            cmd.insert(1, "-U9999")
        if filepath:
            cmd.append("--")
            cmd.append(filepath)

        # Note: git diff returns 0 for no changes, 1 for changes - both are valid
        result = self._run_git(cmd, timeout=TIMEOUT_MUTATE)
        if result.data is None:
            # Subprocess failed completely (timeout, not found, etc.)
            return result
        if result.data.returncode not in (0, 1):
            return OperationResult(success=False, error=result.error or f"Git diff failed with returncode {result.data.returncode}")

        diff_output = result.data.stdout

        # If file is untracked, show contents as a diff
        if filepath and not diff_output:
            diff_output = self._build_untracked_diff(filepath) or diff_output

        return OperationResult(success=True, data=diff_output)

    def _build_untracked_diff(self, filepath: str) -> str | None:
        """Build a synthetic diff for an untracked file.

        Returns the diff string, or None if the file is not untracked or unreadable.
        """
        status_result = self._run_git(
            ["status", "--porcelain", "--", filepath], timeout=TIMEOUT_QUERY)
        if not (status_result.success and
                status_result.data.stdout.startswith("??")):
            return None

        full_path = os.path.join(self._config_path, filepath)
        if not os.path.exists(full_path):
            return None

        try:
            with open(full_path) as f:
                content = f.read()
            lines = content.split("\n")
            diff_output = f"diff --git a/{filepath} b/{filepath}\n"
            diff_output += "new file mode 100644\n"
            diff_output += "--- /dev/null\n"
            diff_output += f"+++ b/{filepath}\n"
            diff_output += f"@@ -0,0 +1,{len(lines)} @@\n"
            diff_output += "\n".join("+" + line for line in lines)
            return diff_output
        except OSError:
            return None

    def get_workspace_diff(self, excluded_paths: list[str] | None = None) -> OperationResult:
        """Get workspace diff with parsed file-based structure.

        Used by the staging/diff endpoint. Returns structured diff data.

        Args:
            excluded_paths: Paths to exclude from diff output.

        Returns OperationResult with data=dict containing 'diffs' and 'git_changes'.

        """
        if excluded_paths is None:
            excluded_paths = [".backups/", ".staging/", ".git/"]

        # Get raw diff output (tries HEAD first, falls back to plain diff)
        diff_result = self._get_raw_diff_output()
        if not diff_result.success:
            return diff_result

        diff_output = diff_result.data
        diffs = []
        git_changes = []
        diff_file_paths = set()

        # Parse unified diff into file-based structure
        self._parse_diff_into_files(diff_output, excluded_paths,
                                    diffs, git_changes, diff_file_paths)

        # Also check for untracked and deleted files not in diff
        self._collect_untracked_changes(excluded_paths, diff_file_paths,
                                        diffs, git_changes)

        return OperationResult(success=True, data={
            "diffs": diffs,
            "git_changes": git_changes,
        })

    def _get_raw_diff_output(self) -> OperationResult:
        """Get raw git diff output, trying HEAD first then falling back.

        Returns OperationResult with data=str (raw diff text).
        """
        # Use HEAD to show both staged and unstaged changes (important after git restore)
        # Note: git diff returns 0 for no changes, 1 for changes - both are valid
        result = self._run_git(["diff", "HEAD", "--patience", "-U3"], timeout=TIMEOUT_MUTATE)
        if result.data is None:
            return result
        if result.data.returncode not in (0, 1):
            # Fall back to plain diff (e.g., no commits yet means no HEAD)
            result = self._run_git(["diff", "--patience", "-U3"], timeout=TIMEOUT_MUTATE)
            if result.data is None:
                return result
            if result.data.returncode not in (0, 1):
                return OperationResult(success=False,
                                       error=f"Git diff failed: {result.data.stderr}")

        return OperationResult(success=True, data=result.data.stdout)

    def _parse_diff_into_files(self, diff_output: str, excluded_paths: list[str],
                               diffs: list[dict], git_changes: list[dict],
                               diff_file_paths: set) -> None:
        """Parse unified diff output into per-file diff entries (mutates in place).

        Args:
            diff_output: Raw unified diff text.
            excluded_paths: Paths to exclude.
            diffs: List to append diff entry dicts to (mutated).
            git_changes: List to append git change dicts to (mutated).
            diff_file_paths: Set to add file paths to (mutated).

        """
        current_file = None
        current_lines = []
        current_rel_path = None

        for line in diff_output.split("\n"):
            if line.startswith("diff --git"):
                # Save previous file
                if (current_file and current_lines and current_rel_path and
                        not any(current_rel_path.startswith(exc) for exc in excluded_paths)):
                    self._append_diff_entry(diffs, git_changes, diff_file_paths,
                                            current_rel_path, current_lines)

                # Start new file
                parts = line.split(" b/")
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
        if (current_file and current_lines and current_rel_path and
                not any(current_rel_path.startswith(exc) for exc in excluded_paths)):
            self._append_diff_entry(diffs, git_changes, diff_file_paths,
                                    current_rel_path, current_lines)

    def _collect_untracked_changes(self, excluded_paths: list[str],
                                   diff_file_paths: set,
                                   diffs: list[dict],
                                   git_changes: list[dict]) -> None:
        """Collect untracked (.cfg) and deleted files not already in diff (mutates in place).

        Args:
            excluded_paths: Paths to exclude.
            diff_file_paths: Set of file paths already in diff output.
            diffs: List to append diff entry dicts to (mutated).
            git_changes: List to append git change dicts to (mutated).

        """
        status_result = self._run_git(["status", "--porcelain"], timeout=TIMEOUT_STATUS)
        if not (status_result.success and status_result.data.returncode == 0):
            return

        for line in status_result.data.stdout.split("\n"):
            if not line:
                continue
            status_code = line[:2]
            file_path = line[3:]

            if any(file_path.startswith(exc) for exc in excluded_paths):
                continue
            if file_path in diff_file_paths:
                continue

            if status_code == "??":
                self._add_untracked_cfg_diff(file_path, diffs, git_changes)
            elif status_code[0] == "D":
                self._add_deleted_file_diff(file_path, diffs, git_changes)

    def _add_untracked_cfg_diff(self, file_path: str, diffs: list[dict],
                                git_changes: list[dict]) -> None:
        """Add a synthetic diff entry for an untracked .cfg file (mutates in place)."""
        if not file_path.endswith(".cfg"):
            return
        full_path = os.path.join(self._config_path, file_path)
        try:
            with open(full_path) as f:
                content = f.read()
            content_lines = content.split("\n")
            diff_lines = [
                f"diff --git a/{file_path} b/{file_path}",
                "new file mode 100644",
                "--- /dev/null",
                f"+++ b/{file_path}",
                f"@@ -0,0 +1,{len(content_lines)} @@",
            ]
            diff_lines.extend(["+" + line for line in content_lines])
            diffs.append({
                "file_path": file_path,
                "diff": "\n".join(diff_lines),
                "diff_lines": diff_lines,
                "status": "added",
                "change_count": len(content_lines),
            })
            git_changes.append({"path": file_path, "status": "added"})
        except OSError:
            pass  # Unreadable untracked file - skip silently

    @staticmethod
    def _add_deleted_file_diff(file_path: str, diffs: list[dict],
                               git_changes: list[dict]) -> None:
        """Add a synthetic diff entry for a deleted file (mutates in place)."""
        diffs.append({
            "file_path": file_path,
            "diff": f"diff --git a/{file_path} b/{file_path}\ndeleted file",
            "diff_lines": [f"diff --git a/{file_path} b/{file_path}", "deleted file"],
            "status": "deleted",
            "change_count": 0,
        })
        git_changes.append({"path": file_path, "status": "deleted"})

    def _append_diff_entry(self,
                           diffs: list[dict],
                           git_changes: list[dict],
                           diff_file_paths: set,
                           rel_path: str,
                           lines: list[str]) -> None:
        """Append a parsed diff entry to the provided collections (mutates in place).

        Args:
            diffs: List to append diff entry dict to (mutated)
            git_changes: List to append git change dict to (mutated)
            diff_file_paths: Set to add file path to (mutated)
            rel_path: Relative path of the file
            lines: Diff lines for this file

        """
        additions = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))

        status = "modified"
        if any("new file mode" in line for line in lines):
            status = "added"
        elif any("deleted file mode" in line for line in lines):
            status = "deleted"

        diffs.append({
            "file_path": rel_path,
            "diff": "\n".join(lines),
            "diff_lines": lines,
            "status": status,
            "change_count": additions + deletions,
        })
        git_changes.append({"path": rel_path, "status": status})
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

        git_dir = os.path.join(self._config_path, ".git")
        if not os.path.isdir(git_dir):
            return OperationResult(success=True, data={
                "is_repo": False,
                "error": "Not a git repository",
                "commits": [],
            })

        # Use %x00 (null byte) as separator - cannot appear in commit messages
        result = self._run_git(
            ["log", f"-{limit}", "--format=%H%x00%an%x00%ai%x00%s"],
            timeout=TIMEOUT_MUTATE,
        )

        if result.data is None:
            return result
        # Handle non-zero returncodes - check for "no commits" case first
        if result.data.returncode != 0:
            if "does not have any commits" in result.data.stderr:
                return OperationResult(success=True, data={
                    "is_repo": True,
                    "commits": [],
                    "message": "No commits yet",
                })
            return OperationResult(success=False,
                                   error=f"Failed to get log: {result.data.stderr}")

        commits = _parse_log_entries(result.data.stdout)
        matching_commit = self._find_matching_commit(commits)

        return OperationResult(success=True, data={
            "is_repo": True,
            "commits": commits,
            "matching_commit": matching_commit,
        })

    def _find_matching_commit(self, commits: list[GitCommit]) -> str | None:
        """Find which commit (if any) matches the current working directory.

        Checks HEAD first, then scans up to 20 recent commits.

        Returns the matching commit hash, or None.
        """
        if not commits:
            return None

        head_check = self._run_git(["diff", "--quiet", "HEAD", "--"], timeout=TIMEOUT_STATUS)
        if head_check.success and head_check.data.returncode == 0:
            # No changes from HEAD
            commits[0].matches_working_dir = True
            return commits[0].hash

        # Check if working dir matches any recent commit (limit to first 20)
        for commit in commits[:20]:
            diff_check = self._run_git(
                ["diff", "--quiet", commit.hash, "--"], timeout=TIMEOUT_QUERY)
            if diff_check.success and diff_check.data.returncode == 0:
                commit.matches_working_dir = True
                return commit.hash

        return None

    def has_uncommitted_changes(self) -> OperationResult:
        """Check if there are uncommitted changes.

        Returns OperationResult with data=bool.
        """
        result = self._run_git(["status", "--porcelain"], timeout=TIMEOUT_STATUS)
        if not result.success:
            return result
        return OperationResult(success=True, data=bool(result.data.stdout.strip()))

    # =========================================================================
    # Mutation methods (hold lock for thread safety)
    # =========================================================================

    def _extract_error(self, result: OperationResult, context: str = "") -> str:
        """Extract error message from OperationResult with optional context.

        Args:
            result: OperationResult from _run_git
            context: Optional context string (e.g., 'Failed to stage files')

        Returns:
            Formatted error message

        """
        if not result.success:
            error = result.error
        elif result.data:
            error = result.data.stderr or result.data.stdout or "Unknown error"
        else:
            error = "Unknown error"

        return f"{context}: {error}" if context else error

    def init_repo(self) -> OperationResult:
        """Initialize a git repository in config_path.

        Creates .gitignore if it doesn't exist.
        Returns OperationResult with data=GitRunResult.
        """
        with self._lock:
            return self._init_repo_impl()

    def _init_repo_impl(self) -> OperationResult:
        """Implementation of repo initialization (lock must be held by caller).

        Returns OperationResult with data=GitRunResult.
        """
        result = self._run_git(["init"], timeout=TIMEOUT_MUTATE)
        if not result.success:
            return result
        if result.data.returncode != 0:
            return OperationResult(success=False,
                                   error=f"Failed to initialize git: {result.data.stderr}")

        gitignore_path = os.path.join(self._config_path, ".gitignore")
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, "w") as f:
                f.write("# Nagios Bulk Editor - auto-generated .gitignore\n")
                f.write("backups/\n")
                f.write(".staging/\n")
                f.write("*.bak\n")
                f.write("*.tmp\n")

        return OperationResult(success=True, data=result.data)

    def commit(self, message: str, files: list[str] | None = None,
               user_name: str | None = None, user_email: str | None = None,
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
                error="User identity (name and email) required for git operations",
            )

        with self._lock:
            # Ensure repo exists (auto-init if requested)
            init_error, initialized = self._ensure_repo(auto_init)
            if init_error is not None:
                return init_error

            return self._stage_and_commit(message, files, user_name, user_email, initialized)

    def _ensure_repo(self, auto_init: bool) -> tuple:
        """Ensure a git repo exists, optionally auto-initializing.

        Args:
            auto_init: If True, initialize repo when missing.

        Returns:
            Tuple of (error_result_or_None, initialized_bool).
            If error_result is not None, caller should return it immediately.

        """
        git_dir = os.path.join(self._config_path, ".git")
        if os.path.isdir(git_dir):
            return None, False

        if auto_init:
            init_result = self._init_repo_impl()
            if not init_result.success:
                return init_result, False
            return None, True

        return OperationResult(success=False, error="Not a git repository"), False

    def _stage_and_commit(self, message: str, files: list[str] | None,
                          user_name: str, user_email: str,
                          initialized: bool) -> OperationResult:
        """Stage files and execute a git commit (lock must be held by caller).

        Returns OperationResult with data=dict containing commit info.
        """
        # Stage files
        stage_cmd = ["add", "--"] + files if files else ["add", "-A"]
        stage_result = self._run_git(stage_cmd, timeout=TIMEOUT_MUTATE, retry=True)
        if not stage_result.success:
            return stage_result
        if stage_result.data.returncode != 0:
            return OperationResult(success=False,
                                   error=self._extract_error(stage_result, "Failed to stage files"))

        # Commit with user identity
        commit_cmd = ["-c", f"user.name={user_name}", "-c", f"user.email={user_email}",
                      "commit", "-m", message]
        commit_result = self._run_git(commit_cmd, timeout=TIMEOUT_MUTATE, retry=True)
        if not commit_result.success:
            return commit_result
        if commit_result.data.returncode != 0:
            combined = commit_result.data.stdout + commit_result.data.stderr
            if "nothing to commit" in combined:
                return OperationResult(success=False, error="Nothing to commit")
            return OperationResult(success=False,
                                   error=f"Commit failed: {commit_result.data.stderr or commit_result.data.stdout}")

        commit_hash = self._get_head_short_hash()

        return OperationResult(success=True, data={
            "commit_hash": commit_hash,
            "message": message,
            "output": commit_result.data.stdout,
            "initialized": initialized,
        })

    def _get_head_short_hash(self) -> str:
        """Get the short hash of HEAD. Returns empty string on failure."""
        hash_result = self._run_git(["rev-parse", "--short", "HEAD"], timeout=TIMEOUT_QUERY)
        if hash_result.success and hash_result.data.returncode == 0:
            return hash_result.data.stdout.strip()
        logger.warning(
            "Commit succeeded but failed to retrieve commit hash via rev-parse. "
            "commit_hash will be empty in response.",
        )
        return ""


    def discard(self, filepath: str) -> OperationResult:
        """Discard changes to a specific file.

        For untracked files, deletes them. For tracked files, checks out
        the committed version.

        Returns OperationResult with data=dict containing 'action'.
        """
        with self._lock:
            # Check if file is untracked
            status_result = self._run_git(
                ["status", "--porcelain", "--", filepath], timeout=TIMEOUT_QUERY)
            if not status_result.success:
                return status_result

            if status_result.data.stdout.startswith("??"):
                # Untracked file - delete it
                full_path = os.path.join(self._config_path, filepath)
                if os.path.exists(full_path):
                    os.remove(full_path)
                return OperationResult(success=True, data={"action": "deleted"})

            # Tracked file - checkout to discard
            result = self._run_git(["checkout", "--", filepath], timeout=TIMEOUT_STATUS)
            if not result.success:
                return result
            if result.data.returncode != 0:
                return OperationResult(success=False,
                                       error=f"Failed to discard changes: {result.data.stderr}")

            return OperationResult(success=True, data={"action": "restored"})

    def discard_all(self) -> OperationResult:
        """Discard all uncommitted changes (reset, checkout, clean).

        Returns OperationResult with data=dict containing 'commands'.
        """
        with self._lock:
            commands_run = []

            # Reset staged changes
            reset_result = self._run_git(["reset", "HEAD"], timeout=TIMEOUT_STATUS, retry=True)
            commands_run.append({
                "command": "git reset HEAD",
                "success": reset_result.success and reset_result.data.returncode == 0,
                "output": (reset_result.data.stdout or reset_result.data.stderr) if reset_result.success else reset_result.error,
            })

            # Checkout tracked files
            checkout_result = self._run_git(["checkout", "--", "."], timeout=TIMEOUT_MUTATE, retry=True)
            commands_run.append({
                "command": "git checkout -- .",
                "success": checkout_result.success and checkout_result.data.returncode == 0,
                "output": (checkout_result.data.stdout or checkout_result.data.stderr) if checkout_result.success else checkout_result.error,
            })
            if not checkout_result.success or checkout_result.data.returncode != 0:
                return OperationResult(success=False,
                                       error=self._extract_error(checkout_result, "Failed to discard changes"),
                                       data={"commands": commands_run})

            # Clean untracked files
            clean_result = self._run_git(["clean", "-fd"], timeout=TIMEOUT_MUTATE, retry=True)
            commands_run.append({
                "command": "git clean -fd",
                "success": clean_result.success and clean_result.data.returncode == 0,
                "output": (clean_result.data.stdout or clean_result.data.stderr) if clean_result.success else clean_result.error,
            })
            if not clean_result.success or clean_result.data.returncode != 0:
                return OperationResult(success=False,
                                       error=self._extract_error(clean_result, "Failed to clean untracked files"),
                                       data={"commands": commands_run})

            return OperationResult(success=True, data={"commands": commands_run})

    def _cleanup_extra_files(self, files_to_delete: list[str]) -> list[str]:
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
        for dir_path in sorted(directories_to_check, key=lambda x: x.count("/"), reverse=True):
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
            status_result = self._run_git(["status", "--porcelain"], timeout=TIMEOUT_STATUS)
            if not status_result.success:
                return status_result
            has_changes = bool(status_result.data.stdout.strip()) if status_result.data else False

            # Verify commit exists and get message
            verify_error = self._verify_commit_exists(commit_hash)
            if verify_error is not None:
                return verify_error

            commit_message = self._get_commit_message(commit_hash)

            # Stash uncommitted changes if present
            stashed = self._stash_if_needed(has_changes)

            return self._perform_restore(commit_hash, commit_message,
                                         has_changes, stashed)

    def _verify_commit_exists(self, commit_hash: str) -> OperationResult | None:
        """Verify that a commit hash exists and is a commit object.

        Returns an error OperationResult if verification fails, or None on success.
        """
        verify_result = self._run_git(["cat-file", "-t", commit_hash], timeout=TIMEOUT_QUERY)
        if verify_result.data is None:
            return OperationResult(success=False, error=verify_result.error)
        if verify_result.data.returncode != 0 or verify_result.data.stdout.strip() != "commit":
            return OperationResult(success=False, error="Commit not found")
        return None

    def _get_commit_message(self, commit_hash: str) -> str:
        """Get the subject line of a commit. Returns empty string on failure."""
        msg_result = self._run_git(["log", "-1", "--format=%s", commit_hash], timeout=TIMEOUT_QUERY)
        if msg_result.success and msg_result.data and msg_result.data.returncode == 0:
            return msg_result.data.stdout.strip()
        return ""

    def _stash_if_needed(self, has_changes: bool) -> bool:
        """Stash uncommitted changes if present. Returns True if stash succeeded."""
        if not has_changes:
            return False
        stash_result = self._run_git(["stash", "push", "-m", "Auto-stash before restore"],
                                     timeout=TIMEOUT_MUTATE)
        return stash_result.success and stash_result.data and stash_result.data.returncode == 0

    def _handle_restore_error(self, base_error: str, stashed: bool) -> OperationResult:
        """Try to restore stash after a failed restore and build error message."""
        if not stashed:
            return OperationResult(success=False, error=base_error)

        pop_result = self._run_git(["stash", "pop"], timeout=TIMEOUT_STATUS)
        if not pop_result.success or pop_result.data.returncode != 0:
            stash_pop_error = (pop_result.error if not pop_result.success
                               else pop_result.data.stderr)
            logger.warning("Failed to restore stash: %s", stash_pop_error)
            error_msg = (
                f"{base_error} Your uncommitted changes were stashed but could not be "
                f"automatically restored (error: {stash_pop_error}). "
                "Run 'git stash pop' manually to recover your work."
            )
        else:
            error_msg = f"{base_error} Your uncommitted changes have been restored from stash."

        return OperationResult(success=False, error=error_msg)

    def _list_tree_files(self, ref: str) -> set | None:
        """List all file paths in a git tree reference (commit or HEAD).

        Returns a set of file paths, or None if the command failed.
        """
        result = self._run_git(["ls-tree", "-r", "--name-only", ref],
                               timeout=TIMEOUT_MUTATE)
        if result.data is None or result.data.returncode != 0:
            return None
        return set(f.strip() for f in result.data.stdout.strip().split("\n") if f.strip())

    def _perform_restore(self, commit_hash: str, commit_message: str,
                         has_changes: bool, stashed: bool) -> OperationResult:
        """Execute the restore operation (lock must be held by caller).

        Lists files in HEAD and target, checks out target, and cleans up extras.
        """
        head_files = self._list_tree_files("HEAD")
        if head_files is None:
            return self._handle_restore_error("Failed to list HEAD files", stashed)

        target_files = self._list_tree_files(commit_hash)
        if target_files is None:
            return self._handle_restore_error("Failed to list target commit files", stashed)

        files_to_delete = list(head_files - target_files)

        # Checkout files from target commit
        restore_result = self._run_git(["checkout", commit_hash, "--", "."],
                                       timeout=TIMEOUT_MUTATE)
        if restore_result.data is None or restore_result.data.returncode != 0:
            error = (restore_result.error or
                     (restore_result.data.stderr if restore_result.data else "Unknown error"))
            return self._handle_restore_error(f"Failed to restore: {error}", stashed)

        # Delete files that were added after the target commit
        deleted_files = self._cleanup_extra_files(files_to_delete)

        return OperationResult(success=True, data={
            "commit": commit_hash,
            "message": commit_message,
            "had_uncommitted_changes": has_changes,
            "stashed": stashed,
            "deleted_files": deleted_files,
        })

    def clear_history(self, user_name: str, user_email: str) -> OperationResult:
        """Clear all git history and reinitialize with a fresh commit.

        Args:
            user_name: Git author name for the fresh commit.
            user_email: Git author email for the fresh commit.

        Returns OperationResult with data=dict on success.

        """
        with self._lock:
            git_dir = os.path.join(self._config_path, ".git")

            # Remove .git directory
            if os.path.isdir(git_dir):
                shutil.rmtree(git_dir)

            # Initialize new repo
            init_result = self._run_git(["init"], timeout=TIMEOUT_STATUS)
            if not init_result.success or init_result.data.returncode != 0:
                return OperationResult(success=False,
                                       error=self._extract_error(init_result, "Failed to initialize git"))

            # Add all files
            self._run_git(["add", "-A"], timeout=TIMEOUT_MUTATE)

            # Create initial commit
            commit_result = self._run_git(
                ["-c", f"user.name={user_name}", "-c", f"user.email={user_email}",
                 "commit", "-m", "Initial commit"],
                timeout=TIMEOUT_MUTATE,
            )
            if not commit_result.success or commit_result.data.returncode != 0:
                return OperationResult(success=False,
                                       error=self._extract_error(commit_result, "Failed to create initial commit"))

            return OperationResult(success=True, data={
                "message": "Git history cleared and reinitialized",
            })
