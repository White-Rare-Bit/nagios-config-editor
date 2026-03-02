# L14 — `.claude/ROUTES_REFERENCE.md` — MODIFY

**Layer:** 14 — Reference Documentation
**Action:** MODIFY
**Path:** `.claude/ROUTES_REFERENCE.md`
**Dependencies:** L03-routes-candidate.md (candidate blueprint), L04-routes-staging.md (staging removal), L04-routes-files.md (mutation route removal)
**Goal:** Replace all staging route documentation with candidate route documentation. Ensure every staging route is either mapped to a candidate equivalent or explicitly marked as removed with justification.

---

## Purpose

Replace the `staging.py` route table and all staging references in ROUTES_REFERENCE.md with the candidate route table. This is a documentation-only change — no code is modified. The documented routes must accurately reflect the candidate model: all mutations go through `/api/candidate/*` endpoints, and nothing touches the live config until Apply.

## Removal Audit — Staging Routes to Candidate Mapping

Every staging route must map to a candidate equivalent or be explicitly removed. Nothing dropped on the floor.

| Old Staging Route | Method | New Candidate Route | Method | Notes |
|-------------------|--------|---------------------|--------|-------|
| `/api/staging` | GET | _removed_ | — | No client-side staging state to fetch; candidate objects served via `GET /api/candidate/objects` |
| `/api/staging` | POST | _removed_ | — | No client-side save; each edit is a server-side candidate mutation |
| `/api/staging` | DELETE | `DELETE /api/candidate` | DELETE | Clear/discard candidate session |
| `/api/staging/info` | GET | `GET /api/candidate` | GET | Session status (replaces staging info polling) |
| `/api/staging/lock` | GET | `GET /api/candidate` | GET | Session status includes lock info |
| `/api/staging/lock/break` | POST | `DELETE /api/candidate?force=1` | DELETE | Force-discard with breaker identity logging |
| `/api/staging/apply` | POST | `POST /api/candidate/apply` | POST | Apply candidate to running config |
| `/api/staging/virtual-tree` | GET | `GET /api/candidate/objects` | GET | Parse candidate directly instead of overlay |
| `/api/staging/undo` | POST | `POST /api/candidate/undo` | POST | Git-based undo (`git reset --hard HEAD~1`) |
| `/api/staging/conflicts` | GET | `GET /api/candidate/conflicts` | GET | Detect external modifications |
| `/api/staging/diff` | GET | `GET /api/candidate/diff` | GET | File-level changes + unified diff |
| `/api/staging/analyze-references` | GET | `GET /api/candidate/analyze-references` | GET | Preview cross-reference updates for pending name changes |
| `/api/staging/commit` | POST | _removed_ | — | Commit is now a separate git operation after apply; no combined staging commit |

**Result:** 13 staging routes mapped. 3 removed (with justification), 10 mapped to candidate equivalents. Zero functionality dropped.

## Changes

**1. Remove entire `Staging Operations (routes/staging.py)` section** — Delete the table containing all 13 `/api/staging/*` routes (lines 33-49 of current file). Dead code deletion: `routes/staging.py` is deleted in L04-routes-staging.md; its documentation must also be deleted.

**2. Add `Candidate Operations (routes/candidate.py)` section** — Insert after `Core Object Operations` section with the full candidate route table:

```markdown
## Candidate Operations (routes/candidate.py)

### Session Lifecycle

| Route | Method | What |
|-------|--------|------|
| /api/candidate/init | POST | Start candidate session (copy running config to .candidate/) |
| /api/candidate | GET | Get session status (lock info, change counts) |
| /api/candidate | DELETE | Discard candidate session (?force=1 to break another user's lock) |

### Object Operations

| Route | Method | What |
|-------|--------|------|
| /api/candidate/objects | GET | List objects from candidate config (paths normalized to running) |
| /api/candidate/files | GET | List .cfg files in candidate directory |
| /api/candidate/folders | GET | List folders in candidate directory |
| /api/candidate/edit | POST | Edit object in candidate (git commit per action) |
| /api/candidate/delete-objects | POST | Delete objects from candidate |
| /api/candidate/create | POST | Create object in candidate |
| /api/candidate/move | POST | Move objects between files in candidate |
| /api/candidate/undo | POST | Undo last action (git reset --hard HEAD~1) |

### Bulk Operations

| Route | Method | What |
|-------|--------|------|
| /api/candidate/bulk-edit | POST | Bulk attribute edit in candidate |
| /api/candidate/bulk-move | POST | Bulk move objects in candidate |

### Diff, Analysis & Validation

| Route | Method | What |
|-------|--------|------|
| /api/candidate/diff | GET | File-level changes + unified diff |
| /api/candidate/diff/structured | GET | Per-object structured changes for commit dialog |
| /api/candidate/diff/file | POST | Diff for a specific file |
| /api/candidate/analyze-references | GET | Preview cross-reference updates for pending name changes |
| /api/candidate/conflicts | GET | Detect external file modifications |
| /api/candidate/health-check | GET | Run health checks on candidate objects |
| /api/candidate/validate | POST | Run nagios -v on candidate config |

### Apply

| Route | Method | What |
|-------|--------|------|
| /api/candidate/apply | POST | Apply candidate to running config (conflict check, backup, copy, reload) |

### File/Folder Operations

| Route | Method | What |
|-------|--------|------|
| /api/candidate/file/create | POST | Create file in candidate |
| /api/candidate/file/delete | POST | Delete file from candidate |
| /api/candidate/file/move | POST | Move/rename file in candidate |
| /api/candidate/folder/create | POST | Create folder in candidate |
| /api/candidate/folder/delete | POST | Delete folder from candidate |
| /api/candidate/folder/move | POST | Move/rename folder in candidate |
```

