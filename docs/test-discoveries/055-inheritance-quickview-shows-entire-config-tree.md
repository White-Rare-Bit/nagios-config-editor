# Bug 055: Inheritance Quick View Shows Entire Config Inheritance Tree, Not Just Selected Host's Chain

**Severity**: Medium
**Area**: Graph View — Quick Views / Inheritance
**Discovered**: 2026-02-19

## Description

When applying the "Inheritance" quick view for a host, the graph expands to show **all hosts in the configuration that share any common ancestor** — not just the selected host's template chain. For `web-prod-01` (which uses `linux-server → generic-host`), Inheritance expands to 32 hosts, including network devices (firewall-02, core-switch-02, router-main, vpn-gateway) and Windows servers that have nothing to do with web-prod-01's configuration.

## Steps to Reproduce

1. Open Graph View, add `web-prod-01` (host) via search
2. Quick Views shows "FOR HOST" — click "Inheritance"
3. Observe: 32 nodes appear, all of type "host"
4. Inspect list: includes `firewall-02`, `core-switch-02`, `vpn-gateway`, `windows-server` — completely unrelated to web-prod-01

## Root Cause

The Inheritance quick view uses `expandWithRules` with `categories: ['templates']`. The edge filter enables `use` edges in both directions. The expansion rule follows ALL `use` edges bidirectionally from the starting node:

- `web-prod-01 → linux-server` (via `use`)
- `linux-server ← [18 hosts using linux-server as template]` (reverse `use`)
- `linux-server → generic-host` (via `use`)
- `generic-host ← [ALL hosts using generic-host as template]` (reverse `use`)

Once `generic-host` is reached as the common ancestor, every host in the config that inherits from `generic-host` is pulled in — expanding to the entire template tree.

## Expected Behaviour

The Inheritance quick view should show only the **selected object's direct ancestry chain** and optionally its direct children:

```
Expected:  generic-host → linux-server → web-prod-01
                                        ↳ web-prod-02, web-prod-03 (siblings OK)

Got:       [entire 32-host config tree]
```

A Nagios admin applying Inheritance on a host wants to answer: *"What templates does this host inherit from, and what inherits from those templates directly?"* — not *"What does the entire config's inheritance graph look like?"*

## Impact

- **Cognitive overload**: 32 nodes for a simple host is overwhelming and obscures the actual chain
- **Misleading**: Including network devices and Windows servers suggests they're related to web-prod-01
- **Inheritance view is effectively broken** as a tool for understanding a specific object's inheritance — it always degenerates to showing the full config tree for hosts that share any common ancestor (which is almost all hosts)

## Additional Context

For `linux-server` (which is itself a template used by 18 hosts), Inheritance also returns 32 nodes — the same result as for web-prod-01. The view is not specific to the selected node.

The correct chain for `web-prod-01` is: `web-prod-01 → linux-server → generic-host` (3 nodes).
