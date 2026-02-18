# BUG 013 — check_command Autocomplete Resets to All Commands After "!" Character

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Minor
**Category:** Autocomplete UX

## Description

When typing in the `check_command` field, autocomplete correctly filters commands by the typed prefix (e.g., typing "check_ping" shows only `check_ping`). However, after typing the `!` argument separator, the autocomplete dropdown resets to showing ALL available commands instead of closing.

## Steps to Reproduce

1. Open a service creation form
2. Click `check_command` field
3. Type `check_ping` — dropdown shows `check_ping` as the only suggestion ✓
4. Type `!` to begin entering arguments
5. Continue typing (e.g., `!100,20%`)

## Expected Behavior

After typing `!`, the autocomplete should close (or at minimum not show suggestions), since the user is now entering argument values for the already-selected command name, not searching for a new command.

## Actual Behavior

The autocomplete dropdown resets to showing all ~20 commands (check-host-alive, check_ad_replication, check_apache_status, etc.), treating the text after `!` as a new command search query.

## Impact

Minor UX issue — the dropdown is confusing but doesn't block the user. The value `check_ping!100,20%!500,60%` is correctly entered into the field; the stale dropdown is just noise. However, a user might accidentally select a command from the dropdown and overwrite the partial value they typed.

## Fix Direction

For `check_command` fields, autocomplete should treat `!` as a terminator — either close the dropdown when `!` is typed, or only suggest against the portion of text before the first `!`.
