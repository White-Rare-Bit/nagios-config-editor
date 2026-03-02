# L10 — `static/js/explorer/impact-section.js` — MODIFY

## Purpose
Add `?candidate=1` to reference/inheritance API calls. Remove `overlayStagedTemplateEdits()`. Rename `getStagedDisplayName()` alias to `getDisplayName()`.

## Removal Audit
- `overlayStagedTemplateEdits(resolvedAttrs, chain, obj)` (lines 194-243) → REMOVED. This function overlaid pending edits from templates onto resolved attributes. In candidate mode, the inheritance endpoint already returns resolved attributes that include candidate edits — no client-side overlay needed.
- `state.pendingEdits.get(tmplObj.global_index)` (line 215) → REMOVED with function. No client-side pending edits.
- `state.pendingEdits.size === 0` check → NOT PRESENT in this file (only in badge-issues.js).
- Call to `overlayStagedTemplateEdits()` at line 179 → REMOVED.
- Bug 019 comment block (lines 176-178, 190-192) → REMOVED with function.

No mutations occur in this file — it is purely a read/render module. All data comes from API calls that already go through the candidate pipeline when `?candidate=1` is appended. No audit logging is required for read-only rendering.

## Changes

**1. Rename `getStagedDisplayName` alias to `getDisplayName`** (lines 31-33):
```javascript
// BEFORE:
function getStagedDisplayName(obj) {
    return Explorer.getStagedDisplayName(obj);
}

// AFTER:
function getDisplayName(obj) {
    return Explorer.getDisplayName(obj);
}
```
In candidate mode, `obj.attributes` already reflects edits, so the `Explorer.getDisplayName()` helper (simplified in L07-state-management.md) returns the name from attributes directly.

**2. Add candidate suffix to object-references call** (line 92):
```javascript
// BEFORE:
const result = await ApiClient.get(`/api/object-references/${obj.global_index}`);

// AFTER:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const result = await ApiClient.get(`/api/object-references/${obj.global_index}${suffix}`);
```

**3. Add candidate suffix to inheritance fetch** (line 173):
```javascript
// BEFORE:
const inheritData = await Explorer.fetchInheritance(stableKey);

// AFTER:
const suffix = Explorer.state.candidateActive ? '?candidate=1' : '';
const inheritData = await Explorer.fetchInheritance(stableKey, suffix);
```
Note: The `suffix` variable is declared locally in each function scope (`loadImpactAndRelationships` and `gatherInheritanceData`) because they are separate async functions.

**4. Remove call to `overlayStagedTemplateEdits()`** (line 179) and the associated Bug 019 comment (lines 176-178).

**5. Remove `overlayStagedTemplateEdits()` function** (lines 190-243) — entire function body including doc comment. Server-side inheritance resolution in candidate mode already includes edits; this client-side overlay is dead code.

## Detailed Staging References

All staging references found via `grep -n stag impact-section.js`:

| Line(s) | Reference | Action |
|---------|-----------|--------|
| 31-33 | `function getStagedDisplayName(obj) { return Explorer.getStagedDisplayName(obj); }` | RENAME → `getDisplayName(obj)` delegating to `Explorer.getDisplayName(obj)` |
| 176-178 | `// Bug 019: Overlay staged template edits onto resolved attrs.` comment block | REMOVE with function call |
| 179 | Call to `overlayStagedTemplateEdits(resolvedAttrs, chain, obj)` | REMOVE — candidate inheritance endpoint returns resolved attrs including edits |
| 190-192 | Function doc comment referencing "staged edits" | REMOVE with function |
| 194-243 | `overlayStagedTemplateEdits()` function body | REMOVE entirely (50 lines of dead code) |
| 215 | `state.pendingEdits.get(tmplObj.global_index)` inside removed function | REMOVE with function |
| 218 | `// Apply each changed attribute from the staged edit` comment | REMOVE with function |
| 224 | `// Update or add the resolved attribute with staged value` comment | REMOVE with function |
| 489 | `getStagedDisplayName(ref.object)` in `renderIncomingSubsection` | RENAME → `getDisplayName(ref.object)` |
| 524 | `getStagedDisplayName(ref.object)` in `renderOutgoingSubsection` | RENAME → `getDisplayName(ref.object)` |
| 566 | `getStagedDisplayName(item.object)` in `renderMembershipSubsection` (memberOf) | RENAME → `getDisplayName(item.object)` |
| 600 | `getStagedDisplayName(m.object)` in `renderMembershipSubsection` (members) | RENAME → `getDisplayName(m.object)` |

