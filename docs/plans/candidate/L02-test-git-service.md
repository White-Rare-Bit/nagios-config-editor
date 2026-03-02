# L02: tests/test_git_service.py — MODIFY

**Layer:** 2 — Backend Prep
**Action:** MODIFY
**Path:** `tests/test_git_service.py`
**Dependencies:** L02-git-service.md must be applied first (or simultaneously)
**Goal:** Update the .gitignore assertion to match the new `.candidate/` pattern.

---

## Current State

The test file contains an assertion checking that `.staging/` appears in the auto-generated .gitignore.

## Changes

### Step 1: Find and update the `.staging/` assertion

Search for `assert ".staging/" in gitignore` and replace with:

```python
assert ".candidate/" in gitignore
```

## Change Tracking

- [ ] Replace `assert ".staging/" in gitignore` with `assert ".candidate/" in gitignore` in `tests/test_git_service.py`

## Verification

```bash
# Run the updated test
python3 -m pytest tests/test_git_service.py -v

# Lint check (Python)
python3 -m ruff check tests/test_git_service.py
python3 -m ruff format --check tests/test_git_service.py
```

## Commandments Compliance

- [ ] **C1 — No live config mutation until Apply.** N/A — this is a test file change only; no config write paths are affected.
- [ ] **C2 — UI visual parity.** N/A — no UI changes; backend test only.
- [ ] **C3 — Full audit logging.** N/A — test file; no auditable operations introduced or removed.
- [ ] **C4 — Proper error handling.** N/A — test assertions only; no new error-handling paths.
- [x] **C5 — Dead code deletion.** The old `.staging/` assertion is replaced, not left alongside the new one.
- [x] **C6 — Full functionality migration.** The `.staging/` gitignore assertion is migrated to `.candidate/`, preserving test coverage.
- [x] **C7 — Palo Alto candidate model.** Change directly supports the candidate directory rename required by the new model.
- [x] **C8 — Change tracking.** Change Tracking section with tickable checklist added above.
- [x] **C9 — Complete planning before implementation.** This plan documents the full change before any code is modified.
- [ ] **C10 — Linting enforcement.** Ruff check and format commands included in Verification section above.
- [ ] **C11 — Playwright validation.** N/A — backend test file only; no UI to validate.
