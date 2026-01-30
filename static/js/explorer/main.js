/**
 * Nagios Bulk Editor - Explorer Main Module
 *
 * This is the entry point for the explorer functionality.
 * It defines the shared state namespace and initializes the application.
 */

// =============================================================================
// Namespace Definition
// =============================================================================

window.Explorer = window.Explorer || {};

// =============================================================================
// Shared State
// =============================================================================
// All modules access state through Explorer.state

Explorer.state = {
    // Core data
    allObjects: [],
    allFiles: [],

    // Selection (uses stable keys)
    selectedKeys: new Set(),
    selectedStagedIndices: new Set(),

    // Staging data - Object operations
    pendingEdits: new Map(),      // global_index -> {original, edited, object}
    stagedMoves: new Map(),       // objKey -> {targetFile, originalFile, object}
    stagedCreations: [],          // {object_type, attributes, targetFile, displayName}
    stagedObjectDeletions: new Set(),  // Set of global_index
    stagedCreationDeletions: new Set(),
    newFiles: new Set(),

    // Staging data - File/folder operations (true staging)
    stagedFileCreations: [],      // [{id, path, timestamp}]
    stagedFileDeletions: [],      // [{id, path, timestamp}]
    stagedFileMoves: [],          // [{id, sourcePath, targetPath, timestamp}]
    stagedFolderCreations: [],    // [{id, path, timestamp}]
    stagedFolderDeletions: [],    // [{id, path, timestamp}]
    stagedFolderMoves: [],        // [{id, sourcePath, targetPath, timestamp}]

    // Undo support
    undoStack: [],                // [{id, type, data, description, timestamp}]

    // UI state
    currentView: 'file',
    editedObject: null,
    originalAttributes: null,
    isNewObject: false,
    newObjectStagedIndex: null,
    contextTarget: null,
    hoveredIndex: null,
    externalChangePending: false,

    // Center pane state
    infoPanelObject: null,
    infoPanelData: {},
    currentCenterObject: null,
    currentCenterIssue: null,
    currentCenterIsOrphan: false,
    currentCenterHostListInfo: null,
    issuesByObject: new Map(),

    // Analysis suggestions
    allGroupingSuggestions: [],
    allTemplateSuggestions: [],
    allCleanupSuggestions: [],
    allNotificationSuggestions: [],
    groupedErrors: [],

    // Folder/file state
    expandedFolders: new Set(),
    expandedFiles: new Set(),
    openTreeFolders: new Set(),
    existingFolders: [],

    // Config
    configPath: '',

    // Session
    sessionId: null,
    currentStagingOwner: null,
    isEditingLocked: false,

    // Autocomplete state
    currentAutocompleteKey: null,
    highlightedIndex: -1,
    addAttrHighlightedIndex: -1,
    addAttrNameHighlightedIndex: -1,

    // Pending actions
    pendingHostgroupServiceLink: null
};

// =============================================================================
// Constants
// =============================================================================

Explorer.constants = {
    // Type display labels
    typeLabels: {
        host: 'Hosts',
        service: 'Services',
        hostgroup: 'Host Groups',
        servicegroup: 'Service Groups',
        contact: 'Contacts',
        contactgroup: 'Contact Groups',
        command: 'Commands',
        timeperiod: 'Time Periods',
        servicedependency: 'Service Dependencies',
        hostdependency: 'Host Dependencies',
        serviceescalation: 'Service Escalations',
        hostescalation: 'Host Escalations'
    },

    // Fields that define the object identity
    identityFields: {
        host: ['host_name', 'alias', 'display_name', 'address', 'name'],
        hostgroup: ['hostgroup_name', 'alias', 'name'],
        service: ['service_description', 'alias', 'display_name', 'name'],
        servicegroup: ['servicegroup_name', 'alias', 'name'],
        contact: ['contact_name', 'alias', 'name'],
        contactgroup: ['contactgroup_name', 'alias', 'name'],
        command: ['command_name', 'command_line', 'name'],
        timeperiod: ['timeperiod_name', 'alias', 'name'],
        servicedependency: ['name'],
        hostdependency: ['name'],
        serviceescalation: ['name'],
        hostescalation: ['name']
    },

    // Attributes that affect inheritance/reference sections
    inheritanceAttrs: ['use', 'parents'],
    referenceAttrs: [
        'use', 'parents', 'hostgroups', 'servicegroups', 'contactgroups',
        'contact_groups', 'host_name', 'hostgroup_name', 'check_command',
        'event_handler', 'check_period', 'notification_period', 'contacts', 'members'
    ],

    // Name fields by object type (must stay in sync with nagios_model.py:NAME_FIELDS)
    // N-01: Added dependency and escalation object types
    nameFields: {
        host: 'host_name',
        hostgroup: 'hostgroup_name',
        service: 'service_description',
        servicegroup: 'servicegroup_name',
        contact: 'contact_name',
        contactgroup: 'contactgroup_name',
        command: 'command_name',
        timeperiod: 'timeperiod_name',
        servicedependency: 'service_description',
        hostdependency: 'host_name',
        serviceescalation: 'service_description',
        hostescalation: 'host_name'
    },

    // Notification options
    HOST_NOTIFICATION_OPTIONS: [
        'd - Down', 'u - Unreachable', 'r - Recovery',
        'f - Flapping', 's - Scheduled Downtime', 'n - None'
    ],
    SERVICE_NOTIFICATION_OPTIONS: [
        'w - Warning', 'u - Unknown', 'c - Critical', 'r - Recovery',
        'f - Flapping', 's - Scheduled Downtime', 'n - None'
    ],
    NOTIFICATION_OPTION_ATTRS: [
        'notification_options', 'host_notification_options', 'service_notification_options'
    ],

    // Attribute reference map
    ATTR_REFERENCE_MAP: {
        'hostgroup_name': 'hostgroup',
        'hostgroups': 'hostgroup',
        'hostgroup_members': 'hostgroup',
        'parents': 'host',
        'members': null,
        'servicegroups': 'servicegroup',
        'servicegroup_name': 'servicegroup',
        'servicegroup_members': 'servicegroup',
        'contacts': 'contact',
        'contact_groups': 'contactgroup',
        'contactgroups': 'contactgroup',
        'contactgroup_members': 'contactgroup',
        'check_command': 'command',
        'event_handler': 'command',
        'host_notification_commands': 'command',
        'service_notification_commands': 'command',
        'check_period': 'timeperiod',
        'notification_period': 'timeperiod',
        'host_notification_period': 'timeperiod',
        'service_notification_period': 'timeperiod',
        'dependency_period': 'timeperiod',
        'escalation_period': 'timeperiod',
        'use': null,
        'dependent_host_name': 'host',
        'dependent_hostgroup_name': 'hostgroup'
    }
};

