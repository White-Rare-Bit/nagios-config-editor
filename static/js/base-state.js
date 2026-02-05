/**
 * Nagios Bulk Editor - Base State Module
 *
 * Centralized state object shared across base modules:
 * - Lock status
 * - Commit dialog state
 * - Git operations state
 *
 * This module must be loaded before other base modules.
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

// Export to global scope for other modules
window.baseState = baseState;
