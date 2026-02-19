# 062 — Combined Orphans+Issues Filter Uses AND Logic Instead of OR

**Phase:** 21 — Search, Filter & Analysis
**Severity:** Minor
**Screenshot:** screenshots/phase21-combined-filters.png

## Steps to Reproduce

1. Enable the **Issues** filter — tree shows ~88 objects across many files (commands:35, hosts:30, etc.)
2. Enable **Orphans** in addition — tree collapses back to 26 objects (commands:4, contacts:2, etc.)

## Actual Behavior

When both Orphans and Issues are checked, the tree shows the intersection (AND): only objects that are both orphaned AND flagged as issues. Since all orphaned objects are also flagged as issues, the combined result equals the orphan set alone (26 objects), hiding the 60+ additional non-orphan issues.

## Expected Behavior

When both filters are enabled, the tree should show the union (OR): all objects that are either orphaned OR have issues. This gives an admin a comprehensive "show me everything that needs attention" view.

## Admin Impact

An admin who checks both boxes hoping for a comprehensive audit sees **fewer** objects than with Issues alone. The combined view appears to "work" (it shows the orphan set) but silently hides 60+ additional issue-flagged objects like the 30 hosts with broken notification chains, the 12 contacts with issues, and the service with missing check_command. This creates false confidence in the configuration's health.
