# L12 — `tests/test_atomic_writes.py` — MODIFY

**Layer:** 12 — Staging Cleanup
**Action:** MODIFY
**Path:** `tests/test_atomic_writes.py`
**Dependencies:** L01-candidate-manager.md, L01-test-candidate-manager.md (replacement coverage must exist first)
**Tracked in:** L00-migration-inventory.md (Section 1.12, test files table)

## Purpose

Delete the `TestStagingSaveAtomic` class, which tests `staging_manager.save_staging()` atomic writes. This class depends on `StagingManager`, which is deleted in L12-staging-manager.md. The atomic write behavior it validates (temp file + fsync + os.replace) is provided by `file_operations.py` and remains tested by the `TestServerConfigSaveAtomic` class in the same file. CandidateManager's write paths are tested via `tests/test_candidate_manager.py` (L01).

## Removal Audit

| Item | Lines | Disposition | Replacement Coverage |
|------|-------|-------------|---------------------|
| `TestStagingSaveAtomic` class | 12-40 | DELETE | `test_candidate_manager.py` tests CandidateManager write paths; `TestServerConfigSaveAtomic` (kept) tests `file_operations.py` atomic pattern |
| `from staging_manager import StagingManager` | 17 | DELETE (inside class) | No longer needed — StagingManager deleted in L12 |

**Kept intact:**
- `TestServerConfigSaveAtomic` class (lines 44-79) — Tests `server_config.save_config()` atomic write pattern. No staging dependency. Still valid.

## Changes

Delete the `TestStagingSaveAtomic` class (lines 12-40) and its blank trailing lines. Keep all other test classes in the file. The file-level imports (`json`, `os`, `tempfile`, `Path`, `patch`, `pytest`) remain valid for the surviving test class.

## Dead Code Confirmation

After this change, zero references to `staging_manager` remain in `test_atomic_writes.py`. The file contains only `TestServerConfigSaveAtomic`, which imports from `server_config` — no dead code is left behind.

## Verification

```bash
# Tests pass
python3 -m pytest tests/test_atomic_writes.py -v

# No staging imports remain in this file
grep -r "staging_manager\|StagingManager" tests/test_atomic_writes.py
# Expected: no matches

# Linting passes (Commandment 10)
python3 -m ruff check tests/test_atomic_writes.py
python3 -m ruff format --check tests/test_atomic_writes.py
```

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | N/A | Test file cleanup only. The surviving `TestServerConfigSaveAtomic` tests atomic writes for `server_config`, which does not mutate Nagios config. CandidateManager enforces the "no live mutation" invariant, tested in `test_candidate_manager.py::TestLiveConfigImmutability`. |
| 2 | UI visual parity | N/A | Backend test file — no UI impact. |
| 3 | Full audit logging | N/A | Test cleanup — no auditable operations introduced or removed. |
| 4 | Proper error handling | OK | No error handling removed. The deleted test class only exercised `staging_manager.save_staging()` round-trip; equivalent coverage exists in `test_candidate_manager.py`. |
| 5 | Dead code deletion | OK | This plan's primary purpose — removes test class that depends on deleted `StagingManager`. |
| 6 | Full functionality migration | OK | Atomic write testing is preserved: `TestServerConfigSaveAtomic` remains for `server_config.py`; `test_candidate_manager.py` covers CandidateManager write paths; `file_operations.py` atomic primitives are unchanged. |
| 7 | Palo Alto candidate model | OK | Removal aligns with candidate migration: `StagingManager` is replaced by `CandidateManager`, so its tests are replaced by `test_candidate_manager.py`. |
| 8 | Change tracking document | OK | Tracked in L00-migration-inventory.md, Section 1.12 (`tests/test_atomic_writes.py` — MODIFY — `[covered]`). |
| 9 | Complete planning before implementation | OK | This plan is complete. All impacts enumerated; no ambiguity in what to delete vs keep. |
| 10 | Linting enforcement | OK | Verification section includes `ruff check` and `ruff format --check` commands. |
| 11 | Playwright validation | N/A | Backend test file cleanup — no UI changes to validate. |
