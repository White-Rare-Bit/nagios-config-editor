/**
 * Nagios Bulk Editor - Base JavaScript
 *
 * Shared functionality across all pages:
 * - Session/identity management
 * - Lock status handling
 * - Toast notifications
 * - Confirmation dialogs
 * - Global commit dialog
 * - Git operations UI
 */

// =============================================================================
// Consolidated State
// =============================================================================

const baseState = {
    // Lock status
    isEditingLocked: false,
    lockOwner: null,
    lockUserName: null,
    lockUserEmail: null,
    lockPollInterval: null,

    // Commit dialog
    commitContextLines: 3,
    diffData: null,
    referenceData: null,
    gitResultNeedsReload: false,

    // Git-only commit
    gitOnlyChanges: null,
    gitOnlyContextLines: 3,

    // Reference analysis
    currentRefData: null,

    // C-10: Pending commit message for retry after failed git commit
    pendingCommitMessage: null
};

// Global lock state alias - used by explorer/data-loading.js for lock status checks
window.isEditingLocked = false;

// =============================================================================
// Debug Logger - sends debug logs to backend for file logging
// =============================================================================

const DebugLogger = (function() {
    'use strict';

    // Set to true to enable debug logging to backend
    const ENABLED = true;

    // Buffer logs and send in batches to reduce HTTP requests
    let logBuffer = [];
    let flushTimeout = null;
    const FLUSH_INTERVAL = 2000; // 2 seconds

    function log(level, message, context = {}) {
        if (!ENABLED) return;

        logBuffer.push({ level, message, context, timestamp: new Date().toISOString() });

        // Schedule flush if not already scheduled
        if (!flushTimeout) {
            flushTimeout = setTimeout(flush, FLUSH_INTERVAL);
        }
    }

    async function flush() {
        flushTimeout = null;
        if (logBuffer.length === 0) return;

        const logsToSend = logBuffer;
        logBuffer = [];

        // Send each log entry (could batch in future if needed)
        for (const entry of logsToSend) {
            try {
                await fetch('/api/logs/frontend', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(entry)
                });
            } catch (e) {
                // Silently fail - don't break the app for logging failures
            }
        }
    }

    // Flush on page unload
    window.addEventListener('beforeunload', () => {
        if (logBuffer.length > 0) {
            // Use sendBeacon for reliable delivery on page unload
            const data = JSON.stringify(logBuffer.map(entry => ({
                level: entry.level,
                message: entry.message,
                context: entry.context
            })));
            navigator.sendBeacon('/api/logs/frontend', new Blob([data], { type: 'application/json' }));
        }
    });

    return {
        debug: (message, context) => log('debug', message, context),
        info: (message, context) => log('info', message, context),
        warning: (message, context) => log('warning', message, context),
        error: (message, context) => log('error', message, context)
    };
})();

// =============================================================================
// Session & Identity Management
// =============================================================================

function getSessionId() {
    let sessionId = localStorage.getItem('nagios_session_id');
    if (!sessionId) {
        sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('nagios_session_id', sessionId);
    }
    return sessionId;
}

function getUserIdentity() {
    return {
        userName: localStorage.getItem('nagios_user_name') || '',
        userEmail: localStorage.getItem('nagios_user_email') || ''
    };
}

function setUserIdentity(name, email) {
    localStorage.setItem('nagios_user_name', name);
    localStorage.setItem('nagios_user_email', email);
}

function hasUserIdentity() {
    const identity = getUserIdentity();
    return !!(identity.userName && identity.userEmail);
}

function getStagingHeaders() {
    return {
        'Content-Type': 'application/json',
        'X-Session-Id': getSessionId()
    };
}

// =============================================================================
// Lock Status Management
// =============================================================================

async function checkLockStatus() {
    const result = await ApiClient.get('/api/staging/lock', { silent: true });

    if (!result.success) {
        console.error('Failed to check lock status:', result.error);
        return null;
    }

    const data = result.data;
    baseState.isEditingLocked = data.locked && !data.isOwner;
    baseState.lockOwner = data.owner;
    baseState.lockUserName = data.userName;
    baseState.lockUserEmail = data.userEmail;
    // Update legacy alias
    window.isEditingLocked = baseState.isEditingLocked;

    updateLockBannerUI();
    return data;
}

function updateLockBannerUI() {
    const banner = document.getElementById('lockBanner');
    const bannerText = document.getElementById('lockBannerText');
    if (banner) {
        if (baseState.isEditingLocked) {
            banner.classList.remove('u-hidden');
            banner.classList.add('lock-banner-visible');
            if (bannerText) {
                let userInfo = escapeHtml(baseState.lockUserName) || 'Another user';
                if (baseState.lockUserEmail) {
                    userInfo += ` (${escapeHtml(baseState.lockUserEmail)})`;
                }
                bannerText.innerHTML = `<strong>${userInfo}</strong> has pending changes. Commit or discard to edit.`;
            }
            document.body.classList.add('editing-locked');
        } else {
            banner.classList.add('u-hidden');
            banner.classList.remove('lock-banner-visible');
            document.body.classList.remove('editing-locked');
        }
    }
}

async function breakLock() {
    const confirmed = await showConfirmDialog({
        title: 'Break Lock',
        message: 'Are you sure you want to break the lock? This will discard the other user\'s pending changes.',
        confirmText: 'Break Lock',
        cancelText: 'Cancel',
        type: 'danger'
    });

    if (!confirmed) return;

    const result = await ApiClient.post('/api/staging/lock/break', {}, { silent: true });

    if (result.success && result.data?.success) {
        baseState.isEditingLocked = false;
        baseState.lockOwner = null;
        baseState.lockUserName = null;
        baseState.lockUserEmail = null;
        window.isEditingLocked = false;
        updateLockBannerUI();
        updateNavCommitButton(0);

        if (result.data.gitDiscarded) {
            showGitOperationResult('Discard All Changes', 'git checkout -- . && git clean -fd', true,
                'All uncommitted changes have been discarded.');
        } else {
            showToast('Lock broken - staging cleared', 'success');
        }

        if (typeof onLockCleared === 'function') {
            onLockCleared();
        }
    } else {
        showToast(result.data?.error || result.error || 'Failed to break lock', 'error');
    }
}

// =============================================================================
// Toast Notifications
// =============================================================================

