# BUG-002: BROKEN REFERENCE Badge Persists on Open Tab After Undo

**Phase:** Phase 10 — Bulk Rename with References
**Severity:** Minor
**Date:** 2026-02-18

## Summary

After undoing a rename operation, an already-open object tab retains its **BROKEN REFERENCE**
badge even though the underlying data is now valid. The badge only clears when the user
re-selects the object from the tree.

## Steps to Reproduce

1. Open the PING service (which has `hostgroup_name: linux-hosts`)
2. Rename `linux-hosts` → `linux-hosts-renamed` via context menu "Rename..."
3. Observe BROKEN REFERENCE badge appears on the PING service tab ✓ (correct)
4. Click Undo (Ctrl+Z)
5. Observe that `linux-hosts` hostgroup is fully restored (0 pending edits, API confirms correct data)
6. Check the PING service tab — **BROKEN REFERENCE badge still showing** ✗

## Actual Behavior

Two manifestations of the same root cause:

**Manifestation A — stale error badge:** After undo, the open PING service tab continues
to display a red BROKEN REFERENCE badge in the breadcrumb, even though the referenced
hostgroup `linux-hosts` has been restored. The badge clears only when the user explicitly
re-clicks the PING service in the tree.

**Manifestation B — stale tab title:** After undoing a bulk rename of `web-prod-01` →
`web-production-01`, the open tab's breadcrumb still displays `web-production-01` while
the object's `host_name` field correctly shows `web-prod-01`. The tab title reflects the
pre-undo (renamed) state until the user re-selects the object.

## Expected Behavior

Undo should trigger a re-validation of all currently open object tabs. Any validity badge
(BROKEN REFERENCE, etc.) should reflect the post-undo state immediately without requiring
user interaction.

## Root Cause (suspected)

The object detail panel is not re-rendered on staging state changes. The breadcrumb/badge
is only recalculated when an object is explicitly selected from the tree.

## Impact

Minor UX confusion — after undo, the interface appears to still have errors that no longer
exist. Could mislead users into thinking undo didn't fully work.

## Screenshots

- `screenshots/phase10-after-undo.png` — shows stale BROKEN REFERENCE badge after undo
