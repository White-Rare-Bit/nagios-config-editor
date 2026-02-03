"""
Backup Manager for Nagios Configuration

Creates timestamped zip backups before any changes and provides restore functionality.
"""

import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict


class BackupManager:
    """Manages backups of Nagios configuration files as zip archives."""

    def __init__(self, config_path: str, backup_path: Optional[str] = None, op_logger=None):
        self.config_path = Path(config_path)
        self.backup_path = Path(backup_path) if backup_path else self.config_path / "backups"
        self._op_logger = op_logger

        # C-03: Validate backup_path != config_path to prevent empty backups
        if self.backup_path.resolve() == self.config_path.resolve():
            raise ValueError(
                f"backup_path ({self.backup_path}) must not equal config_path ({self.config_path}). "
                "This would cause empty backups since all .cfg files would be skipped."
            )

    def create_backup(self, description: str = "", user_name: str = "", user_email: str = "") -> str:
        """Create a timestamped zip backup of all configuration files."""
        if self._op_logger:
            self._op_logger.info('backup', 'create_backup', params={'description': description}, user_name=user_name, user_email=user_email)
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
        metadata_lines = [
            f"Backup created: {datetime.now().isoformat()}",
            f"Description: {description}",
            f"Source: {self.config_path}",
        ]
        if user_name:
            metadata_lines.append(f"User name: {user_name}")
        if user_email:
            metadata_lines.append(f"User email: {user_email}")

        # Create zip with all .cfg files
        # S-02: Use os.walk with followlinks=False to avoid following symlinks
        copied_files = 0
        skipped_symlinks = 0
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(self.config_path, followlinks=False):
                root_path = Path(root)
                # Skip the backup directory
                try:
                    root_path.relative_to(self.backup_path)
                    dirs[:] = []  # Don't descend into backup directory
                    continue
                except ValueError:
                    pass

                for filename in files:
                    if not filename.endswith('.cfg'):
                        continue
                    cfg_file = root_path / filename

                    # S-02: Skip symlinks with warning to prevent security leak
                    if cfg_file.is_symlink():
                        skipped_symlinks += 1
                        if self._op_logger:
                            self._op_logger.warning('backup', 'create_backup',
                                params={'skipped_symlink': str(cfg_file)},
                                error='Symlink skipped for security')
                        continue

                    rel_path = cfg_file.relative_to(self.config_path)
                    zf.write(cfg_file, str(rel_path))
                    copied_files += 1

            # Add metadata inside the zip
            metadata_lines.insert(3, f"Files backed up: {copied_files}")
            if skipped_symlinks > 0:
                metadata_lines.insert(4, f"Symlinks skipped: {skipped_symlinks}")
            zf.writestr("_backup_info.txt", "\n".join(metadata_lines) + "\n")

        return str(zip_path)

    def list_backups(self) -> List[Dict]:
        """List all available backups, most recent first."""
        backups = []

        if not self.backup_path.exists():
            return backups

        for item in self.backup_path.iterdir():
            # Support zip archives
            if item.is_file() and item.name.startswith("backup_") and item.name.endswith(".zip"):
                info = {
                    'name': item.name,
                    'path': str(item),
                    'created': None,
                    'description': '',
                    'file_count': 0,
                    'user_name': '',
                    'user_email': ''
                }

                try:
                    with zipfile.ZipFile(item, 'r') as zf:
                        if '_backup_info.txt' in zf.namelist():
                            metadata = zf.read('_backup_info.txt').decode('utf-8')
                            for line in metadata.splitlines():
                                if line.startswith("Backup created:"):
                                    info['created'] = line.split(":", 1)[1].strip()
                                elif line.startswith("Description:"):
                                    info['description'] = line.split(":", 1)[1].strip()
                                elif line.startswith("Files backed up:"):
                                    try:
                                        info['file_count'] = int(line.split(":")[1].strip())
                                    except ValueError:
                                        pass
                                elif line.startswith("User name:"):
                                    info['user_name'] = line.split(":", 1)[1].strip()
                                elif line.startswith("User email:"):
                                    info['user_email'] = line.split(":", 1)[1].strip()
                        else:
                            info['created'] = datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                            info['file_count'] = len([n for n in zf.namelist() if n.endswith('.cfg')])
                except (zipfile.BadZipFile, OSError):
                    info['created'] = datetime.fromtimestamp(item.stat().st_mtime).isoformat()

                backups.append(info)

        # Sort by creation time, most recent first
        backups.sort(key=lambda x: x['created'] or '', reverse=True)
        return backups

    def restore_backup(self, backup_name: str, user_name: str = "", user_email: str = "") -> Dict:
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
        if self._op_logger:
            self._op_logger.info('backup', 'restore_backup', params={'backup_name': backup_name}, user_name=user_name, user_email=user_email)
        # Validate backup_name to prevent path traversal
        if '..' in backup_name or backup_name.startswith('/'):
            raise ValueError(f"Invalid backup name: {backup_name}")

        backup_path = self.backup_path / backup_name

        # Only zip backups are supported (directory backups removed)
        if backup_path.is_dir():
            raise ValueError(
                f"Directory-based backups are no longer supported. "
                f"Please restore from a zip backup or manually copy files from {backup_path}"
            )

        if not (backup_name.endswith('.zip') and backup_path.is_file()):
            raise ValueError(f"Backup not found: {backup_name}")

        # Verify path is actually under backup_path
        try:
            backup_path.resolve().relative_to(self.backup_path.resolve())
        except ValueError:
            raise ValueError(f"Backup outside backup path: {backup_name}")

        # Create a safety backup before restoring
        safety_backup = self.create_backup("pre_restore_safety", user_name=user_name, user_email=user_email)

        # C-01 FIX: Extract to temp directory first, validate, then replace
        temp_dir = None
        try:
            # Phase 1: Extract backup to temporary directory
            temp_dir = tempfile.mkdtemp(prefix='nagios_restore_')
            temp_path = Path(temp_dir)
            restored_count = 0
            skipped_count = 0

            # Extract zip backup to temp directory
            with zipfile.ZipFile(backup_path, 'r') as zf:
                for member in zf.namelist():
                    # Skip metadata file
                    if member == '_backup_info.txt':
                        continue
                    if not member.endswith('.cfg'):
                        continue

                    # Path traversal protection
                    member_path = Path(member)
                    if '..' in member_path.parts:
                        skipped_count += 1
                        continue

                    dest_path = (temp_path / member_path).resolve()
                    try:
                        dest_path.relative_to(temp_path.resolve())
                    except ValueError:
                        skipped_count += 1
                        continue

                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest_path, 'wb') as dst:
                        dst.write(src.read())
                    restored_count += 1

            # Phase 2: Validate extraction succeeded
            if restored_count == 0:
                raise ValueError("Backup contains no valid .cfg files to restore")

            # Phase 3: Now safe to remove current config files (extraction succeeded)
            for cfg_file in self.config_path.rglob("*.cfg"):
                try:
                    cfg_file.relative_to(self.backup_path)
                    continue  # Skip files in backups directory
                except ValueError:
                    pass
                cfg_file.unlink()

            # Phase 4: Move extracted files to config directory
            for cfg_file in temp_path.rglob("*.cfg"):
                rel_path = cfg_file.relative_to(temp_path)
                dest_path = self.config_path / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(cfg_file), str(dest_path))

            return {
                'restored_from': backup_name,
                'files_restored': restored_count,
                'files_skipped': skipped_count,
                'safety_backup': safety_backup
            }
        except Exception as e:
            raise ValueError(
                f"Restore failed: {e}. "
                f"Safety backup available at: {safety_backup}. "
                f"Recovery: DELETE /api/staging to clear lock, then POST /api/backups/<safety_backup>/restore"
            ) from e
        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except OSError:
                    pass  # Best effort cleanup

    def delete_backup(self, backup_name: str) -> bool:
        """Delete a specific zip backup."""
        if self._op_logger:
            self._op_logger.info('backup', 'delete_backup', params={'backup_name': backup_name})
        # Validate backup_name to prevent path traversal
        if '..' in backup_name or backup_name.startswith('/'):
            raise ValueError(f"Invalid backup name: {backup_name}")

        backup_path = self.backup_path / backup_name

        # Verify path is actually under backup_path
        try:
            backup_path.resolve().relative_to(self.backup_path.resolve())
        except ValueError:
            raise ValueError(f"Backup outside backup path: {backup_name}")

        if backup_path.is_file() and backup_name.endswith('.zip'):
            backup_path.unlink()
            return True
        return False

    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """Remove old backups, keeping only the most recent ones."""
        if self._op_logger:
            self._op_logger.info('backup', 'cleanup_old_backups', params={'keep_count': keep_count})
        backups = self.list_backups()
        deleted = 0

        if len(backups) > keep_count:
            for backup in backups[keep_count:]:
                if self.delete_backup(backup['name']):
                    deleted += 1

        return deleted
