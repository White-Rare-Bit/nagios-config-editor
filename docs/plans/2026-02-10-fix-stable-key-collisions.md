# Fix Stable Key Collisions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the bug where clicking a service in the left panel shows the wrong object in the attribute editor when multiple services share the same `service_description` (e.g., "PING" on linux-hosts vs windows-hosts).

**Architecture:** Stable keys currently use `get_name()` which returns raw `service_description` — not unique for services on different hosts. Switch to `get_display_name()` which includes host/hostgroup context (e.g., "PING on linux-hosts"). This change affects key generation + lookup in both backend and frontend, but does NOT touch `get_name()` itself (which is still needed for reference matching).

**Tech Stack:** Python (Flask), JavaScript (vanilla), pytest

---

### The Bug

Stable keys have format `"source_file|object_type|name"`. For services, `name` = `service_description` (e.g., "PING"). When two services in the same file share a `service_description` on different hosts, they produce identical keys. The first match wins in lookup, so clicking the second service shows the first one's attributes.

### The Fix

Replace `name` with `display_name` in key generation/lookup. `display_name` includes host/hostgroup context and is guaranteed unique per (source_file, object_type) pair.

**Verified:** Running `get_display_name()` over all 198 objects in sample-config produces zero key collisions.

**Unaffected code:** Reference lookups, bulk rename, health checks — these all use `get_name()` directly, not stable keys.

---

### Task 1: Backend — `generate_stable_key_for_object()` uses `get_display_name()`

**Files:**
- Modify: `staging_manager.py:1375-1388`
- Test: `tests/test_stable_keys.py` (create)

**Step 1: Write the failing test**

Create `tests/test_stable_keys.py`:

```python
"""Tests for stable key generation and uniqueness."""

import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from staging_manager import generate_stable_key_for_object


@pytest.fixture
def app_with_duplicate_services():
    """Create app with services that share service_description."""
    test_dir = tempfile.mkdtemp()
    test_config_path = Path(test_dir) / "nagios"
    test_config_path.mkdir()

    services_cfg = test_config_path / "services.cfg"
    services_cfg.write_text("""
define service {
    hostgroup_name    linux-hosts
    service_description    PING
    use    local-service
    check_command    check_ping!100.0,20%!500.0,60%
}

define service {
    hostgroup_name    windows-hosts
    service_description    PING
    use    local-service
    check_command    check_ping!200.0,40%!600.0,80%
}
""")

    app = create_app(config_path=str(test_config_path))
    app.config["TESTING"] = True

    yield app

    shutil.rmtree(test_dir, ignore_errors=True)


def test_duplicate_service_descriptions_get_unique_keys(app_with_duplicate_services):
    """Services with same service_description on different hosts must have unique stable keys."""
    with app_with_duplicate_services.app_context():
        from routes.helpers import get_service
        service = get_service()
        services = [o for o in service.get_objects() if o.object_type == "service"]

        assert len(services) == 2
        key1 = generate_stable_key_for_object(services[0])
        key2 = generate_stable_key_for_object(services[1])
        assert key1 != key2, f"Keys must differ but both are: {key1}"
        # Keys should contain the display name with host context
        assert "linux-hosts" in key1
        assert "windows-hosts" in key2
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stable_keys.py::test_duplicate_service_descriptions_get_unique_keys -v`
Expected: FAIL — both keys are `"...services.cfg|service|PING"`

**Step 3: Implement the fix**

In `staging_manager.py`, change `generate_stable_key_for_object()` (lines 1375-1388):

```python
def generate_stable_key_for_object(obj: Any) -> str:
    """Generate a stable key for a NagiosObject.

    Uses get_display_name() to ensure uniqueness — services with the same
    service_description on different hosts get different keys.

    Args:
        obj: NagiosObject instance

    Returns:
        Stable key string

    """
    name = obj.get_display_name()
    return generate_stable_key(obj.source_file, obj.object_type, name)
```

