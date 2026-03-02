# L02: backup_manager.py — MODIFY

**Layer:** 2 — Backend Prep
**Action:** MODIFY
**Path:** `backup_manager.py`
**Dependencies:** None
**Goal:** Exclude `.candidate/` (and `.staging/`) directories from backup creation and restore operations. Update error message referencing `DELETE /api/staging`.

---

## Current State

### `_collect_config_files()` (line 33)

Currently only skips the backup directory. Does NOT exclude `.candidate/` or `.staging/`:

```python
def _collect_config_files(self):
    for root, dirs, files in os.walk(self.config_path, followlinks=False):
        root_path = Path(root)
        # Skip the backup directory
        try:
            root_path.relative_to(self.backup_path)
            dirs[:] = []
            continue
        except ValueError:
            pass
        # ... yields .cfg files
```

### `_replace_config_files()` (line 242)

During restore, deletes ALL .cfg files except those in backup directory. Does NOT protect `.candidate/`:

```python
def _replace_config_files(self, temp_path: Path) -> None:
    for cfg_file in self.config_path.rglob("*.cfg"):
        try:
            cfg_file.relative_to(self.backup_path)
            continue
        except ValueError:
            pass
        cfg_file.unlink()
```

### Error message in `restore_backup()` (line ~308)

Contains reference to `DELETE /api/staging`:
```python
f"Recovery: DELETE /api/staging to clear lock, then POST /api/backups/<safety_backup>/restore"
```

## Changes

### Step 1: Update `_collect_config_files()` to exclude `.candidate/` and `.staging/`

After the backup directory skip block, add directory pruning:

```python
# Skip candidate and staging directories
dir_name = root_path.name
if dir_name in ('.candidate', '.staging', '.nagios_staging'):
    dirs[:] = []
    continue
```

### Step 2: Update `_replace_config_files()` to protect `.candidate/` and `.staging/`

Add skip logic for candidate/staging directories, matching the backup skip pattern:

```python
def _replace_config_files(self, temp_path: Path) -> None:
    for cfg_file in self.config_path.rglob("*.cfg"):
        try:
            cfg_file.relative_to(self.backup_path)
            continue  # Skip files in backups directory
        except ValueError:
            pass
        # Skip candidate and staging directories
        rel = cfg_file.relative_to(self.config_path)
        if any(part in ('.candidate', '.staging', '.nagios_staging') for part in rel.parts):
            continue
        cfg_file.unlink()
```

### Step 3: Update error message in `restore_backup()`

Change `DELETE /api/staging` to `DELETE /api/candidate`:

```python
f"Recovery: DELETE /api/candidate to clear session, then POST /api/backups/<safety_backup>/restore"
```

## Change Tracking

- [ ] Step 1: Update `_collect_config_files()` — add `.candidate`/`.staging`/`.nagios_staging` skip
- [ ] Step 2: Update `_replace_config_files()` — add `.candidate`/`.staging`/`.nagios_staging` skip
- [ ] Step 3: Update error message in `restore_backup()` — `DELETE /api/staging` → `DELETE /api/candidate`
- [ ] Verification: all existing backup tests pass
- [ ] Verification: ruff lint passes on `backup_manager.py`

## Removal Audit

No code is removed. All changes are additive (new skip conditions) or text updates (error message).

## Verification

```bash
# Unit tests
python3 -m pytest tests/test_backup_manager.py -v

# Linting
python3 -m ruff check backup_manager.py
python3 -m ruff format --check backup_manager.py
```

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This plan only modifies backup/restore behavior to exclude the candidate directory. No config mutation logic is changed.
- [x] **C2 — UI visual parity.** N/A — backend-only change, no UI impact.
- [x] **C3 — Full audit logging.** N/A — backup_manager already logs via app logging. No new operations are introduced that require additional audit entries.
- [x] **C4 — Proper error handling.** Existing error handling is preserved. The new skip conditions use safe relative_to checks and `any()` iteration — no new failure paths are introduced.
- [x] **C5 — Dead code deletion.** N/A — no dead code exists in this change; all additions are functional.
- [x] **C6 — Full functionality migration.** Backup and restore continue to work for all live config files. The candidate directory is correctly excluded from both collection and restore-time deletion.
- [x] **C7 — Palo Alto candidate model.** Aligns with candidate model by ensuring the `.candidate/` working directory is not swept into backups or destroyed during restore.
- [x] **C8 — Change tracking.** Change Tracking section with tickable checklist added above.
- [x] **C9 — Complete planning before implementation.** All three steps are fully specified with exact code snippets before any implementation.
- [x] **C10 — Linting enforcement.** Verification section includes `ruff check` and `ruff format --check` commands.
- [x] **C11 — Playwright validation.** N/A — backend-only change with no UI surface. Unit tests are sufficient.
