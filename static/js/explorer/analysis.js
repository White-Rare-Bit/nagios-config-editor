/** Explorer Analysis Module - Suggestions, cleanup, issues, and template/grouping analysis */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // A-01: Shared utilities extracted from duplicated patterns

    // Severity order for consistent sorting across suggestion types
    const SEVERITY_ORDER = { error: 0, warning: 1, info: 2 };

    // A-02: Filter out suggestions for objects marked for deletion (used 11+ times)
    function filterActiveSuggestions(suggestions) {
        return suggestions.filter(s => s.object && !Explorer.isObjectMarkedForDeletion(s.object.global_index));
    }

    // A-03: Build file dropdown options HTML (used 3+ times in dialogs)
    function buildFileOptionsHtml(defaultFile = '') {
        const configFiles = [...new Set(state.allObjects.map(o => o.source_file))].sort();
        return configFiles.map(f => {
            const fileName = f.split('/').pop();
            const selected = f === defaultFile ? 'selected' : '';
            return `<option value="${Explorer.escapeHtml(f)}" ${selected}>${Explorer.escapeHtml(fileName)}</option>`;
        }).join('');
    }

async function analyzeAll() {
    try {
        await loadAllSuggestions(true);
    } catch (error) {
        showToast('Analysis failed: ' + error.message, 'error');
    }
}

/**
 * Update the validation summary banner in the Suggestions tab
 */
function updateValidationSummary() {
    const summary = document.getElementById('validationSummary');
    const summaryText = document.getElementById('validationSummaryText');

    if (!summary) return;

    const errorCount = state.groupedErrors ? state.groupedErrors.length : 0;

    if (errorCount > 0) {
        summary.style.display = 'flex';
        summaryText.textContent = `${errorCount} syntax error${errorCount !== 1 ? 's' : ''} found`;
    } else {
        summary.style.display = 'none';
    }
}

/**
 * Update the create target path display in the Files tab
 */
function updateCreatePath(path) {
    const pathEl = document.getElementById('createTargetPath');
    if (pathEl) {
        pathEl.textContent = path ? `in ${path}` : '';
        pathEl.title = path || '';
    }
}

// Legacy function - keep for backwards compatibility
function switchSuggestionsSubtab(subtab) {
    Explorer.switchTabs('.suggestions-subtab', '.suggestions-section', subtab, 'subtab', 'Suggestions');
}

async function loadAllSuggestions(forceRefresh = false) {
    if (!forceRefresh && state.healthCheckData) {
        mapHealthCheckToState(state.healthCheckData);
    } else {
        try {
            const result = await ApiClient.get('/api/health-check');
            if (result.success) {
                state.healthCheckData = result.data;
                mapHealthCheckToState(result.data);
            }
        } catch (error) {
            showToast('Analysis failed: ' + error.message, 'error');
            return;
        }
    }
    await Explorer.loadGroupingSuggestions(forceRefresh);
    await Explorer.loadTemplateIssues(forceRefresh);
    renderUnifiedSuggestionsList();
}

/**
 * Distribute health-check issues from backend into existing state arrays.
 * Called after fetching /api/health-check or from cached data.
 */
function mapHealthCheckToState(data) {
    // 1. Reset state arrays
    state.allCleanupSuggestions = [];
    state.allNotificationSuggestions = [];
    state.allTemplateSuggestions = [];
    state.orphanIndices = new Set();

    // 2. Store all issues
    state.allIssues = data.issues || [];

    // 3. Rebuild issuesByObject map
    state.issuesByObject.clear();
    state.allIssues.forEach(issue => {
        const key = `${issue.object_type}:${issue.object}`;
        if (!state.issuesByObject.has(key) || issue.severity === 'error') {
            state.issuesByObject.set(key, issue);
        }
    });

    // 4. Call filterIssues to build groupedErrors
    Explorer.filterIssues();

    // 5. Build index lookup for O(1) object resolution
    const objectsByIndex = new Map();
    state.allObjects.forEach(o => objectsByIndex.set(o.global_index, o));

    // 6. Loop through issues and distribute to appropriate state arrays
    for (const issue of state.allIssues) {
        const obj = issue.global_index != null ? objectsByIndex.get(issue.global_index) : null;

        // Skip issues for objects staged for deletion
        if (obj && state.stagedObjectDeletions.has(obj.global_index)) continue;

        switch (issue.type) {
            case 'duplicate': {
                // Build duplicateGroup from related_objects if available
                let duplicateGroup = [];
                if (issue.related_objects) {
                    duplicateGroup = issue.related_objects
                        .map(ro => objectsByIndex.get(ro.global_index))
                        .filter(Boolean);
                } else if (obj) {
                    // Fallback: find all matching objects by name/type
                    duplicateGroup = state.allObjects.filter(o =>
                        o.object_type === issue.object_type &&
                        (o.name === issue.object || o.display_name === issue.object)
                    );
                }
                // Only add one entry per duplicate group (first occurrence)
                const existingDup = state.allCleanupSuggestions.find(s =>
                    s.type === 'duplicate' && s.object?.object_type === issue.object_type &&
                    (s.object?.name === issue.object || s.object?.display_name === issue.object)
                );
                if (!existingDup) {
                    state.allCleanupSuggestions.push({
                        type: 'duplicate',
                        severity: 'error',
                        object: obj || null,
                        objects: duplicateGroup,
                        title: `Duplicate ${issue.object_type}: ${issue.object}`,
                        description: issue.message || `Found ${duplicateGroup.length} definitions with the same identity.`,
                        action: 'review',
                        duplicateGroup: duplicateGroup
                    });
                }
                break;
            }

            case 'empty_group':
                if (obj) {
                    state.allCleanupSuggestions.push({
                        type: 'empty_group',
                        severity: 'warning',
                        object: obj,
                        title: `Empty ${issue.object_type}: ${issue.object}`,
                        description: issue.message || 'Group has no members and is not referenced',
                        action: 'delete'
                    });
                }
                break;

            case 'orphan':
                if (obj) {
                    state.orphanIndices.add(obj.global_index);
                    state.allCleanupSuggestions.push({
                        type: 'orphan',
                        severity: 'info',
                        object: obj,
                        title: `Orphan ${issue.object_type}: ${issue.object}`,
                        description: issue.message || 'This object is not referenced by any other object in the configuration.',
                        action: 'delete'
                    });
                }
                break;

            case 'unused_template':
            case 'unused_command':
            case 'unused_contact':
            case 'unused_contactgroup':
            case 'unused_timeperiod':
                if (obj) {
                    state.allCleanupSuggestions.push({
                        type: issue.type,
                        severity: 'warning',
                        object: obj,
                        title: `${issue.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}: ${issue.object}`,
                        description: issue.message || '',
                        action: 'delete'
                    });
                }
                break;

            case 'long_host_list':
                if (obj) {
                    state.allCleanupSuggestions.push({
                        type: 'long_host_list',
                        severity: 'info',
                        object: obj,
                        title: `Consider hostgroup: ${issue.object}`,
                        description: issue.message || `This service has many hosts listed individually.`,
                        action: 'review'
                    });
                }
                break;

            case 'missing_contacts':
                state.allNotificationSuggestions.push({
                    type: issue.object_type === 'host' ? 'host_no_contacts' : 'service_no_contacts',
                    severity: issue.severity || 'warning',
                    object: obj || null,
                    title: `No contacts: ${issue.object}`,
                    description: issue.message || 'No contacts or contact_groups defined',
                    fix: null
                });
                break;

            case 'template_opportunity':
                if (issue.suggestion) {
                    const s = issue.suggestion;
                    state.allTemplateSuggestions.push({
                        type: s.type,
                        suggestedName: s.suggested_name,
                        attributes: s.attributes,
                        objects: (s.object_indices || []).map(idx =>
                            state.allObjects.find(o => o.global_index === idx)
                        ).filter(Boolean),
                        count: s.count,
                        attrCount: s.attr_count
                    });
                }
                break;

            // Other types (missing_*, notification_gap for contacts, etc.) are handled
            // by filterIssues() which builds groupedErrors for the errors tab
        }
    }
}

