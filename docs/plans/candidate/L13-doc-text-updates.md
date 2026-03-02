# L13: Documentation Text Updates — MODIFY

**Layer:** 13 — CSS & Docs
**Action:** MODIFY
**Paths:** 6 documentation templates (4 files changed, 2 confirmed no-change)
**Dependencies:** L06-L11 (frontend rewrite complete), L13-doc-templates (page deletions)
**Goal:** Fix technically inaccurate text in user-facing documentation — broken links to deleted pages, wrong code identifiers, and wrong API endpoint references. Per Commandment 2 (UI visual parity), user-facing prose, section headings, button labels, and SVG diagram text are NOT changed unless they would be factually wrong in the new system.

---

## Commandment 2 Rationale

The word "staged" in user-facing prose is **not technically inaccurate**. The candidate system still holds changes in a staging area until Apply — the implementation changed (delta-based to file-copy), but the user-facing concept of "staging changes before applying" remains correct. Therefore:

- Prose descriptions using "staged", "staging", "staged for deletion", etc. are LEFT UNCHANGED.
- Section headings like "Staged Indicators" are LEFT UNCHANGED.
- SVG diagram labels are LEFT UNCHANGED.
- Button labels and panel titles are LEFT UNCHANGED.
- `package.json` description is LEFT UNCHANGED.

Only three categories of text ARE changed:
1. **Broken anchor links** — `#app/staging-system` and `#app/data-flow-staging` point to pages deleted in L13-doc-templates. These must be removed or retargeted.
2. **Code identifier references** — Function names, class names, and variable names that actually change in the codebase (e.g., `get_staging_info` -> `get_candidate_info`, `staging_manager` -> `candidate_manager`).
3. **API endpoint references** — `/api/staging/*` routes are deleted and replaced by `/api/candidate/*` routes.

---

## File 1: `templates/docs/contributing.html`

These are developer-facing code examples that must match the actual post-migration codebase.

| Line | Old Text | New Text | Reason |
|------|----------|----------|--------|
| 23 | `<code>get_staging_info</code>, <code>staging_manager</code>, <code>apply_object_composite</code>` | `<code>get_candidate_info</code>, <code>candidate_manager</code>, <code>apply_object_composite</code>` | Python function/module names change |
| 28 | `<code>getStagingInfo</code>, <code>refreshAfterObjectChange</code>, <code>buildTypeDropdown</code>` | `<code>getCandidateInfo</code>, <code>refreshAfterObjectChange</code>, <code>buildTypeDropdown</code>` | JS function name changes |
| 76 | `<h4>Lock Check for Staging Mutations</h4>` | `<h4>Lock Check for Candidate Mutations</h4>` | Section describes code that uses CandidateManager |
| 79 | `Route handlers that modify staging state must verify session ownership:` | `Route handlers that modify candidate state must verify session ownership:` | Code pattern description must match actual code |
| 82-83 | `if not sm.can_modify(...)` code block referencing `sm` | Updated code block using `cm = get_candidate_manager()` / `cm.can_modify(...)` | Variable name and helper function change |
| 119 | `const result = await ApiClient.post('/api/staging', { data: payload });` | `const result = await ApiClient.post('/api/candidate', { data: payload });` | API endpoint changes |

---

## File 2: `templates/docs/file-folder-management.html`

Only broken links are fixed. All prose text ("staged", "staging") is left unchanged.

| Line | Old Text | New Text | Reason |
|------|----------|----------|--------|
| 14 | `<a href="#app/staging-system">Staging System</a> for details.` | `<a href="#app/overview">Overview</a> for details.` | Target page deleted in L13-doc-templates |
| 177 | `<a href="#app/staging-system">Staging System</a> and appear in the commit dialog` | `<a href="#app/overview">Overview</a> and appear in the commit dialog` | Target page deleted in L13-doc-templates |

---

## File 3: `templates/docs/editing-objects.html`

Only the broken link is fixed. All prose text is left unchanged.

| Line | Old Text | New Text | Reason |
|------|----------|----------|--------|
| 7 | `<a href="#app/staging-system">Staging System</a>` | `<a href="#app/overview">Overview</a>` | Target page deleted in L13-doc-templates |

---

## File 4: `templates/docs/quick-start.html`

No changes needed. No broken links or wrong code identifiers.

---

## File 5: `templates/docs/explorer-navigation.html`

No changes needed. No broken links or wrong code identifiers.

---

## File 6: `templates/docs/git-integration.html`

Only the broken link is fixed. All prose text and SVG labels are left unchanged.

| Line | Old Text | New Text | Reason |
|------|----------|----------|--------|
| 178 | `<a href="#app/staging-system">staging system</a>` | `<a href="#app/overview">staging system</a>` | Target page deleted in L13-doc-templates |

---

## File 7: `templates/docs/bulk-operations.html`

