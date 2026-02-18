# BUG 018 — Cyclic Template Inheritance Silently Accepted, Causes JavaScript Stack Overflow

**Phase:** 6 — Template Inheritance Adversarial
**Severity:** Critical
**Category:** Validation / Crash

## Summary

Setting a template's `use` field to itself (self-referential inheritance) is accepted without validation. On blur, the value is saved to staging with no error. The cyclic inheritance then causes `RangeError: Maximum call stack size exceeded` in `relations-loader.js`, crashing the impact/relationships analysis for that object and any objects inheriting from it.

## Steps to Reproduce

1. Open the `generic-contact` template (contacts.cfg → generic-contact)
2. Click "+ Add attribute" and add a `use` field
3. Type `generic-contact` into the `use` field — autocomplete shows it as a suggestion
4. Press Enter to select, then click another field to blur
5. Observe the browser console

## Expected Behavior

The app should detect that setting `use: generic-contact` on `generic-contact` creates a direct cycle and:
- Reject the value with an error toast: `"Cannot use 'generic-contact' as a template for itself — this would create a circular dependency"`
- Not save the cyclic reference to staging

## Actual Behavior

- No error toast is shown
- The value `generic-contact` is saved to the `use` field of `generic-contact`
- The browser console immediately shows:
  ```
  RangeError: Maximum call stack size exceeded
      at relations-loader.js:1
  RangeError: Maximum call stack size exceeded
      at relations-loader.js:1
  RangeError: Maximum call stack size exceeded
      at relations-loader.js:1
  ```
- The Impact & Relationships panel crashes silently

## Extended Impact

This vulnerability is not limited to self-reference. A two-object cycle (A uses B, B uses A) would have the same effect and is equally easy to create. Nagios itself does detect such cycles, but the editor does not guard against them at edit time.

## Fix Direction

Before saving a `use` field value:
1. Walk the entire inheritance chain of the proposed parent template
2. If the current object appears anywhere in that chain, reject with a cycle-detection error
3. This should apply to all object types, not just contacts

## Evidence

- Field typed: `generic-contact` in `use` field of `generic-contact`
- Autocomplete offered `generic-contact` as a valid suggestion (no filtering to exclude self)
- No validation error or toast on blur
- Console: `RangeError: Maximum call stack size exceeded` (3+ occurrences in `relations-loader.js`)
