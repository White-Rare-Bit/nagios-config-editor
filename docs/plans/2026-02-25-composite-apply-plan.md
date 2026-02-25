# Per-Entity Composite Apply Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the 4 separate object-apply phases with a single per-entity composite phase that merges operations before executing, fixing the edit+move bug class.

**Architecture:** Add a `_build_composite_actions()` merge step that collapses pendingEdits, stagedMoves, stagedObjectDeletions, and stagedCreations into per-entity `CompositeAction` objects. Replace the 4 object phase calls in `_execute_apply_phases()` with a single `apply_object_composite()` that executes these actions in order: deletes, moves/edits/move_edits, creates.

**Tech Stack:** Python/Flask backend, Playwright MCP for E2E testing, ruff for linting

---

## Global Directives

### MCP Tool Strategy (for E2E tasks)

1. **Screenshots for observation/verification** — use `browser_take_screenshot` for visual confirmation
2. **`browser_run_code` with JS selectors** — when the DOM structure is known, use JS to find refs and interact directly
3. **`browser_snapshot` to file only** — use with `filename` when exploring unknown structure; then `Read` to inspect
4. **Avoid returning full snapshots inline** — never call `browser_snapshot` without a `filename`

### Quality Gates

- `ruff check` on all changed Python files after each code task
- `python3 -m pytest tests/ -v` after implementation tasks
- E2E Playwright validation before and after

---

### Task 1: E2E Bug Reproduction — Confirm Edit+Move Fails

**Files:**
- None (testing only, uses Playwright MCP against running app)

**Step 1: Ensure Flask app is running on port 8080**

Check if the app is running. If not:
```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor
python3 app.py &
```

Wait for `Running on http://0.0.0.0:8080`.

**Step 2: Navigate to the Explorer page**

```
browser_navigate → http://localhost:8080/explorer
```

Wait for the page to load. Take a screenshot to confirm.

**Step 3: Select an object to edit**

Use `browser_snapshot` to file, then find a host object (e.g., `firewall-02`) in the left tree. Click it to select it and open it in the center pane.

**Step 4: Edit an attribute**

In the center pane editor, modify the `hostgroups` field — add `,test-group` to the end of the existing value. Click Save/stage the edit.

**Step 5: Move the same object to a different file**

Right-click the same object in the tree. Select "Move to..." from the context menu. Choose `services.cfg` as the target file. Confirm the move.

**Step 6: Apply staged changes**

Click the Commit button in the navbar. In the commit dialog, click Apply (not commit — just apply). Or use the Explorer's apply button if available.

**Step 7: Assert failure**

Verify the apply fails with an error containing "objectMoves" and "Could not find object to move". Take a screenshot of the error.

**Step 8: Reset state**

Discard/clear the staging state so the sample-config is clean for later tasks. Use the discard button or:
```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor/sample-config && git checkout .
```

Then reload the page.

---

### Task 2: Add CompositeAction Dataclass

**Files:**
- Modify: `nagios_service.py` (add dataclass near top, after imports)

**Step 1: Add the dataclass**

After the existing imports in `nagios_service.py` (around line 30), add:

```python
from dataclasses import dataclass, field


@dataclass
class CompositeAction:
    """A merged per-entity action for the apply phase.

    Collapses separate staging operations (edit, move, delete, create) on the
    same object into a single composite action. This eliminates phase-ordering
    bugs where the same object appears in multiple phases.
    """

    action_type: str          # "delete" | "edit" | "move" | "move_edit" | "create"
    stable_key: str           # "source_file|object_type|name"
    object_type: str
    object_name: str
    source_file: str | None = None
    original_attrs: dict | None = None
    final_attrs: dict | None = None
    target_file: str | None = None
    insert_position: float | None = None
    inline_comments: dict | None = None
    global_index: int | None = None
```

**Step 2: Verify import works**

```bash
python3 -c "from nagios_service import CompositeAction; print('OK')"
```

