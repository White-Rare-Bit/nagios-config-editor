"""Tests for composite apply: _build_composite_actions and apply_object_composite."""

import os
import tempfile
import shutil
import pytest
from nagios_service import NagiosService, CompositeAction


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
                    "original": {"host_name": "web-01", "alias": "Web Server 1",
                                 "address": "10.0.0.1", "use": "linux-server"},
                    "edited": {"host_name": "web-01", "alias": "Edited Alias",
                               "address": "10.0.0.1", "use": "linux-server"},
                    "object": {"source_file": hosts, "object_type": "host",
                               "display_name": "web-01", "global_index": 0},
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
            "stagedCreations": [{
                "object_type": "host",
                "attributes": {"host_name": "new-host", "alias": "New", "address": "10.0.0.50"},
                "targetFile": hosts,
            }],
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
                    "original": {"host_name": "web-01", "alias": "Web Server 1",
                                 "address": "10.0.0.1", "use": "linux-server"},
                    "edited": {"host_name": "web-01", "alias": "Edited",
                               "address": "10.0.0.1", "use": "linux-server"},
                    "object": {"source_file": hosts, "object_type": "host",
                               "display_name": "web-01", "global_index": 0},
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
                    "original": {"host_name": "old-host", "alias": "Old Host",
                                 "address": "10.0.0.99", "use": "linux-server"},
                    "edited": {"host_name": "old-host", "alias": "Should Not Apply",
                               "address": "10.0.0.99", "use": "linux-server"},
                    "object": {"source_file": hosts, "object_type": "host",
                               "display_name": "old-host", "global_index": 2},
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
                    "original": {"host_name": "web-01", "alias": "Web Server 1",
                                 "address": "10.0.0.1", "use": "linux-server"},
                    "edited": {"host_name": "web-01", "alias": "Edited",
                               "address": "10.0.0.1", "use": "linux-server"},
                    "object": {"source_file": hosts, "object_type": "host",
                               "display_name": "web-01", "global_index": 0},
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
