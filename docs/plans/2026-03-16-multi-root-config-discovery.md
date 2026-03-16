# Multi-Root Config Discovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single-directory config model with nagios.cfg-driven multi-root discovery, where all config directories and files are derived from `cfg_dir`/`cfg_file` directives.

**Architecture:** `nagios.cfg` is the single entry point. A discovery layer parses it to produce lists of `cfg_dirs` and `cfg_files`, which flow through the parser, service, and shadow copy manager. Protected files (`nagios.cfg`, `resource.cfg`, `cgi.cfg`) are never editable or shown in the file tree.

**Tech Stack:** Python/Flask backend, vanilla JS frontend, existing test infrastructure (`pytest`)

**Design doc:** `docs/plans/2026-03-16-multi-root-config-discovery-design.md`

---

### Task 1: Update PathsConfig dataclass and serialization

**Files:**
- Modify: `server_config.py:35-86` (PathsConfig, ServerConfig.from_dict, ServerConfig.to_dict)
- Test: `tests/test_server_config.py` (create if needed)

**Step 1: Write failing tests for new PathsConfig fields**

```python
# tests/test_server_config.py
from server_config import PathsConfig, ServerConfig, load_config, save_config

class TestPathsConfig:
    def test_new_fields_have_defaults(self):
        p = PathsConfig()
        assert p.nagios_cfg == ""
        assert p.nagios_bin == "/usr/local/nagios/bin/nagios"
        assert p.backup_path is None
        assert p.shadow_path is None
        assert p.resource_cfg == ""
        assert p.extra_cfg_dirs == []
        assert p.primary_dir == ""

    def test_nagios_config_path_removed(self):
        """nagios_config_path field no longer exists."""
        p = PathsConfig()
        assert not hasattr(p, "nagios_config_path")

    def test_round_trip_serialization(self):
        config = ServerConfig()
        config.paths.nagios_cfg = "/etc/nagios/nagios.cfg"
        config.paths.extra_cfg_dirs = ["/opt/custom"]
        config.paths.primary_dir = "/etc/nagios/servers"
        config.paths.resource_cfg = "/etc/nagios/resources.cfg"
        d = config.to_dict()
        restored = ServerConfig.from_dict(d)
        assert restored.paths.nagios_cfg == "/etc/nagios/nagios.cfg"
        assert restored.paths.extra_cfg_dirs == ["/opt/custom"]
        assert restored.paths.primary_dir == "/etc/nagios/servers"
        assert restored.paths.resource_cfg == "/etc/nagios/resources.cfg"

    def test_from_dict_with_missing_new_fields(self):
        """Old settings.json without new fields should use defaults."""
        d = {"paths": {"nagios_bin": "/usr/bin/nagios"}}
        config = ServerConfig.from_dict(d)
        assert config.paths.extra_cfg_dirs == []
        assert config.paths.primary_dir == ""
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_server_config.py -v`
Expected: FAIL — `nagios_config_path` still exists, `extra_cfg_dirs`/`primary_dir` not defined

**Step 3: Update PathsConfig dataclass**

In `server_config.py:35-43`, replace the PathsConfig dataclass:

```python
@dataclass
class PathsConfig:
    """Path configuration settings."""

    nagios_cfg: str = ""
    nagios_bin: str = "/usr/local/nagios/bin/nagios"
    backup_path: str | None = None
    shadow_path: str | None = None
    resource_cfg: str = ""
    extra_cfg_dirs: list[str] = field(default_factory=list)
    primary_dir: str = ""
```

**Step 4: Update ServerConfig.from_dict (lines 62-86)**

Update the `from_dict` method to handle new fields:

```python
paths=PathsConfig(
    nagios_cfg=paths_data.get("nagios_cfg", ""),
    nagios_bin=paths_data.get("nagios_bin", "/usr/local/nagios/bin/nagios"),
    backup_path=paths_data.get("backup_path"),
    shadow_path=paths_data.get("shadow_path"),
    resource_cfg=paths_data.get("resource_cfg", ""),
    extra_cfg_dirs=paths_data.get("extra_cfg_dirs", []),
    primary_dir=paths_data.get("primary_dir", ""),
),
```

**Step 5: Remove nagios_config_path property and setter (lines 89-95)**

Delete the `nagios_config_path` property and setter from ServerConfig. Also remove `shadow_path` property/setter since it's still accessible via `config.paths.shadow_path`.

Keep `nagios_bin` and `nagios_cfg` convenience properties if routes use them directly — check usages first via grep.

**Step 6: Update _apply_env_overrides (lines 136-160)**

Remove `NAGIOS_CONFIG_PATH` env var handling. Keep `NAGIOS_CFG`, `NAGIOS_BIN`, `BACKUP_PATH`, `NBE_SHADOW_PATH`.

**Step 7: Update _apply_paths_updates (lines 217-231)**

Update the field list to match new PathsConfig fields. Remove `nagios_config_path` handling. Add `extra_cfg_dirs` and `primary_dir`.

