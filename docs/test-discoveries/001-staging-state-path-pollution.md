# Staging State Carries Stale File Paths When Config Is Copied

**Phase**: Infrastructure / Worktree Setup
**Severity**: Major
**Category**: State Management

## What Was Tested

Created a fresh git worktree and copied `sample-config/` from the main branch:
```bash
cp -r sample-config/ .worktrees/e2e-playwright/sample-config/
```

Started the Flask server in the worktree at `http://localhost:8080`.

## Expected Behavior

The server should start with clean/empty staging state. Any staging data should reference the current worktree's file paths.

## Actual Behavior

The Commit badge immediately showed "2" on a fresh server start. Investigation revealed the staging file `.staging/staging.json` was copied along with the sample-config.

The staging file contained paths pointing to the **main branch directory**:
```json
"source_file": "/Users/ohm/Desktop/claude/nagios-bulk-editor/sample-config/hosts.cfg"
```

Instead of the worktree path:
```
/Users/ohm/Desktop/claude/nagios-bulk-editor/.worktrees/e2e-playwright/sample-config/hosts.cfg
```

This means if the user committed the staged changes, the server would attempt to write to the **main branch's files**, not the worktree's files — a cross-branch write corruption risk.

## Screenshot

`screenshots/00-baseline.png` — shows "2 Commit" badge on fresh load.

## Impact

**Cross-environment staging corruption**: Copying a Nagios config directory (e.g., to a worktree, staging environment, or DR site) silently carries stale staging operations pointing to the source location. If those operations are committed, they corrupt the source environment's files while leaving the new environment unchanged.

**Specifically**: The `.staging/` directory is a hidden implementation detail that users would not know to exclude when copying config directories.

**Recommendation**: Either (a) validate that all staged file paths belong to the currently configured `NAGIOS_CFG_DIR`, or (b) store the staging state outside the config directory (e.g., in `config/staging.json`) to prevent accidental copying.