Only the broken link is fixed. All prose text and SVG labels are left unchanged.

| Line | Old Text | New Text | Reason |
|------|----------|----------|--------|
| 235 | `<a href="#app/staging-system">commit dialog</a>` | `<a href="#app/overview">commit dialog</a>` | Target page deleted in L13-doc-templates |

---

## File 8: `templates/docs/validation.html`

Only the broken link is fixed. All prose text is left unchanged.

| Line | Old Text | New Text | Reason |
|------|----------|----------|--------|
| 61 | `<a href="#app/staging-system">Commit dialog</a>` | `<a href="#app/overview">Commit dialog</a>` | Target page deleted in L13-doc-templates |

---

## Files with NO changes needed

The following files from the original plan require zero changes (no broken links, no wrong code identifiers):

- `templates/docs/quick-start.html` — prose only, no code refs or broken links
- `templates/docs/explorer-navigation.html` — prose only, no code refs or broken links
- `templates/docs/settings.html` — prose only ("pending staged changes" is not inaccurate)
- `templates/docs/keyboard-shortcuts.html` — prose only, no code refs
- `package.json` — description text is marketing, not technical accuracy

---

## Out of Scope

The following documentation files are handled by L13-doc-templates (DELETE or MODIFY):

- `templates/docs/staging-system.html` — DELETED in L13-doc-templates
- `templates/docs/data-flow-staging.html` — DELETED in L13-doc-templates
- `templates/docs/architecture.html` — handled in L13-doc-templates
- `templates/docs/backend-services.html` — handled in L13-doc-templates
- `templates/docs/frontend-architecture.html` — handled in L13-doc-templates
- `templates/docs/api-reference.html` — handled in L13-doc-templates (API endpoint refs must change there)
- `templates/docs/backups.html` — handled in L13-doc-templates

---

## Anchor Link Strategy

The deleted pages `staging-system.html` and `data-flow-staging.html` were linked from 6 locations across the user-facing docs. Since these pages are deleted (L13-doc-templates) and no direct replacement page is created (candidate documentation goes to `.claude/CANDIDATE_REFERENCE.md` per L13-doc-templates), all 6 links are retargeted to `#app/overview` which provides the high-level system description including the apply workflow.

If a dedicated candidate system doc page is added later, these links can be updated to point there.

---

## Change Count

**Original plan:** 85 text replacements across 12 files
**Revised plan:** 12 text replacements across 4 files (86% reduction)

| Category | Count |
|----------|-------|
| Broken anchor links fixed | 6 |
| Code identifier updates (contributing.html) | 5 |
| API endpoint updates (contributing.html) | 1 |
| **Total** | **12** |

---

## Verification

1. **Broken link check** — After applying all changes, run:
   ```bash
   grep -rn '#app/staging-system\|#app/data-flow-staging' templates/docs/
   ```
   Expected: **zero matches** (all links to deleted pages have been retargeted).

2. **Code identifier check** — Verify contributing.html references match actual post-migration code:
   ```bash
   grep -n 'get_staging_info\|getStagingInfo\|staging_manager\|/api/staging' templates/docs/contributing.html
   ```
   Expected: **zero matches**.

3. **Visual review** — Load each modified documentation page in the browser and confirm no broken links or layout issues.

4. **Prose preservation check** — Verify that user-facing prose still uses "staged"/"staging" terminology:
   ```bash
   grep -c 'staged\|staging' templates/docs/file-folder-management.html
   ```
   Expected: **non-zero** (prose is intentionally preserved).

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | This plan only modifies documentation templates, not runtime behavior. |
| 2 | UI visual parity | COMPLIANT | Reduced from 85 to 12 changes. Only technically inaccurate text is changed (broken links, wrong code identifiers, wrong API endpoints). All user-facing prose, headings, labels, and SVG text preserved. |
| 3 | Full audit logging | N/A | Documentation-only changes; no runtime code affected. |
| 4 | Proper error handling | N/A | Documentation-only changes; no runtime code affected. |
| 5 | Dead code deletion | COMPLIANT | No dead code introduced; broken links to deleted pages are fixed rather than left dangling. |
| 6 | Full functionality migration | COMPLIANT | Developer-facing code examples in contributing.html are updated to match the migrated codebase. |
| 7 | Palo Alto candidate model | COMPLIANT | Code references updated to candidate model identifiers. User-facing docs still accurately describe the "edit then apply" workflow. |
| 8 | Change tracking document | COMPLIANT | Every change is enumerated with line number, old text, new text, and reason. |
| 9 | Complete planning before implementation | COMPLIANT | Full plan with verification steps documented before any implementation. |
| 10 | Linting enforcement | N/A | HTML template changes only; no JS or Python code affected. |
| 11 | Playwright validation | COMPLIANT | Verification step 3 includes visual review of each modified page. Playwright tests can validate that documentation pages load without broken links. |
