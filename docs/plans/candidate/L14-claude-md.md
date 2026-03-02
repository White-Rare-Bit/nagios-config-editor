# L14 — `CLAUDE.md` — MODIFY

## Purpose
Full rewrite of staging references to candidate terminology throughout the project's root documentation. Every section of CLAUDE.md that references the staging system must be updated to reflect the Palo Alto-style candidate config model, and dead staging references must be deleted — not left behind.

## Changes

**1. Update Documentation Index** — Reference docs section:
```markdown
<!-- BEFORE -->
**Reference docs** (`.claude/`): ROUTES_REFERENCE.md, API_REFERENCE.md, STAGING_REFERENCE.md, ...
<!-- AFTER -->
**Reference docs** (`.claude/`): ROUTES_REFERENCE.md, API_REFERENCE.md, CANDIDATE_REFERENCE.md, ...
```

**2. Update Backend Module Index table:**
```markdown
<!-- BEFORE -->
| `staging_manager.py` | Staging state, locks, undo stack |
<!-- AFTER -->
| `candidate_manager.py` | Candidate session: file-copy, git-based undo, object CRUD |
```
Also remove the `apply_verification.py` row entirely (dead code — file is deleted in L12).

**3. Update Thread Safety section** — Replace StagingManager reference:
```markdown
<!-- BEFORE -->
- **StagingManager**: Atomic file writes (temp file + rename)
<!-- AFTER -->
- **CandidateManager**: fcntl file lock for process-safe session exclusion
```

**4. Replace "Staging System" section** with "Candidate System":
```markdown
## Candidate System

Palo Alto-style candidate config: running config copied to `.candidate/`, git repo inside for undo.
All edits modify candidate files directly. NO changes written to the live Nagios configuration until the user clicks Apply. Apply = copy candidate back to running config. See `.claude/CANDIDATE_REFERENCE.md`.

- **Lock**: fcntl file lock. One session at a time. Check: `cm.can_modify(session_id)`.
- **Stable keys**: `"source_file|object_type|name"` for object identity (same as staging system).
- **Undo**: Each action = git commit. Undo = `git reset --hard HEAD~1`.
- **Audit**: All operations logged via `audit_service.py` (append-only JSONL) and application logger.
```

**5. Update App Factory section helpers:**
```python
# BEFORE
from .helpers import get_service, get_staging_manager, get_backup_manager, get_server_config
# AFTER
from .helpers import get_service, get_candidate_manager, get_backup_manager, get_server_config
```

**6. Update Error Handling section** — Replace staging conflict reference:
```markdown
<!-- BEFORE -->
**HTTP status codes:** 200 (success), 400 (invalid input), 404 (not found), 409 (staging conflicts), 423 (locked), 500 (internal error)
<!-- AFTER -->
**HTTP status codes:** 200 (success), 400 (invalid input), 404 (not found), 409 (candidate conflicts), 423 (locked), 500 (internal error)
```

**7. Update Conventions section** — Add linting enforcement:
```markdown
<!-- AFTER existing convention bullets, ADD: -->
- **Linting**: All Python must pass Ruff; all JavaScript must pass ESLint. No dirty commits.
```

**8. Update Staging Operations list** — The old "Operations" bullet listing `pendingEdits, stagedMoves, ...` is deleted entirely. The candidate system has no client-side staging maps; all state lives server-side in `.candidate/`.

## Removal Audit

Every instance of "staging" in CLAUDE.md must be accounted for:

| Location | Current Text | Action |
|----------|-------------|--------|
| Documentation Index | `STAGING_REFERENCE.md` | Replace with `CANDIDATE_REFERENCE.md` |
| App Factory helpers | `get_staging_manager` | Replace with `get_candidate_manager` |
| Thread Safety | `StagingManager: Atomic file writes` | Replace with `CandidateManager: fcntl file lock` |
| Module Index | `staging_manager.py` row | Replace with `candidate_manager.py` row |
| Module Index | `apply_verification.py` row (if present) | DELETE — dead code |
| Section heading | `## Staging System` | Replace with `## Candidate System` |
| Section body | `True staging: NO changes written...` | Replace with Palo Alto candidate description |
| Section body | `STAGING_REFERENCE.md` link | Replace with `CANDIDATE_REFERENCE.md` link |
| Section body | `sm.can_modify(session_id)` | Replace with `cm.can_modify(session_id)` |
| Section body | `pendingEdits, stagedMoves, ...` operations list | DELETE entirely |
| Error Handling | `409 (staging conflicts)` | Replace with `409 (candidate conflicts)` |

## Verification