Changes:
- Replace `get_object_name(obj.object_type, obj.attributes)` with `obj.get_display_name()`
- Remove the `from nagios_model import get_object_name` import (no longer needed here)

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_stable_keys.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add staging_manager.py tests/test_stable_keys.py
git commit -m "fix: use display_name in stable key generation to avoid collisions"
```

---

### Task 2: Backend — `find_object_by_stable_key()` matches on `get_display_name()`

**Files:**
- Modify: `nagios_service.py:249-277`

Note: This function currently has zero callers — it's dead code. But it should stay consistent with key generation so it works if/when it's used.

**Step 1: Write the failing test**

Add to `tests/test_stable_keys.py`:

```python
def test_find_object_by_stable_key_with_display_name(app_with_duplicate_services):
    """find_object_by_stable_key should resolve keys that use display_name."""
    with app_with_duplicate_services.app_context():
        from routes.helpers import get_service
        service = get_service()
        services = [o for o in service.get_objects() if o.object_type == "service"]

        key1 = generate_stable_key_for_object(services[0])
        key2 = generate_stable_key_for_object(services[1])

        result1 = service.find_object_by_stable_key(key1)
        result2 = service.find_object_by_stable_key(key2)

        assert result1 is not None, f"Should find object for key: {key1}"
        assert result2 is not None, f"Should find object for key: {key2}"
        # They should find different objects
        assert result1[0] != result2[0], "Should find different objects"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stable_keys.py::test_find_object_by_stable_key_with_display_name -v`
Expected: FAIL — key contains display_name but lookup uses `get_object_name()` which returns raw name

**Step 3: Implement the fix**

In `nagios_service.py`, change `find_object_by_stable_key()` (lines 249-277):

```python
def find_object_by_stable_key(self, stable_key: str) -> tuple | None:
    """Find an object by its stable key.

    Args:
        stable_key: Stable key in format "source_file|object_type|display_name"

    Returns:
        Tuple of (global_index, NagiosObject) or None if not found

    """
    parsed = parse_stable_key(stable_key)
    if not parsed:
        return None

    source_file = parsed["source_file"]
    obj_type = parsed["object_type"]
    target_name = parsed["name"]

    p = self.parser
    for idx, obj in enumerate(p.objects):
        if obj.source_file != source_file:
            continue
        if obj.object_type != obj_type:
            continue
        if obj.get_display_name() == target_name:
            return (idx, obj)

    return None
```

Change: Replace `get_object_name(obj.object_type, obj.attributes)` with `obj.get_display_name()`. Remove `from nagios_model import get_object_name` import if no longer used elsewhere in the file.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_stable_keys.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add nagios_service.py tests/test_stable_keys.py
git commit -m "fix: find_object_by_stable_key matches on display_name"
```

---

### Task 3: Backend — `_decode_and_find_object()` in templates route

**Files:**
- Modify: `routes/templates.py:70-73`

This function is used by the inheritance API. It receives Base64-encoded stable keys from the frontend and finds matching objects. It currently matches `obj.get_name() == obj_name` — must match `get_display_name()`.

**Step 1: Write the failing test**

Add to `tests/test_stable_keys.py`:

```python
import base64


def test_inheritance_api_resolves_correct_service(app_with_duplicate_services):
    """GET /api/templates/inheritance/<key> should find the right service by display_name."""
    with app_with_duplicate_services.app_context():
        from routes.helpers import get_service
        service = get_service()
        services = [o for o in service.get_objects() if o.object_type == "service"]

        # Build a stable key for the second service (windows-hosts PING)
        key2 = generate_stable_key_for_object(services[1])
        encoded_key = base64.b64encode(key2.encode()).decode()

        client = app_with_duplicate_services.test_client()
        resp = client.get(f"/api/templates/inheritance/{encoded_key}")
        # Should not 404 — must find the object
        assert resp.status_code != 404, f"Should find object for key: {key2}"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stable_keys.py::test_inheritance_api_resolves_correct_service -v`
Expected: FAIL with 404 because the key contains "PING on windows-hosts" but lookup matches against `get_name()` which returns "PING"

**Step 3: Implement the fix**

In `routes/templates.py`, change line 73:

From:
```python
            obj.get_name() == obj_name):
```

To:
```python
            obj.get_display_name() == obj_name):
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_stable_keys.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add routes/templates.py tests/test_stable_keys.py
git commit -m "fix: templates route matches stable key against display_name"
```

---

### Task 4: Frontend — `getObjectKey()` uses `display_name`

**Files:**
- Modify: `static/js/explorer/main.js:113-117`

**Step 1: Understand the current code**

```javascript
Explorer.getObjectKey = function(obj) {
    const nameComponent = obj.name ?? obj.display_name ?? `idx:${obj.global_index}`;
    return `${obj.source_file}|${obj.object_type}|${nameComponent}`;
};
```

Currently prefers `obj.name` (raw `service_description`). Must prefer `obj.display_name`.

**Step 2: Implement the fix**

Change to:

```javascript
/**
 * Generate a stable key for an object
 * Format: "source_file|object_type|display_name"
 * Uses display_name to ensure uniqueness — services with the same
 * service_description on different hosts get different keys.
 */
Explorer.getObjectKey = function(obj) {
    const nameComponent = obj.display_name ?? obj.name ?? `idx:${obj.global_index}`;
    return `${obj.source_file}|${obj.object_type}|${nameComponent}`;
};
```

Change: Swap `obj.name ?? obj.display_name` to `obj.display_name ?? obj.name`. The API always returns both fields from `to_dict()`, so `display_name` is always present when `name` is.

**Step 3: Commit**

```bash
git add static/js/explorer/main.js
git commit -m "fix: getObjectKey uses display_name for unique stable keys"
```

---

### Task 5: Frontend — `findObjectByKey()` in explorer matches `display_name`

**Files:**
- Modify: `static/js/explorer/main.js:122-132`

**Step 1: Understand the current code**

```javascript
Explorer.findObjectByKey = function(key) {
    const [source_file, object_type, ...nameParts] = key.split('|');
    const name = nameParts.join('|');
    return Explorer.state.allObjects.find(o => {
        const objName = o.name ?? o.display_name ?? `idx:${o.global_index}`;
        return o.source_file === source_file &&
               o.object_type === object_type &&
               objName === name;
    });
};
```

Must match the same fallback order as `getObjectKey()`.

**Step 2: Implement the fix**

```javascript
/**
 * Find an object by its stable key
 */
Explorer.findObjectByKey = function(key) {
    const [source_file, object_type, ...nameParts] = key.split('|');
    const name = nameParts.join('|');
    return Explorer.state.allObjects.find(o => {
        const objName = o.display_name ?? o.name ?? `idx:${o.global_index}`;
        return o.source_file === source_file &&
               o.object_type === object_type &&
               objName === name;
    });
};
```

Change: `o.name ?? o.display_name` → `o.display_name ?? o.name`

**Step 3: Commit**

```bash
git add static/js/explorer/main.js
git commit -m "fix: findObjectByKey matches display_name for consistency"
```

---

### Task 6: Frontend — `findObjectByKey()` in commit-dialog matches `display_name`

**Files:**
- Modify: `static/js/commit-dialog.js:592-611`

**Step 1: Understand the current code**

```javascript
function findObjectByKey(key, allObjects) {
    const stableKeyParts = decodeStableKey(key);
    if (stableKeyParts) {
        const { source_file, object_type, name } = stableKeyParts;
        return allObjects.find(o =>
            o.source_file === source_file &&
            o.object_type === object_type &&
            o.name === name    // <-- matches raw name only
        );
    }
    // ...
}
```

**Step 2: Implement the fix**

Change line 600 from:

```javascript
            o.name === name
```

To:

```javascript
            (o.display_name ?? o.name) === name
```

**Step 3: Commit**

```bash
git add static/js/commit-dialog.js
git commit -m "fix: commit dialog findObjectByKey matches display_name"
```

---

### Task 7: Fix test_reorder.py stable key construction

**Files:**
- Modify: `tests/test_reorder.py:114-115`

This test manually constructs stable keys like the frontend does. It must use `get_display_name()` now. For hostgroups, `get_name()` and `get_display_name()` return the same value, so this is a correctness fix for consistency.

**Step 1: Understand the current code**

```python
# Build stable key like frontend does: source_file|object_type|name
stable_key = f"{obj.source_file}|{obj.object_type}|{name}"
```

Where `name` comes from `obj.attributes.get('hostgroup_name')`.

**Step 2: Implement the fix**

Change to:

```python
# Build stable key like frontend does: source_file|object_type|display_name
stable_key = f"{obj.source_file}|{obj.object_type}|{obj.get_display_name()}"
```

**Step 3: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/test_reorder.py
git commit -m "fix: test_reorder uses display_name in stable key construction"
```

---

### Task 8: Run full test suite and manual verification

**Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 2: Manual verification with sample config**

Run:
```bash
python3 -c "
from nagios_parser import parse_config
from staging_manager import generate_stable_key_for_object
from collections import defaultdict
p = parse_config('sample-config')
keys = defaultdict(list)
for obj in p.objects:
    key = generate_stable_key_for_object(obj)
    keys[key].append(obj)
collisions = {k: v for k, v in keys.items() if len(v) > 1}
if collisions:
    for k, objs in collisions.items():
        print(f'COLLISION: {k}')
else:
    print(f'All {len(p.objects)} objects have unique stable keys')
"
```

Expected: "All 198 objects have unique stable keys"

**Step 3: Commit (if any fixups needed)**

If all good, no commit needed for this task.
