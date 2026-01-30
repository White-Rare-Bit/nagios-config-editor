# Dependency Graph Edge Category System

## Overview

The dependency graph (`dependencies.js`) implements a three-layer abstraction for visualizing Nagios object relationships: backend relationship fields → edge categories → quick view presets. This architecture enables users to filter complex graphs using semantic concepts ("show notification routing") rather than raw Nagios field names ("show contacts, contact_groups, contactgroup_members").

## Architecture

```
User Request (type filter, node selection)
           |
           v
    +-------------+
    | /api/deps   |  relationship_fields dict defines which attrs create edges
    +-------------+
           |
           v
    +-------------+
    | Graph Data  |  nodes + edges with field names as edge labels
    +-------------+
           |
           v
    +----------------+     +------------------+
    | Edge Categories|---->| Quick View       |
    | (7 groups)     |     | Presets (10)     |
    +----------------+     +------------------+
           |                        |
           v                        v
    +----------------+     +------------------+
    | Type Filters   |     | Layout Selection |
    | (12 types)     |     | (hierarchical/   |
    +----------------+     |  force-directed) |
                           +------------------+
```

## Data Flow

```
Backend relationship_fields → edges with 'label' = field name
                                      ↓
Frontend edgeCategories → maps field names to semantic groups
                                      ↓
Quick view presets → select categories + layout + type filters
                                      ↓
User sees filtered, laid-out subgraph
```

## Why This Structure

Edge categories exist as an abstraction layer between raw Nagios field names and user mental models:

- **Mental model alignment**: Users think "show me notification routing" not "show contacts, contact_groups, contactgroup_members"
- **Declarative presets**: Categories enable quick view presets to be defined declaratively without listing every field
- **Extension without breaking changes**: New fields can be added to existing categories without changing preset definitions

## Edge Categories

The system defines 7 semantic edge categories:

1. **dependencies**: Network topology and monitoring logic (parents, host_name, dependency targets)
2. **templates**: Inheritance chain (use directive)
3. **groups**: Organizational grouping (bidirectional member/group relationships)
4. **contacts**: Notification routing (contacts, contact_groups)
5. **commands**: Implementation details (check_command, event_handler, notification commands, obsession commands)
6. **schedules**: Time periods (check_period, notification_period, escalation_period, dependency_period)
7. **escalation**: Escalation-specific contact routing (escalation_contacts, escalation_contact_groups)

### Why Escalation Is Separate

Escalation contacts route notifications through multi-tier escalation chains, distinct from direct notification contacts. This separation enables:

- The "escalations" preset to filter only escalation edges (hostescalation/serviceescalation → Contact/ContactGroup), excluding regular notification routing
- Users to understand escalation chains independently from normal notification flow
- Clearer graph visualization when analyzing escalation policies

**Tradeoff**: More categories increase cognitive load, but escalation routing is conceptually distinct enough to warrant dedicated filtering.

## Invariants

These rules MUST be maintained when modifying the graph system:

1. **Category completeness**: Every edge `label` value must have an entry in exactly one `edgeCategories` group
2. **Label mapping**: Every `edgeCategories` entry must have a human-readable label in `edgeLabelMap`
3. **Preset validity**: `presetsByType` must only reference presets that exist in `quickViewPresets`
4. **Type validity**: `typesByPreset` values must only reference types in `allObjectTypes`

Violating these invariants will cause:
- Missing edges in graph (Invariant 1)
- Raw field names displayed instead of labels (Invariant 2)
- Console errors when clicking preset buttons (Invariant 3)
- Type filters showing wrong objects (Invariant 4)

## Adding New Nagios Relationship Types

To add support for a new Nagios reference field:

1. **Backend** (`routes/analysis.py`): Add field to `relationship_fields` dict mapping field name to target object type
2. **Frontend category** (`dependencies.js`): Add field name to appropriate `edgeCategories` array
3. **Edge label** (`dependencies.js`): Add human-readable label to `edgeLabelMap` object
4. **Edge color** (`dependencies.js`): Add color to `edgeColors` object (match category's semantic color)
5. **Verify presets**: Check if any quick view presets should include the new field (via its category)

Example (adding `escalation_contacts`):

```javascript
// Backend: routes/analysis.py
relationship_fields = {
    'escalation_contacts': 'contact',  // New field
    // ...
}

// Frontend: dependencies.js
edgeCategories = {
    escalation: [
        'escalation_contacts',  // New field added to escalation category
        // ...
    ]
}

edgeLabelMap = {
    'escalation_contacts': 'escalates to',  // Human-readable label
    // ...
}

edgeColors = {
    'escalation_contacts': '#00BCD4',  // Cyan - matches escalation color
    // ...
}
```

No preset changes needed if the field's category is already used by relevant presets.

## Tradeoffs

- **More categories = finer filtering but more cognitive load**: 7 categories chosen as balance between filtering granularity and complexity
- **Bidirectional group edges**: Group membership edges include both object→group and group→member directions, increasing edge count but enabling both "what groups contain this?" and "what's in this group?" queries without manual expansion
- **No reverse edges for most relationships**: Only groups have bidirectional edges; other relationships are forward-only (e.g., service→host but not host→services) to reduce visual clutter

## Quick View Expansion Rules

The quick view system uses two distinct expansion strategies depending on the preset:

1. **Semantic expansion** (`useSmartExpansion: true`): Full graph preset uses 900+ lines of context-aware logic in `addAllConnectedRecursively()` to understand Nagios object relationships
2. **Rule-based expansion** (all other presets): Declarative `expansionRules` table defines which edges to follow for each (objectType, preset) combination

### Expansion Rules Architecture

```
Quick View Click
      |
      v
+------------------+
| applyQuickView() |
+------------------+
      |
      v
+------------------------+     Yes    +---------------------------+
| useSmartExpansion?     |----------->| addAllConnectedRecursively|
+------------------------+            +---------------------------+
      | No
      v
+------------------------+
| expansionRules lookup  |
| [nodeType][preset]     |
+------------------------+
      |
      v
+------------------------+
| expandWithRules()      |
| (BFS traversal)        |
+------------------------+
```

### Rule Structure

Each rule defines how to traverse the graph from a starting node:

```javascript
expansionRules = {
    host: {
        services: {
            forward: ['hostgroups'],           // Edges to follow FROM this node
            backward: ['host_name'],           // Edges to follow TO this node
            atType: {                          // Type-specific rules at intermediate nodes
                hostgroup: {
                    backward: ['hostgroup_name']
                }
            },
            stopAt: ['host']                   // Node types to exclude from graph
        }
    }
}
```

### Rule Components

#### forward
Outgoing edges to follow when visiting a node (edge.from === nodeId). Used when you want to expand "downstream" to targets of a relationship.

Example: `forward: ['check_command']` follows edges from services to their check commands.

#### backward
Incoming edges to follow when visiting a node (edge.to === nodeId). Used when you want to find "upstream" objects that reference this node.

Example: `backward: ['host_name']` finds services that point to this host.

#### atType
Type-specific rules applied when BFS reaches an intermediate node of a given type. Enables different behavior at different node types during traversal.

Example: When expanding from a host, reaching a hostgroup triggers `atType.hostgroup` rules to find services targeting that group.

**Merging behavior**: atType rules are unioned with base forward/backward rules (not overridden) to preserve both base and type-specific edge traversal.

#### stopAt
Node types to exclude from the final graph. These nodes are visited during BFS (to traverse through them) but not added to `addedNodeIds`.

Example: `stopAt: ['host']` in hostgroup services view prevents sibling host expansion while still finding services linked to those hosts.

**Dual tracking**: stopAt nodes are added to BFS `visited` set (prevents cycles) but excluded from `addedNodeIds` (controls graph membership).

### Data Flow Example

**User clicks "Services" on host:web-prod-01**

```
Starting Node: host:web-prod-01
     |
     v
Rule Lookup: expansionRules.host.services
     |
     +-- forward: ['hostgroups']          → Find hostgroups this host belongs to
     +-- backward: ['host_name']          → Find services targeting this host
     +-- atType.hostgroup.backward: ['hostgroup_name']  → At hostgroups, find services
     +-- stopAt: ['host']                 → Don't add sibling hosts to graph
     |
     v
BFS Traversal:
  1. Add host:web-prod-01
  2. Follow backward host_name → find service:http-check → add to graph
  3. Follow forward hostgroups → find hostgroup:production
  4. At hostgroup:production, apply atType rules
  5. Follow backward hostgroup_name → find service:disk-check → add to graph
  6. Find host:web-prod-02 via hostgroup membership
  7. host:web-prod-02 in stopAt → mark visited but don't add to graph
     |
     v
Final Graph: host:web-prod-01, service:http-check, hostgroup:production, service:disk-check
```

### Adding Rules for New Presets

To add a new quick view preset:

1. **Define the preset** in `quickViewPresets`:
   ```javascript
   quickViewPresets = {
       myNewPreset: {
           label: "My View",
           description: "Shows custom relationships",
           layout: 'hierarchical'
       }
   }
   ```

2. **Add rules for relevant types** in `expansionRules`:
   ```javascript
   expansionRules = {
       host: {
           myNewPreset: {
               forward: ['parents'],
               backward: [],
               stopAt: []
           }
       },
       service: {
           myNewPreset: {
               forward: ['check_command'],
               backward: ['host_name'],
               stopAt: []
           }
       }
   }
   ```

3. **Register types** in `presetsByType`:
   ```javascript
   presetsByType = {
       host: ['full', 'services', 'myNewPreset'],
       service: ['full', 'myNewPreset']
   }
   ```

### Undefined Rule Behavior

If no rule exists for a (nodeType, preset) combination, `expandWithRules()` returns early without expansion. This "show nothing" behavior forces explicit rule definition and prevents unpredictable graph expansion.

**Why this design**: User-confirmed preference to avoid surprising behavior. Explicit rules make preset behavior predictable and testable.

### Rule Design Guidelines

**Keep rules focused**: Each preset should answer a single user question ("What services use this host?" not "Show everything related to monitoring").

**Use stopAt for sibling prevention**: When expanding through intermediate nodes, use stopAt to prevent pulling in unwanted siblings (e.g., services view shouldn't expand to all hosts in a hostgroup).

**Leverage atType for multi-hop patterns**: When traversal logic changes at intermediate nodes, use atType rules rather than expanding the base rule (preserves single responsibility per rule section).

**Test with realistic graphs**: Expansion rules can have unexpected interactions with complex object graphs. Always test with multi-level scenarios (host → hostgroup → services → commands).

### Why Two Expansion Strategies

The full graph preset uses semantic expansion (`addAllConnectedRecursively`) because it requires context-aware decision making (e.g., "follow templates up but dependencies down", "expand contactgroups but not service groups"). This logic spans 900+ lines and would be difficult to express declaratively.

Other presets have simpler, predictable traversal patterns that fit the declarative rule model. Rules provide:
- **Testability**: Each type+preset combination has explicit expected behavior
- **Maintainability**: Adding fields to edge categories automatically updates relevant presets
- **Clarity**: Rules document intended behavior in structured data rather than scattered conditionals

**Tradeoff**: Two expansion systems increase complexity, but migration of full preset to rules would risk regression without clear benefit.
