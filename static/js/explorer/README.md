# Explorer UI Refresh Synchronization

## Overview

The explorer implements a centralized refresh pattern to prevent UI inconsistencies. Prior to this design, different operations (delete, edit, create, undo) each called different subsets of refresh functions in different orders, causing bugs like deleted objects reappearing in the suggestions panel after polling sync. The `refreshAfterObjectChange()` function ensures all five UI components (tree, file pane, center pane, suggestions, commit UI) refresh together after any object mutation.

## Architecture

```
Object Mutation (delete/create/edit/move/reorder)
              |
              v
+-----------------------------------+
| Explorer.refreshAfterObjectChange |
+-----------------------------------+
              |
    +---------+---------+-----------+-----------+
    |         |         |           |           |
    v         v         v           v           v
buildTree  render    syncCenter  loadAll    updateCommit
(left)    TargetPane  Pane      Suggestions    UI
           (right)   (center)    (right)
```

**Data Flow**: User Action → Stage Change → Save to Backend → refreshAfterObjectChange() → All 5 UI components filter via staging state (stagedObjectDeletions, pendingEdits, stagedMoves).

## Design Decisions

**Centralized function over scattered calls**: Current code had 4+ different refresh sequences (delete, undo, polling, sync) each calling different subsets of refresh functions. This inconsistency caused the suggestions panel bug. Single function prevents future bugs when adding new operations.

**No batching/debouncing**: User specified immediate refresh. Each operation gets instant feedback. Simpler implementation without debounce complexity. Bulk operations can call refresh once at end if needed.

**Refresh order matters**: buildTree → renderTargetPane → syncCenterPane → loadAllSuggestions → updateCommitUI. Tree provides base object state. Target pane depends on tree object count. Center pane reads from state that tree populates. Suggestions need final filtered list. Commit UI summarizes all staged changes so runs last to ensure accurate counts.

**Conditional center pane refresh**: Center pane only displays content when an object is selected (state.editedObject !== null). Calling refresh when nothing selected wastes cycles and may show stale placeholder. Other panes always have content to display regardless of selection.

**Force flag only for suggestions**: buildTree/renderTargetPane/updateCommitUI execute immediately with no internal debounce. loadAllSuggestions has 500ms debounce via triggerAnalysisUpdate() to prevent rapid API calls during typing. force=true bypasses this debounce for immediate consistency after object changes, preventing deleted objects from reappearing during the 500ms debounce window.

**Options param for selective refresh**: Use case: polling sync only needs commit UI update without full tree rebuild. During bulk operations, caller may refresh once at end. Provides flexibility without separate functions for each combination.

**Suggestions filter via isObjectMarkedForDeletion**: Suggestions previously read state.allObjects unfiltered. Adding same check that tree uses ensures consistent filtering across all components.

**Placement in state-management.js**: This file already handles staging state sync and has access to all relevant state. Keeps refresh logic with state logic. No new module needed.

**Function calls over event bus**: Event bus adds indirection and debugging complexity. Only 6-8 operation sites need refresh calls. Direct function calls are simpler and sufficient for current needs.

## Invariants

- `refreshAfterObjectChange()` must be called AFTER staging state is updated
- Suggestions must filter objects using `isObjectMarkedForDeletion()` - same check as tree
- Refresh must be synchronous (no batching per user requirement)

## Tradeoffs

**Simplicity vs Flexibility**: Chose direct function calls over event bus pattern. Cost: Less flexible for future event-based extensions. Benefit: Easier debugging, no indirection, sufficient for 6-8 call sites.

**Consistency vs Performance**: Chose always refresh all components over selective refresh. Cost: Slightly more work per operation. Benefit: Never have stale UI state, single point to add batching later if needed.
