/** Explorer File Operations Module - Target pane rendering, file/folder operations, drag-drop in workspace
 *
 * Shadow copy architecture: all mutations go through API endpoints that operate
 * on the shadow copy. No local staging state. After mutation, call
 * afterFrontendMutation() to reload data + rebuild UI.
 */

import { state } from './state.js';
import { constants, isObjectTemplate, getTypeBadge, getTypeBadgeTier } from './constants.js';
import { getObjectKey, findObjectByKey, getSelectedIndices, groupByType, getConfigRootName } from './main.js';
import { isSelectedByIndex, clearSelection, addToSelectionByIndex, removeFromSelectionByIndex } from './state-management.js';
import { afterFrontendMutation, loadObjects, getStagingHeaders } from './data-loading.js'; // circular — safe (function-level)
import { showCenterPaneObject, hideCenterPaneObject, checkForChanges } from './object-editor.js'; // circular — safe (function-level)
import { getEffectiveAttributes, getEffectiveName } from './app.js'; // circular — safe (function-level)
import { openTab } from './tab-manager.js'; // circular — safe (function-level)
import { getIcon, handleApiError, toRelativePath, toDisplayPath, extractFileName, updateBadge } from './ui-utils.js';
import { refreshPanelTiers } from './panel-resizer.js';
import { cleanupDragState } from './drag-drop.js';
import { buildTree, updateSelection, selectObjectByIndex } from './app.js'; // circular — safe (function-level)
import { ApiClient } from '../api-client.js';
import { showToast, showConfirmDialog } from '../ui-notifications.js';
import { escapeHtml } from '../app.js';
import { escapeJs } from '../base.js';
import { StableKey } from '../stable-key.js';

// Data transfer types for drag-drop operations
const DATA_TYPES = {
    OBJECTS: 'text/plain',
    FILE_MOVE: 'application/x-file-move',
    FOLDER_MOVE: 'application/x-folder-move'
};

/**
 * After moving an object between files, update selectedKeys, tabs, and
 * editedObject so they reference the new source_file.
 */
function migrateKeysAfterMove(oldSourceFile, newSourceFile, objectType, nameComponent) {
    const oldKey = `${oldSourceFile}|${objectType}|${nameComponent}`;
    const newKey = `${newSourceFile}|${objectType}|${nameComponent}`;

    if (state.selectedKeys.has(oldKey)) {
        state.selectedKeys.delete(oldKey);
        state.selectedKeys.add(newKey);
    }
    if (state.activeTabKey === oldKey) {
        state.activeTabKey = newKey;
    }
    if (state.openTabs) {
        for (const tab of state.openTabs) {
            if (tab.key === oldKey) {tab.key = newKey;}
        }
    }
    if (state.editedObject && getObjectKey(state.editedObject) === oldKey) {
        state.editedObject.source_file = newSourceFile;
    }
}

// ============================================================================
// Navigation
// ============================================================================

export function navigateToObjectByIndex(index) {
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
        buildTree();
    }

    // Expand the parent folder based on current view (via state, not DOM)
    const viewBtn = document.querySelector('.view-btn[data-view="file"]');
    const isFileView = viewBtn ? viewBtn.classList.contains('active') : true;

    if (isFileView) {
        state.leftTreeExpansion.add(obj.source_file);
    } else {
        state.leftTreeExpansion.add('type:' + obj.object_type);
    }
    buildTree();

    // Open as tab (handles selection sync and center pane rendering)
    openTab(obj);

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

/**
 * Scroll a file row into view in the right pane after a rebuild.
 * Used after drag-drop moves to keep the drop target visible.
 */
function scrollTargetFileIntoView(filePath) {
    const container = document.getElementById('targetPaneContent');
    if (!container) {return;}
    const row = Array.from(container.querySelectorAll('.workspace-tree-row[data-file]'))
        .find(el => el.dataset.file === filePath);
    if (row) {row.scrollIntoView({ block: 'nearest' });}
}

export function selectObjectByName(name) {
    const obj = state.allObjects.find(o => o.name === name || o.display_name === name);
    if (obj) {
        navigateToObjectByIndex(obj.global_index);
    }
}

