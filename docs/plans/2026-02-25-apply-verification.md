# Apply Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a post-apply verification step that uses git diff and parser re-inspection to confirm the changes written to disk match exactly what staging intended — and surface the results to the user in the git commit result panel.

**Architecture:** After all apply phases succeed and the parser reloads, a new `verify_apply_integrity()` function compares (1) git-reported file changes against an expected changeset built from staging data, and (2) re-parsed object state against each staging operation's intent. The verification report is included in the apply response under a `verification` key. The frontend propagates this through the commit flow and renders a verification summary section in the existing git result panel. On verification failure, the panel title downgrades to "Committed with Warnings". Non-fatal — verification failures produce warnings, not rollbacks.

**Tech Stack:** Python (`apply_verification.py`), Flask (`routes/staging.py`), existing `git_service.py`, existing `commit-dialog.js` / `git-ui.js`

**Single apply path:** The only apply path is the commit dialog (`applyGuiStagingChanges` in `commit-dialog.js`), which calls `/api/staging/apply` with `deferClear: true`, then proceeds to git commit. The `Explorer.applyAllStaged` function in `data-loading.js` is dead code — never called.

**Existing CSS classes used (no new CSS needed):**
- `.success-text` → `color: var(--nbe-terminal-success)` (green, `#0c0`)
- `.error-text` → `color: var(--nbe-terminal-error)` (red, `#e44`)
- `.info-text` → `color: var(--nbe-terminal-prompt)` (green, `#0a0`)
- `--nbe-dark-validation-warning-text` → `#ffb74d` (amber) — exists in `tokens.css` but has no `.warning-text` class inside `.git-result-output`; Task 7 adds one rule to the existing inline `<style>` block in `base.html`

---

### Task 1: Build Expected Changeset from Staging Data

**Files:**
- Create: `tests/test_apply_verification.py`
- Create: `apply_verification.py`

This module extracts the set of files that *should* change from the staging data dict, categorized by change type. This is pure logic — no git, no flask, no I/O.

**Step 1: Write the failing test**

```python
"""Tests for apply verification module."""

import os

from apply_verification import build_expected_changeset


def test_empty_staging_returns_empty_changeset():
    changeset = build_expected_changeset({})
    assert changeset == {"modified": set(), "created": set(), "deleted": set()}


def test_pending_edits_expect_modified_files():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {
                    "source_file": "/etc/nagios/hosts.cfg",
                    "object_type": "host",
                    "name": "web01",
                },
                "edited": {"alias": "New Alias"},
            },
        },
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]


def test_staged_creations_expect_modified_or_created():
    staging = {
        "stagedCreations": [
            {"object_type": "host", "targetFile": "/etc/nagios/hosts.cfg",
             "attributes": {"host_name": "new"}},
        ],
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]


def test_staged_deletions_use_object_lookup():
    """Deletions need parser objects to know which files are affected.
    Without parser_objects, deletions are skipped gracefully."""
    staging = {"stagedObjectDeletions": [0, 3]}
    changeset = build_expected_changeset(staging)
    # No parser_objects provided, so no files expected
    assert changeset["modified"] == set()


def test_staged_deletions_with_parser_objects():
    parser_objects = [
        {"source_file": "/etc/nagios/hosts.cfg", "object_type": "host"},
        {"source_file": "/etc/nagios/services.cfg", "object_type": "service"},
        {"source_file": "/etc/nagios/hosts.cfg", "object_type": "host"},
        {"source_file": "/etc/nagios/commands.cfg", "object_type": "command"},
    ]
    staging = {"stagedObjectDeletions": [0, 3]}
    changeset = build_expected_changeset(staging, parser_objects=parser_objects)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]
    assert "/etc/nagios/commands.cfg" in changeset["modified"]


def test_staged_moves_expect_both_files():
    staging = {
        "stagedMoves": {
            "key1": {
                "object": {"source_file": "/etc/nagios/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "targetFile": "/etc/nagios/hosts-prod.cfg",
            },
        },
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]
    assert "/etc/nagios/hosts-prod.cfg" in changeset["modified"]


def test_file_creations():
    staging = {"stagedFileCreations": [{"path": "/etc/nagios/new.cfg"}]}
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/new.cfg" in changeset["created"]


def test_file_deletions():
    staging = {"stagedFileDeletions": [{"path": "/etc/nagios/old.cfg"}]}
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/old.cfg" in changeset["deleted"]


def test_file_moves_expect_delete_source_create_target():
    staging = {
        "stagedFileMoves": [
            {"sourcePath": "/etc/nagios/old.cfg", "targetPath": "/etc/nagios/new.cfg"},
        ],
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/old.cfg" in changeset["deleted"]
    assert "/etc/nagios/new.cfg" in changeset["created"]


def test_combined_operations():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/etc/nagios/hosts.cfg",
                           "object_type": "host", "name": "w1"},
                "edited": {"alias": "x"},
            },
        },
        "stagedFileCreations": [{"path": "/etc/nagios/new.cfg"}],
        "stagedFileDeletions": [{"path": "/etc/nagios/old.cfg"}],
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]
    assert "/etc/nagios/new.cfg" in changeset["created"]
    assert "/etc/nagios/old.cfg" in changeset["deleted"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_apply_verification.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apply_verification'`

**Step 3: Write minimal implementation**

Create `apply_verification.py` in the project root (alongside `nagios_service.py`):

