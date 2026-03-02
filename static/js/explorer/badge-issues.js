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

            // Bug 040: Refresh center pane issue badge for the currently displayed object.
            // On page load, openTab() runs before health-check data is available,
            // so the badge is empty. Now that issues are loaded, update it.
            refreshCenterPaneIssueBadge();
        } catch (e) {
            console.error('Failed to load issues for badges:', e);
        }
    }

    /**
     * Bug 040 / 002-badge: Refresh the issue badge in the center pane breadcrumb
     * for the currently displayed object. Call after issue data changes
     * (health-check load, undo, staging changes) to keep the badge in sync.
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
            // Bug 017: Even with no pending edits, we need to run
            // updateStagedIssuesUI to clear any previously resolved warnings.
            updateStagedIssuesUI();
            return;
        }

        // Bug 017: Check if staged template edits resolve existing warnings
        resolveWarningsFromStagedTemplateEdits();

        // Build a map of original names -> new names for renamed objects
        const renames = new Map(); // "type:originalName" -> newName
        for (const [key, edit] of state.pendingEdits) {
            const obj = StableKey.findObject(key, state.allObjects);
            if (!obj) {continue;}

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
            if (state.stagedObjectDeletions.has(Explorer.getObjectKey(o))) {return;}

            const attrs = Explorer.getEffectiveAttributes(o);

            for (const [field, refType] of Object.entries(referenceFields)) {
                if (!attrs[field]) {continue;}

                // Determine the actual type being referenced
                let targetType = refType;
                if (field === 'use') {
                    targetType = o.object_type; // Templates are same type
                } else if (field === 'members') {
                    // Members type depends on group type
                    const groupInfo = Explorer.constants.groupStructure?.[o.object_type];
                    if (!groupInfo) { continue; }
                    targetType = groupInfo.member_type;
                }

                if (!targetType) {continue;}

                // Check each referenced value
                const values = attrs[field].split(',').map(v => v.trim().split('!')[0]); // Remove command args
                values.forEach(val => {
                    if (!val || val === '*') {return;}

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
    // Bug 017: Resolve warnings when staged template edits provide missing fields
    // =============================================================================

    /**
     * Build a map of template names to their staged edit data.
     * Only includes templates (register=0) that have pending edits.
     */
    function buildEditedTemplatesMap() {
        const editedTemplates = new Map();
        for (const [key, edit] of state.pendingEdits) {
            const obj = StableKey.findObject(key, state.allObjects);
            if (!obj) {continue;}
            if (obj.attributes.register !== '0' && edit.edited.register !== '0') {continue;}
            const tmplName = obj.attributes.name || obj.display_name;
            if (tmplName) {
                editedTemplates.set(tmplName, { attrs: edit.edited, objType: obj.object_type });
            }
        }
        return editedTemplates;
    }

    /**
     * Parse "has no field_name" patterns from a notification_gap message.
     */
    function parseMissingFields(message) {
        const fields = [];
        const regex = / has no (\w+)/g;
        let match;
        while ((match = regex.exec(message)) !== null) {
            fields.push(match[1]);
        }
        return fields;
    }

    /**
     * Collect all attribute names provided by an object's template chain,
     * including any staged edits to those templates.
     */
    function collectTemplateChainFields(obj, editedTemplates) {
        const useAttr = Explorer.getEffectiveAttributes(obj).use;
        if (!useAttr) {return new Set();}

        const providedFields = new Set();
        const visited = new Set();
        const queue = useAttr.split(',').map(t => t.trim());

        while (queue.length > 0) {
            const tmplName = queue.shift();
            if (!tmplName || visited.has(tmplName)) {continue;}
            visited.add(tmplName);

            const editedTmpl = editedTemplates.get(tmplName);
            if (editedTmpl && editedTmpl.objType === obj.object_type) {
                Object.keys(editedTmpl.attrs).forEach(a => providedFields.add(a));
            }

            const tmplObj = state.allObjects.find(o =>
                o.object_type === obj.object_type &&
                (o.attributes.name === tmplName || o.display_name === tmplName)
            );
            if (!tmplObj) {continue;}
            const tmplAttrs = Explorer.getEffectiveAttributes(tmplObj);
            Object.keys(tmplAttrs).forEach(a => providedFields.add(a));
            if (tmplAttrs.use) {
                tmplAttrs.use.split(',').map(t => t.trim()).forEach(t => queue.push(t));
            }
        }
        return providedFields;
    }

    /**
     * Check if staged template edits resolve existing health-check warnings.
     * For example, if generic-contact gains host_notification_period through
     * a staged edit, the "notification chain broken" warning on contacts
     * that inherit from it should be cleared.
     */
    function resolveWarningsFromStagedTemplateEdits() {
        const editedTemplates = buildEditedTemplatesMap();
        if (editedTemplates.size === 0) {return;}

        const keysToRemove = [];
        for (const [key, issue] of state.issuesByObject) {
            if (issue.staged || issue.type !== 'notification_gap') {continue;}

            const missingFields = parseMissingFields(issue.message);
            if (missingFields.length === 0) {continue;}

            const obj = state.allObjects.find(o =>
                o.object_type === issue.object_type &&
                (o.display_name === issue.object || o.attributes.name === issue.object)
            );
            if (!obj) {continue;}

            const providedFields = collectTemplateChainFields(obj, editedTemplates);
            if (missingFields.every(f => providedFields.has(f))) {
                keysToRemove.push(key);
            }
        }

        for (const key of keysToRemove) {
            state.issuesByObject.delete(key);
        }
    }

    // =============================================================================
    // Export to Explorer namespace
    // =============================================================================

    Explorer.loadIssuesForBadges = loadIssuesForBadges;
    Explorer.loadSuggestionsForBadges = loadSuggestionsForBadges;
    Explorer.getObjectIdentity = getObjectIdentity;
    Explorer.computeStagedIssues = computeStagedIssues;
    Explorer.updateStagedIssuesUI = updateStagedIssuesUI;
    Explorer.refreshCenterPaneIssueBadge = refreshCenterPaneIssueBadge;

    // Expose stagedIssues as a getter so it always returns the current value
    Object.defineProperty(Explorer, 'stagedIssues', {
        get: function() { return stagedIssues; },
        enumerable: true
    });

})(window.Explorer);
