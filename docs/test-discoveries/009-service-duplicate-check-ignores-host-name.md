# BUG 009 — Service Duplicate Check Uses service_description Alone (Not Composite Key)

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Critical
**Category:** Validation / Data Integrity

## Description

When creating a new service, the duplicate name check validates `service_description` in isolation rather than the composite key `(host_name, service_description)`. In Nagios, a service is uniquely identified by the combination of host_name + service_description — multiple hosts can each have a service named "PING" without conflict.

## Steps to Reproduce

1. Observe that services.cfg already has a service named "PING" on host "linux-hosts"
2. Create a new service for a different host (e.g., `e2e-compound-host-01`)
3. Set `service_description` to "PING"

## Expected Behavior

No duplicate error — "PING" on "e2e-compound-host-01" is a distinct service from "PING" on "linux-hosts".

## Actual Behavior

Error toast: `"Error: service 'PING' already exists in services.cfg"` — rejecting the creation based on `service_description` alone.

## Impact

**Critical** — this prevents valid Nagios configurations from being created. Any attempt to use the same service name (e.g., "PING", "HTTP", "SSH") across multiple hosts will be incorrectly rejected. This is a fundamental misunderstanding of the Nagios service identity model.

## Fix Direction

Duplicate detection for service objects must use the composite key `(host_name, service_description)`, not `service_description` alone. Same applies to servicedependency and serviceescalation objects which also use composite keys.