```python
"""Post-apply verification — confirms disk changes match staging intent.

Two-layer verification:
1. File-level: git status changes vs expected changeset from staging data
2. Object-level: re-parsed objects vs each staging operation's intent
"""

import logging

logger = logging.getLogger("nagios_bulk_editor.verification")


def build_expected_changeset(staging_data, parser_objects=None):
    """Build set of files expected to change from staging operations.

    Args:
        staging_data: Staging data dict (pendingEdits, stagedCreations, etc.)
        parser_objects: Optional list of parser object dicts (needed for
            deletion indices). Each must have 'source_file' key.

    Returns:
        Dict with keys 'modified', 'created', 'deleted' — each a set of
        absolute file paths.

    """
    modified = set()
    created = set()
    deleted = set()

    # Object edits → modified files
    for entry in staging_data.get("pendingEdits", {}).values():
        if isinstance(entry, dict):
            obj = entry.get("object", {})
            source = obj.get("source_file")
            if source:
                modified.add(source)

    # Object creations → modified files (appended to existing file)
    for creation in staging_data.get("stagedCreations", []):
        target = creation.get("targetFile")
        if target:
            modified.add(target)

    # Object deletions → need parser objects to resolve indices to files
    if parser_objects:
        for idx in staging_data.get("stagedObjectDeletions", []):
            if isinstance(idx, int) and 0 <= idx < len(parser_objects):
                source = parser_objects[idx].get("source_file")
                if source:
                    modified.add(source)

    # Object moves → both source and target modified
    for move in staging_data.get("stagedMoves", {}).values():
        if isinstance(move, dict):
            obj = move.get("object", {})
            source = obj.get("source_file")
            target = move.get("targetFile")
            if source:
                modified.add(source)
            if target:
                modified.add(target)

    # File creations
    for entry in staging_data.get("stagedFileCreations", []):
        path = entry.get("path")
        if path:
            created.add(path)

    # File deletions
    for entry in staging_data.get("stagedFileDeletions", []):
        path = entry.get("path")
        if path:
            deleted.add(path)

    # File moves → source deleted, target created
    for entry in staging_data.get("stagedFileMoves", []):
        source = entry.get("sourcePath")
        target = entry.get("targetPath")
        if source:
            deleted.add(source)
        if target:
            created.add(target)

    return {"modified": modified, "created": created, "deleted": deleted}
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_apply_verification.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add apply_verification.py tests/test_apply_verification.py
git commit -m "feat(verification): build expected changeset from staging data"
```

---

### Task 2: Compare Git Status Against Expected Changeset

**Files:**
- Modify: `tests/test_apply_verification.py`
- Modify: `apply_verification.py`

Add `compare_file_changes()` which takes pre-apply and post-apply git status lists, plus the expected changeset, and returns a file-level verification report. Pure logic — no git calls.

**Step 1: Write the failing tests**

Append to `tests/test_apply_verification.py`:

```python
from apply_verification import compare_file_changes


def test_perfect_match():
    """All expected changes present, no unexpected changes."""
    expected = {"modified": {"/cfg/hosts.cfg"}, "created": set(), "deleted": set()}
    # pre-apply: clean tree. post-apply: hosts.cfg modified.
    pre_files = []
    post_files = [{"path": "hosts.cfg", "status_code": " M"}]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is True
    assert report["unexpected"] == []
    assert report["missing"] == []


def test_unexpected_file_changed():
    """A file changed on disk that staging didn't intend to touch."""
    expected = {"modified": {"/cfg/hosts.cfg"}, "created": set(), "deleted": set()}
    pre_files = []
    post_files = [
        {"path": "hosts.cfg", "status_code": " M"},
        {"path": "services.cfg", "status_code": " M"},
    ]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is False
    assert any("services.cfg" in u for u in report["unexpected"])


def test_missing_expected_change():
    """Staging expected to modify a file but git shows no diff."""
    expected = {"modified": {"/cfg/hosts.cfg"}, "created": set(), "deleted": set()}
    pre_files = []
    post_files = []
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is False
    assert any("hosts.cfg" in m for m in report["missing"])


def test_pre_existing_changes_excluded():
    """Files already dirty before apply are not flagged as unexpected."""
    expected = {"modified": {"/cfg/hosts.cfg"}, "created": set(), "deleted": set()}
    pre_files = [{"path": "unrelated.cfg", "status_code": " M"}]
    post_files = [
        {"path": "hosts.cfg", "status_code": " M"},
        {"path": "unrelated.cfg", "status_code": " M"},
    ]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is True
    assert report["unexpected"] == []


def test_file_creation_detected():
    expected = {"modified": set(), "created": {"/cfg/new.cfg"}, "deleted": set()}
    pre_files = []
    post_files = [{"path": "new.cfg", "status_code": "??"}]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is True


def test_file_deletion_detected():
    expected = {"modified": set(), "created": set(), "deleted": {"/cfg/old.cfg"}}
    pre_files = []
    post_files = [{"path": "old.cfg", "status_code": " D"}]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is True
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_apply_verification.py::test_perfect_match -v`
Expected: FAIL — `ImportError: cannot import name 'compare_file_changes'`

**Step 3: Write minimal implementation**

Add to `apply_verification.py`:

```python
def compare_file_changes(expected, pre_files, post_files, config_path):
    """Compare git-reported file changes against expected changeset.

    Args:
        expected: Dict from build_expected_changeset() with 'modified',
            'created', 'deleted' sets of absolute paths.
        pre_files: List of git status file dicts BEFORE apply.
            Each: {"path": "relative/path.cfg", "status_code": "XY"}
        post_files: List of git status file dicts AFTER apply.
            Same format as pre_files.
        config_path: Absolute path to config directory (for resolving
            relative git paths to absolute).

    Returns:
        Dict with 'passed' (bool), 'unexpected' (list of str descriptions),
        'missing' (list of str descriptions), 'expectedFiles' (list),
        'actualFiles' (list).

    """
    import os

    # Build sets of relative paths that were dirty before apply (pre-existing noise)
    pre_dirty = {f["path"] for f in pre_files}

    # Build set of files that actually changed (new in post, not in pre)
    post_paths = {f["path"] for f in post_files}
    newly_changed = post_paths - pre_dirty

    # Convert expected absolute paths to relative (for git comparison)
    def to_relative(abs_path):
        if abs_path.startswith(config_path):
            rel = os.path.relpath(abs_path, config_path)
            return rel
        return abs_path

    expected_relative = set()
    for path in expected["modified"] | expected["created"] | expected["deleted"]:
        expected_relative.add(to_relative(path))

    # Find unexpected: changed on disk but not in expected set
    unexpected = []
    for path in sorted(newly_changed - expected_relative):
        unexpected.append(f"Unexpected change: {path}")

    # Find missing: expected to change but didn't show up in git diff
    missing = []
    for path in sorted(expected_relative - newly_changed):
        missing.append(f"Expected change not found: {path}")

    passed = len(unexpected) == 0 and len(missing) == 0

    return {
        "passed": passed,
        "unexpected": unexpected,
        "missing": missing,
        "expectedFiles": sorted(expected_relative),
        "actualFiles": sorted(newly_changed),
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_apply_verification.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add apply_verification.py tests/test_apply_verification.py
git commit -m "feat(verification): compare git status against expected changeset"
```

