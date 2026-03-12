# Conflict Detection — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect when original `.cfg` files are modified externally between shadow creation and apply, warn the user, and allow force-apply to override.

**Architecture:** `create_shadow()` stores SHA-256 hashes of all original `.cfg` files in `checksums.json`. `apply()` rehashes originals before writing — if any differ, it returns a conflict error. The apply route returns 409 with the conflict list. Frontend shows a warning dialog; user can force-apply or cancel.

**Tech Stack:** Python `hashlib`, no new dependencies.

---

## Task 1: Write failing test for checksum storage

**Files:**
- Modify: `tests/test_shadow_copy_manager.py`

**Step 1: Write the failing test**

Add to the `TestShadowLifecycle` class:

```python
def test_create_shadow_stores_checksums(self, setup_dirs):
    """create_shadow should hash all .cfg files and write checksums.json."""
    config_dir, shadow_base = setup_dirs
    scm = ShadowCopyManager(config_dir, shadow_base)
    scm.create_shadow("s1", "user", "u@t.com")

    checksums_path = os.path.join(shadow_base, "checksums.json")
    assert os.path.isfile(checksums_path), "checksums.json not created"

    with open(checksums_path) as f:
        checksums = json.load(f)

    # Should have an entry for each .cfg file in config_dir
    cfg_files = []
    for root, _dirs, files in os.walk(config_dir):
        for fn in files:
            if fn.endswith(".cfg"):
                cfg_files.append(os.path.relpath(os.path.join(root, fn), config_dir))

    assert set(checksums.keys()) == set(cfg_files)
    # Each value should be a 64-char hex string (SHA-256)
    for path, digest in checksums.items():
        assert len(digest) == 64, f"Bad checksum for {path}: {digest}"
```

Add `import json` at the top of the test file if not already present.

**Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_shadow_copy_manager.py::TestShadowLifecycle::test_create_shadow_stores_checksums -v
```

Expected: FAIL — `checksums.json` does not exist.

---

## Task 2: Implement checksum storage in `create_shadow`

**Files:**
- Modify: `shadow_copy_manager.py:34-105`

**Step 1: Add a checksums file property**

After `_snapshots_dir` (line 52), add:

```python
@property
def _checksums_file(self) -> str:
    """Path to the original-file checksums."""
    return os.path.join(self.shadow_base_path, "checksums.json")
