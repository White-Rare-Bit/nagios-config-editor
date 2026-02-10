# Reduce Cyclomatic Complexity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce all ruff C901/PLR09 violations by extracting helper functions, without changing behavior.

**Architecture:** Pure refactoring — extract logical sections from oversized functions into named helpers. Every task is behavior-preserving. Tests must pass before and after each change.

**Tech Stack:** Python 3, Flask, ruff (linter), pytest

**Verification command:** `ruff check . --select C901,PLR09 --statistics`

**Starting violations:** 118

---

## Priority Tiers

**Tier 1 — Extreme (complexity > 30):** Must fix, code is unmaintainable
**Tier 2 — High (complexity 15-30):** Should fix, hard to reason about
**Tier 3 — Moderate (complexity 11-14):** Nice to fix, low risk
**Tier 4 — Skip:** Test files, already-well-factored code, or inherent complexity

### Functions to SKIP (not worth refactoring)

| Function | Why skip |
|----------|----------|
| `tests/test_conventions.py:test_reference_fields_synchronized` (11) | Test code, complexity is from thorough checking |
| `tests/test_orphan_detection.py:test_command_used_by_service_not_orphan` (12) | Test code |
| `test_reorder.py:run_test` | Standalone test script |
| `staging_manager.py:_stage_operation` (PLR0913 only) | Generic helper — 8 args is justified for DRY across 6 callers |
| `routes/staging.py:_write_apply_audit_log` (11) | Already extracted helper, barely over threshold |
| `nagios_model.py:get_name` (13) | Inherent branching — each object type has different name field |
| `nagios_model.py:get_display_name` (14) | Same — fallback chain is the whole point |
| `git_service.py:get_diff` (11) | Barely over threshold, already focused |
| `git_service.py:_run_git` (14) | Retry logic is inherently branchy |

---

## Task 1: Extract `api_health_check` into a health check module

**Complexity: 268 → target < 10 per function**

This is the #1 priority. A single 1,100-line function with 23 distinct checks.

**Files:**
- Create: `routes/health_checks.py`
- Modify: `routes/validation.py:104-1180`
- Test: `tests/test_health_check.py` (existing)

**Step 1: Read and understand existing tests**

Run: `python3 -m pytest tests/ -v -k health 2>&1 | head -40`

**Step 2: Create `routes/health_checks.py` with extracted check functions**

Each of the 23 numbered sections in `api_health_check` becomes its own function. They all share a common signature:

```python
def check_missing_required_fields(objects, obj_to_index, **ctx):
    """Check 1: Objects missing required fields."""
    issues = []
    # ... moved code from validation.py ...
    return issues

def check_invalid_references(objects, obj_to_index, template_lookup, **ctx):
    """Check 2: Invalid references."""
    issues = []
    # ... moved code ...
    return issues

# ... etc for all 23 checks
```

Common context (`ctx`) includes: `template_lookup`, `parser (p)`, `config_path`, `strip_prefix`.

**Step 3: Refactor `api_health_check` to call extracted functions**

```python
def api_health_check():
    service = get_service()
    p = service.parser
    objects = p.objects
    obj_to_index = {id(obj): i for i, obj in enumerate(objects)}
    template_lookup = _build_template_lookup(objects)

    ctx = {'template_lookup': template_lookup, 'parser': p, ...}

    issues = []
    checks = [
        check_missing_required_fields,
        check_invalid_references,
        check_circular_templates,
        # ... all 23
    ]
    for check_fn in checks:
        issues.extend(check_fn(objects, obj_to_index, **ctx))

    summary = _build_summary(issues)
    return jsonify({'issues': issues, 'summary': summary})
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass, identical behavior.

**Step 5: Run ruff to verify complexity reduction**

Run: `ruff check routes/validation.py routes/health_checks.py --select C901`
Expected: No function exceeds 10.

**Step 6: Commit**

```bash
git add routes/validation.py routes/health_checks.py
git commit -m "refactor: extract health check functions from api_health_check (complexity 268→<10)"
```

---

## Task 2: Extract `api_analysis_orphans` shared logic

**Complexity: 36 → target < 10**

`api_analysis_orphans` and checks 20 in `api_health_check` share nearly identical orphan detection code. After Task 1 extracts the health check version, DRY up by having both call the same helper.

**Files:**
- Modify: `routes/health_checks.py` (from Task 1)
- Modify: `routes/validation.py:1184-1325`

**Step 1: Extract shared orphan detection into a reusable function**

Create `_detect_orphans(objects, template_lookup)` in `routes/health_checks.py` that returns orphan data. Both `check_orphan_objects()` (health check #20) and `api_analysis_orphans()` call it.

**Step 2: Simplify `api_analysis_orphans` to thin wrapper**

```python
def api_analysis_orphans():
    service = get_service()
    objects = service.get_objects()
    template_lookup = _build_template_lookup(objects)
    orphan_indices, by_type = _detect_orphans(objects, template_lookup)
    return jsonify({
        'orphan_indices': orphan_indices,
        'summary': {'total_orphans': len(orphan_indices), 'by_type': by_type}
    })