Expected: `OK`

**Step 3: Run ruff check**

```bash
ruff check nagios_service.py
```

Expected: No errors on the new code.

---

### Task 3: Implement `_build_composite_actions()`

**Files:**
- Modify: `nagios_service.py` (add method to NagiosService class)

**Step 1: Write `_build_composite_actions` method**

Add to the `NagiosService` class (after the `CompositeAction` dataclass, within the class body — place it before `apply_object_moves`):

```python
def _build_composite_actions(self, staging_data: dict) -> list[CompositeAction]:
    """Merge staging operations into per-entity composite actions.

    Indexes pendingEdits, stagedMoves, stagedObjectDeletions, and
    stagedCreations by stable key, then merges overlapping operations
    into a single CompositeAction per entity.

    Args:
        staging_data: Full staging data dict from staging manager.

    Returns:
        List of CompositeAction sorted: deletes first, then moves/edits, then creates.

    """
    p = self.parser
    edits_by_key = {}
    moves_by_key = {}
    deletes_by_key = {}

    # Index pendingEdits by stable key
    for gi_str, entry in staging_data.get("pendingEdits", {}).items():
        if not isinstance(entry, dict):
            continue
        obj_meta = entry.get("object", {})
        source_file = obj_meta.get("source_file")
        obj_type = obj_meta.get("object_type")
        obj_name = obj_meta.get("display_name") or obj_meta.get("name")
        if source_file and obj_type and obj_name is not None:
            key = f"{source_file}|{obj_type}|{obj_name}"
            edits_by_key[key] = {
                "entry": entry,
                "global_index": int(gi_str) if gi_str is not None else None,
            }

    # Index stagedMoves by stable key (already keyed this way)
    for key, move_entry in staging_data.get("stagedMoves", {}).items():
        if isinstance(move_entry, dict):
            moves_by_key[key] = move_entry

    # Index stagedObjectDeletions by stable key (resolve via parser)
    for deletion_idx in staging_data.get("stagedObjectDeletions", []):
        if isinstance(deletion_idx, int) and 0 <= deletion_idx < len(p.objects):
            obj = p.objects[deletion_idx]
            name = get_object_name(obj.object_type, obj.attributes)
            key = f"{obj.source_file}|{obj.object_type}|{name}"
            deletes_by_key[key] = {
                "global_index": deletion_idx,
                "obj": obj,
            }

    # Collect creation actions (no merging needed)
    create_actions = []
    for creation in staging_data.get("stagedCreations", []):
        obj_type = creation.get("object_type")
        attrs = creation.get("attributes", {})
        target_file = creation.get("targetFile")
        if not (obj_type and target_file):
            continue
        name_field = NAME_FIELDS.get(obj_type)
        obj_name = attrs.get(name_field, "") if name_field else ""
        if not os.path.isabs(target_file):
            target_file = os.path.join(self._config_path, target_file)
        create_actions.append(CompositeAction(
            action_type="create",
            stable_key=f"{target_file}|{obj_type}|{obj_name}",
            object_type=obj_type,
            object_name=obj_name,
            target_file=target_file,
            final_attrs=attrs,
            inline_comments=creation.get("inline_comments"),
        ))

    # Merge edits, moves, deletes by stable key
    all_keys = set(edits_by_key) | set(moves_by_key) | set(deletes_by_key)
    delete_actions = []
    modify_actions = []

    for key in all_keys:
        has_edit = key in edits_by_key
        has_move = key in moves_by_key
        has_delete = key in deletes_by_key
        parsed = parse_stable_key(key)
        if not parsed:
            continue
        obj_type = parsed["object_type"]
        obj_name = parsed["name"]
        source_file = parsed["source_file"]

        if has_delete:
            del_info = deletes_by_key[key]
            delete_actions.append(CompositeAction(
                action_type="delete",
                stable_key=key,
                object_type=obj_type,
                object_name=obj_name,
                source_file=source_file,
                global_index=del_info["global_index"],
            ))

        elif has_edit and has_move:
            edit_info = edits_by_key[key]
            move_info = moves_by_key[key]
            original_attrs = edit_info["entry"].get("original", {})
            final_attrs = edit_info["entry"].get("edited", {})
            target_file = move_info.get("targetFile")
            insert_position = move_info.get("insertPosition")
            modify_actions.append(CompositeAction(
                action_type="move_edit",
                stable_key=key,
                object_type=obj_type,
                object_name=obj_name,
                source_file=source_file,
                original_attrs=original_attrs,
                final_attrs=final_attrs,
                target_file=target_file,
                insert_position=insert_position,
            ))

        elif has_move:
            move_info = moves_by_key[key]
            target_file = move_info.get("targetFile")
            insert_position = move_info.get("insertPosition")
            # Get on-disk attrs from parser for matching
            obj_meta = move_info.get("object", {})
            move_attrs = obj_meta.get("attributes", {})
            # Resolve original attrs from parser (on-disk truth)
            original_attrs = self._resolve_on_disk_attrs(source_file, obj_type, obj_name)
            if original_attrs is None:
                original_attrs = move_attrs  # Fallback to snapshot
            modify_actions.append(CompositeAction(
                action_type="move",
                stable_key=key,
                object_type=obj_type,
                object_name=obj_name,
                source_file=source_file,
                original_attrs=original_attrs,
                target_file=target_file,
                insert_position=insert_position,
            ))

        elif has_edit:
            edit_info = edits_by_key[key]
            final_attrs = edit_info["entry"].get("edited", {})
            gi = edit_info["global_index"]
            modify_actions.append(CompositeAction(
                action_type="edit",
                stable_key=key,
                object_type=obj_type,
                object_name=obj_name,
                source_file=source_file,
                final_attrs=final_attrs,
                global_index=gi,
            ))

    # Sort deletes by reverse line order within same file (same as current)
    delete_actions.sort(key=lambda a: (a.source_file or "", -(a.global_index or 0)))

    return delete_actions + modify_actions + create_actions
```

