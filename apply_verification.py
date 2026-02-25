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
