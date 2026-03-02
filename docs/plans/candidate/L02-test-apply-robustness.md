# L02: tests/test_apply_robustness.py — SKIP

**Layer:** 2 — Backend Prep
**Action:** SKIP (no changes)
**Path:** `tests/test_apply_robustness.py`
**Goal:** Originally planned to remove xfail decorators after fixing _exec_delete. SKIPPED because the _exec_delete bug is in staging code that will be deleted entirely in L12. No point fixing dead code.

---

## Rationale

The `_exec_delete` method uses stale `global_index` after cross-file deletes. This is a known bug in the old staging apply system. Since the candidate system doesn't use `_exec_delete` at all (it uses direct file operations via `file_operations.*`), fixing this bug provides no value. The test file is deleted entirely in L12.

## Change Tracking

- [x] Decision: SKIP this file — no changes needed (dead code, deleted in L12)

## Verification

No action needed. File remains unchanged until L12 deletion.

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** N/A — no changes made; file is skipped.
- [x] **C2 — UI visual parity.** N/A — test file, no UI involvement.
- [x] **C3 — Full audit logging.** N/A — test file, no operations to log.
- [x] **C4 — Proper error handling.** N/A — no changes made.
- [x] **C5 — Dead code deletion.** The entire test file targets dead staging code (`_exec_delete`). It is deferred to L12 for bulk deletion with `staging_manager.py`, which is the correct approach — deleting it now would remove test coverage for code that still exists.
- [x] **C6 — Full functionality migration.** N/A — the tested functionality (`_exec_delete`) is not migrated; the candidate system uses `file_operations.*` instead.
- [x] **C7 — Palo Alto candidate model.** N/A — skip decision aligns with candidate model: the old staging apply path is replaced entirely, not patched.
- [x] **C8 — Change tracking.** Change Tracking section added above (single item, pre-checked as decided).
- [x] **C9 — Complete planning before implementation.** Skip rationale is fully documented; no implementation required.
- [x] **C10 — Linting enforcement.** N/A — no code changes to lint.
- [x] **C11 — Playwright validation.** N/A — no changes to validate.