function updateSuggestionsBadge() {
    // Use collectAllSuggestions() for accurate count that matches the rendered list
    const allSuggestions = collectAllSuggestions();
    const totalCount = allSuggestions.length;
    const errorCount = allSuggestions.filter(s => s.severity === 'error').length;

    const badge = document.getElementById('suggestionsBadge');
    if (badge) {
        badge.textContent = totalCount;
        // Use classList to toggle u-hidden class (which has !important)
        if (totalCount > 0) {
            badge.classList.remove('u-hidden');
        } else {
            badge.classList.add('u-hidden');
        }
    }

    // Update issues section badge (only actual errors)
    const issuesBadge = document.getElementById('issuesSectionBadge');
    if (issuesBadge) {
        issuesBadge.textContent = errorCount;
        if (errorCount > 0) {
            issuesBadge.classList.remove('u-hidden');
        } else {
            issuesBadge.classList.add('u-hidden');
        }
    }
}

// =========================================================================
// Unified Flat Suggestions List
// =========================================================================

// Current filter state
let currentSuggestionFilter = 'all';

/**
 * Collect all suggestions into a unified list with normalized format
 */
function collectAllSuggestions() {
    const suggestions = [];

    // 1. Issues/Errors from health check (grouped errors)
    if (state.groupedErrors) {
        for (const group of state.groupedErrors) {
            // Skip ungrouped errors that can't be resolved by creating something
            if (!group.objectType) continue;

            // Skip missing commands - these are typically external check plugins, not config objects
            if (group.objectType === 'command') continue;

            // Build detail showing actual referencing object names
            let detail = '';
            if (group.issues && group.issues.length > 0) {
                const names = group.issues.map(i => i.object || 'unknown');
                if (names.length <= 3) {
                    detail = `Referenced by: ${names.join(', ')}`;
                } else {
                    detail = `Referenced by: ${names.slice(0, 2).join(', ')} +${names.length - 2} more`;
                }
            }

            suggestions.push({
                id: `error-${group.objectType}-${group.missingName}`,
                severity: 'error',
                type: 'missing',
                label: `Missing ${group.objectType}`,
                name: group.missingName || 'unknown',
                detail,
                actionLabel: 'Create',
                actionType: 'create',
                data: group
            });
        }
    }

    // 1b. Health check warnings (e.g. hosts without services)
    // Skip types already handled by cleanup (section 3) or notification suggestions
    const cleanupTypes = new Set([
        'duplicate', 'empty_group', 'orphan', 'long_host_list',
        'unused_template', 'unused_command', 'unused_contact',
        'unused_contactgroup', 'unused_timeperiod',
        'missing_contacts', 'template_opportunity',
    ]);
    if (state.allIssues) {
        const warnings = state.allIssues.filter(i => i.severity === 'warning' && !cleanupTypes.has(i.type));
        for (const issue of warnings) {
            // Skip warnings for objects staged for deletion
            if (issue.global_index != null && state.stagedObjectDeletions.has(issue.global_index)) continue;
            suggestions.push({
                id: `health-warning-${issue.type}-${issue.object}`,
                severity: 'warning',
                type: 'health_check_warning',
                label: getHealthWarningLabel(issue.type),
                name: issue.object || 'unknown',
                detail: issue.message || '',
                actionLabel: 'View',
                actionType: 'navigate',
                data: { issue }
            });
        }
    }

    // 2. Template Issues (invalid refs, circular deps)
    if (state.templateIssues) {
        if (state.templateIssues.invalid_use) {
            for (const issue of state.templateIssues.invalid_use) {
                suggestions.push({
                    id: `template-invalid-${issue.object?.global_index}`,
                    severity: 'error',
                    type: 'template_invalid',
                    label: 'Invalid template',
                    name: issue.template_name || 'unknown',
                    detail: `${issue.object_type} "${issue.object_name}" uses undefined template`,
                    actionLabel: 'View',
                    actionType: 'navigate',
                    data: issue
                });
            }
        }
        if (state.templateIssues.circular_dependencies) {
            for (const issue of state.templateIssues.circular_dependencies) {
                suggestions.push({
                    id: `template-circular-${issue.chain?.join('-')}`,
                    severity: 'error',
                    type: 'template_circular',
                    label: 'Circular dependency',
                    name: issue.chain?.[0] || 'unknown',
                    detail: `Template chain: ${issue.chain?.join(' → ')}`,
                    actionLabel: 'View',
                    actionType: 'navigate',
                    data: issue
                });
            }
        }
    }

    // 3. Cleanup suggestions (duplicates, unused, orphans, etc.)
    if (state.allCleanupSuggestions) {
        for (let i = 0; i < state.allCleanupSuggestions.length; i++) {
            const s = state.allCleanupSuggestions[i];
            let actionLabel = 'Delete';
            let actionType = 'delete';

            if (s.type === 'duplicate') {
                actionLabel = 'Resolve';
                actionType = 'resolve_duplicate';
            } else if (s.type === 'long_host_list') {
                actionLabel = 'Group';
                actionType = 'create_hostgroup';
            }

            suggestions.push({
                id: `cleanup-${s.type}-${i}`,
                severity: s.severity || 'warning',
                type: s.type,
                label: getCleanupTypeLabel(s.type),
                name: s.object?.display_name || s.title?.split(':')[1]?.trim() || 'unknown',
                detail: s.description || '',
                actionLabel,
                actionType,
                data: s,
                cleanupIndex: i
            });
        }
    }

    // 4. Notification gaps
    if (state.allNotificationSuggestions) {
        for (let i = 0; i < state.allNotificationSuggestions.length; i++) {
            const s = state.allNotificationSuggestions[i];
            suggestions.push({
                id: `notification-${i}`,
                severity: 'warning',
                type: 'notification_gap',
                label: s.type === 'host_no_contacts' ? 'Host no contacts' : 'Service no contacts',
                name: s.object?.display_name || 'unknown',
                detail: s.description || 'No contacts or contact_groups defined',
                actionLabel: 'View',
                actionType: 'navigate',
                data: s,
                notificationIndex: i
            });
        }
    }

    // 5. Template consolidation opportunities
    if (state.allTemplateSuggestions) {
        for (let i = 0; i < state.allTemplateSuggestions.length; i++) {
            const s = state.allTemplateSuggestions[i];
            suggestions.push({
                id: `template-opportunity-${i}`,
                severity: 'info',
                type: 'template_opportunity',
                label: 'Template opportunity',
                name: s.suggestedName || 'common pattern',
                detail: `${s.count} ${s.type}s share ${s.attrCount || 0} attributes`,
                actionLabel: 'Create',
                actionType: 'create_template',
                data: s,
                templateIndex: i
            });
        }
    }

    // 6. Hostgroup suggestions
    if (state.allGroupingSuggestions) {
        for (let i = 0; i < state.allGroupingSuggestions.length; i++) {
            const s = state.allGroupingSuggestions[i];
            suggestions.push({
                id: `grouping-${i}`,
                severity: 'info',
                type: 'hostgroup_suggestion',
                label: 'Hostgroup pattern',
                name: s.name || 'unnamed group',
                detail: `${s.members?.length || s.count || 0} hosts match pattern`,
                actionLabel: 'Create',
                actionType: 'create_hostgroup_pattern',
                data: s,
                groupingIndex: i
            });
        }
    }

    // Sort by severity: error > warning > info (A-01: use shared constant)
    suggestions.sort((a, b) => {
        const aSev = SEVERITY_ORDER[a.severity] ?? 3;
        const bSev = SEVERITY_ORDER[b.severity] ?? 3;
        if (aSev !== bSev) return aSev - bSev;
        // Within same severity, sort by label then name
        if (a.label !== b.label) return a.label.localeCompare(b.label);
        return (a.name || '').localeCompare(b.name || '');
    });

    return suggestions;
}

