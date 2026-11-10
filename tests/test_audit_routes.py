"""Tests for audit log calls in route handlers."""

import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from app import create_app


@contextmanager
def _audit_capture(app):
    """Collect the lines appended to the app's real audit.log while the block runs.

    Reads the file operators actually see, rather than intercepting log records,
    so it also catches a broken audit handler or formatter.
    """
    path = Path(app.extensions["log_dir"]) / "audit.log"
    before = len(path.read_text().splitlines()) if path.exists() else 0
    lines: list[str] = []
    yield lines
    lines.extend(path.read_text().splitlines()[before:] if path.exists() else [])


@pytest.fixture
def audit_app():
    """Create Flask app with isolated temp config for audit testing."""
    test_dir = os.path.realpath(tempfile.mkdtemp())
    config_path = Path(test_dir) / "nagios"
    config_path.mkdir()

    (config_path / "hosts.cfg").write_text("""\
define host {
    host_name       test-host-1
    alias           Test Host 1
    address         192.168.1.1
}
""")

    log_dir = os.path.join(test_dir, "logs")
    app = create_app(config_path=str(config_path), log_dir_override=log_dir)
    app.config["TESTING"] = True

    # Override primary_dir so _resolve_stable_key can remap paths to shadow
    with app.app_context():
        server_config = app.extensions.get("server_config")
        if server_config:
            server_config.paths.primary_dir = str(config_path)

    yield app

    with app.app_context():
        sm = app.extensions.get("shadow")
        if sm and sm.has_shadow():
            sm.destroy_shadow()
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def audit_client(audit_app):
    return audit_app.test_client()


def _get_object(client, host_name):
    resp = client.get("/api/objects")
    obj = next(o for o in resp.json if o["attributes"].get("host_name") == host_name)
    # Build stable_key from object data (source_file|object_type|display_name)
    obj["stable_key"] = f"{obj['source_file']}|{obj['object_type']}|{obj['display_name']}"
    return obj