**Step 8: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_server_config.py -v`
Expected: PASS

**Step 9: Run full test suite to see what breaks**

Run: `python3 -m pytest tests/ -v`
Expected: Some failures in tests that reference `nagios_config_path` — note these for later tasks.

**Step 10: Commit**

```bash
git add server_config.py tests/test_server_config.py
git commit -m "refactor: replace nagios_config_path with multi-root config model"
```

---

### Task 2: Add discovery module — resolve config roots from nagios.cfg

**Files:**
- Modify: `nagios_cfg.py:10-42` (extend parse_nagios_cfg)
- Create: `config_discovery.py`
- Test: `tests/test_config_discovery.py`

**Step 1: Write failing test for resource_file extraction**

```python
# tests/test_config_discovery.py
import os
import tempfile
from nagios_cfg import parse_nagios_cfg

class TestParseNagiosCfg:
    def test_extracts_resource_file(self):
        """parse_nagios_cfg should also extract resource_file directive."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
            f.write("cfg_dir=/etc/nagios/servers\n")
            f.write("resource_file=/etc/nagios/resources.cfg\n")
            f.name
        try:
            result = parse_nagios_cfg(f.name)
            assert result["cfg_dirs"] == ["/etc/nagios/servers"]
            assert result["resource_file"] == "/etc/nagios/resources.cfg"
        finally:
            os.unlink(f.name)

    def test_resource_file_defaults_empty(self):
        """Missing resource_file returns empty string."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
            f.write("cfg_dir=/etc/nagios/servers\n")
            f.name
        try:
            result = parse_nagios_cfg(f.name)
            assert result["resource_file"] == ""
        finally:
            os.unlink(f.name)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config_discovery.py::TestParseNagiosCfg -v`
Expected: FAIL — `resource_file` key missing from result

**Step 3: Extend parse_nagios_cfg to extract resource_file**

In `nagios_cfg.py`, update `parse_nagios_cfg`:

```python
def parse_nagios_cfg(nagios_cfg_path):
    result = {"cfg_dirs": [], "cfg_files": [], "resource_file": ""}
    # ... existing parsing loop ...
                if key == "cfg_dir":
                    result["cfg_dirs"].append(value)
                elif key == "cfg_file":
                    result["cfg_files"].append(value)
                elif key == "resource_file":
                    result["resource_file"] = value
    return result
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_config_discovery.py::TestParseNagiosCfg -v`
Expected: PASS

**Step 5: Write failing tests for discover_config_roots**

```python
# tests/test_config_discovery.py (append)
from config_discovery import discover_config_roots, PROTECTED_FILENAMES

class TestDiscoverConfigRoots:
    def test_discovers_cfg_dirs(self, tmp_path):
        servers = tmp_path / "servers"
        servers.mkdir()
        (servers / "hosts.cfg").write_text("define host {}\n")

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(f"cfg_dir={servers}\n")

        result = discover_config_roots(str(nagios_cfg))
        accessible = [d for d in result["directories"] if d["accessible"]]
        assert len(accessible) == 1
        assert accessible[0]["path"] == str(servers)

    def test_derives_dirs_from_cfg_files(self, tmp_path):
        """cfg_file entries grouped by parent directory."""
        (tmp_path / "hosts.cfg").write_text("define host {}\n")
        (tmp_path / "services.cfg").write_text("define service {}\n")

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(
            f"cfg_file={tmp_path}/hosts.cfg\n"
            f"cfg_file={tmp_path}/services.cfg\n"
        )

        result = discover_config_roots(str(nagios_cfg))
        accessible = [d for d in result["directories"] if d["accessible"]]
        assert len(accessible) == 1
        assert accessible[0]["path"] == str(tmp_path)

    def test_deduplicates_cfg_dir_and_cfg_file_parents(self, tmp_path):
        servers = tmp_path / "servers"
        servers.mkdir()
        (servers / "hosts.cfg").write_text("define host {}\n")

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(
            f"cfg_dir={servers}\n"
            f"cfg_file={servers}/hosts.cfg\n"
        )

        result = discover_config_roots(str(nagios_cfg))
        accessible = [d for d in result["directories"] if d["accessible"]]
        assert len(accessible) == 1

    def test_merges_extra_dirs(self, tmp_path):
        custom = tmp_path / "custom"
        custom.mkdir()

        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text("")

        result = discover_config_roots(str(nagios_cfg), extra_cfg_dirs=[str(custom)])
        accessible = [d for d in result["directories"] if d["accessible"]]
        assert any(d["path"] == str(custom) for d in accessible)

    def test_flags_inaccessible_dirs(self, tmp_path):
        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text("cfg_dir=/nonexistent/path\n")

        result = discover_config_roots(str(nagios_cfg))
        assert len(result["directories"]) == 1
        assert result["directories"][0]["accessible"] is False
        assert result["directories"][0]["error"] is not None

    def test_extracts_resource_file(self, tmp_path):
        nagios_cfg = tmp_path / "nagios.cfg"
        res_file = tmp_path / "resources.cfg"
        res_file.write_text("$USER1$=/usr/lib/nagios/plugins\n")
        nagios_cfg.write_text(f"resource_file={res_file}\n")

        result = discover_config_roots(str(nagios_cfg))
        assert result["resource_file"] == str(res_file)

    def test_protected_filenames(self):
        assert "nagios.cfg" in PROTECTED_FILENAMES
        assert "resource.cfg" in PROTECTED_FILENAMES
        assert "cgi.cfg" in PROTECTED_FILENAMES

    def test_returns_cfg_files_list(self, tmp_path):
        """Individual cfg_file paths are returned for the parser."""
        (tmp_path / "hosts.cfg").write_text("define host {}\n")
        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(f"cfg_file={tmp_path}/hosts.cfg\n")

        result = discover_config_roots(str(nagios_cfg))
        assert str(tmp_path / "hosts.cfg") in result["cfg_files"]

    def test_empty_nagios_cfg_path(self):
        result = discover_config_roots("")
        assert result["directories"] == []
        assert result["cfg_files"] == []
        assert result["resource_file"] == ""
