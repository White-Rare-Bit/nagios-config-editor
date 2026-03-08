/**
 * Nagios Bulk Editor - State Management Module
 *
 * Handles stable key operations, pending edits, and deletion tracking.
 *
 * Dependencies:
 * - window.Explorer (from main.js)
 * - Explorer.state (shared state object)
 * - Explorer.findObjectByKey (from main.js)
 * - Explorer.getObjectKeyByIndex (from main.js)
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // =============================================================================
    // Private Helpers
    // =============================================================================

    /**
     * Resolve various input types to a stable key
     * @param {string|number|Object} objOrKeyOrIndex - Stable key, global_index, or object
     * @returns {string|null} The stable key or null if not resolvable
     */
    function resolveToStableKey(objOrKeyOrIndex) {
        if (typeof objOrKeyOrIndex === 'string') {
            // Already a stable key — verify it's valid
            return objOrKeyOrIndex.indexOf('|') !== -1 ? objOrKeyOrIndex : null;
        }
        if (typeof objOrKeyOrIndex === 'number') {
            // Legacy: global_index — convert to stable key
            return Explorer.getObjectKeyByIndex(objOrKeyOrIndex);
        }
        if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
            return Explorer.getObjectKey(objOrKeyOrIndex);
        }
        return null;
    }

    // =============================================================================
    // Pending Edit Operations
    // =============================================================================

    /**
     * Get pending edit using either stable key, global_index, or object
     * @param {string|number|Object} objOrKeyOrIndex
     * @returns {Object|undefined} The pending edit data
     */
    // =============================================================================
    // Deletion Tracking
    // =============================================================================

    /**
     * Check if object is marked for deletion
     * @param {string|number|Object} objOrKeyOrIndex
     * @returns {boolean}
     */
    Explorer.isObjectMarkedForDeletion = function(objOrKeyOrIndex) {
        const key = resolveToStableKey(objOrKeyOrIndex);
        return key !== null && state.stagedObjectDeletions.has(key);
    };

    /**
     * Mark object for deletion
     * @param {string|number|Object} objOrKeyOrIndex
     * @returns {boolean} True if marked successfully
     */
    // =============================================================================
    // Selection Management
    // =============================================================================

    /**
     * Check if an object is selected by index
     */
    Explorer.isSelectedByIndex = function(index) {
        const key = Explorer.getObjectKeyByIndex(index);
        return key ? state.selectedKeys.has(key) : false;
    };

    /**
     * Add object to selection by index
     */
    Explorer.addToSelectionByIndex = function(index) {
        const key = Explorer.getObjectKeyByIndex(index);
        if (key) {
            state.selectedKeys.add(key);
            return true;
        }
        return false;
    };

    /**
     * Remove object from selection by index
     */
    Explorer.removeFromSelectionByIndex = function(index) {
        const key = Explorer.getObjectKeyByIndex(index);
        if (key) {
            state.selectedKeys.delete(key);
            return true;
        }
        return false;
    };

    /**
     * Clear all selections
     */
    Explorer.clearSelection = function() {
        state.selectedKeys.clear();
    };

    /**
     * Get count of selected items
     */
    // =============================================================================
    // Staged Changes Helpers
    // =============================================================================

    /**
     * Check if there are any staged changes
     */
    Explorer.hasStagedChanges = function() {
        return state.pendingEdits.size > 0 ||
               state.stagedMoves.size > 0 ||
               state.stagedCreations.length > 0 ||
               state.stagedObjectDeletions.size > 0 ||
               state.stagedCreationDeletions.size > 0 ||
               state.newFiles.size > 0 ||
               // File/folder operations
               state.stagedFileCreations.length > 0 ||
               state.stagedFileDeletions.length > 0 ||
               state.stagedFileMoves.length > 0 ||
               state.stagedFolderCreations.length > 0 ||
               state.stagedFolderDeletions.length > 0 ||
               state.stagedFolderMoves.length > 0;
    };

    /**
     * Reset all staging state
     */
    Explorer.resetStagingState = function() {
        state.pendingEdits.clear();
        state.stagedMoves.clear();
        state.stagedCreations = [];
        state.stagedObjectDeletions.clear();
        state.stagedCreationDeletions.clear();
        state.newFiles.clear();
        // File/folder operations
        state.stagedFileCreations = [];
        state.stagedFileDeletions = [];
        state.stagedFileMoves = [];
        state.stagedFolderCreations = [];
        state.stagedFolderDeletions = [];
        state.stagedFolderMoves = [];
        // Undo stack
        state.undoStack = [];
        state.isEditingLocked = false;
    };

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
    Explorer.findObjectByAttributes = function(objMeta) {
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
    };

    // =============================================================================
    // Editing Lock Management
    // =============================================================================

    /**
     * Update UI to show/hide editing lock state
     */
    Explorer.updateEditingLockedUI = function() {
        if (state.isEditingLocked) {
            document.body.classList.add('editing-locked');
        } else {
            document.body.classList.remove('editing-locked');
        }
    };

    /**
     * Check if editing is allowed
     */
    Explorer.canEdit = function() {
        return !state.isEditingLocked;
    };

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
    Explorer.rebuildUI = function(options = {}) {
        if (!options.skipTree && Explorer.computeStagedIssues) {
            Explorer.computeStagedIssues();
        }

        if (!options.skipTree && Explorer.buildTree) {
            Explorer.buildTree();
        }

        if (!options.skipTarget && Explorer.renderTargetPane) {
            Explorer.renderTargetPane();
        }

        if (!options.skipCenter && Explorer.syncCenterPaneAfterUndo && state.editedObject) {
            Explorer.syncCenterPaneAfterUndo();
        }

        if (Explorer.renderTabBar) {
            Explorer.renderTabBar();
        }
    };

})(window.Explorer);