**Step 2: Add the `_resolve_on_disk_attrs` helper**

Add this method to NagiosService (right before `_build_composite_actions`):

```python
def _resolve_on_disk_attrs(self, source_file: str, obj_type: str,
                            obj_name: str) -> dict | None:
    """Look up the on-disk attributes for an object by identity.

    Args:
        source_file: Source file path
        obj_type: Object type
        obj_name: Object name

    Returns:
        Attribute dict from parser, or None if not found.

    """
    source_real = os.path.realpath(source_file)
    name_field = NAME_FIELDS.get(obj_type)
    for obj in self.parser.objects:
        if (os.path.realpath(obj.source_file) == source_real
                and obj.object_type == obj_type):
            if name_field and obj.attributes.get(name_field) == obj_name:
                return dict(obj.attributes)
            if not name_field and obj.get_name() == obj_name:
                return dict(obj.attributes)
    return None
```

**Step 3: Run ruff check**

```bash
ruff check nagios_service.py
```

Fix any issues.

**Step 4: Quick smoke test**

```bash
python3 -c "from nagios_service import NagiosService; print('imports OK')"
```

---

### Task 4: Implement `apply_object_composite()`

**Files:**
- Modify: `nagios_service.py` (add method to NagiosService class)

**Step 1: Write the composite apply method**

Add to NagiosService class:

```python
def apply_object_composite(self, staging_data: dict) -> OperationResult:
    """Apply all object operations as per-entity composite actions.

    Replaces the separate apply_object_deletions, apply_object_moves,
    apply_object_edits, and apply_object_creations methods. Merges
    operations on the same entity into a single action before executing.

    Returns:
        OperationResult with data containing per-type counts, errors, details.

    """
    logger.debug("apply_object_composite: result=started")
    actions = self._build_composite_actions(staging_data)

    counts = {"deletes": 0, "moves": 0, "edits": 0, "move_edits": 0, "creates": 0}
    errors = []
    details = []

    for action in actions:
        result, detail = self._execute_composite_action(action)
        if result.success:
            count_key = action.action_type + "s" if action.action_type != "move_edit" else "move_edits"
            counts[count_key] = counts.get(count_key, 0) + 1
            if detail:
                details.append(detail)
        else:
            errors.append(result.error or f"Failed {action.action_type} on {action.stable_key}")

    total = sum(counts.values())
    if errors:
        result_str = "partial" if total > 0 else "failed"
        logger.warning(
            "apply_object_composite: %s errors=%d result=%s",
            " ".join(f"{k}={v}" for k, v in counts.items()),
            len(errors), result_str,
        )
    elif total > 0:
        logger.info(
            "apply_object_composite: %s result=success",
            " ".join(f"{k}={v}" for k, v in counts.items()),
        )
    else:
        logger.debug("apply_object_composite: total=0 result=noop")

    return OperationResult(True, data={
        "count": total,
        "errors": errors,
        "details": details,
        "counts": counts,
    })
```

**Step 2: Write `_execute_composite_action`**

```python
def _execute_composite_action(self, action: CompositeAction) -> tuple[OperationResult, dict | None]:
    """Execute a single composite action and return result + detail entry.

    Each action triggers a parser reload after modifying files so
    subsequent actions see the updated state.

    Args:
        action: The CompositeAction to execute.

    Returns:
        Tuple of (OperationResult, detail_dict or None).

    """
    if action.action_type == "delete":
        return self._exec_delete(action)
    if action.action_type == "edit":
        return self._exec_edit(action)
    if action.action_type == "move":
        return self._exec_move(action)
    if action.action_type == "move_edit":
        return self._exec_move_edit(action)
    if action.action_type == "create":
        return self._exec_create(action)
    return OperationResult(False, f"Unknown action type: {action.action_type}"), None
```

**Step 3: Write action executors**

