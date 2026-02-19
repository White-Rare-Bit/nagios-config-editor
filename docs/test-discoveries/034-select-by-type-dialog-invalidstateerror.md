# Bug 034: InvalidStateError thrown every time "Select by Type" dialog opens

**Phase:** 11 — Multi-Select Bulk Edit
**Severity:** Minor (no visible user impact observed, but indicates bad state)
**Console log:** .playwright-mcp/console-2026-02-18T19-10-31-420Z.log

## Steps to Reproduce

1. Click Select → Select by type...
2. Observe browser console

## Actual Behavior

Every invocation of "Select by type..." triggers:
```
InvalidStateError: Failed to execute 'setSelection' on 'Selection': ...
  at context-menu.js:245:23
```

Reproduced consistently on every opening of the dialog (at least 4 times during Phase 11 testing).

## Expected Behavior

No JS errors on dialog open. The error originates in `context-menu.js:245` suggesting the context menu code attempts a text selection operation on an element in an invalid state (e.g., a non-editable element, or a detached element).

## Nagios Admin Impact

Low direct impact — the dialog opens and functions correctly despite the error. However, indicates unhandled state in the selection code that could mask real errors or cause hard-to-reproduce failures in other browsers or edge cases.
