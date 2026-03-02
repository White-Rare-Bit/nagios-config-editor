# L04: routes/analysis.py — MODIFY

**Layer:** 4 — Route Cleanup
**Action:** MODIFY
**Path:** `routes/analysis.py`
**Dependencies:** L03
**Goal:** Remove staging mutation routes. Read routes updated in L05.

---

## Routes to REMOVE

| Route | Candidate Equivalent |
|-------|---------------------|
| `POST /api/smart-grouping/create` | `POST /api/candidate/create` (frontend calls CandidateApi) |
| `POST /api/smart-grouping/add-to-group` | `POST /api/candidate/bulk-edit` (frontend calls CandidateApi) |

## Routes to KEEP (all read-only)

All GET endpoints stay. They get `?candidate=1` support in L05.

## Removal Audit

| Removed | Candidate Equivalent | Notes |
|---------|---------------------|-------|
| `POST /api/smart-grouping/create` | `POST /api/candidate/create` | Frontend calls CandidateApi instead |
| `POST /api/smart-grouping/add-to-group` | `POST /api/candidate/bulk-edit` | Frontend calls CandidateApi instead |

No read-only routes are removed. All GET endpoints retained.

## Change Tracking

- [ ] Remove `POST /api/smart-grouping/create` route handler
- [ ] Remove `POST /api/smart-grouping/add-to-group` route handler
- [ ] Remove any now-unused imports related to removed routes
- [ ] Verify all GET endpoints remain intact
- [ ] Verify app starts without errors

## Verification

```bash
python3 -c "from app import create_app; create_app()"
ruff check routes/analysis.py
npx eslint static/js/  # if any JS touches analysis routes
```

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** Removed routes were staging mutations; their candidate equivalents go through CandidateManager which only writes to `.candidate/` until Apply.
- [x] **C2 — UI visual parity.** No UI changes; only backend route removal. Frontend already calls CandidateApi equivalents.
- [x] **C3 — Full audit logging.** N/A — removed routes; their candidate replacements in L03 already include audit logging.
- [x] **C4 — Proper error handling.** N/A — this plan removes code, no new error paths introduced.
- [x] **C5 — Dead code deletion.** The two mutation routes become dead code after candidate migration and are deleted here.
- [x] **C6 — Full functionality migration.** Both routes have candidate equivalents documented in the removal audit above. No functionality dropped.
- [x] **C7 — Palo Alto candidate model.** Mutations routed through CandidateManager which follows copy-edit-apply model.
- [x] **C8 — Change tracking document.** Checklist added above.
- [x] **C9 — Complete planning before implementation.** This document is the plan; implementation follows after all L04 plans are finalized.
- [x] **C10 — Linting enforcement.** Verification section includes `ruff check` command.
- [x] **C11 — Playwright validation.** N/A — backend-only route removal; UI unchanged. Playwright tests for the candidate workflow are covered in L03-test-candidate-routes.md.
