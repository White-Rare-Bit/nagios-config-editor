/**
 * Nagios Bulk Editor - Frontend JavaScript
 */

// ============================================================================
// Global Functions
// ============================================================================

/**
 * Reload Nagios configuration from disk
 */
async function reloadConfig() {
    const result = await ApiClient.post('/api/reload', {}, { errorPrefix: 'Reload' });
    if (result.success) {
        location.reload();
    }
}

/**
 * Create a manual backup
 */
async function createBackup() {
    const description = prompt('Enter a description for this backup (optional):');
    if (description === null) return; // Cancelled

    const result = await ApiClient.post('/api/backups', {
        description: description || 'Manual backup'
    }, { silent: true });

    if (result.success) {
        alert('Backup created successfully!\n\nPath: ' + result.data.path);
    } else {
        alert('Error creating backup: ' + (result.error || 'Unknown error'));
    }
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Escape HTML special characters
 */
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

/**
 * Escape special regex characters
 * @param {*} str - String to escape (handles null/undefined)
 * @returns {string} Escaped string safe for use in RegExp
 */
function escapeRegex(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Debounce function for search inputs
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Generate a unique ID for staged operations
 * @returns {string} A unique identifier string
 */
function generateUniqueId() {
    return Date.now().toString(36) + Math.random().toString(36).substring(2, 10);
}

/**
 * Format a date string for display.
 * @param {string} dateStr - Date string to format
 * @param {boolean} useRelative - If true, use relative time ("2 hours ago"). Default: true
 * @returns {string} Formatted date string
 */
function formatDate(dateStr, useRelative = true) {
    if (!dateStr) return '-';
    try {
        const date = new Date(dateStr);

        if (!useRelative) {
            return date.toLocaleString();
        }

        const now = new Date();
        const diff = now - date;

        // Less than 1 hour
        if (diff < 3600000) {
            const mins = Math.floor(diff / 60000);
            return mins <= 1 ? 'just now' : `${mins} minutes ago`;
        }

        // Less than 24 hours
        if (diff < 86400000) {
            const hours = Math.floor(diff / 3600000);
            return hours === 1 ? '1 hour ago' : `${hours} hours ago`;
        }

        // Less than 7 days
        if (diff < 604800000) {
            const days = Math.floor(diff / 86400000);
            return days === 1 ? 'yesterday' : `${days} days ago`;
        }

        // Otherwise show date
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch (e) {
        return dateStr;
    }
}

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
 * Copy text to clipboard
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (err) {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            return true;
        } catch (err) {
            return false;
        } finally {
            textArea.remove();
        }
    }
}

// ============================================================================
// API Helper Functions
// ============================================================================

// API requests should use ApiClient (defined in api-client.js) which provides:
// - Standardized error handling with toast notifications
// - Automatic session headers for staging lock management
// - Consistent {success, data, error} response format
//
// Example: const result = await ApiClient.post('/api/endpoint', data, { silent: false });

// ============================================================================
// Notification Functions
// ============================================================================

// showToast() is defined in base.js (loaded after app.js but provides the
// authoritative implementation with message filtering). Use that global function.

// ============================================================================
// Keyboard Shortcuts
// ============================================================================

// Use a named function and guard to prevent duplicate listeners
function handleGlobalKeydown(e) {
    // Ctrl/Cmd + R: Reload config (prevent browser refresh)
    if ((e.ctrlKey || e.metaKey) && e.key === 'r' && e.shiftKey) {
        e.preventDefault();
        reloadConfig();
    }

    // Ctrl/Cmd + B: Create backup
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        createBackup();
    }

    // Escape: Close modals
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('.modal.show');
        modals.forEach(modal => {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        });
    }
}

// Only add listener once
if (!window._globalKeydownAdded) {
    document.addEventListener('keydown', handleGlobalKeydown);
    window._globalKeydownAdded = true;
}

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips if Bootstrap is loaded
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
        const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltips.forEach(el => new bootstrap.Tooltip(el));
    }

    // Add confirmation to dangerous buttons using consistent dialog
    document.querySelectorAll('[data-confirm]').forEach(button => {
        button.addEventListener('click', async function(e) {
            e.preventDefault();
            e.stopPropagation();
            const confirmed = await showConfirmDialog({
                title: 'Confirm Action',
                message: this.dataset.confirm,
                confirmText: 'Continue',
                type: 'warning'
            });
            if (confirmed) {
                // Re-dispatch the click without the confirm handler
                this.removeAttribute('data-confirm');
                this.click();
            }
        });
    });

    console.log('Nagios Bulk Editor initialized');
});
