# L10 — `static/js/explorer/relations-loader.js` — MODIFY

## Purpose
Add `?candidate=1` to inheritance and object-references API calls. Simplify effective attribute helpers.

No live configuration is mutated by this module. All API calls are read-only `GET` requests. The `?candidate=1` suffix directs the server to return data from the candidate directory rather than the running config (Palo Alto model: copy config to candidate, edit candidate, apply candidate to live).

## Removal Audit
- `getEffectiveAttrs(o)` local wrapper (line 19) → SIMPLIFIED. Now just returns `Explorer.getEffectiveAttributes(o)` which is itself a passthrough to `o.attributes` in candidate mode.
- `getEffectiveName(obj)` local wrapper (line 24) → SIMPLIFIED. Same pattern.
- `getStagedDisplayName(obj)` local wrapper (line 29) → SIMPLIFIED. Returns `obj.display_name`.
- These wrappers stay as convenience aliases but their implementations simplify because the underlying Explorer methods are now passthroughs (updated in L07-state-management.md).

No staging-specific references (`pendingEdits`, `stagedObjectDeletions`, `saveStagedChanges`) exist directly in this file. The helper wrappers delegate to Explorer methods.

No functionality lost — in candidate mode, objects from the server already have correct attributes.

## Changes

**1. Add candidate suffix to inheritance API call** (line 123):
```javascript
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const response = await fetch(`/api/inheritance/${obj.object_type}/${encodeURIComponent(obj.name || obj.display_name)}${suffix}`);
```

Note: The actual endpoint is `/api/inheritance/` (not `/api/templates/inheritance/`), as verified in the source code.

**2. Add candidate suffix to object-references calls** (lines 378, 654):
```javascript
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/object-references/${obj.global_index}${suffix}`);
```

**3. Helper wrappers stay but are now trivial** — No code changes needed in this file since they delegate to Explorer methods which were simplified in L07-state-management.md. The wrappers at lines 19-31 already just call `Explorer.getEffectiveAttributes()`, `Explorer.getEffectiveName()`, and `Explorer.getStagedDisplayName()`.

## UI Visual Parity

The following UI elements must remain visually identical after migration:

- **Inheritance chain display**: Same chain rendering with template names and arrows.
- **Reference relationships**: Same reference cards with object type labels and names.
- **Members section**: Same group membership rendering.
- **`ref-name` spans**: Same `getStagedDisplayName()` output in title and content attributes.

No CSS classes are added, removed, or renamed. No DOM structure changes.

## Audit Logging

This module is read-only — it calls `GET /api/inheritance/...` and `GET /api/object-references/...`, both non-mutating endpoints. No audit logging is required for read-only operations. The backend endpoints log their own execution through the application logging system.

## Error Handling

Existing error handling is preserved:

| Function | Error Handling | Status |
|----------|---------------|--------|
| Inheritance fetch (line 122-134) | `try/catch` with `container.innerHTML = error message` | PRESERVED |
| `result.error` check (line 126) | Guard clause with error display in container | PRESERVED |
| Object-references fetch (line 378) | ApiClient handles errors via `{success, error}` pattern | PRESERVED |
| Object-references fetch (line 654) | ApiClient handles errors via `{success, error}` pattern | PRESERVED |

No error paths are removed or weakened.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Add `?candidate=1` suffix to inheritance API call (line 123) | [ ] |
| 2 | Add `?candidate=1` suffix to object-references call (line 378) | [ ] |
| 3 | Add `?candidate=1` suffix to object-references call (line 654) | [ ] |
| 4 | Verify helper wrappers (lines 19-31) delegate correctly after L07 changes | [ ] |
| 5 | `npm run lint:js` passes | [ ] |
| 6 | Playwright validation passes (see below) | [ ] |

## Verification
- Relations panel loads in candidate mode
- Inheritance chain displays correctly with candidate data
- Reference relationships display correctly with candidate data
- `getStagedDisplayName()` shows correct names for candidate objects
- No references to `pendingEdits` or `stagedObjectDeletions` directly in this file
- `npm run lint:js` passes
- `python3 -m ruff check` passes (no Python in this file, verify no cross-file breakage)
- No console errors in browser devtools

## Playwright Validation

**Test: Inheritance chain renders in candidate mode**
1. Navigate to explorer page with candidate session active
2. Select an object that uses templates (e.g., a host with a template)
3. Assert inheritance chain section renders with template names
4. Assert chain data reflects candidate state

**Test: References section renders in candidate mode**
1. Navigate to explorer page with candidate session active
2. Select an object with known references (e.g., a service referencing a host)
3. Assert references section renders with correct relationships
4. Assert reference names match candidate data

**Test: No console errors on relations load**
1. Navigate to explorer page
2. Select various objects
3. Assert no `console.error` messages related to relations-loader

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Module is read-only. `?candidate=1` reads candidate directory data. No mutations. |
| 2 | UI visual parity | COMPLIANT | Inheritance chains, references, and member sections render identically. See "UI Visual Parity" section. |
| 3 | Full audit logging | COMPLIANT | Read-only GET requests — no audit logging needed. Backend logs its own execution. See "Audit Logging" section. |
| 4 | Proper error handling | COMPLIANT | All existing try/catch blocks and guard clauses preserved. See "Error Handling" section. |
| 5 | Dead code deletion | N/A | No staging-specific code exists directly in this file. Helper wrappers are still used (called 20+ times) and are not dead code. |
| 6 | Full functionality migration | COMPLIANT | All relations functionality preserved — inheritance, references, and members all get candidate-aware data via `?candidate=1`. |
| 7 | Palo Alto candidate model | COMPLIANT | `?candidate=1` suffix follows copy-edit-apply model. Relations display candidate state. |
| 8 | Change tracking document | COMPLIANT | See "Change Tracking" section with 6 items. |
| 9 | Complete planning before implementation | COMPLIANT | This plan fully specifies all changes before any code changes. |
| 10 | Linting enforcement | COMPLIANT | `npm run lint:js` required in verification and change tracking (item 5). |
| 11 | Playwright validation | COMPLIANT | Three Playwright test scenarios defined in "Playwright Validation" section. |