// ============================================================================
// Target Pane (Right Side File Browser) - Setup
// ============================================================================

export function initTargetPane() {
    // Expansion state is restored early in DOMContentLoaded. Apply defaults here
    // since configPath is guaranteed set by this point.
    if (state.rightTreeExpansion.size === 0 && state.configPath) {
        state.rightTreeExpansion.add(state.configPath);
    }
    if (!state.selectedFolder && state.configPath) {
        state.selectedFolder = state.configPath;
    }
    initWorkspaceToolbar();
    renderTargetPane();
}

export function initWorkspaceToolbar() {
    const createMenuBtn = document.getElementById('createMenuBtn');
    const collapseAllBtn = document.getElementById('collapseAllBtn');
    const refreshBtn = document.getElementById('refreshBtn');
    const workspaceRootIcon = document.getElementById('workspaceRootIcon');
    const newFileIcon = document.getElementById('newFileIcon');
    const newFolderIcon = document.getElementById('newFolderIcon');

    if (createMenuBtn) {createMenuBtn.innerHTML = getIcon('plus');}
    if (collapseAllBtn) {collapseAllBtn.innerHTML = getIcon('minimize-2');}
    if (refreshBtn) {refreshBtn.innerHTML = getIcon('refresh-cw');}
    if (workspaceRootIcon) {workspaceRootIcon.innerHTML = getIcon('folder-open');}
    if (newFileIcon) {newFileIcon.innerHTML = getIcon('file-plus');}
    if (newFolderIcon) {newFolderIcon.innerHTML = getIcon('folder-plus');}

    document.addEventListener('click', function(event) {
        const dropdown = document.getElementById('createDropdownMenu');
        const btn = document.getElementById('createMenuBtn');
        if (dropdown && btn && !dropdown.contains(event.target) && !btn.contains(event.target)) {
            dropdown.classList.remove('visible');
        }
    });
}

export function toggleCreateMenu(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('createDropdownMenu');
    if (dropdown) {
        dropdown.classList.toggle('visible');
    }
}

