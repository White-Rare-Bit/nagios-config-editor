"""Tests for deterministic move ordering in the apply path."""

import os
import shutil
import tempfile

import pytest

from file_operations import extract_all_blocks, assemble_file_from_blocks
from nagios_service import CompositeAction, NagiosService


class TestExtractAllBlocks:
    def test_extract_two_blocks(self):
        content = (
            "# File header comment\n\n"
            "define host {\n    host_name    a\n}\n\n"
            "define host {\n    host_name    b\n}\n"
        )
        blocks = extract_all_blocks(content)
        assert len(blocks) == 2
        assert "host_name    a" in blocks[0][2]
        assert "host_name    b" in blocks[1][2]

    def test_extract_preserves_order(self):
        content = (
            "define host {\n    host_name    first\n}\n\n"
            "define service {\n    service_description    svc1\n    host_name    first\n}\n\n"
            "define host {\n    host_name    second\n}\n"
        )
        blocks = extract_all_blocks(content)
        assert len(blocks) == 3
        assert blocks[0][0] < blocks[1][0] < blocks[2][0]

    def test_extract_empty_file(self):
        blocks = extract_all_blocks("")
        assert blocks == []

    def test_extract_preamble_only(self):
        content = "# Just a comment\n# No define blocks\n"
        blocks = extract_all_blocks(content)
        assert blocks == []

    def test_start_end_positions(self):
        content = "define host {\n    host_name    x\n}\n"
        blocks = extract_all_blocks(content)
        assert len(blocks) == 1
        start, end, text = blocks[0]
        assert content[start:end] == text


class TestAssembleFileFromBlocks:
    def test_preserves_preamble(self):
        preamble = "# My hosts file\n# Auto-generated\n"
        blocks = [
            "define host {\n    host_name    c\n}",
            "define host {\n    host_name    a\n}",
        ]
        result = assemble_file_from_blocks(preamble, blocks)
        assert result.startswith("# My hosts file\n")
        assert result.index("host_name    c") < result.index("host_name    a")

    def test_empty_preamble(self):
        blocks = ["define host {\n    host_name    x\n}"]
        result = assemble_file_from_blocks("", blocks)
        assert result.startswith("define host")
        assert result.endswith("\n")

    def test_trailing_newline(self):
        result = assemble_file_from_blocks("", ["define host {\n    host_name    a\n}"])
        assert result.endswith("\n")
        assert not result.endswith("\n\n")

    def test_two_blank_lines_between_blocks(self):
        blocks = [
            "define host {\n    host_name    a\n}",
            "define host {\n    host_name    b\n}",
        ]
        result = assemble_file_from_blocks("", blocks)
        assert "\n\n\n" not in result  # no triple newlines
        # Two blocks separated by exactly 2 blank lines = \n\n between them
        parts = result.split("\n\n")
        assert len(parts) == 2

    def test_empty_blocks(self):
        result = assemble_file_from_blocks("# header\n", [])
        assert result == "# header\n"

    def test_preamble_with_trailing_whitespace(self):
        preamble = "# header\n\n\n"
        blocks = ["define host {\n    host_name    a\n}"]
        result = assemble_file_from_blocks(preamble, blocks)
        # Should not have excessive blank lines between preamble and first block
        assert "\n\n\n\n" not in result


# --- Fixtures for service-level tests ---

@pytest.fixture
def config_dir():
    """Create a temp config dir with hosts.cfg and services.cfg."""
    d = tempfile.mkdtemp()
    hosts = os.path.join(d, "hosts.cfg")
    services = os.path.join(d, "services.cfg")
    with open(hosts, "w") as f:
        f.write(
            "define host {\n"
            "    host_name    web-01\n"
            "    alias        Web Server 1\n"
            "    address      10.0.0.1\n"
            "}\n\n"
            "define host {\n"
            "    host_name    web-02\n"
            "    alias        Web Server 2\n"
            "    address      10.0.0.2\n"
            "}\n\n"
            "define host {\n"
            "    host_name    web-03\n"
            "    alias        Web Server 3\n"
            "    address      10.0.0.3\n"
            "}\n"
        )
    with open(services, "w") as f:
        f.write(
            "define host {\n"
            "    host_name    existing-svc\n"
            "    alias        Existing\n"
            "    address      10.0.1.1\n"
            "}\n"
        )
    yield d
    shutil.rmtree(d)


@pytest.fixture
def service(config_dir):
    return NagiosService(config_dir)


