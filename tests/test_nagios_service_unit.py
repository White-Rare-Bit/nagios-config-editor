"""
Tests for nagios_service.py - NagiosService Layer
"""

import pytest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nagios_service import NagiosService
from nagios_model import NagiosObject


@pytest.fixture
def service_with_hosts(temp_config_dir):
    """Create a service with multiple host configurations."""
    hosts_content = '''define host {
    host_name       server-01
    alias           Server 01
    address         192.168.1.1
}

define host {
    host_name       server-02
    alias           Server 02
    address         192.168.1.2
}

define host {
    host_name       server-03
    alias           Server 03
    address         192.168.1.3
}
'''
    services_content = '''define service {
    host_name                   server-01
    service_description         HTTP
    check_command               check_http
}

define service {
    host_name                   server-02
    service_description         SSH
    check_command               check_ssh
}
'''
    contacts_content = '''define contact {
    contact_name                admin
    alias                       Administrator
    email                       admin@example.com
}

define contactgroup {
    contactgroup_name           admins
    alias                       Admin Group
    members                     admin
}
'''

    hosts_file = os.path.join(temp_config_dir, 'hosts.cfg')
    with open(hosts_file, 'w') as f:
        f.write(hosts_content)

    services_file = os.path.join(temp_config_dir, 'services.cfg')
    with open(services_file, 'w') as f:
        f.write(services_content)

    contacts_file = os.path.join(temp_config_dir, 'contacts.cfg')
    with open(contacts_file, 'w') as f:
        f.write(contacts_content)

    service = NagiosService(temp_config_dir)
    return service


class TestSearchObjects:
    """Tests for search_objects method."""

    def test_search_by_name(self, service_with_hosts):
        """Search objects by name."""
        results = service_with_hosts.search_objects('server-01')
        assert len(results) >= 1
        assert any(obj.object_type == 'host' and 'server-01' in str(obj.attributes)
                   for obj in results)

    def test_search_filtered_by_type(self, service_with_hosts):
        """Search filtered by object type."""
        results = service_with_hosts.search_objects('server', object_type='host')
        assert len(results) == 3
        assert all(obj.object_type == 'host' for obj in results)

    def test_search_filtered_by_field(self, service_with_hosts):
        """Search filtered by specific field."""
        results = service_with_hosts.search_objects('HTTP', field='service_description')
        assert len(results) == 1
        assert results[0].object_type == 'service'
        assert results[0].attributes.get('service_description') == 'HTTP'

    def test_search_empty_results(self, service_with_hosts):
        """Search with no matching results."""
        results = service_with_hosts.search_objects('nonexistent-object-xyz')
        assert len(results) == 0

    def test_search_regex_mode(self, service_with_hosts):
        """Search using regex pattern."""
        results = service_with_hosts.search_objects(r'server-0[12]', use_regex=True)
        assert len(results) >= 2


class TestGetObjectStats:
    """Tests for get_object_stats method."""

    def test_returns_object_counts_by_type(self, service_with_hosts):
        """Returns counts grouped by object type."""
        stats = service_with_hosts.get_object_stats()
        assert 'by_type' in stats
        assert stats['by_type']['host'] == 3
        assert stats['by_type']['service'] == 2
        assert stats['by_type']['contact'] == 1
        assert stats['by_type']['contactgroup'] == 1

    def test_returns_file_count(self, service_with_hosts):
        """Returns count of config files."""
        stats = service_with_hosts.get_object_stats()
        assert 'file_count' in stats
        assert stats['file_count'] == 3

    def test_returns_total_count(self, service_with_hosts):
        """Returns total object count."""
        stats = service_with_hosts.get_object_stats()
        assert 'total' in stats
        assert stats['total'] == 7


class TestTransformName:
    """Tests for transform_name method."""

    def test_simple_find_replace(self, service_with_hosts):
        """Simple find and replace transformation."""
        result = service_with_hosts.transform_name(
            'test-server-01',
            find_pattern='test',
            replace_with='prod'
        )
        assert result == 'prod-server-01'

    def test_prefix_addition(self, service_with_hosts):
        """Add prefix to name."""
        result = service_with_hosts.transform_name(
            'server-01',
            prefix='prod-'
        )
        assert result == 'prod-server-01'

    def test_suffix_addition(self, service_with_hosts):
        """Add suffix to name."""
        result = service_with_hosts.transform_name(
            'server-01',
            suffix='-backup'
        )
        assert result == 'server-01-backup'

    def test_regex_mode(self, service_with_hosts):
        """Transform using regex pattern."""
        result = service_with_hosts.transform_name(
            'server-01-test',
            find_pattern=r'-\d+',
            replace_with='-99',
            use_regex=True
        )
        assert result == 'server-99-test'

    def test_invalid_regex_returns_none(self, service_with_hosts):
        """Invalid regex returns None."""
        result = service_with_hosts.transform_name(
            'server-01',
            find_pattern='[invalid(',
            replace_with='x',
            use_regex=True
        )
        assert result is None

    def test_combined_operations(self, service_with_hosts):
        """Combine find/replace with prefix/suffix."""
        result = service_with_hosts.transform_name(
            'server-01',
            find_pattern='server',
            replace_with='host',
            prefix='prod-',
            suffix='-live'
        )
        assert result == 'prod-host-01-live'


