/**
 * Nagios Bulk Editor - Base State Module
 *
 * Centralized state object shared across base modules:
 * - Commit dialog state
 * - Git operations state
 *
 * This module must be loaded before other base modules.
 */

// =============================================================================
// Consolidated State
// =============================================================================

export const baseState = {
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

    // Reference analysis
    currentRefData: null,

    // C-10: Pending commit message for retry after failed git commit
    pendingCommitMessage: null
};
