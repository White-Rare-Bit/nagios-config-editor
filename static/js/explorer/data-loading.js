/**
 * Nagios Bulk Editor - Data Loading Module (Shadow Copy Architecture)
 *
 * Handles API calls and data fetching. All mutations are server-side.
 * No client-side staging state — the shadow copy IS the staging.
 */

(function(Explorer) {
    'use strict';

    const CONFIG = {
        ANALYSIS_DEBOUNCE_MS: 500
    };

    let analysisDebounceTimer = null;
    let undoInProgress = false;

    /**
     * Trigger analysis update with debouncing (500ms)
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

        // Store original config display name (shadow dir is named "config" internally)
        if (filesResult.data?.config_display_name) {
            Explorer.state.configDisplayName = filesResult.data.config_display_name;
        }

        // Sync configPath with server (may change when shadow copy is created)
        const newConfigPath = filesResult.data?.config_path;
        if (newConfigPath && newConfigPath !== Explorer.state.configPath) {
            const oldPath = Explorer.state.configPath;
            Explorer.state.configPath = newConfigPath;

            // Migrate expanded folders/files and selected folder to new path prefix
            const migrateSet = (set) => {
                const migrated = new Set();
                for (const p of set) {
                    if (p === oldPath) {
                        migrated.add(newConfigPath);
                    } else if (p.startsWith(oldPath + '/')) {
                        migrated.add(newConfigPath + p.substring(oldPath.length));
                    } else {
                        migrated.add(p);
                    }
                }
                return migrated;
            };
            Explorer.state.expandedFolders = migrateSet(Explorer.state.expandedFolders);
            Explorer.state.expandedFiles = migrateSet(Explorer.state.expandedFiles);
            if (Explorer.state.selectedFolder === oldPath) {
                Explorer.state.selectedFolder = newConfigPath;
            } else if (Explorer.state.selectedFolder?.startsWith(oldPath + '/')) {
                Explorer.state.selectedFolder = newConfigPath + Explorer.state.selectedFolder.substring(oldPath.length);
            }

            // Migrate stable keys (source_file|type|name) in selections and tabs.
            // migrateSet works because source_file is the first component —
            // startsWith(oldPath + '/') matches and the rest (|type|name) carries over.
            Explorer.state.selectedKeys = migrateSet(Explorer.state.selectedKeys);

            if (Explorer.state.activeTabKey) {
                const migrated = migrateSet(new Set([Explorer.state.activeTabKey]));
                Explorer.state.activeTabKey = migrated.values().next().value;
            }
            if (Explorer.state.openTabs) {
                for (const tab of Explorer.state.openTabs) {
                    const migrated = migrateSet(new Set([tab.key]));
                    tab.key = migrated.values().next().value;
                }
            }

            // Migrate editedObject.source_file so center pane key matches reloaded data
            if (Explorer.state.editedObject) {
                const sf = Explorer.state.editedObject.source_file;
                if (sf === oldPath) {
                    Explorer.state.editedObject.source_file = newConfigPath;
                } else if (sf && sf.startsWith(oldPath + '/')) {
                    Explorer.state.editedObject.source_file = newConfigPath + sf.substring(oldPath.length);
                }
            }
        }

        // Populate constants from backend metadata (once)
        if (metadataResult && metadataResult.success) {
            Explorer.applyMetadata(metadataResult.data.data || metadataResult.data);
            Explorer.state.metadataLoaded = true;
        }

        // Validate open tabs against refreshed objects
        if (Explorer.validateTabs) {Explorer.validateTabs();}
    };

    // =============================================================================
    // Staging Headers
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

    // =============================================================================
    // Mutation Orchestrators
    // =============================================================================

    /**
     * Fetch staging info and update nav badges (commit count + undo button).
     */
    Explorer.updateBadges = async function() {
        const infoResult = await ApiClient.get('/api/staging/info', { silent: true });

        if (infoResult.success) {
            const info = infoResult.data;
            let count = info.totalCount || 0;

            if (typeof updateUndoButton === 'function') {
                updateUndoButton(info.undoCount || 0);
            }

            // If no shadow changes, check git for external changes
            if (count === 0) {
                const gitResult = await ApiClient.get('/api/git/status', { silent: true });
                if (gitResult.success && gitResult.data?.has_changes) {
                    count = gitResult.data.files.length;
                }
            }

            if (typeof updateNavCommitButton === 'function') {
                updateNavCommitButton(count);
            }
        }
    };

    /**
     * Load changed files from server diff and populate state.changedFilesMap.
     * Used by tree rendering to show modified/added/deleted indicators.
     */
    Explorer.loadChangedFiles = async function() {
        const result = await ApiClient.get('/api/staging/diff', { silent: true });
        Explorer.state.changedFilesMap.clear();
        if (result.success && result.data?.files) {
            for (const f of result.data.files) {
                Explorer.state.changedFilesMap.set(f.path, f.status);
            }
        }
    };

    /**
     * ORCHESTRATOR: Call after any mutation (frontend-initiated or server-sync).
     * Reloads data, rebuilds UI, updates badges, triggers debounced analysis.
     *
     * @param {Object} options - Passed through to rebuildUI
     */
    Explorer.afterFrontendMutation = async function(options = {}) {
        await Promise.all([Explorer.loadObjects(), Explorer.loadChangedFiles()]);
        Explorer.rebuildUI(options);
        Explorer.updateBadges();
        triggerAnalysisUpdate();
    };

    /**
     * ORCHESTRATOR: Call after server-originated changes (undo, apply).
     * Rebuilds UI, updates badges.
     *
     * @param {Object} options - Passed through to rebuildUI
     */
    Explorer.afterServerSync = async function(options = {}) {
        await Explorer.loadChangedFiles();
        Explorer.rebuildUI(options);
        Explorer.updateBadges();
        triggerAnalysisUpdate();
    };

    // =============================================================================
    // Staging API
    // =============================================================================

    /**
     * Clear staged changes — destroy shadow copy
     */
    Explorer.clearStagedChanges = async function() {
        const result = await ApiClient.del('/api/staging', { silent: true });

        if (result.success) {
            await Explorer.loadObjects();
            Explorer.afterServerSync();
        } else {
            Explorer.handleApiError('Failed to clear staged changes', result.error);
        }
    };

    /**
     * Apply all staged changes to disk
     * @returns {Promise<{success: boolean, message?: string, results?: object}>}
     */
    Explorer.applyAllStaged = async function() {
        const result = await ApiClient.post('/api/staging/apply', {}, { silent: true });

        if (result.success && result.data?.success) {
            // Reload fresh data from disk
            await Explorer.loadObjects();
            Explorer.afterServerSync();

            Explorer.showToast('Changes applied successfully', 'success');
            return { success: true, results: result.data };
        }
        const errorMsg = result.data?.error || result.error || 'Failed to apply changes';
        Explorer.showToast(errorMsg, 'error');
        return { success: false, message: errorMsg };
    };

    /**
     * Undo the last staged operation
     * @returns {Promise<{success: boolean, undone?: object, message?: string}>}
     */
    Explorer.undoLastAction = async function() {
        if (undoInProgress) {
            return { success: false, message: 'Undo already in progress' };
        }
        undoInProgress = true;

        try {
            const result = await ApiClient.post('/api/staging/undo', {}, { silent: true });

            if (result.success && result.data?.success) {
                await Explorer.loadObjects();
                Explorer.afterServerSync();

                const description = result.data.undone?.description || 'action';
                Explorer.showToast(`Undone: ${description}`, 'info');
                return { success: true, undone: result.data.undone };
            } else if (result.status === 404) {
                Explorer.showToast('Nothing to undo', 'info');
                return { success: false, message: 'Nothing to undo' };
            }
            const errorMsg = result.data?.error || result.error || 'Failed to undo';
            Explorer.showToast(errorMsg, 'error');
            return { success: false, message: errorMsg };
        } finally {
            undoInProgress = false;
        }
    };

    /**
     * Get count of undoable actions (server query)
     * @returns {Promise<number>}
     */
    Explorer.getUndoCount = async function() {
        const result = await ApiClient.get('/api/staging/info', { silent: true });
        if (result.success) {
            return result.data.undoCount || 0;
        }
        return 0;
    };

    /**
     * Get total count of all staged changes (server query)
     * @returns {Promise<number>}
     */
    Explorer.getTotalStagedCount = async function() {
        const result = await ApiClient.get('/api/staging/info', { silent: true });
        if (result.success) {
            return result.data.totalCount || 0;
        }
        return 0;
    };

})(window.Explorer);