function getHealthWarningLabel(issueType) {
    const labels = {
        'host_without_services': 'No services',
        'notification_gap': 'Notification gap',
        'duplicate_dependency': 'Duplicate dependency',
        'command_arg_mismatch': 'Argument mismatch',
        'template_conflict': 'Template conflict',
        'missing_contacts': 'Missing contacts',
        'missing_parent': 'Missing parent',
        'missing_timeperiod': 'Missing timeperiod',
        'missing_contact': 'Missing contact',
        'missing_contactgroup': 'Missing contactgroup',
        'missing_hostgroup': 'Missing hostgroup',
        'missing_servicegroup': 'Missing servicegroup',
    };
    return labels[issueType] || issueType.replace(/_/g, ' ');
}

function getCleanupTypeLabel(type) {
    const labels = {
        'duplicate': 'Duplicate',
        'empty_group': 'Empty group',
        'orphan': 'Orphan',
        'unused_template': 'Unused template',
        'unused_command': 'Unused command',
        'unused_contact': 'Unused contact',
        'unused_contactgroup': 'Unused contactgroup',
        'unused_timeperiod': 'Unused timeperiod',
        'long_host_list': 'Long host list',
        'health_check_warning': 'Health warning'
    };
    return labels[type] || type;
}

/**
 * Render the unified flat suggestions list
 */
function renderUnifiedSuggestionsList() {
    const container = document.getElementById('suggestionsList');
    const actionsFooter = document.getElementById('suggestionsActions');
    if (!container) return;

    const allSuggestions = collectAllSuggestions();

    // Update summary counts
    const errorCount = allSuggestions.filter(s => s.severity === 'error').length;
    const warningCount = allSuggestions.filter(s => s.severity === 'warning').length;
    const infoCount = allSuggestions.filter(s => s.severity === 'info').length;

    document.getElementById('summaryCountAll').textContent = allSuggestions.length;
    document.getElementById('summaryCountErrors').textContent = errorCount;
    document.getElementById('summaryCountWarnings').textContent = warningCount;
    document.getElementById('summaryCountInfo').textContent = infoCount;

    // Update the tab badge to match the summary count
    // This ensures badge stays in sync when renderUnifiedSuggestionsList is called
    // without going through loadAllSuggestions (e.g., after commit refresh)
    const badge = document.getElementById('suggestionsBadge');
    if (badge) {
        badge.textContent = allSuggestions.length;
        if (allSuggestions.length > 0) {
            badge.classList.remove('u-hidden');
        } else {
            badge.classList.add('u-hidden');
        }
    }

    // Filter based on current filter
    let filtered = allSuggestions;
    if (currentSuggestionFilter !== 'all') {
        filtered = allSuggestions.filter(s => s.severity === currentSuggestionFilter);
    }

    // Show/hide bulk actions
    const hasUnused = allSuggestions.some(s => s.type.startsWith('unused_'));
    const hasMissing = allSuggestions.some(s => s.type === 'missing');
    if (actionsFooter) {
        if (hasUnused || hasMissing) {
            actionsFooter.classList.remove('u-hidden');
            document.getElementById('bulkDeleteUnused').style.display = hasUnused ? '' : 'none';
            document.getElementById('bulkCreateMissing').style.display = hasMissing ? '' : 'none';
        } else {
            actionsFooter.classList.add('u-hidden');
        }
    }

    // Render empty state
    if (filtered.length === 0) {
        if (allSuggestions.length === 0) {
            container.innerHTML = `
                <div class="suggestions-empty">
                    <span class="suggestions-empty-icon"><i class="fa-solid fa-circle-check"></i></span>
                    <div class="suggestions-empty-title">All clear!</div>
                    <div class="suggestions-empty-desc">No issues or suggestions found</div>
                </div>
            `;
        } else {
            container.innerHTML = `
                <div class="suggestions-empty">
                    <span class="suggestions-empty-icon" style="color: var(--nbe-dark-text-muted);"><i class="fa-solid fa-filter"></i></span>
                    <div class="suggestions-empty-title">No matches</div>
                    <div class="suggestions-empty-desc">No items match the current filter</div>
                </div>
            `;
        }
        return;
    }

    // Group by severity for dividers
    let html = '';
    let currentSeverity = null;

    for (const s of filtered) {
        // Add divider when severity changes (only if showing all)
        if (currentSuggestionFilter === 'all' && s.severity !== currentSeverity) {
            currentSeverity = s.severity;
            const dividerLabel = s.severity === 'error' ? 'Errors' : s.severity === 'warning' ? 'Warnings' : 'Suggestions';
            html += `<div class="suggestion-divider">${dividerLabel}</div>`;
        }

        html += renderSuggestionRow(s);
    }

    container.innerHTML = html;
}

function renderSuggestionRow(s) {
    const actionClass = s.actionType === 'delete' ? 'action-delete' :
                        s.actionType.startsWith('create') ? 'action-create' : '';

    return `
        <div class="suggestion-row" data-id="${s.id}" onclick="Explorer.handleSuggestionClick('${s.id}', event)">
            <span class="suggestion-severity ${s.severity}"></span>
            <span class="suggestion-text">
                <span class="suggestion-type">${Explorer.escapeHtml(s.label)}:</span>
                <span class="suggestion-name">${Explorer.escapeHtml(s.name)}</span>
            </span>
            <button class="suggestion-action ${actionClass}" onclick="Explorer.handleSuggestionAction('${s.id}', event)">
                ${Explorer.escapeHtml(s.actionLabel)}
            </button>
            ${s.detail ? `<div class="suggestion-detail">${Explorer.escapeHtml(s.detail)}</div>` : ''}
        </div>
    `;
}

/**
 * Handle clicking a suggestion row (navigate/expand)
 */
