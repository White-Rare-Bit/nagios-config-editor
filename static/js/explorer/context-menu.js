/** Explorer Context Menu Module - Context menus, bulk actions, preview, drag-drop from tree
 *
 * Shadow copy architecture: all mutations go directly to the server via API calls.
 * No local pendingEdits/stagedMoves/stagedCreations — the shadow copy IS the edited state.
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;
    const typeLabels = constants.typeLabels;

    const VIEWPORT_PADDING = 10;

    // C-01: Derive group maps from constants.groupStructure (populated by /api/metadata)
    function getGroupAttrMap() {
        const map = {};
        for (const [groupType, gs] of Object.entries(constants.groupStructure || {})) {
            map[gs.member_type] = gs.member_of_attr;
        }
        return map;
    }

    function getGroupTypeMap() {
        const map = {};
        for (const [groupType, gs] of Object.entries(constants.groupStructure || {})) {
            map[gs.member_type] = groupType;
        }
        return map;
    }

    /**
     * Update a comma-separated reference value, replacing oldName with newName.
     * Preserves Nagios additive (+) and exclusion (!) prefixes.
     */
    function updateReferenceValue(value, oldName, newName) {
        const parts = value.split(',').map(v => v.trim());
        const updatedParts = parts.map(part => {
            const stripped = part.replace(/^[+!]+/, '').trim();
            if (stripped === oldName) {
                const prefix = part.substring(0, part.indexOf(stripped));
                return prefix + newName;
            }
            return part;
        });
        return updatedParts.join(',');
    }

    /**
     * Update references for all objects that reference the old name via API calls.
     * @param {string} oldName - The old name being replaced
     * @param {string} newName - The new name to replace with
     * @param {number} excludeIndex - global_index of the renamed object (to exclude)
     * @returns {Promise<number>} count of objects updated
     */
    async function updateReferencesViaApi(oldName, newName, excludeIndex) {
        const deps = Explorer.findDependencies(oldName);
        let updatedCount = 0;

        for (const dep of deps) {
            const obj = dep.object;
            if (obj.global_index === excludeIndex) {continue;}

            const editedAttrs = {...obj.attributes};
            let changed = false;

            for (const fieldName of dep.fields) {
                const currentValue = editedAttrs[fieldName] || '';
                const updatedValue = updateReferenceValue(currentValue, oldName, newName);
                if (updatedValue !== currentValue) {
                    editedAttrs[fieldName] = updatedValue;
                    changed = true;
                }
            }

            if (changed) {
                const result = await ApiClient.post('/api/objects/update', {
                    stable_key: Explorer.getObjectKey(obj),
                    attributes: editedAttrs
                }, { silent: true });
                if (result.success) {updatedCount++;}
            }
        }

        return updatedCount;
    }

    // Context Menu
    function handleContextMenu(event, index) {
        event.preventDefault();
        event.stopPropagation();

        if (!Explorer.isSelectedByIndex(index)) {
            // If multi-select is active, preserve the selection instead of
            // clearing it and navigating to the right-clicked item (Bug 031)
            if (state.selectedKeys.size > 1) {
                // Don't change selection — show context menu for current selection
            } else {
                Explorer.clearSelection();
                Explorer.selectObjectByIndex(index);
                // Update visual highlighting only — don't open a tab on right-click
                state.isTabSwitch = true;
                Explorer.updateSelection();
                state.isTabSwitch = false;
            }
        }

        state.contextTarget = index;
        const menu = document.getElementById('contextMenu');

        // Check if multiple types are selected
        const selectedTypes = new Set(
            Array.from(Explorer.getSelectedIndices())
                .map(i => state.allObjects.find(o => o.global_index === i)?.object_type)
                .filter(t => t)
        );
        const hasMixedTypes = selectedTypes.size > 1;

        // Set selection mode class
        menu.classList.remove('single-selection', 'multi-selection', 'mixed-types');
        menu.classList.add(state.selectedKeys.size > 1 ? 'multi-selection' : 'single-selection');
        if (hasMixedTypes) {
            menu.classList.add('mixed-types');
        }

        // Update "Add to group" menu item based on selected types
        const addToGroupItem = document.getElementById('addToGroupMenuItem');
        const gs = Explorer.constants.groupStructure;
        const groupableTypes = gs ? Object.values(gs).map(g => g.member_type) : [];
        const groupableSelected = [...selectedTypes].filter(t => groupableTypes.includes(t));

        if (groupableSelected.length === 0) {
            addToGroupItem.textContent = 'Add to group... (select hosts, services, or contacts)';
            addToGroupItem.classList.add('disabled');
            addToGroupItem.onclick = null;
        } else if (groupableSelected.length > 1 || selectedTypes.size > 1) {
            addToGroupItem.textContent = 'Add to group... (select only one object type)';
            addToGroupItem.classList.add('disabled');
            addToGroupItem.onclick = null;
        } else {
            addToGroupItem.textContent = 'Add to group...';
            addToGroupItem.classList.remove('disabled');
            addToGroupItem.onclick = showAddToGroupDialog;
        }

        // First show to get dimensions, but off-screen
        menu.style.visibility = 'hidden';
        menu.classList.add('visible');

        const menuRect = menu.getBoundingClientRect();
        const viewportHeight = window.innerHeight;
        const viewportWidth = window.innerWidth;

        // Calculate position, adjusting if menu would go off-screen
        let left = event.clientX;
        let top = event.clientY;

        // Check right edge (C-01: use extracted constant)
        if (left + menuRect.width > viewportWidth - VIEWPORT_PADDING) {
            left = viewportWidth - menuRect.width - VIEWPORT_PADDING;
        }

        // Check bottom edge
        if (top + menuRect.height > viewportHeight - VIEWPORT_PADDING) {
            top = viewportHeight - menuRect.height - VIEWPORT_PADDING;
        }

        // Ensure not off left or top
        left = Math.max(VIEWPORT_PADDING, left);
        top = Math.max(VIEWPORT_PADDING, top);

        menu.style.left = left + 'px';
        menu.style.top = top + 'px';
        menu.style.visibility = 'visible';
    }

    function hideContextMenu() {
        const menu = document.getElementById('contextMenu');
        menu.classList.remove('visible', 'single-selection', 'multi-selection', 'staged-context', 'mixed-types');
    }

    function contextAction(action) {
        hideContextMenu();

        if (baseState.isEditingLocked) {
            showToast('Editing is locked by another user', 'warning');
            return;
        }

        function getCurrentName(obj) {
            const nameField = Explorer.getNameFieldForObject(obj);
            return obj.attributes[nameField] || obj.display_name || obj.name || 'unnamed';
        }

        if (action === 'rename') {
            const obj = state.allObjects.find(o => o.global_index === state.contextTarget);
            const currentName = getCurrentName(obj);

            // Count references to this object's current name (exclude self)
            const deps = Explorer.findDependencies(currentName)
                .filter(d => d.object.global_index !== state.contextTarget);
            const refCount = deps.length;

            let refHtml = '';
            if (refCount > 0) {
                refHtml = `
                    <div class="dialog-reference-option u-mt-sm">
                        <label class="commit-reference-label">
                            <input type="checkbox" id="renameUpdateRefs" checked>
                            <span><strong>Update references</strong> (${refCount} reference${refCount !== 1 ? 's' : ''} in other objects)</span>
                        </label>
                    </div>`;
            }

            showDialog('Rename', `
                <label>New name</label>
                <input type="text" id="renameValue" value="${Explorer.escapeHtml(currentName)}">
                ${refHtml}
            `, applyRename);
        } else if (action === 'clone') {
            const obj = state.allObjects.find(o => o.global_index === state.contextTarget);
            const currentName = getCurrentName(obj);
            const currentFile = obj ? obj.source_file : '';
            // Build file options from known files
            const filesFromObjects = state.allObjects.map(o => o.source_file);
            const allFiles = [...new Set([...filesFromObjects, ...state.allFiles])].sort();
            const fileOptions = allFiles.map(f => {
                const displayName = f.split('/').pop();
                const selected = f === currentFile ? ' selected' : '';
                return `<option value="${Explorer.escapeHtml(f)}"${selected}>${Explorer.escapeHtml(displayName)}</option>`;
            }).join('');
            showDialog('Clone', `
                <label>New name</label>
                <input type="text" id="cloneNewName" value="${Explorer.escapeHtml(currentName + '-copy')}">
                <label>Target file</label>
                <select id="cloneTargetFile">${fileOptions}</select>
            `, applyClone);
        } else if (action === 'delete') {
            showBulkAction('delete');
        }
    }

    // Preview
    function showPreview() {
        // Use hovered item if available, otherwise fall back to selected item
        const targetIndex = state.hoveredIndex !== null
            ? state.hoveredIndex
            : Array.from(Explorer.getSelectedIndices())[0];
        const obj = state.allObjects.find(o => o.global_index === targetIndex);
        if (!obj) {return;}

        const attrs = obj.attributes;
        const comments = obj.inline_comments || {};

        let code = `define ${obj.object_type} {\n`;
        for (const [k, v] of Object.entries(attrs)) {
            let line = `    ${k.padEnd(30)} ${v}`;
            if (comments[k]) {
                line += ` ; ${comments[k]}`;
            }
            code += line + '\n';
        }
        code += '}';

        document.getElementById('previewTitle').textContent = `${obj.object_type}: ${obj.display_name}`;
        document.getElementById('previewCode').textContent = code;
        document.getElementById('previewModal').classList.add('visible');
    }

    function closePreview() {
        document.getElementById('previewModal').classList.remove('visible');
    }

    // Dialog
    function showDialog(title, bodyHtml, onConfirm) {
        document.getElementById('dialogTitle').textContent = title;
        document.getElementById('dialogBody').innerHTML = bodyHtml;

        const confirmBtn = document.getElementById('dialogConfirm');
        const cancelBtn = document.querySelector('#dialog .dialog-footer button:first-child');

        if (onConfirm) {
            confirmBtn.onclick = onConfirm;
            confirmBtn.style.display = '';
            // Reset button text based on dialog title
            if (title.includes('Rename')) {
                confirmBtn.textContent = 'Rename';
            } else if (title.includes('Clone')) {
                confirmBtn.textContent = 'Clone';
            } else if (title.includes('Move')) {
                confirmBtn.textContent = 'Move';
            } else if (title.includes('Set Attribute') || title.includes('Add to Group')) {
                confirmBtn.textContent = 'Confirm';
            } else {
                confirmBtn.textContent = 'OK';
            }
            // Reset button classes
            confirmBtn.classList.remove('btn-danger');
            cancelBtn.textContent = 'Cancel';
        } else {
            // No confirm action - hide confirm button and show just Close
            confirmBtn.style.display = 'none';
            cancelBtn.textContent = 'Close';
        }

        const dialogOverlay = document.getElementById('dialogOverlay');
        dialogOverlay.classList.add('visible');

        // Add Escape key handler for dialog
        const escapeHandler = (e) => {
            if (e.key === 'Escape') {
                closeDialog();
            }
        };
        dialogOverlay.addEventListener('keydown', escapeHandler);
        // Store handler reference for cleanup
        dialogOverlay._escapeHandler = escapeHandler;

        // Focus first input and position cursor at end
        setTimeout(() => {
            const input = document.querySelector('#dialogBody input:not([type="hidden"])');
            if (input) {
                input.focus();
                // Move cursor to end of text (only for text-like inputs)
                if (input.type === 'text' || input.type === 'search' || input.type === '' || !input.type) {
                    const len = input.value.length;
                    input.setSelectionRange(len, len);
                }
            }
        }, 100);
    }

    function closeDialog() {
        const dialogOverlay = document.getElementById('dialogOverlay');
        dialogOverlay.classList.remove('visible');
        // Remove Escape key handler
        if (dialogOverlay._escapeHandler) {
            dialogOverlay.removeEventListener('keydown', dialogOverlay._escapeHandler);
            dialogOverlay._escapeHandler = null;
        }
        // Reset dialog styles for next use
        const dialog = document.getElementById('dialog');
        dialog.classList.remove('commit-dialog');
        dialog.style.width = '';
        dialog.style.maxWidth = '';
        // Show default footer
        const footer = dialog.querySelector('.dialog-footer');
        if (footer) {footer.style.display = '';}
        // Reset button states
        const confirmBtn = document.getElementById('dialogConfirm');
        if (confirmBtn) {confirmBtn.style.display = '';}
        const cancelBtn = dialog.querySelector('.dialog-footer button:first-child');
        if (cancelBtn) {cancelBtn.textContent = 'Cancel';}
    }

    // Bulk Actions
    function showBulkAction(action) {
        hideContextMenu();

        if (baseState.isEditingLocked) {
            showToast('Editing is locked by another user', 'warning');
            return;
        }

        if (action === 'delete') {
            // Stage deletions instead of immediate delete
            Explorer.stageObjectDeletions();
        } else if (action === 'move') {
            // J-021: Prioritize type-compatible files in move dialog
            const files = [...new Set(state.allObjects.map(o => o.source_file))];
            const selectedIndices = Array.from(Explorer.getSelectedIndices());
            const selectedTypes = new Set(
                selectedIndices
                    .map(idx => state.allObjects.find(o => o.global_index === idx))
                    .filter(Boolean)
                    .map(o => o.object_type)
            );
            // Find which files contain matching object types
            const fileTypes = new Map();
            for (const obj of state.allObjects) {
                if (!fileTypes.has(obj.source_file)) {
                    fileTypes.set(obj.source_file, new Set());
                }
                fileTypes.get(obj.source_file).add(obj.object_type);
            }
            const isCompatible = (f) => {
                const types = fileTypes.get(f);
                if (!types || types.size === 0) {return true;} // empty files are compatible
                return [...selectedTypes].some(t => types.has(t));
            };
            const compatible = files.filter(f => isCompatible(f)).sort();
            const incompatible = files.filter(f => !isCompatible(f)).sort();
            // Pre-select: first compatible file that isn't the source file
            const sourceFiles = new Set(
                selectedIndices
                    .map(idx => state.allObjects.find(o => o.global_index === idx))
                    .filter(Boolean)
                    .map(o => o.source_file)
            );
            const defaultFile = compatible.find(f => !sourceFiles.has(f)) || compatible[0] || files[0];
            const buildOption = (f, dimmed) => {
                const selected = f === defaultFile ? ' selected' : '';
                const label = f.split('/').pop() + (dimmed ? ' (different types)' : '');
                return `<option value="${f}"${selected}>${label}</option>`;
            };
            const options = [
                ...compatible.map(f => buildOption(f, false)),
                ...(incompatible.length > 0 ? [`<option disabled>───────────</option>`] : []),
                ...incompatible.map(f => buildOption(f, true)),
                `<option value="__new__">+ Create new file...</option>`
            ].join('');
            showDialog('Move to File', `
                <label>Target file</label>
                <select id="moveTarget" onchange="Explorer.toggleNewFileInput()">
                    ${options}
                </select>
                <div id="newFileInputWrapper" class="u-hidden u-mt-md">
                    <label>New filename</label>
                    <input type="text" id="newFileName" placeholder="my-services.cfg">
                </div>
            `, applyMove);
        } else if (action === 'clone') {
            showDialog('Clone Objects', `
                <label>Name suffix</label>
                <input type="text" id="cloneSuffix" value="-copy">
            `, applyBulkClone);
        } else if (action === 'attribute') {
            showDialog('Set Attribute', `
                <label>Attribute name</label>
                <input type="text" id="attrName" placeholder="check_interval">
                <label>Value</label>
                <input type="text" id="attrValue" placeholder="5">
            `, applyBulkAttribute);
        } else if (action === 'group') {
            showDialog('Add to Group', `
                <label>Group name</label>
                <input type="text" id="groupName" placeholder="Enter existing group name">
            `, applyAddToGroup);
        }
    }

    async function applyMove() {
        let targetFile = document.getElementById('moveTarget').value;

        if (targetFile === '__new__') {
            const newFileName = document.getElementById('newFileName').value.trim();
            if (!newFileName) {
                showToast('Please enter a filename', 'warning');
                return;
            }
            const firstObj = state.allObjects.find(o => Explorer.isSelectedByIndex(o.global_index));
            if (firstObj) {
                const dir = firstObj.source_file.substring(0, firstObj.source_file.lastIndexOf('/'));
                targetFile = dir + '/' + (newFileName.endsWith('.cfg') ? newFileName : newFileName + '.cfg');
            } else {
                targetFile = state.configPath + '/' + (newFileName.endsWith('.cfg') ? newFileName : newFileName + '.cfg');
            }
        }

        let moved = 0;
        for (const idx of Explorer.getSelectedIndices()) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (!obj || obj.source_file === targetFile) {continue;}

            const result = await ApiClient.post('/api/objects/move', {
                stable_key: Explorer.getObjectKey(obj),
                target_file: targetFile
            }, { silent: true });

            if (result.success) {
                moved++;
            } else {
                showToast(result.error || `Failed to move ${obj.display_name || obj.name}`, 'error');
            }
        }

        await Explorer.afterFrontendMutation();
        closeDialog();

        if (moved > 0) {
            showToast(`Moved ${moved} object(s) to ${targetFile.split('/').pop()}`, 'success');
        } else {
            showToast('No objects moved', 'info');
        }
    }

    function applyBulkClone() {
        applyClone();
    }

    async function applyRename() {
        const newName = document.getElementById('renameValue').value.trim();
        if (!newName) {
            showToast('Please enter a name', 'warning');
            return;
        }

        const obj = state.allObjects.find(o => o.global_index === state.contextTarget);
        if (!obj) {
            closeDialog();
            return;
        }

        const nameField = Explorer.getNameFieldForObject(obj);
        const currentName = obj.attributes[nameField] || '';

        if (newName === currentName) {
            closeDialog();
            showToast('Name unchanged', 'info');
            return;
        }

        // Update the object's name via API
        const newAttrs = {...obj.attributes, [nameField]: newName};
        const result = await ApiClient.post('/api/objects/update', {
            stable_key: Explorer.getObjectKey(obj),
            attributes: newAttrs
        });

        if (!result.success) {
            showToast(result.error || 'Failed to rename', 'error');
            return;
        }

        // Update references if checkbox is checked
        const updateRefsCheckbox = document.getElementById('renameUpdateRefs');
        const shouldUpdateRefs = updateRefsCheckbox ? updateRefsCheckbox.checked : false;
        let refUpdates = 0;
        if (shouldUpdateRefs) {
            refUpdates = await updateReferencesViaApi(currentName, newName, state.contextTarget);
        }

        state.healthCheckData = null;
        await Explorer.afterFrontendMutation();
        closeDialog();

        // Refresh center pane if this object is currently displayed
        if (state.editedObject && state.editedObject.global_index === state.contextTarget) {
            Explorer.showCenterPaneObject(obj);
        } else if (state.editedObject) {
            Explorer.loadImpactAndRelationships(state.editedObject);
        }

        const refMsg = refUpdates > 0 ? ` Updated ${refUpdates} reference${refUpdates !== 1 ? 's' : ''}.` : '';
        showToast(`Renamed successfully.${refMsg}`, 'success');
    }

    async function applyClone() {
        // Check if this is a single clone (cloneNewName) or bulk clone (cloneSuffix)
        const newNameInput = document.getElementById('cloneNewName');
        const suffixInput = document.getElementById('cloneSuffix');
        const targetFileSelect = document.getElementById('cloneTargetFile');
        const isSingleClone = newNameInput !== null;
        const suffix = suffixInput ? (suffixInput.value || '-copy') : '-copy';

        if (isSingleClone && !newNameInput.value.trim()) {
            showToast('Please enter a name', 'warning');
            return;
        }

        let clonedCount = 0;
        for (const idx of Explorer.getSelectedIndices()) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (!obj) {continue;}

            const nameField = Explorer.getNameFieldForObject(obj);
            const currentName = obj.attributes[nameField] || obj.name || obj.display_name || 'unnamed';
            const newName = isSingleClone ? newNameInput.value.trim() : currentName + suffix;

            const cloneTargetFile = (targetFileSelect && targetFileSelect.value) || obj.source_file;
            const newAttrs = {...obj.attributes, [nameField]: newName};

            const result = await ApiClient.post('/api/objects/create', {
                target_file: cloneTargetFile,
                object_type: obj.object_type,
                attributes: newAttrs
            }, { silent: true });

            if (result.success) {
                clonedCount++;
            } else {
                showToast(result.error || `Failed to clone ${currentName}`, 'error');
                if (isSingleClone) {return;} // Don't close dialog for single clone error
            }
        }

        if (clonedCount === 0) {return;}

        await Explorer.afterFrontendMutation();
        closeDialog();
        showToast(`Cloned ${clonedCount} object(s)`, 'success');
    }

    function toggleNewFileInput() {
        const select = document.getElementById('moveTarget');
        const wrapper = document.getElementById('newFileInputWrapper');
        if (select.value === '__new__') {
            wrapper.style.display = 'block';
            document.getElementById('newFileName').focus();
        } else {
            wrapper.style.display = 'none';
        }
    }

    async function applyBulkAttribute() {
        const name = document.getElementById('bulkAttrName').value.trim();
        const value = document.getElementById('bulkAttrValue').value;
        const action = document.getElementById('bulkAttrAction').value;

        if (!name) {
            showToast('Please enter an attribute name', 'warning');
            return;
        }

        let updatedCount = 0;

        for (const idx of Explorer.getSelectedIndices()) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (!obj) {continue;}

            const newAttrs = {...obj.attributes};
            let madeChange = false;

            if (action === 'remove') {
                if (name in newAttrs) {
                    delete newAttrs[name];
                    madeChange = true;
                }
            } else if (newAttrs[name] !== value) {
                newAttrs[name] = value;
                madeChange = true;
            }

            if (madeChange) {
                const result = await ApiClient.post('/api/objects/update', {
                    stable_key: Explorer.getObjectKey(obj),
                    attributes: newAttrs
                }, { silent: true });
                if (result.success) {updatedCount++;}
            }
        }

        await Explorer.afterFrontendMutation();
        closeDialog();

        if (updatedCount > 0) {
            const actionText = action === 'remove' ? 'removed from' : 'set on';
            showToast(`Attribute ${actionText} ${updatedCount} object(s)`, 'success');
        } else {
            showToast('No changes made', 'info');
        }
    }

    function applyAddToGroup() {
        // C-02: Delegate to consolidated addToGroup implementation
        const groupName = document.getElementById('groupName').value.trim();
        if (!groupName) {return;}
        Explorer.closeDialog();
        addToGroup(groupName);
    }

    function showAddToGroupDialog() {
        hideContextMenu();

        if (baseState.isEditingLocked) {
            showToast('Editing is locked by another user', 'warning');
            return;
        }

        if (state.selectedKeys.size === 0) {
            showToast('No objects selected', 'warning');
            return;
        }

        // Get relevant group names based on selected object types
        const selectedTypes = new Set(
            Array.from(Explorer.getSelectedIndices())
                .map(i => state.allObjects.find(o => o.global_index === i)?.object_type)
                .filter(t => t)
        );

        const groupTypes = [];
        if (selectedTypes.has('host')) {groupTypes.push('hostgroup');}
        if (selectedTypes.has('service')) {groupTypes.push('servicegroup');}
        if (selectedTypes.has('contact')) {groupTypes.push('contactgroup');}

        const groups = state.allObjects
            .filter(o => groupTypes.includes(o.object_type))
            .map(o => o.name || o.display_name)
            .filter(name => name)
            .sort();

        showDialog('Add to Group', `
            <label>Group name</label>
            <div class="autocomplete-wrapper">
                <input type="text" id="groupSearchInput" placeholder="Search groups..." autocomplete="off">
                <div class="autocomplete-suggestions" id="groupSuggestions"></div>
            </div>
            <p class="dialog-hint">Type to search existing groups.</p>
        `, () => {
            const groupName = document.getElementById('groupSearchInput').value.trim();
            if (groupName) {
                addToGroup(groupName);
            } else {
                showToast('Please enter a group name', 'warning');
            }
        });

        // Setup autocomplete after dialog is shown
        setTimeout(() => {
            const input = document.getElementById('groupSearchInput');
            const suggestionsEl = document.getElementById('groupSuggestions');

            input.focus();

            input.addEventListener('input', () => {
                const query = input.value.toLowerCase().trim();
                if (!query) {
                    suggestionsEl.innerHTML = '';
                    suggestionsEl.style.display = 'none';
                    return;
                }

                const matches = groups.filter(g => g.toLowerCase().includes(query)).slice(0, 8);
                if (matches.length === 0) {
                    suggestionsEl.innerHTML = '<div class="suggestion-item no-results">No matching groups</div>';
                } else {
                    suggestionsEl.innerHTML = matches.map(g =>
                        `<div class="suggestion-item" data-value="${Explorer.escapeHtml(g)}">${Explorer.escapeHtml(g)}</div>`
                    ).join('');
                }
                suggestionsEl.style.display = 'block';
            });

            suggestionsEl.addEventListener('click', (e) => {
                const item = e.target.closest('.suggestion-item');
                if (item && item.dataset.value) {
                    input.value = item.dataset.value;
                    suggestionsEl.style.display = 'none';
                }
            });

            // Hide suggestions when clicking outside
            input.addEventListener('blur', () => {
                setTimeout(() => { suggestionsEl.style.display = 'none'; }, 200);
            });
        }, 100);
    }

    /**
     * Open the selected object in the Graph view
     */
    function viewInGraph() {
        hideContextMenu();

        // Get the first selected object
        const selectedIndices = Array.from(Explorer.getSelectedIndices());
        if (selectedIndices.length === 0) {
            showToast('No object selected', 'warning');
            return;
        }

        const obj = state.allObjects.find(o => o.global_index === selectedIndices[0]);
        if (!obj) {
            showToast('Object not found', 'error');
            return;
        }

        // Build node ID in format expected by Graph page
        // Services use "service:{host}:{service_description}", others use "type:name"
        let nodeId;
        if (obj.object_type === 'service') {
            const target = obj.attributes?.hostgroup_name || obj.attributes?.host_name || '';
            // Clean up target: strip whitespace, remove '+' prefix, filter '!' exclusions
            const cleanTarget = target.split(',')
                .map(t => t.trim().replace(/^\+/, '').trim())
                .filter(t => !t.startsWith('!'))
                .join(',');
            const serviceName = obj.attributes?.service_description || obj.name || '';
            nodeId = cleanTarget ? `service:${cleanTarget}:${serviceName}` : `service:${serviceName}`;
        } else {
            nodeId = `${obj.object_type}:${obj.name || ''}`;
        }

        // Build URL with query params (expand=true to show connections)
        const params = new URLSearchParams({
            node: nodeId,
            expand: 'true'
        });

        // Navigate to graph page with object info
        window.location.href = `/dependencies?${params.toString()}`;
    }

    async function addToGroup(groupName) {
        Explorer.hideContextMenu();
        Explorer.closeDialog();

        if (!groupName) {
            showToast('Invalid group name', 'error');
            return;
        }

        const eligibleObjects = Array.from(Explorer.getSelectedIndices())
            .map(i => state.allObjects.find(o => o.global_index === i))
            .filter(o => o && getGroupAttrMap()[o.object_type]);

        if (eligibleObjects.length === 0) {
            showToast('Please select hosts, services, or contacts', 'warning');
            return;
        }

        let updatedCount = 0;
        for (const obj of eligibleObjects) {
            const groupAttr = getGroupAttrMap()[obj.object_type];
            const currentGroups = (obj.attributes[groupAttr] || '').split(',').map(g => g.trim()).filter(g => g);

            if (!currentGroups.includes(groupName)) {
                currentGroups.push(groupName);
                const newAttrs = {...obj.attributes, [groupAttr]: currentGroups.join(',')};

                const result = await ApiClient.post('/api/objects/update', {
                    stable_key: Explorer.getObjectKey(obj),
                    attributes: newAttrs
                }, { silent: true });
                if (result.success) {updatedCount++;}
            }
        }

        await Explorer.afterFrontendMutation();

        // Refresh center pane if the displayed object was updated
        if (state.editedObject) {
            Explorer.showCenterPaneObject(state.editedObject);
        }

        if (updatedCount > 0) {
            showToast(`Added "${groupName}" to ${updatedCount} object(s)`, 'success');
        } else {
            showToast(`Selected objects already belong to "${groupName}"`, 'info');
        }
    }

    // Drag and Drop

    function handleDragStart(event, index) {
        // If clicking on unselected item, select just that one
        // IMPORTANT: Don't call updateSelection() here - it causes layout changes
        // (border-left: 3px solid on .selected) that make Chrome cancel the drag
        if (!Explorer.isSelectedByIndex(index)) {
            Explorer.clearSelection();
            Explorer.selectObjectByIndex(index);
        }

        // SIMPLE: Get selected objects by their stable keys, then look them up fresh
        // The key (source_file|object_type|name) never changes, so this is always correct
        const dragObjects = Array.from(state.selectedKeys).map(key => {
            const obj = Explorer.findObjectByKey(key);
            if (!obj) {return null;}
            return {
                source_file: obj.source_file,
                object_type: obj.object_type,
                name: obj.name,
                display_name: obj.display_name,
                attributes: { ...obj.attributes }
            };
        }).filter(Boolean);

        const dragData = JSON.stringify({
            type: 'objects',
            objects: dragObjects
        });
        event.dataTransfer.setData('text/plain', dragData);
        event.dataTransfer.setData('application/json', dragData);

        // Set effectAllowed for Chrome compatibility
        event.dataTransfer.effectAllowed = 'move';

        // Find the actual tree item element and mark it as dragging
        const treeItem = event.target.closest('.tree-item');
        if (treeItem) {
            treeItem.classList.add('dragging');
        }

        // Create custom drag image with count - position off-screen so it's not visible
        const count = state.selectedKeys.size;
        const dragBadge = document.createElement('div');
        dragBadge.className = 'drag-badge';
        dragBadge.id = 'drag-badge-temp';
        dragBadge.textContent = count;
        dragBadge.style.cssText = `
            position: absolute;
            top: -100px;
            left: -100px;
            width: 32px;
            height: 32px;
            background: var(--nbe-primary, #1976d2);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: 600;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            pointer-events: none;
            z-index: 9999;
        `;
        document.body.appendChild(dragBadge);

        // Set drag image - must happen synchronously in dragstart
        // Offset (0, 0) puts the badge to bottom-right of cursor so number is visible
        try {
            event.dataTransfer.setDragImage(dragBadge, 0, 0);
        } catch (e) {
            // Fallback: some browsers don't support setDragImage
        }

        // Highlight the right pane files area as drop target
        document.body.classList.add('dragging-objects');

        // Switch to Files tab and highlight it
        Explorer.switchRightTab('files');
    }

    function handleDragEnd(event) {
        Explorer.cleanupDragState();
        // Apply visual selection after drag completes (deferred from handleDragStart
        // to avoid layout changes that cancel the drag operation).
        // Use visualOnly to avoid loading impact data with stale source_file —
        // the drop handler's afterFrontendMutation will rebuild the center pane.
        Explorer.updateSelection({ visualOnly: true });
    }

    function handleDragOver(event) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        event.currentTarget.closest('.tree-folder')?.classList.add('drop-target');
    }

    async function handleDrop(event, targetFile) {
        event.preventDefault();
        Explorer.cleanupDragState();

        const dataStr = event.dataTransfer.getData('text/plain');
        if (!dataStr) {return;}

        let data;
        try {
            data = JSON.parse(dataStr);
        } catch (e) {
            return;
        }

        if (data.type !== 'objects' || !data.objects?.length) {return;}

        let moved = 0;
        for (const objData of data.objects) {
            if (!objData?.source_file || objData.source_file === targetFile) {continue;}

            // Find the live object for its stable key
            const nameComponent = objData.name ?? objData.display_name ?? '';
            const objKey = `${objData.source_file}|${objData.object_type}|${nameComponent}`;

            // Move = create in target + delete from source
            const createResult = await ApiClient.post('/api/objects/create', {
                target_file: targetFile,
                object_type: objData.object_type,
                attributes: objData.attributes
            }, { silent: true });

            if (createResult.success) {
                const deleteResult = await ApiClient.post('/api/objects/delete', {
                    stable_key: objKey
                }, { silent: true });
                if (deleteResult.success) {moved++;}
            }
        }

        if (moved > 0) {
            await Explorer.afterFrontendMutation();
            showToast(`Moved ${moved} object(s) to ${targetFile.split('/').pop()}`, 'success');
        }
    }

    // isObjectTemplate is now a shared implementation in constants.js (Explorer.isObjectTemplate)

    // Export all functions
    Explorer.handleContextMenu = handleContextMenu;
    Explorer.hideContextMenu = hideContextMenu;
    Explorer.contextAction = contextAction;
    Explorer.showPreview = showPreview;
    Explorer.closePreview = closePreview;
    Explorer.showDialog = showDialog;
    Explorer.closeDialog = closeDialog;
    Explorer.showBulkAction = showBulkAction;
    Explorer.applyMove = applyMove;
    Explorer.applyBulkClone = applyBulkClone;
    Explorer.applyRename = applyRename;
    Explorer.applyClone = applyClone;
    Explorer.toggleNewFileInput = toggleNewFileInput;
    Explorer.applyBulkAttribute = applyBulkAttribute;
    Explorer.applyAddToGroup = applyAddToGroup;
    Explorer.showAddToGroupDialog = showAddToGroupDialog;
    Explorer.addToGroup = addToGroup;
    Explorer.viewInGraph = viewInGraph;
    Explorer.handleDragStart = handleDragStart;
    Explorer.handleDragEnd = handleDragEnd;
    Explorer.handleDragOver = handleDragOver;
    Explorer.handleDrop = handleDrop;
    Explorer.updateReferencesViaApi = updateReferencesViaApi;
    Explorer.updateReferenceValue = updateReferenceValue;

})(Explorer);
