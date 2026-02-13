/**
 * Nagios Bulk Editor - UI Notifications Module
 *
 * Handles toast notifications and confirmation dialogs.
 * Extracted from base.js to reduce complexity.
 *
 * Dependencies (from app.js, loaded before this file):
 * - escapeHtml(text) - Escape HTML special characters
 */

// =============================================================================
// Toast Notifications
// =============================================================================

/**
 * Show a toast notification.
 * @param {string} message - Message to display
 * @param {string} [type='info'] - Type: 'success', 'error', 'warning', 'info'
 * @param {number} [duration=3000] - Duration in ms (0 = permanent)
 * @returns {HTMLElement|null} The toast element, or null if filtered
 */
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
// Confirmation Dialog
// =============================================================================

/**
 * Show a confirmation dialog.
 * @param {object} [options] - Dialog options
 * @param {string} [options.title='Confirm'] - Dialog title
 * @param {string} [options.message='Are you sure?'] - Dialog message
 * @param {string} [options.confirmText='Confirm'] - Confirm button text
 * @param {string} [options.cancelText='Cancel'] - Cancel button text
 * @param {string} [options.type='warning'] - Type: 'warning', 'danger', 'info'
 * @param {boolean} [options.showCancel=true] - Whether to show cancel button
 * @param {boolean} [options.allowHtml=false] - Allow HTML in message
 * @returns {Promise<boolean>} True if confirmed, false if cancelled
 */
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
        confirmBtn.className = 'nbe-btn nbe-btn--dark nbe-btn--sm ' + (type === 'danger' ? 'nbe-btn--danger' : 'nbe-btn--tonal');

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

// Export to global scope for backward compatibility
window.showToast = showToast;
window.showConfirmDialog = showConfirmDialog;
