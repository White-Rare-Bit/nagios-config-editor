# 026 — Drop payload with empty object item corrupts staged state, crashes renderer

**Phase:** 8 — Drag & Drop Stress
**Severity:** Major (cascading effect; requires page reload to recover)
**Category:** Error Handling / Drag-and-Drop / Crash

## Steps to Reproduce

1. Drop event is received with `objects` array containing an empty object `{}` (or any object missing an `attributes` field):
   ```json
   { "type": "objects", "objects": [{}] }
   ```
2. The drop is processed by `handleFileDrop` → `processObject`
3. A staged move entry is stored with `object.attributes = undefined` (since `{}.attributes` is `undefined`)
4. Any subsequent drag-and-drop operation (or file-expand) triggers `renderTargetPane`
5. `buildPendingObjectRow` calls `Explorer.isObjectTemplate(item.move.object)`
6. **CRASH:** `TypeError: Cannot read properties of undefined (reading 'register')`

## Actual Behavior

- `processObject` does `if (!objData) {return;}` which correctly skips `null`/`undefined`, but passes through `{}` (truthy empty object)
- Stored staged move: `{ object: { source_file: undefined, object_type: undefined, name: undefined, attributes: undefined } }`
- On next render, `isObjectTemplate` accesses `obj.attributes.register` where `obj.attributes === undefined` → crash
- The crash breaks ALL subsequent drag-and-drop on the page until reload

## Expected Behavior

`processObject` should validate that `objData.attributes` is a non-null object before proceeding. `isObjectTemplate` should also guard: `if (!obj || !obj.attributes) return false`.

## Technical Details

- `file-operations.js` → `processObject`: missing `if (!objData.attributes) return;`
- `constants.js:143` → `Explorer.isObjectTemplate`: `obj.attributes.register` accessed without null check

## Impact

While not exploitable through normal UI interaction, this crash state can be triggered if:
- A browser extension injects a drag event with partial data
- A race condition delivers corrupted state from the backend
- During future refactoring if staging data is partially initialized

Once triggered, all drag-and-drop operations fail until page reload, losing any unsaved staging state.

## Screenshot

See: `screenshots/phase8-drag-cross-file.png`
