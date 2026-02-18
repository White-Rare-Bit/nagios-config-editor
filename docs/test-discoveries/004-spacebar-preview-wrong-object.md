# Spacebar Quick Preview Shows Keyboard-Focused Object, Not Selected Object

**Phase**: Phase 3 — Keyboard Navigation Gauntlet
**Severity**: Minor
**Category**: UI/UX

## What Was Tested

1. Clicked `web-prod-01` in the tree — center panel updated to show web-prod-01
2. Previously pressed ArrowDown 6 times, which moved keyboard focus through the tree
3. Clicked `web-prod-01` in the tree (center panel updated)
4. Pressed Spacebar

## Expected Behavior

Spacebar quick preview should show the raw Nagios config block for the **currently displayed** object (web-prod-01, shown in the center panel).

The preview format itself was correct: `define host { address ..., alias ..., host_name ..., ... }`

## Actual Behavior

The preview opened with title "host: web-prod-02" and showed web-prod-02's attributes — the object with keyboard focus in the tree (from prior ArrowDown navigation), NOT the object displayed in the center panel.

## Screenshot

`screenshots/06-spacebar-preview.png`

## Impact

A user who:
1. Clicks an object (center panel shows it)
2. Navigates the tree with arrow keys to browse
3. Then presses Space expecting to preview the currently displayed object

…instead gets a preview of the tree-highlighted item, not the one they were editing. This creates confusion between "what is displayed" and "what is keyboard-focused" — two separate states that users may not distinguish visually.

## Also Observed

- Escape correctly closes the quick preview ✓
- The quick preview format (`define host { ... }`) is correct Nagios syntax ✓
- Enter on a keyboard-focused tree item does NOT open it in the center panel (no observable effect)