---

### Task 3: Object-Level Verification via Re-Parsed State

**Files:**
- Modify: `tests/test_apply_verification.py`
- Modify: `apply_verification.py`

Add `verify_objects()` which checks re-parsed objects against staging intent: edits applied, creations exist, deletions gone, moves relocated.

**Step 1: Write the failing tests**

Append to `tests/test_apply_verification.py`:

```python
from apply_verification import verify_objects
from nagios_model import NAME_FIELDS


def test_verify_edits_pass():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "edited": {"alias": "New Alias"},
            },
        },
    }
    # After apply, parser has the object with the new alias
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "web01", "alias": "New Alias", "address": "1.2.3.4"}},
    ]
    report = verify_objects(staging, parsed)
    assert report["passed"] is True
    assert report["editsVerified"] == 1


def test_verify_edits_fail_wrong_value():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "edited": {"alias": "New Alias"},
            },
        },
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "web01", "alias": "Old Alias"}},
    ]
    report = verify_objects(staging, parsed)
    assert report["passed"] is False
    assert report["editsFailed"] == 1
    assert len(report["failures"]) == 1


def test_verify_creation_exists():
    staging = {
        "stagedCreations": [
            {"object_type": "host", "targetFile": "/cfg/hosts.cfg",
             "attributes": {"host_name": "newhost", "alias": "New"}},
        ],
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "newhost", "alias": "New"}},
    ]
    report = verify_objects(staging, parsed)
    assert report["passed"] is True
    assert report["creationsVerified"] == 1


def test_verify_creation_missing():
    staging = {
        "stagedCreations": [
            {"object_type": "host", "targetFile": "/cfg/hosts.cfg",
             "attributes": {"host_name": "newhost"}},
        ],
    }
    parsed = []
    report = verify_objects(staging, parsed)
    assert report["passed"] is False
    assert report["creationsFailed"] == 1


def test_verify_deletion_gone():
    staging = {
        "stagedObjectDeletions": [0],
    }
    pre_objects = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "oldhost"}},
    ]
    parsed = []
    report = verify_objects(staging, parsed, pre_objects=pre_objects)
    assert report["passed"] is True
    assert report["deletionsVerified"] == 1


def test_verify_deletion_still_present():
    staging = {
        "stagedObjectDeletions": [0],
    }
    pre_objects = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "oldhost"}},
    ]
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "oldhost"}},
    ]
    report = verify_objects(staging, parsed, pre_objects=pre_objects)
    assert report["passed"] is False
    assert report["deletionsFailed"] == 1


def test_verify_move_relocated():
    staging = {
        "stagedMoves": {
            "key1": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "targetFile": "/cfg/hosts-prod.cfg",
            },
        },
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts-prod.cfg",
         "attributes": {"host_name": "web01"}},
    ]
    report = verify_objects(staging, parsed)
    assert report["passed"] is True
    assert report["movesVerified"] == 1
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_apply_verification.py::test_verify_edits_pass -v`
Expected: FAIL — `ImportError: cannot import name 'verify_objects'`

**Step 3: Write minimal implementation**

Add to `apply_verification.py`:

```python
from nagios_model import NAME_FIELDS


def _find_object(parsed_objects, obj_type, name, source_file=None):
    """Find an object in parsed list by type, name, and optionally file.

    Args:
        parsed_objects: List of parsed object dicts.
        obj_type: Object type string.
        name: Object name.
        source_file: Optional file path constraint.

    Returns:
        Matching object dict, or None.

    """
    name_field = NAME_FIELDS.get(obj_type)
    for obj in parsed_objects:
        if obj.get("object_type") != obj_type:
            continue
        if source_file and obj.get("source_file") != source_file:
            continue
        obj_name = obj.get("attributes", {}).get(name_field, "") if name_field else ""
        if obj_name == name:
            return obj
    return None


def verify_objects(staging_data, parsed_objects, pre_objects=None):
    """Verify re-parsed objects match staging intent.

    Args:
        staging_data: Staging data dict.
        parsed_objects: List of object dicts from re-parsed config
            (each with 'object_type', 'source_file', 'attributes').
        pre_objects: Optional list of object dicts from BEFORE apply
            (needed for deletion verification to know what was deleted).

    Returns:
        Dict with 'passed', counts per operation, and 'failures' list.

    """
    edits_verified = 0
    edits_failed = 0
    creations_verified = 0
    creations_failed = 0
    deletions_verified = 0
    deletions_failed = 0
    moves_verified = 0
    moves_failed = 0
    failures = []

    # Verify edits
    for entry in staging_data.get("pendingEdits", {}).values():
        if not isinstance(entry, dict):
            continue
        obj_meta = entry.get("object", {})
        edited = entry.get("edited", {})
        if not edited:
            continue

        obj_type = obj_meta.get("object_type")
        obj_name = obj_meta.get("name")

        # If the name field itself was edited, look for the new name
        name_field = NAME_FIELDS.get(obj_type, "")
        lookup_name = edited.get(name_field, obj_name)

        found = _find_object(parsed_objects, obj_type, lookup_name)
        if not found:
            edits_failed += 1
            failures.append(f"Edit: {obj_type} '{obj_name}' not found after apply")
            continue

        # Check each edited attribute
        all_match = True
        for key, expected_val in edited.items():
            actual_val = found.get("attributes", {}).get(key)
            if actual_val != expected_val:
                all_match = False
                failures.append(
                    f"Edit: {obj_type} '{lookup_name}' field '{key}': "
                    f"expected '{expected_val}', got '{actual_val}'"
                )

        if all_match:
            edits_verified += 1
        else:
            edits_failed += 1

    # Verify creations
    for creation in staging_data.get("stagedCreations", []):
        obj_type = creation.get("object_type")
        attrs = creation.get("attributes", {})
        target_file = creation.get("targetFile")
        name_field = NAME_FIELDS.get(obj_type)
        obj_name = attrs.get(name_field, "") if name_field else ""

        found = _find_object(parsed_objects, obj_type, obj_name, source_file=target_file)
        if found:
            creations_verified += 1
        else:
            creations_failed += 1
            failures.append(f"Creation: {obj_type} '{obj_name}' not found in {target_file}")

    # Verify deletions (need pre_objects to know what was deleted)
    if pre_objects:
        for idx in staging_data.get("stagedObjectDeletions", []):
            if not isinstance(idx, int) or idx < 0 or idx >= len(pre_objects):
                continue
            old_obj = pre_objects[idx]
            obj_type = old_obj.get("object_type")
            source_file = old_obj.get("source_file")
            name_field = NAME_FIELDS.get(obj_type)
            obj_name = old_obj.get("attributes", {}).get(name_field, "") if name_field else ""

            still_exists = _find_object(parsed_objects, obj_type, obj_name,
                                        source_file=source_file)
            if still_exists:
                deletions_failed += 1
                failures.append(f"Deletion: {obj_type} '{obj_name}' still exists in {source_file}")
            else:
                deletions_verified += 1

    # Verify moves
    for move in staging_data.get("stagedMoves", {}).values():
        if not isinstance(move, dict):
            continue
        obj_meta = move.get("object", {})
        target_file = move.get("targetFile")
        obj_type = obj_meta.get("object_type")
        obj_name = obj_meta.get("name")

        found = _find_object(parsed_objects, obj_type, obj_name, source_file=target_file)
        if found:
            moves_verified += 1
        else:
            moves_failed += 1
            failures.append(f"Move: {obj_type} '{obj_name}' not found in {target_file}")

    passed = (edits_failed == 0 and creations_failed == 0
              and deletions_failed == 0 and moves_failed == 0)

    return {
        "passed": passed,
        "editsVerified": edits_verified,
        "editsFailed": edits_failed,
        "creationsVerified": creations_verified,
        "creationsFailed": creations_failed,
        "deletionsVerified": deletions_verified,
        "deletionsFailed": deletions_failed,
        "movesVerified": moves_verified,
        "movesFailed": moves_failed,
        "failures": failures,
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_apply_verification.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add apply_verification.py tests/test_apply_verification.py
git commit -m "feat(verification): object-level verification via re-parsed state"
```

---

### Task 4: Orchestrator Function

**Files:**
- Modify: `apply_verification.py`
- Modify: `tests/test_apply_verification.py`

Add `verify_apply_integrity()` — the top-level orchestrator that calls `build_expected_changeset`, `compare_file_changes`, and `verify_objects`, returning the combined report. Pure logic — no git calls (receives pre/post file lists as arguments).

**Step 1: Write the failing test**

Append to `tests/test_apply_verification.py`:

```python
from apply_verification import verify_apply_integrity


def test_orchestrator_full_pass():
    """Full verification passes when git and objects both match."""
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "edited": {"alias": "New"},
            },
        },
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "web01", "alias": "New"}},
    ]

    pre_files = []
    post_files = [{"path": "hosts.cfg", "status_code": " M"}]

    report = verify_apply_integrity(
        staging_data=staging,
        parsed_objects=parsed,
        pre_git_files=pre_files,
        post_git_files=post_files,
        config_path="/cfg",
    )
    assert report["passed"] is True
    assert report["fileLevel"]["passed"] is True
    assert report["objectLevel"]["passed"] is True


def test_orchestrator_file_mismatch():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "edited": {"alias": "New"},
            },
        },
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "web01", "alias": "New"}},
    ]

    pre_files = []
    # Unexpected extra file changed
    post_files = [
        {"path": "hosts.cfg", "status_code": " M"},
        {"path": "rogue.cfg", "status_code": " M"},
    ]

    report = verify_apply_integrity(
        staging_data=staging,
        parsed_objects=parsed,
        pre_git_files=pre_files,
        post_git_files=post_files,
        config_path="/cfg",
    )
    assert report["passed"] is False
    assert report["fileLevel"]["passed"] is False
    assert report["objectLevel"]["passed"] is True


def test_orchestrator_no_git_graceful():
    """When git data is not provided, file-level is skipped, object-level still runs."""
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "edited": {"alias": "New"},
            },
        },
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "web01", "alias": "New"}},
    ]

    report = verify_apply_integrity(
        staging_data=staging,
        parsed_objects=parsed,
        pre_git_files=None,
        post_git_files=None,
        config_path="/cfg",
    )
    assert report["passed"] is True
    assert report["fileLevel"] is None
    assert report["objectLevel"]["passed"] is True
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_apply_verification.py::test_orchestrator_full_pass -v`
Expected: FAIL — `ImportError: cannot import name 'verify_apply_integrity'`

**Step 3: Write minimal implementation**

Add to `apply_verification.py`:

```python
def verify_apply_integrity(staging_data, parsed_objects, pre_git_files=None,
                           post_git_files=None, config_path=None,
                           pre_parser_objects=None):
    """Top-level verification: compare apply results against staging intent.

    Args:
        staging_data: Staging data dict.
        parsed_objects: List of re-parsed object dicts (post-apply).
        pre_git_files: List of git status file dicts before apply, or None
            if git is unavailable. Each: {"path": str, "status_code": str}
        post_git_files: List of git status file dicts after apply, or None.
        config_path: Absolute path to config directory.
        pre_parser_objects: Optional list of object dicts from before apply
            (for deletion verification).

    Returns:
        Dict with 'passed' (bool), 'fileLevel' (dict or None),
        'objectLevel' (dict).

    """
    # File-level verification (git-based)
    file_report = None
    if pre_git_files is not None and post_git_files is not None and config_path:
        expected = build_expected_changeset(staging_data,
                                           parser_objects=pre_parser_objects)
        file_report = compare_file_changes(expected, pre_git_files,
                                           post_git_files, config_path)

    # Object-level verification (parser-based)
    object_report = verify_objects(staging_data, parsed_objects,
                                  pre_objects=pre_parser_objects)

    file_passed = file_report["passed"] if file_report else True
    passed = file_passed and object_report["passed"]

    return {
        "passed": passed,
        "fileLevel": file_report,
        "objectLevel": object_report,
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_apply_verification.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add apply_verification.py tests/test_apply_verification.py
git commit -m "feat(verification): orchestrator combining file and object verification"
```

---

### Task 5: Hook Into Apply Flow

**Files:**
- Modify: `routes/staging.py:1309-1341` (the `api_apply_staging` function)

Wire the verification into the existing apply endpoint. Capture pre-apply git status and parser objects, call `verify_apply_integrity` after reload, include result in response.

**Important context:** The commit dialog calls apply with `deferClear: true`, meaning staging data is still intact during verification. Verification runs after `service.reload()` and reference updates, but before `sm.clear_staging()`.

**Step 1: Write the failing integration test**

Append to `tests/test_staging_integration.py`:

```python
def test_apply_includes_verification(client, app):
    """Apply response includes verification report."""
    resp = client.get("/api/objects")
    objects = resp.json
    obj = objects[0]

    edit_data = {
        "sessionId": "test-session",
        "pendingEdits": {
            str(obj["global_index"]): {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Verified Alias"},
            },
        },
    }

    client.post("/api/staging",
                data=json.dumps(edit_data),
                content_type="application/json",
                headers={"X-Session-Id": "test-session"})

    resp = client.post("/api/staging/apply",
                       data=json.dumps({}),
                       content_type="application/json",
                       headers={"X-Session-Id": "test-session"})
    assert resp.status_code == 200

    data = resp.json
    assert "verification" in data
    v = data["verification"]
    assert v["objectLevel"]["passed"] is True
    assert v["objectLevel"]["editsVerified"] == 1
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_staging_integration.py::test_apply_includes_verification -v`
Expected: FAIL — `"verification"` key not in response

**Step 3: Modify the apply flow**

In `routes/staging.py`, make the following targeted changes:

**3a.** Add import at the top (after existing imports, around line 14):

```python
from apply_verification import verify_apply_integrity
```

**3b.** Add the helper function `_capture_git_file_list` near the other apply helpers (e.g., after `_create_pre_apply_backup` around line 1113):

```python
def _capture_git_file_list():
    """Capture current git status file list for verification.

    Returns list of dicts with 'path' and 'status_code', or None if git
    is unavailable.
    """
    try:
        git_svc = get_git_service()
        result = git_svc.get_status()
        if result.success and result.data and result.data.is_repo:
            return [{"path": f.path, "status_code": f.status_code}
                    for f in result.data.files]
        return None
    except Exception:
        return None
```

**3c.** In `api_apply_staging()`, capture pre-apply state. Insert after line 1310 (`_create_pre_apply_backup`), before line 1312 (`try:`):

```python
    # Capture pre-apply state for verification
    pre_git_files = _capture_git_file_list()
    pre_parser_objects = [obj.to_dict() for obj in service.parser.objects]
```

**3d.** After reference updates (line 1329) and before staging clear (line 1332), insert verification:

```python
        # Post-apply verification
        post_git_files = _capture_git_file_list()
        parsed_objects = [obj.to_dict() for obj in service.parser.objects]
        verification = verify_apply_integrity(
            staging_data=staging_data,
            parsed_objects=parsed_objects,
            pre_git_files=pre_git_files,
            post_git_files=post_git_files,
            config_path=get_config_path(),
            pre_parser_objects=pre_parser_objects,
        )
```

**3e.** Add `"verification": verification` to the `result_ctx` dict (around line 1336).

**3f.** In `_build_apply_success_response()` (around line 1245), add verification to the response. After the `response_data` dict is built:

```python
    verification = result_ctx.get("verification")
    if verification:
        response_data["verification"] = verification
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_staging_integration.py::test_apply_includes_verification -v`
Expected: PASS

Then run full test suite:

Run: `python3 -m pytest tests/ -v`
Expected: All PASS (existing tests unaffected)

**Step 5: Commit**

```bash
git add routes/staging.py tests/test_staging_integration.py
git commit -m "feat(verification): wire apply verification into staging endpoint"
```

---

### Task 6: Integration Test — Multi-Operation Verification

**Files:**
- Modify: `tests/test_staging_integration.py`

Add a test covering the combined create + edit scenario to make sure verification works with multiple simultaneous operation types.

**Step 1: Write the test**

Append to `tests/test_staging_integration.py`:

```python
def test_apply_verification_multi_operation(client, app):
    """Verification works with create + edit together."""
    session_id = "test-session"
    headers = {"X-Session-Id": session_id}

    resp = client.get("/api/objects")
    objects = resp.json
    obj = objects[0]

    staging_data = {
        "sessionId": session_id,
        "stagedCreations": [{
            "id": "create-v1",
            "object_type": "host",
            "targetFile": "hosts.cfg",
            "attributes": {
                "host_name": "verified-host",
                "alias": "Verified",
                "address": "10.0.0.99",
            },
        }],
        "pendingEdits": {
            str(obj["global_index"]): {
                "object": obj,
                "original": obj["attributes"],
                "edited": {**obj["attributes"], "alias": "Also Verified"},
            },
        },
    }

    client.post("/api/staging",
                data=json.dumps(staging_data),
                content_type="application/json",
                headers=headers)

    resp = client.post("/api/staging/apply",
                       data=json.dumps({}),
                       content_type="application/json",
                       headers=headers)
    assert resp.status_code == 200

    data = resp.json
    v = data["verification"]
    assert v["passed"] is True
    assert v["objectLevel"]["editsVerified"] == 1
    assert v["objectLevel"]["creationsVerified"] == 1
```

