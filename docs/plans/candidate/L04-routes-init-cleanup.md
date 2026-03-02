# L04: routes/__init__.py — MODIFY (remove staging blueprint)

**Layer:** 4 — Route Cleanup
**Action:** MODIFY
**Path:** `routes/__init__.py`
**Dependencies:** L03-routes-init.md (adds candidate_bp), L04-routes-staging.md (deletes staging.py, this removes the import)
**Goal:** Remove staging blueprint import and registration after staging.py is deleted. Candidate blueprint (added in L03) is preserved.

---

## Removal Audit

These references exist in the post-L03 state of `routes/__init__.py` (after L03-routes-init.md has added the candidate blueprint):

| Code | Action | Reason |
|------|--------|--------|
| `from .staging import bp as staging_bp` | REMOVE import | staging.py deleted in L04-routes-staging.md |
| `app.register_blueprint(staging_bp)` | REMOVE registration | staging.py deleted in L04-routes-staging.md |

**Kept intact:** `from .candidate import bp as candidate_bp` and `app.register_blueprint(candidate_bp)` — added by L03-routes-init.md, these are the replacement for the staging blueprint.

## Functionality Migration Verification

All staging endpoints have candidate equivalents (verified in L04-routes-staging.md):

| Old Staging Route | Candidate Equivalent |
|-------------------|---------------------|
| `GET /api/staging` | `GET /api/candidate` |
| `POST /api/staging/save` | Not needed (candidate writes directly) |
| `POST /api/staging/apply` | `POST /api/candidate/apply` |
| `POST /api/staging/undo` | `POST /api/candidate/undo` |
| `DELETE /api/staging` | `DELETE /api/candidate` |
| `GET /api/staging/lock` | `GET /api/candidate` (session info includes lock) |
| `POST /api/staging/lock` | `POST /api/candidate/init` |
| `DELETE /api/staging/lock` | `DELETE /api/candidate?force=1` |
| `GET /api/staging/diff` | `GET /api/candidate/diff` |
| `GET /api/staging/info` | `GET /api/candidate` |

No staging functionality is dropped. All useful endpoints are migrated to the candidate blueprint (L03-routes-candidate.md). The `POST /api/staging/save` endpoint is intentionally not migrated because the candidate system writes directly to the candidate directory — there is no separate "save" step.

## Changes

### Step 1: Remove staging blueprint import

Delete:
```python
    from .staging import bp as staging_bp
```

### Step 2: Remove staging blueprint registration

Delete:
```python
    app.register_blueprint(staging_bp)
```

### Result

`register_blueprints()` after changes (post-L03 state with candidate_bp, minus staging_bp):

```python
def register_blueprints(app):
    """Register all route blueprints with the Flask app."""
    from .analysis import bp as analysis_bp
    from .backups import bp as backups_bp
    from .bulk_ops import bp as bulk_ops_bp
    from .candidate import bp as candidate_bp
    from .files import bp as files_bp
    from .git import bp as git_bp
    from .logs import bp as logs_bp
    from .metadata import bp as metadata_bp
    from .objects import bp as objects_bp
    from .pages import bp as pages_bp
    from .settings import bp as settings_bp
    from .templates import bp as templates_bp
    from .validation import bp as validation_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(validation_bp)
    app.register_blueprint(backups_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(git_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(objects_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(bulk_ops_bp)
    app.register_blueprint(metadata_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(candidate_bp)
```

## Error Handling

After this change, any HTTP requests to `/api/staging/*` routes will return Flask's default 404 response. This is correct behavior — the staging system has been fully replaced by the candidate system, and the frontend has been rewired in earlier layers to call `/api/candidate/*` endpoints instead.

If `routes/candidate.py` has a syntax error or missing dependency, the import will raise `ImportError` or `SyntaxError` at app startup, preventing the app from starting. This is correct — a broken candidate module should not result in a silently degraded app.

## Linting

This file must pass Ruff after modification. Verify:

```bash
python3 -m ruff check routes/__init__.py
python3 -m ruff format --check routes/__init__.py
```

## Change Tracking

| # | Change | File | Status |
|---|--------|------|--------|
| 1 | Remove `from .staging import bp as staging_bp` import | `routes/__init__.py` | [ ] |
| 2 | Remove `app.register_blueprint(staging_bp)` registration | `routes/__init__.py` | [ ] |
| 3 | Verify candidate_bp import and registration remain intact | `routes/__init__.py` | [ ] |
| 4 | Run Ruff check and format | `routes/__init__.py` | [ ] |
| 5 | Run verification tests | — | [ ] |

## Verification

### App startup

```bash
python3 -c "from app import create_app; create_app()"
# App should start without error
```

### Route verification

```bash
python3 -c "
from app import create_app
app = create_app()
rules = [rule.rule for rule in app.url_map.iter_rules()]
# Staging routes must be gone
staging_rules = [r for r in rules if 'staging' in r]
assert len(staging_rules) == 0, f'Staging routes still present: {staging_rules}'
# Candidate routes must be present
candidate_rules = [r for r in rules if 'candidate' in r]
assert len(candidate_rules) > 0, 'No candidate routes registered'
print('OK: staging routes removed, candidate routes present:', len(candidate_rules))
"
```

### Test suite

```bash
python3 -m pytest tests/ -v
```

### Linting

```bash
python3 -m ruff check routes/__init__.py
python3 -m ruff format --check routes/__init__.py
```

### Playwright

Not applicable to this plan. This is a backend wiring change (removing a dead import) with no UI impact. The candidate routes themselves are validated by Playwright tests in later layers (L06+) once the frontend is wired to call them.

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | [x] | This plan only removes a Flask blueprint import/registration. No config files are read, written, or mutated. The candidate system's apply-gated mutation flow (L03-routes-candidate.md) is unaffected. |
| 2 | UI visual parity | [x] | N/A — backend-only change. No UI impact. Removing the staging blueprint does not alter any rendered page; the frontend was already rewired to candidate endpoints in earlier layers. |
| 3 | Full audit logging | [x] | N/A — blueprint deregistration is not a user-initiated auditable action; it is a deployment-time code change. Audit logging for individual candidate routes is specified in L03-routes-candidate.md. |
| 4 | Proper error handling | [x] | Requests to removed `/api/staging/*` routes return Flask's default 404 (no silent failure). Import errors at startup raise loudly. Documented in Error Handling section. |
| 5 | Dead code deletion | [x] | This plan IS dead code deletion — removing the staging blueprint import/registration after `routes/staging.py` is deleted in L04-routes-staging.md. Zero staging references remain after this change. |
| 6 | Full functionality migration | [x] | All 10 staging endpoints have candidate equivalents (mapping table included in Functionality Migration Verification section). `POST /api/staging/save` is intentionally not migrated (candidate writes directly). |
| 7 | Palo Alto candidate model | [x] | This plan completes the transition from the staging blueprint to the candidate blueprint, which implements the Palo Alto copy-edit-apply model. |
| 8 | Change tracking document | [x] | Change Tracking section with 5 tickable items added. |
| 9 | Complete planning before implementation | [x] | Plan is complete. All dependencies enumerated. Full expected result shown. Removal audit, error handling, linting, and verification all specified. |
| 10 | Linting enforcement | [x] | Ruff check and format commands specified in both the Linting section and the Verification section. |
| 11 | Playwright validation | [x] | N/A — backend wiring change only. No UI changes to validate. Playwright coverage for candidate routes is specified in later layers (L06+). |