```python
def _exec_delete(self, action: CompositeAction) -> tuple[OperationResult, dict | None]:
    """Execute a delete composite action."""
    p = self.parser
    if action.global_index is None or action.global_index >= len(p.objects):
        return OperationResult(False, f"Invalid index for delete: {action.stable_key}"), None
    obj = p.objects[action.global_index]
    result = self.delete_object(obj.source_file, obj.line_number)
    if result.success:
        detail = {
            "action": "delete",
            "object_type": action.object_type,
            "object_name": action.object_name,
            "file": obj.source_file,
        }
        return result, detail
    return result, None

def _exec_edit(self, action: CompositeAction) -> tuple[OperationResult, dict | None]:
    """Execute an edit composite action."""
    self._parser = NagiosConfigParser(self._config_path)
    self._parser.parse_all()
    target_obj = self._find_by_identity(action.source_file, action.object_type, action.object_name)
    if not target_obj:
        return OperationResult(False, f"Edit: object not found: {action.stable_key}"), None
    old_attrs = dict(target_obj.attributes)
    merged_attrs = dict(target_obj.attributes)
    merged_attrs.update(action.final_attrs)
    result = self.update_object(
        target_obj.source_file, target_obj.line_number,
        merged_attrs, target_obj.object_type,
        inline_comments=target_obj.inline_comments,
    )
    if result.success:
        detail = self._build_edit_detail(target_obj, old_attrs, action.final_attrs)
        detail["action"] = "edit"
        return result, detail
    return result, None

def _exec_move(self, action: CompositeAction) -> tuple[OperationResult, dict | None]:
    """Execute a move composite action."""
    self._parser = NagiosConfigParser(self._config_path)
    self._parser.parse_all()
    target_obj = self._find_by_attrs(action.source_file, action.object_type, action.original_attrs)
    if not target_obj:
        return OperationResult(False, f"Move: object not found: {action.stable_key}"), None
    insert_line = self._resolve_insert_position(
        action.target_file, action.insert_position, self._parser.objects,
        exclude_obj=target_obj,
    )
    result = move_object_between_files(
        target_obj.source_file, target_obj.line_number,
        action.target_file, action.object_type,
        action.original_attrs, insert_line,
    )
    if result.success:
        detail = {
            "action": "move",
            "object_type": action.object_type,
            "object_name": action.object_name,
            "from_file": action.source_file,
            "to_file": action.target_file,
        }
        return result, detail
    return result, None

def _exec_move_edit(self, action: CompositeAction) -> tuple[OperationResult, dict | None]:
    """Execute a move+edit composite action.

    Step 1: Move using original on-disk attrs for matching.
    Step 2: Edit in new location with final attrs.
    """
    # Move phase
    self._parser = NagiosConfigParser(self._config_path)
    self._parser.parse_all()
    target_obj = self._find_by_attrs(action.source_file, action.object_type, action.original_attrs)
    if not target_obj:
        return OperationResult(False, f"MoveEdit move: object not found: {action.stable_key}"), None
    insert_line = self._resolve_insert_position(
        action.target_file, action.insert_position, self._parser.objects,
        exclude_obj=target_obj,
    )
    move_result = move_object_between_files(
        target_obj.source_file, target_obj.line_number,
        action.target_file, action.object_type,
        action.original_attrs, insert_line,
    )
    if not move_result.success:
        return move_result, None

    # Edit phase — find the moved object in target file
    self._parser = NagiosConfigParser(self._config_path)
    self._parser.parse_all()
    moved_obj = self._find_by_identity(action.target_file, action.object_type, action.object_name)
    if not moved_obj:
        return OperationResult(False, f"MoveEdit edit: object not found after move: {action.stable_key}"), None
    old_attrs = dict(moved_obj.attributes)
    merged_attrs = dict(moved_obj.attributes)
    merged_attrs.update(action.final_attrs)
    edit_result = self.update_object(
        moved_obj.source_file, moved_obj.line_number,
        merged_attrs, moved_obj.object_type,
        inline_comments=moved_obj.inline_comments,
    )
    if edit_result.success:
        detail = {
            "action": "move_edit",
            "object_type": action.object_type,
            "object_name": action.object_name,
            "from_file": action.source_file,
            "to_file": action.target_file,
            "changes": self._build_edit_detail(moved_obj, old_attrs, action.final_attrs).get("changes", []),
        }
        return edit_result, detail
    return edit_result, None

def _exec_create(self, action: CompositeAction) -> tuple[OperationResult, dict | None]:
    """Execute a create composite action."""
    result = self.create_object(
        action.target_file, action.object_type, action.final_attrs,
        inline_comments=action.inline_comments,
    )
    if result.success:
        detail = {
            "action": "create",
            "object_type": action.object_type,
            "object_name": action.object_name,
            "file": action.target_file,
        }
        return result, detail
    return result, None
```

**Step 4: Write identity lookup helpers**

These replace `_find_object_by_entry` and `_find_object_by_attrs`:

```python
def _find_by_identity(self, source_file: str, obj_type: str,
                       obj_name: str) -> NagiosObject | None:
    """Find object by stable identity: source_file + type + name."""
    source_real = os.path.realpath(source_file)
    name_field = NAME_FIELDS.get(obj_type)
    for obj in self.parser.objects:
        if (os.path.realpath(obj.source_file) == source_real
                and obj.object_type == obj_type):
            if name_field and obj.attributes.get(name_field) == obj_name:
                return obj
            if not name_field and obj.get_name() == obj_name:
                return obj
    return None

def _find_by_attrs(self, source_file: str, obj_type: str,
                    attrs: dict) -> NagiosObject | None:
    """Find object by exact attribute match (for moves)."""
    source_real = os.path.realpath(source_file)
    for obj in self.parser.objects:
        if (os.path.realpath(obj.source_file) == source_real
                and obj.object_type == obj_type
                and obj.attributes == attrs):
            return obj
    return None
```

