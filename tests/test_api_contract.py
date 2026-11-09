"""Every API error has the same shape; domain logic lives outside routes."""

import pytest

H = {"X-Session-Id": "s1"}

ERROR_REQUESTS = [
    ("post", "/api/objects/update", {}),
    ("post", "/api/objects/update", {"stable_key": "/nope.cfg|host|x", "attributes": {"a": "b"}}),
    ("post", "/api/objects/create", {}),
    ("post", "/api/objects/delete", {"stable_key": "/nope.cfg|host|x"}),
    ("post", "/api/files/create", {}),
    ("post", "/api/folders", {}),
    ("post", "/api/files/move", {}),
    ("post", "/api/move-objects", {}),
    ("post", "/api/batch-mutations", {}),
    ("post", "/api/git/commit", {}),
    ("post", "/api/git/restore", {}),
    ("post", "/api/backups/nope.zip/restore", {}),
    ("delete", "/api/backups/nope.zip", None),
    ("delete", "/api/files/nope.cfg", None),
    ("get", "/api/no-such-endpoint", None),
]


@pytest.mark.parametrize("method,url,body", ERROR_REQUESTS)
def test_errors_share_one_shape(client, method, url, body):
    kwargs = {"headers": H}
    if body is not None:
        kwargs["json"] = body
    resp = getattr(client, method)(url, **kwargs)

    assert resp.status_code >= 400
    assert resp.is_json, f"{url} answered {resp.status_code} without JSON"
    assert resp.json["success"] is False
    assert isinstance(resp.json["error"], str) and resp.json["error"]


def test_health_checks_are_not_a_routes_module():
    from app import health_checks
    assert callable(health_checks.run_all_checks)
    with pytest.raises(ImportError):
        from app.routes import health_checks as _old  # noqa: F401
