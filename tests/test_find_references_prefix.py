"""Tests for find_references prefix handling."""

import shutil
import tempfile
from pathlib import Path

from app.nagios_parser import NagiosConfigParser


def _make_parser(cfg_text):
    test_dir = tempfile.mkdtemp()
    (Path(test_dir) / "test.cfg").write_text(cfg_text)
    p = NagiosConfigParser(test_dir)
    p.parse_all()
    return p, test_dir


def test_find_references_strips_plus_prefix():
    """References with + prefix should be found."""
    p, path = _make_parser("""
define hostgroup {
    hostgroup_name  web-servers
}

define service {
    host_name       web-01
    hostgroup_name  +web-servers
    service_description HTTP
    check_command   check_http
}
""")
    try:
        refs = p.find_references("hostgroup", "web-servers")
        # Should find both the hostgroup definition AND the service reference
        service_refs = [(o, f) for o, f in refs if o.object_type == "service"]
        assert len(service_refs) == 1, \
            f"Expected service to reference web-servers via +prefix, got: {service_refs}"
        assert service_refs[0][1] == "hostgroup_name"
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_find_references_strips_bang_prefix():
    """References with ! exclusion prefix should be found."""
    p, path = _make_parser("""
define host {
    host_name   web-01
}

define service {
    host_name       web-02,!web-01
    service_description HTTP
    check_command   check_http
}
""")
    try:
        refs = p.find_references("host", "web-01")
        # Should find both the host definition AND the service exclusion reference
        service_refs = [(o, f) for o, f in refs if o.object_type == "service"]
        assert len(service_refs) == 1, \
            f"Expected service to reference web-01 via !prefix, got: {service_refs}"
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_find_references_exact_match_still_works():
    """Normal references without prefixes still work."""
    p, path = _make_parser("""
define host {
    host_name   db-01
}

define service {
    host_name       db-01
    service_description MySQL
    check_command   check_mysql
}
""")
    try:
        refs = p.find_references("host", "db-01")
        service_refs = [(o, f) for o, f in refs if o.object_type == "service"]
        assert len(service_refs) == 1
    finally:
        shutil.rmtree(path, ignore_errors=True)
