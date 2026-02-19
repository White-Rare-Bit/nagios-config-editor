# 058 — hostgroup_name and service_description Missing Autocomplete

**Phase:** 20 — Escalation & Dependency Chains
**Severity:** Major
**Category:** Autocomplete / Reference Fields

## Summary

The fields `hostgroup_name`, `service_description`, and `host_name` do not render with autocomplete suggestions in escalation/dependency object types — despite being defined as global reference fields in the metadata (`hostgroup_name → hostgroup`, `service_description → service`, `host_name → host`). The bug affects the "subject" reference fields in these types (i.e., the fields describing which host/service/hostgroup the object applies to).

## Steps to Reproduce

1. Open the Object Explorer and navigate to any serviceescalation (By Type → serviceescalation)
2. Click the `hostgroup_name` field to edit it
3. Observe: no autocomplete dropdown appears, no "Arrow keys to navigate suggestions" aria-label

**Repeat for:**
- `service_description` field in a serviceescalation
- `hostgroup_name` field in a servicedependency
- `service_description` field in a servicedependency
- `hostgroup_name` field in a service
- `service_description` field in a service

## Actual Behavior

These fields render as plain text inputs with no autocomplete. The user must type the exact value manually, with no suggestions from the existing objects in the config.

## Expected Behavior

Both fields are declared in the global `reference_fields` map in `nagios_model.py`:
- `hostgroup_name: hostgroup`
- `service_description: service`

Clicking these fields should show autocomplete suggestions listing existing hostgroup names (for `hostgroup_name`) or existing service descriptions (for `service_description`), consistent with how other reference fields like `contact_groups`, `check_command`, `use`, etc. behave.

## Contrast: Working Fields in the Same Objects

In servicedependency, the **dependent_** prefixed versions DO get autocomplete:
- `dependent_hostgroup_name` → autocomplete ✓
- `dependent_service_description` → autocomplete ✓

This suggests the autocomplete logic may only apply the field name lookup verbatim from `reference_fields`, while the `dependent_*` variants are mapped separately (possibly via object-type-specific metadata or a prefix-stripping rule that works for `dependent_*` but not for the base fields in this context).

## Impact

For a Nagios admin, these are critical fields in escalation/dependency configuration. Without autocomplete:
- Typos in hostgroup or service names create silent misconfiguration — Nagios silently ignores invalid references in some object types
- No discoverability of available values
- Particularly painful for `service_description` which must match exactly (case-sensitive)

## Affected Object Types

- `service` — `hostgroup_name`, `service_description`
- `serviceescalation` — `hostgroup_name`, `service_description`
- `servicedependency` — `hostgroup_name`, `service_description`
- `hostescalation` — `hostgroup_name` (confirmed)
- `hostdependency` — `host_name` (confirmed; no autocomplete despite being a host reference)

## Screenshot

`docs/test-discoveries/screenshots/phase20-serviceescalation-editor.png`
