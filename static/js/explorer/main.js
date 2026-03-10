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

    // UI state
    currentView: 'file',
    editedObject: null,
    originalAttributes: null,
    isNewObject: false,
    contextTarget: null,
    hoveredIndex: null,
    selectedFolder: null,           // Track selected folder for subfolder creation

    // Tab state
    openTabs: [],              // Array of { key, label, typeIcon }
    activeTabKey: null,        // Stable key of currently active tab
    isTabSwitch: false,        // Guard flag to prevent tab↔tree infinite loop

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
    orphanIndices: new Set(),   // Set of stable keys for orphan objects
    healthCheckData: null,      // Cached /api/health-check response

    // Folder/file state
    expandedFolders: new Set(),
    expandedFiles: new Set(),
    openTreeFolders: new Set(),
    existingFolders: [],

    // Config
    configPath: '',

    // Session
    sessionId: null,

    // Autocomplete state
    currentAutocompleteKey: null,
    highlightedIndex: -1,
    addAttrHighlightedIndex: -1,
    addAttrNameHighlightedIndex: -1,

    // Pending actions
    pendingHostgroupServiceLink: null,

    // Metadata
    metadataLoaded: false
};

// =============================================================================
// Core Utility Functions
// (Constants are now in constants.js)
// =============================================================================

/**
 * Generate a stable key for an object
 * Format: "source_file|object_type|display_name"
 * Uses display_name to ensure uniqueness — services with the same
 * service_description on different hosts get different keys.
 * Delegates to shared StableKey module (static/js/stable-key.js).
 */
Explorer.getObjectKey = function(obj) {
    return StableKey.build(obj);
};

/**
 * Find an object by its stable key.
 * Delegates to shared StableKey module (static/js/stable-key.js).
 */
Explorer.findObjectByKey = function(key) {
    return StableKey.findObject(key, Explorer.state.allObjects);
};

/**
 * Get selected indices from stable keys
 */
Explorer.getSelectedIndices = function() {
    const indices = new Set();
    for (const key of Explorer.state.selectedKeys) {
        const obj = Explorer.findObjectByKey(key);
        if (obj) {indices.add(obj.global_index);}
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
        if (!groups[type]) {groups[type] = [];}
        groups[type].push(item);
    });
    return groups;
};

/**
 * Parse comma-separated values
 */
Explorer.parseCommaValues = function(str) {
    if (!str) {return [];}
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

    // Initialize panel resizer (must happen after DOM ready, before data load)
    Explorer.initPanelResizer();

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
        if (!actionEl) {return;}

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
        if (!actionEl) {return;}

        const action = actionEl.dataset.action;
        const handler = actionHandlers[action];
        if (handler) {
            handler(actionEl, e);
        }
    });

    // Handle input events for search/sliders (via data-action)
    document.addEventListener('input', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) {return;}

        const action = actionEl.dataset.action;
        const handler = actionHandlers[action];
        if (handler) {
            handler(actionEl, e);
        }
    });
};
