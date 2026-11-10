"""Batch mutations are all-or-nothing; edits report the key the object now has."""

import pytest

from app import create_app
from app.nagios_model import OperationResult
from app.nagios_service import NagiosService
from app.shadow_copy_manager import ShadowCopyManager
from tests.test_audit_routes import _audit_capture

HEADERS = {"X-Session-Id": "s1"}

HOSTS = (
    "define host {\n    host_name web-01\n    address 10.0.0.1\n}\n\n"
    "define host {\n    host_name web-02\n    address 10.0.0.2\n}\n"
)
SERVICES = (
    "define service {\n    host_name web-01\n    service_description PING\n"
    "    check_command check_ping\n}\n"
)


@pytest.fixture
def env(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "hosts.cfg").write_text(HOSTS)
    (config_dir / "services.cfg").write_text(SERVICES)
    app = create_app(config_path=str(config_dir), log_dir_override=str(tmp_path / "logs"))
    app.config["TESTING"] = True
    sm = app.extensions["shadow"]
    sm.config_path = str(config_dir)
    sm.shadow_base_path = str(tmp_path / "shadow")
    return app, app.test_client(), sm, str(config_dir)


def _shadow_text(sm, name):
    with open(sm.shadow_path(name)) as f:
        return f.read()


def _key(cfg, name, otype, display):
    return f"{cfg}/{name}|{otype}|{display}"


def _two_updates(cfg):
    return [
        {"action": "update", "stable_key": _key(cfg, "hosts.cfg", "host", "web-01"),
         "attributes": {"host_name": "web-01", "address": "1.1.1.1"}},
        {"action": "update", "stable_key": _key(cfg, "hosts.cfg", "host", "web-02"),
         "attributes": {"host_name": "web-02", "address": "2.2.2.2"}},
    ]


def _fail_second_update(monkeypatch):
    original = NagiosService.update_object
    calls = {"n": 0}

    def flaky(self, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            from app.nagios_model import OperationResult
            return OperationResult(success=False, error="boom")
        return original(self, *a, **kw)

    monkeypatch.setattr(NagiosService, "update_object", flaky)


def test_batch_failure_rolls_back_everything(env, monkeypatch):
    app, client, sm, cfg = env
    first = client.post("/api/objects/update", headers=HEADERS, json={
        "stable_key": _key(cfg, "services.cfg", "service", "PING on web-01"),
        "attributes": {"host_name": "web-01", "service_description": "PING",
                       "check_command": "check_ping2"},
    })
    assert first.status_code == 200
    before = {n: _shadow_text(sm, n) for n in ("hosts.cfg", "services.cfg")}
    undo_before = client.get("/api/staging/info").get_json()["data"]["undoCount"]

    _fail_second_update(monkeypatch)
    resp = client.post("/api/batch-mutations", headers=HEADERS,
                       json={"operations": _two_updates(cfg)})
    body = resp.get_json()
    assert resp.status_code == 409
    assert body["success"] is False
    assert len(body["errors"]) == 1
    assert {n: _shadow_text(sm, n) for n in before} == before
    assert client.get("/api/staging/info").get_json()["data"]["undoCount"] == undo_before


def test_batch_failure_on_first_use_leaves_no_shadow(env, monkeypatch):
    app, client, sm, cfg = env
    assert not sm.has_shadow()
    _fail_second_update(monkeypatch)
    resp = client.post("/api/batch-mutations", headers=HEADERS,
                       json={"operations": _two_updates(cfg)})
    assert resp.status_code == 409
    assert sm.has_shadow() is False


def test_batch_missing_key_is_an_error(env):
    app, client, sm, cfg = env
    ops = _two_updates(cfg)[:1] + [
        {"action": "update", "stable_key": _key(cfg, "hosts.cfg", "host", "nope"),
         "attributes": {"host_name": "nope"}},
    ]
    resp = client.post("/api/batch-mutations", headers=HEADERS, json={"operations": ops})
    assert resp.status_code == 409
    assert resp.get_json()["success"] is False
    assert sm.has_shadow() is False


def test_batch_success_returns_new_keys(env):
    app, client, sm, cfg = env
    ops = [{"action": "update",
            "stable_key": _key(cfg, "services.cfg", "service", "PING on web-01"),
            "attributes": {"host_name": "web-02", "service_description": "PING",
                           "check_command": "check_ping"}}]
    resp = client.post("/api/batch-mutations", headers=HEADERS, json={"operations": ops})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["keys"] == [f"{cfg}/services.cfg|service|PING on web-02"]


def test_update_returns_key_matching_listing(env):
    app, client, sm, cfg = env
    resp = client.post("/api/objects/update", headers=HEADERS, json={
        "stable_key": _key(cfg, "services.cfg", "service", "PING on web-01"),
        "attributes": {"host_name": "web-01,web-02", "hostgroup_name": "hg",
                       "service_description": "PING", "check_command": "check_ping"},
    })
    key = resp.get_json()["stable_key"]
    listed = client.get("/api/objects?type=service").get_json()
    keys = {f"{o['source_file']}|{o['object_type']}|{_display(o)}" for o in listed}
    assert key in keys


def _display(o):
    return o.get("display_name") or o.get("name")


def test_batch_rollback_is_audited(env, monkeypatch):
    app, client, sm, cfg = env
    _fail_second_update(monkeypatch)
    with _audit_capture(app) as lines:
        resp = client.post("/api/batch-mutations", headers=HEADERS, json={
            "description": "two edits", "operations": _two_updates(cfg)})
    assert resp.status_code == 409
    assert any("action=batch_rollback" in l and "failed=1" in l and "total=2" in l
               for l in lines)


def test_batch_rollback_failure_is_a_500_and_keeps_shadow(env, monkeypatch):
    app, client, sm, cfg = env
    _fail_second_update(monkeypatch)
    monkeypatch.setattr(ShadowCopyManager, "undo",
                        lambda self: OperationResult(success=False, error="disk gone"))
    with _audit_capture(app) as lines:
        resp = client.post("/api/batch-mutations", headers=HEADERS,
                           json={"operations": _two_updates(cfg)})
    assert any("action=batch_rollback" in l and "rollback_failed=" in l and "disk gone" in l
               for l in lines)
    assert resp.status_code == 500
    assert resp.get_json()["error"].startswith(
        "Batch failed and could not be rolled back: disk gone.")
    assert sm.has_shadow() is True