class TestUpdateReferences:
    """Tests for update_references method."""

    def test_updates_references_in_objects(self, service_with_hosts):
        """Updates references in other objects."""
        objects = service_with_hosts.get_objects()
        count = service_with_hosts.update_references(
            objects,
            old_name='admin',
            new_name='superadmin'
        )
        assert count >= 1

        # Verify contactgroup was updated
        for obj in objects:
            if obj.object_type == 'contactgroup':
                assert 'superadmin' in obj.attributes.get('members', '')

    def test_returns_count_of_updated_references(self, service_with_hosts):
        """Returns count of individual reference updates."""
        objects = service_with_hosts.get_objects()
        count = service_with_hosts.update_references(
            objects,
            old_name='admin',
            new_name='administrator'
        )
        assert count >= 1

    def test_updates_comma_separated_values(self, temp_config_dir):
        """Updates references in comma-separated lists."""
        config_content = '''define hostgroup {
    hostgroup_name      servers
    alias               All Servers
    members             server-01,server-02,server-03
}
'''
        config_file = os.path.join(temp_config_dir, 'hostgroups.cfg')
        with open(config_file, 'w') as f:
            f.write(config_content)

        service = NagiosService(temp_config_dir)
        objects = service.get_objects()
        count = service.update_references(
            objects,
            old_name='server-02',
            new_name='server-new'
        )
        assert count == 1

        # Verify update
        for obj in objects:
            if obj.object_type == 'hostgroup':
                members = obj.attributes.get('members', '')
                assert 'server-new' in members
                assert 'server-02' not in members


class TestFindObjectByStableKey:
    """Tests for find_object_by_stable_key method."""

    def test_finds_by_stable_key(self, service_with_hosts):
        """Finds object by file+type+name key."""
        objects = service_with_hosts.get_objects()
        host_obj = None
        for obj in objects:
            if obj.object_type == 'host' and obj.attributes.get('host_name') == 'server-01':
                host_obj = obj
                break

        assert host_obj is not None
        stable_key = f"{host_obj.source_file}|host|server-01"
        result = service_with_hosts.find_object_by_stable_key(stable_key)

        assert result is not None
        idx, found_obj = result
        assert found_obj.object_type == 'host'
        assert found_obj.attributes.get('host_name') == 'server-01'

    def test_returns_none_for_nonexistent(self, service_with_hosts):
        """Returns None for non-existent key."""
        stable_key = "/fake/path.cfg|host|nonexistent"
        result = service_with_hosts.find_object_by_stable_key(stable_key)
        assert result is None


class TestFindObjectByIndex:
    """Tests for find_object_by_index method."""

    def test_valid_index_returns_object(self, service_with_hosts):
        """Valid index returns object."""
        obj = service_with_hosts.find_object_by_index(0)
        assert obj is not None
        assert isinstance(obj, NagiosObject)

    def test_invalid_index_returns_none(self, service_with_hosts):
        """Invalid index returns None."""
        obj = service_with_hosts.find_object_by_index(9999)
        assert obj is None

    def test_negative_index_returns_none(self, service_with_hosts):
        """Negative index returns None."""
        obj = service_with_hosts.find_object_by_index(-1)
        assert obj is None


class TestApplyObjectEdits:
    """Tests for apply_object_edits method."""

    def test_edits_objects_on_disk(self, temp_config_dir):
        """Edits objects and persists to disk."""
        config_content = '''define host {
    host_name       test-host
    alias           Test Host
    address         192.168.1.1
}
'''
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write(config_content)

        service = NagiosService(temp_config_dir)
        objects = service.get_objects()
        assert len(objects) == 1

        staging_data = {
            'pendingEdits': [{
                'globalIndex': 0,
                'object': {
                    'source_file': objects[0].source_file,
                    'line_number': objects[0].line_number
                },
                'edited': {
                    'alias': 'Updated Host'
                }
            }]
        }

        result = service.apply_object_edits(staging_data)
        assert result.success
        assert result.data['count'] == 1

        # Verify change persisted
        service.reload()
        updated_obj = service.get_objects()[0]
        assert updated_obj.attributes.get('alias') == 'Updated Host'


