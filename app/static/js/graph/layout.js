/**
 * Graph View layouts: node positions computed from nodes and edges. No DOM,
 * so it runs under node:test (tests/js/graph-layout.test.mjs).
 */

/**
 * Hierarchical layout by edge direction (dagre).
 *
 * An edge ranks its source above (or left of) its target, except edges that
 * name a template (`use`): those rank the template above the object using it,
 * so ancestors sit above descendants. `parents` edges already run from the
 * parent host to the child.
 *
 * @param {object} dagre - The dagre library
 * @param {Array} nodes - Nodes to place ({id, label})
 * @param {Array} edges - Edges among them ({from, to, label})
 * @param {object} options
 * @param {'TB'|'LR'} options.rankDir
 * @param {Set<string>} options.ancestorFields - Fields whose target ranks above the source
 * @param {object} options.config - LAYOUT_CONFIG.dagre
 * @returns {Object<string, {x: number, y: number}>}
 */
export function hierarchicalPositions(dagre, nodes, edges, { rankDir, ancestorFields, config }) {
    const g = new dagre.graphlib.Graph({ multigraph: true });
    g.setGraph({
        rankdir: rankDir,
        nodesep: config.nodeSep,
        ranksep: rankDir === 'LR' ? config.rankSepLR : config.rankSep,
        ranker: 'network-simplex'
    });
    g.setDefaultEdgeLabel(() => ({}));
    for (const node of nodes) {
        const width = Math.min(config.maxNodeWidth,
            Math.max(config.minNodeWidth, (node.label || '').length * config.charWidth));
        g.setNode(node.id, { width, height: config.nodeHeight });
    }
    for (const edge of edges) {
        if (!g.hasNode(edge.from) || !g.hasNode(edge.to)) {continue;}
        const [source, target] = ancestorFields.has(edge.label) ? [edge.to, edge.from] : [edge.from, edge.to];
        g.setEdge(source, target, {}, `${edge.from}|${edge.label}|${edge.to}`);
    }
    dagre.layout(g);
    const positions = {};
    for (const id of g.nodes()) {
        const { x, y } = g.node(id);
        positions[id] = { x, y };
    }
    return positions;
}

// ---------------------------------------------------------------------------
// Clustered layout (Full Graph and the default view with a focus node)
// ---------------------------------------------------------------------------

// Type clusters around the focus node. A cluster with `orbitsAround` is placed
// in a ring around that cluster instead of at its own angle.
const CLUSTER_DEFS = {
    contactgroups: { types: ['contactgroup'], angle: -Math.PI / 2 },
    contacts: { types: ['contact'], angle: -Math.PI / 2, orbitsAround: 'contactgroups' },
    services: { types: ['service'], angle: -Math.PI / 2, orbitsAround: 'contacts' },
    commands: { types: ['command'], angle: -Math.PI / 2, orbitsAround: 'services' },
    timeperiods: { types: ['timeperiod'], angle: -Math.PI / 2, orbitsAround: 'services' },
    hostgroups: { types: ['hostgroup'], angle: Math.PI },
    servicegroups: { types: ['servicegroup'], angle: 0 },
    hosts: { types: ['host'], angle: Math.PI * 3 / 4 },
    dependencies: {
        types: ['servicedependency', 'hostdependency', 'serviceescalation', 'hostescalation'],
        angle: Math.PI / 4
    }
};

const byLabel = nodeMap => (a, b) => (nodeMap[a]?.label || '').localeCompare(nodeMap[b]?.label || '');

/** Nodes reachable from the focus over edges in either direction, and the rest. */
function reach(nodes, edges, focusId) {
    const nodeMap = {};
    const adjacency = {};
    for (const node of nodes) {
        nodeMap[node.id] = node;
        adjacency[node.id] = new Set();
    }
    for (const edge of edges) {
        if (adjacency[edge.from] && adjacency[edge.to]) {
            adjacency[edge.from].add(edge.to);
            adjacency[edge.to].add(edge.from);
        }
    }
    const visited = new Set();
    if (adjacency[focusId]) {
        visited.add(focusId);
        const queue = [focusId];
        for (let head = 0; head < queue.length; head++) {
            for (const next of adjacency[queue[head]]) {
                if (!visited.has(next)) {
                    visited.add(next);
                    queue.push(next);
                }
            }
        }
    }
    const disconnected = nodes.map(n => n.id).filter(id => !visited.has(id));
    return { nodeMap, visited, disconnected };
}