class TestObjectEditAudit:
    def test_object_edit_logs_field_diffs(self, audit_client, audit_app):
        obj = _get_object(audit_client, "test-host-1")
        new_attrs = dict(obj["attributes"])
        new_attrs["alias"] = "New Alias"
        new_attrs["address"] = "10.0.0.1"

        with _audit_capture(audit_app) as audit_lines:
            resp = audit_client.post("/api/objects/update", json={
                "stable_key": obj["stable_key"],
                "attributes": new_attrs,
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200

        # Should have one line per changed field (alias and address)
        alias_lines = [l for l in audit_lines if "field=alias" in l]
        address_lines = [l for l in audit_lines if "field=address" in l]
        assert len(alias_lines) == 1
        assert 'from="Test Host 1"' in alias_lines[0]
        assert 'to="New Alias"' in alias_lines[0]
        assert len(address_lines) == 1
        assert "action=object_edit" in address_lines[0]
        assert "type=host" in address_lines[0]
        assert "name=test-host-1" in address_lines[0]

        # All lines should share the same txn
        txn_values = set()
        for line in audit_lines:
            m = re.search(r"txn=(\w+)", line)
            if m:
                txn_values.add(m.group(1))
        assert len(txn_values) == 1

        # file= should show original path, not shadow internal path
        for line in audit_lines:
            assert "file=nagios/hosts.cfg" in line or "file=hosts.cfg" in line
            assert "root_0" not in line


class TestObjectCreateAudit:
    def test_object_create_logs_audit(self, audit_client, audit_app):
        obj = _get_object(audit_client, "test-host-1")
        target_file = obj["source_file"]

        with _audit_capture(audit_app) as audit_lines:
            resp = audit_client.post("/api/objects/create", json={
                "target_file": target_file,
                "object_type": "host",
                "attributes": {"host_name": "new-host", "address": "1.2.3.4"},
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        assert any("action=object_create" in l and "name=new-host" in l and "type=host" in l for l in audit_lines)
        # Verify file path doesn't leak shadow internals
        for l in audit_lines:
            assert "root_0" not in l


class TestObjectDeleteAudit:
    def test_object_delete_logs_audit(self, audit_client, audit_app):
        obj = _get_object(audit_client, "test-host-1")

        with _audit_capture(audit_app) as audit_lines:
            resp = audit_client.post("/api/objects/delete", json={
                "stable_key": obj["stable_key"],
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        assert any("action=object_delete" in l and "name=test-host-1" in l and "type=host" in l for l in audit_lines)
        for l in audit_lines:
            assert "root_0" not in l


@pytest.fixture
def audit_app_multi():
    """App with multiple hosts for bulk operation testing."""
    test_dir = os.path.realpath(tempfile.mkdtemp())
    config_path = Path(test_dir) / "nagios"
    config_path.mkdir()

    (config_path / "hosts.cfg").write_text("""\
define host {
    host_name       host-a
    address         1.1.1.1
}

define host {
    host_name       host-b
    address         2.2.2.2
}

define host {
    host_name       host-c
    address         3.3.3.3
}
""")

    log_dir = os.path.join(test_dir, "logs")
    app = create_app(config_path=str(config_path), log_dir_override=log_dir)
    app.config["TESTING"] = True

    with app.app_context():
        server_config = app.extensions.get("server_config")
        if server_config:
            server_config.paths.primary_dir = str(config_path)

    yield app

    with app.app_context():
        sm = app.extensions.get("shadow")
        if sm and sm.has_shadow():
            sm.destroy_shadow()
    shutil.rmtree(test_dir, ignore_errors=True)


class TestBulkDeleteAudit:
    def test_delete_multiple_logs_per_object(self, audit_app_multi):
        client = audit_app_multi.test_client()
        resp = client.get("/api/objects")
        objects = resp.json
        keys = [
            f"{o['source_file']}|{o['object_type']}|{o['display_name']}"
            for o in objects if o["attributes"].get("host_name") in ("host-a", "host-b")
        ]

        with _audit_capture(audit_app_multi) as audit_lines:
            resp = client.post("/api/objects/delete-multiple", json={
                "stable_keys": keys,
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        delete_lines = [l for l in audit_lines if "action=object_delete" in l]
        assert len(delete_lines) == 2

        # All should share the same txn
        txns = set()
        for l in delete_lines:
            m = re.search(r"txn=(\w+)", l)
            if m:
                txns.add(m.group(1))
        assert len(txns) == 1

        # No shadow path leakage
        for l in delete_lines:
            assert "root_0" not in l


class TestBulkMoveAudit:
    def test_move_objects_logs_per_object(self, audit_app_multi):
        client = audit_app_multi.test_client()

        # Get objects to move
        resp = client.get("/api/objects")
        objects = resp.json
        keys = []
        for o in objects:
            if o["attributes"].get("host_name") in ("host-a", "host-b"):
                key = f"{o['source_file']}|{o['object_type']}|{o['display_name']}"
                keys.append(key)

        with audit_app_multi.app_context():
            config_path = audit_app_multi.extensions["service"].config_path
        target = os.path.join(config_path, "moved.cfg")

        with _audit_capture(audit_app_multi) as audit_lines:
            resp = client.post("/api/move-objects", json={
                "stable_keys": keys,
                "target_file": target,
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        move_lines = [l for l in audit_lines if "action=object_move" in l]
        assert len(move_lines) == 2
        assert all("from_file=" in l and "to_file=" in l for l in move_lines)

        # All should share the same txn
        txns = set()
        for l in move_lines:
            m = re.search(r"txn=(\w+)", l)
            if m:
                txns.add(m.group(1))
        assert len(txns) == 1

        # No shadow path leakage
        for l in move_lines:
            assert "root_0" not in l


class TestBatchMutationsAudit:
    def test_batch_update_logs_field_diffs(self, audit_client, audit_app):
        obj = _get_object(audit_client, "test-host-1")
        new_attrs = dict(obj["attributes"])
        new_attrs["alias"] = "Batch Updated"

        with _audit_capture(audit_app) as audit_lines:
            resp = audit_client.post("/api/batch-mutations", json={
                "description": "test batch",
                "operations": [
                    {"action": "update", "stable_key": obj["stable_key"], "attributes": new_attrs},
                ],
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        assert any("action=object_edit" in l and "field=alias" in l for l in audit_lines)
        assert any('to="Batch Updated"' in l for l in audit_lines)

    def test_batch_create_logs_audit(self, audit_client, audit_app):
        obj = _get_object(audit_client, "test-host-1")
        target_file = obj["source_file"]

        with _audit_capture(audit_app) as audit_lines:
            resp = audit_client.post("/api/batch-mutations", json={
                "description": "test batch create",
                "operations": [
                    {"action": "create", "target_file": target_file, "object_type": "host",
                     "attributes": {"host_name": "batch-host", "address": "5.5.5.5"}},
                ],
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        assert any("action=object_create" in l and "name=batch-host" in l for l in audit_lines)


class TestFileMutationAudit:
    def test_create_file_logs_audit(self, audit_app):
        client = audit_app.test_client()
        with _audit_capture(audit_app) as audit_lines:
            resp = client.post("/api/files/create", json={
                "path": "newfile.cfg",
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        [line] = [l for l in audit_lines if "action=file_create" in l]  # exactly one
        assert re.search(r"\bfile=\S*newfile.cfg", line)
        assert "admin@example.com" in line
        assert "root_0" not in line

    def test_delete_file_logs_audit(self, audit_app):
        client = audit_app.test_client()
        # First create a file to delete
        client.post("/api/files/create", json={"path": "todelete.cfg"},
                     headers={"X-Session-Id": "test-session"})

        with _audit_capture(audit_app) as audit_lines:
            resp = client.delete("/api/files/todelete.cfg",
                headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        [line] = [l for l in audit_lines if "action=file_delete" in l]  # exactly one
        assert re.search(r"\bfile=\S*todelete.cfg", line)
        assert "admin@example.com" in line
        assert "root_0" not in line

    def test_create_folder_logs_audit(self, audit_app):
        client = audit_app.test_client()
        with _audit_capture(audit_app) as audit_lines:
            resp = client.post("/api/folders", json={
                "path": "newfolder",
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        [line] = [l for l in audit_lines if "action=folder_create" in l]  # exactly one
        assert re.search(r"\bfolder=\S*newfolder", line)
        assert "admin@example.com" in line
        assert "root_0" not in line

    def test_delete_folder_logs_audit(self, audit_app):
        client = audit_app.test_client()
        # Create a folder first
        client.post("/api/folders", json={"path": "rmfolder"},
                     headers={"X-Session-Id": "test-session"})

        with _audit_capture(audit_app) as audit_lines:
            resp = client.delete("/api/folders/rmfolder",
                headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        [line] = [l for l in audit_lines if "action=folder_delete" in l]  # exactly one
        assert re.search(r"\bfolder=\S*rmfolder", line)
        assert "admin@example.com" in line
        assert "root_0" not in line


class TestObjectMoveAudit:
    def test_object_move_logs_audit(self, audit_app):
        client = audit_app.test_client()
        obj = _get_object(client, "test-host-1")

        with audit_app.app_context():
            config_path = audit_app.extensions["service"].config_path

        # Move to a new file (the service will create it)
        target_file = os.path.join(config_path, "other.cfg")

        with _audit_capture(audit_app) as audit_lines:
            resp = client.post("/api/objects/move", json={
                "stable_key": obj["stable_key"],
                "target_file": target_file,
            }, headers={"X-Session-Id": "test-session", "X-User-Name": "admin", "X-User-Email": "admin@example.com"})

        assert resp.status_code == 200
        assert any("action=object_move" in l and "name=test-host-1" in l for l in audit_lines)
        assert any("from_file=" in l and "to_file=" in l for l in audit_lines)
        for l in audit_lines:
            assert "root_0" not in l


# ---------------------------------------------------------------------------
# Staging lifecycle: the audit log must show what happened to staged edits,
# not only that they were made.
# ---------------------------------------------------------------------------

ALICE = {"X-Session-Id": "alice-session-secret", "X-User-Name": "Alice", "X-User-Email": "alice@x"}
BOB = {"X-Session-Id": "bob-session-secret", "X-User-Name": "Bob", "X-User-Email": "bob@x"}


def _session_ref(session_id):
    import hashlib
    return hashlib.sha256(session_id.encode()).hexdigest()[:8]


def _stage_alias_edit(client, headers, alias="Staged Alias"):
    obj = _get_object(client, "test-host-1")
    resp = client.post("/api/objects/update", json={
        "stable_key": obj["stable_key"],
        "attributes": {**obj["attributes"], "alias": alias},
    }, headers=headers)
    assert resp.status_code == 200, resp.json


def _line(lines, action):
    found = [l for l in lines if f"action={action}" in l]
    assert len(found) == 1, f"expected one {action} line in {lines}"
    return found[0]


class TestAuditSessionRef:
    def test_audit_lines_carry_hashed_session_not_the_session_id(self, audit_client, audit_app):
        with _audit_capture(audit_app) as lines:
            _stage_alias_edit(audit_client, ALICE)

        edit = _line(lines, "object_edit")
        assert f"session={_session_ref(ALICE['X-Session-Id'])}" in edit
        # The raw id would let anyone reading the log act as the lock owner.
        assert ALICE["X-Session-Id"] not in edit


class TestStagingLifecycleAudit:
    def test_apply_lists_files_and_links_to_the_staging_session(self, audit_client, audit_app):
        _stage_alias_edit(audit_client, ALICE)

        with _audit_capture(audit_app) as lines:
            resp = audit_client.post("/api/staging/apply", headers=ALICE)

        assert resp.status_code == 200, resp.json
        apply = _line(lines, "apply")
        assert re.search(r"files=\S*hosts\.cfg", apply)
        assert "files_changed=1" in apply
        assert f"session={_session_ref(ALICE['X-Session-Id'])}" in apply

    def test_discarding_staged_changes_is_audited(self, audit_client, audit_app):
        _stage_alias_edit(audit_client, ALICE)

        with _audit_capture(audit_app) as lines:
            resp = audit_client.delete("/api/staging", headers=ALICE)

        assert resp.status_code == 200
        discard = _line(lines, "staging_discard")
        assert 'user="Alice <alice@x>"' in discard
        assert re.search(r"files=\S*hosts\.cfg", discard)
        assert f"session={_session_ref(ALICE['X-Session-Id'])}" in discard

    def test_undo_is_audited_with_what_was_undone(self, audit_client, audit_app):
        _stage_alias_edit(audit_client, ALICE)

        with _audit_capture(audit_app) as lines:
            resp = audit_client.post("/api/staging/undo", headers=ALICE)

        assert resp.status_code == 200, resp.json
        undo = _line(lines, "undo")
        assert 'user="Alice <alice@x>"' in undo
        assert 'undone="edit host test-host-1"' in undo  # the undone snapshot's description

    def test_lock_break_records_breaker_and_previous_owner(self, audit_client, audit_app):
        _stage_alias_edit(audit_client, ALICE)

        with _audit_capture(audit_app) as lines:
            resp = audit_client.post("/api/staging/lock/break", headers=BOB)

        assert resp.status_code == 200
        broke = _line(lines, "lock_break")
        assert 'user="Bob <bob@x>"' in broke
        assert 'owner="Alice <alice@x>"' in broke
        assert f"owner_session={_session_ref(ALICE['X-Session-Id'])}" in broke
        assert re.search(r"files=\S*hosts\.cfg", broke)


class TestSettingsAudit:
    def test_settings_update_is_audited(self, audit_client, audit_app):
        with _audit_capture(audit_app) as lines:
            resp = audit_client.post("/api/settings", json={"paths": {"primary_dir": "/tmp/x"}},
                                     headers=ALICE)

        assert resp.status_code == 200
        line = _line(lines, "settings_update")
        assert 'user="Alice <alice@x>"' in line
        assert "changed=primary_dir" in line

    def test_logging_settings_update_is_audited(self, audit_client, audit_app):
        with _audit_capture(audit_app) as lines:
            resp = audit_client.post("/api/settings/logging", json={"log_level": "DEBUG"},
                                     headers=ALICE)

        assert resp.status_code == 200
        line = _line(lines, "settings_update")
        assert "section=logging" in line
        assert "log_level=DEBUG" in line


class TestGitAudit:
    def test_git_discard_of_a_file_is_audited(self, tmp_path):
        import subprocess

        cfg = tmp_path / "nagios"
        cfg.mkdir()
        (cfg / "hosts.cfg").write_text("define host {\n    host_name h1\n}\n")
        for args in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@t"],
                     ["add", "-A"], ["commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(cfg), *args], check=True, capture_output=True)
        app = create_app(config_path=str(cfg), log_dir_override=str(tmp_path / "logs"))
        app.config["TESTING"] = True
        client = app.test_client()
        (cfg / "hosts.cfg").write_text("define host {\n    host_name h2\n}\n")

        with _audit_capture(app) as lines:
            resp = client.post("/api/git/discard", json={"file": "hosts.cfg"}, headers=ALICE)

        assert resp.status_code == 200, resp.json
        line = _line(lines, "git_discard")
        assert 'user="Alice <alice@x>"' in line
        assert "file=hosts.cfg" in line

    def test_git_identity_change_is_audited(self, audit_client, audit_app):
        with _audit_capture(audit_app) as lines:
            resp = audit_client.post("/api/git/identity",
                                     json={"user_name": "Alice A", "user_email": "alice@new.example"},
                                     headers=ALICE)

        assert resp.status_code == 200, resp.json
        line = _line(lines, "identity_change")
        assert 'to="Alice A <alice@new.example>"' in line


class TestTrustedUserHeader:
    """With NBE_TRUSTED_USER_HEADER set, the proxy-authenticated user is audited,
    not the name/email the browser claims."""

    def _create_file(self, client, app, headers):
        target = os.path.join(app.extensions["primary_dir"], "new.cfg")
        with _audit_capture(app) as lines:
            resp = client.post("/api/files/create", json={"path": target}, headers=headers)
        assert resp.status_code == 200, resp.json
        return _line(lines, "file_create")

    def test_trusted_header_overrides_claimed_identity(self, audit_client, audit_app, monkeypatch):
        monkeypatch.setenv("NBE_TRUSTED_USER_HEADER", "X-Remote-User")

        line = self._create_file(audit_client, audit_app, {
            **ALICE, "X-User-Name": "Someone Else", "X-User-Email": "ceo@corp.example",
            "X-Remote-User": "alice",
        })

        assert 'user="alice"' in line or "user=alice" in line
        assert "ceo@corp.example" not in line

    def test_missing_trusted_header_marks_identity_unverified(self, audit_client, audit_app, monkeypatch):
        monkeypatch.setenv("NBE_TRUSTED_USER_HEADER", "X-Remote-User")

        line = self._create_file(audit_client, audit_app, ALICE)

        assert 'user="unverified: Alice <alice@x>"' in line

    def test_without_setting_claimed_identity_is_used(self, audit_client, audit_app):
        line = self._create_file(audit_client, audit_app, {**ALICE, "X-Remote-User": "mallory"})

        assert 'user="Alice <alice@x>"' in line

    def test_apply_credits_the_verified_requester(self, audit_client, audit_app, monkeypatch):
        monkeypatch.setenv("NBE_TRUSTED_USER_HEADER", "X-Remote-User")
        headers = {**ALICE, "X-Remote-User": "alice"}
        _stage_alias_edit(audit_client, headers)

        with _audit_capture(audit_app) as lines:
            resp = audit_client.post("/api/staging/apply", headers=headers)

        assert resp.status_code == 200, resp.json
        assert 'user="alice"' in _line(lines, "apply")
