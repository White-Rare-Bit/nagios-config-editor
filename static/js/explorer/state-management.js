/**
 * Nagios Bulk Editor - State Management Module (Shadow Copy Architecture)
 *
 * Handles stable key operations, selection management, and UI rebuild.
 * Client-side staging state removed — server is the source of truth.
 */

import { state } from './state.js';
import { getObjectKeyByIndex } from './main.js';
import { computeStagedIssues } from './badge-issues.js'; // circular — safe (function-level)
import { buildTree } from './app.js'; // circular — safe (function-level)
import { renderTargetPane } from './file-operations.js'; // circular — safe (function-level)
import { syncCenterPaneAfterUndo } from './object-editor.js'; // circular — safe (function-level)
import { renderTabBar } from './tab-manager.js';

// =============================================================================
// Selection Management
// =============================================================================

/**
 * Check if an object is selected by index
 */
export function isSelectedByIndex(index) {
    const key = getObjectKeyByIndex(index);
    return key ? state.selectedKeys.has(key) : false;
}

/**
 * Add object to selection by index
 */
export function addToSelectionByIndex(index) {
    const key = getObjectKeyByIndex(index);
    if (key) {
        state.selectedKeys.add(key);
        return true;
    }
    return false;
}

/**
 * Remove object from selection by index
 */
export function removeFromSelectionByIndex(index) {
    const key = getObjectKeyByIndex(index);
    if (key) {
        state.selectedKeys.delete(key);
        return true;
    }
    return false;
}

/**
 * Clear all selections
 */
export function clearSelection() {
    state.selectedKeys.clear();
}

// =============================================================================
// Object Lookup
// =============================================================================

/**
 * Find object by attributes (for idempotent operations).
 * Used when we need to find an object after reload when global_index may have changed.
 * First tries exact match by source_file + object_type + all attributes,
 * then falls back to source_file + object_type + name match.
 *
 * @param {Object} objMeta - Object metadata to search for
 * @param {string} objMeta.source_file - Source file path
 * @param {string} objMeta.object_type - Nagios object type
 * @param {Object} objMeta.attributes - Object attributes to match
 * @param {string} [objMeta.name] - Object name for fallback matching
 * @returns {Object|null} Matching object from allObjects, or null if not found
 */
export function findObjectByAttributes(objMeta) {
    if (!objMeta || !objMeta.source_file || !objMeta.attributes) {return null;}

    const attrsMatch = (a, b) => {
        if (!a || !b) {return false;}
        const keysA = Object.keys(a);
        const keysB = Object.keys(b);
        if (keysA.length !== keysB.length) {return false;}
        return keysA.every(key => a[key] === b[key]);
    };

    // Try exact match by source_file + object_type + attributes
    let found = state.allObjects.find(o =>
        o.source_file === objMeta.source_file &&
        o.object_type === objMeta.object_type &&
        attrsMatch(o.attributes, objMeta.attributes)
    );

    if (found) {return found;}

    // Fallback: match by source_file + object_type + name
    if (objMeta.name) {
        found = state.allObjects.find(o =>
            o.source_file === objMeta.source_file &&
            o.object_type === objMeta.object_type &&
            o.name === objMeta.name
        );
    }

    return found;
}

// =============================================================================
// UI Rebuild Primitives
// =============================================================================

/**
 * Synchronous UI rebuild — no network calls, no saves.
 * @param {Object} options
 * @param {boolean} options.skipTree - Skip tree + staged issues refresh
 * @param {boolean} options.skipTarget - Skip target pane refresh
 * @param {boolean} options.skipCenter - Skip center pane sync
 * @param {boolean} options.skipTabs - Skip tab bar refresh
 */
export function rebuildUI(options = {}) {
    if (!options.skipTree) {
        computeStagedIssues();
    }

    if (!options.skipTree) {
        buildTree();
    }

    if (!options.skipTarget) {
        renderTargetPane();
    }

    if (!options.skipCenter && state.editedObject) {
        syncCenterPaneAfterUndo();
    }

    renderTabBar();
}
