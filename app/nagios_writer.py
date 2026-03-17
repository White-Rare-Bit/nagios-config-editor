"""Nagios Configuration Writer

Writes NagiosObject instances back to configuration files.
Handles formatting and maintains consistency.
"""

import logging
import os
import tempfile
from pathlib import Path

from .nagios_model import NagiosObject, format_object_block

logger = logging.getLogger(__name__)


class NagiosConfigWriter:
    """Writer for Nagios configuration files."""

    def __init__(self, indent: str = "    "):
        self.indent = indent

    def object_to_string(self, obj: NagiosObject) -> str:
        """Convert a NagiosObject to its config file string representation."""
        return format_object_block(obj.object_type, obj.attributes, self.indent,
                                   getattr(obj, "inline_comments", None))

    def objects_to_string(self, objects: list[NagiosObject], preserve_order: bool = True) -> str:
        """Convert multiple objects to config file content.

        Args:
            objects: List of NagiosObject instances to write
            preserve_order: If True, sort by line_number to preserve file order.
                          If False, group by object type for readability.

        """
        if preserve_order:
            # Sort by (source_file, line_number) to preserve file order
            # This ensures objects from different files don't get interleaved
            sorted_objects = sorted(objects, key=lambda o: (o.source_file, o.line_number))
            return "\n\n".join(self.object_to_string(obj) for obj in sorted_objects) + "\n"

        # Legacy behavior: Group by object type for readability
        by_type: dict[str, list[NagiosObject]] = {}
        for obj in objects:
            if obj.object_type not in by_type:
                by_type[obj.object_type] = []
            by_type[obj.object_type].append(obj)

        sections = []

        # Order types logically
        type_order = ["timeperiod", "command", "contact", "contactgroup",
                      "host", "hostgroup", "service", "servicegroup",
                      "servicedependency", "hostdependency",
                      "serviceescalation", "hostescalation"]

        def type_sort_key(t):
            if t in type_order:
                return (0, type_order.index(t))
            return (1, t)

        for obj_type in sorted(by_type.keys(), key=type_sort_key):
            type_objects = by_type[obj_type]
            section_header = f"# {'=' * 60}\n# {obj_type.upper()} DEFINITIONS\n# {'=' * 60}\n"
            section_content = "\n\n".join(self.object_to_string(obj) for obj in type_objects)
            sections.append(section_header + "\n" + section_content)

        return "\n\n".join(sections) + "\n"

    def write_file(self, filepath: str, objects: list[NagiosObject]) -> None:
        """Write objects to a configuration file atomically."""
        logger.info("write_file: %s (%d objects)", filepath, len(objects))
        content = self.objects_to_string(objects)
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file in same directory (ensures same filesystem for atomic rename)
        dir_path = path.parent
        fd, temp_path = tempfile.mkstemp(suffix=".tmp", prefix=".nagios_", dir=dir_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk
            # Atomic rename (on POSIX systems)
            os.replace(temp_path, filepath)
        except Exception as e:
            # C-07: Clean up temp file on failure with proper error logging
            try:
                os.unlink(temp_path)
            except OSError as cleanup_err:
                logger.exception("DISK_LEAK: Temp file cleanup failed for %s: %s", temp_path, cleanup_err)
            logger.exception("write_file failed for %s", filepath)
            raise

    def write_objects_to_original_files(self, objects: list[NagiosObject]) -> dict[str, int]:
        """Write objects back to their original source files."""
        logger.info("write_objects_to_original_files: %d objects", len(objects))
        # Group objects by source file
        by_file: dict[str, list[NagiosObject]] = {}
        for obj in objects:
            if obj.source_file not in by_file:
                by_file[obj.source_file] = []
            by_file[obj.source_file].append(obj)

        results = {}
        for filepath, file_objects in by_file.items():
            self.write_file(filepath, file_objects)
            results[filepath] = len(file_objects)

        return results