```

**Step 3: Run tests**

Run: `python3 -m pytest tests/ -v`

**Step 4: Commit**

```bash
git add routes/validation.py routes/health_checks.py
git commit -m "refactor: DRY orphan detection between health check and analysis endpoint"
```

---

## Task 3: Simplify `api_save_staging`

**Complexity: 33 → target < 10**

**Files:**
- Modify: `routes/staging.py:441-649`

**Step 1: Run existing tests**

Run: `python3 -m pytest tests/ -v -k staging`

**Step 2: Extract helper functions**

Extract these sections:

```python
def _collect_affected_files(staging_data, config_path):
    """Collect set of files affected by all staging operations."""
    # Lines 498-540 of current api_save_staging
    ...

def _preserve_existing_session_data(existing_staging, new_staging, session_id):
    """Preserve file/folder ops and user identity from existing staging if same session."""
    # Lines 481-496
    ...
```

**Step 3: Refactor `api_save_staging` to use helpers**

The function should become: validate → acquire lock → preserve session data → collect files → build undo entries → save.

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`

**Step 5: Run ruff**

Run: `ruff check routes/staging.py --select C901 -q`

**Step 6: Commit**

```bash
git add routes/staging.py
git commit -m "refactor: extract helpers from api_save_staging (complexity 33→<10)"
```

---

## Task 4: Simplify `api_staging_edit`

**Complexity: 22 → target < 10**

**Files:**
- Modify: `routes/staging.py` (wherever `api_staging_edit` lives)

**Step 1: Extract validation and response building**

Split into: input validation → object lookup → edit application → response building.

**Step 2: Run tests and ruff**

**Step 3: Commit**

```bash
git add routes/staging.py
git commit -m "refactor: extract helpers from api_staging_edit (complexity 22→<10)"
```

---

## Task 5: Simplify `api_get_virtual_tree`

**Complexity: 21 → target < 10**

**Files:**
- Modify: `routes/staging.py:1043-1167`

**Step 1: Extract virtual object building**

The function builds a virtual view by applying staged changes to objects. Extract:

```python
def _apply_staged_edits_to_virtual(virtual_objects, pending_edits):
    """Apply pending edits to virtual object list."""
    ...

def _apply_staged_deletions_to_virtual(virtual_objects, staged_deletions):
    """Remove deleted objects from virtual list."""
    ...

def _apply_staged_moves_to_virtual(virtual_objects, staged_moves):
    """Update source_file for moved objects."""
    ...

def _count_staged_operations(staging_data):
    """Calculate staged operation counts."""
    ...
```

**Step 2: Run tests and ruff**

**Step 3: Commit**

```bash
git add routes/staging.py
git commit -m "refactor: extract helpers from api_get_virtual_tree (complexity 21→<10)"
```

---

## Task 6: Simplify `api_staging_diff`

**Complexity: 17 → target < 10**

**Files:**
- Modify: `routes/staging.py:1254-1377`

**Step 1: Extract staged changes summary builder**

The repetitive `if count > 0: staged_changes.append(...)` block (lines 1319-1340) is a clear extraction target:

```python
def _build_staged_changes_summary(staging):
    """Build human-readable summary of staged changes for commit dialog."""
    ...
```

**Step 2: Run tests and ruff**

**Step 3: Commit**

```bash
git add routes/staging.py
git commit -m "refactor: extract helpers from api_staging_diff (complexity 17→<10)"
```

---

## Task 7: Simplify `api_apply_staging`

**Complexity: 19 → target < 10**

**Files:**
- Modify: `routes/staging.py:865-1039`

**Step 1: Extract post-apply validation**

```python
def _run_post_apply_validation(config_path, log):
    """Run nagios -v validation after apply and return result dict."""
    # Lines 1005-1027
    ...
```