```

**Step 6: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_config_discovery.py::TestDiscoverConfigRoots -v`
Expected: FAIL — `config_discovery` module doesn't exist

**Step 7: Create config_discovery.py**

```python
"""Config discovery — resolves config roots from nagios.cfg.

Parses nagios.cfg for cfg_dir, cfg_file, and resource_file directives,
then builds a unified list of config directories with accessibility checks.
"""

import os
from nagios_cfg import parse_nagios_cfg

# Files that are never editable, never shown in file tree, never copied to shadow
PROTECTED_FILENAMES = frozenset({"nagios.cfg", "resource.cfg", "cgi.cfg"})


def discover_config_roots(nagios_cfg_path, extra_cfg_dirs=None):
    """Discover config directories and files from nagios.cfg.

    Args:
        nagios_cfg_path: Path to nagios.cfg file.
        extra_cfg_dirs: Optional list of additional directories to include.

    Returns:
        dict with keys:
            directories: list of {path, accessible, error, source}
            cfg_files: list of individual cfg_file paths (for parser)
            resource_file: path to resource.cfg (or "")
    """
    if not nagios_cfg_path:
        return {"directories": [], "cfg_files": [], "resource_file": ""}

    parsed = parse_nagios_cfg(nagios_cfg_path)

    # Collect directories from cfg_dir directives
    seen_dirs = set()
    directories = []

    for d in parsed["cfg_dirs"]:
        abs_d = os.path.abspath(d)
        if abs_d not in seen_dirs:
            seen_dirs.add(abs_d)
            directories.append(_check_directory(abs_d, source="nagios.cfg"))

    # Derive directories from cfg_file parent dirs
    for f in parsed["cfg_files"]:
        abs_f = os.path.abspath(f)
        parent = os.path.dirname(abs_f)
        if parent not in seen_dirs:
            seen_dirs.add(parent)
            directories.append(_check_directory(parent, source="nagios.cfg"))

    # Merge extra_cfg_dirs
    for d in (extra_cfg_dirs or []):
        abs_d = os.path.abspath(d)
        if abs_d not in seen_dirs:
            seen_dirs.add(abs_d)
            directories.append(_check_directory(abs_d, source="manual"))

    # Resolve cfg_files to absolute paths
    cfg_files = [os.path.abspath(f) for f in parsed["cfg_files"]]

    # Resolve resource_file
    resource_file = parsed.get("resource_file", "")
    if resource_file:
        resource_file = os.path.abspath(resource_file)

    return {
        "directories": directories,
        "cfg_files": cfg_files,
        "resource_file": resource_file,
    }


def _check_directory(path, source):
    """Check if a directory is accessible and return status dict."""
    if not os.path.exists(path):
        return {"path": path, "accessible": False, "error": "Directory not found", "source": source}
    if not os.path.isdir(path):
        return {"path": path, "accessible": False, "error": "Not a directory", "source": source}
    if not os.access(path, os.R_OK):
        return {"path": path, "accessible": False, "error": "Permission denied", "source": source}
    return {"path": path, "accessible": True, "error": None, "source": source}
```

**Step 8: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config_discovery.py -v`
Expected: PASS

**Step 9: Commit**

```bash
git add nagios_cfg.py config_discovery.py tests/test_config_discovery.py
git commit -m "feat: add config discovery module for multi-root nagios.cfg parsing"
```

---

### Task 3: Update NagiosConfigParser for multi-root

**Files:**
- Modify: `nagios_parser.py:44-74` (__init__ and parse_all)
- Test: `tests/test_parser_multiroot.py`

**Step 1: Write failing tests for multi-root parser**

```python
# tests/test_parser_multiroot.py
import os
from nagios_parser import NagiosConfigParser

