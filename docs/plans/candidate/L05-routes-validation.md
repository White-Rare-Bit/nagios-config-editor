# L05: routes/validation.py — MODIFY

**Layer:** 5 — Route Analysis
**Action:** MODIFY
**Path:** `routes/validation.py`
**Dependencies:** L03 (get_objects_for_request, get_parser_for_request must exist)
**Goal:** Make 4 read-only endpoints candidate-aware via `?candidate=1` query param. Keep 4 endpoints unchanged. No mutations to live config.

---

## Endpoint Inventory

All 8 endpoints in `routes/validation.py` and their disposition:

| Endpoint | Method | Action | Reason |
|----------|--------|--------|--------|
| `GET /api/summary` | GET | MODIFY | Add candidate-aware parser via `get_parser_for_request()` |
| `GET /api/health-check` | GET | MODIFY | Add candidate-aware parser via `get_parser_for_request()` |
| `GET /api/analysis/orphans` | GET | MODIFY | Add candidate-aware objects via `get_objects_for_request()` |
| `GET /api/analysis/template-suggestions` | GET | MODIFY | Add candidate-aware objects via `get_objects_for_request()` |
| `POST /api/reload` | POST | KEEP | Reloads running parser from disk; not candidate-related. No live config files mutated (re-parses existing files). |
| `POST /api/validate` | POST | KEEP | Runs `nagios -v` against live config. Not candidate-related (candidate validation is in L03 `POST /api/candidate/validate`). |
| `GET /api/validate/check` | GET | KEEP | Checks Nagios binary availability. Not data-dependent. |
| `GET /api/constants` | GET | KEEP | Returns domain metadata from `nagios_model.py`. Not data-dependent. |

## Changes

### Step 1: Update import

```python
# Before:
from .helpers import get_config, get_service

# After:
from .helpers import get_config, get_service, get_objects_for_request, get_parser_for_request
```

### Step 2: `GET /api/summary` — use candidate-aware parser

Replace `service.get_objects()` and `service.parser` calls with `get_parser_for_request()`:

```python
# Before (lines 26-33):
service = get_service()
p = service.parser
return jsonify({
    "summary": p.get_summary(),
    "files": p.get_files(),
    "total_objects": len(service.get_objects()),
})

# After:
parser, is_candidate = get_parser_for_request()
return jsonify({
    "summary": parser.get_summary(),
    "files": parser.get_files(),
    "total_objects": len(parser.objects),
})
```

No live config mutation. When `?candidate=1` is passed, `get_parser_for_request()` parses the candidate directory (read-only). When absent, returns the running parser. Returns 404 if `?candidate=1` but no session active.

### Step 3: `GET /api/health-check` — use candidate-aware parser

Replace `service.parser` with `get_parser_for_request()`:

```python
# Before (lines 110-112):
service = get_service()
p = service.parser
objects = p.objects

# After:
p, is_candidate = get_parser_for_request()
objects = p.objects
```

The remainder of the function (building `obj_to_index`, `template_lookup`, `config_paths`, calling `run_all_checks`) stays the same. The `config_paths` dict is still populated from `get_server_config()` since health checks need to know about `nagios.cfg` and `resource.cfg` paths regardless of candidate mode.

Error handling: `get_parser_for_request()` aborts with 404 if `?candidate=1` but no session active. The existing `run_all_checks` call can raise exceptions which Flask handles as 500.

### Step 4: `GET /api/analysis/orphans` — use candidate-aware objects

Replace `service.get_objects()` with `get_objects_for_request()`:

```python
# Before (lines 153-154):
service = get_service()
objects = service.get_objects()

# After:
objects, is_candidate = get_objects_for_request()
```

Remove the `service = get_service()` call — no longer needed. The `build_template_lookup(objects)` and `detect_orphans(objects, template_lookup)` calls stay the same.

### Step 5: `GET /api/analysis/template-suggestions` — use candidate-aware objects

Same pattern as orphans:

```python
# Before (lines 175-176):
service = get_service()
objects = service.get_objects()

# After:
objects, is_candidate = get_objects_for_request()
```

Remove the `service = get_service()` call. The `_build_type_signatures` and `_collect_suggestions` helper functions are unchanged — they operate on object lists, not on the service.

### Step 6: No changes to remaining 4 endpoints

- `POST /api/reload` — Reloads running parser from disk files. This is NOT a live config mutation (it re-reads, not writes). No candidate awareness needed since reloading the running parser is always against live config.
- `POST /api/validate` — Runs `nagios -v` against live config binary/cfg path. Candidate validation lives separately in `POST /api/candidate/validate` (L03).
- `GET /api/validate/check` — Static binary check. No data dependency.
- `GET /api/constants` — Returns `nagios_model.py` constants. No data dependency.

## Removal Audit