**Step 2: Run test**

Run: `python3 -m pytest tests/test_staging_integration.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/test_staging_integration.py
git commit -m "test(verification): multi-operation integration test"
```

---

### Task 7: Frontend — Propagate Verification Through Commit Flow

**Files:**
- Modify: `static/js/commit-dialog.js` — `applyGuiStagingChanges()`, `applyGlobalCommit()`, `autoGitCommitGlobal()`, `showGitResultPanel()`
- Modify: `templates/base.html` — add `.warning-text` CSS rule

**Context:** The commit dialog flow is: `applyGlobalCommit()` → `applyGuiStagingChanges()` → `autoGitCommitGlobal()` → `showGitResultPanel()`. Currently `applyGuiStagingChanges()` returns `true/false`, discarding the apply result data. We need to thread the verification data through.

**Step 1: Add `.warning-text` to existing inline styles in `base.html`**

In `templates/base.html`, inside the existing `.git-result-output` CSS rules (around line 965-973 in the inline `<style>` block), add after the `.info-text` rule:

```css
    .git-result-output .warning-text {
        color: var(--nbe-dark-validation-warning-text);
    }
```

This uses the existing `--nbe-dark-validation-warning-text: #ffb74d` token from `tokens.css`.

**Step 2: Modify `applyGuiStagingChanges` to return verification data**

In `commit-dialog.js`, change `applyGuiStagingChanges()` (around line 239) from returning `true/false` to returning the apply result data or `null`:

Current:
```javascript
async function applyGuiStagingChanges() {
    showGitRunningPanel('Applying Changes', 'Applying staged changes...');
    const updateRefsCheckbox = document.getElementById('globalUpdateReferences');
    const updateReferences = updateRefsCheckbox ? updateRefsCheckbox.checked : false;
    const applyResult = await ApiClient.post('/api/staging/apply', {
        updateReferences,
        deferClear: true
    }, { silent: true });
    if (!applyResult.success || !applyResult.data?.success) {
        showStagingResultPanel(false, applyResult.data?.error || applyResult.error || 'Failed to apply staged changes');
        return false;
    }
    return true;
}
```

New:
```javascript
async function applyGuiStagingChanges() {
    showGitRunningPanel('Applying Changes', 'Applying staged changes...');
    const updateRefsCheckbox = document.getElementById('globalUpdateReferences');
    const updateReferences = updateRefsCheckbox ? updateRefsCheckbox.checked : false;
    const applyResult = await ApiClient.post('/api/staging/apply', {
        updateReferences,
        deferClear: true
    }, { silent: true });
    if (!applyResult.success || !applyResult.data?.success) {
        showStagingResultPanel(false, applyResult.data?.error || applyResult.error || 'Failed to apply staged changes');
        return null;
    }
    return applyResult.data;
}
```

**Step 3: Modify `applyGlobalCommit` to thread verification data**

In `applyGlobalCommit()` (around line 1470), change the call to capture and pass the apply data:

Current:
```javascript
    if (hasGuiStaging) {
        const applied = await applyGuiStagingChanges();
        if (!applied) {return;}
    } else {
        showGitRunningPanel('Git Commit', 'Committing changes...');
    }

    updateNavCommitButton(0);
    await autoGitCommitGlobal(commitMessage, hasGuiStaging);
```

New:
```javascript
    let applyData = null;
    if (hasGuiStaging) {
        applyData = await applyGuiStagingChanges();
        if (!applyData) {return;}
    } else {
        showGitRunningPanel('Git Commit', 'Committing changes...');
    }

    updateNavCommitButton(0);
    await autoGitCommitGlobal(commitMessage, hasGuiStaging, applyData);
```

**Step 4: Modify `autoGitCommitGlobal` to accept and pass verification**

Change the function signature and pass verification to `showGitResultPanel`:

Current signature:
```javascript
async function autoGitCommitGlobal(message, clearStagingOnSuccess = false) {
```

New signature:
```javascript
async function autoGitCommitGlobal(message, clearStagingOnSuccess = false, applyData = null) {
```

At the bottom, change the `showGitResultPanel` call to include verification:

Current:
```javascript
    showGitResultPanel(message, result.success, result.data || { error: result.error }, clearStagingOnSuccess && !isSuccess);
```

New:
```javascript
    const verification = applyData?.verification || null;
    showGitResultPanel(message, result.success, result.data || { error: result.error }, clearStagingOnSuccess && !isSuccess, verification);
```

**Step 5: Modify `showGitResultPanel` to render verification**

Change the function signature:

Current:
```javascript
function showGitResultPanel(message, success, result, showRetryOption = false) {
```

New:
```javascript
function showGitResultPanel(message, success, result, showRetryOption = false, verification = null) {
```

After the existing `outputHtml` is built (after the `if (isSuccess) { ... } else { ... }` block, around line 1557), add the verification section:

```javascript
    // Append verification summary if available
    if (verification) {
        outputHtml += '\n' + buildVerificationHtml(verification);
    }
```

**Step 6: Add `buildVerificationHtml` function**

Add this function near `showGitResultPanel` (before or after):

