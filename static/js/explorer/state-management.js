/**
 * Nagios Bulk Editor - State Management Module
 *
 * Handles stable key operations, pending edits, and deletion tracking.
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // =============================================================================
    // Stable Key Helpers
    // =============================================================================

    /**
     * Get pending edit using either stable key, global_index, or object
     */
    Explorer.getPendingEdit = function(objOrKeyOrIndex) {
        if (typeof objOrKeyOrIndex === 'string') {
            const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
            return obj ? state.pendingEdits.get(obj.global_index) : undefined;
        } else if (typeof objOrKeyOrIndex === 'number') {
            return state.pendingEdits.get(objOrKeyOrIndex);
        } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
            return state.pendingEdits.get(objOrKeyOrIndex.global_index);
        }
        return undefined;
    };

    /**
     * Set pending edit using either stable key, global_index, or object
     */
    Explorer.setPendingEdit = function(objOrKeyOrIndex, editData) {
        let globalIndex;

        if (typeof objOrKeyOrIndex === 'string') {
            const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
            globalIndex = obj ? obj.global_index : null;
        } else if (typeof objOrKeyOrIndex === 'number') {
            globalIndex = objOrKeyOrIndex;
        } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
            globalIndex = objOrKeyOrIndex.global_index;
        }

        if (globalIndex !== null && globalIndex !== undefined) {
            state.pendingEdits.set(globalIndex, editData);
            return true;
        }
        return false;
    };

    /**
     * Delete pending edit
     */
    Explorer.deletePendingEdit = function(objOrKeyOrIndex) {
        let globalIndex;

        if (typeof objOrKeyOrIndex === 'string') {
            const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
            globalIndex = obj ? obj.global_index : null;
        } else if (typeof objOrKeyOrIndex === 'number') {
            globalIndex = objOrKeyOrIndex;
        } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
            globalIndex = objOrKeyOrIndex.global_index;
        }

        if (globalIndex !== null && globalIndex !== undefined) {
            state.pendingEdits.delete(globalIndex);
            return true;
        }
        return false;
    };

    /**
     * Check if object is marked for deletion
     */
    Explorer.isObjectMarkedForDeletion = function(objOrKeyOrIndex) {
        let globalIndex;

        if (typeof objOrKeyOrIndex === 'string') {
            const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
            globalIndex = obj ? obj.global_index : null;
        } else if (typeof objOrKeyOrIndex === 'number') {
            globalIndex = objOrKeyOrIndex;
        } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
            globalIndex = objOrKeyOrIndex.global_index;
        }

        return globalIndex !== null && globalIndex !== undefined &&
               state.stagedObjectDeletions.has(globalIndex);
    };

    /**
     * Mark object for deletion
     */
    Explorer.markObjectForDeletion = function(objOrKeyOrIndex) {
        let globalIndex;

        if (typeof objOrKeyOrIndex === 'string') {
            const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
            globalIndex = obj ? obj.global_index : null;
        } else if (typeof objOrKeyOrIndex === 'number') {
            globalIndex = objOrKeyOrIndex;
        } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
            globalIndex = objOrKeyOrIndex.global_index;
        }

        if (globalIndex !== null && globalIndex !== undefined) {
            state.stagedObjectDeletions.add(globalIndex);
            return true;
        }
        return false;
    };

    /**
     * Unmark object for deletion
     */
    Explorer.unmarkObjectForDeletion = function(objOrKeyOrIndex) {
        let globalIndex;

        if (typeof objOrKeyOrIndex === 'string') {
            const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
            globalIndex = obj ? obj.global_index : null;
        } else if (typeof objOrKeyOrIndex === 'number') {
            globalIndex = objOrKeyOrIndex;
        } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
            globalIndex = objOrKeyOrIndex.global_index;
        }

        if (globalIndex !== null && globalIndex !== undefined) {
            state.stagedObjectDeletions.delete(globalIndex);
            return true;
        }
        return false;
    };

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
            Explorer.updateSelectionCount && Explorer.updateSelectionCount();
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
            Explorer.updateSelectionCount && Explorer.updateSelectionCount();
            return true;
        }
        return false;
    };

    /**
     * Clear all selections
     */
    Explorer.clearSelection = function() {
        state.selectedKeys.clear();
        Explorer.updateSelectionCount && Explorer.updateSelectionCount();
    };

    /**
     * Get count of selected items
     */
    Explorer.getSelectionCount = function() {
        return state.selectedKeys.size + state.selectedStagedIndices.size;
    };

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
     * Find object by attributes (for idempotent operations)
     */
    Explorer.findObjectByAttributes = function(objMeta) {
        if (!objMeta || !objMeta.source_file || !objMeta.attributes) return null;

        const attrsMatch = (a, b) => {
            if (!a || !b) return false;
            const keysA = Object.keys(a);
            const keysB = Object.keys(b);
            if (keysA.length !== keysB.length) return false;
            return keysA.every(key => a[key] === b[key]);
        };

        // Try exact match by source_file + object_type + attributes
        let found = state.allObjects.find(o =>
            o.source_file === objMeta.source_file &&
            o.object_type === objMeta.object_type &&
            attrsMatch(o.attributes, objMeta.attributes)
        );

        if (found) return found;

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
    // Centralized Refresh Function
    // =============================================================================

    /**
     * Refresh UI components after object changes
     * @param {Object} options - Optional controls for which components to refresh
     * @param {boolean} options.skipTree - Skip tree refresh
     * @param {boolean} options.skipTarget - Skip target pane refresh
     * @param {boolean} options.skipCenter - Skip center pane refresh
     * @param {boolean} options.skipSuggestions - Skip suggestions refresh
     * @param {boolean} options.skipCommit - Skip commit UI refresh
     */
    Explorer.refreshAfterObjectChange = function(options = {}) {
        if (!options.skipTree && Explorer.buildTree) {
            Explorer.buildTree();
        }

        if (!options.skipTarget && Explorer.renderTargetPane) {
            Explorer.renderTargetPane();
        }

        if (!options.skipCenter && Explorer.syncCenterPaneAfterUndo && state.editedObject) {
            Explorer.syncCenterPaneAfterUndo();
        }

        if (!options.skipSuggestions && Explorer.loadAllSuggestions) {
            Explorer.loadAllSuggestions(true);
        }

        if (!options.skipCommit && window.updateCommitUI) {
            window.updateCommitUI();
        }
    };

})(window.Explorer);
