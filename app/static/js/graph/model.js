/**
 * Graph View model: indexing, expansion, filtering and search over the
 * GET /api/dependencies data. No DOM and no module state, so it runs under
 * node:test (tests/js/graph-model.test.mjs).
 *
 * Edge direction (see app/dependency_graph.py): an edge goes from the object
 * that has a field to the object the field names. `use` points from an object
 * to its template, `host_name` from a service (or dependency, escalation) to
 * its host, `members` from a group to a member. `parents` is the exception: it
 * points from the parent host to the child.
 */

/**
 * Index nodes by id and edges by endpoint, once after loading.
 * @param {Array} nodes - API nodes
 * @param {Array} edges - API edges
 */
export function buildGraphIndex(nodes, edges) {
    const byId = new Map();
    const out = new Map();
    const incoming = new Map();
    for (const node of nodes) {
        byId.set(node.id, node);
        out.set(node.id, []);
        incoming.set(node.id, []);
    }
    for (const edge of edges) {
        if (!byId.has(edge.from) || !byId.has(edge.to)) {continue;}
        out.get(edge.from).push(edge);
        incoming.get(edge.to).push(edge);
    }
    return { nodes, edges, byId, out, in: incoming };
}

/** Edges leaving `id`, optionally only those with field `label`. */
export function edgesFrom(index, id, label = null) {
    const list = index.out.get(id) || [];
    return label === null ? list : list.filter(e => e.label === label);
}

/** Edges arriving at `id`, optionally only those with field `label`. */
export function edgesTo(index, id, label = null) {
    const list = index.in.get(id) || [];
    return label === null ? list : list.filter(e => e.label === label);
}

/** Stable Cytoscape id for an edge. */
export function edgeId(edge) {
    return `e|${edge.from}|${edge.label}|${edge.to}`;
}

// ---------------------------------------------------------------------------
// Full Graph: the effective configuration of one object
// ---------------------------------------------------------------------------

// Fields that say how an object is checked and who is notified.
const OBJECT_SETTINGS_FIELDS = ['check_command', 'event_handler', 'check_period', 'notification_period',
    'contacts', 'contact_groups'];
const CONTACT_SETTINGS_FIELDS = ['host_notification_commands', 'service_notification_commands',
    'host_notification_period', 'service_notification_period', 'contactgroups'];
const COMMAND_USER_FIELDS = ['check_command', 'event_handler', 'host_notification_commands',
    'service_notification_commands', 'notification_commands'];
const TIMEPERIOD_USER_FIELDS = ['check_period', 'notification_period', 'host_notification_period',
    'service_notification_period', 'escalation_period', 'dependency_period', 'exclude'];
const RULE_TYPES = new Set(['hostdependency', 'servicedependency', 'hostescalation', 'serviceescalation']);

/**
 * Add what Nagios applies to `startId` to `result`: its templates, the
 * services on a host, commands, contacts, time periods, groups, and the
 * dependency/escalation rules that name it. Directional: for a host it does
 * not add other hosts that share its template or command.
 *
 * @param {object} index - buildGraphIndex() result
 * @param {string} startId - Node to expand
 * @param {Set} result - Node ids; added to in place
 */
