/**
 * Nagios Bulk Editor - UI Utilities Module
 *
 * Common UI utilities for the Explorer module.
 *
 * Dependencies:
 * - window.Explorer (from main.js)
 * - window.showToast (from base.js)
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
    // SVG Icons
    // =============================================================================

    Explorer.icons = {
        'chevron-right': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>',
        'folder': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>',
        'folder-open': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v1"></path><path d="M2 10h20"></path></svg>',
        'file-text': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>',
        'file-plus': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>',
        'folder-plus': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v11z"></path><line x1="12" y1="11" x2="12" y2="17"></line><line x1="9" y1="14" x2="15" y2="14"></line></svg>',
        'plus': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>',
        'minimize-2': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>',
        'refresh-cw': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>',
        'more-horizontal': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle></svg>',
        'trash-2': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>',
        'grip-vertical': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="5" r="1"></circle><circle cx="9" cy="12" r="1"></circle><circle cx="9" cy="19" r="1"></circle><circle cx="15" cy="5" r="1"></circle><circle cx="15" cy="12" r="1"></circle><circle cx="15" cy="19" r="1"></circle></svg>',
        'x': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
        'edit': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>',
        'copy': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>'
    };

    /**
     * Get SVG icon HTML
     */
    Explorer.getIcon = function(name) {
        return Explorer.icons[name] || '';
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
                if (count > 0) {
                    badge.classList.remove('u-hidden');
                } else {
                    badge.classList.add('u-hidden');
                }
            }
        }
    };

    // =============================================================================
    // Toast Notifications
    // =============================================================================

    /**
     * Show toast notification (wrapper for global showToast)
     */
    Explorer.showToast = function(message, type = 'info', duration = 3000) {
        window.showToast(message, type, duration);
    };

    // =============================================================================
    // Path Utilities
    // =============================================================================

    /**
     * Convert absolute path to display path with config folder prefix
     * @param {string} path - Absolute path
     * @returns {string} Display path with config root name
     */
    Explorer.toDisplayPath = function(path) {
        if (!path) return '';
        const configPath = Explorer.state.configPath;
        const configRootName = Explorer.getConfigRootName();

        if (path.startsWith(configPath + '/')) {
            return configRootName + '/' + path.substring(configPath.length + 1);
        } else if (path === configPath) {
            return configRootName;
        }
        if (!path.startsWith('/')) {
            return configRootName + '/' + path;
        }
        return path;
    };

    /**
     * Convert display path back to absolute path
     * @param {string} displayPath - Display path with config root name
     * @returns {string} Absolute path
     */
    Explorer.toAbsolutePath = function(displayPath) {
        if (!displayPath) return '';
        const configPath = Explorer.state.configPath;
        const configRootName = Explorer.getConfigRootName();

        if (displayPath.startsWith(configRootName + '/')) {
            return configPath + '/' + displayPath.substring(configRootName.length + 1);
        } else if (displayPath === configRootName) {
            return configPath;
        }
        if (displayPath.startsWith('/')) {
            return displayPath;
        }
        return configPath + '/' + displayPath;
    };

    // =============================================================================
    // Error Handling
    // =============================================================================

    /**
     * Centralized API error handler
     * @param {string} context - Description of what operation failed
     * @param {string} error - Error message
     * @param {boolean} showToast - Whether to show a toast notification
     */
    Explorer.handleApiError = function(context, error, showToast = false) {
        console.error(`${context}:`, error);
        if (showToast) {
            Explorer.showToast(`${context}: ${error}`, 'error');
        }
    };

})(window.Explorer);