```javascript
function buildVerificationHtml(verification) {
    const ol = verification.objectLevel;
    const fl = verification.fileLevel;
    let html = '\n<span class="info-text">--- Verification ---</span>\n';

    // Object-level lines: only show categories that have counts
    const objectLines = [];
    if (ol.editsVerified > 0 || ol.editsFailed > 0) {
        objectLines.push(ol.editsFailed > 0
            ? `<span class="warning-text">\u26a0\ufe0f ${ol.editsFailed} edit(s) NOT verified</span>`
            : `<span class="success-text">\u2705 ${ol.editsVerified} edit(s) verified</span>`);
    }
    if (ol.creationsVerified > 0 || ol.creationsFailed > 0) {
        objectLines.push(ol.creationsFailed > 0
            ? `<span class="warning-text">\u26a0\ufe0f ${ol.creationsFailed} creation(s) NOT verified</span>`
            : `<span class="success-text">\u2705 ${ol.creationsVerified} creation(s) verified</span>`);
    }
    if (ol.deletionsVerified > 0 || ol.deletionsFailed > 0) {
        objectLines.push(ol.deletionsFailed > 0
            ? `<span class="warning-text">\u26a0\ufe0f ${ol.deletionsFailed} deletion(s) NOT verified</span>`
            : `<span class="success-text">\u2705 ${ol.deletionsVerified} deletion(s) verified</span>`);
    }
    if (ol.movesVerified > 0 || ol.movesFailed > 0) {
        objectLines.push(ol.movesFailed > 0
            ? `<span class="warning-text">\u26a0\ufe0f ${ol.movesFailed} move(s) NOT verified</span>`
            : `<span class="success-text">\u2705 ${ol.movesVerified} move(s) verified</span>`);
    }
    html += objectLines.join('\n') + '\n';

    // File-level line
    if (fl) {
        const fileCount = fl.actualFiles?.length || 0;
        if (fl.passed) {
            html += `<span class="success-text">\u2705 File changes match (${fileCount} file${fileCount !== 1 ? 's' : ''})</span>\n`;
        } else {
            html += `<span class="warning-text">\u26a0\ufe0f File changes mismatch</span>\n`;
            for (const msg of (fl.unexpected || [])) {
                html += `<span class="warning-text">   ${msg}</span>\n`;
            }
            for (const msg of (fl.missing || [])) {
                html += `<span class="warning-text">   ${msg}</span>\n`;
            }
        }
    }

    // Failure details
    if (ol.failures?.length > 0) {
        html += '\n';
        for (const f of ol.failures) {
            html += `<span class="warning-text">   ${f}</span>\n`;
        }
    }

    return html;
}
```

**Step 7: Downgrade title on verification warnings**

In `showGitResultPanel`, after building the `outputHtml` and verification section, adjust the title when verification has failures. Insert before the `showResultPanel()` call:

```javascript
    // Downgrade title if commit succeeded but verification has warnings
    let title = isSuccess ? 'Git Commit Successful' : 'Git Commit Failed';
    if (isSuccess && verification && !verification.passed) {
        title = 'Committed with Warnings';
    }
```

Then use `title` instead of the inline ternary in the `showResultPanel` call:

```javascript
    showResultPanel({
        command,
        success: isSuccess,
        title,
        outputHtml,
        showRetryCommit: showRetryOption && !isSuccess
    });
```

**Step 8: Run the app and manually verify**

Run: `python3 app.py`
1. Make an edit in the explorer
2. Open commit dialog and commit
3. Verify the result panel shows the verification section with green checkmarks
4. Verify the title says "Git Commit Successful" (not "Committed with Warnings")

**Step 9: Commit**

```bash
git add static/js/commit-dialog.js templates/base.html
git commit -m "feat(verification): render verification summary in git result panel"
```

---

### Task 8: Audit Log Verification Results

**Files:**
- Modify: `routes/staging.py` — `_build_apply_success_response()` or after verification runs

Log verification results to the audit trail so there's a permanent record of whether each apply was cleanly verified.

**Step 1: Add verification audit logging**

After verification runs in `api_apply_staging()` (after the `verify_apply_integrity` call), add an audit log entry:

```python
        # Log verification result to audit trail
        if verification:
            v_status = "passed" if verification["passed"] else "warnings"
            ol = verification.get("objectLevel", {})
            log_audit(
                action="verify",
                user=staging_data.get("userEmail"),
                txn=None,
                status=v_status,
                edits_ok=ol.get("editsVerified", 0),
                edits_fail=ol.get("editsFailed", 0),
                creates_ok=ol.get("creationsVerified", 0),
                creates_fail=ol.get("creationsFailed", 0),
                deletes_ok=ol.get("deletionsVerified", 0),
                deletes_fail=ol.get("deletionsFailed", 0),
                moves_ok=ol.get("movesVerified", 0),
                moves_fail=ol.get("movesFailed", 0),
            )
            if not verification["passed"]:
                for failure in ol.get("failures", []):
                    log_audit(action="verify_warning", user=staging_data.get("userEmail"), detail=failure)
```