**Total: 12 staging references removed/renamed. Zero staging references remain after migration.**

## Error Handling

Existing error handling is preserved unchanged:
- Line 92-142: `try/catch` around `ApiClient.get('/api/object-references/...')` with `console.error('Failed to load object references:', error)`.
- Line 171-183: `try/catch` around `Explorer.fetchInheritance(stableKey, suffix)` with `console.error('Error loading resolved attributes:', error)`.
- Stale request detection via `impactRequestId` counter (Bug 003-relationships) is preserved.

No new error paths are introduced. The candidate suffix is a passive query parameter — if the candidate session is not active, the endpoint returns live config data as before.

## UI Visual Parity

No visual changes. The impact section renders identically:
- Same template ancestry chain layout
- Same parent hosts chain layout
- Same resolved attributes table
- Same incoming/outgoing reference grids
- Same group membership display

The only difference is that in candidate mode, the data comes from the candidate config via `?candidate=1` instead of live config with client-side overlays. The rendered output is visually identical.

## Change Tracking

- L00-migration-inventory.md section 2.2: `impact-section.js` — 5 refs → [covered]
- This plan accounts for all 12 staging-related references (the inventory count of 5 was based on `grep stag`; the full list above includes comments and call sites within removed functions).

## Verification
- Impact section loads in candidate mode with `?candidate=1` on API calls
- Resolved attributes reflect candidate edits (server-side, not client-side overlay)
- Display names show candidate values via `getDisplayName()`
- No console errors when navigating between objects
- Template inheritance chain renders correctly
- Incoming/outgoing references display correctly
- `npm run lint:js` passes with no errors
- Playwright: verify impact section renders for a host with templates in candidate mode; confirm resolved attributes table shows expected inherited values

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | This file is read-only (no mutations). Adds `?candidate=1` to read from candidate, not live. No writes occur. |
| 2 | UI visual parity | COMPLIANT | No visual changes. Same rendering, different data source in candidate mode. |
| 3 | Full audit logging | N/A | Read-only rendering module — no mutations to audit. API endpoints called here handle their own logging server-side. |
| 4 | Proper error handling | COMPLIANT | Existing `try/catch` blocks with `console.error` preserved. Stale request detection preserved. No new error paths introduced. |
| 5 | Dead code deletion | COMPLIANT | `overlayStagedTemplateEdits()` (50 lines) deleted — zero use in candidate model. All `state.pendingEdits` references removed. |
| 6 | Full functionality migration | COMPLIANT | Inheritance resolution migrated from client-side overlay (`overlayStagedTemplateEdits`) to server-side via `?candidate=1` on the inheritance endpoint. Display name resolution migrated from `getStagedDisplayName` to `getDisplayName`. No functionality dropped. |
| 7 | Palo Alto candidate model | COMPLIANT | Reads from candidate config via `?candidate=1` suffix. No client-side staging state. Server is the source of truth. |
| 8 | Change tracking document | COMPLIANT | Cross-referenced with L00-migration-inventory.md. All 12 staging references enumerated with line numbers and actions. |
| 9 | Complete planning before implementation | COMPLIANT | All changes fully specified with before/after code, line numbers, and detailed reference table. |
| 10 | Linting enforcement | COMPLIANT | `npm run lint:js` included in verification checklist. |
| 11 | Playwright validation | COMPLIANT | Playwright test specified: verify impact section renders with resolved attributes in candidate mode. |
