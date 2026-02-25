"""Post-apply verification — confirms disk changes match staging intent.

Two-layer verification:
1. File-level: git status changes vs expected changeset from staging data
2. Object-level: re-parsed objects vs each staging operation's intent
"""

import logging

from nagios_model import NAME_FIELDS

logger = logging.getLogger("nagios_bulk_editor.verification")


def build_expected_changeset(staging_data, parser_objects=None):
    """Build set of files expected to change from staging operations.

    Args:
        staging_data: Staging data dict (pendingEdits, stagedCreations, etc.)
        parser_objects: Optional list of parser object dicts (needed for
            deletion indices). Each must have 'source_file' key.

    Returns:
        Dict with keys 'modified', 'created', 'deleted' — each a set of
        absolute file paths.

    """
    modified = set()
    created = set()
    deleted = set()

    # Object edits → modified files
    for entry in staging_data.get("pendingEdits", {}).values():
        if isinstance(entry, dict):
            obj = entry.get("object", {})
            source = obj.get("source_file")
            if source:
                modified.add(source)

    # Object creations → modified files (appended to existing file)
    for creation in staging_data.get("stagedCreations", []):
        target = creation.get("targetFile")
        if target:
            modified.add(target)

    # Object deletions → need parser objects to resolve indices to files
    if parser_objects:
        for idx in staging_data.get("stagedObjectDeletions", []):
            if isinstance(idx, int) and 0 <= idx < len(parser_objects):
                source = parser_objects[idx].get("source_file")
                if source:
                    modified.add(source)

    # Object moves → both source and target modified
    for move in staging_data.get("stagedMoves", {}).values():
        if isinstance(move, dict):
            obj = move.get("object", {})
            source = obj.get("source_file")
            target = move.get("targetFile")
            if source:
                modified.add(source)
            if target:
                modified.add(target)

    # File creations
    for entry in staging_data.get("stagedFileCreations", []):
        path = entry.get("path")
        if path:
            created.add(path)

    # File deletions
    for entry in staging_data.get("stagedFileDeletions", []):
        path = entry.get("path")
        if path:
            deleted.add(path)

    # File moves → source deleted, target created
    for entry in staging_data.get("stagedFileMoves", []):
        source = entry.get("sourcePath")
        target = entry.get("targetPath")
        if source:
            deleted.add(source)
        if target:
            created.add(target)

    return {"modified": modified, "created": created, "deleted": deleted}


def compare_file_changes(expected, pre_files, post_files, config_path):
    """Compare git-reported file changes against expected changeset.

    Args:
        expected: Dict from build_expected_changeset() with 'modified',
            'created', 'deleted' sets of absolute paths.
        pre_files: List of git status file dicts BEFORE apply.
            Each: {"path": "relative/path.cfg", "status_code": "XY"}
        post_files: List of git status file dicts AFTER apply.
            Same format as pre_files.
        config_path: Absolute path to config directory (for resolving
            relative git paths to absolute).

    Returns:
        Dict with 'passed' (bool), 'unexpected' (list of str descriptions),
        'missing' (list of str descriptions), 'expectedFiles' (list),
        'actualFiles' (list).

    """
    import os

    # Build sets of relative paths that were dirty before apply (pre-existing noise)
    pre_dirty = {f["path"] for f in pre_files}

    # Build set of files that actually changed (new in post, not in pre)
    post_paths = {f["path"] for f in post_files}
    newly_changed = post_paths - pre_dirty

    # Convert expected absolute paths to relative (for git comparison)
    def to_relative(abs_path):
        if abs_path.startswith(config_path):
            rel = os.path.relpath(abs_path, config_path)
            return rel
        return abs_path

    expected_relative = set()
    for path in expected["modified"] | expected["created"] | expected["deleted"]:
        expected_relative.add(to_relative(path))

    # Find unexpected: changed on disk but not in expected set
    unexpected = []
    for path in sorted(newly_changed - expected_relative):
        unexpected.append(f"Unexpected change: {path}")

    # Find missing: expected to change but didn't show up in git diff
    missing = []
    for path in sorted(expected_relative - newly_changed):
        missing.append(f"Expected change not found: {path}")

    passed = len(unexpected) == 0 and len(missing) == 0

    return {
        "passed": passed,
        "unexpected": unexpected,
        "missing": missing,
        "expectedFiles": sorted(expected_relative),
        "actualFiles": sorted(newly_changed),
    }


