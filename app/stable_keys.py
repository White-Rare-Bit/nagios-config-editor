"""Stable key utilities for Nagios object identity.

Stable key format: "source_file|object_type|name"
This format is shared with the frontend (static/js/stable-key.js).
Any change here MUST be coordinated with the frontend.
"""

from typing import Any


def generate_stable_key(source_file: str, object_type: str, name: str) -> str:
    """Generate a stable key for an object.

    The stable key format is: "source_file|object_type|name"
    This key remains stable across parser reloads and index changes.

    Args:
        source_file: Path to the source file
        object_type: Type of the object (host, service, etc.)
        name: The object's name (varies by type)

    Returns:
        Stable key string

    """
    return f"{source_file}|{object_type}|{name}"


def parse_stable_key(key: str) -> dict[str, str] | None:
    """Parse a stable key back into its components.

    Args:
        key: Stable key string

    Returns:
        Dictionary with source_file, object_type, name keys, or None if invalid

    """
    parts = key.split("|")
    if len(parts) < 3:  # noqa: PLR2004
        return None

    return {
        "source_file": parts[0],
        "object_type": parts[1],
        "name": "|".join(parts[2:]),
    }


def generate_stable_key_for_object(obj: Any) -> str:
    """Generate a stable key for a NagiosObject.

    Uses get_display_name() to ensure uniqueness — services with the same
    service_description on different hosts get different keys.

    Args:
        obj: NagiosObject instance

    Returns:
        Stable key string

    """
    name = obj.get_display_name()
    return generate_stable_key(obj.source_file, obj.object_type, name)
