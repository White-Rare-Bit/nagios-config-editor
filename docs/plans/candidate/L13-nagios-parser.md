# L13 — `nagios_parser.py` — MODIFY

**Layer:** 13 — CSS & Docs (Dead Code Cleanup)
**Action:** MODIFY
**Path:** `nagios_parser.py`
**Dependencies:** L02-nagios-parser.md (added `.candidate/` skip), L12-staging-manager.md (deleted `staging_manager.py`)
**Goal:** Remove the `.staging/` and `.nagios_staging/` directory exclusions from `parse_all()`. These are dead code now that `staging_manager.py` has been deleted in L12. Only the `.candidate/` skip (added in L02) is needed going forward.

---

## Current State (after L02, before this plan)

In `parse_all()` (lines 65-68), the parser skips both staging and candidate directories:

```python
# Skip staging directories (shadow copies, baselines)
if "/.staging/" in file_path or "/.nagios_staging/" in file_path:
    continue
# Skip candidate config directory
if "/.candidate/" in file_path:
    continue
```

The `.staging/` and `.nagios_staging/` skips were needed when `staging_manager.py` existed and created shadow copies under these directories. Since `staging_manager.py` is deleted in L12, no code creates or uses `.staging/` or `.nagios_staging/` directories. These conditions are dead code.

## Removal Audit

| Line | Code | Status | Rationale |
|------|------|--------|-----------|
| 65 | `# Skip staging directories (shadow copies, baselines)` | DEAD — REMOVE | Comment describes deleted staging system |
| 66 | `if "/.staging/" in file_path or "/.nagios_staging/" in file_path:` | DEAD — REMOVE | No code creates `.staging/` or `.nagios_staging/` directories after L12 |
| 67 | `continue` | DEAD — REMOVE | Part of dead staging skip block |

**Kept:**
| Line | Code | Status | Rationale |
|------|------|--------|-----------|
| 68 | `# Skip candidate config directory` | KEEP | Documents the candidate skip added in L02 |
| 69 | `if "/.candidate/" in file_path:` | KEEP | Required for candidate model — prevents candidate files from appearing in live config |
| 70 | `continue` | KEEP | Part of candidate skip block |

## Changes

Remove the two-line staging skip block and its comment. Keep the candidate skip block.

**BEFORE (after L02):**
```python
# Skip staging directories (shadow copies, baselines)
if "/.staging/" in file_path or "/.nagios_staging/" in file_path:
    continue
# Skip candidate config directory
if "/.candidate/" in file_path:
    continue
```

**AFTER:**
```python
# Skip candidate config directory
if "/.candidate/" in file_path:
    continue
```

This is a 3-line deletion (comment + condition + continue). No new code is added.

## Error Handling

No new error paths introduced. This change removes dead filtering logic from a loop. The existing `parse_file()` method already handles `OSError` and `UnicodeDecodeError` with proper logging (lines 82-99). No additional error handling is needed (Commandment 4).

## Audit Logging

Not applicable to this change. The parser's `parse_all()` is a read-only file scanning operation, not a user-initiated mutation. Audit events through `audit_service.py` apply to mutations (edits, applies, backups, etc.), not internal file discovery. Application-level logging already exists via `logger = logging.getLogger("nagios_bulk_editor.parser")` (Commandment 3).

## UI Impact

None. This is a backend-only change removing dead filtering logic from the parser. No UI changes, no visual differences. The parser's output is identical because no `.staging/` or `.nagios_staging/` directories exist after L12 (Commandment 2).

## Playwright Validation

Not applicable. This is a backend-only parser change with no UI surface. No `.staging/` directories exist after L12, so this removal has zero behavioral effect. Verification is handled by the grep check and unit tests below (Commandment 11).

## Change Tracking

- [ ] Remove `.staging/` and `.nagios_staging/` skip block (comment + condition + continue) from `parse_all()` in `nagios_parser.py`
- [ ] Confirm `.candidate/` skip remains intact
- [ ] Run `python3 -m ruff check nagios_parser.py` — passes
- [ ] Run `python3 -m pytest tests/ -v` — all pass
- [ ] Run grep verification — no "staging" references remain in nagios_parser.py

## Verification

```bash
# Step 1: Lint check (Commandment 10)
python3 -m ruff check nagios_parser.py

# Step 2: Existing tests pass (regression check)
python3 -m pytest tests/ -v

# Step 3: No staging references remain in the parser
grep -n "staging" nagios_parser.py
# Expected: zero matches

# Step 4: Candidate skip still present and functional
grep -n "candidate" nagios_parser.py
# Expected: one match — the /.candidate/ skip line

# Step 5: Verify candidate skip behavior still works
python3 -c "
from nagios_parser import NagiosConfigParser
import tempfile, os
d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, '.candidate'))
with open(os.path.join(d, '.candidate', 'hosts.cfg'), 'w') as f:
    f.write('define host { host_name test address 1.1.1.1 }')
with open(os.path.join(d, 'hosts.cfg'), 'w') as f:
    f.write('define host { host_name real address 2.2.2.2 }')
p = NagiosConfigParser(d)
p.parse_all()
assert len(p.objects) == 1, f'Expected 1 object, got {len(p.objects)}'
assert p.objects[0].attributes['host_name'] == 'real'
print('OK: .candidate/ files correctly skipped, .staging/ skip removed cleanly')
"
```

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This change does not write to any config files. It modifies read-only parser filtering logic. The candidate skip (which enforces the separation between candidate and live) is preserved.
- [x] **C2 — UI visual parity.** No UI changes. Backend-only parser filter modification. Zero visual impact.
- [x] **C3 — Full audit logging.** Not applicable (read-only file scanning, not a user mutation). Application logging already present via `logging.getLogger("nagios_bulk_editor.parser")`.
- [x] **C4 — Proper error handling everywhere.** No new error paths introduced. Existing `parse_file()` handles `OSError` and `UnicodeDecodeError` with proper logging.
- [x] **C5 — Dead code deletion.** This plan IS the dead code deletion — removing the `.staging/` and `.nagios_staging/` skip conditions that became dead when `staging_manager.py` was deleted in L12.
- [x] **C6 — Full functionality migration.** No functionality dropped. The `.staging/` skip was only needed to prevent staging shadow copies from being parsed as live config. With `staging_manager.py` deleted, no code creates these directories, so the skip serves no purpose.
- [x] **C7 — Palo Alto candidate model.** Supports the candidate model by cleaning up vestiges of the old staging system while preserving the `.candidate/` skip that enforces candidate/live separation.
- [x] **C8 — Change tracking document.** Change tracking checklist included above with all implementation steps.
- [x] **C9 — Complete planning before implementation.** Plan includes current state, removal audit with line-by-line analysis, exact before/after code, error handling analysis, UI impact assessment, and multi-step verification.
- [x] **C10 — Linting enforcement.** Ruff lint check is first step in verification sequence.
- [x] **C11 — Playwright validation.** Not applicable (backend-only dead code removal with no UI surface and zero behavioral effect). Noted with rationale.
