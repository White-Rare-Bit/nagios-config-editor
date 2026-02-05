/**
 * Explorer Analysis Module - Cleanup Analysis
 *
 * Pure analysis functions for finding cleanup opportunities:
 * - Unused templates, commands, contacts, contactgroups, timeperiods
 * - Duplicate objects
 * - Empty groups
 * - Orphan objects
 * - Long host lists
 *
 * Dependencies:
 * - window.Explorer (from main.js)
 * - Explorer.state (shared state)
 * - Explorer.buildOrphanCache (from orphan-detection.js)
 * - Explorer.getHostListInfo, Explorer.getEffectiveName (from app.js)
 * - Explorer.isObjectMarkedForDeletion (from state-management.js)
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // ==========================================================================
    // Shared Utilities (duplicated from analysis.js for module independence)
    // ==========================================================================

    // Strip +/! prefixes from Nagios additive/exclusion syntax
    const stripPrefix = s => s.trim().replace(/^[+!]+/, '').trim();

    // Severity order for sorting
    const SEVERITY_ORDER = { error: 0, warning: 1, info: 2 };

    // Filter out suggestions for objects marked for deletion
    function filterActiveSuggestions(suggestions) {
        return suggestions.filter(s => s.object && !Explorer.isObjectMarkedForDeletion(s.object.global_index));
    }

    // ==========================================================================
    // Cleanup Analysis Functions
    // ==========================================================================

    function findUnusedTemplates() {
        const suggestions = [];
        const templates = state.allObjects.filter(o => o.attributes.register === '0');
        const usedTemplates = new Set();

        for (const obj of state.allObjects) {
            if (obj.attributes.use) {
                obj.attributes.use.split(',').map(s => s.trim()).forEach(u => usedTemplates.add(u));
            }
        }

        for (const template of templates) {
            const templateName = template.attributes.name;
            if (templateName && !usedTemplates.has(templateName)) {
                suggestions.push({
                    type: 'unused_template',
                    severity: 'warning',
                    object: template,
                    title: `Unused template: ${templateName}`,
                    description: `This ${template.object_type} template is not referenced by any object's 'use' directive.`,
                    action: 'delete'
                });
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findDuplicateObjects() {
        const suggestions = [];
        const identityMap = new Map();

        for (const obj of state.allObjects) {
            if (obj.attributes.register === '0') continue;

            let identity = null;
            switch (obj.object_type) {
                case 'host': identity = obj.attributes.host_name; break;
                case 'service':
                    identity = `${obj.attributes.host_name || obj.attributes.hostgroup_name || '*'}::${obj.attributes.service_description}`;
                    break;
                case 'contact': identity = obj.attributes.contact_name; break;
                case 'hostgroup': identity = obj.attributes.hostgroup_name; break;
                case 'servicegroup': identity = obj.attributes.servicegroup_name; break;
                case 'contactgroup': identity = obj.attributes.contactgroup_name; break;
                case 'command': identity = obj.attributes.command_name; break;
                case 'timeperiod': identity = obj.attributes.timeperiod_name; break;
            }

            if (identity) {
                const key = `${obj.object_type}:${identity}`;
                if (!identityMap.has(key)) identityMap.set(key, []);
                identityMap.get(key).push(obj);
            }
        }

        for (const [key, objects] of identityMap) {
            if (objects.length > 1) {
                const colonIdx = key.indexOf(':');
                const type = key.substring(0, colonIdx);
                const identity = key.substring(colonIdx + 1);

                for (const obj of objects) {
                    suggestions.push({
                        type: 'duplicate',
                        severity: 'error',
                        object: obj,
                        title: `Duplicate ${type}: ${identity}`,
                        description: `Found ${objects.length} definitions with the same identity across different files.`,
                        action: 'review',
                        duplicateGroup: objects
                    });
                }
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findEmptyGroups() {
        const suggestions = [];
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

                const hasDirectMembers = gt.memberAttrs.some(attr =>
                    group.attributes[attr] && group.attributes[attr].trim() !== ''
                );

                let hasIndirectMembers = false;
                for (const obj of state.allObjects) {
                    if (obj.attributes[gt.memberOf]) {
                        const memberOfGroups = obj.attributes[gt.memberOf].split(',').map(stripPrefix);
                        if (memberOfGroups.includes(groupName)) {
                            hasIndirectMembers = true;
                            break;
                        }
                    }
                }

                if (!hasDirectMembers && !hasIndirectMembers) {
                    suggestions.push({
                        type: 'empty_group',
                        severity: 'warning',
                        object: group,
                        title: `Empty ${gt.type}: ${groupName}`,
                        description: `This group has no members defined and no objects reference it.`,
                        action: 'delete'
                    });
                }
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findOrphanObjects(existingSuggestions) {
        const suggestions = [];
        const orphanCache = Explorer.buildOrphanCache();

        for (const obj of state.allObjects) {
            if (obj.attributes.register === '0') continue;

            if (orphanCache.has(obj.global_index)) {
                // Remove from existingSuggestions if already present with lower priority
                const existingIdx = existingSuggestions.findIndex(s =>
                    s.object?.global_index === obj.global_index && s.severity !== 'error'
                );
                if (existingIdx >= 0) {
                    existingSuggestions.splice(existingIdx, 1);
                }

                const displayName = obj.display_name || obj.name || Explorer.getEffectiveName(obj);
                suggestions.push({
                    type: 'orphan',
                    severity: 'info',
                    object: obj,
                    title: `Orphan ${obj.object_type}: ${displayName}`,
                    description: `This object is not referenced by any other object in the configuration.`,
                    action: 'delete'
                });
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findLongHostLists() {
        const suggestions = [];
        for (const obj of state.allObjects) {
            if (obj.attributes.register === '0') continue;

            const hostListInfo = Explorer.getHostListInfo(obj);
            if (hostListInfo.shouldGroup) {
                const displayName = obj.display_name || obj.name || Explorer.getEffectiveName(obj);
                suggestions.push({
                    type: 'long_host_list',
                    severity: 'info',
                    object: obj,
                    title: `Consider hostgroup: ${displayName}`,
                    description: `This ${obj.object_type} has ${hostListInfo.count} hosts listed. Consider using a hostgroup instead.`,
                    action: 'review'
                });
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findUnusedCommands() {
        const suggestions = [];
        const commands = state.allObjects.filter(o => o.object_type === 'command');
        const usedCommands = new Set();
        const commandAttrs = ['check_command', 'event_handler', 'host_notification_commands',
                              'service_notification_commands', 'global_host_event_handler',
                              'global_service_event_handler'];

        for (const obj of state.allObjects) {
            for (const attr of commandAttrs) {
                if (obj.attributes[attr]) {
                    obj.attributes[attr].split(',').map(s => s.trim().split('!')[0]).forEach(cmd => usedCommands.add(cmd));
                }
            }
        }

        for (const cmd of commands) {
            const cmdName = cmd.attributes.command_name;
            if (cmdName && !usedCommands.has(cmdName)) {
                suggestions.push({
                    type: 'unused_command',
                    severity: 'warning',
                    object: cmd,
                    title: `Unused command: ${cmdName}`,
                    description: `This command is not referenced by any check_command, event_handler, or notification command.`,
                    action: 'delete'
                });
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findUnusedContacts() {
        const suggestions = [];
        const contacts = state.allObjects.filter(o => o.object_type === 'contact');
        const usedContacts = new Set();

        for (const obj of state.allObjects) {
            if (obj.attributes.contacts) {
                obj.attributes.contacts.split(',').map(stripPrefix).forEach(c => usedContacts.add(c));
            }
        }

        const contactgroups = state.allObjects.filter(o => o.object_type === 'contactgroup');
        for (const cg of contactgroups) {
            if (cg.attributes.members) {
                cg.attributes.members.split(',').map(stripPrefix).forEach(c => usedContacts.add(c));
            }
        }

        for (const contact of contacts) {
            if (contact.attributes.register === '0') continue;
            const contactName = contact.attributes.contact_name;
            if (contactName && !usedContacts.has(contactName)) {
                suggestions.push({
                    type: 'unused_contact',
                    severity: 'warning',
                    object: contact,
                    title: `Unused contact: ${contactName}`,
                    description: `This contact is not assigned to any host/service and not a member of any contactgroup.`,
                    action: 'delete'
                });
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findUnusedContactgroups() {
        const suggestions = [];
        const contactgroups = state.allObjects.filter(o => o.object_type === 'contactgroup');
        const contacts = state.allObjects.filter(o => o.object_type === 'contact');
        const usedContactgroups = new Set();

        for (const obj of state.allObjects) {
            if (obj.attributes.contact_groups) {
                obj.attributes.contact_groups.split(',').map(stripPrefix).forEach(cg => usedContactgroups.add(cg));
            }
        }

        for (const cg of contactgroups) {
            if (cg.attributes.contactgroup_members) {
                cg.attributes.contactgroup_members.split(',').map(stripPrefix).forEach(c => usedContactgroups.add(c));
            }
        }

        for (const contact of contacts) {
            if (contact.attributes.contactgroups) {
                contact.attributes.contactgroups.split(',').map(stripPrefix).forEach(cg => usedContactgroups.add(cg));
            }
        }

        for (const cg of contactgroups) {
            const cgName = cg.attributes.contactgroup_name;
            if (cgName && !usedContactgroups.has(cgName)) {
                suggestions.push({
                    type: 'unused_contactgroup',
                    severity: 'warning',
                    object: cg,
                    title: `Unused contactgroup: ${cgName}`,
                    description: `This contactgroup is not assigned to any host/service.`,
                    action: 'delete'
                });
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findUnusedTimeperiods() {
        const suggestions = [];
        const timeperiods = state.allObjects.filter(o => o.object_type === 'timeperiod');
        const usedTimeperiods = new Set();
        const timeperiodAttrs = ['check_period', 'notification_period', 'host_notification_period',
                                 'service_notification_period', 'dependency_period', 'exclude'];

        for (const obj of state.allObjects) {
            for (const attr of timeperiodAttrs) {
                if (obj.attributes[attr]) {
                    obj.attributes[attr].split(',').map(stripPrefix).forEach(tp => usedTimeperiods.add(tp));
                }
            }
        }

        for (const tp of timeperiods) {
            if (tp.attributes.register === '0') continue;
            const tpName = tp.attributes.timeperiod_name;
            if (tpName && !usedTimeperiods.has(tpName)) {
                suggestions.push({
                    type: 'unused_timeperiod',
                    severity: 'warning',
                    object: tp,
                    title: `Unused timeperiod: ${tpName}`,
                    description: `This timeperiod is not referenced by any check_period, notification_period, or dependency.`,
                    action: 'delete'
                });
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    function findHealthCheckWarnings() {
        const suggestions = [];
        const warningTypes = ['missing_timeperiod', 'missing_contact', 'missing_contactgroup', 'missing_hostgroup', 'missing_servicegroup'];

        for (const issue of state.allIssues) {
            if (warningTypes.includes(issue.type)) {
                const sourceObj = state.allObjects.find(o =>
                    o.object_type === issue.object_type &&
                    (o.display_name === issue.object || o.attributes.name === issue.object)
                );
                suggestions.push({
                    type: issue.type,
                    severity: 'warning',
                    object: sourceObj || null,
                    title: `${issue.object_type}: ${issue.object}`,
                    description: issue.message,
                    action: 'review',
                    issueData: issue
                });
            }
        }
        return filterActiveSuggestions(suggestions);
    }

    // ==========================================================================
    // Main Cleanup Analysis Aggregator
    // ==========================================================================

    /**
     * Analyze all cleanup issues and return sorted suggestions
     * @returns {Array} Array of cleanup suggestion objects
     */
    function analyzeCleanupIssues() {
        const suggestions = [];

        // Collect all suggestions from helper functions
        suggestions.push(...findUnusedTemplates());
        suggestions.push(...findDuplicateObjects());
        suggestions.push(...findEmptyGroups());
        suggestions.push(...findOrphanObjects(suggestions)); // Pass suggestions to allow orphan to remove duplicates
        suggestions.push(...findLongHostLists());
        suggestions.push(...findUnusedCommands());
        suggestions.push(...findUnusedContacts());
        suggestions.push(...findUnusedContactgroups());
        suggestions.push(...findUnusedTimeperiods());
        suggestions.push(...findHealthCheckWarnings());

        // Sort: errors first, then warnings, then info, then by type
        suggestions.sort((a, b) => {
            const severityDiff = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
            if (severityDiff !== 0) return severityDiff;
            return a.type.localeCompare(b.type);
        });

        return suggestions;
    }

    // ==========================================================================
    // Exports
    // ==========================================================================

    // Export to Explorer namespace
    Explorer.analyzeCleanupIssues = analyzeCleanupIssues;
    Explorer.findUnusedTemplates = findUnusedTemplates;
    Explorer.findDuplicateObjects = findDuplicateObjects;
    Explorer.findEmptyGroups = findEmptyGroups;
    Explorer.findOrphanObjects = findOrphanObjects;
    Explorer.findLongHostLists = findLongHostLists;
    Explorer.findUnusedCommands = findUnusedCommands;
    Explorer.findUnusedContacts = findUnusedContacts;
    Explorer.findUnusedContactgroups = findUnusedContactgroups;
    Explorer.findUnusedTimeperiods = findUnusedTimeperiods;
    Explorer.findHealthCheckWarnings = findHealthCheckWarnings;

})(window.Explorer);
