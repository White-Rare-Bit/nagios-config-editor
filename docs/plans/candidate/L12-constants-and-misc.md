# L12: JS Constants and Misc — MODIFY

**Layer:** 12 — Staging Removal
**Action:** MODIFY
**Paths:** `static/js/explorer/constants.js`, `static/js/docs.js`, `static/js/base-state.js`
**Dependencies:** L07 (state management rewritten), L09 (supporting JS rewritten)
**Goal:** Remove staging references from 3 small JS files not covered by other L-plans.

---

## File 1: `static/js/explorer/constants.js`

### Removal Audit

| Line(s) | Code | Action |
|---------|------|--------|
| 247 | `@param {number\|null} [excludeStagedIndex=null] - staged creation index to skip` | REWRITE — remove param from JSDoc |
| 250 | `Explorer.checkDuplicateName = function(objectType, name, attributes, excludeStagedIndex)` | REWRITE — remove `excludeStagedIndex` parameter, add `excludeObj` parameter for self-exclusion |
| 277-290 | `// Check against other staged creations` block (`state.stagedCreations.findIndex(...)`) | REMOVE — no client-side staged creations in candidate mode. Candidate objects are already in `state.allObjects` and checked by the existing on-disk block above. |

### Changes

Rewrite `checkDuplicateName` to remove the staged creations check while preserving self-exclusion logic:

**Rationale for `excludeObj`:** In the old code, `excludeStagedIndex` prevented a staged creation from flagging itself as a duplicate when being re-validated. In candidate mode, candidate-created objects appear inside `state.allObjects` (they are real objects on the candidate config). Without self-exclusion, editing an existing object's non-name attributes would cause `checkDuplicateName` to find the object itself and report a false duplicate. The `excludeObj` parameter lets callers pass the object being edited so it is skipped during the scan.

Before (lines 243-293):
```javascript
    /**
     * Check whether a name would be a duplicate for the given object type.
     * ...
     * @param {number|null} [excludeStagedIndex=null] - staged creation index to skip
     * @returns {{isDuplicate: boolean, location: string}} result
     */
    Explorer.checkDuplicateName = function(objectType, name, attributes, excludeStagedIndex) {
        ...
        // Check against other staged creations
        const dupStaged = state.stagedCreations.findIndex((sc, idx) => {
            ...
        });
        if (dupStaged !== -1) {
            return {isDuplicate: true, location: 'staged'};
        }

        return {isDuplicate: false, location: ''};
    };
```

After:
```javascript
    /**
     * Check whether a name would be a duplicate for the given object type.
     * For host-scoped types (service, serviceescalation, servicedependency),
     * uses composite key (name + host_name/hostgroup_name).
     *
     * @param {string} objectType - e.g. 'host', 'service'
     * @param {string} name - the name value to check
     * @param {Object} attributes - full attributes of the object being checked
     * @param {Object|null} [excludeObj=null] - object to exclude from check (self-exclusion when editing)
     * @returns {{isDuplicate: boolean, location: string}} result
     */
    Explorer.checkDuplicateName = function(objectType, name, attributes, excludeObj) {
        if (!name) {return {isDuplicate: false, location: ''};}

        const state = Explorer.state;
        if (!state || !Array.isArray(state.allObjects)) {
            return {isDuplicate: false, location: ''};
        }
        const c = Explorer.constants;
        const nameField = c.nameFields[objectType] || 'name';
        const isHostScoped = HOST_SCOPED_TYPES.has(objectType);
        const hostScope = isHostScoped
            ? (attributes.host_name || attributes.hostgroup_name || '')
            : '';

        // Check against all objects (includes candidate-created objects)
        const existingObj = state.allObjects.find(obj => {
            // Self-exclusion: skip the object being edited
            if (excludeObj && obj === excludeObj) {return false;}
            if (obj.object_type !== objectType) {return false;}
            const objName = obj.attributes?.[nameField] || obj.attributes?.name || '';
            if (objName !== name) {return false;}
            if (isHostScoped) {
                const objHost = obj.attributes?.host_name || obj.attributes?.hostgroup_name || '';
                return objHost === hostScope;
            }
            return true;
        });
        if (existingObj) {
            const file = (existingObj.source_file || '').split('/').pop();
            return {isDuplicate: true, location: file};
        }

        return {isDuplicate: false, location: ''};
    };
```

