# Bug 048: Service Node Labels Show Only Description, Not Full Identity

## Severity
**Major**

## Summary
Service nodes in the graph canvas display only the `service_description` (e.g., "HTTP"), not the full compound identity ("HTTP on web-servers"). In a real Nagios config where dozens of hostgroups each have an "HTTP" or "PING" service, the graph becomes unreadable — all "PING" services from different hostgroups look identical.

## Evidence
- Canvas node label: "HTTP"
- Node sidebar label: "HTTP on web-servers" (compound name correctly shown here)
- Graph node ID: `service:web-servers:HTTP` (correct internally)

The sidebar uses the full name but the canvas node — the primary visual element — shows only the bare description.

## Steps to Reproduce
1. Add two services with the same description but different hostgroups to the graph (e.g., "PING on linux-hosts" and "PING on windows-hosts")
2. Both nodes render with the label "PING"
3. No visual distinction between them in the canvas

## Expected Behavior
Node label should show either:
- "HTTP / web-servers" (description / hostgroup)
- "HTTP on web-servers" (matching the Nagios display convention)

## Impact
In any production Nagios config with multiple hostgroups, service nodes in the graph are visually indistinguishable. An admin investigating "which HTTP service has this dependency?" cannot tell the nodes apart. This is a fundamental readability issue for the graph's core use case.
