"""Tests for apply verification module."""

import os

from apply_verification import build_expected_changeset, compare_file_changes, verify_objects
from nagios_model import NAME_FIELDS


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


def test_perfect_match():
    """All expected changes present, no unexpected changes."""
    expected = {"modified": {"/cfg/hosts.cfg"}, "created": set(), "deleted": set()}
    pre_files = []
    post_files = [{"path": "hosts.cfg", "status_code": " M"}]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is True
    assert report["unexpected"] == []
    assert report["missing"] == []


def test_unexpected_file_changed():
    """A file changed on disk that staging didn't intend to touch."""
    expected = {"modified": {"/cfg/hosts.cfg"}, "created": set(), "deleted": set()}
    pre_files = []
    post_files = [
        {"path": "hosts.cfg", "status_code": " M"},
        {"path": "services.cfg", "status_code": " M"},
    ]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is False
    assert any("services.cfg" in u for u in report["unexpected"])


def test_missing_expected_change():
    """Staging expected to modify a file but git shows no diff."""
    expected = {"modified": {"/cfg/hosts.cfg"}, "created": set(), "deleted": set()}
    pre_files = []
    post_files = []
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is False
    assert any("hosts.cfg" in m for m in report["missing"])


def test_pre_existing_changes_excluded():
    """Files already dirty before apply are not flagged as unexpected."""
    expected = {"modified": {"/cfg/hosts.cfg"}, "created": set(), "deleted": set()}
    pre_files = [{"path": "unrelated.cfg", "status_code": " M"}]
    post_files = [
        {"path": "hosts.cfg", "status_code": " M"},
        {"path": "unrelated.cfg", "status_code": " M"},
    ]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is True
    assert report["unexpected"] == []


def test_file_creation_detected():
    expected = {"modified": set(), "created": {"/cfg/new.cfg"}, "deleted": set()}
    pre_files = []
    post_files = [{"path": "new.cfg", "status_code": "??"}]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is True


def test_file_deletion_detected():
    expected = {"modified": set(), "created": set(), "deleted": {"/cfg/old.cfg"}}
    pre_files = []
    post_files = [{"path": "old.cfg", "status_code": " D"}]
    config_path = "/cfg"

    report = compare_file_changes(expected, pre_files, post_files, config_path)
    assert report["passed"] is True


def test_verify_edits_pass():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "edited": {"alias": "New Alias"},
            },
        },
    }
    # After apply, parser has the object with the new alias
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "web01", "alias": "New Alias", "address": "1.2.3.4"}},
    ]
    report = verify_objects(staging, parsed)
    assert report["passed"] is True
    assert report["editsVerified"] == 1


def test_verify_edits_fail_wrong_value():
    staging = {
        "pendingEdits": {
            "0": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "edited": {"alias": "New Alias"},
            },
        },
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "web01", "alias": "Old Alias"}},
    ]
    report = verify_objects(staging, parsed)
    assert report["passed"] is False
    assert report["editsFailed"] == 1
    assert len(report["failures"]) == 1


def test_verify_creation_exists():
    staging = {
        "stagedCreations": [
            {"object_type": "host", "targetFile": "/cfg/hosts.cfg",
             "attributes": {"host_name": "newhost", "alias": "New"}},
        ],
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "newhost", "alias": "New"}},
    ]
    report = verify_objects(staging, parsed)
    assert report["passed"] is True
    assert report["creationsVerified"] == 1


def test_verify_creation_missing():
    staging = {
        "stagedCreations": [
            {"object_type": "host", "targetFile": "/cfg/hosts.cfg",
             "attributes": {"host_name": "newhost"}},
        ],
    }
    parsed = []
    report = verify_objects(staging, parsed)
    assert report["passed"] is False
    assert report["creationsFailed"] == 1


def test_verify_deletion_gone():
    staging = {
        "stagedObjectDeletions": [0],
    }
    pre_objects = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "oldhost"}},
    ]
    parsed = []
    report = verify_objects(staging, parsed, pre_objects=pre_objects)
    assert report["passed"] is True
    assert report["deletionsVerified"] == 1


def test_verify_deletion_still_present():
    staging = {
        "stagedObjectDeletions": [0],
    }
    pre_objects = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "oldhost"}},
    ]
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts.cfg",
         "attributes": {"host_name": "oldhost"}},
    ]
    report = verify_objects(staging, parsed, pre_objects=pre_objects)
    assert report["passed"] is False
    assert report["deletionsFailed"] == 1


def test_verify_move_relocated():
    staging = {
        "stagedMoves": {
            "key1": {
                "object": {"source_file": "/cfg/hosts.cfg",
                           "object_type": "host", "name": "web01"},
                "targetFile": "/cfg/hosts-prod.cfg",
            },
        },
    }
    parsed = [
        {"object_type": "host", "source_file": "/cfg/hosts-prod.cfg",
         "attributes": {"host_name": "web01"}},
    ]
    report = verify_objects(staging, parsed)
    assert report["passed"] is True
    assert report["movesVerified"] == 1
