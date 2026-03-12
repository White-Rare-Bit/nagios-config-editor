/**
 * Nagios Bulk Editor - Data Loading Module (Shadow Copy Architecture)
 *
 * Handles API calls and data fetching. All mutations are server-side.
 * No client-side staging state — the shadow copy IS the staging.
 */

import { state } from './state.js';
import { applyMetadata } from './constants.js';
import { validateTabs } from './tab-manager.js'; // circular — safe (function-level)
import { rebuildUI } from './state-management.js'; // circular — safe (function-level)
import { loadAllSuggestions } from './analysis.js'; // circular — safe (function-level)
import { handleApiError } from './ui-utils.js';
import { ApiClient } from '../api-client.js';
import { showToast } from '../ui-notifications.js';
import { updateUndoButton, updateNavCommitButton } from '../base.js';

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
        loadAllSuggestions(true);
    }, CONFIG.ANALYSIS_DEBOUNCE_MS);
}

// =============================================================================
// Data Loading
// =============================================================================

/**
 * Load objects, files, and metadata from backend.
 * Metadata is fetched once (first load) and cached via metadataLoaded flag.
 */
export async function loadObjects() {
    const [objectsResult, filesResult, foldersResult, metadataResult] = await Promise.all([
        ApiClient.get('/api/objects?_=' + Date.now(), { silent: true }),
        ApiClient.get('/api/files?_=' + Date.now(), { silent: true }),
        ApiClient.get('/api/folders?_=' + Date.now(), { silent: true }),
        state.metadataLoaded
            ? Promise.resolve(null)
            : ApiClient.get('/api/metadata', { silent: true })
    ]);

    state.allObjects = objectsResult.data || [];
    state.allFiles = filesResult.data?.files || [];
    state.existingFolders = foldersResult.data?.folders || [];

    // Store original config display name (shadow dir is named "config" internally)
    if (filesResult.data?.config_display_name) {
        state.configDisplayName = filesResult.data.config_display_name;
    }

    // Sync configPath with server (may change when shadow copy is created)
    const newConfigPath = filesResult.data?.config_path;
    if (newConfigPath && newConfigPath !== state.configPath) {
        const oldPath = state.configPath;
        state.configPath = newConfigPath;

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
        state.expandedFolders = migrateSet(state.expandedFolders);
        state.expandedFiles = migrateSet(state.expandedFiles);
        if (state.selectedFolder === oldPath) {
            state.selectedFolder = newConfigPath;
        } else if (state.selectedFolder?.startsWith(oldPath + '/')) {
            state.selectedFolder = newConfigPath + state.selectedFolder.substring(oldPath.length);
        }

        // Migrate stable keys (source_file|type|name) in selections and tabs.
        // migrateSet works because source_file is the first component —
        // startsWith(oldPath + '/') matches and the rest (|type|name) carries over.
        state.selectedKeys = migrateSet(state.selectedKeys);

        if (state.activeTabKey) {
            const migrated = migrateSet(new Set([state.activeTabKey]));
            state.activeTabKey = migrated.values().next().value;
        }
        if (state.openTabs) {
            for (const tab of state.openTabs) {
                const migrated = migrateSet(new Set([tab.key]));
                tab.key = migrated.values().next().value;
            }
        }

        // Migrate editedObject.source_file so center pane key matches reloaded data
        if (state.editedObject) {
            const sf = state.editedObject.source_file;
            if (sf === oldPath) {
                state.editedObject.source_file = newConfigPath;
            } else if (sf && sf.startsWith(oldPath + '/')) {
                state.editedObject.source_file = newConfigPath + sf.substring(oldPath.length);
            }
        }
    }

    // Populate constants from backend metadata (once)
    if (metadataResult && metadataResult.success) {
        applyMetadata(metadataResult.data.data || metadataResult.data);
        state.metadataLoaded = true;
    }

    // Validate open tabs against refreshed objects
    validateTabs();
}

// =============================================================================
// Staging Headers
// =============================================================================

/**
 * Get headers for staging API calls
 */
export function getStagingHeaders() {
    return {
        'Content-Type': 'application/json',
        'X-Session-Id': state.sessionId
    };
}

// =============================================================================
// Mutation Orchestrators
// =============================================================================

/**
 * Fetch staging info and update nav badges (commit count + undo button).
 */
export async function updateBadges() {
    const infoResult = await ApiClient.get('/api/staging/info', { silent: true });

    if (infoResult.success) {
        const info = infoResult.data.data || infoResult.data;
        let count = info.totalCount || 0;

        // Update object-level change tracking
        state.changedObjectKeys = new Set(info.changedObjectKeys || []);

        updateUndoButton(info.undoCount || 0);

        // If no shadow changes, check git for external changes
        if (count === 0) {
            const gitResult = await ApiClient.get('/api/git/status', { silent: true });
            if (gitResult.success && gitResult.data?.has_changes) {
                count = gitResult.data.files.length;
            }
        }

        updateNavCommitButton(count);
    }
}