**Step 2: Run tests and ruff**

**Step 3: Commit**

```bash
git add routes/staging.py
git commit -m "refactor: extract post-apply validation from api_apply_staging"
```

---

## Task 8: Simplify `get_workspace_diff`

**Complexity: 23 → target < 10**

**Files:**
- Modify: `git_service.py:357-510`

**Step 1: Extract diff parsing**

```python
def _parse_diff_output(self, diff_text, excluded_paths):
    """Parse raw git diff output into structured file-based diffs."""
    ...
```

**Step 2: Run tests and ruff**

**Step 3: Commit**

```bash
git add git_service.py
git commit -m "refactor: extract diff parsing from get_workspace_diff"
```

---

## Task 9: Simplify `backup_manager.py` functions

**Combined: restore_backup (18), list_backups (13), create_backup (12)**

**Files:**
- Modify: `backup_manager.py:32-264`

**Step 1: Extract from `restore_backup`**

```python
def _validate_backup_request(self, backup_name):
    """Validate backup name and return path, or raise ValueError."""
    ...

def _extract_backup_to_temp(self, zip_path):
    """Extract backup zip to temp directory, return temp path."""
    ...
```

**Step 2: Extract from `list_backups`**

```python
def _parse_backup_metadata(self, zip_path):
    """Read metadata from backup zip file."""
    ...
```

**Step 3: Extract from `create_backup`**

```python
def _collect_config_files(self):
    """Walk config directory and collect .cfg files for backup."""
    ...
```

**Step 4: Run tests and ruff**

**Step 5: Commit**

```bash
git add backup_manager.py
git commit -m "refactor: extract helpers from backup_manager (restore/list/create)"
```

---

## Task 10: Simplify remaining service/route functions

**Batch the remaining moderate-complexity functions.**

**Functions:**
- `nagios_service.py:_apply_changes` (31) — already has helpers extracted, reduce orchestration complexity
- `nagios_service.py:_validate_pending_edits` (24) — extract validation sub-checks
- `file_operations.py:move_object_between_files` (17) — extract same-file vs cross-file paths
- `file_operations.py:find_block_range` (16) — extract brace matching
- `nagios_parser.py:_find_define_blocks` (15) / `parse_config_file` (20) — extract brace matching loop
- `server_config.py:update_config` (17) — extract per-section update logic
- `staging_manager.py:get_staging_info` (14) — extract counting logic

**Files:**
- Modify: `nagios_service.py`, `file_operations.py`, `nagios_parser.py`, `server_config.py`, `staging_manager.py`

**Step 1: Extract helpers for each function**

Apply the same pattern: identify logical sections, extract into named helpers.

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`

**Step 3: Run ruff**

Run: `ruff check . --select C901,PLR09 --statistics`

**Step 4: Commit**

```bash
git add nagios_service.py file_operations.py nagios_parser.py server_config.py staging_manager.py
git commit -m "refactor: reduce complexity in service and utility modules"
```

---

## Task 11: Simplify remaining route handlers

**Functions:**
- `routes/explorer.py:api_explorer_detail` (18) — extract attribute resolution logic
- `routes/staging.py:api_staging_edit` (22) — extract validation/lookup (if not done in Task 4)
- `routes/git.py:api_git_commit` (14), `api_git_discard` (12) — extract validation
- `routes/objects.py:api_delete_objects` (18) — extract batch deletion loop
- `routes/settings.py:api_update_settings` (15) — extract per-section validation
- `routes/templates.py:get_inheritance` (20) — extract chain walking logic
- `routes/validation.py:api_analysis_template_suggestions` (14) — extract signature building

**Step 1: Extract helpers for each**

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`

**Step 3: Run ruff final check**

Run: `ruff check . --select C901,PLR09 --statistics`
Expected: 0 errors (excluding skipped test files).

**Step 4: Commit**

```bash
git add routes/
git commit -m "refactor: reduce complexity in all route handlers"
```

---

## Task 12: Final verification

**Step 1: Full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass.

**Step 2: Final ruff check**

Run: `ruff check . --select C901,PLR09 --statistics`
Expected: Only test file violations remain (if any).

**Step 3: Compare before/after**

Document: started at 118 violations, ended at N.

**Step 4: Final commit if needed**

```bash
git commit -m "refactor: complexity reduction complete — 118 → N violations"
```
