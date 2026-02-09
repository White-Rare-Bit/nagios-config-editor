# Explorer Refresh Synchronization — Design Decisions

## Problem

Different operations (delete, edit, create, undo) each called different subsets of refresh functions in different orders, causing bugs like deleted objects reappearing in the suggestions panel after polling sync.

## Solution

`refreshAfterObjectChange()` in `state-management.js` ensures all 5 UI components refresh together after any mutation:

buildTree (left) → renderTargetPane (right) → syncCenterPane (center) → loadAllSuggestions → updateCommitUI

Order matters: tree provides base state, target pane depends on tree counts, suggestions need final filtered list, commit UI summarizes all changes.

## Key Decisions

- **Centralized function over scattered calls**: Single function prevents future inconsistencies
- **No batching/debouncing**: Immediate refresh per operation; bulk ops can call once at end
- **Options param for selective refresh**: Polling sync only needs commit UI update, not full tree rebuild
- **Force flag for suggestions only**: Bypasses the 500ms analysis debounce to prevent stale data
- **Direct function calls over event bus**: Only 6-8 call sites; event bus adds indirection without benefit