export function expandEffective(index, startId, result) {
    const start = index.byId.get(startId);
    if (!start) {return;}
    result.add(startId);
    const visited = new Set([startId]);

    const typeOf = id => index.byId.get(id)?.type;
    const collect = (id) => {
        if (visited.has(id) || !index.byId.has(id)) {return false;}
        visited.add(id);
        result.add(id);
        return true;
    };
    const followOut = (id, label, onAdd) => {
        for (const e of edgesFrom(index, id, label)) {
            if (collect(e.to) && onAdd) {onAdd(e.to);}
        }
    };
    const followIn = (id, label, fromType, onAdd) => {
        for (const e of edgesTo(index, id, label)) {
            if (fromType && typeOf(e.from) !== fromType) {continue;}
            if (collect(e.from) && onAdd) {onAdd(e.from);}
        }
    };

    // Templates: `use` points from an object to its template.
    const addTemplates = (id) => followOut(id, 'use', addTemplates);
    // Contact groups bring their members.
    const addGroupMembers = (id) => {
        if (typeOf(id) === 'contactgroup') {followOut(id, 'members');}
    };
    const addSettings = (id) => {
        for (const label of OBJECT_SETTINGS_FIELDS) {followOut(id, label, addGroupMembers);}
    };
    const addService = (id) => { addTemplates(id); addSettings(id); };

    const handlers = {
        host() {
            addTemplates(startId);
            addSettings(startId);
            // Hostgroups: from the host's `hostgroups`, or the group's `members`.
            const hostgroups = new Set();
            for (const e of edgesFrom(index, startId, 'hostgroups')) {hostgroups.add(e.to);}
            for (const e of edgesTo(index, startId, 'members')) {
                if (typeOf(e.from) === 'hostgroup') {hostgroups.add(e.from);}
            }
            for (const hg of hostgroups) {collect(hg);}
            // Services: `host_name` points from the service to this host;
            // `hostgroup_name` from the service to one of its hostgroups.
            followIn(startId, 'host_name', 'service', addService);
            for (const hg of hostgroups) {followIn(hg, 'hostgroup_name', 'service', addService);}
            // Parent and child hosts (`parents` points from parent to child).
            followIn(startId, 'parents', 'host');
            followOut(startId, 'parents');
            // Dependency and escalation rules that name this host.
            followIn(startId, 'host_name', 'hostdependency');
            followIn(startId, 'dependent_host_name', 'hostdependency');
            followIn(startId, 'host_name', 'hostescalation');
        },
        service() {
            addTemplates(startId);
            addSettings(startId);
            followOut(startId, 'host_name');       // its hosts
            followOut(startId, 'hostgroup_name');  // its hostgroups
            followOut(startId, 'servicegroups');
            followIn(startId, 'members', 'servicegroup');
            followIn(startId, 'service_description', 'servicedependency');
            followIn(startId, 'dependent_service_description', 'servicedependency');
            followIn(startId, 'service_description', 'serviceescalation');
        },
        hostgroup() {
            addTemplates(startId);
            followOut(startId, 'members');
            followOut(startId, 'hostgroup_members');
            followIn(startId, 'hostgroups', 'host');
            followIn(startId, 'hostgroup_name', 'service', addService);
        },
        servicegroup() {
            addTemplates(startId);
            followOut(startId, 'members');
            followOut(startId, 'servicegroup_members');
            followIn(startId, 'servicegroups', 'service');
        },
        contact() {
            addTemplates(startId);
            for (const label of CONTACT_SETTINGS_FIELDS) {followOut(startId, label);}
            followIn(startId, 'members', 'contactgroup');
        },
        contactgroup() {
            addTemplates(startId);
            followOut(startId, 'members');
            followOut(startId, 'contactgroup_members');
        },
        command() {
            for (const label of COMMAND_USER_FIELDS) {followIn(startId, label);}
        },
        timeperiod() {
            addTemplates(startId);
            for (const label of TIMEPERIOD_USER_FIELDS) {followIn(startId, label);}
            followOut(startId, 'exclude');
        }
    };

    const handler = handlers[start.type];
    if (handler) {
        handler();
    } else if (RULE_TYPES.has(start.type)) {
        // A dependency or escalation: everything it names, contact groups with members.
        addTemplates(startId);
        for (const e of edgesFrom(index, startId)) {
            if (e.label !== 'use' && collect(e.to)) {addGroupMembers(e.to);}
        }
    } else {
        addTemplates(startId);
        addSettings(startId);
    }
}

// ---------------------------------------------------------------------------
// Quick views: declarative expansion rules (dependencies-config.js)
// ---------------------------------------------------------------------------

/** Forward/backward fields at a node of `type`: base rules plus atType rules (union). */
export function resolveApplicableRules(rules, type) {
    let forward = rules.forward || [];
    let backward = rules.backward || [];
    const typeRules = rules.atType?.[type];
    if (typeRules) {
        forward = [...new Set([...forward, ...(typeRules.forward || [])])];
        backward = [...new Set([...backward, ...(typeRules.backward || [])])];
    }
    return { forward, backward };
}

/** Every field a rule can follow; a quick view shows exactly these edges. */
export function ruleFields(rules) {
    const fields = new Set([...(rules.forward || []), ...(rules.backward || [])]);
    for (const typeRules of Object.values(rules.atType || {})) {
        for (const f of [...(typeRules.forward || []), ...(typeRules.backward || [])]) {fields.add(f);}
    }
    return fields;
}

/**
 * Breadth-first expansion from `startId` following `rules`.
 *
 * @param {object} index - buildGraphIndex() result
 * @param {string} startId - Focus node (always added, exempt from stopAt and allowedTypes)
 * @param {object} rules - One expansionRules[type][preset] entry
 * @param {Set} result - Node ids; added to in place
 * @param {object} [options]
 * @param {Set|null} [options.allowedTypes] - Types that may be added and traversed (null = any)
 */
