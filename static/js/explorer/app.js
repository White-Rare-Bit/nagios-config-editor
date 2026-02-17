/**
 * Nagios Bulk Editor - Explorer Application Module
 * 
 * This module contains all the explorer functionality.
 * Functions are attached to the Explorer namespace.
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;
    
    // Convenience aliases
    const typeLabels = constants.typeLabels;
    const identityFields = constants.identityFields;
    const inheritanceAttrs = constants.inheritanceAttrs;
    const referenceAttrs = constants.referenceAttrs;

// Delegates to functions defined in object-editor.js and dialogs.js modules
function updateCommitUI() { Explorer.updateCommitUI(); }
function showCenterPaneObject(obj) { Explorer.showCenterPaneObject(obj); }
function hideCenterPaneObject() { Explorer.hideCenterPaneObject(); }
function showCenterPaneMultiple(count) { Explorer.showCenterPaneMultiple(count); }
function showCenterPaneNewObject(obj, targetFile) { Explorer.showCenterPaneNewObject(obj, targetFile); }
function renderCenterAttributes() { Explorer.renderCenterAttributes(); }
function getNewObjectNameField(objectType) { return Explorer.getNewObjectNameField(objectType); }
function stageObjectDeletions() { Explorer.stageObjectDeletions(); }
function stageNewObjectChanges() { Explorer.stageNewObjectChanges(); }
function removeStagedCreation(idx) { Explorer.removeStagedCreation(idx); }

// Delegates to functions in context-menu.js
function hideContextMenu() { Explorer.hideContextMenu(); }
function closeDialog() { Explorer.closeDialog(); }
function showDialog(title, bodyHtml, onConfirm) { return Explorer.showDialog(title, bodyHtml, onConfirm); }
function showPreview() { Explorer.showPreview(); }
function closePreview() { Explorer.closePreview(); }

// Delegates to functions in file-operations.js
function initTargetPane() { Explorer.initTargetPane(); }
function renderTargetPane() { Explorer.renderTargetPane(); }
function navigateToObjectByIndex(index) { Explorer.navigateToObjectByIndex(index); }

// Delegates to functions in analysis.js
function isObjectTemplate(obj) { return Explorer.isObjectTemplate(obj); }
function loadAllSuggestions(forceRefresh) { return Explorer.loadAllSuggestions(forceRefresh); }
function loadIssues() { return Explorer.loadIssues(); }
function analyzeAll(forceRefresh) { return Explorer.analyzeAll(forceRefresh); }
function switchSuggestionsSubtab(subtab) { Explorer.switchSuggestionsSubtab(subtab); }
function navigateToIssue(search, type) { Explorer.navigateToIssue(search, type); }
function loadCleanupSuggestions() { return Explorer.loadCleanupSuggestions(); }
function renderCleanupSuggestions() { Explorer.renderCleanupSuggestions(); }

// Local state not in Explorer.state (UI-specific)

// Utility: Refresh Impact & Relationships when relevant attributes change
function refreshRelatedSections(key, obj) {
    // If any reference-related attribute changes, refresh the unified section
    if (inheritanceAttrs.includes(key) || referenceAttrs.includes(key) || key === 'members' || key === 'use') {
        Explorer.loadImpactAndRelationships(obj);
    }
}

// Utility: Hide autocomplete dropdown with delay
function hideAutocompleteDropdown(selector, resetCallback) {
    setTimeout(() => {
        const dropdown = selector.startsWith('#')
            ? document.getElementById(selector.slice(1))
            : document.querySelector(selector);
        if (dropdown) {dropdown.remove();}
        if (resetCallback) {resetCallback();}
    }, 150);
}

// Utility: Handle autocomplete keyboard navigation
function handleAutocompleteKeyNav(event, config) {
    const dropdown = config.selector.startsWith('#')
        ? document.getElementById(config.selector.slice(1))
        : document.querySelector(config.selector);
    if (!dropdown) {return false;}

    const items = dropdown.querySelectorAll('.attr-autocomplete-item');
    if (items.length === 0) {return false;}

    const currentIndex = config.getIndex();

    if (event.key === 'ArrowDown') {
        event.preventDefault();
        const newIndex = Math.min(currentIndex + 1, items.length - 1);
        config.setIndex(newIndex);
        items.forEach((item, i) => item.classList.toggle('highlighted', i === newIndex));
        if (items[newIndex]) {items[newIndex].scrollIntoView({ block: 'nearest' });}
        return true;
    } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        const newIndex = Math.max(currentIndex - 1, 0);
        config.setIndex(newIndex);
        items.forEach((item, i) => item.classList.toggle('highlighted', i === newIndex));
        if (items[newIndex]) {items[newIndex].scrollIntoView({ block: 'nearest' });}
        return true;
    } else if (event.key === 'Enter' && currentIndex >= 0) {
        event.preventDefault();
        const value = items[currentIndex].dataset.value;
        config.onSelect(value);
        return true;
    } else if (event.key === 'Escape' || event.key === 'Tab') {
        dropdown.remove();
        config.setIndex(-1);
        if (config.onClose) {config.onClose();}
        return true;
    }
    return false;
}

// Utility: Render a grouped info section
function renderGroupedInfoSection(title, items, renderItem, options = {}) {
    if (items.length === 0) {return '';}
    const { showCount = false, showAttr = true } = options;
    const grouped = Explorer.groupByType(items);

    let html = `<div class="info-section">
        <div class="info-section-title">${title}${showCount ? ` <span class="member-count">${items.length}</span>` : ''}</div>`;

    for (const [type, typeItems] of Object.entries(grouped)) {
        html += `
            <div class="ref-type-group">
                <div class="ref-type-header">${typeLabels[type] || type}</div>
                <div class="ref-type-list">
                    ${typeItems.map(item => renderItem(item, showAttr)).join('')}
                </div>
            </div>`;
    }
    html += `</div>`;
    return html;
}

// Use loadObjects, saveStagedChanges, loadStagedChanges, clearStagedChanges from data-loading.js
// Use toDisplayPath from data-loading.js
const configRootName = Explorer.getConfigRootName();

// Session ID for staging
const mySessionId = getSessionId();

// resetStagingState is now defined in state-management.js
// It already handles isEditingLocked = false

// Update UI to show/hide editing lock state (banner is handled by base.html)
function updateEditingLockedUI() {
    if (state.isEditingLocked) {
        document.body.classList.add('editing-locked');
    } else {
        document.body.classList.remove('editing-locked');
    }
}

// Check if editing is allowed (not locked by another session)
function canEdit() {
    return !state.isEditingLocked;
}

// Check if staging has changed (for multi-user sync)
async function checkStagingChanges() {
    // Skip check while we're in the middle of saving
    if (isSavingStaging) {return;}

    try {
        // Check lock status from base.html (updates banner)
        await checkLockStatus();

        const response = await fetch('/api/staging/info');
        const info = await response.json();

        if (info.hasStaging) {
            // Check if staging was modified
            if (info.lastModified && info.lastModified !== lastStagingTimestamp) {
                // Double-check we're not saving (race condition guard)
                if (isSavingStaging) {return;}

                // Reload staging from server (don't update lock state during polling)
                await Explorer.loadStagedChanges(false);
                updateCommitUI();
                renderTargetPane();
                buildTree();
            }
        } else if (Explorer.hasStagedChanges() || state.isEditingLocked) {
            // Server staging was cleared (committed or discarded)
            Explorer.resetStagingState();
            lastStagingTimestamp = null;
            state.isEditingLocked = false;
            Explorer.updateEditingLockedUI();
            updateCommitUI();
            // Reload data in case changes were committed
            await Explorer.loadObjects();
            renderTargetPane();
            buildTree();
            loadIssues();
        }
    } catch (e) {
        console.error('Failed to check staging changes:', e);
    }
}

// hasStagedChanges, startStagingPoll, stopStagingPoll now in modules

// Load data
document.addEventListener('DOMContentLoaded', async () => {
    // Load objects, files, and folders from backend
    await Explorer.loadObjects();

    // Load any staged changes from server (shared across all users)
    await Explorer.loadStagedChanges();

    // Restore tabs from sessionStorage
    Explorer.restoreTabs();

    // Restore tree folder expanded state from localStorage
    restoreTreeFolderState();

    buildTree();

    let selectionRestored = false;

    // Restore active tab or fall back to saved selection
    if (state.openTabs.length > 0 && state.activeTabKey) {
        const obj = Explorer.findObjectByKey(state.activeTabKey);
        if (obj) {
            Explorer.openTab(obj);
            selectionRestored = true;
        }
    } else {
        const savedKey = sessionStorage.getItem('explorerSelectedKey');
        if (savedKey) {
            const obj = Explorer.findObjectByKey(savedKey);
            if (obj) {
                Explorer.openTab(obj);
                selectionRestored = true;
            }
        }
    }

    // Render tab bar (may be empty if no tabs restored)
    Explorer.renderTabBar();

    // Show empty state if no selection was restored
    if (!selectionRestored) {
        const emptyState = document.getElementById('centerEmptyState');
        emptyState.classList.remove('u-hidden');
        emptyState.style.display = 'flex';
    }

    // Start polling for staging changes from other users
    Explorer.startStagingPoll();
    initTargetPane();

    // Restore suggestion section expanded/collapsed state
    restoreSuggestionSectionState();

    // Set up drag event delegation for Chrome compatibility
    const objectTree = document.getElementById('treeContent');
    if (objectTree) {
        // Prevent text selection from interfering with drag in Chrome
        objectTree.addEventListener('selectstart', (event) => {
            const treeItem = event.target.closest('.tree-item[draggable="true"]');
            if (treeItem) {
                event.preventDefault();
            }
        });

        // Use event delegation for dragstart - more reliable in Chrome
        objectTree.addEventListener('dragstart', (event) => {
            const treeItem = event.target.closest('.tree-item[draggable="true"]');
            if (treeItem) {
                const index = parseInt(treeItem.dataset.index, 10);
                if (!isNaN(index)) {
                    Explorer.handleDragStart(event, index);
                }
            }
        });

        objectTree.addEventListener('dragend', (event) => {
            // Always clean up on dragend, regardless of target
            Explorer.handleDragEnd(event);
        });

        // Track hovered item for spacebar preview
        objectTree.addEventListener('mouseover', (event) => {
            const treeItem = event.target.closest('.tree-item[data-index]');
            if (treeItem) {
                state.hoveredIndex = parseInt(treeItem.dataset.index, 10);
            }
        });

        objectTree.addEventListener('mouseout', (event) => {
            const treeItem = event.target.closest('.tree-item[data-index]');
            if (treeItem) {
                // Only clear if we're leaving the tree item (not entering a child)
                const relatedTarget = event.relatedTarget;
                if (!relatedTarget || !treeItem.contains(relatedTarget)) {
                    state.hoveredIndex = null;
                }
            }
        });
    }

    // Add document-level dragend listener as safety net
    // This catches drags that end outside the tree container
    document.addEventListener('dragend', (event) => {
        if (document.body.classList.contains('dragging-objects')) {
            Explorer.cleanupDragState();
        }
    });

    // Update commit button with any persisted changes
    updateCommitUI();

    // Load issues in background for badges
    Explorer.loadIssuesForBadges();

    // Load suggestions in background for badges
    Explorer.loadSuggestionsForBadges();

    // Pre-load full suggestions content so it's ready when user navigates to the tab
    loadAllSuggestions();

    // Check if we need to navigate to an object after reload
    const navigateTo = sessionStorage.getItem('navigateToObject');
    if (navigateTo) {
        sessionStorage.removeItem('navigateToObject');
        try {
            const { type, name } = JSON.parse(navigateTo);
            const obj = state.allObjects.find(o => o.object_type === type && (o.name === name || o.display_name === name));
            if (obj) {
                setTimeout(() => navigateToObjectByIndex(obj.global_index), 100);
            }
        } catch (e) {
            console.error('Failed to navigate to object:', e);
        }
    }

    // Check if we should open commit dialog (redirected from another page)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('showCommit') === '1') {
        // Clean URL
        window.history.replaceState({}, '', window.location.pathname);
        // Open commit dialog after a short delay to ensure everything is loaded
        setTimeout(() => {
            const totalChanges = state.pendingEdits.size + state.stagedMoves.size + state.stagedCreations.length +
                state.stagedObjectDeletions.size + state.newFiles.size;
            if (totalChanges > 0) {
                showGlobalCommitDialog();
            }
        }, 300);
    }

    // Check if we should auto-commit (redirected from another page with Apply button)
    if (urlParams.get('autoCommit') === '1') {
        // Clean URL
        window.history.replaceState({}, '', window.location.pathname);
        // Open commit dialog after a short delay to ensure staging is loaded
        setTimeout(() => {
            const totalChanges = state.pendingEdits.size + state.stagedMoves.size + state.stagedCreations.length +
                state.stagedObjectDeletions.size + state.newFiles.size;
            if (totalChanges > 0) {
                showGlobalCommitDialog();
            }
        }, 300);
    }

    // Check if we should navigate to a specific object (from Graph View)
    const searchParam = urlParams.get('search');
    const typeParam = urlParams.get('type');
    if (searchParam && typeParam) {
        // Clean URL
        window.history.replaceState({}, '', window.location.pathname);
        // Navigate to the object after a short delay to ensure tree is built
        setTimeout(() => {
            navigateToIssue(searchParam, typeParam);
        }, 100);
    }
});

// Keyboard handling - Escape only for closing dialogs
document.addEventListener('keydown', (e) => {
    // Ignore keyboard shortcuts when typing in inputs/textareas
    const isTyping = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT' || e.target.isContentEditable;

    if (e.code === 'Escape') {
        closePreview();
        closeDialog();
        closeObjectDetail();
        hideContextMenu();
        // Only clear selection if no object is being edited
        if (!state.editedObject) {
            Explorer.clearSelection();
            updateSelection();
        }
    } else if (e.code === 'Space' && !isTyping) {
        // Space: quick preview selected object
        e.preventDefault();
        if (state.selectedKeys.size > 0) {
            showPreview();
        }
    }
});

// Hide context menu on click outside
document.addEventListener('click', () => hideContextMenu());

// Hide context menu on scroll in tree panel
document.querySelector('.tree-panel').addEventListener('scroll', () => hideContextMenu(), true);

function setView(view) {
    state.currentView = view;
    document.querySelectorAll('.tree-panel .panel-tab-header .nbe-tab').forEach(btn => {
        const isActive = btn.dataset.view === view;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive);
    });
    buildTree();
}

function buildTree() {
    const container = document.getElementById('treeContent');
    const search = document.getElementById('treeSearch').value.toLowerCase();
    const orphansOnly = document.getElementById('showOrphansOnly').checked;
    const issuesOnly = document.getElementById('showIssuesOnly').checked;

    let filtered = state.allObjects;

    // Filter by search (name, type, and attributes)
    if (search) {
        filtered = filtered.filter(o => {
            // Check name and type
            if (o.display_name.toLowerCase().includes(search) ||
                o.object_type.toLowerCase().includes(search)) {
                return true;
            }
            // Check attribute keys and values
            for (const [key, value] of Object.entries(o.attributes || {})) {
                if (key.toLowerCase().includes(search) ||
                    String(value).toLowerCase().includes(search)) {
                    return true;
                }
            }
            return false;
        });
    }

    // Filter by orphans
    if (orphansOnly) {
        filtered = filtered.filter(o => state.orphanIndices.has(o.global_index));
    }

    // Filter by issues
    if (issuesOnly) {
        filtered = filtered.filter(o => getObjectIssue(o) !== null);
    }

    if (state.currentView === 'file') {
        buildFileTree(container, filtered);
    } else {
        buildTypeTree(container, filtered);
    }
}

function buildFileTree(container, objects) {
    const byFile = {};
    objects.forEach(obj => {
        const file = obj.source_file.split('/').pop();
        if (!byFile[file]) {byFile[file] = [];}
        byFile[file].push(obj);
    });

    // Group staged creations by file
    const stagedByFile = {};
    state.stagedCreations.forEach((creation, idx) => {
        const file = creation.targetFile.split('/').pop();
        if (!stagedByFile[file]) {stagedByFile[file] = [];}
        stagedByFile[file].push({ creation, idx });
    });

    // Merge file lists (existing + staged)
    const allFilesSet = new Set([...Object.keys(byFile), ...Object.keys(stagedByFile)]);

    container.innerHTML = Array.from(allFilesSet)
        .sort((a, b) => a.localeCompare(b))
        .map(file => {
            const objs = byFile[file] || [];
            const staged = stagedByFile[file] || [];
            const filePath = objs.length > 0 ? objs[0].source_file : staged[0].creation.targetFile;
            const totalCount = objs.length + staged.length;

            const isOpen = state.openTreeFolders.has(filePath);

            // Combine existing objects and staged creations, sorted by position
            const allItems = [
                ...objs.map(o => ({ type: 'existing', obj: o, position: o.line_number })),
                ...staged.map(s => ({
                    type: 'staged',
                    creation: s.creation,
                    idx: s.idx,
                    position: s.creation.insertPosition !== undefined ? s.creation.insertPosition + 0.5 : Infinity
                }))
            ].sort((a, b) => a.position - b.position);

            const itemsHtml = allItems.map(item => {
                if (item.type === 'existing') {
                    return renderTreeItem(item.obj);
                } 
                    return renderStagedCreationTreeItem(item.creation, item.idx);
                
            }).join('');

            return `
            <div class="tree-folder${isOpen ? ' open' : ''}" data-file="${Explorer.escapeHtml(filePath)}">
                <div class="tree-folder-header" onclick="Explorer.toggleFolder(this.parentElement)"
                     ondragover="Explorer.handleDragOver(event)" ondrop="Explorer.handleDrop(event, '${Explorer.escapeJs(filePath)}')"
                     ondragleave="if(!this.contains(event.relatedTarget))this.closest('.tree-folder')?.classList.remove('drop-target')">
                    <span class="tree-folder-icon"><i class="fa-solid fa-chevron-right"></i></span>
                    <span class="tree-folder-name">${Explorer.escapeHtml(file)}</span>
                    <button class="tree-folder-add-btn" onclick="event.stopPropagation(); Explorer.createNewObject('${Explorer.escapeJs(filePath)}')" title="Add new object">+</button>
                    <span class="tree-folder-count">${totalCount}${staged.length > 0 ? ` <span class="staged-count">(+${staged.length})</span>` : ''}</span>
                </div>
                <div class="tree-folder-children">
                    ${itemsHtml}
                </div>
            </div>
        `}).join('');
}

function renderStagedCreationTreeItem(creation, idx) {
    const isSelected = state.selectedStagedIndices.has(idx);
    const selected = isSelected ? 'selected' : '';
    const displayName = creation.displayName || '(unnamed)';

    return `
        <div class="tree-item staged-creation ${selected}"
             data-staged-index="${idx}"
             draggable="true"
             onclick="Explorer.handleStagedItemClick(event, ${idx})"
             oncontextmenu="Explorer.handleStagedContextMenu(event, ${idx})"
             ondragstart="Explorer.handleStagedDragStart(event, ${idx})"
             ondragend="Explorer.handleDragEnd(event)">
            <span class="tree-item-staged-badge" title="Pending - not yet committed">+</span>
            <span class="tree-item-name">${Explorer.escapeHtml(displayName)}</span>
            <span class="tree-item-type type-${creation.object_type}" title="${Explorer.escapeHtml(creation.object_type)}">${Explorer.getTypeBadge(creation.object_type)}</span>
        </div>
    `;
}

function handleStagedItemClick(event, idx) {
    event.stopPropagation();

    // Clear regular object selection when clicking staged items
    Explorer.clearSelection();
    document.querySelectorAll('.tree-item:not(.staged-creation)').forEach(el => {
        el.classList.remove('selected');
    });

    if (event.ctrlKey || event.metaKey) {
        // Toggle selection
        if (state.selectedStagedIndices.has(idx)) {
            state.selectedStagedIndices.delete(idx);
        } else {
            state.selectedStagedIndices.add(idx);
        }
    } else if (event.shiftKey && state.selectedStagedIndices.size > 0) {
        // Range select
        const allStaged = Array.from(document.querySelectorAll('.tree-item.staged-creation')).map(el => parseInt(el.dataset.stagedIndex, 10));
        const lastSelected = Array.from(state.selectedStagedIndices).pop();
        const start = allStaged.indexOf(lastSelected);
        const end = allStaged.indexOf(idx);
        const range = allStaged.slice(Math.min(start, end), Math.max(start, end) + 1);
        range.forEach(i => state.selectedStagedIndices.add(i));
    } else {
        // Single select
        state.selectedStagedIndices.clear();
        state.selectedStagedIndices.add(idx);
    }

    updateStagedSelection();
}

function updateStagedSelection() {
    // Update visual selection for staged items
    document.querySelectorAll('.tree-item.staged-creation').forEach(el => {
        const idx = parseInt(el.dataset.stagedIndex, 10);
        el.classList.toggle('selected', state.selectedStagedIndices.has(idx));
    });

    // Update center pane based on selection
    if (state.selectedStagedIndices.size === 1) {
        const idx = Array.from(state.selectedStagedIndices)[0];
        selectStagedCreationForEdit(idx);
    } else if (state.selectedStagedIndices.size === 0 && state.selectedKeys.size === 0) {
        hideCenterPaneObject();
    } else if (state.selectedStagedIndices.size > 1) {
        showCenterPaneMultiple(state.selectedStagedIndices.size);
    }
}

function selectStagedCreationForEdit(idx) {
    // Get the staged creation
    const creation = state.stagedCreations[idx];
    if (!creation) {return;}

    // Create an object representation for editing
    const obj = {
        object_type: creation.object_type,
        attributes: {...creation.attributes},
        source_file: creation.targetFile,
        line_number: 999999,
        display_name: creation.displayName || '(unnamed)',
        global_index: -1
    };

    // Set editing state
    state.editedObject = obj;
    state.originalAttributes = {...creation.attributes};
    state.isNewObject = true;
    state.newObjectStagedIndex = idx;

    // Show in center pane
    showCenterPaneNewObject(obj, creation.targetFile);
}

function handleStagedContextMenu(event, idx) {
    event.preventDefault();
    event.stopPropagation();

    // If not already selected, select just this one
    if (!state.selectedStagedIndices.has(idx)) {
        Explorer.clearSelection();
        state.selectedStagedIndices.clear();
        state.selectedStagedIndices.add(idx);
        updateStagedSelection();
    }

    // Clear regular selection
    Explorer.clearSelection();
    document.querySelectorAll('.tree-item:not(.staged-creation)').forEach(el => {
        el.classList.remove('selected');
    });

    state.contextTarget = idx;
    const menu = document.getElementById('contextMenu');

    // Set selection mode class - staged creations only support delete
    menu.classList.remove('single-selection', 'multi-selection');
    menu.classList.add(state.selectedStagedIndices.size > 1 ? 'multi-selection' : 'single-selection');
    // Add class to indicate staged context
    menu.classList.add('staged-context');

    // Position menu
    menu.style.left = event.pageX + 'px';
    menu.style.top = event.pageY + 'px';
    menu.classList.add('visible');
}

function handleStagedDragStart(event, idx) {
    // If not selected, select only this item
    if (!state.selectedStagedIndices.has(idx)) {
        Explorer.clearSelection();
        state.selectedStagedIndices.clear();
        state.selectedStagedIndices.add(idx);
        updateStagedSelection();
    }

    // Clear regular selection for staged drag
    Explorer.clearSelection();
    document.querySelectorAll('.tree-item:not(.staged-creation)').forEach(el => {
        el.classList.remove('selected');
    });

    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', JSON.stringify({
        type: 'staged-creations',
        indices: Array.from(state.selectedStagedIndices)
    }));

    // Add dragging class to selected items
    state.selectedStagedIndices.forEach(i => {
        const el = document.querySelector(`[data-staged-index="${i}"]`);
        if (el) {el.classList.add('dragging');}
    });
}

function buildTypeTree(container, objects) {
    const byType = {};
    objects.forEach(obj => {
        if (!byType[obj.object_type]) {byType[obj.object_type] = [];}
        byType[obj.object_type].push(obj);
    });

    container.innerHTML = Object.entries(byType)
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([type, objs]) => {
            const folderKey = 'type:' + type;
            const isOpen = state.openTreeFolders.has(folderKey);
            return `
            <div class="tree-folder${isOpen ? ' open' : ''}" data-file="${folderKey}">
                <div class="tree-folder-header" onclick="Explorer.toggleFolder(this.parentElement)">
                    <span class="tree-folder-icon"><i class="fa-solid fa-chevron-right"></i></span>
                    <span class="tree-folder-name">${Explorer.escapeHtml(type)}</span>
                    <span class="tree-folder-count">${objs.length}</span>
                </div>
                <div class="tree-folder-children">
                    ${objs.map(o => renderTreeItem(o, false)).join('')}
                </div>
            </div>
        `}).join('');
}

function renderTreeItem(obj, showType = false) {
    const selected = Explorer.isSelectedByIndex(obj.global_index) ? 'selected' : '';
    const isTemplate = isTreeItemTemplate(obj);
    const isOrphan = state.orphanIndices.has(obj.global_index);
    const hostListInfo = getHostListInfo(obj);
    const issue = getObjectIssue(obj);
    const isDeleted = state.stagedObjectDeletions.has(obj.global_index);
    const isStagedMove = state.stagedMoves.has(Explorer.getObjectKey(obj));
    const orphanClass = isOrphan ? 'is-orphan' : '';
    const longListClass = hostListInfo.shouldGroup ? 'has-long-list' : '';
    const deletedClass = isDeleted ? 'staged-for-deletion' : '';
    const stagedClass = isStagedMove ? 'staged' : '';
    const typeLabel = Explorer.getTypeBadge(obj.object_type, isTemplate);

    // Check if there's a staged edit with a new name
    const displayName = getStagedDisplayName(obj);

    // Don't allow interaction with deleted objects except to undo
    if (isDeleted) {
        return `
        <div class="tree-item ${deletedClass}"
             data-index="${obj.global_index}">
            <span class="tree-item-delete-badge" title="Staged for deletion">−</span>
            <span class="tree-item-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
            ${showType ? '' : `<span class="tree-item-type type-${obj.object_type}" title="${obj.object_type}">${typeLabel}</span>`}
            <button class="tree-item-undo-btn" onclick="event.stopPropagation(); Explorer.unstageObjectDeletion(${obj.global_index})" title="Undo deletion">Undo</button>
        </div>
    `;
    }

    return `
        <div class="tree-item ${selected} ${orphanClass} ${longListClass} ${stagedClass}"
             data-index="${obj.global_index}"
             draggable="true"
             onclick="Explorer.handleItemClick(event, ${obj.global_index})"
             oncontextmenu="Explorer.handleContextMenu(event, ${obj.global_index})">
            <span class="tree-item-drag-handle" title="Drag to move to another file">${Explorer.getIcon('grip-vertical')}</span>
            ${issue ? `<span class="tree-item-issue-badge ${issue.severity}" title="${Explorer.escapeHtml(issue.message)}">${Explorer.getIssueIcon(issue)}</span>` : ''}
            ${hostListInfo.shouldGroup ? `<span class="tree-item-group-badge" title="Consider using a hostgroup (${hostListInfo.count} hosts)"><i class="fa-solid fa-list"></i></span>` : ''}
            ${isStagedMove ? '<span class="tree-item-staged-badge" title="Pending move - not yet committed">→</span>' : ''}
            <span class="tree-item-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
            ${showType ? '' : `<span class="tree-item-type type-${obj.object_type}" title="${obj.object_type}">${typeLabel}</span>`}
        </div>
    `;
}

// Get display name for an object, checking staged edits first
function getStagedDisplayName(obj) {
    const edit = state.pendingEdits.get(obj.global_index);
    if (edit) {
        // Get the name field for this object type
        const nameField = getNewObjectNameField(obj.object_type);
        if (nameField && edit.edited[nameField] !== undefined) {
            return edit.edited[nameField] || '(unnamed)';
        }
    }
    return obj.display_name;
}

function getObjectIssue(obj) {
    const key = `${obj.object_type}:${obj.display_name}`;
    return state.issuesByObject.get(key) || null;
}

// Check if object has a long host list that should probably be a hostgroup
function getHostListInfo(obj) {
    const HOST_LIST_THRESHOLD = 4; // Suggest grouping if more than this many hosts

    // Only check services and other objects that can have host_name lists
    if (!['service', 'serviceescalation', 'servicedependency'].includes(obj.object_type)) {
        return { shouldGroup: false, count: 0 };
    }

    const hostName = obj.attributes.host_name;
    if (!hostName) {return { shouldGroup: false, count: 0 };}

    // If already using hostgroup_name, no need to suggest
    if (obj.attributes.hostgroup_name) {return { shouldGroup: false, count: 0 };}

    // Count hosts (excluding wildcards)
    const hosts = hostName.split(',').map(h => h.trim()).filter(h => h && h !== '*');

    return {
        shouldGroup: hosts.length > HOST_LIST_THRESHOLD,
        count: hosts.length
    };
}

// Check if tree item is a template (delegates to shared implementation)
function isTreeItemTemplate(obj) {
    return Explorer.isObjectTemplate(obj);
}

// Helper to get effective attributes for an object (considering pending edits)
function getEffectiveAttributes(obj) {
    const pendingEdit = state.pendingEdits.get(obj.global_index);
    return pendingEdit ? pendingEdit.edited : obj.attributes;
}

// Helper to get the name field that should be used for an object
// Templates use 'name', regular objects use type-specific field (host_name, etc.)
function getNameFieldForObject(obj) {
    const typeField = constants.nameFields[obj.object_type];
    const attrs = getEffectiveAttributes(obj);

    if (typeField && attrs[typeField]) {
        return typeField;
    }
    if ((obj.object_type === 'hostescalation' || obj.object_type === 'hostdependency') && attrs.hostgroup_name) {
        return 'hostgroup_name';
    }
    if (attrs.name) {
        return 'name';
    }
    return typeField || 'name';
}

// Helper to get effective name for an object (considering pending edits)
function getEffectiveName(obj) {
    const attrs = getEffectiveAttributes(obj);
    const nameField = getNameFieldForObject(obj);
    return attrs[nameField] || obj.name || obj.display_name;
}

function toggleFolder(folder) {
    folder.classList.toggle('open');
    // Track folder state for persistence across tree rebuilds
    const filePath = folder.dataset.file;
    if (filePath) {
        if (folder.classList.contains('open')) {
            state.openTreeFolders.add(filePath);
        } else {
            state.openTreeFolders.delete(filePath);
        }
        // Save to localStorage for persistence across page refreshes
        saveTreeFolderState();
    }
}

function saveTreeFolderState() {
    try {
        localStorage.setItem('nagios_openTreeFolders', JSON.stringify([...state.openTreeFolders]));
    } catch (e) {
        console.warn('Failed to save tree folder state:', e);
    }
}

function restoreTreeFolderState() {
    try {
        const saved = localStorage.getItem('nagios_openTreeFolders');
        if (saved) {
            const arr = JSON.parse(saved);
            if (Array.isArray(arr)) {
                state.openTreeFolders = new Set(arr);
            }
        }
    } catch (e) {
        console.warn('Failed to restore tree folder state:', e);
    }
}

function filterTree() {
    buildTree();
}

function handleItemClick(event, index) {
    event.stopPropagation();
    hideContextMenu();

    // Clear staged creation selection when clicking a regular item
    state.selectedStagedIndices.clear();
    document.querySelectorAll('.tree-item.staged-creation').forEach(el => {
        el.classList.remove('selected');
    });

    if (event.ctrlKey || event.metaKey) {
        if (Explorer.isSelectedByIndex(index)) {
            Explorer.removeFromSelectionByIndex(index);
        } else {
            selectObjectByIndex(index);
        }
    } else if (event.shiftKey && state.selectedKeys.size > 0) {
        // Range select
        const all = Array.from(document.querySelectorAll('.tree-item:not(.staged-creation)')).map(el => parseInt(el.dataset.index, 10));
        const selectedIndices = Explorer.getSelectedIndices();
        const lastSelected = Array.from(Explorer.getSelectedIndices()).pop();
        const start = all.indexOf(lastSelected);
        const end = all.indexOf(index);
        const range = all.slice(Math.min(start, end), Math.max(start, end) + 1);
        range.forEach(i => selectObjectByIndex(i));
    } else {
        Explorer.clearSelection();
        selectObjectByIndex(index);
    }

    updateSelection();
}

// Simple selection helpers using stable keys
function selectObjectByIndex(index) {
    const obj = state.allObjects.find(o => o.global_index === index);
    if (obj) {
        state.selectedKeys.add(Explorer.getObjectKey(obj));
            }
}

/**
 * Select an object by its stable key (file|type|name format).
 * Clears current selection and selects the matching object.
 * @param {string} stableKey - "source_file|object_type|name" format
 */