**Step 5: Run ruff check**

```bash
ruff check nagios_service.py
```

**Step 6: Run existing tests**

```bash
python3 -m pytest tests/ -v
```

Expected: All existing tests pass (new code not wired in yet).

**Step 7: Commit**

```bash
git add nagios_service.py
git commit -m "feat: add CompositeAction model and apply_object_composite method

Implements per-entity composite actions that merge staging operations
(edit, move, delete, create) before executing. This replaces the
phase-based object apply with a unified composite system."
```

---

### Task 5: Wire Composite Phase into `_execute_apply_phases`

**Files:**
- Modify: `routes/staging.py` (update `_execute_apply_phases` and audit logging)

**Step 1: Replace 4 object phases with 1 composite phase**

In `_execute_apply_phases()` (around line 860), replace:

```python
phases = [
    ("folderCreations", lambda: service.apply_folder_creations(staging_data)),
    ("fileCreations", lambda: service.apply_file_creations(staging_data)),
    ("objectDeletions", lambda: service.apply_object_deletions(staging_data)),
    ("objectMoves", lambda: service.apply_object_moves(staging_data)),
    ("objectEdits", lambda: service.apply_object_edits(staging_data)),
    ("objectCreations", lambda: service.apply_object_creations(staging_data)),
    ("fileMoves", lambda: service.apply_file_moves(staging_data)),
    ("folderMoves", lambda: service.apply_folder_moves(staging_data)),
    ("fileDeletions", lambda: service.apply_file_deletions(staging_data)),
    ("folderDeletions", lambda: service.apply_folder_deletions(staging_data)),
]
```

With:

```python
phases = [
    ("folderCreations", lambda: service.apply_folder_creations(staging_data)),
    ("fileCreations", lambda: service.apply_file_creations(staging_data)),
    ("objectComposite", lambda: service.apply_object_composite(staging_data)),
    ("fileMoves", lambda: service.apply_file_moves(staging_data)),
    ("folderMoves", lambda: service.apply_folder_moves(staging_data)),
    ("fileDeletions", lambda: service.apply_file_deletions(staging_data)),
    ("folderDeletions", lambda: service.apply_folder_deletions(staging_data)),
]
```

**Step 2: Update `_PHASE_TO_AUDIT_KEY` mapping**

Replace the 4 object phase entries with the composite key:

```python
_PHASE_TO_AUDIT_KEY = {
    "objectComposite": "object_composite",
    "folderCreations": "folder_creations",
    "fileCreations": "file_creations",
    "fileMoves": "file_moves",
    "folderMoves": "folder_moves",
    "fileDeletions": "file_deletions",
    "folderDeletions": "folder_deletions",
}
```

**Step 3: Update `_write_apply_audit_log` for composite details**

The composite phase returns details with an `action` field per entry. Update the audit writer to dispatch on `detail["action"]` instead of `audit_key`:

In `_write_apply_audit_log`, replace the object-type-specific branches (the `if audit_key == "object_edits"` / `elif audit_key == "object_moves"` / etc. block) with a handler for `"object_composite"`:

```python
elif audit_key == "object_composite":
    action_type = detail.get("action", "")
    obj_type = detail.get("object_type", "")
    obj_name = detail.get("object_name", "")

    if action_type in ("edit", "move_edit"):
        for change in detail.get("changes", []):
            log_audit(
                action="edit", user=user, txn=txn,
                type=obj_type, name=obj_name,
                field=change.get("key", ""),
                op=change.get("type", "modify"),
                from_val=change.get("from", ""),
                to_val=change.get("to", change.get("value", "")),
            )
    if action_type in ("move", "move_edit"):
        log_audit(
            action="move", user=user, txn=txn,
            type=obj_type, name=obj_name,
            op="move",
            from_val=_make_relative_path(detail.get("from_file", "")),
            to_val=_make_relative_path(detail.get("to_file", "")),
        )
    if action_type == "create":
        log_audit(
            action="create", user=user, txn=txn,
            type=obj_type, name=obj_name,
            op="create",
        )
    if action_type == "delete":
        log_audit(
            action="delete", user=user, txn=txn,
            type=obj_type, name=obj_name,
            op="delete",
        )
```