Note: `log_audit` is already imported in `routes/staging.py` (via `from audit_service import log_audit` at top of file).

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS (audit logging is fire-and-forget, doesn't affect response)

**Step 3: Commit**

```bash
git add routes/staging.py
git commit -m "feat(verification): log verification results to audit trail"
```

---

### Task 9: Lint All Changes

**Files:** All modified Python and JS files

Run linters on all changed files and fix any violations before proceeding to E2E tests.

**Step 1: Ruff (Python)**

Run: `ruff check apply_verification.py routes/staging.py tests/test_apply_verification.py tests/test_staging_integration.py`
Expected: No new violations. Fix any that appear.

**Step 2: ESLint (JavaScript)**

Run: `npm run lint:js`
Expected: No new violations from `commit-dialog.js`. Fix any that appear.

Note: `buildVerificationHtml` must be added to the globals list in `eslint.config.mjs` if it's called cross-file, or kept in the same file scope. Since it's only called from within `commit-dialog.js`, no config change needed.

**Step 3: Commit fixes (if any)**

```bash
git add -A
git commit -m "fix: resolve lint violations in verification code"
```

---

### Task 10: Update Docs — Staging System Page

**Files:**
- Modify: `templates/docs/staging-system.html`

Add a "Post-Apply Verification" subsection after the existing "Git Commit" subsection (after line 282), within the "Applying Changes" section.

**Step 1: Add verification documentation**

Insert after the `<h4>Git Commit</h4>` section (after line 282) and before `<h3>Lock System</h3>` (line 284):

```html
    <h4>Post-Apply Verification</h4>

    <p>
        After changes are written to disk, the app automatically verifies that the apply
        succeeded. Verification runs at two levels:
    </p>

    <ul>
        <li><strong>File-level:</strong> Compares git status (which files actually changed on disk)
            against the set of files that staging intended to modify. Detects unexpected changes
            or missing writes.</li>
        <li><strong>Object-level:</strong> Re-parses the configuration and checks each staged
            operation against the result:
            <ul>
                <li>Edited objects have the expected attribute values</li>
                <li>Created objects exist in their target files</li>
                <li>Deleted objects are gone</li>
                <li>Moved objects are in their target files</li>
            </ul>
        </li>
    </ul>

    <p>
        The verification result appears in the commit result panel after the git commit hash:
    </p>

    <ul>
        <li><span style="color: var(--nbe-terminal-success);">&#x2705;</span> Green lines indicate verified operations.</li>
        <li><span style="color: var(--nbe-dark-validation-warning-text);">&#x26a0;&#xfe0f;</span> Amber lines indicate operations that could not be verified.</li>
    </ul>

    <p>
        If all operations are verified, the panel title reads <strong>Git Commit Successful</strong>.
        If any operation could not be verified, the title changes to <strong>Committed with
        Warnings</strong>. The commit still succeeds — the warning means you should inspect the
        configuration to confirm the changes are correct.
    </p>

    <div class="docs-note">
        Verification results are also recorded in the <a href="#app/audit-log">audit log</a>
        for traceability.
    </div>
```

**Step 2: Update the "On this page" summary**

Change the summary list at the top of the file to include verification:

Current:
```html
        <ul>
            <li>The 10 categories of staged changes</li>
            <li>Reviewing diffs and reference analysis</li>
            <li>Undo, apply, and conflict detection</li>
            <li>Session-based lock system</li>
        </ul>
```

New:
```html
        <ul>
            <li>The 10 categories of staged changes</li>
            <li>Reviewing diffs and reference analysis</li>
            <li>Undo, apply, and conflict detection</li>
            <li>Post-apply verification</li>
            <li>Session-based lock system</li>
        </ul>
```

**Step 3: Commit**

```bash
git add templates/docs/staging-system.html
git commit -m "docs: add post-apply verification section to staging system page"
```

---

### Task 11: Playwright E2E Tests

**Files:**
- These tests use the Playwright MCP tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_run_code`, `browser_take_screenshot`)

Test the verification feature end-to-end in the browser. The app must be running on `http://localhost:8080` with `sample-config/` as the config directory, initialized as a git repo.

**Precondition setup:**

```bash
cd sample-config && git init && git add -A && git commit -m "initial" && cd ..
python3 app.py &
```

**Test Case 1: Verification success — single edit**

1. Navigate to `http://localhost:8080/explorer`
2. Take a snapshot to find an editable object
3. Click on a host object to select it
4. Edit the `alias` field to a new value
5. Click the commit button in the navbar
6. Enter a commit message
7. Click the Apply/Commit button
8. Wait for the git result panel to appear
9. Take a screenshot of the result panel
10. Verify via snapshot:
    - Title contains "Git Commit Successful" (not "Committed with Warnings")
    - Output contains "Verification" section
    - Output contains "edit(s) verified"
    - Output contains "File changes match"

**Test Case 2: Verification success — create + edit**

1. Create a new host object (via right-click → Create Object, or the create button)
2. Also edit an existing object
3. Commit both changes
4. Verify result panel shows:
    - "edit(s) verified"
    - "creation(s) verified"
    - Title is "Git Commit Successful"

**Test Case 3: Verification section visible in result panel**

1. Perform any staging operation and commit
2. Take a screenshot of the result panel
3. Verify the `--- Verification ---` divider is visible
4. Verify at least one green checkmark line is present

**Test Case 4: Docs page shows verification info**

1. Navigate to `http://localhost:8080/docs`
2. Click on "Staging System" in the sidebar
3. Verify the page contains "Post-Apply Verification" heading
4. Verify the page mentions both "File-level" and "Object-level" verification

**Step 1: Execute each test case using Playwright MCP tools**

Run each test case sequentially using the browser tools. Take screenshots at key verification points.

**Step 2: Commit any fixes**

```bash
git add -A
git commit -m "fix(verification): address issues found during E2E testing"
```

---

## Summary

| Task | What | Files | Complexity |
|------|------|-------|------------|
| 1 | `build_expected_changeset()` + tests | `apply_verification.py`, `tests/test_apply_verification.py` | Pure logic |
| 2 | `compare_file_changes()` + tests | Same files | Pure logic |
| 3 | `verify_objects()` + tests | Same files | Pure logic, uses NAME_FIELDS |
| 4 | `verify_apply_integrity()` orchestrator + tests | Same files | Combines 1-3 |
| 5 | Wire into apply flow | `routes/staging.py`, `tests/test_staging_integration.py` | Backend integration |
| 6 | Multi-op integration test | `tests/test_staging_integration.py` | Test only |
| 7 | Frontend: propagate + render verification | `commit-dialog.js`, `base.html` | Frontend integration |
| 8 | Audit log verification results | `routes/staging.py` | Backend, uses existing `log_audit` |
| 9 | Lint all changes (ruff + eslint) | All modified files | Quality gate |
| 10 | Update docs — staging system page | `templates/docs/staging-system.html` | Documentation |
| 11 | Playwright E2E tests | Browser-based | 4 test cases |

**New files:** `apply_verification.py`, `tests/test_apply_verification.py`

**Modified files:** `routes/staging.py` (import + ~30 lines + audit), `tests/test_staging_integration.py` (2 tests), `static/js/commit-dialog.js` (~60 lines), `templates/base.html` (1 CSS rule), `templates/docs/staging-system.html` (~40 lines)

**CSS approach:** All existing tokens and classes reused. One new rule added: `.git-result-output .warning-text` using existing `--nbe-dark-validation-warning-text` (#ffb74d amber).

**Linting:** `ruff check` for Python, `npm run lint:js` for JavaScript — run in Task 9 before E2E testing.

**Audit trail:** Verification results logged as `action=verify` with pass/fail counts, and `action=verify_warning` per individual failure detail.
