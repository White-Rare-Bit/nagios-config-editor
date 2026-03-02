# L14 — `routes/CLAUDE.md` — MODIFY

**Layer:** 14 — Reference Documentation
**Action:** MODIFY
**Path:** `routes/CLAUDE.md`
**Dependencies:** L03 (routes/candidate.py created), L04 (routes/staging.py deleted), L12 (staging_manager.py deleted, helpers cleaned up)
**Goal:** Update route module documentation to fully reflect the candidate system, removing all staging references and documenting new patterns.

---

## Removal Audit

Every staging reference in routes/CLAUDE.md is enumerated and addressed:

| Line(s) | Current Content | Action |
|----------|----------------|--------|
| 11 | `staging.py` row in Module Index | REMOVE |
| 32-36 | "Lock check" pattern using `sm.can_modify()` | REPLACE with candidate lock check |
| 38-41 | "Parser modification" pattern using `get_parser_for_modification()` | REMOVE (dead code after L12) |
| 44 | "Backup before mutation" pattern | KEEP (still applies to apply phase) |

## Changes

**1. Remove staging.py from route module table:**
```markdown
<!-- REMOVE this row -->
| `staging.py` | GET/POST/DELETE /api/staging, POST /api/staging/apply, /undo |
```

**2. Add candidate.py to route module table:**
```markdown
| `candidate.py` | Candidate session lifecycle, object CRUD, bulk ops, diff/apply |
```

**3. Update Key Helpers section:**

Replace the entire Key Helpers section:
```markdown
## Key Helpers (helpers.py)

` `` python
operation_response(result, success_data=None, error_code=500)
# Converts OperationResult -> (jsonify, status_code)

get_candidate_manager()
# Access CandidateManager from app.extensions

get_objects_for_request()
# Returns candidate or running objects based on ?candidate=1 query param

guard_candidate_or_abort()
# Blocks admin routes (settings, restore) during active candidate session
# Fails CLOSED: abort(500) if CandidateManager not found in extensions
` ``
```

Remove stale helper references:
```markdown
<!-- REMOVE -->
`get_staging_manager()` -- Access StagingManager from app.extensions
```

**4. Replace Patterns section:**

Replace the entire Patterns section with candidate-aware patterns:

```markdown
## Patterns

**Candidate lock check** (required for candidate mutations):
` `` python
cm = get_candidate_manager()
session_id = request.headers.get("X-Session-Id", "")
if not cm.can_modify(session_id):
    return jsonify({"error": "Session is locked by another user", "locked": True}), 423
` ``

**Candidate guard** (blocks admin routes during active session):
` `` python
guard_candidate_or_abort()
# Aborts with 409 if a candidate session is active
` ``

**Backup before apply**: `bm.create_backup("pre_apply")` before copying candidate to running config.

**Audit logging on apply**:
` `` python
from routes.helpers import format_audit_user
log_audit(action="edit", user=user, txn=txn, type=obj_type, name=obj_name, ...)
` ``
```

**5. Verify no stale references remain:**

The following terms must NOT appear in the updated file:
- `staging.py`
- `get_staging_manager`
- `get_parser_for_modification`
- `StagingManager`
- `sm.can_modify`

## Verification

```bash
# No stale staging references
grep -i "staging" routes/CLAUDE.md
# Expected: zero matches

# Candidate references present
grep -i "candidate" routes/CLAUDE.md
# Expected: multiple matches (candidate.py, get_candidate_manager, etc.)

# Module table has correct row count (staging removed, candidate added)
grep -c "^\|" routes/CLAUDE.md
```

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Documentation-only change. Updated patterns section explicitly shows that backup happens "before apply" (not before each edit). The candidate lock check pattern replaces the staging lock check. |
| 2 | UI visual parity | N/A | Documentation file, no UI impact. |
| 3 | Full audit logging | COMPLIANT | Added audit logging pattern to Patterns section documenting `log_audit()` calls with transaction ID. |
| 4 | Proper error handling | COMPLIANT | Lock check pattern documents 423 response. `guard_candidate_or_abort()` documented as fail-CLOSED (abort 500). `operation_response()` helper preserved for OperationResult error mapping. |
| 5 | Dead code deletion | COMPLIANT | Removal audit enumerates all 4 staging references. `staging.py` row removed. `get_staging_manager()` removed. `get_parser_for_modification()` pattern removed (dead after L12). No stale references left behind. |
| 6 | Full functionality migration | COMPLIANT | Every staging pattern has a candidate equivalent: lock check migrated (`sm` to `cm`), helper functions migrated (`get_staging_manager` to `get_candidate_manager`), new helpers documented (`get_objects_for_request`, `guard_candidate_or_abort`). Parser modification pattern removed because candidate edits files directly (no in-memory staging). |
| 7 | Palo Alto candidate model | COMPLIANT | Documentation reflects the file-copy candidate model: edits go to candidate directory, backup before apply, copy-back on apply. Patterns section shows candidate lock check, not staging lock. |
| 8 | Change tracking document | COMPLIANT | Removal audit table tracks every staging reference with line numbers and actions. L00 inventory shows this file as `[covered]` under L14-routes-claude-md.md. |
| 9 | Complete planning before implementation | COMPLIANT | All 5 changes are fully specified with before/after content. Verification steps defined. No ambiguity left for implementation. |
| 10 | Linting enforcement | N/A | Markdown documentation file. Python snippets in code blocks follow project conventions (snake_case, proper imports). |
| 11 | Playwright validation | N/A | Internal developer documentation file. Not user-visible UI. No Playwright test needed. |
