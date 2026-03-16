# Multi-Root Config Discovery from nagios.cfg

## Problem

The editor currently takes a single directory path and recursively scans it for .cfg files. Real Nagios installations use `nagios.cfg` as the source of truth, with `cfg_dir` and `cfg_file` directives that can reference multiple directories across the filesystem. The editor should discover config paths from `nagios.cfg` rather than hardcoding a single directory.

## Decisions

1. **nagios.cfg is the single entry point** — the only required user setting. All config directories and files are discovered from its `cfg_dir` and `cfg_file` directives.
2. **Manual additions supported** — users can add extra directories via settings UI (`extra_cfg_dirs`).
3. **Protected files** — `nagios.cfg`, `resource.cfg`, and `cgi.cfg` are excluded from the shadow copy, the file tree, and all write operations. They are never editable.
4. **resource.cfg** — path auto-populated from `resource_file=` directive in nagios.cfg. Stored in settings.json. Displayed read-only in settings UI. Used by health checks only.
5. **No legacy code** — the old `nagios_config_path` single-directory setting is dropped entirely. No migration path needed (no existing users).
6. **cfg_file handling** — individual `cfg_file` entries are grouped by parent directory. Each unique parent directory becomes a root, same as `cfg_dir` entries. Deduplicated.
7. **Inaccessible directories** — shown red in settings UI with OS error reason (e.g., "Permission denied", "Directory not found"). Not shown in explorer tree.

## Configuration Model

### settings.json

```json
{
  "paths": {
    "nagios_cfg": "/etc/nagios/nagios.cfg",
    "nagios_bin": "/usr/local/nagios/bin/nagios",
    "backup_path": null,
    "shadow_path": null,
    "resource_cfg": "/etc/nagios/resources.cfg",
    "extra_cfg_dirs": [],
    "primary_dir": ""
  }
}
```

### PathsConfig dataclass

- `nagios_cfg` — required, the one entry point
- `nagios_bin` — path to Nagios binary for validation
- `backup_path` — user-configured backup location (null = default)
- `shadow_path` — user-configured shadow location (null = default)
- `resource_cfg` — auto-populated from nagios.cfg, persisted, displayed read-only
- `extra_cfg_dirs` — manually added directories (persisted)
- `primary_dir` — where new files go; defaults to first cfg_dir from nagios.cfg if empty; user can override

### Discovery flow

1. Parse `nagios_cfg` → extract `cfg_dir[]`, `cfg_file[]`, `resource_file`
2. Derive directories from `cfg_file` entries (group by parent dir)
3. Deduplicate against `cfg_dir` entries
4. Merge with `extra_cfg_dirs`
5. Update `resource_cfg` in settings from `resource_file` directive
6. Check each directory for accessibility → flag inaccessible ones with error reason

## Parser Changes

`NagiosConfigParser` changes from single `config_path` to multi-root:

```python
class NagiosConfigParser:
    def __init__(self, cfg_dirs: list[str], cfg_files: list[str]):
        self.cfg_dirs = [Path(d).resolve() for d in cfg_dirs]
        self.cfg_files = [Path(f).resolve() for f in cfg_files]

    def parse_all(self):
        seen = set()
        # Individual cfg_file entries first
        for f in self.cfg_files:
            if f.exists() and str(f) not in seen:
                seen.add(str(f))
                self.parse_file(str(f))
        # Then recurse cfg_dir entries
        for d in self.cfg_dirs:
            for cfg in d.rglob("*.cfg"):
                if str(cfg) not in seen:
                    seen.add(str(cfg))
                    self.parse_file(str(cfg))
```

- `seen` set prevents double-parsing
- Existing skip logic (backups, timestamps, staging dirs) preserved
- Protected files excluded before reaching the parser

## Shadow Copy with Multiple Roots

Unified shadow directory with flattened namespace:

```
.shadow/
  config/
    etc_nagios_servers/      ← from /etc/nagios/servers/
    etc_nagios_switches/     ← from /etc/nagios/switches/
    opt_custom_nagios/       ← from /opt/custom/nagios/
  root_map.json              ← bidirectional path mapping
  checksums.json
  snapshots/
```

### root_map.json

```json
{
  "etc_nagios_servers": "/etc/nagios/servers",
  "etc_nagios_switches": "/etc/nagios/switches"
}
```

### Operations

- **Create shadow:** Copy each source directory into its mapped subdirectory
- **Mutations:** Write to shadow files, snapshot before mutation (same as today)
- **Apply:** Iterate changed files, resolve back to original paths via root_map.json, atomic write each changed file only (surgical — unchanged files untouched)
- **Destroy:** Remove entire `.shadow/` directory
- **Checksums:** Keyed by `shadow_subdir/rel_path` for global uniqueness
- **Protected files:** `nagios.cfg`, `resource.cfg`, `cgi.cfg` never copied into shadow

## File Tree (Explorer UI)

- Multiple root nodes, one per accessible config directory
- Sources from `cfg_dir`, `cfg_file` parent dirs, and `extra_cfg_dirs` (deduplicated)
- Each root labeled with its full path, sorted alphabetically
- Protected files excluded from tree
- New file creation defaults to `primary_dir`

## Settings UI

```
┌─ Nagios Configuration ──────────────────────────────┐
│  nagios.cfg path:  [/etc/nagios/nagios.cfg] [Browse] │
│                                                       │
│  Discovered directories:                              │
│    ✓ /etc/nagios/servers/                             │
│    ✓ /etc/nagios/switches/                            │
│    ✗ /etc/nagios/printers/  (red)                     │
│      - Directory not found                            │
│                                                       │
│  Additional directories:                              │
│    /opt/custom/nagios/                  [Remove]      │
│    [Add directory...]                                 │
│                                                       │
│  Primary directory:  [/etc/nagios/servers/ ▾]         │
│                                                       │
│  Resource file:  /etc/nagios/resources.cfg (read-only)│
├─ Paths ──────────────────────────────────────────────┤
│  Nagios binary:  [/usr/local/nagios/bin/nagios]       │
│  Backup path:    [                          ]         │
│  Shadow path:    [                          ]         │
└───────────────────────────────────────────────────────┘
```

- Changing nagios.cfg path triggers re-discovery
- Discovered directories list is read-only (derived from nagios.cfg)
- Inaccessible dirs shown red with OS error reason
- Primary directory dropdown lists all accessible directories

## API Changes

### GET /api/settings response adds `discovered`:

```json
{
  "paths": { ... },
  "discovered": {
    "cfg_dirs": [
      {"path": "/etc/nagios/servers", "accessible": true, "error": null},
      {"path": "/etc/nagios/printers", "accessible": false, "error": "Directory not found"}
    ],
    "resource_file": "/etc/nagios/resources.cfg"
  }
}
```

### POST /api/settings

Accepts `paths` only — `discovered` is always computed server-side.

### GET /api/files, /api/folders

Return files/folders across all roots. Response adds `roots` field listing active directories.

### GET /api/objects

Returns objects from all accessible directories. No format change — objects carry absolute `source_file` paths.

## What Doesn't Change

- Object CRUD — works on absolute file paths, multi-root transparent
- Undo/snapshot system — file-level, paths relative to shadow root
- Diff view — per-file diffs, just more files
- Git integration — independent of config discovery
- Validation (`nagios -v`) — already uses nagios_cfg path
- Stable keys — absolute paths, unique across roots
- Health checks — already accept config paths via context
