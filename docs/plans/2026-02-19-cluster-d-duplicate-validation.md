# Cluster D — Duplicate Validation at Creation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 3 duplicate-validation bugs: service duplicate check uses service_description alone instead of composite key host_name+service_description (009), no duplicate check at creation time (022), clone dialog accepts duplicate names without error (035).

**Architecture:** Fix the composite key check in `nagios_service.py` for service uniqueness, add pre-creation duplicate detection in the Create Object and Clone dialogs in `object-editor.js` / `dialogs.js`, checking against both disk objects and staged creations.

**Tech Stack:** Python/Flask, JavaScript. Key files: `nagios_service.py`, `static/js/explorer/dialogs.js`, `static/js/explorer/object-editor.js`.

---

### Task 1: Reproduce all 3 bugs with Playwright

**Files:**
- Read: `docs/test-discoveries/009-service-duplicate-check-ignores-host-name.md`
- Read: `docs/test-discoveries/022-no-duplicate-name-validation-at-creation.md`
- Read: `docs/test-discoveries/035-clone-accepts-duplicate-name.md`

**Step 1: Start app**
Run: `python3 app.py`, navigate to http://localhost:8080

**Step 2: Reproduce 009 — service duplicate check ignores host_name**
1. Verify services.cfg has a service named "PING" on host "linux-hosts"
2. Click "+" on services.cfg → create a new service
3. Set host_name to a DIFFERENT host (e.g., `web-prod-01`), set service_description to `PING`
4. Save — observe: error toast "service 'PING' already exists" (wrong, this is a valid config)
5. Take screenshot: `.playwright-mcp/repro-009.png`

**Step 3: Reproduce 022 — no duplicate check at creation**
1. Click "+" on hosts.cfg → new host
2. Type `web-prod-01` in the name field (this already exists)
3. Tab away / save
4. Observe: no duplicate warning, object is staged silently
5. Take screenshot

**Step 4: Reproduce 035 — clone accepts duplicate name**
1. Right-click `web-prod-01` → Clone
2. Enter name: `web-prod-01-copy` → Clone
3. Clone again: right-click `web-prod-01` → Clone → name: `web-prod-01-copy`
4. Observe: second clone succeeds without error, two objects with same name appear
5. Take screenshot

---

### Task 2: Fix 009 — Service composite key duplicate check

**Files:**
- Read + Modify: `nagios_service.py`

**Step 1: Find duplicate checking logic**
Read `nagios_service.py`. Search for where service creation validates uniqueness. Look for code that checks `service_description` against existing services.

**Step 2: Find the composite key requirement**
In Nagios, a service is unique by `(host_name, service_description)`. Find where the code compares only `service_description` and change it to compare both fields:

```python
# Before (wrong):
if new_attrs.get('service_description') == existing.attributes.get('service_description'):
    # duplicate

# After (correct):
if (new_attrs.get('service_description') == existing.attributes.get('service_description') and
        new_attrs.get('host_name') == existing.attributes.get('host_name')):
    # duplicate
```

Note: hostgroup-based services (using `hostgroup_name` instead of `host_name`) are also valid — the check should only flag duplicates when BOTH fields match.

**Step 3: Validate with Playwright**
Reproduce Task 1 Step 2. PING on web-prod-01 should now be accepted (no duplicate error). PING on linux-hosts should still be rejected as a duplicate.

**Step 4: Run ruff**
Run: `ruff check nagios_service.py`

**Step 5: Commit**
```bash
git add nagios_service.py
git commit -m "fix: service duplicate check uses composite key (host_name, service_description)

Fixes #009 — duplicate detection used service_description alone, rejecting
valid configs where multiple hosts each have a service with the same name.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 022 — Add pre-creation duplicate check in Create Object dialog

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js` AND/OR `static/js/explorer/dialogs.js`

**Step 1: Find the Create Object form submission handler**
Read `static/js/explorer/object-editor.js` and `static/js/explorer/dialogs.js`. Search for where a new object is staged from the creation form. Find where the object name is set and where `stagedCreations` is populated.

**Step 2: Find where to add the duplicate check**
Before staging the creation, check:
1. `state.allObjects` for an existing object of the same type with the same name
2. `state.stagedCreations` (or equivalent) for any already-staged creation with the same name
3. For services: use the composite key (host_name + service_description)

```javascript
function checkDuplicateName(objectType, name, hostName) {
    // For services, use composite key
    const isService = objectType === 'service';

    const existsInObjects = state.allObjects.some(obj => {
        if (obj.object_type !== objectType) { return false; }
        if (isService) {
            return obj.attributes.service_description === name &&
                   obj.attributes.host_name === hostName;
        }
        const nameField = Explorer.getNameField(objectType);
        return obj.attributes[nameField] === name;
    });

    const existsInStaged = /* check stagedCreations similarly */;

    return existsInObjects || existsInStaged;
}
```

**Step 3: Show inline error or prevent staging**
If duplicate detected, show an inline error in the form (not just a toast) and prevent the object from being staged:

```javascript
if (checkDuplicateName(objectType, name, hostName)) {
    showFieldError(nameField, `A ${objectType} named '${name}' already exists`);
    return; // Don't stage
}
```

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 3. Typing `web-prod-01` in the name field and blurring should show an inline error preventing staging.

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: add pre-creation duplicate name validation to Create Object form

Fixes #022 — duplicates were only surfaced post-hoc via Suggestions panel;
users could silently stage duplicate objects until apply-time failure.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 035 — Add duplicate check to Clone dialog

**Files:**
- Read + Modify: `static/js/explorer/dialogs.js` (Clone dialog submit handler)

**Step 1: Find the Clone dialog submit handler**
Read `static/js/explorer/dialogs.js`. Search for the clone dialog confirmation handler (likely `confirmClone` or similar).

**Step 2: Add duplicate check before cloning**
Before staging the cloned object, call `checkDuplicateName` (created in Task 3 or inline here):

```javascript
async function confirmClone() {
    const newName = document.getElementById('cloneNameInput').value.trim();
    if (!newName) { return; }

    if (checkDuplicateName(objectBeingCloned.object_type, newName)) {
        showDialogError('cloneDialog', `A ${objectBeingCloned.object_type} named '${newName}' already exists`);
        return;
    }

    // ... existing clone logic
}
```

**Step 3: Validate with Playwright**
Reproduce Task 1 Step 4. Second clone with same name should show inline error in dialog.

**Step 4: Run ESLint**

**Step 5: Commit**
```bash
git add static/js/explorer/dialogs.js
git commit -m "fix: clone dialog validates for duplicate names before staging

Fixes #035 — cloning to an existing name silently created two objects with
the same name, causing Nagios validation failure at apply time.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Final Playwright validation

Verify:
- [ ] PING on different host is accepted (not flagged as duplicate) (009)
- [ ] Typing existing name in Create dialog shows inline error (022)
- [ ] Clone dialog rejects duplicate name with inline error (035)

Run: `python3 -m pytest tests/ -v`
