# BUG-002: Stale Session Lock Persists Across Server Restart

**Phase:** Pre-test setup / Session management
**Severity:** Major
**Date:** 2026-02-19

## Summary

When a staging session is active (lock held by a user) and the Flask server is restarted, the lock from the previous session persists and blocks ALL editing from new sessions. The only recovery paths are: (a) POST `/api/staging/lock/break`, which is documented but did not fully clear the lock in testing, or (b) manually emptying `sample-config/.staging/staging.json`.

## Steps to Reproduce

1. Open the app in a browser tab and make any edit (this acquires a staging lock for that session)
2. Stop the Flask server
3. Restart the Flask server
4. Open the app in a new browser tab (new session ID)
5. Try to edit any object

## Actual Behavior

- New session sees "Locked by another user" (the stale session)
- Commit button shows the previous session's pending count
- `POST /api/staging/lock/break` attempted — returns `{ "gitDiscarded": true, "success": true }` but lock re-appears on next request
- Root cause: `staging.json` retains the old session's `sessionId` and `userName`; the server reloads it on startup

## Additional Finding: `lock/break` Discards Uncommitted Git Changes

When `POST /api/staging/lock/break` is called and there are uncommitted git changes, the endpoint also discards ALL git changes (`git_svc.discard_all()`). This is a destructive side-effect: breaking a stale lock also reverses any file changes that were applied but not yet committed to git.

In this test session, the test host added to `hosts.cfg` was silently reverted when the lock was broken.

## Expected Behavior

1. `POST /api/staging/lock/break` should reliably clear the lock with a single call
2. After a server restart with no active browser sessions, the lock should be considered stale and auto-released (or at least easily clearable)
3. The lock-break side-effect of discarding git changes should be explicitly surfaced in the API response and UI

## Root Cause

`staging.json` is persisted to `sample-config/.staging/staging.json` and read on server startup. The `clear_staging()` call in `api_break_lock()` should zero out this file, but in testing the old session data reappeared.

**Relevant code:**
- `routes/staging.py:611` — `api_break_lock()`
- `staging_manager.py:751` — `staging_file` path
- `staging_manager.py:637` — `sm.clear_staging()` in break_lock

## Impact

- After a server restart during active development/testing, the app becomes stuck
- Manual filesystem intervention required to recover
- Silent data loss: `lock/break` can discard disk changes without admin awareness

## Workaround

Manually write `{}` to `sample-config/.staging/staging.json`:
```bash
python3 -c "import json; json.dump({}, open('sample-config/.staging/staging.json','w'))"
```
