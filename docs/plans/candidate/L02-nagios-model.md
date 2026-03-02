# L02: nagios_model.py — MODIFY

**Layer:** 2 — Backend Prep
**Action:** MODIFY
**Path:** `nagios_model.py`
**Dependencies:** None
**Goal:** Receive 3 stable key functions migrated from `staging_manager.py` so they can be imported without depending on the staging module.

---

## Current State

`nagios_model.py` ends with the `get_object_name()` function at line ~597. It does not contain any stable key functions.

The functions to migrate are in `staging_manager.py` at lines 1394-1448:
- `generate_stable_key(source_file, object_type, name) -> str`
- `parse_stable_key(key) -> dict | None`
- `generate_stable_key_for_object(obj) -> str`

## Changes

### Step 1: Add stable key functions at end of `nagios_model.py`

Append after the `get_object_name()` function:

```python
# =============================================================================
# Stable Key Functions (migrated from staging_manager)
# =============================================================================


def generate_stable_key(source_file: str, object_type: str, name: str) -> str:
    """Generate a stable key for an object.

    The stable key format is: "source_file|object_type|name"
    This key remains stable across parser reloads and index changes.
    """
    return f"{source_file}|{object_type}|{name}"


def parse_stable_key(key: str) -> dict[str, str] | None:
    """Parse a stable key back into its components.

    Returns dictionary with source_file, object_type, name keys, or None if invalid.
    """
    parts = key.split("|")
    if len(parts) != 3:  # noqa: PLR2004
        return None
    return {
        "source_file": parts[0],
        "object_type": parts[1],
        "name": parts[2],
    }


def generate_stable_key_for_object(obj) -> str:
    """Generate a stable key for a NagiosObject.

    Uses get_display_name() to ensure uniqueness.
    """
    name = obj.get_display_name()
    return generate_stable_key(obj.source_file, obj.object_type, name)
```

Note: The `obj` parameter uses duck typing (no type annotation) to avoid a circular import — `NagiosObject` is defined in the same file but the function is a module-level function, not a method.

## Change Tracking

- [ ] Step 1: Add `generate_stable_key()` function to end of `nagios_model.py`
- [ ] Step 1: Add `parse_stable_key()` function to end of `nagios_model.py`
- [ ] Step 1: Add `generate_stable_key_for_object()` function to end of `nagios_model.py`
- [ ] Verification: inline smoke test passes
- [ ] Verification: existing `test_stable_keys.py` passes
- [ ] Verification: ruff lint passes on `nagios_model.py`

## Removal Audit

No code is removed from this file. The original functions in `staging_manager.py` are kept for now (removed when staging_manager.py is deleted in L12).

## Verification

```bash
# Smoke test
python3 -c "
from nagios_model import generate_stable_key, parse_stable_key, generate_stable_key_for_object
key = generate_stable_key('/path/hosts.cfg', 'host', 'web-01')
assert key == '/path/hosts.cfg|host|web-01'
parsed = parse_stable_key(key)
assert parsed['source_file'] == '/path/hosts.cfg'
assert parsed['object_type'] == 'host'
assert parsed['name'] == 'web-01'
print('OK: stable key functions work')
"

# Unit tests
python3 -m pytest tests/test_stable_keys.py -v
# NOTE: test_stable_keys.py still imports from staging_manager — that's OK for now.
# Import update happens when staging_manager.py is deleted in L12.

# Linting
python3 -m ruff check nagios_model.py
python3 -m ruff format --check nagios_model.py
```

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** N/A — these are pure functions for key generation/parsing. No config mutation involved.
- [x] **C2 — UI visual parity.** N/A — backend-only change, no UI impact.
- [x] **C3 — Full audit logging.** N/A — utility functions only; no operations that require audit logging.
- [x] **C4 — Proper error handling.** `parse_stable_key()` returns `None` for invalid input (matching existing behavior). No silent failures.
- [x] **C5 — Dead code deletion.** Original copies in `staging_manager.py` are intentionally kept until L12 deletion to avoid breaking existing imports mid-migration.
- [x] **C6 — Full functionality migration.** All three stable key functions are migrated verbatim. No functionality is dropped.
- [x] **C7 — Palo Alto candidate model.** Moving stable key functions to `nagios_model.py` decouples them from the staging module, enabling the candidate system to use them without importing staging.
- [x] **C8 — Change tracking.** Change Tracking section with tickable checklist added above.
- [x] **C9 — Complete planning before implementation.** Full function signatures, implementations, and duck-typing rationale are specified before any code changes.
- [x] **C10 — Linting enforcement.** Verification section includes `ruff check` and `ruff format --check` commands. Code includes `# noqa: PLR2004` for the magic number check.
- [x] **C11 — Playwright validation.** N/A — backend-only utility functions with no UI surface. Unit tests are sufficient.
