# 059 — Search: No Empty-State Message When Zero Results

**Phase:** 21 — Search, Filter & Analysis
**Severity:** Minor
**Screenshot:** screenshots/phase21-search-noexist.png

## Steps to Reproduce

1. Open Object Explorer
2. Type a string that matches no objects (e.g., `zznonexistentxxx`) in the search box

## Actual Behavior

The object tree becomes completely blank. No message, label, or indicator is shown. The section headers (By File / By Type) are also hidden.

## Expected Behavior

A visible empty-state message: *"No objects matching 'zznonexistentxxx'"* or *"0 results"* — something that confirms the search worked and returned zero results, rather than appearing broken.

## Admin Impact

An admin who mistyped a hostname sees blank space and has no feedback. They may think search is broken, the app crashed, or their configuration files are empty. This erodes trust in a tool where mistyped searches are common.