// =============================================================================
// SVG Icons - Enterprise File Browser
// =============================================================================

Explorer.icons = {
    'chevron-right': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>',

    'folder': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>',

    'folder-open': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v1"></path><path d="M2 10h20"></path></svg>',

    'file-text': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>',

    'file-plus': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>',

    'folder-plus': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v11z"></path><line x1="12" y1="11" x2="12" y2="17"></line><line x1="9" y1="14" x2="15" y2="14"></line></svg>',

    'plus': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>',

    'minimize-2': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>',

    'refresh-cw': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>',

    'more-horizontal': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle></svg>',

    'trash-2': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>',

    'grip-vertical': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="5" r="1"></circle><circle cx="9" cy="12" r="1"></circle><circle cx="9" cy="19" r="1"></circle><circle cx="15" cy="5" r="1"></circle><circle cx="15" cy="12" r="1"></circle><circle cx="15" cy="19" r="1"></circle></svg>',

    'x': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',

    'edit': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>',

    'copy': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>'
};

/**
 * Get SVG icon HTML
 */
Explorer.getIcon = function(name) {
    return this.icons[name] || '';
};

// =============================================================================
// Core Utility Functions
// =============================================================================

/**
 * Generate a stable key for an object
 * Format: "source_file|object_type|name"
 * Note: Uses display_name as fallback when name is null to ensure key uniqueness
 */
Explorer.getObjectKey = function(obj) {
    // Use name if available, otherwise fall back to display_name
    const nameComponent = obj.name ?? obj.display_name ?? `idx:${obj.global_index}`;
    return `${obj.source_file}|${obj.object_type}|${nameComponent}`;
};

/**
 * Find an object by its stable key
 */
Explorer.findObjectByKey = function(key) {
    const [source_file, object_type, ...nameParts] = key.split('|');
    // Rejoin name parts in case the name itself contains '|'
    const name = nameParts.join('|');
    return Explorer.state.allObjects.find(o => {
        const objName = o.name ?? o.display_name ?? `idx:${o.global_index}`;
        return o.source_file === source_file &&
               o.object_type === object_type &&
               objName === name;
    });
};

/**
 * Get selected indices from stable keys
 */
Explorer.getSelectedIndices = function() {
    const indices = new Set();
    for (const key of Explorer.state.selectedKeys) {
        const obj = Explorer.findObjectByKey(key);
        if (obj) indices.add(obj.global_index);
    }
    return indices;
};

/**
 * Get object key by global index
 */
Explorer.getObjectKeyByIndex = function(index) {
    const obj = Explorer.state.allObjects.find(o => o.global_index === index);
    return obj ? Explorer.getObjectKey(obj) : null;
};

/**
 * Group items by object type
 */
Explorer.groupByType = function(items) {
    const groups = {};
    items.forEach(item => {
        const type = item.object ? item.object.object_type : item.object_type;
        if (!groups[type]) groups[type] = [];
        groups[type].push(item);
    });
    return groups;
};

/**
 * Parse comma-separated values
 */
Explorer.parseCommaValues = function(str) {
    if (!str) return [];
    return str.split(',').map(s => s.trim()).filter(s => s);
};