/**
 * Load changed files from server diff and populate state.changedFilesMap.
 * Used by tree rendering to show modified/added/deleted indicators.
 */
export async function loadChangedFiles() {
    const result = await ApiClient.get('/api/staging/diff', { silent: true });
    state.changedFilesMap.clear();
    const diffData = result.data?.data || result.data;
    if (result.success && diffData?.files) {
        for (const f of diffData.files) {
            state.changedFilesMap.set(f.path, f.status);
        }
    }
}

/**
 * ORCHESTRATOR: Call after any mutation (frontend-initiated or server-sync).
 * Reloads data, rebuilds UI, updates badges, triggers debounced analysis.
 *
 * @param {Object} options - Passed through to rebuildUI
 */
export async function afterFrontendMutation(options = {}) {
    await Promise.all([loadObjects(), loadChangedFiles(), updateBadges()]);
    rebuildUI(options);
    triggerAnalysisUpdate();
}

/**
 * ORCHESTRATOR: Call after server-originated changes (undo, apply).
 * Rebuilds UI, updates badges.
 *
 * @param {Object} options - Passed through to rebuildUI
 */
export async function afterServerSync(options = {}) {
    await Promise.all([loadChangedFiles(), updateBadges()]);
    rebuildUI(options);
    triggerAnalysisUpdate();
}

// =============================================================================
// Staging API
// =============================================================================

/**
 * Clear staged changes — destroy shadow copy
 */
export async function clearStagedChanges() {
    const result = await ApiClient.del('/api/staging', { silent: true });

    if (result.success) {
        await loadObjects();
        afterServerSync();
    } else {
        handleApiError('Failed to clear staged changes', result.error);
    }
}

/**
 * Apply all staged changes to disk
 * @returns {Promise<{success: boolean, message?: string, results?: object}>}
 */
export async function applyAllStaged(force = false) {
    const url = force ? '/api/staging/apply?force=true' : '/api/staging/apply';
    const result = await ApiClient.post(url, {}, { silent: true });

    if (result.success && result.data?.success) {
        // Reload fresh data from disk
        await loadObjects();
        afterServerSync();

        showToast('Changes applied successfully', 'success');
        return { success: true, results: result.data };
    }

    // Check for conflict response (409)
    if (result.data?.conflicts) {
        const conflicts = result.data.conflicts;
        const fileList = conflicts.map(f => `  \u2022 ${f}`).join('\n');
        const msg = `${conflicts.length} file(s) were modified externally:\n\n${fileList}\n\nForce apply will overwrite. A backup is created first.`;
        if (confirm(msg)) {
            return applyAllStaged(true);
        }
        showToast('Apply cancelled due to conflicts', 'warning');
        return { success: false, message: 'Conflicts detected' };
    }

    const errorMsg = result.data?.error || result.error || 'Failed to apply changes';
    showToast(errorMsg, 'error');
    return { success: false, message: errorMsg };
}

/**
 * Undo the last staged operation
 * @returns {Promise<{success: boolean, undone?: object, message?: string}>}
 */
export async function undoLastAction() {
    if (undoInProgress) {
        return { success: false, message: 'Undo already in progress' };
    }
    undoInProgress = true;

    try {
        const result = await ApiClient.post('/api/staging/undo', {}, { silent: true });

        if (result.success && result.data?.success) {
            await loadObjects();
            afterServerSync();

            const description = result.data.undone?.description || 'action';
            showToast(`Undone: ${description}`, 'info');
            return { success: true, undone: result.data.undone };
        } else if (result.status === 404) {
            showToast('Nothing to undo', 'info');
            return { success: false, message: 'Nothing to undo' };
        }
        const errorMsg = result.data?.error || result.error || 'Failed to undo';
        showToast(errorMsg, 'error');
        return { success: false, message: errorMsg };
    } finally {
        undoInProgress = false;
    }
}

/**
 * Get count of undoable actions (server query)
 * @returns {Promise<number>}
 */
export async function getUndoCount() {
    const result = await ApiClient.get('/api/staging/info', { silent: true });
    if (result.success) {
        const info = result.data.data || result.data;
        return info.undoCount || 0;
    }
    return 0;
}

/**
 * Get total count of all staged changes (server query)
 * @returns {Promise<number>}
 */
export async function getTotalStagedCount() {
    const result = await ApiClient.get('/api/staging/info', { silent: true });
    if (result.success) {
        const info = result.data.data || result.data;
        return info.totalCount || 0;
    }
    return 0;
}
