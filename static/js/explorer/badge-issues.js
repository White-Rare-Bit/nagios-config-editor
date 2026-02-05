/**
 * Nagios Bulk Editor - Explorer Badge Issues Module
 *
 * Handles badge and issue calculation for the explorer tree.
 * Detects duplicates, unused objects, empty groups, orphans, and staged issues.
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
            const response = await fetch('/api/health-check');
            const result = await response.json();
            state.allIssues = result.issues || [];
            state.issuesByObject.clear();
            state.allIssues.forEach(issue => {
                const key = `${issue.object_type}:${issue.object}`;
                if (!state.issuesByObject.has(key) || issue.severity === 'error') {
                    state.issuesByObject.set(key, issue);
                }
            });

            // Add client-side duplicate detection
            addCleanupIssuesToBadges();

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
            // Load issues from server
            const issuesResponse = await fetch('/api/health-check');
            const issuesResult = await issuesResponse.json();
            state.allIssues = issuesResult.issues || [];

            // Load grouping suggestions from server
            const response = await fetch('/api/smart-grouping/suggest');
            const result = await response.json();
            state.allGroupingSuggestions = result.suggestions || [];

            // Load client-side analysis suggestions
            state.allTemplateSuggestions = Explorer.analyzeTemplateConsolidation();
            state.allCleanupSuggestions = Explorer.analyzeCleanupIssues();
            state.allNotificationSuggestions = Explorer.analyzeNotificationGaps();

            // Build grouped errors (this populates state.groupedErrors array)
            Explorer.filterIssues();

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
        switch (obj.object_type) {
            case 'host': return obj.attributes.host_name;
            case 'service':
                return `${obj.attributes.host_name || obj.attributes.hostgroup_name || '*'}::${obj.attributes.service_description}`;
            case 'contact': return obj.attributes.contact_name;
            case 'hostgroup': return obj.attributes.hostgroup_name;
            case 'servicegroup': return obj.attributes.servicegroup_name;
            case 'contactgroup': return obj.attributes.contactgroup_name;
            case 'command': return obj.attributes.command_name;
            case 'timeperiod': return obj.attributes.timeperiod_name;
            default: return null;
        }
    }

    function addDuplicateIssuesToBadges() {
        const identityMap = new Map();

        for (const obj of state.allObjects) {
            if (obj.attributes.register === '0') continue;
            const identity = getObjectIdentity(obj);
            if (identity) {
                const key = `${obj.object_type}:${identity}`;
                if (!identityMap.has(key)) identityMap.set(key, []);
                identityMap.get(key).push(obj);
            }
        }

        for (const [key, objects] of identityMap) {
            if (objects.length > 1) {
                const identity = key.substring(key.indexOf(':') + 1);
                objects.forEach(obj => {
                    const issueKey = `${obj.object_type}:${obj.display_name}`;
                    const otherFiles = objects
                        .filter(o => o.global_index !== obj.global_index)
                        .map(o => o.source_file.split('/').pop())
                        .join(', ');
                    state.issuesByObject.set(issueKey, {
                        type: 'duplicate_name',
                        severity: 'error',
                        object: obj.name || obj.display_name,
                        object_type: obj.object_type,
                        file: obj.source_file,
                        message: `Duplicate ${obj.object_type} name (also in ${otherFiles})`,
                        identity: identity
                    });
                });
            }
        }
    }

    function buildUsageSets() {
        const usedCommands = new Set();
        const usedContacts = new Set();
        const usedContactgroups = new Set();
        const usedTimeperiods = new Set();
        const usedTemplates = new Set();

        const commandAttrs = ['check_command', 'event_handler', 'host_notification_commands', 'service_notification_commands'];
        const timeperiodAttrs = ['check_period', 'notification_period', 'host_notification_period', 'service_notification_period', 'dependency_period', 'exclude'];
        const stripPfx = s => s.trim().replace(/^[+!]+/, '').trim();

        for (const obj of state.allObjects) {
            for (const attr of commandAttrs) {
                if (obj.attributes[attr]) {
                    obj.attributes[attr].split(',').map(s => s.trim().split('!')[0]).forEach(cmd => usedCommands.add(cmd));
                }
            }
            if (obj.attributes.contacts) {
                obj.attributes.contacts.split(',').map(stripPfx).forEach(c => usedContacts.add(c));
            }
            if (obj.attributes.contact_groups) {
                obj.attributes.contact_groups.split(',').map(stripPfx).forEach(cg => usedContactgroups.add(cg));
            }
            for (const attr of timeperiodAttrs) {
                if (obj.attributes[attr]) {
                    obj.attributes[attr].split(',').map(stripPfx).forEach(tp => usedTimeperiods.add(tp));
                }
            }
            if (obj.attributes.use) {
                obj.attributes.use.split(',').map(stripPfx).forEach(u => usedTemplates.add(u));
            }
        }

        // Contact group members count as used contacts
        const contactgroups = state.allObjects.filter(o => o.object_type === 'contactgroup');
        for (const cg of contactgroups) {
            if (cg.attributes.members) {
                cg.attributes.members.split(',').map(stripPfx).forEach(c => usedContacts.add(c));
            }
            if (cg.attributes.contactgroup_members) {
                cg.attributes.contactgroup_members.split(',').map(stripPfx).forEach(c => usedContactgroups.add(c));
            }
        }

        // Contacts can reference contactgroups
        const contacts = state.allObjects.filter(o => o.object_type === 'contact');
        for (const contact of contacts) {
            if (contact.attributes.contactgroups) {
                contact.attributes.contactgroups.split(',').map(stripPfx).forEach(cg => usedContactgroups.add(cg));
            }
        }

        return { usedCommands, usedContacts, usedContactgroups, usedTimeperiods, usedTemplates };
    }

    function addUnusedIssuesToBadges(usageSets) {
        const { usedCommands, usedContacts, usedContactgroups, usedTimeperiods, usedTemplates } = usageSets;

        for (const obj of state.allObjects) {
            const issueKey = `${obj.object_type}:${obj.display_name}`;
            if (state.issuesByObject.has(issueKey) && state.issuesByObject.get(issueKey).severity === 'error') continue;

            if (obj.attributes.register === '0') {
                const templateName = obj.attributes.name;
                if (templateName && !usedTemplates.has(templateName)) {
                    state.issuesByObject.set(issueKey, { type: 'unused_template', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused template' });
                }
                continue;
            }

            if (obj.object_type === 'command') {
                const cmdName = obj.attributes.command_name;
                if (cmdName && !usedCommands.has(cmdName)) {
                    state.issuesByObject.set(issueKey, { type: 'unused_command', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused command' });
                }
            }

            if (obj.object_type === 'contact') {
                const contactName = obj.attributes.contact_name;
                if (contactName && !usedContacts.has(contactName)) {
                    state.issuesByObject.set(issueKey, { type: 'unused_contact', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused contact' });
                }
            }

            if (obj.object_type === 'contactgroup') {
                const cgName = obj.attributes.contactgroup_name;
                if (cgName && !usedContactgroups.has(cgName)) {
                    state.issuesByObject.set(issueKey, { type: 'unused_contactgroup', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused contactgroup' });
                }
            }

            if (obj.object_type === 'timeperiod') {
                const tpName = obj.attributes.timeperiod_name;
                if (tpName && !usedTimeperiods.has(tpName)) {
                    state.issuesByObject.set(issueKey, { type: 'unused_timeperiod', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused timeperiod' });
                }
            }
        }
    }

    function addEmptyGroupIssuesToBadges() {
        const groupTypes = [
            { type: 'hostgroup', nameAttr: 'hostgroup_name', memberAttrs: ['members', 'hostgroup_members'], memberOf: 'hostgroups' },
            { type: 'servicegroup', nameAttr: 'servicegroup_name', memberAttrs: ['members', 'servicegroup_members'], memberOf: 'servicegroups' },
            { type: 'contactgroup', nameAttr: 'contactgroup_name', memberAttrs: ['members', 'contactgroup_members'], memberOf: 'contactgroups' }
        ];

        for (const gt of groupTypes) {
            const groups = state.allObjects.filter(o => o.object_type === gt.type);
            for (const group of groups) {
                const groupName = group.attributes[gt.nameAttr];
                if (!groupName) continue;

                const issueKey = `${group.object_type}:${group.display_name}`;
                if (state.issuesByObject.has(issueKey) && state.issuesByObject.get(issueKey).severity === 'error') continue;

                const hasDirectMembers = gt.memberAttrs.some(attr => group.attributes[attr] && group.attributes[attr].trim() !== '');

                let hasIndirectMembers = false;
                for (const obj of state.allObjects) {
                    if (obj.attributes[gt.memberOf]) {
                        const memberOfGroups = obj.attributes[gt.memberOf].split(',').map(s => s.trim().replace(/^[+!]+/, '').trim());
                        if (memberOfGroups.includes(groupName)) {
                            hasIndirectMembers = true;
                            break;
                        }
                    }
                }

                if (!hasDirectMembers && !hasIndirectMembers) {
                    state.issuesByObject.set(issueKey, { type: 'empty_group', severity: 'warning', object: group.name || group.display_name, object_type: group.object_type, file: group.source_file, message: `Empty ${gt.type} - no members` });
                }
            }
        }
    }

    function addOrphanIssuesToBadges() {
        const orphanCache = Explorer.buildOrphanCache();
        for (const obj of state.allObjects) {
            if (obj.attributes.register === '0') continue;
            if (orphanCache.has(obj.global_index)) {
                const issueKey = `${obj.object_type}:${obj.display_name}`;
                const existingIssue = state.issuesByObject.get(issueKey);
                if (existingIssue && existingIssue.severity === 'error') continue;
                state.issuesByObject.set(issueKey, { type: 'orphan', severity: 'info', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Orphan - not referenced by anything' });
            }
        }
    }

    // =============================================================================
    // Main Badge Issue Function
    // =============================================================================

    function addCleanupIssuesToBadges() {
        addDuplicateIssuesToBadges();
        const usageSets = buildUsageSets();
        addUnusedIssuesToBadges(usageSets);
        addEmptyGroupIssuesToBadges();
        addOrphanIssuesToBadges();
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
    Explorer.addDuplicateIssuesToBadges = addDuplicateIssuesToBadges;
    Explorer.buildUsageSets = buildUsageSets;
    Explorer.addUnusedIssuesToBadges = addUnusedIssuesToBadges;
    Explorer.addEmptyGroupIssuesToBadges = addEmptyGroupIssuesToBadges;
    Explorer.addOrphanIssuesToBadges = addOrphanIssuesToBadges;
    Explorer.addCleanupIssuesToBadges = addCleanupIssuesToBadges;
    Explorer.computeStagedIssues = computeStagedIssues;
    Explorer.updateStagedIssuesUI = updateStagedIssuesUI;

    // Expose stagedIssues as a getter so it always returns the current value
    Object.defineProperty(Explorer, 'stagedIssues', {
        get: function() { return stagedIssues; },
        enumerable: true
    });

})(window.Explorer);
