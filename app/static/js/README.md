# Dependency Graph — Design Decisions

See `CLAUDE.md` in this directory for the module index.

## Who owns what

- **Backend** (`app/dependency_graph.py`, `GET /api/dependencies`): one node per
  object and per undefined reference, one edge per reference. Service references
  (`*service_description`, service `parents`, servicegroup `members`) are
  resolved to the service object that applies to that host, directly or through
  a hostgroup, so the same service isn't drawn twice. Each edge carries its
  field (`label`) and `category`.
- **Domain metadata** (`app/nagios_model.py`: `GRAPH_NODE_TYPES`,
  `GRAPH_EDGE_CATEGORIES`, `GRAPH_EDGE_FIELDS`, served in `/api/metadata` as
  `graph`): type colours and badges, edge labels, colours and categories, the
  type and category filter checkboxes. Nothing of this is repeated in JS.
- **`dependencies-config.js`**: presentation only: layout constants, quick view
  presets (with the object types each collects), expansion rules, node icons.
- **`graph/model.js`** (pure, tested): index, expansion, display filtering, search.
- **`graph/layout.js`** (pure, tested): dagre ranking, clustered layout, edge bundling.
- **`dependencies.js`**: page state, the single Cytoscape instance, DOM.

## Edge direction

An edge goes from the object that has a field to the object it names: `use`
from an object to its template, `host_name` from a service (or dependency,
escalation) to its host, `members` from a group to its member. `parents` is
reversed (parent host → child). Expansion code must follow these directions;
following one backwards silently drops objects (GRAPH_REVIEW 1).

## Edge categories

Six categories (dependencies, templates, groups, contacts, commands, schedules)
let users filter by concept rather than by raw field. `members` is `groups`,
except on a contactgroup, where it is `contacts` (`category_by_type`).

A quick view does not filter by category: it shows exactly the fields its
expansion rules follow (`ruleFields`), and the category boxes only reflect
them. Changing a box switches to category filtering.

## Two expansion strategies

**Effective configuration** (`expandEffective` in `graph/model.js`): Full Graph
and "Expand connections". What Nagios applies to the object: templates,
settings, services (direct and via hostgroups), groups, the rules that name it.
Directional: it never adds a host's siblings.

**Rule-based** (`expandWithRules`): every other quick view. Declarative
`expansionRules[type][preset]` in `dependencies-config.js`:

- `forward` / `backward`: fields followed along / against the edge direction
- `atType`: extra fields at nodes of that type (unioned with the base rules)
- `stopAt`: types not entered (the focus node is exempt)
- `monotonic`: a path never turns around (inheritance: an ancestor's other
  children are not pulled in)
- `backwardFromTemplateOnly`: backward fields only when the focus is a template

The preset's `types` also limit what is collected. A preset is offered for a
type exactly when a rule exists (`presetsForType`); Full Graph for every type.

## Layouts

- **Hierarchical TB/LR**: dagre over the directed edges, with fields that name a
  template ranked the other way so templates sit above their users.
- **Clustered** (`static`): with a focus node, fixed type clusters around it,
  contacts/services/commands/time periods orbiting the contact groups, edges
  bundled toward their target's cluster (`clusterPositions`, `bundleEdges`).
  Without a focus node, cose. Users preferred this to a force layout seeded by
  type sectors, which was tried and reverted.

The Cytoscape instance is created once. Updates add/remove only the changed
elements; the layout reruns only when the layout or focus changes or a node
without a remembered position appears. Labels toggle through the stylesheet.

## Invariants (tested)

1. Every field in `GRAPH_EDGE_FIELDS` has a label, colour and known category
   (`tests/test_dependency_graph.py`).
2. Every quick view offered for a type has a rule or uses smart expansion
   (`tests/js/graph-model.test.mjs`).

## Adding a new relationship field

1. `app/nagios_model.py`: add it to `GRAPH_EDGE_FIELDS` (target type, category,
   label, colour). The backend draws it and the frontend labels, colours and
   filters it from metadata.
2. If quick views should follow it, add it to the relevant `expansionRules`.