class TestApplyObjectCreations:
    """Tests for apply_object_creations method."""

    def test_creates_new_objects(self, temp_config_dir):
        """Creates new objects in files."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write('# Hosts file\n\n')

        service = NagiosService(temp_config_dir)

        staging_data = {
            'stagedCreations': [{
                'object_type': 'host',
                'targetFile': config_file,
                'attributes': {
                    'host_name': 'new-host',
                    'alias': 'New Host',
                    'address': '10.0.0.1'
                }
            }]
        }

        result = service.apply_object_creations(staging_data)
        assert result.success
        assert result.data['count'] == 1

        # Verify creation
        service.reload()
        objects = service.get_objects()
        assert len(objects) == 1
        assert objects[0].object_type == 'host'
        assert objects[0].attributes.get('host_name') == 'new-host'


class TestApplyObjectDeletions:
    """Tests for apply_object_deletions method."""

    def test_removes_objects(self, temp_config_dir):
        """Removes objects from files."""
        config_content = '''define host {
    host_name       host-to-delete
    alias           Will be deleted
    address         192.168.1.99
}

define host {
    host_name       host-to-keep
    alias           Keep this one
    address         192.168.1.100
}
'''
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')
        with open(config_file, 'w') as f:
            f.write(config_content)

        service = NagiosService(temp_config_dir)
        objects = service.get_objects()
        assert len(objects) == 2

        # Find the object to delete
        obj_to_delete = None
        for obj in objects:
            if obj.attributes.get('host_name') == 'host-to-delete':
                obj_to_delete = obj
                break

        staging_data = {
            'stagedObjectDeletions': [{
                'source_file': obj_to_delete.source_file,
                'line_number': obj_to_delete.line_number,
                'object_type': 'host'
            }]
        }

        result = service.apply_object_deletions(staging_data)
        assert result.success
        assert result.data['count'] == 1

        # Verify deletion
        service.reload()
        objects = service.get_objects()
        assert len(objects) == 1
        assert objects[0].attributes.get('host_name') == 'host-to-keep'


class TestGetNameField:
    """Tests for get_name_field method."""

    def test_returns_correct_field_for_host(self, service_with_hosts):
        """Returns correct name field for host type."""
        assert service_with_hosts.get_name_field('host') == 'host_name'

    def test_returns_correct_field_for_service(self, service_with_hosts):
        """Returns correct name field for service type."""
        assert service_with_hosts.get_name_field('service') == 'service_description'

    def test_returns_correct_field_for_contact(self, service_with_hosts):
        """Returns correct name field for contact type."""
        assert service_with_hosts.get_name_field('contact') == 'contact_name'

    def test_returns_default_for_unknown_type(self, service_with_hosts):
        """Returns 'name' for unknown object type."""
        assert service_with_hosts.get_name_field('unknown_type') == 'name'


class TestReload:
    """Tests for reload method."""

    def test_reloads_parser_state(self, temp_config_dir):
        """Reloads parser to pick up external changes."""
        config_file = os.path.join(temp_config_dir, 'hosts.cfg')

        # Initial content
        with open(config_file, 'w') as f:
            f.write('''define host {
    host_name       initial-host
    address         192.168.1.1
}
''')

        service = NagiosService(temp_config_dir)
        objects = service.get_objects()
        assert len(objects) == 1
        assert objects[0].attributes.get('host_name') == 'initial-host'

        # External modification
        with open(config_file, 'w') as f:
            f.write('''define host {
    host_name       updated-host
    address         192.168.1.2
}

define host {
    host_name       second-host
    address         192.168.1.3
}
''')

        # Reload and verify
        service.reload()
        objects = service.get_objects()
        assert len(objects) == 2
        names = {obj.attributes.get('host_name') for obj in objects}
        assert 'updated-host' in names
        assert 'second-host' in names
        assert 'initial-host' not in names


class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_access_to_parser(self, service_with_hosts):
        """Multiple threads can safely access parser."""
        import threading

        results = []
        errors = []

        def read_objects():
            try:
                objs = service_with_hosts.get_objects()
                results.append(len(objs))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=read_objects) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        assert all(r == results[0] for r in results)
