/**
 * Nagios Bulk Editor - Explorer State Module
 *
 * Shared state for all explorer modules.
 * Extracted from main.js to break circular import chains.
 */

/**
 * Convert a set of absolute paths to relative paths for localStorage persistence.
 * Non-path keys (e.g., 'type:host') pass through unchanged.
 */
export function toRelativePaths(absoluteSet, configPath) {
    if (!configPath) {return [...absoluteSet];}
    const prefix = configPath.endsWith('/') ? configPath : configPath + '/';
    return [...absoluteSet].map(p => {
        if (p === configPath) {return '.';}
        if (p.startsWith(prefix)) {return p.substring(prefix.length);}
        return p;
    });
}

/**
 * Convert an array of relative paths back to absolute paths using current configPath.
 */
export function toAbsolutePaths(relativeArr, configPath) {
    if (!configPath) {return new Set(relativeArr);}
    return new Set(relativeArr.map(p => {
        if (p === '.') {return configPath;}
        if (p.startsWith('/') || p.startsWith('type:')) {return p;}
        return configPath + '/' + p;
    }));
}

/**
 * Manages tree node expansion state with localStorage persistence
 * and drag-hover auto-expand behavior.
 */
export class TreeExpansionState {
    constructor(storageKey) {
        this._set = new Set();
        this._storageKey = storageKey;
    }

    has(key)    { return this._set.has(key); }
    add(key)    { this._set.add(key); }
    delete(key) { this._set.delete(key); }
    clear()     { this._set.clear(); }
    get size()  { return this._set.size; }

    toggle(key) {
        if (this._set.has(key)) { this._set.delete(key); }
        else { this._set.add(key); }
    }

    save(configPath) {
        try {
            if (this._set.size > 0) {
                localStorage.setItem(this._storageKey,
                    JSON.stringify(toRelativePaths(this._set, configPath)));
            } else {
                localStorage.removeItem(this._storageKey);
            }
        } catch (e) {
            console.warn(`Failed to save ${this._storageKey}:`, e);
        }
    }

    restore(configPath) {
        try {
            const saved = localStorage.getItem(this._storageKey);
            if (saved) {
                const arr = JSON.parse(saved);
                if (Array.isArray(arr)) {
                    this._set = toAbsolutePaths(arr, configPath);
                }
            }
        } catch (e) {
            console.warn(`Failed to restore ${this._storageKey}:`, e);
        }
    }

    createDragHoverHandler(renderFn) {
        let timeout = null;
        let target = null;
        return {
            onDragOver: (event, path) => {
                event.preventDefault();
                event.dataTransfer.dropEffect = 'move';
                event.currentTarget.classList.add('drop-active');
                if (path && !this._set.has(path) && target !== path) {
                    if (timeout) clearTimeout(timeout);
                    target = path;
                    timeout = setTimeout(() => {
                        if (target === path) { this._set.add(path); renderFn(); }
                    }, 800);
                }
            },
            onDragLeave: (event) => {
                if (event.currentTarget.contains(event.relatedTarget)) return;
                event.currentTarget.classList.remove('drop-active');
                if (timeout) { clearTimeout(timeout); timeout = null; target = null; }
            }
        };
    }
}

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
    leftTreeExpansion: new TreeExpansionState('nagios_openTreeFolders'),
    rightTreeExpansion: new TreeExpansionState('nagios_expandedPaths'),
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
