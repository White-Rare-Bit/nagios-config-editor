# Cluster M — Audit Log & Commit Accuracy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 6 audit log and commit accuracy bugs: correct action type labels, relative paths in logs, file/folder operations in filters, external file modification detection, and commit diff completeness.

**Architecture:** Backend fixes in `audit_service.py` (correct action enum, relative paths, filter values) and `nagios_service.py`/`nagios_writer.py` (mtime check before write). Frontend commit dialog fix ensures git diff is always shown after apply rather than toggling between staging preview and ground-truth diff.

**Tech Stack:** Python/Flask, JavaScript. Key files: `audit_service.py`, `nagios_service.py`, `nagios_writer.py`, `static/js/explorer/commit-dialog.js` (or wherever the commit dialog lives).

---

## Task 1: Reproduce key bugs with Playwright

**Step 1:** Start the app.

```bash
python3 app.py
```

Navigate to http://localhost:8080. Take a screenshot to `.playwright-mcp/repro-068-start.png`.

**Step 2:** Reproduce 068 — audit log action always shows "edit".

Perform three distinct operations: rename an object, delete an object, and create a new object. Then open the audit log. Observe that all three entries show `action: "edit"` regardless of the actual operation type. Take a screenshot to `.playwright-mcp/repro-068.png`.

**Step 3:** Reproduce 069 — audit log stores absolute paths.

Move a file to a different folder within the config directory. Open the audit log entry for the move. Observe that the path is stored as an absolute path (e.g., `/Users/ohm/Desktop/.../nagios/hosts.cfg`) instead of a config-root-relative path (e.g., `hosts.cfg`). Take a screenshot to `.playwright-mcp/repro-069.png`.

**Step 4:** Reproduce 071 — file/folder operations missing from audit log filter dropdown.

Open the audit log filter. Inspect the action-type dropdown options. Observe that "Move file", "Create folder", "Delete folder" and similar file/folder operation types are absent from the filter list. Take a screenshot to `.playwright-mcp/repro-071.png`.

**Step 5:** Reproduce 072 and 073 — no external modification detection; commit diff incomplete.

While the app is running, externally edit a `.cfg` file (e.g., via a text editor or `echo >> hosts.cfg`). Then attempt to apply staged changes and open the commit dialog. Observe that the app does not warn about the external modification (072), and the commit diff preview does not include the externally changed lines (073). Take a screenshot to `.playwright-mcp/repro-072-073.png`.

**Step 6:** Reproduce 074 — commit dialog toggles between two diff views.

Stage some changes. Open the commit dialog. Observe that the diff display switches between or shows inconsistently a staging preview and a full git diff, with no clear label distinguishing the two. Take a screenshot to `.playwright-mcp/repro-074.png`.

---

## Task 2: Fix 068 — Correct action types in audit log

**Step 1:** Read `audit_service.py` in full to understand the current structure:

```bash
cat audit_service.py
```

Find where audit entries are created. Locate the `action` field — it will be hardcoded as `"edit"` or a single string literal.

**Step 2:** Find all call sites that create audit entries:

```bash
grep -rn "audit\|log_action\|add_entry\|create_entry\|AuditService" *.py routes/
```

**Step 3:** Define an `AuditAction` constants class (or module-level constants) at the top of `audit_service.py`:

```python
class AuditAction:
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    RENAME = "rename"
    MOVE = "move"
    CLONE = "clone"
    CREATE_FILE = "create_file"
    DELETE_FILE = "delete_file"
    MOVE_FILE = "move_file"
    CREATE_FOLDER = "create_folder"
    DELETE_FOLDER = "delete_folder"
    MOVE_FOLDER = "move_folder"
```

**Step 4:** Update each call site to pass the correct `AuditAction` constant instead of the hardcoded `"edit"` string. Map operations as follows:

