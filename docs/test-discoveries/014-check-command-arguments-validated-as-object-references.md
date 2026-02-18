# BUG 014 — check_command "!" Arguments Validated as Object References; Field Cleared on Failure

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Critical
**Category:** Validation / Data Loss

## Description

When a `check_command` value includes Nagios `!` argument syntax (e.g., `check_ping!100,20%!500,60%`), the system validates the argument tokens as if they were object references. When an argument value (e.g., `20%`) doesn't match any known object, the system shows an error toast and clears the entire field value.

## Steps to Reproduce

1. Create a new service form
2. Type `check_ping!100,20%!500,60%` into the `check_command` field
3. Click elsewhere (blur the field to trigger validation/save)

## Expected Behavior

The value `check_ping!100,20%!500,60%` should be saved verbatim. The system should only validate that `check_ping` (the command name, before the first `!`) exists as a defined command object. Argument values after `!` are threshold strings passed to the plugin — they are not Nagios object references.

## Actual Behavior

- Toast: `"20%" does not exist`
- The `check_command` field is cleared (value lost)

## Impact

**Critical** — makes it impossible to set `check_command` with any plugin arguments. This breaks the primary purpose of monitoring services: nearly every real-world check command uses `!` arguments (thresholds, ports, URLs, credentials). Users cannot create usable service configurations.

## Fix Direction

When validating `check_command`, split on the first `!` and only validate the command name prefix against the defined command objects. Discard/ignore everything after the first `!` for validation purposes. Never clear the field value; at most show a warning if the command name portion doesn't exist.

## Evidence

Field before blur: `check_ping!100,20%!500,60%`
Toast after blur: `"20%" does not exist`
Field after blur: empty (value cleared)