export function showCreateInput(type) {
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

export function hideCreateInput() {
    const inlineCreate = document.getElementById('workspaceCreateInline');
    if (inlineCreate) {inlineCreate.classList.remove('visible');}
}

export function handleCreateKeydown(event) {
    if (event.key === 'Enter') {
        createNewItem();
    } else if (event.key === 'Escape') {
        hideCreateInput();
    }
}

export function collapseAllFolders() {
    state.rightTreeExpansion.clear();
    state.rightTreeExpansion.save(state.configPath);
    renderTargetPane();
}

export function refreshWorkspace() {
    loadObjects().then(() => {
        renderTargetPane();
    });
}

export function updateWorkspaceHeader() {
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
    const escaped = escapeJs(path);
    if (isFolder) {
        return `<button class="tree-action-btn tree-action-btn--danger" onclick="event.stopPropagation(); Explorer.deleteFolder('${escaped}', event)" title="Delete folder">${getIcon('trash-2')}</button>`;
    }
    return `<button class="tree-action-btn tree-action-btn--danger" onclick="event.stopPropagation(); Explorer.deleteFile('${escaped}', event)" title="Delete file">${getIcon('trash-2')}</button>`;
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

export function renderTargetPane() {
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
        const isExpanded = state.rightTreeExpansion.has(folder.path);
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

        const expandIcon = hasChildren ? getIcon('chevron-right') : '';
        const folderIcon = isExpanded ? getIcon('folder-open') : getIcon('folder');

        const folderStatus = getFolderChangeStatus(folder.path);
        const rowClasses = buildRowClasses('workspace-tree-row', [
            ['expanded', isExpanded], ['selected', isSelected],
            ['staged-new', folderStatus === 'added'], ['staged-move', folderStatus === 'modified']
        ]);

        const actionHtml = canDelete ? buildDeleteButton(folder.path, true) : '';
        const indicatorHtml = buildChangeIndicator(folderStatus);

        let html = `
        <div class="${rowClasses}" data-depth="${depth}" data-folder="${escapeHtml(folder.path)}"
             onclick="Explorer.selectFolder('${escapeJs(folder.path)}')"
             ondragover="Explorer.handleDragExpandOver(event, '${escapeJs(folder.path)}')"
             ondrop="Explorer.handleFolderDrop(event, '${escapeJs(folder.path)}')"
             ondragleave="Explorer.handleDragExpandLeave(event)"
             draggable="${canDrag ? 'true' : 'false'}"
             ondragstart="Explorer.handleFolderDragStart(event, '${escapeJs(folder.path)}')">
            <button class="tree-expand-btn${isExpanded ? ' expanded' : ''}" onclick="event.stopPropagation(); Explorer.toggleFolderExpand('${escapeJs(folder.path)}')">${expandIcon}</button>
            <span class="tree-icon tree-icon--folder${isExpanded ? ' expanded' : ''}">${folderIcon}</span>
            <span class="tree-label tree-label--folder">${escapeHtml(name)}</span>
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
        const isExpanded = state.rightTreeExpansion.has(file.path);
        const hasObjects = fileObjects.length > 0;

        const expandIcon = hasObjects ? getIcon('chevron-right') : '';
        const fileStatus = getFileChangeStatus(file.path);
        const isNew = fileStatus === 'added';
        const fileIcon = isNew ? getIcon('file-plus') : getIcon('file-text');

        const rowClasses = buildRowClasses('workspace-tree-row', [
            ['expanded', isExpanded],
            ['staged-new', isNew], ['staged-move', fileStatus === 'modified'],
            ['staged-deletion', fileStatus === 'deleted']
        ]);

        const actionHtml = buildDeleteButton(file.path, false);
        const indicatorHtml = buildChangeIndicator(fileStatus);

        let html = `
        <div class="${rowClasses}" data-depth="${depth}" data-file="${escapeHtml(file.path)}"
             onclick="Explorer.toggleFileExpand('${escapeJs(file.path)}')"
             ondragover="Explorer.handleDragExpandOver(event, '${escapeJs(file.path)}')"
             ondrop="Explorer.handleFileDrop(event, '${escapeJs(file.path)}')"
             ondragleave="Explorer.handleDragExpandLeave(event)"
             draggable="true"
             ondragstart="Explorer.handleFileDragStart(event, '${escapeJs(file.path)}')">
            ${hasObjects ? `<button class="tree-expand-btn${isExpanded ? ' expanded' : ''}" onclick="event.stopPropagation(); Explorer.toggleFileExpand('${escapeJs(file.path)}')">${expandIcon}</button>` : '<span class="tree-expand-placeholder"></span>'}
            <span class="tree-icon tree-icon--file${isNew ? '-new' : ''}">${fileIcon}</span>
            <span class="tree-label${isNew ? ' tree-label--staged' : ''}${fileStatus === 'deleted' ? ' tree-label--deleted' : ''}">${escapeHtml(file.name)}</span>
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
    const isRootExpanded = state.rightTreeExpansion.has(state.configPath);
    const isRootSelected = state.selectedFolder === state.configPath;
    const hasRootChildren = rootFolderNames.length > 0 || root.files.length > 0;

    let totalRootObjects = root.files.reduce((sum, f) => {
        return sum + state.allObjects.filter(o => o.source_file === f.path).length;
    }, 0);
    for (const subName of rootFolderNames) {
        totalRootObjects += countFolderObjects(root.folders[subName]);
    }

    const rootExpandIcon = hasRootChildren ? getIcon('chevron-right') : '';
    const rootFolderIcon = isRootExpanded ? getIcon('folder-open') : getIcon('folder');

    html += `
    <div class="workspace-tree-row workspace-tree-row--root${isRootExpanded ? ' expanded' : ''}${isRootSelected ? ' selected' : ''}" data-depth="0" data-folder="${escapeHtml(state.configPath)}"
         onclick="Explorer.selectFolder('${escapeJs(state.configPath)}')"
         ondragover="Explorer.handleDragExpandOver(event, '${escapeJs(state.configPath)}')"
         ondrop="Explorer.handleFolderDrop(event, '${escapeJs(state.configPath)}')"
         ondragleave="Explorer.handleDragExpandLeave(event)">
        <button class="tree-expand-btn${isRootExpanded ? ' expanded' : ''}" onclick="event.stopPropagation(); Explorer.toggleFolderExpand('${escapeJs(state.configPath)}')">${rootExpandIcon}</button>
        <span class="tree-icon tree-icon--folder${isRootExpanded ? ' expanded' : ''}">${rootFolderIcon}</span>
        <span class="tree-label tree-label--folder tree-label--root">${escapeHtml(rootName)}</span>
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

    refreshPanelTiers();
}

export function toggleFolderExpand(folderPath) {
    state.rightTreeExpansion.toggle(folderPath);
    state.selectedFolder = folderPath;
    renderTargetPane();
}

export function selectFolder(folderPath) {
    state.selectedFolder = folderPath;
    if (!state.rightTreeExpansion.has(folderPath)) {
        state.rightTreeExpansion.add(folderPath);
    }
    renderTargetPane();
}

// ============================================================================
// File Object Rendering
// ============================================================================

function isObjectCreated(obj) {
    if (state.createdObjectKeys.size === 0) { return false; }
    const relPath = toRelativePath(obj.source_file);
    const name = obj.display_name ?? obj.name ?? ('idx:' + obj.global_index);
    return state.createdObjectKeys.has(relPath + '|' + obj.object_type + '|' + name);
}

function isObjectChanged(obj) {
    if (state.changedObjectKeys.size === 0) { return false; }
    const relPath = toRelativePath(obj.source_file);
    const name = obj.display_name ?? obj.name ?? ('idx:' + obj.global_index);
    return state.changedObjectKeys.has(relPath + '|' + obj.object_type + '|' + name);
}

function buildExistingObjectRow(obj, gripIcon, filePath) {
    const displayName = obj.display_name || obj.name || '(unnamed)';
    const isTemplate = isObjectTemplate(obj);
    const typeLabel = getTypeBadge(obj.object_type, isTemplate);
    const changedClass = isObjectCreated(obj) ? ' staged-creation' : isObjectChanged(obj) ? ' is-changed' : '';
    return `
        <div class="workspace-object-row${changedClass}" data-index="${obj.global_index}" data-file="${escapeHtml(filePath)}"
             draggable="true"
             ondragstart="Explorer.handleTargetObjectDragStart(event, ${obj.global_index}, 'existing', '${escapeJs(filePath)}')"
             ondragend="Explorer.handleTargetObjectDragEnd(event)">
            <span class="tree-drag-handle">${gripIcon}</span>
            <span class="tree-object-type type-${obj.object_type}" data-badge-compact="${getTypeBadgeTier(obj.object_type, isTemplate, 'compact')}" data-badge-medium="${getTypeBadgeTier(obj.object_type, isTemplate, 'medium')}" data-badge-full="${getTypeBadgeTier(obj.object_type, isTemplate, 'full')}">${typeLabel}</span>
            <span class="tree-object-name" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</span>
        </div>`;
}

export function renderFileObjects(filePath, fileObjects, depth = 2) {
    const sortedObjects = [...fileObjects].sort((a, b) => a.line_number - b.line_number);
    const gripIcon = getIcon('grip-vertical');

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
        html = `<div class="workspace-empty-file" data-file="${escapeHtml(filePath)}">
                Empty file
            </div>`;
    }

    return html;
}

function buildDropZone(filePath, position) {
    return `<div class="workspace-drop-zone" data-file="${escapeHtml(filePath)}" data-position="${position}"
             ondragover="Explorer.handleObjectDragOver(event)"
             ondrop="Explorer.handleObjectDrop(event, '${escapeJs(filePath)}', ${position})"
             ondragleave="Explorer.handleObjectDragLeave(event)"></div>`;
}

export function handleObjectDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'move';
    event.currentTarget.classList.add('drop-active');
}

export function handleObjectDragLeave(event) {
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

export async function handleObjectDrop(event, targetFile, position) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drop-active');
    cleanupDragState();

    const objects = parseDragObjects(event.dataTransfer.getData('text/plain'));
    if (!objects) {return;}
    const valid = objects.filter(o => o?.source_file);
    if (valid.length === 0) {return;}

    const stableKeys = valid
        .map(o => `${o.source_file}|${o.object_type}|${o.display_name ?? o.name ?? ''}`);

    const payload = { stable_keys: stableKeys, target_file: targetFile };
    if (position > 0) {payload.after_line = position;}

    const result = await ApiClient.post('/api/move-objects', payload, { silent: true });

    let moved = 0;
    if (result.success && result.data?.moved > 0) {
        moved = result.data.moved;
        for (const o of valid) {
            if (o.source_file !== targetFile) {
                migrateKeysAfterMove(o.source_file, targetFile, o.object_type, o.display_name ?? o.name ?? '');
            }
        }
    }

    if (moved > 0) {
        state.rightTreeExpansion.add(targetFile);
        await afterFrontendMutation();
        showToast(`Moved ${moved} object(s) to ${extractFileName(targetFile)}`, 'success');
    }
}

export function toggleFileExpand(filePath) {
    state.rightTreeExpansion.toggle(filePath);
    renderTargetPane();
}

// ============================================================================
// Drag and Drop Handlers - Files and Folders
// ============================================================================

const dragExpand = state.rightTreeExpansion.createDragHoverHandler(renderTargetPane);
export const handleDragExpandOver = dragExpand.onDragOver;
export const handleDragExpandLeave = dragExpand.onDragLeave;

export async function handleFileDrop(event, targetFile) {
    event.preventDefault();
    event.currentTarget.classList.remove('drop-active');
    cleanupDragState();

    const objects = parseDragObjects(event.dataTransfer.getData('text/plain'));
    if (!objects) {return;}

    const stableKeys = objects
        .filter(o => o?.source_file && o.source_file !== targetFile)
        .map(o => `${o.source_file}|${o.object_type}|${o.display_name ?? o.name ?? ''}`);
    if (stableKeys.length === 0) {return;}

    const result = await ApiClient.post('/api/move-objects', {
        stable_keys: stableKeys,
        target_file: targetFile
    }, { silent: true });

    if (result.success && result.data?.moved > 0) {
        for (const o of objects) {
            if (o?.source_file && o.source_file !== targetFile) {
                migrateKeysAfterMove(o.source_file, targetFile, o.object_type, o.display_name ?? o.name ?? '');
            }
        }
        await afterFrontendMutation();
        scrollTargetFileIntoView(targetFile);
        showToast(`Moved ${result.data.moved} object(s) to ${extractFileName(targetFile)}`, 'success');
    }
}

export function handleTargetObjectDragStart(event, index, itemType, sourceFile) {
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

export function handleTargetObjectDragEnd(event) {
    event.currentTarget.classList.remove('dragging');
}

// ============================================================================
// Folder Drag and Drop
// ============================================================================

export async function moveFileImmediate(sourcePath, targetFolder) {
    const result = await ApiClient.post('/api/files/move', { sourcePath, targetFolder }, { silent: true });

    if (!result.success) {
        showToast(result.data?.error || result.error || 'Failed to move file', 'error');
        return;
    }

    state.rightTreeExpansion.add(targetFolder);
    await afterFrontendMutation();
    showToast(`Moved file to ${extractFileName(targetFolder)}/`, 'success');
}

export async function moveFolderImmediate(sourcePath, targetFolder) {
    const result = await ApiClient.post('/api/folders/move', { sourcePath, targetFolder }, { silent: true });

    if (!result.success) {
        showToast(result.data?.error || result.error || 'Failed to move folder', 'error');
        return;
    }

    state.rightTreeExpansion.add(targetFolder);
    await afterFrontendMutation();
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
    state.rightTreeExpansion.add(targetFolder);
    showToast('Multiple files in folder. Drop objects on a specific file.', 'info');
    return null;
}

export function handleFolderDrop(event, targetFolder) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drop-active');
    cleanupDragState();

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

    const stableKeys = objects
        .filter(o => o?.source_file && o.source_file !== targetFile)
        .map(o => `${o.source_file}|${o.object_type}|${o.display_name ?? o.name ?? ''}`);
    if (stableKeys.length === 0) {return;}

    const result = await ApiClient.post('/api/move-objects', {
        stable_keys: stableKeys,
        target_file: targetFile
    }, { silent: true });

    if (result.success && result.data?.moved > 0) {
        for (const o of objects) {
            if (o?.source_file && o.source_file !== targetFile) {
                migrateKeysAfterMove(o.source_file, targetFile, o.object_type, o.display_name ?? o.name ?? '');
            }
        }
        state.rightTreeExpansion.add(targetFile);
        state.rightTreeExpansion.add(targetFolder);
        await afterFrontendMutation();
        scrollTargetFileIntoView(targetFile);
        showToast(`Moved ${result.data.moved} object(s) to ${extractFileName(targetFile)}`, 'success');
    }
}

export function handleFileDragStart(event, filePath) {
    const target = event.currentTarget || event.target;
    if (!target) {return;}

    event.dataTransfer.setData(DATA_TYPES.FILE_MOVE, filePath);
    event.dataTransfer.effectAllowed = 'move';

    target.style.opacity = '0.5';
    target.addEventListener('dragend', () => {
        target.style.opacity = '';
    }, { once: true });
}

export function handleFolderDragStart(event, folderPath) {
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

export async function deleteFile(filePath, event) {
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

    await afterFrontendMutation();
    showToast(`Deleted "${fileName}"`, 'success');
}

export async function deleteFolder(folderPath, event) {
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

    await afterFrontendMutation();
    showToast(`Deleted "${folderName}/"`, 'success');
}

// ============================================================================
// File/Folder Creation
// ============================================================================

export async function createNewItem() {
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

        state.rightTreeExpansion.add(fullPath);
        document.getElementById('newItemName').value = '';
        await afterFrontendMutation();
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

    state.rightTreeExpansion.add(fullPath);
    document.getElementById('newItemName').value = '';
    await afterFrontendMutation();
    showToast(`Created file "${name}"`, 'success');
}

// ============================================================================
// Inline File/Folder Creation
// ============================================================================

export function createInlineFile() {
    createInlineItem('file');
}

export function createInlineFolder() {
    createInlineItem('folder');
}

export function createInlineItem(type) {
    const container = document.getElementById('targetPaneContent');
    if (!container) {return;}

    const existing = container.querySelector('.tree-item-inline-edit');
    if (existing) {
        existing.remove();
    }

    const icon = type === 'folder' ? getIcon('folder-plus') : getIcon('file-plus');
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

export async function confirmInlineCreate(type, name, row) {
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

        state.rightTreeExpansion.add(fullPath);
        row.remove();
        await afterFrontendMutation();
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

        state.rightTreeExpansion.add(fullPath);
        row.remove();
        await afterFrontendMutation();
        showToast(`Created file "${fileName}"`, 'success');
    }
}

// onclick/ondragstart handlers in generated HTML — must be on window.Explorer
window.Explorer = window.Explorer || {};
window.Explorer.selectFolder = selectFolder;
window.Explorer.toggleFolderExpand = toggleFolderExpand;
window.Explorer.handleDragExpandOver = handleDragExpandOver;
window.Explorer.handleDragExpandLeave = handleDragExpandLeave;
window.Explorer.handleFolderDrop = handleFolderDrop;
window.Explorer.handleFolderDragStart = handleFolderDragStart;
window.Explorer.toggleFileExpand = toggleFileExpand;
window.Explorer.handleFileDrop = handleFileDrop;
window.Explorer.handleFileDragStart = handleFileDragStart;
window.Explorer.handleTargetObjectDragStart = handleTargetObjectDragStart;
window.Explorer.handleTargetObjectDragEnd = handleTargetObjectDragEnd;
window.Explorer.handleObjectDragOver = handleObjectDragOver;
window.Explorer.handleObjectDrop = handleObjectDrop;
window.Explorer.handleObjectDragLeave = handleObjectDragLeave;
window.Explorer.deleteFile = deleteFile;
window.Explorer.deleteFolder = deleteFolder;
window.Explorer.escapeHtml = escapeHtml;
window.Explorer.escapeJs = escapeJs;
window.Explorer.getIcon = getIcon;
