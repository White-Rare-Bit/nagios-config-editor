"""Tests for additive inheritance field whitelist."""

from app.nagios_model import ADDITIVE_FIELDS


def test_host_additive_fields():
    """Hosts support + on parents, hostgroups, contact_groups, contacts."""
    expected = {"parents", "hostgroups", "contact_groups", "contacts"}
    assert ADDITIVE_FIELDS["host"] == expected


def test_service_additive_fields():
    """Services support + on parents, host_name, hostgroup_name, servicegroups, contact_groups, contacts."""
    expected = {"parents", "host_name", "hostgroup_name", "servicegroups", "contact_groups", "contacts"}
    assert ADDITIVE_FIELDS["service"] == expected


def test_hostgroup_additive_fields():
    assert "members" in ADDITIVE_FIELDS["hostgroup"]
    assert "hostgroup_members" in ADDITIVE_FIELDS["hostgroup"]


def test_servicegroup_additive_fields():
    assert "members" in ADDITIVE_FIELDS["servicegroup"]
    assert "servicegroup_members" in ADDITIVE_FIELDS["servicegroup"]


def test_contactgroup_additive_fields():
    assert "members" in ADDITIVE_FIELDS["contactgroup"]
    assert "contactgroup_members" in ADDITIVE_FIELDS["contactgroup"]


def test_contact_additive_fields():
    """Contacts support + on host_notification_commands, service_notification_commands, etc."""
    assert "host_notification_commands" in ADDITIVE_FIELDS["contact"]
    assert "service_notification_commands" in ADDITIVE_FIELDS["contact"]
    assert "contactgroups" in ADDITIVE_FIELDS["contact"]


def test_escalation_additive_fields():
    for esc_type in ("hostescalation", "serviceescalation"):
        assert "contacts" in ADDITIVE_FIELDS[esc_type]
        assert "contact_groups" in ADDITIVE_FIELDS[esc_type]


def test_dependency_additive_fields():
    for dep_type in ("hostdependency", "servicedependency"):
        assert "host_name" in ADDITIVE_FIELDS[dep_type]
        assert "hostgroup_name" in ADDITIVE_FIELDS[dep_type]
