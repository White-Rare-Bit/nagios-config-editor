# BUG 007 — "+" Button Inherits Object Type From Previous Creation Form

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Major
**Category:** Creation UX

## Description

When clicking the "+" button on a file node in the tree (e.g., services.cfg), the new creation form inherits the object type from whichever creation form was most recently open, rather than defaulting to the most common type for that file.

## Steps to Reproduce

1. Open a host creation form (type = "host")
2. Navigate away or open a second creation form
3. Click the "+" button on services.cfg

## Expected Behavior

The new creation form should default to `service` type when created from services.cfg (or the most logical type for that file).

## Actual Behavior

The new creation form opens with type = `host`, inheriting from the previously open form. The tree shows the new pending object under services.cfg labeled as `(unnamed) HOST`.

## Impact

Users intending to create a service will silently create a host instead unless they notice the type dropdown. This is especially confusing because the object appears under the services.cfg node but has the wrong type.

## Evidence

- services.cfg "+" button clicked → form opened with "host ▼" type selector and host fields (address, alias, host_name, hostgroups) instead of service fields
- Tree shows "(unnamed) HOST" under services.cfg
