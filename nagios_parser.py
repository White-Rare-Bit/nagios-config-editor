"""Nagios Configuration Parser

Parses Nagios .cfg files and builds an in-memory object model.
Supports all major object types: host, hostgroup, service, servicegroup,
contact, contactgroup, command, timeperiod, etc.
"""

import logging
import os
import re
from pathlib import Path

from nagios_model import REFERENCE_FIELDS, NagiosObject
from nagios_model import format_object_block as _model_format_object_block

logger = logging.getLogger("nagios_bulk_editor.parser")


# Minimum digit count to identify timestamp patterns in filenames (e.g. 20240115)
_MIN_TIMESTAMP_DIGITS = 8


class NagiosConfigParser:

    """Parser for Nagios configuration files."""

    # Reference fields imported from nagios_model for backward compatibility
    REFERENCE_FIELDS = REFERENCE_FIELDS

    # Regex matching a Nagios time range value (e.g. 00:00-24:00, 08:00-17:00)
    _TIMERANGE_RE = re.compile(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}")

    # Standard timeperiod attributes that use normal key/value splitting
    _TIMEPERIOD_STANDARD_ATTRS = frozenset({
        "timeperiod_name", "alias", "use", "name", "register", "exclude",
    })

    def __init__(self, config_path: str = "./sample-config"):
        # Always use absolute path to ensure consistent file paths
        self.config_path = Path(config_path).resolve()
        self.objects: list[NagiosObject] = []
        self.files_parsed: list[str] = []

    def parse_all(self) -> list[NagiosObject]:
        """Parse all .cfg files in the config directory, excluding backups."""
        self.objects = []
        self.files_parsed = []

        if not self.config_path.exists():
            return self.objects

        for cfg_file in self.config_path.rglob("*.cfg"):
            # Skip backup files and directories
            file_path = str(cfg_file)
            if "/backups/" in file_path or "/backup/" in file_path:
                continue
            if ".bak" in file_path or ".backup" in file_path:
                continue
            # Skip staging directories (shadow copies, baselines)
            if "/.staging/" in file_path or "/.nagios_staging/" in file_path:
                continue
            # Skip files with timestamp patterns like _20240115_ or .20240115.
            parts = cfg_file.name
            if any(part.isdigit() and len(part) >= _MIN_TIMESTAMP_DIGITS for part in parts.replace("_", ".").split(".")):
                continue
            self.parse_file(file_path)

        return self.objects

    def parse_file(self, filepath: str) -> list[NagiosObject]:
        """Parse a single Nagios configuration file."""
        # Normalize filepath to avoid issues with ./dir vs dir
        filepath = os.path.normpath(filepath)
        objects = []

        try:
            with open(filepath, encoding="utf-8", errors="strict") as f:
                content = f.read()
        except UnicodeDecodeError as e:
            logger.warning(
                "Unicode error in %s: %s. Retrying with latin-1 encoding. "
                "File may contain non-UTF-8 characters.",
                filepath, e,
            )
            try:
                with open(filepath, encoding="latin-1") as f:
                    content = f.read()
            except OSError as e2:
                logger.exception("Error reading %s with latin-1 fallback: %s", filepath, e2)
                return objects
        except OSError as e:
            logger.exception("Error reading %s: %s", filepath, e)
            return objects

        self.files_parsed.append(filepath)

        # Use state machine approach for proper brace matching
        # This handles braces inside quoted strings correctly
        for obj_type, block_content, line_num in self._find_define_blocks(content):
            attributes, inline_comments = self._parse_attributes(block_content, object_type=obj_type)

            obj = NagiosObject(
                object_type=obj_type,
                attributes=attributes,
                source_file=filepath,
                line_number=line_num,
                inline_comments=inline_comments,
            )
            objects.append(obj)
            self.objects.append(obj)

        return objects

    def _scan_block_body(self, content: str, brace_start: int, length: int) -> tuple:
        """Scan from opening brace to find closing brace and nested defines.

        Respects quoted strings and escape sequences. Detects nested 'define'
        keywords that indicate malformed config.

        Args:
            content: Full file content
            brace_start: Position of the opening brace
            length: Total content length

        Returns:
            Tuple of (end_pos, brace_depth, nested_define_pos).
            end_pos is position after closing brace (or last scanned position).
            brace_depth is 0 on balanced match, >0 if unmatched.
            nested_define_pos is position of first nested define, or None.

        """
        j = brace_start + 1
        brace_depth = 1
        in_double_quote = False
        in_single_quote = False
        nested_define_pos = None

        while j < length and brace_depth > 0:
            char = content[j]
            prev_char = content[j - 1] if j > 0 else ""

            if prev_char == "\\":
                j += 1
                continue

            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif not in_double_quote and not in_single_quote:
                if char == "{":
                    brace_depth += 1
                elif char == "}":
                    brace_depth -= 1
                elif char == "d" and content[j:j + 6] == "define" and brace_depth == 1:
                    define_check = re.match(r"define\s+\w+\s*\{", content[j:])
                    if define_check and nested_define_pos is None:
                        nested_define_pos = j

            j += 1

        return (j, brace_depth, nested_define_pos)

    def _find_define_blocks(self, content: str) -> list[tuple]:
        """Find all define blocks handling braces in quoted strings.

        Returns list of (object_type, block_content, line_number) tuples.
        """
        blocks = []
        i = 0
        length = len(content)

        while i < length:
            define_match = re.search(r"define\s+(\w+)\s*\{", content[i:])
            if not define_match:
                break

            start_pos = i + define_match.start()
            object_type = define_match.group(1)
            brace_start = i + define_match.end() - 1
            line_number = content[:start_pos].count("\n") + 1

            j, brace_depth, nested_define_pos = self._scan_block_body(content, brace_start, length)

            if nested_define_pos is not None and (brace_depth > 0 or nested_define_pos < j - 1):
                block_content = content[brace_start + 1:nested_define_pos]
                if block_content.strip():
                    blocks.append((object_type, block_content, line_number))
                i = nested_define_pos
            elif brace_depth == 0:
                block_content = content[brace_start + 1:j - 1]
                blocks.append((object_type, block_content, line_number))
                i = j
            else:
                logger.warning("Unmatched brace in define block at line %s", line_number)
                i = brace_start + 1

        return blocks

    def _parse_attributes(self, block_content: str, object_type: str = None) -> tuple:
        """Parse attributes from a define block content.

        Args:
            block_content: The text inside the define { } block.
            object_type: The Nagios object type (e.g. 'timeperiod'). Used to
                enable special parsing for timeperiod date-range directives.

        Returns:
            Tuple of (attributes dict, inline_comments dict).
            inline_comments maps attribute keys to their comment text (without
            the leading ';').

        """
        attributes = {}
        inline_comments = {}

        # Handle line continuations (backslash at end of line)
        block_content = re.sub(r"\\\n\s*", " ", block_content)

        for line in block_content.split("\n"):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#") or line.startswith(";"):
                continue

            if object_type == "timeperiod":
                key, value = self._parse_timeperiod_line(line)
            else:
                # Split on first whitespace to get key/value
                parts = line.split(None, 1)
                key = parts[0]
                value = parts[1] if len(parts) > 1 else ""

            # Extract inline comment before stripping it
            comment = self._extract_inline_comment(value)

            # Remove inline comments (semicolons outside quotes)
            value = self._strip_inline_comment(value)

            attributes[key] = value.strip()
            if comment:
                inline_comments[key] = comment

        return attributes, inline_comments

    def _parse_timeperiod_line(self, line: str) -> tuple:
        """Parse a single line inside a timeperiod block.

        Timeperiod directives have multi-word keys like:
            monday 1                08:00-12:00
            day 1 - 15              08:00-17:00
            2025-12-24 - 2025-12-26 00:00-24:00
            monday 3 - thursday 4   00:00-24:00

        The value always starts with a time range pattern (HH:MM-HH:MM).
        Standard attributes (timeperiod_name, alias, etc.) use normal splitting.

        Returns:
            (key, value) tuple.

        """
        # First, check if the line starts with a standard timeperiod attribute
        parts = line.split(None, 1)
        first_word = parts[0]

        if first_word in self._TIMEPERIOD_STANDARD_ATTRS:
            value = parts[1] if len(parts) > 1 else ""
            return first_word, value

        # For date-range directives, find the time range pattern.
        # Everything before it is the key; from the pattern onward is the value.
        match = self._TIMERANGE_RE.search(line)
        if match:
            key = line[:match.start()].rstrip()
            value = line[match.start():]
            if key:
                return key, value

        # Fallback: standard first-whitespace split
        key = parts[0]
        value = parts[1] if len(parts) > 1 else ""
        return key, value

    def _strip_inline_comment(self, value: str) -> str:
        """Remove inline comments (;) while respecting quoted strings.

        Handles both single and double quotes, and escaped quotes.
        """
        result = []
        in_double_quote = False
        in_single_quote = False
        i = 0

        while i < len(value):
            char = value[i]
            prev_char = value[i-1] if i > 0 else ""

            # Handle escaped characters
            if prev_char == "\\":
                result.append(char)
                i += 1
                continue

            # Track quote state
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                result.append(char)
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                result.append(char)
            elif char == ";" and not in_double_quote and not in_single_quote:
                # Found comment start outside quotes, stop here
                break
            else:
                result.append(char)

            i += 1

        return "".join(result)

    def _extract_inline_comment(self, value: str) -> str | None:
        """Extract inline comment text from a value string.

        Returns the comment text (after the ';') stripped of whitespace,
        or None if no inline comment is present. Respects quoted strings.
        """
        in_double_quote = False
        in_single_quote = False
        i = 0

        while i < len(value):
            char = value[i]
            prev_char = value[i-1] if i > 0 else ""

            # Handle escaped characters
            if prev_char == "\\":
                i += 1
                continue

            # Track quote state
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == ";" and not in_double_quote and not in_single_quote:
                # Found comment start outside quotes
                comment = value[i+1:].strip()
                return comment or None

            i += 1

        return None

    def get_objects_by_type(self, object_type: str) -> list[NagiosObject]:
        """Get all objects of a specific type."""
        return [obj for obj in self.objects if obj.object_type == object_type]

    def get_object_types(self) -> list[str]:
        """Get a list of all object types found."""
        return sorted(set(obj.object_type for obj in self.objects))

    def get_files(self) -> list[str]:
        """Get list of all parsed config files."""
        return sorted(set(obj.source_file for obj in self.objects))

    def find_objects(self, search_term: str, object_type: str | None = None,
                     field: str | None = None, regex: bool = False) -> list[NagiosObject]:
        """Search for objects matching criteria.

        Args:
            search_term: Text to search for
            object_type: Limit search to this object type
            field: Search only in this field (None = all fields)
            regex: If True, treat search_term as regex pattern

        """
        results = []

        if regex:
            try:
                pattern = re.compile(search_term, re.IGNORECASE)
            except re.error:
                return results

        for obj in self.objects:
            if object_type and obj.object_type != object_type:
                continue

            fields_to_search = [field] if field else obj.attributes.keys()

            for f in fields_to_search:
                if f not in obj.attributes:
                    continue
                value = obj.attributes[f]

                if regex:
                    if pattern.search(value):
                        results.append(obj)
                        break
                elif search_term.lower() in value.lower():
                    results.append(obj)
                    break

        return results

    def find_references(self, object_type: str, name: str) -> list[tuple]:
        """Find all objects that reference the given object.

        Returns list of tuples: (object, field_name) that reference the target.
        """
        references = []

        # Determine which fields could reference this object type
        ref_fields = []
        for field_name, ref_type in self.REFERENCE_FIELDS.items():
            if ref_type == object_type or ref_type is None:
                ref_fields.append(field_name)

        for obj in self.objects:
            for field_name in ref_fields:
                if field_name not in obj.attributes:
                    continue

                value = obj.attributes[field_name]
                # Handle comma-separated lists
                values = [v.strip() for v in value.split(",")]

                if name in values:
                    references.append((obj, field_name))

        return references

    def get_summary(self) -> dict[str, int]:
        """Get a summary count of objects by type."""
        summary = {}
        for obj in self.objects:
            summary[obj.object_type] = summary.get(obj.object_type, 0) + 1
        return summary

    # ==================== Write Methods ====================

    def _format_object_block(self, object_type: str, attributes: dict[str, str]) -> str:
        """Format an object as a Nagios define block."""
        return _model_format_object_block(object_type, attributes)

    def _find_block_range(self, content: str, line_number: int) -> tuple | None:
        """Find the start and end positions of a define block starting at line_number.

        Returns (start_pos, end_pos) or None if not found.
        """
        lines = content.split("\n")

        # Convert line number to character position
        pos = 0
        for i, line in enumerate(lines):
            if i + 1 == line_number:
                remaining = content[pos:]
                match = re.match(r"\s*define\s+\w+\s*\{", remaining)
                if not match:
                    return None

                start_pos = pos
                brace_start = pos + remaining.index("{")
                j, brace_depth, _ = self._scan_block_body(content, brace_start, len(content))

                if brace_depth == 0:
                    end_pos = j
                    if end_pos < len(content) and content[end_pos] == "\n":
                        end_pos += 1
                    return (start_pos, end_pos)
                return None

            pos += len(line) + 1

        return None


def parse_config(config_path: str = "./sample-config") -> NagiosConfigParser:
    """Convenience function to parse a Nagios configuration directory."""
    parser = NagiosConfigParser(config_path)
    parser.parse_all()
    return parser