class TestComputeExpectedFileOrder:
    def test_cross_file_moves_ordered_by_insert_position(self, service, config_dir):
        """Two objects moved to services.cfg with explicit positions."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        # Move web-02 at position 10, web-01 at position 20
        move_actions = [
            CompositeAction(
                action_type="move",
                stable_key=f"{os.path.realpath(hosts)}|host|web-02",
                object_type="host",
                object_name="web-02",
                source_file=hosts,
                original_attrs={"host_name": "web-02", "alias": "Web Server 2", "address": "10.0.0.2"},
                target_file=services,
                insert_position=10,
            ),
            CompositeAction(
                action_type="move",
                stable_key=f"{os.path.realpath(hosts)}|host|web-01",
                object_type="host",
                object_name="web-01",
                source_file=hosts,
                original_attrs={"host_name": "web-01", "alias": "Web Server 1", "address": "10.0.0.1"},
                target_file=services,
                insert_position=20,
            ),
        ]
        # incoming = actions targeting services.cfg
        incoming = [a for a in move_actions if os.path.realpath(a.target_file) == os.path.realpath(services)]
        order = service._compute_expected_file_order(
            services, incoming, move_actions, set(),
        )
        names = [item["name"] for item in order]
        # existing-svc is at line 1 (position < 10), so it stays first
        # Then web-02 (pos 10), then web-01 (pos 20)
        assert names == ["existing-svc", "web-02", "web-01"]

    def test_same_file_reorder(self, service, config_dir):
        """Reorder objects within same file."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        hosts_real = os.path.realpath(hosts)
        # Move web-03 to position 0 (before everything), web-01 to position 5
        move_actions = [
            CompositeAction(
                action_type="move",
                stable_key=f"{hosts_real}|host|web-03",
                object_type="host",
                object_name="web-03",
                source_file=hosts,
                original_attrs={"host_name": "web-03", "alias": "Web Server 3", "address": "10.0.0.3"},
                target_file=hosts,
                insert_position=0,
            ),
            CompositeAction(
                action_type="move",
                stable_key=f"{hosts_real}|host|web-01",
                object_type="host",
                object_name="web-01",
                source_file=hosts,
                original_attrs={"host_name": "web-01", "alias": "Web Server 1", "address": "10.0.0.1"},
                target_file=hosts,
                insert_position=5,
            ),
        ]
        incoming = move_actions  # same file, so all are incoming
        order = service._compute_expected_file_order(
            hosts, incoming, move_actions, set(),
        )
        names = [item["name"] for item in order]
        # web-03 at pos 0, web-01 at pos 5, web-02 stays (not moved, keeps original line ~7)
        assert names == ["web-03", "web-01", "web-02"]

    def test_mixed_existing_and_incoming(self, service, config_dir):
        """File has existing objects + incoming moves interleaved."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        svc_real = os.path.realpath(services)
        hosts_real = os.path.realpath(hosts)
        # Move web-01 to services.cfg at position 0 (before existing-svc)
        move_actions = [
            CompositeAction(
                action_type="move",
                stable_key=f"{hosts_real}|host|web-01",
                object_type="host",
                object_name="web-01",
                source_file=hosts,
                original_attrs={"host_name": "web-01", "alias": "Web Server 1", "address": "10.0.0.1"},
                target_file=services,
                insert_position=0,
            ),
        ]
        incoming = move_actions
        order = service._compute_expected_file_order(
            services, incoming, move_actions, set(),
        )
        names = [item["name"] for item in order]
        assert names == ["web-01", "existing-svc"]

    def test_deleted_objects_excluded(self, service, config_dir):
        """Objects staged for deletion are excluded from expected order."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        hosts_real = os.path.realpath(hosts)
        delete_keys = {f"{hosts_real}|host|web-02"}
        order = service._compute_expected_file_order(
            hosts, [], [], delete_keys,
        )
        names = [item["name"] for item in order]
        assert "web-02" not in names
        assert "web-01" in names
        assert "web-03" in names


