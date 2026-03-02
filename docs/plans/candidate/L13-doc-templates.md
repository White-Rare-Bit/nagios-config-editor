# L13 — Documentation Templates — MIGRATE + MODIFY

**Layer:** 13 — CSS & Docs
**Action:** MIGRATE + MODIFY
**Paths:** `templates/docs/staging-system.html`, `templates/docs/data-flow-staging.html`, 14 other `templates/docs/*.html` files, `static/js/docs.js`
**Dependencies:** L12 (staging manager renamed to candidate manager), L13-doc-text-updates (terminology replacements in other doc files)
**Goal:** Migrate the two staging-specific documentation pages to describe the candidate system, update navigation slugs, and replace staging terminology in 14 other doc files.

---

## Files to MIGRATE (not delete)

These two user-facing documentation pages must be **migrated** to describe the candidate system. Deleting them would violate the requirement for full functionality migration (commandment 6) and UI visual parity (commandment 2). Users who navigate to these pages must still find equivalent documentation.

### 1. `templates/docs/staging-system.html` -> `templates/docs/candidate-system.html`

- Rename the file from `staging-system.html` to `candidate-system.html`
- Update the page heading from "Staging System" to "Candidate System"
- Replace all "staging" / "staged" terminology with "candidate" / "pending" equivalents per the replacement table below
- Update the SVG diagram title from "Staging Workflow" to "Candidate Workflow"
- Update internal architecture descriptions to reflect the candidate model (file-copy to `.candidate/`, git-based undo via `git reset --hard HEAD~1`, apply copies candidate back to running config)
- Replace `staging.json` references with the candidate system's state mechanism
- Update the "10 Operation Types" section: the candidate system still supports the same 10 operation categories, but operations modify files directly in the `.candidate/` directory rather than accumulating deltas
- Update the "Lock System" section: replace "staging lock" with "candidate lock", update `sm.can_modify()` references to reflect `CandidateManager`
- Update the "Clearing Staging" heading to "Discarding Changes"
- Update the link to data-flow-staging: `#app/data-flow-staging` -> `#app/data-flow-candidate`
- Keep similar headings and navigation structure for UI visual parity

### 2. `templates/docs/data-flow-staging.html` -> `templates/docs/data-flow-candidate.html`

- Rename the file from `data-flow-staging.html` to `data-flow-candidate.html`
- Update the page heading from "Data Flow & Staging Internals" to "Data Flow & Candidate Internals"
- Update the SVG "Edit Flow: UI to Disk" diagram:
  - Replace "StagingManager" box with "CandidateManager"
  - Replace `staging.json` box with candidate state mechanism
  - Update the "No disk writes" zone annotation: in the candidate model, edits DO write to the `.candidate/` directory (but not to the running config)
- Update "State Transitions" SVG and description:
  - States are still EMPTY, ACTIVE, RESTORE_PENDING but the mechanism is session-file-based
- Replace "Staged Operations" table: the candidate system uses git commits in `.candidate/` rather than `staging.json` fields. Keep the same 10 operation categories but describe the candidate storage model
- Update "Lock Mechanics": replace `sm.can_modify()` with CandidateManager equivalents, update `/api/staging/lock/break` to `/api/candidate/lock/break`
- Update "Undo Stack": describe git-based undo (`git reset --hard HEAD~1`) instead of LIFO stack with inverse operations
- Update "Apply Phase Order": the candidate apply copies `.candidate/` back to running config rather than executing 7 ordered phases
- Update "Conflict Detection": describe how the candidate system detects external modifications
- Update "Commit Workflow": replace `/api/staging/*` endpoints with `/api/candidate/*`
- Update "Atomic File Writes": keep this section as atomic writes are still used
- Update the back-link to staging-system: `#app/staging-system` -> `#app/candidate-system`
- Keep similar headings and navigation structure for UI visual parity

### Terminology replacement table (for migrated files)

| Old Text | New Text |
|----------|----------|
| Staging System | Candidate System |
| staging system | candidate system |
| staging area | candidate area |
| staged changes | pending changes |
| staged (adjective) | pending / marked (context-dependent) |
| staging lock | candidate lock |
| staging state | candidate state |
| staging data | candidate data |
| staging indicator | change indicator |
| staged for deletion | marked for deletion |
| clear all staging | discard all changes |
| Data Flow & Staging Internals | Data Flow & Candidate Internals |
| `staging.json` | `.candidate/` git state |
| `StagingManager` | `CandidateManager` |
| `staging_manager` | `candidate_manager` |
| `/api/staging/*` | `/api/candidate/*` |
| `#app/staging-system` | `#app/candidate-system` |
| `#app/data-flow-staging` | `#app/data-flow-candidate` |

---

## Files to MODIFY (replace "staging" -> "candidate" terminology)

These 14 `templates/docs/*.html` files contain staging references that must be updated:

1. `api-reference.html` — API endpoint documentation
2. `backend-services.html` — Backend service descriptions
3. `backups.html` — Backup system docs
4. `bulk-operations.html` — Bulk operation docs
5. `editing-objects.html` — Object editing workflow
6. `explorer-navigation.html` — Explorer UI docs
7. `file-folder-management.html` — File/folder operation docs
8. `frontend-architecture.html` — Frontend architecture overview
9. `git-integration.html` — Git integration docs
10. `keyboard-shortcuts.html` — Keyboard shortcut reference
11. `overview.html` — System overview
12. `quick-start.html` — Quick start guide
13. `settings.html` — Settings page docs
14. `validation.html` — Validation docs

