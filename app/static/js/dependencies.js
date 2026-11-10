/**
 * Nagios Bulk Editor - Graph View page
 *
 * Draws the object graph from GET /api/dependencies with Cytoscape.js. The
 * graph logic (expansion, filtering, search) is in graph/model.js and the
 * layouts in graph/layout.js; this module holds the page state, the one
 * Cytoscape instance and the DOM.
 *
 * Domain metadata (type colours, edge labels/colours/categories) comes from
 * GET /api/metadata ("graph"); see app/nagios_model.py.
 */

import {
    LAYOUT_CONFIG, GRAPH_LIMITS, quickViewPresets, expansionRules, typeIconSvg, defaultIconSvg
} from './dependencies-config.js';
import {
    buildGraphIndex, edgesFrom, edgesTo, edgeId, expandEffective, expandWithRules, ruleFields,
    presetsForType, computeDisplay, searchNodes
} from './graph/model.js';
import { hierarchicalPositions, clusterPositions, bundleEdges } from './graph/layout.js';
import { ApiClient, apiUrl } from './api-client.js';
import { escapeHtml } from './app.js';
import { showToast } from './ui-notifications.js';

const STORAGE_KEY = 'graphViewState';
const LAYOUTS = ['static', 'hierarchical', 'hierarchicalLR'];

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
    index: null,              // buildGraphIndex() of the API data
    meta: null,               // /api/metadata "graph"
    typeLabels: {},           // /api/metadata object_type_labels
    allTypes: [],             // graph node types, in metadata order
    allCategories: [],        // edge categories, in metadata order
    ancestorFields: new Set(),// fields naming a template: ranked above their users

    addedIds: new Set(),      // nodes in the graph (before filters)
    manualIds: new Set(),     // added by hand: shown even without a visible edge
    focusId: null,            // focus node: quick views start here, force layout centres on it
    activeQuickView: null,    // preset that produced the graph, null once the user changes it
    enabledTypes: new Set(),
    edgeFilter: { fields: null, categories: new Set() },
    layout: 'static',
    showEdgeLabels: true
};

let cy = null;
let display = { nodes: [], edges: [], hidden: new Map() };
// Last laid-out position of each drawn node. Lets nodes hidden by a filter
// come back where they were without re-running the layout.
let positionCache = new Map();
let contextMenuNodeIds = [];
let search = { results: [], total: 0, active: -1, timer: null };
let highlightPending = false;
let hoveredNodeId = null;

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    start();
});

async function start() {
    if (!await loadData()) {return;}
    buildFilterControls();
    restoreState();
    syncControls();
    renderQuickViewButtons();
    render({ relayout: true });
    saveState();
}

async function loadData() {
    showLoadError(null);
    const [metaResult, graphResult] = await Promise.all([
        ApiClient.get('/api/metadata', { silent: true }),
        ApiClient.get('/api/dependencies', { silent: true })
    ]);
    const failed = [metaResult, graphResult].find(r => !r.success);
    if (failed) {
        showLoadError(failed.error || 'Request failed');
        return false;
    }
    const meta = metaResult.payload || {};
    const data = graphResult.payload;
    if (!meta.graph || !Array.isArray(data?.nodes) || !Array.isArray(data?.edges)) {
        showLoadError('The server returned data the graph cannot read');
        return false;
    }
    state.meta = meta.graph;
    state.typeLabels = meta.object_type_labels || {};
    state.allTypes = meta.graph.node_type_order;
    state.allCategories = meta.graph.edge_category_order;
    state.ancestorFields = new Set(Object.entries(meta.graph.edge_fields)
        .filter(([, field]) => field.target === 'template').map(([name]) => name));
    state.index = buildGraphIndex(data.nodes, data.edges);
    state.enabledTypes = new Set(state.allTypes);
    state.edgeFilter = { fields: null, categories: defaultCategories() };
    return true;
}

function showLoadError(message) {
    const errorState = document.getElementById('graphErrorState');
    const emptyState = document.getElementById('graphEmptyState');
    if (message === null) {
        errorState.hidden = true;
        return;
    }
    document.getElementById('graphErrorMessage').textContent = message;
    errorState.hidden = false;
    emptyState.hidden = true;
}

function defaultCategories() {
    return new Set(state.allCategories.filter(c => state.meta.edge_categories[c].default));
}

// ---------------------------------------------------------------------------
// Persistence: the URL (shareable) and sessionStorage (navbar visits)
// ---------------------------------------------------------------------------

function serializeState() {
    return {
        addedIds: [...state.addedIds],
        manualIds: [...state.manualIds],
        focusId: state.focusId,
        activeQuickView: state.activeQuickView,
        enabledTypes: [...state.enabledTypes],
        edgeFields: state.edgeFilter.fields ? [...state.edgeFilter.fields] : null,
        edgeCategories: [...state.edgeFilter.categories],
        layout: state.layout,
        showEdgeLabels: state.showEdgeLabels
    };
}

/**
 * URL for the current view. A quick view is fully described by its focus node
 * and preset; anything else lists its nodes and filters.
 */
function stateToParams() {
    const params = new URLSearchParams();
    if (state.addedIds.size === 0) {return params;}
    if (state.focusId) {params.set('node', state.focusId);}
    const preset = quickViewPresets[state.activeQuickView];
    if (preset) {
        params.set('view', state.activeQuickView);
        if (state.layout !== preset.layout) {params.set('layout', state.layout);}
    } else {
        for (const id of state.addedIds) {params.append('n', id);}
        for (const id of state.manualIds) {params.append('m', id);}
        params.set('layout', state.layout);
        if (state.enabledTypes.size !== state.allTypes.length) {
            params.set('types', [...state.enabledTypes].join(','));
        }
        if (state.edgeFilter.fields) {
            params.set('fields', [...state.edgeFilter.fields].join(','));
        } else {
            params.set('edges', [...state.edgeFilter.categories].join(','));
        }
    }
    if (!state.showEdgeLabels) {params.set('labels', '0');}
    return params;
}

