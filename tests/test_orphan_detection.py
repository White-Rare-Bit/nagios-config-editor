"""Tests for /api/analysis/orphans endpoint."""

import pytest
import os
import json


class TestOrphanDetection:
    """Test orphan detection API endpoint."""

    def test_orphan_endpoint_returns_200(self, client):
        """Endpoint exists and returns 200."""
        response = client.get('/api/analysis/orphans')
        assert response.status_code == 200
        data = response.get_json()
        assert 'orphan_indices' in data
        assert isinstance(data['orphan_indices'], list)

    def test_referenced_host_not_orphan(self, client, service):
        """A host referenced by a service is not an orphan."""
        response = client.get('/api/analysis/orphans')
        data = response.get_json()

        hosts_referenced_by_services = set()
        for obj in service.get_objects():
            if obj.object_type == 'service':
                host_ref = obj.attributes.get('host_name', '')
                for h in host_ref.split(','):
                    h = h.strip()
                    if h and h != '*':
                        hosts_referenced_by_services.add(h)

        orphan_indices = set(data['orphan_indices'])
        for idx, obj in enumerate(service.get_objects()):
            if obj.object_type == 'host':
                host_name = obj.get_name()
                if host_name in hosts_referenced_by_services:
                    assert idx not in orphan_indices, \
                        f"Host {host_name} is referenced by a service but flagged as orphan"

    def test_templates_excluded(self, client, service):
        """Templates (register=0) should NOT appear in orphan results."""
        response = client.get('/api/analysis/orphans')
        data = response.get_json()
        orphan_indices = set(data['orphan_indices'])

        for idx, obj in enumerate(service.get_objects()):
            if obj.attributes.get('register', '1') == '0':
                assert idx not in orphan_indices, \
                    f"Template {obj.get_name()} should not appear in orphan results"

    def test_host_with_hostgroups_not_orphan(self, client, service):
        """A host that has a 'hostgroups' attribute is in use and not an orphan."""
        response = client.get('/api/analysis/orphans')
        data = response.get_json()
        orphan_indices = set(data['orphan_indices'])

        for idx, obj in enumerate(service.get_objects()):
            if obj.object_type == 'host' and obj.attributes.get('hostgroups'):
                assert idx not in orphan_indices, \
                    f"Host {obj.get_name()} has hostgroups attribute but flagged as orphan"

    def test_service_with_host_name_not_orphan(self, client, service):
        """A service with host_name is actively monitoring and not an orphan."""
        response = client.get('/api/analysis/orphans')
        data = response.get_json()
        orphan_indices = set(data['orphan_indices'])

        for idx, obj in enumerate(service.get_objects()):
            if obj.object_type == 'service' and obj.attributes.get('host_name'):
                if obj.attributes.get('register', '1') != '0':
                    assert idx not in orphan_indices, \
                        f"Service {obj.get_name()} has host_name but flagged as orphan"

    def test_command_used_by_service_not_orphan(self, client, service):
        """A command referenced via check_command is not an orphan."""
        response = client.get('/api/analysis/orphans')
        data = response.get_json()
        orphan_indices = set(data['orphan_indices'])

        used_commands = set()
        for obj in service.get_objects():
            for field in ['check_command', 'event_handler']:
                val = obj.attributes.get(field, '')
                if val:
                    cmd_name = val.split('!')[0].strip()
                    if cmd_name:
                        used_commands.add(cmd_name)
            for field in ['host_notification_commands', 'service_notification_commands']:
                val = obj.attributes.get(field, '')
                if val:
                    for cmd in val.split(','):
                        cmd_name = cmd.strip().split('!')[0].strip()
                        if cmd_name:
                            used_commands.add(cmd_name)

        for idx, obj in enumerate(service.get_objects()):
            if obj.object_type == 'command':
                cmd_name = obj.attributes.get('command_name', '')
                if cmd_name in used_commands:
                    assert idx not in orphan_indices, \
                        f"Command {cmd_name} is used but flagged as orphan"

    def test_response_includes_summary(self, client):
        """Response includes summary counts."""
        response = client.get('/api/analysis/orphans')
        data = response.get_json()
        assert 'summary' in data
        assert 'total_orphans' in data['summary']
        assert 'by_type' in data['summary']
