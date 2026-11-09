"""Backup Manager for Nagios Configuration

Creates timestamped zip backups before any changes and provides restore functionality.

A backup covers every config root. With a single root the zip holds the files
at their relative paths (the original layout). With several roots each root's
files sit under ``root_N/`` and ``_backup_info.txt`` records which directory
each ``root_N`` is, so a restore puts every file back where it came from.
"""

import contextlib
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages backups of Nagios configuration files as zip archives."""

    def __init__(self, config_path: str, backup_path: str | None = None, *,
                 cfg_dirs: list[str] | None = None):
        """Create a backup manager.

        Args:
            config_path: Primary config directory. Backups go to its
                ``backups/`` subdirectory unless backup_path is given.
            backup_path: Directory to store backup zips in.
            cfg_dirs: Every config root. Each one is backed up and restored
                along with config_path. Defaults to just config_path.
        """
        self.config_path = Path(config_path)
        self.backup_path = Path(backup_path) if backup_path else self.config_path / "backups"
        self.roots = self._covering_roots([config_path, *(cfg_dirs or [])])

        # C-03: Validate backup_path != config_path to prevent empty backups
        if self.backup_path.resolve() == self.config_path.resolve():
            raise ValueError(
                f"backup_path ({self.backup_path}) must not equal config_path ({self.config_path}). "
                "This would cause empty backups since all .cfg files would be skipped.",
            )

    @staticmethod
    def _covering_roots(dirs: list[str]) -> list[Path]:
        """Smallest list of directories that contains every given directory.

        Duplicates and directories nested inside another one are dropped, so
        no file is backed up (or restored) twice. Order is kept.
        """
        resolved = []
        for d in dirs:
            path = Path(d).resolve()
            if path not in resolved:
                resolved.append(path)
        return [
            d for d in resolved
            if not any(other != d and other in d.parents for other in resolved)
        ]

    @property
    def _multi_root(self) -> bool:
        """Whether archives use the ``root_N/`` layout with a root table.

        The plain layout (paths relative to config_path, as in backups made
        before multi-root support) is only used when config_path is the one
        and only root, so a plain archive always means "relative to
        config_path".
        """
        return len(self.roots) > 1 or self.roots[0] != self.config_path.resolve()

    def _collect_config_files(self):
        """Yield every .cfg file of every root as (path, archive_name, was_symlink).

        archive_name is the path inside the zip: relative to the root, with a
        ``root_N/`` prefix when there are several roots.
        """
        for index, root in enumerate(self.roots):
            prefix = Path(f"root_{index}") if self._multi_root else Path()
            for cfg_file, rel_path, is_symlink in self._collect_root_files(root):
                yield cfg_file, (prefix / rel_path if rel_path is not None else None), is_symlink

    def _collect_root_files(self, config_root: Path):
        """Walk one config root, yield (cfg_file_path, rel_path) for each .cfg file.

        Skips the backup directory, non-.cfg files, and symlinks.
        Returns tuples of (Path, Path, was_symlink) where was_symlink indicates
        a skipped symlink (cfg_file_path and rel_path will be None for symlinks).

        S-02: Uses os.walk with followlinks=False to avoid following symlinks.
        """
        backup_dir = self.backup_path.resolve()
        for root, dirs, files in os.walk(config_root, followlinks=False):
            root_path = Path(root)
            # Skip the backup directory
            try:
                root_path.relative_to(backup_dir)
                dirs[:] = []  # Don't descend into backup directory
                continue
            except ValueError:
                pass

            for filename in files:
                if not filename.endswith(".cfg"):
                    continue
                cfg_file = root_path / filename

                # S-02: Skip symlinks with warning to prevent security leak
                if cfg_file.is_symlink():
                    yield cfg_file, None, True
                    continue

                rel_path = cfg_file.relative_to(config_root)
                yield cfg_file, rel_path, False

    def create_backup(self, description: str = "", user_name: str = "", user_email: str = "") -> str:
        """Create a timestamped zip backup of all configuration files."""
        logger.info("create_backup: description=%s user=%s", description, user_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # C-02: Add UUID suffix to prevent filename collision on concurrent creates
        unique_id = uuid.uuid4().hex[:8]
        backup_name = f"backup_{timestamp}_{unique_id}"
        if description:
            # Sanitize description for use in filename
            safe_desc = "".join(c if c.isalnum() or c in "-_" else "_" for c in description)
            backup_name = f"{backup_name}_{safe_desc[:30]}"

        self.backup_path.mkdir(parents=True, exist_ok=True)
        zip_path = self.backup_path / f"{backup_name}.zip"

        # Build metadata content
        metadata_lines = self._build_metadata_lines(description, user_name, user_email)

        # Create zip with all .cfg files
        copied_files = 0
        skipped_symlinks = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for cfg_file, rel_path, is_symlink in self._collect_config_files():
                if is_symlink:
                    skipped_symlinks += 1
                    logger.warning("create_backup: symlink skipped for security: %s", cfg_file)
                    continue
                zf.write(cfg_file, str(rel_path))
                copied_files += 1

            # Add metadata inside the zip
            metadata_lines.insert(3, f"Files backed up: {copied_files}")
            if skipped_symlinks > 0:
                metadata_lines.insert(4, f"Symlinks skipped: {skipped_symlinks}")
            zf.writestr("_backup_info.txt", "\n".join(metadata_lines) + "\n")

        return str(zip_path)

    def _build_metadata_lines(self, description: str, user_name: str, user_email: str) -> list[str]:
        """Build metadata lines for backup info file."""
        lines = [
            f"Backup created: {datetime.now().isoformat()}",
            f"Description: {description}",
            f"Source: {self.config_path}",
        ]
        if self._multi_root:
            lines.extend(f"Root root_{i}: {root}" for i, root in enumerate(self.roots))
        if user_name:
            lines.append(f"User name: {user_name}")
        if user_email:
            lines.append(f"User email: {user_email}")
        return lines

    def _parse_backup_metadata(self, zip_path: Path) -> dict:
        """Read metadata from a backup zip file.

        Returns a dict with keys: name, path, created, description, file_count,
        user_name, user_email.
        """
        info = {
            "name": zip_path.name,
            "path": str(zip_path),
            "created": None,
            "description": "",
            "file_count": 0,
            "user_name": "",
            "user_email": "",
        }

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "_backup_info.txt" in zf.namelist():
                    self._parse_metadata_text(info, zf.read("_backup_info.txt").decode("utf-8"))
                else:
                    info["created"] = datetime.fromtimestamp(zip_path.stat().st_mtime).isoformat()
                    info["file_count"] = len([n for n in zf.namelist() if n.endswith(".cfg")])
        except (zipfile.BadZipFile, OSError):
            info["created"] = datetime.fromtimestamp(zip_path.stat().st_mtime).isoformat()

        return info

    @staticmethod
    def _parse_metadata_text(info: dict, metadata: str) -> None:
        """Parse _backup_info.txt content into info dict."""
        _METADATA_FIELDS = {
            "Backup created:": "created",
            "Description:": "description",
            "User name:": "user_name",
            "User email:": "user_email",
        }
        for line in metadata.splitlines():
            for prefix, key in _METADATA_FIELDS.items():
                if line.startswith(prefix):
                    info[key] = line.split(":", 1)[1].strip()
                    break
            else:
                if line.startswith("Files backed up:"):
                    with contextlib.suppress(ValueError):
                        info["file_count"] = int(line.split(":")[1].strip())

    def list_backups(self) -> list[dict]:
        """List all available backups, most recent first."""
        backups = []

        if not self.backup_path.exists():
            return backups

        for item in self.backup_path.iterdir():
            # Support zip archives
            if item.is_file() and item.name.startswith("backup_") and item.name.endswith(".zip"):
                backups.append(self._parse_backup_metadata(item))

        # Sort by creation time, most recent first
        backups.sort(key=lambda x: x["created"] or "", reverse=True)
        return backups

    def _validate_backup_request(self, backup_name: str) -> Path:
        """Validate backup name for path safety and existence.

        Returns the resolved backup path if valid.
        Raises ValueError for invalid names, missing files, or directory backups.
        """
        # Validate backup_name to prevent path traversal
        if ".." in backup_name or backup_name.startswith("/"):
            raise ValueError(f"Invalid backup name: {backup_name}")

        backup_path = self.backup_path / backup_name

        # Only zip backups are supported (directory backups removed)
        if backup_path.is_dir():
            raise ValueError(
                f"Directory-based backups are no longer supported. "
                f"Please restore from a zip backup or manually copy files from {backup_path}",
            )

        if not (backup_name.endswith(".zip") and backup_path.is_file()):
            raise ValueError(f"Backup not found: {backup_name}")

        # Verify path is actually under backup_path
        try:
            backup_path.resolve().relative_to(self.backup_path.resolve())
        except ValueError:
            raise ValueError(f"Backup outside backup path: {backup_name}") from None

        return backup_path

    def _extract_backup_to_temp(self, zip_path: Path, temp_path: Path) -> tuple:
        """Extract .cfg files from backup zip to temp directory.

        Returns (restored_count, skipped_count).
        Path traversal protection: members with '..' in parts are skipped.
        """
        restored_count = 0
        skipped_count = 0

        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if member == "_backup_info.txt" or not member.endswith(".cfg"):
                    continue

                member_path = Path(member)
                if ".." in member_path.parts:
                    skipped_count += 1
                    continue

                dest_path = (temp_path / member_path).resolve()
                try:
                    dest_path.relative_to(temp_path.resolve())
                except ValueError:
                    skipped_count += 1
                    continue

                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest_path, "wb") as dst:
                    dst.write(src.read())
                restored_count += 1

        return restored_count, skipped_count

    @staticmethod
    def _recorded_roots(zip_path: Path) -> dict[str, Path]:
        """Read the ``root_N -> directory`` table of a multi-root backup.

        Empty for single-root backups (and for backups made before multi-root
        support), whose files are stored relative to the primary directory.
        """
        roots = {}
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "_backup_info.txt" not in zf.namelist():
                    return roots
                for line in zf.read("_backup_info.txt").decode("utf-8").splitlines():
                    if line.startswith("Root root_"):
                        name, _, path = line[len("Root "):].partition(": ")
                        if path:
                            roots[name] = Path(path)
        except (zipfile.BadZipFile, OSError):
            pass
        return roots

    def _restore_plan(self, zip_path: Path, temp_path: Path) -> list[tuple[Path, Path]]:
        """Decide where the extracted files go: [(extracted_dir, config_root)].

        A backup may only be restored into directories that are config roots
        now. What a zip claims about its origin is never trusted as a place
        to write to.
        """
        recorded = self._recorded_roots(zip_path)
        if not recorded:
            return [(temp_path, self.config_path.resolve())]
        plan = []
        for name, original in recorded.items():
            original = original.resolve()
            if original in self.roots:
                plan.append((temp_path / name, original))
            else:
                logger.warning("restore: %s (%s) is not a config root any more; skipped", name, original)
        return plan

    def _replace_config_files(self, temp_path: Path, config_root: Path | None = None) -> int:
        """Remove current .cfg files and move extracted ones into a config root.

        Phase 3: Remove current config files (skipping backup directory).
        Phase 4: Move extracted files from temp to config directory.

        Returns the number of files put in place.
        """
        config_root = config_root or self.config_path.resolve()
        backup_dir = self.backup_path.resolve()
        for cfg_file in config_root.rglob("*.cfg"):
            try:
                cfg_file.resolve().relative_to(backup_dir)
                continue  # Skip files in backups directory
            except ValueError:
                pass
            cfg_file.unlink()

        moved = 0
        for cfg_file in temp_path.rglob("*.cfg"):
            rel_path = cfg_file.relative_to(temp_path)
            dest_path = config_root / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(cfg_file), str(dest_path))
            moved += 1
        return moved

    def restore_backup(self, backup_name: str, user_name: str = "", user_email: str = "") -> dict:
        """Restore configuration from a zip backup.

        C-01 FIX: Uses atomic restore pattern - extracts to temp dir first, validates,
        then replaces config files. This prevents empty config directory on restore failure.

        D-01 RECOVERY PROCEDURE:
        If restore fails after safety backup but before file replacement, config is unchanged.
        If restore fails during file replacement:
        1. Clear staging lock: DELETE /api/staging
        2. Restore from safety backup: POST /api/backups/{safety_backup_name}/restore
        Or manually extract the safety backup zip to config directory.
        """
        logger.info("restore_backup: backup_name=%s user=%s", backup_name, user_name)

        backup_path = self._validate_backup_request(backup_name)

        # Create a safety backup before restoring
        safety_backup = self.create_backup("pre_restore_safety", user_name=user_name, user_email=user_email)

        # C-01 FIX: Extract to temp directory first, validate, then replace
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="nagios_restore_")
            temp_path = Path(temp_dir)

            # Phase 1: Extract backup to temporary directory
            restored_count, skipped_count = self._extract_backup_to_temp(backup_path, temp_path)

            # Phase 2: Validate extraction succeeded
            if restored_count == 0:
                raise ValueError("Backup contains no valid .cfg files to restore")

            # Phase 3 & 4: Remove old configs and move new ones, root by root
            plan = self._restore_plan(backup_path, temp_path)
            if not plan:
                raise ValueError("Backup was made for directories that are not config roots now")
            placed = sum(self._replace_config_files(src, root) for src, root in plan)
            skipped_count += restored_count - placed
            restored_count = placed

            return {
                "restored_from": backup_name,
                "files_restored": restored_count,
                "files_skipped": skipped_count,
                "safety_backup": safety_backup,
            }
        except Exception as e:  # noqa: BLE001
            raise ValueError(
                f"Restore failed: {e}. "
                f"Safety backup available at: {safety_backup}. "
                f"Recovery: DELETE /api/staging to clear lock, then POST /api/backups/<safety_backup>/restore",
            ) from e
        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                with contextlib.suppress(OSError):
                    shutil.rmtree(temp_dir)  # Best effort cleanup

    def delete_backup(self, backup_name: str) -> bool:
        """Delete a specific zip backup."""
        logger.info("delete_backup: backup_name=%s", backup_name)
        # Validate backup_name to prevent path traversal
        if ".." in backup_name or backup_name.startswith("/"):
            raise ValueError(f"Invalid backup name: {backup_name}")

        backup_path = self.backup_path / backup_name

        # Verify path is actually under backup_path
        try:
            backup_path.resolve().relative_to(self.backup_path.resolve())
        except ValueError:
            raise ValueError(f"Backup outside backup path: {backup_name}") from None

        if backup_path.is_file() and backup_name.endswith(".zip"):
            backup_path.unlink()
            return True
        return False

    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """Remove old backups, keeping only the most recent ones."""
        logger.info("cleanup_old_backups: keep_count=%d", keep_count)
        backups = self.list_backups()
        deleted = 0

        if len(backups) > keep_count:
            for backup in backups[keep_count:]:
                if self.delete_backup(backup["name"]):
                    deleted += 1

        return deleted
