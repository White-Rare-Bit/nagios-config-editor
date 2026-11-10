"""POST /api/objects/rename and GET /api/objects/referenced-by.

Rename changes an object's name and, optionally, the references to it. Only
references of the renamed object's type count: renaming one "PING" service
must not touch another service whose description is also PING (UI_REVIEW bug 1).
"""

import pytest

from app import create_app
from app.nagios_service import NagiosService
from tests.test_audit_routes import _audit_capture

HEADERS = {"X-Session-Id": "s1"}

HOSTS = (
    "define host {\n    host_name web-01\n    address 10.0.0.1\n}\n\n"
    "define host {\n    host_name web-02\n    address 10.0.0.2\n}\n"
)
SERVICES = (
    "define service {\n    host_name web-01\n    service_description PING\n"
    "    check_command check_ping!100\n}\n\n"
    "define service {\n    host_name web-02\n    service_description PING\n"
    "    check_command check_ping!100\n}\n\n"
    "define service {\n    hostgroup_name web\n    host_name !web-01\n"
    "    service_description HTTP\n    check_command check_http\n}\n"
)
GROUPS = (
    "define hostgroup {\n    hostgroup_name web\n    members web-01,web-02\n}\n\n"
    "define contactgroup {\n    contactgroup_name web\n    alias Web team\n}\n"
)


def _make_env(tmp_path, extra=None):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    files = {"hosts.cfg": HOSTS, "services.cfg": SERVICES, "groups.cfg": GROUPS}
    files.update(extra or {})
    for name, text in files.items():
        (config_dir / name).write_text(text)
    app = create_app(config_path=str(config_dir), log_dir_override=str(tmp_path / "logs"))
    app.config["TESTING"] = True
    sm = app.extensions["shadow"]
    sm.config_path = str(config_dir)
    sm.shadow_base_path = str(tmp_path / "shadow")
    return app, app.test_client(), sm, str(config_dir)


@pytest.fixture
def env(tmp_path):
    return _make_env(tmp_path)


def _key(cfg, name, otype, display):
    return f"{cfg}/{name}|{otype}|{display}"


def _shadow_text(sm, name):
    with open(sm.shadow_path(name)) as f:
        return f.read()


def _objects(client):
    return client.get("/api/objects").get_json()


def _find(client, otype, **attrs):
    return [
        o for o in _objects(client)
        if o["object_type"] == otype
        and all(o["attributes"].get(k) == v for k, v in attrs.items())
    ]


def _rename(client, key, new_name, update_references=True):
    return client.post("/api/objects/rename", headers=HEADERS, json={
        "renames": [{"stable_key": key, "new_name": new_name}],
        "update_references": update_references,
    })


# -- rename ----------------------------------------------------------------


def test_rename_service_leaves_other_services_alone(env):
    app, client, sm, cfg = env
    resp = _rename(client, _key(cfg, "services.cfg", "service", "PING on web-01"), "PING4")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["keys"] == [_key(cfg, "services.cfg", "service", "PING4 on web-01")]
    assert body["references_updated"] == 0
    assert _find(client, "service", host_name="web-01", service_description="PING4")
    assert _find(client, "service", host_name="web-02", service_description="PING")


def test_rename_host_updates_references(env):
    app, client, sm, cfg = env
    resp = _rename(client, _key(cfg, "hosts.cfg", "host", "web-01"), "web-03")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["keys"] == [_key(cfg, "hosts.cfg", "host", "web-03")]
    assert body["references_updated"] == 3
    assert _find(client, "host", host_name="web-03")
    assert _find(client, "service", host_name="web-03", service_description="PING")
    assert _find(client, "hostgroup", hostgroup_name="web", members="web-03,web-02")
    assert _find(client, "service", service_description="HTTP", host_name="!web-03")


