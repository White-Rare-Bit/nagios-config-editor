# E2E Playwright Test Design — Adversarial Object Explorer Testing

**Date**: 2026-02-18
**Approach**: MCP-driven exploratory test via Playwright browser automation
**Scope**: Full Object Explorer CRUD, staging, drag-drop, graph, audit, commit

## Overview

A single continuous Playwright MCP session simulating an expert Nagios administrator performing complex operations on the bulk editor. The test builds state progressively across 30 phases, with each phase performing multiple compound operations designed to stress-test state management, reference integrity, and UI resilience.

**Goal**: Discover real bugs by actively trying to break things, not just verify happy paths.

## Execution Infrastructure

### Worktree Setup
- Branch: `test/e2e-playwright`
- Worktree: `.worktrees/e2e-playwright`
- Copy `sample-config/` into worktree
- Flask server: `python3 app.py` on port 8080, runs continuously

### Issue Documentation
Each issue gets its own file in `docs/test-discoveries/`:
```
docs/test-discoveries/
  001-{short-description}.md
  002-{short-description}.md
```

Format per file:
```markdown
# {Title}
**Phase**: {number and name}
**Severity**: Critical | Major | Minor | Cosmetic
**Category**: State Management | Reference Integrity | UI/UX | Domain Logic | Error Handling

## What Was Tested
{Exact operation sequence}

## Expected Behavior
{What a Nagios admin would expect}

## Actual Behavior
{What actually happened}

## Screenshot
{Path if relevant}

## Impact
{Why this matters}
```

### Context Management
- Announce each phase start
- Screenshots at key moments
- Issue files written immediately on discovery
- Periodic progress summaries

## Test Data

Sample config: 198 Nagios objects across 11 .cfg files:
- 54 services, 37 commands, 33 hosts, 23 hostgroups, 12 contacts
- 10 timeperiods, 9 servicegroups, 8 contactgroups
- 4 servicedependencies, 3 serviceescalations, 3 hostdependencies, 2 hostescalations
- 9 templates in templates.cfg

---

## Phase Plan (30 Phases, 200+ Test Actions)

### Phase 1: Orientation & Tree Integrity
- Load `/explorer`, verify 198 objects and correct type counts
- Switch "By Type" view — verify counts match "By File"
- Switch back to "By File" — document expansion state behavior
- Expand all folders, count objects per file, compare against `/api/objects`
- Click a host, verify center pane displays it. Click a different host, verify no ghost state
- Click 5 objects rapidly — verify no race condition, last-clicked displayed
- Resize browser narrow — verify tree doesn't break

### Phase 2: Object Inspection Stress
- Open a host: verify all expected attributes (address, check_command, max_check_attempts)
- Click a reference field value — does it navigate to the referenced object?
- Open relationships panel — verify host's services listed. Navigate host → service → back to host — verify no loop or stale display
- Open a template (register 0) — verify template indicator, resolved attributes
- Open an object with `use` — verify resolved attributes show inherited + overridden values
- Open serviceescalation — verify escalation-specific fields
- Open servicedependency — verify dependency fields

### Phase 3: Keyboard Navigation Gauntlet
- Arrow Down 10 times — verify selection moves exactly 10 objects
- Arrow Right on collapsed folder → expand. Arrow Left → collapse
- Enter on selected → opens in center. Spacebar → quick preview with `define host { ... }` syntax
- Escape → close preview, focus returns to tree
- `?` → shortcuts modal with all bindings. Escape → close modal
- Delete key → deletion confirmation. Escape → cancel (object NOT deleted)
- Ctrl+Z with nothing to undo → verify graceful handling
- Tab through editor attribute fields — verify logical focus order

