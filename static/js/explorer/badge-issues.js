/**
 * Nagios Bulk Editor - Explorer Badge Issues Module
 *
 * Handles badge and issue calculation for the explorer tree.
 * Consumes backend health-check data for all issue types via mapHealthCheckToState.
 * Client-side only: staged issue detection (broken references from pending edits).
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;

    // Staged issues from pending edits (broken references, orphans, etc.)
    let stagedIssues = [];

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
        } catch (e) {
            console.error('Failed to load issues for badges:', e);
        }
    }

    async function loadSuggestionsForBadges() {
        try {
            // Load health-check data (populates all issue types including orphans)
            const result = await ApiClient.get('/api/health-check');
            if (result.success) {
                state.healthCheckData = result.data;
                Explorer.mapHealthCheckToState(result.data);
            }

            // Load grouping suggestions from server
            const groupingResult = await ApiClient.get('/api/smart-grouping/suggest', { silent: true });
            if (groupingResult.success) {
                state.allGroupingSuggestions = groupingResult.data?.suggestions || [];
            }

            // Update main badge using centralized function that matches collectAllSuggestions()
            Explorer.updateSuggestionsBadge();

            // Update section badges
            Explorer.updateBadge('#groupingSectionBadge', state.allGroupingSuggestions.length);
            Explorer.updateBadge('#templatesSectionBadge', state.allTemplateSuggestions.length);
            Explorer.updateBadge('#cleanupSectionBadge', state.allCleanupSuggestions.length);
            Explorer.updateBadge('#notificationsSectionBadge', state.allNotificationSuggestions.length);

            // Update validation summary banner
            Explorer.updateValidationSummary();
        } catch (e) {
            console.error('Failed to load suggestions for badges:', e);
        }
    }

    // =============================================================================
    // Badge Issue Detection Helpers
    // =============================================================================

    function getObjectIdentity(obj) {
        const nameField = constants.nameFields[obj.object_type];
        if (obj.object_type === 'service') {
            const host = obj.attributes.host_name || obj.attributes.hostgroup_name || '*';
            const desc = obj.attributes.service_description || '';
            return `${host}::${desc}`;
        }
        return nameField ? (obj.attributes[nameField] || '') : (obj.attributes.name || '');
    }

    // =============================================================================
    // Staged Issues (from pending edits)
    // =============================================================================

    // Compute issues that would result from staged changes
    function computeStagedIssues() {
        stagedIssues = [];

        if (state.pendingEdits.size === 0) {
            updateStagedIssuesUI();
            return;
        }

        // Build a map of original names -> new names for renamed objects
        const renames = new Map(); // "type:originalName" -> newName
        for (const [idx, edit] of state.pendingEdits) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (!obj) continue;

            const nameField = Explorer.getNameFieldForObject(obj);
            const originalName = edit.original[nameField] || obj.name || obj.display_name;
            const newName = edit.edited[nameField];

            if (originalName && newName && originalName !== newName) {
                renames.set(`${obj.object_type}:${originalName}`, { newName, obj });
            }
        }

        if (renames.size === 0) {
            updateStagedIssuesUI();
            return;
        }

        // Use centralized reference fields from constants
        const referenceFields = constants.referenceFields;

        // Check all objects for references to renamed objects
        state.allObjects.forEach(o => {
            // Skip deleted objects
            if (state.stagedObjectDeletions.has(o.global_index)) return;

            const attrs = Explorer.getEffectiveAttributes(o);

            for (const [field, refType] of Object.entries(referenceFields)) {
                if (!attrs[field]) continue;

                // Determine the actual type being referenced
                let targetType = refType;
                if (field === 'use') {
                    targetType = o.object_type; // Templates are same type
                } else if (field === 'members') {
                    // Members type depends on group type
                    if (o.object_type === 'hostgroup') targetType = 'host';
                    else if (o.object_type === 'contactgroup') targetType = 'contact';
                    else if (o.object_type === 'servicegroup') targetType = 'service';
                    else continue;
                }

                if (!targetType) continue;

                // Check each referenced value
                const values = attrs[field].split(',').map(v => v.trim().split('!')[0]); // Remove command args
                values.forEach(val => {
                    if (!val || val === '*') return;

                    const renameKey = `${targetType}:${val}`;
                    const rename = renames.get(renameKey);

                    if (rename) {
                        // This object references something that was renamed
                        const displayName = Explorer.getStagedDisplayName(o);
                        stagedIssues.push({
                            severity: 'error',
                            type: 'broken_reference',
                            object_type: o.object_type,
                            object: displayName,
                            message: `References "${val}" which was renamed to "${rename.newName}". Update the ${field} field.`,
                            file: o.source_file,
                            field: field,
                            oldValue: val,
                            newValue: rename.newName,
                            staged: true
                        });
                    }
                });
            }
        });

        updateStagedIssuesUI();
    }

    // Update the issues UI with staged issues (call before buildTree for efficiency)
    function updateStagedIssuesUI() {
        // Clear staged issues from state.issuesByObject first
        for (const [key, issue] of state.issuesByObject) {
            if (issue.staged) {
                state.issuesByObject.delete(key);
            }
        }

        // Add new staged issues to map
        stagedIssues.forEach(issue => {
            const key = `${issue.object_type}:${issue.object}`;
            // Staged issues take precedence
            state.issuesByObject.set(key, issue);
        });

        // Rebuild grouped errors and update badge
        Explorer.filterIssues();

        const badge = document.getElementById('issuesSectionBadge');
        if (badge) {
            badge.textContent = state.groupedErrors.length;
            badge.style.display = state.groupedErrors.length > 0 ? 'inline-flex' : 'none';
        }

        // Update validation summary banner in suggestions tab
        Explorer.updateValidationSummary();

        // Update the main suggestions badge as well
        Explorer.updateSuggestionsBadge();
    }

    // =============================================================================
    // Export to Explorer namespace
    // =============================================================================

    Explorer.loadIssuesForBadges = loadIssuesForBadges;
    Explorer.loadSuggestionsForBadges = loadSuggestionsForBadges;
    Explorer.getObjectIdentity = getObjectIdentity;
    Explorer.computeStagedIssues = computeStagedIssues;
    Explorer.updateStagedIssuesUI = updateStagedIssuesUI;

    // Expose stagedIssues as a getter so it always returns the current value
    Object.defineProperty(Explorer, 'stagedIssues', {
        get: function() { return stagedIssues; },
        enumerable: true
    });

})(window.Explorer);
