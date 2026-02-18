# 024 — No Attribute Value Length Limit on Input Fields

**Phase:** 7 — Error Handling
**Severity:** Minor
**Category:** Validation / UX

## Steps to Reproduce

1. Open any object in the editor (e.g., `web-prod-01` host)
2. Click the `address` attribute field
3. Paste or type 5000+ characters (e.g., `'A' * 5000`)
4. Observe: value is accepted with no warning or truncation

## Actual Behavior

The `address` field (and other plain-text attribute fields) has no `maxlength` HTML attribute. Values of 5000+ characters are accepted by the browser and staged without validation error.

Timing: 5000 chars filled in ~27ms (no hang — good).

## Expected Behavior

Attribute fields that represent specific Nagios values (e.g., IP address, hostname, command name) should enforce a reasonable maximum length. For `address` specifically, a 255-char limit would be appropriate (max hostname/IP length).

Alternatively, a general cap (e.g., 2000 chars) could be enforced for all single-line fields to prevent config file pollution.

## Notes

- Multi-line values via keyboard (`Shift+Enter`) are correctly prevented by `<input type="text">` (browser-native)
- JS injection of `\n` into input values is also stripped by the browser
- The large-value concern is primarily: 1) cosmetic (breaks layout), 2) produces invalid Nagios config that fails `nagios -v`
- No server-side length validation was observed on the staging endpoint either