### Phase 4: Create Objects — Compound Creation
- Create host `test-critical-host` in hosts.cfg with address, check_command (autocomplete), contacts, hostgroups
- Without committing: create service `test-http-check` referencing `test-critical-host` — verify autocomplete shows just-created host
- Create service `test-ssh-check` also referencing `test-critical-host`
- Create contact `test-admin-contact` — verify notification_commands autocomplete shows notify-host-by-email, notify-service-by-email
- Create hostgroup `test-critical-servers` with `test-critical-host` as member
- Verify badge counts: green "+" on all 5, commit badge shows 5
- Create object with no required fields — verify validation error
- Create host with existing name — verify duplicate rejected
- Create servicedependency (composite key) — verify tree display
- Create service with `host_name *` (wildcard) — document handling
- Create object with `use` referencing multiple templates comma-separated
- Create command with `!` separators in arguments — verify `!` not misinterpreted
- Create timeperiod with complex date ranges — verify rendering

### Phase 5: Edit Attributes & Autocomplete — Deep Testing
- Edit host's `check_command` — type "check_" — verify shows check_* NOT notify_*
- Edit contact's `service_notification_commands` — type "notify" — verify shows notify-service-by-* NOT notify-host-by-*
- Edit contact's `host_notification_commands` — verify shows notify-host-by-* only
- Edit service's `host_name` — verify shows hosts only
- Type comma in multi-value field, then type — verify autocomplete appears after comma
- Enter value not in autocomplete — document acceptance/rejection
- Edit attribute then Escape — verify original value restored
- Edit attribute then click different object — document auto-save behavior
- Edit `use` directive — verify shows only templates (register 0)
- Clear required field — verify validation warning
- Enter 200+ character value — verify no layout break
- Edit while search filter active that should hide the object post-edit — document behavior
- Edit two different attributes on same object rapidly — verify both staged
- Open same object from tree AND relationships — verify consistent view
- Edit notification_options to `d,u,r,f,s` — verify flags accepted
- Edit command_line with `$USER1$`, `$HOSTADDRESS$`, `$ARG1$` macros — verify no mangling

### Phase 6: Template Inheritance Adversarial
- Find template, verify `register 0` shown
- Open child using template — verify resolved attributes
- Edit template's `max_check_attempts` — re-open child — verify resolved attribute updated (or document staleness)
- Create new template → object using it → verify inheritance works for staged objects
- Chain: template A → template B uses A → object C uses B → verify full chain resolves
- Move template to different file — verify dependents still resolve
- Delete template — verify dependents show warning/broken reference
- Undo deletion — verify everything restores
- Create cyclic inheritance: A uses B, B uses A — verify detection or graceful handling

### Phase 7: Error Handling — Break It
- File name `../../../etc/passwd` → verify path traversal rejected
- File name `<script>alert(1)</script>` → verify XSS rejected/escaped
- Folder moved inside itself → verify circular move rejected
- Two hosts same name → verify duplicate rejected
- Object with zero attributes → document behavior
- Multi-line value in single-line field → document handling
- Large text paste into attribute → verify no hang
- Rapid-click Create Object 5 times → verify no duplicates
- Submit form while submission in-flight → verify no double-submit

### Phase 8: Drag & Drop — Multi-Object Stress
- Multi-select 5 hosts (Ctrl+click) → drag to new file → verify all 5 moved, orange arrows on all
- Drop on invalid target (center pane) → verify rejection, no state corruption
- Select 3, start drag, press Escape → verify drag cancelled, no visual artifacts
- Drag to folder → verify folder auto-expand on hover (or document)
- Multi-select from DIFFERENT files → drag to target → verify all sources updated
- Drag object with PENDING EDITS → verify both edit and move staged
- Verify objects in right pane file tree under new location
- Drag ALL objects out of file → verify empty file handling
- Drag to file staged for deletion → verify rejection/warning
- Drag to folder staged for move → document behavior
- Multi-select from 3+ files → drag → verify all sources correct
- Hover collapsed folder 2+ seconds → verify auto-expand

### Phase 9: Compound Operations & Undo Stack Torture
- Create → edit → move → rename → clone → delete clone = 5-operation chain
- Undo once → clone reappears. Verify correct attributes
- Undo again → verify LIFO order
- Undo 3 more → verify object back to original state
- Undo create → object gone, commit count back
- Redo all → verify state identical to post-operations
- New edit after partial undo → verify redo stack cleared
- 30 operations rapidly → undo ALL → verify staging clean
- Undo after navigating away and back → verify stack persists
- Rapid undo/redo toggle 10 times → verify no corruption
- Bulk move of 5 objects → undo → verify single step (not 5)
- Undo to empty staging → verify commit button disabled/shows 0

