# L12 — Test File Deletions — DELETE

**Layer:** 12 — Dead Code Removal
**Action:** DELETE
**Paths:** 5 test files (see below)
**Dependencies:** L01-candidate-manager.md, L01-test-candidate-manager.md, L03-test-candidate-routes.md, L12-staging-manager.md, L12-apply-verification.md, L12-nagios-service.md must all be implemented first
**Goal:** Remove test files that exercise deleted staging/apply code, after verifying equivalent coverage exists in the new candidate test suites

---

## Purpose

Delete 5 test files whose code under test is being removed by other L12 plans (staging_manager.py, apply_verification.py, and the staging/apply methods in nagios_service.py). These tests cannot pass once their dependencies are deleted, and their coverage has been migrated to the candidate test suites.

## Files to Delete

| File | Tests | Lines | Exercises |
|------|-------|-------|-----------|
| `tests/test_staging_integration.py` | 8 tests | 661 | Staging round-trip workflows via Flask test client (`POST /api/staging`, `POST /api/staging/apply`, undo, conflict detection, bulk ops, analyze-references) |
| `tests/test_composite_apply.py` | 17 tests | 558 | `_build_composite_actions` merge logic and `apply_object_composite` execution on `NagiosService` |
| `tests/test_apply_verification.py` | 28 tests | 440 | All 4 public functions of `apply_verification.py`: `build_expected_changeset`, `compare_file_changes`, `verify_objects`, `verify_apply_integrity` |
| `tests/test_apply_robustness.py` | 8 tests | 428 | Edge cases: multi-file delete with stale indices (3 xfail), apply retry idempotency (3 tests), composite error isolation (2 tests) |
| `tests/test_reorder.py` | 1 test | 297 | Object reorder via `StagingManager` + `apply_object_composite`, run as script (`if __name__ == "__main__"`) |

**Total: 62 tests, ~2,384 lines deleted.**

## Removal Audit — Coverage Migration Map

Every category of test coverage in the deleted files has an equivalent in the new candidate test suites. The mapping below proves no coverage is lost.

### 1. `test_staging_integration.py` (8 tests)

| Deleted Test | Coverage Area | Replacement Test (L01/L03) |
|-------------|---------------|---------------------------|
| `test_staging_round_trip_dict_format` | Edit round-trip: stage, verify, apply, read back | `TestObjectOperations::test_edit_object` (L01) + `TestCandidateEditRoutes::test_edit_accepts_running_path` (L03) |
| `test_reject_old_list_format` | Input validation (list format rejection) | Not needed -- candidate API uses individual operation endpoints, not a bulk staging dict |
| `test_undo_operations_dict_format` | Undo after edit | `TestUndo::test_undo_reverts_edit` (L01) + `TestCandidateUndoRoute::test_undo_after_edit` (L03) |
| `test_multi_operation_workflow` | Create + edit in single apply | `TestDiffAndApply::test_apply_copies_to_running` (L01) -- candidate applies all accumulated ops at once |
| `test_conflict_detection` | External file change detection | `TestDiffAndApply::test_detect_conflicts_after_external_change` (L01) + `TestCandidateConflictsRoute` (L03) |
| `TestBulkOpsUseStagingSystem::test_bulk_rename_does_not_write_to_disk_without_apply` | Commandment 1: no live mutation before Apply | `TestLiveConfigImmutability::test_edit_does_not_touch_running` (L01) |
| `TestBulkOpsUseStagingSystem::test_bulk_rename_api_stages_changes` | Bulk rename stages, not writes | `TestBulkOperations::test_bulk_edit` (L01) + `TestCandidateBulkRoutes::test_bulk_edit` (L03) |
| `TestBulkOpsUseStagingSystem::test_bulk_move_api_stages_changes` | Bulk move stages, not writes | `TestBulkOperations::test_bulk_move` (L01) + `TestCandidateBulkRoutes::test_bulk_move` (L03) |
| `TestAnalyzeReferences::test_analyze_references_finds_all_direct_refs` | Reference analysis with comma-separated values | `TestReferenceAnalysis::test_analyze_references_detects_name_change` (L01) |
| `TestAnalyzeReferences::test_analyze_references_returns_diff_data` | Reference diff data structure | `TestReferenceAnalysis::test_analyze_references_detects_name_change` (L01) |
| `test_apply_includes_verification` | Post-apply verification report | Not needed -- CandidateManager uses per-operation parse-check verification (L01 `TestParserCorruptionGuard`), not post-apply batch verification |
| `test_apply_verification_multi_operation` | Multi-op verification report | Same as above -- continuous validation replaces batch verification |

