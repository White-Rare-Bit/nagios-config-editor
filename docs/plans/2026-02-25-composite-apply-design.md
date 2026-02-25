# Per-Entity Composite Apply Design

## Problem

The staging apply system uses fixed phase ordering (all moves, then all edits, etc.). When the same object appears in multiple phases (e.g., edited AND moved), phases make assumptions about object state that prior phases may have violated.

Concrete bug: editing an object then moving it fails because objectMoves runs before objectEdits. The move snapshot stores edited attributes, but on-disk attributes are still original. The exact-match lookup fails with "Could not find object to move."

This is a class of bugs, not a single bug. Every combination of phases touching the same object is a potential failure.

## Research

Established systems handle this differently:

- **SQLAlchemy Unit of Work**: Groups by entity. One entry per entity, one SQL statement per entity. Merges all changes before flush.
- **Hibernate ActionQueue**: Groups by operation type (like our current system). Only major ORM that does this, motivated by JDBC batching, not correctness.
- **Terraform**: Groups by entity. One graph node per resource. `moved` blocks are pre-graph state transforms, not operations.
- **Django Migrations**: Pairwise reduction — merges operations on same entity (e.g., AddField + AlterField = AddField with new definition).
- **Puppet**: Refuses duplicate declarations entirely. One authoritative declaration per resource.

Our current system matches Hibernate's pattern — the only system that groups by operation type, and it does so for performance reasons that don't apply to us.

## Design: Per-Entity Composite Actions

Replace the 4 object phases (delete, move, edit, create) with a single composite phase that merges per-entity before executing.

### Composite Action Model

```python
@dataclass
class CompositeAction:
    action_type: str          # "delete" | "edit" | "move" | "move_edit" | "create"
    stable_key: str           # "source_file|object_type|name"
    object_type: str
    object_name: str
    source_file: str | None   # Current on-disk location
    original_attrs: dict | None  # On-disk attributes (for matching)
    final_attrs: dict | None     # Desired end-state attributes
    target_file: str | None   # Destination file (moves)
    insert_position: float | None
    inline_comments: dict | None
    global_index: int | None  # For deletion lookup
```

### Merge Logic

Before applying, scan staging data and merge per stable key:

1. Index `pendingEdits` by stable key (derived from entry's `object` metadata)
2. Index `stagedMoves` by stable key (already keyed this way)
3. Index `stagedObjectDeletions` by stable key (resolve via parser)
4. For each unique key, merge:

| Staged ops | Composite action | `original_attrs` source |
|-----------|-----------------|------------------------|
| Edit only | `edit` | Not needed (uses stable key identity) |
| Move only | `move` | Parser (current on-disk state) |
| Edit + Move | `move_edit` | pendingEdit's `original` field |
| Delete only | `delete` | Not needed |
| Create only | `create` | Not applicable |

### New Phase Order

```
1. Folder creations        (unchanged)
2. File creations          (unchanged)
3. Object composite        (NEW — replaces phases 3-6)
     Execution order within:
     a. Deletes first
     b. Moves + Edits + MoveEdits
     c. Creates last
4. File moves              (unchanged)
5. Folder moves            (unchanged)
6. File deletions          (unchanged)
7. Folder deletions        (unchanged)
```

### Composite Action Execution

- **delete**: Find by globalIndex, call `delete_object_from_file`. Same as current.
- **edit**: Find by stable key (source_file + type + name), merge `final_attrs`, call `edit_object_in_file`.
- **move**: Find by `original_attrs` (exact match — always on-disk values), call `move_object_between_files`.
- **move_edit**: Find by `original_attrs`, move to target file, then edit in new location with `final_attrs`. Two file ops, reuses existing functions.
- **create**: Call `add_object_to_file`. Same as current.

Parser reloads after each action that modifies files (same as current move logic).

### What Changes

**Replaced:**
- `apply_object_deletions`, `apply_object_moves`, `apply_object_edits`, `apply_object_creations` — replaced by `apply_object_composite`
- `_find_object_by_attrs`, `_find_object_by_entry` — replaced by unified identity resolution
- `_normalize_staged_moves`, `_determine_insert_line`, `_track_inserted_position` — folded into composite execution

**Added:**
- `_build_composite_actions(staging_data)` — merge logic
- `_execute_composite_action(action)` — dispatch to action type handlers
- `CompositeAction` dataclass

**Unchanged:**
- All 6 file/folder phase methods
- `_handle_apply_failure`, `_create_pre_apply_backup`, `_apply_post_phase_reference_updates`
- Staging manager, staging data format, frontend staging logic
- Undo system, API contract (response shape)

### Logging

Three layers, all preserved:

**App log**: Single summary line per composite phase with per-type subtotals:
```
apply_object_composite: deletes=2 moves=1 edits=2 move_edits=1 creates=0 errors=0 result=success
```

**Audit trail (JSONL)**: `move_edit` composites emit two audit entries — one `move` and one `edit` with field-level changes. No new audit action types. Existing `_write_apply_audit_log` updated to handle combined detail entries.

**API response**: Flattened summary for backward compatibility:
```python
{"objectDeletions": 2, "objectMoves": 1, "objectEdits": 2,
 "objectMoveEdits": 1, "objectCreations": 0}
```

### Documentation Updates

1. `.claude/STAGING_REFERENCE.md` — Replace 10-step phase list with 7-step structure
2. `templates/docs/staging-system.html` — Update "Applying Changes" section and SVG diagram
3. Check `data-flow-staging.html`, `backend-services.html`, `architecture.html` for phase references

### Testing and Quality

**Pre-implementation E2E (Playwright)** — reproduces the bug:
1. Edit an object (change an attribute)
2. Move that same object to a different file
3. Apply
4. Assert: fails during objectMoves phase

**Post-implementation E2E (Playwright)** — validates the fix:
1. Same steps: edit, move, apply
2. Assert: apply succeeds
3. Assert: object in target file with edited attributes
4. Assert: object not in source file

**Regression E2E (Playwright):**
- Edit only
- Move only
- Delete only
- Create only
- Multiple independent operations in one apply

**Code quality:**
- `ruff check` and `ruff format` on all changed files
- `python3 -m pytest tests/ -v` — existing unit tests pass
