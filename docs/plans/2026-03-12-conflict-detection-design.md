# Conflict Detection for Shadow Copy Apply

**Goal:** Detect when original `.cfg` files have been modified externally (by another admin, config management tool, or Nagios itself) between shadow creation and apply, and warn the user before overwriting.

**Architecture:** SHA-256 content hashes of all `.cfg` files are stored at shadow creation time. Before apply, originals are rehashed and compared. Conflicts block apply with a 409 response; the user can force-apply to override.

---

## Data Storage

At shadow creation time, `create_shadow()` hashes every `.cfg` file in the original config directory and writes `checksums.json` alongside `lock.json`:

```json
{
  "hosts.cfg": "a1b2c3...",
  "services/web.cfg": "d4e5f6...",
}
```

SHA-256, hex-encoded. Relative paths as keys (same format used everywhere else in the system).

---

## Apply Flow

`apply()` gains a conflict detection step before writing any files:

1. Rehash current originals, compare against `checksums.json`
2. If no conflicts → apply as normal
3. If conflicts → return `OperationResult(success=False, error="conflicts", data={"conflicts": [...]})` with conflicted file paths
4. The apply route returns this as a **409 Conflict** response with the file list
5. Frontend shows a warning dialog listing conflicted files, with two buttons: **Force Apply** (overwrites) and **Cancel**
6. Force Apply re-calls the apply endpoint with `?force=true` query param, which skips the checksum comparison

Method signature: `apply(backup_manager=None, force=False)`

---

## Edge Cases

- **Deleted original files**: File existed at shadow creation but deleted externally → conflict (checksum present but file missing). Reported as `"file deleted externally"`.
- **New original files**: Files that didn't exist at shadow creation but appear now → ignored. Not in `checksums.json`, nothing to conflict with. Apply won't touch them unless shadow also created a file at that path.
- **Checksums.json missing**: Older shadows created before this feature won't have the file. Treat as no conflicts (backwards compatible, graceful degradation).
