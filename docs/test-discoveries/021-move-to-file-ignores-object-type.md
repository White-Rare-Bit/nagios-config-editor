# 021 — "Move to File" Dialog Defaults to Alphabetically First File, Ignores Object Type

**Phase:** 6 — Template Inheritance Adversarial
**Severity:** Minor
**Category:** UX / Object Management

## Steps to Reproduce

1. Right-click a host template (`linux-server`) in the Explorer tree
2. Select "Move to file..."

## Actual Behaviour

- Dialog opens with `hostgroups.cfg` pre-selected (alphabetically first among valid files)
- All files are listed as valid targets regardless of object type compatibility
  (e.g., `services.cfg`, `timeperiods.cfg` shown as options for a host template)

## Expected Behaviour

- The dialog should pre-select the most type-appropriate destination
  (for a host template: `hosts.cfg` or `templates.cfg`)
- Ideally, incompatible files should be omitted or de-prioritised
  (moving a host template to `timeperiods.cfg` will result in a config error)

## Notes

- Current filtering already excludes `resources.cfg` and `nagios.cfg` (good)
- The "+ Create new file..." option is correctly included
- This is a UX concern; the move operation itself executes correctly when a valid
  destination is chosen