| Removed Code | Line(s) | Replacement |
|-------------|---------|-------------|
| `service = get_service()` in `api_summary()` | 28 | `parser, is_candidate = get_parser_for_request()` |
| `p = service.parser` in `api_summary()` | 29 | Replaced by `parser` from above |
| `len(service.get_objects())` in `api_summary()` | 32 | `len(parser.objects)` |
| `service = get_service()` in `api_health_check()` | 110 | `p, is_candidate = get_parser_for_request()` |
| `p = service.parser` in `api_health_check()` | 111 | Replaced by `p` from above |
| `service = get_service()` in `api_analysis_orphans()` | 153 | Removed (not needed) |
| `objects = service.get_objects()` in `api_analysis_orphans()` | 154 | `objects, is_candidate = get_objects_for_request()` |
| `service = get_service()` in `api_analysis_template_suggestions()` | 175 | Removed (not needed) |
| `objects = service.get_objects()` in `api_analysis_template_suggestions()` | 176 | `objects, is_candidate = get_objects_for_request()` |

9 lines changed total. No dead code left behind. Import line updated (1 line). Net: pure read-only candidate awareness added.

## Error Handling

All 4 modified endpoints inherit error handling from the helper functions:

| Scenario | Behavior | HTTP Status |
|----------|----------|-------------|
| `?candidate=1` with no active session | `get_parser_for_request()` / `get_objects_for_request()` calls `abort(404)` | 404 |
| `?candidate=1` with active session | Parses candidate directory, normalizes paths | 200 |
| No `?candidate` param (default) | Uses running service parser/objects as before | 200 |
| Candidate parse failure | Exception propagates, Flask returns error | 500 |
| `run_all_checks` failure (health-check) | Exception propagates, Flask returns error | 500 |
| `detect_orphans` failure (orphans) | Exception propagates, Flask returns error | 500 |

No silent failures. No swallowed exceptions.

## Audit Logging

These 4 endpoints are read-only analysis/query endpoints. They do not mutate configuration state so they do not generate audit log entries. This is consistent with the existing system where `GET` endpoints are not audited.

The app-level request logging (Flask's built-in request logging) still captures all requests including these endpoints.

## UI Visual Parity

No UI changes. These are backend API endpoints. The frontend passes `?candidate=1` when in candidate mode (handled by `CandidateApi` in L06). Response shapes are identical — the frontend sees the same JSON structure regardless of candidate mode.

## Change Tracking

- [ ] Update import line to add `get_objects_for_request`, `get_parser_for_request`
- [ ] Modify `GET /api/summary` to use `get_parser_for_request()`
- [ ] Modify `GET /api/health-check` to use `get_parser_for_request()`
- [ ] Modify `GET /api/analysis/orphans` to use `get_objects_for_request()`
- [ ] Modify `GET /api/analysis/template-suggestions` to use `get_objects_for_request()`
- [ ] Verify `POST /api/reload` unchanged and functional
- [ ] Verify `POST /api/validate` unchanged and functional
- [ ] Verify `GET /api/validate/check` unchanged and functional
- [ ] Verify `GET /api/constants` unchanged and functional
- [ ] Run Ruff linter on `routes/validation.py`
- [ ] Run full test suite

## Verification

```bash
# Ruff lint check
python3 -m ruff check routes/validation.py

# Unit tests
python3 -m pytest tests/ -v

# Smoke test: verify endpoints respond correctly without candidate param
python3 -c "
from app import create_app
app = create_app()
client = app.test_client()
for endpoint in ['/api/summary', '/api/health-check', '/api/analysis/orphans', '/api/analysis/template-suggestions']:
    resp = client.get(endpoint)
    assert resp.status_code == 200, f'{endpoint} returned {resp.status_code}'
    print(f'{endpoint}: OK')
print('All endpoints verified')
"
```

## Playwright Validation

Not applicable for this plan. These are backend-only API changes with no UI modifications. The response shape is unchanged so existing frontend behavior is preserved. Playwright tests for the analysis/health-check UI panels (if any) will validate these endpoints indirectly when they run against a candidate session.

## Commandments Compliance

- [x] **C1: No live config mutation until Apply.** All 4 modified endpoints are read-only. When `?candidate=1`, they parse the candidate directory (read-only). No config files are written. `POST /api/reload` re-reads disk (no write). `POST /api/validate` runs nagios binary verification (no write).
- [x] **C2: UI visual parity.** No UI changes. API response shapes are identical in both running and candidate modes.
- [x] **C3: Full audit logging.** These are read-only GET endpoints — no audit entries required (consistent with existing system). App-level request logging still captures all requests.
- [x] **C4: Proper error handling.** All error paths documented: 404 for missing candidate session, 500 for parse/check failures. No silent failures or swallowed exceptions.
- [x] **C5: Dead code deletion.** 9 lines of `service = get_service()` / `service.get_objects()` / `service.parser` calls replaced. No dead code left behind.
- [x] **C6: Full functionality migration.** All 8 endpoints accounted for (4 modified, 4 kept unchanged). No functionality dropped.
- [x] **C7: Palo Alto candidate model.** Read-only endpoints use `?candidate=1` query param to switch between running config and candidate config. Candidate config is a copy of running config edited in isolation.
- [x] **C8: Change tracking document.** Change tracking checklist included with all items enumerated.
- [x] **C9: Complete planning before implementation.** All endpoints inventoried, all changes specified with before/after code, removal audit complete.
- [x] **C10: Linting enforcement.** Ruff lint check included in verification steps.
- [x] **C11: Playwright validation.** Assessed and determined not applicable — backend-only API changes with no UI modifications. Documented reasoning.
