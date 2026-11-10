/**
 * Nagios Bulk Editor - UI Notifications Module
 *
 * Handles toast notifications and confirmation dialogs.
 */
import { escapeHtml } from './app.js'; // circular

// =============================================================================
// Toast Notifications
// =============================================================================

/**
 * Show a toast notification.
 * @param {string} message - Message to display
 * @param {string} [type='info'] - Type: 'success', 'error', 'warning', 'info'
 * @param {number} [duration=3000] - Duration in ms (0 = permanent)
 * @returns {HTMLElement|null} The toast element
 */
export function showToast(message, type = 'info', duration = 3000) {
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
 * @param {boolean} [options.allowHtml=false] - Render message as HTML; caller must escapeHtml() every interpolated value
 * @returns {Promise<boolean>} True if confirmed, false if cancelled
 */
export function showConfirmDialog(options = {}) {
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
        // Messages embed object/file names, so they are text unless the caller
        // opts in with allowHtml (and then escapes every value it interpolates).
        if (allowHtml) {
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
                // Enter activates whichever button has focus: on Cancel it cancels.
                if (document.activeElement === cancelBtn) {
                    e.preventDefault();
                    handleCancel();
                } else {
                    handleConfirm();
                }
            } else if (e.key === 'Tab') {
                // Focus trap: cycle between the buttons while the dialog is open
                // (only the confirm button when Cancel is hidden).
                e.preventDefault();
                const buttons = showCancel ? [confirmBtn, cancelBtn] : [confirmBtn];
                const idx = buttons.indexOf(document.activeElement);
                const step = e.shiftKey ? -1 : 1;
                // Nothing focused yet: Tab goes to the first, Shift+Tab to the last.
                let next = (idx + step + buttons.length) % buttons.length;
                if (idx === -1) {next = e.shiftKey ? buttons.length - 1 : 0;}
                buttons[next].focus();
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