**Grep verification:**
```bash
# No stale staging references
grep -i "staging" CLAUDE.md
# Expected: zero matches (except possibly in git history context)

# Candidate references present
grep -i "candidate" CLAUDE.md
# Expected: multiple matches (system section, module table, helpers, reference doc)

# Linting mentioned
grep -i "lint\|ruff\|eslint" CLAUDE.md
# Expected: at least one match in Conventions
```

**Playwright validation:**
```
# After applying this plan, load the app at http://localhost:8080 and verify:
# 1. The app still starts without errors (documentation change should not break runtime)
# 2. The /docs page (if it renders CLAUDE.md or references it) shows no "staging" terminology
```

**Manual review checklist:**
- [ ] No occurrence of "staging" remains in CLAUDE.md
- [ ] CANDIDATE_REFERENCE.md is referenced (not STAGING_REFERENCE.md)
- [ ] `candidate_manager.py` appears in module index
- [ ] `staging_manager.py` does NOT appear in module index
- [ ] `apply_verification.py` does NOT appear in module index
- [ ] `get_candidate_manager` appears in App Factory helpers
- [ ] Candidate System section explicitly states no live mutation until Apply
- [ ] Candidate System section mentions audit logging
- [ ] Thread Safety section references CandidateManager, not StagingManager
- [ ] Error Handling section says "candidate conflicts" not "staging conflicts"
- [ ] Conventions section includes linting enforcement

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Replace `STAGING_REFERENCE.md` with `CANDIDATE_REFERENCE.md` in Documentation Index | [ ] |
| 2 | Replace `staging_manager.py` row with `candidate_manager.py` in Module Index | [ ] |
| 3 | Remove `apply_verification.py` row from Module Index (dead code) | [ ] |
| 4 | Replace `get_staging_manager` with `get_candidate_manager` in App Factory | [ ] |
| 5 | Replace `StagingManager` with `CandidateManager` in Thread Safety | [ ] |
| 6 | Replace `## Staging System` section with `## Candidate System` section | [ ] |
| 7 | Ensure no-live-mutation guarantee is explicit in Candidate System section | [ ] |
| 8 | Add audit logging bullet to Candidate System section | [ ] |
| 9 | Delete `pendingEdits, stagedMoves, ...` operations list | [ ] |
| 10 | Replace `staging conflicts` with `candidate conflicts` in Error Handling | [ ] |
| 11 | Add linting enforcement to Conventions section | [ ] |
| 12 | Final grep: zero "staging" matches in CLAUDE.md | [ ] |

## Commandments Compliance

| # | Commandment | Status | How This Plan Complies |
|---|-------------|--------|------------------------|
| 1 | No live config mutation until Apply | PASS | Change 7 ensures the Candidate System section explicitly states: "NO changes written to the live Nagios configuration until the user clicks Apply." |
| 2 | UI visual parity | PASS | This plan modifies only documentation (CLAUDE.md), not UI code. No visual changes introduced. |
| 3 | Full audit logging | PASS | Change 8 adds an "Audit" bullet to the Candidate System section documenting that all operations are logged via `audit_service.py` and the application logger. |
| 4 | Proper error handling | PASS | Change 6 updates the Error Handling section to use candidate terminology. The error handling section itself (HTTP status codes, backup on mutation) remains intact. |
| 5 | Dead code deletion | PASS | Changes 3 and 9 delete the `apply_verification.py` row and the `pendingEdits/stagedMoves/...` operations list. The Removal Audit table accounts for every staging reference. |
| 6 | Full functionality migration | PASS | Every staging reference is mapped to a candidate equivalent in the Removal Audit table. No functionality is dropped — `staging_manager.py` becomes `candidate_manager.py`, `STAGING_REFERENCE.md` becomes `CANDIDATE_REFERENCE.md`, helpers are renamed, etc. |
| 7 | Palo Alto candidate model | PASS | Change 4 explicitly references the "Palo Alto-style candidate config" model in the replacement section text. |
| 8 | Change tracking document | PASS | The Change Tracking section provides a numbered checklist of all 12 changes to tick off during implementation. |
| 9 | Complete planning before implementation | PASS | This plan is fully specified with exact before/after text, a removal audit, verification steps, and a change tracking checklist — all before any code changes. |
| 10 | Linting enforcement | PASS | Change 11 adds a linting enforcement bullet to the Conventions section: "All Python must pass Ruff; all JavaScript must pass ESLint. No dirty commits." |
| 11 | Playwright validation | PASS | The Verification section includes a Playwright validation step to confirm the app starts without errors and documentation pages show no stale "staging" terminology. |
