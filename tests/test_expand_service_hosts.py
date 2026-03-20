"""Tests for expand_service_hosts cross-boundary exclusion logic."""

from app.nagios_model import expand_service_hosts


def test_exclusion_crosses_hostgroup_boundary():
    """!host in host_name also excludes that host from hostgroup expansion."""
    hostgroup_to_hosts = {"web-servers": {"web-01", "web-02", "web-03"}}
    result = expand_service_hosts(
        host_name_attr="db-01,!web-01",
        hostgroup_name_attr="web-servers",
        hostgroup_to_hosts=hostgroup_to_hosts,
    )
    assert result == {"db-01", "web-02", "web-03"}


def test_no_exclusions():
    """Without ! prefix, all hosts included from both fields."""
    hostgroup_to_hosts = {"web-servers": {"web-01", "web-02"}}
    result = expand_service_hosts(
        host_name_attr="db-01",
        hostgroup_name_attr="web-servers",
        hostgroup_to_hosts=hostgroup_to_hosts,
    )
    assert result == {"db-01", "web-01", "web-02"}


def test_wildcard_host_name():
    """Wildcard * in host_name means 'all hosts'."""
    all_hosts = {"h1", "h2", "h3"}
    result = expand_service_hosts(
        host_name_attr="*",
        hostgroup_name_attr="",
        hostgroup_to_hosts={},
        all_hosts=all_hosts,
    )
    assert result == all_hosts


def test_exclusion_only_in_host_name():
    """Only ! entries (no direct hosts), plus hostgroup expansion."""
    hostgroup_to_hosts = {"linux": {"srv-01", "srv-02", "srv-03"}}
    result = expand_service_hosts(
        host_name_attr="!srv-02",
        hostgroup_name_attr="linux",
        hostgroup_to_hosts=hostgroup_to_hosts,
    )
    assert result == {"srv-01", "srv-03"}


def test_empty_both_fields():
    result = expand_service_hosts("", "", {})
    assert result == set()


def test_hostgroup_name_with_plus_prefix():
    """+ prefix on hostgroup_name is stripped before lookup."""
    hostgroup_to_hosts = {"web": {"w1", "w2"}}
    result = expand_service_hosts(
        host_name_attr="",
        hostgroup_name_attr="+web",
        hostgroup_to_hosts=hostgroup_to_hosts,
    )
    assert result == {"w1", "w2"}
