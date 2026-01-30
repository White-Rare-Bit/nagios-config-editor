/** Explorer File Operations Module - Target pane rendering, file/folder operations, drag-drop in workspace */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;
    const toDisplayPath = Explorer.toDisplayPath;

    // ============================================================================
    // Navigation
    // ============================================================================

    function navigateToObjectByIndex(index) {
        const obj = state.allObjects.find(o => o.global_index === index);
        if (!obj) return;

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
            // Find folder by file path
            const folder = document.querySelector(`.tree-folder[data-file="${obj.source_file}"]`);
            if (folder && !folder.classList.contains('open')) {
                folder.classList.add('open');
            }
        } else {
            // Find folder by type - type folders don't have data-file, find by name
            const folders = document.querySelectorAll('.tree-folder');
            folders.forEach(folder => {
                const nameEl = folder.querySelector('.tree-folder-name');
                if (nameEl && nameEl.textContent === obj.object_type && !folder.classList.contains('open')) {
                    folder.classList.add('open');
                }
            });
        }

        Explorer.clearSelection();
        selectObjectByIndex(index);
        Explorer.updateSelection();

        // Scroll to item with slight delay to ensure DOM is updated
        setTimeout(() => {
            const item = document.querySelector(`.tree-item[data-index="${index}"]`);
            if (item) {
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Add highlight pulse effect
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
    // Target Pane (Right Side File Browser)
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

    // Save state before page unload
    window.addEventListener('beforeunload', saveExpandedState);

    function initTargetPane() {
        restoreExpandedState();
        initWorkspaceToolbar();
        renderTargetPane();
    }

    function initWorkspaceToolbar() {
        // Set toolbar button icons
        const createMenuBtn = document.getElementById('createMenuBtn');
        const collapseAllBtn = document.getElementById('collapseAllBtn');
        const refreshBtn = document.getElementById('refreshBtn');
        const workspaceRootIcon = document.getElementById('workspaceRootIcon');
        const newFileIcon = document.getElementById('newFileIcon');
        const newFolderIcon = document.getElementById('newFolderIcon');

        if (createMenuBtn) createMenuBtn.innerHTML = Explorer.getIcon('plus');
        if (collapseAllBtn) collapseAllBtn.innerHTML = Explorer.getIcon('minimize-2');
        if (refreshBtn) refreshBtn.innerHTML = Explorer.getIcon('refresh-cw');
        if (workspaceRootIcon) workspaceRootIcon.innerHTML = Explorer.getIcon('folder-open');
        if (newFileIcon) newFileIcon.innerHTML = Explorer.getIcon('file-plus');
        if (newFolderIcon) newFolderIcon.innerHTML = Explorer.getIcon('folder-plus');

        // Close dropdown when clicking outside
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

        if (dropdown) dropdown.classList.remove('visible');
        if (inlineCreate) inlineCreate.classList.add('visible');
        if (input) {
            input.placeholder = type === 'folder' ? 'foldername/' : 'filename.cfg';
            input.value = '';
            input.focus();
            // Store the type for createNewItem
            input.dataset.createType = type;
        }
    }

    function hideCreateInput() {
        const inlineCreate = document.getElementById('workspaceCreateInline');
        if (inlineCreate) inlineCreate.classList.remove('visible');
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
            showToast('Workspace refreshed', 'success');
        });
    }

    function updateWorkspaceHeader() {
        const rootName = document.getElementById('workspaceRootName');
        const rootMeta = document.getElementById('workspaceRootMeta');
        const configRootName = state.configPath.split('/').pop() || 'config';
        const totalObjects = state.allObjects.length;

        if (rootName) rootName.textContent = configRootName;
        if (rootMeta) rootMeta.textContent = `${totalObjects} object${totalObjects !== 1 ? 's' : ''}`;
    }

    function renderTargetPane() {
        const container = document.getElementById('targetPaneContent');

        // Update header info
        updateWorkspaceHeader();

        // Combine files from objects with all files from filesystem (includes empty files)
        const filesFromObjects = state.allObjects.map(o => o.source_file);
        const files = [...new Set([...filesFromObjects, ...state.allFiles])].sort();

        // Build a nested folder tree structure starting from config root
        const root = { folders: {}, files: [], path: state.configPath, isNew: false };

        // Helper to convert absolute path to relative path from state.configPath
        function toRelativePath(absPath) {
            if (absPath.startsWith(state.configPath + '/')) {
                return absPath.substring(state.configPath.length + 1);
            } else if (absPath === state.configPath) {
                return '';
            }
            return absPath;
        }

        // Helper to ensure folder path exists in tree
        function ensureFolderPath(absPath) {
            if (absPath === state.configPath) {
                return root;
            }
            const relativePath = toRelativePath(absPath);
            if (!relativePath) return root;

            const parts = relativePath.split('/').filter(p => p);
            let current = root;
            let currentAbsPath = state.configPath;

            for (const part of parts) {
                currentAbsPath += '/' + part;
                if (!current.folders[part]) {
                    current.folders[part] = { folders: {}, files: [], path: currentAbsPath, isNew: false };
                }
                current = current.folders[part];
            }
            return current;
        }

        // Add existing files to tree
        for (const file of files) {
            const parts = file.split('/');
            const filename = parts.pop();
            const dir = parts.join('/') || state.configPath;
            const folder = ensureFolderPath(dir);
            folder.files.push({ path: file, name: filename, isNew: false });
        }

        // Add existing folders from filesystem
        for (const folderPath of state.existingFolders) {
            ensureFolderPath(folderPath);
        }

        // Add staged folder creations (not yet on disk)
        for (const staged of (state.stagedFolderCreations || [])) {
            if (staged.path) {
                ensureFolderPath(staged.path);
            }
        }

        // Add staged file creations (not yet on disk)
        for (const staged of (state.stagedFileCreations || [])) {
            if (staged.path) {
                const parts = staged.path.split('/');
                const filename = parts.pop();
                const dir = parts.join('/') || state.configPath;
                const folder = ensureFolderPath(dir);
                if (!folder.files.some(f => f.path === staged.path)) {
                    folder.files.push({ path: staged.path, name: filename, isNew: true });
                }
            }
        }

        // Add new files (staged only, not yet on disk)
        for (const newFile of state.newFiles) {
            const parts = newFile.split('/');
            const filename = parts.pop();
            const dir = parts.join('/') || state.configPath;
            const folder = ensureFolderPath(dir);
            if (!folder.files.some(f => f.path === newFile)) {
                folder.files.push({ path: newFile, name: filename, isNew: true });
            }
        }

        // Count objects in folder recursively
        function countFolderObjects(folder) {
            let count = folder.files.reduce((sum, f) => {
                return sum + state.allObjects.filter(o => o.source_file === f.path).length;
            }, 0);
            for (const subName of Object.keys(folder.folders)) {
                count += countFolderObjects(folder.folders[subName]);
            }
            return count;
        }

        // Render folder row with new enterprise styling
        function renderFolder(folder, name, depth) {
            const isExpanded = state.expandedFolders.has(folder.path);
            const subfolderNames = Object.keys(folder.folders).sort();
            const hasChildren = subfolderNames.length > 0 || folder.files.length > 0;

            // Count total objects
            let totalObjects = folder.files.reduce((sum, f) => {
                return sum + state.allObjects.filter(o => o.source_file === f.path).length;
            }, 0);
            for (const subName of subfolderNames) {
                totalObjects += countFolderObjects(folder.folders[subName]);
            }

            // Count pending moves
            const pendingInFolder = folder.files.reduce((sum, f) => {
                return sum + [...state.stagedMoves.entries()].filter(([_, m]) => m.targetFile === f.path).length;
            }, 0);

            // Check for staged folder operations
            const isStagedForDeletion = (state.stagedFolderDeletions || []).some(d => d.path === folder.path);
            const isStagedForMove = (state.stagedFolderMoves || []).some(m => m.sourcePath === folder.path);
            const isStagedNew = (state.stagedFolderCreations || []).some(c => c.path === folder.path);

            const canDrag = folder.path !== state.configPath;
            const canDelete = folder.path !== state.configPath;

            const expandIcon = hasChildren ? Explorer.getIcon('chevron-right') : '';
            const folderIcon = isExpanded ? Explorer.getIcon('folder-open') : Explorer.getIcon('folder');
            const deleteIcon = Explorer.getIcon('trash-2');

            // Determine row styling based on staged status
            let rowClasses = 'workspace-tree-row';
            if (isExpanded) rowClasses += ' expanded';
            if (isStagedForDeletion) rowClasses += ' staged-deletion';
            if (isStagedForMove) rowClasses += ' staged-move';
            if (isStagedNew) rowClasses += ' staged-new';

            // Build action button
            let actionHtml = '';
            if (isStagedNew) {
                actionHtml = `<button class="tree-action-btn" onclick="event.stopPropagation(); Explorer.unstageFolderCreation('${Explorer.escapeJs(folder.path)}', event)" title="Undo">${Explorer.getIcon('x')}</button>`;
            } else if (isStagedForDeletion) {
                actionHtml = `<button class="tree-action-btn" onclick="event.stopPropagation(); Explorer.unstageFolderDeletion('${Explorer.escapeJs(folder.path)}', event)" title="Undo deletion">${Explorer.getIcon('x')}</button>`;
            } else if (canDelete) {
                actionHtml = `<button class="tree-action-btn tree-action-btn--danger" onclick="event.stopPropagation(); Explorer.stageDeleteFolder('${Explorer.escapeJs(folder.path)}', event)" title="Delete folder">${deleteIcon}</button>`;
            }

            // Add visual indicator badge
            let indicatorHtml = '';
            if (isStagedForDeletion) indicatorHtml = '<span class="staged-indicator staged-indicator--delete" title="Staged for deletion">DEL</span>';
            else if (isStagedForMove) indicatorHtml = '<span class="staged-indicator staged-indicator--move" title="Staged for move">MOV</span>';
            else if (isStagedNew) indicatorHtml = '<span class="staged-indicator staged-indicator--new" title="Staged for creation">NEW</span>';

            let html = `
            <div class="${rowClasses}" data-depth="${depth}" data-folder="${Explorer.escapeHtml(folder.path)}"
                 onclick="Explorer.toggleFolderExpand('${Explorer.escapeJs(folder.path)}')"
                 ondragover="Explorer.handleFolderDragOver(event, '${Explorer.escapeJs(folder.path)}')"
                 ondrop="Explorer.handleFolderDrop(event, '${Explorer.escapeJs(folder.path)}')"
                 ondragleave="Explorer.handleFolderDragLeave(event)"
                 draggable="${canDrag ? 'true' : 'false'}"
                 ondragstart="Explorer.handleFolderDragStart(event, '${Explorer.escapeJs(folder.path)}')">
                <button class="tree-expand-btn${isExpanded ? ' expanded' : ''}" onclick="event.stopPropagation(); Explorer.toggleFolderExpand('${Explorer.escapeJs(folder.path)}')">${expandIcon}</button>
                <span class="tree-icon tree-icon--folder${isExpanded ? ' expanded' : ''}${isStagedNew ? ' tree-icon--new' : ''}">${folderIcon}</span>
                <span class="tree-label tree-label--folder${isStagedForDeletion ? ' tree-label--deleted' : ''}">${Explorer.escapeHtml(name)}</span>
                ${indicatorHtml}
                <span class="tree-count${totalObjects === 0 ? ' tree-count--empty' : ''}">${totalObjects}</span>
                ${pendingInFolder > 0 ? `<span class="tree-count tree-count--pending">+${pendingInFolder}</span>` : ''}
                <div class="tree-row-actions">
                    ${actionHtml}
                </div>
            </div>
            <div class="tree-children${isExpanded ? ' expanded with-guides' : ''}">`;

            // Render subfolders
            for (const subName of subfolderNames) {
                html += renderFolder(folder.folders[subName], subName, depth + 1);
            }

            // Render files
            for (const file of folder.files.sort((a, b) => a.name.localeCompare(b.name))) {
                html += renderFileItem(file, depth + 1);
            }

            html += `</div>`;
            return html;
        }

        // Render file row with new enterprise styling
        function renderFileItem(file, depth = 0) {
            const fileObjects = state.allObjects.filter(o => o.source_file === file.path);
            const pendingObjects = [...state.stagedMoves.entries()].filter(([_, m]) => m.targetFile === file.path);
            const stagedCreationsForFile = state.stagedCreations
                .map((creation, idx) => ({ creation, idx }))
                .filter(item => item.creation.targetFile === file.path);
            const isExpanded = state.expandedFiles.has(file.path);
            const pendingCount = pendingObjects.length;
            const creationCount = stagedCreationsForFile.length;
            const hasObjects = fileObjects.length > 0 || pendingCount > 0 || creationCount > 0;

            // Check for staged file operations
            const isStagedForDeletion = (state.stagedFileDeletions || []).some(d => d.path === file.path);
            const isStagedForMove = (state.stagedFileMoves || []).some(m => m.sourcePath === file.path);
            const isStagedNew = (state.stagedFileCreations || []).some(c => c.path === file.path);

            const expandIcon = hasObjects ? Explorer.getIcon('chevron-right') : '';
            const fileIcon = file.isNew || isStagedNew ? Explorer.getIcon('file-plus') : Explorer.getIcon('file-text');
            const deleteIcon = Explorer.getIcon('trash-2');

            // Determine row styling based on staged status
            let rowClasses = 'workspace-tree-row';
            if (isExpanded) rowClasses += ' expanded';
            if (isStagedForDeletion) rowClasses += ' staged-deletion';
            if (isStagedForMove) rowClasses += ' staged-move';
            if (file.isNew || isStagedNew) rowClasses += ' staged-new';

            let actionHtml = '';
            if (file.isNew || isStagedNew) {
                actionHtml = `<button class="tree-action-btn" onclick="event.stopPropagation(); Explorer.undoNewFile('${Explorer.escapeJs(file.path)}', event)" title="Undo">${Explorer.getIcon('x')}</button>`;
            } else if (isStagedForDeletion) {
                actionHtml = `<button class="tree-action-btn" onclick="event.stopPropagation(); Explorer.unstageFileDeletion('${Explorer.escapeJs(file.path)}', event)" title="Undo deletion">${Explorer.getIcon('x')}</button>`;
            } else {
                actionHtml = `<button class="tree-action-btn tree-action-btn--danger" onclick="event.stopPropagation(); Explorer.stageDeleteFile('${Explorer.escapeJs(file.path)}', event)" title="Delete file">${deleteIcon}</button>`;
            }

            // Add visual indicator badge
            let indicatorHtml = '';
            if (isStagedForDeletion) indicatorHtml = '<span class="staged-indicator staged-indicator--delete" title="Staged for deletion">DEL</span>';
            else if (isStagedForMove) indicatorHtml = '<span class="staged-indicator staged-indicator--move" title="Staged for move">MOV</span>';
            else if (file.isNew || isStagedNew) indicatorHtml = '<span class="staged-indicator staged-indicator--new" title="Staged for creation">NEW</span>';

            let html = `
            <div class="${rowClasses}" data-depth="${depth}" data-file="${Explorer.escapeHtml(file.path)}"
                 onclick="Explorer.toggleFileExpand('${Explorer.escapeJs(file.path)}')"
                 ondragover="Explorer.handleFileDragOver(event, '${Explorer.escapeJs(file.path)}')"
                 ondrop="Explorer.handleFileDrop(event, '${Explorer.escapeJs(file.path)}')"
                 ondragleave="Explorer.handleFileDragLeave(event)"
                 draggable="true"
                 ondragstart="Explorer.handleFileDragStart(event, '${Explorer.escapeJs(file.path)}')">
                ${hasObjects ? `<button class="tree-expand-btn${isExpanded ? ' expanded' : ''}" onclick="event.stopPropagation(); Explorer.toggleFileExpand('${Explorer.escapeJs(file.path)}')">${expandIcon}</button>` : '<span class="tree-expand-placeholder"></span>'}
                <span class="tree-icon tree-icon--file${file.isNew || isStagedNew ? '-new' : ''}">${fileIcon}</span>
                <span class="tree-label${file.isNew || isStagedNew ? ' tree-label--staged' : ''}${isStagedForDeletion ? ' tree-label--deleted' : ''}">${Explorer.escapeHtml(file.name)}</span>
                ${indicatorHtml}
                <span class="tree-count${fileObjects.length === 0 ? ' tree-count--empty' : ''}">${fileObjects.length}</span>
                ${(pendingCount + creationCount) > 0 ? `<span class="tree-count tree-count--pending">+${pendingCount + creationCount}</span>` : ''}
                <div class="tree-row-actions">
                    ${actionHtml}
                </div>
            </div>
            <div class="tree-children${isExpanded ? ' expanded' : ''}">
                ${renderFileObjects(file.path, fileObjects, pendingObjects, stagedCreationsForFile, depth + 1)}
            </div>`;

            return html;
        }

        // Build the tree HTML
        let html = '';
        const rootFolderNames = Object.keys(root.folders).sort();

        if (rootFolderNames.length === 0 && root.files.length === 0) {
            html = '<div class="workspace-empty-file">No configuration files yet. Click + to create one.</div>';
        } else {
            // Render all subfolders at root level
            for (const name of rootFolderNames) {
                html += renderFolder(root.folders[name], name, 0);
            }
            // Render files at root level
            for (const file of root.files.sort((a, b) => a.name.localeCompare(b.name))) {
                html += renderFileItem(file, 0);
            }
        }

        container.innerHTML = html;
    }

    function toggleFolderExpand(folderPath) {
        if (state.expandedFolders.has(folderPath)) {
            state.expandedFolders.delete(folderPath);
        } else {
            state.expandedFolders.add(folderPath);
        }
        renderTargetPane();
    }

    function renderFileObjects(filePath, existingObjects, pendingObjects, stagedCreationsForFile = [], depth = 2) {
        // Sort existing objects by line_number to preserve file order
        const sortedExisting = [...existingObjects].sort((a, b) => a.line_number - b.line_number);

        // Build a combined list of existing, pending, and new objects with positions
        const items = [];

        // Add existing objects (excluding those being moved out or deleted)
        for (const obj of sortedExisting) {
            const objKey = Explorer.getObjectKey(obj);
            const isPendingOut = state.stagedMoves.has(objKey) && state.stagedMoves.get(objKey).originalFile === filePath;
            const isDeleted = state.stagedObjectDeletions.has(obj.global_index);
            if (!isPendingOut && !isDeleted) {
                items.push({
                    type: 'existing',
                    obj: obj,
                    position: obj.line_number
                });
            }
        }

        // Add pending move objects at their specified positions
        for (const [idx, move] of pendingObjects) {
            items.push({
                type: 'pending',
                idx: idx,
                move: move,
                position: move.insertPosition !== undefined ? move.insertPosition : Infinity
            });
        }

        // Add staged creations at their specified positions (or end by default)
        for (const { creation, idx } of stagedCreationsForFile) {
            items.push({
                type: 'creation',
                creation: creation,
                idx: idx,
                position: creation.insertPosition !== undefined ? creation.insertPosition : Infinity
            });
        }

        // Sort all items by position
        items.sort((a, b) => a.position - b.position);

        const gripIcon = Explorer.getIcon('grip-vertical');
        const xIcon = Explorer.getIcon('x');

        let html = '';

        // Render drop zone at start of file
        html += `<div class="workspace-drop-zone" data-file="${Explorer.escapeHtml(filePath)}" data-position="0"
                 ondragover="Explorer.handleObjectDragOver(event)"
                 ondrop="Explorer.handleObjectDrop(event, '${Explorer.escapeJs(filePath)}', 0)"
                 ondragleave="Explorer.handleObjectDragLeave(event)"></div>`;

        for (let i = 0; i < items.length; i++) {
            const item = items[i];

            if (item.type === 'existing') {
                const displayName = Explorer.getStagedDisplayName(item.obj);
                const isTemplate = Explorer.isObjectTemplate(item.obj);
                const typeLabel = isTemplate ? `${item.obj.object_type} tmpl` : item.obj.object_type;
                html += `
                <div class="workspace-object-row" data-index="${item.obj.global_index}" data-position="${item.position}" data-file="${Explorer.escapeHtml(filePath)}"
                     draggable="true"
                     ondragstart="Explorer.handleTargetObjectDragStart(event, ${item.obj.global_index}, 'existing', '${Explorer.escapeJs(filePath)}')"
                     ondragend="Explorer.handleTargetObjectDragEnd(event)">
                    <span class="tree-drag-handle">${gripIcon}</span>
                    <span class="tree-object-type type-${item.obj.object_type}">${typeLabel}</span>
                    <span class="tree-object-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
                </div>
            `;
            } else if (item.type === 'pending') {
                const pendingDisplayName = item.move.object.display_name || item.move.object.name;
                const isTemplate = Explorer.isObjectTemplate(item.move.object);
                const typeLabel = isTemplate ? `${item.move.object.object_type} tmpl` : item.move.object.object_type;
                const escapedKey = Explorer.escapeJs(item.idx);
                html += `
                <div class="workspace-object-row pending" data-index="${Explorer.escapeHtml(item.idx)}" data-position="${item.position}" data-file="${Explorer.escapeHtml(filePath)}"
                     draggable="true"
                     ondragstart="Explorer.handleTargetObjectDragStart(event, '${escapedKey}', 'pending', '${Explorer.escapeJs(filePath)}')"
                     ondragend="Explorer.handleTargetObjectDragEnd(event)">
                    <span class="tree-drag-handle">${gripIcon}</span>
                    <span class="tree-object-type type-${item.move.object.object_type}">${typeLabel}</span>
                    <span class="tree-object-name" title="${Explorer.escapeHtml(pendingDisplayName)}">${Explorer.escapeHtml(pendingDisplayName)}</span>
                    <button class="tree-object-action" onclick="event.stopPropagation(); Explorer.undoObjectMove('${escapedKey}')" title="Undo move">${xIcon}</button>
                </div>
            `;
            } else if (item.type === 'creation') {
                const creationAttrs = item.creation.attributes || {};
                const isTemplate = creationAttrs.register === '0' ||
                    (item.creation.object_type === 'host' && creationAttrs.name && !creationAttrs.host_name) ||
                    (item.creation.object_type === 'service' && creationAttrs.name && !creationAttrs.service_description) ||
                    (item.creation.object_type === 'contact' && creationAttrs.name && !creationAttrs.contact_name);
                const typeLabel = isTemplate ? `${item.creation.object_type} tmpl` : item.creation.object_type;
                const creationDisplayName = item.creation.displayName || '(unnamed)';
                html += `
                <div class="workspace-object-row staged-creation" data-staged-index="${item.idx}" data-position="${item.position}" data-file="${Explorer.escapeHtml(filePath)}"
                     draggable="true"
                     ondragstart="Explorer.handleTargetObjectDragStart(event, ${item.idx}, 'creation', '${Explorer.escapeJs(filePath)}')"
                     ondragend="Explorer.handleTargetObjectDragEnd(event)">
                    <span class="tree-drag-handle">${gripIcon}</span>
                    <span class="tree-object-type type-${item.creation.object_type}">${typeLabel}</span>
                    <span class="tree-object-name" title="${Explorer.escapeHtml(creationDisplayName)}">${Explorer.escapeHtml(creationDisplayName)}</span>
                    <button class="tree-object-action" onclick="event.stopPropagation(); Explorer.removeStagedCreation(${item.idx})" title="Remove">${xIcon}</button>
                </div>
            `;
            }

            // Drop zone after each item
            html += `<div class="workspace-drop-zone" data-file="${Explorer.escapeHtml(filePath)}" data-position="${item.position + 0.5}"
                     ondragover="Explorer.handleObjectDragOver(event)"
                     ondrop="Explorer.handleObjectDrop(event, '${Explorer.escapeJs(filePath)}', ${item.position + 0.5})"
                     ondragleave="Explorer.handleObjectDragLeave(event)"></div>`;
        }

        if (items.length === 0) {
            html = `<div class="workspace-empty-file" data-file="${Explorer.escapeHtml(filePath)}"
                     ondragover="Explorer.handleObjectDragOver(event)"
                     ondrop="Explorer.handleObjectDrop(event, '${Explorer.escapeJs(filePath)}', 0)"
                     ondragleave="Explorer.handleObjectDragLeave(event)">
                    Empty file - drag objects here
                </div>`;
        }

        return html;
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
    // Drag and Drop Handlers
    // ============================================================================

    let fileHoverTimeout = null;
    let fileHoverTarget = null;

    function handleFileDragOver(event, filePath) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        event.currentTarget.classList.add('drop-active');

        // Auto-expand collapsed files after hovering for 800ms
        if (filePath && !state.expandedFiles.has(filePath)) {
            if (fileHoverTarget !== filePath) {
                // Clear any existing timeout if we moved to a different file
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
        // Only remove highlight if actually leaving the element (not entering a child)
        if (event.currentTarget.contains(event.relatedTarget)) return;
        event.currentTarget.classList.remove('drop-active');
        // Clear auto-expand timeout when leaving
        if (fileHoverTimeout) {
            clearTimeout(fileHoverTimeout);
            fileHoverTimeout = null;
            fileHoverTarget = null;
        }
    }

    function handleObjectDragOver(event) {
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.add('drop-active');
    }

    function handleObjectDragLeave(event) {
        if (event.currentTarget.contains(event.relatedTarget)) return;
        event.currentTarget.classList.remove('drop-active');
    }

    function handleTargetObjectDragStart(event, index, itemType, sourceFile) {
        event.stopPropagation();
        event.currentTarget.classList.add('dragging');

        // Set the data transfer with info about what's being dragged
        const dragData = {
            type: 'target-object-reorder',
            index: index,
            itemType: itemType,
            sourceFile: sourceFile
        };

        // For existing objects, include stable metadata to prevent wrong-object bugs
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

        event.dataTransfer.setData('text/plain', JSON.stringify(dragData));
        event.dataTransfer.effectAllowed = 'move';
    }

    function handleTargetObjectDragEnd(event) {
        event.currentTarget.classList.remove('dragging');
    }

    function handleObjectDrop(event, targetFile, position) {
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.remove('drop-active');

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
            let insertPos = position;
            data.indices.forEach(idx => {
                const creation = state.stagedCreations[idx];
                if (creation) {
                    const wasInDifferentFile = creation.targetFile !== targetFile;
                    creation.targetFile = targetFile;
                    creation.insertPosition = insertPos;
                    insertPos += 0.001;
                    if (wasInDifferentFile) moved++;
                }
            });
            state.expandedFiles.add(targetFile);
            Explorer.saveStagedChanges();
            Explorer.updateCommitUI();
            renderTargetPane();
            Explorer.buildTree();
            if (moved > 0) {
                showToast(`Moved ${moved} new object(s) to ${targetFile.split('/').pop()}`, 'info');
            }
            return;
        }

        // Handle reordering objects within the right panel
        if (data.type === 'target-object-reorder') {
            const { index, itemType, sourceFile, objectMeta } = data;

            if (itemType === 'existing') {
                let obj = null;
                if (objectMeta) {
                    obj = Explorer.findObjectByAttributes(objectMeta);
                }
                if (!obj) {
                    obj = state.allObjects.find(o => o.global_index === index);
                }

                if (obj) {
                    const objKey = Explorer.getObjectKey(obj);
                    const objData = {
                        source_file: obj.source_file,
                        object_type: obj.object_type,
                        name: obj.name,
                        display_name: obj.display_name,
                        attributes: obj.attributes
                    };
                    if (sourceFile === targetFile) {
                        state.stagedMoves.set(objKey, {
                            originalFile: obj.source_file,
                            targetFile: targetFile,
                            object: objData,
                            insertPosition: position
                        });
                        Explorer.saveStagedChanges();
                        Explorer.updateCommitUI();
                        renderTargetPane();
                        Explorer.buildTree();
                    } else {
                        state.stagedMoves.set(objKey, {
                            originalFile: obj.source_file,
                            targetFile: targetFile,
                            object: objData,
                            insertPosition: position
                        });
                        state.expandedFiles.add(targetFile);
                        Explorer.saveStagedChanges();
                        Explorer.updateCommitUI();
                        renderTargetPane();
                        Explorer.buildTree();
                        showToast(`Staged object to move. Use Commit to apply.`, 'info');
                    }
                } else {
                    console.warn('[drop] Could not find object for reorder:', objectMeta?.name || index);
                }
            } else if (itemType === 'pending') {
                const move = state.stagedMoves.get(index);
                if (move) {
                    move.targetFile = targetFile;
                    move.insertPosition = position;
                    Explorer.saveStagedChanges();
                    Explorer.updateCommitUI();
                    renderTargetPane();
                    Explorer.buildTree();
                    if (sourceFile !== targetFile) {
                        showToast(`Moved pending object to ${targetFile.split('/').pop()}`, 'info');
                    }
                }
            } else if (itemType === 'creation') {
                const creation = state.stagedCreations[index];
                if (creation) {
                    const wasInDifferentFile = creation.targetFile !== targetFile;
                    creation.targetFile = targetFile;
                    creation.insertPosition = position;
                    Explorer.saveStagedChanges();
                    Explorer.updateCommitUI();
                    renderTargetPane();
                    Explorer.buildTree();
                    if (wasInDifferentFile) {
                        showToast(`Moved new object to ${targetFile.split('/').pop()}`, 'info');
                    }
                }
            }
            return;
        }

        // Handle regular objects using stable keys
        let staged = 0;
        let insertPos = position;

        if (data.type === 'objects' && data.objects && data.objects.length > 0) {
            for (const objData of data.objects) {
                if (!objData || !objData.source_file) continue;

                if (objData.source_file === targetFile) continue;

                // Use same fallback logic as getObjectKey for null-safe key generation
                const nameComponent = objData.name ?? objData.display_name ?? `idx:${objData.global_index}`;
                const objKey = `${objData.source_file}|${objData.object_type}|${nameComponent}`;
                state.stagedMoves.set(objKey, {
                    originalFile: objData.source_file,
                    targetFile: targetFile,
                    object: {
                        source_file: objData.source_file,
                        object_type: objData.object_type,
                        name: objData.name,
                        display_name: objData.display_name || objData.name,
                        attributes: objData.attributes
                    },
                    insertPosition: insertPos
                });
                insertPos += 0.001;
                state.expandedFiles.add(targetFile);
                staged++;
            }
        }

        if (staged > 0) {
            showToast(`Staged ${staged} object(s) to move. Use Commit to apply.`, 'info');
            Explorer.saveStagedChanges();
            Explorer.updateCommitUI();
        }

        renderTargetPane();
        Explorer.buildTree();
    }

    function handleFileDrop(event, targetFile) {
        event.preventDefault();
        event.currentTarget.classList.remove('drop-active');

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
            // Find the highest position in target file to append at end
            const targetObjects = state.allObjects.filter(o => o.source_file === targetFile);
            let maxLine = targetObjects.reduce((max, o) => Math.max(max, o.line_number), 0);
            for (const [_, move] of state.stagedMoves) {
                if (move.targetFile === targetFile && move.insertPosition) {
                    maxLine = Math.max(maxLine, move.insertPosition);
                }
            }
            for (const c of state.stagedCreations) {
                if (c.targetFile === targetFile && c.insertPosition !== undefined) {
                    maxLine = Math.max(maxLine, c.insertPosition);
                }
            }

            let moved = 0;
            let alreadyInFile = 0;
            data.indices.forEach(idx => {
                const creation = state.stagedCreations[idx];
                if (creation) {
                    const wasInDifferentFile = creation.targetFile !== targetFile;
                    if (wasInDifferentFile) {
                        creation.targetFile = targetFile;
                        maxLine += 100;
                        creation.insertPosition = maxLine;
                        moved++;
                    } else {
                        alreadyInFile++;
                    }
                }
            });
            state.expandedFiles.add(targetFile);
            Explorer.saveStagedChanges();
            Explorer.updateCommitUI();
            renderTargetPane();
            Explorer.buildTree();
            if (moved > 0 && alreadyInFile > 0) {
                showToast(`Moved ${moved} new object(s) to ${targetFile.split('/').pop()}. ${alreadyInFile} already in file.`, 'info');
            } else if (moved > 0) {
                showToast(`Moved ${moved} new object(s) to ${targetFile.split('/').pop()}`, 'info');
            } else if (alreadyInFile > 0) {
                showToast(`${alreadyInFile === 1 ? 'Object' : 'All ' + alreadyInFile + ' objects'} already in ${targetFile.split('/').pop()}`, 'info');
            }
            return;
        }

        // Handle regular objects
        let staged = 0;
        let alreadyInFile = 0;
        let cancelled = 0;

        // Find the highest line number in target file to append at end
        const targetObjects = state.allObjects.filter(o => o.source_file === targetFile);
        let maxLine = targetObjects.reduce((max, o) => Math.max(max, o.line_number), 0);
        for (const [_, move] of state.stagedMoves) {
            if (move.targetFile === targetFile && move.insertPosition) {
                maxLine = Math.max(maxLine, move.insertPosition);
            }
        }

        const processObject = (objData) => {
            if (!objData) return;

            // Use same fallback logic as getObjectKey for null-safe key generation
            const nameComponent = objData.name ?? objData.display_name ?? `idx:${objData.global_index}`;
            const objKey = `${objData.source_file}|${objData.object_type}|${nameComponent}`;

            const existingMove = state.stagedMoves.get(objKey);

            if (existingMove && existingMove.originalFile === targetFile) {
                state.stagedMoves.delete(objKey);
                cancelled++;
            } else if (!existingMove && objData.source_file === targetFile) {
                alreadyInFile++;
            } else {
                maxLine += 100;
                state.stagedMoves.set(objKey, {
                    originalFile: existingMove ? existingMove.originalFile : objData.source_file,
                    targetFile: targetFile,
                    object: {
                        source_file: objData.source_file,
                        object_type: objData.object_type,
                        name: objData.name,
                        display_name: objData.display_name || objData.name,
                        attributes: objData.attributes
                    },
                    insertPosition: maxLine
                });
                state.expandedFiles.add(targetFile);
                staged++;
            }
        };

        if (data.type === 'objects' && data.objects && data.objects.length > 0) {
            for (const objData of data.objects) {
                processObject(objData);
            }
        }

        if (staged > 0 || cancelled > 0) {
            Explorer.saveStagedChanges();
            Explorer.updateCommitUI();
        }

        renderTargetPane();
        Explorer.buildTree();

        if (cancelled > 0 && staged === 0 && alreadyInFile === 0) {
            showToast(`${cancelled === 1 ? 'Object move' : cancelled + ' object moves'} cancelled`, 'info');
        } else if (staged > 0 && cancelled > 0) {
            showToast(`Staged ${staged} object(s). Cancelled ${cancelled} move(s).`, 'info');
        } else if (staged > 0 && alreadyInFile > 0) {
            showToast(`Staged ${staged} object(s) to move. ${alreadyInFile} already in file.`, 'info');
        } else if (staged > 0) {
            showToast(`Staged ${staged} object(s) to move. Use Commit to apply.`, 'info');
        } else if (alreadyInFile > 0) {
            const msg = `${alreadyInFile === 1 ? 'Object' : 'All ' + alreadyInFile + ' objects'} already in ${targetFile.split('/').pop()}`;
            showToast(msg, 'info');
        }
    }

    function removePendingMove(idx) {
        state.stagedMoves.delete(idx);
        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        renderTargetPane();
        Explorer.buildTree();
    }

    function undoObjectMove(idx) {
        removePendingMove(idx);
        showToast('Object move undone', 'info');
    }

    function undoNewFile(filePath, event) {
        if (event) {
            event.stopPropagation();
        }
        // Also remove any staged objects that were going to this new file
        for (const [idx, move] of state.stagedMoves) {
            if (move.targetFile === filePath) {
                state.stagedMoves.delete(idx);
            }
        }
        // Remove any staged creations targeting this file
        for (let i = state.stagedCreations.length - 1; i >= 0; i--) {
            if (state.stagedCreations[i].targetFile === filePath) {
                state.stagedCreations.splice(i, 1);
            }
        }
        state.newFiles.delete(filePath);
        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        renderTargetPane();
        showToast('New file removed', 'info');
    }

    function removeStagedCreation(idx) {
        state.stagedCreations.splice(idx, 1);
        // Reset editing state if we were editing this creation
        if (state.isNewObject && state.newObjectStagedIndex === idx) {
            state.isNewObject = false;
            state.newObjectStagedIndex = null;
            state.editedObject = null;
            Explorer.checkPendingExternalChanges();
            Explorer.hideCenterPaneObject();
        } else if (state.isNewObject && state.newObjectStagedIndex > idx) {
            state.newObjectStagedIndex--;
        }
        state.selectedStagedIndices.clear();
        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        renderTargetPane();
        Explorer.buildTree();
    }

    function getFilesInFolder(folderPath) {
        // Get files from existing objects
        const existingFiles = [...new Set(state.allObjects.map(o => o.source_file))]
            .filter(f => f.startsWith(folderPath + '/') && !f.substring(folderPath.length + 1).includes('/'));

        // Get new files in this folder
        const newFilesInFolder = [...state.newFiles]
            .filter(f => f.startsWith(folderPath + '/') && !f.substring(folderPath.length + 1).includes('/'));

        // Combine and dedupe
        return [...new Set([...existingFiles, ...newFilesInFolder])];
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

        // Auto-expand collapsed folders after hovering for 800ms
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
        if (event.currentTarget.contains(event.relatedTarget)) return;
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

        await Explorer.loadObjects();
        state.expandedFolders.add(targetFolder);
        Explorer.updateCommitUI();
        renderTargetPane();
        const displayName = targetFolder.split('/').pop() || 'config';
        showToast(`Moved file to ${displayName}/`, 'success');
    }

    async function moveFolderImmediate(sourcePath, targetFolder) {
        const result = await ApiClient.post('/api/folders/move', { sourcePath, targetFolder }, { silent: true });

        if (!result.success) {
            showToast(result.data?.error || result.error || 'Failed to move folder', 'error');
            return;
        }

        await Explorer.loadObjects();
        state.expandedFolders.add(targetFolder);
        Explorer.updateCommitUI();
        renderTargetPane();
        const displayName = targetFolder.split('/').pop() || 'config';
        showToast(`Moved folder to ${displayName}/`, 'success');
    }

    function handleFolderDrop(event, targetFolder) {
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.classList.remove('drop-active');

        // Clean up all drag state
        Explorer.cleanupDragState();

        const data = event.dataTransfer.getData('text/plain');
        const fileData = event.dataTransfer.getData('application/x-file-move');
        const folderData = event.dataTransfer.getData('application/x-folder-move');

        const effectiveTargetFolder = targetFolder;

        // Handle folder being dropped into another folder
        if (folderData) {
            const sourcePath = folderData;
            const folderName = sourcePath.split('/').pop();
            const sourceParent = sourcePath.substring(0, sourcePath.lastIndexOf('/'));

            // Can't move folder into itself or its children
            const normalizedSource = sourcePath.replace(/\/+$/, '');
            const normalizedTarget = targetFolder.replace(/\/+$/, '');

            if (normalizedTarget === normalizedSource ||
                normalizedTarget.startsWith(normalizedSource + '/')) {
                console.warn('Blocked circular folder move:', { sourcePath, targetFolder });
                showToast('Cannot move folder into itself or its children', 'warning');
                return;
            }

            if (sourceParent === effectiveTargetFolder) {
                showToast('Folder is already in this location', 'warning');
                return;
            }

            moveFolderImmediate(sourcePath, effectiveTargetFolder);
            return;
        }

        // Handle file being dropped into folder
        if (fileData) {
            const sourcePath = fileData;
            const fileName = sourcePath.split('/').pop();
            const sourceParent = sourcePath.substring(0, sourcePath.lastIndexOf('/'));
            const newPath = effectiveTargetFolder + '/' + fileName;
            const isNewFile = state.newFiles.has(sourcePath);

            // Handle new files (staged only, not on disk yet)
            if (isNewFile) {
                if (sourceParent === effectiveTargetFolder) {
                    showToast('File is already in this folder', 'warning');
                    return;
                }
                state.newFiles.delete(sourcePath);
                state.newFiles.add(newPath);

                // Update any staged creations that target this file
                for (const creation of state.stagedCreations) {
                    if (creation.targetFile === sourcePath) {
                        creation.targetFile = newPath;
                    }
                }

                state.expandedFolders.add(effectiveTargetFolder);
                Explorer.saveStagedChanges();
                Explorer.updateCommitUI();
                renderTargetPane();
                const displayName = effectiveTargetFolder.split('/').pop() || 'config';
                showToast(`Moved new file to ${displayName}/`, 'info');
                return;
            }

            if (sourceParent === effectiveTargetFolder) {
                showToast('File is already in this folder', 'warning');
                return;
            }

            moveFileImmediate(sourcePath, effectiveTargetFolder);
            return;
        }

        // Handle objects being dropped into folder
        if (data) {
            try {
                const parsedData = JSON.parse(data);

                // Handle staged creations being moved to folder
                if (parsedData.type === 'staged-creations') {
                    const filesInFolder = getFilesInFolder(effectiveTargetFolder);

                    let targetFile;
                    if (filesInFolder.length === 0) {
                        targetFile = effectiveTargetFolder + '/objects.cfg';
                        state.newFiles.add(targetFile);
                    } else if (filesInFolder.length === 1) {
                        targetFile = filesInFolder[0];
                    } else {
                        state.expandedFolders.add(targetFolder);
                        showToast('Multiple files in folder. Drop objects on a specific file.', 'info');
                        renderTargetPane();
                        return;
                    }

                    // Find the highest position in target file to append at end
                    const targetObjects = state.allObjects.filter(o => o.source_file === targetFile);
                    let maxLine = targetObjects.reduce((max, o) => Math.max(max, o.line_number), 0);
                    for (const [_, move] of state.stagedMoves) {
                        if (move.targetFile === targetFile && move.insertPosition) {
                            maxLine = Math.max(maxLine, move.insertPosition);
                        }
                    }
                    for (const c of state.stagedCreations) {
                        if (c.targetFile === targetFile && c.insertPosition !== undefined) {
                            maxLine = Math.max(maxLine, c.insertPosition);
                        }
                    }

                    let moved = 0;
                    parsedData.indices.forEach(idx => {
                        const creation = state.stagedCreations[idx];
                        if (creation) {
                            const wasInDifferentFile = creation.targetFile !== targetFile;
                            creation.targetFile = targetFile;
                            maxLine += 100;
                            creation.insertPosition = maxLine;
                            if (wasInDifferentFile) moved++;
                        }
                    });

                    state.expandedFiles.add(targetFile);
                    state.expandedFolders.add(targetFolder);
                    Explorer.saveStagedChanges();
                    Explorer.updateCommitUI();
                    renderTargetPane();
                    Explorer.buildTree();
                    if (moved > 0) {
                        showToast(`Moved ${moved} new object(s) to ${targetFile.split('/').pop()}`, 'info');
                    }
                    return;
                }

                // Handle regular objects
                const indices = Array.isArray(parsedData) ? parsedData : parsedData.indices;

                const filesInFolder = getFilesInFolder(effectiveTargetFolder);

                if (filesInFolder.length === 0) {
                    const newFile = effectiveTargetFolder + '/objects.cfg';
                    state.newFiles.add(newFile);
                    state.expandedFiles.add(newFile);

                    let staged = 0;
                    for (const idx of indices) {
                        const obj = state.allObjects.find(o => o.global_index === idx);
                        if (obj && obj.source_file !== newFile) {
                            const objKey = Explorer.getObjectKey(obj);
                            state.stagedMoves.set(objKey, {
                                originalFile: obj.source_file,
                                targetFile: newFile,
                                object: {
                                    source_file: obj.source_file,
                                    object_type: obj.object_type,
                                    name: obj.name,
                                    display_name: obj.display_name,
                                    attributes: obj.attributes
                                },
                                insertPosition: Infinity
                            });
                            staged++;
                        }
                    }

                    if (staged > 0) {
                        showToast(`Created ${newFile.split('/').pop()} and staged ${staged} object(s). Commit to apply.`, 'info');
                        Explorer.saveStagedChanges();
                        Explorer.updateCommitUI();
                    }
                } else if (filesInFolder.length === 1) {
                    const targetFile = filesInFolder[0];
                    let staged = 0;
                    for (const idx of indices) {
                        const obj = state.allObjects.find(o => o.global_index === idx);
                        if (obj && obj.source_file !== targetFile) {
                            const objKey = Explorer.getObjectKey(obj);
                            state.stagedMoves.set(objKey, {
                                originalFile: obj.source_file,
                                targetFile: targetFile,
                                object: {
                                    source_file: obj.source_file,
                                    object_type: obj.object_type,
                                    name: obj.name,
                                    display_name: obj.display_name,
                                    attributes: obj.attributes
                                },
                                insertPosition: Infinity
                            });
                            staged++;
                        }
                    }
                    if (staged > 0) {
                        showToast(`Staged ${staged} object(s) to ${targetFile.split('/').pop()}. Commit to apply.`, 'info');
                        Explorer.saveStagedChanges();
                        Explorer.updateCommitUI();
                    }
                } else {
                    state.expandedFolders.add(targetFolder);
                    showToast('Multiple files in folder. Drop objects on a specific file.', 'info');
                }

                renderTargetPane();
                Explorer.buildTree();
            } catch (e) {
                console.error('Error handling folder drop:', e);
            }
        }
    }

    function handleFileDragStart(event, filePath) {
        const target = event.currentTarget || event.target;
        if (!target) return;

        if (state.newFiles.has(filePath)) {
            event.dataTransfer.setData('application/x-new-file-move', filePath);
        }
        event.dataTransfer.setData('application/x-file-move', filePath);
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
        if (!target) return;
        event.dataTransfer.setData('application/x-folder-move', folderPath);
        event.dataTransfer.effectAllowed = 'move';

        target.style.opacity = '0.5';

        target.addEventListener('dragend', () => {
            target.style.opacity = '';
        }, { once: true });
    }

    // ============================================================================
    // Deletion Functions
    // ============================================================================

    async function stageDeleteFile(filePath, event) {
        if (event) {
            event.stopPropagation();
        }

        // Don't allow deleting new files that haven't been committed yet
        if (state.newFiles.has(filePath)) {
            state.newFiles.delete(filePath);
            state.stagedCreations = state.stagedCreations.filter(c => c.targetFile !== filePath);
            Explorer.saveStagedChanges();
            Explorer.updateCommitUI();
            renderTargetPane();
            showToast('Removed new file', 'info');
            return;
        }

        // C-08: Check if there are staged object moves targeting this file
        const movesToThisFile = state.stagedMoves.filter(move => {
            const targetFile = move[1]?.targetFile || move.targetFile;
            return targetFile === filePath;
        });

        if (movesToThisFile.length > 0) {
            const confirmed = await showConfirmDialog({
                title: 'File Has Pending Moves',
                message: `${movesToThisFile.length} object(s) are being moved to this file. Deleting the file will remove those pending moves.`,
                confirmText: 'Delete Anyway',
                cancelText: 'Cancel',
                type: 'warning'
            });

            if (!confirmed) {
                return;
            }

            // Remove the staged moves targeting this file
            state.stagedMoves = state.stagedMoves.filter(move => {
                const targetFile = move[1]?.targetFile || move.targetFile;
                return targetFile !== filePath;
            });
        }

        // Delete file immediately via API
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

        await Explorer.loadStagedChanges(false);
        Explorer.updateCommitUI();
        renderTargetPane();
        showToast(`Staged deletion of "${filePath.split('/').pop()}"`, 'info');
    }

    async function stageDeleteFolder(folderPath, event) {
        if (event) {
            event.stopPropagation();
        }

        if (folderPath === state.configPath) {
            showToast('Cannot delete the config root folder', 'error');
            return;
        }

        // C-08: Check if there are staged object moves targeting files in this folder
        const movesToThisFolder = state.stagedMoves.filter(move => {
            const targetFile = move[1]?.targetFile || move.targetFile;
            return targetFile && targetFile.startsWith(folderPath + '/');
        });

        if (movesToThisFolder.length > 0) {
            const confirmed = await showConfirmDialog({
                title: 'Folder Has Pending Moves',
                message: `${movesToThisFolder.length} object(s) are being moved to files in this folder. Deleting the folder will remove those pending moves.`,
                confirmText: 'Delete Anyway',
                cancelText: 'Cancel',
                type: 'warning'
            });

            if (!confirmed) {
                return;
            }

            // Remove the staged moves targeting files in this folder
            state.stagedMoves = state.stagedMoves.filter(move => {
                const targetFile = move[1]?.targetFile || move.targetFile;
                return !targetFile || !targetFile.startsWith(folderPath + '/');
            });
        }

        // Remove any new files (staged only) that are inside this folder
        let hadStagedFiles = false;
        for (const newFile of [...state.newFiles]) {
            if (newFile.startsWith(folderPath + '/')) {
                state.newFiles.delete(newFile);
                hadStagedFiles = true;
            }
        }
        const prevLen = state.stagedCreations.length;
        state.stagedCreations = state.stagedCreations.filter(c => !c.targetFile.startsWith(folderPath + '/'));
        if (hadStagedFiles || state.stagedCreations.length !== prevLen) {
            Explorer.saveStagedChanges();
        }

        // Delete folder immediately via API
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

        await Explorer.loadStagedChanges(false);
        Explorer.updateCommitUI();
        renderTargetPane();
        showToast(`Staged deletion of "${folderPath.split('/').pop()}/"`, 'info');
    }

    async function unstageFileDeletion(filePath, event) {
        if (event) {
            event.stopPropagation();
        }

        state.stagedFileDeletions = (state.stagedFileDeletions || []).filter(d => d.path !== filePath);

        Explorer.saveStagedChanges();
        await Explorer.loadStagedChanges(false);

        Explorer.updateCommitUI();
        renderTargetPane();
        showToast(`Unstaged deletion of "${filePath.split('/').pop()}"`, 'info');
    }

    async function unstageFolderDeletion(folderPath, event) {
        if (event) {
            event.stopPropagation();
        }

        state.stagedFolderDeletions = (state.stagedFolderDeletions || []).filter(d => d.path !== folderPath);

        Explorer.saveStagedChanges();
        await Explorer.loadStagedChanges(false);

        Explorer.updateCommitUI();
        renderTargetPane();
        showToast(`Unstaged deletion of "${folderPath.split('/').pop()}/"`, 'info');
    }

    async function unstageFolderCreation(folderPath, event) {
        if (event) {
            event.stopPropagation();
        }

        state.stagedFolderCreations = (state.stagedFolderCreations || []).filter(c => c.path !== folderPath);

        Explorer.saveStagedChanges();
        await Explorer.loadStagedChanges(false);

        Explorer.updateCommitUI();
        renderTargetPane();
        showToast(`Unstaged folder "${folderPath.split('/').pop()}/"`, 'info');
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

        let basePath = state.configPath;

        const isFolder = name.endsWith('/');

        if (isFolder) {
            name = name.slice(0, -1);
            const fullPath = basePath + '/' + name;

            if (state.existingFolders.includes(fullPath)) {
                showToast('Folder already exists', 'warning');
                return;
            }
            const isStagedForCreation = (state.stagedFolderCreations || []).some(c => c.path === fullPath);
            if (isStagedForCreation) {
                showToast('Folder already staged for creation', 'warning');
                return;
            }

            const result = await ApiClient.post('/api/folders', { path: fullPath }, { silent: true });

            if (!result.success) {
                showToast(result.data?.error || result.error || 'Failed to stage folder creation', 'error');
                return;
            }

            await Explorer.loadStagedChanges(false);

            state.expandedFolders.add(fullPath);
            document.getElementById('newItemName').value = '';
            Explorer.updateCommitUI();
            renderTargetPane();
            showToast(`Staged folder "${name}/". Use Commit to apply.`, 'info');
            return;
        }

        // Stage file creation
        if (!name.endsWith('.cfg')) {
            name += '.cfg';
        }

        const fullPath = basePath + '/' + name;

        const existingFiles = [...new Set(state.allObjects.map(o => o.source_file))];
        if (existingFiles.includes(fullPath) || state.newFiles.has(fullPath)) {
            showToast('File already exists', 'warning');
            return;
        }

        state.newFiles.add(fullPath);
        state.expandedFiles.add(fullPath);
        document.getElementById('newItemName').value = '';
        Explorer.saveStagedChanges();
        Explorer.updateCommitUI();
        renderTargetPane();
        showToast(`Staged new file "${name}". Commit to create.`, 'info');
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
        if (!container) return;

        // Remove any existing inline edit
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

        const basePath = state.configPath;

        if (type === 'folder') {
            if (name.endsWith('/')) {
                name = name.slice(0, -1);
            }

            const fullPath = basePath + '/' + name;

            if (state.existingFolders.includes(fullPath)) {
                showToast('Folder already exists', 'warning');
                row.remove();
                return;
            }

            const isStagedForCreation = (state.stagedFolderCreations || []).some(c => c.path === fullPath);
            if (isStagedForCreation) {
                showToast('Folder already staged for creation', 'warning');
                row.remove();
                return;
            }

            const result = await ApiClient.post('/api/folders', { path: fullPath }, { silent: true });

            if (!result.success) {
                showToast(result.data?.error || result.error || 'Failed to stage folder creation', 'error');
                row.remove();
                return;
            }

            await Explorer.loadStagedChanges(false);

            state.expandedFolders.add(fullPath);
            row.remove();
            Explorer.updateCommitUI();
            renderTargetPane();
            showToast(`Staged folder "${name}/". Use Commit to apply.`, 'info');
        } else {
            name = name.replace(/\.cfg$/i, '');
            if (!name) {
                row.remove();
                return;
            }
            name += '.cfg';

            const fullPath = basePath + '/' + name;

            const existingFiles = [...new Set(state.allObjects.map(o => o.source_file))];
            if (existingFiles.includes(fullPath) || state.newFiles.has(fullPath)) {
                showToast('File already exists', 'warning');
                row.remove();
                return;
            }

            state.newFiles.add(fullPath);
            state.expandedFiles.add(fullPath);
            row.remove();
            Explorer.saveStagedChanges();
            Explorer.updateCommitUI();
            renderTargetPane();
            showToast(`Staged new file "${name}". Commit to create.`, 'info');
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
    Explorer.renderFileObjects = renderFileObjects;
    Explorer.toggleFileExpand = toggleFileExpand;
    Explorer.handleFileDragOver = handleFileDragOver;
    Explorer.handleFileDragLeave = handleFileDragLeave;
    Explorer.handleObjectDragOver = handleObjectDragOver;
    Explorer.handleObjectDragLeave = handleObjectDragLeave;
    Explorer.handleTargetObjectDragStart = handleTargetObjectDragStart;
    Explorer.handleTargetObjectDragEnd = handleTargetObjectDragEnd;
    Explorer.handleObjectDrop = handleObjectDrop;
    Explorer.handleFileDrop = handleFileDrop;
    Explorer.removePendingMove = removePendingMove;
    Explorer.undoObjectMove = undoObjectMove;
    Explorer.undoNewFile = undoNewFile;
    Explorer.removeStagedCreation = removeStagedCreation;
    Explorer.getFilesInFolder = getFilesInFolder;
    Explorer.handleFolderDragOver = handleFolderDragOver;
    Explorer.handleFolderDragLeave = handleFolderDragLeave;
    Explorer.moveFileImmediate = moveFileImmediate;
    Explorer.moveFolderImmediate = moveFolderImmediate;
    Explorer.handleFolderDrop = handleFolderDrop;
    Explorer.handleFileDragStart = handleFileDragStart;
    Explorer.handleFolderDragStart = handleFolderDragStart;
    Explorer.stageDeleteFile = stageDeleteFile;
    Explorer.stageDeleteFolder = stageDeleteFolder;
    Explorer.unstageFileDeletion = unstageFileDeletion;
    Explorer.unstageFolderDeletion = unstageFolderDeletion;
    Explorer.unstageFolderCreation = unstageFolderCreation;
    Explorer.createNewItem = createNewItem;
    Explorer.createInlineFile = createInlineFile;
    Explorer.createInlineFolder = createInlineFolder;
    Explorer.createInlineItem = createInlineItem;
    Explorer.confirmInlineCreate = confirmInlineCreate;

})(Explorer);