**3. Remove staging references from `File/Folder Operations (routes/files.py)` section** — The current files.py section describes staging file/folder operations. In the candidate system, file/folder mutations move to `routes/candidate.py`. Update the files.py section to contain only read-only routes:

```markdown
## File/Folder Operations (routes/files.py)

| Route | Method | What |
|-------|--------|------|
| /api/files | GET | List all .cfg files in config directory |
| /api/folders | GET | List all folders in config directory |
```

All mutation routes (`/api/files/create`, `/api/folders`, `/api/files/move`, `/api/folders/move`, `/api/files/relocate`, `/api/folders/relocate`, `DELETE /api/files/*`, `DELETE /api/folders/*`, `POST /api/delete`) are removed from files.py and replaced by `/api/candidate/file/*` and `/api/candidate/folder/*` endpoints above.

**4. Remove staging references from `Core Object Operations (routes/objects.py)` section** — Mutation routes (`POST /api/delete-objects`, `POST /api/clone-objects`) move to candidate. The objects.py section retains only read:

```markdown
## Core Object Operations (routes/objects.py)

| Route | Method | What |
|-------|--------|------|
| /api/objects | GET | List objects with optional type/search filter (?candidate=1 for candidate-aware) |
```

**5. Remove staging-specific routes from `Bulk Operations (routes/bulk_ops.py)` section** — Mutation routes (`POST /api/apply-rename`, `POST /api/move-objects`) move to candidate bulk endpoints. Read-only routes stay:

```markdown
## Bulk Operations (routes/bulk_ops.py)

| Route | Method | What |
|-------|--------|------|
| /api/search | POST | Search objects by query, type, field, regex |
| /api/preview-rename | POST | Preview bulk rename with pattern/prefix/suffix |
| /api/diff/rename | POST | Generate diff for bulk rename operation |
```

**6. Update cross-references** — Replace any mention of "staging" in route descriptions with "candidate" equivalents. Specifically:
- Git routes: replace `staging` references with `candidate` (e.g., "excludes backups/staging" becomes "excludes backups/candidate")
- Analysis routes: note `?candidate=1` query parameter where applicable

**7. Update helper function references** — If the doc mentions `get_staging_manager()`, replace with `get_candidate_manager()`.

## Error Handling

This is a documentation-only change. No code is modified, so no runtime error handling applies. However, the documented routes must accurately reflect the error handling behavior:
- 423 for locked candidate session
- 404 for no active session
- 409 for conflicts during apply
- 500 for apply failures (with candidate preserved for retry)

## Audit Logging

Documentation-only change; no audit log entries are emitted. The documented candidate routes include audit logging specifications (per L03-routes-candidate.md): transaction-grouped audit entries on apply, force-discard identity logging, and structured apply start/result logging.

## Verification

```bash
# No stale staging references
grep -i "staging" .claude/ROUTES_REFERENCE.md
# Expected: zero matches (or only in historical context notes if any)

# All candidate routes documented
grep "/api/candidate" .claude/ROUTES_REFERENCE.md | wc -l
# Expected: 27 (all candidate endpoints)

# No dead route documentation for removed mutation endpoints
grep -E "/api/(delete-objects|clone-objects|files/create|folders/move|files/move|apply-rename|move-objects)" .claude/ROUTES_REFERENCE.md
# Expected: zero matches (all moved to candidate routes)
```

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|-------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Documented candidate routes enforce this: all mutations target `.candidate/` directory; only `POST /api/candidate/apply` copies to running config. Removal audit confirms no staging routes that wrote to disk remain documented. |
| 2 | UI visual parity | N/A | Documentation-only change. No UI modifications. |
| 3 | Full audit logging | COMPLIANT | No code change, so no audit entries emitted. Documented routes reference audit logging specs from L03-routes-candidate.md (transaction-grouped apply audit, force-discard logging). |
| 4 | Proper error handling | COMPLIANT | Documented routes include HTTP status codes (423, 404, 409, 500) with proper error semantics. No code to fail silently. |
| 5 | Dead code deletion | COMPLIANT | Entire staging route table deleted. Mutation routes removed from files.py, objects.py, and bulk_ops.py sections. Removal audit maps every staging route to disposition (migrated or removed with justification). |
| 6 | Full functionality migration | COMPLIANT | Removal audit proves every staging route is either mapped to a candidate equivalent or explicitly removed with justification. 10 routes migrated, 3 removed (GET/POST staging state no longer needed; commit merged into apply). Zero functionality dropped. |
| 7 | Palo Alto candidate model | COMPLIANT | Route table documents the candidate model: init copies config, edits modify candidate, apply copies back. Route structure (`/api/candidate/*`) reflects this architecture. |
| 8 | Change tracking document | COMPLIANT | This plan is tracked in L00-migration-inventory.md under L14 documentation layer. Removal audit provides line-by-line accountability. |
| 9 | Complete planning before implementation | COMPLIANT | This plan fully specifies all changes before any edits to ROUTES_REFERENCE.md. No ambiguity in what gets added, removed, or modified. |
| 10 | Linting enforcement | N/A | Markdown documentation file. No Python or JavaScript code to lint. |
| 11 | Playwright validation | N/A | Documentation-only change. No UI behavior to validate with Playwright. |
