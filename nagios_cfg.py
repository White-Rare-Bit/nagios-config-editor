"""Lightweight parser for nagios.cfg and resource.cfg files.

Extracts cfg_dir, cfg_file directives and $USERn$ macro definitions.
"""

import os
import re


def parse_nagios_cfg(nagios_cfg_path):
    """Parse nagios.cfg and extract cfg_dir and cfg_file directives.

    Args:
        nagios_cfg_path: Path to the nagios.cfg file.

    Returns:
        dict with 'cfg_dirs' (list of str) and 'cfg_files' (list of str).
        Returns empty lists if the file doesn't exist or can't be read.
    """
    result = {"cfg_dirs": [], "cfg_files": []}
    if not nagios_cfg_path or not os.path.isfile(nagios_cfg_path):
        return result

    try:
        with open(nagios_cfg_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key == "cfg_dir":
                    result["cfg_dirs"].append(value)
                elif key == "cfg_file":
                    result["cfg_files"].append(value)
    except (OSError, UnicodeDecodeError):
        pass

    return result


def parse_resource_cfg(resource_cfg_path):
    """Parse resource.cfg and extract $USERn$ macro definitions.

    Args:
        resource_cfg_path: Path to the resource.cfg file.

    Returns:
        dict mapping macro name (e.g. '$USER1$') to its value.
        Returns empty dict if the file doesn't exist or can't be read.
    """
    macros = {}
    if not resource_cfg_path or not os.path.isfile(resource_cfg_path):
        return macros

    try:
        with open(resource_cfg_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if re.match(r"^\$USER\d+\$$", key):
                    macros[key] = value
    except (OSError, UnicodeDecodeError):
        pass

    return macros