/** A cluster's nodes in concentric rings around its centre. */
function positionClusterNodes(nodeList, centerX, centerY, clusterAngle, nodeMap, config) {
    const positions = {};
    let maxRadius = 0;
    const { clusterRadius, clusterRadiusStep, nodesPerRing } = config;
    nodeList.sort(byLabel(nodeMap));
    if (nodeList.length === 1) {
        positions[nodeList[0]] = { x: centerX, y: centerY };
    } else {
        nodeList.forEach((nodeId, i) => {
            const ringIndex = Math.floor(i / nodesPerRing);
            const posInRing = i % nodesPerRing;
            const nodesInThisRing = Math.min(nodesPerRing, nodeList.length - ringIndex * nodesPerRing);
            const nodeRadius = clusterRadius + ringIndex * clusterRadiusStep;
            maxRadius = Math.max(maxRadius, nodeRadius);
            const nodeAngle = clusterAngle + posInRing * ((2 * Math.PI) / nodesInThisRing);
            positions[nodeId] = {
                x: centerX + Math.cos(nodeAngle) * nodeRadius,
                y: centerY + Math.sin(nodeAngle) * nodeRadius
            };
        });
    }
    return { positions, maxRadius };
}

/** An orbiting cluster in rings just outside its parent cluster. */
function positionOrbitCluster(nodeList, parentBounds, nodeMap, config) {
    const positions = {};
    const orbitRadius = parentBounds.outerRadius + config.orbitGap;
    const nodesPerOrbitRing = Math.max(6, Math.floor((2 * Math.PI * orbitRadius) / 80));
    let maxOrbitRadius = orbitRadius;
    nodeList.sort(byLabel(nodeMap));
    nodeList.forEach((nodeId, i) => {
        const ringIndex = Math.floor(i / nodesPerOrbitRing);
        const posInRing = i % nodesPerOrbitRing;
        const nodesInThisRing = Math.min(nodesPerOrbitRing, nodeList.length - ringIndex * nodesPerOrbitRing);
        const nodeRadius = orbitRadius + ringIndex * 80;
        maxOrbitRadius = Math.max(maxOrbitRadius, nodeRadius);
        const nodeAngle = posInRing * ((2 * Math.PI) / nodesInThisRing) - Math.PI / 2;
        positions[nodeId] = {
            x: parentBounds.centerX + Math.cos(nodeAngle) * nodeRadius,
            y: parentBounds.centerY + Math.sin(nodeAngle) * nodeRadius
        };
    });
    return { positions, maxOrbitRadius };
}

function groupNodesByCluster(visited, focusId, nodeMap, clusterDefs) {
    const clusters = { other: [] };
    for (const name of Object.keys(clusterDefs)) {clusters[name] = [];}
    for (const nodeId of visited) {
        if (nodeId === focusId || !nodeMap[nodeId]) {continue;}
        const name = Object.keys(clusterDefs).find(c => clusterDefs[c].types.includes(nodeMap[nodeId].type));
        clusters[name || 'other'].push(nodeId);
    }
    return clusters;
}

function positionClusters(tree, focusId, config) {
    const positions = { [focusId]: { x: 0, y: 0 } };
    const clusterDefs = { ...CLUSTER_DEFS };
    const clusters = groupNodesByCluster(tree.visited, focusId, tree.nodeMap, clusterDefs);
    if (clusters.other.length > 0) {
        clusterDefs.other = { types: [], angle: Math.PI * 2 / 3 };
    }
    const { clusterDistance } = config;
    const clusterBounds = {};
    const orbitDepth = name => (clusterDefs[name]?.orbitsAround ? 1 + orbitDepth(clusterDefs[name].orbitsAround) : 0);
    const order = Object.keys(clusters).filter(name => clusters[name].length > 0);
    order.sort((a, b) => orbitDepth(a) - orbitDepth(b));

    for (const name of order) {
        const def = clusterDefs[name];
        if (!def) {continue;}
        if (!def.orbitsAround) {
            const cx = Math.cos(def.angle) * clusterDistance;
            const cy = Math.sin(def.angle) * clusterDistance;
            const result = positionClusterNodes(clusters[name], cx, cy, def.angle, tree.nodeMap, config);
            Object.assign(positions, result.positions);
            clusterBounds[name] = { centerX: cx, centerY: cy, outerRadius: result.maxRadius };
            continue;
        }
        const parentName = def.orbitsAround;
        let parentBounds = clusterBounds[parentName];
        if (!parentBounds) {
            const angle = clusterDefs[parentName] ? clusterDefs[parentName].angle : def.angle;
            parentBounds = {
                centerX: Math.cos(angle) * clusterDistance,
                centerY: Math.sin(angle) * clusterDistance,
                outerRadius: 0
            };
            clusterBounds[parentName] = parentBounds;
        }
        const result = positionOrbitCluster(clusters[name], parentBounds, tree.nodeMap, config);
        Object.assign(positions, result.positions);
        clusterBounds[name] = {
            centerX: parentBounds.centerX, centerY: parentBounds.centerY, outerRadius: result.maxOrbitRadius
        };
        // Clusters orbiting the same parent (or its ancestors) go further out.
        for (let ancestor = parentName; ancestor; ancestor = clusterDefs[ancestor]?.orbitsAround) {
            if (clusterBounds[ancestor]) {
                clusterBounds[ancestor].outerRadius = Math.max(clusterBounds[ancestor].outerRadius, result.maxOrbitRadius);
            }
        }
    }

    if (tree.disconnected.length > 0) {
        const angle = Math.PI * 7 / 8;
        const dcX = Math.cos(angle) * clusterDistance;
        const dcY = Math.sin(angle) * clusterDistance;
        if (tree.disconnected.length === 1) {
            positions[tree.disconnected[0]] = { x: dcX, y: dcY };
        } else {
            const step = (2 * Math.PI) / tree.disconnected.length;
            tree.disconnected.forEach((nodeId, i) => {
                positions[nodeId] = {
                    x: dcX + Math.cos(i * step) * config.clusterRadius,
                    y: dcY + Math.sin(i * step) * config.clusterRadius
                };
            });
        }
    }
    return positions;
}

