"""Writes must be atomic: a crash part-way through leaves the old file intact.

Break caught: replacing the temp-file + os.replace pattern with a direct
open(path, "w").write(), which truncates the real file before the new content
is safely on disk. Simulated here by making os.fsync fail mid-write.
"""

import os
from unittest.mock import patch

import pytest

from app import server_config
from app.file_operations import edit_object_in_file
from app.server_config import ServerConfig, save_config

ORIGINAL_HOST = """define host {
    host_name       test-host
    alias           Original
    address         1.2.3.4
}
"""


def _crash_during_fsync(_fd):
    raise OSError("simulated crash during write")


def test_edit_object_crash_leaves_original_file_intact(tmp_path):
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text(ORIGINAL_HOST)

    with patch("os.fsync", side_effect=_crash_during_fsync):
        try:
            result = edit_object_in_file(
                str(cfg), 1,
                {"host_name": "test-host", "alias": "Updated", "address": "1.2.3.4"},
                "host",
            )
            assert result.success is False
        except OSError:
            pass  # propagating the error is also acceptable

    assert cfg.read_text() == ORIGINAL_HOST
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hosts.cfg"], "temp file left behind"


def test_edit_object_writes_new_content(tmp_path):
    cfg = tmp_path / "hosts.cfg"
    cfg.write_text(ORIGINAL_HOST)

    result = edit_object_in_file(
        str(cfg), 1, {"host_name": "test-host", "alias": "Updated", "address": "1.2.3.4"}, "host",
    )

    assert result.success, result.error
    assert "Updated" in cfg.read_text()
    assert "Original" not in cfg.read_text()


def test_save_config_crash_leaves_original_settings_intact():
    # conftest redirects CONFIG_FILE to a per-test temp dir
    original = ServerConfig()
    original.paths.nagios_cfg = "/etc/nagios/nagios.cfg"
    save_config(original)
    before = server_config.CONFIG_FILE.read_bytes()

    changed = ServerConfig()
    changed.paths.nagios_cfg = "/somewhere/else.cfg"
    with patch("os.fsync", side_effect=_crash_during_fsync), pytest.raises(OSError):
        save_config(changed)

    assert server_config.CONFIG_FILE.read_bytes() == before
    assert sorted(os.listdir(server_config.CONFIG_DIR)) == ["settings.json"], "temp file left behind"
