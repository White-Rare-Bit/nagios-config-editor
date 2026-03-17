"""Config discovery — resolves config roots from nagios.cfg.

Parses nagios.cfg for cfg_dir, cfg_file, and resource_file directives,
then builds a unified list of config directories with accessibility checks.
"""

import os

from .nagios_cfg import parse_nagios_cfg

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
