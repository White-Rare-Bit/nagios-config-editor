"""Post-apply verification — confirms disk changes match staging intent.

Two-layer verification:
1. File-level: git status changes vs expected changeset from staging data
2. Object-level: re-parsed objects vs each staging operation's intent
"""

import logging

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
