# 019 — Resolved Attributes Ignore Staged Template Edits

**Phase:** 6 — Template Inheritance Adversarial
**Severity:** Major
**Category:** Staging / Template Inheritance

## Steps to Reproduce

1. Open `generic-host` template in the Explorer
2. Change `notifications_enabled` from `1` to `0` (staged edit, commit badge goes 7→8)
3. Navigate to `linux-server` template (which has `use: generic-host`)
4. Expand **Impact & Relationships** → resolved attributes table

## Actual Behaviour

The resolved attributes table still shows `notifications_enabled: 1` sourced from `generic-host`,
even though a staged edit has set it to `0`.

Extracted resolved row: `notifications_enabled  1  generic-host`

## Expected Behaviour

The resolved attributes view should reflect staged edits to parent templates. If `generic-host`'s
`notifications_enabled` is staged as `0`, all child objects' resolved view should show `0`.

## Screenshot

`screenshots/019-template-cascade-stale-resolved.png`

## Notes

- The staging system correctly captures the template edit (visible in `/api/staging`)
- The commit badge increments correctly (7→8)
- Only the **resolved attributes display** is stale — it reads from disk values, not staged state
- Related to bug 017 (warning badges not updated on cascade), but affects the resolved value
  table rather than warning indicators
