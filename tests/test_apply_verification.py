"""Tests for apply verification module."""

import os

from apply_verification import build_expected_changeset


def test_empty_staging_returns_empty_changeset():
    changeset = build_expected_changeset({})
    assert changeset == {"modified": set(), "created": set(), "deleted": set()}


def test_pending_edits_expect_modified_files():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {
                    "source_file": "/etc/nagios/hosts.cfg",
                    "object_type": "host",
                    "name": "web01",
                },
                "edited": {"alias": "New Alias"},
            },
        },
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]


def test_staged_creations_expect_modified_or_created():
    staging = {
        "stagedCreations": [
            {"object_type": "host", "targetFile": "/etc/nagios/hosts.cfg",
             "attributes": {"host_name": "new"}},
        ],
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]


def test_staged_deletions_use_object_lookup():
    """Deletions need parser objects to know which files are affected.
    Without parser_objects, deletions are skipped gracefully."""
    staging = {"stagedObjectDeletions": [0, 3]}
    changeset = build_expected_changeset(staging)
    # No parser_objects provided, so no files expected
    assert changeset["modified"] == set()


def test_staged_deletions_with_parser_objects():
    parser_objects = [
        {"source_file": "/etc/nagios/hosts.cfg", "object_type": "host"},
        {"source_file": "/etc/nagios/services.cfg", "object_type": "service"},
        {"source_file": "/etc/nagios/hosts.cfg", "object_type": "host"},
        {"source_file": "/etc/nagios/commands.cfg", "object_type": "command"},
    ]
    staging = {"stagedObjectDeletions": [0, 3]}
    changeset = build_expected_changeset(staging, parser_objects=parser_objects)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]
    assert "/etc/nagios/commands.cfg" in changeset["modified"]


def test_staged_moves_expect_both_files():
    staging = {
        "stagedMoves": {
            "key1": {
                "object": {"source_file": "/etc/nagios/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "targetFile": "/etc/nagios/hosts-prod.cfg",
            },
        },
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]
    assert "/etc/nagios/hosts-prod.cfg" in changeset["modified"]


def test_file_creations():
    staging = {"stagedFileCreations": [{"path": "/etc/nagios/new.cfg"}]}
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/new.cfg" in changeset["created"]


def test_file_deletions():
    staging = {"stagedFileDeletions": [{"path": "/etc/nagios/old.cfg"}]}
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/old.cfg" in changeset["deleted"]


def test_file_moves_expect_delete_source_create_target():
    staging = {
        "stagedFileMoves": [
            {"sourcePath": "/etc/nagios/old.cfg", "targetPath": "/etc/nagios/new.cfg"},
        ],
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/old.cfg" in changeset["deleted"]
    assert "/etc/nagios/new.cfg" in changeset["created"]


def test_combined_operations():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/etc/nagios/hosts.cfg",
                           "object_type": "host", "name": "w1"},
                "edited": {"alias": "x"},
            },
        },
        "stagedFileCreations": [{"path": "/etc/nagios/new.cfg"}],
        "stagedFileDeletions": [{"path": "/etc/nagios/old.cfg"}],
    }
    changeset = build_expected_changeset(staging)
    assert "/etc/nagios/hosts.cfg" in changeset["modified"]
    assert "/etc/nagios/new.cfg" in changeset["created"]
    assert "/etc/nagios/old.cfg" in changeset["deleted"]