def test_rename_hostgroup_ignores_same_named_contactgroup(env):
    app, client, sm, cfg = env
    resp = _rename(client, _key(cfg, "groups.cfg", "hostgroup", "web"), "web-servers")
    assert resp.status_code == 200, resp.get_json()
    assert _find(client, "hostgroup", hostgroup_name="web-servers")
    assert _find(client, "contactgroup", contactgroup_name="web")
    assert _find(client, "service", service_description="HTTP", hostgroup_name="web-servers")


def test_rename_without_reference_update(env):
    app, client, sm, cfg = env
    resp = _rename(client, _key(cfg, "hosts.cfg", "host", "web-01"), "web-03",
                   update_references=False)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 0
    assert _find(client, "host", host_name="web-03")
    assert _find(client, "service", host_name="web-01", service_description="PING")
    assert _find(client, "hostgroup", members="web-01,web-02")
    assert _shadow_text(sm, "groups.cfg") == GROUPS
    assert _shadow_text(sm, "services.cfg") == SERVICES


def test_rename_is_one_undo(env):
    app, client, sm, cfg = env
    resp = _rename(client, _key(cfg, "hosts.cfg", "host", "web-01"), "web-03")
    assert resp.status_code == 200, resp.get_json()
    for name in ("hosts.cfg", "services.cfg", "groups.cfg"):
        assert "web-03" in _shadow_text(sm, name)
    assert client.get("/api/staging/info").get_json()["data"]["undoCount"] == 1

    undo = client.post("/api/staging/undo", headers=HEADERS)
    assert undo.status_code == 200, undo.get_json()
    assert _shadow_text(sm, "hosts.cfg") == HOSTS
    assert _shadow_text(sm, "services.cfg") == SERVICES
    assert _shadow_text(sm, "groups.cfg") == GROUPS


def test_rename_updates_references_in_second_root(tmp_path):
    from app.server_config import ServerConfig, save_config

    dir_a = tmp_path / "servers"
    dir_b = tmp_path / "checks"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "hosts.cfg").write_text(HOSTS)
    (dir_b / "services.cfg").write_text(SERVICES)
    nagios_cfg = tmp_path / "nagios.cfg"
    nagios_cfg.write_text(f"cfg_dir={dir_a}\ncfg_dir={dir_b}\n")
    config = ServerConfig()
    config.paths.nagios_cfg = str(nagios_cfg)
    save_config(config)

    app = create_app(log_dir_override=str(tmp_path / "logs"))
    app.config["TESTING"] = True
    client = app.test_client()

    resp = _rename(client, f"{dir_a}/hosts.cfg|host|web-01", "web-03")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 2
    services = [o for o in _objects(client) if o["object_type"] == "service"]
    assert {o["source_file"] for o in services} == {f"{dir_b}/services.cfg"}
    assert any(o["attributes"].get("host_name") == "web-03" for o in services)
    assert any(o["attributes"].get("host_name") == "!web-03" for o in services)


