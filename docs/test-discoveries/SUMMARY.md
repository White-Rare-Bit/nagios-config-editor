# E2E Playwright Adversarial Test — Summary

**Test run:** 2026-02-18 – 2026-02-19
**Tester:** Claude (Playwright MCP, adversarial exploration)
**Target:** Nagios Bulk Editor — Object Explorer + Graph View + supporting pages
**Config:** 30 phases, 85 documented findings (84 bugs + 1 design assessment)

---

## Total Issues by Severity

| Severity | Count | Notes |
|----------|-------|-------|
| **Critical** | 11 | App crashes, silent data corruption, broken core features |
| **Major** | 39 | Significant UX failures, data integrity gaps, missing safeguards |
| **Minor** | 33 | Cosmetic issues, edge-case UX gaps, missing polish |
| **Cosmetic** | 1 | Design gap (audit log: undo not recorded) |
| Assessment | 1 | Non-bug design evaluation (#053 — Graph Quick Views) |
| **Total** | **85** | |

---

## Issues by Category

| Category | Count | Example Issues |
|----------|-------|----------------|
| Data Integrity / Config Correctness | 15 | #009, #014, #015, #033, #035, #038, #067, #072 |
| Graph View — Missing / Broken Functionality | 14 | #044 (all quick views broken), #049, #047, #050 |
| Staging / State Management | 12 | #001-staging, #019, #020, #025, #026, #028, #039 |
| UI / Stale State / Misleading Feedback | 10 | #003-stale, #017, #040, #041, #042, #043 |
| Validation / Error Handling | 9 | #009, #014, #015, #022, #023, #034, #064 |
| Autocomplete / Reference Fields | 7 | #008, #013, #016, #058, #066 |
| Audit Log / Observability | 4 | #068, #069, #070, #071 |
| Undo Stack | 4 | #020, #027, #028, #070 |
| Bulk Edit / Rename | 5 | #003, #029, #030, #032, #033 |
| File / Folder Operations | 4 | #003-delete, #037, #038, #021 |
| Clone / Create Workflows | 5 | #007, #022, #035, #036, #063 |
| Keyboard / Accessibility | 4 | #004, #005, #006, #012 |
| Lock / Multi-Session | 3 | #002-session, #042, #067 |
| Template Inheritance | 3 | #017, #018/075 (duplicate finding), #019 |

---

## Phases with Most Issues

| Phase | Issues | Notable |
|-------|--------|---------|
| Phase 19 — Graph View (044–057) | 14 | Critical: all quick views broken (#044), servicegroups stranded (#049) |
| Phase 4 — Create Objects | 9 | Critical: check_command arg validation (#014, #015) |
| Phase 21 — Search, Filter & Analysis | 6 | Orphan filter gap (#061), combined filter AND-vs-OR (#062) |
| Phase 6 — Template Inheritance | 5 | Stack overflow from cyclic use (#018, #075) |
| Phase 23 — Audit Log | 4 | Action always "edit" (#068), staging ops not logged (#070) |
| Phase 11 — Multi-Select Bulk Edit | 4 | Mixed-type attribute application (#033), InvalidStateError (#034) |
| Phase 22 — Context Menu | 3 | Lock bypass — Critical (#067) |
| Phase 9 — Undo Stack | 2 | Race condition (#028), "unknown" description (#027) |
| Phase 24 — Conflict Detection | 2 | No conflict detection (#072), diff excludes external changes (#073) |
| **Phase 29 — Empty State & Boundaries** | **0** | No bugs found |
| **Phase 30 — Browser Edge Cases** | **0** | No bugs found |

---

## Top 5 Most Impactful Findings

### 1. #044 — All Graph Edges Missing `category` Field: All Quick Views Broken
**Severity: Critical** | Phase 19 — Graph View
Every edge in the dependency graph is missing its `category` field (e.g. `"member"`, `"parent"`, `"use"`). As a result, all 6 Quick View presets (Network, Inheritance, Host→Services, etc.) are permanently broken — the preset buttons are visible and clickable but produce no useful filter. The entire Graph View feature has significantly reduced utility. This is a systemic data model issue, not a display bug.

### 2. #067 — Context Menu Operations Bypass Staging Lock
**Severity: Critical** | Phase 22 — Context Menu
Right-click → "Add to Group", "Move to File", and Delete operations execute and stage changes even when the staging system is locked by another session. This breaks the session isolation guarantee: a second admin can corrupt the first admin's in-progress staged config without any warning. The staging lock is enforced for inline attribute edits but not for context menu bulk operations.

### 3. #072 — No Conflict Detection for External File Modifications
**Severity: Critical** | Phase 24 — Conflict Detection
When a `.cfg` file is modified externally (e.g., by a restore, direct shell edit, or another process) while a staging session is active, the app has no awareness of the conflict. Committing a staged edit will overlay the external changes with the staging diff, silently discarding the external modifications. In production, this could silently overwrite restored config content or manual emergency fixes.

### 4. #038 — Deleting a File With Objects Shows No Warning
**Severity: Critical** | Phase 14 — File & Folder Operations
Clicking "Delete file" on a .cfg file that contains Nagios objects (hosts, services, etc.) stages the deletion immediately with no confirmation dialog and no warning that N objects will be lost. A single misclick on a file like `hosts.cfg` (31 objects) stages permanent deletion with no undo for the file-level operation.

### 5. #033 — Mixed-Type Bulk Edit Silently Applies Invalid Attributes
**Severity: Critical** | Phase 11 — Multi-Select Bulk Edit
When a mixed-type selection (e.g., hosts + services) is bulk-edited with an attribute valid only for one type (e.g., `check_command`), the attribute is silently applied to all selected objects regardless of type. Hosts receive `check_command` (valid) but services may receive `address` (invalid for services). No warning is shown. The resulting config will fail Nagios validation.

---

## Notable Runners-Up

| # | Title | Severity |
|---|-------|----------|
| #009 | Service duplicate check ignores `host_name` — two identical services can coexist | Critical |
| #014 | `check_command` arguments (after `!`) validated as object references — blocks saving any parameterized service check | Critical |
| #015 | Wildcard `*` in `host_name` (valid Nagios syntax) rejected as invalid reference | Critical |
| #049 | Servicegroups have no member edges — rendered as stranded isolated nodes with no connections | Critical |
| #018/075 | Cyclic template `use` directive causes `RangeError: Maximum call stack exceeded` in frontend | Major/Critical |
| #026 | Drop null object onto tree corrupts staged state — requires page reload to recover | Major |
| #003 | Bulk Rename dialog only renames one object even when multiple are selected | Major |
| #039 | Object editor shows original values (not staged) when reopening a previously-edited object | Major |
| #066 | "Add to Group" drops composite tree label — service loses "on {hostgroup}" disambiguation | Major |

---

## Phases with No Issues Found

- **Phase 29 — Empty State & Boundary Conditions**: All edge cases (zero results, 1100-char values, empty staging, mass delete cascade) behaved correctly.
- **Phase 30 — Browser Edge Cases**: Back/Forward navigation, direct URL navigation, and zoom (75%/150%) all rendered correctly with no JS errors.

---

## Recommendations (Priority Order)

### Immediate (Critical — Config Corruption Risk)

1. **Fix graph edge `category` field** (#044) — restore Quick View filtering; this makes the entire Graph View feature functional.
2. **Enforce staging lock for all context menu operations** (#067) — add `sm.can_modify(session_id)` check to all context menu write paths, not just attribute edits.
3. **Add external-modification conflict detection** (#072) — track file mtimes or git HEAD at staging-start; warn before commit if files changed externally.
4. **Add confirmation for file deletion** (#038) — require explicit confirmation with object count before staging file deletion.
5. **Guard mixed-type bulk edit** (#033) — filter attribute suggestions to types valid for *all* selected objects, or warn prominently.

### High Priority (Major — Data Integrity)

6. **Fix `check_command` argument parsing** (#014/#015) — split on `!` before validating the command name; allow `*` as a valid reference value.
7. **Implement service duplicate check with `host_name` scope** (#009) — `(service_description, host_name)` is the composite key, not just `service_description`.
8. **Cascade rename references at staging time** (#029, #030, #076) — or at minimum block commit when "Update References" is unchecked with a prominent irreversible-config warning.
9. **Fix editor to show staged values on reopen** (#039) — pre-populate form fields from `state.pendingEdits` if a pending edit exists for this object.
10. **Add cycle detection to `buildParentChain`** (#018/#075) — `visited = new Set()` prevents stack overflow; also validate at staging time.

### Medium Priority (UX / Observability)

11. **Fix audit log action taxonomy** (#068) — use distinct action values: `create`, `delete`, `rename`, `move`, `bulk_edit`, not just `edit`.
12. **Fix commit dialog to always show git diff** (#073/#074) — when staging is active, merge staging preview with git diff, never show staging-only.
13. **Fix servicegroups in graph** (#049) — add `members` edges from servicegroup nodes to their member services.
14. **Add empty-state message for zero search results** (#059) — "No objects match your search" with a clear filter button.
15. **Fix orphan filter to include services on nonexistent hosts** (#061) — the Orphans filter should catch unreferenced service objects.

---

## Files Covered

All 30 test phases, 85 documented findings across:
`Object Explorer` (all 3 panes) · `Graph View` · `Logs` · `Backups` · `Git` · `Settings`

See individual `NNN-*.md` files for reproduction steps, screenshots, and fix suggestions.
