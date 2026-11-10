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
import { showToast, showConfirmDialog } from '../ui-notifications.js';
import { escapeHtml } from '../shared/escape.js';
import { updateUndoButton, updateNavCommitButton, commitCountFromInfo } from '../base.js';

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

// Failed reloads can repeat (polling, parallel callers); toast at most once per 10 s.
const LOAD_ERROR_TOAST_INTERVAL_MS = 10000;
let lastLoadErrorToast = 0;

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

    if (!objectsResult.success) {
        // Keep what is on screen: emptying allObjects would blank the tree and
        // validateTabs() would close every tab.
        const now = Date.now();
        if (now - lastLoadErrorToast > LOAD_ERROR_TOAST_INTERVAL_MS) {
            lastLoadErrorToast = now;
            showToast(`Could not load objects: ${objectsResult.error || 'unknown error'}`, 'error');
        }
        return;
    }

    state.allObjects = objectsResult.data || [];
    state.allFiles = filesResult.data?.files || [];
    state.existingFolders = foldersResult.data?.folders || [];

    // Store config roots from multi-root API response
    if (filesResult.data?.roots) {
        state.configRoots = filesResult.data.roots;
    }

    // Paths from the API are the original config locations whether or not a
    // staging session is active, so nothing here needs migrating when one
    // starts or ends.
    const primaryRoot = state.configRoots[0] || '';
    if (primaryRoot) {
        state.configPath = primaryRoot;
        state.configDisplayName = primaryRoot.split('/').pop() || '';
    }

    // Populate constants from backend metadata (once)
    if (metadataResult && metadataResult.success) {
        applyMetadata(metadataResult.payload);
        state.metadataLoaded = true;
    }

    // Validate open tabs against refreshed objects
    validateTabs();
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
        const info = infoResult.payload;
        let count = commitCountFromInfo(info);

        // Update object-level change tracking
        state.changedObjectKeys = new Set(info.changedObjectKeys || []);

        // Prune created keys that are no longer changed (deleted or undone)
        for (const key of state.createdObjectKeys) {
            if (!state.changedObjectKeys.has(key)) {
                state.createdObjectKeys.delete(key);
            }
        }

        updateUndoButton(info.undoCount || 0);

        // If no shadow changes, clear created keys and check git for external changes
        if (count === 0) {
            state.createdObjectKeys.clear();
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
    const diffData = result.payload;
    if (result.success && diffData?.files) {
        for (const f of diffData.files) {
            // abs_path is the same path /api/files and obj.source_file use,
            // so it identifies the file in any config root.
            state.changedFilesMap.set(f.abs_path, f.status);
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
        const msg = `<p>${conflicts.length} file(s) were modified externally:</p><ul>${conflicts.map(f => `<li>${escapeHtml(f)}</li>`).join('')}</ul><p>Force apply will overwrite. A backup is created first.</p>`;
        if (await showConfirmDialog({ title: 'Files changed outside the editor', message: msg, confirmText: 'Force Apply', type: 'danger', allowHtml: true })) {
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
        const info = result.payload;
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
        const info = result.payload;
        return commitCountFromInfo(info);
    }
    return 0;
}
