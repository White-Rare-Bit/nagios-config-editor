# 023 — Null Reference Crash in impact-section.js During stageCurrentChanges on New Object

**Phase:** 7 — Error Handling
**Severity:** Major
**Category:** JavaScript Error / Crash

## Steps to Reproduce

1. Open the Object Explorer
2. Click "+" on any file (e.g., `hosts.cfg`) to open the Create Object dialog
3. The new unnamed object form opens (stage count increments immediately)
4. Type a name in the "Enter name..." breadcrumb field
5. Trigger `stageCurrentChanges()` — this can happen when navigating away or the auto-save timer fires on a new object that has not yet loaded its relationships

Observed via console (simulates the auto-save path):
```js
await window.Explorer.stageCurrentChanges();
```

## Actual Behavior

```
TypeError: Cannot read properties of null (reading 'attributes')
    at gatherInheritanceData (impact-section.js:141:29)
    at Object.loadImpactAndRelationships (impact-section.js:67:39)
    at Object.stageCurrentChanges (object-editor.js:1225:18)
```

The center pane closes unexpectedly and shows "No object selected".
The name typed by the user is NOT persisted to the staged object (attributes remain empty).

## Expected Behavior

`stageCurrentChanges` should guard against null object state in `gatherInheritanceData`. For a newly created object with no backing data yet, `loadImpactAndRelationships` should no-op rather than crash.

## Root Cause (Hypothesis)

`impact-section.js:141` calls `obj.attributes` where `obj` is null — likely because the new staged object hasn't been looked up in `state.allObjects` yet (it was just created and the object list may not have refreshed to include it).

## Additional Notes

- Also observed: `GET /api/objects/create` returns 404. The UI attempted to call this non-existent endpoint at some point during the create flow.
- The crash may be intermittent — depends on timing of auto-save vs object list refresh
- When the crash occurs, the staged empty object remains in the staging state but is inaccessible via the UI (no name displayed, form closed)

## Screenshot

`screenshots/phase7-zero-attr-object.png`