/**
 * Get config root name from path
 */
Explorer.getConfigRootName = function() {
    return Explorer.state.configPath.split('/').pop() || 'config';
};

// Use global escapeHtml/escapeJs from base.js
Explorer.escapeHtml = escapeHtml;
Explorer.escapeJs = escapeJs;

// =============================================================================
// Initialization
// =============================================================================

/**
 * Initialize the explorer with config path
 */
Explorer.init = function(configPath) {
    Explorer.state.configPath = configPath;

    // Use the global getSessionId() from base.html for consistent session handling
    if (typeof getSessionId === 'function') {
        Explorer.state.sessionId = getSessionId();
    } else {
        Explorer.state.sessionId = 'session-' + Math.random().toString(36).substr(2, 9) +
                                   '-' + Date.now().toString(36);
    }

    // Initialize event delegation
    Explorer.initEventDelegation();

    DebugLogger.info('Explorer initialized', { sessionId: Explorer.state.sessionId });
};

// =============================================================================
// Event Delegation - Handles data-action attributes
// =============================================================================

/**
 * Initialize event delegation for data-action attributes
 * This replaces inline onclick handlers with a centralized event handling system
 */
Explorer.initEventDelegation = function() {
    // Action handlers map
    const actionHandlers = {
        // View and navigation
        setView: (el) => Explorer.setView(el.dataset.view),
        switchRightTab: (el) => Explorer.switchRightTab(el.dataset.tab),
        toggleSection: (el) => Explorer.toggleSection(el.dataset.section),
        toggleSuggestionSection: (el) => Explorer.toggleSuggestionSection(el.dataset.suggestionSection),

        // Actions menu
        toggleActionsMenu: (el, e) => Explorer.toggleActionsMenu(e),
        selectAllVisible: () => Explorer.selectAllVisible(),
        selectByType: () => Explorer.selectByType(),
        selectByPattern: () => Explorer.selectByPattern(),

        // Object actions
        navigateToObjectIssue: () => Explorer.navigateToObjectIssue(),
        openInGraphView: () => Explorer.openInGraphView(),
        discardNewObject: () => Explorer.discardNewObject(),
        showAddAttribute: () => Explorer.showAddAttribute(),

        // File/folder operations
        createInlineFile: () => Explorer.createInlineFile(),
        createInlineFolder: () => Explorer.createInlineFolder(),

        // Analysis
        analyzeAll: () => Explorer.analyzeAll(),
        runValidationFull: () => Explorer.runValidationFull(),

        // Dialogs and modals
        closeObjectDetail: () => Explorer.closeObjectDetail(),
        closePreview: () => Explorer.closePreview(),
        closeDialog: () => Explorer.closeDialog(),

        // Context menu actions
        contextAction: (el) => Explorer.contextAction(el.dataset.contextAction),
        showBulkRenameDialog: () => Explorer.showBulkRenameDialog(),
        showEditAttributesDialog: () => Explorer.showEditAttributesDialog(),
        showBulkAction: (el) => Explorer.showBulkAction(el.dataset.bulkAction),
        showAddToGroupDialog: () => Explorer.showAddToGroupDialog(),
        viewInGraph: () => Explorer.viewInGraph(),

        // Filter actions (for input/change events)
        filterTree: () => Explorer.filterTree(),
        filterTemplateSuggestions: () => Explorer.filterTemplateSuggestions(),
        filterGroupingSuggestions: () => Explorer.filterGroupingSuggestions(),

        // Object selection (for suggestion items)
        selectObjectByKey: (el) => Explorer.selectObjectByStableKey(el.dataset.stableKey),

        // Unified suggestions list actions
        filterSuggestions: (el, e) => Explorer.filterSuggestions(e),
        bulkDeleteUnused: () => Explorer.bulkDeleteUnused(),
        bulkCreateMissing: () => Explorer.bulkCreateMissing(),

        // Undo action
        undo: () => Explorer.undoLastAction()
    };

    // Handle click events with event delegation
    document.addEventListener('click', function(e) {
        // Handle stop propagation attribute
        const stopPropEl = e.target.closest('[data-stop-propagation="true"]');
        if (stopPropEl && stopPropEl.contains(e.target)) {
            e.stopPropagation();
            return;
        }

        // Find element with data-action
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;

        const action = actionEl.dataset.action;
        const handler = actionHandlers[action];

        // Only handle actions this module knows about; other modules (base.js) may handle others
        if (handler) {
            handler(actionEl, e);
        }
    });

    // Handle change events for filters (via data-action)
    document.addEventListener('change', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;

        const action = actionEl.dataset.action;
        const handler = actionHandlers[action];
        if (handler) {
            handler(actionEl, e);
        }
    });

    // Handle input events for search/sliders (via data-action)
    document.addEventListener('input', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;

        const action = actionEl.dataset.action;
        const handler = actionHandlers[action];
        if (handler) {
            handler(actionEl, e);
        }
    });
};
