# L12 — `tests/test_health_check.py` — MODIFY

**Layer:** 12 — Dead Code Cleanup
**Action:** MODIFY
**Path:** `tests/test_health_check.py`
**Dependencies:** L02-git-service.md (replaces `.staging/` with `.candidate/` in gitignore), L04-routes-staging.md (deletes `routes/staging.py` and all staging API endpoints)
**Goal:** Delete staging-specific tests that depend on staging API routes or reference the now-removed `.staging/` directory convention. Keep all non-staging health check tests unchanged.

---

## Purpose

Delete 2 staging-specific test functions whose dependencies no longer exist after earlier layers:

1. `test_gitignore_references_correct_staging_dir` (line 136) — Asserts `.staging/` appears in auto-generated `.gitignore`. After L02-git-service.md, `.staging/` is replaced by `.candidate/` in `git_service.py`. A duplicate test in `tests/test_git_service.py` is already updated by L02-test-git-service.md to assert `.candidate/`. This test is redundant dead code.

2. `test_apply_staging_with_validate_flag` (line 639) — Calls `POST /api/staging` and `POST /api/staging/apply`, both of which are deleted in L04-routes-staging.md. The test exercises the old staging apply workflow (stage an edit via dict-format `POST /api/staging`, then apply via `POST /api/staging/apply`). In the candidate model, the equivalent flow is: create candidate via `POST /api/candidate`, edit via CandidateApi, apply via `POST /api/candidate/apply` — tested in `tests/test_candidate_routes.py` (L03).

---

## Removal Audit

| Line | Test Function | Staging Dependency | Why Dead | Replacement Coverage |
|------|---------------|-------------------|----------|---------------------|
| 136 | `test_gitignore_references_correct_staging_dir` | Asserts `.staging/` in `.gitignore` | L02-git-service.md replaces `.staging/` with `.candidate/` | `tests/test_git_service.py` (updated in L02-test-git-service.md to assert `.candidate/`) |
| 639 | `test_apply_staging_with_validate_flag` | Calls `POST /api/staging` and `POST /api/staging/apply` | L04-routes-staging.md deletes both endpoints | `tests/test_candidate_routes.py` (L03) tests candidate apply with validation |

**Kept tests (not modified):** All other tests in the file (health check issue detection, required fields, atomic writes, duplicate detection, unused object detection, template conflicts, etc.) are staging-independent — they call `GET /api/health-check` and `GET /api/objects`, both of which remain and become candidate-aware via `?candidate=1` in L05-routes-validation.md. No changes needed for these tests because they test the live-config health check path, which continues to work.

---

## Changes

### Step 1: Delete `test_gitignore_references_correct_staging_dir` (lines 136-149)

Delete the entire function:
```python
# DELETE lines 136-149
def test_gitignore_references_correct_staging_dir():
    """Generated .gitignore should reference .staging/ not .nagios_staging/."""
    test_dir = tempfile.mkdtemp()
    try:
        gs = GitService(test_dir)
        gs.init_repo()
        gitignore_path = os.path.join(test_dir, ".gitignore")
        assert os.path.exists(gitignore_path), ".gitignore should be created"
        content = Path(gitignore_path).read_text()
        assert ".staging/" in content, f".gitignore should contain '.staging/', got:\n{content}"
        assert ".nagios_staging/" not in content, \
            f".gitignore should NOT contain '.nagios_staging/', got:\n{content}"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
```

After deletion, check whether `GitService` import (line 13) is still used by other tests. If not, remove the import as well. Grep: `grep -n 'GitService' tests/test_health_check.py` — if only the deleted test uses it, remove `from git_service import GitService`.

### Step 2: Delete `test_apply_staging_with_validate_flag` (lines 639-700)

Delete the entire function:
```python
# DELETE lines 639-700
def test_apply_staging_with_validate_flag():
    """Apply staging should include validation result when validate=true."""
    ...
```

After deletion, check whether the `json` import (line 3) is still used by other tests. If not, remove it. Grep: `grep -n 'json\.' tests/test_health_check.py` — if only the deleted test uses `json.dumps`, remove `import json`.

### Step 3: Verify unused imports

After both deletions, verify no orphaned imports remain:
```bash
grep -n 'import json' tests/test_health_check.py
grep -n 'GitService' tests/test_health_check.py
```

Remove any imports that are now unused (Commandment 5: dead code deletion).

---

## Error Handling