function handleSuggestionClick(id, event) {
    // Don't trigger if clicking the action button
    if (event.target.closest('.suggestion-action')) return;

    const s = findSuggestionById(id);
    if (!s) return;

    // Navigate to the object if possible
    if (s.data?.object) {
        Explorer.navigateToObjectByIndex(s.data.object.global_index);
    } else if (s.data?.objects && s.data.objects.length > 0) {
        // For duplicates, show the first one
        Explorer.navigateToObjectByIndex(s.data.objects[0].global_index);
    } else if (s.data?.issue) {
        // For health check warnings, navigate to the referenced object
        Explorer.navigateToIssue(s.data.issue.object, s.data.issue.object_type);
    } else if (s.data?.issues && s.data.issues.length > 0) {
        // For missing objects, navigate to the first referencing object
        const firstIssue = s.data.issues[0];
        if (firstIssue.object && firstIssue.object_type) {
            Explorer.navigateToIssue(firstIssue.object, firstIssue.object_type);
        }
    }
}

/**
 * Handle clicking a suggestion's action button
 */
function handleSuggestionAction(id, event) {
    event.stopPropagation();

    const s = findSuggestionById(id);
    if (!s) return;

    switch (s.actionType) {
        case 'create':
            // Create missing object from grouped error - find the index in groupedErrors
            if (s.data && state.groupedErrors) {
                const idx = state.groupedErrors.indexOf(s.data);
                if (idx !== -1) {
                    Explorer.resolveGroupedError(idx);
                }
            }
            break;

        case 'delete':
            // Delete unused/orphan object
            if (s.data?.object) {
                stageCleanupDeletion(s.cleanupIndex);
            }
            break;

        case 'resolve_duplicate':
            // Show duplicate resolution dialog
            if (s.cleanupIndex !== undefined) {
                fixDuplicate(s.cleanupIndex);
            }
            break;

        case 'create_hostgroup':
            // Create hostgroup from long host list
            if (s.cleanupIndex !== undefined) {
                fixLongHostList(s.cleanupIndex);
            }
            break;

        case 'create_template':
            // Create template from opportunity
            if (s.templateIndex !== undefined) {
                Explorer.showCreateTemplateDialog(s.templateIndex);
            }
            break;

        case 'create_hostgroup_pattern':
            // Create hostgroup from pattern
            if (s.groupingIndex !== undefined) {
                Explorer.showCreateGroupDialog(s.groupingIndex);
            }
            break;

        case 'navigate':
            // Just navigate to the object
            handleSuggestionClick(id, { target: document.body, stopPropagation: () => {} });
            break;
    }
}

/**
 * Find a suggestion by its ID
 */
function findSuggestionById(id) {
    const allSuggestions = collectAllSuggestions();
    return allSuggestions.find(s => s.id === id);
}

/**
 * Filter suggestions by severity
 */
function filterSuggestions(event) {
    const filter = event.target.closest('[data-filter]')?.dataset.filter;
    if (!filter) return;

    currentSuggestionFilter = filter;

    // Update active state on buttons
    document.querySelectorAll('.summary-filter').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });

    renderUnifiedSuggestionsList();
}

/**
 * Stage deletion for a cleanup item
 */
function stageCleanupDeletion(idx) {
    const s = state.allCleanupSuggestions[idx];
    if (!s || !s.object) return;

    const obj = s.object;

    // Stage the deletion
    if (!state.stagedObjectDeletions.has(obj.global_index)) {
        state.stagedObjectDeletions.add(obj.global_index);
        state.pendingEdits.delete(obj.global_index);

        // Remove from cleanup suggestions
        state.allCleanupSuggestions.splice(idx, 1);

        Explorer.saveStagedChanges();
        Explorer.refreshAfterObjectChange();
        renderUnifiedSuggestionsList();

        showToast(`Staged "${obj.display_name}" for deletion`, 'success');
    }
}

/**
 * Bulk delete all unused items
 */
function bulkDeleteUnused() {
    const unusedItems = state.allCleanupSuggestions.filter(s =>
        s.type.startsWith('unused_') || s.type === 'orphan' || s.type === 'empty_group'
    );

    if (unusedItems.length === 0) {
        showToast('No unused items to delete', 'info');
        return;
    }

    showConfirmDialog({
        title: 'Delete All Unused',
        message: `This will stage ${unusedItems.length} unused item(s) for deletion. Continue?`,
        confirmText: 'Delete All',
        confirmClass: 'btn-danger',
        onConfirm: () => {
            let count = 0;
            // Delete in reverse order to maintain indices
            for (let i = state.allCleanupSuggestions.length - 1; i >= 0; i--) {
                const s = state.allCleanupSuggestions[i];
                if ((s.type.startsWith('unused_') || s.type === 'orphan' || s.type === 'empty_group') && s.object) {
                    if (!state.stagedObjectDeletions.has(s.object.global_index)) {
                        state.stagedObjectDeletions.add(s.object.global_index);
                        state.pendingEdits.delete(s.object.global_index);
                        state.allCleanupSuggestions.splice(i, 1);
                        count++;
                    }
                }
            }

            Explorer.saveStagedChanges();
            Explorer.refreshAfterObjectChange();
            renderUnifiedSuggestionsList();

            showToast(`Staged ${count} item(s) for deletion`, 'success');
        }
    });
}

/**
 * Bulk create all missing objects - shows summary of missing items by type
 */
function bulkCreateMissing() {
    if (!state.groupedErrors || state.groupedErrors.length === 0) {
        showToast('No missing objects to create', 'info');
        return;
    }

    // Group errors by type
    const byType = {};
    for (const group of state.groupedErrors) {
        const type = group.objectType || 'unknown';
        if (!byType[type]) byType[type] = [];
        byType[type].push(group);
    }

    // Build summary HTML
    let html = '<p class="u-mb-md dialog-info-text">Create missing objects by type:</p>';
    html += '<div class="batch-create-list">';

    for (const [type, groups] of Object.entries(byType)) {
        const count = groups.length;
        html += `
            <div class="batch-create-type-row">
                <span class="batch-create-type-label">${count} missing ${type}${count !== 1 ? 's' : ''}</span>
                <button class="suggestion-action action-create" onclick="Explorer.createAllMissing('${type}'); Explorer.closeDialog();">
                    Create All
                </button>
            </div>
        `;
    }
    html += '</div>';

    Explorer.showDialog('Create Missing Objects', html, null);
}

// =========================================================================
// Template & Grouping Suggestions - moved to analysis-suggestions.js
// =========================================================================

// ============================================================================
// Cleanup Suggestions (Unused Templates, Duplicates, Empty Groups)
// ============================================================================

