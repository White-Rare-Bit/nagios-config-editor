"""Robustness tests for the staging → apply flow.

These tests assert CORRECT behavior for edge cases in bulk operations.
Tests marked xfail are expected to FAIL with the current implementation,
proving the bug exists. After a fix, remove the xfail marker.
"""

import os
import shutil
import tempfile

import pytest

from nagios_service import NagiosService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def two_file_config():
    """Two config files, each with 2 hosts.  Alphabetical order a < b
    guarantees parser assigns indices 0,1 to a_hosts.cfg and 2,3 to
    b_hosts.cfg.
    """
    d = tempfile.mkdtemp()
    a_cfg = os.path.join(d, "a_hosts.cfg")
    b_cfg = os.path.join(d, "b_hosts.cfg")

    with open(a_cfg, "w") as f:
        f.write(
            "define host {\n"
            "    host_name    alpha\n"
            "    alias        Alpha Host\n"
            "    address      10.0.0.1\n"
            "}\n\n"
            "define host {\n"
            "    host_name    bravo\n"
            "    alias        Bravo Host\n"
            "    address      10.0.0.2\n"
            "}\n"
        )

    with open(b_cfg, "w") as f:
        f.write(
            "define host {\n"
            "    host_name    charlie\n"
            "    alias        Charlie Host\n"
            "    address      10.0.0.3\n"
            "}\n\n"
            "define host {\n"
            "    host_name    delta\n"
            "    alias        Delta Host\n"
            "    address      10.0.0.4\n"
            "}\n"
        )

    yield d
    shutil.rmtree(d)


@pytest.fixture
def three_file_config():
    """Three config files with 2 hosts each (6 objects total)."""
    d = tempfile.mkdtemp()

    for filename, hosts in [
        ("a_hosts.cfg", [("alpha", "10.0.0.1"), ("bravo", "10.0.0.2")]),
        ("b_hosts.cfg", [("charlie", "10.0.0.3"), ("delta", "10.0.0.4")]),
        ("c_hosts.cfg", [("echo", "10.0.0.5"), ("foxtrot", "10.0.0.6")]),
    ]:
        path = os.path.join(d, filename)
        with open(path, "w") as f:
            for name, addr in hosts:
                f.write(
                    f"define host {{\n"
                    f"    host_name    {name}\n"
                    f"    alias        {name.title()} Host\n"
                    f"    address      {addr}\n"
                    f"}}\n\n"
                )

    yield d
    shutil.rmtree(d)


@pytest.fixture
def single_file_config():
    """Single config file with 4 hosts for within-file delete tests."""
    d = tempfile.mkdtemp()
    cfg = os.path.join(d, "hosts.cfg")

    with open(cfg, "w") as f:
        for name, addr in [
            ("alpha", "10.0.0.1"),
            ("bravo", "10.0.0.2"),
            ("charlie", "10.0.0.3"),
            ("delta", "10.0.0.4"),
        ]:
            f.write(
                f"define host {{\n"
                f"    host_name    {name}\n"
                f"    alias        {name.title()} Host\n"
                f"    address      {addr}\n"
                f"}}\n\n"
            )

    yield d
    shutil.rmtree(d)


def _host_names(service):
    """Return sorted list of host_name values from current parser state."""
    return sorted(
        obj.attributes.get("host_name", "?")
        for obj in service.parser.objects
        if obj.object_type == "host"
    )


def _find_index(service, host_name):
    """Find global_index for a host by name."""
    for i, obj in enumerate(service.parser.objects):
        if obj.attributes.get("host_name") == host_name:
            return i
    raise ValueError(f"Host {host_name!r} not found")


def _make_staging(deletions=None, edits=None, moves=None, creations=None):
    """Build a minimal staging data dict."""
    return {
        "pendingEdits": edits or {},
        "stagedMoves": moves or {},
        "stagedCreations": creations or [],
        "stagedObjectDeletions": deletions or [],
    }


# ===================================================================
# Bug 1: Multi-file delete uses stale global indices
# ===================================================================


