/**
 * Nagios Bulk Editor - Drag and Drop Cleanup Utilities
 *
 * Provides cleanup functions for drag-drop operations.
 * Note: Actual drag-drop handlers are in context-menu.js and file-operations.js.
 */

(function(Explorer) {
    'use strict';

    /**
     * Clean up all drag state - resets visual indicators and internal state.
     * Called by multiple modules at drag end/cancel.
     */
    Explorer.cleanupDragState = function() {
        // Remove all drag-related classes
        document.querySelectorAll('.drop-active, .drag-over, .dragging, .drop-target').forEach(el => {
            el.classList.remove('drop-active', 'drag-over', 'dragging', 'drop-target');
        });

        // Remove dimming effect
        document.body.classList.remove('dragging-objects');

        // Remove insertion markers
        document.querySelectorAll('.drop-indicator').forEach(el => el.remove());

        // Clean up drag badge
        const badge = document.getElementById('drag-badge-temp');
        if (badge) badge.remove();
    };

})(window.Explorer);
