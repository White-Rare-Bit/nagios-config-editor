"""Tests for the multi-process-safe rotating log handler.

Gunicorn runs several worker processes, each with its own handler on the same
app.log/audit.log. The stdlib RotatingFileHandler rotates without coordinating
with the other processes, which loses lines and leaves workers writing into
already-rotated files.
"""

import glob
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from app.log_handlers import MultiProcessRotatingFileHandler

HANDLERS_MODULE = Path(__file__).resolve().parent.parent / "app" / "log_handlers.py"


def _record(msg):
    return logging.LogRecord("t", logging.INFO, __file__, 0, msg, None, None)


def _all_lines(log_path):
    lines = []
    for f in glob.glob(f"{log_path}*"):
        if f.endswith(".lock"):
            continue
        lines.extend(Path(f).read_text().splitlines())
    return lines


def test_concurrent_processes_lose_no_lines(tmp_path):
    """Two processes rotating the same file must not lose or misplace lines."""
    log_path = tmp_path / "audit.log"
    per_worker = 1500
    # Load the module from its file so the child doesn't import the `app`
    # package (whose __init__ builds the whole Flask app at import time).
    script = textwrap.dedent(f"""
        import importlib.util, logging, sys
        spec = importlib.util.spec_from_file_location("lh", {str(HANDLERS_MODULE)!r})
        lh = importlib.util.module_from_spec(spec); spec.loader.exec_module(lh)
        h = lh.MultiProcessRotatingFileHandler({str(log_path)!r}, maxBytes=20_000, backupCount=500)
        lg = logging.getLogger("w"); lg.addHandler(h); lg.setLevel(logging.INFO)
        for i in range({per_worker}):
            lg.info("w=%s seq=%05d padding=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", sys.argv[1], i)
    """)
    procs = [
        subprocess.Popen([sys.executable, "-c", script, str(w)], stderr=subprocess.PIPE)
        for w in (0, 1)
    ]
    errors = [p.communicate()[1].decode() for p in procs]

    assert all(p.returncode == 0 for p in procs)
    assert errors == ["", ""], "handler reported logging errors"
    lines = _all_lines(log_path)
    assert len(lines) == 2 * per_worker
    assert len(set(lines)) == 2 * per_worker


def test_handler_follows_rotation_done_by_another_handler(tmp_path):
    """After another process rotates, this handler writes to the new live file."""
    log_path = str(tmp_path / "app.log")
    first = MultiProcessRotatingFileHandler(log_path, maxBytes=200, backupCount=5)
    second = MultiProcessRotatingFileHandler(log_path, maxBytes=200, backupCount=5)
    try:
        second.emit(_record("second opens the file"))
        for i in range(10):  # enough to make `first` rotate
            first.emit(_record(f"first line {i} " + "x" * 30))
        assert os.path.exists(log_path + ".1")

        second.emit(_record("second after rotation"))

        assert "second after rotation" in Path(log_path).read_text()
    finally:
        first.close()
        second.close()


def test_rotation_keeps_backup_count(tmp_path):
    log_path = str(tmp_path / "app.log")
    handler = MultiProcessRotatingFileHandler(log_path, maxBytes=100, backupCount=2)
    try:
        for i in range(50):
            handler.emit(_record(f"line {i} " + "x" * 40))
    finally:
        handler.close()
    rotated = sorted(f for f in glob.glob(log_path + ".*") if not f.endswith(".lock"))
    assert rotated == [log_path + ".1", log_path + ".2"]