### Changes in each file

Apply the same terminology replacement table above. Specifically:

- "staging" -> "candidate" (in prose descriptions, not code identifiers)
- "staged" -> "pending" or "marked" (where referring to the staging system concept)
- `/api/staging/*` -> `/api/candidate/*` (API endpoint references)
- `StagingManager` -> `CandidateManager` (class name references)
- `#app/staging-system` -> `#app/candidate-system` (internal doc links)
- `#app/data-flow-staging` -> `#app/data-flow-candidate` (internal doc links)

Detailed per-file line-level replacements are specified in `L13-doc-text-updates.md`.

---

## Update `static/js/docs.js` navigation

The `APP_DOCS_TREE` array in `static/js/docs.js` defines the sidebar navigation slugs and labels. Update the two entries to match the renamed files:

| Old Slug | Old Label | New Slug | New Label |
|----------|-----------|----------|-----------|
| `staging-system` | `Staging System` | `candidate-system` | `Candidate System` |
| `data-flow-staging` | `Data Flow & Staging Internals` | `data-flow-candidate` | `Data Flow & Candidate Internals` |

Keep both entries in their current positions within the navigation tree (User Guide section and Developer Guide section respectively) to maintain UI visual parity.

---

## Error Handling

- If the file rename fails (e.g., permission error), the implementation must report the error and halt rather than leaving orphaned files
- All internal `#app/` links across the 14 modified files must be updated atomically with the rename to prevent broken links
- After migration, verify no remaining references to the old slugs `staging-system` or `data-flow-staging` exist in any template or JS file

## Audit Logging

- The migration of these documentation files should be tracked in the project change log
- All file renames and content modifications must be included in the git commit for this layer

---

## Verification

### Automated checks
1. **No deleted doc pages** — Confirm both `templates/docs/candidate-system.html` and `templates/docs/data-flow-candidate.html` exist after migration
2. **Old files removed** — Confirm `templates/docs/staging-system.html` and `templates/docs/data-flow-staging.html` no longer exist (they were renamed, not copied)
3. **No broken links** — `grep -r "staging-system\|data-flow-staging" templates/ static/js/docs.js` returns zero matches
4. **Terminology check** — `grep -r "staging" templates/docs/` returns minimal/no matches (only acceptable in historical context quotations if any)
5. **Navigation integrity** — `grep "candidate-system\|data-flow-candidate" static/js/docs.js` returns both new slugs
6. **Linting** — Run ESLint on `static/js/docs.js` to confirm no lint violations introduced

### Playwright validation
7. **Page loads** — Navigate to `#app/candidate-system` and `#app/data-flow-candidate` and confirm both pages render content (not 404 or empty)
8. **Navigation works** — Click "Candidate System" and "Data Flow & Candidate Internals" in the sidebar and confirm they load the correct content
9. **Cross-links work** — Click internal links from other doc pages (e.g., the link from `editing-objects.html` to `#app/candidate-system`) and confirm they navigate correctly
10. **Visual parity** — The migrated pages retain similar heading structure, diagrams, and navigation as the original staging pages

### Manual review
11. **Content accuracy** — Read through both migrated pages and confirm the architecture descriptions accurately reflect the candidate model (file-copy, git-based undo, apply-copies-back)

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Documentation pages describe the candidate system which preserves this invariant. The candidate model still requires explicit Apply before running config is modified. |
| 2 | UI visual parity | COMPLIANT | Both documentation pages are migrated with similar headings, navigation position, and structure. Sidebar labels are updated in-place. No pages removed from navigation. |
| 3 | Full audit logging | COMPLIANT | Migration tracked in git commit. Audit logging requirement noted in plan. |
| 4 | Proper error handling | COMPLIANT | Error handling section added for file rename failures and broken link prevention. |
| 5 | Dead code deletion | COMPLIANT | Old `staging-system.html` and `data-flow-staging.html` files are removed after rename (not left as dead copies). Old slugs in `docs.js` are replaced, not duplicated. |
| 6 | Full functionality migration | COMPLIANT | Both staging doc pages are MIGRATED to candidate equivalents, not deleted. Content is updated to reflect the new architecture while preserving the same documentation coverage. |
| 7 | Palo Alto candidate model | COMPLIANT | Migrated content describes the candidate model architecture (file-copy to `.candidate/`, git-based undo, apply copies back to running config). |
| 8 | Change tracking document | COMPLIANT | This plan serves as the change tracking document. Per-file changes are enumerated. |
| 9 | Complete planning before implementation | COMPLIANT | All changes specified in detail before implementation. Line-level text replacements deferred to L13-doc-text-updates.md which is a dependency. |
| 10 | Linting enforcement | COMPLIANT | ESLint check on `docs.js` included in verification. |
| 11 | Playwright validation | COMPLIANT | Playwright checks added: page loads, navigation clicks, cross-link integrity, and visual parity verification. |