class TestMultiRootParser:
    def test_parses_multiple_cfg_dirs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text('define host {\n    host_name server1\n}\n')
        (dir_b / "hosts.cfg").write_text('define host {\n    host_name server2\n}\n')

        parser = NagiosConfigParser(cfg_dirs=[str(dir_a), str(dir_b)])
        parser.parse_all()
        names = {o.attributes.get("host_name") for o in parser.objects}
        assert names == {"server1", "server2"}

    def test_parses_individual_cfg_files(self, tmp_path):
        f = tmp_path / "commands.cfg"
        f.write_text('define command {\n    command_name check_ping\n}\n')

        parser = NagiosConfigParser(cfg_files=[str(f)])
        parser.parse_all()
        assert len(parser.objects) == 1
        assert parser.objects[0].attributes["command_name"] == "check_ping"

    def test_deduplicates_files(self, tmp_path):
        """File listed in both cfg_file and cfg_dir should be parsed once."""
        (tmp_path / "hosts.cfg").write_text('define host {\n    host_name server1\n}\n')

        parser = NagiosConfigParser(cfg_dirs=[str(tmp_path)], cfg_files=[str(tmp_path / "hosts.cfg")])
        parser.parse_all()
        assert len(parser.objects) == 1

    def test_skips_nonexistent_dirs(self, tmp_path):
        parser = NagiosConfigParser(cfg_dirs=[str(tmp_path / "nonexistent")])
        parser.parse_all()
        assert parser.objects == []

    def test_skips_nonexistent_files(self, tmp_path):
        parser = NagiosConfigParser(cfg_files=[str(tmp_path / "missing.cfg")])
        parser.parse_all()
        assert parser.objects == []

    def test_backward_compat_single_dir(self, tmp_path):
        """Single positional arg still works as config_path."""
        (tmp_path / "hosts.cfg").write_text('define host {\n    host_name server1\n}\n')

        parser = NagiosConfigParser(str(tmp_path))
        parser.parse_all()
        assert len(parser.objects) == 1

    def test_preserves_skip_logic(self, tmp_path):
        """Backup and staging files still skipped."""
        d = tmp_path / "configs"
        d.mkdir()
        (d / "hosts.cfg").write_text('define host {\n    host_name server1\n}\n')
        bak = d / "backups"
        bak.mkdir()
        (bak / "old.cfg").write_text('define host {\n    host_name old\n}\n')

        parser = NagiosConfigParser(cfg_dirs=[str(d)])
        parser.parse_all()
        names = {o.attributes.get("host_name") for o in parser.objects}
        assert "old" not in names
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_parser_multiroot.py -v`
Expected: FAIL — NagiosConfigParser doesn't accept `cfg_dirs`/`cfg_files` kwargs

**Step 3: Update NagiosConfigParser.__init__ and parse_all**

In `nagios_parser.py`, replace `__init__` and `parse_all`:

```python
def __init__(self, config_path=None, *, cfg_dirs=None, cfg_files=None):
    """Initialize parser.

    Args:
        config_path: Single directory (backward compat). Treated as sole cfg_dir.
        cfg_dirs: List of directories to recursively scan for .cfg files.
        cfg_files: List of individual .cfg file paths to parse.
    """
    if config_path is not None:
        self.cfg_dirs = [Path(config_path).resolve()]
        self.cfg_files = []
    else:
        self.cfg_dirs = [Path(d).resolve() for d in (cfg_dirs or [])]
        self.cfg_files = [Path(f).resolve() for f in (cfg_files or [])]
    # Keep config_path for backward compat (first dir or None)
    self.config_path = self.cfg_dirs[0] if self.cfg_dirs else None
    self.objects: list[NagiosObject] = []
    self.files_parsed: list[str] = []

def parse_all(self) -> list[NagiosObject]:
    """Parse all config files from cfg_dirs and cfg_files."""
    self.objects = []
    self.files_parsed = []
    seen: set[str] = set()

    # Parse individual cfg_file entries first
    for f in self.cfg_files:
        resolved = str(f)
        if f.exists() and resolved not in seen:
            seen.add(resolved)
            self.parse_file(resolved)

    # Then recurse cfg_dir entries
    for d in self.cfg_dirs:
        if not d.exists():
            continue
        for cfg_file in d.rglob("*.cfg"):
            file_path = str(cfg_file)
            if file_path in seen:
                continue
            # Skip backup files and directories
            if "/backups/" in file_path or "/backup/" in file_path:
                continue
            if ".bak" in file_path or ".backup" in file_path:
                continue
            # Skip staging directories
            if "/.staging/" in file_path or "/.nagios_staging/" in file_path:
                continue
            # Skip timestamp-patterned files
            parts = cfg_file.name
            if any(
                part.isdigit() and len(part) >= _MIN_TIMESTAMP_DIGITS
                for part in parts.replace("_", ".").split(".")
            ):
                continue
            seen.add(file_path)
            self.parse_file(file_path)

    return self.objects
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_parser_multiroot.py -v`
Expected: PASS

**Step 5: Run existing parser tests to verify backward compat**

Run: `python3 -m pytest tests/ -k "parser" -v`
Expected: PASS (single-directory usage unchanged)

**Step 6: Commit**

```bash
git add nagios_parser.py tests/test_parser_multiroot.py
git commit -m "feat: multi-root parsing with cfg_dirs and cfg_files support"
```

---

### Task 4: Update NagiosService for multi-root

**Files:**
- Modify: `nagios_service.py:33-71` (__init__, config_path, parser, reload)
- Test: `tests/test_service_multiroot.py`

**Step 1: Write failing tests**

```python
# tests/test_service_multiroot.py
from nagios_service import NagiosService

