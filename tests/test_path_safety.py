"""Tests for file_operations.is_safe_path, the guard that keeps every file
write, delete and git operation inside the configured Nagios directory.

Breaks caught: traversal accepted (../, absolute paths, symlinks out of the
root, sibling directories sharing a name prefix), null bytes accepted,
missing base_dir accepted, and routes that stop calling the guard.
"""

import os

import pytest

from app.file_operations import is_safe_path


@pytest.fixture
def base(tmp_path):
    """A config root with a subdirectory, plus an 'outside' dir next to it."""
    root = tmp_path / "nagios"
    (root / "sub").mkdir(parents=True)
    (root / "hosts.cfg").write_text("")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.cfg").write_text("")
    return root, outside


@pytest.mark.parametrize("rel_path", [
    "hosts.cfg",
    "sub/new.cfg",
    "sub/../hosts.cfg",          # traversal that stays inside
    "sub/deeper/not-yet.cfg",    # non-existent nested path
])
def test_paths_inside_root_are_allowed(base, rel_path):
    root, _ = base
    assert is_safe_path(rel_path, str(root)).success is True


def test_absolute_path_inside_root_is_allowed(base):
    root, _ = base
    assert is_safe_path(str(root / "sub" / "x.cfg"), str(root)).success is True


@pytest.mark.parametrize("rel_path", [
    "../outside/secret.cfg",
    "sub/../../outside/secret.cfg",
    "../../../../etc/passwd",
])
def test_relative_traversal_out_of_root_is_rejected(base, rel_path):
    root, _ = base
    result = is_safe_path(rel_path, str(root))
    assert result.success is False
    assert result.error


def test_absolute_path_outside_root_is_rejected(base):
    root, outside = base
    assert is_safe_path(str(outside / "secret.cfg"), str(root)).success is False
    assert is_safe_path("/etc/passwd", str(root)).success is False


def test_sibling_dir_sharing_name_prefix_is_rejected(base, tmp_path):
    """/x/nagios-evil must not pass as being inside /x/nagios (string-prefix bug)."""
    root, _ = base
    evil = tmp_path / "nagios-evil"
    evil.mkdir()
    assert is_safe_path(str(evil / "x.cfg"), str(root)).success is False


def test_symlinked_dir_pointing_outside_is_rejected(base):
    root, outside = base
    os.symlink(outside, root / "escape")
    assert is_safe_path("escape/secret.cfg", str(root)).success is False
    assert is_safe_path("escape/new-file.cfg", str(root)).success is False


def test_symlinked_file_pointing_outside_is_rejected(base):
    root, outside = base
    os.symlink(outside / "secret.cfg", root / "link.cfg")
    assert is_safe_path("link.cfg", str(root)).success is False


def test_null_byte_is_rejected(base):
    root, _ = base
    result = is_safe_path("hosts.cfg\x00.txt", str(root))
    assert result.success is False
    assert "null" in (result.error or "").lower()


def test_missing_base_dir_is_rejected():
    assert is_safe_path("hosts.cfg", None).success is False


def test_file_create_route_refuses_traversal(tmp_path):
    """The guard is wired into POST /api/files/create: nothing is written outside."""
    from app import create_app
    root = tmp_path / "nagios"
    root.mkdir()
    (root / "hosts.cfg").write_text("define host {\n    host_name h1\n}\n")
    app = create_app(config_path=str(root))
    app.config["TESTING"] = True
    client = app.test_client()

    resp = client.post("/api/files/create", json={"path": "../escaped.cfg"},
                       headers={"X-Session-Id": "s1"})

    assert resp.status_code == 400
    # Not written next to the config dir, nor anywhere in the shadow copy
    assert list(tmp_path.rglob("escaped.cfg")) == []
