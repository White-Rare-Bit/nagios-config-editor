/** Explorer Dialogs Module - New object creation, deletion, bulk rename, edit attributes, validation */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;

    // ============================================================================
    // New Object Creation
    // ============================================================================

    function createNewObject(targetFile) {
        // Ensure the target folder is expanded so we can see the new object
        state.openTreeFolders.add(targetFile);

        // Clear selection first (update UI but don't hide center pane yet)
        Explorer.clearSelection();
        document.querySelectorAll('.tree-item').forEach(el => {
            el.classList.remove('selected');
        });

        // Create a new object stub with default attributes for the type
        const defaultType = 'host';
        const newObj = {
            object_type: defaultType,
            attributes: {...getDefaultAttributes(defaultType)},
            source_file: targetFile,
            line_number: 999999,
            display_name: '(new object)',
            global_index: -1 // Special index for new objects
        };

        // Set up editing state for new object
        state.editedObject = newObj;
        state.originalAttributes = {};
        state.isNewObject = true;
        state.newObjectStagedIndex = null;

        // Stage immediately so it appears in the tree
        stageNewObjectChanges();

        // Show in center pane with special handling for new objects
        showCenterPaneNewObject(newObj, targetFile);

        // Select the newly created item in the tree and scroll to it
        setTimeout(() => {
            const item = document.querySelector(`[data-staged-index="${state.newObjectStagedIndex}"]`);
            if (item) {
                item.classList.add('selected');
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 50);
    }

    function showCenterPaneNewObject(obj, targetFile) {
        DebugLogger.debug('showCenterPaneNewObject called', {obj, targetFile});
        const fileName = targetFile.split('/').pop();

        // Build object type selector
        const objectTypes = [
            'host', 'hostgroup', 'service', 'servicegroup',
            'contact', 'contactgroup', 'command', 'timeperiod',
            'servicedependency', 'hostdependency', 'serviceescalation', 'hostescalation'
        ];

        // Show center pane first
        const emptyState = document.getElementById('centerEmptyState');
        const content = document.getElementById('centerContent');
        DebugLogger.debug('centerEmptyState and centerContent elements', {
            emptyStateFound: !!emptyState,
            contentFound: !!content
        });

        if (emptyState) {
            emptyState.classList.add('u-hidden');
            emptyState.style.display = 'none';
        }
        if (content) {
            content.classList.remove('u-hidden');
            content.style.display = 'flex';
        }

        const typeEl = document.getElementById('centerCardType');
        DebugLogger.debug('centerCardType element', { found: !!typeEl });

        if (!typeEl) {
            DebugLogger.error('centerCardType not found - DOM may not be ready');
            return;
        }

        // Store object types for dropdown
        window.newObjectTypes = objectTypes;

        typeEl.innerHTML = `
            <div class="new-object-type-container">
                <button type="button" id="newObjectTypeSelect" class="new-object-type-btn" onclick="Explorer.toggleObjectTypeDropdown()">
                    <span id="newObjectTypeValue">${obj.object_type}</span>
                    <span class="dropdown-arrow">▼</span>
                </button>
                <div id="newObjectTypeDropdown" class="object-type-dropdown u-hidden"></div>
            </div>
            <span class="new-object-badge">NEW</span>
        `;
        typeEl.className = 'card-type is-new';

        // Hide issue button for new objects
        const issueBtn = document.getElementById('centerCardIssue');
        if (issueBtn) issueBtn.style.display = 'none';

        // Get the current name from the object
        const nameField = getNewObjectNameField(obj.object_type);
        const currentName = obj.attributes[nameField] || '';

        const nameEl = document.getElementById('centerCardName');
        if (nameEl) {
            nameEl.innerHTML = `
                <input type="text" id="newObjectNameInput" class="new-object-name-input"
                       placeholder="Enter name..." onchange="Explorer.updateNewObjectName()" value="${Explorer.escapeHtml(currentName)}">
            `;
        }

        const fileEl = document.getElementById('centerCardFile');
        if (fileEl) fileEl.textContent = fileName;

        renderCenterAttributes();

        // Load Impact & Relationships section (will show inheritance if use attribute exists)
        Explorer.loadImpactAndRelationships(state.editedObject);

        // Ensure impact section stays collapsed for new objects
        setTimeout(() => {
            const titleEl = document.querySelector('#impactSection .section-title');
            const contentEl = document.getElementById('impactContent');
            if (titleEl) titleEl.classList.add('collapsed');
            if (contentEl) {
                contentEl.classList.add('collapsed');
                contentEl.style.display = 'none';
            }
        }, 0);

        // Show close button for new objects
        document.getElementById('centerCloseBtn').style.display = 'flex';
    }

    function discardNewObject() {
        if (!state.isNewObject) return;

        // Remove from staged creations if it was staged
        if (state.newObjectStagedIndex !== null && state.newObjectStagedIndex < state.stagedCreations.length) {
            state.stagedCreations.splice(state.newObjectStagedIndex, 1);
        }

        // Clear pending hostgroup service link if this was from cleanup
        state.pendingHostgroupServiceLink = null;

        // Clear center pane
        state.editedObject = null;
        state.originalAttributes = null;
        state.isNewObject = false;
        state.newObjectStagedIndex = null;
        Explorer.checkPendingExternalChanges();

        const content = document.getElementById('centerContent');
        const emptyState = document.getElementById('centerEmptyState');
        content.classList.add('u-hidden');
        content.style.display = 'none';
        emptyState.classList.remove('u-hidden');
        emptyState.style.display = 'flex';
        document.getElementById('centerCloseBtn').style.display = 'none';

        // Centralized refresh ensures all UI components stay in sync
        Explorer.saveStagedChanges();
        Explorer.refreshAfterObjectChange();
        showToast('New object discarded', 'info');
    }

    function toggleObjectTypeDropdown() {
        const dropdown = document.getElementById('newObjectTypeDropdown');
        if (!dropdown) return;

        const isOpen = dropdown.style.display !== 'none';

        if (isOpen) {
            dropdown.style.display = 'none';
        } else {
            // Populate dropdown
            const objectTypes = window.newObjectTypes || [];
            const currentType = state.editedObject.object_type;

            dropdown.innerHTML = objectTypes.map(t =>
                `<div class="object-type-dropdown-item${t === currentType ? ' selected' : ''}" onclick="Explorer.selectObjectType('${t}')">${t}</div>`
            ).join('');

            dropdown.style.display = 'block';

            // Close dropdown when clicking outside
            setTimeout(() => {
                document.addEventListener('click', closeObjectTypeDropdownOnClickOutside);
            }, 0);
        }
    }

    function closeObjectTypeDropdownOnClickOutside(event) {
        const dropdown = document.getElementById('newObjectTypeDropdown');
        const btn = document.getElementById('newObjectTypeSelect');
        if (dropdown && btn && !dropdown.contains(event.target) && !btn.contains(event.target)) {
            dropdown.style.display = 'none';
            document.removeEventListener('click', closeObjectTypeDropdownOnClickOutside);
        }
    }

    function selectObjectType(newType) {
        // Close dropdown
        const dropdown = document.getElementById('newObjectTypeDropdown');
        if (dropdown) dropdown.style.display = 'none';
        document.removeEventListener('click', closeObjectTypeDropdownOnClickOutside);

        // Update the button text
        const valueEl = document.getElementById('newObjectTypeValue');
        if (valueEl) valueEl.textContent = newType;

        // Update the object
        updateNewObjectType(newType);
    }

    function updateNewObjectType(newType) {
        const oldType = state.editedObject.object_type;

        // Get the current name value before switching types
        const oldNameField = getNewObjectNameField(oldType);
        const currentName = state.editedObject.attributes[oldNameField] || '';

        // Reset attributes to defaults for the new type
        state.editedObject.attributes = {...getDefaultAttributes(newType)};

        // Preserve the name in the new name field
        const newNameField = getNewObjectNameField(newType);
        if (currentName) {
            state.editedObject.attributes[newNameField] = currentName;
        }

        state.editedObject.object_type = newType;

        // Re-render center pane to show new attributes
        renderCenterAttributes();
        stageNewObjectChanges();
    }

    function updateNewObjectName() {
        const nameInput = document.getElementById('newObjectNameInput');
        const name = nameInput.value.trim();
        const nameField = getNewObjectNameField(state.editedObject.object_type);

        if (name) {
            state.editedObject.attributes[nameField] = name;
            state.editedObject.display_name = name;
        } else {
            delete state.editedObject.attributes[nameField];
            state.editedObject.display_name = '(unnamed)';
        }

        // Re-render attributes to show the updated name field
        renderCenterAttributes();
        stageNewObjectChanges();
    }

    function getNewObjectNameField(objectType) {
        const nameFields = {
            'host': 'host_name',
            'hostgroup': 'hostgroup_name',
            'service': 'service_description',
            'servicegroup': 'servicegroup_name',
            'contact': 'contact_name',
            'contactgroup': 'contactgroup_name',
            'command': 'command_name',
            'timeperiod': 'timeperiod_name',
            'servicedependency': 'service_description',
            'hostdependency': 'host_name',
            'serviceescalation': 'service_description',
            'hostescalation': 'host_name'
        };
        return nameFields[objectType] || 'name';
    }

    function getDefaultAttributes(objectType) {
        // Returns default empty attributes for a new object of the given type
        const defaults = {
            'host': {
                host_name: '',
                alias: '',
                address: '',
                hostgroups: ''
            },
            'service': {
                service_description: '',
                host_name: '',
                check_command: '',
                max_check_attempts: '',
                check_period: '',
                notification_period: '',
                contact_groups: ''
            },
            'hostgroup': {
                hostgroup_name: '',
                alias: ''
            },
            'servicegroup': {
                servicegroup_name: '',
                alias: ''
            },
            'contact': {
                contact_name: '',
                alias: '',
                email: '',
                host_notification_period: '',
                service_notification_period: '',
                host_notification_commands: '',
                service_notification_commands: '',
                host_notification_options: '',
                service_notification_options: ''
            },
            'contactgroup': {
                contactgroup_name: '',
                alias: ''
            },
            'command': {
                command_name: '',
                command_line: ''
            },
            'timeperiod': {
                timeperiod_name: '',
                alias: ''
            },
            'servicedependency': {
                host_name: '',
                service_description: '',
                dependent_host_name: '',
                dependent_service_description: ''
            },
            'hostdependency': {
                host_name: '',
                dependent_host_name: ''
            },
            'serviceescalation': {
                host_name: '',
                service_description: '',
                contact_groups: '',
                first_notification: '',
                last_notification: ''
            },
            'hostescalation': {
                host_name: '',
                contact_groups: '',
                first_notification: '',
                last_notification: ''
            }
        };
        return defaults[objectType] || {};
    }

    function stageNewObjectChanges() {
        if (!state.isNewObject) return;

        const nameField = getNewObjectNameField(state.editedObject.object_type);
        const name = state.editedObject.attributes[nameField] || '';

        const creation = {
            id: generateUniqueId(),
            object_type: state.editedObject.object_type,
            attributes: {...state.editedObject.attributes},
            targetFile: state.editedObject.source_file,
            displayName: name || '(unnamed)'
        };

        if (state.newObjectStagedIndex !== null) {
            // Update existing staged creation
            state.stagedCreations[state.newObjectStagedIndex] = creation;
        } else {
            // Add new staged creation
            state.stagedCreations.push(creation);
            state.newObjectStagedIndex = state.stagedCreations.length - 1;
        }

        // Handle linked service update for hostgroup creation from cleanup
        handleHostgroupServiceLink();

        // Centralized refresh ensures all UI components stay in sync
        Explorer.saveStagedChanges();
        Explorer.refreshAfterObjectChange();

        // Scroll to and highlight the newly staged item
        setTimeout(() => {
            const item = document.querySelector(`[data-staged-index="${state.newObjectStagedIndex}"]`);
            if (item) {
                // Expand parent folders if collapsed
                let parent = item.parentElement;
                while (parent) {
                    if (parent.classList && parent.classList.contains('tree-children') && parent.style.display === 'none') {
                        parent.style.display = 'block';
                        const toggle = parent.previousElementSibling?.querySelector('.tree-toggle');
                        if (toggle) toggle.textContent = '▼';
                    }
                    parent = parent.parentElement;
                }
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                item.classList.add('highlighted');
                setTimeout(() => item.classList.remove('highlighted'), 2000);
            }
        }, 50);
    }

    // ============================================================================
    // Object Deletion
    // ============================================================================

    /**
     * Find all objects that reference the given object by name
     * Uses proper reference field matching and handles +/! prefixes
     */
    function findDependencies(objectName, objectType = null) {
        const dependencies = [];

        // Helper to strip +/! prefixes from Nagios additive/exclusion syntax
        const stripPrefix = v => v.trim().replace(/^[+!]+/, '').trim();

        for (const obj of state.allObjects) {
            let foundInFields = [];
            for (const [key, value] of Object.entries(obj.attributes)) {
                if (!value || typeof value !== 'string') continue;

                // Check each comma-separated value, stripping prefixes
                const values = value.split(',').map(stripPrefix).filter(v => v);
                if (values.includes(objectName)) {
                    foundInFields.push(key);
                }
            }

            if (foundInFields.length > 0) {
                dependencies.push({
                    object: obj,
                    field: foundInFields.join(', '),
                    fields: foundInFields
                });
            }
        }
        return dependencies;
    }

    function checkDependenciesAndDelete(stagedCreationDeletedCount = 0) {
        // Collect all objects being deleted and their dependencies
        const objectsToDelete = [];
        const allDependencies = [];

        for (const index of Explorer.getSelectedIndices()) {
            const obj = state.allObjects.find(o => o.global_index === index);
            if (obj) {
                const objName = obj.display_name;
                const deps = findDependencies(objName);
                // Filter out self-references and objects also being deleted
                const externalDeps = deps.filter(d =>
                    d.object.global_index !== index &&
                    !Explorer.isSelectedByIndex(d.object.global_index)
                );
                if (externalDeps.length > 0) {
                    objectsToDelete.push({ obj, deps: externalDeps });
                    allDependencies.push(...externalDeps);
                }
            }
        }

        if (allDependencies.length > 0) {
            // Show warning dialog
            showDeleteDependencyWarning(objectsToDelete, () => {
                executeObjectDeletions(stagedCreationDeletedCount);
            });
        } else {
            // No dependencies, proceed directly
            executeObjectDeletions(stagedCreationDeletedCount);
        }
    }

    function showDeleteDependencyWarning(objectsWithDeps, onConfirm) {
        const totalDeps = objectsWithDeps.reduce((sum, o) => sum + o.deps.length, 0);

        // Categorize dependencies by impact severity
        const orphanedServices = [];
        const brokenReferences = [];

        for (const { obj, deps } of objectsWithDeps) {
            for (const dep of deps) {
                // Services that lose their host/hostgroup become orphaned
                if (dep.object.object_type === 'service' &&
                    (dep.fields?.includes('host_name') || dep.fields?.includes('hostgroup_name'))) {
                    orphanedServices.push(dep);
                } else {
                    brokenReferences.push(dep);
                }
            }
        }

        let warningHtml = `
            <div class="dialog-warning-box">
                <strong><i class="fa-solid fa-triangle-exclamation"></i> Warning: This deletion will affect other objects</strong>
            </div>
        `;

        // Show orphaned services warning prominently
        if (orphanedServices.length > 0) {
            warningHtml += `
                <div class="dialog-danger-box">
                    <strong><i class="fa-solid fa-exclamation-circle"></i> ${orphanedServices.length} service(s) will become orphaned</strong>
                    <p>These services will have no host/hostgroup and may fail to load:</p>
                    <ul>
            `;
            for (const dep of orphanedServices.slice(0, 5)) {
                warningHtml += `<li>${Explorer.escapeHtml(dep.object.display_name)}</li>`;
            }
            if (orphanedServices.length > 5) {
                warningHtml += `<li class="dialog-detail-more">... and ${orphanedServices.length - 5} more</li>`;
            }
            warningHtml += '</ul></div>';
        }

        // Show other broken references
        warningHtml += '<div class="dialog-scrollable-list">';

        for (const { obj, deps } of objectsWithDeps) {
            const nonOrphanDeps = deps.filter(d =>
                !(d.object.object_type === 'service' &&
                  (d.fields?.includes('host_name') || d.fields?.includes('hostgroup_name')))
            );

            if (nonOrphanDeps.length === 0) continue;

            warningHtml += `
                <div class="dialog-detail-item">
                    <strong>${Explorer.escapeHtml(obj.object_type)}: ${Explorer.escapeHtml(obj.display_name)}</strong>
                    <ul>
            `;
            for (const dep of nonOrphanDeps.slice(0, 5)) {
                warningHtml += `<li>${Explorer.escapeHtml(dep.object.object_type)} "${Explorer.escapeHtml(dep.object.display_name)}" (${Explorer.escapeHtml(dep.field)})</li>`;
            }
            if (nonOrphanDeps.length > 5) {
                warningHtml += `<li class="dialog-detail-more">... and ${nonOrphanDeps.length - 5} more</li>`;
            }
            warningHtml += '</ul></div>';
        }

        warningHtml += `
            </div>
            <div class="u-mt-lg dialog-info-text">
                <p><strong>Total impact:</strong> ${totalDeps} object(s) will have broken references.</p>
                <p>Nagios may fail to start if these references are not fixed.</p>
            </div>
        `;

        document.getElementById('dialogTitle').textContent = 'Confirm Deletion';
        document.getElementById('dialogBody').innerHTML = warningHtml;
        document.getElementById('dialog').style.width = '550px';
        document.getElementById('dialog').style.maxWidth = '90vw';

        // Reset confirm button text and handler
        const confirmBtn = document.querySelector('#dialog .dialog-footer button:last-child');
        if (confirmBtn) {
            confirmBtn.textContent = 'Delete Anyway';
            confirmBtn.classList.add('btn-danger');
            confirmBtn.onclick = () => {
                closeDialog();
                onConfirm();
            };
        }

        document.getElementById('dialogOverlay').classList.add('visible');
    }

    function stageObjectDeletions() {
        // Handle both regular objects and staged creations
        let stagedCreationDeletedCount = 0;

        // Delete staged creations (remove them entirely since they don't exist yet)
        if (state.selectedStagedIndices.size > 0) {
            // Sort in reverse order so we can splice without index shifting issues
            const sortedIndices = Array.from(state.selectedStagedIndices).sort((a, b) => b - a);
            for (const idx of sortedIndices) {
                state.stagedCreations.splice(idx, 1);
                stagedCreationDeletedCount++;
            }
            // Reset state.newObjectStagedIndex if it was deleted
            if (state.selectedStagedIndices.has(state.newObjectStagedIndex)) {
                state.newObjectStagedIndex = null;
                state.isNewObject = false;
                state.editedObject = null;
                Explorer.checkPendingExternalChanges();
            }
            state.selectedStagedIndices.clear();
        }

        // Check for dependencies before deleting regular objects
        if (state.selectedKeys.size > 0) {
            checkDependenciesAndDelete(stagedCreationDeletedCount);
        } else if (stagedCreationDeletedCount > 0) {
            // Only staged creations were deleted
            // Centralized refresh ensures all UI components (tree, target, suggestions, commit) stay in sync
            Explorer.saveStagedChanges();
            Explorer.refreshAfterObjectChange();
            showToast(`Removed ${stagedCreationDeletedCount} staged creation(s)`, 'success');
        }
    }

    function executeObjectDeletions(stagedCreationDeletedCount = 0) {
        let deletedCount = 0;

        // Stage regular objects for deletion
        for (const index of Explorer.getSelectedIndices()) {
            if (!state.stagedObjectDeletions.has(index)) {
                state.stagedObjectDeletions.add(index);
                // Remove any pending edits for this object since it's being deleted
                state.pendingEdits.delete(index);
                // Remove any staged moves for this object (use stable key)
                const obj = state.allObjects.find(o => o.global_index === index);
                if (obj) {
                    state.stagedMoves.delete(Explorer.getObjectKey(obj));
                }
                deletedCount++;
            }
        }

        // Clear selection and hide center pane
        Explorer.clearSelection();
        Explorer.hideCenterPaneObject();

        // Centralized refresh ensures all UI components (tree, target, suggestions, commit) stay in sync
        Explorer.saveStagedChanges();
        Explorer.refreshAfterObjectChange();

        // Show appropriate message
        const totalDeleted = deletedCount + stagedCreationDeletedCount;
        if (stagedCreationDeletedCount > 0 && deletedCount > 0) {
            showToast(`Staged ${deletedCount} object(s) for deletion, removed ${stagedCreationDeletedCount} staged creation(s)`, 'success');
        } else if (deletedCount > 0) {
            showToast(`Staged ${deletedCount} object(s) for deletion`, 'success');
        }
    }

    function unstageObjectDeletion(index) {
        state.stagedObjectDeletions.delete(index);
        // Centralized refresh ensures all UI components stay in sync
        Explorer.saveStagedChanges();
        Explorer.refreshAfterObjectChange();
    }

    // ============================================================================
    // Bulk Operations Dialogs
    // ============================================================================

    function showBulkRenameDialog() {
        hideContextMenu();
        closeActionsMenu();
        if (state.selectedKeys.size === 0) {
            showToast('Please select objects first', 'warning');
            return;
        }

        showDialog('Bulk Rename', `
            <label>Find</label>
            <input type="text" id="renameFind" placeholder="Text to find...">
            <label>Replace with</label>
            <input type="text" id="renameReplace" placeholder="Replacement text...">
        `, () => {
            const find = document.getElementById('renameFind').value;
            const replace = document.getElementById('renameReplace').value;

            if (!find) {
                showToast('Please enter text to find', 'warning');
                return;
            }

            let renamedCount = 0;
            let centerPaneNeedsRefresh = false;

            for (const idx of Explorer.getSelectedIndices()) {
                const obj = state.allObjects.find(o => o.global_index === idx);
                if (!obj) continue;

                const nameField = Explorer.getNameFieldForObject(obj);
                // Use pending edit's current name if available
                const existingEdit = state.pendingEdits.get(idx);
                const currentName = existingEdit ? (existingEdit.edited[nameField] || '') : (obj.attributes[nameField] || '');
                const newName = currentName.split(find).join(replace);

                if (newName !== currentName) {
                    const originalAttrs = existingEdit ? existingEdit.original : {...obj.attributes};
                    const editedAttrs = existingEdit ? {...existingEdit.edited} : {...obj.attributes};
                    editedAttrs[nameField] = newName;

                    state.pendingEdits.set(idx, {
                        original: originalAttrs,
                        edited: editedAttrs,
                        object: {
                            source_file: obj.source_file,
                            line_number: obj.line_number,
                            object_type: obj.object_type,
                            name: obj.name,
                            display_name: obj.display_name
                        }
                    });
                    renamedCount++;

                    // Check if this is the currently displayed object
                    if (state.editedObject && state.editedObject.global_index === idx) {
                        centerPaneNeedsRefresh = true;
                    }
                }
            }

            // Centralized refresh ensures all UI components stay in sync
            Explorer.saveStagedChanges();
            Explorer.invalidateOrphanCache();
            Explorer.computeStagedIssues();
            Explorer.refreshAfterObjectChange();
            closeDialog();

            // Refresh center pane if displayed object was renamed
            if (centerPaneNeedsRefresh && state.editedObject) {
                const obj = state.allObjects.find(o => o.global_index === state.editedObject.global_index);
                if (obj) Explorer.showCenterPaneObject(obj);
            } else if (state.editedObject && renamedCount > 0) {
                // Refresh Impact & Relationships since renames might affect this object
                loadImpactAndRelationships(state.editedObject);
            }

            if (renamedCount > 0) {
                showToast(`Staged ${renamedCount} rename(s). Commit to apply.`, 'info');
            } else {
                showToast('No matches found', 'warning');
            }
        });
    }

    function showEditAttributesDialog() {
        hideContextMenu();
        closeActionsMenu();

        // Collect all unique attribute names from selected objects
        const scope = state.selectedKeys.size > 0 ? Array.from(Explorer.getSelectedIndices()) : state.allObjects.map(o => o.global_index);
        const availableFields = new Set();
        for (const idx of scope) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (!obj) continue;
            const pendingEdit = state.pendingEdits.get(idx);
            const attrs = pendingEdit ? pendingEdit.edited : obj.attributes;
            Object.keys(attrs).forEach(k => availableFields.add(k));
        }
        const sortedFields = [...availableFields].sort();

        showDialog('Edit Attributes', `
            <label>Action</label>
            <select id="editAttrAction" class="dialog-select u-mb-md">
                <option value="findreplace">Find & Replace</option>
                <option value="set">Set value</option>
                <option value="remove">Remove attribute</option>
            </select>
            <label>Attribute</label>
            <div class="autocomplete-wrapper">
                <input type="text" id="editAttrField" placeholder="Select attribute or leave empty for all..." autocomplete="off">
                <div class="autocomplete-suggestions" id="editAttrSuggestions"></div>
            </div>
            <div id="editAttrFindSection">
                <label>Find text</label>
                <input type="text" id="editAttrFind" placeholder="Text to find...">
            </div>
            <div id="editAttrValueSection">
                <label id="editAttrValueLabel">Replace with</label>
                <input type="text" id="editAttrValue" placeholder="Replacement text...">
            </div>
        `, () => {
            const action = document.getElementById('editAttrAction').value;
            const field = document.getElementById('editAttrField').value.trim();
            const findText = document.getElementById('editAttrFind').value;
            const valueText = document.getElementById('editAttrValue').value;

            // Validate field if specified
            if (field && !sortedFields.includes(field)) {
                showToast(`Field "${field}" does not exist in selected objects`, 'warning');
                return;
            }

            if (action === 'findreplace' && !findText) {
                showToast('Please enter text to find', 'warning');
                return;
            }

            if (action === 'set' && !field) {
                showToast('Please select an attribute to set', 'warning');
                return;
            }

            if (action === 'remove' && !field) {
                showToast('Please select an attribute to remove', 'warning');
                return;
            }

            // For 'set' action, validate reference values
            if (action === 'set' && field && valueText) {
                // Get object type(s) from selection to determine valid suggestions
                const objectTypes = [...new Set(scope.map(idx => {
                    const obj = state.allObjects.find(o => o.global_index === idx);
                    return obj?.object_type;
                }).filter(t => t))];

                // Check each object type's suggestions for this field
                for (const objType of objectTypes) {
                    const suggestions = Explorer.getAttributeSuggestions(field, objType);
                    if (suggestions.length > 0) {
                        const values = valueText.split(',').map(v => v.trim()).filter(v => v);
                        const isCommandAttr = ['check_command', 'event_handler', 'host_notification_commands', 'service_notification_commands'].includes(field);

                        for (const v of values) {
                            let checkValue = isCommandAttr ? v.split('!')[0] : v;
                            // Strip +/! prefixes for group membership attributes (additive/exclusion syntax)
                            checkValue = checkValue.replace(/^[+!]+/, '').trim();
                            if (!suggestions.includes(checkValue)) {
                                showToast(`"${checkValue}" does not exist`, 'error');
                                return;
                            }
                        }
                        break; // Only need to validate once
                    }
                }
            }

            let updatedCount = 0;

            for (const idx of scope) {
                const obj = state.allObjects.find(o => o.global_index === idx);
                if (!obj) continue;

                const existingEdit = state.pendingEdits.get(idx);
                const originalAttrs = existingEdit ? existingEdit.original : {...obj.attributes};
                const editedAttrs = existingEdit ? {...existingEdit.edited} : {...obj.attributes};

                let objectChanged = false;

                if (action === 'findreplace') {
                    const fieldsToCheck = field ? [field] : Object.keys(editedAttrs);
                    for (const f of fieldsToCheck) {
                        if (!(f in editedAttrs)) continue;
                        const currentValue = editedAttrs[f] || '';
                        const newValue = currentValue.split(findText).join(valueText);
                        if (newValue !== currentValue) {
                            editedAttrs[f] = newValue;
                            objectChanged = true;
                        }
                    }
                } else if (action === 'set') {
                    if (editedAttrs[field] !== valueText) {
                        editedAttrs[field] = valueText;
                        objectChanged = true;
                    }
                } else if (action === 'remove') {
                    if (field in editedAttrs) {
                        delete editedAttrs[field];
                        objectChanged = true;
                    }
                }

                if (objectChanged) {
                    state.pendingEdits.set(idx, {
                        original: originalAttrs,
                        edited: editedAttrs,
                        object: {
                            source_file: obj.source_file,
                            line_number: obj.line_number,
                            object_type: obj.object_type,
                            name: obj.name,
                            display_name: obj.display_name
                        }
                    });
                    updatedCount++;
                }
            }

            // Centralized refresh ensures all UI components stay in sync
            Explorer.saveStagedChanges();
            Explorer.invalidateOrphanCache();
            Explorer.computeStagedIssues();
            Explorer.refreshAfterObjectChange();
            closeDialog();

            // Refresh center pane if needed
            if (state.editedObject && !state.isNewObject && scope.includes(state.editedObject.global_index)) {
                Explorer.showCenterPaneObject(state.allObjects.find(o => o.global_index === state.editedObject.global_index));
            }

            if (updatedCount > 0) {
                const actionText = action === 'findreplace' ? 'Updated' : (action === 'set' ? 'Set attribute in' : 'Removed attribute from');
                showToast(`${actionText} ${updatedCount} object(s). Commit to apply.`, 'info');
            } else {
                showToast('No changes made', 'warning');
            }
        });

        // Setup after dialog shown
        setTimeout(() => {
            const actionSelect = document.getElementById('editAttrAction');
            const findSection = document.getElementById('editAttrFindSection');
            const valueSection = document.getElementById('editAttrValueSection');
            const valueLabel = document.getElementById('editAttrValueLabel');
            const fieldInput = document.getElementById('editAttrField');
            const suggestionsEl = document.getElementById('editAttrSuggestions');

            function updateUI() {
                const action = actionSelect.value;
                findSection.style.display = action === 'findreplace' ? 'block' : 'none';
                valueSection.style.display = action === 'remove' ? 'none' : 'block';
                valueLabel.textContent = action === 'findreplace' ? 'Replace with' : 'Value';
                fieldInput.placeholder = action === 'findreplace'
                    ? 'Select attribute or leave empty for all...'
                    : 'Select attribute...';
            }

            actionSelect.addEventListener('change', updateUI);
            updateUI();

            fieldInput.focus();

            fieldInput.addEventListener('input', () => {
                const query = fieldInput.value.trim();
                const queryLower = query.toLowerCase();
                const matches = query
                    ? sortedFields.filter(f => f.toLowerCase().includes(queryLower))
                    : sortedFields;

                if (matches.length === 0) {
                    suggestionsEl.innerHTML = '<div class="suggestion-item no-results suggestion-invalid">Not a valid attribute</div>';
                } else {
                    let html = matches.slice(0, 10).map(f =>
                        `<div class="suggestion-item" data-value="${Explorer.escapeHtml(f)}">${Explorer.escapeHtml(f)}</div>`
                    ).join('');
                    if (query && !sortedFields.includes(query)) {
                        html += '<div class="suggestion-item no-results suggestion-invalid suggestion-separator">Not a valid attribute</div>';
                    }
                    suggestionsEl.innerHTML = html;
                }
                suggestionsEl.style.display = 'block';
            });

            fieldInput.addEventListener('focus', () => {
                if (!fieldInput.value.trim()) {
                    suggestionsEl.innerHTML = sortedFields.slice(0, 10).map(f =>
                        `<div class="suggestion-item" data-value="${Explorer.escapeHtml(f)}">${Explorer.escapeHtml(f)}</div>`
                    ).join('');
                    suggestionsEl.style.display = 'block';
                }
            });

            suggestionsEl.addEventListener('click', (e) => {
                const item = e.target.closest('.suggestion-item');
                if (item && item.dataset.value) {
                    fieldInput.value = item.dataset.value;
                    suggestionsEl.style.display = 'none';
                }
            });

            fieldInput.addEventListener('blur', () => {
                setTimeout(() => { suggestionsEl.style.display = 'none'; }, 200);
            });
        }, 100);
    }

    // ============================================================================
    // Selection Helpers
    // ============================================================================

    function selectAllVisible() {
        closeActionsMenu();
        const items = document.querySelectorAll('.tree-item:not([style*="display: none"])');
        items.forEach(item => {
            const idx = parseInt(item.dataset.index);
            if (!isNaN(idx)) selectObjectByIndex(idx);
        });
        Explorer.updateSelection();
        showToast(`Selected ${state.selectedKeys.size} objects`, 'info');
    }

    function selectByType() {
        closeActionsMenu();
        const types = [...new Set(state.allObjects.map(o => o.object_type))].sort();

        showDialog('Select by Type', `
            <label>Object type</label>
            <div class="dialog-type-list">
                ${types.map(t => {
                    const count = state.allObjects.filter(o => o.object_type === t).length;
                    return `<div class="dialog-type-item" data-type="${t}" onclick="Explorer.selectDialogType(this)">
                        <span class="dialog-type-name">${t}</span>
                        <span class="dialog-type-count">${count}</span>
                    </div>`;
                }).join('')}
            </div>
            <input type="hidden" id="selectType" value="${types[0]}">
        `, () => {
            const type = document.getElementById('selectType').value;
            Explorer.clearSelection();
            state.allObjects.filter(o => o.object_type === type).forEach(o => {
                selectObjectByIndex(o.global_index);
            });
            Explorer.updateSelection();
            closeDialog();
            showToast(`Selected ${state.selectedKeys.size} ${type} objects`, 'info');
        });

        // Select first item by default
        setTimeout(() => {
            const firstItem = document.querySelector('.dialog-type-item');
            if (firstItem) firstItem.classList.add('selected');
        }, 0);
    }

    function selectDialogType(el) {
        document.querySelectorAll('.dialog-type-item').forEach(item => item.classList.remove('selected'));
        el.classList.add('selected');
        document.getElementById('selectType').value = el.dataset.type;
    }

    function selectByPattern() {
        closeActionsMenu();

        showDialog('Select by Pattern', `
            <label>Name pattern (regex)</label>
            <input type="text" id="selectPattern" placeholder="e.g., ^web-.*">
        `, () => {
            const pattern = document.getElementById('selectPattern').value;
            if (!pattern) return;

            try {
                const regex = new RegExp(pattern, 'i');
                Explorer.clearSelection();
                state.allObjects.filter(o => regex.test(o.display_name)).forEach(o => {
                    selectObjectByIndex(o.global_index);
                });
                Explorer.updateSelection();
                closeDialog();
                showToast(`Selected ${state.selectedKeys.size} matching objects`, 'info');
            } catch (e) {
                showToast('Invalid regex pattern', 'error');
            }
        });
    }

    // ============================================================================
    // Validation
    // ============================================================================

    async function runValidation() {
        closeActionsMenu();
        switchRightTab('validation');
        runValidationFull();
    }

    async function runValidationFull() {
        const container = document.getElementById('validationContent');
        const badge = document.getElementById('validationBadge');

        container.innerHTML = '<div class="tab-placeholder">Running validation...</div>';

        const response = await ApiClient.post('/api/validate', {}, { silent: true });

        if (!response.success) {
            container.innerHTML = `<div class="tab-placeholder">Error: ${Explorer.escapeHtml(response.error || 'Validation request failed')}</div>`;
            showToast(response.error || 'Validation request failed', 'error');
            return;
        }

        const result = response.data;
        let html = '';

        // F-03: Backend returns 'success' field, not 'valid'
        if (result.success) {
            html += '<div class="validation-status valid">Configuration is valid</div>';
            badge.style.display = 'none';
        } else {
            html += '<div class="validation-status invalid">Configuration is invalid</div>';
            badge.textContent = '!';
            badge.style.display = 'inline-block';
        }

        let output = '';
        if (result.errors && result.errors.length > 0) {
            output += 'ERRORS:\n' + result.errors.join('\n') + '\n\n';
        }
        if (result.warnings && result.warnings.length > 0) {
            output += 'WARNINGS:\n' + result.warnings.join('\n') + '\n\n';
        }
        if (result.raw_output) {
            output += result.raw_output;
        }

        html += `<pre class="validation-output">${Explorer.escapeHtml(output || 'Validation completed successfully.')}</pre>`;

        container.innerHTML = html;

        if (result.valid) {
            showToast('Configuration is valid!', 'success');
        } else {
            showToast(`Validation failed: ${result.errors?.length || 0} errors`, 'error');
        }
    }

    // ============================================================================
    // Commit System
    // ============================================================================

    function updateCommitUI() {
        Explorer.saveStagedChanges();
    }

    function removeStagedCreation(idx) {
        // Check if this is the currently displayed new object
        if (state.isNewObject && state.newObjectStagedIndex === idx) {
            // Clear center pane
            state.editedObject = null;
            state.originalAttributes = null;
            state.isNewObject = false;
            state.newObjectStagedIndex = null;
            Explorer.checkPendingExternalChanges();
            const content = document.getElementById('centerContent');
            const emptyState = document.getElementById('centerEmptyState');
            content.classList.add('u-hidden');
            content.style.display = 'none';
            emptyState.classList.remove('u-hidden');
            emptyState.style.display = 'flex';
        } else if (state.isNewObject && state.newObjectStagedIndex !== null && state.newObjectStagedIndex > idx) {
            // Adjust the index since we're removing an item before it
            state.newObjectStagedIndex--;
        }

        state.stagedCreations.splice(idx, 1);
        Explorer.saveStagedChanges();
        Explorer.refreshAfterObjectChange();
    }

    // ============================================================================
    // Cross-module function delegates (defined in other modules, accessed via Explorer namespace)
    // ============================================================================

    function renderCenterAttributes() {
        Explorer.renderCenterAttributes();
    }

    function handleHostgroupServiceLink() {
        Explorer.handleHostgroupServiceLink();
    }

    function hideContextMenu() {
        Explorer.hideContextMenu();
    }

    function closeActionsMenu() {
        Explorer.closeActionsMenu();
    }

    function showDialog(title, bodyHtml, onConfirm) {
        Explorer.showDialog(title, bodyHtml, onConfirm);
    }

    function closeDialog() {
        Explorer.closeDialog();
    }

    function switchRightTab(tabName) {
        Explorer.switchRightTab(tabName);
    }

    function selectObjectByIndex(index) {
        Explorer.selectObjectByIndex(index);
    }

    function loadImpactAndRelationships(obj) {
        Explorer.loadImpactAndRelationships(obj);
    }

    // ============================================================================
    // Export Functions to Explorer Namespace
    // ============================================================================

    Explorer.createNewObject = createNewObject;
    Explorer.showCenterPaneNewObject = showCenterPaneNewObject;
    Explorer.discardNewObject = discardNewObject;
    Explorer.toggleObjectTypeDropdown = toggleObjectTypeDropdown;
    Explorer.selectObjectType = selectObjectType;
    Explorer.updateNewObjectType = updateNewObjectType;
    Explorer.updateNewObjectName = updateNewObjectName;
    Explorer.getNewObjectNameField = getNewObjectNameField;
    Explorer.getDefaultAttributes = getDefaultAttributes;
    Explorer.stageNewObjectChanges = stageNewObjectChanges;
    Explorer.findDependencies = findDependencies;
    Explorer.checkDependenciesAndDelete = checkDependenciesAndDelete;
    Explorer.showDeleteDependencyWarning = showDeleteDependencyWarning;
    Explorer.stageObjectDeletions = stageObjectDeletions;
    Explorer.executeObjectDeletions = executeObjectDeletions;
    Explorer.unstageObjectDeletion = unstageObjectDeletion;
    Explorer.showBulkRenameDialog = showBulkRenameDialog;
    Explorer.showEditAttributesDialog = showEditAttributesDialog;
    Explorer.selectAllVisible = selectAllVisible;
    Explorer.selectByType = selectByType;
    Explorer.selectDialogType = selectDialogType;
    Explorer.selectByPattern = selectByPattern;
    Explorer.runValidation = runValidation;
    Explorer.runValidationFull = runValidationFull;
    Explorer.updateCommitUI = updateCommitUI;
    Explorer.removeStagedCreation = removeStagedCreation;

})(Explorer);
