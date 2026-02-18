# BUG 015 — Wildcard `*` in host_name Rejected as Invalid Object Reference; Field Cleared

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Critical
**Category:** Validation / Data Loss

## Description

When a `host_name` value of `*` (Nagios wildcard syntax for "all hosts") is entered in a service creation form and the field is blurred, the system validates it as an object reference, fails to find an object named `*`, fires an error toast, and clears the field value.

## Steps to Reproduce

1. Open a service creation form
2. Click the `host_name` field
3. Type `*` (Nagios wildcard for "apply service to all hosts")
4. Blur the field (click elsewhere or press Tab)

## Expected Behavior

The value `*` should be accepted verbatim. Nagios uses `*` as a special wildcard value in `host_name` meaning the service applies to all hosts. It is not an object reference — it is a special keyword and should never be validated against the list of defined host objects.

## Actual Behavior

- Autocomplete dropdown opens showing all hosts (treating `*` as a wildcard filter to show everything — the filtering behavior is correct)
- On blur: Toast `"*" does not exist`
- The `host_name` field is cleared (value lost)

## Impact

**Critical** — prevents creating services that should apply to all hosts, which is a common real-world Nagios pattern (e.g., a PING check or security-scan service that runs on every monitored host). Same root cause as BUG 014.

## Root Cause

Same as BUG 014: the reference field validation treats the field value as a strict object reference lookup. Special Nagios syntax values (`*`, `+groupname`, negations) are not given any special treatment.

## Fix Direction

Before performing object-reference validation on a field value:
1. Check if the value is a Nagios special keyword (`*`, values with `+` prefix for additive inheritance, etc.)
2. If so, skip validation and accept the value verbatim

## Evidence

Field value typed: `*`
Autocomplete behavior: shows all hosts (correct — wildcard filter works)
Toast on blur: `"*" does not exist`
Field after blur: empty (value cleared)

## Related Bugs

- BUG 014: Same root cause — `check_command` argument values after `!` validated as object references
