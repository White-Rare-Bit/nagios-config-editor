# 043 — Editor Shows Rejected Value After Lock Releases

**Phase:** 18 — Multi-Tab Lock  
**Severity:** Minor  
**Category:** Locking / State Consistency

## Steps to Reproduce

1. Tab 1 holds the lock with a staged edit
2. Tab 2 (different session) attempts an edit — it is rejected (423), but the value appears in the field
3. Tab 1 releases the lock (discard or commit)
4. Tab 2 detects the lock release via polling — lock banner disappears ✓
5. Observe Tab 2's editor for the object that was edited in step 2

## Actual Behavior

After lock release, Tab 2's editor still shows the **rejected (never-saved) value** typed during the lock period (e.g., "Tab2 attempt") instead of the actual current value ("Production Web Server 1").

## Expected Behavior

When the lock is released and Tab 2 regains editing ability, the editor should refresh the displayed values to reflect actual current state — discarding any locally-typed but server-rejected values.

## Impact

An admin who typed edits while locked, then later gains the lock, will see their old rejected values still displayed. They may believe those values are now staged when they are not. The Undo/Commit counts will correctly show 0, but the visual field values create a false sense of saved state.

## What Works Correctly

- Lock banner disappears promptly after polling detects release ✓
- Server correctly returns 423 for all locked sessions ✓
- Lock is symmetric: either session can hold it ✓
- Editing succeeds after lock release ✓
