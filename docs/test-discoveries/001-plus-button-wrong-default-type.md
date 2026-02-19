# Bug 001: "+" Button Defaults to Wrong Object Type for File Context

**Phase:** 13 — Dialog Cancellation
**Severity:** Major
**Category:** Object Creation / UX

## Steps to Reproduce

1. Navigate to Object Explorer (By File view)
2. Scroll to `commands.cfg` in the left panel (file contains only `command` type objects)
3. Click the `+` button next to `commands.cfg`

## Actual Behavior

- A new object is immediately staged with type `host` (count 38→39)
- The center panel opens an inline editor showing: `commands.cfg > Enter name... [HOST ▼] [NEW]`
- Required fields shown: `address`, `alias`, `host_name`, `hostgroups` — all host-specific fields
- The object appears in the `commands.cfg` tree as `(unnamed)` with type `HOST`

## Expected Behavior

- The default type should be `command` (the dominant/only type in `commands.cfg`)
- An admin clicking "+" on a commands file expects to create a command, not a host

## Impact

An admin managing a large config with many files could accidentally add an object of entirely the wrong type to a file. The wrong-type object would have no relevant required fields, would be a misconfiguration, and the admin may not notice immediately since the error only appears as a validation warning.

## Screenshot

`.playwright-mcp/screenshots/task16-bug-plus-button-immediate-stage.png`