function saveState() {
    try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(serializeState()));
    } catch (e) {
        // Storage unavailable (private mode, quota): the URL still holds the view.
    }
    const query = stateToParams().toString();
    const url = window.location.pathname + (query ? `?${query}` : '');
    if (url !== window.location.pathname + window.location.search) {
        window.history.replaceState(null, '', url);
    }
}

function validIds(ids) {
    return (ids || []).filter(id => state.index.byId.has(id));
}

function listParam(params, name, allowed) {
    const value = params.get(name);
    if (value === null) {return null;}
    return new Set(value.split(',').filter(v => allowed.includes(v)));
}

/** Restore from the URL if it names a node, else from this tab's session. */
function restoreState() {
    const params = new URLSearchParams(window.location.search);
    const node = params.get('node');
    if (params.has('labels')) {state.showEdgeLabels = params.get('labels') !== '0';}
    if (LAYOUTS.includes(params.get('layout'))) {state.layout = params.get('layout');}

    if (node && !state.index.byId.has(node)) {
        showToast(`"${node}" is not in the configuration`, 'warning');
    } else if (node || params.has('n')) {
        state.focusId = node;
        if (params.has('n')) {
            state.addedIds = new Set(validIds(params.getAll('n')));
            state.manualIds = new Set(validIds(params.getAll('m')));
            state.enabledTypes = listParam(params, 'types', state.allTypes) || new Set(state.allTypes);
            const fields = params.get('fields');
            state.edgeFilter = fields
                ? { fields: new Set(fields.split(',')), categories: new Set() }
                : { fields: null, categories: listParam(params, 'edges', state.allCategories) || defaultCategories() };
            return;
        }
        // A node and a view (Explorer links send only the node: Full Graph).
        const view = quickViewPresets[params.get('view')] ? params.get('view') : 'full';
        const layout = params.get('layout');
        state.addedIds = new Set([node]);
        applyQuickView(view, { save: false, render: false });
        if (LAYOUTS.includes(layout)) {state.layout = layout;}
        return;
    }
    loadSessionState();
}

function loadSessionState() {
    let saved;
    try {
        saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    } catch (e) {
        saved = null;
    }
    if (!saved || typeof saved !== 'object') {return;}
    state.addedIds = new Set(validIds(saved.addedIds));
    state.manualIds = new Set(validIds(saved.manualIds));
    state.focusId = state.index.byId.has(saved.focusId) ? saved.focusId : null;
    state.activeQuickView = quickViewPresets[saved.activeQuickView] ? saved.activeQuickView : null;
    if (Array.isArray(saved.enabledTypes)) {
        state.enabledTypes = new Set(saved.enabledTypes.filter(t => state.allTypes.includes(t)));
    }
    if (Array.isArray(saved.edgeFields)) {
        state.edgeFilter = { fields: new Set(saved.edgeFields), categories: new Set() };
    } else if (Array.isArray(saved.edgeCategories)) {
        state.edgeFilter = {
            fields: null,
            categories: new Set(saved.edgeCategories.filter(c => state.allCategories.includes(c)))
        };
    }
    if (LAYOUTS.includes(saved.layout)) {state.layout = saved.layout;}
    if (typeof saved.showEdgeLabels === 'boolean') {state.showEdgeLabels = saved.showEdgeLabels;}
}

// ---------------------------------------------------------------------------
// Graph changes
// ---------------------------------------------------------------------------

/** Mark the graph as changed by hand: it no longer matches a quick view. */
function leaveQuickView() {
    if (state.activeQuickView) {
        state.activeQuickView = null;
        updateQuickViewButtons();
    }
}

function changed({ relayout = false } = {}) {
    render({ relayout });
    saveState();
}

function applyQuickView(presetId, { save = true, render: doRender = true } = {}) {
    const preset = quickViewPresets[presetId];
    if (!preset) {return;}
    const rootId = state.index.byId.has(state.focusId) ? state.focusId : [...state.addedIds][0];
    if (!rootId) {
        showToast('Add a node to the graph first, then apply a quick view', 'info');
        return;
    }
    const root = state.index.byId.get(rootId);
    const rules = preset.smartExpansion ? null : expansionRules[root.type]?.[presetId];
    if (!preset.smartExpansion && !rules) {
        showToast(`${preset.label} is not available for ${root.type} objects`, 'info');
        return;
    }

    const allowedTypes = preset.types ? new Set(preset.types) : null;
    const result = new Set([rootId]);
    if (preset.smartExpansion) {
        expandEffective(state.index, rootId, result);
    } else {
        expandWithRules(state.index, rootId, rules, result, { allowedTypes });
    }

    state.activeQuickView = presetId;
    state.focusId = rootId;
    state.addedIds = result;
    state.manualIds = new Set();
    state.enabledTypes = allowedTypes
        ? new Set(state.allTypes.filter(t => allowedTypes.has(t)))
        : new Set(state.allTypes);
    state.edgeFilter = rules
        ? { fields: ruleFields(rules), categories: new Set() }
        : { fields: null, categories: new Set(state.allCategories) };
    state.layout = preset.layout;

    if (doRender) {
        syncControls();
        renderQuickViewButtons();
        render({ relayout: true });
    }
    if (save) {saveState();}
}

function addNode(nodeId) {
    if (!state.index.byId.has(nodeId) || state.addedIds.has(nodeId)) {return;}
    const isFirst = state.addedIds.size === 0;
    if (isFirst) {state.focusId = nodeId;}
    state.addedIds.add(nodeId);
    state.manualIds.add(nodeId);
    leaveQuickView();
    if (isFirst) {renderQuickViewButtons();}
    changed();
}

