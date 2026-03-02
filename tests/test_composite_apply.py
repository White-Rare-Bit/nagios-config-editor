"""Tests for composite apply: _build_composite_actions and apply_object_composite."""

import os
import tempfile
import shutil
import pytest
from nagios_service import NagiosService


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
            "    use          linux-server\n"
            "}\n\n"
            "define host {\n"
            "    host_name    web-02\n"
            "    alias        Web Server 2\n"
            "    address      10.0.0.2\n"
            "    use          linux-server\n"
            "}\n\n"
            "define host {\n"
            "    host_name    old-host\n"
            "    alias        Old Host\n"
            "    address      10.0.0.99\n"
            "    use          linux-server\n"
            "}\n"
        )
    with open(services, "w") as f:
        f.write("")  # empty file
    yield d
    shutil.rmtree(d)


@pytest.fixture
def service(config_dir):
    svc = NagiosService(config_dir)
    return svc


class TestBuildCompositeActions:
    """Tests for _build_composite_actions merge logic."""

    def test_edit_only(self, service, config_dir):
        hosts = os.path.join(config_dir, "hosts.cfg")
        staging = {
            "pendingEdits": {
                "0": {
                    "original": {
                        "host_name": "web-01",
                        "alias": "Web Server 1",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "edited": {
                        "host_name": "web-01",
                        "alias": "Edited Alias",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "web-01",
                        "global_index": 0,
                    },
                }
            },
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        actions = service._build_composite_actions(staging)
        assert len(actions) == 1
        assert actions[0].action_type == "edit"
        assert actions[0].object_name == "web-01"

    def test_move_only(self, service, config_dir):
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        staging = {
            "pendingEdits": {},
            "stagedMoves": {
                f"{hosts}|host|web-01": {
                    "global_index": 0,
                    "targetFile": services,
                    "insertPosition": None,
                }
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        actions = service._build_composite_actions(staging)
        assert len(actions) == 1
        assert actions[0].action_type == "move"
        assert actions[0].target_file == services

    def test_delete_only(self, service, config_dir):
        staging = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [2],  # old-host at index 2
        }
        actions = service._build_composite_actions(staging)
        assert len(actions) == 1
        assert actions[0].action_type == "delete"
        assert actions[0].object_name == "old-host"

    def test_create_only(self, service, config_dir):
        hosts = os.path.join(config_dir, "hosts.cfg")
        staging = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedCreations": [
                {
                    "object_type": "host",
                    "attributes": {
                        "host_name": "new-host",
                        "alias": "New",
                        "address": "10.0.0.50",
                    },
                    "targetFile": hosts,
                }
            ],
            "stagedObjectDeletions": [],
        }
        actions = service._build_composite_actions(staging)
        assert len(actions) == 1
        assert actions[0].action_type == "create"
        assert actions[0].object_name == "new-host"

    def test_edit_plus_move_merges_to_move_edit(self, service, config_dir):
        """The original bug scenario: edit + move on same entity -> move_edit."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        stable_key = f"{hosts}|host|web-01"
        staging = {
            "pendingEdits": {
                "0": {
                    "original": {
                        "host_name": "web-01",
                        "alias": "Web Server 1",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "edited": {
                        "host_name": "web-01",
                        "alias": "Edited",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "web-01",
                        "global_index": 0,
                    },
                }
            },
            "stagedMoves": {
                stable_key: {
                    "global_index": 0,
                    "targetFile": services,
                    "insertPosition": None,
                }
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        actions = service._build_composite_actions(staging)
        assert len(actions) == 1
        assert actions[0].action_type == "move_edit"
        assert actions[0].target_file == services
        assert actions[0].final_attrs["alias"] == "Edited"

    def test_delete_wins_over_edit(self, service, config_dir):
        """If same entity has both edit and delete staged, delete wins."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        staging = {
            "pendingEdits": {
                "2": {
                    "original": {
                        "host_name": "old-host",
                        "alias": "Old Host",
                        "address": "10.0.0.99",
                        "use": "linux-server",
                    },
                    "edited": {
                        "host_name": "old-host",
                        "alias": "Should Not Apply",
                        "address": "10.0.0.99",
                        "use": "linux-server",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "old-host",
                        "global_index": 2,
                    },
                }
            },
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [2],
        }
        actions = service._build_composite_actions(staging)
        assert len(actions) == 1
        assert actions[0].action_type == "delete"

    def test_delete_wins_over_move(self, service, config_dir):
        """If same entity has both move and delete staged, delete wins."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        staging = {
            "pendingEdits": {},
            "stagedMoves": {
                f"{hosts}|host|old-host": {
                    "global_index": 2,
                    "targetFile": services,
                    "insertPosition": None,
                }
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [2],
        }
        actions = service._build_composite_actions(staging)
        assert len(actions) == 1
        assert actions[0].action_type == "delete"

    def test_deletes_sorted_reverse_line_order(self, service, config_dir):
        """Deletes should be processed in reverse line order to preserve indices."""
        staging = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [0, 2],  # web-01 (line 1) and old-host (line ~15)
        }
        actions = service._build_composite_actions(staging)
        assert len(actions) == 2
        assert all(a.action_type == "delete" for a in actions)
        # First action should be the later-in-file object (higher global_index)
        assert actions[0].object_name == "old-host"
        assert actions[1].object_name == "web-01"

    def test_multiple_independent_ops(self, service, config_dir):
        """Edit one, move another, delete a third -- all independent."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        staging = {
            "pendingEdits": {
                "0": {
                    "original": {
                        "host_name": "web-01",
                        "alias": "Web Server 1",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "edited": {
                        "host_name": "web-01",
                        "alias": "Edited",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "web-01",
                        "global_index": 0,
                    },
                }
            },
            "stagedMoves": {
                f"{hosts}|host|web-02": {
                    "global_index": 1,
                    "targetFile": services,
                    "insertPosition": None,
                }
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [2],  # old-host
        }
        actions = service._build_composite_actions(staging)
        types = {a.action_type for a in actions}
        assert types == {"edit", "move", "delete"}
        assert len(actions) == 3


class TestApplyObjectComposite:
    """Tests for apply_object_composite end-to-end execution."""

    def test_edit_changes_attribute(self, service, config_dir):
        hosts = os.path.join(config_dir, "hosts.cfg")
        staging = {
            "pendingEdits": {
                "0": {
                    "original": {
                        "host_name": "web-01",
                        "alias": "Web Server 1",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "edited": {
                        "host_name": "web-01",
                        "alias": "New Alias",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "web-01",
                        "global_index": 0,
                    },
                }
            },
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["edits"] == 1
        # Verify on disk
        service._parser.parse_all()
        obj = next(
            o
            for o in service._parser.objects
            if o.attributes.get("host_name") == "web-01"
        )
        assert obj.attributes["alias"] == "New Alias"

    def test_move_relocates_object(self, service, config_dir):
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        staging = {
            "pendingEdits": {},
            "stagedMoves": {
                f"{hosts}|host|web-02": {
                    "global_index": 1,
                    "targetFile": services,
                    "insertPosition": None,
                }
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["moves"] == 1
        # Verify on disk
        service._parser.parse_all()
        files = {
            os.path.realpath(o.source_file)
            for o in service._parser.objects
            if o.attributes.get("host_name") == "web-02"
        }
        assert os.path.realpath(services) in files
        assert os.path.realpath(hosts) not in files

    def test_delete_removes_object(self, service, config_dir):
        staging = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [2],  # old-host
        }
        result = service.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["deletes"] == 1
        service._parser.parse_all()
        names = [o.attributes.get("host_name") for o in service._parser.objects]
        assert "old-host" not in names

    def test_create_adds_object(self, service, config_dir):
        hosts = os.path.join(config_dir, "hosts.cfg")
        staging = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedCreations": [
                {
                    "object_type": "host",
                    "attributes": {
                        "host_name": "new-host",
                        "alias": "New",
                        "address": "10.0.0.50",
                        "use": "linux-server",
                    },
                    "targetFile": hosts,
                }
            ],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["creates"] == 1
        service._parser.parse_all()
        names = [o.attributes.get("host_name") for o in service._parser.objects]
        assert "new-host" in names

    def test_move_edit_no_duplicate(self, service, config_dir):
        """The critical test: edit+move must not create duplicates."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        stable_key = f"{hosts}|host|web-01"
        staging = {
            "pendingEdits": {
                "0": {
                    "original": {
                        "host_name": "web-01",
                        "alias": "Web Server 1",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "edited": {
                        "host_name": "web-01",
                        "alias": "Moved And Edited",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "web-01",
                        "global_index": 0,
                    },
                }
            },
            "stagedMoves": {
                stable_key: {
                    "global_index": 0,
                    "targetFile": services,
                    "insertPosition": None,
                }
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["move_edits"] == 1
        # Verify: exactly ONE web-01, in services.cfg, with edited alias
        service._parser.parse_all()
        web01s = [
            o
            for o in service._parser.objects
            if o.attributes.get("host_name") == "web-01"
        ]
        assert len(web01s) == 1, f"Expected 1 web-01, found {len(web01s)}"
        assert os.path.realpath(web01s[0].source_file) == os.path.realpath(services)
        assert web01s[0].attributes["alias"] == "Moved And Edited"

    def test_multiple_independent_ops(self, service, config_dir):
        """Edit one + move another + delete third in single apply."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        services = os.path.join(config_dir, "services.cfg")
        staging = {
            "pendingEdits": {
                "0": {
                    "original": {
                        "host_name": "web-01",
                        "alias": "Web Server 1",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "edited": {
                        "host_name": "web-01",
                        "alias": "Edited",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "web-01",
                        "global_index": 0,
                    },
                }
            },
            "stagedMoves": {
                f"{hosts}|host|web-02": {
                    "global_index": 1,
                    "targetFile": services,
                    "insertPosition": None,
                }
            },
            "stagedCreations": [],
            "stagedObjectDeletions": [2],  # old-host
        }
        result = service.apply_object_composite(staging)
        assert result.success
        counts = result.data["counts"]
        assert counts["edits"] == 1
        assert counts["moves"] == 1
        assert counts["deletes"] == 1
        # Verify on disk
        service._parser.parse_all()
        names = {o.attributes.get("host_name") for o in service._parser.objects}
        assert "web-01" in names
        assert "web-02" in names
        assert "old-host" not in names

    def test_empty_staging_is_noop(self, service):
        staging = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        assert all(v == 0 for v in result.data["counts"].values())

    def test_details_include_action_type(self, service, config_dir):
        """Each detail dict must include 'action' for audit trail."""
        hosts = os.path.join(config_dir, "hosts.cfg")
        staging = {
            "pendingEdits": {
                "0": {
                    "original": {
                        "host_name": "web-01",
                        "alias": "Web Server 1",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "edited": {
                        "host_name": "web-01",
                        "alias": "X",
                        "address": "10.0.0.1",
                        "use": "linux-server",
                    },
                    "object": {
                        "source_file": hosts,
                        "object_type": "host",
                        "display_name": "web-01",
                        "global_index": 0,
                    },
                }
            },
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [2],
        }
        result = service.apply_object_composite(staging)
        assert result.success
        for detail in result.data["details"]:
            assert "action" in detail
            assert "object_type" in detail
            assert "object_name" in detail


class TestMultiFileDeletes:
    """Tests for deleting objects across multiple files.

    Regression: _exec_delete used stale global_index after parser reloads
    from prior deletes, causing wrong-object deletion or index-out-of-bounds
    when deletes span multiple files.
    """

    @pytest.fixture
    def multi_file_dir(self):
        """Config dir with objects spread across two files."""
        d = tempfile.mkdtemp()
        hosts_a = os.path.join(d, "hosts-a.cfg")
        hosts_b = os.path.join(d, "hosts-b.cfg")
        with open(hosts_a, "w") as f:
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
        with open(hosts_b, "w") as f:
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
    def multi_file_service(self, multi_file_dir):
        return NagiosService(multi_file_dir)

    def test_delete_objects_across_two_files(
        self, multi_file_service, multi_file_dir
    ):
        """Delete one object from each file — indices shift after first delete."""
        svc = multi_file_service
        # Identify the indices for bravo and delta
        bravo_idx = next(
            i
            for i, o in enumerate(svc.parser.objects)
            if o.attributes.get("host_name") == "bravo"
        )
        delta_idx = next(
            i
            for i, o in enumerate(svc.parser.objects)
            if o.attributes.get("host_name") == "delta"
        )

        staging = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [bravo_idx, delta_idx],
        }
        result = svc.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["deletes"] == 2
        assert not result.data["errors"]

        # Verify correct objects remain
        svc._parser.parse_all()
        remaining = {
            o.attributes.get("host_name") for o in svc._parser.objects
        }
        assert remaining == {"alpha", "charlie"}

    def test_delete_all_from_file_a_and_one_from_file_b(
        self, multi_file_service, multi_file_dir
    ):
        """Delete both objects from file A plus one from file B.

        After removing two objects from file A, stored indices for file B
        objects are off by 2 — this is the core stale-index scenario.
        """
        svc = multi_file_service
        alpha_idx = next(
            i
            for i, o in enumerate(svc.parser.objects)
            if o.attributes.get("host_name") == "alpha"
        )
        bravo_idx = next(
            i
            for i, o in enumerate(svc.parser.objects)
            if o.attributes.get("host_name") == "bravo"
        )
        charlie_idx = next(
            i
            for i, o in enumerate(svc.parser.objects)
            if o.attributes.get("host_name") == "charlie"
        )

        staging = {
            "pendingEdits": {},
            "stagedMoves": {},
            "stagedCreations": [],
            "stagedObjectDeletions": [alpha_idx, bravo_idx, charlie_idx],
        }
        result = svc.apply_object_composite(staging)
        assert result.success
        assert result.data["counts"]["deletes"] == 3
        assert not result.data["errors"]

        svc._parser.parse_all()
        remaining = {
            o.attributes.get("host_name") for o in svc._parser.objects
        }
        assert remaining == {"delta"}
