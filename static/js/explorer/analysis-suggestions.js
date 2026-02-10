/**
 * Explorer Analysis Module - Template & Grouping Suggestions
 *
 * Functions for template consolidation and hostgroup suggestions:
 * - Template issues (invalid references, unused templates)
 * - Template consolidation suggestions
 * - Hostgroup grouping suggestions
 * - Dialogs for creating templates and groups
 *
 * Dependencies:
 * - window.Explorer (from main.js)
 * - Explorer.state (shared state)
 * - Explorer.escapeHtml (from ui-utils.js)
 * - Explorer.showDialog, Explorer.closeDialog (from dialogs.js)
 * - ApiClient (from api-client.js)
 * - showToast (from base.js)
 * - generateUniqueId (from main.js)
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // ==========================================================================
    // Shared Utilities
    // ==========================================================================

    function getObjectDisplayName(obj) {
        return obj.attributes.host_name || obj.attributes.service_description || obj.attributes.name || obj.attributes.contact_name || `${obj.object_type}@${obj.line_number}`;
    }

    // ==========================================================================
    // Template Issues (Invalid References, Circular Dependencies)
    // ==========================================================================

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

    // ==========================================================================
    // Template Consolidation Suggestions
    // ==========================================================================

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

        // Template suggestions are populated by mapHealthCheckToState from health-check data.
        // If not loaded yet, trigger a health-check fetch.
        if (!state.healthCheckData) {
            try {
                const result = await ApiClient.get('/api/health-check');
                if (result.success) {
                    state.healthCheckData = result.data;
                    Explorer.mapHealthCheckToState(result.data);
                }
            } catch (error) {
                if (container) {
                    container.innerHTML = '<div class="tab-placeholder">Error loading template suggestions.</div>';
                }
                return;
            }
        }

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

    // ==========================================================================
    // Grouping Suggestions (Hostgroups)
    // ==========================================================================

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

    // ==========================================================================
    // Create Dialogs
    // ==========================================================================

    function showCreateTemplateDialog(idx) {
        const suggestion = state.allTemplateSuggestions[idx];

        const configFiles = [...new Set(state.allObjects.map(o => o.source_file))].sort();
        const objectFiles = [...new Set(suggestion.objects.map(o => o.source_file))];
        const defaultFile = configFiles.find(f => f.toLowerCase().includes('template')) ||
                            objectFiles[0] || configFiles[0] || '';

        // Format attributes for display
        const kvPairs = Object.entries(suggestion.attributes).map(([k, v]) => ({ key: k, value: v }));

        Explorer.showDialog('Create Template', `
            <label>Template Name</label>
            <input type="text" id="newTemplateName" value="${Explorer.escapeHtml(suggestion.suggestedName)}">
            ${Explorer.dialogFileSelect('newTemplateFile', 'Target File', defaultFile)}
            <label>Shared Attributes (${Object.keys(suggestion.attributes).length})</label>
            <div class="dialog-scrollable-list dialog-scrollable-list--short">
                ${Explorer.dialogKvList(kvPairs)}
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
            Explorer.renderUnifiedSuggestionsList();
        });
    }

    function showCreateGroupDialog(idx) {
        const suggestion = state.allGroupingSuggestions[idx];

        const configFiles = [...new Set(state.allObjects.map(o => o.source_file))].sort();
        const defaultFile = configFiles.find(f => f.toLowerCase().includes('hostgroup')) ||
                            configFiles.find(f => state.allObjects.some(o => o.source_file === f && o.object_type === 'host')) ||
                            configFiles[0] || '';

        Explorer.showDialog('Create Hostgroup', `
            <label>Group Name</label>
            <input type="text" id="newGroupName" value="${Explorer.escapeHtml(suggestion.name)}">
            ${Explorer.dialogFileSelect('newGroupFile', 'Target File', defaultFile)}
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
            Explorer.renderUnifiedSuggestionsList();
        });
    }

    // ==========================================================================
    // Exports
    // ==========================================================================

    // Template functions
    Explorer.loadTemplateIssues = loadTemplateIssues;
    Explorer.renderTemplateIssues = renderTemplateIssues;
    Explorer.loadTemplateSuggestions = loadTemplateSuggestions;
    Explorer.filterTemplateSuggestions = filterTemplateSuggestions;
    Explorer.showCreateTemplateDialog = showCreateTemplateDialog;

    // Grouping functions
    Explorer.loadGroupingSuggestions = loadGroupingSuggestions;
    Explorer.filterGroupingSuggestions = filterGroupingSuggestions;
    Explorer.getConfidenceClass = getConfidenceClass;
    Explorer.showCreateGroupDialog = showCreateGroupDialog;

    // Shared utilities
    Explorer.getObjectDisplayName = getObjectDisplayName;

})(window.Explorer);