class TestNagiosServiceMultiRoot:
    def test_init_with_cfg_dirs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text('define host {\n    host_name h1\n}\n')
        (dir_b / "hosts.cfg").write_text('define host {\n    host_name h2\n}\n')

        svc = NagiosService(cfg_dirs=[str(dir_a), str(dir_b)])
        objects = svc.get_objects()
        names = {o.attributes.get("host_name") for o in objects}
        assert names == {"h1", "h2"}

    def test_init_with_cfg_files(self, tmp_path):
        f = tmp_path / "commands.cfg"
        f.write_text('define command {\n    command_name check_ping\n}\n')

        svc = NagiosService(cfg_files=[str(f)])
        objects = svc.get_objects()
        assert len(objects) == 1

    def test_backward_compat_single_path(self, tmp_path):
        (tmp_path / "hosts.cfg").write_text('define host {\n    host_name h1\n}\n')
        svc = NagiosService(config_path=str(tmp_path))
        assert len(svc.get_objects()) == 1

    def test_reload_preserves_multi_root(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text('define host {\n    host_name h1\n}\n')

        svc = NagiosService(cfg_dirs=[str(dir_a)])
        svc.get_objects()  # trigger initial parse
        # Add a new file
        (dir_a / "services.cfg").write_text('define service {\n    service_description svc1\n    host_name h1\n    check_command check_ping\n}\n')
        svc.reload()
        assert len(svc.get_objects()) == 2

    def test_config_path_returns_first_dir(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        svc = NagiosService(cfg_dirs=[str(dir_a), str(dir_b)])
        assert svc.config_path == str(dir_a.resolve())
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_service_multiroot.py -v`
Expected: FAIL — NagiosService doesn't accept cfg_dirs/cfg_files

**Step 3: Update NagiosService**

```python
class NagiosService:
    def __init__(self, config_path=None, *, cfg_dirs=None, cfg_files=None):
        if config_path is not None:
            self._cfg_dirs = [config_path]
            self._cfg_files = []
        else:
            self._cfg_dirs = list(cfg_dirs or [])
            self._cfg_files = list(cfg_files or [])
        self._parser: NagiosConfigParser | None = None
        self._lock = multiprocessing.Lock()
        self._parser_corrupted = False

    @property
    def config_path(self) -> str:
        """First cfg_dir for backward compat. Returns empty string if none."""
        if self._cfg_dirs:
            return str(Path(self._cfg_dirs[0]).resolve())
        return ""

    @config_path.setter
    def config_path(self, path: str) -> None:
        """Set single config path (backward compat, replaces all dirs)."""
        with self._lock:
            self._cfg_dirs = [path]
            self._cfg_files = []
            self._parser = None

    @property
    def cfg_dirs(self) -> list[str]:
        return list(self._cfg_dirs)

    @property
    def cfg_files(self) -> list[str]:
        return list(self._cfg_files)

    def set_roots(self, cfg_dirs, cfg_files):
        """Update config roots and clear parser cache."""
        with self._lock:
            self._cfg_dirs = list(cfg_dirs)
            self._cfg_files = list(cfg_files)
            self._parser = None

    @property
    def parser(self) -> NagiosConfigParser:
        with self._lock:
            if self._parser is None:
                self._parser = NagiosConfigParser(
                    cfg_dirs=self._cfg_dirs,
                    cfg_files=self._cfg_files,
                )
                self._parser.parse_all()
            return self._parser

    def reload(self) -> NagiosConfigParser:
        with self._lock:
            self._parser = NagiosConfigParser(
                cfg_dirs=self._cfg_dirs,
                cfg_files=self._cfg_files,
            )
            self._parser.parse_all()
            self._parser_corrupted = False
            logger.debug("Parser reload: cfg_dirs=%s", self._cfg_dirs)
            return self._parser
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_service_multiroot.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Note failures for fixing in later tasks.

**Step 6: Commit**

```bash
git add nagios_service.py tests/test_service_multiroot.py
git commit -m "feat: multi-root NagiosService with cfg_dirs/cfg_files support"
```

---

### Task 5: Update ShadowCopyManager for multi-root

**Files:**
- Modify: `shadow_copy_manager.py`
- Test: `tests/test_shadow_multiroot.py`

This is the largest task. The shadow manager needs to handle multiple source directories mapped into a unified shadow.

**Step 1: Write failing tests for multi-root shadow**

```python
# tests/test_shadow_multiroot.py
import json
import os
from shadow_copy_manager import ShadowCopyManager

class TestMultiRootShadow:
    def test_create_shadow_copies_all_roots(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text("define host { host_name h1 }\n")
        (dir_b / "services.cfg").write_text("define service { service_description s1 }\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(
            cfg_dirs=[str(dir_a), str(dir_b)],
            shadow_base_path=str(shadow_base),
        )
        result = sm.create_shadow("sess1", "user", "user@test.com")
        assert result.success
        assert sm.has_shadow()

        # Both files should exist in shadow
        root_map = sm.get_root_map()
        assert len(root_map) == 2

    def test_root_map_json_created(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        root_map_path = os.path.join(str(shadow_base), "root_map.json")
        assert os.path.exists(root_map_path)
        with open(root_map_path) as f:
            root_map = json.load(f)
        assert len(root_map) == 1
        assert str(dir_a.resolve()) in root_map.values()

    def test_shadow_path_resolves_correctly(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        # shadow_path should return path within the shadow config dir
        sp = sm.shadow_path_for(str(dir_a.resolve() / "hosts.cfg"))
        assert os.path.exists(sp)

    def test_original_path_resolves_correctly(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        sp = sm.shadow_path_for(str(dir_a.resolve() / "hosts.cfg"))
        op = sm.original_path_for(sp)
        assert op == str(dir_a.resolve() / "hosts.cfg")

    def test_apply_writes_to_correct_roots(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("original\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        # Modify file in shadow
        sp = sm.shadow_path_for(str(dir_a.resolve() / "hosts.cfg"))
        with open(sp, "w") as f:
            f.write("modified\n")

        result = sm.apply(force=True)
        assert result.success

        # Original should now be modified
        assert (dir_a / "hosts.cfg").read_text() == "modified\n"

    def test_protected_files_excluded(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {}\n")
        (dir_a / "nagios.cfg").write_text("cfg_dir=.\n")
        (dir_a / "cgi.cfg").write_text("some=setting\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(cfg_dirs=[str(dir_a)], shadow_base_path=str(shadow_base))
        sm.create_shadow("sess1", "user", "user@test.com")

        # Protected files should not be in shadow
        sp_nagios = sm.shadow_path_for(str(dir_a.resolve() / "nagios.cfg"))
        sp_cgi = sm.shadow_path_for(str(dir_a.resolve() / "cgi.cfg"))
        assert not os.path.exists(sp_nagios)
        assert not os.path.exists(sp_cgi)

    def test_backward_compat_single_config_path(self, tmp_path):
        (tmp_path / "hosts.cfg").write_text("define host {}\n")
        shadow_base = tmp_path / "shadow"

        sm = ShadowCopyManager(config_path=str(tmp_path), shadow_base_path=str(shadow_base))
        result = sm.create_shadow("sess1", "user", "user@test.com")
        assert result.success
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_shadow_multiroot.py -v`
Expected: FAIL

**Step 3: Update ShadowCopyManager**

This is a significant refactor. Key changes:

1. **`__init__`** — accept `cfg_dirs` (list) or `config_path` (single, backward compat)
2. **`create_shadow`** — iterate cfg_dirs, create subdirs per root, write `root_map.json`, exclude protected files
3. **Path helpers** — `shadow_path_for(original_abs_path)` and `original_path_for(shadow_abs_path)` using root map
4. **`apply`** — resolve changed files back to original roots via root map
5. **`_hash_cfg_files`** — hash across all roots
6. **`get_changed_files`** — diff across all roots

The exact implementation is complex — the implementor should:
- Add `_root_map_file` property (path to `root_map.json`)
- Add `get_root_map() -> dict` (load from file)
- Add `_dir_to_shadow_name(abs_dir_path) -> str` (deterministic: replace `/` with `_`, strip leading)
- Update `create_shadow` to loop over `self._cfg_dirs`
- Update `shadow_path_for` / `original_path_for` to use root map
- Keep backward compat: single `config_path` → single entry in `_cfg_dirs`
- Filter PROTECTED_FILENAMES during copytree (use `shutil.copytree(ignore=...)`)

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_shadow_multiroot.py -v`
Expected: PASS

**Step 5: Run existing shadow tests**

Run: `python3 -m pytest tests/test_shadow_copy_manager.py -v`
Expected: PASS (backward compat via config_path)

**Step 6: Commit**

```bash
git add shadow_copy_manager.py tests/test_shadow_multiroot.py
git commit -m "feat: multi-root shadow copy with root_map.json"
```

---

### Task 6: Update app factory and route helpers

**Files:**
- Modify: `app.py:97-157` (create_app)
- Modify: `routes/helpers.py:35-43` (get_config_path)
- Modify: `routes/files.py:49-81` (ensure_shadow_lock)
- Test: existing integration tests should cover this

**Step 1: Update create_app to use discovery**

In `app.py`, update `create_app`:

```python
from config_discovery import discover_config_roots

def create_app(config_path=None, log_dir_override=None):
    # ... load server config ...
    server_config = load_server_config()

    # Discover config roots from nagios.cfg
    discovery = discover_config_roots(
        server_config.paths.nagios_cfg,
        extra_cfg_dirs=server_config.paths.extra_cfg_dirs,
    )
    accessible_dirs = [d["path"] for d in discovery["directories"] if d["accessible"]]
    cfg_files = discovery["cfg_files"]

    # Update resource_cfg from discovery
    if discovery["resource_file"]:
        server_config.paths.resource_cfg = discovery["resource_file"]

    # Set primary_dir default
    if not server_config.paths.primary_dir and accessible_dirs:
        server_config.paths.primary_dir = accessible_dirs[0]

    # Create services with multi-root
    service = NagiosService(cfg_dirs=accessible_dirs, cfg_files=cfg_files)
    # ... rest of service init ...

    app.extensions["discovery"] = discovery
```

**Step 2: Update routes/helpers.py get_config_path**

This function currently returns a single path. It needs to handle multi-root or be replaced with a function that returns the list of roots. Assess existing callers and update them.

```python
def get_config_roots() -> list[str]:
    """Get list of active config directory paths."""
    service = get_service()
    return service.cfg_dirs

def get_config_path() -> str:
    """Get primary config path (backward compat)."""
    service = get_service()
    return service.config_path
```

**Step 3: Update ensure_shadow_lock in routes/files.py**

When creating shadow, pass `cfg_dirs` instead of single path:

```python
def ensure_shadow_lock(session_id):
    sm = get_shadow_manager()
    service = get_service()
    # ... lock logic unchanged ...
    # When shadow created, point service at shadow roots:
    service.set_roots(cfg_dirs=sm.shadow_cfg_dirs, cfg_files=[])
    service.reload()
```

**Step 4: Update staging routes (apply/destroy)**

When shadow is applied or destroyed, reset service back to original roots.

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Fix any remaining failures.

**Step 6: Commit**

```bash
git add app.py routes/helpers.py routes/files.py routes/staging.py
git commit -m "feat: wire multi-root discovery into app factory and routes"
```

---

### Task 7: Update Settings API

**Files:**
- Modify: `routes/settings.py:20-72`
- Test: `tests/test_settings_api.py` (create or extend)

**Step 1: Write failing tests for new settings response**

```python
# tests/test_settings_api.py
class TestSettingsAPI:
    def test_get_settings_returns_discovered(self, client):
        resp = client.get("/api/settings")
        data = resp.get_json()
        assert "discovered" in data
        assert "cfg_dirs" in data["discovered"]
        assert "resource_file" in data["discovered"]

    def test_get_settings_returns_extra_cfg_dirs(self, client):
        resp = client.get("/api/settings")
        data = resp.get_json()
        assert "extra_cfg_dirs" in data["paths"]
        assert "primary_dir" in data["paths"]

    def test_post_settings_updates_nagios_cfg(self, client, tmp_path):
        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(f"cfg_dir={tmp_path}\n")
        resp = client.post("/api/settings", json={
            "paths": {"nagios_cfg": str(nagios_cfg)}
        })
        assert resp.status_code == 200

    def test_post_settings_updates_extra_dirs(self, client, tmp_path):
        d = tmp_path / "extra"
        d.mkdir()
        resp = client.post("/api/settings", json={
            "paths": {"extra_cfg_dirs": [str(d)]}
        })
        assert resp.status_code == 200

    def test_post_settings_rejects_nagios_config_path(self, client):
        """Old nagios_config_path field should be ignored."""
        resp = client.post("/api/settings", json={
            "nagios_config_path": "/some/path"
        })
        data = resp.get_json()
        # Should not error but should not apply either
```

**Step 2: Run tests, verify fail**

**Step 3: Update GET /api/settings**

```python
@blueprint.route("/api/settings", methods=["GET"])
def api_get_settings():
    server_config = get_server_config()
    discovery = current_app.extensions.get("discovery", {})
    return jsonify({
        "paths": {
            "nagios_cfg": server_config.paths.nagios_cfg,
            "nagios_bin": server_config.paths.nagios_bin,
            "backup_path": server_config.paths.backup_path,
            "shadow_path": server_config.paths.shadow_path,
            "resource_cfg": server_config.paths.resource_cfg,
            "extra_cfg_dirs": server_config.paths.extra_cfg_dirs,
            "primary_dir": server_config.paths.primary_dir,
        },
        "discovered": {
            "cfg_dirs": discovery.get("directories", []),
            "resource_file": discovery.get("resource_file", ""),
        },
    })
```

**Step 4: Update POST /api/settings**

Handle `nagios_cfg`, `extra_cfg_dirs`, `primary_dir` updates. On nagios_cfg change, re-run discovery, reinitialize services.

**Step 5: Run tests, verify pass**

**Step 6: Commit**

```bash
git add routes/settings.py tests/test_settings_api.py
git commit -m "feat: settings API with multi-root discovery response"
```

---

### Task 8: Update Files and Folders API for multi-root

**Files:**
- Modify: `routes/files.py:116-136` (api_files, api_list_folders)
- Test: `tests/test_files_multiroot.py`

**Step 1: Write failing tests**

```python
# tests/test_files_multiroot.py
class TestFilesMultiRoot:
    def test_api_files_returns_roots(self, client):
        resp = client.get("/api/files")
        data = resp.get_json()
        assert "roots" in data

    def test_api_files_includes_all_roots(self, client_with_two_dirs):
        resp = client_with_two_dirs.get("/api/files")
        data = resp.get_json()
        assert len(data["roots"]) == 2

    def test_api_folders_returns_roots(self, client):
        resp = client.get("/api/folders")
        data = resp.get_json()
        assert "roots" in data
```

**Step 2: Run tests, verify fail**

**Step 3: Update api_files to include roots**

```python
@blueprint.route("/api/files")
def api_files():
    service = get_service()
    config_roots = service.cfg_dirs
    all_files = []
    for root in config_roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for cfg_file in root_path.rglob("*.cfg"):
            # Apply same skip logic as parser
            # Exclude protected files
            if cfg_file.name in PROTECTED_FILENAMES:
                continue
            all_files.append(str(cfg_file))
    return jsonify({
        "files": sorted(all_files),
        "roots": config_roots,
    })
```

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git add routes/files.py tests/test_files_multiroot.py
git commit -m "feat: multi-root file and folder listing"
```

---

### Task 9: Update Settings UI template

**Files:**
- Modify: `templates/settings.html`
- No backend test needed (UI-only)

**Step 1: Update the settings form layout**

Replace the current Configuration Paths section with the new layout from the design:

1. nagios.cfg path field with Browse button
2. Discovered directories list (read-only, with red/error styling)
3. Additional directories section with Add/Remove
4. Primary directory dropdown
5. Resource file display (read-only text)
6. Keep Nagios binary, Backup path, Shadow path fields

**Step 2: Add JavaScript for discovery refresh**

When nagios.cfg path changes and is saved, re-fetch `/api/settings` to update the discovered directories list.

**Step 3: Add CSS for inaccessible directory styling**

Red text + error message for directories with `accessible: false`.

**Step 4: Manual test**

Run: `python3 app.py` and verify the settings page at http://localhost:8080/settings

**Step 5: Commit**

```bash
git add templates/settings.html static/css/*.css
git commit -m "feat: settings UI with multi-root discovery display"
```

---

### Task 10: Update Explorer file tree for multi-root

**Files:**
- Modify: `static/js/explorer/state.js` (add roots to state)
- Modify: `static/js/explorer/data-loading.js` (load roots from API)
- Modify: `static/js/explorer/file-operations.js` (build multi-root tree)
- Test: manual browser testing

**Step 1: Update state.js**

Add `configRoots: []` to the state object.

**Step 2: Update data-loading.js loadObjects()**

When fetching `/api/files`, store the `roots` array in `state.configRoots`.

**Step 3: Update tree building**

The file tree currently shows a single root. Update to:
- Create a root node for each directory in `state.configRoots`
- Group files under their respective root
- Sort roots alphabetically
- Label each root with its full path

**Step 4: Update new file creation**

Default the folder picker to `state.primaryDir` (from settings).

**Step 5: Manual test**

Run app with sample-config (which has one root) — should look the same as before. Test with multiple roots if possible.

**Step 6: Commit**

```bash
git add static/js/explorer/state.js static/js/explorer/data-loading.js static/js/explorer/file-operations.js
git commit -m "feat: multi-root file tree in explorer"
```

---

### Task 11: Fix remaining tests and update sample-config

**Files:**
- Modify: Various test files that reference `nagios_config_path`
- Modify: `config/settings.json` (update to new schema)
- Test: full suite

**Step 1: Update config/settings.json**

Remove `nagios_config_path`, ensure `nagios_cfg` points to sample nagios.cfg:

```json
{
  "version": 1,
  "paths": {
    "nagios_cfg": "./sample-config/nagios.cfg",
    "nagios_bin": "/opt/homebrew/bin/Nagios",
    "backup_path": null,
    "shadow_path": null,
    "resource_cfg": "./sample-config/resources.cfg",
    "extra_cfg_dirs": [],
    "primary_dir": ""
  },
  "logging": { ... }
}
```

**Step 2: Grep for all references to nagios_config_path**

Run: `grep -r "nagios_config_path" --include="*.py" --include="*.js" --include="*.html"`

Update each reference:
- In test fixtures: use `cfg_dirs=[str(tmp_path)]` instead of `config_path=str(tmp_path)`
- In route code: use `service.cfg_dirs` instead of `service.config_path` where appropriate
- In templates: remove the old field

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Fix all failures.

**Step 4: Commit**

```bash
git add -A
git commit -m "fix: update all references from nagios_config_path to multi-root"
```

---

### Task 12: Integration testing

**Files:**
- Create: `tests/test_multiroot_integration.py`

**Step 1: Write end-to-end integration test**

```python
# tests/test_multiroot_integration.py
"""Integration test: multi-root config discovery through full stack."""
import json
import os
import tempfile
from app import create_app

class TestMultiRootIntegration:
    def test_full_workflow(self, tmp_path):
        """Test: nagios.cfg → discovery → parse → shadow → apply."""
        # Setup: two config directories
        dir_a = tmp_path / "servers"
        dir_b = tmp_path / "switches"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text('define host {\n    host_name web1\n    address 10.0.0.1\n}\n')
        (dir_b / "hosts.cfg").write_text('define host {\n    host_name switch1\n    address 10.0.1.1\n}\n')

        # Create nagios.cfg
        nagios_cfg = tmp_path / "nagios.cfg"
        nagios_cfg.write_text(
            f"cfg_dir={dir_a}\n"
            f"cfg_dir={dir_b}\n"
            f"resource_file={tmp_path}/resources.cfg\n"
        )
        (tmp_path / "resources.cfg").write_text("$USER1$=/usr/lib/nagios/plugins\n")

        # Create app with this config
        # ... (setup app with nagios_cfg path pointing to our file)

        # GET /api/objects should return objects from both dirs
        # GET /api/files should return files from both dirs with roots
        # GET /api/settings should show discovered dirs
        # Create shadow, modify, apply — verify changes go to correct dirs
```

**Step 2: Run integration test**

Run: `python3 -m pytest tests/test_multiroot_integration.py -v`

**Step 3: Fix any issues found**

**Step 4: Commit**

```bash
git add tests/test_multiroot_integration.py
git commit -m "test: multi-root integration test covering full workflow"
```

---

## Task Dependency Graph

```
Task 1 (PathsConfig) ─────┐
                           ├──→ Task 6 (App factory + routes wiring)
Task 2 (Discovery module) ─┤         │
                           │         ├──→ Task 7 (Settings API)
Task 3 (Parser multi-root)─┤         │
                           │         ├──→ Task 8 (Files API)
Task 4 (Service multi-root)┤         │
                           │         ├──→ Task 9 (Settings UI)
Task 5 (Shadow multi-root)─┘         │
                                     ├──→ Task 10 (Explorer tree)
                                     │
                                     ├──→ Task 11 (Fix tests)
                                     │
                                     └──→ Task 12 (Integration test)
```

Tasks 1-5 can be done in order (each builds on the previous). Tasks 7-10 can be parallelized after Task 6. Tasks 11-12 are final cleanup.
