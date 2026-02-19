# 067 — Context Menu Operations Bypass Staging Lock

**Phase:** 22 — Context Menu
**Severity:** Critical
**Screenshot:** `screenshots/phase22-rename-while-locked.png`

## Steps to Reproduce

1. Open Explorer in two tabs (Tab 0, Tab 1) — each gets an independent session ID
2. In Tab 1, make an edit (e.g., change a field value) to acquire the staging lock for Tab 1's session
3. Verify Tab 1 owns the staging lock: `GET /api/staging` shows a non-Tab-0 session owner
4. Reload Tab 0 (fresh session ID, does NOT own the lock)
5. In Tab 0, right-click any service → **Rename...**
6. Enter a new name → click **Rename**

## Actual Behavior

- Context menu items show no visual indication of locked state (all enabled, full opacity)
- Rename dialog opens without any lock check
- Rename **succeeds** silently — the object is renamed in staging, the tree updates, Commit badge increments
- No error, no lock banner, no toast

## Expected Behavior

- Context menu edit items (Rename, Clone, Move to file, Add to group, Delete) should be visually disabled or show a lock indicator when another session holds the staging lock
- Attempting to open the Rename dialog while locked should either be blocked outright, or the dialog submit should fail with a visible "locked" error and the lock banner should appear
- Under no circumstances should a locked session's rename commit to staging

## Impact (Nagios Admin Perspective)

This completely undermines the multi-user staging safety model. If two admins are simultaneously editing, the second admin's changes silently merge into (or overwrite) the first admin's staged work. The second admin has no way to know the lock existed. This can produce a Nagios config that neither admin intended.

## Related Bugs

- **#042** (`fields-not-readonly-while-locked`): Edit fields in the object editor also don't enforce the lock upfront
- The context menu lock bypass is even more severe because the admin gets no feedback at all — the rename silently succeeds
