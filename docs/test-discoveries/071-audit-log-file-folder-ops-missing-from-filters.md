# 071 — Audit Log: File & Folder Operations Don't Appear Under Any Filter Chip

**Phase:** 23 — Audit Log
**Severity:** Major

## Steps to Reproduce

1. Create a new file or folder via the Files panel, move it, or delete it, then Apply.
2. Navigate to `/logs`. Try clicking "Creates", "Moves", or "Deletes" filter chips.

## Actual Behavior

File and folder operations are NOT matched by any filter chip. The filter chips use exact match against the `op` field:

| Filter chip | Checks | Expected match | Actual `op` value |
|-------------|--------|----------------|-------------------|
| Creates     | `op === 'create'` | file creation | `"file_creation"` ❌ |
| Creates     | `op === 'create'` | folder creation | `"folder_creation"` ❌ |
| Moves       | `op === 'move'` | file move | `"file_move"` ❌ |
| Moves       | `op === 'move'` | folder move | `"folder_move"` ❌ |
| Deletes     | `op === 'delete'` | file deletion | `"file_deletion"` ❌ |
| Deletes     | `op === 'delete'` | folder deletion | `"folder_deletion"` ❌ |

Root cause in `routes/staging.py:887–892`:
```python
op_type = audit_key.rstrip("s").split("_")[-1]
# "file_creations" → "file_creation" → split[-1] → "creation"  (not "create")
# "file_deletions" → "file_deletion" → split[-1] → "deletion"   (not "delete")
prefix = "file" if "file" in audit_key else "folder"
log_audit(..., op=f"{prefix}_{op_type}")
# Results: "file_creation", "folder_creation", "file_move", "folder_move",
#          "file_deletion", "folder_deletion"
```

The filter chip keys (`"create"`, `"move"`, `"delete"`) don't match the logged op suffixes (`"creation"`, `"deletion"`).

## Expected Behavior

File and folder operations should appear under their respective filter chips:
- File/folder creates → "Creates" chip
- File/folder moves → "Moves" chip
- File/folder deletes → "Deletes" chip

## Admin Impact

An admin clicking "Creates" to audit recent file/folder structure changes will see only object creations — all file and folder operations are invisible to the filter system. The only way to find file/folder ops is to remove all filters and scan the full log. For a busy production config with many changes, this makes file structure changes unfindable via filter.

## Fix Options

Either normalize the op values in the backend (`"file_create"`, `"folder_create"`, etc.) and update the filter to use prefix matching, or fix the `op_type` computation:
```python
# Fix: strip "ion" suffix or use a lookup table
op_map = {"creation": "create", "deletion": "delete", "move": "move"}
op_type = op_map.get(audit_key.rstrip("s").split("_")[-1], "unknown")
```