| Operation | AuditAction constant |
|-----------|----------------------|
| Edit/update an object attribute | `AuditAction.EDIT` |
| Create a new object | `AuditAction.CREATE` |
| Delete an object | `AuditAction.DELETE` |
| Rename an object (name field change) | `AuditAction.RENAME` |
| Move an object to another file | `AuditAction.MOVE` |
| Clone/duplicate an object | `AuditAction.CLONE` |
| Create a new .cfg file | `AuditAction.CREATE_FILE` |
| Delete a .cfg file | `AuditAction.DELETE_FILE` |
| Move/rename a .cfg file | `AuditAction.MOVE_FILE` |
| Create a folder | `AuditAction.CREATE_FOLDER` |
| Delete a folder | `AuditAction.DELETE_FOLDER` |
| Move/rename a folder | `AuditAction.MOVE_FOLDER` |

**Step 5:** Run ruff to check for issues:

```bash
ruff check audit_service.py nagios_service.py routes/
```

Fix any reported issues.

**Step 6:** Commit:

```bash
git add audit_service.py nagios_service.py routes/
git commit -m "$(cat <<'EOF'
fix(audit): correct action type labels in audit log entries

All audit log entries were hardcoded as action="edit". Introduced
AuditAction constants and updated every call site to pass the
semantically correct action type (create, delete, rename, move, etc.).

Fixes bug 068.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Fix 069 — Store relative paths in audit log

**Step 1:** Find where file paths are stored in audit entries. Search for path-related fields:

```bash
grep -n "source_file\|file_path\|abs_path\|config_root\|config_dir\|NAGIOS_CONFIG" audit_service.py nagios_service.py
```

**Step 2:** Find the config root directory. It is likely accessed via `app.config['NAGIOS_CONFIG_DIR']` or equivalent. Confirm:

```bash
grep -rn "NAGIOS_CONFIG_DIR\|config_dir\|nagios_dir" server_config.py app.py nagios_service.py
```

**Step 3:** Add a path normalization helper to `audit_service.py`:

```python
import os

def _make_relative(abs_path: str, config_root: str) -> str:
    """Return path relative to config_root, or abs_path on failure."""
    if not abs_path:
        return abs_path
    try:
        return os.path.relpath(abs_path, config_root)
    except ValueError:
        # Cross-drive paths on Windows — return as-is
        return abs_path
```

**Step 4:** Apply `_make_relative(path, config_root)` to every path field before it is written into an audit entry. This includes `source_file`, `destination_file`, `old_path`, `new_path`, and any other path-like fields in the log entry dict.

Pass `config_root` through the `AuditService` constructor or retrieve it from `app.extensions` at log time.

**Step 5:** Validate: make a move operation, then read the audit log. The stored path should be relative (e.g., `hosts.cfg` or `subdir/hosts.cfg`) not absolute.

**Step 6:** Run ruff:

```bash
ruff check audit_service.py
```

**Step 7:** Commit:

```bash
git add audit_service.py
git commit -m "$(cat <<'EOF'
fix(audit): store config-relative paths in audit log entries

Absolute filesystem paths were recorded in audit entries, making logs
non-portable and leaking system layout. All path fields are now made
relative to the Nagios config root before storage.

Fixes bug 069.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Fix 071 — Add file/folder operations to audit log filter

**Step 1:** Read the audit log filter backend endpoint. Find where allowed filter values are defined:

```bash
grep -rn "audit\|filter\|action_type" routes/
grep -n "filter\|action" audit_service.py | head -40
```

**Step 2:** Find the frontend audit log filter dropdown. Locate where its options are populated:

```bash
grep -rn "auditFilter\|audit.*filter\|filterAudit\|actionType" static/js/
```

**Step 3:** On the backend, ensure the filter query accepts all `AuditAction` values. If there is an allowlist of valid filter values, add the file/folder constants:

```python
VALID_AUDIT_ACTIONS = {
    AuditAction.CREATE,
    AuditAction.EDIT,
    AuditAction.DELETE,
    AuditAction.RENAME,
    AuditAction.MOVE,
    AuditAction.CLONE,
    AuditAction.CREATE_FILE,
    AuditAction.DELETE_FILE,
    AuditAction.MOVE_FILE,
    AuditAction.CREATE_FOLDER,
    AuditAction.DELETE_FOLDER,
    AuditAction.MOVE_FOLDER,
}
```

**Step 4:** On the frontend, add the missing options to the filter `<select>` element. The options should use the same string values as `AuditAction` constants. Add the following entries if absent:

```javascript
const AUDIT_ACTION_OPTIONS = [
    { value: '', label: 'All actions' },
    { value: 'create', label: 'Create object' },
    { value: 'edit', label: 'Edit object' },
    { value: 'delete', label: 'Delete object' },
    { value: 'rename', label: 'Rename object' },
    { value: 'move', label: 'Move object' },
    { value: 'clone', label: 'Clone object' },
    { value: 'create_file', label: 'Create file' },
    { value: 'delete_file', label: 'Delete file' },
    { value: 'move_file', label: 'Move/rename file' },
    { value: 'create_folder', label: 'Create folder' },
    { value: 'delete_folder', label: 'Delete folder' },
    { value: 'move_folder', label: 'Move/rename folder' },
];
```

**Step 5:** Validate with Playwright. Open the audit log filter dropdown — all file/folder action types should appear. Select "Move file" and confirm only move-file entries are shown. Take a screenshot to `.playwright-mcp/validate-071.png`.

**Step 6:** Run ruff and ESLint:

```bash
ruff check audit_service.py routes/
npx eslint static/js/
```

**Step 7:** Commit:

```bash
git add audit_service.py routes/ static/js/
git commit -m "$(cat <<'EOF'
fix(audit): add file/folder operation types to audit log filter

File and folder operations (create_file, delete_file, move_file,
create_folder, delete_folder, move_folder) were missing from the audit
log filter dropdown. All AuditAction values are now included.

Fixes bug 071.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Fix 072 and 073 — External file modification detection

**Step 1:** Read `nagios_writer.py` to understand the atomic write flow:

```bash
cat nagios_writer.py
```

Locate the section that writes files: temp file creation → `flush()` → `os.fsync()` → `os.replace()`.

**Step 2:** Read `staging_manager.py` to understand when files are first loaded and how state is stored:

```bash
cat staging_manager.py
```

Find where files are read initially and where mtimes could be recorded.

**Step 3:** Add a freshness check helper to `nagios_writer.py` (or a shared utility module):

```python
import os

def check_file_freshness(file_path: str, expected_mtime: float) -> bool:
    """
    Return True if the file has NOT been modified since expected_mtime.
    Returns True (safe to write) if the file does not yet exist.
    """
    try:
        actual_mtime = os.path.getmtime(file_path)
        return abs(actual_mtime - expected_mtime) < 0.001  # 1 ms tolerance
    except FileNotFoundError:
        return True  # File doesn't exist yet — OK to create
```

**Step 4:** In `staging_manager.py` (or wherever files are first parsed/loaded), record each file's mtime at load time:

```python
import os

# When loading a file:
file_mtime = os.path.getmtime(file_path)
self._file_mtimes[file_path] = file_mtime
```

Store `_file_mtimes` as a dict on the `StagingManager` instance.

**Step 5:** In the apply phase (in `nagios_service.py` or `staging_manager.py`), before writing each file, check freshness:

```python
from .nagios_writer import check_file_freshness

for file_path, new_content in files_to_write.items():
    expected_mtime = self._file_mtimes.get(file_path)
    if expected_mtime is not None:
        if not check_file_freshness(file_path, expected_mtime):
            return OperationResult(
                success=False,
                error=(
                    f"External modification detected on '{file_path}'. "
                    "Reload the config and re-apply your changes."
                )
            )
```

Return HTTP 409 (conflict) from the route when this `OperationResult` has `success=False` due to an external modification.

**Step 6:** Fix 073 — ensure the commit diff preview always includes external changes. In the commit dialog JS, after a successful apply, fetch the full git diff instead of relying on the staging preview:

```bash
grep -rn "git.*diff\|gitDiff\|commitDiff\|staging.*preview" static/js/explorer/
```

Find the diff-display code. After apply succeeds, call a backend endpoint that returns `git diff HEAD` (or `git diff --cached` if changes are staged for git). Show this as the authoritative diff. Do not use the staging manager's in-memory preview as the post-apply diff source, since it will miss external changes.

**Step 7:** Validate with Playwright.
- Externally modify a `.cfg` file while the app has staged changes.
- Attempt to apply → a 409 conflict error should appear warning about the external modification.
- Reload the config, re-apply → apply succeeds.
- Open commit dialog → git diff shows all changes including the externally modified lines.
- Take screenshots to `.playwright-mcp/validate-072.png` and `.playwright-mcp/validate-073.png`.

**Step 8:** Run ruff and ESLint:

```bash
ruff check nagios_service.py nagios_writer.py staging_manager.py
npx eslint static/js/explorer/
```

**Step 9:** Commit:

```bash
git add nagios_service.py nagios_writer.py staging_manager.py static/js/explorer/
git commit -m "$(cat <<'EOF'
fix(apply): detect external file modifications before writing

