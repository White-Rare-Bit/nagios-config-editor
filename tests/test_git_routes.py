"""HTTP-level tests for the destructive git routes (discard, restore, commit).

GitService itself is tested in test_git_service.py; these cover what the
routes add on top: path validation, commit-hash validation, the shadow-lock
guard, reloading the parsed config, and the audit trail.
"""

import subprocess
from pathlib import Path

import pytest

from app import create_app

HOSTS = "define host {\n    host_name   web-01\n    alias       Original\n}\n"


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """Config dir under git with one commit, plus a file outside the config dir."""
    cfg = tmp_path / "nagios"
    cfg.mkdir()
    (cfg / "hosts.cfg").write_text(HOSTS)
    _git(cfg, "init", "-q")
    _git(cfg, "config", "user.name", "Test")
    _git(cfg, "config", "user.email", "t@t.com")
    _git(cfg, "add", "-A")
    _git(cfg, "commit", "-q", "-m", "Initial")
    (tmp_path / "outside.cfg").write_text("do not touch\n")

    app = create_app(config_path=str(cfg))
    app.config["TESTING"] = True
    return app, app.test_client(), cfg


def _alias(client):
    host = next(o for o in client.get("/api/objects").json if o["attributes"].get("host_name") == "web-01")
    return host["attributes"]["alias"]


def _lock_by_other_session(client):
    obj = client.get("/api/objects").json[0]
    key = f"{obj['source_file']}|{obj['object_type']}|{obj['display_name']}"
    resp = client.post("/api/objects/update", json={
        "stable_key": key, "attributes": {**obj["attributes"], "alias": "Staged"},
    }, headers={"X-Session-Id": "other-user"})
    assert resp.status_code == 200


class TestDiscard:

    def test_discard_restores_file_and_reloads(self, repo):
        app, client, cfg = repo
        (cfg / "hosts.cfg").write_text(HOSTS.replace("Original", "Edited on disk"))
        client.post("/api/reload")
        assert _alias(client) == "Edited on disk"

        resp = client.post("/api/git/discard", json={"file": "hosts.cfg"}, headers={"X-Session-Id": "s1"})

        assert resp.status_code == 200
        assert resp.json["action"] == "restored"
        assert (cfg / "hosts.cfg").read_text() == HOSTS
        assert _alias(client) == "Original"  # parsed config reloaded, not stale

    def test_discard_rejects_path_outside_config_dir(self, repo):
        app, client, cfg = repo
        resp = client.post("/api/git/discard", json={"file": "../outside.cfg"}, headers={"X-Session-Id": "s1"})
        assert resp.status_code == 400
        assert (cfg.parent / "outside.cfg").read_text() == "do not touch\n"

    def test_discard_blocked_while_another_session_has_staged_changes(self, repo):
        app, client, cfg = repo
        _lock_by_other_session(client)
        (cfg / "hosts.cfg").write_text("edited\n")
        resp = client.post("/api/git/discard", json={"file": "hosts.cfg"}, headers={"X-Session-Id": "me"})
        assert resp.status_code == 423
        assert (cfg / "hosts.cfg").read_text() == "edited\n"

    def test_discard_without_session_header_cannot_bypass_lock(self, repo):
        app, client, cfg = repo
        _lock_by_other_session(client)
        (cfg / "hosts.cfg").write_text("edited\n")
        resp = client.post("/api/git/discard", json={"file": "hosts.cfg"})  # no X-Session-Id
        assert resp.status_code == 423
        assert (cfg / "hosts.cfg").read_text() == "edited\n"


class TestRestore:

    def _second_commit(self, cfg):
        initial = _git(cfg, "rev-parse", "HEAD")
        (cfg / "extra.cfg").write_text("define host {\n    host_name extra\n}\n")
        _git(cfg, "add", "-A")
        _git(cfg, "commit", "-q", "-m", "Add extra")
        return initial

    def test_restore_returns_tree_to_commit_and_audits(self, repo):
        app, client, cfg = repo
        initial = self._second_commit(cfg)
        client.post("/api/reload")

        resp = client.post("/api/git/restore", json={"commit": initial}, headers={
            "X-Session-Id": "s1", "X-User-Name": "Alice", "X-User-Email": "alice@example.com"})

        assert resp.status_code == 200
        assert not (cfg / "extra.cfg").exists()
        names = {o["attributes"].get("host_name") for o in client.get("/api/objects").json}
        assert names == {"web-01"}
        audit = (Path(app.extensions["log_dir"]) / "audit.log").read_text()
        assert "action=git_restored" in audit and f"commit_hash={initial}" in audit
        assert "alice@example.com" in audit

    @pytest.mark.parametrize("bad", ["abc;rm -rf /", "HEAD~1 --hard", "../../x"])
    def test_restore_rejects_malformed_commit_hash(self, repo, bad):
        app, client, cfg = repo
        head = _git(cfg, "rev-parse", "HEAD")
        resp = client.post("/api/git/restore", json={"commit": bad}, headers={"X-Session-Id": "s1"})
        assert resp.status_code == 400
        assert _git(cfg, "rev-parse", "HEAD") == head

    def test_restore_unknown_commit_is_404(self, repo):
        app, client, cfg = repo
        resp = client.post("/api/git/restore", json={"commit": "deadbeef" * 5}, headers={"X-Session-Id": "s1"})
        assert resp.status_code == 404

    def test_restore_blocked_while_another_session_has_staged_changes(self, repo):
        app, client, cfg = repo
        initial = self._second_commit(cfg)
        _lock_by_other_session(client)
        resp = client.post("/api/git/restore", json={"commit": initial}, headers={"X-Session-Id": "me"})
        assert resp.status_code == 423
        assert (cfg / "extra.cfg").exists()


class TestCommit:

    def test_commit_records_message_and_author(self, repo):
        app, client, cfg = repo
        (cfg / "hosts.cfg").write_text(HOSTS.replace("Original", "Committed"))

        resp = client.post("/api/git/commit", json={
            "message": "Rename web-01", "user_name": "Alice", "user_email": "alice@example.com",
        }, headers={"X-Session-Id": "s1"})

        assert resp.status_code == 200, resp.json
        assert _git(cfg, "log", "-1", "--format=%s|%an|%ae") == "Rename web-01|Alice|alice@example.com"
        assert _git(cfg, "status", "--porcelain") == ""
