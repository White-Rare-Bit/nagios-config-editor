/** Explorer Context Menu Module - Context menus, bulk actions, preview, drag-drop from tree */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;
    const typeLabels = constants.typeLabels;

    // C-01: Extracted constants for add-to-group functionality
    const GROUP_ATTR_MAP = { host: 'hostgroups', service: 'servicegroups', contact: 'contactgroups' };
    const GROUP_TYPE_MAP = { host: 'hostgroup', service: 'servicegroup', contact: 'contactgroup' };
    const VIEWPORT_PADDING = 10;

    // Context Menu
    function handleContextMenu(event, index) {
        event.preventDefault();
        event.stopPropagation();

        if (!Explorer.isSelectedByIndex(index)) {
            Explorer.clearSelection();
            Explorer.selectObjectByIndex(index);
            Explorer.updateSelection();
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
        const groupableTypes = ['host', 'service', 'contact'];
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

        // Helper to get current name (respecting pending edits and templates)
        function getCurrentName(obj) {
            const nameField = Explorer.getNameFieldForObject(obj);
            const pendingEdit = state.pendingEdits.get(obj.global_index);
            if (pendingEdit) {
                return pendingEdit.edited[nameField] || obj.display_name || obj.name || 'unnamed';
            }
            return obj.attributes[nameField] || obj.display_name || obj.name || 'unnamed';
        }

        if (action === 'rename') {
            const obj = state.allObjects.find(o => o.global_index === state.contextTarget);
            const currentName = getCurrentName(obj);
            showDialog('Rename', `
                <label>New name</label>
                <input type="text" id="renameValue" value="${Explorer.escapeHtml(currentName)}">
            `, applyRename);
        } else if (action === 'clone') {
            const obj = state.allObjects.find(o => o.global_index === state.contextTarget);
            const currentName = getCurrentName(obj);
            showDialog('Clone', `
                <label>New name</label>
                <input type="text" id="cloneNewName" value="${Explorer.escapeHtml(currentName + '-copy')}">
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
        if (!obj) return;

        // Use pending edit attributes if available
        const pendingEdit = state.pendingEdits.get(obj.global_index);
        const attrs = pendingEdit ? pendingEdit.edited : obj.attributes;

        let code = `define ${obj.object_type} {\n`;
        for (const [k, v] of Object.entries(attrs)) {
            code += `    ${k.padEnd(30)} ${v}\n`;
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
        const cancelBtn = document.querySelector('#dialog .btn-cancel');

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
            const input = document.querySelector('#dialogBody input');
            if (input) {
                input.focus();
                // Move cursor to end of text
                const len = input.value.length;
                input.setSelectionRange(len, len);
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
        if (footer) footer.style.display = '';
        // Reset button states
        const confirmBtn = document.getElementById('dialogConfirm');
        if (confirmBtn) confirmBtn.style.display = '';
        const cancelBtn = dialog.querySelector('.btn-cancel');
        if (cancelBtn) cancelBtn.textContent = 'Cancel';
    }

    // Bulk Actions
    function showBulkAction(action) {
        hideContextMenu();

        if (action === 'delete') {
            // Stage deletions instead of immediate delete
            Explorer.stageObjectDeletions();
        } else if (action === 'move') {
            const files = [...new Set(state.allObjects.map(o => o.source_file))];
            showDialog('Move to File', `
                <label>Target file</label>
                <select id="moveTarget" onchange="Explorer.toggleNewFileInput()">
                    ${files.map(f => `<option value="${f}">${f.split('/').pop()}</option>`).join('')}
                    <option value="__new__">+ Create new file...</option>
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

    function applyMove() {
        let targetFile = document.getElementById('moveTarget').value;

        if (targetFile === '__new__') {
            const newFileName = document.getElementById('newFileName').value.trim();
            if (!newFileName) {
                showToast('Please enter a filename', 'warning');
                return;
            }
            // Construct full path - put in same directory as first selected object
            const firstObj = state.allObjects.find(o => Explorer.isSelectedByIndex(o.global_index));
            if (firstObj) {
                const dir = firstObj.source_file.substring(0, firstObj.source_file.lastIndexOf('/'));
                targetFile = dir + '/' + (newFileName.endsWith('.cfg') ? newFileName : newFileName + '.cfg');
            } else {
                targetFile = state.configPath + '/' + (newFileName.endsWith('.cfg') ? newFileName : newFileName + '.cfg');
            }
        }

        let staged = 0;
        for (const idx of Explorer.getSelectedIndices()) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (obj && obj.source_file !== targetFile) {
                const objKey = Explorer.getObjectKey(obj);
                state.stagedMoves.set(objKey, {
                    targetFile: targetFile,
                    originalFile: obj.source_file,
                    object: {
                        source_file: obj.source_file,
                        object_type: obj.object_type,
                        name: obj.name,
                        display_name: obj.display_name,
                        attributes: obj.attributes
                    }
                });
                staged++;
            }
        }

        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        Explorer.buildTree();
        closeDialog();

        if (staged > 0) {
            showToast(`Staged ${staged} object(s) to move. Commit to apply.`, 'info');
        } else {
            showToast('No objects to move', 'info');
        }
    }

    function applyBulkClone() {
        applyClone();
    }

    function applyRename() {
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
        const existingEdit = state.pendingEdits.get(state.contextTarget);
        const currentName = existingEdit ? (existingEdit.edited[nameField] || '') : (obj.attributes[nameField] || '');

        if (newName === currentName) {
            closeDialog();
            showToast('Name unchanged', 'info');
            return;
        }

        const originalAttrs = existingEdit ? existingEdit.original : {...obj.attributes};
        const editedAttrs = existingEdit ? {...existingEdit.edited} : {...obj.attributes};
        editedAttrs[nameField] = newName;

        state.pendingEdits.set(state.contextTarget, {
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

        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        Explorer.invalidateOrphanCache();
        Explorer.computeStagedIssues();
        Explorer.buildTree();
        Explorer.renderTargetPane();
        closeDialog();

        // Refresh center pane if this object is currently displayed
        if (state.editedObject && state.editedObject.global_index === state.contextTarget) {
            Explorer.showCenterPaneObject(obj);
        } else if (state.editedObject) {
            // Refresh Impact & Relationships even if a different object is displayed
            // since the rename might affect what references it or its inheritance chain
            Explorer.loadImpactAndRelationships(state.editedObject);
        }

        showToast('Rename staged. Commit to apply.', 'info');
    }

    async function applyClone() {
        // Check if this is a single clone (cloneNewName) or bulk clone (cloneSuffix)
        const newNameInput = document.getElementById('cloneNewName');
        const suffixInput = document.getElementById('cloneSuffix');
        const isSingleClone = newNameInput !== null;
        const suffix = suffixInput ? (suffixInput.value || '-copy') : '-copy';

        // Validate single clone has a name
        if (isSingleClone && !newNameInput.value.trim()) {
            showToast('Please enter a name', 'warning');
            return;
        }

        let clonedCount = 0;
        for (const idx of Explorer.getSelectedIndices()) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (!obj) continue;

            const nameField = Explorer.getNameFieldForObject(obj);
            // Use pending edit attributes if available (clone includes staged changes)
            const pendingEdit = state.pendingEdits.get(idx);
            const sourceAttrs = pendingEdit ? pendingEdit.edited : obj.attributes;
            const currentName = sourceAttrs[nameField] || obj.name || obj.display_name || 'unnamed';

            // For single clone, use the full new name from input; for bulk, append suffix
            const newName = isSingleClone ? newNameInput.value.trim() : currentName + suffix;

            // Clone attributes and update name
            const clonedAttrs = {...sourceAttrs};
            clonedAttrs[nameField] = newName;

            // Stage the cloned object - place it right after the source object
            state.stagedCreations.push({
                id: generateUniqueId(),
                object_type: obj.object_type,
                attributes: clonedAttrs,
                targetFile: obj.source_file,
                displayName: newName,
                insertPosition: obj.line_number
            });
            clonedCount++;
        }

        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        Explorer.buildTree();
        Explorer.renderTargetPane();
        closeDialog();
        showToast(`Staged ${clonedCount} cloned object(s). Commit to apply.`, 'info');
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

    function applyBulkAttribute() {
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
            if (!obj) continue;

            const existingEdit = state.pendingEdits.get(idx);
            const originalAttrs = existingEdit ? existingEdit.original : {...obj.attributes};
            const editedAttrs = existingEdit ? {...existingEdit.edited} : {...obj.attributes};

            if (action === 'remove') {
                if (name in editedAttrs) {
                    delete editedAttrs[name];
                    updatedCount++;
                }
            } else {
                // Set value
                if (editedAttrs[name] !== value) {
                    editedAttrs[name] = value;
                    updatedCount++;
                }
            }

            if (updatedCount > 0 || existingEdit) {
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
            }
        }

        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        Explorer.buildTree();
        closeDialog();

        if (updatedCount > 0) {
            const actionText = action === 'remove' ? 'removed from' : 'set on';
            showToast(`Attribute ${actionText} ${updatedCount} object(s). Commit to apply.`, 'info');
        } else {
            showToast('No changes made', 'info');
        }
    }

    function applyAddToGroup() {
        // C-02: Delegate to consolidated addToGroup implementation
        const groupName = document.getElementById('groupName').value.trim();
        if (!groupName) return;
        Explorer.closeDialog();
        addToGroup(groupName);
    }

    function showAddToGroupDialog() {
        hideContextMenu();

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
        if (selectedTypes.has('host')) groupTypes.push('hostgroup');
        if (selectedTypes.has('service')) groupTypes.push('servicegroup');
        if (selectedTypes.has('contact')) groupTypes.push('contactgroup');

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

    function addToGroup(groupName) {
        Explorer.hideContextMenu();
        Explorer.closeDialog();

        if (!groupName) {
            showToast('Invalid group name', 'error');
            return;
        }

        // C-01: Use extracted constants
        // Get selected objects that can have groups
        const eligibleObjects = Array.from(Explorer.getSelectedIndices())
            .map(i => state.allObjects.find(o => o.global_index === i))
            .filter(o => o && GROUP_ATTR_MAP[o.object_type]);

        if (eligibleObjects.length === 0) {
            showToast('Please select hosts, services, or contacts', 'warning');
            return;
        }

        // Validate that the group exists
        const requiredGroupTypes = [...new Set(eligibleObjects.map(o => GROUP_TYPE_MAP[o.object_type]))];
        const existingGroups = state.allObjects
            .filter(o => requiredGroupTypes.includes(o.object_type))
            .map(o => o.name || o.display_name);

        if (!existingGroups.includes(groupName)) {
            showToast(`Group "${groupName}" does not exist`, 'error');
            return;
        }

        // Update each object's group attribute by appending the new group
        let updatedCount = 0;
        for (const obj of eligibleObjects) {
            const groupAttr = GROUP_ATTR_MAP[obj.object_type];
            const existingEdit = state.pendingEdits.get(obj.global_index);
            const originalAttrs = existingEdit ? existingEdit.original : {...obj.attributes};
            const editedAttrs = existingEdit ? {...existingEdit.edited} : {...obj.attributes};

            // Parse existing groups and add new one
            const currentGroups = (editedAttrs[groupAttr] || '').split(',').map(g => g.trim()).filter(g => g);
            if (!currentGroups.includes(groupName)) {
                currentGroups.push(groupName);
                editedAttrs[groupAttr] = currentGroups.join(',');

                state.pendingEdits.set(obj.global_index, {
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

        Explorer.saveStagedChanges();
        Explorer.Explorer.updateCommitUI();
        Explorer.Explorer.buildTree();

        // If the currently displayed object in center panel was updated, refresh it
        if (state.editedObject && state.editedObject.global_index !== -1) {
            const pendingEdit = state.pendingEdits.get(state.editedObject.global_index);
            if (pendingEdit) {
                state.editedObject.attributes = {...pendingEdit.edited};
                Explorer.renderCenterAttributes();
            }
        }

        if (updatedCount > 0) {
            showToast(`Staged adding "${groupName}" to ${updatedCount} object(s). Commit to apply.`, 'info');
        } else {
            showToast(`Selected objects already belong to "${groupName}"`, 'info');
        }
    }

    // Drag and Drop

    function handleDragStart(event, index) {
        // If clicking on unselected item, select just that one
        if (!Explorer.isSelectedByIndex(index)) {
            Explorer.clearSelection();
            Explorer.selectObjectByIndex(index);
            Explorer.updateSelection();
        }

        // SIMPLE: Get selected objects by their stable keys, then look them up fresh
        // The key (source_file|object_type|name) never changes, so this is always correct
        const dragObjects = Array.from(state.selectedKeys).map(key => {
            const obj = Explorer.findObjectByKey(key);
            if (!obj) return null;
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
    }

    function handleDragOver(event) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        event.currentTarget.closest('.tree-folder')?.classList.add('drop-target');
    }

    function handleDrop(event, targetFile) {
        event.preventDefault();

        // Clean up all drag state
        Explorer.cleanupDragState();

        const dataStr = event.dataTransfer.getData('text/plain');
        if (!dataStr) return;

        let data;
        try {
            data = JSON.parse(dataStr);
        } catch (e) {
            return;
        }

        // Handle staged creations being moved
        if (data.type === 'staged-creations') {
            let moved = 0;
            data.indices.forEach(idx => {
                const creation = state.stagedCreations[idx];
                if (creation && creation.targetFile !== targetFile) {
                    creation.targetFile = targetFile;
                    moved++;
                }
            });
            if (moved > 0) {
                Explorer.saveStagedChanges();
                Explorer.buildTree();
                showToast(`Moved ${moved} new object(s) to ${targetFile.split('/').pop()}`, 'info');
            }
            return;
        }

        // Handle regular objects using stable keys
        let staged = 0;

        if (data.type === 'objects' && data.objects && data.objects.length > 0) {
            // Use stable object info directly from drag data
            data.objects.forEach(objData => {
                if (!objData || !objData.source_file) return;

                if (objData.source_file !== targetFile) {
                    // Use same fallback logic as getObjectKey for null-safe key generation
                    const nameComponent = objData.name ?? objData.display_name ?? `idx:${objData.global_index}`;
                    const objKey = `${objData.source_file}|${objData.object_type}|${nameComponent}`;
                    state.stagedMoves.set(objKey, {
                        targetFile: targetFile,
                        originalFile: objData.source_file,
                        object: {
                            source_file: objData.source_file,
                            object_type: objData.object_type,
                            name: objData.name,
                            display_name: objData.display_name || objData.name,
                            attributes: objData.attributes
                        }
                    });
                    staged++;
                }
            });
        }

        if (staged > 0) {
            Explorer.saveStagedChanges();
            showToast(`Staged ${staged} object(s) to move. Use Commit to apply.`, 'info');
            Explorer.updateCommitUI();
            Explorer.buildTree();
        }
    }

    // Target Pane Renderers

    function renderInheritance(chain) {
        const container = document.getElementById('infoPanelContent');

        // Flatten the inheritance chain into an array, from current object to root ancestors
        function flattenChain(node, path = []) {
            path.push(node);
            const parents = node.parents || [];
            if (parents.length > 0) {
                flattenChain(parents[0], path);
            }
            return path;
        }

        // Render nested tree from a flat array (reversed so ancestors first)
        function renderNestedTree(flatArray, idx = 0) {
            if (idx >= flatArray.length) return '';

            const node = flatArray[idx];
            const isCurrent = idx === flatArray.length - 1;
            const isTemplate = node.is_template;
            const isMissing = !!node.error;
            const hasChildren = idx < flatArray.length - 1;
            const connector = idx > 0 ? '<span class="dep-tree-connector">↳</span>' : '';

            let nodeClass = '';
            if (isCurrent) nodeClass = 'current';
            else if (isMissing) nodeClass = 'missing';
            else if (isTemplate) nodeClass = 'template';

            let html = `
                <div class="ref-item ${nodeClass} ${isMissing ? '' : 'ref-item-clickable'}" ${isMissing ? '' : `onclick="Explorer.selectObjectByName('${Explorer.escapeJs(node.name)}')"`}>
                    ${connector}
                    <span class="ref-type-badge type-${state.infoPanelObject.object_type}">${state.infoPanelObject.object_type}</span>
                    <span class="ref-name" title="${Explorer.escapeHtml(node.name)}">${Explorer.escapeHtml(node.name)}</span>
                    ${isTemplate ? '<span class="template-marker">template</span>' : ''}
                    ${isCurrent ? '<span class="current-marker">current</span>' : ''}
                    ${isMissing ? `<span class="error-marker"><i class="fa-solid fa-xmark"></i> ${Explorer.escapeHtml(node.error)}</span>` : ''}
                </div>
            `;

            // Render child (next in chain) nested inside
            if (hasChildren) {
                html += `<div class="inheritance-children">${renderNestedTree(flatArray, idx + 1)}</div>`;
            }

            return html;
        }

        if (!chain || (!chain.parents || chain.parents.length === 0) && !chain.is_template) {
            container.innerHTML = `
                <div class="info-section">
                    <div class="inheritance-tree">
                        <div class="ref-item current">
                            <span class="ref-type-badge type-${state.infoPanelObject.object_type}">${state.infoPanelObject.object_type}</span>
                            <span class="ref-name" title="${Explorer.escapeHtml(chain?.name || state.infoPanelObject.display_name)}">${Explorer.escapeHtml(chain?.name || state.infoPanelObject.display_name)}</span>
                            <span class="current-marker">current</span>
                        </div>
                    </div>
                    <div class="info-empty u-mt-md">No parent templates</div>
                </div>
            `;
        } else {
            // Flatten and reverse to show ancestors at top, current object at bottom
            const flatChain = flattenChain(chain);
            flatChain.reverse();

            container.innerHTML = `
                <div class="info-section">
                    <div class="info-section-title">Inheritance Chain</div>
                    <div class="inheritance-tree">${renderNestedTree(flatChain)}</div>
                </div>
            `;
        }
    }

    function isParentGroupField(field, objType) {
        // Check if this field indicates a parent group relationship
        if (objType === 'hostgroup' && field === 'hostgroup_members') return true;
        if (objType === 'servicegroup' && field === 'servicegroup_members') return true;
        if (objType === 'contactgroup' && field === 'contactgroup_members') return true;
        return false;
    }

    function renderReferences(refs) {
        const container = document.getElementById('infoPanelContent');

        const { outgoing = [], incoming = [] } = refs;

        if (outgoing.length === 0 && incoming.length === 0) {
            container.innerHTML = '<div class="info-empty">No references found</div>';
            return;
        }

        // Friendly field names
        const fieldLabels = {
            'use': 'use', 'host_name': 'host_name', 'hostgroup_name': 'hostgroup_name',
            'hostgroups': 'hostgroups', 'hostgroup_members': 'hostgroup_members',
            'servicegroups': 'servicegroups', 'servicegroup_members': 'servicegroup_members',
            'contactgroup_members': 'contactgroup_members', 'check_command': 'check_command',
            'event_handler': 'event_handler', 'notification_commands': 'notification_commands',
            'check_period': 'check_period', 'notification_period': 'notification_period',
            'contact_groups': 'contact_groups', 'contacts': 'contacts', 'parents': 'parents',
            'members': 'members'
        };

        // Helper to render a single reference item
        const renderRefItem = (r, showAttr = true) => `
            <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${r.object.global_index})">
                <span class="ref-type-badge type-${r.object.object_type}">${r.object.object_type}</span>
                <span class="ref-name" title="${Explorer.escapeHtml(Explorer.getStagedDisplayName(r.object))}">${Explorer.escapeHtml(Explorer.getStagedDisplayName(r.object))}</span>
                ${showAttr && r.field ? `<span class="ref-attr">${fieldLabels[r.field] || r.field}</span>` : ''}
            </div>
        `;

        let html = '';

        // Show outgoing references (USES - what this object references)
        if (outgoing.length > 0) {
            const grouped = Explorer.groupByType(outgoing);
            html += `<div class="info-section">
                <div class="info-section-title">Dependencies</div>`;

            for (const [type, items] of Object.entries(grouped)) {
                html += `
                    <div class="ref-type-group">
                        <div class="ref-type-header">${typeLabels[type] || type}</div>
                        <div class="ref-type-list">
                            ${items.map(r => renderRefItem(r)).join('')}
                        </div>
                    </div>
                `;
            }
            html += `</div>`;
        }

        // Separate parent groups from other incoming references
        const parentGroups = incoming.filter(r => r.isParentGroup);
        const otherRefs = incoming.filter(r => !r.isParentGroup);

        // Show parent groups (BELONGS TO)
        if (parentGroups.length > 0) {
            const grouped = Explorer.groupByType(parentGroups);
            html += `<div class="info-section">
                <div class="info-section-title">Belongs To</div>`;

            for (const [type, items] of Object.entries(grouped)) {
                html += `
                    <div class="ref-type-group">
                        <div class="ref-type-header">${typeLabels[type] || type}</div>
                        <div class="ref-type-list">
                            ${items.map(r => renderRefItem(r, false)).join('')}
                        </div>
                    </div>
                `;
            }
            html += `</div>`;
        }

        // Show other incoming references (Dependents)
        if (otherRefs.length > 0) {
            const grouped = Explorer.groupByType(otherRefs);
            html += `<div class="info-section">
                <div class="info-section-title">Dependents</div>`;

            for (const [type, items] of Object.entries(grouped)) {
                html += `
                    <div class="ref-type-group">
                        <div class="ref-type-header">${typeLabels[type] || type}</div>
                        <div class="ref-type-list">
                            ${items.map(r => renderRefItem(r)).join('')}
                        </div>
                    </div>
                `;
            }
            html += `</div>`;
        }

        container.innerHTML = html;
    }

    // Helper function to detect if an object is a template
    function isObjectTemplate(obj) {
        // Check for register 0 (explicit template marker)
        if (obj.attributes.register === '0') return true;

        // For hosts: has 'name' but no 'host_name'
        if (obj.object_type === 'host') {
            return obj.attributes.name && !obj.attributes.host_name;
        }

        // For services: has 'name' but no 'service_description'
        if (obj.object_type === 'service') {
            return obj.attributes.name && !obj.attributes.service_description;
        }

        // For contacts: has 'name' but no 'contact_name'
        if (obj.object_type === 'contact') {
            return obj.attributes.name && !obj.attributes.contact_name;
        }

        return false;
    }

    // Find all objects that directly use this template
    function findTemplateUsers(templateObj, objType, members) {
        const templateName = templateObj.attributes.name || templateObj.name || templateObj.display_name;

        state.allObjects.filter(o => o.object_type === objType).forEach(other => {
            if (other.global_index === templateObj.global_index) return;

            const uses = (other.attributes.use || '').split(',').map(x => x.trim());
            if (uses.includes(templateName)) {
                const otherIsTemplate = isObjectTemplate(other);
                members.push({
                    object: other,
                    via: 'use',
                    isTemplate: otherIsTemplate
                });
            }
        });
    }

    function renderMembers(members) {
        const container = document.getElementById('infoPanelContent');
        const obj = state.infoPanelObject;
        const objIsTemplate = isObjectTemplate(obj);

        // Section titles based on object type
        const memberSectionLabels = {
            hostgroup: 'Members',
            servicegroup: 'Members',
            contactgroup: 'Members',
            host: objIsTemplate ? 'Inheriting Objects' : 'Services',
            service: 'Inheriting Objects',
            contact: 'Inheriting Objects',
            command: 'Dependents',
            timeperiod: 'Dependents'
        };

        // Helper to render a single member item
        const renderMemberItem = (m, showAttr = true) => `
            <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${m.object.global_index})">
                <span class="ref-type-badge type-${m.object.object_type}">${m.object.object_type}</span>
                <span class="ref-name" title="${Explorer.escapeHtml(Explorer.getStagedDisplayName(m.object))}">${Explorer.escapeHtml(Explorer.getStagedDisplayName(m.object))}</span>
                ${showAttr && m.via ? `<span class="ref-attr">${Explorer.escapeHtml(m.via)}</span>` : ''}
            </div>
        `;

        // Separate different types of members
        const childGroups = members.filter(m => m.isGroup);
        const inheritingTemplates = members.filter(m => m.isTemplate && !m.isGroup);
        const directMembers = members.filter(m => !m.isGroup && !m.isTemplate);

        if (members.length === 0) {
            const label = memberSectionLabels[obj.object_type] || 'Members';
            container.innerHTML = `<div class="info-empty">No ${label.toLowerCase()}</div>`;
            return;
        }

        let html = '';

        // Show child groups first (for hostgroups, etc.)
        if (childGroups.length > 0) {
            const grouped = Explorer.groupByType(childGroups);
            html += `<div class="info-section">
                <div class="info-section-title">Child Groups <span class="member-count">${childGroups.length}</span></div>`;

            for (const [type, items] of Object.entries(grouped)) {
                html += `
                    <div class="ref-type-group">
                        <div class="ref-type-header">${typeLabels[type] || type}</div>
                        <div class="ref-type-list">
                            ${items.map(m => renderMemberItem(m, false)).join('')}
                        </div>
                    </div>
                `;
            }
            html += `</div>`;
        }

        // Show inheriting templates
        if (inheritingTemplates.length > 0) {
            const grouped = Explorer.groupByType(inheritingTemplates);
            html += `<div class="info-section">
                <div class="info-section-title">Inheriting Templates <span class="member-count">${inheritingTemplates.length}</span></div>`;

            for (const [type, items] of Object.entries(grouped)) {
                html += `
                    <div class="ref-type-group">
                        <div class="ref-type-header">${typeLabels[type] || type}</div>
                        <div class="ref-type-list">
                            ${items.map(m => renderMemberItem(m, false)).join('')}
                        </div>
                    </div>
                `;
            }
            html += `</div>`;
        }

        // Show direct members
        if (directMembers.length > 0) {
            const grouped = Explorer.groupByType(directMembers);
            const sectionLabel = memberSectionLabels[obj.object_type] || 'Members';

            html += `<div class="info-section">
                <div class="info-section-title">${sectionLabel} <span class="member-count">${directMembers.length}</span></div>`;

            for (const [type, items] of Object.entries(grouped)) {
                html += `
                    <div class="ref-type-group">
                        <div class="ref-type-header">${typeLabels[type] || type}</div>
                        <div class="ref-type-list">
                            ${items.map(m => renderMemberItem(m)).join('')}
                        </div>
                    </div>
                `;
            }
            html += `</div>`;
        }

        container.innerHTML = html;
    }

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
    Explorer.renderInheritance = renderInheritance;
    Explorer.isParentGroupField = isParentGroupField;
    Explorer.renderReferences = renderReferences;
    Explorer.isObjectTemplate = isObjectTemplate;
    Explorer.findTemplateUsers = findTemplateUsers;
    Explorer.renderMembers = renderMembers;

})(Explorer);