class TestBatchedMoveApply:
    """End-to-end tests for _exec_moves_batched via apply_object_composite."""

    def test_two_cross_file_moves_preserve_order(self, service, config_dir):
        """Move web-01 and web-02 from hosts.cfg to services.cfg.
        web-02 at position 10, web-01 at position 20.
        After apply: services.cfg has existing-svc, web-02, web-01."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        staging = {
            "pendingEdits": {},
            "stagedMoves": {
                f"{hosts}|host|web-02": {
                    "targetFile": services,
                    "insertPosition": 10,
                },
                f"{hosts}|host|web-01": {
                    "targetFile": services,
                    "insertPosition": 20,
                },
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["moves"] == 2
        # Re-parse and verify order
        service._parser = None
        svc_objs = [
            o for o in service.parser.objects
            if os.path.realpath(o.source_file) == os.path.realpath(services)
        ]
        svc_objs.sort(key=lambda o: o.line_number)
        names = [o.attributes.get("host_name") for o in svc_objs]
        assert names == ["existing-svc", "web-02", "web-01"]

    def test_same_file_reorder_three_objects(self, service, config_dir):
        """Reorder web-01, web-02, web-03 to web-03, web-01, web-02."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        staging = {
            "pendingEdits": {},
            "stagedMoves": {
                f"{hosts}|host|web-03": {
                    "targetFile": hosts,
                    "insertPosition": 0,
                },
                f"{hosts}|host|web-01": {
                    "targetFile": hosts,
                    "insertPosition": 5,
                },
                # web-02 is not moved, stays in place
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        # Re-parse and verify order
        service._parser = None
        host_objs = [
            o for o in service.parser.objects
            if os.path.realpath(o.source_file) == os.path.realpath(hosts)
        ]
        host_objs.sort(key=lambda o: o.line_number)
        names = [o.attributes.get("host_name") for o in host_objs]
        assert names == ["web-03", "web-01", "web-02"]

    def test_source_objects_removed(self, service, config_dir):
        """After cross-file move, source file no longer has the objects."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        staging = {
            "pendingEdits": {},
            "stagedMoves": {
                f"{hosts}|host|web-01": {
                    "targetFile": services,
                    "insertPosition": None,
                },
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        service._parser = None
        hosts_objs = [
            o for o in service.parser.objects
            if os.path.realpath(o.source_file) == os.path.realpath(hosts)
        ]
        host_names = [o.attributes.get("host_name") for o in hosts_objs]
        assert "web-01" not in host_names
        # web-02 and web-03 should still be in hosts
        assert "web-02" in host_names
        assert "web-03" in host_names

    def test_raw_block_formatting_preserved(self, service, config_dir):
        """Move object with inline comments. Verify formatting kept."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        # Rewrite hosts.cfg with custom formatting
        with open(hosts, "w") as f:
            f.write(
                "define host {\n"
                "    host_name    web-01  ; primary server\n"
                "    alias        Web Server 1\n"
                "    address      10.0.0.1\n"
                "}\n"
            )
        service._parser = None
        staging = {
            "pendingEdits": {},
            "stagedMoves": {
                f"{hosts}|host|web-01": {
                    "targetFile": services,
                    "insertPosition": None,
                },
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        # Read services.cfg and check inline comment preserved
        with open(services) as f:
            content = f.read()
        assert "; primary server" in content

    def test_interleaved_moves_with_existing_objects(self, config_dir):
        """Regression: two moves interleaving with existing objects.

        services.cfg has Alpha (line 1), Gamma (line 7).
        Move Beta at insertPosition=4 (between Alpha and Gamma).
        Move Delta at insertPosition=8 (after Gamma).
        Expected: Alpha, Beta, Gamma, Delta.

        The sequential approach fails because after inserting Beta,
        Gamma shifts from line 7 to ~13, so Delta's insertPosition=8
        resolves to "after Beta" instead of "after Gamma".
        """
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        # Set up services.cfg with two existing objects
        with open(services, "w") as f:
            f.write(
                "define host {\n"
                "    host_name    alpha\n"
                "    alias        Alpha\n"
                "    address      10.0.1.1\n"
                "}\n\n"
                "define host {\n"
                "    host_name    gamma\n"
                "    alias        Gamma\n"
                "    address      10.0.1.3\n"
                "}\n"
            )
        # Set up hosts.cfg with two objects to move
        with open(hosts, "w") as f:
            f.write(
                "define host {\n"
                "    host_name    beta\n"
                "    alias        Beta\n"
                "    address      10.0.1.2\n"
                "}\n\n"
                "define host {\n"
                "    host_name    delta\n"
                "    alias        Delta\n"
                "    address      10.0.1.4\n"
                "}\n"
            )
        svc = NagiosService(config_dir)
        staging = {
            "pendingEdits": {},
            "stagedMoves": {
                f"{hosts}|host|beta": {
                    "targetFile": services,
                    "insertPosition": 4,
                },
                f"{hosts}|host|delta": {
                    "targetFile": services,
                    "insertPosition": 8,
                },
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = svc.apply_object_composite(staging)
        assert result.success
        svc._parser = None
        svc_objs = [
            o for o in svc.parser.objects
            if os.path.realpath(o.source_file) == os.path.realpath(services)
        ]
        svc_objs.sort(key=lambda o: o.line_number)
        names = [o.attributes.get("host_name") for o in svc_objs]
        assert names == ["alpha", "beta", "gamma", "delta"]

    def test_move_edit_applies_edit_after_batch(self, service, config_dir):
        """move_edit action: move to new file, then edit attributes."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        stable_key = f"{hosts}|host|web-01"
        staging = {
            "pendingEdits": {
                stable_key: {
                    "original": {
                        "host_name": "web-01",
                        "alias": "Web Server 1",
                        "address": "10.0.0.1",
                    },
                    "edited": {
                        "host_name": "web-01",
                        "alias": "Moved And Edited",
                        "address": "10.0.0.1",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "web-01",
                    },
                }
            },
            "stagedMoves": {
                stable_key: {
                    "targetFile": services,
                    "insertPosition": None,
                },
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["move_edits"] == 1
        # Verify the edit was applied
        service._parser = None
        web01s = [
            o for o in service.parser.objects
            if o.attributes.get("host_name") == "web-01"
        ]
        assert len(web01s) == 1
        assert os.path.realpath(web01s[0].source_file) == os.path.realpath(services)
        assert web01s[0].attributes["alias"] == "Moved And Edited"
