/**
 * Explorer Analysis Module - Cleanup Analysis
 *
 * Reads backend health-check data from state.allIssues for:
 * - Unused templates, commands, contacts, contactgroups, timeperiods
 * - Duplicate objects
 * - Empty groups
 *
 * Runs client-side analysis for:
 * - Orphan objects (needs Explorer.getEffectiveAttributes() for pending edits)
 * - Long host lists (UI-only suggestion with "Create Hostgroup" action)
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
    // Shared Utilities
    // ==========================================================================

    // Severity order for sorting
    const SEVERITY_ORDER = { error: 0, warning: 1, info: 2 };

    // Filter out suggestions for objects marked for deletion
    function filterActiveSuggestions(suggestions) {
        return suggestions.filter(s => s.object && !Explorer.isObjectMarkedForDeletion(s.object.global_index));
    }

    // ==========================================================================
    // Client-Side Analysis Functions (cannot move to backend)
    // ==========================================================================

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

    // ==========================================================================
    // Backend Issue Type Mapping
    // ==========================================================================

    const BACKEND_ISSUE_TYPES = {
        'unused_template':    { severity: 'warning', action: 'delete' },
        'unused_command':     { severity: 'warning', action: 'delete' },
        'unused_contact':     { severity: 'warning', action: 'delete' },
        'unused_contactgroup':{ severity: 'warning', action: 'delete' },
        'unused_timeperiod':  { severity: 'warning', action: 'delete' },
        'empty_group':        { severity: 'warning', action: 'delete' },
        'duplicate_object':   { severity: 'error',   action: 'review' }
    };

    // ==========================================================================
    // Main Cleanup Analysis Aggregator
    // ==========================================================================

    /**
     * Analyze all cleanup issues and return sorted suggestions.
     * Reads backend health-check issues from state.allIssues for most types,
     * and runs client-side analysis for orphans and long host lists.
     * @returns {Array} Array of cleanup suggestion objects
     */
    function analyzeCleanupIssues() {
        const suggestions = [];
        const seen = new Set();

        // Read backend issues from state.allIssues
        if (state.allIssues) {
            for (const issue of state.allIssues) {
                const config = BACKEND_ISSUE_TYPES[issue.type];
                if (!config) continue;

                // Find the actual frontend object
                const obj = state.allObjects.find(o =>
                    o.object_type === issue.object_type &&
                    (o.name === issue.object || o.display_name === issue.object)
                );

                // Skip if object not found or marked for deletion
                if (!obj) continue;
                if (Explorer.isObjectMarkedForDeletion(obj.global_index)) continue;

                // Deduplicate by type:global_index
                const dedupeKey = `${issue.type}:${obj.global_index}`;
                if (seen.has(dedupeKey)) continue;
                seen.add(dedupeKey);

                if (issue.type === 'duplicate_object') {
                    // For duplicates, find all matching objects to form the duplicateGroup
                    const duplicateGroup = state.allObjects.filter(o =>
                        o.object_type === issue.object_type &&
                        (o.name === issue.object || o.display_name === issue.object)
                    );

                    suggestions.push({
                        type: 'duplicate',
                        severity: 'error',
                        object: obj,
                        title: `Duplicate ${issue.object_type}: ${issue.object}`,
                        description: issue.message || `Found ${duplicateGroup.length} definitions with the same identity.`,
                        action: 'review',
                        duplicateGroup: duplicateGroup
                    });
                } else {
                    suggestions.push({
                        type: issue.type,
                        severity: config.severity,
                        object: obj,
                        title: `${issue.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}: ${issue.object}`,
                        description: issue.message || '',
                        action: config.action
                    });
                }
            }
        }

        // Client-side analyses
        suggestions.push(...findOrphanObjects(suggestions));
        suggestions.push(...findLongHostLists());

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

    Explorer.analyzeCleanupIssues = analyzeCleanupIssues;
    Explorer.findOrphanObjects = findOrphanObjects;
    Explorer.findLongHostLists = findLongHostLists;

})(window.Explorer);