async function loadCleanupSuggestions(forceRefresh = false) {
    const container = document.getElementById('cleanupContent');
    const badge = document.getElementById('cleanupSectionBadge');

    if (!forceRefresh && state.allCleanupSuggestions.length > 0) {
        renderCleanupSuggestions();
        return;
    }

    if (container) {
        container.innerHTML = '<div class="tab-placeholder">Analyzing configuration...</div>';
    }

    // Ensure health-check data is loaded (force re-fetch if forceRefresh)
    if (!state.healthCheckData || forceRefresh) {
        try {
            const result = await ApiClient.get('/api/health-check');
            if (result.success) {
                state.healthCheckData = result.data;
                mapHealthCheckToState(result.data);
            }
        } catch (error) {
            if (container) {
                container.innerHTML = '<div class="tab-placeholder">Error loading cleanup data.</div>';
            }
            return;
        }
    }

    if (state.allCleanupSuggestions.length === 0) {
        if (container) {
            container.innerHTML = '<div class="empty-state empty-state-success"><span class="empty-icon"><i class="fa-solid fa-circle-check"></i></span><div class="empty-title">No cleanup needed</div><div class="empty-desc">Your configuration is clean!</div></div>';
        }
        if (badge) badge.style.display = 'none';
        return;
    }

    if (badge) {
        badge.textContent = state.allCleanupSuggestions.length;
        badge.style.display = 'inline-flex';
    }

    renderCleanupSuggestions();
}

// =============================================================================
// Cleanup Analysis Rendering
// =============================================================================

