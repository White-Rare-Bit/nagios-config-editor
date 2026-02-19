# Assessment 053: Graph Quick Views — Critical Usefulness Evaluation

## Severity
**N/A** (design assessment, not a single bug)

## Overview
Beyond Bug 044 (all category-based presets broken due to missing edge `category` field), this assessment evaluates whether the quick view system is well-designed for Nagios administrators, assuming the category bug were fixed.

---

## Quick Views That Would Be Genuinely Useful (if fixed)

### ✅ Host → Notifications
"Who gets paged when this host goes down?" is the most frequent on-call question. Traversing `host → contactgroups → contacts` and showing it as a hierarchy is extremely valuable.

### ✅ Host → Services
"What is this host monitoring?" — straightforward and useful, though an admin can answer this in the Explorer too.

### ✅ Service → Dependencies
"What must be UP before this service is checked?" — critical for understanding false-alert suppression chains.

### ✅ Service → Escalations
"At what point does this alert go to the on-call manager?" — useful for SLA review.

### ✅ Command → Used By
"If I modify or delete this check command, what breaks?" — the most useful view for commands. Correct design.

### ✅ Timeperiod → Used By
Same as command — high value for impact analysis.

### ✅ Contactgroup → Members + Notified By
Bidirectional view of a contactgroup is the right design.

---

## Quick Views With Serious Design Problems

### ❌ Contact → Notified By (structurally broken by design)
Services notify *contactgroups*, never contacts directly. The `notifiedBy` preset would need to traverse:
`contact ← members ← contactgroup ← contact_groups ← host/service`

No direct edges exist from services to contacts. This two-hop reverse traversal is not represented in the graph data or traversal logic. The feature as designed cannot work.

**What's needed:** Either add `service → contact` resolved edges to the graph data, or implement multi-hop traversal.

### ❌ Servicegroup → Members (no edges exist)
See Bug 049. Servicegroups have zero service member edges. The "Members" preset would expand to nothing even if Bug 044 were fixed.

### ❌ "Network" for escalation/dependency objects
See Bug 051. Applied to types where host parent-child topology is irrelevant.

### ⚠️ Host → Network (parent-child topology)
Conceptually correct — shows `host:X parents host:Y` relationships. However, in modern infrastructure (and in the sample config), `parents` is rarely used compared to `hostdependency` objects. The `hostdependency` object type is the correct way to model network topology in Nagios, but "Network" preset targets the `parents` attribute. An admin could be confused about the difference.

### ⚠️ Service → Inheritance
Shows `service → use → service-template → use → generic-service` chain. Useful for debugging wrong check intervals or inherited defaults. However, the Full Graph expansion for services does NOT follow the `use` edge (template is absent from service Full Graph — tested: HTTP service expanded to 17 nodes, none of which were `local-service` or `generic-service`). This suggests the "templates" category edge is not generated for services or is not working even in Full Graph.

---

## Structural Issues With the Graph Model

### Services identified by hostgroup, not host
Nagios services use either `host_name` or `hostgroup_name`. The graph correctly models this. However, it means a "Services" view for an individual host must traverse `host → hostgroup membership → servicegroup-bound services` — a multi-hop path that the category-based system may not handle.

### Reverse traversal is missing
Many useful admin questions require reverse-direction traversal:
- "What notifies this contact?" (contact ← contactgroup ← service)
- "What services are in this servicegroup?" (servicegroup ← service)
- "Who depends on this service?" (servicedependency ← service)

The current graph model only follows forward edges from the root node. An "inbound connections" capability is missing.

---

## Overall Verdict

The quick view system has the **right intent** — context-sensitive views for each object type are exactly what a Nagios admin needs. The preset selection per type is mostly sensible. However, the implementation has 3 layers of problems stacked on each other:

1. **Bug 044**: All category-filtered presets broken (no `category` field on edges)
2. **Bug 049**: Servicegroup member edges missing entirely
3. **Design gaps**: Contact "Notified By" and service "Inheritance" are architecturally incomplete even if 1 and 2 were fixed

The Full Graph preset (which bypasses categories) works and produces useful output for hosts, services, and complex types like servicedependencies and escalations. As a workaround it is reasonable. But it's too noisy for large configs — it can pull in 70+ nodes from a single host.