Record file mtimes at load time. Before each apply, check that no
file has been modified externally since load; return HTTP 409 if so.
Commit dialog now shows full git diff after apply to capture any
externally introduced changes alongside staged ones.

Fixes bugs 072 and 073.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Fix 074 — Commit dialog shows consistent diff

**Step 1:** Read the commit dialog JavaScript to understand the current two-view toggle:

```bash
grep -rn "commitDialog\|commit-dialog\|CommitDialog\|stagingPreview\|gitDiff" static/js/explorer/
cat static/js/explorer/commit-dialog.js  # adjust path as needed
```

**Step 2:** Identify the two diff views:
- "Staged changes preview" — in-memory list of what the staging manager plans to do; shown before Apply.
- "Git diff" — actual `git diff HEAD` output after Apply completes.

**Step 3:** The fix strategy is to make the transition explicit rather than ambiguous:

- **Before Apply** (staging preview phase): show the staging manager's planned changes labeled clearly as `"Pending changes (not yet written to disk)"`.
- **After Apply** (git diff phase): replace the staging preview with the git diff output labeled `"Git diff — changes written to disk"`.

Ensure the label element updates on transition:

```javascript
function showStagingPreview(changes) {
    diffLabel.textContent = 'Pending changes (not yet written to disk)';
    diffContainer.innerHTML = renderStagingPreview(changes);
}

function showGitDiff(diffText) {
    diffLabel.textContent = 'Git diff \u2014 changes written to disk';
    diffContainer.innerHTML = renderGitDiff(diffText);
}
```

**Step 4:** Remove any toggle button or ambiguous switch that allows the user to flip between the two views after apply — the git diff is the ground truth post-apply. If a "Show staging preview" toggle is present after apply, remove it or disable it with a tooltip explaining "Changes have already been applied — showing git diff."

**Step 5:** Validate with Playwright.
- Stage changes and open the commit dialog before applying → label reads "Pending changes".
- Click Apply → label transitions to "Git diff — changes written to disk" and the diff content updates to reflect actual file changes.
- No toggle between views appears after apply.
- Take a screenshot to `.playwright-mcp/validate-074.png`.

**Step 6:** Run ESLint:

```bash
npx eslint static/js/explorer/
```

**Step 7:** Commit:

```bash
git add static/js/explorer/
git commit -m "$(cat <<'EOF'
fix(commit-dialog): show consistent, labeled diff before and after apply

The commit dialog previously toggled ambiguously between staging
preview and git diff. It now shows a clearly labeled staging preview
before Apply and transitions to the authoritative git diff after Apply,
with no confusing toggle available post-apply.

Fixes bug 074.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final Playwright validation

**Step 1:** Run a full Playwright validation pass. Navigate to http://localhost:8080 and verify each fix in sequence:

- 068: Perform a rename, delete, and create → audit log shows correct action labels (`rename`, `delete`, `create`) for each entry.
- 069: Move a file → audit log stores a relative path (e.g., `subdir/hosts.cfg`), not an absolute path.
- 071: Open the audit log filter dropdown → "Create file", "Delete file", "Move/rename file", "Create folder", "Delete folder", "Move/rename folder" all appear as options.
- 072: Externally modify a `.cfg` file → attempting to apply staged changes produces a 409 conflict warning.
- 073: After a successful apply, the commit dialog diff shows all changes including externally modified lines.
- 074: Commit dialog shows "Pending changes" label before apply and "Git diff" label after apply with no ambiguous toggle.

Take a final composite screenshot to `.playwright-mcp/validate-cluster-m-final.png`.

**Step 2:** Run the Python test suite to confirm no regressions:

```bash
python3 -m pytest tests/ -v
```

All tests must pass before this cluster is considered complete.