```

**Step 2: Add a static helper to hash files**

Add as a static method on `ShadowCopyManager`:

```python
@staticmethod
def _hash_cfg_files(directory: str) -> dict[str, str]:
    """Compute SHA-256 hashes of all .cfg files in directory.

    Returns:
        Dict mapping relative paths to hex digest strings
    """
    import hashlib
    checksums = {}
    for root, _dirs, files in os.walk(directory):
        for fn in files:
            if fn.endswith(".cfg"):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, directory)
                h = hashlib.sha256()
                with open(full, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                checksums[rel] = h.hexdigest()
    return checksums
```

**Step 3: Write checksums in `create_shadow`**

In `create_shadow`, after the `shutil.copytree` call (line 82) and before writing `lock.json` (line 85), add:

```python
# Hash original files for conflict detection at apply time
checksums = self._hash_cfg_files(self.config_path)
os.makedirs(self.shadow_base_path, exist_ok=True)
with open(self._checksums_file, "w", encoding="utf-8") as f:
    json.dump(checksums, f)
```

Move the existing `os.makedirs(self.shadow_base_path, exist_ok=True)` (line 91) before the checksums write so it only appears once.

**Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_shadow_copy_manager.py::TestShadowLifecycle::test_create_shadow_stores_checksums -v
```

Expected: PASS

**Step 5: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests pass.

**Step 6: Commit**

```bash
git add shadow_copy_manager.py tests/test_shadow_copy_manager.py
git commit -m "store SHA-256 checksums of original .cfg files at shadow creation"
```

---

## Task 3: Write failing test for conflict detection in `apply`

**Files:**
- Modify: `tests/test_shadow_copy_manager.py`

**Step 1: Write the failing test**

Add a new test class:

```python
class TestConflictDetection:
    def test_apply_detects_external_modification(self, setup_dirs):
        """apply() should fail when original files changed since shadow creation."""
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")

        # Modify a file in shadow (user's edit)
        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write("define host {\n    host_name edited\n}\n")

        # Simulate external modification to original
        with open(os.path.join(config_dir, "hosts.cfg"), "w") as f:
            f.write("define host {\n    host_name external-change\n}\n")

        result = scm.apply()
        assert not result.success
        assert result.error == "conflicts"
        assert "hosts.cfg" in result.data["conflicts"]

    def test_apply_succeeds_when_no_conflicts(self, setup_dirs):
        """apply() should succeed when originals are unchanged."""
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")

        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write("define host {\n    host_name edited\n}\n")

        result = scm.apply()
        assert result.success

    def test_apply_force_overrides_conflicts(self, setup_dirs):
        """apply(force=True) should overwrite despite conflicts."""
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")

        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write("define host {\n    host_name edited\n}\n")

        # External modification
        with open(os.path.join(config_dir, "hosts.cfg"), "w") as f:
            f.write("define host {\n    host_name external\n}\n")

        result = scm.apply(force=True)
        assert result.success
        with open(os.path.join(config_dir, "hosts.cfg")) as f:
            assert "edited" in f.read()

    def test_apply_detects_externally_deleted_file(self, setup_dirs):
        """apply() should detect when an original file was deleted externally."""
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")

        # External deletion
        os.remove(os.path.join(config_dir, "hosts.cfg"))

        result = scm.apply()
        assert not result.success
        assert result.error == "conflicts"
        assert "hosts.cfg" in result.data["conflicts"]

    def test_apply_skips_check_when_no_checksums_file(self, setup_dirs):
        """apply() should succeed without checksums.json (backward compat)."""
        config_dir, shadow_base = setup_dirs
        scm = ShadowCopyManager(config_dir, shadow_base)
        scm.create_shadow("s1", "user", "u@t.com")

        # Remove checksums.json to simulate old shadow
        checksums_path = os.path.join(shadow_base, "checksums.json")
        if os.path.exists(checksums_path):
            os.remove(checksums_path)

        with open(scm.shadow_path("hosts.cfg"), "w") as f:
            f.write("modified\n")

        # Externally modify original — should NOT be detected
        with open(os.path.join(config_dir, "hosts.cfg"), "w") as f:
            f.write("external\n")

        result = scm.apply()
        assert result.success
```

**Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_shadow_copy_manager.py::TestConflictDetection -v
```

Expected: `test_apply_detects_external_modification` and `test_apply_detects_externally_deleted_file` FAIL (apply succeeds when it shouldn't). Others may pass or fail depending on signature.

---

## Task 4: Implement conflict detection in `apply`

**Files:**
- Modify: `shadow_copy_manager.py:494-572`

**Step 1: Add a conflict detection method**

Add to `ShadowCopyManager`:

```python
def _detect_conflicts(self) -> list[str]:
    """Compare current originals against stored checksums.

    Returns:
        List of relative paths that have changed externally.
        Empty list if checksums.json doesn't exist (backward compat).
    """
    if not os.path.isfile(self._checksums_file):
        return []

    with open(self._checksums_file, encoding="utf-8") as f:
        stored = json.load(f)

    current = self._hash_cfg_files(self.config_path)
    conflicts = []
    for rel_path, original_hash in stored.items():
        current_hash = current.get(rel_path)
        if current_hash is None:
            # File was deleted externally
            conflicts.append(rel_path)
        elif current_hash != original_hash:
            conflicts.append(rel_path)
    return conflicts
```

**Step 2: Update `apply` method signature and add conflict check**

Change the `apply` method signature to:

```python
def apply(self, backup_manager=None, force: bool = False) -> OperationResult:
```

Inside `apply`, after the `has_shadow()` check (line 508-510) and before `changed = self.get_changed_files()` (line 513), add:

```python
# Check for external modifications unless force-applying
if not force:
    conflicts = self._detect_conflicts()
    if conflicts:
        return OperationResult(
            success=False,
            error="conflicts",
            data={"conflicts": conflicts},
        )
```

**Step 3: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_shadow_copy_manager.py::TestConflictDetection -v
```

Expected: All 5 tests PASS.

**Step 4: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add shadow_copy_manager.py tests/test_shadow_copy_manager.py
git commit -m "detect external file conflicts before apply, support force override"
```

---

## Task 5: Update apply route to return 409 and accept force param

**Files:**
- Modify: `routes/staging.py:157-196`

**Step 1: Write the failing test**

Add to `tests/test_shadow_copy_manager.py` or a route test file if one exists for staging:

This is tested via the `ShadowCopyManager` unit tests already. The route change is a thin adapter — pass `force` from query param, return 409 on conflicts.

**Step 2: Update the route**

In `routes/staging.py`, modify `api_apply_staging`:

```python
@bp.route("/api/staging/apply", methods=["POST"])
def api_apply_staging():
    """Apply all staged changes to disk."""
    sm = get_shadow_manager()
    bm = get_backup_manager()
    force = request.args.get("force", "").lower() == "true"

    # Get lock info for audit before apply destroys it
    lock_status = sm.get_lock_status() if sm.has_shadow() else {}
    user_name = lock_status.get("user_name", "")
    user_email = lock_status.get("user_email", "")

    result = sm.apply(backup_manager=bm, force=force)

    if not result.success:
        if result.error == "conflicts":
            return jsonify({
                "success": False,
                "error": "conflicts",
                "conflicts": result.data["conflicts"],
            }), 409
        return jsonify({"success": False, "error": result.error}), 500

    # Reload service to pick up applied changes (now on original config)
    service = get_service()
    service.config_path = sm.config_path
    service.reload()

    # Audit log
    changed = result.data.get("changed_files", []) if result.data else []
    if changed:
        txn = uuid.uuid4().hex[:8]
        user = format_audit_user(name=user_name, email=user_email)
        log_audit(
            action="apply",
            user=user,
            txn=txn,
            files_changed=len(changed),
        )

    # Post-apply validation
    validation = _run_post_apply_validation()

    return jsonify({
        "success": True,
        "data": result.data,
        "validation": validation,
    })
```

**Step 3: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests pass.

**Step 4: Commit**

```bash
git add routes/staging.py
git commit -m "return 409 with conflict list from apply route, accept force param"
```

---

## Task 6: Update frontend to handle conflicts and show force dialog

**Files:**
- Modify: `static/js/commit-dialog.js:158-166`
- Modify: `static/js/explorer/data-loading.js:234-248`

**Step 1: Update `applyShadowChanges` in commit-dialog.js**

Replace the `applyShadowChanges` function:

```javascript
async function applyShadowChanges(force = false) {
    showGitRunningPanel('Applying Changes', 'Applying shadow copy to original config...');
    const url = force ? '/api/staging/apply?force=true' : '/api/staging/apply';
    const applyResult = await ApiClient.post(url, {}, { silent: true });

    if (!applyResult.success) {
        // Check for conflict response (409)
        if (applyResult.data?.conflicts) {
            const conflicts = applyResult.data.conflicts;
            const fileList = conflicts.map(f => `  • ${f}`).join('\n');
            const msg = `${conflicts.length} file(s) were modified externally since you started editing:\n\n${fileList}\n\nForce apply will overwrite these changes. A backup is created first.`;
            if (confirm(msg)) {
                return applyShadowChanges(true);
            }
            showStagingResultPanel(false, 'Apply cancelled due to conflicts');
            return null;
        }
        showStagingResultPanel(false, applyResult.error || 'Failed to apply staged changes');
        return null;
    }
    return applyResult.data || {};
}
```

**Step 2: Update `applyAllStaged` in data-loading.js**

Replace the `applyAllStaged` function:

```javascript
export async function applyAllStaged(force = false) {
    const url = force ? '/api/staging/apply?force=true' : '/api/staging/apply';
    const result = await ApiClient.post(url, {}, { silent: true });

    if (result.success && result.data?.success) {
        await loadObjects();
        afterServerSync();
        showToast('Changes applied successfully', 'success');
        return { success: true, results: result.data };
    }

    // Check for conflict response (409)
    if (result.data?.conflicts) {
        const conflicts = result.data.conflicts;
        const fileList = conflicts.map(f => `  • ${f}`).join('\n');
        const msg = `${conflicts.length} file(s) were modified externally:\n\n${fileList}\n\nForce apply will overwrite. A backup is created first.`;
        if (confirm(msg)) {
            return applyAllStaged(true);
        }
        showToast('Apply cancelled due to conflicts', 'warning');
        return { success: false, message: 'Conflicts detected' };
    }

    const errorMsg = result.data?.error || result.error || 'Failed to apply changes';
    showToast(errorMsg, 'error');
    return { success: false, message: errorMsg };
}
```

**Step 3: Verify callers of both functions**

Search for all call sites of `applyShadowChanges` and `applyAllStaged` to ensure they don't pass arguments that conflict with the new `force` parameter. Both previously took no arguments, so existing callers are unaffected.

**Step 4: Commit**

```bash
git add static/js/commit-dialog.js static/js/explorer/data-loading.js
git commit -m "show conflict warning dialog with force-apply option in frontend"
```

---

## Task 7: Browser verification

**No code changes.** Manual test in the browser.

1. Start the app: `python3 app.py`
2. Make an edit to any object (triggers shadow creation)
3. Externally modify the original file (e.g., edit `sample-config/objects/hosts.cfg` directly)
4. Click Commit → Apply — verify the conflict dialog appears listing the modified file
5. Click Cancel — verify apply is aborted
6. Click Commit → Apply again, this time click Force Apply — verify it succeeds
7. Verify the force-applied content overwrites the external change
