# Nagios Semantic Issues: Attribute Editor

## Overview

This document captures gaps in how the attribute editor displays Nagios object relationships and dependencies. The current implementation handles basic references well but misses important Nagios-specific semantics.

---

## Critical Gaps

### 1. hostdependency and servicedependency Objects Ignored

**Location**: `object-editor.js:2151-2486`

**Problem**: Objects of type `hostdependency` and `servicedependency` define relationships themselves but are NOT displayed as relationship documents. They're treated as regular objects.

**Example config**:
```
define hostdependency {
    host_name                       db-prod-master
    dependent_host_name             web-prod-01,web-prod-02,web-prod-03
    execution_failure_criteria      n
    notification_failure_criteria   d,u
}

define servicedependency {
    host_name                       database-servers
    service_description             MySQL
    dependent_host_name             database-servers
    dependent_service_description   MySQL Slave Status
    execution_failure_criteria      w,c,u
}
```

**Current behavior**: When viewing host `db-prod-master`:
- Shows `parents` relationship in inheritance section
- Does NOT show hostdependency objects where it's the master
- Does NOT show servicedependency objects that reference it
- User must manually find these in config files

**Impact**: Users can't see the full dependency chain for a host or service. Critical monitoring dependencies are invisible.

**Recommendation**: When viewing a host/service, scan for hostdependency/servicedependency objects where this object is referenced and display them in the Dependencies/Dependents sections.

---

### 2. Incomplete Frontend Reference Fields

**Location**: `object-editor.js:43-93` vs `nagios_model.py:50-114`

**Problem**: Frontend `ATTR_REFERENCE_MAP` is incomplete compared to backend `REFERENCE_FIELDS`.

**Missing from frontend**:
| Field | Target Type | Used By |
|-------|-------------|---------|
| `service_description` | service | servicedependency, serviceescalation |
| `dependent_service_description` | service | servicedependency |
| `master_service_description` | service | servicedependency |
| `obsess_over_host_command` | command | host |
| `obsess_over_service_command` | command | service |
| `ocsp_command` | command | nagios.cfg |
| `ochp_command` | command | nagios.cfg |
| `global_host_event_handler` | command | nagios.cfg |
| `global_service_event_handler` | command | nagios.cfg |

**Impact**: References using these fields don't appear in Dependencies/Dependents sections. Users can't navigate relationships for these attributes.

**Recommendation**: Sync `ATTR_REFERENCE_MAP` with backend `REFERENCE_FIELDS` to ensure all reference fields are recognized.

---

### 3. Escalation Objects Not Shown Relationally

**Location**: `app.js:2488-2547` (loadCenterMembers)

**Problem**: When viewing a contact or contactgroup:
- Shows usage via `contacts`/`contact_groups` attributes on hosts/services
- Does NOT show usage via `hostescalation`/`serviceescalation` objects

**Example**: Contact "oncall" is used by:
```
define host {
    host_name       webserver
    contacts        oncall          ; SHOWN in dependents
}

define hostescalation {
    host_name       webserver
    contacts        oncall          ; NOT SHOWN
    first_notification  3
    last_notification   0
}
```

**Impact**: User sees limited usage of contact, doesn't realize it's heavily referenced in escalation rules. May incorrectly think contact is safe to delete.

**Recommendation**: Include hostescalation/serviceescalation objects in the Dependents section when viewing contacts and contactgroups.

---

### 4. No Dependency Failure Criteria Display

**Location**: N/A (not implemented)

**Problem**: hostdependency and servicedependency objects have critical attributes that define WHEN the dependency takes effect:
- `execution_failure_criteria` - when dependent object skips checks
- `notification_failure_criteria` - when notifications are suppressed
- `dependency_period` - timeperiod when dependency is active

These are never displayed in the relationship view.

**Example**:
```
define servicedependency {
    dependent_service_description   MySQL Slave Status
    service_description             MySQL
    execution_failure_criteria      w,c,u    ; Skip checks if MySQL is warning/critical/unknown
    notification_failure_criteria   c        ; Suppress notifications only if MySQL is critical
}
```

**Impact**: Users see "MySQL Slave Status depends on MySQL" but not WHY or WHEN. The semantic meaning of the dependency is lost.

**Recommendation**: Display failure criteria as part of dependency description, e.g., "MySQL Slave Status → MySQL (skip checks on w,c,u; suppress notifications on c)"

---

### 5. Incomplete Bidirectional Group Membership

**Location**: `app.js:2488-2547`