**Step 4: Update `_build_apply_success_response` summary**

The composite phase returns `data["counts"]` dict. Update `_execute_apply_phases` to flatten composite counts into the summary:

After the phase loop in `_execute_apply_phases`, when the phase key is `"objectComposite"`, expand the counts:

```python
for key, apply_fn in phases:
    result = apply_fn()

    if key == "objectComposite":
        # Flatten composite counts into summary
        composite_counts = result.data.get("counts", {})
        applied_summary["objectDeletions"] = composite_counts.get("deletes", 0)
        applied_summary["objectMoves"] = composite_counts.get("moves", 0)
        applied_summary["objectEdits"] = composite_counts.get("edits", 0)
        applied_summary["objectMoveEdits"] = composite_counts.get("move_edits", 0)
        applied_summary["objectCreations"] = composite_counts.get("creates", 0)
    else:
        applied_summary[key] = result.data.get("count", 0)

    errors = result.data.get("errors", [])
    details = result.data.get("details", [])

    if details:
        if key == "objectComposite":
            all_details[key] = details
        else:
            all_details[key] = details

    if errors:
        phase_errors.extend(errors)
        return applied_summary, all_details, phase_errors, key

return applied_summary, all_details, phase_errors, None
```

**Step 5: Update docstring in `api_apply_staging`**

Update the docstring at the top of `api_apply_staging()` (line 1279) to reflect the new 7-phase order.

**Step 6: Run ruff check**

```bash
ruff check routes/staging.py
```

**Step 7: Run existing tests**

```bash
python3 -m pytest tests/ -v
```

Expected: All pass. The staging integration tests use the API which now goes through the composite path.

**Step 8: Commit**

```bash
git add routes/staging.py
git commit -m "feat: wire composite apply phase, replace 4 object phases with 1

Replaces objectDeletions, objectMoves, objectEdits, objectCreations
phases with single objectComposite phase. Updates audit logging and
summary flattening for backward compatibility."
```

---

### Task 6: Remove Old Phase Methods

**Files:**
- Modify: `nagios_service.py` (remove replaced methods)

**Step 1: Remove old methods**

Remove these methods from `NagiosService` (they are replaced by the composite system):
- `apply_object_deletions` (the method body)
- `apply_object_moves` (the method body)
- `apply_object_edits` (the method body)
- `apply_object_creations` (the method body)
- `_normalize_staged_moves`
- `_find_object_by_attrs`
- `_find_object_by_entry`
- `_determine_insert_line`
- `_track_inserted_position`

Keep:
- `_resolve_insert_position` (still used by `_exec_move` and `_exec_move_edit`)
- `_build_edit_detail` (still used by `_exec_edit` and `_exec_move_edit`)
- `_build_apply_result` (still used by file/folder phases)
- `_log_apply_result` (still used by file/folder phases)

**Step 2: Run ruff check**

```bash
ruff check nagios_service.py
```

**Step 3: Run tests**

```bash
python3 -m pytest tests/ -v
```

Expected: All pass.

**Step 4: Commit**

```bash
git add nagios_service.py
git commit -m "refactor: remove old phase-based object apply methods

Removes apply_object_deletions, apply_object_moves, apply_object_edits,
apply_object_creations and their helper methods, now replaced by
apply_object_composite."
```

---

### Task 7: Update Documentation

**Files:**
- Modify: `.claude/STAGING_REFERENCE.md` (lines 96-111)
- Modify: `templates/docs/staging-system.html` (lines 55, 248-259)
- Check: `templates/docs/data-flow-staging.html`, `templates/docs/backend-services.html`, `templates/docs/architecture.html`