export function expandWithRules(index, startId, rules, result, { allowedTypes = null } = {}) {
    const start = index.byId.get(startId);
    if (!start || !rules) {return;}
    const allowBackwardAtRoot = !rules.backwardFromTemplateOnly || start.is_template === true;

    // A node outside allowedTypes or in stopAt is neither added nor expanded.
    const enters = node => node.id === startId
        || (!rules.stopAt?.includes(node.type) && (!allowedTypes || allowedTypes.has(node.type)));

    const visited = new Set([startId]);
    const queue = [{ id: startId, dir: null }];
    const enqueue = (id, dir) => {
        if (visited.has(id)) {return;}
        visited.add(id);
        queue.push({ id, dir });
    };
    for (let head = 0; head < queue.length; head++) {
        const { id, dir } = queue[head];
        const node = index.byId.get(id);
        if (!enters(node)) {continue;}
        result.add(id);

        const { forward, backward } = resolveApplicableRules(rules, node.type);
        if (!(rules.monotonic && dir === 'backward')) {
            for (const e of edgesFrom(index, id)) {
                if (forward.includes(e.label)) {enqueue(e.to, 'forward');}
            }
        }
        if (allowBackwardAtRoot && !(rules.monotonic && dir === 'forward')) {
            for (const e of edgesTo(index, id)) {
                if (backward.includes(e.label)) {enqueue(e.from, 'backward');}
            }
        }
    }
}

/**
 * Quick view presets offered for a focus node of `type`, in `presetOrder`:
 * those with an expansion rule for the type, plus the smart-expansion ones.
 */
export function presetsForType(expansionRules, presets, type) {
    const rules = expansionRules[type] || {};
    return Object.keys(presets).filter(p => presets[p].smartExpansion || p in rules);
}

// ---------------------------------------------------------------------------
// What the canvas shows
// ---------------------------------------------------------------------------

/**
 * Edge filter: a quick view shows the fields its rules follow (`fields`);
 * otherwise edges are shown by category (`categories`).
 * @param {{fields: Set|null, categories: Set}} filter
 */
export function isEdgeVisible(edge, filter) {
    if (filter.fields) {return filter.fields.has(edge.label);}
    return filter.categories.has(edge.category);
}

/**
 * Split the added nodes into what the canvas draws and what it hides.
 *
 * A node is drawn when its type is enabled and it has a visible edge to
 * another drawn node, or it is pinned (the focus, a node the user added by
 * hand, a selected node) or it is the only node.
 *
 * @returns {{nodes: Array, edges: Array, hidden: Map<string, string>}} hidden: id -> reason
 */
export function computeDisplay(index, { addedIds, enabledTypes, edgeFilter, pinnedIds = new Set() }) {
    const hidden = new Map();
    const typeOk = new Set();
    for (const id of addedIds) {
        const node = index.byId.get(id);
        if (!node) {continue;}
        if (enabledTypes.has(node.type)) {
            typeOk.add(id);
        } else {
            hidden.set(id, `${node.type} objects are filtered out`);
        }
    }

    const edges = [];
    const connected = new Set();
    for (const id of typeOk) {
        for (const e of edgesFrom(index, id)) {
            if (typeOk.has(e.to) && isEdgeVisible(e, edgeFilter)) {
                edges.push(e);
                connected.add(e.from);
                connected.add(e.to);
            }
        }
    }

    const nodes = [];
    for (const id of typeOk) {
        if (connected.has(id) || pinnedIds.has(id) || typeOk.size === 1) {
            nodes.push(index.byId.get(id));
        } else {
            hidden.set(id, 'no connection shown by the current filters');
        }
    }
    return { nodes, edges, hidden };
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

function matchRank(text, query) {
    if (!text) {return Infinity;}
    const t = text.toLowerCase();
    if (t === query) {return 0;}
    if (t.startsWith(query)) {return 1;}
    const at = t.indexOf(query);
    if (at < 0) {return Infinity;}
    return /[\s/_.:,-]/.test(t[at - 1]) ? 2 : 3;  // word start beats mid-word
}

/**
 * Nodes matching `query`, best first: exact name, then prefix, then word
 * start, then anywhere; defined objects before undefined ones; then by label.
 *
 * @param {Array} nodes
 * @param {string} query
 * @param {object} [options]
 * @param {string} [options.type] - Only this object type
 * @param {number} [options.limit=30]
 * @returns {{results: Array, total: number}}
 */
export function searchNodes(nodes, query, { type = '', limit = 30 } = {}) {
    const q = query.trim().toLowerCase();
    if (!q) {return { results: [], total: 0 };}
    const scored = [];
    for (const node of nodes) {
        if (type && node.type !== type) {continue;}
        const name = node.type === 'service' ? node.label.split(' / ')[0] : node.label;
        const rank = Math.min(
            matchRank(name, q),
            matchRank(node.label, q) + 0.5,
            matchRank(node.search_label, q) + 0.5,
            matchRank(node.detail, q) + 4
        );
        if (rank !== Infinity) {scored.push({ node, rank });}
    }
    scored.sort((a, b) =>
        a.rank - b.rank
        || (a.node.exists === false) - (b.node.exists === false)
        || a.node.label.localeCompare(b.node.label)
        || a.node.type.localeCompare(b.node.type));
    return { results: scored.slice(0, limit).map(s => s.node), total: scored.length };
}