class TestMultiFileDeleteStaleIndices:
    """Deleting objects across multiple files must find targets by identity,
    not by stale global index.

    Within a single file, the reverse-order sort prevents index drift.
    Across files, the identity-based lookup ensures correct targets.
    """

    def test_delete_from_two_files_correct_objects(self, two_file_config):
        """Delete bravo (file A) and charlie (file B).

        Expected: alpha and delta remain.
        """
        service = NagiosService(two_file_config)
        bravo_idx = _find_index(service, "bravo")
        charlie_idx = _find_index(service, "charlie")

        staging = _make_staging(deletions=[bravo_idx, charlie_idx])
        result = service.apply_object_composite(staging)
        assert result.success

        remaining = _host_names(service)
        assert remaining == ["alpha", "delta"]

    def test_delete_from_three_files(self, three_file_config):
        """Delete one host from each of three files.

        Delete bravo (file A), charlie (file B), echo (file C).
        Expected remaining: alpha, delta, foxtrot.
        """
        service = NagiosService(three_file_config)
        bravo_idx = _find_index(service, "bravo")
        charlie_idx = _find_index(service, "charlie")
        echo_idx = _find_index(service, "echo")

        staging = _make_staging(deletions=[bravo_idx, charlie_idx, echo_idx])
        result = service.apply_object_composite(staging)
        assert result.success

        remaining = _host_names(service)
        assert remaining == ["alpha", "delta", "foxtrot"]

    def test_delete_within_single_file_correct(self, single_file_config):
        """Baseline: deletes within a single file use reverse-order sort
        and should work correctly.
        """
        service = NagiosService(single_file_config)
        bravo_idx = _find_index(service, "bravo")
        charlie_idx = _find_index(service, "charlie")

        staging = _make_staging(deletions=[bravo_idx, charlie_idx])
        result = service.apply_object_composite(staging)
        assert result.success

        remaining = _host_names(service)
        assert remaining == ["alpha", "delta"]


# ===================================================================
# Bug 2: Apply is not idempotent — retry creates duplicates
# ===================================================================


class TestApplyRetryDuplicates:
    """After a successful apply, re-applying the same staging data
    must not corrupt state.  In a partial-failure retry scenario the
    staging is preserved verbatim, so the retry re-executes everything
    including already-completed operations.
    """

    @pytest.mark.xfail(
        reason="Bug: re-applying create staging produces duplicate objects",
        strict=True,
    )
    def test_create_replay_does_not_duplicate(self, two_file_config):
        """Apply a creation twice — second apply must not add a duplicate."""
        service = NagiosService(two_file_config)
        target = os.path.join(two_file_config, "a_hosts.cfg")

        staging = _make_staging(
            creations=[
                {
                    "object_type": "host",
                    "targetFile": target,
                    "attributes": {
                        "host_name": "new-host",
                        "alias": "New Host",
                        "address": "10.0.0.99",
                    },
                }
            ]
        )

        # First apply — should create the host
        result1 = service.apply_object_composite(staging)
        assert result1.success
        assert result1.data["counts"]["creates"] == 1

        count_after_first = len(service.parser.objects)

        # Second apply (simulates retry after partial failure)
        result2 = service.apply_object_composite(staging)

        # Object count should not increase
        count_after_second = len(service.parser.objects)
        assert count_after_second == count_after_first, (
            f"Duplicate created: {count_after_second} objects after retry "
            f"vs {count_after_first} after first apply"
        )

    def test_move_replay_fails_gracefully(self, two_file_config):
        """Apply a move twice — second apply fails gracefully without data loss.

        The second apply can't find the object at the original source file
        (it was already moved), so it reports an error but doesn't corrupt state.
        """
        service = NagiosService(two_file_config)
        a_cfg = os.path.join(two_file_config, "a_hosts.cfg")
        b_cfg = os.path.join(two_file_config, "b_hosts.cfg")

        alpha = service.parser.objects[_find_index(service, "alpha")]
        stable_key = f"{os.path.realpath(a_cfg)}|host|alpha"

        staging = _make_staging(
            moves={
                stable_key: {
                    "targetFile": b_cfg,
                    "insertPosition": None,
                    "object": {
                        "source_file": a_cfg,
                        "object_type": "host",
                        "display_name": "alpha",
                        "attributes": dict(alpha.attributes),
                    },
                }
            }
        )

        # First apply — moves alpha from a→b
        result1 = service.apply_object_composite(staging)
        assert result1.success
        assert result1.data["counts"]["moves"] == 1

        # Second apply (simulates retry) — should fail to find object
        result2 = service.apply_object_composite(staging)
        assert result2.data["errors"], "Second apply should report move error"

        # alpha should still exist exactly once, in b_hosts.cfg (no corruption)
        alphas = [
            o for o in service.parser.objects
            if o.attributes.get("host_name") == "alpha"
        ]
        assert len(alphas) == 1, f"Expected 1 alpha, found {len(alphas)}"
        assert os.path.realpath(alphas[0].source_file) == os.path.realpath(b_cfg)

    def test_delete_replay_does_not_delete_wrong_object(self, single_file_config):
        """Apply a delete twice — second apply must not delete a different object.

        When _deletionIdentities is provided, _build_composite_actions uses
        stored identity (source_file + type + name) instead of the stale index.
        On retry, the identity lookup fails to find the already-deleted object
        and skips it rather than deleting whatever now occupies that index.
        """
        service = NagiosService(single_file_config)
        bravo_idx = _find_index(service, "bravo")
        bravo_obj = service.parser.objects[bravo_idx]

        # Simulate enriched staging data (as the backend save route would produce)
        staging = _make_staging(deletions=[bravo_idx])
        staging["_deletionIdentities"] = {
            str(bravo_idx): {
                "source_file": bravo_obj.source_file,
                "object_type": bravo_obj.object_type,
                "name": "bravo",
            }
        }

        # First apply — deletes bravo
        result1 = service.apply_object_composite(staging)
        assert result1.success
        assert "bravo" not in _host_names(service)

        remaining_after_first = _host_names(service)

        # Second apply (simulates retry with same staging data)
        result2 = service.apply_object_composite(staging)

        # Must not delete any additional objects
        remaining_after_second = _host_names(service)
        assert remaining_after_second == remaining_after_first, (
            f"Retry deleted additional objects: "
            f"was {remaining_after_first}, now {remaining_after_second}"
        )