function removeNodes(ids) {
    for (const id of ids) {
        state.addedIds.delete(id);
        state.manualIds.delete(id);
    }
    leaveQuickView();
    changed();
}

function clearGraph() {
    state.addedIds = new Set();
    state.manualIds = new Set();
    state.focusId = null;
    state.activeQuickView = null;
    renderQuickViewButtons();
    changed();
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function render({ relayout = false } = {}) {
    const pinned = new Set(state.manualIds);
    if (state.focusId) {pinned.add(state.focusId);}
    if (cy) {cy.$('node:selected').forEach(n => { pinned.add(n.id()); });}
    display = computeDisplay(state.index, {
        addedIds: state.addedIds,
        enabledTypes: state.enabledTypes,
        edgeFilter: state.edgeFilter,
        pinnedIds: pinned
    });
    updateCanvas(relayout);
    updateNodeList();
    updateLegend();
    updateEmptyState();
}

function updateEmptyState() {
    const emptyState = document.getElementById('graphEmptyState');
    const legend = document.getElementById('graphLegend');
    const empty = display.nodes.length === 0;
    emptyState.hidden = !empty || !document.getElementById('graphErrorState').hidden;
    legend.hidden = empty;
    const filteredOut = empty && state.addedIds.size > 0;
    document.getElementById('graphEmptyTitle').textContent = filteredOut
        ? `All ${state.addedIds.size} nodes are hidden by the current filters`
        : 'No nodes in graph';
    document.getElementById('graphEmptyTips').hidden = filteredOut;
}

function fieldMeta(field) {
    return state.meta.edge_fields[field] || {};
}

function nodeImage(node) {
    const isTemplate = node.is_template === true;
    const exists = node.exists !== false;
    const additive = node.additive === true;
    return getNodeImageUrl(node.type, node.color, isTemplate, exists, additive);
}

function nodeData(node) {
    return {
        id: node.id,
        label: node.label,
        imageUrl: nodeImage(node),
        isFocus: node.id === state.focusId
    };
}

function edgeData(edge) {
    const meta = fieldMeta(edge.label);
    return {
        id: edgeId(edge),
        source: edge.from,
        target: edge.to,
        field: edge.label,
        displayLabel: meta.label || edge.label.replace(/_/g, ' '),
        color: meta.color || '#999'
    };
}

/** Bring the Cytoscape elements in line with `display`, changing only what differs. */
function updateCanvas(relayout) {
    if (display.nodes.length === 0) {
        if (cy) {cy.elements().remove();}
        hideTooltip();
        return;
    }
    ensureCy();
    const wantedNodes = new Map(display.nodes.map(n => [n.id, n]));
    const wantedEdges = new Map(display.edges.map(e => [edgeId(e), e]));
    let unplaced = false;
    cy.batch(() => {
        cy.edges().filter(e => !wantedEdges.has(e.id())).remove();
        cy.nodes().filter(n => !wantedNodes.has(n.id())).remove();
        const additions = [];
        for (const [id, node] of wantedNodes) {
            const existing = cy.getElementById(id);
            if (existing.nonempty()) {
                existing.data(nodeData(node));
                continue;
            }
            const cached = positionCache.get(id);
            if (!cached) {unplaced = true;}
            additions.push({ group: 'nodes', data: nodeData(node), position: cached ? { ...cached } : { x: 0, y: 0 } });
        }
        for (const [id, edge] of wantedEdges) {
            if (cy.getElementById(id).empty()) {additions.push({ group: 'edges', data: edgeData(edge) });}
        }
        cy.add(additions);
    });
    if (relayout || unplaced) {
        runLayout();
    }
    scheduleHighlight();
}

function runLayout() {
    if (!cy || cy.nodes().empty()) {return;}
    // Edges bend toward their target's cluster only in the clustered layout.
    cy.edges().data({ hasBundling: false, controlDistance: 0 });
    let layout;
    if (state.layout === 'hierarchical' || state.layout === 'hierarchicalLR') {
        const positions = hierarchicalPositions(window.dagre, display.nodes, display.edges, {
            rankDir: state.layout === 'hierarchicalLR' ? 'LR' : 'TB',
            ancestorFields: state.ancestorFields,
            config: LAYOUT_CONFIG.dagre
        });
        layout = cy.layout({
            name: 'preset',
            positions: n => positions[n.id()] || n.position(),
            fit: true,
            padding: 50,
            animate: false
        });
    } else if (state.focusId && cy.getElementById(state.focusId).nonempty()) {
        const positions = clusterPositions(display.nodes, display.edges, state.focusId, LAYOUT_CONFIG.cluster);
        const bends = bundleEdges(display.nodes, display.edges.map(e => ({ ...e, id: edgeId(e) })), positions);
        cy.batch(() => {
            cy.edges().forEach(e => {
                const bend = bends.get(e.id());
                e.data({ hasBundling: bend !== undefined, controlDistance: bend ?? 0 });
            });
        });
        layout = cy.layout({
            name: 'preset',
            positions: n => positions[n.id()] || n.position(),
            fit: true,
            padding: 50,
            animate: false
        });
    } else {
        layout = cy.layout({
            name: 'cose',
            ...LAYOUT_CONFIG.cose,
            randomize: false,
            fit: true,
            padding: 50,
            animate: false
        });
    }
    layout.one('layoutstop', () => {
        positionCache = new Map();
        cy.nodes().forEach(n => { positionCache.set(n.id(), { ...n.position() }); });
        limitFitZoom();
    });
    layout.run();
}

/** After a fit, keep a small graph at a readable size instead of filling the screen. */
function limitFitZoom() {
    if (cy.zoom() > LAYOUT_CONFIG.maxFitZoom) {
        cy.zoom(LAYOUT_CONFIG.maxFitZoom);
        cy.center();
    }
}

function getCytoscapeStyle() {
    const labelFont = {
        'font-size': 9,
        'color': '#aaa',
        'text-background-color': '#1e1e1e',
        'text-background-opacity': 0.9,
        'text-background-padding': 2,
        'text-rotation': 'autorotate'
    };
    return [
        {
            selector: 'node',
            style: {
                'background-image': 'data(imageUrl)',
                'background-fit': 'contain',
                'background-opacity': 0,
                'width': 50,
                'height': 50,
                'label': 'data(label)',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'text-margin-y': 5,
                'text-wrap': 'ellipsis',
                'text-max-width': `${LAYOUT_CONFIG.dagre.maxNodeWidth - 10}px`,
                'font-size': 11,
                'color': '#fff',
                'text-background-color': 'rgba(0,0,0,0.8)',
                'text-background-opacity': 1,
                'text-background-padding': 3,
                'text-background-shape': 'roundrectangle'
            }
        },
        { selector: 'node[?isFocus]', style: { 'width': 60, 'height': 60, 'font-size': 13 } },
        { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#4ec9b0', 'border-opacity': 1 } },
        {
            selector: 'edge',
            style: {
                'width': 1.5,
                'line-color': 'data(color)',
                'target-arrow-color': 'data(color)',
                'target-arrow-shape': 'triangle',
                'arrow-scale': 0.8,
                'curve-style': 'bezier',
                'label': state.showEdgeLabels ? 'data(displayLabel)' : '',
                ...labelFont
            }
        },
        {
            selector: 'edge[?hasBundling]',
            style: {
                'curve-style': 'unbundled-bezier',
                'control-point-distances': ele => [ele.data('controlDistance')],
                'control-point-weights': [0.5]
            }
        },
        { selector: 'edge:selected', style: { 'width': 2.5, 'line-color': '#4ec9b0', 'target-arrow-color': '#4ec9b0' } },
        // Hover/selection: the node, its edges and neighbours stay; the rest fades.
        { selector: '.faded', style: { 'opacity': 0.12 } },
        { selector: 'node.highlighted', style: { 'z-index': 20 } },
        { selector: 'edge.highlighted', style: { 'width': 2.5, 'z-index': 19, 'label': 'data(displayLabel)' } }
    ];
}

function ensureCy() {
    if (cy) {return;}
    cy = cytoscape({
        container: document.getElementById('graphContainer'),
        style: getCytoscapeStyle(),
        layout: { name: 'preset' },
        boxSelectionEnabled: true,
        selectionType: 'additive',
        minZoom: 0.1,
        maxZoom: 3
    });

    cy.on('tap', evt => {
        if (evt.target === cy) {hideContextMenu();}
    });
    cy.on('tap', 'node', () => hideContextMenu());
    cy.on('cxttap', evt => {
        if (evt.target === cy) {hideContextMenu();}
    });
    cy.on('cxttap', 'node', evt => {
        evt.originalEvent.preventDefault();
        const node = evt.target;
        let ids;
        if (node.selected()) {
            ids = cy.$('node:selected').map(n => n.id());
        } else {
            cy.$(':selected').unselect();
            node.select();
            ids = [node.id()];
        }
        showContextMenu(evt.originalEvent, ids);
    });
    cy.on('dragfree', 'node', evt => {
        positionCache.set(evt.target.id(), { ...evt.target.position() });
    });

    cy.on('mouseover', 'node', evt => {
        hoveredNodeId = evt.target.id();
        highlight(evt.target);
        showTooltip(nodeTooltipLines(evt.target.id()), evt.renderedPosition);
    });
    cy.on('mouseover', 'edge', evt => {
        showTooltip(edgeTooltipLines(evt.target), evt.renderedPosition);
    });
    cy.on('mouseout', 'node', () => {
        hoveredNodeId = null;
        hideTooltip();
        scheduleHighlight();
    });
    cy.on('mouseout', 'edge', hideTooltip);
    cy.on('select unselect', 'node', scheduleHighlight);
    cy.on('viewport', hideTooltip);
}

// --- Highlighting and tooltips ---------------------------------------------

function highlight(node) {
    cy.batch(() => {
        cy.elements().removeClass('highlighted').addClass('faded');
        node.closedNeighborhood().removeClass('faded').addClass('highlighted');
    });
}

/**
 * Highlight the hovered node, else the single selected node, else nothing.
 * Batched: box selection fires one event per node.
 */
function scheduleHighlight() {
    if (highlightPending) {return;}
    highlightPending = true;
    requestAnimationFrame(() => {
        highlightPending = false;
        if (!cy) {return;}
        const hovered = hoveredNodeId ? cy.getElementById(hoveredNodeId) : null;
        const selected = cy.$('node:selected');
        if (hovered?.nonempty()) {
            highlight(hovered);
        } else if (selected.length === 1) {
            highlight(selected[0]);
        } else {
            cy.elements().removeClass('faded highlighted');
        }
    });
}

function nodeTooltipLines(id) {
    const node = state.index.byId.get(id);
    if (!node) {return [id];}
    const kind = node.is_template ? `${node.type} template` : node.type;
    const lines = [{ text: node.label, strong: true }, kind];
    if (node.detail) {lines.push(`on ${node.detail.split(',').join(', ')}`);}
    if (node.exists === false) {lines.push('Not defined in any config file');}
    if (node.additive) {lines.push('Added with + (additive inheritance)');}
    if (id === state.focusId) {lines.push('Focus node');}
    return lines;
}

function edgeTooltipLines(edge) {
    const from = state.index.byId.get(edge.data('source'));
    const to = state.index.byId.get(edge.data('target'));
    return [
        { text: edge.data('displayLabel'), strong: true },
        `field: ${edge.data('field')}`,
        `${from?.label ?? edge.data('source')} → ${to?.label ?? edge.data('target')}`
    ];
}

function showTooltip(lines, renderedPos) {
    const tip = document.getElementById('graphTooltip');
    tip.replaceChildren(...lines.map(line => {
        const div = document.createElement('div');
        div.textContent = typeof line === 'string' ? line : line.text;
        if (line.strong) {div.className = 'graph-tooltip-title';}
        return div;
    }));
    tip.hidden = false;
    const box = document.getElementById('graphContainer').getBoundingClientRect();
    const x = Math.min(renderedPos.x + 14, box.width - tip.offsetWidth - 8);
    const y = renderedPos.y + 14 + tip.offsetHeight > box.height
        ? renderedPos.y - tip.offsetHeight - 10
        : renderedPos.y + 14;
    tip.style.left = `${Math.max(8, x)}px`;
    tip.style.top = `${Math.max(8, y)}px`;
}

function hideTooltip() {
    const tip = document.getElementById('graphTooltip');
    if (tip) {tip.hidden = true;}
}

// --- Node images and badges ------------------------------------------------

const nodeImageCache = new Map();

/**
 * SVG data URL for a node: the type icon in a white circle. Templates get a
 * dashed ring and their own icon, undefined objects a red X, additive (+)
 * references a green "+" badge.
 */
function getNodeImageUrl(type, color, isTemplate = false, exists = true, isAdditive = false) {
    const key = `${type}|${color}|${isTemplate}|${exists}|${isAdditive}`;
    if (nodeImageCache.has(key)) {return nodeImageCache.get(key);}
    const iconType = isTemplate && (type === 'host' || type === 'service') ? `${type}_template` : type;
    const iconData = typeIconSvg[iconType] || typeIconSvg[type] || defaultIconSvg;
    const ring = isTemplate ? 'stroke-width="3" stroke-dasharray="4,2"' : 'stroke-width="2"';
    const orphanOverlay = exists ? '' : `
        <line x1="10" y1="10" x2="40" y2="40" stroke="#f14c4c" stroke-width="4" stroke-linecap="round"/>
        <line x1="40" y1="10" x2="10" y2="40" stroke="#f14c4c" stroke-width="4" stroke-linecap="round"/>`;
    const additiveOverlay = isAdditive ? `
        <circle cx="40" cy="10" r="7" fill="#4CAF50"/>
        <text x="40" y="14" text-anchor="middle" fill="white" font-size="12" font-weight="bold">+</text>` : '';
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 50 50">
        <circle cx="25" cy="25" r="23" fill="white" stroke="${color}" ${ring}/>
        <svg x="9" y="9" width="32" height="32" viewBox="${iconData.viewBox}">
            <path fill="${exists ? color : '#999'}" d="${iconData.path}"/>
        </svg>${orphanOverlay}${additiveOverlay}
    </svg>`;
    const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    nodeImageCache.set(key, url);
    return url;
}

/** Legend marker: a plain ring with a template, undefined or additive mark. */
function markerImageUrl(kind) {
    const color = '#9e9e9e';
    if (kind === 'template') {return getNodeImageUrl('', color, true, true, false);}
    if (kind === 'undefined') {return getNodeImageUrl('', color, false, false, false);}
    return getNodeImageUrl('', color, false, true, true);
}

function typeColor(type) {
    return state.meta.node_types[type]?.color || '#9e9e9e';
}

/** Dark text on light badge colours, white on dark ones. */
function badgeTextColor(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) {return '#fff';}
    const n = parseInt(m[1], 16);
    const lum = (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
    return lum > 0.6 ? '#1e1e1e' : '#fff';
}

function badgeStyle(type) {
    const color = typeColor(type);
    return `--nbe-type-color: ${escapeHtml(color)}; --nbe-type-text: ${badgeTextColor(color)}`;
}

function typeBadge(type) {
    return `<span class="dep-type-badge" style="${badgeStyle(type)}">${escapeHtml(type)}</span>`;
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function buildFilterControls() {
    document.getElementById('objectTypeFilters').innerHTML = state.allTypes.map(type => `
        <label class="type-filter-option" title="${escapeHtml(state.typeLabels[type] || type)}">
            <input type="checkbox" data-type="${escapeHtml(type)}" data-action="onTypeFilterChange">
            <span class="type-badge" style="${badgeStyle(type)}">${escapeHtml(state.meta.node_types[type].badge)}</span>
        </label>`).join('');

    document.getElementById('edgeCategoryFilters').innerHTML = state.allCategories.map(cat => {
        const meta = state.meta.edge_categories[cat];
        return `
        <label class="edge-filter-option" title="${escapeHtml(meta.description)}">
            <input type="checkbox" data-category="${escapeHtml(cat)}" data-action="onEdgeFilterChange">
            <span>${escapeHtml(meta.label)}</span>
        </label>`;
    }).join('');

    document.getElementById('nodeSearchType').innerHTML = '<option value="">All types</option>'
        + state.allTypes.map(type =>
            `<option value="${escapeHtml(type)}">${escapeHtml(state.typeLabels[type] || type)}</option>`).join('');
}

/** Categories that contain the given fields (what a quick view's edges amount to). */
function categoriesOfFields(fields) {
    const cats = new Set();
    for (const field of fields) {
        const meta = fieldMeta(field);
        if (meta.category) {cats.add(meta.category);}
        for (const cat of Object.values(meta.category_by_type || {})) {cats.add(cat);}
    }
    return cats;
}

/** Make the filter checkboxes, layout select and labels button show the state. */
function syncControls() {
    document.querySelectorAll('#objectTypeFilters input[type="checkbox"]').forEach(cb => {
        cb.checked = state.enabledTypes.has(cb.dataset.type);
    });
    const cats = state.edgeFilter.fields ? categoriesOfFields(state.edgeFilter.fields) : state.edgeFilter.categories;
    document.querySelectorAll('#edgeCategoryFilters input[type="checkbox"]').forEach(cb => {
        cb.checked = cats.has(cb.dataset.category);
    });
    const note = document.getElementById('edgeFilterNote');
    note.hidden = !state.edgeFilter.fields;
    document.getElementById('layoutType').value = state.layout;
    document.getElementById('toggleLabelsBtn').textContent =
        state.showEdgeLabels ? 'Hide Connection Labels' : 'Show Connection Labels';
}

function onEdgeFilterChange() {
    const categories = new Set();
    document.querySelectorAll('#edgeCategoryFilters input[type="checkbox"]').forEach(cb => {
        if (cb.checked) {categories.add(cb.dataset.category);}
    });
    state.edgeFilter = { fields: null, categories };
    document.getElementById('edgeFilterNote').hidden = true;
    leaveQuickView();
    changed();
}

function onTypeFilterChange() {
    const types = new Set();
    document.querySelectorAll('#objectTypeFilters input[type="checkbox"]').forEach(cb => {
        if (cb.checked) {types.add(cb.dataset.type);}
    });
    state.enabledTypes = types;
    leaveQuickView();
    changed();
}

function onLayoutChange() {
    state.layout = document.getElementById('layoutType').value;
    changed({ relayout: true });
}

function toggleEdgeLabels() {
    state.showEdgeLabels = !state.showEdgeLabels;
    syncControls();
    if (cy) {cy.style(getCytoscapeStyle());}
    saveState();
}

function fitGraph() {
    if (!cy) {return;}
    cy.fit(undefined, 50);
    limitFitZoom();
}

// --- Quick view buttons ----------------------------------------------------

function renderQuickViewButtons() {
    const container = document.getElementById('quickViewContainer');
    const focus = state.index?.byId.get(state.focusId) || state.index?.byId.get([...state.addedIds][0]);
    const presetIds = focus
        ? presetsForType(expansionRules, quickViewPresets, focus.type)
        : Object.keys(quickViewPresets).filter(p => p === 'inheritance' || quickViewPresets[p].smartExpansion);
    container.innerHTML = presetIds.map(id => {
        const preset = quickViewPresets[id];
        return `
            <button type="button" class="quick-view-btn ${id === state.activeQuickView ? 'active' : ''}"
                    data-action="applyQuickView" data-preset="${escapeHtml(id)}"
                    title="${escapeHtml(preset.description)}">
                <i class="fa-solid ${escapeHtml(preset.icon)}" aria-hidden="true"></i>
                <span>${escapeHtml(preset.label)}</span>
            </button>`;
    }).join('');
    const contextLabel = document.getElementById('quickViewContextLabel');
    contextLabel.textContent = focus ? `for ${focus.type}` : '';
    contextLabel.hidden = !focus;
}

function updateQuickViewButtons() {
    document.querySelectorAll('.quick-view-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.preset === state.activeQuickView);
    });
}

// --- Node list -------------------------------------------------------------

function updateNodeList() {
    const container = document.getElementById('addedNodesList');
    const total = state.addedIds.size;
    const shown = display.nodes.length;
    const count = document.getElementById('nodeCount');
    count.textContent = shown === total ? String(total) : `${shown} of ${total}`;
    count.title = shown === total ? `${total} nodes` : `${shown} of ${total} nodes shown; the rest are hidden by filters`;
    document.getElementById('clearGraphBtn').hidden = total <= 1;

    if (total === 0) {
        container.innerHTML = '<div class="dep-empty">No nodes added yet</div>';
        return;
    }
    const nodes = [...state.addedIds].map(id => state.index.byId.get(id)).filter(Boolean);
    nodes.sort((a, b) =>
        display.hidden.has(a.id) - display.hidden.has(b.id)
        || a.type.localeCompare(b.type)
        || a.label.localeCompare(b.label));
    container.innerHTML = nodes.map(node => {
        const id = escapeHtml(node.id);
        const orphan = node.exists === false;
        const hiddenReason = display.hidden.get(node.id);
        const classes = ['dep-node-item', orphan ? 'orphan' : '', hiddenReason ? 'is-hidden' : ''].join(' ');
        const title = hiddenReason ? `Not drawn: ${hiddenReason}` : 'Open in Explorer';
        return `
            <div class="${classes}" role="listitem" data-action="openInExplorer" data-node-id="${id}"
                 title="${escapeHtml(title)}">
                <span class="dep-node-item-main">
                    ${typeBadge(node.type)}
                    <span class="dep-node-label">${escapeHtml(node.label)}</span>
                    ${orphan ? '<span class="orphan-badge" title="Referenced but not defined">✗</span>' : ''}
                    ${hiddenReason ? '<span class="dep-hidden-tag">hidden</span>' : ''}
                </span>
                <button type="button" class="remove-btn" data-action="removeNode" data-node-id="${id}"
                        aria-label="Remove ${escapeHtml(node.label)} from graph">&times;</button>
            </div>`;
    }).join('');
}

// --- Legend ----------------------------------------------------------------

function updateLegend() {
    const content = document.getElementById('graphLegendContent');
    if (display.nodes.length === 0) {
        content.replaceChildren();
        return;
    }
    const legendItem = (image, text, title = '') =>
        `<div class="graph-legend-item"${title ? ` title="${escapeHtml(title)}"` : ''}>${image}<span>${escapeHtml(text)}</span></div>`;
    const img = url => `<img class="graph-legend-icon" src="${url}" alt="">`;

    const types = state.allTypes.filter(t => display.nodes.some(n => n.type === t));
    const objects = types.map(t => legendItem(img(getNodeImageUrl(t, typeColor(t))), t));

    const markers = [];
    if (display.nodes.some(n => n.is_template)) {markers.push(legendItem(img(markerImageUrl('template')), 'template (dashed ring)'));}
    if (display.nodes.some(n => n.exists === false)) {markers.push(legendItem(img(markerImageUrl('undefined')), 'referenced but not defined'));}
    if (display.nodes.some(n => n.additive)) {markers.push(legendItem(img(markerImageUrl('additive')), 'added with + (additive)'));}

    const connections = new Map();
    for (const edge of display.edges) {
        const meta = fieldMeta(edge.label);
        const label = meta.label || edge.label.replace(/_/g, ' ');
        const color = meta.color || '#999';
        const key = `${label}|${color}`;
        if (!connections.has(key)) {connections.set(key, { label, color, fields: new Set() });}
        connections.get(key).fields.add(edge.label);
    }
    const lines = [...connections.values()]
        .sort((a, b) => a.label.localeCompare(b.label))
        .map(c => legendItem(
            `<span class="graph-legend-line" style="--nbe-edge-color: ${escapeHtml(c.color)}"></span>`,
            c.label, [...c.fields].join(', ')));

    const group = (heading, items) => items.length
        ? `<div class="graph-legend-heading">${heading}</div><div class="graph-legend-grid">${items.join('')}</div>`
        : '';
    content.innerHTML = group('Objects', objects) + group('Markers', markers) + group('Connections', lines);
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

function onSearchInput() {
    clearTimeout(search.timer);
    search.timer = setTimeout(runSearch, 100);
}

function runSearch() {
    const input = document.getElementById('nodeSearchAdd');
    const query = input.value.trim();
    if (query.length < 2) {
        hideSearchResults();
        return;
    }
    const type = document.getElementById('nodeSearchType').value;
    const { results, total } = searchNodes(state.index.nodes, query, { type, limit: GRAPH_LIMITS.searchResults });
    search.results = results;
    search.total = total;
    search.active = results.length ? 0 : -1;
    renderSearchResults();
}

function renderSearchResults() {
    const container = document.getElementById('nodeSearchResults');
    const input = document.getElementById('nodeSearchAdd');
    if (search.results.length === 0) {
        container.innerHTML = '<div class="dep-search-item dep-empty" role="presentation">No matches found</div>';
    } else {
        container.innerHTML = search.results.map((node, i) => {
            const isAdded = state.addedIds.has(node.id);
            const orphan = node.exists === false;
            return `
                <div class="dep-search-item ${isAdded ? 'added' : ''} ${orphan ? 'orphan' : ''} ${i === search.active ? 'active' : ''}"
                     role="option" id="nodeSearchOption${i}" aria-selected="${i === search.active}"
                     data-action="addNode" data-node-id="${escapeHtml(node.id)}">
                    ${typeBadge(node.type)}
                    <span class="dep-search-label">${escapeHtml(node.label)}</span>
                    ${orphan ? '<span class="orphan-badge" title="Referenced but not defined">✗</span>' : ''}
                    ${isAdded ? '<span class="dep-search-added">(added)</span>' : ''}
                </div>`;
        }).join('');
        if (search.total > search.results.length) {
            container.insertAdjacentHTML('beforeend',
                `<div class="dep-search-more" role="presentation">Showing ${search.results.length} of ${search.total} matches. Type more or pick a type to narrow.</div>`);
        }
    }
    container.classList.add('visible');
    input.setAttribute('aria-expanded', 'true');
    if (search.active >= 0) {
        input.setAttribute('aria-activedescendant', `nodeSearchOption${search.active}`);
        document.getElementById(`nodeSearchOption${search.active}`)?.scrollIntoView({ block: 'nearest' });
    } else {
        input.removeAttribute('aria-activedescendant');
    }
}

function hideSearchResults() {
    const input = document.getElementById('nodeSearchAdd');
    document.getElementById('nodeSearchResults').classList.remove('visible');
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
}

function onSearchKeydown(e) {
    const open = document.getElementById('nodeSearchResults').classList.contains('visible');
    if (e.key === 'Escape') {
        hideSearchResults();
        return;
    }
    if (!open || search.results.length === 0) {
        if (e.key === 'ArrowDown') {runSearch();}
        return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const step = e.key === 'ArrowDown' ? 1 : -1;
        search.active = (search.active + step + search.results.length) % search.results.length;
        renderSearchResults();
    } else if (e.key === 'Enter') {
        e.preventDefault();
        const node = search.results[Math.max(0, search.active)];
        if (node) {
            addNode(node.id);
            runSearch();
        }
    }
}

// ---------------------------------------------------------------------------
// Context menu
// ---------------------------------------------------------------------------

function showContextMenu(event, nodeIds) {
    const menu = document.getElementById('graphContextMenu');
    const header = document.getElementById('contextMenuHeader');
    contextMenuNodeIds = nodeIds;
    hideTooltip();

    if (nodeIds.length === 1) {
        const node = state.index.byId.get(nodeIds[0]);
        header.textContent = node ? `${node.type}: ${node.label}` : 'Node';
    } else {
        header.textContent = `${nodeIds.length} nodes selected`;
    }
    for (const action of ['contextCenterOnNode', 'contextSetAsFocus', 'contextOpenInExplorer']) {
        const item = menu.querySelector(`[data-action="${action}"]`);
        if (item) {item.hidden = nodeIds.length !== 1;}
    }

    // Place at the pointer, then keep the whole menu inside the window.
    menu.style.left = '0px';
    menu.style.top = '0px';
    menu.classList.add('visible');
    const { width, height } = menu.getBoundingClientRect();
    const x = Math.min(event.clientX, window.innerWidth - width - 8);
    const y = Math.min(event.clientY, window.innerHeight - height - 8);
    menu.style.left = `${Math.max(8, x)}px`;
    menu.style.top = `${Math.max(8, y)}px`;
}

function hideContextMenu() {
    document.getElementById('graphContextMenu').classList.remove('visible');
}

function contextExpandConnections() {
    hideContextMenu();
    if (contextMenuNodeIds.length === 0) {return;}
    const next = new Set(state.addedIds);
    for (const id of contextMenuNodeIds) {expandEffective(state.index, id, next);}
    const added = next.size - state.addedIds.size;
    if (added === 0) {
        showToast('No new connections to add', 'info');
        return;
    }
    state.addedIds = next;
    state.focusId = contextMenuNodeIds[0];
    leaveQuickView();
    renderQuickViewButtons();
    changed({ relayout: true });
    showToast(`Added ${added} connected node(s)`, 'success');
}

function contextShowOnlyConnections() {
    hideContextMenu();
    if (contextMenuNodeIds.length === 0) {return;}
    const keep = new Set(contextMenuNodeIds);
    for (const id of contextMenuNodeIds) {
        for (const e of edgesFrom(state.index, id)) {keep.add(e.to);}
        for (const e of edgesTo(state.index, id)) {keep.add(e.from);}
    }
    state.addedIds = new Set([...state.addedIds].filter(id => keep.has(id)));
    state.manualIds = new Set([...state.manualIds].filter(id => keep.has(id)));
    leaveQuickView();
    changed();
    showToast(`Showing ${state.addedIds.size} connected node(s)`, 'info');
}

function contextCenterOnNode() {
    hideContextMenu();
    const node = cy?.getElementById(contextMenuNodeIds[0]);
    if (node?.nonempty()) {
        cy.animate({ center: { eles: node }, zoom: 1.5, duration: 400 });
    }
}

function contextSetAsFocus() {
    hideContextMenu();
    const id = contextMenuNodeIds[0];
    const node = state.index.byId.get(id);
    if (!node) {return;}
    state.focusId = id;
    leaveQuickView();
    renderQuickViewButtons();
    changed({ relayout: true });
    showToast(`"${node.label}" is now the focus node`, 'success');
}

function contextRemoveNode() {
    hideContextMenu();
    const ids = contextMenuNodeIds.length ? contextMenuNodeIds : selectedNodeIds();
    if (ids.length === 0) {return;}
    removeNodes(ids);
    showToast(`Removed ${ids.length} node(s) from graph`, 'success');
}

function contextRemoveDisconnected() {
    hideContextMenu();
    const connected = new Set();
    for (const id of state.addedIds) {
        for (const e of edgesFrom(state.index, id)) {
            if (state.addedIds.has(e.to)) {
                connected.add(e.from);
                connected.add(e.to);
            }
        }
    }
    const removed = [...state.addedIds].filter(id => !connected.has(id));
    if (removed.length === 0) {
        showToast('No disconnected nodes found', 'info');
        return;
    }
    removeNodes(removed);
    showToast(`Removed ${removed.length} disconnected node(s)`, 'success');
}

function contextOpenInExplorer() {
    hideContextMenu();
    openInExplorer(contextMenuNodeIds[0]);
}

function selectedNodeIds() {
    return cy ? cy.$('node:selected').map(n => n.id()) : [];
}

function openInExplorer(nodeId) {
    const node = state.index.byId.get(nodeId);
    if (!node) {return;}
    if (node.exists === false) {
        showToast(`"${node.label}" is not defined in any config file`, 'warning');
        return;
    }
    // The stable key identifies the exact object (two services can share a description).
    const params = node.stable_key
        ? new URLSearchParams({ key: node.stable_key })
        : new URLSearchParams({ search: node.label, type: node.type });
    window.location.href = apiUrl(`/explorer?${params}`);
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

const clickActions = {
    fitGraph,
    clearGraph,
    toggleEdgeLabels,
    retryLoad: () => start(),
    applyQuickView: el => applyQuickView(el.dataset.preset),
    addNode: el => {
        addNode(el.dataset.nodeId);
        runSearch();
    },
    removeNode: el => removeNodes([el.dataset.nodeId]),
    openInExplorer: el => openInExplorer(el.dataset.nodeId),
    contextExpandConnections,
    contextShowOnlyConnections,
    contextCenterOnNode,
    contextSetAsFocus,
    contextRemoveNode,
    contextRemoveDisconnected,
    contextOpenInExplorer
};

const changeActions = {
    onLayoutChange,
    onEdgeFilterChange,
    onTypeFilterChange,
    onSearchTypeChange: runSearch
};

function bindEvents() {
    document.addEventListener('click', e => {
        if (!e.target.closest('#nodeSearchAdd, #nodeSearchResults')) {hideSearchResults();}
        if (!e.target.closest('.graph-context-menu')) {hideContextMenu();}
        const el = e.target.closest('[data-action]');
        const handler = el && clickActions[el.dataset.action];
        if (handler) {handler(el);}
    });
    document.addEventListener('change', e => {
        const el = e.target.closest('[data-action]');
        const handler = el && changeActions[el.dataset.action];
        if (handler) {handler(el);}
    });

    const searchInput = document.getElementById('nodeSearchAdd');
    searchInput.addEventListener('input', onSearchInput);
    searchInput.addEventListener('keydown', onSearchKeydown);
    searchInput.addEventListener('focus', () => {
        if (searchInput.value.trim().length >= 2) {runSearch();}
    });

    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            hideContextMenu();
            return;
        }
        if (e.key !== 'Delete' && e.key !== 'Backspace') {return;}
        if (e.ctrlKey || e.metaKey || e.altKey) {return;}
        // Only when the graph (or nothing in particular) has focus: never while
        // typing, choosing from a select, or on a focused button.
        const target = e.target;
        if (target !== document.body && !target.closest?.('#graphContainer')) {return;}
        const ids = selectedNodeIds();
        if (ids.length === 0) {return;}
        e.preventDefault();
        removeNodes(ids);
        showToast(`Removed ${ids.length} node(s) from graph`, 'success');
    });

    window.addEventListener('resize', hideContextMenu);
}