### 2. `test_composite_apply.py` (17 tests)

| Deleted Test | Coverage Area | Replacement Test (L01) |
|-------------|---------------|----------------------|
| `TestBuildCompositeActions::test_edit_only` | Single edit action build | Not needed -- candidate does not batch actions; each operation is immediate |
| `TestBuildCompositeActions::test_move_only` | Single move action build | Same -- no composite action concept in candidate |
| `TestBuildCompositeActions::test_delete_only` | Single delete action build | Same |
| `TestBuildCompositeActions::test_create_only` | Single create action build | Same |
| `TestBuildCompositeActions::test_edit_plus_move_merges_to_move_edit` | Edit+move merge to move_edit | Not needed -- candidate executes move and edit as separate git commits; no merge needed |
| `TestBuildCompositeActions::test_delete_wins_over_edit` | Delete priority over edit | Not needed -- candidate executes operations individually; no conflict resolution needed |
| `TestBuildCompositeActions::test_delete_wins_over_move` | Delete priority over move | Same |
| `TestBuildCompositeActions::test_deletes_sorted_reverse_line_order` | Reverse sort for index safety | Not needed -- candidate uses git reset for undo, not index-based operations |
| `TestBuildCompositeActions::test_multiple_independent_ops` | Multi-op action build | Same |
| `TestApplyObjectComposite::test_edit_changes_attribute` | Edit execution | `TestObjectOperations::test_edit_object` (L01) |
| `TestApplyObjectComposite::test_move_relocates_object` | Move execution | `TestObjectOperations::test_move_object` (L01) |
| `TestApplyObjectComposite::test_delete_removes_object` | Delete execution | `TestObjectOperations::test_delete_object` (L01) |
| `TestApplyObjectComposite::test_create_adds_object` | Create execution | `TestObjectOperations::test_create_object` (L01) |
| `TestApplyObjectComposite::test_move_edit_no_duplicate` | Move+edit no duplicates | Not needed -- candidate does not have move_edit composite action |
| `TestApplyObjectComposite::test_multiple_independent_ops` | Multi-op execution | `TestObjectOperations::test_multi_file_delete_correct_objects` (L01) |
| `TestApplyObjectComposite::test_empty_staging_is_noop` | Empty apply no-op | `TestDiffAndApply::test_get_diff_empty_when_no_changes` (L01) |
| `TestApplyObjectComposite::test_details_include_action_type` | Audit trail in results | `TestAuditLogging::test_edit_logs_audit` (L01) |

### 3. `test_apply_verification.py` (28 tests)

All 28 tests exercise `apply_verification.py` which is being deleted in L12-apply-verification.md. The entire post-apply verification model is replaced by CandidateManager's per-operation verification:

| Old Model | New Model (L01) |
|-----------|----------------|
| `build_expected_changeset` -- predict which files will change | Not needed -- candidate tracks changes via git diff |
| `compare_file_changes` -- compare git status before/after apply | Not needed -- `CandidateManager.get_diff()` uses git diff directly |
| `verify_objects` -- verify parsed objects match staging intent | Replaced by per-op re-parse: `TestParserCorruptionGuard::test_edit_reverts_on_corrupt_output` |
| `verify_apply_integrity` -- orchestrate file+object verification | Apply is a simple file copy; integrity comes from per-op validation during editing |

### 4. `test_apply_robustness.py` (8 tests)

| Deleted Test | Coverage Area | Replacement |
|-------------|---------------|-------------|
| `TestMultiFileDeleteStaleIndices::test_delete_from_two_files_correct_objects` (xfail) | Stale global_index bug across files | Bug does not exist in candidate -- each delete is a separate operation with re-parse between ops; `TestObjectOperations::test_multi_file_delete_correct_objects` (L01) |
| `TestMultiFileDeleteStaleIndices::test_delete_from_three_files` (xfail) | Same bug, three files | Same -- architecture prevents this class of bug |
| `TestMultiFileDeleteStaleIndices::test_delete_within_single_file_correct` | Baseline single-file delete | `TestObjectOperations::test_delete_object` (L01) |
| `TestApplyRetryDuplicates::test_create_replay_does_not_duplicate` (xfail) | Idempotency on retry | Not needed -- candidate does not retry; each operation is committed to git immediately |
| `TestApplyRetryDuplicates::test_move_replay_fails_gracefully` | Move retry graceful failure | Same -- no retry model in candidate |
| `TestApplyRetryDuplicates::test_delete_replay_does_not_delete_wrong_object` (xfail) | Delete retry safety | Same |
| `TestCompositeErrorIsolation::test_out_of_range_delete_silently_skipped` | Invalid index handling | `TestPathSafety` (L01) covers input validation; out-of-range indices return OperationResult(success=False) |
| `TestCompositeErrorIsolation::test_cross_file_delete_doesnt_corrupt_subsequent_edit` | Cross-file operation safety | Not needed -- candidate processes operations individually, not as a batch |