function selectObjectByStableKey(stableKey) {
    if (!stableKey) {return;}

    // Parse stable key: "source_file|object_type|name"
    // Name part may contain '|' so rejoin remaining parts
    const parts = stableKey.split('|');
    if (parts.length < 3) {return;}

    const [sourceFile, objType, ...nameParts] = parts;
    const objName = nameParts.join('|');

    // Find the object - check multiple name sources for flexibility
    const obj = state.allObjects.find(o => {
        if (o.source_file !== sourceFile || o.object_type !== objType) {return false;}
        // Match against the same name resolution used by getObjectKey
        const objKeyName = o.name ?? o.display_name ?? `idx:${o.global_index}`;
        if (objKeyName === objName) {return true;}
        // Also check display_name and attributes.name for backward compatibility
        if (o.display_name === objName || o.attributes?.name === objName) {return true;}
        return false;
    });

    if (obj) {
        // Clear current selection and select this object
        Explorer.clearSelection();
        state.selectedKeys.add(Explorer.getObjectKey(obj));
        updateSelection();
        // Scroll to the object in the tree
        scrollToObject(obj.global_index);
    } else {
        showToast(`Object not found: ${objName}`, 'error');
    }
}

// clearSelection, removeFromSelectionByIndex, isSelectedByIndex now in state-management.js

