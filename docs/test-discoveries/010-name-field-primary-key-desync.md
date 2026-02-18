# BUG 010 — Name Field and Primary Key Attribute Desync After Initial Fill

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Major
**Category:** Creation UX / Data Binding

## Description

In object creation forms, the top "Enter name..." field is supposed to stay in sync with the primary key attribute field (e.g., `service_description` for services). After the first auto-population (via Tab key), subsequent changes to the top name field do NOT immediately update the corresponding attribute field in the form body.

## Steps to Reproduce

1. Create a new service form
2. Type a name in the top "Enter name..." field (e.g., "PING")
3. Press Tab — `service_description` auto-populates with "PING" ✓
4. Change the top name field to a different value (e.g., "E2E PING Check")
5. Observe `service_description` in the form body

## Expected Behavior

`service_description` should update to "E2E PING Check" immediately and stay in sync with the name field.

## Actual Behavior

`service_description` retains the old value "PING" initially. The sync eventually occurs through subsequent interactions (clicking other fields, etc.) but is not reliable or immediate.

## Impact

Users may set a name in the header field but have a different (stale) `service_description` submitted to the staging system. Could cause invisible data inconsistency between what the user sees in the name field vs. what gets staged.

## Note

The desync was observed during testing but appeared to self-correct in some scenarios (eventual consistency). The exact trigger for re-sync is unclear.
