# 020 — Ctrl+Z Undoes Multiple Operations in One Keystroke

**Phase:** 6 — Template Inheritance Adversarial
**Severity:** Major
**Category:** Undo Stack

## Steps to Reproduce

1. Have 8 staged creations + 1 pending edit in staging (9 commit items shown)
2. Stage a "Move to file" on `linux-server` template → badge becomes 10
3. Press Ctrl+Z once

## Actual Behaviour

The commit badge drops from 10 → 8, meaning **two operations** were undone in a single Ctrl+Z:
- The staged move was removed (stagedMoves: 1 → 0)
- One staged creation was also removed (stagedCreations: 8 → 7)

## Expected Behaviour

A single Ctrl+Z should undo exactly one operation (the most recent). Badge should go 10 → 9.

## Verified State (via API after undo)

| Field | Before undo | After undo |
|-------|-------------|------------|
| pendingEdits | 1 | 1 |
| stagedCreations | 8 | 7 |
| stagedMoves | 1 | 0 |
| Commit badge | 10 | 8 |

## Screenshot

`screenshots/phase6-after-undo-move.png`

## Notes

The two removed operations (move + creation) were unrelated — created in separate user
interactions. This suggests the undo stack may be grouping unrelated operations or using
an incorrect pop strategy.