/** Push overlapping nodes apart; the focus node stays put. */
function resolveCollisions(positions, focusId, minDistance) {
    const ids = Object.keys(positions);
    for (let iter = 0; iter < 6; iter++) {
        for (let i = 0; i < ids.length; i++) {
            for (let j = i + 1; j < ids.length; j++) {
                const a = positions[ids[i]];
                const b = positions[ids[j]];
                const dx = b.x - a.x;
                const dy = b.y - a.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist >= minDistance || dist === 0) {continue;}
                const push = (minDistance - dist) * 0.5;
                const px = (dx / dist) * push;
                const py = (dy / dist) * push;
                if (ids[i] !== focusId) {
                    a.x -= px;
                    a.y -= py;
                }
                if (ids[j] !== focusId) {
                    b.x += px;
                    b.y += py;
                }
            }
        }
    }
}

/**
 * Clustered layout around a focus node: the focus at the origin, each type in
 * a cluster at its own angle, contacts/services/commands/time periods in
 * rings orbiting the contact groups, unreachable nodes in a group of their own.
 *
 * @param {Array} nodes - Nodes to place ({id, type, label})
 * @param {Array} edges - Edges among them ({from, to})
 * @param {string} focusId
 * @param {object} config - LAYOUT_CONFIG.cluster
 * @returns {Object<string, {x: number, y: number}>}
 */
export function clusterPositions(nodes, edges, focusId, config) {
    if (!focusId || nodes.length === 0) {return {};}
    const positions = positionClusters(reach(nodes, edges, focusId), focusId, config);
    resolveCollisions(positions, focusId, config.minNodeDistance);
    return positions;
}

/**
 * Edge bundling for the clustered layout: each edge bends toward the centre of
 * its target's type cluster, so edges into one cluster run together.
 *
 * @param {Array} nodes - Placed nodes ({id, type})
 * @param {Array} edges - ({id, from, to})
 * @param {Object<string, {x: number, y: number}>} positions
 * @returns {Map<string, number>} edge id -> control point distance (only edges that bend)
 */
export function bundleEdges(nodes, edges, positions, strength = 0.4) {
    const sums = new Map();
    const typeOf = new Map();
    for (const node of nodes) {
        typeOf.set(node.id, node.type);
        const pos = positions[node.id];
        if (!pos) {continue;}
        const sum = sums.get(node.type) || { x: 0, y: 0, n: 0 };
        sums.set(node.type, { x: sum.x + pos.x, y: sum.y + pos.y, n: sum.n + 1 });
    }
    const result = new Map();
    for (const edge of edges) {
        const s = positions[edge.from];
        const t = positions[edge.to];
        const centroid = sums.get(typeOf.get(edge.to));
        if (!s || !t || !centroid) {continue;}
        const midX = (s.x + t.x) / 2;
        const midY = (s.y + t.y) / 2;
        const cx = midX + (centroid.x / centroid.n - midX) * strength;
        const cy = midY + (centroid.y / centroid.n - midY) * strength;
        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len === 0) {continue;}
        // Signed perpendicular distance of the control point from the straight line.
        const distance = ((cy - s.y) * dx - (cx - s.x) * dy) / len;
        if (Math.abs(distance) > 10) {result.set(edge.id, distance);}
    }
    return result;
}
