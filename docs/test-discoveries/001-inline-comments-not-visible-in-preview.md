# BUG-001: Inline Comments Not Visible in Quick Preview (Spacebar)

**Phase:** 16 — Comments Preservation
**Severity:** Minor
**Date:** 2026-02-19

## Summary

The spacebar quick preview modal does not show inline comments (`;` comments) that exist in the config file. Comments are silently stripped from the displayed config block.

## Steps to Reproduce

1. Add a Nagios object with inline comments to a .cfg file, e.g.:
   ```
   define host {
       address    192.168.9.99  ; primary management IP
       alias      My Host       ; production server
   }
   ```
2. Open the Object Explorer at `/explorer`
3. Click on the object in the tree
4. Press Spacebar to open the quick preview modal

## Actual Behavior

The preview modal shows the object without inline comments:
```
define host {
    address    192.168.9.99
    alias      My Host
}
```

## Expected Behavior

Inline comments should be visible in the preview, matching the actual file content:
```
define host {
    address    192.168.9.99 ; primary management IP
    alias      My Host      ; production server
}
```

## Root Cause

`GET /api/objects` response does not include the `inline_comments` field from `NagiosObject`. The parser correctly parses and stores inline comments in `NagiosObject.inline_comments` (a dict), but the API serialization omits this field. The frontend therefore has no access to comment data when rendering the preview.

**Relevant code:**
- `nagios_parser.py:221` — `inline_comments` dict populated during parse
- `nagios_model.py:416` — `inline_comments` field on `NagiosObject`
- `nagios_model.py:563` — `format_object_block` adds comments to output when provided
- API response: missing `inline_comments` field entirely

## Impact

- Admins using quick preview to verify config text will see a different representation than what is on disk
- Could cause confusion — admin sees "clean" preview but file actually has comments
- Not a data-loss bug (comments are preserved on disk), but misleading UX

## Screenshot

See: `screenshots/phase16-03-spacebar-preview.png`

## Workaround

None within the UI. Comments are only visible by reading the file directly.