### Phase 10: Bulk Rename with Reference Integrity
- Find host referenced by 3+ services → rename
- Verify ALL referencing services' `host_name` updated
- Verify hostgroup `members` updated
- Verify dependency objects updated
- Bulk rename: select 5 hosts, pattern `renamed-{name}` → verify preview
- Apply → verify all 5 renamed, all references updated
- Check diff preview → verify reference updates in diff
- Undo bulk rename → verify ALL names/references revert as one step

### Phase 11: Multi-Select Bulk Edit Stress
- Select 5 services → bulk edit `max_check_attempts` to 7 → verify all updated
- Select 3 hosts + 2 services (mixed) → verify only common attributes shown
- "Select by type" → select all of one type → verify count
- "Select by pattern" with regex → verify correct selection
- Bulk edit + then individually edit one object → verify individual edit overrides

### Phase 12: Cloning Adversarial
- Clone a host → verify all attributes copied, name change required
- Clone, change name AND check_command before save → verify both apply
- Clone into different file → verify correct placement
- Clone object with pending edits → verify clone gets edited values
- Clone service, keep same host_name → verify valid second service
- Clone with existing name → verify rejection

### Phase 13: Dialog Cancellation — State Pollution
- Open Create → fill all fields → Cancel → verify nothing created
- Open Move → select target → Cancel → verify original location
- Open Rename → type name → Cancel → verify original name
- Open Delete confirm → Cancel → verify object exists
- Open Clone → fill details → Cancel → verify no clone
- Open Bulk Rename → configure → Cancel → verify no renames
- After ALL cancels: verify staging count identical to before

### Phase 14: File & Folder Operations Compound
- Create `test-monitoring.cfg` → verify in workspace
- Create `test-zone/` folder → verify
- Create `test-zone/critical/` subfolder → verify nested creation (or document failure)
- Move file into folder → verify objects accessible from new path
- Rename folder → verify file paths updated
- Delete file with objects → verify warning/rejection
- Empty a file, delete it → verify clean deletion
- Create file with same name as deleted file → verify no conflict

### Phase 15: Reorder & Reorganize
- Reorder objects within a file → verify new order persists
- Move 3 from A → B, 2 from B → C → verify no objects lost
- Move object to file, then again to different file → verify only final destination staged
- Split one large file into 3 → verify all objects accounted for

### Phase 16: Comments Preservation
- Find object with inline comments
- Edit attribute → spacebar preview → verify comments present
- Move to different file → verify comments preserved
- Clone → verify comments in clone
- Document any comment loss as critical issue

### Phase 17: State Persistence Across Refresh
- Note exact state: commit count, open tabs, tree expansion
- F5 refresh → verify same tabs, same count, same edits, same tree
- Navigate to `/audit-log` → back to `/explorer` → verify state
- Close browser tab → reopen `/explorer` → verify staging persists via backend

### Phase 18: Multi-Tab Lock Behavior
- Open second tab to `/explorer`
- Try edit from second tab → verify lock banner, editing blocked
- First tab commit → verify lock released
- Second tab → verify lock banner gone, editing works
- Start editing in second tab → check first tab → verify lock banner shown

### Phase 19: Dependency Graph — Full Validation
- Navigate to `/dependencies`
- Find host node → verify edges to its services
- Verify edges from services to contacts/contactgroups
- Verify hostgroup membership edges
- Click node → verify focus/highlight of connected nodes
- Verify template inheritance edges
- Verify newly created objects (phase 4) appear in graph
- Verify orphaned nodes only for truly standalone objects

### Phase 20: Escalation & Dependency Chain Validation
- Open serviceescalation → verify levels, contacts, intervals
- Open servicedependency → verify dependent/depended-on shown
- Verify escalation path: service → escalation → contact
- Verify hostdependency failure criteria
- Navigate between dependent objects → verify bidirectional

