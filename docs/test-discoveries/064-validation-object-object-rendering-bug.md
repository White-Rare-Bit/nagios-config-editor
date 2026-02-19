# 064 — Validation Tab Shows "[object Object]" in Error Output

**Phase:** 21 — Search, Filter & Analysis
**Severity:** Minor
**Screenshot:** screenshots/phase21-validation-result.png

## Steps to Reproduce

1. Open the Workspace panel → **Validation** tab
2. Click **Run Validation**
3. Observe the error output when the Nagios binary is not found

## Actual Behavior

The validation result shows:

```
CONFIGURATION IS INVALID

ERRORS:
[object Object]

Binary verification failed: Binary not found: /usr/local/nagios/bin/nagios
```

The first error line renders `[object Object]` — a JavaScript object that was not properly serialized to a string before being inserted into the DOM.

## Expected Behavior

The error details should display the actual error message text (e.g., the specific validation failure message or exception detail), not the raw JavaScript object reference.

## Root Cause

Likely a template literal or string concatenation using an Error object directly (e.g., `` `${error}` `` or `"" + error`) instead of `error.message` or `JSON.stringify(error)`.

## Admin Impact

When a Nagios admin runs validation on a system where the Nagios binary path is misconfigured, they see `[object Object]` as the primary error, which is meaningless. Additionally, there is no link to Settings to fix the binary path. The admin is left with no actionable guidance.

## Secondary Issue

The error message "Binary not found: /usr/local/nagios/bin/nagios" does not tell the admin where to configure a different path. A link to Settings → Nagios binary path would make this actionable.
