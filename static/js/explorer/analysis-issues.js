/**
 * Explorer Analysis Module - Issues/Validation
 *
 * Functions for handling validation errors and issue resolution:
 * - Loading and displaying grouped errors
 * - Creating missing objects to resolve errors
 * - Navigating to objects with issues
 *
 * Dependencies:
 * - window.Explorer (from main.js)
 * - Explorer.state (shared state)
 * - Explorer.escapeHtml, Explorer.escapeJs (from ui-utils.js)
 * - Explorer.showDialog, Explorer.closeDialog (from dialogs.js)
 * - Explorer.toggleCleanupSection (from analysis.js)
 * - ApiClient (from api-client.js)
 * - showToast (from base.js)
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // ==========================================================================
    // Issue Loading and Display
    // ==========================================================================

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

        Explorer.updateSuggestionsBadge();
    }

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
                if (typeCompare !== 0) {return typeCompare;}
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
            if (!errorGroups[groupType]) {errorGroups[groupType] = [];}
            errorGroups[groupType].push({ group, idx });
        });

        // Render grouped errors with section headers
        let html = '';
        for (const groupType of groupOrder) {
            if (!errorGroups[groupType] || errorGroups[groupType].length === 0) {continue;}

            const config = groupConfig[groupType] || { icon: '<i class="fa-solid fa-circle-xmark"></i>', label: groupType };
            const items = errorGroups[groupType];

            // Check if this group has resolvable items (can create missing objects)
            const hasResolvableItems = groupType !== 'other' && items.some(({ group }) => group.objectType);
            const createAllBtn = hasResolvableItems
                ? `<button class="nbe-btn nbe-btn--dark nbe-btn--tonal nbe-btn--xs" onclick="event.stopPropagation(); Explorer.createAllMissing('${groupType}')" title="Create all missing ${groupType}s">Create All</button>`
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
                            <button class="nbe-btn nbe-btn--dark nbe-btn--tonal nbe-btn--xs" onclick="event.stopPropagation(); Explorer.resolveGroupedError(${idx})">Create ${group.objectType}</button>
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

    // ==========================================================================
    // Issue Detail and Resolution
    // ==========================================================================

    function showGroupedErrorDetail(idx) {
        const group = state.groupedErrors[idx];
        if (!group) {return;}

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
            ${Explorer.dialogInfoText(`This ${group.objectType} is referenced by ${group.issues.length} object(s) but doesn't exist.`)}
            <p class="u-mb-sm"><strong>Affected objects:</strong></p>
            <div class="dialog-scrollable-list">${objectList}</div>
        `, null);
    }

    function resolveGroupedError(idx) {
        const group = state.groupedErrors[idx];
        if (!group || !group.objectType) {return;}

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
        if (!info) {return null;}

        // Extract the missing object name from the message
        const match = issue.message.match(info.pattern);
        if (!match) {return null;}

        return {
            objectType: info.objectType,
            missingName: match[1].trim()
        };
    }

    // ==========================================================================
    // Batch Creation
    // ==========================================================================

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

        // Default to canonical file for this type, then most common source file, then first file
        const existingFiles = [...new Set(state.allObjects.map(o => o.source_file))].sort();
        const fallbackFile = Object.entries(fileCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || existingFiles[0];
        const defaultFile = preferCanonicalFile(groupType, fallbackFile);

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
            ${Explorer.dialogInfoText(`Create ${matchingGroups.length} missing ${typeLabel} at once.`)}
            ${Explorer.dialogFileSelect('batchCreateTargetFile', 'Target File', defaultFile)}
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

                state.stagedCreations.push(creation);

                // Add to allObjects for UI display
                state.allObjects.push(newObj);

                created++;
            } catch (e) {
                failed++;
                console.error('Failed to stage creation:', group.missingName, e);
            }
        }

        // Refresh UI
        state.healthCheckData = null;
        Explorer.afterFrontendMutation();
        loadIssues();

        if (failed === 0) {
            showToast(`Staged ${created} new object${created !== 1 ? 's' : ''} for creation`, 'success');
        } else {
            showToast(`Staged ${created} objects, ${failed} failed`, 'warning');
        }
    }

    // ==========================================================================
    // Object Creation Helpers
    // ==========================================================================

    /**
     * Prefer a canonical file for a given object type (e.g., hosts.cfg for hosts).
     * Falls back to the provided targetFile if no canonical match exists.
     */
    function preferCanonicalFile(objectType, targetFile) {
        const canonicalNames = {
            host: 'hosts.cfg',
            service: 'services.cfg',
            command: 'commands.cfg',
            contact: 'contacts.cfg',
            contactgroup: 'contactgroups.cfg',
            hostgroup: 'hostgroups.cfg',
            servicegroup: 'servicegroups.cfg',
            timeperiod: 'timeperiods.cfg',
        };
        const canonical = canonicalNames[objectType];
        if (!canonical) {return targetFile;}

        // Check if a file with the canonical name exists
        const match = state.allObjects.find(o => o.source_file.endsWith('/' + canonical));
        return match ? match.source_file : targetFile;
    }

    /**
     * Build default attributes for a new object based on type
     */
    function buildDefaultAttributes(objectType, objectName, isTemplate) {
        const nameField = isTemplate ? 'name' : (Explorer.constants.nameFields[objectType] || 'name');
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

    function openCreateObjectForIssue(objectType, objectName, targetFile, issue) {
        // Determine if this should be a template (for missing_template issues)
        const isTemplate = issue.type === 'missing_template';

        // For templates, use the referencing object's type instead
        const effectiveType = isTemplate ? issue.object_type : objectType;

        // Prefer a canonical file matching the object type (e.g., hosts.cfg for host)
        const resolvedFile = preferCanonicalFile(effectiveType, targetFile);

        // For templates, the name field is 'name' and we need to set register=0
        const nameField = isTemplate ? 'name' : (Explorer.constants.nameFields[effectiveType] || 'name');

        // Build initial attributes
        const attributes = {};
        attributes[nameField] = objectName;

        if (isTemplate) {
            attributes.register = '0';
        }

        // Add common required attributes based on type
        if (effectiveType === 'command') {
            attributes.command_line = '/usr/lib/nagios/plugins/check_dummy 0 "OK"';
        } else if (effectiveType === 'timeperiod') {
            attributes.alias = objectName;
        } else if (effectiveType === 'host' && !isTemplate) {
            attributes.alias = objectName;
            attributes.address = '127.0.0.1';
        } else if (effectiveType === 'contact') {
            attributes.alias = objectName;
        } else if (effectiveType === 'hostgroup' || effectiveType === 'servicegroup' || effectiveType === 'contactgroup') {
            attributes.alias = objectName;
        }

        // Show dialog to select target file and confirm creation
        showCreateObjectForIssueDialog(effectiveType, attributes, resolvedFile, isTemplate);
    }

    function showCreateObjectForIssueDialog(objectType, attributes, suggestedFile, isTemplate) {
        const typeLabel = isTemplate ? `${objectType} template` : objectType;

        // Build attributes preview
        const kvPairs = Object.entries(attributes).map(([key, val]) => ({ key, value: val }));

        Explorer.showDialog(`Create Missing ${typeLabel}`, `
            ${Explorer.dialogInfoText(`Create a new ${typeLabel} to resolve this issue.`)}
            ${Explorer.dialogFileSelect('resolveTargetFile', 'Target File', suggestedFile)}
            <div class="u-mb-md">
                <label class="form-label">Attributes</label>
                <div class="code-preview">
                    ${Explorer.dialogKvList(kvPairs)}
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
        Explorer.openNewObjectInEditor(newObj, targetFile);

        showToast(`Edit the ${objectType} and save to stage the creation`, 'info');

        // Refresh issues to update the display
        Explorer.computeStagedIssues();
        loadIssues();
    }

    // ==========================================================================
    // Navigation
    // ==========================================================================

    function navigateToIssue(objectName, objectType) {
        const obj = state.allObjects.find(o =>
            o.object_type === objectType &&
            (o.name === objectName || o.display_name === objectName)
        );
        if (obj) {
            Explorer.navigateToObjectByIndex(obj.global_index);
        }
    }

    // ==========================================================================
    // Exports
    // ==========================================================================

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

})(window.Explorer);