### Caller Migration

Callers of `checkDuplicateName` that previously passed `excludeStagedIndex` must be updated to pass `excludeObj` instead (handled by L08-dialogs.md and L08-object-editor.md):

| File | Old Call | New Call |
|------|----------|----------|
| `dialogs.js:433` | `checkDuplicateName(type, name, attrs, state.newObjectStagedIndex)` | `checkDuplicateName(type, name, attrs, editingObject)` where `editingObject` is the `allObjects` entry being edited, or `null` for new creations |
| `context-menu.js:640` | `checkDuplicateName(type, name, attrs, null)` | `checkDuplicateName(type, name, attrs, null)` (unchanged -- clones are always new, so no self-exclusion needed) |

### Error Message Migration

The old location string `'staged'` is no longer returned. Callers that check `dupCheck.location === 'staged'` (context-menu.js:644, dialogs.js:440) must be updated to remove that branch. All duplicates now report the file name. This is handled by L08-dialogs.md and L08-object-editor.md (context-menu clone path) respectively.

---

## File 2: `static/js/docs.js`

### Removal Audit

| Line | Code | Action |
|------|------|--------|
| 22 | `{ slug: 'staging-system', label: 'Staging System' },` | KEEP slug, update label only |
| 40 | `{ slug: 'data-flow-staging', label: 'Data Flow & Staging Internals' },` | KEEP slug, update label only |

### Slug Preservation Rationale (Commandment 2 — UI Visual Parity)

The doc navigation slugs (`staging-system`, `data-flow-staging`) appear as URL hash fragments (e.g., `#app/staging-system`). These are user-visible URLs that may be bookmarked, shared in runbooks, or linked from external documentation. Changing them would break existing references.

**Decision:** Keep the existing slugs unchanged. Update only the display labels to reflect candidate terminology. The slug is an internal identifier that happens to appear in URLs; the label is what users see in the navigation tree.

If the doc pages are later replaced with candidate-specific content (L13-doc-templates.md), the slug must remain `staging-system` and `data-flow-staging` to preserve URL stability, or a redirect mechanism must be added first.

### Changes

Line 22 -- before:
```javascript
            { slug: 'staging-system', label: 'Staging System' },
```
After:
```javascript
            { slug: 'staging-system', label: 'Candidate System' },
```

Line 40 -- before:
```javascript
            { slug: 'data-flow-staging', label: 'Data Flow & Staging Internals' },
```
After:
```javascript
            { slug: 'data-flow-staging', label: 'Data Flow & Candidate Internals' },
```

**Impact on L13-doc-templates.md and L13-doc-text-updates.md:** Those plans must also preserve the slug values. Any `#app/staging-system` link targets in HTML templates must NOT be changed to `#app/candidate-system` -- they must remain as-is to match the preserved slugs. The L13 plans must be updated for compliance with this constraint. Specifically:
- `templates/docs/staging-system.html` must keep its filename (since it maps to the `staging-system` slug via `/api/docs/<slug>`)
- `templates/docs/data-flow-staging.html` must keep its filename
- All `href="#app/staging-system"` and `href="#app/data-flow-staging"` links across doc templates must remain unchanged

Note: corresponding doc content templates are handled by L13-doc-templates.md (which must be updated to comply with slug preservation).

---

## File 3: `static/js/base-state.js`

### Removal Audit

| Line | Code | Action |
|------|------|--------|
| 19 | `lockOwner: null,` | KEEP -- still used by L09-lock-manager.md after migration |

### Rationale for Keeping `lockOwner`

L09-lock-manager.md (line 33) writes `baseState.lockOwner = session.session_id` after migration. The field is repurposed to hold the candidate session ID instead of the staging lock owner, but it is still read and written by the rewritten lock-manager. Removing it here would cause a runtime error in `checkLockStatus()`.

**No changes to this file.** The `lockOwner` field in `baseState` is retained. The verification grep below is updated to not flag `lockOwner` as a residual staging reference.

---

## Change Tracking

