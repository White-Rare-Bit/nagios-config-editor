# Ctrl+Z Keyboard Shortcut Fires API Call Even When Undo Is Disabled

**Phase**: Phase 3 — Keyboard Navigation Gauntlet
**Severity**: Minor
**Category**: State Management

## What Was Tested

Pressed Ctrl+Z while staging state was empty (no pending edits, no staged operations).
The Undo button in the navbar was visually disabled (`[disabled]` attribute set).

## Expected Behavior

When there is nothing to undo, Ctrl+Z should:
- Do nothing (silently ignore the keypress), OR
- Show a toast: "Nothing to undo"

No API call should be made when the undo stack is empty.

## Actual Behavior

Pressing Ctrl+Z fired a request to `POST /api/staging/undo` even though:
1. The Undo button was disabled
2. The undo stack was empty

The server responded with **404 Not Found**, resulting in a console error:
```
Failed to load resource: the server responded with a status of 404 (NOT FOUND) @ /api/staging/undo
```

The UI silently swallowed the error — no error message was displayed to the user, and the page remained functional.

## Screenshot

`screenshots/07-ctrlz-with-empty-undo.png`

## Impact

- Silent 404 errors accumulate in the browser console, making debugging harder
- The keyboard handler does not check the disabled state of the Undo button before firing the API call
- Minor usability concern: users pressing Ctrl+Z repeatedly (a common habit) generate unnecessary API traffic

## Root Cause (Hypothesis)

The Ctrl+Z keyboard handler likely calls the undo API directly rather than triggering a click on the (disabled) Undo button. The button's `disabled` attribute guards against mouse clicks but the keyboard shortcut bypasses this guard.

The fix would be to check `if (undoButton.disabled) return;` in the keyboard handler before making the API call.
