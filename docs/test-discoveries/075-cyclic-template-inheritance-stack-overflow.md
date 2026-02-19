# 075 — Cyclic Template Inheritance Causes Frontend Stack Overflow

**Phase:** 26 — Cascading Dependency Stress
**Severity:** Major
**Category:** Data Integrity / Crash

## Summary

The app allows staging a cyclic `use` directive (e.g., template A uses template B while template B already uses template A) without any validation error. When the staged cyclic relationship is accepted, the frontend's inheritance chain resolver (`buildParentChain` in `relations-loader.js`) recursively follows the cycle until the JavaScript call stack is exhausted. This produces 3+ `RangeError: Maximum call stack size exceeded` errors and silently breaks the Impact & Relationships panel.

## Steps to Reproduce

1. Verify that `linux-server` template uses `generic-host` (this is the default in sample config).
2. Open `generic-host` template in the Object Explorer.
3. Click "+ Add attribute". Set Name: `use`, Value: `linux-server`. Click OK.
4. The edit is staged silently — no cycle warning shown.

## Actual Behavior

```
RangeError: Maximum call stack size exceeded
    at relations-loader.js:1
    at Array.find
    at findTemplate (relations-loader.js:1)
    at buildParentChain (relations-loader.js:1)
    at buildParentChain (relations-loader.js:1)
    at buildParentChain (relations-loader.js:1)
    ... (repeating)
```

- Error occurs 3+ times immediately after the edit is staged.
- The `generic-host` form shows `use: linux-server` with no visual warning.
- The Impact & Relationships panel silently fails to render (infinite loop aborted by engine).
- The edit remains staged with no indication to the admin that it is invalid.

## Expected Behavior

The app should:
1. Detect the cycle before staging the edit and display an error: "This `use` directive creates a circular inheritance chain: generic-host → linux-server → generic-host"
2. Reject the edit (prevent staging) or show a prominent warning

## Why This Matters

A Nagios config with a cyclic `use` directive will cause Nagios to fail to start (`Error: Circular object template dependency detected`). An admin who stages this change and commits will break Nagios entirely. The frontend crash is a secondary concern — the real danger is that the invalid config reaches disk.

## Root Cause (Hypothesis)

`buildParentChain` in `relations-loader.js` follows `use` directives recursively without maintaining a `visited` set to detect cycles. Fix: add cycle detection with a `Set` of template names already visited.

## Screenshots

- `phase26-cyclic-inheritance-staged.png` — generic-host showing `use: linux-server` with no warning
- `phase26-cyclic-stack-overflow.png` — same state showing staged edit accepted

## Fix Suggestion

```javascript
function buildParentChain(template, allTemplates, visited = new Set()) {
  if (visited.has(template.name)) {
    console.warn('Circular template dependency detected:', template.name);
    return [];
  }
  visited.add(template.name);
  // ... rest of chain building using visited
}
```

Validation should also run at staging time to reject the edit with a user-visible error.
