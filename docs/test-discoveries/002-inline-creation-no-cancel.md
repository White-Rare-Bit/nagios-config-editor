# Bug 002: Inline Object Creation Has No Cancel Mechanism

**Phase:** 13 — Dialog Cancellation
**Severity:** Major
**Category:** Dialog Cancellation / State Pollution

## Steps to Reproduce

1. Click the `+` button next to any file in the By File tree (e.g., `commands.cfg`)
2. Note that staged count immediately increments (38→39)
3. Press `Escape` while the inline name field is focused
4. Check staged count

## Actual Behavior

- Clicking `+` immediately stages a new object — there is no "open dialog then confirm" flow; the object enters staging before the user provides any input
- After pressing `Escape`, staged count remains 39 (object is NOT removed)
- The inline editor remains open after Escape
- Only `Ctrl+Z` (Undo) removes the staged creation

## Expected Behavior

Option A (preferred): Show a dialog with a Cancel button before staging anything
Option B: Pressing `Escape` in the inline name field should discard the creation and revert staging

## Impact

Operational risk: An admin who accidentally clicks "+" (easy to do when trying to expand a file section) immediately pollutes staging with an unwanted object. If they then commit without noticing, a misconfigured empty object is written to disk. The Undo path is non-obvious and requires knowing the keyboard shortcut.

## Screenshot

`.playwright-mcp/screenshots/task16-bug-plus-button-immediate-stage.png`
