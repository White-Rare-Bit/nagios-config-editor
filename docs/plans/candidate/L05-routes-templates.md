# L05: routes/templates.py — MODIFY

**Layer:** 5 — Route Analysis
**Action:** MODIFY
**Path:** `routes/templates.py`
**Dependencies:** L03 (get_objects_for_request must exist in routes/helpers.py)
**Goal:** Make 3 read-only GET endpoints candidate-aware via `?candidate=1` query param.

---

## Scope

All three endpoints and the private helper in `routes/templates.py` are **read-only** (GET). This plan:
- Replaces `service.get_objects()` calls with `get_objects_for_request()` so each endpoint returns data from either the running config or the candidate copy.
- Does **not** introduce any mutations, writes, or state changes.
- Does **not** alter any UI — these are backend JSON API endpoints only.

## Changes

### 1. Update imports

Replace:
```python
from .helpers import get_service
```
With:
```python
from .helpers import get_objects_for_request
```

`get_service` is no longer called directly in this file after the migration; remove it from the import line. `base64` and the `flask` imports remain unchanged.

### 2. Endpoint: `GET /api/templates`

Replace `service = get_service()` and `service.get_objects()` with `get_objects_for_request()`:

```python
@bp.route("/api/templates")
def list_templates():
    """List all templates grouped by object type."""
    objects, is_candidate = get_objects_for_request()
    templates_by_type = {}

    for obj in objects:
        if obj.attributes.get("register", "1") == "0":
            obj_type = obj.object_type
            if obj_type not in templates_by_type:
                templates_by_type[obj_type] = []
            templates_by_type[obj_type].append(obj.to_dict())

    return jsonify(templates_by_type)
```

**Error handling:** `get_objects_for_request()` aborts with 404 if `?candidate=1` is set but no candidate session exists. This propagates as a proper HTTP 404 response — no silent failure.

### 3. Endpoint: `GET /api/templates/inheritance/<stable_key>`

Replace both `service = get_service()` and `service.get_objects()` calls. Pass `objects` to the updated `_decode_and_find_object()` helper:

```python
@bp.route("/api/templates/inheritance/<stable_key>")
def get_inheritance(stable_key):
    """Get inheritance chain for an object by stable key."""
    objects, is_candidate = get_objects_for_request()

    target_obj, obj_type, error = _decode_and_find_object(objects, stable_key)
    if error:
        return error

    template_lookup = build_type_template_lookup(objects, obj_type)
    chain, inherited, errors = resolve_chain(target_obj, obj_type, template_lookup)

    return jsonify({"chain": chain, "inherited": inherited, "errors": errors})
```

**Error handling:** Existing error tuple returns from `_decode_and_find_object()` (400 for bad key, 404 for not found) are preserved unchanged.

### 4. Endpoint: `GET /api/templates/validate-use`

Replace `service = get_service()` and `service.get_objects()`:

```python
@bp.route("/api/templates/validate-use")
def validate_use():
    """Check if use references exist for given object type."""
    obj_type = request.args.get("object_type", "")
    use_string = request.args.get("use", "")

    if not obj_type or not use_string:
        return jsonify({"error": "object_type and use parameters required"}), 400

    objects, is_candidate = get_objects_for_request()

    # Build template lookup for this object type
    template_names = set()
    for obj in objects:
        if obj.object_type == obj_type and obj.attributes.get("register", "1") == "0":
            name = obj.attributes.get("name")
            if name:
                template_names.add(name)

    # Check each template in use string
    errors = []
    use_list = [t.strip() for t in use_string.split(",") if t.strip()]

    for tmpl_name in use_list:
        if tmpl_name not in template_names:
            errors.append(f"Template '{tmpl_name}' not found for type '{obj_type}'")

    return jsonify({
        "valid": len(errors) == 0,
        "errors": errors,
    })
```

**Error handling:** Existing 400 response for missing parameters is preserved.

### 5. Helper: `_decode_and_find_object()`

Change signature from `(service, stable_key)` to `(objects, stable_key)`. Replace internal `service.get_objects()` iteration with the passed `objects` list:

```python
def _decode_and_find_object(objects, stable_key):
    """Decode a base64 stable key and find the matching object.

    Args:
        objects: List of NagiosObject instances to search.
        stable_key: Base64-encoded "source_file|object_type|name" string.

    Returns:
        Tuple of (target_obj, obj_type, error_response).
        If error_response is not None, target_obj and obj_type are None.

    """
    if not stable_key:
        return None, None, (jsonify({"error": "stable_key parameter required"}), 400)

    try:
        decoded_key = base64.b64decode(stable_key).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None, None, (jsonify({"error": "Invalid stable key encoding"}), 400)

    try:
        source_file, obj_type, obj_name = decoded_key.split("|", 2)
    except ValueError:
        return None, None, (jsonify({"error": "Invalid stable key format"}), 400)

    for obj in objects:
        if (obj.source_file == source_file and
            obj.object_type == obj_type and
            obj.get_display_name() == obj_name):
            return obj, obj_type, None

    return None, None, (jsonify({"error": "Object not found"}), 404)
```