**Note on xfail tests:** Three xfail tests document known bugs in the old staging system's batch apply model (stale global indices, duplicate creation on retry). These bugs are architecturally eliminated in the candidate model because operations execute individually with re-parse between each one.

### 5. `test_reorder.py` (1 test, run as script)

| Deleted Test | Coverage Area | Replacement |
|-------------|---------------|-------------|
| `run_test()` | Object reorder via staged moves + apply_object_composite | Reorder in candidate is a sequence of individual move operations; `TestObjectOperations::test_move_object` (L01) + `TestBulkOperations::test_bulk_move` (L01) |

**Note:** This file imports `StagingManager` directly (line 23) and would fail to import once `staging_manager.py` is deleted. It also uses `print` statements and `sys.exit` -- it is a manual test script, not a pytest test module.

## Changes

Delete all 5 files:

- [ ] `tests/test_staging_integration.py` (661 lines)
- [ ] `tests/test_composite_apply.py` (558 lines)
- [ ] `tests/test_apply_verification.py` (440 lines)
- [ ] `tests/test_apply_robustness.py` (428 lines)
- [ ] `tests/test_reorder.py` (297 lines)

## Verification

```bash
# 1. Confirm all remaining tests pass
python3 -m pytest tests/ -v

# 2. Confirm no remaining test files import from deleted modules
grep -r "from staging_manager\|import staging_manager" tests/
grep -r "from apply_verification\|import apply_verification" tests/
grep -r "from nagios_service import.*apply_object_composite\|_build_composite_actions" tests/
# All three grep commands must return no matches.

# 3. Confirm replacement test suites exist and pass
python3 -m pytest tests/test_candidate_manager.py -v
python3 -m pytest tests/test_candidate_routes.py -v

# 4. Confirm no lint issues in remaining test files
ruff check tests/
ruff format --check tests/

# 5. Confirm the deleted files no longer exist
test ! -f tests/test_staging_integration.py
test ! -f tests/test_composite_apply.py
test ! -f tests/test_apply_verification.py
test ! -f tests/test_apply_robustness.py
test ! -f tests/test_reorder.py
```

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Deleted tests validated this for the old staging system. Replacement `TestLiveConfigImmutability` (L01, 4 tests) validates the same invariant for the candidate system. |
| 2 | UI visual parity | N/A | Test file deletion has no UI impact. |
| 3 | Full audit logging | COMPLIANT | Deleted tests did not exercise audit logging directly. Replacement `TestAuditLogging` (L01, 4 tests) validates audit logging for all candidate operations. |
| 4 | Proper error handling | COMPLIANT | Error-handling tests in deleted files (xfail bugs, out-of-range indices, retry failures) are replaced by `TestPathSafety` (4 tests) and `TestParserCorruptionGuard` (1 test) in L01, which cover the equivalent error surfaces in the candidate architecture. |
| 5 | Dead code deletion | COMPLIANT | This plan IS dead code deletion. All 5 test files exercise modules being deleted (staging_manager.py, apply_verification.py, nagios_service.py staging methods). They will fail to import once dependencies are removed. |
| 6 | Full functionality migration | COMPLIANT | Detailed coverage migration map above proves every test category has a replacement. Three xfail tests document bugs that are architecturally eliminated. No coverage is dropped without explanation. |
| 7 | Palo Alto candidate model | COMPLIANT | Replacement tests (L01, L03) validate the candidate model: copy-edit-apply lifecycle, per-operation validation, git-based undo and diff. |
| 8 | Change tracking document | COMPLIANT | Changes section provides a checklist of all 5 files with line counts. |
| 9 | Complete planning before implementation | COMPLIANT | Plan includes full removal audit, per-test coverage migration map, verification commands, and dependency list. No ambiguity remains for implementation. |
| 10 | Linting enforcement | COMPLIANT | Verification section includes `ruff check` and `ruff format --check` for remaining test files. Deletion-only change cannot introduce lint violations. |
| 11 | Playwright validation | N/A | Backend test file deletion has no UI impact. No Playwright tests needed. |
