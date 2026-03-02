# E2E Playwright Test — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Execute a 30-phase adversarial E2E test of the Object Explorer via Playwright MCP, documenting all discovered issues.

**Architecture:** MCP-driven exploratory test — Claude uses Playwright MCP tools (browser_navigate, browser_snapshot, browser_click, etc.) to drive the browser through the full test workflow. Issues documented as individual markdown files in `docs/test-discoveries/`. All work in an isolated git worktree.

**Tech Stack:** Flask (Python), Playwright MCP, Chromium browser

---

## Global Directives

### MCP Tool Strategy (follow throughout all tasks)

1. **Screenshots for observation/verification** — use `browser_take_screenshot` for visual confirmation; much smaller than snapshots, prefer these when the structure is already known
2. **`browser_run_code` with JS selectors** — when the DOM structure is known, use JS to find refs and click elements directly instead of snapshotting
3. **`browser_snapshot` to file only** — use `browser_snapshot` with a `filename` only when exploring unknown structure; then use `Read` to inspect targeted sections rather than returning the full snapshot inline
4. **Avoid returning full snapshots inline** — never call `browser_snapshot` without a `filename` unless absolutely necessary; inline snapshots are verbose and slow

### Nagios Administrator Perspective

When evaluating behavior, think critically as an experienced Nagios administrator. Ask: *Would a real admin notice this? Would it cause confusion, data loss, or misconfiguration in production?* Prioritize issues that affect operational correctness over cosmetic concerns.

### Bug Documentation Requirement

**Before moving on to the next test phase or task, document every discovered issue.** Do not defer writing discovery files. For each bug:
- Create `docs/test-discoveries/NNN-{description}.md` immediately when found
- Include: steps to reproduce, actual vs expected behavior, severity, screenshot filename if taken
- Only proceed to the next step after all issues from the current step are recorded

---

### Task 1: Create Worktree and Branch

**Files:**
- Create: `.worktrees/e2e-playwright/` (via git worktree)

**Step 1: Create branch and worktree**

```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor
git worktree add .worktrees/e2e-playwright -b test/e2e-playwright
```

**Step 2: Copy sample-config into worktree**

```bash
cp -r sample-config/ .worktrees/e2e-playwright/sample-config/
```

**Step 3: Create test-discoveries directory**

```bash
mkdir -p .worktrees/e2e-playwright/docs/test-discoveries
```

**Step 4: Verify worktree**

```bash
ls .worktrees/e2e-playwright/sample-config/
```

Expected: All 11 .cfg files listed (hosts.cfg, services.cfg, commands.cfg, contacts.cfg, dependencies.cfg, hostgroups.cfg, servicegroups.cfg, templates.cfg, timeperiods.cfg, resources.cfg, nagios.cfg)

---

### Task 2: Start Flask Server

**Step 1: Start server in background**

```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor/.worktrees/e2e-playwright
python3 app.py &
```

**Step 2: Verify server is running**

```bash
curl -s http://localhost:8080/api/health-check | python3 -m json.tool
```

Expected: JSON response with `"status": "ok"` or similar health check response.

**Step 3: Verify sample config loaded**

```bash
curl -s http://localhost:8080/api/objects | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'Total objects: {len(data)}')"
```

Expected: `Total objects: 198` (or close — exact count from sample config)

---

### Task 3: Open Browser and Navigate to Explorer

**Step 1: Navigate to explorer**

Use `browser_navigate` to open `http://localhost:8080/explorer`

**Step 2: Take initial snapshot**

Use `browser_snapshot` to capture the accessibility tree. Verify:
- Left panel shows object tree
- Center panel is empty or shows welcome state
- Right panel shows workspace with files

**Step 3: Take screenshot for baseline**

Use `browser_take_screenshot` to save baseline as `docs/test-discoveries/screenshots/00-baseline.png`

---

### Task 4: Execute Phase 1 — Orientation & Tree Integrity

**Reference:** Design doc Phase 1

**Step 1: Verify object count and tree structure**

Use `browser_snapshot`. Count objects in tree. Verify ~198 objects across expected file groupings.

**Step 2: Switch view modes**

Click "By Type" toggle. Snapshot. Verify type-based grouping shows same object count. Switch back to "By File". Document expansion state behavior.

**Step 3: Click through objects rapidly**