def _find_object(parsed_objects, obj_type, name, source_file=None):
    """Find an object in parsed list by type, name, and optionally file.

    Args:
        parsed_objects: List of parsed object dicts.
        obj_type: Object type string.
        name: Object name.
        source_file: Optional file path constraint.

    Returns:
        Matching object dict, or None.

    """
    name_field = NAME_FIELDS.get(obj_type)
    for obj in parsed_objects:
        if obj.get("object_type") != obj_type:
            continue
        if source_file and obj.get("source_file") != source_file:
            continue
        obj_name = obj.get("attributes", {}).get(name_field, "") if name_field else ""
        if obj_name == name:
            return obj
    return None


def verify_objects(staging_data, parsed_objects, pre_objects=None):
    """Verify re-parsed objects match staging intent.

    Args:
        staging_data: Staging data dict.
        parsed_objects: List of object dicts from re-parsed config
            (each with 'object_type', 'source_file', 'attributes').
        pre_objects: Optional list of object dicts from BEFORE apply
            (needed for deletion verification to know what was deleted).

    Returns:
        Dict with 'passed', counts per operation, and 'failures' list.

    """
    edits_verified = 0
    edits_failed = 0
    creations_verified = 0
    creations_failed = 0
    deletions_verified = 0
    deletions_failed = 0
    moves_verified = 0
    moves_failed = 0
    failures = []

    # Verify edits
    for entry in staging_data.get("pendingEdits", {}).values():
        if not isinstance(entry, dict):
            continue
        obj_meta = entry.get("object", {})
        edited = entry.get("edited", {})
        if not edited:
            continue

        obj_type = obj_meta.get("object_type")
        obj_name = obj_meta.get("name")

        # If the name field itself was edited, look for the new name
        name_field = NAME_FIELDS.get(obj_type, "")
        lookup_name = edited.get(name_field, obj_name)

        found = _find_object(parsed_objects, obj_type, lookup_name)
        if not found:
            edits_failed += 1
            failures.append(f"Edit: {obj_type} '{obj_name}' not found after apply")
            continue

        # Check each edited attribute
        all_match = True
        for key, expected_val in edited.items():
            actual_val = found.get("attributes", {}).get(key)
            if actual_val != expected_val:
                all_match = False
                failures.append(
                    f"Edit: {obj_type} '{lookup_name}' field '{key}': "
                    f"expected '{expected_val}', got '{actual_val}'"
                )

        if all_match:
            edits_verified += 1
        else:
            edits_failed += 1

    # Verify creations
    for creation in staging_data.get("stagedCreations", []):
        obj_type = creation.get("object_type")
        attrs = creation.get("attributes", {})
        target_file = creation.get("targetFile")
        name_field = NAME_FIELDS.get(obj_type)
        obj_name = attrs.get(name_field, "") if name_field else ""

        found = _find_object(parsed_objects, obj_type, obj_name, source_file=target_file)
        if found:
            creations_verified += 1
        else:
            creations_failed += 1
            failures.append(f"Creation: {obj_type} '{obj_name}' not found in {target_file}")

    # Verify deletions (need pre_objects to know what was deleted)
    if pre_objects:
        for idx in staging_data.get("stagedObjectDeletions", []):
            if not isinstance(idx, int) or idx < 0 or idx >= len(pre_objects):
                continue
            old_obj = pre_objects[idx]
            obj_type = old_obj.get("object_type")
            source_file = old_obj.get("source_file")
            name_field = NAME_FIELDS.get(obj_type)
            obj_name = old_obj.get("attributes", {}).get(name_field, "") if name_field else ""

            still_exists = _find_object(parsed_objects, obj_type, obj_name,
                                        source_file=source_file)
            if still_exists:
                deletions_failed += 1
                failures.append(f"Deletion: {obj_type} '{obj_name}' still exists in {source_file}")
            else:
                deletions_verified += 1

    # Verify moves
    for move in staging_data.get("stagedMoves", {}).values():
        if not isinstance(move, dict):
            continue
        obj_meta = move.get("object", {})
        target_file = move.get("targetFile")
        obj_type = obj_meta.get("object_type")
        obj_name = obj_meta.get("name")

        found = _find_object(parsed_objects, obj_type, obj_name, source_file=target_file)
        if found:
            moves_verified += 1
        else:
            moves_failed += 1
            failures.append(f"Move: {obj_type} '{obj_name}' not found in {target_file}")

    passed = (edits_failed == 0 and creations_failed == 0
              and deletions_failed == 0 and moves_failed == 0)

    return {
        "passed": passed,
        "editsVerified": edits_verified,
        "editsFailed": edits_failed,
        "creationsVerified": creations_verified,
        "creationsFailed": creations_failed,
        "deletionsVerified": deletions_verified,
        "deletionsFailed": deletions_failed,
        "movesVerified": moves_verified,
        "movesFailed": moves_failed,
        "failures": failures,
    }
