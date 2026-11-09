"""Two app instances sharing one config dir behave like two gunicorn workers.

Each create_app() call builds an independent app (own service, own parser
cache) over the same files on disk, which is exactly what two worker
processes are. Everything a worker needs to know about staging must
therefore come from disk, not from memory.
"""

import os

from app import create_app

H_A = {"X-Session-Id": "session-a"}


def _worker(config_path):
    application = create_app(config_path=config_path)
    application.config["TESTING"] = True
    return application.test_client()


def _real_hosts(client):
    """Hosts with a host_name (the sample config also has host templates)."""
    return [o for o in client.get("/api/objects?type=host").json
            if "host_name" in o["attributes"]]


def _first_host(client):
    return _real_hosts(client)[0]


def _key(obj):
    return f"{obj['source_file']}|host|{obj['attributes']['host_name']}"


def _edit(client, obj, alias, headers=H_A):
    attrs = dict(obj["attributes"], alias=alias)
    return client.post(
        "/api/objects/update", headers=headers,
        json={"stable_key": _key(obj), "attributes": attrs},
    )


class TestFactory:
    def test_create_app_returns_independent_apps(self, sample_config_path):
        first = create_app(config_path=sample_config_path)
        second = create_app(config_path=sample_config_path)
        assert first is not second
        assert first.extensions["service"] is not second.extensions["service"]


class TestTwoWorkers:
    def test_other_worker_sees_staged_edit(self, sample_config_path):
        a, b = _worker(sample_config_path), _worker(sample_config_path)
        host = _first_host(a)
        _first_host(b)  # worker B has parsed and cached the original config

        assert _edit(a, host, "EDITED").status_code == 200

        seen = [o for o in _real_hosts(b)
                if o["attributes"]["host_name"] == host["attributes"]["host_name"]][0]
        assert seen["attributes"]["alias"] == "EDITED"

    def test_edit_through_other_worker_stays_out_of_live_config(self, sample_config_path):
        a, b = _worker(sample_config_path), _worker(sample_config_path)
        host = _first_host(a)
        _first_host(b)
        live_file = host["source_file"]
        before = open(live_file).read()

        assert _edit(a, host, "EDIT_ONE").status_code == 200
        assert _edit(b, host, "EDIT_TWO").status_code == 200

        assert open(live_file).read() == before
        assert a.get("/api/staging/info").json["data"]["totalCount"] == 1

    def test_other_worker_follows_undo_and_discard(self, sample_config_path):
        a, b = _worker(sample_config_path), _worker(sample_config_path)
        host = _first_host(a)
        original_alias = host["attributes"].get("alias")
        name = host["attributes"]["host_name"]

        def alias_seen_by(client):
            return [o for o in _real_hosts(client)
                    if o["attributes"]["host_name"] == name][0]["attributes"].get("alias")

        _edit(a, host, "ONE")
        _edit(a, host, "TWO")
        assert alias_seen_by(b) == "TWO"

        assert a.post("/api/staging/undo", headers=H_A).status_code == 200
        assert alias_seen_by(b) == "ONE"

        assert a.delete("/api/staging", headers=H_A).status_code == 200
        assert alias_seen_by(b) == original_alias

    def test_other_worker_sees_applied_change(self, sample_config_path):
        a, b = _worker(sample_config_path), _worker(sample_config_path)
        host = _first_host(a)
        _first_host(b)
        _edit(a, host, "APPLIED")
        assert a.post("/api/staging/apply", headers=H_A).status_code == 200

        seen = [o for o in _real_hosts(b)
                if o["attributes"]["host_name"] == host["attributes"]["host_name"]][0]
        assert seen["attributes"]["alias"] == "APPLIED"
        assert "EDITED" not in open(host["source_file"]).read()
        assert "APPLIED" in open(host["source_file"]).read()

    def test_worker_restart_keeps_staged_work(self, sample_config_path):
        a = _worker(sample_config_path)
        host = _first_host(a)
        _edit(a, host, "SURVIVES")

        restarted = _worker(sample_config_path)  # a recycled worker boots

        assert restarted.get("/api/staging/lock").json["data"]["locked"] is True
        seen = [o for o in _real_hosts(restarted)
                if o["attributes"]["host_name"] == host["attributes"]["host_name"]][0]
        assert seen["attributes"]["alias"] == "SURVIVES"

    def test_startup_drops_shadow_left_over_from_different_roots(self, sample_config_path, tmp_path):
        a = _worker(sample_config_path)
        _edit(a, _first_host(a), "STALE")
        shadow_base = a.application.extensions["shadow"].shadow_base_path

        other_root = tmp_path / "other"
        other_root.mkdir()
        (other_root / "hosts.cfg").write_text("define host {\n    host_name x\n}\n")
        from app.shadow_copy_manager import ShadowCopyManager
        sm = ShadowCopyManager(cfg_dirs=[str(other_root)], shadow_base_path=shadow_base)
        assert sm.has_shadow()
        sm.discard_if_stale()
        assert not sm.has_shadow()

    def test_settings_change_reaches_other_worker(self, tmp_path):
        """A worker picks up config/settings.json saved by another worker."""
        dir_a = tmp_path / "servers"
        dir_b = tmp_path / "switches"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "hosts.cfg").write_text("define host {\n    host_name web1\n}\n")
        (dir_b / "hosts.cfg").write_text("define host {\n    host_name switch1\n}\n")
        cfg_one = tmp_path / "one.cfg"
        cfg_one.write_text(f"cfg_dir={dir_a}\n")
        cfg_two = tmp_path / "two.cfg"
        cfg_two.write_text(f"cfg_dir={dir_a}\ncfg_dir={dir_b}\n")

        from app.server_config import ServerConfig, save_config
        config = ServerConfig()
        config.paths.nagios_cfg = str(cfg_one)
        save_config(config)

        a = create_app().test_client()
        b = create_app().test_client()
        assert {o["attributes"]["host_name"] for o in b.get("/api/objects").json} == {"web1"}

        resp = a.post("/api/settings", json={"nagios_cfg": str(cfg_two)})
        assert resp.status_code == 200, resp.json

        names = {o["attributes"]["host_name"] for o in b.get("/api/objects").json}
        assert names == {"web1", "switch1"}


class TestProcessLock:
    def test_lock_excludes_other_processes(self, tmp_path):
        """A lock held here must block a different process (what a worker is)."""
        import subprocess
        import sys
        from app.process_lock import ProcessLock

        lock_file = tmp_path / "x.lock"
        probe = (
            "import sys\n"
            "from app.process_lock import ProcessLock\n"
            "lock = ProcessLock(sys.argv[1])\n"
            "print('acquired' if lock.acquire(timeout=0.3) else 'blocked')\n"
        )
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def run_probe():
            return subprocess.run(
                [sys.executable, "-c", probe, str(lock_file)],
                capture_output=True, text=True, cwd=repo_root, check=True,
            ).stdout.strip()

        with ProcessLock(str(lock_file)):
            assert run_probe() == "blocked"
        assert run_probe() == "acquired"