Click 5 objects in quick succession. After each click, snapshot to verify center pane updates to correct object.

**Step 4: Resize browser**

Use `browser_resize` to narrow width (800px). Snapshot. Verify no broken layout. Restore to normal width (1400px).

**Step 5: Document any issues found**

For each issue: create `docs/test-discoveries/NNN-{description}.md` using the issue template from design doc.

---

### Task 5: Execute Phase 2 — Object Inspection Stress

**Reference:** Design doc Phase 2

**Step 1: Open a host object**

Click a host (e.g., `web-server-01` or first available). Snapshot. Verify attributes: `host_name`, `address`, `check_command`, `max_check_attempts` all visible.

**Step 2: Test reference navigation**

Click a reference field value (e.g., `check_command` value). Verify it navigates to the command object or document that it doesn't.

**Step 3: Test relationships panel**

Open relationships/impact section. Verify host's services listed. Click a service. Verify service opens. Navigate back to host from service's relationships.

**Step 4: Inspect template object**

Find a template (register 0) in templates.cfg. Open it. Verify "template" indicator shown.

**Step 5: Inspect inheritance**

Open an object with `use` directive. Verify resolved attributes section shows inherited + local values.

**Step 6: Inspect complex types**

Open a serviceescalation and servicedependency. Verify type-specific fields render correctly.

**Step 7: Document issues**

---

### Task 6: Execute Phase 3 — Keyboard Navigation Gauntlet

**Reference:** Design doc Phase 3

Test all keyboard interactions: Arrow keys, Enter, Escape, Spacebar (quick preview), `?` (help), Delete key, Ctrl+Z, Tab navigation. Document any unexpected behavior.

---

### Task 7: Execute Phase 4 — Create Objects (Compound Creation)

**Reference:** Design doc Phase 4

Create 5 objects that reference each other: host, 2 services, contact, hostgroup. Verify autocomplete shows staged (uncommitted) objects. Test error cases: no required fields, duplicate names, composite key objects, wildcards, multi-template use, command arguments with `!`.

---

### Task 8: Execute Phase 5 — Edit Attributes & Autocomplete

**Reference:** Design doc Phase 5

Deep autocomplete testing: verify domain-correct suggestions per field type (check_* for check_command, notify-service-* for service_notification_commands, etc.). Test: Escape cancel, auto-save behavior, multi-value comma fields, 200+ char values, editing with active filters, Nagios macros.

---

### Task 9: Execute Phase 6 — Template Inheritance Adversarial

**Reference:** Design doc Phase 6

Edit template attributes and verify cascade. Create template chains. Test cyclic inheritance. Move/delete templates and verify dependent behavior.

---

### Task 10: Execute Phase 7 — Error Handling

**Reference:** Design doc Phase 7

Try to break it: path traversal filenames, XSS in names, circular folder moves, duplicate names, rapid clicks, double submissions.

---

### Task 11: Execute Phase 8 — Drag & Drop Stress

**Reference:** Design doc Phase 8

Multi-select drag, invalid targets, drag cancel, auto-expand, cross-file drag, drag with pending edits, drag to deleted/moved targets.

---

### Task 12: Execute Phase 9 — Undo Stack Torture

**Reference:** Design doc Phase 9

5-operation chain with undo/redo. 30 rapid operations + full undo. Cross-navigation undo persistence. Rapid toggle. Bulk operation undo as single step.

---

### Task 13: Execute Phase 10 — Bulk Rename with References

**Reference:** Design doc Phase 10

Rename host with 3+ service references, verify all updated. Pattern-based bulk rename. Undo as single step.

---

### Task 14: Execute Phase 11 — Multi-Select Bulk Edit

**Reference:** Design doc Phase 11

Bulk edit same-type, mixed-type. Select by type/pattern. Individual override after bulk edit.

---

### Task 15: Execute Phase 12 — Cloning Adversarial

**Reference:** Design doc Phase 12

Clone with modifications, into different file, with pending edits, duplicate name rejection.

---

### Task 16: Execute Phase 13 — Dialog Cancellation

**Reference:** Design doc Phase 13

Cancel every dialog type after filling fields. Verify zero state pollution across all cancellations.

---

### Task 17: Execute Phase 14 — File & Folder Operations

**Reference:** Design doc Phase 14