**Problem**: Group membership display is inconsistent across object types:

| Object Type | Shows Members | Shows "Member Of" |
|-------------|---------------|-------------------|
| hostgroup | ✅ Yes | ✅ Yes (via host's `hostgroups`) |
| contactgroup | ✅ Yes | ❌ No |
| servicegroup | ✅ Yes (partial) | ❌ No |

**Current code for hostgroups** (lines 2501-2516):
```javascript
// Shows both directions - GOOD
const directMembers = obj.attrs.members?.split(',')...
const reverseMembers = state.allObjects.filter(o =>
    o.attrs.hostgroups?.includes(groupName))
```

**Missing for contactgroups**: No reverse lookup for contacts that have this contactgroup in their `contactgroups` attribute.

**Impact**: Inconsistent UX. Users expect bidirectional view for all group types.

**Recommendation**: Implement reverse membership lookup for contactgroups and servicegroups matching hostgroup pattern.

---

### 6. Exclusion Syntax Not Visualized

**Location**: `object-editor.js:2224`

**Problem**: Nagios allows exclusion syntax with `!` prefix. Current code strips these:
```javascript
// Line 2224 - strips exclusion prefix
const refValue = value.replace(/^!/, '');
```

But exclusions are never displayed differently from inclusions.

**Example**:
```
define hostgroup {
    hostgroup_name  all-servers
    members         *,!test-server    ; All servers EXCEPT test-server
}
```

**Impact**: Users can't see that `test-server` is EXCLUDED from `all-servers`. The relationship shows as a normal membership or doesn't show at all.

**Recommendation**:
1. Track exclusion status when parsing references
2. Display excluded references with visual distinction (e.g., strikethrough, red text, "excluded" badge)

---

### 7. Missing Reference Attributes in Trigger Constants

**Location**: `main.js:135-140`

**Problem**: The `referenceAttrs` constant controls which attribute changes trigger UI refresh:
```javascript
referenceAttrs: [
    'use', 'parents', 'hostgroups', 'servicegroups', 'contactgroups',
    'contact_groups', 'host_name', 'hostgroup_name', 'check_command',
    'event_handler', 'check_period', 'notification_period', 'contacts', 'members'
]
```

**Missing attributes**:
- `dependent_host_name`, `dependent_hostgroup_name`
- `dependent_service_description`
- `master_host_name`, `master_hostgroup_name`, `master_service_description`
- `escalation_contacts`, `escalation_contact_groups`
- All global command references

**Impact**: When user edits a missing attribute, the Dependencies/Dependents sections don't refresh. User sees stale relationship data.

**Recommendation**: Add all reference fields to the trigger list.

---

## Summary Table

| Issue | Severity | Effort | Files to Modify |
|-------|----------|--------|-----------------|
| hostdependency/servicedependency ignored | High | Medium | object-editor.js, app.js |
| Incomplete frontend reference fields | Medium | Low | object-editor.js |
| Escalation objects not shown | Medium | Medium | app.js |
| No failure criteria display | Medium | Medium | object-editor.js |
| Incomplete bidirectional membership | Low | Low | app.js |
| Exclusion syntax not visualized | Low | Medium | object-editor.js |
| Missing trigger attributes | Low | Low | main.js |

---

## Code Reference Summary

| File | Lines | Contains |
|------|-------|----------|
| `nagios_model.py` | 50-114 | Backend REFERENCE_FIELDS (complete) |
| `object-editor.js` | 43-93 | Frontend ATTR_REFERENCE_MAP (incomplete) |
| `object-editor.js` | 2151-2486 | loadCenterReferences, renderCenterReferences |
| `app.js` | 1840-2139 | Inheritance section rendering |
| `app.js` | 2488-2547 | Members section rendering |
| `main.js` | 135-140 | Reference attribute trigger list |
| `explorer.html` | 97-118 | Section containers |

---

## Part 2: Unified Impact & Relationships Redesign

### Meta-Review: Current UX Problems

The current implementation spreads object relationship information across **4 separate collapsible sections**:

```
Attributes Section
├─ Inheritance Section       (template chain + parent hosts)
├─ Dependencies Section      (outgoing references + master dependency rules)
├─ Dependents Section        (incoming references + dependent dependency rules)
└─ Members Section           (group members - groups/templates only)
```

#### Problem 1: Confusing Terminology

| Current Term | User Expects | Actually Shows |
|--------------|--------------|----------------|
| **Dependencies** | "Things I need" | Outgoing references (things this object references) |
| **Dependents** | "Things that need me" | Incoming references (things referencing this object) |

The terms are **semantically correct** but **counter-intuitive**. Users must read tooltips to understand which section answers "what breaks if I delete this?"

#### Problem 2: Scattered Concepts

The 4 sections mix **5 distinct relationship types**:

| Relationship Type | Current Section | Semantics |
|-------------------|-----------------|-----------|
| Template inheritance (`use`) | Inheritance | Configuration inheritance |
| Host network hierarchy (`parents`) | Inheritance (subsection) | Network/monitoring topology |
| Reference attributes | Dependencies/Dependents | Static config references |
| Dependency rules | Dependencies/Dependents | Runtime execution/notification control |
| Group membership | Members | Group containment |

Users must mentally combine information from multiple sections to understand full impact.

#### Problem 3: Missing Impact Clarity

When a user needs to rename or delete an object, they must answer:
- "What will break if I delete this?" → Dependents section
- "What does this need to work?" → Dependencies section
- "What's the scope of a rename?" → Must check both + Inheritance

The current UI doesn't directly answer these questions - it presents raw data.

#### Problem 4: Inconsistent Visual Treatment

| Content Type | Visual Treatment |
|--------------|------------------|
| Regular references | Simple list item with type badge |
| Dependency rules | List item with "rule" badge + compact failure criteria |
| Group hierarchies | Nested tree with parent chain |
| Inheritance chain | Linear chain with markers |
| Missing references | Error styling (red) |

Users can't quickly scan and understand what each item represents.

---

### Proposed Design: Unified "Impact & Relationships" Section

Replace all 4 sections with a single, well-organized section that directly answers user questions.

#### Visual Structure

```
┌─────────────────────────────────────────────────────────────────┐
│ IMPACT & RELATIONSHIPS                              [Collapse ▼] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ┌─ CONFIGURATION ANCESTRY ────────────────────────────────────┐ │
│ │                                                              │ │
│ │  Templates:  generic-host → linux-server → [current]        │ │
│ │                                                              │ │
│ │  Network:    datacenter-switch → rack-switch → [current]    │ │
│ │              (parents hierarchy - hosts only)                │ │
│ │                                                              │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─ IF THIS OBJECT IS DELETED OR RENAMED ──────────────────────┐ │
│ │                                                              │ │
│ │  ⚠️ 5 objects reference this and would need updates:        │ │
│ │                                                              │ │
│ │  Services (3)           ─────────────────────────────────    │ │
│ │    • http-check         (host_name → this)                   │ │
│ │    • ssh-check          (host_name → this)                   │ │
│ │    • disk-check         (host_name → this)                   │ │
│ │                                                              │ │
│ │  Dependency Rules (1)   ─────────────────────────────────    │ │
│ │    • servicedependency  (dependent_host_name → this)         │ │
│ │      ↳ Skips checks on: w,c,u | Suppresses notify on: c      │ │
│ │                                                              │ │
│ │  Escalations (1)        ─────────────────────────────────    │ │
│ │    • hostescalation     (host_name → this)                   │ │
│ │                                                              │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─ THIS OBJECT REQUIRES ──────────────────────────────────────┐ │
│ │                                                              │ │
│ │  🔗 4 objects must exist for this to work:                   │ │
│ │                                                              │ │
│ │  Commands (2)           ─────────────────────────────────    │ │
│ │    • check_http         (check_command)                      │ │
│ │    • notify-by-email    (event_handler)                      │ │
│ │                                                              │ │
│ │  Timeperiods (2)        ─────────────────────────────────    │ │
│ │    • 24x7               (check_period)                       │ │
│ │    • workhours          (notification_period)                │ │
│ │                                                              │ │
│ │  Dependency Rules (1)   ─────────────────────────────────    │ │
│ │    • hostdependency     (this is master → web-servers)       │ │
│ │      ↳ Controls: web-servers execution/notifications         │ │
│ │                                                              │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─ GROUP MEMBERSHIP ──────────────────────────────────────────┐ │
│ │                                                              │ │
│ │  Member of:                                                  │ │
│ │    • linux-servers (hostgroup)                               │ │
│ │    • production-hosts (hostgroup)                            │ │
│ │      ↳ parent: all-hosts                                     │ │
│ │                                                              │ │
│ │  (For groups: shows direct members list here)                │ │
│ │                                                              │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Key Design Principles

1. **Question-Oriented Headers**: Instead of abstract terms, use headers that match user intent:
   - "If this object is deleted or renamed" → Answers "what will break?"
   - "This object requires" → Answers "what must exist for this to work?"
   - "Configuration ancestry" → Shows inheritance clearly

2. **Counts First**: Show total count in section header so users can quickly assess impact scope.

3. **Grouped by Type**: Within each section, group items by object type for scanability.

4. **Inline Context**: Show WHY the relationship exists (which attribute creates it).

5. **Dependency Rules Explained**: Show failure criteria in human-readable form, not compact codes.

6. **Visual Hierarchy**: Use indentation and subtle separators to distinguish relationship categories.

---

### Detailed Section Specifications

#### Section 1: Configuration Ancestry

**Purpose**: Show where this object inherits configuration from.

**Contents**:
- **Templates**: Linear chain from root template to current object (via `use` attribute)
- **Network Hierarchy**: Parent hosts chain (via `parents` attribute, hosts only)

**Rendering**:
```
Templates:  generic-host → linux-server → [current]
            ↑ clickable    ↑ clickable    ↑ styled differently

Network:    dc-switch → rack-switch → [current]
            (Only shown for hosts with parents attribute)
```

**Click behavior**: Clicking ancestor navigates to that object.

**Error states**:
- Missing template: Show with ⚠️ "missing" badge
- Circular inheritance: Show with 🔄 "circular" badge

---

#### Section 2: "If This Object Is Deleted or Renamed"

**Purpose**: Show all objects that reference this one (impact of deletion/rename).

**Subsections** (grouped by object type):
- **Services**: Services with `host_name` pointing here
- **Hosts**: Hosts with `parents` pointing here (network children)
- **Dependency Rules**: `hostdependency`/`servicedependency` where this is master or dependent_*
- **Escalations**: `hostescalation`/`serviceescalation` referencing this
- **Groups**: Groups with this object in `members`
- **Templates**: Objects using this as template (via `use`)
- **Contacts/Contactgroups**: If this is a timeperiod, command, etc.

**For each item, show**:
```
• object-name        (attribute-name → this)
  ↳ [additional context if dependency rule]
```

**Dependency rule context**:
```
• servicedependency  (dependent_host_name → this)
  ↳ Skips checks on: warning, critical, unknown
  ↳ Suppresses notifications on: critical
  ↳ Active during: workhours (timeperiod)
```

**Summary line at top**:
```
⚠️ 5 objects reference this and would need updates:
```

---

#### Section 3: "This Object Requires"

**Purpose**: Show all objects this one depends on (what must exist for this to work).

**Subsections** (grouped by reference type):
- **Commands**: `check_command`, `event_handler`, `obsess_over_*_command`
- **Timeperiods**: `check_period`, `notification_period`, `dependency_period`
- **Contacts/Contactgroups**: `contacts`, `contact_groups`
- **Hosts/Hostgroups**: `host_name`, `hostgroup_name`
- **Services/Servicegroups**: `service_description`, `servicegroup_name`
- **Templates**: `use` attribute targets
- **Dependency Rules**: Where this object is master (controls others)

**For each item, show**:
```
• object-name        (attribute-name)
```

**For dependency rules where this is master**:
```
• hostdependency     (this is master → web-servers)
  ↳ Controls: web-servers check execution when this fails
```

**Summary line at top**:
```
🔗 4 objects must exist for this to work:
```

---

#### Section 4: Group Membership

**Purpose**: Show group relationships bidirectionally.

**For regular objects (hosts, services, contacts)**:
```
Member of:
  • linux-servers (hostgroup)
  • production-hosts (hostgroup)
    ↳ parent: all-hosts (shows group hierarchy)
```

**For groups (hostgroup, servicegroup, contactgroup)**:
```
Direct members (5):
  • host1, host2, host3, host4, host5

Implicit members (via reverse reference) (12):
  • webserver01 (has hostgroups: this)
  • webserver02 (has hostgroups: this)
  [Show more...]
```

**For templates**:
```
Used by (3):
  • webserver01 (host)
  • webserver02 (host)
  • dbserver01 (host)
```

---

### Implementation Approach

#### Phase 1: Consolidate Sections (HTML/CSS)

1. **Modify `explorer.html`** (lines 97-124):
   - Remove 4 separate section containers
   - Add single "Impact & Relationships" container with subsection divs

2. **Update `explorer.css`**:
   - Add styles for new subsection layout
   - Preserve existing item rendering styles (badges, tree connectors)
   - Add summary line styles

#### Phase 2: Unify Data Loading (JavaScript)

1. **Create `loadImpactAndRelationships()` in `app.js`**:
   - Combine logic from `loadCenterInheritance()`, `loadCenterReferences()`, `loadCenterMembers()`
   - Organize results by section (ancestry, incoming refs, outgoing refs, membership)

2. **Update rendering functions**:
   - `renderConfigurationAncestry()` - templates + network parents
   - `renderIncomingReferences()` - "what breaks if deleted"
   - `renderOutgoingReferences()` - "what this requires"
   - `renderGroupMembership()` - bidirectional membership

#### Phase 3: Enhanced Dependency Rule Display

1. **Expand `formatFailureCriteria()` in `app.js`**:
   - Return structured object instead of compact string
   - Include human-readable descriptions

2. **Add dependency rule context rendering**:
   - Show which objects are controlled
   - Explain execution vs notification criteria
   - Show dependency_period if present

#### Phase 4: Improve Discoverability

1. **Add expandable summaries**:
   - Default: Show count + first 3 items
   - Click to expand full list

2. **Add quick actions**:
   - "Select all referencing objects" for bulk rename
   - "Show in tree" to highlight in left pane

---

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      Object Selected                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 loadImpactAndRelationships()                     │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ getAncestry()   │  │ getIncoming()   │  │ getOutgoing()   │ │
│  │                 │  │                 │  │                 │ │
│  │ - Templates     │  │ - All objects   │  │ - Scan attrs    │ │
│  │ - Parent hosts  │  │   referencing   │  │   for refs      │ │
│  │                 │  │   this one      │  │ - Dependency    │ │
│  │ API:            │  │ - Dependency    │  │   rules (master)│ │
│  │ /inheritance/   │  │   rules (this   │  │                 │ │
│  │ {type}/{name}   │  │   is target)    │  │ Source:         │ │
│  │                 │  │                 │  │ REFERENCE_FIELDS│ │
│  │                 │  │ Source:         │  │                 │ │
│  │                 │  │ allObjects scan │  │                 │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                    │                    │           │
│           ▼                    ▼                    ▼           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              getGroupMembership()                            ││
│  │                                                              ││
│  │  - Groups this object belongs to (hostgroups, etc.)          ││
│  │  - For groups: direct members + reverse members              ││
│  │  - Group parent hierarchy                                    ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Render Unified Section                        │
│                                                                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐│
│  │  Ancestry   │ │  Incoming   │ │  Outgoing   │ │ Membership ││
│  │  Section    │ │  Section    │ │  Section    │ │ Section    ││
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

### Human-Readable Failure Criteria

Replace compact codes with clear descriptions:

| Code | Meaning | Display As |
|------|---------|------------|
| `o` | UP (hosts) / OK (services) | "up" / "ok" |
| `d` | DOWN | "down" |
| `u` | UNREACHABLE (hosts) / UNKNOWN (services) | "unreachable" / "unknown" |
| `w` | WARNING | "warning" |
| `c` | CRITICAL | "critical" |
| `p` | PENDING | "pending" |
| `n` | NONE | "(no criteria)" |

**Example transformation**:
```
Current:   (skip: w,c,u; notify: c)

Proposed:  Execution: Skip checks when master is warning, critical, or unknown
           Notifications: Suppress when master is critical
```

---

### CSS Token Additions for New Section

```css
/* Impact & Relationships section */
--nbe-impact-header-bg: var(--nbe-bg-subtle);
--nbe-impact-subsection-border: var(--nbe-border-color);
--nbe-impact-warning-color: var(--nbe-warning);
--nbe-impact-link-color: var(--nbe-primary);

/* Summary badges */
--nbe-badge-incoming: #dc3545;   /* Red - these things reference you */
--nbe-badge-outgoing: #0d6efd;   /* Blue - you reference these things */
--nbe-badge-ancestry: #6f42c1;   /* Purple - inheritance */
--nbe-badge-membership: #198754; /* Green - groups */
```

---

### Migration Notes

1. **Preserve existing function names** as internal helpers (don't break callers)
2. **Keep tooltip content** but move to section headers
3. **Maintain staging awareness** via `getEffectiveAttrs()` - no changes needed
4. **Test with dependency objects** - hostdependency/servicedependency scenarios

---

### Success Metrics

After implementation, users should be able to:

1. **In < 3 seconds**: Determine if renaming/deleting an object is safe
2. **Without reading tooltips**: Understand what each section shows
3. **In one glance**: See total count of impacted objects
4. **With one click**: Navigate to any related object
5. **Without confusion**: Distinguish between different relationship types
