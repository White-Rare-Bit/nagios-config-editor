# L12: apply_verification.py — DELETE

**Layer:** 12 — Staging Removal
**Action:** DELETE
**Path:** `apply_verification.py`
**Dependencies:** L01 (CandidateManager provides continuous verification), L04-routes-staging.md (routes/staging.py deleted, removing the sole import)
**Goal:** Delete post-apply verification module. All functionality replaced by CandidateManager's continuous per-operation parse verification (L01).

---

## Context

`apply_verification.py` (376 lines) provides post-apply verification for the delta-based staging system. It checks that disk changes match staging intent after `POST /api/staging/apply` executes. The candidate system (L01) eliminates the need for post-apply verification by validating each mutation immediately — every object operation re-parses the candidate directory and auto-reverts via `git checkout -- .` on parse failure. See L01-candidate-manager.md "Verification Model: Continuous vs Post-Apply" for the full rationale.

## Removal Audit

| Function | Lines | Replacement |
|----------|-------|-------------|
| `build_expected_changeset()` | 18-92 | Not needed. CandidateManager verifies each write via re-parse; apply is a simple file copy of already-validated files. |
| `compare_file_changes()` | 95-150 | Not needed. No delta/phase system that could apply wrong changes. Git diff in candidate provides change tracking (`CandidateManager.get_diff()`). |
| `_find_object()` | 153-175 | Not needed. Post-mutation parse check in CandidateManager confirms object identity after each operation. |
| `verify_objects()` | 178-326 | Not needed. CandidateManager re-parses after each edit, catching corruption immediately rather than at apply time. |
| `verify_apply_integrity()` | 329-376 | Not needed. Top-level orchestrator for the two-layer check. Both layers are superseded by continuous validation. |

### Import References (must be zero before deletion)

| File | Line | Reference | Handled By |
|------|------|-----------|------------|
| `routes/staging.py` | 12 | `from apply_verification import verify_apply_integrity` | L04-routes-staging.md (entire file deleted) |
| `tests/test_apply_verification.py` | 3 | `from apply_verification import (build_expected_changeset, ...)` | L12-test-deletions.md (test file deleted) |

### Functionality Migration Checklist

| Guarantee | Old System | New System | Status |
|-----------|-----------|------------|--------|
| Every mutation produces parseable config | Post-apply `verify_objects()` catches after the fact | Per-operation parse verification with auto-revert (L01 step 5) | Migrated (better: immediate feedback) |
| Object identity maintained after changes | Post-apply re-parse and attribute check | Per-operation parse check confirms all objects discoverable | Migrated (better: immediate feedback) |
| File-level git diff verification | `compare_file_changes()` at apply time | Not replicated — candidate apply is `shutil.copy2` of known files, no delta phases | Intentionally dropped (no value in candidate model) |
| Post-apply running config re-parse | `verify_apply_integrity()` re-parses after apply | Not replicated — candidate was validated operation-by-operation | Intentionally dropped (redundant) |

## Changes

Delete entire file: `apply_verification.py`

## Audit Logging

No audit logging changes needed. The file being deleted is a pure utility module with no audit log calls. Audit logging for apply operations is handled by `routes/candidate.py` (L03-routes-candidate.md).

## Error Handling

No error handling changes needed. The deletion removes error handling code that is no longer reachable. The replacement error handling (per-operation parse verification with auto-revert) is defined in L01-candidate-manager.md.

## Verification

```bash
# Confirm file is deleted
test ! -f apply_verification.py && echo "DELETED" || echo "STILL EXISTS"

# No import references remain in source files
grep -r "from apply_verification\|import apply_verification" *.py routes/ tests/ && echo "FAIL: references found" || echo "OK: no references"

# All tests pass with no import errors
python3 -m pytest tests/ -v

# Lint check on any files that were modified (none expected for this plan)
ruff check .
```

## Playwright Validation

No Playwright tests needed for this plan. This is a backend-only module deletion with no UI impact (Commandment 2: UI visual parity is unaffected). The CandidateManager's continuous verification is tested by `tests/test_candidate_manager.py` (L01).

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Module being deleted is part of the old staging system. Replacement (CandidateManager) edits only the `.candidate/` directory; live config untouched until Apply. |
| 2 | UI visual parity | COMPLIANT | No UI changes. This is a backend utility module with no frontend impact. |
| 3 | Full audit logging | COMPLIANT | Module has no audit log calls. Apply audit logging is handled by L03-routes-candidate.md. |
| 4 | Proper error handling | COMPLIANT | Replacement error handling (per-operation parse verification with auto-revert on corruption) is defined in L01, step 5 of the operation pattern. No silent failures. |
| 5 | Dead code deletion | COMPLIANT | This plan IS the dead code deletion — the entire 376-line module is removed because it has zero use in the candidate system. |
| 6 | Full functionality migration | COMPLIANT | All four guarantees audited above. Two migrated (improved), two intentionally dropped with documented rationale (no value in candidate model). |
| 7 | Palo Alto candidate model | COMPLIANT | Candidate model validates at edit time (edit the copy), not at apply time (copy back to live). Post-apply verification is architecturally unnecessary. |
| 8 | Change tracking document | COMPLIANT | This file is tracked in L00-migration-inventory.md (Section 1.1, row 2) with status [covered]. |
| 9 | Complete planning before implementation | COMPLIANT | Full removal audit with function-by-function analysis, import reference tracking, and functionality migration checklist completed before any deletion. |
| 10 | Linting enforcement | COMPLIANT | Verification section includes `ruff check .` to confirm no lint regressions. |
| 11 | Playwright validation | COMPLIANT | Not applicable — no UI changes. Documented in Playwright Validation section with rationale. |
