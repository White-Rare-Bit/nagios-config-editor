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
