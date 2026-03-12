/**
 * Nagios Bulk Editor - Explorer State Module
 *
 * Shared state for all explorer modules.
 * Extracted from main.js to break circular import chains.
 */

export const state = {
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

    // Shadow copy change indicators (from /api/staging/diff)
    // Map of relative path -> status ('added'|'modified'|'deleted')
    changedFilesMap: new Map(),

    // Changed object stable keys (from /api/staging/info)
    changedObjectKeys: new Set(),

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
