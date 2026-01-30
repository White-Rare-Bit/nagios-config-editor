"""
Nagios Configuration Writer

Writes NagiosObject instances back to configuration files.
Handles formatting and maintains consistency.
"""

import os
import tempfile
from typing import List, Dict, Optional
from pathlib import Path
from nagios_model import NagiosObject, ATTRIBUTE_SORT_ORDER, format_object_block


class NagiosConfigWriter:
    """Writer for Nagios configuration files."""

    def __init__(self, indent: str = "    ", op_logger=None):
        self.indent = indent
        self._op_logger = op_logger

    def object_to_string(self, obj: NagiosObject) -> str:
        """Convert a NagiosObject to its config file string representation."""
        return format_object_block(obj.object_type, obj.attributes, self.indent)

    def objects_to_string(self, objects: List[NagiosObject], preserve_order: bool = True) -> str:
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
        by_type: Dict[str, List[NagiosObject]] = {}
        for obj in objects:
            if obj.object_type not in by_type:
                by_type[obj.object_type] = []
            by_type[obj.object_type].append(obj)

        sections = []

        # Order types logically
        type_order = ['timeperiod', 'command', 'contact', 'contactgroup',
                      'host', 'hostgroup', 'service', 'servicegroup',
                      'servicedependency', 'hostdependency',
                      'serviceescalation', 'hostescalation']

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

    def write_file(self, filepath: str, objects: List[NagiosObject]) -> None:
        """Write objects to a configuration file atomically."""
        if self._op_logger:
            self._op_logger.info('writer', 'write_file', params={'filepath': filepath, 'object_count': len(objects)})
        content = self.objects_to_string(objects)
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file in same directory (ensures same filesystem for atomic rename)
        dir_path = path.parent
        fd, temp_path = tempfile.mkstemp(suffix='.tmp', prefix='.nagios_', dir=dir_path)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
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
                # Log temp file cleanup failure for manual intervention
                if self._op_logger:
                    self._op_logger.error('writer', 'write_file',
                        params={'filepath': filepath, 'temp_file': temp_path},
                        error=f"DISK_LEAK: Temp file cleanup failed: {cleanup_err}")
            if self._op_logger:
                self._op_logger.error('writer', 'write_file', params={'filepath': filepath}, error=str(e))
            raise

    def write_objects_to_original_files(self, objects: List[NagiosObject]) -> Dict[str, int]:
        """Write objects back to their original source files."""
        if self._op_logger:
            self._op_logger.info('writer', 'write_objects_to_original_files', params={'total_objects': len(objects)})
        # Group objects by source file
        by_file: Dict[str, List[NagiosObject]] = {}
        for obj in objects:
            if obj.source_file not in by_file:
                by_file[obj.source_file] = []
            by_file[obj.source_file].append(obj)

        results = {}
        for filepath, file_objects in by_file.items():
            self.write_file(filepath, file_objects)
            results[filepath] = len(file_objects)

        return results


def write_config_file(filepath: str, objects: List[NagiosObject], indent: str = "    ") -> None:
    """Convenience function to write objects to a file."""
    writer = NagiosConfigWriter(indent=indent)
    writer.write_file(filepath, objects)
