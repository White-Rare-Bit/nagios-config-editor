"""Tests for directive alias normalization."""

from app.nagios_model import normalize_attribute_name


def test_host_alias_on_service():
    assert normalize_attribute_name("service", "host") == "host_name"


def test_hosts_alias_on_service():
    assert normalize_attribute_name("service", "hosts") == "host_name"


def test_description_alias_on_service():
    assert normalize_attribute_name("service", "description") == "service_description"


def test_hostgroup_alias_on_service():
    assert normalize_attribute_name("service", "hostgroup") == "hostgroup_name"


def test_hostgroups_alias_on_service():
    assert normalize_attribute_name("service", "hostgroups") == "hostgroup_name"


def test_canonical_name_unchanged():
    assert normalize_attribute_name("service", "host_name") == "host_name"


def test_unknown_attr_unchanged():
    assert normalize_attribute_name("service", "check_command") == "check_command"


def test_host_alias_on_hostdependency():
    """host/hosts aliases also apply to dependency and escalation types."""
    assert normalize_attribute_name("hostdependency", "host") == "host_name"


def test_alias_not_applied_to_wrong_type():
    """'hostgroups' on a host is a real field, not an alias for hostgroup_name."""
    assert normalize_attribute_name("host", "hostgroups") == "hostgroups"


def test_description_alias_on_serviceescalation():
    assert normalize_attribute_name("serviceescalation", "description") == "service_description"
