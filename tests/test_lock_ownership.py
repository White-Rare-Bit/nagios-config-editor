"""Only the session that owns the staging lock may apply, discard or change it."""

OWNER_SESSION = "sess-7f3a-secret"
OWNER = {"X-Session-Id": OWNER_SESSION}
OTHER = {"X-Session-Id": "intruder"}


def _stage_edit(client):
    host = [o for o in client.get("/api/objects?type=host").json
            if "host_name" in o["attributes"]][0]
    resp = client.post("/api/objects/update", headers=OWNER, json={
        "stable_key": f"{host['source_file']}|host|{host['attributes']['host_name']}",
        "attributes": dict(host["attributes"], alias="STAGED"),
    })
    assert resp.status_code == 200
    return host


def _staged_count(client):
    return client.get("/api/staging/info").json["data"]["totalCount"]


class TestOwnership:
    def test_other_session_cannot_discard(self, client):
        _stage_edit(client)
        assert client.delete("/api/staging", headers=OTHER).status_code == 423
        assert _staged_count(client) == 1

    def test_missing_session_cannot_discard(self, client):
        _stage_edit(client)
        assert client.delete("/api/staging").status_code == 423
        assert _staged_count(client) == 1

    def test_other_session_cannot_apply(self, client):
        host = _stage_edit(client)
        assert client.post("/api/staging/apply", headers=OTHER).status_code == 423
        assert "STAGED" not in open(host["source_file"]).read()
        assert _staged_count(client) == 1

    def test_other_session_cannot_undo(self, client):
        _stage_edit(client)
        assert client.post("/api/staging/undo", headers=OTHER).status_code == 423
        assert _staged_count(client) == 1

    def test_other_session_cannot_restore_backup_under_staged_work(self, client):
        client.post("/api/backups", json={"description": "b"})
        name = client.get("/api/backups").json[0]["name"]
        _stage_edit(client)
        assert client.post(f"/api/backups/{name}/restore", headers=OTHER, json={}).status_code == 423

    def test_owner_can_apply(self, client):
        host = _stage_edit(client)
        assert client.post("/api/staging/apply", headers=OWNER).status_code == 200
        assert "STAGED" in open(host["source_file"]).read()

    def test_owner_can_discard(self, client):
        _stage_edit(client)
        assert client.delete("/api/staging", headers=OWNER).status_code == 200
        assert _staged_count(client) == 0


class TestLockStatusDoesNotLeakTheSession:
    def test_session_id_is_not_exposed(self, client):
        _stage_edit(client)
        for headers in (OWNER, OTHER, {}):
            body = client.get("/api/staging/lock", headers=headers).get_data(as_text=True)
            assert OWNER_SESSION not in body

    def test_is_owner_tells_each_session_where_it_stands(self, client):
        _stage_edit(client)
        assert client.get("/api/staging/lock", headers=OWNER).json["data"]["is_owner"] is True
        assert client.get("/api/staging/lock", headers=OTHER).json["data"]["is_owner"] is False

    def test_lock_conflict_response_does_not_leak_the_session(self, client):
        _stage_edit(client)
        resp = client.post("/api/git/discard-all", headers=OTHER)
        assert resp.status_code == 423
        assert OWNER_SESSION not in resp.get_data(as_text=True)

    def test_break_lock_is_still_available_to_others_and_is_audited(self, client, app):
        _stage_edit(client)
        assert client.post("/api/staging/lock/break", headers=OTHER).status_code == 200
        assert client.get("/api/staging/lock").json["data"]["locked"] is False
        import os
        audit = open(os.path.join(app.extensions["log_dir"], "audit.log")).read()
        assert "action=lock_break" in audit
