# Auto Git Init on Config Path Change

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically initialize a git repository in the config directory when the user saves new config paths in settings, so changes are tracked from the start.

**Architecture:** After `_rediscover_and_reinit()` succeeds in the settings POST handler, check if the new primary directory has a `.git` directory. If not, call `GitService.init_repo()`. Return a `git_initialized` flag in the response. Frontend shows a toast.

**Tech Stack:** Python (Flask), JavaScript, pytest

---

### Task 1: Auto-init git in settings save with test

**Files:**
- Modify: `app/routes/settings.py:88-96`
- Modify: `app/static/js/settings.js:378-392`
- Create: `tests/test_settings_git_init.py`

**Step 1: Write the failing test**

```python
"""Tests for auto git init on config path change."""

import shutil
import tempfile
from pathlib import Path

from app import create_app


def test_settings_save_initializes_git_when_missing():
    """Saving config paths should auto-init git if no repo exists."""
    test_dir = tempfile.mkdtemp()
    try:
        config_path = Path(test_dir) / "nagios"
        config_path.mkdir()

        (config_path / "hosts.cfg").write_text("""
define host {
    host_name   test-host
    alias       Test
    address     10.0.0.1
}
""")

        app = create_app(config_path=str(config_path))
        app.config["TESTING"] = True
        client = app.test_client()

        # Verify no git repo exists
        assert not (config_path / ".git").exists()

        # Save settings with the same config path to trigger rediscovery
        resp = client.post("/api/settings", json={
            "paths": {"extra_cfg_dirs": [str(config_path)]}
        })
        data = resp.get_json()

        assert data["success"] is True
        assert data.get("git_initialized") is True
        assert (config_path / ".git").exists()
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_settings_save_skips_git_init_when_repo_exists():
    """Should not re-init git if repo already exists."""
    test_dir = tempfile.mkdtemp()
    try:
        config_path = Path(test_dir) / "nagios"
        config_path.mkdir()

        (config_path / "hosts.cfg").write_text("""
define host {
    host_name   test-host
    alias       Test
    address     10.0.0.1
}
""")

        app = create_app(config_path=str(config_path))
        app.config["TESTING"] = True
        client = app.test_client()

        # Pre-create a git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=str(config_path), capture_output=True)
        assert (config_path / ".git").exists()

        resp = client.post("/api/settings", json={
            "paths": {"extra_cfg_dirs": [str(config_path)]}
        })
        data = resp.get_json()

        assert data["success"] is True
        assert data.get("git_initialized") is not True
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_settings_git_init.py -v`
Expected: FAIL — `git_initialized` not in response

**Step 3: Add git auto-init to settings save**

In `app/routes/settings.py`, after the `_rediscover_and_reinit` call and before the config save, add git init logic. Modify lines 88-99:

```python
    # Re-run discovery and reinitialize services if nagios_cfg or extra_dirs changed
    git_initialized = False
    if needs_rediscovery and not errors:
        _rediscover_and_reinit(server_config, errors)
        # Auto-init git repo in config directory if none exists
        if not errors:
            git_svc = current_app.extensions.get("git")
            if git_svc:
                git_dir = os.path.join(git_svc._config_path, ".git")
                if not os.path.isdir(git_dir):
                    init_result = git_svc.init_repo()
                    if init_result.success:
                        git_initialized = True
                    else:
                        logger.warning("Auto git init failed: %s", init_result.error)

    if updated and not errors:
        try:
            save_server_config(server_config)
        except (OSError, ValueError) as e:
            errors.append(f"Failed to save config: {e}")
```

Add `git_initialized` to the response dict (inside the `return jsonify({...})` block, after `"errors"`):

```python
        "git_initialized": git_initialized,
```

Also add `import logging` and `logger = logging.getLogger(...)` if not already present. Check the existing imports at the top of the file.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_settings_git_init.py -v`
Expected: PASS

**Step 5: Update frontend toast**

In `app/static/js/settings.js`, in the `saveServerSettings()` success handler (line 378-388), add after the existing toast:

```javascript
    if (result.success && result.data.success) {
        const savedItems = [];
        if (result.data.updated && result.data.updated.length > 0) {
            savedItems.push(...result.data.updated);
        }
        if (savedItems.length > 0) {
            showToast('Server settings saved: ' + savedItems.join(', '), 'success');
        } else {
            showToast('Server settings unchanged', 'info');
        }
        if (result.data.git_initialized) {
            showToast('Git repository initialized in config directory', 'success');
        }
        refreshStatus();
```

**Step 6: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add app/routes/settings.py app/static/js/settings.js tests/test_settings_git_init.py
git commit -m "feat: auto-init git repository when config paths are saved"
```