function renderCleanupSuggestions() {
    const container = document.getElementById('cleanupContent');
    if (!container) return;

    if (state.allCleanupSuggestions.length === 0) {
        container.innerHTML = '<div class="tab-placeholder">No cleanup opportunities found.</div>';
        return;
    }

    // Group suggestions by type
    const groups = {};
    const groupOrder = ['duplicate', 'empty_group', 'orphan', 'long_host_list',
                        'unused_template', 'unused_command', 'unused_contact', 'unused_contactgroup',
                        'unused_timeperiod', 'missing_hostgroup', 'missing_servicegroup',
                        'missing_contact', 'missing_contactgroup', 'missing_timeperiod'];

    const groupConfig = {
        'duplicate': { icon: '<i class="fa-solid fa-copy"></i>', label: 'Duplicate Definitions', severity: 'error', bulkAction: null },
        'empty_group': { icon: '<i class="fa-solid fa-folder-open"></i>', label: 'Empty Groups', severity: 'warning', bulkAction: 'deleteAll' },
        'orphan': { icon: '<i class="fa-solid fa-plug"></i>', label: 'Orphans', severity: 'info', bulkAction: null },
        'long_host_list': { icon: '<i class="fa-solid fa-list"></i>', label: 'Long Host Lists', severity: 'info', bulkAction: null },
        'unused_template': { icon: '<i class="fa-solid fa-clipboard"></i>', label: 'Unused Templates', severity: 'info', bulkAction: 'deleteAll' },
        'unused_command': { icon: '<i class="fa-solid fa-bolt"></i>', label: 'Unused Commands', severity: 'info', bulkAction: 'deleteAll' },
        'unused_contact': { icon: '<i class="fa-solid fa-user"></i>', label: 'Unused Contacts', severity: 'info', bulkAction: 'deleteAll' },
        'unused_contactgroup': { icon: '<i class="fa-solid fa-users"></i>', label: 'Unused Contact Groups', severity: 'info', bulkAction: 'deleteAll' },
        'unused_timeperiod': { icon: '<i class="fa-solid fa-clock"></i>', label: 'Unused Time Periods', severity: 'info', bulkAction: 'deleteAll' },
        'missing_hostgroup': { icon: '<i class="fa-solid fa-desktop"></i>', label: 'Missing Hostgroups', severity: 'warning', bulkAction: null },
        'missing_servicegroup': { icon: '<i class="fa-solid fa-gear"></i>', label: 'Missing Servicegroups', severity: 'warning', bulkAction: null },
        'missing_contact': { icon: '<i class="fa-solid fa-user"></i>', label: 'Missing Contacts', severity: 'warning', bulkAction: null },
        'missing_contactgroup': { icon: '<i class="fa-solid fa-users"></i>', label: 'Missing Contact Groups', severity: 'warning', bulkAction: null },
        'missing_timeperiod': { icon: '<i class="fa-solid fa-clock"></i>', label: 'Missing Time Periods', severity: 'warning', bulkAction: null }
    };

    // Group suggestions
    for (let i = 0; i < state.allCleanupSuggestions.length; i++) {
        const s = state.allCleanupSuggestions[i];
        if (!groups[s.type]) groups[s.type] = [];
        groups[s.type].push({ suggestion: s, index: i });
    }

    let html = '';

    // Render each group in order
    for (const groupType of groupOrder) {
        if (!groups[groupType] || groups[groupType].length === 0) continue;

        const config = groupConfig[groupType] || { icon: '❓', label: groupType, severity: 'info', bulkAction: null };
        const items = groups[groupType];
        const severityClass = `section-${config.severity}`;

        // Build bulk action button if applicable
        let bulkActionBtn = '';
        if (config.bulkAction === 'deleteAll' && items.length > 1) {
            bulkActionBtn = `<button class="cleanup-section-btn nbe-btn nbe-btn--danger nbe-btn--sm" onclick="event.stopPropagation(); Explorer.bulkDeleteCleanupGroup('${groupType}')">Delete All</button>`;
        }

        html += `
            <div class="cleanup-section collapsed ${severityClass}" data-group="${groupType}">
                <div class="cleanup-section-header" onclick="Explorer.toggleCleanupSection(this)">
                    <div class="cleanup-section-title">
                        <span class="cleanup-section-icon">${config.icon}</span>
                        <span>${config.label}</span>
                        <span class="cleanup-section-count">${items.length}</span>
                    </div>
                    <div class="cleanup-section-actions">
                        ${bulkActionBtn}
                        <span class="cleanup-section-toggle"><i class="fa-solid fa-chevron-right"></i></span>
                    </div>
                </div>
                <div class="cleanup-section-items">
        `;

        // Render items within this group
        for (const { suggestion: s, index: i } of items) {
            const severityClass = s.severity === 'error' ? 'cleanup-error' :
                                  s.severity === 'warning' ? 'cleanup-warning' : 'cleanup-info';

            // Simplify description for grouped items
            let displayTitle = s.title;
            let displayDesc = s.description;

            // For empty groups, show just the name since the section header explains the issue
            if (s.type === 'empty_group') {
                // Extract just the group name from title like "Empty hostgroup: windows-hosts"
                displayDesc = s.object?.source_file ? `In: ${s.object.source_file.split('/').pop()}` : '';
            }

            // Determine which buttons to show
            let buttons = '';
            if (s.type === 'duplicate') {
                buttons = `<button class="cleanup-action-btn cleanup-fix-btn" onclick="event.stopPropagation(); Explorer.fixDuplicate(${i})">Resolve</button>`;
            } else if (s.type === 'long_host_list') {
                buttons = `<button class="cleanup-action-btn cleanup-fix-btn" onclick="event.stopPropagation(); Explorer.fixLongHostList(${i})">Create Hostgroup</button>`;
            } else if (s.issueData) {
                const resolveInfo = Explorer.getIssueResolveInfo(s.issueData);
                if (resolveInfo) {
                    buttons = `<button class="cleanup-action-btn cleanup-fix-btn" onclick="event.stopPropagation(); Explorer.resolveCleanupIssue(${i})">Create ${resolveInfo.objectType}</button>`;
                }
            } else if (s.action === 'delete') {
                buttons = `<button class="cleanup-action-btn" onclick="event.stopPropagation(); Explorer.stageCleanupDelete(${i})">Delete</button>`;
            }

            html += `
                <div class="cleanup-suggestion ${severityClass}" data-index="${i}" onclick="Explorer.showCleanupDetail(${i})">
                    <div class="cleanup-info">
                        <div class="cleanup-title">${Explorer.escapeHtml(displayTitle)}</div>
                        ${displayDesc ? `<div class="cleanup-desc">${Explorer.escapeHtml(displayDesc)}</div>` : ''}
                    </div>
                    ${buttons}
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    container.innerHTML = html;
}

function toggleCleanupSection(header) {
    const section = header.closest('.cleanup-section');
    section.classList.toggle('collapsed');
}

function bulkDeleteCleanupGroup(groupType) {
    // Find all suggestions of this type
    const indicesToDelete = [];
    for (let i = state.allCleanupSuggestions.length - 1; i >= 0; i--) {
        const s = state.allCleanupSuggestions[i];
        if (s.type === groupType && s.action === 'delete' && s.object) {
            indicesToDelete.push(i);
        }
    }

    if (indicesToDelete.length === 0) {
        showToast('No items to delete', 'warning');
        return;
    }

    // Get label for display
    const groupLabels = {
        'empty_group': 'empty groups',
        'unused_template': 'unused templates',
        'unused_command': 'unused commands',
        'unused_contact': 'unused contacts',
        'unused_contactgroup': 'unused contact groups',
        'unused_timeperiod': 'unused time periods'
    };
    const label = groupLabels[groupType] || groupType;

    // Build list of items to show in dialog
    const itemsList = indicesToDelete.slice(0, 10).map(idx => {
        const s = state.allCleanupSuggestions[idx];
        const name = s.object?.display_name || s.title;
        return `<li>${Explorer.escapeHtml(name)}</li>`;
    }).join('');
    const moreCount = indicesToDelete.length > 10 ? `<li><em>... and ${indicesToDelete.length - 10} more</em></li>` : '';

    Explorer.showDialog(`Delete All ${label.charAt(0).toUpperCase() + label.slice(1)}`, `
        <p class="u-mb-md">Stage deletion of <strong>${indicesToDelete.length} ${label}</strong>?</p>
        <ul class="dialog-scrollable-list dialog-scrollable-list--medium u-pl-lg">
            ${itemsList}
            ${moreCount}
        </ul>
        <p class="u-mt-md dialog-info-text">
            Changes will be staged and can be reviewed before committing.
        </p>
    `, () => {
        // Stage deletions
        let deletedCount = 0;
        for (const idx of indicesToDelete) {
            const s = state.allCleanupSuggestions[idx];
            if (s.object) {
                state.stagedObjectDeletions.add(s.object.global_index);
                deletedCount++;
            }
        }

        // Remove from suggestions (in reverse order)
        for (const idx of indicesToDelete) {
            state.allCleanupSuggestions.splice(idx, 1);
        }

        // Update UI
        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        Explorer.buildTree();
        Explorer.closeDialog();
        renderCleanupSuggestions();
        updateSuggestionsBadge();
        updateCleanupBadge();
        Explorer.renderTargetPane();

        showToast(`Staged deletion of ${deletedCount} ${label}`, 'success');
    });
}

function showCleanupDetail(idx) {
    const s = state.allCleanupSuggestions[idx];

    if (s.type === 'duplicate') {
        // Show all duplicate objects
        const objectList = s.objects.map(o => {
            const file = o.source_file.split('/').pop();
            return `<div class="cleanup-detail-item" onclick="Explorer.navigateToObjectByIndex(${o.global_index}); Explorer.closeDialog();">
                <span class="cleanup-detail-file">${Explorer.escapeHtml(file)}</span>
                <span class="cleanup-detail-line">Line ${o.line_number || '?'}</span>
            </div>`;
        }).join('');

        Explorer.showDialog('Duplicate Objects', `
            <p class="u-mb-md dialog-info-text">${Explorer.escapeHtml(s.description)}</p>
            <p class="u-mb-sm"><strong>Click to navigate to each definition:</strong></p>
            <div class="cleanup-detail-list">${objectList}</div>
        `, null);
    } else if (s.object) {
        // Single object - navigate to it
        Explorer.navigateToObjectByIndex(s.object.global_index);
    } else if (s.issueData) {
        // Warning without a direct object - show info dialog
        Explorer.showDialog('Issue Details', `
            <p class="u-mb-md"><strong>${Explorer.escapeHtml(s.title)}</strong></p>
            <p class="dialog-info-text">${Explorer.escapeHtml(s.description)}</p>
        `, null);
    }
}

function stageCleanupDelete(idx) {
    const s = state.allCleanupSuggestions[idx];
    const obj = s.object;

    if (!obj) return;

    // Stage the deletion
    state.stagedObjectDeletions.add(obj.global_index);
    Explorer.saveStagedChanges();
    Explorer.updateCommitUI();
    Explorer.buildTree();
    Explorer.renderTargetPane();

    showToast(`Staged deletion of ${obj.object_type} "${obj.display_name || obj.name}"`, 'success');

    // Remove from suggestions
    state.allCleanupSuggestions.splice(idx, 1);
    renderCleanupSuggestions();
    updateSuggestionsBadge();

    // Update cleanup section badge
    const badge = document.getElementById('cleanupSectionBadge');
    if (badge) {
        if (state.allCleanupSuggestions.length > 0) {
            badge.textContent = state.allCleanupSuggestions.length;
        } else {
            badge.style.display = 'none';
        }
    }
}

function resolveCleanupIssue(idx) {
    const s = state.allCleanupSuggestions[idx];
    if (!s.issueData) return;

    const issue = s.issueData;
    const resolveInfo = Explorer.getIssueResolveInfo(issue);
    if (!resolveInfo) return;

    // Find the source file of the object that has the issue
    const sourceObj = s.object;
    const targetFile = sourceObj ? sourceObj.source_file : null;

    // Open create object dialog with pre-filled values
    Explorer.openCreateObjectForIssue(resolveInfo.objectType, resolveInfo.missingName, targetFile, issue);
}

function fixDuplicate(idx) {
    const s = state.allCleanupSuggestions[idx];
    if (!s || s.type !== 'duplicate' || !s.duplicateGroup) return;

    // Find differences between duplicates
    const differences = findDuplicateDifferences(s.duplicateGroup);
    const hasDifferences = differences.length > 0;

    // Build list of duplicates with "Keep" buttons
    const objectList = s.duplicateGroup.map((o, i) => {
        const file = o.source_file.split('/').pop();

        // Show differing attributes for this object
        let diffHtml = '';
        if (hasDifferences) {
            const diffAttrs = differences.map(attr => {
                const val = o.attributes[attr];
                return `<div class="diff-row">
                    <span class="diff-key">${Explorer.escapeHtml(attr)}:</span>
                    <span class="diff-val">${val !== undefined ? Explorer.escapeHtml(String(val)) : '<em>not set</em>'}</span>
                </div>`;
            }).join('');
            diffHtml = `<div class="diff-values">${diffAttrs}</div>`;
        }

        return `
            <div class="cleanup-detail-item cleanup-detail-item--vertical">
                <div class="cleanup-detail-header">
                    <div class="ref-item-clickable" onclick="Explorer.navigateToObjectByIndex(${o.global_index}); Explorer.closeDialog();">
                        <span class="cleanup-detail-file">${Explorer.escapeHtml(file)}</span>
                        <span class="cleanup-detail-line">Line ${o.line_number || '?'}</span>
                    </div>
                    <button class="nbe-btn nbe-btn--primary nbe-btn--sm" onclick="Explorer.keepDuplicateAndDeleteOthers(${idx}, ${i})">Keep This</button>
                </div>
                ${diffHtml}
            </div>`;
    }).join('');

    const diffMessage = hasDifferences
        ? `<div class="dialog-alert dialog-alert--warning">
             <strong>Differences found!</strong> These duplicates have different values for:
             <code>${differences.join('</code>, <code>')}</code>
           </div>`
        : `<div class="dialog-alert dialog-alert--info">
             These duplicates are identical. You can safely delete any of them.
           </div>`;

    Explorer.showDialog('Resolve Duplicate', `
        ${diffMessage}
        <p class="u-mb-sm dialog-info-text">Choose which definition to keep. The others will be staged for deletion.</p>
        <div class="cleanup-detail-list dialog-scrollable-list">${objectList}</div>
    `, null);
}

function findDuplicateDifferences(objects) {
    if (objects.length < 2) return [];

    // Collect all attribute keys across all objects
    const allKeys = new Set();
    objects.forEach(o => {
        Object.keys(o.attributes).forEach(k => allKeys.add(k));
    });

    // Find attributes that differ between objects
    const differences = [];
    for (const key of allKeys) {
        const values = objects.map(o => o.attributes[key]);
        const firstVal = values[0];
        const allSame = values.every(v => v === firstVal);
        if (!allSame) {
            differences.push(key);
        }
    }

    return differences.sort();
}

function keepDuplicateAndDeleteOthers(suggestionIdx, keepIdx) {
    const s = state.allCleanupSuggestions[suggestionIdx];
    if (!s || !s.duplicateGroup) return;

    // Stage deletion of all except the one to keep
    let deletedCount = 0;
    s.duplicateGroup.forEach((obj, i) => {
        if (i !== keepIdx) {
            state.stagedObjectDeletions.add(obj.global_index);
            deletedCount++;
        }
    });

    Explorer.saveStagedChanges();
    Explorer.updateCommitUI();
    Explorer.buildTree();
    Explorer.renderTargetPane();
    Explorer.closeDialog();

    showToast(`Staged deletion of ${deletedCount} duplicate(s)`, 'success');

    // Remove from suggestions and refresh
    state.allCleanupSuggestions.splice(suggestionIdx, 1);
    renderCleanupSuggestions();
    updateSuggestionsBadge();
    updateCleanupBadge();
}

// Track pending hostgroup creation that needs to update a service

function fixLongHostList(idx) {
    const s = state.allCleanupSuggestions[idx];
    if (!s || s.type !== 'long_host_list' || !s.object) return;

    const obj = s.object;
    const hostList = obj.attributes.host_name || '';
    const hosts = hostList.split(',').map(h => h.trim()).filter(h => h && h !== '*');
    const serviceDesc = obj.attributes.service_description || 'service';

    Explorer.showDialog('Create Hostgroup', `
        <div class="dialog-alert dialog-alert--info">
            <strong>This will:</strong>
            <ol class="u-mt-sm u-pl-lg">
                <li>Create a new hostgroup definition with ${hosts.length} hosts</li>
                <li>Update the service "${Explorer.escapeHtml(serviceDesc)}" to use the new hostgroup</li>
            </ol>
        </div>
        <div class="u-mb-md">
            <label class="form-label">Hosts to be grouped:</label>
            <div class="dialog-scrollable-list dialog-scrollable-list--short">
                ${hosts.map(h => Explorer.escapeHtml(h)).join('<br>')}
            </div>
        </div>
        <p class="dialog-info-text">Click Continue to open the hostgroup editor where you can set the name and other attributes.</p>
    `, () => {
        Explorer.closeDialog();
        openHostgroupEditorForService(idx, hosts);
    }, 'Continue');
}

function openHostgroupEditorForService(suggestionIdx, hosts) {
    const s = state.allCleanupSuggestions[suggestionIdx];
    const obj = s.object;
    const serviceDesc = obj.attributes.service_description || 'service';
    const suggestedName = serviceDesc.toLowerCase().replace(/[^a-z0-9]+/g, '-') + '-hosts';

    // Find a suitable file for the new hostgroup (same directory as the service)
    const serviceFile = obj.source_file;
    const dir = serviceFile.substring(0, serviceFile.lastIndexOf('/'));
    const hostgroupFile = dir + '/hostgroups.cfg';

    // Check if the hostgroup file exists, if not mark it as new
    const existingFiles = new Set(state.allObjects.map(o => o.source_file));
    if (!existingFiles.has(hostgroupFile) && !state.newFiles.has(hostgroupFile)) {
        state.newFiles.add(hostgroupFile);
    }

    // Store the link so we can update the service when the hostgroup is saved
    state.pendingHostgroupServiceLink = {
        serviceGlobalIndex: obj.global_index,
        suggestionIdx: suggestionIdx
    };

    // Create the new object and open it in the editor
    const newHostgroup = {
        object_type: 'hostgroup',
        attributes: {
            hostgroup_name: suggestedName,
            alias: suggestedName.replace(/-/g, ' '),
            members: hosts.join(',')
        },
        source_file: hostgroupFile,
        display_name: suggestedName,
        is_new: true
    };

    // Open in editor
    openNewObjectInEditor(newHostgroup, hostgroupFile);
}

function openNewObjectInEditor(newObj, targetFile) {
    // Set up the editor state for a new object
    state.editedObject = newObj;
    state.originalAttributes = {};
    state.isNewObject = true;
    state.currentCenterIsOrphan = false;
    state.currentCenterHostListInfo = { shouldGroup: false, count: 0 };
    state.currentCenterIssue = null;

    // Clear any previous staged creation for this
    state.newObjectStagedIndex = null;

    // Stage the new object immediately so it appears in the tree
    Explorer.stageNewObjectChanges();

    // Show center pane
    const emptyState = document.getElementById('centerEmptyState');
    const content = document.getElementById('centerContent');
    emptyState.classList.add('u-hidden');
    emptyState.style.display = 'none';
    content.classList.remove('u-hidden');
    content.style.display = 'block';
    document.getElementById('centerCloseBtn').style.display = 'block';

    // Render the object in the center pane
    Explorer.showCenterPaneNewObject(newObj, targetFile);

    // Show message about the linked service update
    if (state.pendingHostgroupServiceLink) {
        const serviceObj = state.allObjects.find(o => o.global_index === state.pendingHostgroupServiceLink.serviceGlobalIndex);
        if (serviceObj) {
            showToast(`Set the hostgroup name, then save. The service "${serviceObj.display_name}" will be updated automatically.`, 'info');
        }
    }
}

function handleHostgroupServiceLink() {
    // Called when a new hostgroup is saved that has a pending service link
    if (!state.pendingHostgroupServiceLink || !state.isNewObject || state.editedObject?.object_type !== 'hostgroup') {
        return;
    }

    const hostgroupName = state.editedObject.attributes.hostgroup_name;
    if (!hostgroupName) return;

    const serviceGlobalIndex = state.pendingHostgroupServiceLink.serviceGlobalIndex;
    const suggestionIdx = state.pendingHostgroupServiceLink.suggestionIdx;

    // Stage edit to update the service - remove host_name, add hostgroup_name
    const serviceObj = state.allObjects.find(o => o.global_index === serviceGlobalIndex);
    if (serviceObj) {
        const existingEdit = state.pendingEdits.get(serviceGlobalIndex);
        const edit = existingEdit || {
            original: { ...serviceObj.attributes },
            edited: { ...serviceObj.attributes },
            object: {
                source_file: serviceObj.source_file,
                line_number: serviceObj.line_number,
                object_type: serviceObj.object_type,
                display_name: serviceObj.display_name,
                global_index: serviceGlobalIndex
            }
        };
        delete edit.edited.host_name;
        edit.edited.hostgroup_name = hostgroupName;
        state.pendingEdits.set(serviceGlobalIndex, edit);

        showToast(`Service "${serviceObj.display_name}" will now use hostgroup "${hostgroupName}"`, 'success');
    }

    // Remove from cleanup suggestions
    if (suggestionIdx >= 0 && suggestionIdx < state.allCleanupSuggestions.length) {
        state.allCleanupSuggestions.splice(suggestionIdx, 1);
        renderCleanupSuggestions();
        updateSuggestionsBadge();
        updateCleanupBadge();
    }

    // Clear the link
    state.pendingHostgroupServiceLink = null;
}

function updateCleanupBadge() {
    const badge = document.getElementById('cleanupSectionBadge');
    if (badge) {
        if (state.allCleanupSuggestions.length > 0) {
            badge.textContent = state.allCleanupSuggestions.length;
            badge.style.display = '';
        } else {
            badge.style.display = 'none';
        }
    }
}

// ============================================================================
// Notification Gap Analysis
// ============================================================================

async function loadNotificationSuggestions(forceRefresh = false) {
    const container = document.getElementById('notificationsContent');
    const badge = document.getElementById('notificationsSectionBadge');

    // Ensure health-check data is loaded (force re-fetch if forceRefresh)
    if (!state.healthCheckData || forceRefresh) {
        try {
            const result = await ApiClient.get('/api/health-check');
            if (result.success) {
                state.healthCheckData = result.data;
                mapHealthCheckToState(result.data);
            }
        } catch (error) {
            if (container) {
                container.innerHTML = '<div class="tab-placeholder">Error loading notification data.</div>';
            }
            return;
        }
    }

    if (state.allNotificationSuggestions.length === 0) {
        if (container) {
            container.innerHTML = '<div class="empty-state empty-state-success"><span class="empty-icon"><i class="fa-solid fa-circle-check"></i></span><div class="empty-title">All covered</div><div class="empty-desc">All contacts have notification commands and periods configured!</div></div>';
        }
        if (badge) badge.style.display = 'none';
        return;
    }

    if (badge) {
        badge.textContent = state.allNotificationSuggestions.length;
        badge.style.display = 'inline-flex';
    }

    renderNotificationSuggestions();
}

function renderNotificationSuggestions() {
    const container = document.getElementById('notificationsContent');
    if (!container) return;

    if (state.allNotificationSuggestions.length === 0) {
        container.innerHTML = '<div class="tab-placeholder">No notification gaps found.</div>';
        return;
    }

    // Group by type
    const byType = {};
    for (const s of state.allNotificationSuggestions) {
        if (!byType[s.type]) byType[s.type] = [];
        byType[s.type].push(s);
    }

    let html = '';

    const typeLabels = {
        'host_no_contacts': 'Hosts without contacts',
        'service_no_contacts': 'Services without contacts',
        'notifications_disabled': 'Notifications disabled'
    };

    for (const [type, items] of Object.entries(byType)) {
        html += `<div class="notification-group">
            <div class="notification-group-header">${typeLabels[type] || type} (${items.length})</div>`;

        for (let i = 0; i < items.length; i++) {
            const s = items[i];
            const globalIdx = state.allNotificationSuggestions.indexOf(s);
            const icon = s.severity === 'warning' ? '<i class="fa-solid fa-triangle-exclamation"></i>' : '<i class="fa-solid fa-circle-info"></i>';

            html += `
                <div class="notification-suggestion" onclick="Explorer.navigateToObjectByIndex(${s.object.global_index})">
                    <span class="notification-icon">${icon}</span>
                    <div class="notification-info">
                        <div class="notification-title">${Explorer.escapeHtml(s.title)}</div>
                        <div class="notification-desc">${Explorer.escapeHtml(s.description)}</div>
                    </div>
                </div>
            `;
        }

        html += '</div>';
    }

    container.innerHTML = html;
}

// ============================================================================
// Issues Tab
// ============================================================================

state.allIssues = [];

// Issues functions moved to analysis-issues.js

// Export all functions to Explorer namespace
Explorer.analyzeAll = analyzeAll;
Explorer.updateValidationSummary = updateValidationSummary;
Explorer.updateCreatePath = updateCreatePath;
Explorer.switchSuggestionsSubtab = switchSuggestionsSubtab;
Explorer.loadAllSuggestions = loadAllSuggestions;
Explorer.updateSuggestionsBadge = updateSuggestionsBadge;
// Template & grouping functions exported from analysis-suggestions.js
Explorer.mapHealthCheckToState = mapHealthCheckToState;
Explorer.loadCleanupSuggestions = loadCleanupSuggestions;
Explorer.renderCleanupSuggestions = renderCleanupSuggestions;
Explorer.toggleCleanupSection = toggleCleanupSection;
Explorer.bulkDeleteCleanupGroup = bulkDeleteCleanupGroup;
Explorer.showCleanupDetail = showCleanupDetail;
Explorer.stageCleanupDelete = stageCleanupDelete;
Explorer.resolveCleanupIssue = resolveCleanupIssue;
Explorer.fixDuplicate = fixDuplicate;
Explorer.findDuplicateDifferences = findDuplicateDifferences;
Explorer.keepDuplicateAndDeleteOthers = keepDuplicateAndDeleteOthers;
Explorer.fixLongHostList = fixLongHostList;
Explorer.openHostgroupEditorForService = openHostgroupEditorForService;
Explorer.openNewObjectInEditor = openNewObjectInEditor;
Explorer.handleHostgroupServiceLink = handleHostgroupServiceLink;
Explorer.updateCleanupBadge = updateCleanupBadge;
Explorer.loadNotificationSuggestions = loadNotificationSuggestions;
Explorer.renderNotificationSuggestions = renderNotificationSuggestions;
// Issues functions exported from analysis-issues.js

// New unified suggestions list
Explorer.renderUnifiedSuggestionsList = renderUnifiedSuggestionsList;
Explorer.handleSuggestionClick = handleSuggestionClick;
Explorer.handleSuggestionAction = handleSuggestionAction;
Explorer.filterSuggestions = filterSuggestions;
Explorer.bulkDeleteUnused = bulkDeleteUnused;
Explorer.bulkCreateMissing = bulkCreateMissing;

})(Explorer);
