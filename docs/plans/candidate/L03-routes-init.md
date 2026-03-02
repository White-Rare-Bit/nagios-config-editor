# L03: routes/__init__.py — MODIFY

**Layer:** 3 — App Wiring + Routes
**Action:** MODIFY
**Path:** `routes/__init__.py`
**Dependencies:** L03-routes-candidate.md (candidate.py must exist and define `bp`)
**Goal:** Register the candidate blueprint. Keep staging blueprint for now (removed in L04-routes-init-cleanup.md).

---

## Changes

### Step 1: Import candidate blueprint

Add import alongside existing blueprint imports (after line 17, the staging import):
```python
from .candidate import bp as candidate_bp
```

### Step 2: Register candidate blueprint

Add registration alongside existing blueprint registrations (after the logs_bp registration, line 32):
```python
app.register_blueprint(candidate_bp)
```

### Result

`register_blueprints()` after changes:

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
    from .staging import bp as staging_bp
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
    app.register_blueprint(staging_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(bulk_ops_bp)
    app.register_blueprint(metadata_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(candidate_bp)
```

### Error Handling

If `routes/candidate.py` does not exist or has a syntax error, the import will raise `ImportError` or `SyntaxError` at app startup, preventing the app from starting. This is the correct behavior — a broken candidate module should not result in a silently degraded app. The traceback will clearly indicate the missing dependency.

## Removal Audit

No code removed. Staging blueprint registration is kept for now. Removal is handled explicitly by L04-routes-init-cleanup.md, which deletes the `staging_bp` import and registration after `routes/staging.py` is deleted.

## Linting

This file must pass Ruff after modification. The new import line follows alphabetical ordering within the existing import block. Verify:

```bash
python3 -m ruff check routes/__init__.py
python3 -m ruff format --check routes/__init__.py
```

## Change Tracking

| # | Change | File | Line(s) | Status |
|---|--------|------|---------|--------|
| 1 | Add `from .candidate import bp as candidate_bp` | `routes/__init__.py` | after L17 | [ ] |
| 2 | Add `app.register_blueprint(candidate_bp)` | `routes/__init__.py` | after L32 | [ ] |

## Verification

### Unit verification (import check)

```bash
python3 -c "
from app import create_app
app = create_app()
rules = [rule.rule for rule in app.url_map.iter_rules()]
candidate_rules = [r for r in rules if 'candidate' in r]
assert len(candidate_rules) > 0, 'No candidate routes registered'
print('Candidate routes registered:', candidate_rules[:5])
# Also verify staging routes are still present (not prematurely removed)
staging_rules = [r for r in rules if 'staging' in r]
assert len(staging_rules) > 0, 'Staging routes missing (should still be present in L03)'
print('Staging routes still present:', staging_rules[:5])
"
```

### Test suite

```bash
python3 -m pytest tests/ -v
python3 -m pytest tests/test_candidate_routes.py -v
```

### Playwright

Not applicable to this plan. This is a backend wiring change with no UI impact. The candidate routes themselves are validated by Playwright tests in later layers (L06+) once the frontend is wired to call them.

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | This plan only registers a Flask blueprint. No config files are read, written, or mutated. All candidate mutations are gated behind the candidate session + apply flow defined in L03-routes-candidate.md. |
| 2 | UI visual parity | N/A | Backend-only change. No UI impact. |
| 3 | Full audit logging | N/A | Blueprint registration is not an auditable user action. Audit logging for individual candidate routes is specified in L03-routes-candidate.md. |
| 4 | Proper error handling | COMPLIANT | Import errors fail the app startup loudly (no silent degradation). Documented in Error Handling section above. |
| 5 | Dead code deletion | COMPLIANT | No dead code introduced. Staging blueprint is intentionally kept (still in use). Its removal is tracked in L04-routes-init-cleanup.md. |
| 6 | Full functionality migration | COMPLIANT | Candidate blueprint is added alongside staging. No functionality dropped. Staging removal is deferred to L04. |
| 7 | Palo Alto candidate model | COMPLIANT | This plan wires the candidate blueprint that implements the Palo Alto copy-edit-apply model. The blueprint itself (L03-routes-candidate.md) defines the candidate lifecycle routes. |
| 8 | Change tracking document | COMPLIANT | Change Tracking section added with tickable checklist. |
| 9 | Complete planning before implementation | COMPLIANT | This plan is complete. Dependencies (L03-routes-candidate.md) are enumerated. Full expected result shown. |
| 10 | Linting enforcement | COMPLIANT | Ruff check/format commands specified in Linting section. Import follows alphabetical ordering. |
| 11 | Playwright validation | N/A | No UI changes. Backend wiring only. Playwright coverage for candidate routes is specified in later layers (L06+). |
