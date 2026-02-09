/**
 * Nagios Bulk Editor - Data Loading Module
 *
 * Handles API calls, staging synchronization, and data fetching.
 */

(function(Explorer) {
    'use strict';

    // Configuration constants
    const CONFIG = {
        ANALYSIS_DEBOUNCE_MS: 500,      // Debounce for analysis updates after staging changes
        SAVE_DEBOUNCE_RETRY_MS: 100,    // Retry delay when save is in progress
        STAGING_POLL_INTERVAL_MS: 3000  // Interval for polling staging changes
    };

    // Module-local state
    let stagingPollInterval = null;
    let lastStagingTimestamp = null;
    let isSavingStaging = false;
    let saveDebounceTimer = null;
    let saveInProgress = false;
    let analysisDebounceTimer = null;
    let isPollingInProgress = false;  // C-02: Guard against concurrent polling

    /**
     * Trigger analysis update with debouncing (500ms)
     * Called after staging changes to update suggestions badge
     */
    function triggerAnalysisUpdate() {
        if (analysisDebounceTimer) {
            clearTimeout(analysisDebounceTimer);
        }
        analysisDebounceTimer = setTimeout(() => {
            if (typeof Explorer.loadAllSuggestions === 'function') {
                Explorer.loadAllSuggestions(true);
            }
        }, CONFIG.ANALYSIS_DEBOUNCE_MS);
    }

    // =============================================================================
    // Data Loading
    // =============================================================================

    /**
     * Load objects, files, and metadata from backend.
     * Metadata is fetched once (first load) and cached via metadataLoaded flag.
     */
    Explorer.loadObjects = async function() {
        const [objectsResult, filesResult, foldersResult, metadataResult] = await Promise.all([
            ApiClient.get('/api/objects?_=' + Date.now(), { silent: true }),
            ApiClient.get('/api/files?_=' + Date.now(), { silent: true }),
            ApiClient.get('/api/folders?_=' + Date.now(), { silent: true }),
            Explorer.state.metadataLoaded
                ? Promise.resolve(null)
                : ApiClient.get('/api/metadata', { silent: true })
        ]);

        Explorer.state.allObjects = objectsResult.data || [];
        Explorer.state.allFiles = filesResult.data?.files || [];
        Explorer.state.existingFolders = foldersResult.data?.folders || [];

        // Populate constants from backend metadata (once)
        if (metadataResult && metadataResult.success) {
            Explorer.applyMetadata(metadataResult.data);
            Explorer.state.metadataLoaded = true;
        }
    };

    // =============================================================================
    // Staging API
    // =============================================================================

    /**
     * Get headers for staging API calls
     */
    Explorer.getStagingHeaders = function() {
        return {
            'Content-Type': 'application/json',
            'X-Session-Id': Explorer.state.sessionId
        };
    };

    /**
     * Save staged changes to server (true staging - no disk writes)
     */
    Explorer.saveStagedChanges = async function() {
        // Debounce
        if (saveDebounceTimer) {
            clearTimeout(saveDebounceTimer);
        }

        if (saveInProgress) {
            saveDebounceTimer = setTimeout(() => Explorer.saveStagedChanges(), CONFIG.SAVE_DEBOUNCE_RETRY_MS);
            return;
        }

        saveInProgress = true;
        isSavingStaging = true;

        try {
            const state = Explorer.state;

            // Get user identity (from global function if available)
            const identity = typeof getUserIdentity === 'function' ? getUserIdentity() : {};

            const data = {
                sessionId: state.sessionId,
                userName: identity.userName || '',
                userEmail: identity.userEmail || '',
                // Object operations
                pendingEdits: Object.fromEntries(state.pendingEdits),
                stagedMoves: Object.fromEntries(state.stagedMoves),
                stagedCreations: state.stagedCreations,
                newFiles: Array.from(state.newFiles),
                stagedObjectDeletions: Array.from(state.stagedObjectDeletions),
                // File/folder operations
                stagedFileCreations: state.stagedFileCreations,
                stagedFileDeletions: state.stagedFileDeletions,
                stagedFileMoves: state.stagedFileMoves,
                stagedFolderCreations: state.stagedFolderCreations,
                stagedFolderDeletions: state.stagedFolderDeletions,
                stagedFolderMoves: state.stagedFolderMoves
            };

            const result = await ApiClient.post('/api/staging', data, { silent: true });

            if (result.success) {
                // Update timestamp and undo count
                const infoResult = await ApiClient.get('/api/staging/info', { silent: true });
                if (infoResult.success) {
                    lastStagingTimestamp = infoResult.data.lastModified;
                    // Sync undo count with backend
                    if (typeof updateUndoButton === 'function') {
                        updateUndoButton(infoResult.data.undoCount || 0);
                    }
                }

                if (typeof checkPendingChanges === 'function') {
                    checkPendingChanges();
                }

                // Trigger analysis to update suggestions badge
                triggerAnalysisUpdate();
            } else if (result.status === 423) {
                Explorer.showToast(result.data?.error || 'Staging is locked by another user', 'error');
                window.isEditingLocked = true;
                Explorer.updateEditingLockedUI();
            } else {
                console.error('Failed to save staging to server');
                Explorer.showToast('Failed to save changes to server.', 'error');
            }
        } finally {
            isSavingStaging = false;
            saveInProgress = false;
        }
    };

    /**
     * Load staged changes from server
     */
    Explorer.loadStagedChanges = async function(checkLockState = true) {
        const result = await ApiClient.get('/api/staging', { silent: true });
        const state = Explorer.state;

        if (!result.success) {
            Explorer.handleApiError('Failed to load staged changes', result.error);
            return;
        }

        if (result.data.hasStaging && result.data.staging) {
            const data = result.data.staging;

            state.currentStagingOwner = data.sessionId || null;

            if (checkLockState) {
                window.isEditingLocked = state.currentStagingOwner &&
                                         state.currentStagingOwner !== state.sessionId;
                Explorer.updateEditingLockedUI();
            }

            // Object operations - dict format: {key: entry, ...}
            if (data.pendingEdits) {
                const validEdits = Object.entries(data.pendingEdits).filter(([key, edit]) => {
                    return edit && edit.object && edit.object.source_file;
                });
                state.pendingEdits = new Map(validEdits);
            }
            if (data.stagedMoves) {
                state.stagedMoves = new Map(Object.entries(data.stagedMoves));
            }
            if (data.stagedCreations) {
                state.stagedCreations = data.stagedCreations;
            }
            if (data.newFiles) {
                state.newFiles = new Set(data.newFiles);
            }
            if (data.stagedObjectDeletions) {
                state.stagedObjectDeletions = new Set(data.stagedObjectDeletions);
            }

            // File/folder operations
            state.stagedFileCreations = data.stagedFileCreations || [];
            state.stagedFileDeletions = data.stagedFileDeletions || [];
            state.stagedFileMoves = data.stagedFileMoves || [];
            state.stagedFolderCreations = data.stagedFolderCreations || [];
            state.stagedFolderDeletions = data.stagedFolderDeletions || [];
            state.stagedFolderMoves = data.stagedFolderMoves || [];

            // Undo stack
            state.undoStack = data.undoStack || [];

            lastStagingTimestamp = data.lastModified;
        } else {
            // No staging data from backend - clear local staging state
            Explorer.resetStagingState();
            if (checkLockState && window.isEditingLocked) {
                window.isEditingLocked = false;
                state.currentStagingOwner = null;
                Explorer.updateEditingLockedUI();
            }
        }
    };

    /**
     * Clear staged changes
     */
    Explorer.clearStagedChanges = async function() {
        const result = await ApiClient.del('/api/staging', { silent: true });

        if (result.success) {
            Explorer.resetStagingState();
            window.isEditingLocked = false;
            Explorer.state.currentStagingOwner = null;
            lastStagingTimestamp = null;

            Explorer.updateEditingLockedUI();
            Explorer.updateCommitUI();
        } else {
            Explorer.handleApiError('Failed to clear staged changes', result.error);
        }
    };

    /**
     * Start polling for staging changes
     */
    Explorer.startStagingPoll = function() {
        if (stagingPollInterval) return;

        stagingPollInterval = setInterval(async () => {
            // C-02: Prevent concurrent polling - skip if another poll or save is in progress
            if (isSavingStaging || isPollingInProgress) return;

            isPollingInProgress = true;
            try {
                const result = await ApiClient.get('/api/staging/info', { silent: true });

                if (result.success) {
                    const info = result.data;

                    if (info.lastModified && info.lastModified !== lastStagingTimestamp) {
                        const state = Explorer.state;

                        // If user is actively editing an object, don't disrupt them
                        if (state.editedObject) {
                            // Mark that external changes are pending
                            state.externalChangePending = true;
                            Explorer.showToast('External changes detected. Save or cancel your edit to refresh.', 'info');
                            return;
                        }

                        await Explorer.loadStagedChanges(false);
                        lastStagingTimestamp = info.lastModified;

                        // Centralized refresh ensures all UI components stay in sync
                        // Suggestions now filter by stagedObjectDeletions, so polling won't resurrect deleted objects
                        Explorer.refreshAfterObjectChange();
                    }
                }
            } finally {
                isPollingInProgress = false;
            }
        }, CONFIG.STAGING_POLL_INTERVAL_MS);
    };

    /**
     * Stop polling for staging changes
     */
    Explorer.stopStagingPoll = function() {
        if (stagingPollInterval) {
            clearInterval(stagingPollInterval);
            stagingPollInterval = null;
        }
    };

    /**
     * Check and apply pending external changes after user finishes editing
     * Call this whenever state.editedObject is set to null
     */
    Explorer.checkPendingExternalChanges = async function() {
        const state = Explorer.state;
        if (state.externalChangePending) {
            state.externalChangePending = false;
            await Explorer.loadStagedChanges(false);
            Explorer.buildTree();
            Explorer.renderTargetPane();
            Explorer.updateCommitUI();
        }
    };

    // =============================================================================
    // Virtual Tree & Apply API
    // =============================================================================

    /**
     * Load virtual tree (merged view with staged changes applied)
     * This replaces loadObjects() for displaying the tree with pending changes
     */
    Explorer.loadVirtualTree = async function() {
        const result = await ApiClient.get('/api/staging/virtual-tree?_=' + Date.now(), { silent: true });

        if (!result.success) {
            console.error('Failed to load virtual tree:', result.error);
            // Fall back to regular loadObjects but warn user
            Explorer.showToast('Failed to load merged view. Showing disk state only - staged changes may not be visible.', 'warning');
            return Explorer.loadObjects();
        }

        const data = result.data;
        const state = Explorer.state;

        state.allObjects = data.objects || [];
        state.allFiles = data.files || [];
        state.existingFolders = data.folders || [];

        // Files/folders may have staged flags (_staged_new, _staged_deleted, etc.)
        // These can be used for visual indicators in the tree
    };

    /**
     * Apply all staged changes to disk
     * @returns {Promise<{success: boolean, message?: string, results?: object}>}
     */
    Explorer.applyAllStaged = async function() {
        const result = await ApiClient.post('/api/staging/apply', {}, { silent: true });

        if (result.success && result.data?.success) {
            // Clear local staging state
            Explorer.resetStagingState();
            lastStagingTimestamp = null;

            // Reload fresh data from disk
            await Explorer.loadObjects();

            Explorer.buildTree();
            Explorer.renderTargetPane();
            Explorer.updateCommitUI();

            Explorer.showToast('Changes applied successfully', 'success');
            return { success: true, results: result.data };
        } else {
            const errorMsg = result.data?.error || result.error || 'Failed to apply changes';
            Explorer.showToast(errorMsg, 'error');
            return { success: false, message: errorMsg };
        }
    };

    /**
     * Undo the last staged operation
     * @returns {Promise<{success: boolean, undone?: object, message?: string}>}
     */
    Explorer.undoLastAction = async function() {
        const result = await ApiClient.post('/api/staging/undo', {}, { silent: true });

        if (result.success && result.data?.success) {
            // Reload objects from server to get original values
            // (staged edits mutate state.allObjects, so we need fresh data)
            await Explorer.loadObjects();

            // Reload staged changes to get updated state
            await Explorer.loadStagedChanges(false);

            // Centralized refresh ensures all UI components stay in sync
            // Center pane synced via syncCenterPaneAfterUndo which refreshAfterObjectChange calls conditionally
            Explorer.refreshAfterObjectChange();

            const description = result.data.undone?.description || 'action';
            Explorer.showToast(`Undone: ${description}`, 'info');
            return { success: true, undone: result.data.undone };
        } else if (result.status === 404) {
            Explorer.showToast('Nothing to undo', 'info');
            return { success: false, message: 'Nothing to undo' };
        } else {
            const errorMsg = result.data?.error || result.error || 'Failed to undo';
            Explorer.showToast(errorMsg, 'error');
            return { success: false, message: errorMsg };
        }
    };

    /**
     * Check for conflicts between staged changes and current file state
     * @returns {Promise<{hasConflicts: boolean, conflicts: Array}>}
     */
    Explorer.checkConflicts = async function() {
        const result = await ApiClient.get('/api/staging/conflicts', { silent: true });

        if (result.success) {
            return {
                hasConflicts: result.data.hasConflicts || false,
                conflicts: result.data.conflicts || []
            };
        }
        Explorer.handleApiError('Failed to check conflicts', result.error);
        return { hasConflicts: false, conflicts: [] };
    };

    /**
     * Get extended staging info including counts
     * @returns {Promise<object>}
     */
    Explorer.getStagingInfoExtended = async function() {
        const result = await ApiClient.get('/api/staging/info', { silent: true });
        if (result.success) {
            return result.data;
        }
        Explorer.handleApiError('Failed to get extended staging info', result.error);
        return null;
    };

    /**
     * Get count of undoable actions
     * @returns {number}
     */
    Explorer.getUndoCount = function() {
        return Explorer.state.undoStack.length;
    };

    /**
     * Get total count of all staged changes
     * @returns {number}
     */
    Explorer.getTotalStagedCount = function() {
        const state = Explorer.state;
        return state.pendingEdits.size +
               state.stagedMoves.size +
               state.stagedCreations.length +
               state.stagedObjectDeletions.size +
               state.stagedFileCreations.length +
               state.stagedFileDeletions.length +
               state.stagedFileMoves.length +
               state.stagedFolderCreations.length +
               state.stagedFolderDeletions.length +
               state.stagedFolderMoves.length;
    };

})(window.Explorer);
