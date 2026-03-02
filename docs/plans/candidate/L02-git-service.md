# L02: git_service.py — MODIFY

**Layer:** 2 — Backend Prep
**Action:** MODIFY
**Path:** `git_service.py`
**Dependencies:** None
**Goal:** Replace `.staging/` with `.candidate/` in git exclusion paths and .gitignore generation, ensuring the candidate directory is never tracked by git.

---

## Scope & Safety Notes

- **No live config mutation.** This plan modifies only default exclusion-path strings and .gitignore auto-generation within `git_service.py`. No Nagios configuration files are read, written, or modified. All live config remains untouched.
- **No UI changes.** This is a pure backend change to internal path constants. No templates, CSS, or JavaScript are affected.
- **No new code paths.** Every change is a direct string replacement within existing code. All existing error handling (OperationResult returns, timeout/retry logic, subprocess error capture) is preserved unchanged.
- **Audit logging unaffected.** The git service does not call `audit_service.py` directly; audit logging is handled at the route layer. Existing `logger.info/warning/error` calls in git_service.py remain intact and will continue to log all git operations.

---

## Current State

4 occurrences of `.staging/` in the file:

### 1. `get_status()` default excluded_paths (line ~281)
```python
excluded_paths = [".backups/", ".backups", ".staging/", ".staging",
                  ".git/", "backups/", "backups"]
```

### 2. `get_workspace_diff()` default excluded_paths (line ~452)
```python
excluded_paths = [".backups/", ".staging/", ".git/"]
```

### 3. `_init_repo_impl()` .gitignore content (line ~788)
```python
f.write(".staging/\n")
```

### 4. Comment in `get_workspace_diff()` docstring (line ~443)
```python
Used by the staging/diff endpoint.
```

## Changes

### Step 1: Update `get_status()` excluded_paths

Replace `.staging/` and `.staging` with `.candidate/` and `.candidate`:

```python
excluded_paths = [".backups/", ".backups", ".candidate/", ".candidate",
                  ".git/", "backups/", "backups"]
```

### Step 2: Update `get_workspace_diff()` excluded_paths

Replace `.staging/` with `.candidate/`:

```python
excluded_paths = [".backups/", ".candidate/", ".git/"]
```

### Step 3: Update `_init_repo_impl()` .gitignore

Replace `.staging/` with `.candidate/`:

```python
f.write(".candidate/\n")
```

This ensures that any newly-initialized git repo in a Nagios config directory will have `.candidate/` in its .gitignore, preventing candidate working copies from being tracked.

### Step 4: Update docstring comment

Replace "staging/diff endpoint" with "candidate/diff endpoint":

```python
Used by the candidate/diff endpoint.
```

## Dead Code & Functionality Migration Audit

**Dead code:** All 4 `.staging/` references are being replaced, not left alongside new `.candidate/` references. After this change, zero `.staging/` references will remain in `git_service.py`. The old `.staging/` directory will no longer exist after the full migration, so excluding it would be dead configuration.

**Functionality migrated:** Every exclusion that previously protected `.staging/` from git tracking now protects `.candidate/` identically:
| Function | Old exclusion | New exclusion | Purpose preserved |
|----------|--------------|---------------|-------------------|
| `get_status()` | `.staging/`, `.staging` | `.candidate/`, `.candidate` | Yes — hide candidate dir from status |
| `get_workspace_diff()` | `.staging/` | `.candidate/` | Yes — exclude candidate dir from diffs |
| `_init_repo_impl()` | `.staging/` in .gitignore | `.candidate/` in .gitignore | Yes — gitignore candidate dir |

No functionality is dropped. No new functionality is added.

## Linting

After making changes, verify both linters pass:

```bash
python3 -m ruff check git_service.py
python3 -m ruff format --check git_service.py
```

No new code is introduced, only string literal changes, so lint impact is nil. But verify regardless.

## Verification

```bash
python3 -m pytest tests/test_git_service.py -v
# NOTE: test_git_service.py asserts ".staging/" in gitignore — this test will FAIL.
# Update the assertion in the same commit (see L02-test-git-service.md):
# Change: assert ".staging/" in gitignore
# To:     assert ".candidate/" in gitignore
```

**Post-change grep** to confirm no `.staging/` references remain in git_service.py:

```bash
grep -n '\.staging' git_service.py
# Expected: zero matches
```

## Playwright Applicability

Not applicable. This change is entirely backend (path string constants and .gitignore generation). There are no UI-visible effects to validate with Playwright.

## Change Tracking

| # | Change | File | Line(s) | Status |
|---|--------|------|---------|--------|
| 1 | Replace `.staging/` and `.staging` in `get_status()` default excluded_paths | `git_service.py` | ~281 | [ ] |
| 2 | Replace `.staging/` in `get_workspace_diff()` default excluded_paths | `git_service.py` | ~452 | [ ] |
| 3 | Replace `.staging/` with `.candidate/` in `_init_repo_impl()` .gitignore write | `git_service.py` | ~788 | [ ] |
| 4 | Replace "staging/diff" with "candidate/diff" in `get_workspace_diff()` docstring | `git_service.py` | ~443 | [ ] |
| 5 | Verify Ruff lint passes | `git_service.py` | — | [ ] |
| 6 | Verify test suite passes (with L02-test-git-service.md applied) | `tests/test_git_service.py` | — | [ ] |
| 7 | Verify zero `.staging` references remain in git_service.py via grep | `git_service.py` | — | [ ] |

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This plan modifies only internal path-exclusion strings and .gitignore auto-generation within git_service.py. No Nagios configuration files are read, written, or modified.
- [x] **C2 — UI visual parity.** No UI changes. This is a pure backend change to internal path constants. No templates, CSS, or JavaScript are affected.
- [x] **C3 — Full audit logging.** Existing application logging (`logger.info/warning/error`) in git_service.py is preserved unchanged. Audit logging via audit_service.py is handled at the route layer and is not affected by this change.
- [x] **C4 — Proper error handling everywhere.** No new code paths are introduced. All existing OperationResult returns, timeout/retry logic, and subprocess error capture remain intact.
- [x] **C5 — Dead code deletion.** All 4 `.staging/` references are replaced, not left behind. Zero `.staging/` references will remain in git_service.py after this change. Post-change grep verification is specified.
- [x] **C6 — Full functionality migration.** Every `.staging/` exclusion is replaced with an equivalent `.candidate/` exclusion serving the identical purpose. No functionality is dropped. Migration table provided above.
- [x] **C7 — Palo Alto candidate model.** This change is a direct requirement of the candidate model: the `.candidate/` directory (where config is copied for editing) must be excluded from git tracking, just as `.staging/` was.
- [x] **C8 — Change tracking document.** Change tracking table with 7 items and checkbox status is included in the "Change Tracking" section above.
- [x] **C9 — Complete planning before implementation.** This plan is fully specified (4 string replacements, lint verification, test verification, grep verification) before any code changes begin.
- [x] **C10 — Linting enforcement.** Ruff check and format verification commands are specified in the "Linting" section. Must pass before committing.
- [x] **C11 — Playwright validation.** Explicitly marked as not applicable. This is a backend-only change to path string constants with no UI-visible effects.