### Phase 21: Search, Filter & Analysis Adversarial
- Search "web" → verify correct matches
- Search nonexistent → verify "no results", no crash
- Orphan filter → verify truly unreferenced only
- Issue filter → verify real issues shown
- Search + filter combined → verify AND logic
- Clear search → verify full tree with filter active
- Suggestions panel → verify Nagios-meaningful suggestions
- Health check → verify accuracy

### Phase 22: Context Menu Completeness
- Right-click single host → verify all items (Rename, Clone, View in Graph, Delete)
- Right-click single service → verify service-appropriate items
- Multi-select 3 hosts → right-click → verify bulk items
- Mixed selection (host + service) → verify appropriate items
- "Add to group" → verify relevant group types
- Context menu while locked → verify items disabled

### Phase 23: Audit Log — Admin Perspective
- Navigate to `/audit-log`
- Verify every operation from phases 4-15 logged
- Verify descriptions: "created host test-critical-host" not "created object"
- Verify operation types correct (create/edit/move/delete/clone/rename)
- Verify chronological order
- Verify filtering by type works
- Verify undo operations logged as separate entries

### Phase 24: Conflict Detection & Backup/Restore
- Create backup
- Externally modify a config file while staging active
- Try to commit → verify conflict detection triggers
- Verify conflict identifies which file
- Discard conflict and re-stage
- Test backup restore → verify config returns to known state
- Verify staging state after restore

### Phase 25: Final Staging Review & Commit
- Open commit dialog → verify every staged change in diff
- Verify creates show full object definition
- Verify edits show before/after
- Verify moves show old → new path
- Verify deletions show what's removed
- Verify file operations listed
- Commit → verify success
- Post-commit: zero pending, clean state
- Verify files on disk correct
- Re-open objects → verify committed state

### Phase 26: Cascading Dependency Stress
- Create host A, services S1/S2 on A, contact C1, hostgroup G1 with A
- Delete host A → verify warning about dependents
- If allowed: verify S1/S2 show broken reference badges
- Undo → verify everything reconnects
- Delete service → verify no cascade
- Create servicedependency S1→S2 → delete S1 → verify dependency broken
- Cyclic template inheritance → verify detection / no infinite loop

### Phase 27: Rapid-Fire Stress Test
- 30+ operations fast: create 5, edit 5, move 5, rename 5, clone 5, delete 5
- Verify commit count badge = 30
- Verify diff dialog shows all 30 correctly categorized
- Verify audit log has all 30 entries
- Undo all 30 rapidly → verify staging clean
- Redo all 30 → verify identical state

### Phase 28: Cross-Object Reference Integrity
- Rename host referenced by: services, hostgroups, hostdependencies, hostescalations, servicedependencies
- Verify EVERY reference type updated
- Rename contact referenced by contactgroups AND services → verify both update
- Rename command referenced by hosts AND services AND contacts → verify all three contexts
- Diff preview → verify reference updates in diff

### Phase 29: Empty State & Boundary Conditions
- Filter tree to zero results → verify empty state, no JS errors
- Select all → delete → document behavior
- Object with only required fields → verify renders
- Object with every possible attribute → verify no overflow
- 1-character attribute value → verify saves
- 1000+ character value → verify behavior
- Discard all staging → verify truly empty

### Phase 30: Browser Behavior Edge Cases
- Back button from graph to explorer → verify state
- Forward after Back → verify no double-load
- Two browser windows → verify lock behavior
- Browser zoom 150% → verify layout, drag-drop targets
- Browser zoom 75% → verify readability
- Direct URL navigation with staging active → verify persistence

---

## Success Criteria

- All 30 phases executed
- Every discovered issue documented with severity and impact
- Zero critical issues remaining undocumented
- Badge counts, undo stack, and staging state verified at every phase boundary
- Autocomplete validated for domain correctness (not just "shows something")
- Graph relationships verified against known Nagios semantics
- Audit log entries verified for admin-meaningful descriptions
