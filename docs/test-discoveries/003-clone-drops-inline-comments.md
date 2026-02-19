# BUG-003: Clone Does Not Preserve Inline Comments

**Phase:** 16 — Comments Preservation
**Severity:** Minor
**Date:** 2026-02-19

## Summary

Cloning a Nagios object that has inline (`;`) comments produces a clone without any comments. The admin's annotations are silently dropped.

## Steps to Reproduce

1. Have a Nagios object with inline comments in a .cfg file:
   ```
   define host {
       host_name          comment-test-host
       address            192.168.9.99  ; primary management IP
       alias              Comment Test Host  ; production server
       max_check_attempts 4  ; reduced for testing
   }
   ```
2. Right-click the object in the Object Explorer tree
3. Click **Clone...**
4. Enter a new name and click **Clone**
5. Apply the staged changes

## Actual Behavior

The cloned object has no inline comments:
```
define host {
    host_name          comment-test-host-copy
    address            192.168.9.99
    alias              Comment Test Host
    max_check_attempts 4
}
```

## Expected Behavior

The clone should preserve inline comments from the source:
```
define host {
    host_name          comment-test-host-copy
    address            192.168.9.99  ; primary management IP
    alias              Comment Test Host  ; production server
    max_check_attempts 4  ; reduced for testing
}
```

## Root Cause

The clone workflow stores only `attributes` (the values dict) in `stagedCreations`. The `inline_comments` dict from `NagiosObject` is not passed through:

- `nagios_service.py:984` — `attributes = creation.get("attributes", {})` only
- `nagios_service.py:991` — `create_object(target_file, object_type, attributes)` — no `inline_comments` arg
- The frontend clone dialog captures `state.editedObject.attributes` but not `state.editedObject.inline_comments` (which is absent from the API response anyway — see BUG-001)

## Contrast With Move

Move operations DO preserve inline comments because they use raw block surgery (`file_operations.py:move_object_between_files`), which copies the original text verbatim rather than regenerating it from attributes.

## Impact

Low-severity for most use cases (comments are metadata, not config semantics). However, for admins who use comments to annotate important context (e.g., IP ownership, escalation notes, change history), cloning silently loses that information. An admin cloning a heavily-annotated object may not notice the comment loss until they review the file directly.

## Fix Suggestion

1. Include `inline_comments` in the `/api/objects` response
2. Pass `inline_comments` through the clone staging chain to `create_object`

## Screenshot

See: `screenshots/phase16-09-clone-dialog.png`

## Verification

Original in templates.cfg:
```
address    192.168.9.99 ; primary management IP
alias      Comment Test Host ; for Phase 16 comment preservation testing
hostgroups linux-hosts ; auto-assigned group
max_check_attempts 4 ; reduced for testing
```

Clone in templates.cfg:
```
address    192.168.9.99
alias      Comment Test Host
hostgroups linux-hosts
max_check_attempts 4
```
