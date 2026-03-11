/**
 * Nagios Bulk Editor - Explorer Badge Issues Module
 *
 * Handles badge and issue calculation for the explorer tree.
 * Consumes backend health-check data for all issue types via mapHealthCheckToState.
 *
 * Shadow copy architecture: no client-side staged issue detection needed —
 * health-check runs against the shadow copy which already reflects all edits.
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // =============================================================================
    // Issue Loading
    // =============================================================================

    async function loadIssuesForBadges() {
        try {
            const result = await ApiClient.get('/api/health-check');
            if (result.success) {
                state.healthCheckData = result.data;
                Explorer.mapHealthCheckToState(result.data);
            }

            // Build grouped errors and update badge
            Explorer.filterIssues();
            Explorer.updateBadge('#issuesSectionBadge', state.groupedErrors.length);
            // Re-render tree to show badges
            Explorer.buildTree();

            refreshCenterPaneIssueBadge();
        } catch (e) {
            console.error('Failed to load issues for badges:', e);
        }
    }

    /**
     * Refresh the issue badge in the center pane breadcrumb
     * for the currently displayed object.
     */
    function refreshCenterPaneIssueBadge() {
        if (!state.editedObject) {return;}
        const issueBtn = document.getElementById('centerCardIssue');
        if (!issueBtn) {return;}
        const obj = state.editedObject;
        const issue = Explorer.getObjectIssue(obj);
        const hostListInfo = Explorer.getHostListInfo(obj);
        Explorer.updateIssueBadge(issueBtn, issue, obj, hostListInfo);
    }

    async function loadSuggestionsForBadges() {
        try {
            const result = await ApiClient.get('/api/health-check');
            if (result.success) {
                state.healthCheckData = result.data;
                Explorer.mapHealthCheckToState(result.data);
            }

            const groupingResult = await ApiClient.get('/api/smart-grouping/suggest', { silent: true });
            if (groupingResult.success) {
                state.allGroupingSuggestions = groupingResult.data?.suggestions || [];
            }

            Explorer.updateSuggestionsBadge();

            Explorer.updateBadge('#groupingSectionBadge', state.allGroupingSuggestions.length);
            Explorer.updateBadge('#templatesSectionBadge', state.allTemplateSuggestions.length);
            Explorer.updateBadge('#cleanupSectionBadge', state.allCleanupSuggestions.length);
            Explorer.updateBadge('#notificationsSectionBadge', state.allNotificationSuggestions.length);

            Explorer.updateValidationSummary();
        } catch (e) {
            console.error('Failed to load suggestions for badges:', e);
        }
    }

    // Shadow copy: no-ops — health-check data already reflects shadow state
    function computeStagedIssues() {}
    function updateStagedIssuesUI() {}

    // =============================================================================
    // Export to Explorer namespace
    // =============================================================================

    Explorer.loadIssuesForBadges = loadIssuesForBadges;
    Explorer.loadSuggestionsForBadges = loadSuggestionsForBadges;
    Explorer.computeStagedIssues = computeStagedIssues;
    Explorer.updateStagedIssuesUI = updateStagedIssuesUI;
    Explorer.refreshCenterPaneIssueBadge = refreshCenterPaneIssueBadge;

    // Expose stagedIssues as empty array (no longer populated client-side)
    Object.defineProperty(Explorer, 'stagedIssues', {
        get: function() { return []; },
        enumerable: true
    });

})(window.Explorer);