**Error handling preserved:** All four error paths (missing key: 400, bad encoding: 400, bad format: 400, not found: 404) remain unchanged.

## Removal Audit

| Removed | Reason |
|---------|--------|
| `from .helpers import get_service` | No longer called anywhere in this file. All `service.get_objects()` calls replaced by `get_objects_for_request()`. |
| `service = get_service()` (3 occurrences) | Replaced by `get_objects_for_request()`. |
| `service` parameter in `_decode_and_find_object` | Replaced by `objects` parameter; function no longer calls `service.get_objects()` internally. |

No dead code is left behind. No functionality is dropped.

## Audit Logging

These three endpoints are all **read-only GET** requests returning JSON data. The existing codebase does not audit-log read-only queries (no `audit_service` calls exist in the current `routes/templates.py`), and this plan maintains that convention. Application-level request logging (Flask/WSGI access logs) covers these requests. No additional audit logging is required.

## Change Tracking

- [ ] Update import: replace `get_service` with `get_objects_for_request`
- [ ] Update `list_templates()`: use `get_objects_for_request()`
- [ ] Update `get_inheritance()`: use `get_objects_for_request()`, pass `objects` to helper
- [ ] Update `validate_use()`: use `get_objects_for_request()`
- [ ] Update `_decode_and_find_object()`: change signature from `(service, stable_key)` to `(objects, stable_key)`
- [ ] Remove all `service = get_service()` calls (3 occurrences)
- [ ] Run `ruff check routes/templates.py` — must pass
- [ ] Run `ruff format routes/templates.py` — must pass
- [ ] Run `python3 -m pytest tests/ -v` — all tests must pass

## Verification

```bash
# Lint
ruff check routes/templates.py
ruff format --check routes/templates.py

# Unit tests
python3 -m pytest tests/ -v

# Smoke test: endpoints respond correctly without ?candidate=1
python3 -c "
from app import create_app
app = create_app()
client = app.test_client()
r = client.get('/api/templates')
assert r.status_code == 200, f'Expected 200, got {r.status_code}'
print('GET /api/templates: OK')
r = client.get('/api/templates/validate-use?object_type=host&use=generic-host')
assert r.status_code == 200, f'Expected 200, got {r.status_code}'
print('GET /api/templates/validate-use: OK')
"
```

## Playwright

These are backend JSON API endpoints with no UI component. Playwright browser-level tests are not applicable. API-level correctness is validated via the unit tests and smoke test above. The L03-test-candidate-routes.md plan covers candidate-mode API testing.

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | [x] | All three endpoints are read-only GET requests. No writes to live config. `get_objects_for_request()` reads from candidate copy when `?candidate=1`, otherwise reads running config. Neither path mutates anything. |
| 2 | UI visual parity | [x] | No UI changes. Backend JSON API only. Response schema is identical — same JSON keys, same structure. |
| 3 | Full audit logging | [x] | Read-only GET endpoints. Existing codebase convention: read-only queries are not audit-logged. Flask/WSGI access logs provide request-level coverage. No change from current behavior. |
| 4 | Proper error handling | [x] | All error paths preserved: 400 (missing/invalid params), 404 (object not found, no candidate session), propagated from both endpoint code and `get_objects_for_request()` helper. No silent failures. |
| 5 | Dead code deletion | [x] | `get_service` import and all `service = get_service()` calls removed. `service` parameter in `_decode_and_find_object` replaced with `objects`. Removal audit table documents every deletion. |
| 6 | Full functionality migration | [x] | All three endpoints and the private helper fully migrated. Template listing, inheritance chain resolution, and use-validation all work identically with candidate or running objects. |
| 7 | Palo Alto candidate model | [x] | `?candidate=1` reads from candidate copy; without the param, reads running config. Follows copy-edit-apply model. |
| 8 | Change tracking document | [x] | Change Tracking section with tick-off checklist added. |
| 9 | Complete planning before implementation | [x] | This document is the plan. Full code shown for all changes before any implementation begins. |
| 10 | Linting enforcement | [x] | Verification section includes `ruff check` and `ruff format --check`. Change tracking includes lint pass items. |
| 11 | Playwright validation | [x] | Not applicable — backend JSON API endpoints with no UI component. Noted in Playwright section. API correctness covered by unit tests and smoke test. |
