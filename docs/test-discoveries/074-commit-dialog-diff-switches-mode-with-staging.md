# 074 — Commit Dialog Switches Between Full Git Diff and Staging Preview

**Phase:** 25 — Staging Review & Commit
**Severity:** Major
**Category:** Data Integrity / UI Accuracy

## Summary

The commit dialog has two incompatible behaviors depending on whether staging is active:

- **No staged changes**: Shows the full git diff (all tracked-file modifications)
- **Staged changes present**: Shows only the staging preview (what the staged object edits will change on disk), omitting any pre-existing git modifications to other files

This inconsistency means an admin committing with an active staging session will see an incomplete picture of what will be committed to git.

## Steps to Reproduce

1. Restore a backup (which modifies files on disk without applying via staging).
   - After restore: `hosts.cfg` and `templates.cfg` are modified relative to git HEAD.
2. Open the commit dialog with **no staged edits** → dialog correctly shows both files (full git diff, 2 files).
3. Close the dialog. Stage a small edit (e.g., change `alias` on `web-prod-01`).
4. Open the commit dialog again with **1 staged edit active**.

## Actual Behavior

The dialog header changes from:
- `2 files changed ~2 modified` (no staging)

to:
- `1 file changed ~1 modified` (with staging)

The diff preview shows only the staged alias change. `templates.cfg` (with `comment-test-host` added by the restore) is entirely absent from the preview.

Clicking **Apply Changes** commits: `2 files changed, 10 insertions(+), 5 deletions(-)` — the actual commit included the invisible `templates.cfg` changes.

## Expected Behavior

The commit dialog should always show the full git diff that will result from the commit, regardless of whether staging is active. Staged changes should be shown alongside (not instead of) any pre-existing tracked-file modifications.

## Why This Matters (Nagios Admin Perspective)

An admin doing a restore followed by a targeted config edit will see only their small edit in the diff preview. They will approve what appears to be a one-line change but will actually commit all of the restore-applied file modifications. In production, this could silently commit restored (or corrupted) config content alongside an intentional edit.

## Root Cause (Hypothesis)

When staging is active, the commit dialog renders a **staging preview** (the diff from current disk to staged-edit disk) rather than the **git diff** (current disk to HEAD). These are different computations. The fix would be to always show the git diff (or a combined view of staged changes + pending git modifications) regardless of staging state.

## Related

- #072 — No conflict detection for external file modifications
- #073 — Commit diff preview excludes external modifications (same root: staging preview vs. git diff)

## Screenshots

- `phase25-commit-dialog-initial.png` — correct: 2 files shown with no staged edits
- `phase25-commit-dialog-with-staged.png` — incomplete: only 1 file shown with 1 staged edit active
- `phase25-after-commit.png` — git result showing "2 files changed, 10 insertions(+), 5 deletions(-)"
