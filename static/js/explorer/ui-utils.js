/**
 * Nagios Bulk Editor - UI Utilities Module
 *
 * Common UI utilities, icons, and helper functions.
 */

(function(Explorer) {
    'use strict';

    // =============================================================================
    // Tab Switching
    // =============================================================================

    /**
     * Generic tab switching utility
     */
    Explorer.switchTabs = function(buttonSelector, contentSelector, activeValue, dataAttr, contentSuffix) {
        document.querySelectorAll(buttonSelector).forEach(btn => {
            btn.classList.toggle('active', btn.dataset[dataAttr] === activeValue);
        });
        document.querySelectorAll(contentSelector).forEach(content => {
            content.classList.toggle('active', content.id === activeValue + contentSuffix);
        });
    };

    // =============================================================================
    // Icons
    // =============================================================================

    /**
     * Get icon for object type
     */
    Explorer.getObjectTypeIcon = function(type) {
        const icons = {
            host: 'server',
            hostgroup: 'server',
            service: 'activity',
            servicegroup: 'layers',
            contact: 'user',
            contactgroup: 'users',
            command: 'terminal',
            timeperiod: 'clock',
            servicedependency: 'git-merge',
            hostdependency: 'git-merge',
            serviceescalation: 'trending-up',
            hostescalation: 'trending-up'
        };
        return icons[type] || 'file';
    };

    /**
     * Get icon for issue type
     */
    Explorer.getIssueIcon = function(issueType) {
        const icons = {
            missing: 'alert-circle',
            duplicate: 'copy',
            circular: 'refresh-cw',
            orphan: 'link-2',
            unused: 'archive',
            error: 'x-circle',
            warning: 'alert-triangle'
        };
        return icons[issueType] || 'alert-circle';
    };

    /**
     * Render feather icon HTML
     */
    Explorer.icon = function(name, size = 16) {
        return `<i data-feather="${name}" style="width:${size}px;height:${size}px"></i>`;
    };

    // =============================================================================
    // Badge Updates
    // =============================================================================

    /**
     * Update badge count with optional hide when zero
     */
    Explorer.updateBadge = function(selector, count, hideWhenZero = true) {
        const badge = document.querySelector(selector);
        if (badge) {
            badge.textContent = count;
            if (hideWhenZero) {
                // Use classList to toggle u-hidden class (which has !important)
                if (count > 0) {
                    badge.classList.remove('u-hidden');
                } else {
                    badge.classList.add('u-hidden');
                }
            }
        }
    };

    /**
     * Update selection count indicator in toolbar
     */
    Explorer.updateSelectionCount = function() {
    };

    // =============================================================================
    // Toast Notifications
    // =============================================================================

    /**
     * Show toast notification
     */
    Explorer.showToast = function(message, type = 'info', duration = 3000) {
        // Use global showToast if available
        if (typeof window.showToast === 'function' && window.showToast !== Explorer.showToast) {
            window.showToast(message, type, duration);
            return;
        }

        // Fallback implementation
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;

        container.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, duration);
    };

    // =============================================================================
    // Dialog Utilities
    // =============================================================================

    /**
     * Show confirmation dialog using the global showConfirmDialog
     */
    Explorer.confirm = async function(message, onConfirm, onCancel) {
        // Use global showConfirmDialog from base.js
        if (typeof showConfirmDialog === 'function') {
            const confirmed = await showConfirmDialog({
                title: 'Confirm',
                message: message,
                confirmText: 'Yes',
                type: 'warning'
            });
            if (confirmed) {
                if (onConfirm) onConfirm();
            } else {
                if (onCancel) onCancel();
            }
            return;
        }

        // Fallback to native confirm (should rarely happen)
        if (window.confirm(message)) {
            if (onConfirm) onConfirm();
        } else {
            if (onCancel) onCancel();
        }
    };

    // =============================================================================
    // DOM Utilities
    // =============================================================================

    /**
     * Debounce function calls
     */
    Explorer.debounce = function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    /**
     * Throttle function calls
     */
    Explorer.throttle = function(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    };

    // =============================================================================
    // Keyboard Shortcuts
    // =============================================================================

    /**
     * Check if event is escape key
     */
    Explorer.isEscapeKey = function(event) {
        return event.key === 'Escape' || event.keyCode === 27;
    };

    /**
     * Check if event is enter key
     */
    Explorer.isEnterKey = function(event) {
        return event.key === 'Enter' || event.keyCode === 13;
    };

    /**
     * Check if modifier key is pressed (Ctrl on Windows/Linux, Cmd on Mac)
     */
    Explorer.isModifierKey = function(event) {
        return event.metaKey || event.ctrlKey;
    };

})(window.Explorer);
