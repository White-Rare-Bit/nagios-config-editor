# Explorer Staging Orchestration — Design Decisions

## Problem

Different operations (delete, edit, create, undo) each called different subsets of refresh functions in different orders, causing redundant network requests (7-16 per mutation) and bugs like deleted objects reappearing in the suggestions panel.

## Solution

Two orchestrators in `data-loading.js` with side-effect-free primitives:

- `afterFrontendMutation(opts)` — user mutated state locally: save -> rebuildUI -> updateBadges -> debouncedAnalysis
- `afterServerSync(opts)` — server is source of truth (undo, apply, polling): rebuildUI -> updateBadges -> debouncedAnalysis

`rebuildUI()` in `state-management.js` handles synchronous UI rebuild:

computeStagedIssues -> buildTree (left) -> renderTargetPane (right) -> syncCenterPane (center) -> renderTabBar

## Key Decisions

- **Two orchestrators over one**: Frontend-initiated vs server-initiated flows have different needs (save vs no-save)
- **Side-effect-free primitives**: `saveStaging()`, `updateBadges()`, `rebuildUI()` do exactly one thing each
- **Debounced analysis only**: `loadAllSuggestions` is never called immediately; always goes through 500ms debounce
- **Single badge fetch**: One `GET /api/staging/info` per mutation (was 3x before)
- **Options param for selective refresh**: `{ skipTree, skipTarget, skipCenter, skipTabs }`
