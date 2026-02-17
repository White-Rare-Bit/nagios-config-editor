/**
 * Nagios Bulk Editor - Dependencies Graph Visualization
 *
 * Cytoscape.js network graph for exploring Nagios object relationships.
 */

console.log('dependencies.js loaded');

(function() {
    try {
    console.log('dependencies.js IIFE started');

    // Import configuration from dependencies-config.js
    const {
        LAYOUT_CONFIG,
        edgeCategories,
        viewModePresets,
        quickViewPresets,
        expansionRules,
        typeColors,
        typeIconSvg,
        defaultIconSvg,
        edgeLabelMap,
        edgeColors
    } = window.DepsConfig;

    let cy = null;  // Cytoscape instance
    let allNodes = [];
    let allEdges = [];
    let addedNodeIds = new Set();
    let searchTimeout = null;
    let showEdgeLabels = true;
    let selectedNodeId = null;
    let focusNodeId = null;  // The central node for organized layouts

    const MAX_NODES = Infinity;  // No limit on nodes in graph

    // Map object types to relevant quick view presets
    // Each type shows only the presets that make sense for that object
    const presetsByType = {
        host: ['inheritance', 'network', 'notifications', 'services', 'monitoring', 'escalations', 'dependencies', 'full'],
        hostgroup: ['inheritance', 'notifications', 'services', 'members', 'escalations', 'dependencies', 'full'],
        service: ['inheritance', 'network', 'notifications', 'monitoring', 'escalations', 'dependencies', 'full'],
        servicegroup: ['inheritance', 'network', 'notifications', 'members', 'escalations', 'dependencies', 'full'],
        contact: ['inheritance', 'notifiedBy', 'full'],
        contactgroup: ['inheritance', 'members', 'notifiedBy', 'full'],
        command: ['usedBy', 'full'],
        timeperiod: ['usedBy', 'full'],
        // Dependency/escalation types
        hostdependency: ['inheritance', 'network', 'monitoring', 'full'],
        servicedependency: ['inheritance', 'network', 'monitoring', 'full'],
        hostescalation: ['inheritance', 'notifications', 'network', 'full'],
        serviceescalation: ['inheritance', 'notifications', 'network', 'full'],
        // Default for unknown types
        default: ['inheritance', 'full']
    };

    // Currently active quick view preset (null = custom)
    let activeQuickView = null;

    // Currently enabled edge categories
    let enabledCategories = new Set(['dependencies', 'templates', 'groups']);

    // All available object types for filtering
    const allObjectTypes = [
        'host', 'hostgroup', 'service', 'servicegroup',
        'contact', 'contactgroup', 'command', 'timeperiod',
        'hostdependency', 'servicedependency', 'hostescalation', 'serviceescalation'
    ];

    // Currently enabled object types (all enabled by default)
    let enabledTypes = new Set(allObjectTypes);

    // Map quick view presets to relevant object types
    // When a quick view is applied, only these types are shown
    const typesByPreset = {
        inheritance: null,  // null = all types (templates can be any type)
        network: ['host', 'hostgroup', 'service', 'servicegroup', 'hostdependency', 'servicedependency', 'hostescalation', 'serviceescalation'],
        notifications: ['host', 'hostgroup', 'service', 'servicegroup', 'contact', 'contactgroup', 'hostescalation', 'serviceescalation'],
        services: ['host', 'hostgroup', 'service'],
        members: null,  // depends on starting type - show all
        notifiedBy: ['host', 'hostgroup', 'service', 'servicegroup', 'contact', 'contactgroup'],
        usedBy: ['host', 'service', 'contact', 'command', 'timeperiod'],
        monitoring: ['host', 'service', 'command', 'timeperiod', 'hostdependency', 'servicedependency'],
        escalations: ['host', 'hostgroup', 'service', 'servicegroup', 'contact', 'contactgroup', 'hostescalation', 'serviceescalation'],
        dependencies: ['host', 'hostgroup', 'service', 'servicegroup', 'hostdependency', 'servicedependency'],
        full: null  // null = all types
    };

    // Generate SVG data URL with white background circle
    // Templates get a dashed border and unique icons to distinguish them from regular objects
    function getNodeImageUrl(type, color, isTemplate = false, exists = true) {
        // Use template-specific icons for host and service templates
        let iconType = type;
        if (isTemplate && (type === 'host' || type === 'service')) {
            iconType = type + '_template';
        }
        const iconData = typeIconSvg[iconType] || typeIconSvg[type] || defaultIconSvg;
        const strokeDasharray = isTemplate ? 'stroke-dasharray="4,2"' : '';
        const strokeWidth = isTemplate ? '3' : '2';

        // X overlay for orphan nodes (referenced but not defined)
        const orphanOverlay = !exists ? `
            <line x1="10" y1="10" x2="40" y2="40" stroke="#f14c4c" stroke-width="4" stroke-linecap="round"/>
            <line x1="40" y1="10" x2="10" y2="40" stroke="#f14c4c" stroke-width="4" stroke-linecap="round"/>
        ` : '';

        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 50 50">
            <circle cx="25" cy="25" r="23" fill="white" stroke="${color}" stroke-width="${strokeWidth}" ${strokeDasharray}/>
            <svg x="9" y="9" width="32" height="32" viewBox="${iconData.viewBox}">
                <path fill="${exists ? color : '#999'}" d="${iconData.path}"/>
            </svg>
            ${orphanOverlay}
        </svg>`;
        return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    }

    // Cache generated images to avoid regenerating
    const nodeImageCache = {};

    function formatEdgeLabel(fieldName) {
        return edgeLabelMap[fieldName] || fieldName.replace(/_/g, ' ');
    }

    function getEdgeColor(fieldName) {
        return edgeColors[fieldName] || '#999';
    }

    // Edge traversal utilities - consolidated patterns for filtering edges by node set
    /**
     * Get all edges where both source and target are in the given node set
     * @param {Set} nodeIdSet - Set of node IDs to filter by
     * @returns {Array} Filtered edges
     */
    function getEdgesInSubgraph(nodeIdSet) {
        return allEdges.filter(e => nodeIdSet.has(e.from) && nodeIdSet.has(e.to));
    }

    /**
     * Get all node IDs connected via the given edges
     * @param {Array} edges - Array of edges
     * @returns {Set} Set of node IDs
     */
    function getConnectedNodeIdsFromEdges(edges) {
        const nodeIds = new Set();
        for (const edge of edges) {
            nodeIds.add(edge.from);
            nodeIds.add(edge.to);
        }
        return nodeIds;
    }

    document.addEventListener('DOMContentLoaded', async () => {
        await loadAllData();

        // Check for URL parameters to initialize graph with a specific node
        const urlParams = new URLSearchParams(window.location.search);
        const focusNode = urlParams.get('node');  // Format: "type:name"
        const expandAll = urlParams.get('expand') === 'true';

        console.log('Graph init - focusNode:', focusNode, 'allNodes:', allNodes.length, 'expand:', expandAll);
        if (focusNode) {
            const foundNode = allNodes.find(n => n.id === focusNode);
            console.log('Looking for node:', focusNode, 'found:', foundNode ? 'yes' : 'no');
            if (!foundNode && allNodes.length > 0) {
                console.log('Available node IDs (first 10):', allNodes.slice(0, 10).map(n => n.id));
            }
        }

        if (focusNode && allNodes.find(n => n.id === focusNode)) {
            // Clear any saved state and start fresh with this node
            addedNodeIds.clear();
            addedNodeIds.add(focusNode);
            focusNodeId = focusNode;  // Set this as the central focus node

            // Clear URL params to avoid re-triggering on refresh
            window.history.replaceState({}, '', window.location.pathname);

            // Apply the full graph quick view (sets filters, expands, updates graph)
            applyQuickView('full');
        } else {
            loadGraphState();  // Restore previous session state

            // Ensure checkboxes match the enabled categories (handles both fresh load and restored state)
            syncCheckboxesToCategories();

            updateGraph();
            updateAddedNodesList();
            saveGraphState();  // Save state so refresh preserves it
        }

        // Render context-sensitive quick view buttons based on focus node type
        renderQuickViewButtons();

        // Add hint for keyboard shortcuts
        const graphContainer = document.querySelector('.dep-graph');
        const hint = document.createElement('div');
        hint.className = 'graph-hint';
        hint.innerHTML = '<strong>Right-click</strong> node actions · <strong>Shift+Drag</strong> box select · <strong>Delete</strong> remove selected';
        graphContainer.appendChild(hint);

        // Keyboard handling
        document.addEventListener('keydown', (e) => {
            // Delete key removes selected nodes
            if ((e.key === 'Delete' || e.key === 'Backspace') && !e.target.closest('input, textarea')) {
                e.preventDefault();
                removeSelectedNodes();
            }
        });

        // If we focused on a node, center on it
        if (focusNode && addedNodeIds.has(focusNode)) {
            setTimeout(() => {
                if (cy) {
                    const node = cy.$id(focusNode);
                    if (node.length) {
                        cy.center(node);
                        cy.zoom({ level: 1, position: node.position() });
                        node.select();
                    }
                }
            }, 300);
        }

        // Event delegation for data-action attributes
        document.addEventListener('input', function(e) {
            const actionEl = e.target.closest('[data-action]');
            if (!actionEl) {return;}

            const action = actionEl.dataset.action;
            if (action === 'onNodeSearchInput') {
                onNodeSearchInput();
            }
        });

        document.addEventListener('change', function(e) {
            const actionEl = e.target.closest('[data-action]');
            if (!actionEl) {return;}

            const action = actionEl.dataset.action;
            switch (action) {
                case 'onNodeSearchInput':
                    onNodeSearchInput();
                    break;
                case 'applyLayout':
                    applyLayout();
                    break;
                case 'onEdgeFilterChange':
                    onEdgeFilterChange();
                    break;
                case 'onTypeFilterChange':
                    onTypeFilterChange();
                    break;
            }
        });

        // Click handler for buttons and context menu
        document.addEventListener('click', function(e) {
            const actionEl = e.target.closest('[data-action]');
            if (!actionEl) {return;}

            const action = actionEl.dataset.action;
            switch (action) {
                // Sidebar buttons
                case 'fitGraph':
                    fitGraph();
                    break;
                case 'clearGraph':
                    clearGraph();
                    break;
                case 'toggleEdgeLabels':
                    toggleEdgeLabels();
                    break;
                case 'applyQuickView':
                    applyQuickView(actionEl.dataset.preset);
                    break;
                // Context menu items
                case 'contextExpandConnections':
                    contextExpandConnections();
                    break;
                case 'contextShowOnlyConnections':
                    contextShowOnlyConnections();
                    break;
                case 'contextCenterOnNode':
                    contextCenterOnNode();
                    break;
                case 'contextSetAsFocus':
                    contextSetAsFocus();
                    break;
                case 'contextRemoveNode':
                    contextRemoveNode();
                    break;
                case 'contextRemoveDisconnected':
                    contextRemoveDisconnected();
                    break;
                case 'contextOpenInExplorer':
                    contextOpenInExplorer();
                    break;
            }
        });
    });

    // Add the "effective configuration" for an object - what Nagios will apply to it
    // This is directional: for a host, show services/commands/contacts that apply TO it,
    // but don't show other hosts using the same template or command.
    function addAllConnectedRecursively(startNodeId, visited = new Set()) {
        if (visited.has(startNodeId)) {return;}
        visited.add(startNodeId);

        const maxNodes = MAX_NODES;
        const [startType, startName] = parseNodeId(startNodeId);

        // Helper to add a node if not at max
        function collectNode(nodeId) {
            if (addedNodeIds.size >= maxNodes || addedNodeIds.has(nodeId)) {return false;}
            addedNodeIds.add(nodeId);
            return true;
        }

        // Helper to find edges by criteria
        function findEdges(fromId, toId, label) {
            return allEdges.filter(e =>
                (fromId === null || e.from === fromId) &&
                (toId === null || e.to === toId) &&
                (label === null || e.label === label)
            );
        }

        // Add templates (follow 'use' chain) - templates point TO the object using them
        function addTemplates(nodeId) {
            const templateEdges = findEdges(null, nodeId, 'use');
            for (const edge of templateEdges) {
                if (collectNode(edge.from)) {
                    addTemplates(edge.from);  // Follow template inheritance chain
                }
            }
        }

        // Add commands, contacts, timeperiods for an object
        function addObjectDependencies(nodeId) {
            // These edges point FROM the object TO the referenced objects
            // e.g., service → command, service → contact, service → timeperiod
            const depLabels = ['check_command', 'event_handler', 'check_period',
                              'notification_period', 'contacts', 'contact_groups'];
            for (const label of depLabels) {
                const edges = findEdges(nodeId, null, label);
                for (const edge of edges) {
                    if (collectNode(edge.to)) {
                        // If we added a contactgroup, also add its members (contacts)
                        if (label === 'contact_groups') {
                            const memberEdges = findEdges(edge.to, null, 'members');
                            for (const memberEdge of memberEdges) {
                                collectNode(memberEdge.to);
                            }
                        }
                    }
                }
            }
        }

        // Add hostgroups that a host belongs to
        function addHostgroups(hostId) {
            // Host points TO hostgroups
            const hgEdges = findEdges(hostId, null, 'hostgroups');
            for (const edge of hgEdges) {
                collectNode(edge.to);
            }
        }

        // Find services that apply to a host (directly or via hostgroup)
        function addServicesForHost(hostId, hostName, hostgroupIds) {
            // Services directly targeting this host (host points TO service via host_name)
            const directEdges = findEdges(hostId, null, 'host_name');
            for (const edge of directEdges) {
                if (collectNode(edge.to)) {
                    // Add this service's dependencies (commands, contacts, etc.)
                    addTemplates(edge.to);
                    addObjectDependencies(edge.to);
                }
            }

            // Services targeting hostgroups this host is in
            // Services point TO hostgroups via hostgroup_name
            for (const hgId of hostgroupIds) {
                const hgServiceEdges = findEdges(null, hgId, 'hostgroup_name');
                for (const edge of hgServiceEdges) {
                    if (collectNode(edge.from)) {
                        addTemplates(edge.from);
                        addObjectDependencies(edge.from);
                    }
                }
            }
        }

        // Main logic based on object type
        if (startType === 'host') {
            // For a host: templates, hostgroups, services, and their dependencies
            addTemplates(startNodeId);
            addObjectDependencies(startNodeId);

            // Get hostgroups - host points TO hostgroups
            const hostgroupIds = [];
            const hgEdges = findEdges(startNodeId, null, 'hostgroups');
            for (const edge of hgEdges) {
                if (collectNode(edge.to)) {
                    hostgroupIds.push(edge.to);
                }
            }
            // Also check 'in-group' label
            const igEdges = findEdges(startNodeId, null, 'in-group');
            for (const edge of igEdges) {
                const node = allNodes.find(n => n.id === edge.to);
                if (node && node.type === 'hostgroup') {
                    if (collectNode(edge.to)) {
                        hostgroupIds.push(edge.to);
                    }
                }
            }

            // Add services - host points TO services via host_name (reversed)
            const serviceEdges = findEdges(startNodeId, null, 'host_name');
            for (const edge of serviceEdges) {
                if (collectNode(edge.to)) {
                    // Also add the service's dependencies (commands, contacts, timeperiods)
                    addObjectDependencies(edge.to);
                }
            }

            // Add services for hostgroups this host belongs to
            addServicesForHost(startNodeId, startName, hostgroupIds);

            // Add parent hosts (this host points TO parents)
            const parentEdges = findEdges(startNodeId, null, 'parents');
            for (const edge of parentEdges) {
                collectNode(edge.to);
            }

            // Add child hosts (other hosts point TO this host as parent)
            for (const edge of allEdges) {
                if (edge.to === startNodeId && edge.label === 'parents') {
                    collectNode(edge.from);
                }
            }

            // Add hostdependencies that reference this host
            // - as master (host_name): this host is pointed TO by the dependency
            // - as dependent (dependent_host_name): this host is pointed TO by the dependency
            for (const edge of allEdges) {
                const node = allNodes.find(n => n.id === edge.from);
                if (node && node.type === 'hostdependency') {
                    if (edge.to === startNodeId &&
                        (edge.label === 'host_name' || edge.label === 'dependent_host_name')) {
                        collectNode(edge.from);
                    }
                }
            }

            // Add hostescalations that apply to this host
            for (const edge of allEdges) {
                const node = allNodes.find(n => n.id === edge.from);
                if (node && node.type === 'hostescalation') {
                    if (edge.to === startNodeId && edge.label === 'host_name') {
                        collectNode(edge.from);
                    }
                }
            }

        } else if (startType === 'service') {
            // For a service: templates, host, commands, contacts, timeperiods
            addTemplates(startNodeId);
            addObjectDependencies(startNodeId);

            // Add the host this service runs on (host points TO service)
            const hostEdges = findEdges(null, startNodeId, 'host_name');
            for (const edge of hostEdges) {
                collectNode(edge.from);  // Just add host, don't expand it
            }

            // Add hostgroup if service targets a hostgroup (service points TO hostgroup)
            const hgEdges = findEdges(startNodeId, null, 'hostgroup_name');
            for (const edge of hgEdges) {
                collectNode(edge.to);
            }

            // Add servicegroups this service belongs to (service points TO servicegroup)
            const sgEdges = findEdges(startNodeId, null, 'servicegroups');
            for (const edge of sgEdges) {
                collectNode(edge.to);
            }

            // Add servicedependencies that reference this service
            // - as master (service_description): this service points TO the dependency
            // - as dependent (dependent_service_description): this service points TO the dependency
            for (const edge of allEdges) {
                const node = allNodes.find(n => n.id === edge.from);
                if (node && node.type === 'servicedependency') {
                    if (edge.to === startNodeId &&
                        (edge.label === 'service_description' || edge.label === 'dependent_service_description')) {
                        collectNode(edge.from);
                    }
                }
            }

            // Add serviceescalations that apply to this service
            for (const edge of allEdges) {
                const node = allNodes.find(n => n.id === edge.from);
                if (node && node.type === 'serviceescalation') {
                    if (edge.to === startNodeId && edge.label === 'service_description') {
                        collectNode(edge.from);
                    }
                }
            }

        } else if (startType === 'hostgroup') {
            // For a hostgroup: members (hosts) and services targeting this group
            addTemplates(startNodeId);

            // Members - hostgroup points TO hosts via 'members'
            const memberEdges = findEdges(startNodeId, null, 'members');
            for (const edge of memberEdges) {
                collectNode(edge.to);
            }

            // Services targeting this hostgroup (services point TO hostgroup)
            const serviceEdges = findEdges(null, startNodeId, 'hostgroup_name');
            for (const edge of serviceEdges) {
                if (collectNode(edge.from)) {
                    addTemplates(edge.from);
                    addObjectDependencies(edge.from);
                }
            }

        } else if (startType === 'servicegroup') {
            addTemplates(startNodeId);
            // Members
            const memberEdges = findEdges(startNodeId, null, 'members');
            for (const edge of memberEdges) {
                collectNode(edge.to);
            }

        } else if (startType === 'contact') {
            addTemplates(startNodeId);
            addObjectDependencies(startNodeId);
            // Contact groups this contact is in
            const cgEdges = findEdges(null, startNodeId, 'members');
            for (const edge of cgEdges) {
                collectNode(edge.from);
            }

        } else if (startType === 'contactgroup') {
            addTemplates(startNodeId);
            // Members
            const memberEdges = findEdges(startNodeId, null, 'members');
            for (const edge of memberEdges) {
                collectNode(edge.to);
            }

        } else if (startType === 'servicedependency') {
            // Service dependencies link master service to dependent service
            // host_name is reversed (FROM host TO this), others are normal (FROM this TO target)
            const reversedLabels = ['host_name', 'dependent_host_name'];
            const normalLabels = ['hostgroup_name', 'service_description',
                                  'dependent_hostgroup_name', 'dependent_service_description'];

            for (const label of reversedLabels) {
                const edges = findEdges(null, startNodeId, label);
                for (const edge of edges) { collectNode(edge.from); }
            }
            for (const label of normalLabels) {
                const edges = findEdges(startNodeId, null, label);
                for (const edge of edges) { collectNode(edge.to); }
            }

        } else if (startType === 'hostdependency') {
            // Host dependencies link master host to dependent host
            const reversedLabels = ['host_name', 'dependent_host_name'];
            const normalLabels = ['hostgroup_name', 'dependent_hostgroup_name'];

            for (const label of reversedLabels) {
                const edges = findEdges(null, startNodeId, label);
                for (const edge of edges) { collectNode(edge.from); }
            }
            for (const label of normalLabels) {
                const edges = findEdges(startNodeId, null, label);
                for (const edge of edges) { collectNode(edge.to); }
            }

        } else if (startType === 'serviceescalation') {
            // Service escalations link services to contact groups
            // host_name is reversed, others are normal
            const reversedLabels = ['host_name'];
            const normalLabels = ['hostgroup_name', 'service_description', 'contact_groups', 'escalation_period'];

            for (const label of reversedLabels) {
                const edges = findEdges(null, startNodeId, label);
                for (const edge of edges) { collectNode(edge.from); }
            }
            for (const label of normalLabels) {
                const edges = findEdges(startNodeId, null, label);
                for (const edge of edges) {
                    if (collectNode(edge.to)) {
                        if (label === 'contact_groups') {
                            const memberEdges = findEdges(edge.to, null, 'members');
                            for (const memberEdge of memberEdges) {
                                collectNode(memberEdge.to);
                            }
                        }
                    }
                }
            }

        } else if (startType === 'hostescalation') {
            // Host escalations link hosts to contact groups
            const reversedLabels = ['host_name'];
            const normalLabels = ['hostgroup_name', 'contact_groups', 'escalation_period'];

            for (const label of reversedLabels) {
                const edges = findEdges(null, startNodeId, label);
                for (const edge of edges) { collectNode(edge.from); }
            }
            for (const label of normalLabels) {
                const edges = findEdges(startNodeId, null, label);
                for (const edge of edges) {
                    if (collectNode(edge.to)) {
                        if (label === 'contact_groups') {
                            const memberEdges = findEdges(edge.to, null, 'members');
                            for (const memberEdge of memberEdges) {
                                collectNode(memberEdge.to);
                            }
                        }
                    }
                }
            }

        } else if (startType === 'command') {
            // Commands are referenced BY other objects (hosts, services, contacts)
            // Find all edges where this command is the target
            addTemplates(startNodeId);

            // Find objects that USE this command (edge labels are raw field names)
            const commandFields = ['check_command', 'event_handler', 'host_notification_commands', 'service_notification_commands'];
            for (const edge of allEdges) {
                if (edge.to === startNodeId && commandFields.includes(edge.label)) {
                    collectNode(edge.from);
                }
            }

        } else if (startType === 'timeperiod') {
            // Timeperiods are referenced BY other objects (hosts, services, contacts)
            addTemplates(startNodeId);

            // Find objects that USE this timeperiod (edge labels are raw field names)
            const timeperiodFields = ['check_period', 'notification_period', 'host_notification_period', 'service_notification_period', 'escalation_period'];
            for (const edge of allEdges) {
                if (edge.to === startNodeId && timeperiodFields.includes(edge.label)) {
                    collectNode(edge.from);
                }
            }

        } else {
            // Generic fallback: just add templates
            addTemplates(startNodeId);
            addObjectDependencies(startNodeId);
        }
    }

    // Parse node ID into [type, name]
    // Service IDs may have format "service:target:name" for disambiguation
    function parseNodeId(nodeId) {
        const colonIndex = nodeId.indexOf(':');
        if (colonIndex === -1) {return [nodeId, ''];}
        const type = nodeId.substring(0, colonIndex);
        const rest = nodeId.substring(colonIndex + 1);
        // For services with target prefix, get the actual service name (last part)
        if (type === 'service' && rest.includes(':')) {
            const lastColon = rest.lastIndexOf(':');
            return [type, rest.substring(lastColon + 1)];
        }
        return [type, rest];
    }

    // ========================================
    // Tree Layout Algorithm
    // ========================================

    // Calculate positions using a proper tree structure where children are positioned under their parent
    function calculateOrganizedPositions(nodes, edges, centerNodeId, layoutType = 'static') {
        const positions = {};
        if (!centerNodeId || nodes.length === 0) {return positions;}

        // Build node lookup and adjacency
        const nodeMap = {};
        for (const node of nodes) {
            nodeMap[node.id] = node;
        }

        const adjacency = {};
        for (const node of nodes) {
            adjacency[node.id] = new Set();
        }
        for (const edge of edges) {
            if (adjacency[edge.from]) {adjacency[edge.from].add(edge.to);}
            if (adjacency[edge.to]) {adjacency[edge.to].add(edge.from);}
        }

        // Build tree structure using BFS - each node gets exactly one parent
        const children = {};   // nodeId -> [childIds]
        const parent = {};     // nodeId -> parentId
        const depth = {};      // nodeId -> depth in tree

        for (const node of nodes) {
            children[node.id] = [];
            parent[node.id] = null;
            depth[node.id] = -1;
        }

        // BFS to build tree
        const visited = new Set();
        if (adjacency[centerNodeId]) {
            visited.add(centerNodeId);
            depth[centerNodeId] = 0;
            const queue = [centerNodeId];

            while (queue.length > 0) {
                const nodeId = queue.shift();
                const neighbors = Array.from(adjacency[nodeId] || []);

                // Sort neighbors by type then name for consistent ordering
                const typeOrder = ['hostgroup', 'host', 'servicegroup', 'service', 'contactgroup', 'contact', 'command', 'timeperiod'];
                neighbors.sort((a, b) => {
                    const nodeA = nodeMap[a];
                    const nodeB = nodeMap[b];
                    if (!nodeA || !nodeB) {return 0;}
                    const orderA = typeOrder.indexOf(nodeA.type);
                    const orderB = typeOrder.indexOf(nodeB.type);
                    if (orderA !== orderB) {return orderA - orderB;}
                    return (nodeA.label || '').localeCompare(nodeB.label || '');
                });

                for (const neighborId of neighbors) {
                    if (!visited.has(neighborId)) {
                        visited.add(neighborId);
                        parent[neighborId] = nodeId;
                        children[nodeId].push(neighborId);
                        depth[neighborId] = depth[nodeId] + 1;
                        queue.push(neighborId);
                    }
                }
            }
        }

        // Handle disconnected nodes - place them at the end
        const disconnected = [];
        for (const node of nodes) {
            if (!visited.has(node.id)) {
                disconnected.push(node.id);
                depth[node.id] = 999;  // Far depth
            }
        }

        // Calculate subtree widths (how much space each subtree needs)
        const subtreeWidth = {};
        const { nodeWidth } = LAYOUT_CONFIG;

        function calcSubtreeWidth(nodeId) {
            const childIds = children[nodeId];
            if (childIds.length === 0) {
                subtreeWidth[nodeId] = nodeWidth;
                return nodeWidth;
            }

            let total = 0;
            for (const childId of childIds) {
                total += calcSubtreeWidth(childId);
            }
            subtreeWidth[nodeId] = Math.max(nodeWidth, total);
            return subtreeWidth[nodeId];
        }

        if (adjacency[centerNodeId]) {
            calcSubtreeWidth(centerNodeId);
        }

        // Position nodes based on layout type
        const tierSpacing = layoutType === 'hierarchicalLR'
            ? LAYOUT_CONFIG.tierSpacingHorizontal
            : LAYOUT_CONFIG.tierSpacingVertical;

        if (layoutType === 'hierarchical') {
            // Top-down tree layout
            function positionVertical(nodeId, xCenter, y) {
                positions[nodeId] = { x: xCenter, y: y };

                const childIds = children[nodeId];
                if (childIds.length === 0) {return;}

                // Calculate total width of children
                let totalChildWidth = 0;
                for (const childId of childIds) {
                    totalChildWidth += subtreeWidth[childId];
                }

                // Position children centered under this node
                let childX = xCenter - totalChildWidth / 2;
                const childY = y + tierSpacing;

                for (const childId of childIds) {
                    const childWidth = subtreeWidth[childId];
                    const childCenterX = childX + childWidth / 2;
                    positionVertical(childId, childCenterX, childY);
                    childX += childWidth;
                }
            }

            if (adjacency[centerNodeId]) {
                positionVertical(centerNodeId, 0, 0);
            }

            // Position disconnected nodes at the bottom
            if (disconnected.length > 0) {
                const maxDepth = Math.max(...Object.values(depth).filter(d => d < 999));
                const disconnectedY = (maxDepth + 2) * tierSpacing;
                const totalWidth = disconnected.length * nodeWidth;
                let x = -totalWidth / 2;
                for (const nodeId of disconnected) {
                    positions[nodeId] = { x: x + nodeWidth / 2, y: disconnectedY };
                    x += nodeWidth;
                }
            }

        } else if (layoutType === 'hierarchicalLR') {
            // Left-to-right tree layout
            function positionHorizontal(nodeId, x, yCenter) {
                positions[nodeId] = { x: x, y: yCenter };

                const childIds = children[nodeId];
                if (childIds.length === 0) {return;}

                // Calculate total height of children
                let totalChildHeight = 0;
                for (const childId of childIds) {
                    totalChildHeight += subtreeWidth[childId];  // reuse width as height for LR
                }

                // Position children centered beside this node
                let childY = yCenter - totalChildHeight / 2;
                const childX = x + tierSpacing;

                for (const childId of childIds) {
                    const childHeight = subtreeWidth[childId];
                    const childCenterY = childY + childHeight / 2;
                    positionHorizontal(childId, childX, childCenterY);
                    childY += childHeight;
                }
            }

            if (adjacency[centerNodeId]) {
                positionHorizontal(centerNodeId, 0, 0);
            }

            // Position disconnected nodes at the right
            if (disconnected.length > 0) {
                const maxDepth = Math.max(...Object.values(depth).filter(d => d < 999));
                const disconnectedX = (maxDepth + 2) * tierSpacing;
                const totalHeight = disconnected.length * nodeWidth;
                let y = -totalHeight / 2;
                for (const nodeId of disconnected) {
                    positions[nodeId] = { x: disconnectedX, y: y + nodeWidth / 2 };
                    y += nodeWidth;
                }
            }

        } else {
            // Static layout - Satellite clusters
            // Each object type forms its own cluster orbiting the focus node

            // Define cluster types - each type gets its own cluster at a specific angle
            // Commands and timeperiods will orbit around services instead of being separate
            // Notification-centric layout:
            // contactgroups (center) -> contacts -> services -> commands/timeperiods
            const clusterDefs = {
                'contactgroups': {
                    types: ['contactgroup'],
                    angle: -Math.PI / 2,    // Top - notification satellite
                    color: '#FFC107'
                },
                'contacts': {
                    types: ['contact'],
                    angle: -Math.PI / 2,
                    color: '#FF9800',
                    orbitsAround: 'contactgroups'
                },
                'services': {
                    types: ['service'],
                    angle: -Math.PI / 2,
                    color: '#2196F3',
                    orbitsAround: 'contacts'
                },
                'commands': {
                    types: ['command'],
                    angle: -Math.PI / 2,
                    color: '#9C27B0',
                    orbitsAround: 'services'
                },
                'timeperiods': {
                    types: ['timeperiod'],
                    angle: -Math.PI / 2,
                    color: '#607D8B',
                    orbitsAround: 'services'
                },
                'hostgroups': {
                    types: ['hostgroup'],
                    angle: Math.PI,         // Left
                    color: '#8BC34A'
                },
                'servicegroups': {
                    types: ['servicegroup'],
                    angle: 0,               // Right
                    color: '#03A9F4'
                },
                'hosts': {
                    types: ['host'],
                    angle: Math.PI * 3/4,   // Bottom-left
                    color: '#4CAF50'
                },
                'dependencies': {
                    types: ['servicedependency', 'hostdependency', 'serviceescalation', 'hostescalation'],
                    angle: Math.PI / 4,     // Bottom-right
                    color: '#E91E63'
                }
            };

            // Group nodes by type into clusters
            const clusters = {};
            for (const clusterName of Object.keys(clusterDefs)) {
                clusters[clusterName] = [];
            }
            clusters.other = [];

            for (const nodeId of visited) {
                if (nodeId === centerNodeId) {continue;}
                const node = nodeMap[nodeId];
                if (!node) {continue;}

                // Find cluster by type
                let assigned = false;
                for (const clusterName of Object.keys(clusterDefs)) {
                    if (clusterDefs[clusterName].types.includes(node.type)) {
                        clusters[clusterName].push(nodeId);
                        assigned = true;
                        break;
                    }
                }

                if (!assigned) {
                    clusters.other.push(nodeId);
                }
            }

            // Add 'other' cluster definition if needed
            if (clusters.other.length > 0) {
                clusterDefs.other = {
                    types: [],
                    angle: Math.PI * 2/3,
                    color: '#9E9E9E'
                };
            }

            // Position center node
            positions[centerNodeId] = { x: 0, y: 0 };

            // Position each cluster - use centralized config
            const {
                clusterDistance,
                clusterRadius,
                clusterRadiusStep,
                nodesPerRing,
                orbitGap
            } = LAYOUT_CONFIG;

            // Track cluster bounds for orbiting calculations
            const clusterBounds = {};  // clusterName -> { centerX, centerY, maxRadius }

            // Helper function to position a cluster's nodes
            function positionClusterNodes(clusterName, nodeList, centerX, centerY, clusterAngle) {
                let maxRadius = 0;

                // Sort nodes by name for consistency
                nodeList.sort((a, b) => {
                    const nodeA = nodeMap[a];
                    const nodeB = nodeMap[b];
                    return (nodeA?.label || '').localeCompare(nodeB?.label || '');
                });

                if (nodeList.length === 1) {
                    positions[nodeList[0]] = { x: centerX, y: centerY };
                    maxRadius = 0;
                } else {
                    nodeList.forEach((nodeId, i) => {
                        const ringIndex = Math.floor(i / nodesPerRing);
                        const posInRing = i % nodesPerRing;
                        const nodesInThisRing = Math.min(nodesPerRing, nodeList.length - ringIndex * nodesPerRing);

                        const nodeRadius = clusterRadius + ringIndex * clusterRadiusStep;
                        maxRadius = Math.max(maxRadius, nodeRadius);

                        const angleStep = (2 * Math.PI) / nodesInThisRing;
                        const startAngle = clusterAngle;
                        const nodeAngle = startAngle + posInRing * angleStep;

                        positions[nodeId] = {
                            x: centerX + Math.cos(nodeAngle) * nodeRadius,
                            y: centerY + Math.sin(nodeAngle) * nodeRadius
                        };
                    });
                }

                return maxRadius;
            }

            // Build topological order for chained orbits
            // e.g., contactgroups -> contacts -> services -> commands
            function getOrbitChainRoot(clusterName) {
                const def = clusterDefs[clusterName];
                if (!def || !def.orbitsAround) {return clusterName;}
                return getOrbitChainRoot(def.orbitsAround);
            }

            function getOrbitDepth(clusterName) {
                const def = clusterDefs[clusterName];
                if (!def || !def.orbitsAround) {return 0;}
                return 1 + getOrbitDepth(def.orbitsAround);
            }

            // Sort clusters by orbit depth (roots first, then their children)
            const clusterOrder = Object.keys(clusters).filter(name => clusters[name].length > 0);
            clusterOrder.sort((a, b) => getOrbitDepth(a) - getOrbitDepth(b));

            // Position clusters in dependency order
            for (const clusterName of clusterOrder) {
                const nodeList = clusters[clusterName];
                const def = clusterDefs[clusterName];
                if (!def) {continue;}

                if (!def.orbitsAround) {
                    // Root cluster - position at its angle from center
                    const clusterAngle = def.angle;
                    const clusterCenterX = Math.cos(clusterAngle) * clusterDistance;
                    const clusterCenterY = Math.sin(clusterAngle) * clusterDistance;

                    const maxRadius = positionClusterNodes(clusterName, nodeList, clusterCenterX, clusterCenterY, clusterAngle);

                    clusterBounds[clusterName] = {
                        centerX: clusterCenterX,
                        centerY: clusterCenterY,
                        maxRadius: maxRadius,
                        outerRadius: maxRadius  // Track outermost extent including children
                    };
                } else {
                    // Orbiting cluster - position around parent's center
                    const parentName = def.orbitsAround;
                    let parentBounds = clusterBounds[parentName];

                    // If parent has no nodes, create virtual bounds at its angle
                    if (!parentBounds) {
                        const parentDef = clusterDefs[parentName];
                        const fallbackAngle = parentDef ? parentDef.angle : def.angle;
                        const fallbackX = Math.cos(fallbackAngle) * clusterDistance;
                        const fallbackY = Math.sin(fallbackAngle) * clusterDistance;
                        parentBounds = {
                            centerX: fallbackX,
                            centerY: fallbackY,
                            maxRadius: 0,
                            outerRadius: 0
                        };
                        clusterBounds[parentName] = parentBounds;
                    }

                    // Position this cluster as a ring outside the parent's outer radius
                    const orbitRadius = parentBounds.outerRadius + orbitGap;

                    // Calculate nodes per ring for this orbit
                    const circumference = 2 * Math.PI * orbitRadius;
                    const minSpacing = 80;
                    const nodesPerOrbitRing = Math.max(6, Math.floor(circumference / minSpacing));

                    let maxOrbitRadius = orbitRadius;

                    // Sort nodes by name for consistency
                    nodeList.sort((a, b) => {
                        const nodeA = nodeMap[a];
                        const nodeB = nodeMap[b];
                        return (nodeA?.label || '').localeCompare(nodeB?.label || '');
                    });

                    // Position nodes in concentric orbit rings
                    nodeList.forEach((nodeId, i) => {
                        const ringIndex = Math.floor(i / nodesPerOrbitRing);
                        const posInRing = i % nodesPerOrbitRing;
                        const nodesInThisRing = Math.min(nodesPerOrbitRing, nodeList.length - ringIndex * nodesPerOrbitRing);

                        const nodeRadius = orbitRadius + ringIndex * 80;
                        maxOrbitRadius = Math.max(maxOrbitRadius, nodeRadius);

                        const angleStep = (2 * Math.PI) / nodesInThisRing;
                        const nodeAngle = posInRing * angleStep - Math.PI / 2;  // Start from top

                        positions[nodeId] = {
                            x: parentBounds.centerX + Math.cos(nodeAngle) * nodeRadius,
                            y: parentBounds.centerY + Math.sin(nodeAngle) * nodeRadius
                        };
                    });

                    // Store this cluster's bounds
                    clusterBounds[clusterName] = {
                        centerX: parentBounds.centerX,
                        centerY: parentBounds.centerY,
                        maxRadius: maxOrbitRadius,
                        outerRadius: maxOrbitRadius
                    };

                    // Update parent's outer radius to include this orbit
                    parentBounds.outerRadius = maxOrbitRadius;

                    // Propagate outer radius up the chain
                    let ancestor = parentName;
                    while (ancestor) {
                        const ancestorBounds = clusterBounds[ancestor];
                        if (ancestorBounds) {
                            ancestorBounds.outerRadius = Math.max(ancestorBounds.outerRadius, maxOrbitRadius);
                        }
                        const ancestorDef = clusterDefs[ancestor];
                        ancestor = ancestorDef?.orbitsAround;
                    }
                }
            }

            // Position disconnected nodes
            if (disconnected.length > 0) {
                const disconnectedAngle = Math.PI * 7/8;
                const dcX = Math.cos(disconnectedAngle) * clusterDistance;
                const dcY = Math.sin(disconnectedAngle) * clusterDistance;

                if (disconnected.length === 1) {
                    positions[disconnected[0]] = { x: dcX, y: dcY };
                } else {
                    const angleStep = (2 * Math.PI) / disconnected.length;
                    disconnected.forEach((nodeId, i) => {
                        const angle = i * angleStep;
                        positions[nodeId] = {
                            x: dcX + Math.cos(angle) * clusterRadius,
                            y: dcY + Math.sin(angle) * clusterRadius
                        };
                    });
                }
            }

            // Collision detection within clusters
            const NODE_MIN_DISTANCE = 80;
            const ITERATIONS = 6;

            for (let iter = 0; iter < ITERATIONS; iter++) {
                const nodeIds = Object.keys(positions);
                for (let i = 0; i < nodeIds.length; i++) {
                    for (let j = i + 1; j < nodeIds.length; j++) {
                        const idA = nodeIds[i];
                        const idB = nodeIds[j];
                        const posA = positions[idA];
                        const posB = positions[idB];

                        const dx = posB.x - posA.x;
                        const dy = posB.y - posA.y;
                        const dist = Math.sqrt(dx * dx + dy * dy);

                        if (dist < NODE_MIN_DISTANCE && dist > 0) {
                            const overlap = NODE_MIN_DISTANCE - dist;
                            const pushX = (dx / dist) * overlap * 0.5;
                            const pushY = (dy / dist) * overlap * 0.5;

                            if (idA !== centerNodeId) {
                                posA.x -= pushX;
                                posA.y -= pushY;
                            }
                            if (idB !== centerNodeId) {
                                posB.x += pushX;
                                posB.y += pushY;
                            }
                        }
                    }
                }
            }
        }

        return positions;
    }

    // ========================================
    // Session Storage - Persist graph per user session
    // ========================================

    function saveGraphState() {
        const state = {
            addedNodeIds: Array.from(addedNodeIds),
            layoutType: document.getElementById('layoutType').value,
            showEdgeLabels: showEdgeLabels,
            focusNodeId: focusNodeId,
            enabledCategories: Array.from(enabledCategories),
            enabledTypes: Array.from(enabledTypes),
            viewMode: document.getElementById('viewMode')?.value || 'overview'
        };
        sessionStorage.setItem('graphViewState', JSON.stringify(state));
    }

    function loadGraphState() {
        const saved = sessionStorage.getItem('graphViewState');
        if (!saved) {return;}

        try {
            const state = JSON.parse(saved);

            // Restore added nodes (only if they still exist in the data)
            if (state.addedNodeIds && Array.isArray(state.addedNodeIds)) {
                const validNodeIds = new Set(allNodes.map(n => n.id));
                for (const id of state.addedNodeIds) {
                    if (validNodeIds.has(id)) {
                        addedNodeIds.add(id);
                    }
                }
            }

            // Restore layout type
            if (state.layoutType) {
                document.getElementById('layoutType').value = state.layoutType;
            }

            // Restore edge labels setting
            if (typeof state.showEdgeLabels === 'boolean') {
                showEdgeLabels = state.showEdgeLabels;
                updateLabelsButton();
            }

            // Restore focus node
            if (state.focusNodeId) {
                focusNodeId = state.focusNodeId;
            }

            // Restore edge filter categories
            if (state.enabledCategories && Array.isArray(state.enabledCategories)) {
                enabledCategories = new Set(state.enabledCategories);
                syncCheckboxesToCategories();
            }

            // Restore object type filters
            if (state.enabledTypes && Array.isArray(state.enabledTypes)) {
                enabledTypes = new Set(state.enabledTypes);
                syncCheckboxesToTypes();
            }

            // Restore view mode
            if (state.viewMode) {
                const viewModeSelect = document.getElementById('viewMode');
                if (viewModeSelect) {
                    viewModeSelect.value = state.viewMode;
                }
            }
        } catch (e) {
            console.error('Error loading graph state:', e);
        }
    }

    async function loadAllData() {
        try {
            const response = await fetch('/api/dependencies');
            const data = await response.json();
            allNodes = data.nodes || [];
            allEdges = data.edges || [];
            console.log('Graph data loaded:', allNodes.length, 'nodes,', allEdges.length, 'edges');
            // Expose for debugging
            window._graphDebug = { allNodes, allEdges };
        } catch (error) {
            console.error('Error loading data:', error);
        }
    }

    function updateMaxNodesLabel() {
        // No-op: number input shows its own value
    }

    function onNodeSearchInput() {
        const search = document.getElementById('nodeSearchAdd').value.toLowerCase();
        if (searchTimeout) {clearTimeout(searchTimeout);}

        if (search.length < 2) {
            document.getElementById('nodeSearchResults').style.display = 'none';
            return;
        }

        searchTimeout = setTimeout(() => performNodeSearch(search), 100);
    }

    function performNodeSearch(search) {
        const results = [];

        for (const node of allNodes) {
            if (node.label.toLowerCase().includes(search)) {
                results.push(node);
                if (results.length >= 30) {break;}
            }
        }

        displaySearchResults(results);
    }

    function displaySearchResults(results) {
        const container = document.getElementById('nodeSearchResults');

        if (results.length === 0) {
            container.innerHTML = '<div class="dep-search-item dep-empty">No matches found</div>';
            container.style.display = 'block';
            return;
        }

        container.innerHTML = results.map(node => {
            const isAdded = addedNodeIds.has(node.id);
            const exists = node.exists !== false;
            const displayLabel = getNodeDisplayLabel(node.id, node.type, node.label);
            return `
                <div class="dep-search-item ${isAdded ? 'added' : ''} ${!exists ? 'orphan' : ''}"
                     onclick="addNode('${escapeAttr(node.id)}')">
                    <span class="dep-type-badge dep-type-badge--${escapeAttr(node.type)}">${node.type}</span>
                    <span>${escapeHtml(displayLabel)}</span>
                    ${!exists ? '<span class="orphan-badge" title="Referenced but not defined">✗</span>' : ''}
                    ${isAdded ? '<span style="color:#999;font-size:10px">(added)</span>' : ''}
                </div>
            `;
        }).join('');

        container.style.display = 'block';
    }

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#nodeSearchAdd') && !e.target.closest('#nodeSearchResults')) {
            document.getElementById('nodeSearchResults').style.display = 'none';
        }
    });

    function addNode(nodeId) {
        if (addedNodeIds.has(nodeId)) {return;}

        const maxNodes = MAX_NODES;
        if (addedNodeIds.size >= maxNodes) {
            showToast(`Maximum ${maxNodes} nodes reached`, 'warning');
            return;
        }

        // If this is the first node, set it as the focus/root node
        const isFirstNode = addedNodeIds.size === 0;
        if (isFirstNode) {
            focusNodeId = nodeId;
        }

        addedNodeIds.add(nodeId);
        updateGraph();
        updateAddedNodesList();
        saveGraphState();

        // Re-render quick view buttons when first node added (determines context)
        if (isFirstNode) {
            renderQuickViewButtons();
        }
    }

    function removeNode(nodeId) {
        addedNodeIds.delete(nodeId);
        updateGraph();
        updateAddedNodesList();
        saveGraphState();
    }

    function addConnected() {
        if (!cy) {return;}

        const selected = cy.$(':selected').map(n => n.id());
        if (selected.length === 0) {
            showToast('Please select a node in the graph first', 'warning');
            return;
        }

        const beforeCount = addedNodeIds.size;

        // Set the first selected node as the focus for organized layout
        if (selected.length === 1) {
            focusNodeId = selected[0];
        }

        // Recursively add all connected nodes for each selected node
        for (const nodeId of selected) {
            addAllConnectedRecursively(nodeId);
        }

        const added = addedNodeIds.size - beforeCount;

        if (added > 0) {
            updateGraph();
            updateAddedNodesList();
            saveGraphState();
            showToast(`Added ${added} connected node(s)`, 'success');
        } else {
            showToast('No new connections to add', 'info');
        }
    }

    function clearGraph() {
        addedNodeIds.clear();
        focusNodeId = null;  // Clear the focus node as well
        activeQuickView = null;  // Clear active quick view
        renderQuickViewButtons();  // Re-render buttons (will show default set)
        updateGraph();
        updateAddedNodesList();
        saveGraphState();
    }

    function updateAddedNodesList() {
        const container = document.getElementById('addedNodesList');
        document.getElementById('nodeCount').textContent = addedNodeIds.size;

        // Show/hide clear button based on node count (show when > 1)
        const clearBtn = document.getElementById('clearGraphBtn');
        if (clearBtn) {
            clearBtn.style.display = addedNodeIds.size > 1 ? '' : 'none';
        }

        if (addedNodeIds.size === 0) {
            container.innerHTML = '<div class="dep-empty">No nodes added yet</div>';
            return;
        }

        const nodes = [];
        for (const id of addedNodeIds) {
            const node = allNodes.find(n => n.id === id);
            if (node) {nodes.push(node);}
        }

        nodes.sort((a, b) => {
            if (a.type !== b.type) {return a.type.localeCompare(b.type);}
            return a.label.localeCompare(b.label);
        });

        container.innerHTML = nodes.map(node => {
            const displayLabel = getNodeDisplayLabel(node.id, node.type, node.label);
            const exists = node.exists !== false;
            return `
                <div class="dep-node-item ${!exists ? 'orphan' : ''}" onclick="openNodeInExplorer('${escapeAttr(node.type)}', '${escapeAttr(node.label)}')">
                    <span>
                        <span class="dep-type-badge dep-type-badge--${escapeAttr(node.type)}">${node.type}</span>
                        ${escapeHtml(displayLabel)}
                        ${!exists ? '<span class="orphan-badge" title="Referenced but not defined">✗</span>' : ''}
                    </span>
                    <span class="remove-btn" onclick="event.stopPropagation(); removeNode('${escapeAttr(node.id)}')">&times;</span>
                </div>
            `;
        }).join('');
    }

    // Check if an edge belongs to any of the enabled categories
    // Takes full edge object to handle ambiguous labels like 'members'
    function isEdgeEnabled(edge) {
        const label = edge.label;

        // Special handling for 'members' - depends on node types involved
        if (label === 'members') {
            const fromNode = allNodes.find(n => n.id === edge.from);
            const toNode = allNodes.find(n => n.id === edge.to);

            // contactgroup→contact members: requires 'contacts' category
            if (fromNode && toNode) {
                const isContactRelated =
                    fromNode.type === 'contactgroup' || toNode.type === 'contactgroup' ||
                    fromNode.type === 'contact' || toNode.type === 'contact';

                if (isContactRelated) {
                    return enabledCategories.has('contacts');
                }
            }
            // hostgroup/servicegroup members: requires 'groups' or 'membership' category
            return enabledCategories.has('groups') || enabledCategories.has('membership');
        }

        // Standard label-based check
        for (const category of enabledCategories) {
            if (edgeCategories[category] && edgeCategories[category].includes(label)) {
                return true;
            }
        }
        return false;
    }

    // Update checkbox UI to match enabled categories
    function syncCheckboxesToCategories() {
        // Internal categories map to UI checkboxes:
        // - 'membership' → groups (directional member edges)
        // - 'service-bindings' → dependencies (host_name) + groups (hostgroups)
        // - 'group-refs' → groups (hostgroup_name, servicegroup_name)
        const internalToCheckbox = {
            'membership': ['groups'],
            'service-bindings': ['dependencies', 'groups'],
            'group-refs': ['groups']
        };

        const checkboxes = document.querySelectorAll('#edgeCategoryFilters input[type="checkbox"]');
        checkboxes.forEach(cb => {
            const category = cb.dataset.category;
            // Direct match
            if (enabledCategories.has(category)) {
                cb.checked = true;
                return;
            }
            // Check if any internal category maps to this checkbox
            for (const [internal, checkboxCategories] of Object.entries(internalToCheckbox)) {
                if (enabledCategories.has(internal) && checkboxCategories.includes(category)) {
                    cb.checked = true;
                    return;
                }
            }
            cb.checked = false;
        });
    }

    // Handle individual edge filter checkbox change
    function onEdgeFilterChange() {
        // Read current checkbox state
        const checkboxes = document.querySelectorAll('#edgeCategoryFilters input[type="checkbox"]');
        enabledCategories = new Set();
        checkboxes.forEach(cb => {
            if (cb.checked) {
                enabledCategories.add(cb.dataset.category);
            }
        });

        // Clear active quick view since user is making custom changes
        clearActiveQuickView();

        updateGraph();
        saveGraphState();
    }

    // Update type filter checkboxes to match enabled types
    function syncCheckboxesToTypes() {
        const checkboxes = document.querySelectorAll('#objectTypeFilters input[type="checkbox"]');
        checkboxes.forEach(cb => {
            const objType = cb.dataset.type;
            cb.checked = enabledTypes.has(objType);
        });
    }

    // Handle object type filter checkbox change
    function onTypeFilterChange() {
        // Read current checkbox state
        const checkboxes = document.querySelectorAll('#objectTypeFilters input[type="checkbox"]');
        enabledTypes = new Set();
        checkboxes.forEach(cb => {
            if (cb.checked) {
                enabledTypes.add(cb.dataset.type);
            }
        });

        // Clear active quick view since user is making custom changes
        clearActiveQuickView();

        updateGraph();
        saveGraphState();
    }

    // Apply a quick view preset - sets edge filters, auto-expands connections, applies optimal layout
    function applyQuickView(preset) {
        const config = quickViewPresets[preset];
        if (!config) {
            console.warn('Unknown quick view preset:', preset);
            return;
        }

        // Update active quick view
        activeQuickView = preset;

        // Apply edge category filter
        enabledCategories = new Set(config.categories);
        syncCheckboxesToCategories();

        // Apply object type filter
        const presetTypes = typesByPreset[preset];
        if (presetTypes === null) {
            // null means show all types
            enabledTypes = new Set(allObjectTypes);
        } else {
            enabledTypes = new Set(presetTypes);
        }
        syncCheckboxesToTypes();

        // Apply optimal layout
        const layoutSelect = document.getElementById('layoutType');
        if (layoutSelect) {
            layoutSelect.value = config.layout;
        }

        // Determine the root node (the node user searched for)
        // Use focusNodeId if set AND valid, otherwise the first added node
        // Validation prevents ghost nodes if focusNodeId references a deleted object
        const validFocusNode = focusNodeId && allNodes.find(n => n.id === focusNodeId) ? focusNodeId : null;
        const rootNode = validFocusNode || (addedNodeIds.size > 0 ? [...addedNodeIds][0] : null);

        if (!rootNode) {
            // No root node available - inform user and don't change button state
            showToast('Add a node to the graph first, then apply a quick view', 'info');
            activeQuickView = null;  // Reset since we couldn't apply
            updateQuickViewButtons();
            return;
        }

        // Clear all expanded nodes and start fresh from root
        addedNodeIds.clear();
        addedNodeIds.add(rootNode);  // Always include the root node

        if (config.useSmartExpansion) {
            // Use semantic-aware expansion that understands Nagios object relationships
            addAllConnectedRecursively(rootNode);
        } else {
            // Use declarative expansion rules for type-aware traversal
            expandWithRules(rootNode, preset);
        }

        // Update button states
        updateQuickViewButtons();

        // Refresh graph with new settings
        updateGraph();
        updateAddedNodesList();
        saveGraphState();
    }

    /**
     * Shared BFS implementation for rule-based expansion.
     * @param {string} startNodeId - Node ID to expand from
     * @param {string} preset - Quick view preset name
     * @param {Array} nodes - Node array to search
     * @param {Array} edges - Edge array to traverse
     * @param {Set} resultSet - Set to populate with expanded node IDs
     * @param {boolean} exemptRootFromStopAt - If true, root node bypasses stopAt check
     * @private
     */
    function _expandWithRulesImpl(startNodeId, preset, nodes, edges, resultSet, exemptRootFromStopAt) {
        if (!edges || !nodes) {return;}

        const startNode = nodes.find(n => n.id === startNodeId);
        if (!startNode) {return;}

        const nodeType = startNode.type;
        const rules = expansionRules[nodeType]?.[preset];

        // No rules defined -> show nothing (prevents unpredictable expansion)
        if (!rules) {return;}

        const visited = new Set();
        const toVisit = [startNodeId];

        while (toVisit.length > 0) {
            const nodeId = toVisit.pop();
            if (visited.has(nodeId)) {continue;}
            visited.add(nodeId);

            const currentNode = nodes.find(n => n.id === nodeId);
            if (!currentNode) {continue;}

            const currentType = currentNode.type;

            // stopAt nodes: prevent expansion through unwanted intermediate nodes
            // (e.g., services view from hostgroup shouldn't expand to sibling hosts)
            // Dual tracking required: visited set prevents BFS cycles, resultSet
            // controls graph membership. Mark visited but exclude from graph.
            const shouldApplyStopAt = exemptRootFromStopAt ? (nodeId !== startNodeId) : true;
            if (shouldApplyStopAt && rules.stopAt?.includes(currentType)) {
                continue;
            }

            resultSet.add(nodeId);

            // Get applicable rules: base rules + type-specific atType rules
            // atType rule merging via union enables type-aware behavior at intermediate nodes
            // Union (not override) prevents losing base rules when type-specific rules apply
            let applicableForward = rules.forward || [];
            let applicableBackward = rules.backward || [];

            if (rules.atType && rules.atType[currentType]) {
                const typeRules = rules.atType[currentType];
                // Union of arrays: combine base + type-specific rules
                applicableForward = [...new Set([...applicableForward, ...(typeRules.forward || [])])];
                applicableBackward = [...new Set([...applicableBackward, ...(typeRules.backward || [])])];
            }

            // Follow forward edges: edge.from === nodeId
            for (const edge of edges) {
                if (applicableForward.includes(edge.label) && edge.from === nodeId) {
                    const targetNode = nodes.find(n => n.id === edge.to);
                    if (targetNode && !visited.has(edge.to)) {
                        toVisit.push(edge.to);
                    }
                }
            }

            // Follow backward edges: edge.to === nodeId
            for (const edge of edges) {
                if (applicableBackward.includes(edge.label) && edge.to === nodeId) {
                    const sourceNode = nodes.find(n => n.id === edge.from);
                    if (sourceNode && !visited.has(edge.from)) {
                        toVisit.push(edge.from);
                    }
                }
            }
        }
    }

    /**
     * Expand graph from a starting node using type-aware expansion rules.
     * Production version that operates on closure variables (allNodes, allEdges, addedNodeIds).
     *
     * @param {string} startNodeId - Node ID to expand from
     * @param {string} preset - Quick view preset name (e.g., 'services', 'network')
     */
    function expandWithRules(startNodeId, preset) {
        // Guard against uninitialized graph state
        if (!allEdges || !allNodes) {return;}
        // exemptRootFromStopAt=true: root node bypasses stopAt to allow expansion from it
        // (applyQuickView pre-adds root, stopAt prevents sibling expansion not root expansion)
        _expandWithRulesImpl(startNodeId, preset, allNodes, allEdges, addedNodeIds, true);
    }

    /**
     * Testable version of expandWithRules that accepts graph data as parameters.
     * Used by unit tests to inject mock data. Root node is exempt from stopAt
     * (matches applyQuickView behavior where root is pre-added before expansion).
     *
     * @param {string} startNodeId - Node ID to expand from
     * @param {string} preset - Quick view preset name
     * @param {Array} nodes - Mock node array
     * @param {Array} edges - Mock edge array
     * @param {Set} resultSet - Set to populate with expanded node IDs
     */
    function expandWithRulesTestable(startNodeId, preset, nodes, edges, resultSet) {
        _expandWithRulesImpl(startNodeId, preset, nodes, edges, resultSet, true);
    }

    // Export for browser (window) and Jest (module.exports)
    window.expansionRules = expansionRules;
    window.expandWithRules = expandWithRules;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { expansionRules, expandWithRules, expandWithRulesTestable };
    }

    // Get the type of the current focus/root node
    function getCurrentNodeType() {
        const rootNode = focusNodeId || (addedNodeIds.size > 0 ? [...addedNodeIds][0] : null);
        if (!rootNode) {return null;}
        const node = allNodes.find(n => n.id === rootNode);
        return node ? node.type : null;
    }

    // Render quick view buttons based on the current node type
    function renderQuickViewButtons() {
        const container = document.getElementById('quickViewContainer');
        if (!container) {return;}

        const nodeType = getCurrentNodeType();
        const presets = presetsByType[nodeType] || presetsByType.default;

        // Build button HTML
        const buttonsHtml = presets.map(presetId => {
            const preset = quickViewPresets[presetId];
            if (!preset) {return '';}
            const isActive = presetId === activeQuickView ? 'active' : '';
            return `
                <button class="quick-view-btn ${isActive}"
                        data-action="applyQuickView"
                        data-preset="${presetId}"
                        title="${preset.description}">
                    <i class="fa-solid ${preset.icon}"></i>
                    <span>${preset.label}</span>
                </button>
            `;
        }).join('');

        container.innerHTML = buttonsHtml;

        // Update the context label
        const contextLabel = document.getElementById('quickViewContextLabel');
        if (contextLabel) {
            if (nodeType) {
                contextLabel.textContent = `for ${nodeType}`;
                contextLabel.style.display = '';
            } else {
                contextLabel.textContent = '';
                contextLabel.style.display = 'none';
            }
        }
    }

    // Update quick view button active states (call after preset applied)
    function updateQuickViewButtons() {
        const buttons = document.querySelectorAll('.quick-view-btn');
        buttons.forEach(btn => {
            const preset = btn.dataset.preset;
            if (preset === activeQuickView) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    // Clear active quick view when user makes custom changes
    function clearActiveQuickView() {
        if (activeQuickView) {
            activeQuickView = null;
            updateQuickViewButtons();
        }
    }

    // Check if a node type is enabled in filters
    function isNodeTypeEnabled(nodeType) {
        return enabledTypes.has(nodeType);
    }

    function updateGraph() {
        // First filter nodes by type
        const typeFilteredNodeIds = new Set();
        for (const nodeId of addedNodeIds) {
            const node = allNodes.find(n => n.id === nodeId);
            if (node && isNodeTypeEnabled(node.type)) {
                typeFilteredNodeIds.add(nodeId);
            }
        }

        // Filter edges based on node membership AND edge category filters
        const displayEdges = getEdgesInSubgraph(typeFilteredNodeIds).filter(isEdgeEnabled);

        // Build set of nodes that have at least one visible edge
        const connectedNodeIds = getConnectedNodeIdsFromEdges(displayEdges);

        // Filter nodes: show if they have visible connections OR are focus/selected
        // This provides focused views while keeping the user's primary node visible
        const displayNodes = allNodes.filter(n => {
            if (!typeFilteredNodeIds.has(n.id)) {return false;}
            // Always show focus node (layout center) if its type is enabled
            if (n.id === focusNodeId) {return true;}
            // Always show selected node in Cytoscape
            if (cy && cy.$id(n.id).selected()) {return true;}
            // Always show if only one node added
            if (typeFilteredNodeIds.size === 1) {return true;}
            // Otherwise, must have visible edges
            return connectedNodeIds.has(n.id);
        });

        renderGraph(displayNodes, displayEdges);
    }

    // ========================================
    // Cytoscape.js Rendering
    // ========================================

    function getCytoscapeStyle(layoutType) {
        // Use straight edges for hierarchical layouts, bezier for others
        const isHierarchical = layoutType === 'hierarchical' || layoutType === 'hierarchicalLR';
        const edgeCurveStyle = isHierarchical ? 'straight' : 'bezier';

        return [
            // Node styles
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
                    'font-size': 11,
                    'color': '#fff',
                    'text-background-color': 'rgba(0,0,0,0.8)',
                    'text-background-opacity': 1,
                    'text-background-padding': 3,
                    'text-background-shape': 'roundrectangle'
                }
            },
            // Focus node - larger
            {
                selector: 'node[?isFocus]',
                style: {
                    'width': 60,
                    'height': 60,
                    'font-size': 13
                }
            },
            // Selected node
            {
                selector: 'node:selected',
                style: {
                    'border-width': 3,
                    'border-color': '#4ec9b0',
                    'border-opacity': 1
                }
            },
            // Edge styles - regular edges
            {
                selector: 'edge[!hasBundling]',
                style: {
                    'width': 1.5,
                    'line-color': 'data(color)',
                    'target-arrow-color': 'data(color)',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 0.8,
                    'curve-style': edgeCurveStyle,
                    'label': 'data(displayLabel)',
                    'font-size': 9,
                    'color': '#888',
                    'text-background-color': '#1e1e1e',
                    'text-background-opacity': 0.9,
                    'text-background-padding': 2,
                    'text-rotation': 'autorotate'
                }
            },
            // Bundled edges - use straight for hierarchical, bezier with control points otherwise
            {
                selector: 'edge[?hasBundling]',
                style: {
                    'width': 1.5,
                    'line-color': 'data(color)',
                    'target-arrow-color': 'data(color)',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 0.8,
                    'curve-style': isHierarchical ? 'straight' : 'unbundled-bezier',
                    'control-point-distances': isHierarchical ? undefined : function(ele) {
                        return [ele.data('controlDistance')];
                    },
                    'control-point-weights': isHierarchical ? undefined : [0.5],
                    'label': 'data(displayLabel)',
                    'font-size': 9,
                    'color': '#888',
                    'text-background-color': '#1e1e1e',
                    'text-background-opacity': 0.9,
                    'text-background-padding': 2,
                    'text-rotation': 'autorotate'
                }
            },
            // Selected edge
            {
                selector: 'edge:selected',
                style: {
                    'width': 2.5,
                    'line-color': '#4ec9b0',
                    'target-arrow-color': '#4ec9b0'
                }
            }
        ];
    }

    function renderGraph(nodes = [], edges = []) {
        const container = document.getElementById('graphContainer');
        const emptyState = document.getElementById('graphEmptyState');

        // Show/hide empty state
        if (nodes.length === 0) {
            emptyState.style.display = 'block';
            if (cy) {
                cy.destroy();
                cy = null;
            }
            return;
        } 
            emptyState.style.display = 'none';
        

        const layoutType = document.getElementById('layoutType').value;

        // Calculate organized positions when there's a focus node (for all layout types)
        let organizedPositions = {};
        const hasOrganizedLayout = focusNodeId && addedNodeIds.has(focusNodeId);
        if (hasOrganizedLayout) {
            organizedPositions = calculateOrganizedPositions(nodes, edges, focusNodeId, layoutType);
        }

        // Convert nodes to Cytoscape format
        const cyNodes = nodes.map(n => {
            // Get or create cached image URL for this type/color/template/exists combo
            const isTemplate = n.is_template || false;
            const exists = n.exists !== false;
            const cacheKey = `${n.type}:${n.color}:${isTemplate}:${exists}`;
            if (!nodeImageCache[cacheKey]) {
                nodeImageCache[cacheKey] = getNodeImageUrl(n.type, n.color, isTemplate, exists);
            }
            const isFocusNode = n.id === focusNodeId;

            // Build tooltip - for services, show context from node ID
            const displayLabel = getNodeDisplayLabel(n.id, n.type, n.label);
            let tooltip = isTemplate ? `${n.type} template: ${displayLabel}` : `${n.type}: ${displayLabel}`;
            if (!exists) {tooltip += ' (NOT DEFINED - orphan reference)';}
            if (isFocusNode) {tooltip += ' (layout center)';}

            const nodeData = {
                group: 'nodes',
                data: {
                    id: n.id,
                    label: n.label,
                    imageUrl: nodeImageCache[cacheKey],
                    tooltip: tooltip,
                    nodeType: n.type,
                    isFocus: isFocusNode
                }
            };

            // Set position if we have organized layout
            if (organizedPositions[n.id]) {
                nodeData.position = {
                    x: organizedPositions[n.id].x,
                    y: organizedPositions[n.id].y
                };
            }

            return nodeData;
        });

        // Build node position lookup for edge bundling
        const nodePositions = {};
        cyNodes.forEach(n => {
            if (n.position) {
                nodePositions[n.data.id] = n.position;
            }
        });

        // Calculate cluster centroids by node type for edge bundling
        const typeCentroids = {};
        const typeNodes = {};
        nodes.forEach(n => {
            if (!typeNodes[n.type]) {typeNodes[n.type] = [];}
            const pos = organizedPositions[n.id] || nodePositions[n.id];
            if (pos) {typeNodes[n.type].push(pos);}
        });
        for (const type of Object.keys(typeNodes)) {
            const positions = typeNodes[type];
            if (positions.length > 0) {
                typeCentroids[type] = {
                    x: positions.reduce((sum, p) => sum + p.x, 0) / positions.length,
                    y: positions.reduce((sum, p) => sum + p.y, 0) / positions.length
                };
            }
        }

        // Helper: calculate perpendicular distance from point to line segment
        function perpendicularDistance(px, py, x1, y1, x2, y2) {
            const dx = x2 - x1;
            const dy = y2 - y1;
            const len = Math.sqrt(dx * dx + dy * dy);
            if (len === 0) {return 0;}

            // Perpendicular distance (signed - positive = left of line)
            return ((py - y1) * dx - (px - x1) * dy) / len;
        }

        // Convert edges to Cytoscape format with bundling control points
        const cyEdges = edges.map((e, i) => {
            const sourceNode = nodes.find(n => n.id === e.from);
            const targetNode = nodes.find(n => n.id === e.to);
            const sourcePos = organizedPositions[e.from] || nodePositions[e.from];
            const targetPos = organizedPositions[e.to] || nodePositions[e.to];

            let controlDistance = 0;
            let hasBundling = false;

            // Calculate bundling control point distance if we have positions
            if (sourcePos && targetPos && targetNode && hasOrganizedLayout) {
                const targetCentroid = typeCentroids[targetNode.type];
                if (targetCentroid) {
                    // Midpoint between source and target
                    const midX = (sourcePos.x + targetPos.x) / 2;
                    const midY = (sourcePos.y + targetPos.y) / 2;

                    // Pull control point toward target cluster centroid (bundling strength: 0.4)
                    const bundleStrength = 0.4;
                    const controlX = midX + (targetCentroid.x - midX) * bundleStrength;
                    const controlY = midY + (targetCentroid.y - midY) * bundleStrength;

                    // Calculate perpendicular distance from control point to source-target line
                    controlDistance = perpendicularDistance(
                        controlX, controlY,
                        sourcePos.x, sourcePos.y,
                        targetPos.x, targetPos.y
                    );

                    // Only apply bundling if the distance is significant
                    hasBundling = Math.abs(controlDistance) > 10;
                }
            }

            return {
                group: 'edges',
                data: {
                    id: `edge-${i}`,
                    source: e.from,
                    target: e.to,
                    rawLabel: e.label,
                    displayLabel: showEdgeLabels ? formatEdgeLabel(e.label) : '',
                    color: getEdgeColor(e.label),
                    controlDistance: controlDistance,
                    hasBundling: hasBundling
                }
            };
        });

        // Destroy existing instance
        if (cy) {
            cy.destroy();
        }

        // Create Cytoscape instance
        cy = cytoscape({
            container: container,
            elements: [...cyNodes, ...cyEdges],
            style: getCytoscapeStyle(layoutType),
            layout: getLayoutConfig(layoutType, hasOrganizedLayout),
            // Interaction options
            boxSelectionEnabled: true,
            selectionType: 'additive',
            minZoom: 0.1,
            maxZoom: 3
        });

        // ========================================
        // Event Handling
        // ========================================

        // Click on node
        cy.on('tap', 'node', function(evt) {
            hideContextMenu();
            const node = evt.target;
            selectedNodeId = node.id();
        });

        // Click on background
        cy.on('tap', function(evt) {
            if (evt.target === cy) {
                hideContextMenu();
            }
        });

        // Right-click context menu
        cy.on('cxttap', 'node', function(evt) {
            evt.originalEvent.preventDefault();
            const node = evt.target;
            selectedNodeId = node.id();

            // Get current selection
            const currentSelection = cy.$(':selected');
            let selectedNodes;

            // If clicked node is already selected, keep multi-selection
            if (currentSelection.contains(node)) {
                selectedNodes = currentSelection.filter('node').map(n => n.id());
            } else {
                // New single selection
                cy.$(':selected').unselect();
                node.select();
                selectedNodes = [node.id()];
            }

            showContextMenu(evt.originalEvent, selectedNodes);
        });

        // Right-click on background
        cy.on('cxttap', function(evt) {
            if (evt.target === cy) {
                hideContextMenu();
            }
        });

        // Fit to view after layout completes
        cy.on('layoutstop', function() {
            setTimeout(() => {
                cy.fit(50);
            }, 50);
        });

        // For preset layout (organized positions), fit immediately
        if (hasOrganizedLayout || nodes.length > 0) {
            setTimeout(() => {
                if (cy) {cy.fit(50);}
            }, 100);
        }
    }

    function getLayoutConfig(layoutType, hasOrganizedLayout) {
        // If we have organized positions, use preset layout
        if (hasOrganizedLayout) {
            return { name: 'preset' };
        }

        // Use dagre for hierarchical layouts
        if (layoutType === 'hierarchical') {
            return {
                name: 'dagre',
                rankDir: 'TB',
                nodeSep: 80,
                rankSep: 150,
                animate: false
            };
        }

        if (layoutType === 'hierarchicalLR') {
            return {
                name: 'dagre',
                rankDir: 'LR',
                nodeSep: 80,
                rankSep: 200,
                animate: false
            };
        }

        // Default: use cose for static layout without focus node
        return {
            name: 'cose',
            idealEdgeLength: 150,
            nodeOverlap: 20,
            refresh: 20,
            fit: true,
            padding: 50,
            randomize: false,
            componentSpacing: 100,
            nodeRepulsion: 8000,
            edgeElasticity: 100,
            nestingFactor: 5,
            gravity: 80,
            numIter: 500,
            initialTemp: 200,
            coolingFactor: 0.95,
            minTemp: 1.0,
            animate: false
        };
    }

    // Hide context menu when clicking elsewhere
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.graph-context-menu')) {
            hideContextMenu();
        }
    });

    function applyLayout() {
        // Clear active quick view since user is making custom changes
        clearActiveQuickView();
        updateGraph();
        saveGraphState();
    }
    function fitGraph() {
        if (cy) {cy.fit(50);}
    }

    function escapeAttr(text) {
        if (text === null || text === undefined) {return '';}
        return String(text)
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'")
            .replace(/"/g, '\\"');
    }

    // Get display label for a node, including context for services
    function getNodeDisplayLabel(nodeId, nodeType, nodeLabel) {
        if (nodeType === 'service' && nodeId && nodeId.startsWith('service:')) {
            const parts = nodeId.split(':');
            if (parts.length >= 3) {
                // Has context: service:context:name
                const context = parts.slice(1, -1).join(':');
                return `${nodeLabel} on ${context}`;
            }
        }
        return nodeLabel;
    }

    // ========================================
    // Edge Label Toggle
    // ========================================

    function toggleEdgeLabels() {
        showEdgeLabels = !showEdgeLabels;
        document.getElementById('toggleLabelsBtn').textContent = showEdgeLabels ? 'Hide Connection Labels' : 'Show Connection Labels';
        updateGraph();
        saveGraphState();
    }

    function updateLabelsButton() {
        document.getElementById('toggleLabelsBtn').textContent = showEdgeLabels ? 'Hide Connection Labels' : 'Show Connection Labels';
    }

    // ========================================
    // Context Menu Functions
    // ========================================

    // Track selected nodes for context menu actions
    let contextMenuSelectedNodes = [];

    function showContextMenu(event, selectedNodeIds) {
        const menu = document.getElementById('graphContextMenu');
        const header = document.getElementById('contextMenuHeader');

        // Store selected nodes for context menu actions
        contextMenuSelectedNodes = selectedNodeIds;

        // Set header based on selection count
        if (selectedNodeIds.length === 1) {
            const node = allNodes.find(n => n.id === selectedNodeIds[0]);
            if (node) {
                const displayLabel = getNodeDisplayLabel(node.id, node.type, node.label);
                header.textContent = `${node.type}: ${displayLabel}`;
            } else {
                header.textContent = 'Node';
            }
        } else {
            header.textContent = `${selectedNodeIds.length} nodes selected`;
        }

        // Update menu items for multi-select (some actions don't make sense for multiple nodes)
        const singleOnlyActions = ['contextCenterOnNode', 'contextSetAsFocus', 'contextOpenInExplorer'];
        singleOnlyActions.forEach(action => {
            const item = menu.querySelector(`[data-action="${action}"]`);
            if (item) {
                item.style.display = selectedNodeIds.length === 1 ? '' : 'none';
            }
        });

        // Position menu
        let x = event.pageX || event.clientX;
        let y = event.pageY || event.clientY;

        // Adjust if too close to edge
        const menuWidth = 200;
        const menuHeight = 250;
        if (x + menuWidth > window.innerWidth) {x = window.innerWidth - menuWidth - 10;}
        if (y + menuHeight > window.innerHeight) {y = window.innerHeight - menuHeight - 10;}

        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
        menu.classList.add('visible');
    }

    function hideContextMenu() {
        document.getElementById('graphContextMenu').classList.remove('visible');
        // Don't clear contextMenuSelectedNodes here - actions need it after menu hides
    }

    function contextExpandConnections() {
        hideContextMenu();
        if (contextMenuSelectedNodes.length === 0) {return;}

        const beforeCount = addedNodeIds.size;

        // Set first selected node as focus for organized layout
        focusNodeId = contextMenuSelectedNodes[0];

        // Recursively add all connected nodes for each selected node
        for (const nodeId of contextMenuSelectedNodes) {
            addAllConnectedRecursively(nodeId);
        }

        const added = addedNodeIds.size - beforeCount;

        if (added > 0) {
            updateGraph();
            updateAddedNodesList();
            saveGraphState();
            showToast(`Added ${added} connected node(s)`, 'success');
        } else {
            showToast('No new connections to add', 'info');
        }
    }

    function contextShowOnlyConnections() {
        hideContextMenu();
        if (contextMenuSelectedNodes.length === 0) {return;}

        // Start with all selected nodes
        const connectedIds = new Set(contextMenuSelectedNodes);

        // Add all nodes connected to any selected node
        for (const nodeId of contextMenuSelectedNodes) {
            for (const edge of allEdges) {
                if (edge.from === nodeId) {connectedIds.add(edge.to);}
                if (edge.to === nodeId) {connectedIds.add(edge.from);}
            }
        }

        // Update addedNodeIds to only include connected nodes
        const newAddedIds = new Set();
        for (const id of addedNodeIds) {
            if (connectedIds.has(id)) {newAddedIds.add(id);}
        }

        addedNodeIds = newAddedIds;
        updateGraph();
        updateAddedNodesList();
        saveGraphState();
        showToast(`Showing ${addedNodeIds.size} connected node(s)`, 'info');
    }

    function contextCenterOnNode() {
        hideContextMenu();
        if (!selectedNodeId || !cy) {return;}

        const node = cy.$id(selectedNodeId);
        if (node.length) {
            cy.animate({
                center: { eles: node },
                zoom: 1.5,
                duration: 500
            });
        }
    }

    function contextSetAsFocus() {
        hideContextMenu();
        if (!selectedNodeId) {return;}

        // Set this node as the focus/center for organized layout
        focusNodeId = selectedNodeId;
        updateGraph();
        saveGraphState();

        // Re-render quick view buttons for new focus node type
        renderQuickViewButtons();

        const node = allNodes.find(n => n.id === selectedNodeId);
        const label = node ? getNodeDisplayLabel(node.id, node.type, node.label) : selectedNodeId;
        showToast(`"${label}" is now the layout center`, 'success');

        // Focus on the center node
        setTimeout(() => {
            if (cy) {
                const cyNode = cy.$id(focusNodeId);
                if (cyNode.length) {
                    cy.animate({
                        center: { eles: cyNode },
                        zoom: 1,
                        duration: 500
                    });
                }
            }
        }, 300);
    }

    function contextRemoveNode() {
        hideContextMenu();

        // Use context menu selection (preserves multi-select from right-click)
        if (contextMenuSelectedNodes.length > 0) {
            for (const nodeId of contextMenuSelectedNodes) {
                addedNodeIds.delete(nodeId);
            }
            const count = contextMenuSelectedNodes.length;
            updateGraph();
            updateAddedNodesList();
            saveGraphState();
            selectedNodeId = null;
            showToast(`Removed ${count} node(s) from graph`, 'success');
            return;
        }

        // Fall back to standard selection removal
        removeSelectedNodes();
    }

    function removeSelectedNodes() {
        if (!cy) {return;}

        // Get all selected nodes from Cytoscape
        const selected = cy.$(':selected').filter('node').map(n => n.id());

        if (selected.length === 0 && selectedNodeId) {
            // Fall back to context menu selected node
            removeNode(selectedNodeId);
            selectedNodeId = null;
            showToast('Node removed from graph', 'success');
            return;
        }

        if (selected.length === 0) {return;}

        // Remove all selected nodes
        for (const nodeId of selected) {
            addedNodeIds.delete(nodeId);
        }

        updateGraph();
        updateAddedNodesList();
        saveGraphState();
        selectedNodeId = null;
        showToast(`Removed ${selected.length} node(s) from graph`, 'success');
    }

    function contextRemoveDisconnected() {
        hideContextMenu();

        // Find all nodes that have at least one connection in the current graph
        const currentEdges = getEdgesInSubgraph(addedNodeIds);
        const connectedNodes = getConnectedNodeIdsFromEdges(currentEdges);

        // Remove nodes that have no connections
        const initialCount = addedNodeIds.size;
        const newAddedIds = new Set();
        for (const id of addedNodeIds) {
            if (connectedNodes.has(id)) {newAddedIds.add(id);}
        }

        const removed = initialCount - newAddedIds.size;
        if (removed > 0) {
            addedNodeIds = newAddedIds;
            updateGraph();
            updateAddedNodesList();
            saveGraphState();
            showToast(`Removed ${removed} disconnected node(s)`, 'success');
        } else {
            showToast('No disconnected nodes found', 'info');
        }
    }

    function contextOpenInExplorer() {
        hideContextMenu();
        if (!selectedNodeId) {return;}

        // Parse the node ID to get type and name
        // Service IDs may have format "service:target:name"
        const [type, name] = parseNodeId(selectedNodeId);
        if (type && name) {
            openNodeInExplorer(type, name);
        }
    }

    function openNodeInExplorer(type, name) {
        window.location.href = `/explorer?search=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}`;
    }

    // Expose functions to global scope for inline onclick handlers
    window.addNode = addNode;
    window.removeNode = removeNode;
    window.addConnected = addConnected;
    window.clearGraph = clearGraph;
    window.openNodeInExplorer = openNodeInExplorer;
    window.fitGraph = fitGraph;
    window.toggleEdgeLabels = toggleEdgeLabels;

    // Namespaced exports for testing (avoids global pollution)
    window.DepsModule = {
        // Layout functions
        calculateOrganizedPositions,
        // Expansion functions
        expandWithRules,
        _expandWithRulesImpl,
        // Graph state accessors (for testing)
        getState: () => ({
            allNodes,
            allEdges,
            addedNodeIds: new Set(addedNodeIds),
            focusNodeId,
            selectedNodeId
        }),
        // Edge traversal utilities
        getEdgesInSubgraph,
        getConnectedNodeIdsFromEdges,
        // Formatting utilities
        formatEdgeLabel,
        getEdgeColor,
        getNodeImageUrl
    };
    } catch (e) {
        console.error('dependencies.js IIFE error:', e);
    }
})();
