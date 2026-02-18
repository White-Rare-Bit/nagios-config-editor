# BUG 017 — Template Warning Badges Not Updated When Template Gains Missing Fields

**Phase:** 6 — Template Inheritance Adversarial
**Severity:** Minor
**Category:** UI / Stale State

## Summary

When a template object is edited to add a field that dependent objects were flagged as missing, the tree warning badges on those dependent objects are not updated to reflect the resolution. The warnings remain stale until a page reload.

## Steps to Reproduce

1. Open the `generic-contact` template (contacts.cfg → generic-contact)
2. Observe that contacts using this template (`admin`, `jsmith`, etc.) all show ⚠ "Notification chain broken: has no host_notification_period" warnings in the tree
3. Add `host_notification_period = 24x7` to the `generic-contact` template via "+ Add attribute"
4. Blur the field to save (staging count increments)
5. Observe the warning badges on `admin` and other contacts

## Expected Behavior

After the template gains `host_notification_period`, all contacts that `use: generic-contact` should have their "has no host_notification_period" warning resolved (or at least updated). The tree badge tooltip should no longer list `host_notification_period` as missing.

## Actual Behavior

- The `admin` contact still shows: `"Notification chain broken: admin has no host_notification_commands; admin has no host_notification_period; ..."`
- The warning is unchanged despite the template now providing `host_notification_period` through inheritance
- Warnings only clear after a full page reload (which re-parses the config from disk — not from staged state)

## Impact

Minor — cosmetic stale state. Users editing templates to fix inheritance gaps see no visual feedback that their change resolves the warnings, which may cause them to keep adding redundant attributes to individual objects.

## Notes

- The warnings reflect the committed (on-disk) config, not the staged state
- This is consistent: the tree warnings are based on the parsed config, not the in-memory staging layer
- However, even a full reload wouldn't help here because staged changes aren't committed yet
- Root cause: tree warning computation does not incorporate pendingEdits from the staging manager
