# L03: app.py — MODIFY

**Layer:** 3 — App Wiring + Routes
**Action:** MODIFY
**Path:** `app.py`
**Dependencies:** L01 (candidate_manager.py must exist), L02 (nagios_model.py must have stable keys)
**Goal:** Register CandidateManager in app.extensions. Keep StagingManager for now (removed in L4).

---

## Changes

### Step 1: Add CandidateManager import

After the existing imports (around line 18), add:
```python
from candidate_manager import CandidateManager
```

### Step 2: Instantiate CandidateManager after StagingManager

After the StagingManager instantiation and registration (around line 137), add:

```python
# Candidate config manager
candidate_manager = CandidateManager(
    running_config_path=nagios_config_path,
    nagios_cfg=sc.nagios_cfg if hasattr(sc, 'nagios_cfg') else "",
    backup_manager=backup_manager,
)
# Discard stale candidate session from previous server run
if candidate_manager.has_session():
    candidate_manager.discard()
app.extensions["candidate"] = candidate_manager
```

Note: The stale session cleanup is important — if the server crashes during an active candidate session, we don't want to leave a half-finished `.candidate/` directory around.

### Step 3: No other changes

StagingManager instantiation, NagiosService(staging_manager=...) call, and staging extensions registration are all KEPT for now. They are removed in L4.

## Change Tracking

- [ ] Add `from candidate_manager import CandidateManager` import
- [ ] Instantiate `CandidateManager` after `StagingManager` with correct args
- [ ] Add stale session cleanup (`discard()` on startup)
- [ ] Register as `app.extensions["candidate"]`
- [ ] Verify existing StagingManager code is untouched (removed in L4)

## Removal Audit

No code is removed in this step. Purely additive.

## Verification

```bash
python3 -c "from app import create_app; app = create_app(); print('candidate' in app.extensions)"
# Should print: True
python3 -m pytest tests/ -v
python3 -m ruff check app.py
python3 -m ruff format --check app.py
```

## Commandments Compliance

- [x] **C1 — No live config mutation until Apply.** This step only registers the CandidateManager; no config files are written or mutated.
- [x] **C2 — UI visual parity.** N/A — backend-only change, no UI impact.
- [x] **C3 — Full audit logging.** N/A — registration step only; audit logging is handled by route endpoints (L03-routes-candidate.md).
- [x] **C4 — Proper error handling.** Stale session cleanup runs `discard()` guarded by `has_session()` check; `hasattr` guard on `sc.nagios_cfg`.
- [x] **C5 — Dead code deletion.** No dead code introduced; StagingManager kept intentionally (removed in L4).
- [x] **C6 — Full functionality migration.** CandidateManager is registered alongside StagingManager; no functionality dropped.
- [x] **C7 — Palo Alto candidate model.** CandidateManager implements the copy-edit-apply pattern; this step wires it into the app.
- [x] **C8 — Change tracking.** Tickable checklist added above.
- [x] **C9 — Complete planning before implementation.** This document IS the plan; implementation follows after all L03 plans are reviewed.
- [x] **C10 — Linting enforcement.** Ruff check and format commands included in Verification section.
- [x] **C11 — Playwright validation.** N/A — backend wiring only; no UI changes to validate with Playwright.