# ===================================================================
# Bug 3: Composite phase continues after individual failure
# ===================================================================


class TestCompositeErrorIsolation:
    """If one operation in the composite phase fails, subsequent
    operations still execute.  This tests whether that continuation
    is safe or leads to corruption.
    """

    def test_out_of_range_delete_silently_skipped(self, two_file_config):
        """An out-of-range delete index is filtered by _build_composite_actions
        and never reaches _exec_delete.  The edit still applies.
        """
        service = NagiosService(two_file_config)
        alpha_idx = _find_index(service, "alpha")
        a_cfg = os.path.join(two_file_config, "a_hosts.cfg")

        staging = _make_staging(
            deletions=[999],
            edits={
                str(alpha_idx): {
                    "original": {"host_name": "alpha", "alias": "Alpha Host", "address": "10.0.0.1"},
                    "edited": {"host_name": "alpha", "alias": "Updated Alpha", "address": "10.0.0.1"},
                    "object": {
                        "source_file": a_cfg,
                        "object_type": "host",
                        "display_name": "alpha",
                        "global_index": alpha_idx,
                    },
                }
            },
        )

        result = service.apply_object_composite(staging)
        # Out-of-range index silently filtered — no error, edit still applies
        assert not result.data["errors"], "Invalid index should be silently filtered"
        assert result.data["counts"]["edits"] == 1
        assert result.data["counts"]["deletes"] == 0

        alpha = next(
            o for o in service.parser.objects
            if o.attributes.get("host_name") == "alpha"
        )
        assert alpha.attributes["alias"] == "Updated Alpha"

    def test_cross_file_delete_doesnt_corrupt_subsequent_edit(self, two_file_config):
        """Delete from file A + edit in file B.

        The delete shifts global indices, but edits use identity-based lookup
        (_find_by_identity with file+type+name), NOT global_index.
        So edits are safe even when mixed with cross-file deletes.
        """
        service = NagiosService(two_file_config)
        bravo_idx = _find_index(service, "bravo")
        charlie_idx = _find_index(service, "charlie")
        b_cfg = os.path.join(two_file_config, "b_hosts.cfg")

        staging = _make_staging(
            deletions=[bravo_idx],
            edits={
                str(charlie_idx): {
                    "original": {"host_name": "charlie", "alias": "Charlie Host", "address": "10.0.0.3"},
                    "edited": {"host_name": "charlie", "alias": "Updated Charlie", "address": "10.0.0.3"},
                    "object": {
                        "source_file": b_cfg,
                        "object_type": "host",
                        "display_name": "charlie",
                        "global_index": charlie_idx,
                    },
                }
            },
        )

        result = service.apply_object_composite(staging)
        assert result.success

        remaining = _host_names(service)
        assert "bravo" not in remaining, "bravo should be deleted"
        assert "charlie" in remaining, "charlie should survive"

        charlie = next(
            o for o in service.parser.objects
            if o.attributes.get("host_name") == "charlie"
        )
        assert charlie.attributes["alias"] == "Updated Charlie"
