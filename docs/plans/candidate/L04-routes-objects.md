# L04: routes/objects.py — MODIFY

**Layer:** 4 — Route Cleanup
**Action:** MODIFY
**Path:** `routes/objects.py`
**Dependencies:** L03
**Goal:** Remove direct-write mutation routes.

---

## Routes to REMOVE

| Route | Candidate Equivalent |
|-------|---------------------|
| `POST /api/delete-objects` | `POST /api/candidate/delete-objects` |
| `POST /api/clone-objects` | `POST /api/candidate/create` (clone = create with same attrs) |

## Routes to KEEP

| Route | Reason |
|-------|--------|
| `GET /api/objects` | Primary object list endpoint |

## Removal Audit

| Removed | Candidate Equivalent | Notes |
|---------|---------------------|-------|
| `POST /api/delete-objects` | `POST /api/candidate/delete-objects` | Frontend calls CandidateApi instead |
| `POST /api/clone-objects` | `POST /api/candidate/create` | Clone is create with same attrs; frontend calls CandidateApi |

`GET /api/objects` is read-only and retained as the primary object list endpoint.

## Change Tracking

- [ ] Remove `POST /api/delete-objects` route handler
- [ ] Remove `POST /api/clone-objects` route handler
- [ ] Remove any now-unused imports related to removed routes (e.g., staging helpers)
- [ ] Verify `GET /api/objects` remains intact and functional
- [ ] Verify app starts without errors

## Verification

```bash
python3 -c "from app import create_app; create_app()"
ruff check routes/objects.py
python3 -m pytest tests/ -v -k "object"
```

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Removed routes wrote directly to live config; their candidate equivalents go through CandidateManager which only writes to `.candidate/` until Apply.
- [x] **C2 — UI visual parity.** No UI changes; only backend route removal. Frontend already calls CandidateApi equivalents.
- [x] **C3 — Full audit logging.** N/A — removed routes; their candidate replacements in L03 already include audit logging.
- [x] **C4 — Proper error handling.** N/A — this plan removes code, no new error paths introduced.
- [x] **C5 — Dead code deletion.** The two direct-write mutation routes become dead code after candidate migration and are deleted here.
- [x] **C6 — Full functionality migration.** Both routes have candidate equivalents documented in the removal audit above. Clone functionality is preserved via create-with-same-attrs pattern.
- [x] **C7 — Palo Alto candidate model.** Mutations routed through CandidateManager which follows copy-edit-apply model.
- [x] **C8 — Change tracking document.** Checklist added above.
- [x] **C9 — Complete planning before implementation.** This document is the plan; implementation follows after all L04 plans are finalized.
- [x] **C10 — Linting enforcement.** Verification section includes `ruff check` and `pytest` commands.
- [x] **C11 — Playwright validation.** N/A — backend-only route removal; UI unchanged. Playwright tests for the candidate workflow are covered in L03-test-candidate-routes.md.
