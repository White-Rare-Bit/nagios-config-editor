/**
 * Nagios Bulk Editor - Explorer Badge Issues Module
 *
 * Handles badge and issue calculation for the explorer tree.
 * Consumes backend health-check data for all issue types via mapHealthCheckToState.
 *
 * Shadow copy architecture: no client-side staged issue detection needed —
 * health-check runs against the shadow copy which already reflects all edits.
 */

import { state } from './state.js';
import { ApiClient } from '../api-client.js';
import { updateBadge } from './ui-utils.js';
import { updateIssueBadge } from './object-editor.js'; // circular — safe (function-level)
import { mapHealthCheckToState, updateSuggestionsBadge, updateValidationSummary } from './analysis.js'; // circular — safe (function-level)
import { filterIssues } from './analysis-issues.js'; // circular — safe (function-level)
import { buildTree, getObjectIssue, getHostListInfo } from './app.js'; // circular — safe (function-level)

// =============================================================================
// Issue Loading
// =============================================================================

export async function loadIssuesForBadges() {
    try {
        const result = await ApiClient.get('/api/health-check');
        if (result.success) {
            state.healthCheckData = result.data;
            mapHealthCheckToState(result.data);
        }

        // Build grouped errors and update badge
        filterIssues();
        updateBadge('#issuesSectionBadge', state.groupedErrors.length);
        // Re-render tree to show badges
        buildTree();

        refreshCenterPaneIssueBadge();
    } catch (e) {
        console.error('Failed to load issues for badges:', e);
    }
}

/**
 * Refresh the issue badge in the center pane breadcrumb
 * for the currently displayed object.
 */
export function refreshCenterPaneIssueBadge() {
    if (!state.editedObject) {return;}
    const issueBtn = document.getElementById('centerCardIssue');
    if (!issueBtn) {return;}
    const obj = state.editedObject;
    const issue = getObjectIssue(obj);
    const hostListInfo = getHostListInfo(obj);
    updateIssueBadge(issueBtn, issue, obj, hostListInfo);
}

export async function loadSuggestionsForBadges() {
    try {
        const result = await ApiClient.get('/api/health-check');
        if (result.success) {
            state.healthCheckData = result.data;
            mapHealthCheckToState(result.data);
        }

        const groupingResult = await ApiClient.get('/api/smart-grouping/suggest', { silent: true });
        if (groupingResult.success) {
            state.allGroupingSuggestions = groupingResult.data?.suggestions || [];
        }

        updateSuggestionsBadge();

        updateBadge('#groupingSectionBadge', state.allGroupingSuggestions.length);
        updateBadge('#templatesSectionBadge', state.allTemplateSuggestions.length);
        updateBadge('#cleanupSectionBadge', state.allCleanupSuggestions.length);
        updateBadge('#notificationsSectionBadge', state.allNotificationSuggestions.length);

        updateValidationSummary();
    } catch (e) {
        console.error('Failed to load suggestions for badges:', e);
    }
}

// Shadow copy: no-ops — health-check data already reflects shadow state
export function computeStagedIssues() {}
export function updateStagedIssuesUI() {}
