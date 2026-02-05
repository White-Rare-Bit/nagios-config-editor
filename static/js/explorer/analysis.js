/** Explorer Analysis Module - Suggestions, cleanup, issues, and template/grouping analysis */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // A-01: Shared utilities extracted from duplicated patterns

    // Severity order for consistent sorting across suggestion types
    const SEVERITY_ORDER = { error: 0, warning: 1, info: 2 };

    // Strip +/! prefixes from Nagios additive/exclusion syntax
    const stripPrefix = s => s.trim().replace(/^[+!]+/, '').trim();

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
    await Promise.all([
        loadIssues(),
        loadTemplateSuggestions(forceRefresh),
        loadTemplateIssues(forceRefresh),
        loadGroupingSuggestions(forceRefresh),
        loadCleanupSuggestions(forceRefresh),
        loadNotificationSuggestions(forceRefresh)
    ]);
    // Badge is now updated inside renderUnifiedSuggestionsList() using the accurate
    // collectAllSuggestions() count, so we don't call updateSuggestionsBadge() here
    renderUnifiedSuggestionsList();
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
        // Within same severity, sort by type then name
        if (a.type !== b.type) return a.type.localeCompare(b.type);
        return (a.name || '').localeCompare(b.name || '');
    });

    return suggestions;
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
    } else if (s.data?.issues && s.data.issues.length > 0) {
        // For missing objects, navigate to the first referencing object
        const firstIssue = s.data.issues[0];
        if (firstIssue.object && firstIssue.object_type) {
            navigateToIssue(firstIssue.object, firstIssue.object_type);
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
                    resolveGroupedError(idx);
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
                showCreateTemplateDialog(s.templateIndex);
            }
            break;

        case 'create_hostgroup_pattern':
            // Create hostgroup from pattern
            if (s.groupingIndex !== undefined) {
                showCreateGroupDialog(s.groupingIndex);
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
// Template Issues (validation warnings)
// =========================================================================

/**
 * Load template validation issues from API.
 * Fetches invalid use references, circular dependencies, unused templates.
 * @param {boolean} forceRefresh - Skip cache if true
 */
async function loadTemplateIssues(forceRefresh = false) {
    if (!state.templateIssues) state.templateIssues = {};

    // Skip if already loaded and not forcing refresh
    if (!forceRefresh && Object.keys(state.templateIssues).length > 0) {
        renderTemplateIssues(state.templateIssues);
        return;
    }

    try {
        const result = await ApiClient.get('/api/templates/issues', {silent: true});
        if (result.success) {
            state.templateIssues = result.data;
            renderTemplateIssues(result.data);
        }
    } catch (error) {
        console.error('Failed to load template issues:', error);
    }
}

/**
 * Render template issues in suggestions tab.
 * Groups issues by category: invalid use, circular dependencies, unused templates.
 * @param {Object} issues - {invalid_use, circular_dependencies, unused_templates}
 */
function renderTemplateIssues(issues) {
    const container = document.getElementById('templateIssuesContent');
    const badge = document.getElementById('templateIssuesSectionBadge');
    if (!container) return;

    const totalCount = (issues.invalid_use?.length || 0) +
                       (issues.circular_dependencies?.length || 0) +
                       (issues.unused_templates?.length || 0);

    // Update badge
    if (badge) {
        badge.textContent = totalCount;
        badge.style.display = totalCount > 0 ? 'inline-flex' : 'none';
    }

    if (totalCount === 0) {
        container.innerHTML = '<div class="empty-state empty-state-success"><span class="empty-icon"><i class="fa-solid fa-circle-check"></i></span><div class="empty-title">No template issues</div><div class="empty-desc">All template references are valid!</div></div>';
        return;
    }

    let html = '';

    // Invalid use references (most critical)
    if (issues.invalid_use && issues.invalid_use.length > 0) {
        html += '<div class="suggestion-category">';
        html += '<div class="suggestion-category-title"><i class="fa-solid fa-triangle-exclamation"></i> Invalid Template References</div>';
        issues.invalid_use.forEach(issue => {
            const stableKey = `${issue.source_file}|${issue.object_type}|${issue.object_name}`;
            html += `<div class="suggestion-item severity-error" data-action="selectObjectByKey" data-stable-key="${Explorer.escapeHtml(stableKey)}">`;
            html += `<i class="fa-solid fa-xmark-circle"></i> ${Explorer.escapeHtml(issue.message)}`;
            html += '</div>';
        });
        html += '</div>';
    }

    // Unused templates (informational)
    if (issues.unused_templates && issues.unused_templates.length > 0) {
        html += '<div class="suggestion-category">';
        html += '<div class="suggestion-category-title"><i class="fa-solid fa-circle-info"></i> Unused Templates</div>';
        issues.unused_templates.forEach(issue => {
            // Find the template object to get its source_file
            const templateObj = state.allObjects.find(o =>
                o.object_type === issue.object_type &&
                o.attributes.name === issue.template_name &&
                o.attributes.register === '0'
            );
            const sourceFile = templateObj ? templateObj.source_file : '';
            const stableKey = `${sourceFile}|${issue.object_type}|${issue.template_name}`;
            html += `<div class="suggestion-item severity-info" data-action="selectObjectByKey" data-stable-key="${Explorer.escapeHtml(stableKey)}">`;
            html += `<i class="fa-solid fa-cube"></i> ${Explorer.escapeHtml(issue.message)}`;
            html += '</div>';
        });
        html += '</div>';
    }

    container.innerHTML = html;
}

// Template Consolidation Suggestions
async function loadTemplateSuggestions(forceRefresh = false) {
    const container = document.getElementById('templatesContent');
    const badge = document.getElementById('templatesSectionBadge');

    if (!forceRefresh && state.allTemplateSuggestions.length > 0) {
        filterTemplateSuggestions();
        return;
    }

    if (container) {
        container.innerHTML = '<div class="tab-placeholder">Analyzing objects...</div>';
    }

    // Analyze objects client-side
    state.allTemplateSuggestions = analyzeTemplateConsolidation();

    if (state.allTemplateSuggestions.length === 0) {
        if (container) {
            container.innerHTML = '<div class="empty-state empty-state-success"><span class="empty-icon"><i class="fa-solid fa-circle-check"></i></span><div class="empty-title">No opportunities found</div><div class="empty-desc">Your objects are well-templated!</div></div>';
        }
        if (badge) badge.style.display = 'none';
        return;
    }

    if (badge) {
        badge.textContent = state.allTemplateSuggestions.length;
        badge.style.display = 'inline-flex';
    }

    filterTemplateSuggestions();
}

function analyzeTemplateConsolidation() {
    const suggestions = [];

    // Identity fields that should be excluded from comparison
    const identityFields = ['host_name', 'service_description', 'name', 'contact_name', 'alias', 'address', 'hostgroup_name', 'servicegroup_name', 'contactgroup_name', 'command_name', 'timeperiod_name'];

    // Group objects by type
    const objectsByType = {};
    for (const obj of state.allObjects) {
        if (!objectsByType[obj.object_type]) {
            objectsByType[obj.object_type] = [];
        }
        objectsByType[obj.object_type].push(obj);
    }

    // Analyze each object type
    for (const [objType, objects] of Object.entries(objectsByType)) {
        if (objects.length < 3) continue; // Need at least 3 objects to suggest a template

        // Skip if this type is typically a template itself
        if (['timeperiod', 'command'].includes(objType)) continue;

        // Create signature for each object (excluding identity fields)
        const signatures = new Map(); // signature -> [objects]

        for (const obj of objects) {
            // Skip objects that already use a template
            if (obj.attributes.use || obj.attributes.register === '0') continue;

            // Build attribute signature (sorted key-value pairs)
            const attrPairs = [];
            for (const [key, value] of Object.entries(obj.attributes)) {
                if (!identityFields.includes(key) && key !== 'register') {
                    attrPairs.push(`${key}=${value}`);
                }
            }

            if (attrPairs.length === 0) continue;

            attrPairs.sort();
            const signature = attrPairs.join('|');

            if (!signatures.has(signature)) {
                signatures.set(signature, []);
            }
            signatures.get(signature).push(obj);
        }

        // Find signatures with multiple objects
        for (const [signature, matchingObjects] of signatures) {
            if (matchingObjects.length >= 3) {
                // Parse the signature back to attributes
                const attrs = {};
                for (const pair of signature.split('|')) {
                    const [key, value] = pair.split('=');
                    attrs[key] = value;
                }

                // Generate a suggested template name
                const suggestedName = generateTemplateName(objType, matchingObjects, attrs);

                suggestions.push({
                    type: objType,
                    suggestedName: suggestedName,
                    attributes: attrs,
                    objects: matchingObjects,
                    count: matchingObjects.length,
                    attrCount: Object.keys(attrs).length
                });
            }
        }
    }

    // Sort by potential impact (count * attrCount)
    suggestions.sort((a, b) => (b.count * b.attrCount) - (a.count * a.attrCount));

    return suggestions;
}

function generateTemplateName(objType, objects, attrs) {
    // Try to find common patterns in object names
    const names = objects.map(o => {
        return o.attributes.host_name || o.attributes.service_description || o.attributes.name || '';
    }).filter(n => n);

    if (names.length > 0) {
        // Find common prefix
        let prefix = names[0];
        for (const name of names) {
            while (prefix && !name.startsWith(prefix)) {
                prefix = prefix.slice(0, -1);
            }
        }
        if (prefix && prefix.length >= 3) {
            // Clean up the prefix (remove trailing dashes, numbers, etc.)
            prefix = prefix.replace(/[-_\d]+$/, '');
            if (prefix.length >= 3) {
                return `${prefix}-${objType}-template`;
            }
        }
    }

    // Fall back to attribute-based naming
    if (attrs.check_command) {
        const cmd = attrs.check_command.split('!')[0];
        return `${cmd}-${objType}-template`;
    }

    return `common-${objType}-template`;
}

function filterTemplateSuggestions() {
    const container = document.getElementById('templatesContent');
    const slider = document.getElementById('minTemplateObjects');
    const sliderValue = document.getElementById('minTemplateObjectsValue');

    if (!container || !slider) return;

    const minObjects = parseInt(slider.value);
    if (sliderValue) sliderValue.textContent = minObjects;

    const filtered = state.allTemplateSuggestions.filter(s => s.count >= minObjects);

    if (filtered.length === 0) {
        container.innerHTML = '<div class="tab-placeholder">No suggestions match the filter criteria.</div>';
        return;
    }

    container.innerHTML = filtered.map((s, idx) => `
        <div class="template-suggestion" onclick="Explorer.showCreateTemplateDialog(${state.allTemplateSuggestions.indexOf(s)})">
            <div class="template-suggestion-icon"><i class="fa-solid fa-cube"></i></div>
            <div class="template-suggestion-content">
                <div class="template-suggestion-header">
                    <span class="template-suggestion-name">${Explorer.escapeHtml(s.suggestedName)}</span>
                    <span class="template-suggestion-type">${Explorer.escapeHtml(s.type)}</span>
                </div>
            <div class="template-suggestion-meta">
                ${s.count} objects share ${s.attrCount} identical attributes
            </div>
            <div class="template-suggestion-attrs">
                ${Object.keys(s.attributes).slice(0, 5).map(k => `<span class="template-attr">${Explorer.escapeHtml(k)}</span>`).join('')}
                ${Object.keys(s.attributes).length > 5 ? `<span class="template-attr">+${Object.keys(s.attributes).length - 5} more</span>` : ''}
            </div>
            <div class="template-suggestion-objects">
                ${s.objects.slice(0, 4).map(o => `<span class="template-object-name">${Explorer.escapeHtml(getObjectDisplayName(o))}</span>`).join('')}
                ${s.objects.length > 4 ? `<span class="template-object-name">+${s.objects.length - 4} more</span>` : ''}
            </div>
            </div>
        </div>
    `).join('');
}

function getObjectDisplayName(obj) {
    return obj.attributes.host_name || obj.attributes.service_description || obj.attributes.name || obj.attributes.contact_name || `${obj.object_type}@${obj.line_number}`;
}

// Grouping Suggestions
async function loadGroupingSuggestions(forceRefresh = false) {
    const container = document.getElementById('suggestionsContent');
    const badge = document.getElementById('groupingSectionBadge');

    // Use cached data if available and not forcing refresh
    if (!forceRefresh && state.allGroupingSuggestions.length > 0) {
        filterGroupingSuggestions();
        return;
    }

    if (container) {
        container.innerHTML = '<div class="tab-placeholder">Loading suggestions...</div>';
    }

    const result = await ApiClient.get('/api/smart-grouping/suggest', { silent: true });

    if (!result.success) {
        if (container) {
            container.innerHTML = `<div class="tab-placeholder">Error: ${Explorer.escapeHtml(result.error)}</div>`;
        }
        return;
    }

    state.allGroupingSuggestions = result.data?.suggestions || [];

    if (state.allGroupingSuggestions.length === 0) {
        if (container) {
            container.innerHTML = '<div class="empty-state empty-state-success"><span class="empty-icon"><i class="fa-solid fa-circle-check"></i></span><div class="empty-title">No suggestions</div><div class="empty-desc">Your hosts are well organized!</div></div>';
        }
        if (badge) badge.style.display = 'none';
        return;
    }

    if (badge) {
        badge.textContent = state.allGroupingSuggestions.length;
        badge.style.display = 'inline-flex';
    }

    filterGroupingSuggestions();
}

function filterGroupingSuggestions() {
    const container = document.getElementById('suggestionsContent');
    const slider = document.getElementById('minMembersSlider');
    const sliderValue = document.getElementById('minMembersValue');

    if (!container || !slider) return;

    const minMembers = parseInt(slider.value);
    if (sliderValue) sliderValue.textContent = minMembers;

    const filtered = state.allGroupingSuggestions.filter(s => s.count >= minMembers);

    if (filtered.length === 0) {
        container.innerHTML = '<div class="tab-placeholder">No suggestions match the filter criteria.</div>';
        return;
    }

    container.innerHTML = filtered.map((s, idx) => `
        <div class="suggestion-item" onclick="Explorer.showCreateGroupDialog(${state.allGroupingSuggestions.indexOf(s)})">
            <div class="suggestion-header">
                <span class="suggestion-name">${Explorer.escapeHtml(s.name)}</span>
                <span class="suggestion-type ${s.type}">${s.type.replace('_', ' ')}</span>
            </div>
            <div class="suggestion-meta">
                ${s.count} hosts
                <span class="suggestion-confidence ${getConfidenceClass(s.confidence)}">${s.confidence.toFixed(1)}</span>
                ${s.overlaps_with?.length > 0 ? ` • Overlaps: ${s.overlaps_with.join(', ')}` : ''}
            </div>
            <div class="suggestion-members">
                ${s.members.slice(0, 5).map(m => `<span class="suggestion-member">${Explorer.escapeHtml(m)}</span>`).join('')}
                ${s.members.length > 5 ? `<span class="suggestion-member">+${s.members.length - 5} more</span>` : ''}
            </div>
        </div>
    `).join('');
}

function getConfidenceClass(confidence) {
    if (confidence >= 10) return 'confidence-high';
    if (confidence >= 5) return 'confidence-medium';
    return 'confidence-low';
}

function showCreateTemplateDialog(idx) {
    const suggestion = state.allTemplateSuggestions[idx];

    // A-03: Use shared file options builder
    const configFiles = [...new Set(state.allObjects.map(o => o.source_file))].sort();
    const objectFiles = [...new Set(suggestion.objects.map(o => o.source_file))];
    const defaultFile = configFiles.find(f => f.toLowerCase().includes('template')) ||
                        objectFiles[0] || configFiles[0] || '';
    const fileOptions = buildFileOptionsHtml(defaultFile);

    // Format attributes for display
    const attrsHtml = Object.entries(suggestion.attributes)
        .map(([k, v]) => `<div class="attr-display-row"><span class="attr-display-key">${Explorer.escapeHtml(k)}</span><span class="attr-display-value">${Explorer.escapeHtml(v)}</span></div>`)
        .join('');

    Explorer.showDialog('Create Template', `
        <label>Template Name</label>
        <input type="text" id="newTemplateName" value="${Explorer.escapeHtml(suggestion.suggestedName)}">
        <label>Target File</label>
        <select id="newTemplateFile" class="dialog-select">
            ${fileOptions}
        </select>
        <label>Shared Attributes (${Object.keys(suggestion.attributes).length})</label>
        <div class="dialog-scrollable-list dialog-scrollable-list--short">
            ${attrsHtml}
        </div>
        <div class="dialog-checkbox-group">
            <label>
                <input type="checkbox" id="updateObjects" checked>
                Update ${suggestion.count} objects to use this template
            </label>
            <div class="dialog-scrollable-list dialog-scrollable-list--short code-preview">
                ${suggestion.objects.map(o => `<span class="template-object-name">${Explorer.escapeHtml(getObjectDisplayName(o))}</span>`).join(' ')}
            </div>
        </div>
    `, async () => {
        const name = document.getElementById('newTemplateName').value.trim();
        const targetFile = document.getElementById('newTemplateFile').value;
        const updateObjects = document.getElementById('updateObjects').checked;

        if (!name) {
            showToast('Please enter a name', 'warning');
            return;
        }
        if (!targetFile) {
            showToast('Please select a target file', 'warning');
            return;
        }

        // Check if template with this name already exists
        const existing = state.allObjects.find(o => o.object_type === suggestion.type && o.attributes.name === name);
        if (existing) {
            showToast(`Template "${name}" already exists`, 'error');
            return;
        }

        // Stage the template creation
        const templateAttrs = { ...suggestion.attributes, name: name, register: '0' };
        state.stagedCreations.push({
            id: generateUniqueId(),
            object_type: suggestion.type,
            attributes: templateAttrs,
            targetFile: targetFile,
            displayName: name
        });
        const newStagedIdx = state.stagedCreations.length - 1;

        // If updating objects, stage edits to add 'use' and remove common attrs
        if (updateObjects) {
            for (const obj of suggestion.objects) {
                const newAttrs = { ...obj.attributes };

                // Add 'use' directive
                newAttrs.use = name;

                // Remove attributes that are now in the template
                for (const key of Object.keys(suggestion.attributes)) {
                    delete newAttrs[key];
                }

                // Stage the edit
                state.pendingEdits.set(obj.global_index, {
                    original: { ...obj.attributes },
                    edited: newAttrs,
                    object: {
                        source_file: obj.source_file,
                        line_number: obj.line_number,
                        object_type: obj.object_type,
                        display_name: obj.display_name,
                        global_index: obj.global_index
                    }
                });
            }
        }

        Explorer.closeDialog();
        Explorer.saveStagedChanges();
        Explorer.refreshAfterObjectChange();

        // Select the newly created staged item to show in center pane
        setTimeout(() => {
            state.selectedStagedIndices.clear();
            state.selectedStagedIndices.add(newStagedIdx);
            Explorer.selectStagedCreationForEdit(newStagedIdx);

            // Scroll to and highlight in tree
            const item = document.querySelector(`[data-staged-index="${newStagedIdx}"]`);
            if (item) {
                item.classList.add('selected');
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 50);

        const msg = updateObjects
            ? `Staged template "${name}" and updated ${suggestion.count} objects. Use Commit to apply.`
            : `Staged template "${name}". Use Commit to apply.`;
        showToast(msg, 'success');

        // Remove this suggestion from the list
        const suggestionIdx = state.allTemplateSuggestions.indexOf(suggestion);
        if (suggestionIdx > -1) {
            state.allTemplateSuggestions.splice(suggestionIdx, 1);
        }
        // Refresh suggestions to update counts
        renderUnifiedSuggestionsList();
    });
}

function showCreateGroupDialog(idx) {
    const suggestion = state.allGroupingSuggestions[idx];

    // A-03: Use shared file options builder
    const configFiles = [...new Set(state.allObjects.map(o => o.source_file))].sort();
    const defaultFile = configFiles.find(f => f.toLowerCase().includes('hostgroup')) ||
                        configFiles.find(f => state.allObjects.some(o => o.source_file === f && o.object_type === 'host')) ||
                        configFiles[0] || '';
    const fileOptions = buildFileOptionsHtml(defaultFile);

    Explorer.showDialog('Create Hostgroup', `
        <label>Group Name</label>
        <input type="text" id="newGroupName" value="${Explorer.escapeHtml(suggestion.name)}">
        <label>Target File</label>
        <select id="newGroupFile" class="dialog-select">
            ${fileOptions}
        </select>
        <label>Members (${suggestion.members.length} hosts)</label>
        <div class="dialog-scrollable-list">
            ${suggestion.members.map(m => `<span class="suggestion-member">${Explorer.escapeHtml(m)}</span>`).join(' ')}
        </div>
    `, async () => {
        const name = document.getElementById('newGroupName').value.trim();
        const targetFile = document.getElementById('newGroupFile').value;

        if (!name) {
            showToast('Please enter a name', 'warning');
            return;
        }
        if (!targetFile) {
            showToast('Please select a target file', 'warning');
            return;
        }

        // Check if hostgroup with this name already exists
        const existing = state.allObjects.find(o => o.object_type === 'hostgroup' && o.attributes.hostgroup_name === name);
        if (existing) {
            showToast(`Hostgroup "${name}" already exists`, 'error');
            return;
        }

        // Check if already staged
        const alreadyStaged = state.stagedCreations.find(c => c.object_type === 'hostgroup' && c.attributes.hostgroup_name === name);
        if (alreadyStaged) {
            showToast(`Hostgroup "${name}" is already staged for creation`, 'warning');
            return;
        }

        // Stage the creation instead of immediately creating
        state.stagedCreations.push({
            id: generateUniqueId(),
            object_type: 'hostgroup',
            attributes: {
                hostgroup_name: name,
                alias: name,
                members: suggestion.members.join(',')
            },
            targetFile: targetFile,
            displayName: name
        });
        const newStagedIdx = state.stagedCreations.length - 1;

        Explorer.closeDialog();
        Explorer.saveStagedChanges();
        Explorer.refreshAfterObjectChange();

        // Select the newly created staged item to show in center pane
        setTimeout(() => {
            state.selectedStagedIndices.clear();
            state.selectedStagedIndices.add(newStagedIdx);
            Explorer.selectStagedCreationForEdit(newStagedIdx);

            // Scroll to and highlight in tree
            const item = document.querySelector(`[data-staged-index="${newStagedIdx}"]`);
            if (item) {
                item.classList.add('selected');
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 50);

        showToast(`Staged hostgroup "${name}" for creation. Use Commit to apply.`, 'success');

        // Remove this suggestion from the list since it's been acted on
        const suggestionIdx = state.allGroupingSuggestions.indexOf(suggestion);
        if (suggestionIdx > -1) {
            state.allGroupingSuggestions.splice(suggestionIdx, 1);
        }
        // Refresh suggestions to update counts
        renderUnifiedSuggestionsList();
    });
}

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

    // Client-side analysis
    state.allCleanupSuggestions = analyzeCleanupIssues();

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
// Cleanup Analysis Helpers
// =============================================================================

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
            const files = [...new Set(objects.map(o => o.source_file.split('/').pop()))];

            let displayIdentity = identity;
            if (type === 'service' && identity.includes('::')) {
                const [hostPart, servicePart] = identity.split('::');
                displayIdentity = hostPart === '*' ? `${servicePart} (all hosts)` : `${servicePart} on ${hostPart}`;
            }

            suggestions.push({
                type: 'duplicate',
                severity: 'error',
                objects: objects,
                title: `Duplicate ${type}: ${displayIdentity}`,
                description: `Defined ${objects.length} times in: ${files.join(', ')}`,
                action: 'review'
            });
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
                    // A-01: use shared stripPrefix utility
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
    // A-01: use shared stripPrefix utility (defined at module top)

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
    // A-01: use shared stripPrefix utility (defined at module top)

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
    // A-01: use shared stripPrefix utility (defined at module top)
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

// =============================================================================
// Main Cleanup Analysis Function
// =============================================================================

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

    // Sort: errors first, then warnings, then info, then by type (A-01: use shared constant)
    suggestions.sort((a, b) => {
        const severityDiff = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
        if (severityDiff !== 0) return severityDiff;
        return a.type.localeCompare(b.type);
    });

    return suggestions;
}


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
                const resolveInfo = getIssueResolveInfo(s.issueData);
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
    const resolveInfo = getIssueResolveInfo(issue);
    if (!resolveInfo) return;

    // Find the source file of the object that has the issue
    const sourceObj = s.object;
    const targetFile = sourceObj ? sourceObj.source_file : null;

    // Open create object dialog with pre-filled values
    openCreateObjectForIssue(resolveInfo.objectType, resolveInfo.missingName, targetFile, issue);
}

function fixDuplicate(idx) {
    const s = state.allCleanupSuggestions[idx];
    if (!s || s.type !== 'duplicate' || !s.objects) return;

    // Find differences between duplicates
    const differences = findDuplicateDifferences(s.objects);
    const hasDifferences = differences.length > 0;

    // Build list of duplicates with "Keep" buttons
    const objectList = s.objects.map((o, i) => {
        const file = o.source_file.split('/').pop();

        // Show differing attributes for this object
        let diffHtml = '';
        if (hasDifferences) {
            const diffAttrs = differences.map(attr => {
                const val = o.attributes[attr];
                return `<span class="diff-attr"><code>${Explorer.escapeHtml(attr)}</code>: ${val !== undefined ? Explorer.escapeHtml(String(val)) : '<em>not set</em>'}</span>`;
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
    if (!s || !s.objects) return;

    // Stage deletion of all except the one to keep
    let deletedCount = 0;
    s.objects.forEach((obj, i) => {
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

    if (!forceRefresh && state.allNotificationSuggestions.length > 0) {
        renderNotificationSuggestions();
        return;
    }

    if (container) {
        container.innerHTML = '<div class="tab-placeholder">Analyzing notification coverage...</div>';
    }

    // Client-side analysis
    state.allNotificationSuggestions = analyzeNotificationGaps();

    if (state.allNotificationSuggestions.length === 0) {
        if (container) {
            container.innerHTML = '<div class="empty-state empty-state-success"><span class="empty-icon"><i class="fa-solid fa-circle-check"></i></span><div class="empty-title">All covered</div><div class="empty-desc">All hosts and services have notification contacts configured!</div></div>';
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

function analyzeNotificationGaps() {
    const suggestions = [];

    // Build a set of all contact and contactgroup names
    const contacts = new Set(state.allObjects.filter(o => o.object_type === 'contact').map(o => o.attributes.contact_name));
    const contactgroups = new Set(state.allObjects.filter(o => o.object_type === 'contactgroup').map(o => o.attributes.contactgroup_name));

    // Check hosts
    const hosts = state.allObjects.filter(o => o.object_type === 'host' && o.attributes.register !== '0');
    for (const host of hosts) {
        const hasContacts = host.attributes.contacts && host.attributes.contacts.trim() !== '';
        const hasContactGroups = host.attributes.contact_groups && host.attributes.contact_groups.trim() !== '';

        // Check if it inherits from a template that might have contacts
        const usesTemplate = host.attributes.use;

        if (!hasContacts && !hasContactGroups && !usesTemplate) {
            suggestions.push({
                type: 'host_no_contacts',
                severity: 'warning',
                object: host,
                title: `Host without contacts: ${host.attributes.host_name}`,
                description: 'No contacts or contact_groups defined. Notifications will not be sent.',
                fix: 'contacts'
            });
        }
    }

    // Check services
    const services = state.allObjects.filter(o => o.object_type === 'service' && o.attributes.register !== '0');
    for (const service of services) {
        const hasContacts = service.attributes.contacts && service.attributes.contacts.trim() !== '';
        const hasContactGroups = service.attributes.contact_groups && service.attributes.contact_groups.trim() !== '';
        const usesTemplate = service.attributes.use;

        if (!hasContacts && !hasContactGroups && !usesTemplate) {
            const hostName = service.attributes.host_name || '*';
            const serviceDesc = service.attributes.service_description || 'unknown';
            suggestions.push({
                type: 'service_no_contacts',
                severity: 'warning',
                object: service,
                title: `Service without contacts: ${serviceDesc}`,
                description: `On host "${hostName}". No contacts or contact_groups defined.`,
                fix: 'contacts'
            });
        }
    }

    // Check for hosts/services with notifications disabled but no apparent reason
    for (const host of hosts) {
        if (host.attributes.notifications_enabled === '0' && !host.attributes.use) {
            suggestions.push({
                type: 'notifications_disabled',
                severity: 'info',
                object: host,
                title: `Notifications disabled: ${host.attributes.host_name}`,
                description: 'Host has notifications explicitly disabled.',
                fix: null
            });
        }
    }

    // Sort by severity
    const severityOrder = { warning: 0, info: 1 };
    suggestions.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);

    return filterActiveSuggestions(suggestions);
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

async function loadIssues() {
    const container = document.getElementById('issuesContent');
    const badge = document.getElementById('issuesSectionBadge');

    if (container) {
        container.innerHTML = '<div class="tab-placeholder">Loading issues...</div>';
    }

    const result = await ApiClient.get('/api/health-check', { silent: true });

    if (!result.success) {
        if (container) {
            container.innerHTML = `<div class="tab-placeholder">Error: ${Explorer.escapeHtml(result.error)}</div>`;
        }
        return;
    }

    state.allIssues = result.data?.issues || [];

    // Build grouped errors and render
    filterIssues();

    // Update badge with grouped error count
    if (badge) {
        badge.textContent = state.groupedErrors.length;
        badge.style.display = state.groupedErrors.length > 0 ? 'inline-flex' : 'none';
    }

    updateSuggestionsBadge();
}

// Store grouped errors for resolve functionality

function buildGroupedErrors(combined) {
    // Group errors by the missing object (type + name)
    const groups = new Map();
    for (const issue of combined) {
        const resolveInfo = getIssueResolveInfo(issue);
        if (resolveInfo) {
            // Group by missing object type and name
            const key = `${resolveInfo.objectType}:${resolveInfo.missingName}`;
            if (!groups.has(key)) {
                groups.set(key, {
                    objectType: resolveInfo.objectType,
                    missingName: resolveInfo.missingName,
                    issues: [],
                    firstIssue: issue
                });
            }
            groups.get(key).issues.push(issue);
        } else {
            // Issues that can't be resolved by creating something - show individually
            const key = `ungrouped:${issue.object_type}:${issue.object}:${issue.message}`;
            groups.set(key, {
                objectType: null,
                missingName: null,
                issues: [issue],
                firstIssue: issue
            });
        }
    }

    // Convert to array and sort
    state.groupedErrors = Array.from(groups.values());
    state.groupedErrors.sort((a, b) => {
        // Sort by object type, then by name
        if (a.objectType && b.objectType) {
            const typeCompare = a.objectType.localeCompare(b.objectType);
            if (typeCompare !== 0) return typeCompare;
            return a.missingName.localeCompare(b.missingName);
        }
        return 0;
    });
}

function filterIssues() {
    const container = document.getElementById('issuesContent');

    // Combine server issues with staged issues
    // Only show errors (issues that prevent Nagios from running)
    const combined = [...state.allIssues, ...Explorer.stagedIssues].filter(i => i.severity === 'error');

    if (combined.length === 0) {
        state.groupedErrors = [];
        if (container) {
            container.innerHTML = '<div class="empty-state empty-state-success"><span class="empty-icon"><i class="fa-solid fa-circle-check"></i></span><div class="empty-title">No errors</div><div class="empty-desc">Nagios configuration is valid</div></div>';
        }
        return;
    }

    // Build grouped errors (also updates state.groupedErrors array for badge counts)
    buildGroupedErrors(combined);

    // If container doesn't exist yet, just return (state.groupedErrors is set for badge counting)
    if (!container) {
        return;
    }

    // Group errors by object type for section headers
    const errorGroups = {};
    const groupOrder = ['template', 'command', 'host', 'hostgroup', 'servicegroup', 'contact', 'contactgroup', 'timeperiod', 'other'];
    const groupConfig = {
        'template': { icon: '<i class="fa-solid fa-clipboard"></i>', label: 'Missing Templates' },
        'command': { icon: '<i class="fa-solid fa-bolt"></i>', label: 'Missing Commands' },
        'host': { icon: '<i class="fa-solid fa-desktop"></i>', label: 'Missing Hosts' },
        'hostgroup': { icon: '<i class="fa-solid fa-desktop"></i>', label: 'Missing Hostgroups' },
        'servicegroup': { icon: '<i class="fa-solid fa-gear"></i>', label: 'Missing Servicegroups' },
        'contact': { icon: '<i class="fa-solid fa-user"></i>', label: 'Missing Contacts' },
        'contactgroup': { icon: '<i class="fa-solid fa-users"></i>', label: 'Missing Contact Groups' },
        'timeperiod': { icon: '<i class="fa-solid fa-clock"></i>', label: 'Missing Time Periods' },
        'other': { icon: '<i class="fa-solid fa-circle-xmark"></i>', label: 'Other Errors' }
    };

    // Categorize grouped errors
    state.groupedErrors.forEach((group, idx) => {
        const groupType = group.objectType || 'other';
        if (!errorGroups[groupType]) errorGroups[groupType] = [];
        errorGroups[groupType].push({ group, idx });
    });

    // Render grouped errors with section headers
    let html = '';
    for (const groupType of groupOrder) {
        if (!errorGroups[groupType] || errorGroups[groupType].length === 0) continue;

        const config = groupConfig[groupType] || { icon: '<i class="fa-solid fa-circle-xmark"></i>', label: groupType };
        const items = errorGroups[groupType];

        // Check if this group has resolvable items (can create missing objects)
        const hasResolvableItems = groupType !== 'other' && items.some(({ group }) => group.objectType);
        const createAllBtn = hasResolvableItems
            ? `<button class="nbe-btn nbe-btn--primary nbe-btn--xs" onclick="event.stopPropagation(); Explorer.createAllMissing('${groupType}')" title="Create all missing ${groupType}s">Create All</button>`
            : '';

        html += `
            <div class="cleanup-section collapsed section-error" data-group="${groupType}">
                <div class="cleanup-section-header" onclick="Explorer.toggleCleanupSection(this)">
                    <div class="cleanup-section-title">
                        <span class="cleanup-section-icon">${config.icon}</span>
                        <span>${config.label}</span>
                        <span class="cleanup-section-count">${items.length}</span>
                    </div>
                    <div class="cleanup-section-actions">
                        ${createAllBtn}
                        <span class="cleanup-section-toggle"><i class="fa-solid fa-chevron-right"></i></span>
                    </div>
                </div>
                <div class="cleanup-section-items">
        `;

        for (const { group, idx } of items) {
            if (group.objectType) {
                // Resolvable error - can create missing object
                const title = `${group.missingName}`;
                const count = group.issues.length;
                const desc = count === 1
                    ? `Referenced by: ${group.issues[0].object_type} "${group.issues[0].object}"`
                    : `Referenced by ${count} objects`;

                html += `
                    <div class="cleanup-suggestion cleanup-error" data-index="${idx}" onclick="Explorer.showGroupedErrorDetail(${idx})">
                        <div class="cleanup-info">
                            <div class="cleanup-title">${Explorer.escapeHtml(title)}</div>
                            <div class="cleanup-desc">${Explorer.escapeHtml(desc)}</div>
                        </div>
                        <button class="cleanup-action-btn cleanup-fix-btn" onclick="event.stopPropagation(); Explorer.resolveGroupedError(${idx})">Create ${group.objectType}</button>
                    </div>
                `;
            } else {
                // Ungrouped error
                const issue = group.firstIssue;
                const title = `${issue.object_type}: ${issue.object}`;
                html += `
                    <div class="cleanup-suggestion cleanup-error" data-index="${idx}" onclick="Explorer.navigateToIssue('${Explorer.escapeJs(issue.object)}', '${Explorer.escapeJs(issue.object_type)}')">
                        <div class="cleanup-info">
                            <div class="cleanup-title">${Explorer.escapeHtml(title)}</div>
                            <div class="cleanup-desc">${Explorer.escapeHtml(issue.message)}</div>
                        </div>
                    </div>
                `;
            }
        }

        html += `
                </div>
            </div>
        `;
    }

    container.innerHTML = html;
}

function showGroupedErrorDetail(idx) {
    const group = state.groupedErrors[idx];
    if (!group) return;

    // If only one affected object, navigate directly to it
    if (group.issues.length === 1) {
        const issue = group.issues[0];
        navigateToIssue(issue.object, issue.object_type);
        return;
    }

    // Multiple affected objects - show dialog
    const objectList = group.issues.map(issue => {
        return `<div class="ref-item ref-item-clickable" onclick="Explorer.navigateToIssue('${Explorer.escapeJs(issue.object)}', '${Explorer.escapeJs(issue.object_type)}'); Explorer.closeDialog();">
            <span class="ref-type-badge type-${issue.object_type}">${Explorer.escapeHtml(issue.object_type)}</span>
            <span class="ref-name" title="${Explorer.escapeHtml(issue.object)}">${Explorer.escapeHtml(issue.object)}</span>
        </div>`;
    }).join('');

    Explorer.showDialog(`Missing ${group.objectType}: ${group.missingName}`, `
        <p class="u-mb-md dialog-info-text">This ${group.objectType} is referenced by ${group.issues.length} object(s) but doesn't exist.</p>
        <p class="u-mb-sm"><strong>Affected objects:</strong></p>
        <div class="dialog-scrollable-list">${objectList}</div>
    `, null);
}

function resolveGroupedError(idx) {
    const group = state.groupedErrors[idx];
    if (!group || !group.objectType) return;

    // Use the first issue to determine the target file
    const firstIssue = group.firstIssue;
    const sourceObj = state.allObjects.find(o =>
        o.object_type === firstIssue.object_type &&
        (o.display_name === firstIssue.object || o.name === firstIssue.object)
    );
    const targetFile = sourceObj ? sourceObj.source_file : null;

    // Open create object dialog
    openCreateObjectForIssue(group.objectType, group.missingName, targetFile, firstIssue);
}

/**
 * Create all missing objects of a given type
 * @param {string} groupType - The type of missing objects (command, host, etc.)
 */
function createAllMissing(groupType) {
    // Find all groups of this type that can be resolved
    const matchingGroups = state.groupedErrors.filter(g =>
        g.objectType === groupType || (groupType === 'template' && g.firstIssue?.type === 'missing_template')
    );

    if (matchingGroups.length === 0) {
        showToast('No resolvable items found', 'info');
        return;
    }

    // Get list of existing files for the target file dropdown
    const existingFiles = [...new Set(state.allObjects.map(o => o.source_file))].sort();

    // Try to find the most common target file from source objects
    const fileCounts = {};
    matchingGroups.forEach(g => {
        const issue = g.firstIssue;
        const sourceObj = state.allObjects.find(o =>
            o.object_type === issue.object_type &&
            (o.display_name === issue.object || o.name === issue.object)
        );
        if (sourceObj) {
            fileCounts[sourceObj.source_file] = (fileCounts[sourceObj.source_file] || 0) + 1;
        }
    });

    // Default to most common file, or first file if no matches
    const defaultFile = Object.entries(fileCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || existingFiles[0];

    const fileOptions = existingFiles.map(f => {
        const selected = f === defaultFile ? 'selected' : '';
        const fileName = f.split('/').pop();
        return `<option value="${Explorer.escapeHtml(f)}" ${selected}>${Explorer.escapeHtml(fileName)}</option>`;
    }).join('');

    // Build list of items to create
    const itemsList = matchingGroups.map(g => {
        const refCount = g.issues.length;
        return `<div class="batch-create-item">
            <span class="batch-create-name">${Explorer.escapeHtml(g.missingName)}</span>
            <span class="batch-create-refs">${refCount} reference${refCount !== 1 ? 's' : ''}</span>
        </div>`;
    }).join('');

    const typeLabel = groupType === 'template' ? 'templates' : `${groupType}s`;

    Explorer.showDialog(`Create All Missing ${typeLabel.charAt(0).toUpperCase() + typeLabel.slice(1)}`, `
        <p class="u-mb-md dialog-info-text">Create ${matchingGroups.length} missing ${typeLabel} at once.</p>
        <div class="u-mb-md">
            <label class="form-label">Target File</label>
            <select class="form-select" id="batchCreateTargetFile">
                ${fileOptions}
            </select>
        </div>
        <div class="u-mb-md">
            <label class="form-label">Objects to Create (${matchingGroups.length})</label>
            <div class="dialog-scrollable-list batch-create-list">
                ${itemsList}
            </div>
            <small class="text-muted">Default attributes will be used. You can edit them after creation.</small>
        </div>
    `, async () => {
        const targetFile = document.getElementById('batchCreateTargetFile').value;
        if (!targetFile) {
            showToast('Please select a target file', 'error');
            return;
        }
        await executeBatchCreate(matchingGroups, targetFile);
    }, 'Create All');
}

/**
 * Execute batch creation of multiple objects
 */
async function executeBatchCreate(groups, targetFile) {
    Explorer.closeDialog();

    let created = 0;
    let failed = 0;

    for (const group of groups) {
        const issue = group.firstIssue;
        const isTemplate = issue.type === 'missing_template';
        const objectType = isTemplate ? issue.object_type : group.objectType;

        // Build attributes for this object
        const attributes = buildDefaultAttributes(objectType, group.missingName, isTemplate);

        try {
            // Stage the creation (same as createObjectForIssue)
            const newObj = {
                object_type: objectType,
                display_name: group.missingName,
                attributes: attributes,
                source_file: targetFile,
                line_number: 0,
                global_index: -1
            };

            // Generate a temporary index for the new object
            const tempIndex = -(Date.now() + created);
            newObj.global_index = tempIndex;

            // Add to staged creations
            const creation = {
                object_type: objectType,
                attributes: {...attributes},
                targetFile: targetFile,
                tempIndex: tempIndex,
                display_name: group.missingName
            };

            // Get or initialize staged creations
            const staging = Explorer.getStagedCreations();
            staging.push(creation);
            Explorer.setStagedCreations(staging);

            // Add to allObjects for UI display
            state.allObjects.push(newObj);

            created++;
        } catch (e) {
            failed++;
            console.error('Failed to stage creation:', group.missingName, e);
        }
    }

    // Refresh UI
    Explorer.saveStagedChanges();
    Explorer.updateCommitUI();
    Explorer.buildTree();
    Explorer.invalidateOrphanCache();
    Explorer.computeStagedIssues();
    loadIssues();

    if (failed === 0) {
        showToast(`Staged ${created} new object${created !== 1 ? 's' : ''} for creation`, 'success');
    } else {
        showToast(`Staged ${created} objects, ${failed} failed`, 'warning');
    }
}

/**
 * Build default attributes for a new object based on type
 */
function buildDefaultAttributes(objectType, objectName, isTemplate) {
    const nameFields = {
        'host': 'host_name',
        'service': 'service_description',
        'contact': 'contact_name',
        'contactgroup': 'contactgroup_name',
        'hostgroup': 'hostgroup_name',
        'servicegroup': 'servicegroup_name',
        'command': 'command_name',
        'timeperiod': 'timeperiod_name'
    };

    const nameField = isTemplate ? 'name' : (nameFields[objectType] || 'name');
    const attributes = {};
    attributes[nameField] = objectName;

    if (isTemplate) {
        attributes.register = '0';
    }

    // Add common required attributes based on type
    if (objectType === 'command') {
        attributes.command_line = '/usr/lib/nagios/plugins/check_dummy 0 "OK"';
    } else if (objectType === 'timeperiod') {
        attributes.alias = objectName;
    } else if (objectType === 'host' && !isTemplate) {
        attributes.alias = objectName;
        attributes.address = '127.0.0.1';
    } else if (objectType === 'contact') {
        attributes.alias = objectName;
    } else if (objectType === 'hostgroup' || objectType === 'servicegroup' || objectType === 'contactgroup') {
        attributes.alias = objectName;
    }

    return attributes;
}

function getIssueResolveInfo(issue) {
    // Map issue types to the object type that needs to be created
    // Patterns must match the actual error messages from the backend
    const resolveMap = {
        'missing_template': { objectType: 'template', pattern: /undefined \w+ template[:\s]+(.+)$/i },
        'missing_command': { objectType: 'command', pattern: /non-existent command[:\s]+(.+)$/i },
        'missing_timeperiod': { objectType: 'timeperiod', pattern: /non-existent timeperiod[:\s]+(.+)$/i },
        'missing_contact': { objectType: 'contact', pattern: /non-existent contact[:\s]+(.+)$/i },
        'missing_contactgroup': { objectType: 'contactgroup', pattern: /non-existent contact group[:\s]+(.+)$/i },
        'missing_hostgroup': { objectType: 'hostgroup', pattern: /non-existent hostgroup[:\s]+(.+)$/i },
        'missing_servicegroup': { objectType: 'servicegroup', pattern: /non-existent servicegroup[:\s]+(.+)$/i },
        'orphan_service': { objectType: 'host', pattern: /non-existent host[:\s]+(.+)$/i }
    };

    const info = resolveMap[issue.type];
    if (!info) return null;

    // Extract the missing object name from the message
    const match = issue.message.match(info.pattern);
    if (!match) return null;

    return {
        objectType: info.objectType,
        missingName: match[1].trim()
    };
}

function openCreateObjectForIssue(objectType, objectName, targetFile, issue) {
    // Determine if this should be a template (for missing_template issues)
    const isTemplate = issue.type === 'missing_template';

    // Get the name field for this object type
    const nameFields = {
        'host': 'host_name',
        'service': 'service_description',
        'contact': 'contact_name',
        'contactgroup': 'contactgroup_name',
        'hostgroup': 'hostgroup_name',
        'servicegroup': 'servicegroup_name',
        'command': 'command_name',
        'timeperiod': 'timeperiod_name'
    };

    // For templates, the name field is 'name' and we need to set register=0
    const nameField = isTemplate ? 'name' : (nameFields[objectType] || 'name');

    // Build initial attributes
    const attributes = {};
    attributes[nameField] = objectName;

    if (isTemplate) {
        attributes.register = '0';
        // For templates, we need to determine the actual object type from the referencing object
        // The issue.object_type tells us what type of object is referencing the template
        objectType = issue.object_type;
    }

    // Add common required attributes based on type
    if (objectType === 'command') {
        attributes.command_line = '/usr/lib/nagios/plugins/check_dummy 0 "OK"';
    } else if (objectType === 'timeperiod') {
        attributes.alias = objectName;
    } else if (objectType === 'host' && !isTemplate) {
        attributes.alias = objectName;
        attributes.address = '127.0.0.1';
    } else if (objectType === 'contact') {
        attributes.alias = objectName;
    } else if (objectType === 'hostgroup' || objectType === 'servicegroup' || objectType === 'contactgroup') {
        attributes.alias = objectName;
    }

    // Show dialog to select target file and confirm creation
    showCreateObjectForIssueDialog(objectType, attributes, targetFile, isTemplate);
}

function showCreateObjectForIssueDialog(objectType, attributes, suggestedFile, isTemplate) {
    // A-03: Use shared file options builder
    const fileOptions = buildFileOptionsHtml(suggestedFile);

    const typeLabel = isTemplate ? `${objectType} template` : objectType;
    const nameField = Object.keys(attributes)[0];
    const displayName = attributes[nameField];

    // Build attributes preview
    const attrsHtml = Object.entries(attributes).map(([key, val]) => {
        return `<div class="attr-display-row">
            <span class="attr-display-key">${Explorer.escapeHtml(key)}:</span> ${Explorer.escapeHtml(val)}
        </div>`;
    }).join('');

    Explorer.showDialog(`Create Missing ${typeLabel}`, `
        <p class="u-mb-md dialog-info-text">Create a new ${typeLabel} to resolve this issue.</p>
        <div class="u-mb-md">
            <label class="form-label">Target File</label>
            <select class="form-select" id="resolveTargetFile">
                ${fileOptions}
            </select>
        </div>
        <div class="u-mb-md">
            <label class="form-label">Attributes</label>
            <div class="code-preview">
                ${attrsHtml}
            </div>
            <small class="text-muted">You can edit these after creation.</small>
        </div>
    `, () => {
        const targetFile = document.getElementById('resolveTargetFile').value;
        if (!targetFile) {
            showToast('Please select a target file', 'error');
            return;
        }
        createObjectForIssue(objectType, attributes, targetFile, isTemplate);
    }, 'Create');
}

function createObjectForIssue(objectType, attributes, targetFile, isTemplate) {
    const nameField = Object.keys(attributes)[0];
    const displayName = attributes[nameField];

    Explorer.closeDialog();

    // Create the new object and open it in the editor
    const newObj = {
        object_type: objectType,
        attributes: { ...attributes },
        source_file: targetFile,
        display_name: displayName,
        is_new: true
    };

    // Open in editor so user can modify before staging
    openNewObjectInEditor(newObj, targetFile);

    showToast(`Edit the ${objectType} and save to stage the creation`, 'info');

    // Refresh issues to update the display
    Explorer.computeStagedIssues();
    loadIssues();
}

function navigateToIssue(objectName, objectType) {
    const obj = state.allObjects.find(o =>
        o.object_type === objectType &&
        (o.name === objectName || o.display_name === objectName)
    );
    if (obj) {
        Explorer.navigateToObjectByIndex(obj.global_index);
    }
}

// Export all functions to Explorer namespace
Explorer.analyzeAll = analyzeAll;
Explorer.updateValidationSummary = updateValidationSummary;
Explorer.updateCreatePath = updateCreatePath;
Explorer.switchSuggestionsSubtab = switchSuggestionsSubtab;
Explorer.loadAllSuggestions = loadAllSuggestions;
Explorer.updateSuggestionsBadge = updateSuggestionsBadge;
Explorer.loadTemplateSuggestions = loadTemplateSuggestions;
Explorer.analyzeTemplateConsolidation = analyzeTemplateConsolidation;
Explorer.generateTemplateName = generateTemplateName;
Explorer.filterTemplateSuggestions = filterTemplateSuggestions;
Explorer.getObjectDisplayName = getObjectDisplayName;
Explorer.loadGroupingSuggestions = loadGroupingSuggestions;
Explorer.filterGroupingSuggestions = filterGroupingSuggestions;
Explorer.getConfidenceClass = getConfidenceClass;
Explorer.showCreateTemplateDialog = showCreateTemplateDialog;
Explorer.showCreateGroupDialog = showCreateGroupDialog;
Explorer.loadCleanupSuggestions = loadCleanupSuggestions;
Explorer.analyzeCleanupIssues = analyzeCleanupIssues;
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
Explorer.analyzeNotificationGaps = analyzeNotificationGaps;
Explorer.renderNotificationSuggestions = renderNotificationSuggestions;
Explorer.loadIssues = loadIssues;
Explorer.buildGroupedErrors = buildGroupedErrors;
Explorer.filterIssues = filterIssues;
Explorer.showGroupedErrorDetail = showGroupedErrorDetail;
Explorer.resolveGroupedError = resolveGroupedError;
Explorer.createAllMissing = createAllMissing;
Explorer.executeBatchCreate = executeBatchCreate;
Explorer.buildDefaultAttributes = buildDefaultAttributes;
Explorer.getIssueResolveInfo = getIssueResolveInfo;
Explorer.openCreateObjectForIssue = openCreateObjectForIssue;
Explorer.showCreateObjectForIssueDialog = showCreateObjectForIssueDialog;
Explorer.createObjectForIssue = createObjectForIssue;
Explorer.navigateToIssue = navigateToIssue;

// New unified suggestions list
Explorer.renderUnifiedSuggestionsList = renderUnifiedSuggestionsList;
Explorer.handleSuggestionClick = handleSuggestionClick;
Explorer.handleSuggestionAction = handleSuggestionAction;
Explorer.filterSuggestions = filterSuggestions;
Explorer.bulkDeleteUnused = bulkDeleteUnused;
Explorer.bulkCreateMissing = bulkCreateMissing;

})(Explorer);
