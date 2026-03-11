/**
 * Nagios Bulk Editor - Explorer Main Module
 *
 * Entry point for the explorer page. Sets up event delegation using the
 * action registry, exports shared utility functions, and provides init().
 */

import { state } from './state.js';
import { StableKey } from '../stable-key.js';
import { escapeHtml, escapeJs } from '../app.js';
import { DebugLogger, registerExplorerCallbacks } from '../base.js';
import { getSessionId } from '../session-manager.js';
import { actionHandlers } from './action-registry.js';
import { undoLastAction, getTotalStagedCount, getUndoCount, loadObjects } from './data-loading.js';
import { buildTree } from './app.js'; // circular — safe (function-level)
import { initPanelResizer } from './panel-resizer.js';

// Re-export escapeHtml/escapeJs for explorer modules that import them from main.js
export { escapeHtml, escapeJs };

// =============================================================================
// Core Utility Functions
// =============================================================================

/**
 * Generate a stable key for an object
 * Format: "source_file|object_type|display_name"
 * Delegates to shared StableKey module (static/js/stable-key.js).
 */
export function getObjectKey(obj) {
    return StableKey.build(obj);
}

/**
 * Find an object by its stable key.
 * Delegates to shared StableKey module (static/js/stable-key.js).
 */
export function findObjectByKey(key) {
    return StableKey.findObject(key, state.allObjects);
}

/**
 * Get selected indices from stable keys
 */
export function getSelectedIndices() {
    const indices = new Set();
    for (const key of state.selectedKeys) {
        const obj = findObjectByKey(key);
        if (obj) {indices.add(obj.global_index);}
    }
    return indices;
}

/**
 * Get object key by global index
 */
export function getObjectKeyByIndex(index) {
    const obj = state.allObjects.find(o => o.global_index === index);
    return obj ? getObjectKey(obj) : null;
}

/**
 * Group items by object type
 */
export function groupByType(items) {
    const groups = {};
    items.forEach(item => {
        const type = item.object ? item.object.object_type : item.object_type;
        if (!groups[type]) {groups[type] = [];}
        groups[type].push(item);
    });
    return groups;
}

/**
 * Parse comma-separated values
 */
export function parseCommaValues(str) {
    if (!str) {return [];}
    return str.split(',').map(s => s.trim()).filter(s => s);
}

/**
 * Get config root name from path
 */
export function getConfigRootName() {
    return state.configPath.split('/').pop() || 'config';
}

// =============================================================================
// Event Delegation
// =============================================================================

/**
 * Initialize event delegation for data-action attributes.
 * Uses the centralized action registry for handler lookup.
 */
function initEventDelegation() {
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
}

// =============================================================================
// Initialization
// =============================================================================

// Register callbacks for base.js (undo/commit button updates)
registerExplorerCallbacks({ undoLastAction, getTotalStagedCount, getUndoCount, buildTree });

/**
 * Initialize the explorer with config path.
 * Sets up state, event delegation, and panel resizer.
 * Data loading and UI setup happen in app.js DOMContentLoaded handler.
 */
export function init(configPath) {
    state.configPath = configPath;
    state.sessionId = getSessionId();

    initEventDelegation();
    initPanelResizer();

    DebugLogger.info('Explorer initialized', { sessionId: state.sessionId });
}

// Debug console access
if (typeof window !== 'undefined') {
    window.__debug = { state, getObjectKey, findObjectByKey, loadObjects, buildTree };
}
