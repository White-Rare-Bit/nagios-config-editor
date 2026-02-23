/**
 * Nagios Bulk Editor - Lock Manager Module
 *
 * Handles editing lock status checking and UI updates.
 * Prevents concurrent edits by different users.
 *
 * Dependencies (loaded before this file):
 * - base-state.js: baseState object
 * - ui-notifications.js: showToast, showConfirmDialog
 * - api-client.js: ApiClient
 * - app.js: escapeHtml
 *
 * Runtime dependencies (loaded after, called at runtime):
 * - base.js: updateNavCommitButton, showGitOperationResult
 */

// =============================================================================
// Lock Status Management
// =============================================================================

/**
 * Check current lock status from server and update UI.
 * @returns {Promise<object|null>} Lock status data or null on error
 */
async function checkLockStatus() {
    const result = await ApiClient.get('/api/staging/lock', { silent: true });

    if (!result.success) {
        console.error('Failed to check lock status:', result.error);
        return null;
    }

    const data = result.data;
    const wasLocked = baseState.isEditingLocked;
    baseState.isEditingLocked = data.locked && !data.isOwner;
    baseState.lockOwner = data.owner;
    baseState.lockUserName = data.userName;
    baseState.lockUserEmail = data.userEmail;
    // Update legacy alias
    window.isEditingLocked = baseState.isEditingLocked;

    updateLockBannerUI();

    // When lock state changes, re-render editor to update field editability
    if (wasLocked !== baseState.isEditingLocked) {
        if (typeof Explorer !== 'undefined' && typeof Explorer.renderCenterAttributes === 'function') {
            Explorer.renderCenterAttributes();
        }
    }

    return data;
}

/**
 * Update the lock banner UI based on current lock state.
 */
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

/**
 * Break another user's lock (admin action).
 * Requires confirmation and discards the other user's pending changes.
 */
async function breakLock() {
    const confirmed = await showConfirmDialog({
        title: 'Break Lock',
        message: 'Are you sure you want to break the lock? This will discard the other user\'s pending changes.',
        confirmText: 'Break Lock',
        cancelText: 'Cancel',
        type: 'danger'
    });

    if (!confirmed) {return;}

    const result = await ApiClient.post('/api/staging/lock/break', {}, { silent: true });

    if (result.success && result.data?.success) {
        baseState.isEditingLocked = false;
        baseState.lockOwner = null;
        baseState.lockUserName = null;
        baseState.lockUserEmail = null;
        window.isEditingLocked = false;
        updateLockBannerUI();

        // Call functions from base.js (loaded after, available at runtime)
        if (typeof updateNavCommitButton === 'function') {
            updateNavCommitButton(0);
        }

        if (result.data.gitDiscarded) {
            if (typeof showGitOperationResult === 'function') {
                showGitOperationResult('Discard All Changes', 'git checkout -- . && git clean -fd', true,
                    'All uncommitted changes have been discarded.');
            }
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

// Export to global scope for backward compatibility and cross-module access
window.checkLockStatus = checkLockStatus;
window.updateLockBannerUI = updateLockBannerUI;
window.breakLock = breakLock;
