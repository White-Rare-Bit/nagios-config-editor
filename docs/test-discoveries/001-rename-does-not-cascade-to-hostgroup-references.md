# BUG-001 (REVISED): Rename Broken References Not Explained During Staging

**Phase:** Phase 10 — Bulk Rename with References
**Severity:** Minor (UX / discoverability)
**Date:** 2026-02-18
**Status:** Original severity downgraded — reference cascade DOES happen at commit time

## Summary

Renaming a hostgroup stages only the object itself. During staging, all services referencing
the old name show a red **BROKEN REFERENCE** badge with no explanation. The reference cascade
is deferred to commit time — the commit dialog shows **"✓ Update references (27 references
in other objects)"** — but the user has no indication of this during staging.

## What Actually Happens (Correct Behavior)

1. User renames `linux-hosts` → `linux-hosts-renamed` via "Rename..."
2. Only the hostgroup's own `hostgroup_name` is staged (1 pending edit)
3. Services using `hostgroup_name: linux-hosts` show **BROKEN REFERENCE** badges ← alarming
4. User opens commit dialog → sees **"3 files changed, ~1 modified, 27 ref updates"**
5. Commit dialog has **"✓ Update references (27 references in other objects)"** checkbox (checked by default)
6. Applying changes updates all 27 references atomically ✓

## The UX Problem

The staging phase creates alarm without context:
- Broken reference badges appear on 9+ services immediately after rename
- No tooltip, banner, or inline message explains "these will be fixed on commit"
- A user who sees BROKEN REFERENCE might undo the rename thinking something went wrong
- The resolution mechanism (commit dialog checkbox) is only discoverable by opening commit

## What Would Be Better

Either of:
1. **During rename**: A preview in the Rename dialog showing "This will affect N references — they will be updated on commit"
2. **During staging**: A dismissible notice on the broken-reference badges: "These references will be updated when you Apply Changes"
3. **Both**: Show affected count in the rename dialog AND clarify the staging badge

## Screenshot

- `screenshots/phase10-commit-dialog-27-ref-updates.png` — commit dialog showing 27 ref updates checkbox

## Note on BUG-003

The "Bulk rename..." feature (single-object scope) also does not show a reference update
count in the commit dialog — this needs separate verification. See BUG-003.