Create/rename/move/delete files and folders. Subfolder nesting. Delete file with objects. Same-name after deletion.

---

### Task 18: Execute Phase 15 — Reorder & Reorganize

**Reference:** Design doc Phase 15

Reorder within file. Cross-file moves. Double-move same object. Split large file.

---

### Task 19: Execute Phase 16 — Comments Preservation

**Reference:** Design doc Phase 16

Edit/move/clone objects with inline comments. Verify comments survive each operation via quick preview.

---

### Task 20: Execute Phase 17 — State Persistence

**Reference:** Design doc Phase 17

Browser refresh, cross-page navigation, tab close/reopen. Verify staging, tabs, tree state all persist.

---

### Task 21: Execute Phase 18 — Multi-Tab Lock

**Reference:** Design doc Phase 18

Open second tab. Verify lock blocks editing. Commit from first tab. Verify lock release. Reverse scenario.

---

### Task 22: Execute Phase 19 — Dependency Graph

**Reference:** Design doc Phase 19

Navigate to `/dependencies`. Verify node relationships, edges, click-to-focus, template edges, newly created objects.

---

### Task 23: Execute Phase 20 — Escalation & Dependency Chains

**Reference:** Design doc Phase 20

Service escalation paths, dependency objects, bidirectional navigation.

---

### Task 24: Execute Phase 21 — Search, Filter & Analysis

**Reference:** Design doc Phase 21

Partial search, nonexistent search, orphan filter, issue filter, combined filters, suggestions panel, health check.

---

### Task 25: Execute Phase 22 — Context Menu

**Reference:** Design doc Phase 22

Right-click single/multi/mixed selection. All menu items. Add to group. Disabled when locked.

---

### Task 26: Execute Phase 23 — Audit Log

**Reference:** Design doc Phase 23

Navigate to `/audit-log`. Verify all operations logged with admin-meaningful descriptions. Filtering. Undo logging.

---

### Task 27: Execute Phase 24 — Conflict Detection & Backup

**Reference:** Design doc Phase 24

External file modification during staging. Conflict detection on commit. Backup creation and restore.

---

### Task 28: Execute Phase 25 — Staging Review & Commit

**Reference:** Design doc Phase 25

Open commit dialog. Verify complete diff. Commit. Post-commit clean state. Disk file verification.

---

### Task 29: Execute Phase 26 — Cascading Dependency Stress

**Reference:** Design doc Phase 26

Create object graph, delete central node, verify warnings and broken references. Undo. Cyclic inheritance.

---

### Task 30: Execute Phase 27 — Rapid-Fire Stress

**Reference:** Design doc Phase 27

30+ operations fast. Verify counts, diff, audit log. Undo all. Redo all.

---

### Task 31: Execute Phase 28 — Cross-Object Reference Integrity

**Reference:** Design doc Phase 28

Rename objects referenced by multiple types. Verify every reference type updates. Diff preview.

---

### Task 32: Execute Phase 29 — Empty State & Boundaries

**Reference:** Design doc Phase 29

Zero results, mass deletion, minimal attributes, maximal attributes, boundary values, discard all.

---

### Task 33: Execute Phase 30 — Browser Edge Cases

**Reference:** Design doc Phase 30

Back/Forward buttons, multi-window, zoom 150%/75%, direct URL navigation.

---

### Task 34: Compile Test Summary

**Step 1: Count and categorize issues**

Review all files in `docs/test-discoveries/`. Create a summary.

**Step 2: Write summary file**

Create `docs/test-discoveries/SUMMARY.md` with:
- Total issues found by severity (Critical / Major / Minor / Cosmetic)
- Total issues by category
- Phases with most issues
- Top 5 most impactful findings
- Recommendations

**Step 3: Commit all discoveries**

```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor/.worktrees/e2e-playwright
git add docs/test-discoveries/
git commit -m "test: E2E Playwright test discoveries — adversarial explorer testing"
```

---

### Task 35: Cleanup

**Step 1: Stop Flask server**

```bash
kill %1  # or find and kill the python3 process
```

**Step 2: Merge discoveries to main (if desired)**

```bash
cd /Users/ohm/Desktop/claude/nagios-bulk-editor
git merge test/e2e-playwright
```

**Step 3: Remove worktree**

```bash
git worktree remove .worktrees/e2e-playwright
git branch -d test/e2e-playwright
```