| File | Lines Changed | Type | Description |
|------|--------------|------|-------------|
| `static/js/explorer/constants.js` | 243-293 | REWRITE | `checkDuplicateName`: remove `excludeStagedIndex` param, add `excludeObj` param, remove staged creations block, add state guard |
| `static/js/docs.js` | 22 | MODIFY | Update label text only (slug preserved) |
| `static/js/docs.js` | 40 | MODIFY | Update label text only (slug preserved) |
| `static/js/base-state.js` | (none) | NO CHANGE | `lockOwner` retained per L09 dependency |

**Net line delta:** ~-15 lines (removing staged creations block, simplifying JSDoc)

---

## Verification

```bash
# Lint check
npx eslint static/js/explorer/constants.js static/js/docs.js static/js/base-state.js

# Search for remaining staging references in constants.js and docs.js
# (base-state.js is excluded because lockOwner is intentionally retained)
grep -n 'stagedCreations\|stagedMoves\|stagedObjectDeletions\|excludeStagedIndex' \
    static/js/explorer/constants.js static/js/docs.js static/js/base-state.js
# Should return no matches

# Verify slug preservation -- these slugs must still exist in docs.js
grep -n "slug: 'staging-system'" static/js/docs.js
grep -n "slug: 'data-flow-staging'" static/js/docs.js
# Should return exactly one match each

# Verify checkDuplicateName still detects duplicates correctly
# (manual test: create two hosts with the same name, confirm duplicate warning)

# Verify self-exclusion works
# (manual test: edit a host's address but not its name, confirm no false duplicate)
```

### Playwright Validation

```bash
# E2E: Duplicate name detection
npx playwright test --grep "duplicate name"
```

Playwright test coverage for `checkDuplicateName` functionality:

1. **Duplicate detection -- create object with existing name:**
   - Create a new host with a name that already exists on disk
   - Assert: toast error appears with "already exists in <filename>"
   - Assert: object is NOT created

2. **Self-exclusion -- edit non-name attribute of existing object:**
   - Select an existing host, change its `address` attribute
   - Assert: no duplicate name error appears
   - Assert: change is recorded successfully

3. **Clone duplicate detection:**
   - Clone a host without changing the name suffix
   - Clone again with the same suffix
   - Assert: second clone shows duplicate error

4. **Doc navigation slug stability:**
   - Navigate to `/docs#app/staging-system`
   - Assert: "Candidate System" page content loads
   - Assert: URL hash remains `#app/staging-system`

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | `checkDuplicateName` is a read-only check against `state.allObjects` (in-memory). No disk writes. |
| 2 | UI visual parity -- no user-visible slug changes | COMPLIANT | Slugs `staging-system` and `data-flow-staging` are preserved in `docs.js`. Only display labels are updated. L13 plans flagged for corresponding slug preservation. |
| 3 | Full audit logging | COMPLIANT | These are client-side-only UI changes (label text, duplicate check logic). No server mutations occur, so no audit log entries are needed. The candidate system's server-side mutations (create, edit, delete) are audit-logged in their respective L-plans (L01-L05). |
| 4 | Proper error handling | COMPLIANT | Added `state`/`allObjects` null guard in `checkDuplicateName`. Function returns safe default `{isDuplicate: false}` when state is unavailable. |
| 5 | Dead code deletion | COMPLIANT | `stagedCreations` check block removed. `excludeStagedIndex` parameter removed. No dead code remains. `lockOwner` is NOT dead code (used by L09). |
| 6 | Full functionality migration -- checkDuplicateName must still work | COMPLIANT | Self-exclusion preserved via `excludeObj` parameter (replaces `excludeStagedIndex`). Duplicate detection against all objects (disk + candidate) via `allObjects`. Caller migration table provided. Error message branch (`location === 'staged'`) migration documented. |
| 7 | Palo Alto candidate model | COMPLIANT | Terminology updated in labels. Architecture assumes candidate objects appear in `allObjects` (server-side candidate config is the source of truth). |
| 8 | Change tracking document | COMPLIANT | Change tracking table added with file, lines, type, and description. |
| 9 | Complete planning before implementation | COMPLIANT | Self-exclusion rationale documented. Caller migration table provided. Cross-plan impacts on L13 identified. `lockOwner` retention justified with L09 dependency evidence. |
| 10 | Linting enforcement | COMPLIANT | `npx eslint` verification step included for all 3 files. |
| 11 | Playwright validation | COMPLIANT | Four Playwright test scenarios specified: duplicate detection, self-exclusion, clone duplicates, and doc slug stability. |
