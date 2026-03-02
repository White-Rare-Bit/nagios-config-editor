# L04: routes/staging.py — DELETE

**Layer:** 4 — Route Cleanup
**Action:** DELETE
**Path:** `routes/staging.py`
**Dependencies:** L03 (candidate routes must be registered)
**Goal:** Delete the entire staging blueprint (~2,200 lines). No live config is mutated — this only removes dead code after candidate routes are in place.

---

## Removal Audit

Every endpoint in routes/staging.py has a candidate equivalent. The actual route
decorator in staging.py is listed in the left column (verified via `@bp.route`).

| Old Staging Route | Candidate Equivalent |
|-------------------|---------------------|
| `GET /api/staging` | `GET /api/candidate` |
| `POST /api/staging` (save) | Not needed (candidate writes directly) |
| `POST /api/staging/apply` | `POST /api/candidate/apply` |
| `POST /api/staging/undo` | `POST /api/candidate/undo` |
| `DELETE /api/staging` | `DELETE /api/candidate` |
| `GET /api/staging/lock` | `GET /api/candidate` (session info includes lock) |
| `POST /api/staging/lock/break` | `DELETE /api/candidate?force=1` |
| `GET /api/staging/info` | `GET /api/candidate` |
| `GET /api/staging/diff` | `GET /api/candidate/diff` |
| `GET /api/staging/virtual-tree` | `GET /api/candidate/virtual-tree` |
| `GET /api/staging/conflicts` | `GET /api/candidate/conflicts` |
| `GET /api/staging/analyze-references` | `GET /api/candidate/analyze-references` |
| `POST /api/staging/commit` | `POST /api/candidate/commit` |

Internal helper functions (~30 private functions for undo entry building, virtual
tree assembly, apply phases, etc.) are deleted along with the file. Their candidate
equivalents live in the candidate route module or candidate_manager.

## Change Tracking

- [ ] Confirm all 13 staging endpoints have candidate equivalents registered (L03)
- [ ] Confirm all frontend callers have been migrated to `/api/candidate/*` paths (L07-L09)
- [ ] Confirm tests referencing `routes/staging.py` are deleted or updated (L12)
- [ ] Delete `routes/staging.py`
- [ ] Remove staging blueprint registration from `routes/__init__.py` (or `app.py`)
- [ ] Confirm `python3 -c "from app import create_app; create_app()"` succeeds
- [ ] Confirm `python3 -m pytest tests/ -v` passes (with L12 test deletions applied)
- [ ] Run linting (see Verification)

## Verification

```bash
# Unit tests
python3 -m pytest tests/ -v
# Any test that imports from routes/staging.py will fail — those tests are deleted in L12

# App startup smoke test
python3 -c "from app import create_app; create_app()"
# App should start without error

# Linting — must pass before committing
python3 -m ruff check .
npx eslint static/js/
```

## Playwright Validation

No direct UI changes in this plan (pure backend route deletion). Playwright tests
from earlier layers that exercise the candidate flow (init, edit, apply, undo)
serve as regression validation that the old routes are no longer needed.

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This plan only deletes dead code; it does not introduce any new write paths. The candidate equivalents (L03) enforce the copy-edit-apply model.
- [x] **C2 — UI visual parity.** N/A — no UI changes. This is a backend-only route file deletion.
- [x] **C3 — Full audit logging.** N/A for the deletion itself. The candidate equivalents that replace these routes must include audit logging (verified in L03).
- [x] **C4 — Proper error handling.** N/A — no new code is introduced; this plan only deletes a file.
- [x] **C5 — Dead code deletion.** This plan IS the dead code deletion. The entire staging.py file (~2,200 lines) is removed.
- [x] **C6 — Full functionality migration.** The removal audit table maps all 13 staging endpoints to their candidate equivalents. No functionality is dropped.
- [x] **C7 — Palo Alto candidate model.** Removing the old staging routes is a required step in the migration to the candidate model.
- [x] **C8 — Change tracking.** Change Tracking section with tickable checklist is included above.
- [x] **C9 — Complete planning before implementation.** This plan is part of the full layered migration plan and must not be executed until L03 is complete.
- [x] **C10 — Linting enforcement.** Verification section includes `ruff check` and `eslint` commands.
- [x] **C11 — Playwright validation.** No direct UI changes; existing candidate-flow Playwright tests provide regression coverage. See Playwright Validation section above.
