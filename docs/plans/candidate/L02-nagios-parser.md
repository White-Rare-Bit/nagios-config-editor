# L02: nagios_parser.py — MODIFY

**Layer:** 2 — Backend Prep
**Action:** MODIFY
**Path:** `nagios_parser.py`
**Dependencies:** None
**Goal:** Add `.candidate/` to the parser skip list so candidate config files are never parsed as part of the running config. This ensures the candidate directory (where edits are staged before Apply) remains invisible to the live config parser, enforcing the separation between candidate and live state.

---

## Current State

In `parse_all()` (line 66), the parser skips staging directories:

```python
# Skip staging directories (shadow copies, baselines)
if "/.staging/" in file_path or "/.nagios_staging/" in file_path:
    continue
```

## Changes

### Step 1: Add `.candidate/` skip after the staging skip (line 66)

Add a new `continue` clause immediately after the staging skip:

**After line 67 (`continue`), add:**
```python
# Skip candidate config directory
if "/.candidate/" in file_path:
    continue
```

The complete block should read:
```python
# Skip staging directories (shadow copies, baselines)
if "/.staging/" in file_path or "/.nagios_staging/" in file_path:
    continue
# Skip candidate config directory
if "/.candidate/" in file_path:
    continue
```

Note: The `.staging/` skip is kept for now — it is dead code but cannot be removed yet because `staging_manager.py` still exists at this layer. It is explicitly removed in L13 (`L13-nagios-parser.md`) after `staging_manager.py` is deleted in L12.

## Removal Audit

No code is being removed in this file change. This is purely additive. Dead code removal of the `.staging/` skip is deferred to L13-nagios-parser.md (Commandment 5).

## Error Handling

This change is a simple string containment check in a loop filter. No new error paths are introduced. The existing `parse_file()` method already handles `OSError` and `UnicodeDecodeError` with proper logging (lines 82-99). No additional error handling is needed for this change (Commandment 4).

## Audit Logging

This change modifies parser behavior (read-only file scanning), not a mutation operation. Audit logging through `audit_service.py` is not applicable here — audit events are for user-initiated mutations (edits, applies, backups, etc.), not internal file discovery. Application-level logging already exists in the parser via `logger = logging.getLogger("nagios_bulk_editor.parser")` (Commandment 3).

## UI Impact

None. This is a backend-only change to the parser's file discovery logic. No UI changes, no visual differences (Commandment 2).

## Playwright Validation

Not applicable. This is a backend-only parser change with no UI surface. Playwright tests would not exercise this code path. Verification is handled by the unit test below (Commandment 11).

## Change Tracking

- [ ] Add `.candidate/` skip clause to `parse_all()` in `nagios_parser.py` after line 67
- [ ] Run existing test suite to confirm no regressions
- [ ] Run candidate skip verification script
- [ ] Run `python3 -m ruff check nagios_parser.py` to confirm lint compliance

## Verification

```bash
# Step 1: Lint check (Commandment 10)
python3 -m ruff check nagios_parser.py

# Step 2: Existing tests pass (regression check)
python3 -m pytest tests/ -v

# Step 3: Candidate skip behavior verified
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
print('OK: .candidate/ files correctly skipped')
"
```

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This change supports C1 by ensuring the candidate directory is invisible to the live config parser. The parser only reads; it never writes.
- [x] **C2 — UI visual parity.** No UI changes. Backend-only parser filter modification.
- [x] **C3 — Full audit logging.** Not applicable to this change (read-only file scanning, not a user mutation). Application logging already present via `logging.getLogger("nagios_bulk_editor.parser")`.
- [x] **C4 — Proper error handling everywhere.** No new error paths introduced. Existing `parse_file()` handles `OSError` and `UnicodeDecodeError` with proper logging.
- [x] **C5 — Dead code deletion.** No dead code introduced. The existing `.staging/` skip is acknowledged as future dead code, with explicit removal deferred to L13-nagios-parser.md (after staging_manager.py deletion in L12).
- [x] **C6 — Full functionality migration.** No functionality removed. Purely additive change.
- [x] **C7 — Palo Alto candidate model.** Directly supports the candidate model by preventing candidate config files from being parsed as live config.
- [x] **C8 — Change tracking document.** Change tracking checklist added to this plan.
- [x] **C9 — Complete planning before implementation.** Plan is complete with current state, changes, removal audit, error handling, verification, and change tracking.
- [x] **C10 — Linting enforcement.** Ruff lint check added as first step in verification sequence.
- [x] **C11 — Playwright validation.** Not applicable (backend-only parser change, no UI surface). Noted with rationale.
