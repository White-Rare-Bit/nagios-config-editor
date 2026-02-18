# 035 — Clone Accepts Duplicate Name Without Error

**Phase:** 12 — Cloning Adversarial
**Severity:** Critical
**Screenshot:** screenshots/12-duplicate-clone.png

## Steps to Reproduce

1. Clone `web-prod-01` → name it `web-prod-01-copy` → confirm → host created
2. Clone `web-prod-01` again → name it `web-prod-01-copy` (same name) → click Clone
3. No error shown — dialog closes, commit count increments

## Actual Behavior

Two hosts both named `web-prod-01-copy` appear in the tree with NEW badges. No validation error, no warning toast, no dialog rejection. Commit count went 36→37 silently.

## Expected Behavior

The Clone dialog should detect that `web-prod-01-copy` already exists (either on disk or in staged creations) and either:
- Reject with an inline error in the dialog, or
- Show a warning requiring confirmation

## Impact

A Nagios admin could silently introduce duplicate `host_name` definitions. Nagios would fail validation on apply with a cryptic "duplicate definition" error. The issue is discoverable only at commit time, not at the point of action. Also related to bug #022 (creation dialog has the same gap).

## Notes

- The same gap affects staged creations: an object created earlier in staging is not checked against.
- Duplicate detection should cover: disk objects + stagedCreations + existing pendingEdits that rename.
