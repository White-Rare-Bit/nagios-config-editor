/** Explorer File Operations Module - Target pane rendering, file/folder operations, drag-drop in workspace
 *
 * Shadow copy architecture: all mutations go through API endpoints that operate
 * on the shadow copy. No local staging state. After mutation, call
 * Explorer.afterFrontendMutation() to reload data + rebuild UI.
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;
    const toDisplayPath = Explorer.toDisplayPath;
    const toRelativePath = Explorer.toRelativePath;
    const extractFileName = Explorer.extractFileName;

    // Data transfer types for drag-drop operations
    const DATA_TYPES = {
        OBJECTS: 'text/plain',
        FILE_MOVE: 'application/x-file-move',
        FOLDER_MOVE: 'application/x-folder-move'
    };

    // ============================================================================
    // Navigation
    // ============================================================================

    function navigateToObjectByIndex(index) {
        const obj = state.allObjects.find(o => o.global_index === index);
        if (!obj) {return;}

        // Clear any active filters that might hide the object
        const searchInput = document.getElementById('treeSearch');
        const orphansCheckbox = document.getElementById('showOrphansOnly');
        const issuesCheckbox = document.getElementById('showIssuesOnly');

        if (searchInput.value || orphansCheckbox.checked || issuesCheckbox.checked) {
            searchInput.value = '';
            orphansCheckbox.checked = false;
            issuesCheckbox.checked = false;
            Explorer.buildTree();
        }

        // Expand the parent folder based on current view
        const viewBtn = document.querySelector('.view-btn[data-view="file"]');
        const isFileView = viewBtn ? viewBtn.classList.contains('active') : true;

        if (isFileView) {
            const folder = document.querySelector(`.tree-folder[data-file="${obj.source_file}"]`);
            if (folder && !folder.classList.contains('open')) {
                folder.classList.add('open');
            }
        } else {
            const folders = document.querySelectorAll('.tree-folder');
            folders.forEach(folder => {
                const nameEl = folder.querySelector('.tree-folder-name');
                if (nameEl && nameEl.textContent === obj.object_type && !folder.classList.contains('open')) {
                    folder.classList.add('open');
                }
            });
        }

        // Open as tab (handles selection sync and center pane rendering)
        Explorer.openTab(obj);

        // Scroll to item with slight delay to ensure DOM is updated
        setTimeout(() => {
            const item = document.querySelector(`.tree-item[data-index="${index}"]`);
            if (item) {
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                item.classList.add('highlight-pulse');
                setTimeout(() => item.classList.remove('highlight-pulse'), 1500);
            }
        }, 50);
    }

    function selectObjectByName(name) {
        const obj = state.allObjects.find(o => o.name === name || o.display_name === name);
        if (obj) {
            navigateToObjectByIndex(obj.global_index);
        }
    }

    function selectObjectByIndex(index) {
        Explorer.clearSelection();
        Explorer.addToSelectionByIndex(index);
    }

    // ============================================================================
    // Target Pane (Right Side File Browser) - Setup
    // ============================================================================

    state.expandedFiles = new Set();

    function restoreExpandedState() {
        try {
            const savedFiles = localStorage.getItem('nagios_expandedFiles');
            if (savedFiles) {
                const arr = JSON.parse(savedFiles);
                if (Array.isArray(arr)) {
                    state.expandedFiles = new Set(arr);
                }
                localStorage.removeItem('nagios_expandedFiles');
            }
            const savedFolders = localStorage.getItem('nagios_expandedFolders');
            if (savedFolders) {
                const arr = JSON.parse(savedFolders);
                if (Array.isArray(arr)) {
                    state.expandedFolders = new Set(arr);
                }
                localStorage.removeItem('nagios_expandedFolders');
            }
        } catch (e) {
            console.warn('Failed to restore expanded state:', e);
        }

        if (state.expandedFolders.size === 0 && state.configPath) {
            state.expandedFolders.add(state.configPath);
        }
        if (!state.selectedFolder && state.configPath) {
            state.selectedFolder = state.configPath;
        }
    }

    function saveExpandedState() {
        try {
            if (state.expandedFiles.size > 0) {
                localStorage.setItem('nagios_expandedFiles', JSON.stringify([...state.expandedFiles]));
            }
            if (state.expandedFolders.size > 0) {
                localStorage.setItem('nagios_expandedFolders', JSON.stringify([...state.expandedFolders]));
            }
        } catch (e) {
            console.warn('Failed to save expanded state:', e);
        }
    }

    window.addEventListener('beforeunload', saveExpandedState);

    function initTargetPane() {
        restoreExpandedState();
        initWorkspaceToolbar();
        renderTargetPane();
    }

    function initWorkspaceToolbar() {
        const createMenuBtn = document.getElementById('createMenuBtn');
        const collapseAllBtn = document.getElementById('collapseAllBtn');
        const refreshBtn = document.getElementById('refreshBtn');
        const workspaceRootIcon = document.getElementById('workspaceRootIcon');
        const newFileIcon = document.getElementById('newFileIcon');
        const newFolderIcon = document.getElementById('newFolderIcon');

        if (createMenuBtn) {createMenuBtn.innerHTML = Explorer.getIcon('plus');}
        if (collapseAllBtn) {collapseAllBtn.innerHTML = Explorer.getIcon('minimize-2');}
        if (refreshBtn) {refreshBtn.innerHTML = Explorer.getIcon('refresh-cw');}
        if (workspaceRootIcon) {workspaceRootIcon.innerHTML = Explorer.getIcon('folder-open');}
        if (newFileIcon) {newFileIcon.innerHTML = Explorer.getIcon('file-plus');}
        if (newFolderIcon) {newFolderIcon.innerHTML = Explorer.getIcon('folder-plus');}

        document.addEventListener('click', function(event) {
            const dropdown = document.getElementById('createDropdownMenu');
            const btn = document.getElementById('createMenuBtn');
            if (dropdown && btn && !dropdown.contains(event.target) && !btn.contains(event.target)) {
                dropdown.classList.remove('visible');
            }
        });
    }

    function toggleCreateMenu(event) {
        event.stopPropagation();
        const dropdown = document.getElementById('createDropdownMenu');
        if (dropdown) {
            dropdown.classList.toggle('visible');
        }
    }

    function showCreateInput(type) {
        const dropdown = document.getElementById('createDropdownMenu');
        const inlineCreate = document.getElementById('workspaceCreateInline');
        const input = document.getElementById('newItemName');

        if (dropdown) {dropdown.classList.remove('visible');}
        if (inlineCreate) {inlineCreate.classList.add('visible');}
        if (input) {
            input.placeholder = type === 'folder' ? 'foldername/' : 'filename.cfg';
            input.value = '';
            input.focus();
            input.dataset.createType = type;
        }
    }

    function hideCreateInput() {
        const inlineCreate = document.getElementById('workspaceCreateInline');
        if (inlineCreate) {inlineCreate.classList.remove('visible');}
    }

    function handleCreateKeydown(event) {
        if (event.key === 'Enter') {
            createNewItem();
        } else if (event.key === 'Escape') {
            hideCreateInput();
        }
    }

    function collapseAllFolders() {
        state.expandedFolders.clear();
        state.expandedFiles.clear();
        renderTargetPane();
    }

    function refreshWorkspace() {
        Explorer.loadObjects().then(() => {
            renderTargetPane();
        });
    }

    function updateWorkspaceHeader() {
        const rootName = document.getElementById('workspaceRootName');
        const rootMeta = document.getElementById('workspaceRootMeta');
        const configRootName = state.configDisplayName || extractFileName(state.configPath);
        const totalObjects = state.allObjects.length;

        if (rootName) {rootName.textContent = configRootName;}
        if (rootMeta) {rootMeta.textContent = `${totalObjects} object${totalObjects !== 1 ? 's' : ''}`;}
    }

    // ============================================================================
    // Shared Helpers
    // ============================================================================

    function buildRowClasses(base, flags) {
        let classes = base;
        for (const [cls, condition] of flags) {
            if (condition) {classes += ' ' + cls;}
        }
        return classes;
    }

    function addFileToTree(path, ensureFolderPath, props) {
        const parts = path.split('/');
        const filename = parts.pop();
        const dir = parts.join('/') || state.configPath;
        const folder = ensureFolderPath(dir);
        if (!folder.files.some(f => f.path === path)) {
            folder.files.push({ path, name: filename, ...props });
        }
    }

    function buildDeleteButton(path, isFolder) {
        const escaped = Explorer.escapeJs(path);
        if (isFolder) {
            return `<button class="tree-action-btn tree-action-btn--danger" onclick="event.stopPropagation(); Explorer.deleteFolder('${escaped}', event)" title="Delete folder">${Explorer.getIcon('trash-2')}</button>`;
        }
        return `<button class="tree-action-btn tree-action-btn--danger" onclick="event.stopPropagation(); Explorer.deleteFile('${escaped}', event)" title="Delete file">${Explorer.getIcon('trash-2')}</button>`;
    }

    /**
     * Get change status for a file from server diff data.
     * The changedFilesMap uses relative paths, so we convert absolute paths.
     * @returns {string|null} 'added', 'modified', 'deleted', or null
     */
    function getFileChangeStatus(absPath) {
        const rel = toRelativePath(absPath);
        if (!rel) {return null;}
        return state.changedFilesMap.get(rel) || null;
    }

    /**
     * Get aggregate change status for a folder (any file inside changed).
     * @returns {string|null} 'modified' if any file inside changed, null otherwise
     */
    function getFolderChangeStatus(folderPath) {
        const rel = toRelativePath(folderPath);
        if (!rel && folderPath !== state.configPath) {return null;}
        const prefix = rel ? rel + '/' : '';
        for (const [path] of state.changedFilesMap) {
            if (path.startsWith(prefix) || (!prefix && state.changedFilesMap.size > 0)) {
                return 'modified';
            }
        }
        return null;
    }

    /**
     * Build a change indicator badge from server diff status.
     */
    function buildChangeIndicator(status) {
        if (!status) {return '';}
        const labels = { added: 'NEW', modified: 'MOD', deleted: 'DEL' };
        const classes = { added: 'staged-indicator--new', modified: 'staged-indicator--move', deleted: 'staged-indicator--delete' };
        return `<span class="staged-indicator ${classes[status] || ''}" title="${status}">${labels[status] || status.toUpperCase()}</span>`;
    }

    // ============================================================================
    // Target Pane (Right Side File Browser) - Rendering
    // ============================================================================

    function buildFolderTree() {
        const filesFromObjects = state.allObjects.map(o => o.source_file);
        const files = [...new Set([...filesFromObjects, ...state.allFiles])].sort();
        const root = { folders: {}, files: [], path: state.configPath };

        function ensureFolderPath(absPath) {
            if (absPath === state.configPath) {return root;}
            const relativePath = toRelativePath(absPath);
            if (!relativePath) {return root;}

            const parts = relativePath.split('/').filter(p => p);
            let current = root;
            let currentAbsPath = state.configPath;

            for (const part of parts) {
                currentAbsPath += '/' + part;
                if (!current.folders[part]) {
                    current.folders[part] = { folders: {}, files: [], path: currentAbsPath };
                }
                current = current.folders[part];
            }
            return current;
        }

        for (const file of files) {
            const parts = file.split('/');
            const filename = parts.pop();
            const dir = parts.join('/') || state.configPath;
            ensureFolderPath(dir).files.push({ path: file, name: filename });
        }

        for (const folderPath of state.existingFolders) {
            ensureFolderPath(folderPath);
        }

        return root;
    }

    function renderTargetPane() {
        const container = document.getElementById('targetPaneContent');
        updateWorkspaceHeader();

        const root = buildFolderTree();

        function countFolderObjects(folder) {
            let count = folder.files.reduce((sum, f) => {
                return sum + state.allObjects.filter(o => o.source_file === f.path).length;
            }, 0);
            for (const subName of Object.keys(folder.folders)) {
                count += countFolderObjects(folder.folders[subName]);
            }
            return count;
        }

        function renderFolder(folder, name, depth) {
            const isExpanded = state.expandedFolders.has(folder.path);
            const isSelected = state.selectedFolder === folder.path;
            const subfolderNames = Object.keys(folder.folders).sort();
            const hasChildren = subfolderNames.length > 0 || folder.files.length > 0;

            let totalObjects = folder.files.reduce((sum, f) => {
                return sum + state.allObjects.filter(o => o.source_file === f.path).length;
            }, 0);
            for (const subName of subfolderNames) {
                totalObjects += countFolderObjects(folder.folders[subName]);
            }

            const canDrag = folder.path !== state.configPath;
            const canDelete = folder.path !== state.configPath;

            const expandIcon = hasChildren ? Explorer.getIcon('chevron-right') : '';
            const folderIcon = isExpanded ? Explorer.getIcon('folder-open') : Explorer.getIcon('folder');

            const folderStatus = getFolderChangeStatus(folder.path);
            const rowClasses = buildRowClasses('workspace-tree-row', [
                ['expanded', isExpanded], ['selected', isSelected],
                ['staged-new', folderStatus === 'added'], ['staged-move', folderStatus === 'modified']
            ]);

            const actionHtml = canDelete ? buildDeleteButton(folder.path, true) : '';
            const indicatorHtml = buildChangeIndicator(folderStatus);

            let html = `
            <div class="${rowClasses}" data-depth="${depth}" data-folder="${Explorer.escapeHtml(folder.path)}"
                 onclick="Explorer.selectFolder('${Explorer.escapeJs(folder.path)}')"
                 ondragover="Explorer.handleFolderDragOver(event, '${Explorer.escapeJs(folder.path)}')"
                 ondrop="Explorer.handleFolderDrop(event, '${Explorer.escapeJs(folder.path)}')"
                 ondragleave="Explorer.handleFolderDragLeave(event)"
                 draggable="${canDrag ? 'true' : 'false'}"
                 ondragstart="Explorer.handleFolderDragStart(event, '${Explorer.escapeJs(folder.path)}')">
                <button class="tree-expand-btn${isExpanded ? ' expanded' : ''}" onclick="event.stopPropagation(); Explorer.toggleFolderExpand('${Explorer.escapeJs(folder.path)}')">${expandIcon}</button>
                <span class="tree-icon tree-icon--folder${isExpanded ? ' expanded' : ''}">${folderIcon}</span>
                <span class="tree-label tree-label--folder">${Explorer.escapeHtml(name)}</span>
                ${indicatorHtml}
                <span class="tree-count${totalObjects === 0 ? ' tree-count--empty' : ''}">${totalObjects}</span>
                <div class="tree-row-actions">
                    ${actionHtml}
                </div>
            </div>
            <div class="tree-children${isExpanded ? ' expanded with-guides' : ''}">`;

            for (const subName of subfolderNames) {
                html += renderFolder(folder.folders[subName], subName, depth + 1);
            }

            for (const file of folder.files.sort((a, b) => a.name.localeCompare(b.name))) {
                html += renderFileItem(file, depth + 1);
            }

            html += `</div>`;
            return html;
        }

        function renderFileItem(file, depth = 0) {
            const fileObjects = state.allObjects.filter(o => o.source_file === file.path);
            const isExpanded = state.expandedFiles.has(file.path);
            const hasObjects = fileObjects.length > 0;

            const expandIcon = hasObjects ? Explorer.getIcon('chevron-right') : '';
            const fileStatus = getFileChangeStatus(file.path);
            const isNew = fileStatus === 'added';
            const fileIcon = isNew ? Explorer.getIcon('file-plus') : Explorer.getIcon('file-text');

            const rowClasses = buildRowClasses('workspace-tree-row', [
                ['expanded', isExpanded],
                ['staged-new', isNew], ['staged-move', fileStatus === 'modified'],
                ['staged-deletion', fileStatus === 'deleted']
            ]);

            const actionHtml = buildDeleteButton(file.path, false);
            const indicatorHtml = buildChangeIndicator(fileStatus);

            let html = `
            <div class="${rowClasses}" data-depth="${depth}" data-file="${Explorer.escapeHtml(file.path)}"
                 onclick="Explorer.toggleFileExpand('${Explorer.escapeJs(file.path)}')"
                 ondragover="Explorer.handleFileDragOver(event, '${Explorer.escapeJs(file.path)}')"
                 ondrop="Explorer.handleFileDrop(event, '${Explorer.escapeJs(file.path)}')"
                 ondragleave="Explorer.handleFileDragLeave(event)"
                 draggable="true"
                 ondragstart="Explorer.handleFileDragStart(event, '${Explorer.escapeJs(file.path)}')">
                ${hasObjects ? `<button class="tree-expand-btn${isExpanded ? ' expanded' : ''}" onclick="event.stopPropagation(); Explorer.toggleFileExpand('${Explorer.escapeJs(file.path)}')">${expandIcon}</button>` : '<span class="tree-expand-placeholder"></span>'}
                <span class="tree-icon tree-icon--file${isNew ? '-new' : ''}">${fileIcon}</span>
                <span class="tree-label${isNew ? ' tree-label--staged' : ''}${fileStatus === 'deleted' ? ' tree-label--deleted' : ''}">${Explorer.escapeHtml(file.name)}</span>
                ${indicatorHtml}
                <span class="tree-count${fileObjects.length === 0 ? ' tree-count--empty' : ''}">${fileObjects.length}</span>
                <div class="tree-row-actions">
                    ${actionHtml}
                </div>
            </div>
            <div class="tree-children${isExpanded ? ' expanded' : ''}">
                ${renderFileObjects(file.path, fileObjects, depth + 1)}
            </div>`;

            return html;
        }

        // Build the tree HTML
        let html = '';
        const rootFolderNames = Object.keys(root.folders).sort();
        const rootName = state.configDisplayName || extractFileName(state.configPath);
        const isRootExpanded = state.expandedFolders.has(state.configPath);
        const isRootSelected = state.selectedFolder === state.configPath;
        const hasRootChildren = rootFolderNames.length > 0 || root.files.length > 0;

        let totalRootObjects = root.files.reduce((sum, f) => {
            return sum + state.allObjects.filter(o => o.source_file === f.path).length;
        }, 0);
        for (const subName of rootFolderNames) {
            totalRootObjects += countFolderObjects(root.folders[subName]);
        }

        const rootExpandIcon = hasRootChildren ? Explorer.getIcon('chevron-right') : '';
        const rootFolderIcon = isRootExpanded ? Explorer.getIcon('folder-open') : Explorer.getIcon('folder');

        html += `
        <div class="workspace-tree-row workspace-tree-row--root${isRootExpanded ? ' expanded' : ''}${isRootSelected ? ' selected' : ''}" data-depth="0" data-folder="${Explorer.escapeHtml(state.configPath)}"
             onclick="Explorer.selectFolder('${Explorer.escapeJs(state.configPath)}')"
             ondragover="Explorer.handleFolderDragOver(event, '${Explorer.escapeJs(state.configPath)}')"
             ondrop="Explorer.handleFolderDrop(event, '${Explorer.escapeJs(state.configPath)}')"
             ondragleave="Explorer.handleFolderDragLeave(event)">
            <button class="tree-expand-btn${isRootExpanded ? ' expanded' : ''}" onclick="event.stopPropagation(); Explorer.toggleFolderExpand('${Explorer.escapeJs(state.configPath)}')">${rootExpandIcon}</button>
            <span class="tree-icon tree-icon--folder${isRootExpanded ? ' expanded' : ''}">${rootFolderIcon}</span>
            <span class="tree-label tree-label--folder tree-label--root">${Explorer.escapeHtml(rootName)}</span>
            <span class="tree-count">${totalRootObjects}</span>
        </div>
        <div class="tree-children${isRootExpanded ? ' expanded with-guides' : ''}">`;

        if (!hasRootChildren) {
            html += '<div class="workspace-empty-file">No configuration files yet. Click + to create one.</div>';
        } else {
            for (const name of rootFolderNames) {
                html += renderFolder(root.folders[name], name, 1);
            }
            for (const file of root.files.sort((a, b) => a.name.localeCompare(b.name))) {
                html += renderFileItem(file, 1);
            }
        }

        html += '</div>';

        container.innerHTML = html;

        if (Explorer.refreshPanelTiers) {
            Explorer.refreshPanelTiers();
        }
    }

    function toggleFolderExpand(folderPath) {
        if (state.expandedFolders.has(folderPath)) {
            state.expandedFolders.delete(folderPath);
        } else {
            state.expandedFolders.add(folderPath);
        }
        state.selectedFolder = folderPath;
        renderTargetPane();
    }

    function selectFolder(folderPath) {
        state.selectedFolder = folderPath;
        if (!state.expandedFolders.has(folderPath)) {
            state.expandedFolders.add(folderPath);
        }
        renderTargetPane();
    }

    // ============================================================================
    // File Object Rendering
    // ============================================================================

    function buildExistingObjectRow(obj, gripIcon, filePath) {
        const displayName = obj.display_name || obj.name || '(unnamed)';
        const isTemplate = Explorer.isObjectTemplate(obj);
        const typeLabel = Explorer.getTypeBadge(obj.object_type, isTemplate);
        return `
            <div class="workspace-object-row" data-index="${obj.global_index}" data-file="${Explorer.escapeHtml(filePath)}"
                 draggable="true"
                 ondragstart="Explorer.handleTargetObjectDragStart(event, ${obj.global_index}, 'existing', '${Explorer.escapeJs(filePath)}')"
                 ondragend="Explorer.handleTargetObjectDragEnd(event)">
                <span class="tree-drag-handle">${gripIcon}</span>
                <span class="tree-object-type type-${obj.object_type}" data-badge-compact="${Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'compact')}" data-badge-medium="${Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'medium')}" data-badge-full="${Explorer.getTypeBadgeTier(obj.object_type, isTemplate, 'full')}">${typeLabel}</span>
                <span class="tree-object-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
            </div>`;
    }

    function renderFileObjects(filePath, fileObjects, depth = 2) {
        const sortedObjects = [...fileObjects].sort((a, b) => a.line_number - b.line_number);
        const gripIcon = Explorer.getIcon('grip-vertical');

        let html = '';

        // Drop zone before first object
        html += buildDropZone(filePath, 0);

        for (let i = 0; i < sortedObjects.length; i++) {
            const obj = sortedObjects[i];
            html += buildExistingObjectRow(obj, gripIcon, filePath);

            // Drop zone after each object (use line_number as position)
            const dropPosition = obj.line_number + 1;
            html += buildDropZone(filePath, dropPosition);
        }

        if (sortedObjects.length === 0) {
            html = `<div class="workspace-empty-file" data-file="${Explorer.escapeHtml(filePath)}">
                    Empty file
                </div>`;
        }

        return html;
    }

    function buildDropZone(filePath, position) {
        return `<div class="workspace-drop-zone" data-file="${Explorer.escapeHtml(filePath)}" data-position="${position}"
                 ondragover="Explorer.handleObjectDragOver(event)"
                 ondrop="Explorer.handleObjectDrop(event, '${Explorer.escapeJs(filePath)}', ${position})"
                 ondragleave="Explorer.handleObjectDragLeave(event)"></div>`;
    }

    function handleObjectDragOver(event) {
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'move';
        event.currentTarget.classList.add('drop-active');
    }

    function handleObjectDragLeave(event) {
        event.currentTarget.classList.remove('drop-active');
    }

    /**
     * Normalize drag data from either left-panel ('objects') or right-panel ('target-object-reorder')
     * into a consistent array of {source_file, object_type, name, display_name, attributes}.
     */
    function parseDragObjects(dataStr) {
        if (!dataStr) {return null;}
        let data;
        try { data = JSON.parse(dataStr); } catch (e) { return null; }

        if (data.type === 'objects' && data.objects?.length) {
            return data.objects;
        }
        if (data.type === 'target-object-reorder' && data.objectMeta) {
            return [data.objectMeta];
        }
        return null;
    }

    async function handleObjectDrop(event, targetFile, position) {
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.remove('drop-active');
        Explorer.cleanupDragState();

        const objects = parseDragObjects(event.dataTransfer.getData('text/plain'));
        if (!objects) {return;}

        let moved = 0;
        for (const objData of objects) {
            if (!objData?.source_file) {continue;}

            const nameComponent = objData.name ?? objData.display_name ?? '';
            const objKey = `${objData.source_file}|${objData.object_type}|${nameComponent}`;

            // Delete original first (for both same-file reorder and cross-file move)
            const deleteResult = await ApiClient.post('/api/objects/delete', {
                stable_key: objKey
            }, { silent: true });

            if (!deleteResult.success) {continue;}

            // Create at new position
            const createResult = await ApiClient.post('/api/objects/create', {
                target_file: targetFile,
                object_type: objData.object_type,
                attributes: objData.attributes,
                after_line: position > 0 ? position : null
            }, { silent: true });

            if (createResult.success) {
                moved++;
            }
        }

        if (moved > 0) {
            state.expandedFiles.add(targetFile);
            await Explorer.afterFrontendMutation();
            showToast(`Moved ${moved} object(s) to ${extractFileName(targetFile)}`, 'success');
        }
    }

    function toggleFileExpand(filePath) {
        if (state.expandedFiles.has(filePath)) {
            state.expandedFiles.delete(filePath);
        } else {
            state.expandedFiles.add(filePath);
        }
        renderTargetPane();
    }

    // ============================================================================
    // Drag and Drop Handlers - Files and Folders
    // ============================================================================

    let fileHoverTimeout = null;
    let fileHoverTarget = null;

    function handleFileDragOver(event, filePath) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        event.currentTarget.classList.add('drop-active');

        if (filePath && !state.expandedFiles.has(filePath)) {
            if (fileHoverTarget !== filePath) {
                if (fileHoverTimeout) {
                    clearTimeout(fileHoverTimeout);
                }
                fileHoverTarget = filePath;
                fileHoverTimeout = setTimeout(() => {
                    if (fileHoverTarget === filePath) {
                        state.expandedFiles.add(filePath);
                        renderTargetPane();
                    }
                }, 800);
            }
        }
    }

    function handleFileDragLeave(event) {
        if (event.currentTarget.contains(event.relatedTarget)) {return;}
        event.currentTarget.classList.remove('drop-active');
        if (fileHoverTimeout) {
            clearTimeout(fileHoverTimeout);
            fileHoverTimeout = null;
            fileHoverTarget = null;
        }
    }

    async function handleFileDrop(event, targetFile) {
        event.preventDefault();
        event.currentTarget.classList.remove('drop-active');
        Explorer.cleanupDragState();

        const objects = parseDragObjects(event.dataTransfer.getData('text/plain'));
        if (!objects) {return;}

        let moved = 0;
        for (const objData of objects) {
            if (!objData?.source_file || objData.source_file === targetFile) {continue;}

            const nameComponent = objData.name ?? objData.display_name ?? '';
            const objKey = `${objData.source_file}|${objData.object_type}|${nameComponent}`;

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
            showToast(`Moved ${moved} object(s) to ${extractFileName(targetFile)}`, 'success');
        }
    }

    function handleTargetObjectDragStart(event, index, itemType, sourceFile) {
        event.stopPropagation();
        event.currentTarget.classList.add('dragging');

        const dragData = {
            type: 'target-object-reorder',
            index: index,
            itemType: itemType,
            sourceFile: sourceFile
        };

        if (itemType === 'existing') {
            const obj = state.allObjects.find(o => o.global_index === index);
            if (obj) {
                dragData.objectMeta = {
                    global_index: index,
                    source_file: obj.source_file,
                    line_number: obj.line_number,
                    object_type: obj.object_type,
                    name: obj.name,
                    display_name: obj.display_name,
                    attributes: obj.attributes
                };
            }
        }

        event.dataTransfer.setData(DATA_TYPES.OBJECTS, JSON.stringify(dragData));
        event.dataTransfer.effectAllowed = 'move';
    }

    function handleTargetObjectDragEnd(event) {
        event.currentTarget.classList.remove('dragging');
    }

    // ============================================================================
    // Folder Drag and Drop
    // ============================================================================

    let folderHoverTimeout = null;
    let folderHoverTarget = null;

    function handleFolderDragOver(event, folderPath) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        event.currentTarget.classList.add('drop-active');

        if (folderPath && !state.expandedFolders.has(folderPath)) {
            if (folderHoverTarget !== folderPath) {
                if (folderHoverTimeout) {
                    clearTimeout(folderHoverTimeout);
                }
                folderHoverTarget = folderPath;
                folderHoverTimeout = setTimeout(() => {
                    if (folderHoverTarget === folderPath) {
                        state.expandedFolders.add(folderPath);
                        renderTargetPane();
                    }
                }, 800);
            }
        }
    }

    function handleFolderDragLeave(event) {
        if (event.currentTarget.contains(event.relatedTarget)) {return;}
        event.currentTarget.classList.remove('drop-active');
        if (folderHoverTimeout) {
            clearTimeout(folderHoverTimeout);
            folderHoverTimeout = null;
            folderHoverTarget = null;
        }
    }

    async function moveFileImmediate(sourcePath, targetFolder) {
        const result = await ApiClient.post('/api/files/move', { sourcePath, targetFolder }, { silent: true });

        if (!result.success) {
            showToast(result.data?.error || result.error || 'Failed to move file', 'error');
            return;
        }

        state.expandedFolders.add(targetFolder);
        await Explorer.afterFrontendMutation();
        showToast(`Moved file to ${extractFileName(targetFolder)}/`, 'success');
    }

    async function moveFolderImmediate(sourcePath, targetFolder) {
        const result = await ApiClient.post('/api/folders/move', { sourcePath, targetFolder }, { silent: true });

        if (!result.success) {
            showToast(result.data?.error || result.error || 'Failed to move folder', 'error');
            return;
        }

        state.expandedFolders.add(targetFolder);
        await Explorer.afterFrontendMutation();
        showToast(`Moved folder to ${extractFileName(targetFolder)}/`, 'success');
    }

    function handleFolderOnFolderDrop(folderData, targetFolder) {
        const sourcePath = folderData;
        const sourceParent = sourcePath.substring(0, sourcePath.lastIndexOf('/'));

        const normalizedSource = sourcePath.replace(/\/+$/, '');
        const normalizedTarget = targetFolder.replace(/\/+$/, '');

        if (normalizedTarget === normalizedSource ||
            normalizedTarget.startsWith(normalizedSource + '/')) {
            showToast('Cannot move folder into itself or its children', 'warning');
            return;
        }

        if (sourceParent === targetFolder) {
            showToast('Folder is already in this location', 'warning');
            return;
        }

        moveFolderImmediate(sourcePath, targetFolder);
    }

    function handleFileOnFolderDrop(fileData, targetFolder) {
        const sourcePath = fileData;
        const sourceParent = sourcePath.substring(0, sourcePath.lastIndexOf('/'));

        if (sourceParent === targetFolder) {
            showToast('File is already in this folder', 'warning');
            return;
        }

        moveFileImmediate(sourcePath, targetFolder);
    }

    function resolveTargetFileInFolder(targetFolder) {
        const filesInFolder = state.allFiles.filter(f => {
            const dir = f.substring(0, f.lastIndexOf('/'));
            return dir === targetFolder;
        });
        if (filesInFolder.length === 0) {
            return targetFolder + '/objects.cfg';
        }
        if (filesInFolder.length === 1) {
            return filesInFolder[0];
        }
        state.expandedFolders.add(targetFolder);
        showToast('Multiple files in folder. Drop objects on a specific file.', 'info');
        return null;
    }

    function handleFolderDrop(event, targetFolder) {
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.remove('drop-active');
        Explorer.cleanupDragState();

        const objectData = event.dataTransfer.getData(DATA_TYPES.OBJECTS);
        const fileData = event.dataTransfer.getData(DATA_TYPES.FILE_MOVE);
        const folderData = event.dataTransfer.getData(DATA_TYPES.FOLDER_MOVE);

        if (folderData) {
            handleFolderOnFolderDrop(folderData, targetFolder);
        } else if (fileData) {
            handleFileOnFolderDrop(fileData, targetFolder);
        } else if (objectData) {
            handleObjectsOnFolderDrop(objectData, targetFolder);
        }
    }

    async function handleObjectsOnFolderDrop(data, targetFolder) {
        const objects = parseDragObjects(data);
        if (!objects) {return;}

        const targetFile = resolveTargetFileInFolder(targetFolder);
        if (!targetFile) {renderTargetPane(); return;}

        let moved = 0;
        for (const objData of objects) {
            if (!objData?.source_file || objData.source_file === targetFile) {continue;}

            const nameComponent = objData.name ?? objData.display_name ?? '';
            const objKey = `${objData.source_file}|${objData.object_type}|${nameComponent}`;

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
            state.expandedFiles.add(targetFile);
            state.expandedFolders.add(targetFolder);
            await Explorer.afterFrontendMutation();
            showToast(`Moved ${moved} object(s) to ${extractFileName(targetFile)}`, 'success');
        }
    }

    function handleFileDragStart(event, filePath) {
        const target = event.currentTarget || event.target;
        if (!target) {return;}

        event.dataTransfer.setData(DATA_TYPES.FILE_MOVE, filePath);
        event.dataTransfer.effectAllowed = 'move';

        target.style.opacity = '0.5';
        target.addEventListener('dragend', () => {
            target.style.opacity = '';
        }, { once: true });
    }

    function handleFolderDragStart(event, folderPath) {
        if (folderPath === state.configPath) {
            event.preventDefault();
            return;
        }

        const target = event.currentTarget || event.target;
        if (!target) {return;}
        event.dataTransfer.setData(DATA_TYPES.FOLDER_MOVE, folderPath);
        event.dataTransfer.effectAllowed = 'move';

        target.style.opacity = '0.5';
        target.addEventListener('dragend', () => {
            target.style.opacity = '';
        }, { once: true });
    }

    // ============================================================================
    // Deletion Functions
    // ============================================================================

    async function deleteFile(filePath, event) {
        if (event) {
            event.stopPropagation();
        }

        const fileName = extractFileName(filePath);
        const objectsInFile = state.allObjects.filter(o => o.source_file === filePath);
        const objectCount = objectsInFile.length;
        const objectSummary = objectCount > 0
            ? `\n\nThis file contains ${objectCount} object${objectCount !== 1 ? 's' : ''} that will also be deleted.`
            : '';

        const deleteConfirmed = await showConfirmDialog({
            title: `Delete ${fileName}?`,
            message: `Are you sure you want to delete "${fileName}"?${objectSummary}`,
            confirmText: 'Delete File',
            cancelText: 'Cancel',
            type: 'danger'
        });

        if (!deleteConfirmed) {
            return;
        }

        let relativePath = filePath;
        if (filePath.startsWith(state.configPath + '/')) {
            relativePath = filePath.substring(state.configPath.length + 1);
        } else if (filePath.startsWith(state.configPath)) {
            relativePath = filePath.substring(state.configPath.length);
        }
        const encodedPath = encodeURIComponent(relativePath);
        const result = await ApiClient.del(`/api/files/${encodedPath}`, { silent: true });

        if (!result.success) {
            showToast(result.data?.error || result.error || 'Failed to delete file', 'error');
            return;
        }

        await Explorer.afterFrontendMutation();
        showToast(`Deleted "${fileName}"`, 'success');
    }

    async function deleteFolder(folderPath, event) {
        if (event) {
            event.stopPropagation();
        }

        if (folderPath === state.configPath) {
            showToast('Cannot delete the config root folder', 'error');
            return;
        }

        const folderName = extractFileName(folderPath);

        const deleteConfirmed = await showConfirmDialog({
            title: `Delete ${folderName}/?`,
            message: `Are you sure you want to delete the folder "${folderName}/" and all its contents?`,
            confirmText: 'Delete Folder',
            cancelText: 'Cancel',
            type: 'danger'
        });

        if (!deleteConfirmed) {
            return;
        }

        let relativePath = folderPath;
        if (folderPath.startsWith(state.configPath + '/')) {
            relativePath = folderPath.substring(state.configPath.length + 1);
        } else if (folderPath.startsWith(state.configPath)) {
            relativePath = folderPath.substring(state.configPath.length);
        }
        const encodedPath = encodeURIComponent(relativePath);
        const result = await ApiClient.del(`/api/folders/${encodedPath}`, { silent: true });

        if (!result.success) {
            showToast(result.data?.error || result.error || 'Failed to delete folder', 'error');
            return;
        }

        await Explorer.afterFrontendMutation();
        showToast(`Deleted "${folderName}/"`, 'success');
    }

    // ============================================================================
    // File/Folder Creation
    // ============================================================================

    async function createNewItem() {
        let name = document.getElementById('newItemName').value.trim();
        if (!name) {
            showToast('Please enter a name', 'warning');
            return;
        }

        const nameToValidate = name.endsWith('/') ? name.slice(0, -1) : name;
        const invalidChars = /[\/\\:*?"<>|]/;
        if (invalidChars.test(nameToValidate)) {
            showToast('Name cannot contain / \\ : * ? " < > |', 'error');
            return;
        }

        let basePath = state.selectedFolder || state.configPath;
        const isFolder = name.endsWith('/');

        if (isFolder) {
            name = name.slice(0, -1);
            const fullPath = basePath + '/' + name;

            if (state.existingFolders.includes(fullPath)) {
                showToast('Folder already exists', 'warning');
                return;
            }

            const result = await ApiClient.post('/api/folders', { path: fullPath }, { silent: true });

            if (!result.success) {
                showToast(result.data?.error || result.error || 'Failed to create folder', 'error');
                return;
            }

            state.expandedFolders.add(fullPath);
            document.getElementById('newItemName').value = '';
            await Explorer.afterFrontendMutation();
            showToast(`Created folder "${name}/"`, 'success');
            return;
        }

        // Create file
        if (!name.endsWith('.cfg')) {
            name += '.cfg';
        }

        const fullPath = basePath + '/' + name;

        const existingFiles = [...new Set(state.allObjects.map(o => o.source_file))];
        if (existingFiles.includes(fullPath) || state.allFiles.includes(fullPath)) {
            showToast('File already exists', 'warning');
            return;
        }

        const result = await ApiClient.post('/api/files/create', { path: fullPath }, { silent: true });

        if (!result.success) {
            showToast(result.data?.error || result.error || 'Failed to create file', 'error');
            return;
        }

        state.expandedFiles.add(fullPath);
        document.getElementById('newItemName').value = '';
        await Explorer.afterFrontendMutation();
        showToast(`Created file "${name}"`, 'success');
    }

    // ============================================================================
    // Inline File/Folder Creation
    // ============================================================================

    function createInlineFile() {
        createInlineItem('file');
    }

    function createInlineFolder() {
        createInlineItem('folder');
    }

    function createInlineItem(type) {
        const container = document.getElementById('targetPaneContent');
        if (!container) {return;}

        const existing = container.querySelector('.tree-item-inline-edit');
        if (existing) {
            existing.remove();
        }

        const icon = type === 'folder' ? Explorer.getIcon('folder-plus') : Explorer.getIcon('file-plus');
        const iconClass = type === 'folder' ? 'tree-icon--folder' : 'tree-icon--file';
        const suffix = type === 'file' ? '<span class="tree-inline-suffix">.cfg</span>' : '';

        const row = document.createElement('div');
        row.className = 'tree-item-inline-edit';
        row.innerHTML = `
        <span class="tree-expand-placeholder"></span>
        <span class="tree-icon ${iconClass}">${icon}</span>
        <input type="text" class="tree-inline-input" autocomplete="off">
        ${suffix}
    `;

        container.insertBefore(row, container.firstChild);

        const input = row.querySelector('input');
        input.focus();

        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                confirmInlineCreate(type, input.value.trim(), row);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                row.remove();
            }
        });

        input.addEventListener('blur', function() {
            setTimeout(() => {
                if (row.parentNode) {
                    const value = input.value.trim();
                    if (value) {
                        confirmInlineCreate(type, value, row);
                    } else {
                        row.remove();
                    }
                }
            }, 150);
        });
    }

    async function confirmInlineCreate(type, name, row) {
        if (!name) {
            row.remove();
            return;
        }

        const nameToValidate = name.endsWith('/') ? name.slice(0, -1) : name;
        const invalidChars = /[\/\\:*?"<>|]/;
        if (invalidChars.test(nameToValidate)) {
            showToast('Name cannot contain / \\ : * ? " < > |', 'error');
            row.remove();
            return;
        }

        const basePath = state.selectedFolder || state.configPath;

        if (type === 'folder') {
            const folderName = name.endsWith('/') ? name.slice(0, -1) : name;
            const fullPath = basePath + '/' + folderName;

            if (state.existingFolders.includes(fullPath)) {
                showToast('Folder already exists', 'warning');
                row.remove();
                return;
            }

            const result = await ApiClient.post('/api/folders', { path: fullPath }, { silent: true });

            if (!result.success) {
                showToast(result.data?.error || result.error || 'Failed to create folder', 'error');
                row.remove();
                return;
            }

            state.expandedFolders.add(fullPath);
            row.remove();
            await Explorer.afterFrontendMutation();
            showToast(`Created folder "${folderName}/"`, 'success');
        } else {
            const baseName = name.replace(/\.cfg$/i, '');
            if (!baseName) {
                row.remove();
                return;
            }
            const fileName = baseName + '.cfg';
            const fullPath = basePath + '/' + fileName;

            const existingFiles = [...new Set(state.allObjects.map(o => o.source_file))];
            if (existingFiles.includes(fullPath) || state.allFiles.includes(fullPath)) {
                showToast('File already exists', 'warning');
                row.remove();
                return;
            }

            const result = await ApiClient.post('/api/files/create', { path: fullPath }, { silent: true });

            if (!result.success) {
                showToast(result.data?.error || result.error || 'Failed to create file', 'error');
                row.remove();
                return;
            }

            state.expandedFiles.add(fullPath);
            row.remove();
            await Explorer.afterFrontendMutation();
            showToast(`Created file "${fileName}"`, 'success');
        }
    }

    // ============================================================================
    // Exports
    // ============================================================================

    Explorer.navigateToObjectByIndex = navigateToObjectByIndex;
    Explorer.selectObjectByName = selectObjectByName;
    Explorer.restoreExpandedState = restoreExpandedState;
    Explorer.saveExpandedState = saveExpandedState;
    Explorer.initTargetPane = initTargetPane;
    Explorer.initWorkspaceToolbar = initWorkspaceToolbar;
    Explorer.toggleCreateMenu = toggleCreateMenu;
    Explorer.showCreateInput = showCreateInput;
    Explorer.hideCreateInput = hideCreateInput;
    Explorer.handleCreateKeydown = handleCreateKeydown;
    Explorer.collapseAllFolders = collapseAllFolders;
    Explorer.refreshWorkspace = refreshWorkspace;
    Explorer.updateWorkspaceHeader = updateWorkspaceHeader;
    Explorer.renderTargetPane = renderTargetPane;
    Explorer.toggleFolderExpand = toggleFolderExpand;
    Explorer.selectFolder = selectFolder;
    Explorer.renderFileObjects = renderFileObjects;
    Explorer.toggleFileExpand = toggleFileExpand;
    Explorer.handleFileDragOver = handleFileDragOver;
    Explorer.handleFileDragLeave = handleFileDragLeave;
    Explorer.handleTargetObjectDragStart = handleTargetObjectDragStart;
    Explorer.handleTargetObjectDragEnd = handleTargetObjectDragEnd;
    Explorer.handleFileDrop = handleFileDrop;
    Explorer.handleObjectDragOver = handleObjectDragOver;
    Explorer.handleObjectDragLeave = handleObjectDragLeave;
    Explorer.handleObjectDrop = handleObjectDrop;
    Explorer.handleFolderDragOver = handleFolderDragOver;
    Explorer.handleFolderDragLeave = handleFolderDragLeave;
    Explorer.moveFileImmediate = moveFileImmediate;
    Explorer.moveFolderImmediate = moveFolderImmediate;
    Explorer.handleFolderDrop = handleFolderDrop;
    Explorer.handleFileDragStart = handleFileDragStart;
    Explorer.handleFolderDragStart = handleFolderDragStart;
    Explorer.deleteFile = deleteFile;
    Explorer.deleteFolder = deleteFolder;
    Explorer.createNewItem = createNewItem;
    Explorer.createInlineFile = createInlineFile;
    Explorer.createInlineFolder = createInlineFolder;
    Explorer.createInlineItem = createInlineItem;
    Explorer.confirmInlineCreate = confirmInlineCreate;

})(window.Explorer);
