# L14 — `templates/CLAUDE.md` — MODIFY

**Layer:** 14 — Reference Documentation
**Action:** MODIFY
**Path:** `templates/CLAUDE.md`
**Dependencies:** L06-base-html.md (candidate-api.js added to base.html load order), L06-candidate-api.md (candidate-api.js created)
**Goal:** Update template documentation to reflect the candidate system (Palo Alto model), replacing all staging terminology and updating the JS load order and component descriptions.

---

## Purpose

Update template load order, global component descriptions, and all staging terminology in `templates/CLAUDE.md` to reflect the candidate system migration. This is a documentation-only change -- no runtime code is modified, no live configuration is mutated.

## Removal Audit

Two staging-specific text references exist in `templates/CLAUDE.md`. Both are terminology updates (not dead code deletion) -- no content is removed without replacement.

| Line | Current Text | Action | Replacement |
|------|-------------|--------|-------------|
| 22 | `api-client.js` → `commit-dialog.js` (load order) | UPDATE | Insert `candidate-api.js` between them |
| 30 | `Shown when another user holds staging lock.` | UPDATE | `Shown when another user has an active editing session.` |
| 38 | `Staged changes confirmation` | UPDATE | `Candidate changes confirmation and apply` |

No dead code remains after these changes. All references are migrated, not dropped.

## Current Code

Load order (line 22):
```markdown
**JS** (before `</body>`): Bootstrap JS → `app.js` → `base-state.js` → `session-manager.js` → `ui-notifications.js` → `git-ui.js` → `api-client.js` → `commit-dialog.js` → `lock-manager.js` → `base.js` → `{% block scripts %}`
```

Lock Banner description (line 30):
```markdown
**Lock Banner** (`#lockBanner`): Shown when another user holds staging lock.
```

Commit overlay row (line 38):
```markdown
| `#globalCommitOverlay` | Staged changes confirmation |
```

## Changes

**1. Update JS Load Order** — Add `candidate-api.js` after `api-client.js` (mirrors L06-base-html.md script tag addition):
```markdown
<!-- BEFORE -->
**JS** (before `</body>`): Bootstrap JS → `app.js` → `base-state.js` → `session-manager.js` → `ui-notifications.js` → `git-ui.js` → `api-client.js` → `commit-dialog.js` → `lock-manager.js` → `base.js` → `{% block scripts %}`
<!-- AFTER -->
**JS** (before `</body>`): Bootstrap JS → `app.js` → `base-state.js` → `session-manager.js` → `ui-notifications.js` → `git-ui.js` → `api-client.js` → `candidate-api.js` → `commit-dialog.js` → `lock-manager.js` → `base.js` → `{% block scripts %}`
```

**2. Update Lock Banner description** — Replace staging lock terminology with candidate session terminology:
```markdown
<!-- BEFORE -->
**Lock Banner** (`#lockBanner`): Shown when another user holds staging lock.
<!-- AFTER -->
**Lock Banner** (`#lockBanner`): Shown when another user has an active editing session.
```

**3. Update Commit Dialog description** — Replace "Staged changes" with candidate terminology:
```markdown
<!-- BEFORE -->
| `#globalCommitOverlay` | Staged changes confirmation |
<!-- AFTER -->
| `#globalCommitOverlay` | Candidate changes confirmation and apply |
```

## UI Visual Parity

This plan modifies documentation only. No UI elements are changed. The documentation updates describe UI changes already made by L06-base-html.md (lock banner text, candidate-api.js load order). Visual parity is not affected.

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Insert `candidate-api.js` into JS load order documentation | [ ] |
| 2 | Update Lock Banner description from staging lock to editing session | [ ] |
| 3 | Update `#globalCommitOverlay` description from "Staged" to "Candidate" | [ ] |
| 4 | Verify no remaining staging references via grep | [ ] |

## Verification

- `grep -i "staging\|staged" templates/CLAUDE.md` -- zero matches confirms no stale references remain
- `grep "candidate-api.js" templates/CLAUDE.md` -- confirms load order updated
- `npm run lint:js` -- not applicable (Markdown file, no JS changes)
- `python3 -m ruff check templates/CLAUDE.md` -- not applicable (Markdown file, no Python changes)
- Playwright: not applicable for this plan (documentation-only change with no UI impact). The UI changes this documentation describes are validated by L06-base-html.md's Playwright checks (lock banner text, candidate-api.js loading).

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | PASS | Documentation-only change. No runtime code modified. No config files touched. |
| 2 | UI visual parity | PASS | No UI changes. Documentation describes UI changes already handled by L06-base-html.md. |
| 3 | Full audit logging | N/A | Documentation change -- no auditable runtime operations. |
| 4 | Proper error handling | N/A | Documentation change -- no code paths to error-handle. |
| 5 | Dead code deletion | PASS | Removal audit confirms all three staging references are replaced, not orphaned. No stale text remains. |
| 6 | Full functionality migration | PASS | All staging descriptions migrated to candidate equivalents. Load order updated to include candidate-api.js. No information dropped. |
| 7 | Palo Alto candidate model | PASS | Terminology updated from "staging lock" to "editing session" and from "Staged changes" to "Candidate changes", reflecting the Palo Alto copy-edit-apply model. |
| 8 | Change tracking document | PASS | Change tracking table with 4 items added above. |
| 9 | Complete planning before implementation | PASS | All three changes enumerated with before/after text, line numbers, and current code shown. |
| 10 | Linting enforcement | N/A | Markdown file -- not subject to ESLint or Ruff. Noted in Verification section. |
| 11 | Playwright validation | N/A | Documentation-only change. UI validation deferred to L06-base-html.md which owns the actual UI changes this documentation describes. |
