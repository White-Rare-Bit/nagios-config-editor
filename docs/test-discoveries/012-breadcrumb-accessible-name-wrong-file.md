# BUG 012 — Breadcrumb Element Has Wrong Accessible Name (Wrong File Path)

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Minor
**Category:** Accessibility / UI

## Description

The creation form breadcrumb element shows the correct display text ("services.cfg") but its accessible name (aria-label or title attribute) references an incorrect path containing "hosts.cfg".

## Steps to Reproduce

1. Click "+" on services.cfg to create a new object
2. Inspect the breadcrumb element in the creation form header
3. Check the accessible name via the accessibility tree snapshot

## Expected Behavior

The breadcrumb accessible name should match the displayed text — both should reference services.cfg.

## Actual Behavior

Snapshot shows:
```
generic "/Users/ohm/.../sample-config/hosts.cfg" [ref=e4686]: services.cfg
```

The accessible name (tooltip/aria-label) contains `hosts.cfg` while the visible text shows `services.cfg`.

## Impact

Low functional impact, but affects screen reader users and may indicate a stale state reference in the breadcrumb component. The accessible name is the path used by the previous object's creation form (hosts.cfg), suggesting the tooltip is not updated when a new creation form opens in a different file.
