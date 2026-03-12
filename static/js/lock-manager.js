/**
 * Nagios Bulk Editor - Lock Manager Module
 *
 * Handles editing lock status checking and UI updates.
 * Prevents concurrent edits by different users.
 */

import { baseState } from './base-state.js';
import { ApiClient } from './api-client.js';
import { escapeHtml } from './app.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { getSessionId } from './session-manager.js';

let explorerRenderCallback = null;

/**
 * Register a callback for re-rendering the center pane when lock state changes.
 */
export function registerLockChangeCallback(callback) {
    explorerRenderCallback = callback;
}

/**
 * Check current lock status from server and update UI.
 * @returns {Promise<object|null>} Lock status data or null on error
 */
export async function checkLockStatus() {
    const result = await ApiClient.get('/api/staging/lock', { silent: true });

    if (!result.success) {
        console.error('Failed to check lock status:', result.error);
        return null;
    }

    const data = result.data.data;
    const wasLocked = baseState.isEditingLocked;
    const isOwner = data.session_id === getSessionId();
    baseState.isEditingLocked = data.locked && !isOwner;
    baseState.lockOwner = data.session_id;
    baseState.lockUserName = data.user_name;
    baseState.lockUserEmail = data.user_email;

    updateLockBannerUI();

    // When lock state changes, re-render editor to update field editability
    if (wasLocked !== baseState.isEditingLocked && explorerRenderCallback) {
        explorerRenderCallback();
    }

    return data;
}

/**
 * Update the lock banner UI based on current lock state.
 */
function updateLockBannerUI() {
    const banner = document.getElementById('lockBanner');
    const bannerText = document.getElementById('lockBannerText');
    if (!banner) { return; }

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

/**
 * Break another user's lock (admin action).
 * Requires confirmation and discards the other user's pending changes.
 */
export async function breakLock() {
    const confirmed = await showConfirmDialog({
        title: 'Break Lock',
        message: 'Are you sure you want to break the lock? This will discard the other user\'s pending changes.',
        confirmText: 'Break Lock',
        cancelText: 'Cancel',
        type: 'danger'
    });

    if (!confirmed) { return; }

    const result = await ApiClient.post('/api/staging/lock/break', {}, { silent: true });

    if (result.success && result.data?.success) {
        baseState.isEditingLocked = false;
        baseState.lockOwner = null;
        baseState.lockUserName = null;
        baseState.lockUserEmail = null;
        updateLockBannerUI();
        showToast('Lock broken - staging cleared', 'success');
    } else {
        showToast(result.data?.error || result.error || 'Failed to break lock', 'error');
    }
}