function updateSelection() {
    // Update tree items - highlight selected and show staged items differently
    document.querySelectorAll('.tree-item').forEach(el => {
        const index = parseInt(el.dataset.index, 10);
        el.classList.toggle('selected', Explorer.isSelectedByIndex(index));
        el.classList.toggle('staged', state.stagedMoves.has(Explorer.getObjectKeyByIndex(index)));
    });

    // Update selection count indicator
    
    // Update center pane based on selection
    if (state.selectedKeys.size === 1) {
        const key = Array.from(state.selectedKeys)[0];
        const obj = Explorer.findObjectByKey(key);
        if (obj) {
            // If this is a tab switch, center pane is already handled
            if (!state.isTabSwitch) {
                Explorer.openTab(obj);
            }
            sessionStorage.setItem('explorerSelectedKey', key);
        }
    } else if (state.selectedKeys.size === 0) {
        // Don't hide if we have open tabs — let tab bar handle it
        if (state.openTabs.length === 0) {
            hideCenterPaneObject();
        }
        sessionStorage.removeItem('explorerSelectedKey');
    } else {
        showCenterPaneMultiple(state.selectedKeys.size);
        sessionStorage.removeItem('explorerSelectedKey');
    }
}

// getObjectKeyByIndex now in main.js module

function getIssueShortLabel(issue) {
    const labels = {
        'orphan': 'Orphan',
        'missing_template': 'Missing Template',
        'missing_command': 'Missing Command',
        'missing_timeperiod': 'Missing Timeperiod',
        'missing_contact': 'Missing Contact',
        'missing_contactgroup': 'Missing Contactgroup',
        'missing_hostgroup': 'Missing Hostgroup',
        'missing_servicegroup': 'Missing Servicegroup',
        'missing_host': 'Missing Host',
        'empty_group': 'Empty Group',
        'unused_template': 'Unused Template',
        'unused_command': 'Unused Command',
        'unused_contact': 'Unused Contact',
        'unused_contactgroup': 'Unused Contactgroup',
        'unused_timeperiod': 'Unused Timeperiod',
        'duplicate_name': 'Duplicate',
        'duplicate': 'Duplicate',
        'long_host_list': 'Long Host List'
    };

    // Handle orphan_service - extract missing host name from message
    if (issue.type === 'orphan_service' && issue.message) {
        const match = issue.message.match(/non-existent host: (.+)$/);
        if (match) {
            return `Missing Host: ${match[1]}`;
        }
        return 'Missing Host';
    }

    // Return mapped label or convert underscores to spaces with title case
    if (labels[issue.type]) {return labels[issue.type];}
    return issue.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// Shared icon for Nagios object types (used in errors tab, references, etc.)
function getObjectTypeIcon(objectType) {
    const typeIcons = {
        'host': '<i class="fa-solid fa-desktop"></i>',
        'hostgroup': '<i class="fa-solid fa-layer-group"></i>',
        'service': '<i class="fa-solid fa-gear"></i>',
        'servicegroup': '<i class="fa-solid fa-gears"></i>',
        'contact': '<i class="fa-solid fa-user"></i>',
        'contactgroup': '<i class="fa-solid fa-users"></i>',
        'command': '<i class="fa-solid fa-bolt"></i>',
        'timeperiod': '<i class="fa-solid fa-clock"></i>',
        'template': '<i class="fa-solid fa-clipboard"></i>',
        'hostdependency': '<i class="fa-solid fa-link"></i>',
        'servicedependency': '<i class="fa-solid fa-link"></i>',
        'hostescalation': '<i class="fa-solid fa-arrow-up"></i>',
        'serviceescalation': '<i class="fa-solid fa-arrow-up"></i>'
    };
    return typeIcons[objectType] || '<i class="fa-solid fa-file"></i>';
}

function getIssueIcon(issue) {
    // Use type-specific icons for cleanup issues (matching groupConfig in renderCleanupSuggestions)
    const typeIcons = {
        'duplicate': '<i class="fa-solid fa-copy"></i>',
        'duplicate_name': '<i class="fa-solid fa-copy"></i>',
        'empty_group': '<i class="fa-solid fa-folder-open"></i>',
        'orphan': '<i class="fa-solid fa-plug"></i>',
        'long_host_list': '<i class="fa-solid fa-list"></i>',
        'unused_template': '<i class="fa-solid fa-clipboard"></i>',
        'unused_command': '<i class="fa-solid fa-bolt"></i>',
        'unused_contact': '<i class="fa-solid fa-user"></i>',
        'unused_contactgroup': '<i class="fa-solid fa-users"></i>',
        'unused_timeperiod': '<i class="fa-solid fa-clock"></i>',
        'missing_template': '<i class="fa-solid fa-clipboard"></i>',
        'missing_host': '<i class="fa-solid fa-desktop"></i>',
        'missing_command': '<i class="fa-solid fa-bolt"></i>',
        'missing_hostgroup': '<i class="fa-solid fa-desktop"></i>',
        'missing_servicegroup': '<i class="fa-solid fa-gear"></i>',
        'missing_contact': '<i class="fa-solid fa-user"></i>',
        'missing_contactgroup': '<i class="fa-solid fa-users"></i>',
        'missing_timeperiod': '<i class="fa-solid fa-clock"></i>'
    };

    if (typeIcons[issue.type]) {return typeIcons[issue.type];}

    // Fall back to severity-based icons for other issues
    if (issue.severity === 'error') {return '<i class="fa-solid fa-circle-xmark"></i>';}
    if (issue.severity === 'warning') {return '<i class="fa-solid fa-triangle-exclamation"></i>';}
    return '<i class="fa-solid fa-circle-info"></i>';
}

async function navigateToObjectIssue() {
    if (!state.currentCenterObject) {return;}

    const obj = state.currentCenterObject;
    const issue = state.currentCenterIssue;
    const hostListInfo = state.currentCenterHostListInfo;

    // Switch to Suggestions tab visually, then load data before highlighting
    Explorer.switchTabs('.nbe-tab', '.right-tab-content', 'suggestions', 'tab', 'Tab');
    await loadAllSuggestions();

    // Find the matching suggestion for this object's issue
    const allSuggestions = Explorer.collectAllSuggestions();
    let matchId = null;

    if (issue) {
        const objName = obj.display_name || obj.name;
        const globalIndex = obj.global_index;

        for (const s of allSuggestions) {
            // Match by object global_index (cleanup suggestions)
            if (s.data?.object?.global_index === globalIndex) {
                matchId = s.id;
                break;
            }
            // Match duplicates by objects array
            if (s.data?.objects?.some(o => o.global_index === globalIndex)) {
                matchId = s.id;
                break;
            }
            // Match grouped errors by referencing object name
            if (s.data?.issues?.some(i => i.object === objName && i.object_type === obj.object_type)) {
                matchId = s.id;
                break;
            }
            // Match health warnings by object name and type
            if (s.data?.issue?.object === objName && s.data?.issue?.object_type === obj.object_type) {
                matchId = s.id;
                break;
            }
        }
    } else if (hostListInfo?.shouldGroup) {
        for (const s of allSuggestions) {
            if (s.type === 'long_host_list' && s.data?.object?.global_index === obj.global_index) {
                matchId = s.id;
                break;
            }
        }
    }

    if (matchId) {
        highlightSuggestionRow(matchId);
    }
}

function highlightSuggestionRow(id) {
    const container = document.getElementById('suggestionsList');
    if (!container) {return;}

    const row = container.querySelector(`.suggestion-row[data-id="${CSS.escape(id)}"]`);
    if (row) {
        // Scroll only the container, not the body (prevents navbar layout shift)
        const rowTop = row.offsetTop - container.offsetTop;
        const centerOffset = rowTop - (container.clientHeight / 2) + (row.offsetHeight / 2);
        container.scrollTo({ top: centerOffset, behavior: 'smooth' });

        row.classList.remove('highlighted');
        void row.offsetWidth;
        row.classList.add('highlighted');
        setTimeout(() => row.classList.remove('highlighted'), 1500);
    }
}

// Open current object in Graph View with all connections expanded
function openInGraphView() {
    if (!state.currentCenterObject) {return;}

    const attrs = state.currentCenterObject.attributes || {};
    const objName = state.currentCenterObject.name || state.currentCenterObject.display_name;
    if (!objName) {
        Explorer.showToast('Cannot determine object name for graph view', 'warning');
        return;
    }

    // Build the node ID in the format used by the graph
    // Services have format "service:target:name" where target is hostgroup or host
    let nodeId;
    if (state.currentCenterObject.object_type === 'service') {
        // Get the target (hostgroup_name or host_name), stripping + prefix and filtering ! exclusions
        let target = attrs.hostgroup_name || attrs.host_name || '';
        if (target) {
            // Clean up: strip + prefix, filter out ! exclusions, take first value
            target = target.split(',')
                .map(t => t.trim())
                .filter(t => !t.startsWith('!'))
                .map(t => t.replace(/^\+/, '').trim())
                .filter(t => t)[0] || '';
        }
        nodeId = target ? `service:${target}:${objName}` : `service:${objName}`;
    } else {
        nodeId = `${state.currentCenterObject.object_type}:${objName}`;
    }

    // Navigate to graph view with this node and expand=true
    const url = `/dependencies?node=${encodeURIComponent(nodeId)}&expand=true`;
    window.location.href = url;
}

// Ensure cleanup suggestions are rendered, then call callback
function ensureCleanupRendered(callback) {
    const container = document.getElementById('cleanupContent');
    // Check if cleanup suggestions are already rendered
    if (container && container.querySelector('.cleanup-suggestion')) {
        callback();
        return;
    }
    // Render if we have suggestions but they're not displayed
    if (state.allCleanupSuggestions.length > 0) {
        renderCleanupSuggestions();
        // Give DOM time to update
        setTimeout(callback, 50);
    } else {
        // Load and render cleanup suggestions
        loadCleanupSuggestions().then(() => {
            setTimeout(callback, 50);
        });
    }
}

function highlightAnalysisItem(tab, objectType, objectName) {
    // Find the matching item in the Errors tab and scroll to it
    // Errors are grouped by the missing object, so we need to search through state.groupedErrors
    setTimeout(() => {
        const container = document.getElementById('issuesContent');
        if (!container) {return;}

        // Find which grouped error contains an issue for this object
        let targetIdx = -1;
        for (let i = 0; i < state.groupedErrors.length; i++) {
            const group = state.groupedErrors[i];
            const hasMatchingIssue = group.issues.some(issue =>
                issue.object === objectName && issue.object_type === objectType
            );
            if (hasMatchingIssue) {
                targetIdx = i;
                break;
            }
        }

        if (targetIdx >= 0) {
            const items = container.querySelectorAll('.cleanup-suggestion');
            if (items[targetIdx]) {
                items[targetIdx].scrollIntoView({ behavior: 'smooth', block: 'center' });
                void items[targetIdx].offsetWidth;
                items[targetIdx].classList.add('highlighted');
                setTimeout(() => items[targetIdx].classList.remove('highlighted'), 2000);
            }
        }
    }, 200);
}

function highlightCleanupItem(globalIndex, suggestionType, checkObjectsArray = false) {
    // Find the matching cleanup item using data-index attribute
    setTimeout(() => {
        const idx = state.allCleanupSuggestions.findIndex(s => {
            if (s.type !== suggestionType) {return false;}
            if (s.object?.global_index === globalIndex) {return true;}
            // Optionally check objects array (for duplicates)
            if (checkObjectsArray && s.objects?.some(o => o.global_index === globalIndex)) {return true;}
            return false;
        });
        if (idx >= 0) {
            const container = document.getElementById('cleanupContent');
            const item = container.querySelector(`.cleanup-suggestion[data-index="${idx}"]`);
            if (item) {
                // Expand the section if collapsed
                const section = item.closest('.cleanup-section');
                if (section?.classList.contains('collapsed')) {
                    section.classList.remove('collapsed');
                }
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Remove class first, force reflow, then add to ensure animation restarts
                item.classList.remove('highlighted');
                void item.offsetWidth;
                item.classList.add('highlighted');
                setTimeout(() => item.classList.remove('highlighted'), 2000);
            }
        }
    }, 200);
}

// Alias for backwards compatibility
function highlightCleanupItemByObject(globalIndex, suggestionType) {
    highlightCleanupItem(globalIndex, suggestionType, true);
}

// Center pane relation loading - moved to relations-loader.js
// (loadCenterInheritance, buildLocalInheritanceChain, renderCenterInheritance,
//  findDependencyObjects, isHostInHostgroup, findEscalationObjects,
//  formatFailureCriteria, formatEscalationInfo, loadCenterReferences,
//  renderCenterReferences, loadCenterMembers, renderCenterMembers)



// Context Menu
// Context menus, bulk actions, drag-drop from tree - moved to context-menu.js
// Target pane, file/folder operations, workspace - moved to file-operations.js
// ============================================================================
// Object Detail Modal
// ============================================================================

function closeObjectDetail() {
    document.getElementById('objectDetailModal').classList.remove('visible');
}

// ============================================================================
// Right Pane Tabs
// ============================================================================

function switchRightTab(tabName) {
    Explorer.switchTabs('.nbe-tab', '.right-tab-content', tabName, 'tab', 'Tab');

    // Auto-load data for tabs
    if (tabName === 'suggestions') {
        // Always render the list when switching to suggestions tab
        // Data may have been loaded during init but not rendered yet
        Explorer.renderUnifiedSuggestionsList();
        loadAllSuggestions();
    } else if (tabName === 'issues') {
        loadIssues();
    } else if (tabName === 'validation') {
        // Only auto-run if not already loaded
        const content = document.getElementById('validationContent');
        if (content.querySelector('.tab-placeholder')) {
            // Don't auto-run validation - it requires explicit action
        }
    }
}

// ============================================================================
// Actions Menu
// ============================================================================

function toggleActionsMenu(event) {
    event.stopPropagation();
    const menu = document.getElementById('actionsMenu');
    const wasVisible = menu.classList.contains('visible');
    menu.classList.toggle('visible');

    // Close on click outside
    if (!wasVisible && menu.classList.contains('visible')) {
        // Remove any existing listener first to prevent duplicates
        document.removeEventListener('click', closeActionsMenu);
        setTimeout(() => {
            document.addEventListener('click', closeActionsMenu, { once: true });
        }, 0);
    }
}

function closeActionsMenu() {
    document.getElementById('actionsMenu').classList.remove('visible');
    // Ensure listener is removed
    document.removeEventListener('click', closeActionsMenu);
}

// ============================================================================
// Suggestions Tab
// ============================================================================

/**
 * Toggle a collapsible suggestion section
 */
function toggleSuggestionSection(sectionName) {
    const section = document.querySelector(`.suggestion-section[data-section="${sectionName}"]`);
    if (!section) {return;}

    const body = document.getElementById(sectionName + 'SectionBody');
    const toggle = section.querySelector('.section-toggle');

    section.classList.toggle('collapsed');
    if (body) {body.classList.toggle('collapsed');}

    // Save expanded state to localStorage
    saveSuggestionSectionState();
}

/**
 * Save suggestion section expanded/collapsed state
 */
function saveSuggestionSectionState() {
    const state = {};
    document.querySelectorAll('.suggestion-section').forEach(section => {
        const name = section.dataset.section;
        state[name] = !section.classList.contains('collapsed');
    });
    try {
        localStorage.setItem('suggestionSectionState', JSON.stringify(state));
    } catch (e) {
        // Ignore localStorage errors
    }
}

/**
 * Restore suggestion section expanded/collapsed state
 */
function restoreSuggestionSectionState() {
    try {
        const saved = localStorage.getItem('suggestionSectionState');
        if (!saved) {return;}
        const state = JSON.parse(saved);
        for (const [name, expanded] of Object.entries(state)) {
            const section = document.querySelector(`.suggestion-section[data-section="${name}"]`);
            const body = document.getElementById(name + 'SectionBody');
            if (section && body) {
                if (expanded) {
                    section.classList.remove('collapsed');
                    body.classList.remove('collapsed');
                } else {
                    section.classList.add('collapsed');
                    body.classList.add('collapsed');
                }
            }
        }
    } catch (e) {
        // Ignore localStorage errors
    }
}

/**
 * Analyze all suggestions with forced refresh
 */
// Analysis functions (suggestions, cleanup, issues, templates, grouping, notification gaps) - moved to analysis.js
// Bulk operations, validation, commit UI, save/cancel - moved to dialogs.js

    // =============================================================================
    // Export Functions to Explorer Namespace
    // =============================================================================

    // Utility functions
    Explorer.refreshRelatedSections = refreshRelatedSections;
    Explorer.hideAutocompleteDropdown = hideAutocompleteDropdown;
    Explorer.handleAutocompleteKeyNav = handleAutocompleteKeyNav;
    Explorer.renderGroupedInfoSection = renderGroupedInfoSection;
    Explorer.updateEditingLockedUI = updateEditingLockedUI;
    Explorer.canEdit = canEdit;

    // Tree view functions
    Explorer.setView = setView;
    Explorer.buildTree = buildTree;
    Explorer.buildFileTree = buildFileTree;
    Explorer.renderStagedCreationTreeItem = renderStagedCreationTreeItem;
    Explorer.handleStagedItemClick = handleStagedItemClick;
    Explorer.updateStagedSelection = updateStagedSelection;
    Explorer.selectStagedCreationForEdit = selectStagedCreationForEdit;
    Explorer.handleStagedContextMenu = handleStagedContextMenu;
    Explorer.handleStagedDragStart = handleStagedDragStart;
    Explorer.buildTypeTree = buildTypeTree;
    Explorer.renderTreeItem = renderTreeItem;
    Explorer.getStagedDisplayName = getStagedDisplayName;
    Explorer.getObjectIssue = getObjectIssue;
    Explorer.getHostListInfo = getHostListInfo;
    Explorer.isTreeItemTemplate = isTreeItemTemplate;
    Explorer.getEffectiveAttributes = getEffectiveAttributes;
    Explorer.getNameFieldForObject = getNameFieldForObject;
    Explorer.getEffectiveName = getEffectiveName;
    Explorer.toggleFolder = toggleFolder;
    Explorer.filterTree = filterTree;
    Explorer.handleItemClick = handleItemClick;
    Explorer.selectObjectByIndex = selectObjectByIndex;
    Explorer.selectObjectByStableKey = selectObjectByStableKey;
    Explorer.updateSelection = updateSelection;
    Explorer.getIssueShortLabel = getIssueShortLabel;
    Explorer.getObjectTypeIcon = getObjectTypeIcon;
    Explorer.getIssueIcon = getIssueIcon;

    // Navigation functions
    Explorer.navigateToObjectIssue = navigateToObjectIssue;
    Explorer.openInGraphView = openInGraphView;
    Explorer.ensureCleanupRendered = ensureCleanupRendered;
    Explorer.highlightAnalysisItem = highlightAnalysisItem;
    Explorer.highlightCleanupItem = highlightCleanupItem;
    Explorer.highlightCleanupItemByObject = highlightCleanupItemByObject;

    // Center pane reference/inheritance functions - see relations-loader.js and impact-section.js

    // UI functions
    Explorer.closeObjectDetail = closeObjectDetail;
    Explorer.switchRightTab = switchRightTab;
    Explorer.toggleActionsMenu = toggleActionsMenu;
    Explorer.closeActionsMenu = closeActionsMenu;
    Explorer.toggleSuggestionSection = toggleSuggestionSection;
    Explorer.saveSuggestionSectionState = saveSuggestionSectionState;
    Explorer.restoreSuggestionSectionState = restoreSuggestionSectionState;

})(window.Explorer);
