# L03: routes/helpers.py — MODIFY

**Layer:** 3 — App Wiring + Routes
**Action:** MODIFY
**Path:** `routes/helpers.py`
**Dependencies:** L03-app.md (CandidateManager must be registered)
**Goal:** Add candidate helper functions. Keep staging helpers for now (removed in L4).

---

## Changes

### Step 1: Add `get_candidate_manager()` function

Add after the existing `get_staging_manager()` function:

```python
def get_candidate_manager():
    """Get the CandidateManager instance from app extensions."""
    return current_app.extensions["candidate"]
```

### Step 2: Add `get_objects_for_request()` function

Add a helper that returns candidate or running objects based on `?candidate=1` query param:

```python
def get_objects_for_request():
    """Return (objects, is_candidate) based on ?candidate=1 query param.

    When candidate=1 is set but no session exists, aborts with 404.
    Returns NagiosObject instances with source_file normalized to running paths.
    """
    from candidate_manager import CandidateManager
    from nagios_parser import NagiosConfigParser

    candidate_mode = request.args.get("candidate") == "1"
    if not candidate_mode:
        service = get_service()
        return service.get_objects(), False

    cm = get_candidate_manager()
    if not cm.has_session():
        abort(404, description="No candidate session active")

    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    # Normalize source_file paths back to running equivalents
    for obj in parser.objects:
        obj.source_file = cm.to_running_path(obj.source_file)
    return parser.objects, True
```

### Step 3: Add `get_parser_for_request()` function

For endpoints that need the parser itself (not just objects):

```python
def get_parser_for_request():
    """Return (parser, is_candidate) based on ?candidate=1 query param.

    When candidate=1, parser objects have source_file normalized to running paths.
    """
    from candidate_manager import CandidateManager
    from nagios_parser import NagiosConfigParser

    candidate_mode = request.args.get("candidate") == "1"
    if not candidate_mode:
        service = get_service()
        return service.parser, False

    cm = get_candidate_manager()
    if not cm.has_session():
        abort(404, description="No candidate session active")

    parser = NagiosConfigParser(cm.candidate_path)
    parser.parse_all()
    for obj in parser.objects:
        obj.source_file = cm.to_running_path(obj.source_file)
    return parser, True
```

### Step 4: Add `guard_candidate_or_abort()` function

For admin/recovery routes that should be blocked during active candidate session:

```python
def guard_candidate_or_abort():
    """Abort with 409 if a candidate session is active.

    Used on admin/recovery routes (restore backup, git discard, etc.)
    that would corrupt a candidate session.

    Fails CLOSED: if we cannot verify candidate state, rejects the request
    rather than allowing it through. This is safer — an admin operation that
    corrupts a candidate session could cause data loss, while a spurious 500
    only delays the operation until the issue is resolved.
    """
    try:
        cm = get_candidate_manager()
        if cm.has_session():
            abort(409, description="Cannot perform this operation while a candidate session is active. Discard the session first.")
    except (KeyError, RuntimeError):
        abort(500, description="Unable to verify candidate state")
```

**Decision:** `guard_candidate_or_abort()` must fail-CLOSED — if we can't verify candidate state, it's safer to reject the request than to allow it through. An admin operation (backup restore, git discard) that runs while a candidate session is unknowingly active could corrupt the session and cause data loss. A 500 error is recoverable; lost edits are not.

### Step 5: Add necessary imports

Ensure `request` and `abort` are imported from flask (they likely already are):
```python
from flask import current_app, jsonify, request, abort
```

## Change Tracking

- [ ] Add `get_candidate_manager()` helper function
- [ ] Add `get_objects_for_request()` helper with `?candidate=1` support
- [ ] Add `get_parser_for_request()` helper with `?candidate=1` support
- [ ] Add `guard_candidate_or_abort()` helper (fail-CLOSED design)
- [ ] Ensure `request` and `abort` are imported from flask
- [ ] Verify existing staging helpers are untouched (removed in L4)

## Removal Audit

No code removed. `get_staging_manager()` and related staging helpers are kept for now (removed in L4).

## Verification

```bash
python3 -c "
from app import create_app
app = create_app()
with app.test_request_context('/?candidate=1'):
    from routes.helpers import get_candidate_manager
    cm = get_candidate_manager()
    print(f'CandidateManager: {cm}')
    print('OK')
"
python3 -m ruff check routes/helpers.py
python3 -m ruff format --check routes/helpers.py
```

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** `get_objects_for_request()` and `get_parser_for_request()` are read-only helpers that parse candidate config without writing. `guard_candidate_or_abort()` actively prevents admin operations that could corrupt a candidate session.
- [x] **C2 — UI visual parity.** Path normalization in `get_objects_for_request()` and `get_parser_for_request()` ensures the frontend sees running-config paths, maintaining visual consistency with the existing UI.
- [x] **C3 — Full audit logging.** N/A — these are accessor/guard helpers; audit logging is the responsibility of the route endpoints that call them.
- [x] **C4 — Proper error handling.** `get_objects_for_request()` aborts 404 if no session. `guard_candidate_or_abort()` fails CLOSED — aborts 500 if candidate state cannot be verified, preventing data loss from admin operations during unknown state.
- [x] **C5 — Dead code deletion.** No dead code introduced. Existing staging helpers kept intentionally for L4 removal.
- [x] **C6 — Full functionality migration.** Candidate equivalents provided for all needed helper patterns: manager access, object retrieval, parser retrieval, and admin route guarding.
- [x] **C7 — Palo Alto candidate model.** Helpers support the candidate model by providing transparent path translation between candidate and running config paths.
- [x] **C8 — Change tracking.** Tickable checklist added above.
- [x] **C9 — Complete planning before implementation.** All four helper functions fully specified with signatures, docstrings, and implementation details.
- [x] **C10 — Linting enforcement.** Ruff check and format commands included in Verification section.
- [x] **C11 — Playwright validation.** N/A — utility helpers with no UI surface. Covered indirectly by route tests and eventual Playwright tests in later layers.
