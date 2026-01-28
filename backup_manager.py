"""
Backup Manager for Nagios Configuration

Creates timestamped zip backups before any changes and provides restore functionality.
"""

import shutil
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

    def create_backup(self, description: str = "", user_name: str = "", user_email: str = "") -> str:
        """Create a timestamped zip backup of all configuration files."""
        if self._op_logger:
            self._op_logger.info('backup', 'create_backup', params={'description': description}, user_name=user_name, user_email=user_email)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}"
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
        copied_files = 0
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for cfg_file in self.config_path.rglob("*.cfg"):
                # Skip files in backups directory
                try:
                    cfg_file.relative_to(self.backup_path)
                    continue
                except ValueError:
                    pass

                rel_path = cfg_file.relative_to(self.config_path)
                zf.write(cfg_file, str(rel_path))
                copied_files += 1

            # Add metadata inside the zip
            metadata_lines.insert(3, f"Files backed up: {copied_files}")
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

            # Legacy support: directory-based backups
            elif item.is_dir() and item.name.startswith("backup_"):
                info = {
                    'name': item.name,
                    'path': str(item),
                    'created': None,
                    'description': '',
                    'file_count': 0,
                    'user_name': '',
                    'user_email': ''
                }

                metadata_file = item / "_backup_info.txt"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        for line in f:
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
                    info['file_count'] = len(list(item.rglob("*.cfg")))

                backups.append(info)

        # Sort by creation time, most recent first
        backups.sort(key=lambda x: x['created'] or '', reverse=True)
        return backups

    def restore_backup(self, backup_name: str, user_name: str = "", user_email: str = "") -> Dict:
        """Restore configuration from a backup (zip or legacy directory)."""
        if self._op_logger:
            self._op_logger.info('backup', 'restore_backup', params={'backup_name': backup_name}, user_name=user_name, user_email=user_email)
        # Validate backup_name to prevent path traversal
        if '..' in backup_name or backup_name.startswith('/'):
            raise ValueError(f"Invalid backup name: {backup_name}")

        backup_path = self.backup_path / backup_name

        # Determine if this is a zip or legacy directory backup
        is_zip = backup_name.endswith('.zip') and backup_path.is_file()
        is_dir = backup_path.is_dir()

        if not is_zip and not is_dir:
            raise ValueError(f"Backup not found: {backup_name}")

        # Verify path is actually under backup_path
        try:
            backup_path.resolve().relative_to(self.backup_path.resolve())
        except ValueError:
            raise ValueError(f"Backup outside backup path: {backup_name}")

        # Create a safety backup before restoring
        safety_backup = self.create_backup("pre_restore_safety", user_name=user_name, user_email=user_email)

        try:
            # Remove current config files (except backups)
            for cfg_file in self.config_path.rglob("*.cfg"):
                try:
                    cfg_file.relative_to(self.backup_path)
                    continue
                except ValueError:
                    pass
                cfg_file.unlink()

            restored_count = 0
            skipped_count = 0

            if is_zip:
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

                        dest_path = (self.config_path / member_path).resolve()
                        try:
                            dest_path.relative_to(self.config_path.resolve())
                        except ValueError:
                            skipped_count += 1
                            continue

                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(dest_path, 'wb') as dst:
                            dst.write(src.read())
                        restored_count += 1
            else:
                # Legacy directory restore
                for cfg_file in backup_path.rglob("*.cfg"):
                    rel_path = cfg_file.relative_to(backup_path)

                    dest_path = (self.config_path / rel_path).resolve()
                    try:
                        dest_path.relative_to(self.config_path.resolve())
                    except ValueError:
                        skipped_count += 1
                        continue

                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(cfg_file, dest_path)
                    restored_count += 1

            return {
                'restored_from': backup_name,
                'files_restored': restored_count,
                'files_skipped': skipped_count,
                'safety_backup': safety_backup
            }
        except Exception as e:
            raise ValueError(
                f"Restore failed: {e}. Config state may be inconsistent. "
                f"Safety backup available at: {safety_backup}"
            ) from e

    def delete_backup(self, backup_name: str) -> bool:
        """Delete a specific backup (zip or legacy directory)."""
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
        elif backup_path.is_dir():
            shutil.rmtree(backup_path)
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
