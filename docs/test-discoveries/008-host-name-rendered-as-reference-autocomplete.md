# BUG 008 — host_name Rendered as Reference Autocomplete in Host Creation Form

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Minor
**Category:** Creation UX / Field Rendering

## Description

In the host creation form, the `host_name` field (which is the NAME_FIELD / primary identifier for hosts) is rendered as a reference autocomplete field — showing "Type for suggestions..." placeholder and arrow-key navigation tooltip. This is incorrect: `host_name` is what you're setting, not a reference to another object.

Additionally, pressing Tab from the top "Enter name..." field auto-populates the `host_name` attribute field with the same value, which works correctly but is redundant and confusing given the reference-field rendering.

## Steps to Reproduce

1. Click "+" on any file to create a host
2. Observe the `host_name` attribute row in the form body

## Expected Behavior

`host_name` should render as a plain text input (no autocomplete suggestions, no "Type for suggestions..." placeholder) since it is the primary identifier being defined, not a reference.

## Actual Behavior

`host_name` shows the autocomplete UI: `Arrow keys to navigate suggestions, Enter to select, Escape to close` tooltip and "Type for suggestions..." placeholder.

## Impact

Low — functionally works, but the UI implies `host_name` is a lookup field, which is misleading for new users.
