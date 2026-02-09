# Dependency Graph — Design Decisions

See `CLAUDE.md` in this directory for the module index.

## Edge Category System

Three-layer abstraction: backend relationship fields → 6 edge categories → 10 quick view presets. Enables users to filter by semantic concepts ("notification routing") rather than raw Nagios fields ("contacts, contact_groups, contactgroup_members").

**Categories** (defined in `dependencies-config.js`):
1. **dependencies** — Network topology (parents, host_name, dependency targets)
2. **templates** — Inheritance chain (use)
3. **groups** — Organizational grouping (bidirectional member/group)
4. **contacts** — Notification routing including escalations
5. **commands** — Check/event/notification commands
6. **schedules** — Time periods

Escalation contacts are in `contacts` (not a separate category) because regular and escalation contacts are both "notification routing". The separate "escalations" preset handles the "show escalation policies" use case.

## Two Expansion Strategies

**Semantic expansion** (`addAllConnectedRecursively` in `dependencies.js`): Used by "full graph" preset only. 900+ lines of context-aware logic for complex multi-hop traversal.

**Rule-based expansion** (`expandWithRules` in `dependencies.js`): All other presets. Declarative `expansionRules` table in `dependencies-config.js` defines which edges to follow per (objectType, preset).

Rule structure:
- `forward`: Outgoing edges to follow from a node
- `backward`: Incoming edges to follow to a node
- `atType`: Type-specific rules at intermediate nodes (unioned with base rules)
- `stopAt`: Node types to traverse through but exclude from final graph

If no rule exists for a (nodeType, preset) combination, nothing expands. This forces explicit rule definition.

## Invariants

1. Every edge label must appear in exactly one `edgeCategories` group
2. Every `edgeCategories` entry must have a label in `edgeLabelMap`
3. `presetsByType` must only reference existing presets
4. Quick view preset `typesByPreset` must only reference valid object types

## Adding a New Relationship Field

1. Backend (`routes/analysis.py`): Add to `relationship_fields` dict
2. `dependencies-config.js`: Add to appropriate `edgeCategories` array
3. `dependencies-config.js`: Add label to `edgeLabelMap`, color to `edgeColors`
4. Check if existing presets should include it via its category
