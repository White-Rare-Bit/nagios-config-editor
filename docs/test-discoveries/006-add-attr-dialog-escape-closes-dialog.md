# Escape in Add Attribute Dialog Closes Entire Dialog Instead of Autocomplete Dropdown

**Phase**: Phase 4 — Create Objects (Compound Creation)
**Severity**: Minor
**Category**: UI/UX

## What Was Tested

1. Clicked "+ Add attribute" on a new host object
2. "Add Attribute" dialog opened with attribute name field and autocomplete dropdown
3. Clicked `check_command` in the dropdown to select it
4. Clicked the value field and typed `check_ping!100.0,20%!500.0,60%`
5. An autocomplete dropdown appeared (showing attribute name suggestions like `check_ad_replication`)
6. Pressed Escape to dismiss the autocomplete dropdown

## Expected Behavior

Escape should close the autocomplete dropdown while keeping the "Add Attribute" dialog open. Standard modal+autocomplete behavior: inner Escape → close autocomplete; outer Escape → close dialog.

## Actual Behavior

Pressing Escape closed the entire "Add Attribute" dialog, discarding the attribute name (`check_command`) and the value already entered (`check_ping!100.0,20%!500.0,60%`).

## Also Observed

Typing in the **value** textbox triggered the attribute **name** autocomplete dropdown (showing `check_ad_replication`, etc.), even though the cursor was in the value field. This may be an event bubbling issue: keystrokes in the value field are being picked up by the name field's autocomplete handler.

## Impact

A user who:
1. Opens "Add Attribute" dialog
2. Types a value with `check_` prefix
3. Sees an unexpected autocomplete dropdown appear
4. Presses Escape to dismiss it

...loses all their dialog input and must start over. In practice this is a recoverable annoyance, but it breaks the expected UX for dialogs with inner autocompletes.
