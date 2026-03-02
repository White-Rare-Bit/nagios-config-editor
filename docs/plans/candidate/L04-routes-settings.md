# L04: routes/settings.py — MODIFY

**Layer:** 4 — Route Cleanup
**Action:** MODIFY
**Path:** `routes/settings.py`
**Dependencies:** L03
**Goal:** Replace StagingManager with CandidateManager in config path update.

---

## Changes

### In `_update_config_path()`:
1. Remove `from staging_manager import StagingManager` (local import)
2. Remove `StagingManager` instantiation and `app.extensions["staging"]` registration
3. Replace with `CandidateManager` creation and `app.extensions["candidate"]` registration:
   ```python
   from candidate_manager import CandidateManager
   candidate_manager = CandidateManager(
       running_config_path=new_path,
       nagios_cfg=sc.nagios_cfg if hasattr(sc, 'nagios_cfg') else "",
       backup_manager=app.extensions.get("backup"),
   )
   app.extensions["candidate"] = candidate_manager
   ```

## Removal Audit

| Removed | Candidate Equivalent |
|---------|---------------------|
| `from staging_manager import StagingManager` | `from candidate_manager import CandidateManager` |
| `StagingManager(...)` instantiation | `CandidateManager(...)` instantiation |
| `app.extensions["staging"] = ...` | `app.extensions["candidate"] = ...` |

## Change Tracking

- [ ] Remove `from staging_manager import StagingManager` local import in `_update_config_path()`
- [ ] Remove `StagingManager` instantiation and `app.extensions["staging"]` registration
- [ ] Add `from candidate_manager import CandidateManager` local import
- [ ] Add `CandidateManager` instantiation with correct constructor args
- [ ] Register as `app.extensions["candidate"]`
- [ ] Verify no other references to `StagingManager` remain in settings.py
- [ ] Verify app starts and config path change works

## Verification

```bash
python3 -m pytest tests/ -v
python3 -c "from app import create_app; create_app()"
ruff check routes/settings.py
```

---

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** CandidateManager replaces StagingManager and follows the candidate model: edits go to `.candidate/`, not live config, until Apply.
- [x] **C2 — UI visual parity.** No UI changes; settings page behavior unchanged. Only the internal manager class is swapped.
- [x] **C3 — Full audit logging.** CandidateManager operations include audit logging. The settings route itself logs config path changes as before.
- [x] **C4 — Proper error handling.** CandidateManager constructor and OperationResult pattern provide proper error handling. No silent failures.
- [x] **C5 — Dead code deletion.** StagingManager import and instantiation are removed, not left alongside CandidateManager.
- [x] **C6 — Full functionality migration.** StagingManager re-instantiation on path change is fully replaced by CandidateManager re-instantiation with equivalent parameters.
- [x] **C7 — Palo Alto candidate model.** CandidateManager implements the copy-edit-apply model.
- [x] **C8 — Change tracking document.** Checklist added above.
- [x] **C9 — Complete planning before implementation.** This document is the plan; implementation follows after all L04 plans are finalized.
- [x] **C10 — Linting enforcement.** Verification section includes `ruff check` and `pytest` commands.
- [x] **C11 — Playwright validation.** N/A — backend-only change to internal manager wiring; no UI impact. Settings page Playwright tests would exercise this path indirectly.
