# 028 — Concurrent undo race condition: simultaneous Ctrl+Z calls silently lose operations

**Phase:** 9 — Undo Stack Torture
**Severity:** Major
**Category:** Concurrency / Undo Stack

## Steps to Reproduce

1. Stage 10 edit operations (one per distinct object)
2. Rapidly fire 10 simultaneous undo requests: `Promise.all(Array(10).fill(null).map(() => Explorer.undoLastAction()))`
3. Check the undo count before and after

## Actual Behavior

- All 10 requests return `{ success: true }`
- Undo count decreases by only 2 (not 10)
- 8 "successful" undos were ghost responses — they reported success but performed no actual reversal

## Expected Behavior

Concurrent undo requests should either:
1. **Queue and process serially** — all 10 actually undo 10 distinct entries, or
2. **Return 409 Conflict** for concurrent requests — only one proceeds, others fail with a clear error

Either way, returning `success: true` for an undo that did nothing is incorrect.

## Technical Details

The staging operation lock (`staging_operation_lock`) serializes writes, but the undo endpoint's lock handling appears to return a success response even when the lock prevents actual execution, or multiple requests see the same undo stack state simultaneously before any write completes.

Reproduced via `Promise.all` in browser with 10 concurrent `POST /api/staging/undo` calls.

## Real-world Trigger

- User holds Ctrl+Z key (key-repeat generates rapid-fire events)
- Browser queues multiple Ctrl+Z keypresses while waiting for the first API response
- `base.js` keyboard handler fires `undoLastAction()` on every keydown without debouncing

## Impact

User sees toast "Undone: X" 10 times but only 2 operations are actually reversed. The staging state is inconsistent with the user's intent. This is particularly harmful for bulk undo workflows.