def test_rename_host_leaves_use_alone(tmp_path):
    templates = (
        "define host {\n    name web-01\n    register 0\n    check_interval 5\n}\n\n"
        "define host {\n    use web-01\n    host_name web-09\n    address 10.0.0.9\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"templates.cfg": templates})
    resp = _rename(client, _key(cfg, "hosts.cfg", "host", "web-01"), "web-03")
    assert resp.status_code == 200, resp.get_json()
    assert _find(client, "host", host_name="web-09", use="web-01")
    assert _shadow_text(sm, "templates.cfg") == templates


def test_rename_contact_ignores_hostgroup_members(tmp_path):
    contacts = (
        "define contact {\n    contact_name web-01\n    email a@example.com\n}\n\n"
        "define contactgroup {\n    contactgroup_name admins\n    members web-01\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"contacts.cfg": contacts})
    resp = _rename(client, _key(cfg, "contacts.cfg", "contact", "web-01"), "alice")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 1
    assert _find(client, "contactgroup", contactgroup_name="admins", members="alice")
    assert _find(client, "hostgroup", hostgroup_name="web", members="web-01,web-02")
    assert _find(client, "service", host_name="web-01", service_description="PING")


def test_rename_service_updates_matching_servicegroup_pair_only(tmp_path):
    sg = (
        "define servicegroup {\n    servicegroup_name pings\n"
        "    members web-01,PING,web-02,PING\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"servicegroups.cfg": sg})
    resp = _rename(client, _key(cfg, "services.cfg", "service", "PING on web-01"), "PING4")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 1
    assert _find(client, "servicegroup", servicegroup_name="pings",
                 members="web-01,PING4,web-02,PING")


def test_rename_service_updates_dependency_on_same_host_only(tmp_path):
    deps = (
        "define servicedependency {\n    host_name web-01\n    service_description PING\n"
        "    dependent_host_name web-02\n    dependent_service_description PING\n}\n\n"
        "define servicedependency {\n    host_name web-02\n    service_description PING\n"
        "    dependent_host_name web-02\n    dependent_service_description HTTP\n}\n\n"
        "define serviceescalation {\n    host_name web-02\n    service_description PING\n"
        "    first_notification 2\n    last_notification 0\n    notification_interval 30\n"
        "    contact_groups web\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"deps.cfg": deps})
    resp = _rename(client, _key(cfg, "services.cfg", "service", "PING on web-01"), "PING4")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 1
    assert _find(client, "servicedependency", host_name="web-01",
                 service_description="PING4", dependent_service_description="PING")
    assert _find(client, "servicedependency", host_name="web-02",
                 service_description="PING", dependent_service_description="HTTP")
    assert _find(client, "serviceescalation", host_name="web-02", service_description="PING")


def test_rename_command_keeps_arguments(tmp_path):
    commands = (
        "define command {\n    command_name check_ping\n"
        "    command_line $USER1$/check_ping -H $HOSTADDRESS$ -w $ARG1$\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"commands.cfg": commands})
    resp = _rename(client, _key(cfg, "commands.cfg", "command", "check_ping"), "check_icmp")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 2
    assert len(_find(client, "service", check_command="check_icmp!100")) == 2
    assert _find(client, "service", service_description="HTTP", check_command="check_http")


def test_rename_several_objects_in_one_request(env):
    app, client, sm, cfg = env
    resp = client.post("/api/objects/rename", headers=HEADERS, json={
        "renames": [
            {"stable_key": _key(cfg, "hosts.cfg", "host", "web-01"), "new_name": "app-01"},
            {"stable_key": _key(cfg, "hosts.cfg", "host", "web-02"), "new_name": "app-02"},
        ],
        "update_references": True,
    })
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["keys"] == [
        _key(cfg, "hosts.cfg", "host", "app-01"),
        _key(cfg, "hosts.cfg", "host", "app-02"),
    ]
    # Two PING services, the hostgroup (both members in one edit), and HTTP.
    assert body["references_updated"] == 4
    assert _find(client, "hostgroup", members="app-01,app-02")
    assert client.get("/api/staging/info").get_json()["data"]["undoCount"] == 1


def test_rename_failure_rolls_back(env, monkeypatch):
    app, client, sm, cfg = env
    original = NagiosService.update_object
    calls = {"n": 0}

    def flaky(self, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            from app.nagios_model import OperationResult
            return OperationResult(success=False, error="boom")
        return original(self, *a, **kw)

    monkeypatch.setattr(NagiosService, "update_object", flaky)
    with _audit_capture(app) as lines:
        resp = _rename(client, _key(cfg, "hosts.cfg", "host", "web-01"), "web-03")
    assert resp.status_code == 409
    assert resp.get_json()["success"] is False
    assert "boom" in resp.get_json()["error"]
    assert any("action=rename_rollback" in line for line in lines)
    # The request created the shadow and changed nothing in the end.
    assert sm.has_shadow() is False
    assert _find(client, "host", host_name="web-01")


def test_rename_template_updates_same_type_use_only(tmp_path):
    templates = (
        "define host {\n    name generic\n    register 0\n}\n\n"
        "define service {\n    name generic\n    register 0\n}\n\n"
        "define host {\n    use generic\n    host_name web-09\n}\n\n"
        "define host {\n    use other,generic\n    host_name web-10\n}\n\n"
        "define service {\n    use generic\n    host_name web-09\n    service_description X\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"templates.cfg": templates})
    key = _key(cfg, "templates.cfg", "host", "generic")
    refs = _referenced_by(client, key).get_json()["references"]
    assert sorted((r["display_name"], tuple(r["fields"])) for r in refs) == [
        ("web-09", ("use",)), ("web-10", ("use",)),
    ]

    resp = _rename(client, key, "base-host")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["keys"] == [_key(cfg, "templates.cfg", "host", "base-host")]
    assert body["references_updated"] == 2
    assert _find(client, "host", name="base-host", register="0")
    assert _find(client, "host", host_name="web-09", use="base-host")
    assert _find(client, "host", host_name="web-10", use="other,base-host")
    assert _find(client, "service", name="generic", register="0")
    assert _find(client, "service", service_description="X", use="generic")


def test_rename_object_without_own_name_is_refused(tmp_path):
    deps = (
        "define servicedependency {\n    host_name web-01\n    service_description PING\n"
        "    dependent_host_name web-02\n    dependent_service_description PING\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"deps.cfg": deps})
    resp = _rename(client, _key(cfg, "deps.cfg", "servicedependency", "PING on web-01 → PING"), "X")
    assert resp.status_code == 400
    assert resp.get_json() == {
        "success": False, "error": "servicedependency objects have no name of their own",
    }
    assert sm.has_shadow() is False


def test_rename_hostgroup_service_updates_dependency_naming_member_host(tmp_path):
    extra = (
        "define service {\n    hostgroup_name web\n    service_description HTTPS\n"
        "    check_command check_http\n}\n\n"
        "define servicedependency {\n    host_name web-02\n    service_description HTTPS\n"
        "    dependent_host_name web-02\n    dependent_service_description PING\n}\n\n"
        # HTTP on web excludes web-01, so this names a service that does not exist
        "define servicedependency {\n    host_name web-01\n    service_description HTTP\n"
        "    dependent_host_name web-01\n    dependent_service_description PING\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"extra.cfg": extra})
    resp = _rename(client, _key(cfg, "extra.cfg", "service", "HTTPS on web"), "HTTPS2")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 1
    assert _find(client, "servicedependency", host_name="web-02", service_description="HTTPS2")

    resp = _rename(client, _key(cfg, "services.cfg", "service", "HTTP on web"), "HTTP2")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 0
    assert _find(client, "servicedependency", host_name="web-01", service_description="HTTP")


def test_referenced_by_finds_servicegroup_pair_for_hostgroup_service(tmp_path):
    sg = (
        "define servicegroup {\n    servicegroup_name web-checks\n"
        "    members web-02,HTTP,web-01,HTTP\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"servicegroups.cfg": sg})
    key = _key(cfg, "services.cfg", "service", "HTTP on web")
    refs = _referenced_by(client, key).get_json()["references"]
    assert [(r["object_type"], r["display_name"], r["fields"]) for r in refs] == [
        ("servicegroup", "web-checks", ["members"]),
    ]
    resp = _rename(client, key, "HTTP2")
    assert resp.status_code == 200, resp.get_json()
    # web-01 is excluded from HTTP on web, so only the web-02 pair is its.
    assert _find(client, "servicegroup", members="web-02,HTTP2,web-01,HTTP")


def test_rename_wildcard_service_updates_dependency(tmp_path):
    extra = (
        "define service {\n    host_name *\n    service_description DISK\n"
        "    check_command check_disk\n}\n\n"
        "define servicedependency {\n    host_name web-01\n    service_description DISK\n"
        "    dependent_host_name web-01\n    dependent_service_description PING\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"extra.cfg": extra})
    resp = _rename(client, _key(cfg, "extra.cfg", "service", "DISK on *"), "DISK2")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 1
    assert _find(client, "servicedependency", host_name="web-01", service_description="DISK2")


def test_rename_service_updates_wildcard_dependency(tmp_path):
    deps = (
        "define servicedependency {\n    host_name *\n    service_description PING\n"
        "    dependent_host_name web-02\n    dependent_service_description HTTP\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"deps.cfg": deps})
    resp = _rename(client, _key(cfg, "services.cfg", "service", "PING on web-01"), "PING4")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references_updated"] == 1
    assert _find(client, "servicedependency", host_name="*", service_description="PING4")


def test_bulk_rename_updates_links_between_renamed_objects(tmp_path):
    parents = (
        "define host {\n    host_name core-a\n    address 10.1.0.1\n}\n\n"
        "define host {\n    host_name core-b\n    parents core-a\n    address 10.1.0.2\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"core.cfg": parents})
    resp = client.post("/api/objects/rename", headers=HEADERS, json={
        "renames": [
            {"stable_key": _key(cfg, "core.cfg", "host", "core-a"), "new_name": "edge-a"},
            {"stable_key": _key(cfg, "core.cfg", "host", "core-b"), "new_name": "edge-b"},
        ],
        "update_references": True,
    })
    assert resp.status_code == 200, resp.get_json()
    assert _find(client, "host", host_name="edge-a")
    assert _find(client, "host", host_name="edge-b", parents="edge-a")
    assert client.get("/api/staging/info").get_json()["data"]["undoCount"] == 1


def test_bulk_rename_host_and_its_service(env):
    app, client, sm, cfg = env
    resp = client.post("/api/objects/rename", headers=HEADERS, json={
        "renames": [
            {"stable_key": _key(cfg, "hosts.cfg", "host", "web-01"), "new_name": "app-01"},
            {"stable_key": _key(cfg, "services.cfg", "service", "PING on web-01"),
             "new_name": "PING4"},
        ],
        "update_references": True,
    })
    assert resp.status_code == 200, resp.get_json()
    # The service gets both its new name and its host's new name, in one write,
    # and its returned key reflects both.
    assert resp.get_json()["keys"] == [
        _key(cfg, "hosts.cfg", "host", "app-01"),
        _key(cfg, "services.cfg", "service", "PING4 on app-01"),
    ]
    assert _find(client, "service", host_name="app-01", service_description="PING4")
    assert _find(client, "service", host_name="web-02", service_description="PING")


def test_rename_rejects_bad_requests(env):
    app, client, sm, cfg = env
    key = _key(cfg, "hosts.cfg", "host", "web-01")
    assert client.post("/api/objects/rename", headers=HEADERS, json={}).status_code == 400
    assert _rename(client, key, "  ").status_code == 400
    assert _rename(client, key, "a,b").status_code == 400
    assert _rename(client, key, "a\nb").status_code == 400
    assert _rename(client, _key(cfg, "hosts.cfg", "host", "nope"), "x").status_code == 404
    for bad in ("yes", 1, None):
        resp = client.post("/api/objects/rename", headers=HEADERS, json={
            "renames": [{"stable_key": key, "new_name": "x"}], "update_references": bad})
        assert resp.status_code == 400, bad
    assert sm.has_shadow() is False


def test_rename_is_audited(env):
    app, client, sm, cfg = env
    with _audit_capture(app) as lines:
        resp = _rename(client, _key(cfg, "hosts.cfg", "host", "web-01"), "web-03")
    assert resp.status_code == 200
    edits = [line for line in lines if "action=object_edit" in line]
    assert any("field=host_name" in line and "to=web-03" in line for line in edits)
    assert any("field=members" in line for line in edits)


# -- referenced-by ----------------------------------------------------------


def _referenced_by(client, key):
    return client.get("/api/objects/referenced-by", query_string={"key": key})


def test_referenced_by_counts_typed_references(env):
    app, client, sm, cfg = env
    resp = _referenced_by(client, _key(cfg, "services.cfg", "service", "PING on web-01"))
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["references"] == []

    resp = _referenced_by(client, _key(cfg, "hosts.cfg", "host", "web-01"))
    assert resp.status_code == 200, resp.get_json()
    refs = resp.get_json()["references"]
    assert len(refs) == 3
    by_name = {r["display_name"]: r for r in refs}
    assert by_name["PING on web-01"]["fields"] == ["host_name"]
    assert by_name["PING on web-01"]["object_type"] == "service"
    assert by_name["PING on web-01"]["stable_key"] == _key(
        cfg, "services.cfg", "service", "PING on web-01")
    assert by_name["web"]["fields"] == ["members"]
    assert by_name["HTTP on web"]["fields"] == ["host_name"]


def test_referenced_by_hostgroup_lists_fields(env):
    app, client, sm, cfg = env
    refs = _referenced_by(client, _key(cfg, "groups.cfg", "hostgroup", "web")).get_json()["references"]
    assert [(r["display_name"], r["fields"]) for r in refs] == [("HTTP on web", ["hostgroup_name"])]


def test_referenced_by_errors(env):
    app, client, sm, cfg = env
    assert client.get("/api/objects/referenced-by").status_code == 400
    resp = _referenced_by(client, _key(cfg, "hosts.cfg", "host", "nope"))
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


def test_referenced_by_lists_template_users(tmp_path):
    """Deleting a template breaks the objects that use it, so they are listed."""
    templates = (
        "define host {\n    name generic-host\n    register 0\n}\n\n"
        "define host {\n    use generic-host\n    host_name web-09\n}\n\n"
        "define service {\n    use generic-host\n    service_description X\n}\n"
    )
    app, client, sm, cfg = _make_env(tmp_path, {"templates.cfg": templates})
    resp = _referenced_by(client, _key(cfg, "templates.cfg", "host", "generic-host"))
    assert resp.status_code == 200, resp.get_json()
    assert [(r["display_name"], r["fields"]) for r in resp.get_json()["references"]] == [
        ("web-09", ["use"]),
    ]


# -- key_changes (UI_REVIEW bug 6 through referencing objects) ------------------


def test_rename_hostgroup_reports_key_changes_of_referencing_services(env):
    """A service's key names its hostgroup, so renaming the hostgroup changes
    the service's key too; the client needs both to keep their tabs open."""
    app, client, sm, cfg = env
    resp = _rename(client, _key(cfg, "groups.cfg", "hostgroup", "web"), "web-servers")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["key_changes"] == {
        _key(cfg, "groups.cfg", "hostgroup", "web"):
            _key(cfg, "groups.cfg", "hostgroup", "web-servers"),
        _key(cfg, "services.cfg", "service", "HTTP on web"):
            _key(cfg, "services.cfg", "service", "HTTP on web-servers"),
    }


def test_rename_host_key_changes_leave_out_unchanged_keys(env):
    """Objects whose references changed but whose key did not (the hostgroup's
    members, the HTTP service's ``!web-01``) are not listed."""
    app, client, sm, cfg = env
    resp = _rename(client, _key(cfg, "hosts.cfg", "host", "web-01"), "web-03")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["key_changes"] == {
        _key(cfg, "hosts.cfg", "host", "web-01"): _key(cfg, "hosts.cfg", "host", "web-03"),
        _key(cfg, "services.cfg", "service", "PING on web-01"):
            _key(cfg, "services.cfg", "service", "PING on web-03"),
    }


def test_rename_without_changes_reports_no_key_changes(env):
    app, client, sm, cfg = env
    resp = _rename(client, _key(cfg, "hosts.cfg", "host", "web-01"), "web-01")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["key_changes"] == {}

