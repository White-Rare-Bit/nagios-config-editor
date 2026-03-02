# Service API Reference

## NagiosService

| Function | What | Returns |
|----------|------|---------|
| get_objects() | Return all parsed objects | List[NagiosObject] |
| find_object_by_index(idx) | Get object by global index | Optional[NagiosObject] |
| find_object_by_stable_key(key) | Get object by stable key | Optional[Tuple[int, NagiosObject]] |
| search_objects(query, type, field, regex) | Search objects | List[NagiosObject] |
| get_object_stats() | Get counts by type and file | Dict |
| get_name_field(object_type) | Get name field for object type | str |
| transform_name(name, find, replace, prefix, suffix, regex) | Transform name with find/replace/prefix/suffix | Optional[str] |
| update_references(objects, old_name, new_name) | Update all references when object renamed | int (count updated) |
| create_object(target_file, obj_type, attrs, after_block_line) | Create new object | OperationResult |
| update_object(file, line, attrs, type) | Update object in place | OperationResult |
| delete_object(file, line) | Delete object | OperationResult |
| move_object(src_file, src_line, tgt_file, type, attrs, insert_line) | Move object between files | OperationResult |
| apply_folder_creations(staging_data, is_safe) | Create staged folders | OperationResult |
| apply_file_creations(staging_data, is_safe) | Create staged files | OperationResult |
| apply_object_deletions(staging_data) | Delete staged objects | OperationResult |
| apply_object_moves(staging_data) | Move staged objects | OperationResult |
| apply_object_edits(staging_data) | Edit staged objects | OperationResult |
| apply_object_creations(staging_data) | Create staged objects | OperationResult |
| apply_file_moves(staging_data, is_safe) | Move staged files | OperationResult |
| apply_folder_moves(staging_data, is_safe) | Move staged folders | OperationResult |
| apply_file_deletions(staging_data, is_safe) | Delete staged files | OperationResult |
| apply_folder_deletions(staging_data, is_safe) | Delete staged folders | OperationResult |
| get_typed_staging() | Get typed StagingState instance | Optional[StagingState] |
| reload() | Force parser reload | NagiosConfigParser |

## StagingManager

Delegates to composed managers: `sm.checksums` (ChecksumManager), `sm.undo` (UndoStackManager), `sm.file_ops` (FileOperationsStager).

| Function | What | Returns |
|----------|------|---------|
| get_staging() | Get current staging data | Optional[Dict] |
| save_staging(data) | Save staging atomically | OperationResult |
| save_staging_atomic(data, session_id, lock) | Save with atomic lock validation | OperationResult |
| clear_staging() | Clear all staging | OperationResult |
| has_staging() | Check if lock held | bool |
| get_staging_info() | Get summary with counts | Dict |
| get_lock_owner() | Get session owning lock | Optional[str] |
| can_modify(session_id) | Check if session can modify | bool |
| validate_or_acquire_lock(session_id) | Acquire lock if available | bool |
| get_lock_status(session_id) | Detailed lock info | Dict |
| get_empty_staging_structure() | Get empty staging with all fields | Dict |
| migrate_staging_schema(data) | Migrate to current schema version | Dict |
| add_to_undo_stack(type, data, desc, staging) | Push undo entry | Optional[str] |
| peek_undo_stack() | Peek without removing | Optional[Dict] |
| pop_undo_stack() | Pop and return undo entry | Optional[Dict] |
| get_undo_stack_count() | Get undo stack size | int |
| clear_undo_stack() | Clear all undo entries | OperationResult |
| compute_file_checksum(path) | SHA256 checksum | Optional[str] |
| compute_base_checksums(paths) | Compute checksums for files | Dict[str, str] |
| update_base_checksums(paths) | Store base checksums | OperationResult |
| detect_conflicts() | Find external modifications | List[Dict] |
| stage_file_creation(path) | Stage file create | OperationResult |
| stage_file_deletion(path) | Stage file delete | OperationResult |
| stage_file_move(src, tgt) | Stage file move | OperationResult |
| stage_folder_creation(path) | Stage folder create | OperationResult |
| stage_folder_deletion(path) | Stage folder delete | OperationResult |
| stage_folder_move(src, tgt) | Stage folder move | OperationResult |
| unstage_operation(op_id, op_type) | Remove staged op by ID | OperationResult |
| get_total_staged_count() | Total count of all staged ops | int |

## GitService

| Function | What | Returns |
|----------|------|---------|
| is_repo() | Check if inside git repo | OperationResult[bool] |
| get_user_identity() | Get configured user.name/email | OperationResult[Dict] |
| get_status(excluded_paths) | Git status porcelain | OperationResult[GitStatusResult] |
| get_diff(filepath, staged, full_file, context_lines) | Get diff for file/all | OperationResult[str] |
| get_workspace_diff(excluded) | Structured diff for commit dialog | OperationResult[Dict] |
| get_log(limit) | Commit history | OperationResult[Dict] |
| has_uncommitted_changes() | Check if dirty working dir | OperationResult[bool] |
| init_repo() | Initialize git repo | OperationResult |
| commit(message, files, user_name, user_email) | Stage and commit | OperationResult[Dict] |
| discard(filepath) | Discard changes to file | OperationResult[Dict] |
| discard_all() | Hard reset + clean | OperationResult[Dict] |
| restore(commit_hash) | Restore to specific commit | OperationResult[Dict] |
| clear_history(user_name, user_email) | Wipe history, fresh commit | OperationResult[Dict] |

## BackupManager

| Function | What | Returns |
|----------|------|---------|
| create_backup(desc, user_name, user_email) | Create zip backup with metadata | str (backup path) |
| list_backups() | List all backups (zip + legacy) | List[Dict] |
| restore_backup(name, user_name, user_email) | Restore from backup | Dict |
| delete_backup(name) | Delete specific backup | bool |
| cleanup_old_backups(keep_count) | Keep N recent, delete rest | int (deleted count) |

## OperationResult

```python
@dataclass
class OperationResult:
    success: bool
    error: Optional[str] = None
    data: Any = None
```

Usage:

```python
result = service.create_object(...)
if not result.success:
    return jsonify({'error': result.error}), 500
return jsonify({'success': True, 'data': result.data})
```

## Response Format

All API endpoints return JSON with this envelope:
```json
{"success": true|false, "data": ..., "error": "message if failed"}
```

### ApiClient normalization

`ApiClient.get/post/del()` wraps the **entire JSON body** as `result.data`. So:
- Backend returns: `{"success": true, "data": {"files": [...]}}`
- `result.data` = `{"success": true, "data": {"files": [...]}}`
- `result.data.data` = `{"files": [...]}`
- `result.data.files` = the actual files array

This means for endpoints that nest their payload under `data`, you need `result.data.data` to reach it. The `data.data || data` pattern handles both conventions.

### Error locations

- `result.error` — set by ApiClient from HTTP status text or response body `error` field
- `result.data.error` — some endpoints include error details inside the data payload
- Frontend convention: `result.data?.error || result.error || 'Fallback message'`

### HTTP status codes

| Code | Meaning | Frontend handling |
|------|---------|-------------------|
| 200 | Success | `result.success === true` |
| 400 | Invalid input | Error toast |
| 404 | Not found / nothing to undo | Checked explicitly for undo |
| 409 | Staging conflict | Error toast |
| 423 | Locked by another user | Lock banner shown |
| 500 | Internal error | Error toast |