**Step 1: Update STAGING_REFERENCE.md**

Replace the "Apply Phase Order" section (lines 96-111) with:

```markdown
## Apply Phase Order

`POST /api/staging/apply` executes in this order:

1. **Folder creates** (parent → child sort)
2. **File creates**
3. **Object composite** — per-entity merged actions:
   - Deletions first (reverse line order per file)
   - Moves, edits, and move+edits
   - Creations last (append to target files)
4. **File moves**
5. **Folder moves**
6. **File deletions**
7. **Folder deletions** (child → parent sort)

Object operations on the same entity (e.g., edit + move) are merged into a single
composite action before executing. This prevents phase-ordering bugs where one phase's
assumptions about object state are violated by a prior phase.

Phase implemented as `service.apply_object_composite(staging_data)`.
```

**Step 2: Update staging-system.html**

Update the SVG text at line 55: change "10 phases" to "7 phases".

Update the ordered list at lines 248-259 to match the new phase order.

**Step 3: Check other docs for phase references**

Search `data-flow-staging.html`, `backend-services.html`, `architecture.html` for mentions of the old phase names or "10 phases". Update any references found.

**Step 4: Run ruff check on any Python changes**

```bash
ruff check .claude/STAGING_REFERENCE.md  # (markdown, skip)
```

**Step 5: Commit**

```bash
git add .claude/STAGING_REFERENCE.md templates/docs/staging-system.html
# Add any other docs files that changed
git commit -m "docs: update staging apply docs for composite phase system"
```

---

### Task 8: E2E Validation — Confirm Edit+Move Now Succeeds

**Files:**
- None (testing only, uses Playwright MCP)

**Step 1: Ensure clean state**

Reset sample-config to clean state:
```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor/sample-config && git checkout .
```

Restart Flask app if needed. Navigate to http://localhost:8080/explorer.

**Step 2: Edit an object**

Select `firewall-02` host in the tree. Edit `hostgroups` — add `,test-group` to the end. Save/stage the edit.

**Step 3: Move the same object**

Right-click `firewall-02`, select "Move to...", choose `services.cfg`. Confirm.

**Step 4: Apply**

Click Commit → Apply. Or use Explorer's apply.

**Step 5: Assert success**

Verify apply succeeds (no error dialog). Take screenshot.

**Step 6: Verify object in target file with edited attributes**

Read `sample-config/services.cfg` and verify:
- `firewall-02` host definition is present
- `hostgroups` field contains `test-group`

Read `sample-config/hosts.cfg` and verify:
- `firewall-02` host definition is NOT present

**Step 7: Reset state**

```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor/sample-config && git checkout .
```

---

### Task 9: E2E Regression — Other Operation Types

**Files:**
- None (testing only, uses Playwright MCP)

Test each operation type individually to confirm no regressions:

**Step 1: Edit only**

Select an object, edit an attribute, apply. Verify the change is on disk. Reset.

**Step 2: Move only**

Select an object, move to different file (no edit), apply. Verify object in new file. Reset.

**Step 3: Delete only**

Select an object, delete it, apply. Verify object is removed from disk. Reset.

**Step 4: Create only**

Create a new object in the Explorer, apply. Verify it appears on disk. Reset.

**Step 5: Multiple independent operations**

Edit one object, move a different object, delete a third. Apply. Verify all three operations applied correctly. Reset.

Take screenshots at each assertion point.

---

### Task 10: Final Quality Check

**Files:**
- All changed Python files

**Step 1: Run full ruff check**

```bash
ruff check nagios_service.py routes/staging.py
```

**Step 2: Run ruff format check**

```bash
ruff format --check nagios_service.py routes/staging.py
```

**Step 3: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

**Step 4: Final commit if any formatting fixes needed**

```bash
git add -A
git commit -m "style: fix lint/format issues from composite apply changes"
```