Not applicable — this change deletes test code, it does not introduce any new code paths. No new error handling is needed. Remaining tests continue to exercise proper error handling in the health check endpoint (e.g., testing 200 status codes, validating response structure).

---

## Audit Logging

Not applicable — this is a test file modification. No production code paths are affected. The health check endpoint's audit logging (via the application logging system) is unchanged.

---

## Linting

After modifications, verify the file passes Ruff:
```bash
python3 -m ruff check tests/test_health_check.py
python3 -m ruff format --check tests/test_health_check.py
```

---

## Verification

```bash
# All remaining tests pass
python3 -m pytest tests/test_health_check.py -v

# No staging API references remain in this file
grep -n 'api/staging' tests/test_health_check.py
# Expected: no matches

# No .staging/ directory references remain (except possibly in string literals for other purposes)
grep -n '\.staging/' tests/test_health_check.py
# Expected: no matches

# No unused imports
python3 -m ruff check tests/test_health_check.py --select F401

# Full test suite still passes
python3 -m pytest tests/ -v
```

---

## Playwright Validation

Not applicable — this plan modifies a Python unit test file. There are no UI changes, no visual differences, and no frontend behavior changes. The health check endpoint behavior is unchanged; only dead test code is removed.

---

## Change Tracking

| # | Change | File | Line(s) | Status |
|---|--------|------|---------|--------|
| 1 | Delete `test_gitignore_references_correct_staging_dir` function | `tests/test_health_check.py` | 136-149 | [ ] |
| 2 | Delete `test_apply_staging_with_validate_flag` function | `tests/test_health_check.py` | 639-700 | [ ] |
| 3 | Remove `from git_service import GitService` if unused | `tests/test_health_check.py` | 13 | [ ] |
| 4 | Remove `import json` if unused | `tests/test_health_check.py` | 3 | [ ] |
| 5 | Verify Ruff passes | `tests/test_health_check.py` | — | [ ] |
| 6 | Verify all remaining tests pass | `tests/test_health_check.py` | — | [ ] |
| 7 | Verify no `api/staging` references remain | `tests/test_health_check.py` | — | [ ] |

---

## Commandments Compliance

| # | Commandment | Status | Rationale |
|---|-------------|--------|-----------|
| 1 | No live config mutation until Apply | COMPLIANT | No new code introduced. Deleted test (`test_apply_staging_with_validate_flag`) called the old staging mutation APIs which are themselves deleted in L04. Remaining tests only call read-only endpoints (`GET /api/health-check`, `GET /api/objects`). |
| 2 | UI visual parity | N/A | Test-only change. No UI modifications. |
| 3 | Full audit logging | N/A | Test-only change. No production code affected. The health check endpoint's application logging is unchanged. |
| 4 | Proper error handling | COMPLIANT | No new code introduced. Remaining tests continue to validate proper HTTP status codes and response structure from the health check endpoint. |
| 5 | Dead code deletion | COMPLIANT | Both deleted tests are dead code: `test_gitignore_references_correct_staging_dir` asserts `.staging/` which no longer exists after L02-git-service.md (duplicate coverage in `test_git_service.py`). `test_apply_staging_with_validate_flag` calls `POST /api/staging` and `POST /api/staging/apply`, both deleted in L04. Orphaned imports (`json`, `GitService`) are also removed if unused. |
| 6 | Full functionality migration | COMPLIANT | Both tests have replacement coverage. Gitignore assertion: `tests/test_git_service.py` updated in L02-test-git-service.md. Staging apply with validation: `tests/test_candidate_routes.py` created in L03 tests candidate apply. No test coverage is dropped. |
| 7 | Palo Alto candidate model | COMPLIANT | Removes tests for the old staging model. The candidate model equivalent (copy config to candidate, edit candidate, apply to live) is tested in `tests/test_candidate_routes.py` and `tests/test_candidate_manager.py`. |
| 8 | Change tracking document | COMPLIANT | Change tracking table with 7 items provided above, each with checkable status. |
| 9 | Complete planning before implementation | COMPLIANT | Plan specifies exact line numbers, exact functions to delete, exact verification commands, and exact post-deletion cleanup steps. No ambiguity remains. |
| 10 | Linting enforcement | COMPLIANT | Ruff check and format verification commands specified. Unused import detection via `--select F401` included. |
| 11 | Playwright validation | N/A | No UI changes. This is a backend test file modification with zero visual or behavioral impact on the frontend. |