function showToast(message, type = 'info', duration = 3000) {
    const lowerMessage = message.toLowerCase();

    const isImportantMessage = lowerMessage.includes('discarded') ||
                               lowerMessage.includes('committed') ||
                               lowerMessage.includes('valid') ||
                               lowerMessage.includes('restored') ||
                               lowerMessage.includes('cleared') ||
                               lowerMessage.includes('wiped') ||
                               lowerMessage.includes('configure') ||
                               lowerMessage.includes('settings') ||
                               lowerMessage.includes('already exists') ||
                               lowerMessage.includes('duplicate') ||
                               lowerMessage.includes('cannot contain');

    // Always show error and warning messages - they indicate something user should know
    if (type === 'error' || type === 'warning') {
        // Allow through
    } else if (type === 'info' || type === 'success') {
        if (!isImportantMessage) {
            return null;
        }
    }

    const container = document.getElementById('toastContainer');
    const icons = {
        success: '<i class="fa-solid fa-check"></i>',
        error: '<i class="fa-solid fa-xmark"></i>',
        warning: '<i class="fa-solid fa-triangle-exclamation"></i>',
        info: '<i class="fa-solid fa-circle-info"></i>'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${escapeHtml(message)}</span>
        <button class="toast-close" data-action="close-toast">&times;</button>
    `;

    container.appendChild(toast);

    if (duration > 0) {
        setTimeout(() => {
            toast.classList.add('hiding');
            setTimeout(() => toast.remove(), 200);
        }, duration);
    }

    return toast;
}

// =============================================================================
// Utility Functions
// =============================================================================

// escapeHtml() is defined in app.js (loaded first) - use that global function

function escapeRegex(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeJs(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r');
}

// =============================================================================
// Confirmation Dialog
// =============================================================================

function showConfirmDialog(options = {}) {
    return new Promise((resolve) => {
        const {
            title = 'Confirm',
            message = 'Are you sure?',
            confirmText = 'Confirm',
            cancelText = 'Cancel',
            type = 'warning',
            showCancel = true,
            allowHtml = false
        } = options;

        const overlay = document.getElementById('confirmDialogOverlay');
        const icon = document.getElementById('confirmDialogIcon');
        const titleEl = document.getElementById('confirmDialogTitle');
        const messageEl = document.getElementById('confirmDialogMessage');
        const confirmBtn = document.getElementById('confirmDialogConfirm');
        const cancelBtn = document.getElementById('confirmDialogCancel');

        titleEl.textContent = title;
        if (allowHtml || message.includes('<')) {
            messageEl.innerHTML = message;
        } else {
            messageEl.textContent = message;
        }
        confirmBtn.textContent = confirmText;
        cancelBtn.textContent = cancelText;
        cancelBtn.classList.toggle('u-hidden', !showCancel);

        icon.className = 'confirm-dialog-icon ' + type;
        confirmBtn.className = 'nbe-btn nbe-btn--sm ' + (type === 'danger' ? 'nbe-btn--danger' : 'nbe-btn--primary');

        if (type === 'info') {
            icon.innerHTML = '<i class="fa-solid fa-circle-info"></i>';
        } else {
            icon.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
        }

        overlay.classList.add('visible');

        function handleConfirm() {
            cleanup();
            resolve(true);
        }

        function handleCancel() {
            cleanup();
            resolve(false);
        }

        function handleKeydown(e) {
            if (e.key === 'Escape') {
                handleCancel();
            } else if (e.key === 'Enter') {
                handleConfirm();
            }
        }

        function handleOverlayClick(e) {
            if (e.target === overlay) {
                handleCancel();
            }
        }

        function cleanup() {
            overlay.classList.remove('visible');
            confirmBtn.removeEventListener('click', handleConfirm);
            cancelBtn.removeEventListener('click', handleCancel);
            document.removeEventListener('keydown', handleKeydown);
            overlay.removeEventListener('click', handleOverlayClick);
        }

        confirmBtn.addEventListener('click', handleConfirm);
        cancelBtn.addEventListener('click', handleCancel);
        document.addEventListener('keydown', handleKeydown);
        overlay.addEventListener('click', handleOverlayClick);

        confirmBtn.focus();
    });
}

// =============================================================================
// Loading State Utilities
// =============================================================================

/**
 * Set loading state on a button
 * @param {HTMLElement|string} buttonOrSelector - Button element or CSS selector
 * @param {boolean} isLoading - Whether to show loading state
 * @param {string} [loadingText] - Optional text to show while loading
 */
function setButtonLoading(buttonOrSelector, isLoading, loadingText = null) {
    const button = typeof buttonOrSelector === 'string'
        ? document.querySelector(buttonOrSelector)
        : buttonOrSelector;

    if (!button) return;

    if (isLoading) {
        button.classList.add('loading');
        button.disabled = true;
        if (loadingText) {
            button.dataset.originalText = button.textContent;
            button.textContent = loadingText;
        }
    } else {
        button.classList.remove('loading');
        button.disabled = false;
        if (button.dataset.originalText) {
            button.textContent = button.dataset.originalText;
            delete button.dataset.originalText;
        }
    }
}

/**
 * Show a loading state in a container
 * @param {HTMLElement|string} containerOrSelector - Container element or CSS selector
 * @param {string} [message='Loading...'] - Message to display
 */
function showLoadingState(containerOrSelector, message = 'Loading...') {
    const container = typeof containerOrSelector === 'string'
        ? document.querySelector(containerOrSelector)
        : containerOrSelector;

    if (!container) return;

    container.innerHTML = `
        <div class="loading-state">
            <div class="loading-state-spinner"></div>
            <div class="loading-state-text">${escapeHtml(message)}</div>
        </div>
    `;
}

/**
 * Simple POST wrapper for API calls
 * @param {string} url - API endpoint
 * @param {Object} data - Data to send
 * @returns {Promise<Object>} Response data
 */
async function apiPost(url, data = {}) {
    const response = await fetch(url, {
        method: 'POST',
        headers: getStagingHeaders(),
        body: JSON.stringify(data)
    });
    return response.json();
}

/**
 * Wrap an async action with button loading state
 * @param {HTMLElement} button - Button element
 * @param {Function} action - Async function to execute
 * @param {string} [loadingText] - Text to show while loading
 */
async function withLoadingButton(button, action, loadingText = null) {
    setButtonLoading(button, true, loadingText);
    try {
        return await action();
    } finally {
        setButtonLoading(button, false);
    }
}

// =============================================================================
// Global Commit Dialog
// =============================================================================

function handleCommitClick() {
    showGlobalCommitDialog();
}

async function showGlobalCommitDialog() {
    const overlay = document.getElementById('globalCommitOverlay');
    const content = document.getElementById('globalCommitContent');

    overlay.classList.add('visible');
    content.innerHTML = '<div class="dialog-loading">Loading changes...</div>';

    const [diffResult, refResult] = await Promise.all([
        ApiClient.get('/api/staging/diff', { silent: true }),
        ApiClient.get('/api/staging/analyze-references', { silent: true })
    ]);

    if (!diffResult.success) {
        content.innerHTML = `<div class="commit-empty commit-error-text">Error loading changes: ${escapeHtml(diffResult.error)}</div>`;
        return;
    }

    const result = diffResult.data;
    baseState.referenceData = refResult.data || {};

    const isGitConfigured = hasUserIdentity();

    if (!result.hasChanges) {
        content.innerHTML = '<div class="commit-empty">No pending changes.</div>';
        return;
    }

    baseState.diffData = result;
    content.innerHTML = await buildGlobalCommitDialogHtml(result, baseState.referenceData, isGitConfigured);

    document.querySelectorAll('#globalCommitContent .commit-item-header').forEach(header => {
        header.addEventListener('click', () => {
            header.closest('.commit-item').classList.toggle('expanded');
        });
    });
}

async function buildGlobalCommitDialogHtml(data, refData = null, isGitConfigured = true) {
    const staging = data.staging || {};
    const allObjects = data.objects;
    const configPath = data.configPath;
    const existingFolders = data.existingFolders || [];
    const gitChanges = data.gitChanges || [];
    const hasGitChanges = data.hasGitChanges || false;

    const pendingEdits = staging.pendingEdits || {};
    const stagedMoves = staging.stagedMoves || {};
    const stagedCreations = staging.stagedCreations || [];
    const stagedObjectDeletions = staging.stagedObjectDeletions || [];

    // File/folder operations
    const stagedFileCreations = staging.stagedFileCreations || [];
    const stagedFileDeletions = staging.stagedFileDeletions || [];
    const stagedFileMoves = staging.stagedFileMoves || [];
    const stagedFolderCreations = staging.stagedFolderCreations || [];
    const stagedFolderDeletions = staging.stagedFolderDeletions || [];
    const stagedFolderMoves = staging.stagedFolderMoves || [];

    const hasObjectChanges = Object.keys(pendingEdits).length > 0 || Object.keys(stagedMoves).length > 0 ||
                          stagedCreations.length > 0 || stagedObjectDeletions.length > 0;
    const hasFileOps = stagedFileCreations.length > 0 || stagedFileDeletions.length > 0 || stagedFileMoves.length > 0 ||
                       stagedFolderCreations.length > 0 || stagedFolderDeletions.length > 0 || stagedFolderMoves.length > 0;
    const hasGuiStaging = hasObjectChanges || hasFileOps;

    if (!hasGuiStaging && hasGitChanges) {
        return await buildGitOnlyCommitDialogHtml(gitChanges, configPath, isGitConfigured);
    }

    const fileChanges = buildGlobalFileBasedChanges(pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, allObjects, configPath);

    let newCount = 0, deletedCount = 0, movedCount = 0, modifyCount = 0;
    fileChanges.forEach(fc => {
        fc.additions.forEach(a => { if (a.isNew) newCount++; else movedCount++; });
        fc.removals.forEach(r => { if (r.isDeletion) deletedCount++; });
        modifyCount += fc.modifications.length;
    });

    // Check for external changes (git changes that exist alongside staged changes)
    // This indicates files were modified outside the staging system
    const hasExternalChanges = hasGuiStaging && hasGitChanges && gitChanges.length > 0;

    // Build external changes section with actual diffs (not just a warning)
    let externalChangesHtml = '';
    if (hasExternalChanges) {
        const externalDiffsHtml = await buildExternalChangesHtml(gitChanges, baseState.commitContextLines);
        externalChangesHtml = `
            <div class="commit-section commit-external-section">
                <div class="commit-section-title">
                    <i class="fa-solid fa-triangle-exclamation" style="color: var(--nbe-warning); margin-right: 6px;"></i>
                    External Changes <span class="badge">${gitChanges.length} file${gitChanges.length !== 1 ? 's' : ''}</span>
                    <span class="commit-section-subtitle">(modified outside this editor)</span>
                </div>
                ${externalDiffsHtml}
            </div>
        `;
    }

    let html = `
        <div class="commit-header">
            <div class="commit-summary">
                ${fileChanges.size > 0 ? `<div class="commit-stat edits"><span class="commit-stat-count">${fileChanges.size}</span> file${fileChanges.size !== 1 ? 's' : ''} changed</div>` : ''}
                ${newCount > 0 ? `<div class="commit-stat creates"><span class="commit-stat-count">+${newCount}</span> new</div>` : ''}
                ${deletedCount > 0 ? `<div class="commit-stat deletes"><span class="commit-stat-count">${deletedCount}</span> deleted</div>` : ''}
                ${movedCount > 0 ? `<div class="commit-stat moves"><span class="commit-stat-count">${movedCount}</span> moved</div>` : ''}
                ${modifyCount > 0 ? `<div class="commit-stat edits"><span class="commit-stat-count">~${modifyCount}</span> modified</div>` : ''}
            </div>
            <div class="commit-context-control" title="Number of surrounding lines to show in diffs (drag to adjust)">
                <label>Context:</label>
                <input type="range" min="1" max="10" value="${baseState.commitContextLines > 9 ? 10 : baseState.commitContextLines}" oninput="updateGlobalContextLines(this.value)">
                <span id="globalContextLinesValue" class="context-value">${baseState.commitContextLines > 9 ? 'All' : baseState.commitContextLines}</span>
            </div>
        </div>
        <div class="commit-changes-list" id="globalCommitChangesList">
            ${buildGlobalCommitChangesListHtml(fileChanges, configPath, existingFolders, allObjects, hasFileOps || hasExternalChanges)}
            ${buildFileAndFolderOperationsHtml(stagedFolderCreations, stagedFolderDeletions, stagedFolderMoves, stagedFileCreations, stagedFileDeletions, stagedFileMoves, configPath)}
            ${externalChangesHtml}
        </div>
        ${refData && refData.hasNameChanges ? buildReferenceChangesSection(refData) : ''}
        <div class="commit-footer">
            <div class="commit-footer-left">
                ${isGitConfigured ? `
                <textarea id="globalGitCommitMessage" class="commit-message-textarea" placeholder="Enter commit message..."></textarea>
                ${refData && refData.hasNameChanges ? `
                <div class="commit-reference-option u-mt-sm">
                    <label class="commit-reference-label">
                        <input type="checkbox" id="globalUpdateReferences" checked onchange="toggleReferencePreview(this.checked)">
                        <span>
                            <strong>Update references</strong> (${refData.totalReferences} reference${refData.totalReferences !== 1 ? 's' : ''} in other objects)
                        </span>
                    </label>
                </div>
                ` : ''}
                ` : `
                <div class="git-config-warning">
                    <span class="git-config-warning-icon"><i class="fa-solid fa-triangle-exclamation"></i></span>
                    <div>
                        <strong>Git identity not configured</strong><br>
                        <span class="git-config-warning-text">Configure your name and email in <a href="/settings">Settings</a> to enable commits.</span>
                    </div>
                </div>
                `}
            </div>
            <div class="commit-footer-right">
                <button class="btn-discard-all" onclick="discardGlobalChanges()">Discard All</button>
                <button class="btn-cancel" onclick="closeGlobalCommitDialog()">Cancel</button>
                <button class="btn-apply-commit" id="globalApplyBtn" onclick="applyGlobalCommit()" ${isGitConfigured ? '' : 'disabled class="btn-disabled"'}>Apply Changes</button>
            </div>
        </div>
    `;

    return html;
}

function toggleReferencePreview(checked) {
    const refSection = document.getElementById('referenceChangesSection');
    if (refSection) {
        refSection.style.display = checked ? 'block' : 'none';
    }
}

function buildReferenceChangesSection(refData) {
    if (!refData || !refData.nameChanges || refData.nameChanges.length === 0) {
        return '';
    }

    let itemsHtml = '';
    for (const change of refData.nameChanges) {
        const refsHtml = change.references.map(ref =>
            `<div class="ref-item">
                <span class="ref-type">${escapeHtml(ref.objectType)}</span>
                <span class="ref-name">${escapeHtml(ref.objectName)}</span>
                <span class="ref-field">.${escapeHtml(ref.field)}</span>
            </div>`
        ).join('');

        const moreCount = change.referenceCount - change.references.length;

        itemsHtml += `
            <div class="commit-item expanded">
                <div class="commit-item-header">
                    <span class="commit-item-expand">&#9658;</span>
                    <span class="commit-item-type rename">rename</span>
                    <span class="commit-item-name">${escapeHtml(change.objectType)}: ${escapeHtml(change.oldName)} → ${escapeHtml(change.newName)}</span>
                    <span class="commit-item-file">${change.referenceCount} reference${change.referenceCount !== 1 ? 's' : ''} will be updated</span>
                </div>
                <div class="commit-item-diff ref-changes-diff">
                    <div class="diff-content ref-changes-content">
                        <div class="ref-changes-hint">Objects that reference <strong>${escapeHtml(change.oldName)}</strong> and will be updated:</div>
                        <div class="ref-list">
                            ${refsHtml}
                            ${moreCount > 0 ? `<div class="ref-item ref-more">...and ${moreCount} more</div>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    return `
        <div id="referenceChangesSection" class="commit-changes-list ref-changes-section">
            <div class="commit-section">
                <div class="commit-section-title ref-changes-title">
                    Reference Updates <span class="badge ref-changes-badge">${refData.totalReferences}</span>
                </div>
                ${itemsHtml}
            </div>
        </div>
    `;
}

async function buildGitOnlyCommitDialogHtml(gitChanges, configPath, isGitConfigured = true) {
    baseState.gitOnlyChanges = gitChanges;

    const filesHtml = await buildGitOnlyFilesHtml(gitChanges, baseState.gitOnlyContextLines);

    // Count by status
    let modifiedCount = 0, addedCount = 0, deletedCount = 0;
    for (const change of gitChanges) {
        if (change.status === 'modified') modifiedCount++;
        else if (change.status === 'added' || change.status === 'untracked') addedCount++;
        else if (change.status === 'deleted') deletedCount++;
    }

    return `
        <div class="commit-header">
            <div class="commit-summary">
                ${gitChanges.length > 0 ? `<div class="commit-stat edits"><span class="commit-stat-count">${gitChanges.length}</span> file${gitChanges.length !== 1 ? 's' : ''} changed</div>` : ''}
                ${addedCount > 0 ? `<div class="commit-stat creates"><span class="commit-stat-count">+${addedCount}</span> new</div>` : ''}
                ${deletedCount > 0 ? `<div class="commit-stat deletes"><span class="commit-stat-count">${deletedCount}</span> deleted</div>` : ''}
                ${modifiedCount > 0 ? `<div class="commit-stat edits"><span class="commit-stat-count">~${modifiedCount}</span> modified</div>` : ''}
            </div>
            <div class="commit-context-control" title="Number of surrounding lines to show in diffs (drag to adjust)">
                <label>Context:</label>
                <input type="range" min="1" max="10" value="${baseState.gitOnlyContextLines > 9 ? 10 : baseState.gitOnlyContextLines}" oninput="updateGitOnlyContextLines(this.value)">
                <span id="gitOnlyContextLinesValue" class="context-value">${baseState.gitOnlyContextLines > 9 ? 'All' : baseState.gitOnlyContextLines}</span>
            </div>
        </div>
        <div class="commit-changes-list" id="globalCommitChangesList">
            <div class="commit-section">
                <div class="commit-section-title">File Changes <span class="badge">${gitChanges.length} file${gitChanges.length !== 1 ? 's' : ''}</span></div>
                ${filesHtml}
            </div>
        </div>
        <div class="commit-footer">
            <div class="commit-footer-left">
                ${isGitConfigured ? `
                <textarea id="globalGitCommitMessage" class="commit-message-textarea" placeholder="Enter commit message..."></textarea>
                ` : `
                <div class="git-config-warning">
                    <span class="git-config-warning-icon"><i class="fa-solid fa-triangle-exclamation"></i></span>
                    <div>
                        <strong>Git identity not configured</strong><br>
                        <span class="git-config-warning-text">Configure your name and email in <a href="/settings">Settings</a> to enable commits.</span>
                    </div>
                </div>
                `}
            </div>
            <div class="commit-footer-right">
                <button class="btn-discard-all" onclick="discardGitChanges()">Discard All</button>
                <button class="btn-cancel" onclick="closeGlobalCommitDialog()">Cancel</button>
                <button class="btn-apply-commit" id="globalApplyBtn" onclick="applyGitCommit()" ${isGitConfigured ? '' : 'disabled class="btn-disabled"'}>Apply Changes</button>
            </div>
        </div>
    `;
}

async function buildGitOnlyFilesHtml(gitChanges, contextLines) {
    const statusLabels = {
        'modified': 'Modified',
        'added': 'Added',
        'deleted': 'Deleted',
        'untracked': 'Untracked',
        'renamed': 'Renamed'
    };

    let filesHtml = '';
    for (const change of gitChanges) {
        const statusClass = change.status;
        const statusLabel = statusLabels[change.status] || change.status;
        const typeClass = statusClass === 'modified' ? '' : statusClass === 'added' || statusClass === 'untracked' ? 'create' : statusClass === 'deleted' ? 'delete' : 'move';

        let diffContent = '';
        const useFullFile = contextLines > 9;
        const diffResult = await ApiClient.post('/api/git/diff', {
            file: change.path,
            fullFile: useFullFile,
            contextLines: useFullFile ? null : contextLines
        }, { silent: true });

        if (diffResult.success && diffResult.data?.diff) {
            diffContent = diffResult.data.diff.split('\n').map(line => {
                const lineClass = line.startsWith('+') && !line.startsWith('+++') ? 'add' :
                                 line.startsWith('-') && !line.startsWith('---') ? 'remove' :
                                 line.startsWith('@@') ? 'hunk' : 'context';
                return `<div class="diff-line ${lineClass}">${escapeHtml(line)}</div>`;
            }).join('');
        } else {
            diffContent = '<div class="diff-line context">Unable to load diff</div>';
        }

        filesHtml += `
            <div class="commit-item expanded">
                <div class="commit-item-header">
                    <span class="commit-item-expand">&#9658;</span>
                    <span class="commit-item-type ${typeClass}">${statusLabel}</span>
                    <span class="commit-item-name">${escapeHtml(change.path.split('/').pop())}</span>
                    <span class="commit-item-file">${escapeHtml(change.path)}</span>
                </div>
                <div class="commit-item-diff">
                    <div class="diff-content">${diffContent || '<div class="diff-line context">No changes to display</div>'}</div>
                </div>
            </div>
        `;
    }
    return filesHtml;
}

/**
 * Build HTML for external changes (files modified outside the editor).
 * Similar to buildGitOnlyFilesHtml but for the mixed GUI+external view.
 */
async function buildExternalChangesHtml(gitChanges, contextLines) {
    const statusLabels = {
        'modified': 'Modified',
        'added': 'Added',
        'deleted': 'Deleted',
        'untracked': 'Untracked',
        'renamed': 'Renamed'
    };

    let filesHtml = '';
    for (const change of gitChanges) {
        const statusClass = change.status;
        const statusLabel = statusLabels[change.status] || change.status;
        const typeClass = statusClass === 'modified' ? 'external' : statusClass === 'added' || statusClass === 'untracked' ? 'create' : statusClass === 'deleted' ? 'delete' : 'move';

        let diffContent = '';
        const useFullFile = contextLines > 9;
        const diffResult = await ApiClient.post('/api/git/diff', {
            file: change.path,
            fullFile: useFullFile,
            contextLines: useFullFile ? null : contextLines
        }, { silent: true });

        if (diffResult.success && diffResult.data?.diff) {
            diffContent = diffResult.data.diff.split('\n').map(line => {
                const lineClass = line.startsWith('+') && !line.startsWith('+++') ? 'add' :
                                 line.startsWith('-') && !line.startsWith('---') ? 'remove' :
                                 line.startsWith('@@') ? 'hunk' : 'context';
                return `<div class="diff-line ${lineClass}">${escapeHtml(line)}</div>`;
            }).join('');
        } else {
            diffContent = '<div class="diff-line context">Unable to load diff</div>';
        }

        filesHtml += `
            <div class="commit-item">
                <div class="commit-item-header">
                    <span class="commit-item-expand">&#9658;</span>
                    <span class="commit-item-type ${typeClass}">${statusLabel}</span>
                    <span class="commit-item-name">${escapeHtml(change.path.split('/').pop())}</span>
                    <span class="commit-item-file">${escapeHtml(change.path)}</span>
                </div>
                <div class="commit-item-diff">
                    <div class="diff-content">${diffContent || '<div class="diff-line context">No changes to display</div>'}</div>
                </div>
            </div>
        `;
    }
    return filesHtml;
}

async function updateGitOnlyContextLines(value) {
    const intValue = parseInt(value);
    baseState.gitOnlyContextLines = intValue === 10 ? 9999 : intValue;
    document.getElementById('gitOnlyContextLinesValue').textContent = intValue === 10 ? 'All' : value;

    if (!baseState.gitOnlyChanges) return;

    const changesList = document.getElementById('globalCommitChangesList');
    if (!changesList) return;

    const filesHtml = await buildGitOnlyFilesHtml(baseState.gitOnlyChanges, baseState.gitOnlyContextLines);
    changesList.innerHTML = `
        <div class="commit-section">
            <div class="commit-section-title">File Changes <span class="badge">${baseState.gitOnlyChanges.length} file${baseState.gitOnlyChanges.length !== 1 ? 's' : ''}</span></div>
            ${filesHtml}
        </div>
    `;

    changesList.querySelectorAll('.commit-item-header').forEach(header => {
        header.addEventListener('click', () => {
            header.closest('.commit-item').classList.toggle('expanded');
        });
    });
}

// =============================================================================
// Git Operations
// =============================================================================

async function discardGitChanges() {
    closeGlobalCommitDialog();
    showGitRunningPanel('Discard All Changes', 'git checkout -- . && git clean -fd');

    const identity = getUserIdentity();
    const result = await ApiClient.post('/api/git/discard-all', {
        userName: identity.userName,
        userEmail: identity.userEmail
    }, { silent: true });

    if (result.success && result.data?.success) {
        updateNavCommitButton(0);
    }
    showGitDiscardResultPanel(result.success && result.data?.success, result.data || { error: result.error });
}

function showResultPanel({ command, success, title, outputHtml, needsReload = true, showRetryCommit = false }) {
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const titleEl = document.getElementById('gitResultTitle');
    const commandEl = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    baseState.gitResultNeedsReload = needsReload;

    icon.className = success ? 'git-result-icon success' : 'git-result-icon error';
    icon.innerHTML = success ? '<i class="fa-solid fa-check"></i>' : '<i class="fa-solid fa-xmark"></i>';
    titleEl.textContent = title;
    commandEl.textContent = command;
    output.className = 'git-result-output';

    // C-10: Add retry button if commit failed but staging was preserved
    let retryButtonHtml = '';
    if (showRetryCommit) {
        retryButtonHtml = `
            <div class="git-retry-section">
                <button class="btn-retry-commit" onclick="retryGitCommit()">
                    <i class="fa-solid fa-redo"></i> Retry Commit
                </button>
                <button class="btn-discard-staging" onclick="discardStagingAfterFailedCommit()">
                    Discard Staging
                </button>
            </div>
        `;
    }
    output.innerHTML = outputHtml + retryButtonHtml;

    overlay.classList.add('visible');
}

/**
 * C-10: Retry git commit after a failed attempt.
 * Staging was preserved after apply, so we can retry the commit.
 */
async function retryGitCommit() {
    const message = baseState.pendingCommitMessage;
    if (!message) {
        showToast('No pending commit message found', 'error');
        return;
    }

    // Close the result panel and retry
    const overlay = document.getElementById('gitResultOverlay');
    overlay.classList.remove('visible');

    await autoGitCommitGlobal(message, true);
}

/**
 * C-10: Discard staging after a failed commit.
 * User chose not to retry, so clear the preserved staging.
 */
async function discardStagingAfterFailedCommit() {
    const confirmed = await showConfirmDialog({
        title: 'Discard Staging?',
        message: 'Your changes have been written to disk but not committed to git. Discarding staging will clear the staging state. The files on disk will remain changed.',
        confirmText: 'Discard Staging',
        type: 'warning'
    });

    if (confirmed) {
        await ApiClient.del('/api/staging', { silent: true });
        baseState.pendingCommitMessage = null;
        closeGitResultOverlay();
        showToast('Staging cleared', 'info');
    }
}

function showGitDiscardResultPanel(success, result) {
    const command = (result.commands && result.commands.length > 0)
        ? result.commands.map(c => c.command).join(' && ')
        : 'git discard';

    let outputHtml = '';
    if (success) {
        outputHtml = '<span class="success-text">All uncommitted changes discarded</span>\n\n';
        if (result.commands && result.commands.length > 0) {
            result.commands.forEach(cmd => {
                outputHtml += `<span class="terminal-command">$ ${escapeHtml(cmd.command)}</span>\n`;
                if (cmd.output && cmd.output.trim()) {
                    outputHtml += escapeHtml(cmd.output.trim()) + '\n';
                }
            });
        }
    } else {
        if (result.commands && result.commands.length > 0) {
            result.commands.forEach(cmd => {
                const statusClass = cmd.success ? 'terminal-command-success' : 'terminal-command-error';
                outputHtml += `<span class="${statusClass}">$ ${escapeHtml(cmd.command)}</span>\n`;
                if (cmd.output && cmd.output.trim()) {
                    outputHtml += escapeHtml(cmd.output.trim()) + '\n';
                }
            });
        }
        if (result.error) {
            outputHtml += `\n<span class="error-text">${escapeHtml(result.error)}</span>`;
        }
        outputHtml = outputHtml || '<span class="error-text">Unknown error occurred</span>';
    }

    showResultPanel({
        command,
        success,
        title: success ? 'Discard Successful' : 'Discard Failed',
        outputHtml
    });
}

async function applyGitCommit() {
    const messageInput = document.getElementById('globalGitCommitMessage');
    const message = messageInput?.value?.trim();

    if (!message) {
        showToast('Please enter a commit message', 'error');
        messageInput?.focus();
        return;
    }

    closeGlobalCommitDialog();

    const identity = getUserIdentity();
    const displayMessage = message.length > 60 ? message.substring(0, 60) + '...' : message;
    const fullCommand = `git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "${displayMessage}"`;
    showGitRunningPanel('Git Commit', fullCommand);

    const result = await ApiClient.post('/api/git/commit', {
        message,
        user_name: identity.userName,
        user_email: identity.userEmail
    }, { silent: true });

    if (result.success && result.data?.success) {
        updateNavCommitButton(0);
    }
    showGitResultPanel(message, result.success && result.data?.success, result.data || { error: result.error });
}

// =============================================================================
// File-Based Changes Builder
// =============================================================================

/**
 * Tries to decode a stable key and return its parts.
 * Stable keys are Base64-encoded "source_file|object_type|name" strings.
 * @returns {Object|null} - {source_file, object_type, name} or null if not a valid stable key
 */
function decodeStableKey(key) {
    if (typeof key !== 'string') return null;

    // First check if it's already a decoded format (has pipes)
    if (key.includes('|')) {
        const parts = key.split('|');
        if (parts.length === 3) {
            return { source_file: parts[0], object_type: parts[1], name: parts[2] };
        }
    }

    // Try to decode as Base64
    try {
        const decoded = atob(key);
        if (decoded.includes('|')) {
            const parts = decoded.split('|');
            if (parts.length === 3) {
                return { source_file: parts[0], object_type: parts[1], name: parts[2] };
            }
        }
    } catch (e) {
        // Not valid Base64, that's fine
    }

    return null;
}

/**
 * Finds an object in allObjects by stable key or numeric index.
 * @param {string|number} key - Either a stable key (Base64 or plain) or numeric global_index
 * @param {Array} allObjects - Array of all Nagios objects
 * @returns {Object|null} - Found object or null
 */
function findObjectByKey(key, allObjects) {
    // Try stable key first
    const stableKeyParts = decodeStableKey(key);
    if (stableKeyParts) {
        const { source_file, object_type, name } = stableKeyParts;
        return allObjects.find(o =>
            o.source_file === source_file &&
            o.object_type === object_type &&
            o.name === name
        );
    }

    // Try numeric global_index
    const numericIdx = typeof key === 'string' ? parseInt(key, 10) : key;
    if (!isNaN(numericIdx)) {
        return allObjects.find(o => o.global_index === numericIdx);
    }

    return null;
}

/**
 * Ensures a file entry exists in the fileChanges map with initialized arrays.
 */
function ensureFileChange(fileChanges, filePath, configPath) {
    if (!fileChanges.has(filePath)) {
        fileChanges.set(filePath, {
            fileName: filePath.split('/').pop(),
            relativePath: filePath.startsWith(configPath + '/') ? filePath.substring(configPath.length + 1) : filePath,
            removals: [],
            additions: [],
            modifications: []
        });
    }
    return fileChanges.get(filePath);
}

/**
 * Builds a map of globalIndex -> edit data from pendingEdits dict.
 */
function buildEditsMap(pendingEdits) {
    const editsMap = new Map();
    for (const [key, entry] of Object.entries(pendingEdits)) {
        editsMap.set(key, entry);
    }
    return editsMap;
}

/**
 * Processes a single staged move, adding removal to source file and addition to target file.
 */
function processStagedMove(moveEntry, allObjects, editsMap, fileChanges, configPath) {
    let moveKey, move;
    if (Array.isArray(moveEntry)) {
        moveKey = moveEntry[0];
        move = moveEntry[1];
    } else {
        moveKey = moveEntry.globalIndex || moveEntry.key;
        move = moveEntry;
    }

    // Find object by stable key (Base64-encoded or plain) or by global_index
    let obj = findObjectByKey(moveKey, allObjects);

    // Fallback: create object from move.object data
    if (!obj && move.object) {
        obj = {
            global_index: move.object.global_index !== undefined ? move.object.global_index : -1,
            attributes: move.object.attributes || {},
            object_type: move.object.object_type,
            line_number: move.object.line_number,
            source_file: move.object.source_file,
            name: move.object.name || move.object.display_name
        };
    }
    if (!obj) return;

    // Use the actual global_index for proper matching in diff rendering
    const globalIndex = obj.global_index;

    const edit = editsMap.get(moveKey) || editsMap.get(globalIndex);
    const originalAttrs = edit ? { ...edit.original } : { ...obj.attributes };
    const finalAttrs = edit ? { ...edit.edited } : { ...obj.attributes };

    const sourceFile = ensureFileChange(fileChanges, move.originalFile, configPath);
    sourceFile.removals.push({
        globalIndex: globalIndex,
        object: obj,
        originalAttrs,
        lineNumber: obj.line_number
    });

    const targetFile = ensureFileChange(fileChanges, move.targetFile, configPath);
    targetFile.additions.push({
        globalIndex: globalIndex,
        object: obj,
        finalAttrs,
        objectType: obj.object_type,
        isNew: false,
        insertPosition: move.insertPosition
    });
}

/**
 * Processes a single pending edit (for objects not being moved).
 */
function processPendingEdit(editEntry, allObjects, movedIndices, fileChanges, configPath) {
    let editIdx, edit;
    if (Array.isArray(editEntry)) {
        editIdx = editEntry[0];
        edit = editEntry[1];
    } else {
        editIdx = editEntry.globalIndex;
        edit = editEntry;
    }

    if (movedIndices.has(editIdx)) return;

    // Find object by stable key (Base64-encoded or plain) or by global_index
    let obj = findObjectByKey(editIdx, allObjects);

    if (!obj && edit.object) {
        obj = {
            // Use null-check instead of || to handle global_index = 0
            global_index: edit.object.global_index !== undefined ? edit.object.global_index : -1,
            attributes: edit.object.attributes || {},
            object_type: edit.object.object_type,
            line_number: edit.object.line_number,
            source_file: edit.object.source_file,
            name: edit.object.name || edit.object.display_name
        };
    }
    if (!obj) return;

    const file = ensureFileChange(fileChanges, obj.source_file, configPath);
    file.modifications.push({
        globalIndex: obj.global_index,
        object: obj,
        originalAttrs: { ...edit.original },
        finalAttrs: { ...edit.edited },
        lineNumber: obj.line_number
    });
}

/**
 * Processes a single staged creation.
 */
function processStagedCreation(creation, fileChanges, configPath) {
    const file = ensureFileChange(fileChanges, creation.targetFile, configPath);
    file.additions.push({
        object: { object_type: creation.object_type, display_name: creation.displayName },
        finalAttrs: { ...creation.attributes },
        objectType: creation.object_type,
        isNew: true,
        insertPosition: creation.insertPosition
    });
}

/**
 * Processes a single staged object deletion.
 */
function processStagedDeletion(globalIndex, allObjects, fileChanges, configPath) {
    const obj = allObjects.find(o => o.global_index === globalIndex);
    if (!obj) return;

    const file = ensureFileChange(fileChanges, obj.source_file, configPath);
    file.removals.push({
        globalIndex,
        object: obj,
        originalAttrs: { ...obj.attributes },
        lineNumber: obj.line_number,
        isDeletion: true
    });
}

/**
 * Builds a file-based view of all staged changes for the commit dialog.
 * Groups edits, moves, creations, and deletions by their target files.
 */
function buildGlobalFileBasedChanges(pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, allObjects, configPath) {
    const fileChanges = new Map();
    const editsMap = buildEditsMap(pendingEdits);

    // Process moves (adds to both source and target files) - iterate over dict entries
    for (const [moveKey, move] of Object.entries(stagedMoves)) {
        processStagedMove([moveKey, move], allObjects, editsMap, fileChanges, configPath);
    }

    // Build set of moved indices to skip them in edit processing
    // Need to convert stable keys to global indices for proper matching
    const movedIndices = new Set();
    for (const [moveKey, move] of Object.entries(stagedMoves)) {
        // Try to find the object using stable key or global_index
        const obj = findObjectByKey(moveKey, allObjects);
        if (obj) {
            movedIndices.add(obj.global_index);
        }
        // Also add the key itself for matching against key-based edits
        movedIndices.add(moveKey);
    }

    // Process edits (skip objects that are being moved) - iterate over dict entries
    for (const [editKey, edit] of Object.entries(pendingEdits)) {
        processPendingEdit([editKey, edit], allObjects, movedIndices, fileChanges, configPath);
    }

    // Process creations
    for (const creation of stagedCreations) {
        processStagedCreation(creation, fileChanges, configPath);
    }

    // Process deletions
    for (const globalIndex of stagedObjectDeletions) {
        processStagedDeletion(globalIndex, allObjects, fileChanges, configPath);
    }

    return fileChanges;
}

function buildGlobalCommitChangesListHtml(fileChanges, configPath, existingFolders, allObjects, hasOtherChanges = false) {
    let html = '';

    if (fileChanges.size > 0) {
        html += `<div class="commit-section">
            <div class="commit-section-title">File Changes <span class="badge">${fileChanges.size} file${fileChanges.size !== 1 ? 's' : ''}</span></div>`;

        const sortedFiles = [...fileChanges.entries()].sort((a, b) => a[0].localeCompare(b[0]));

        sortedFiles.forEach(([filePath, fileData]) => {
            html += renderGlobalFileDiff(filePath, fileData, allObjects, configPath);
        });

        html += '</div>';
    }

    // Only show "No changes" if there are no other changes (file/folder ops, external changes)
    if (html === '' && !hasOtherChanges) {
        html = '<div class="commit-empty">No changes to display.</div>';
    }

    return html;
}

function buildFileAndFolderOperationsHtml(folderCreations, folderDeletions, folderMoves, fileCreations, fileDeletions, fileMoves, configPath) {
    const totalOps = folderCreations.length + folderDeletions.length + folderMoves.length +
                     fileCreations.length + fileDeletions.length + fileMoves.length;

    if (totalOps === 0) {
        return '';
    }

    // Helper to get relative path from config path
    const getRelativePath = (fullPath) => {
        if (fullPath.startsWith(configPath)) {
            const rel = fullPath.slice(configPath.length);
            return rel.startsWith('/') ? rel.slice(1) : rel;
        }
        return fullPath;
    };

    let itemsHtml = '';

    // Folder creations
    for (const op of folderCreations) {
        const relPath = getRelativePath(op.path);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-folder-plus file-op-icon file-op-create"></i>
                    <span class="file-op-action">Create folder</span>
                    <span class="file-op-path">${escapeHtml(relPath)}</span>
                </div>
            </div>
        `;
    }

    // Folder deletions
    for (const op of folderDeletions) {
        const relPath = getRelativePath(op.path);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-folder-minus file-op-icon file-op-delete"></i>
                    <span class="file-op-action">Delete folder</span>
                    <span class="file-op-path">${escapeHtml(relPath)}</span>
                </div>
            </div>
        `;
    }

    // Folder moves
    for (const op of folderMoves) {
        const sourceRel = getRelativePath(op.sourcePath);
        const targetRel = getRelativePath(op.targetPath);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-folder-tree file-op-icon file-op-move"></i>
                    <span class="file-op-action">Move folder</span>
                    <span class="file-op-path">${escapeHtml(sourceRel)} <i class="fa-solid fa-arrow-right file-op-arrow"></i> ${escapeHtml(targetRel)}</span>
                </div>
            </div>
        `;
    }

    // File creations
    for (const op of fileCreations) {
        const relPath = getRelativePath(op.path);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-file-circle-plus file-op-icon file-op-create"></i>
                    <span class="file-op-action">Create file</span>
                    <span class="file-op-path">${escapeHtml(relPath)}</span>
                </div>
            </div>
        `;
    }

    // File deletions
    for (const op of fileDeletions) {
        const relPath = getRelativePath(op.path);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-file-circle-minus file-op-icon file-op-delete"></i>
                    <span class="file-op-action">Delete file</span>
                    <span class="file-op-path">${escapeHtml(relPath)}</span>
                </div>
            </div>
        `;
    }

    // File moves
    for (const op of fileMoves) {
        const sourceRel = getRelativePath(op.sourcePath);
        const targetRel = op.targetFolder ? getRelativePath(op.targetFolder) : getRelativePath(op.targetPath);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-file-export file-op-icon file-op-move"></i>
                    <span class="file-op-action">Move file</span>
                    <span class="file-op-path">${escapeHtml(sourceRel)} <i class="fa-solid fa-arrow-right file-op-arrow"></i> ${escapeHtml(targetRel)}</span>
                </div>
            </div>
        `;
    }

    return `
        <div class="commit-section commit-file-ops-section">
            <div class="commit-section-title">
                <i class="fa-solid fa-folder-open" style="margin-right: 6px;"></i>
                File & Folder Operations <span class="badge">${totalOps}</span>
            </div>
            ${itemsHtml}
        </div>
    `;
}

function renderGlobalFileDiff(filePath, fileData, allObjects, configPath) {
    const { fileName, relativePath, removals, additions, modifications } = fileData;

    let summaryParts = [];
    if (additions.length > 0) summaryParts.push(`+${additions.length}`);
    if (removals.length > 0) summaryParts.push(`-${removals.length}`);
    if (modifications.length > 0) summaryParts.push(`~${modifications.length}`);

    let existingObjects = allObjects
        .filter(obj => obj.source_file === filePath)
        .sort((a, b) => a.line_number - b.line_number);

    const removalIndices = new Set(removals.map(r => r.object.global_index));
    const modificationIndices = new Set(modifications.map(m => m.object.global_index));
    const modificationMap = new Map(modifications.map(m => [m.object.global_index, m]));

    const existingIndices = new Set(existingObjects.map(o => o.global_index));
    for (const removal of removals) {
        if (!existingIndices.has(removal.object.global_index)) {
            existingObjects.push(removal.object);
        }
    }
    existingObjects.sort((a, b) => a.line_number - b.line_number);

    const unifiedItems = [];

    existingObjects.forEach((obj, idx) => {
        unifiedItems.push({
            type: 'existing',
            sortKey: obj.line_number,
            idx: idx,
            object: obj,
            isRemoval: removalIndices.has(obj.global_index),
            isModification: modificationIndices.has(obj.global_index)
        });
    });

    additions.forEach((addition, addIdx) => {
        const insertPos = addition.insertPosition !== undefined ? addition.insertPosition : Infinity;
        unifiedItems.push({
            type: 'addition',
            sortKey: insertPos + 0.5,
            addIdx: addIdx,
            addition: addition
        });
    });

    unifiedItems.sort((a, b) => a.sortKey - b.sortKey);

    const maxContext = baseState.commitContextLines;
    const interestingPositions = new Set();
    unifiedItems.forEach((item, pos) => {
        const isInteresting = item.type === 'addition' ||
                             (item.type === 'existing' && (item.isRemoval || item.isModification));
        if (isInteresting) {
            for (let i = Math.max(0, pos - maxContext); i <= Math.min(unifiedItems.length - 1, pos + maxContext); i++) {
                interestingPositions.add(i);
            }
        }
    });

    let diffHtml = `<div class="diff-file-header">${escapeHtml(fileName)}</div>`;
    let lastShownPos = -1;
    let skippedCount = 0;

    unifiedItems.forEach((item, pos) => {
        if (!interestingPositions.has(pos)) {
            skippedCount++;
            return;
        }

        const hadSkipped = skippedCount > 0;
        if (hadSkipped && lastShownPos >= 0) {
            diffHtml += `<div class="diff-line context diff-skipped">  ... ${skippedCount} unchanged object${skippedCount !== 1 ? 's' : ''} ...</div>`;
        }
        skippedCount = 0;

        if (lastShownPos >= 0 && !hadSkipped) {
            diffHtml += `<div class="diff-line context"> </div>`;
        }
        lastShownPos = pos;

        if (item.type === 'addition') {
            const addition = item.addition;
            if (addition.isNew) {
                diffHtml += renderGlobalObject(addition.objectType, addition.finalAttrs, '+');
            } else {
                diffHtml += `<div class="diff-line add">+ [Moved from ${escapeHtml(addition.originalFile || 'another file')}]</div>`;
                diffHtml += renderGlobalObject(addition.objectType, addition.finalAttrs, '+');
            }
        } else if (item.isRemoval) {
            const removal = removals.find(r => r.object.global_index === item.object.global_index);
            if (removal && removal.isDeletion) {
                diffHtml += renderGlobalObject(item.object.object_type, removal.originalAttrs, '-');
            } else if (removal) {
                diffHtml += `<div class="diff-line remove">- [Moving to another file]</div>`;
                diffHtml += renderGlobalObject(item.object.object_type, removal.originalAttrs, '-');
            }
        } else if (item.isModification) {
            const mod = modificationMap.get(item.object.global_index);
            if (mod) {
                diffHtml += renderGlobalModifiedObject(mod.object, mod.originalAttrs, mod.finalAttrs);
            }
        } else {
            diffHtml += renderGlobalObject(item.object.object_type, item.object.attributes, ' ');
        }
    });

    if (skippedCount > 0) {
        diffHtml += `<div class="diff-line context diff-skipped">  ... ${skippedCount} unchanged object${skippedCount !== 1 ? 's' : ''} ...</div>`;
    }

    return `
        <div class="commit-item expanded">
            <div class="commit-item-header">
                <span class="commit-item-expand">&#9658;</span>
                <span class="commit-item-type">file</span>
                <span class="commit-item-name">${escapeHtml(fileName)}</span>
                <span class="commit-item-file">${escapeHtml(relativePath)} · ${summaryParts.join(' ')}</span>
            </div>
            <div class="commit-item-diff">
                <div class="diff-content">${diffHtml}</div>
            </div>
        </div>
    `;
}

function renderGlobalObject(objType, attrs, prefix) {
    const cssClass = prefix === '-' ? 'remove' : (prefix === '+' ? 'add' : 'context');
    let html = `<div class="diff-line ${cssClass}">${prefix} define ${escapeHtml(objType)} {</div>`;
    const keys = Object.keys(attrs).sort();
    for (const key of keys) {
        html += `<div class="diff-line ${cssClass}">${prefix}     ${escapeHtml(key.padEnd(30))} ${escapeHtml(attrs[key])}</div>`;
    }
    html += `<div class="diff-line ${cssClass}">${prefix} }</div>`;
    return html;
}

function renderGlobalModifiedObject(obj, originalAttrs, finalAttrs) {
    const allKeys = [...new Set([...Object.keys(originalAttrs), ...Object.keys(finalAttrs)])].sort();
    let html = `<div class="diff-line modify">  define ${escapeHtml(obj.object_type)} {</div>`;

    allKeys.forEach(key => {
        const origVal = originalAttrs[key];
        const newVal = finalAttrs[key];

        if (origVal === newVal) {
            html += `<div class="diff-line context">      ${escapeHtml(key.padEnd(30))} ${escapeHtml(origVal || '')}</div>`;
        } else if (!origVal && newVal) {
            html += `<div class="diff-line add">+     ${escapeHtml(key.padEnd(30))} ${escapeHtml(newVal)}</div>`;
        } else if (origVal && !newVal) {
            html += `<div class="diff-line remove">-     ${escapeHtml(key.padEnd(30))} ${escapeHtml(origVal)}</div>`;
        } else {
            html += `<div class="diff-line remove">-     ${escapeHtml(key.padEnd(30))} ${escapeHtml(origVal)}</div>`;
            html += `<div class="diff-line add">+     ${escapeHtml(key.padEnd(30))} ${escapeHtml(newVal)}</div>`;
        }
    });

    html += `<div class="diff-line modify">  }</div>`;
    return html;
}

function updateGlobalContextLines(value) {
    const intValue = parseInt(value);
    baseState.commitContextLines = intValue === 10 ? 9999 : intValue;
    document.getElementById('globalContextLinesValue').textContent = intValue === 10 ? 'All' : value;

    if (baseState.diffData && baseState.diffData.staging) {
        const staging = baseState.diffData.staging;
        const allObjects = baseState.diffData.objects;
        const configPath = baseState.diffData.configPath;
        const existingFolders = baseState.diffData.existingFolders || [];

        const pendingEdits = staging.pendingEdits || {};
        const stagedMoves = staging.stagedMoves || {};
        const stagedCreations = staging.stagedCreations || [];
        const stagedObjectDeletions = staging.stagedObjectDeletions || [];

        // File/folder operations
        const stagedFileCreations = staging.stagedFileCreations || [];
        const stagedFileDeletions = staging.stagedFileDeletions || [];
        const stagedFileMoves = staging.stagedFileMoves || [];
        const stagedFolderCreations = staging.stagedFolderCreations || [];
        const stagedFolderDeletions = staging.stagedFolderDeletions || [];
        const stagedFolderMoves = staging.stagedFolderMoves || [];
        const hasFileOps = stagedFileCreations.length > 0 || stagedFileDeletions.length > 0 || stagedFileMoves.length > 0 ||
                           stagedFolderCreations.length > 0 || stagedFolderDeletions.length > 0 || stagedFolderMoves.length > 0;

        const expandedIndices = new Set();
        document.querySelectorAll('#globalCommitContent .commit-item.expanded').forEach((item, idx) => {
            expandedIndices.add(idx);
        });

        const fileChanges = buildGlobalFileBasedChanges(pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, allObjects, configPath);
        const changesList = document.getElementById('globalCommitChangesList');
        if (changesList) {
            let html = buildGlobalCommitChangesListHtml(fileChanges, configPath, existingFolders, allObjects, hasFileOps);
            html += buildFileAndFolderOperationsHtml(stagedFolderCreations, stagedFolderDeletions, stagedFolderMoves, stagedFileCreations, stagedFileDeletions, stagedFileMoves, configPath);
            changesList.innerHTML = html;

            document.querySelectorAll('#globalCommitContent .commit-item').forEach((item, idx) => {
                if (expandedIndices.has(idx)) {
                    item.classList.add('expanded');
                }
                const header = item.querySelector('.commit-item-header');
                if (header) {
                    header.addEventListener('click', () => {
                        item.classList.toggle('expanded');
                    });
                }
            });
        }
    }
}

function closeGlobalCommitDialog() {
    document.getElementById('globalCommitOverlay').classList.remove('visible');
}

async function discardGlobalChanges() {
    let changeCount = 0;
    let changeSummary = [];
    if (baseState.diffData && baseState.diffData.staging) {
        const s = baseState.diffData.staging;
        const edits = Object.keys(s.pendingEdits || {}).length;
        const moves = Object.keys(s.stagedMoves || {}).length;
        const creates = (s.stagedCreations || []).length;
        const objDeletes = (s.stagedObjectDeletions || []).length;
        // Include file/folder operations in count
        const fileCreates = (s.stagedFileCreations || []).length;
        const fileDeletes = (s.stagedFileDeletions || []).length;
        const fileMoves = (s.stagedFileMoves || []).length;
        const folderCreates = (s.stagedFolderCreations || []).length;
        const folderDeletes = (s.stagedFolderDeletions || []).length;
        const folderMoves = (s.stagedFolderMoves || []).length;

        if (edits > 0) changeSummary.push(`${edits} edit${edits !== 1 ? 's' : ''}`);
        if (creates > 0) changeSummary.push(`${creates} creation${creates !== 1 ? 's' : ''}`);
        if (moves > 0) changeSummary.push(`${moves} move${moves !== 1 ? 's' : ''}`);
        if (objDeletes > 0) changeSummary.push(`${objDeletes} object deletion${objDeletes !== 1 ? 's' : ''}`);
        if (fileCreates > 0) changeSummary.push(`${fileCreates} file creation${fileCreates !== 1 ? 's' : ''}`);
        if (fileDeletes > 0) changeSummary.push(`${fileDeletes} file deletion${fileDeletes !== 1 ? 's' : ''}`);
        if (fileMoves > 0) changeSummary.push(`${fileMoves} file move${fileMoves !== 1 ? 's' : ''}`);
        if (folderCreates > 0) changeSummary.push(`${folderCreates} folder creation${folderCreates !== 1 ? 's' : ''}`);
        if (folderDeletes > 0) changeSummary.push(`${folderDeletes} folder deletion${folderDeletes !== 1 ? 's' : ''}`);
        if (folderMoves > 0) changeSummary.push(`${folderMoves} folder move${folderMoves !== 1 ? 's' : ''}`);

        changeCount = edits + moves + creates + objDeletes +
                      fileCreates + fileDeletes + fileMoves +
                      folderCreates + folderDeletes + folderMoves;
    }

    closeGlobalCommitDialog();
    showGitRunningPanel('Discard Changes', 'Clearing staged changes...');

    const result = await ApiClient.del('/api/staging', { silent: true });

    if (result.success && result.data?.success) {
        updateNavCommitButton(0);
        updateUndoButton(0);

        // Reset frontend staging state
        if (typeof Explorer !== 'undefined' && Explorer.resetStagingState) {
            Explorer.resetStagingState();
        }

        // Reload data from server to get clean state
        if (typeof Explorer !== 'undefined' && Explorer.loadObjects) {
            await Explorer.loadObjects();
        }

        // Rebuild UI
        if (typeof buildTree === 'function') buildTree();
        if (typeof renderTargetPane === 'function') renderTargetPane();
    }
    const data = result.data || {};
    showStagingDiscardResultPanel(result.success && data.success, changeCount, changeSummary, data.error || result.error, data.gitDiscarded);
}

function showStagingDiscardResultPanel(success, changeCount, changeSummary, errorMsg = null, gitDiscarded = false) {
    const command = gitDiscarded ? 'git checkout -- . && git clean -fd' : 'Clear staging data';

    let outputHtml = '';
    if (success) {
        if (gitDiscarded) {
            outputHtml = '<span class="success-text">All uncommitted changes have been discarded.</span>\n\n';
            outputHtml += '<span class="terminal-hint">Git working directory restored to HEAD.</span>\n';
        } else if (changeCount > 0) {
            outputHtml = `<span class="success-text">All staged changes discarded (${changeCount} change${changeCount !== 1 ? 's' : ''})</span>\n\n`;
            if (changeSummary.length > 0) {
                outputHtml += '<span class="terminal-hint">Cleared:</span>\n';
                changeSummary.forEach(item => {
                    outputHtml += `  - ${escapeHtml(item)}\n`;
                });
            }
        } else {
            outputHtml = '<span class="success-text">Staging cleared.</span>\n';
        }
    } else {
        outputHtml = `<span class="error-text">${escapeHtml(errorMsg || 'Unknown error occurred')}</span>`;
    }

    showResultPanel({
        command,
        success,
        title: success ? 'Discard Successful' : 'Discard Failed',
        outputHtml
    });
}

async function applyGlobalCommit() {
    const applyBtn = document.getElementById('globalApplyBtn');
    const commitMessageInput = document.getElementById('globalGitCommitMessage');
    const commitMessage = commitMessageInput ? commitMessageInput.value.trim() : '';

    if (!commitMessage) {
        showToast('Please enter a commit message', 'error');
        if (commitMessageInput) {
            commitMessageInput.focus();
        }
        return;
    }

    closeGlobalCommitDialog();
    const displayMessage = commitMessage.length > 60 ? commitMessage.substring(0, 60) + '...' : commitMessage;

    // Check if we have GUI staging to apply
    const hasGuiStaging = baseState.diffData && baseState.diffData.staging && (
        Object.keys(baseState.diffData.staging.pendingEdits || {}).length > 0 ||
        Object.keys(baseState.diffData.staging.stagedMoves || {}).length > 0 ||
        (baseState.diffData.staging.stagedCreations || []).length > 0 ||
        (baseState.diffData.staging.stagedObjectDeletions || []).length > 0 ||
        (baseState.diffData.staging.stagedFileCreations || []).length > 0 ||
        (baseState.diffData.staging.stagedFileDeletions || []).length > 0 ||
        (baseState.diffData.staging.stagedFileMoves || []).length > 0 ||
        (baseState.diffData.staging.stagedFolderCreations || []).length > 0 ||
        (baseState.diffData.staging.stagedFolderDeletions || []).length > 0 ||
        (baseState.diffData.staging.stagedFolderMoves || []).length > 0
    );

    if (hasGuiStaging) {
        // Apply GUI staging first
        showGitRunningPanel('Applying Changes', 'Applying staged changes...');

        const updateRefsCheckbox = document.getElementById('globalUpdateReferences');
        const updateReferences = updateRefsCheckbox ? updateRefsCheckbox.checked : false;

        // C-10: Apply with deferClear=true to ensure atomicity with git commit
        // If git commit fails, staging remains intact for retry
        const applyResult = await ApiClient.post('/api/staging/apply', {
            updateReferences,
            deferClear: true  // Don't clear staging yet - wait for git commit success
        }, { silent: true });

        if (!applyResult.success || !applyResult.data?.success) {
            showStagingResultPanel(false, applyResult.data?.error || applyResult.error || 'Failed to apply staged changes');
            return;
        }
    } else {
        // Git-only commit - no staging to apply
        showGitRunningPanel('Git Commit', 'Committing changes...');
    }

    // Now do the git commit - pass callback to clear staging on success
    updateNavCommitButton(0);
    await autoGitCommitGlobal(commitMessage, hasGuiStaging);  // only clear staging if we had GUI staging
}

function showStagingResultPanel(success, message) {
    showResultPanel({
        command: 'Apply staged changes',
        success: false,
        title: 'Apply Changes Failed',
        outputHtml: `<span class="error-text">${message}</span>`,
        needsReload: false
    });
}

async function autoGitCommitGlobal(message, clearStagingOnSuccess = false) {
    if (!message) return;

    const identity = getUserIdentity();

    const displayMessage = message.length > 60 ? message.substring(0, 60) + '...' : message;
    const fullCommand = `git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "${displayMessage}"`;
    showGitRunningPanel('Git Commit', fullCommand);

    const result = await ApiClient.post('/api/git/commit', {
        message,
        auto_init: true,
        user_name: identity.userName,
        user_email: identity.userEmail
    }, { silent: true });

    if (!result.success && result.data?.needsConfig) {
        showGitResultPanel(message, false, { error: 'Configure git name and email in Settings to enable version control' }, clearStagingOnSuccess);
        return;
    }

    const isSuccess = result.success && result.data?.success;

    // C-10: Only clear staging if commit was successful
    if (isSuccess && clearStagingOnSuccess) {
        // Clear staging after successful commit
        await ApiClient.del('/api/staging', { silent: true });
    }

    showGitResultPanel(message, result.success, result.data || { error: result.error }, clearStagingOnSuccess && !isSuccess);
}

function showGitResultPanel(message, success, result, showRetryOption = false) {
    const identity = getUserIdentity();
    const displayMessage = message.length > 60 ? message.substring(0, 60) + '...' : message;
    const command = `git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "${displayMessage}"`;

    const isSuccess = success && result.success;
    let outputHtml = '';
    if (isSuccess) {
        if (result.initialized) {
            outputHtml += '<span class="success-text">Initialized empty Git repository</span>\n';
        }
        outputHtml += `<span class="success-text">Committed:</span> <span class="hash">${escapeHtml(result.commit_hash)}</span>\n`;
        if (result.output) {
            outputHtml += escapeHtml(result.output);
        }
    } else {
        const errorMsg = result.error || 'Unknown error occurred';
        outputHtml = `<span class="error-text">${escapeHtml(errorMsg)}</span>`;

        // C-10: Show retry option if staging was preserved after apply
        if (showRetryOption) {
            outputHtml += '\n\n<span class="info-text">Changes have been applied to disk but not committed to git.</span>';
            outputHtml += '\n<span class="info-text">Staging preserved - you can retry the commit.</span>';
            // Store message for retry
            baseState.pendingCommitMessage = message;
        }
    }

    showResultPanel({
        command,
        success: isSuccess,
        title: isSuccess ? 'Git Commit Successful' : 'Git Commit Failed',
        outputHtml,
        showRetryCommit: showRetryOption && !isSuccess
    });
}

function showGitRunningPanel(title, command) {
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const titleEl = document.getElementById('gitResultTitle');
    const commandEl = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    baseState.gitResultNeedsReload = false;

    icon.className = 'git-result-icon running';
    icon.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    titleEl.textContent = title;
    commandEl.textContent = command;
    output.className = 'git-result-output running';
    output.innerHTML = 'Running...';

    overlay.classList.add('visible');
}

function showGitOperationResult(title, command, success, message) {
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const titleEl = document.getElementById('gitResultTitle');
    const commandEl = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    baseState.gitResultNeedsReload = true;

    commandEl.textContent = command;

    if (success) {
        icon.className = 'git-result-icon success';
        icon.innerHTML = '<i class="fa-solid fa-check"></i>';
        titleEl.textContent = title;
        output.className = 'git-result-output';
        output.innerHTML = `<span class="success-text">${escapeHtml(message)}</span>`;
    } else {
        icon.className = 'git-result-icon error';
        icon.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        titleEl.textContent = title + ' Failed';
        output.className = 'git-result-output';
        output.innerHTML = `<span class="error-text">${escapeHtml(message)}</span>`;
    }

    overlay.classList.add('visible');
}

function closeGitResultPanel() {
    const icon = document.getElementById('gitResultIcon');
    if (icon.classList.contains('running')) {
        return;
    }
    document.getElementById('gitResultOverlay').classList.remove('visible');
    if (baseState.gitResultNeedsReload) {
        baseState.gitResultNeedsReload = false;
        window.location.reload();
    }
}

// =============================================================================
// Nav Commit Button
// =============================================================================

function updateNavCommitButton(changeCount) {
    const btn = document.getElementById('navCommitBtn');
    const gitIndicator = document.getElementById('gitPendingIndicator');

    if (btn) {
        if (changeCount > 0) {
            btn.classList.remove('disabled');
            btn.classList.add('active');
            btn.disabled = false;
            btn.innerHTML = `<span class="commit-count">${changeCount}</span><span class="commit-btn-text">Commit</span>`;
        } else {
            btn.classList.add('disabled');
            btn.classList.remove('active');
            btn.disabled = true;
            btn.innerHTML = '<span class="commit-btn-text">Commit</span>';
        }
    }

    if (gitIndicator) {
        if (changeCount > 0) {
            gitIndicator.textContent = changeCount;
            gitIndicator.classList.remove('u-hidden');
            gitIndicator.classList.add('u-visible-flex');
        } else {
            gitIndicator.classList.add('u-hidden');
            gitIndicator.classList.remove('u-visible-flex');
        }
    }
}

function updateUndoButton(undoCount) {
    const btn = document.getElementById('navUndoBtn');
    if (!btn) return;

    if (undoCount > 0) {
        btn.classList.remove('disabled');
        btn.classList.add('active');
        btn.disabled = false;
        btn.title = `Undo last action (${undoCount} in stack) - Ctrl+Z`;
    } else {
        btn.classList.add('disabled');
        btn.classList.remove('active');
        btn.disabled = true;
        btn.title = 'Nothing to undo';
    }
}

async function handleUndoClick() {
    if (typeof Explorer !== 'undefined' && Explorer.undoLastAction) {
        const result = await Explorer.undoLastAction();
        if (result.success) {
            checkPendingChanges();
        }
    } else {
        // Fallback: call API directly
        const result = await ApiClient.post('/api/staging/undo', {}, { silent: true });

        if (result.success && result.data?.success) {
            const description = result.data.undone?.description || 'action';
            showToast(`Undone: ${description}`, 'info');
            checkPendingChanges();
            // Reload page to reflect changes
            if (typeof buildTree === 'function') buildTree();
        } else if (result.status === 404) {
            showToast('Nothing to undo', 'info');
        } else {
            showToast(result.data?.error || result.error || 'Failed to undo', 'error');
        }
    }
}

// Keyboard Shortcuts Help Dialog
function showKeyboardShortcuts() {
    const overlay = document.getElementById('keyboardShortcutsOverlay');
    if (overlay) {
        // Update modifier key labels for macOS
        if (navigator.platform && navigator.platform.indexOf('Mac') !== -1) {
            overlay.querySelectorAll('.mod-key').forEach(el => {
                el.textContent = '\u2318';
            });
        }
        overlay.classList.add('visible');
    }
}

function closeKeyboardShortcuts() {
    const overlay = document.getElementById('keyboardShortcutsOverlay');
    if (overlay) overlay.classList.remove('visible');
}

async function checkPendingChanges() {
    // Use extended staging info to get accurate count of staged changes
    const infoResult = await ApiClient.get('/api/staging/info', { silent: true });

    if (infoResult.success) {
        const info = infoResult.data;
        let count = info.totalCount || 0;
        updateUndoButton(info.undoCount || 0);

        // If no GUI staging, check git for external changes (files modified outside editor)
        if (count === 0) {
            const gitResult = await ApiClient.get('/api/git/status', { silent: true });
            if (gitResult.success && gitResult.data?.has_changes) {
                count = gitResult.data.files.length;
            }
        }

        updateNavCommitButton(count);
        return;
    }

    // Fallback: count from Explorer state if available
    if (typeof Explorer !== 'undefined' && Explorer.getTotalStagedCount) {
        const count = Explorer.getTotalStagedCount();
        updateNavCommitButton(count);
        updateUndoButton(Explorer.getUndoCount ? Explorer.getUndoCount() : 0);
        return;
    }

    // Last resort: use diff endpoint
    const diffResult = await ApiClient.get('/api/staging/diff', { silent: true });
    const count = (diffResult.data?.gitChanges || []).length;
    updateNavCommitButton(count);
}

function checkIdentityRequired() {
    const isSettingsPage = window.location.pathname.includes('/settings');
    if (isSettingsPage) {
        return false;
    }

    if (!hasUserIdentity()) {
        document.getElementById('identityRequiredOverlay').classList.add('visible');
        return true;
    }
    return false;
}

// =============================================================================
// Polling
// =============================================================================

function startLockPoll() {
    if (baseState.lockPollInterval) return;
    baseState.lockPollInterval = setInterval(async () => {
        await checkLockStatus();
        await checkPendingChanges();
    }, 5000);
}

// =============================================================================
// Initialization
// =============================================================================

/**
 * Action handlers for data-action elements (used by event delegation).
 * Maps action names to handler functions.
 */
const actionHandlers = {
    'undo': handleUndoClick,
    'commit': handleCommitClick,
    'show-shortcuts': showKeyboardShortcuts,
    'close-shortcuts': closeKeyboardShortcuts,
    'reload-config': reloadConfig,
    'break-lock': breakLock,
    'close-git-result': closeGitResultPanel,
    'close-toast': (e) => e.target.closest('.toast')?.remove()
};

document.addEventListener('DOMContentLoaded', () => {
    // Always check for pending changes and update commit button
    checkPendingChanges();
    checkLockStatus();
    // Start polling for lock status and pending changes
    startLockPoll();

    // Check identity - if not set, show popup (but don't block the above checks)
    checkIdentityRequired();

    // Event delegation for data-action elements (replaces inline onclick handlers)
    document.addEventListener('click', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (actionEl) {
            const action = actionEl.dataset.action;
            const handler = actionHandlers[action];
            if (handler) {
                e.preventDefault();
                handler(e);
            }
        }
    });

    // Set up event listeners for overlays (click outside to close)
    const gitResultOverlay = document.getElementById('gitResultOverlay');
    if (gitResultOverlay) {
        gitResultOverlay.addEventListener('click', function(e) {
            if (e.target === this) {
                closeGitResultPanel();
            }
        });
    }

    const globalCommitOverlay = document.getElementById('globalCommitOverlay');
    if (globalCommitOverlay) {
        globalCommitOverlay.addEventListener('click', function(e) {
            if (e.target === this) {
                closeGlobalCommitDialog();
            }
        });
    }

    const keyboardShortcutsOverlay = document.getElementById('keyboardShortcutsOverlay');
    if (keyboardShortcutsOverlay) {
        keyboardShortcutsOverlay.addEventListener('click', function(e) {
            if (e.target === this) {
                closeKeyboardShortcuts();
            }
        });
    }

    // Close dialogs on Escape key, Undo on Ctrl+Z, ? for help
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeGlobalCommitDialog();
            closeGitResultPanel();
            closeKeyboardShortcuts();
        }

        // Ctrl+Z (or Cmd+Z on Mac) for undo - but not when editing text or in dialogs
        if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
            const activeEl = document.activeElement;
            const isTextInput = activeEl && (
                activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.isContentEditable
            );

            // F-01: Check if any modal dialog is open (Bootstrap modals or custom overlays)
            const hasOpenModal = document.querySelector('.modal.show') !== null;
            const hasOpenOverlay = document.querySelector('.confirm-dialog-overlay.visible, .global-commit-overlay.visible, .git-result-panel.visible') !== null;
            const isDialogOpen = hasOpenModal || hasOpenOverlay;

            // Only handle undo if not in a text input and no dialog is open
            if (!isTextInput && !isDialogOpen) {
                e.preventDefault();
                handleUndoClick();
            }
        }

        // ? key to show keyboard shortcuts help (not when typing in inputs)
        if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
            const activeEl = document.activeElement;
            const isTextInput = activeEl && (
                activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.isContentEditable
            );
            if (!isTextInput) {
                e.preventDefault();
                showKeyboardShortcuts();
            }
        }
    });
});
