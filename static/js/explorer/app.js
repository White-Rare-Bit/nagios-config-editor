/**
 * Nagios Bulk Editor - Explorer Application Module
 *
 * This module contains tree rendering, selection, filtering, and UI coordination.
 */

import { state } from './state.js';
import { constants, isObjectTemplate, getTypeBadge, getTypeBadgeTier } from './constants.js';
import { getObjectKey, findObjectByKey, getSelectedIndices, getConfigRootName } from './main.js';
import { isSelectedByIndex, removeFromSelectionByIndex, clearSelection } from './state-management.js';
import { loadObjects, loadChangedFiles, updateBadges, getTotalStagedCount } from './data-loading.js'; // circular — safe (function-level)
import { openTab, renderTabBar, restoreTabs } from './tab-manager.js'; // circular — safe (function-level)
import { loadIssuesForBadges, loadSuggestionsForBadges } from './badge-issues.js'; // circular — safe (function-level)
import { loadAllSuggestions, loadCleanupSuggestions, renderCleanupSuggestions, collectAllSuggestions, renderUnifiedSuggestionsList } from './analysis.js'; // circular — safe (function-level)
import { navigateToIssue, loadIssues } from './analysis-issues.js'; // circular — safe (function-level)
import { showCenterPaneObject, hideCenterPaneObject, showCenterPaneMultiple, renderCenterAttributes } from './object-editor.js'; // circular — safe (function-level)
import { stageObjectDeletions, stageNewObjectChanges, createNewObject } from './dialogs.js'; // circular — safe (function-level)
import { hideContextMenu, closeDialog, showDialog, showPreview, closePreview, handleDragStart, handleDragEnd, handleContextMenu, handleDragOver, handleDrop } from './context-menu.js'; // circular — safe (function-level)
import { initTargetPane, renderTargetPane, navigateToObjectByIndex } from './file-operations.js'; // circular — safe (function-level)
import { loadImpactAndRelationships } from './impact-section.js'; // circular — safe (function-level)
import { cleanupDragState } from './drag-drop.js';
import { refreshPanelTiers } from './panel-resizer.js';
import { switchTabs, getIcon, toRelativePath } from './ui-utils.js';
import { escapeHtml } from '../app.js';
import { escapeJs } from '../base.js';
import { showToast } from '../ui-notifications.js';
import { showGlobalCommitDialog } from '../commit-dialog.js';
import { getSessionId } from '../session-manager.js';

// Convenience aliases (read at call time, not cached — applyMetadata replaces these)
const typeLabels = constants.typeLabels;
const identityFields = constants.identityFields;
const inheritanceAttrs = constants.inheritanceAttrs;

// Local state (UI-specific)

// Utility: Refresh Impact & Relationships when relevant attributes change
export function refreshRelatedSections(key, obj) {
    // If any reference-related attribute changes, refresh the unified section
    if (inheritanceAttrs.includes(key) || constants.referenceAttrs.includes(key) || key === 'members' || key === 'use') {
        loadImpactAndRelationships(obj);
    }
}

// Utility: Hide autocomplete dropdown with delay
export function hideAutocompleteDropdown(selector, resetCallback) {
    setTimeout(() => {
        const dropdown = selector.startsWith('#')
            ? document.getElementById(selector.slice(1))
            : document.querySelector(selector);
        if (dropdown) {dropdown.remove();}
        if (resetCallback) {resetCallback();}
    }, 150);
}

// Utility: Handle autocomplete keyboard navigation
export function handleAutocompleteKeyNav(event, config) {
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

// Session ID for staging
const mySessionId = getSessionId();

// resetStagingState is now defined in state-management.js

// Update UI to show/hide editing lock state (banner is handled by base.html)
// Lock check is now server-side (ensure_shadow_lock). These are kept for API compatibility.
export function updateEditingLockedUI() {}
export function canEdit() { return true; }

// Load data
document.addEventListener('DOMContentLoaded', async () => {
    // Restore expanded state from localStorage before loadObjects.
    // Paths are stored as relative in localStorage and converted to absolute
    // using current configPath (set by init from template), so they survive
    // shadow→original transitions without migration.
    state.leftTreeExpansion.restore(state.configPath);
    state.rightTreeExpansion.restore(state.configPath);

    // Load objects, files, and folders from backend
    await loadObjects();

    // Load changed files from shadow copy diff (for tree indicators)
    await loadChangedFiles();

    // Restore tabs from sessionStorage
    restoreTabs();

    buildTree();

    let selectionRestored = false;

    // Restore active tab or fall back to saved selection
    if (state.openTabs.length > 0 && state.activeTabKey) {
        const obj = findObjectByKey(state.activeTabKey);
        if (obj) {
            openTab(obj);
            selectionRestored = true;
        }
    } else {
        const savedKey = sessionStorage.getItem('explorerSelectedKey');
        if (savedKey) {
            const obj = findObjectByKey(savedKey);
            if (obj) {
                openTab(obj);
                selectionRestored = true;
            }
        }
    }

    // Render tab bar (may be empty if no tabs restored)
    renderTabBar();

    // Show empty state if no selection was restored
    if (!selectionRestored) {
        const emptyState = document.getElementById('centerEmptyState');
        emptyState.classList.remove('u-hidden');
        emptyState.style.display = 'flex';
    }

    // Update badges (commit count, undo button)
    updateBadges();
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
                    handleDragStart(event, index);
                }
            }
        });

        objectTree.addEventListener('dragend', (event) => {
            // Always clean up on dragend, regardless of target
            handleDragEnd(event);
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
            cleanupDragState();
        }
    });

    // Update commit button with any persisted changes
    updateBadges();

    // Load issues in background for badges
    loadIssuesForBadges();

    // Load suggestions in background for badges
    loadSuggestionsForBadges();

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
        setTimeout(async () => {
            const count = await getTotalStagedCount();
            if (count > 0) {
                showGlobalCommitDialog();
            }
        }, 300);
    }

    // Check if we should auto-commit (redirected from another page with Apply button)
    if (urlParams.get('autoCommit') === '1') {
        // Clean URL
        window.history.replaceState({}, '', window.location.pathname);
        // Open commit dialog after a short delay to ensure data is loaded
        setTimeout(async () => {
            const count = await getTotalStagedCount();
            if (count > 0) {
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
            clearSelection();
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

export function setView(view) {
    state.currentView = view;
    document.querySelectorAll('.tree-panel .panel-tab-header .nbe-tab').forEach(btn => {
        const isActive = btn.dataset.view === view;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive);
    });
    buildTree();
}

let currentSearchTerm = '';

export function buildTree() {
    const container = document.getElementById('treeContent');
    const search = document.getElementById('treeSearch').value.toLowerCase();
    currentSearchTerm = search;
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

    // Filter by orphans and/or issues (OR logic when both checked)
    if (orphansOnly && issuesOnly) {
        filtered = filtered.filter(o =>
            state.orphanIndices.has(getObjectKey(o)) || getObjectIssue(o) !== null
        );
    } else if (orphansOnly) {
        filtered = filtered.filter(o => state.orphanIndices.has(getObjectKey(o)));
    } else if (issuesOnly) {
        filtered = filtered.filter(o => getObjectIssue(o) !== null);
    }

    // Show empty state when no results
    if (filtered.length === 0 && (search || orphansOnly || issuesOnly)) {
        const msg = search
            ? `No objects matching "${escapeHtml(search)}"`
            : 'No matching objects';
        container.innerHTML = `<div class="empty-state"><span class="empty-icon"><i class="fa-solid fa-search"></i></span><div class="empty-title">${msg}</div><div class="empty-desc">${state.allObjects.length} objects in configuration</div></div>`;
        return;
    }

    if (state.currentView === 'file') {
        buildFileTree(container, filtered);
    } else {
        buildTypeTree(container, filtered);
    }

    // Update badge tiers after tree re-render
    if (refreshPanelTiers) {
        refreshPanelTiers();
    }
}

export function buildFileTree(container, objects) {
    const byFile = {};
    objects.forEach(obj => {
        const file = obj.source_file.split('/').pop();
        if (!byFile[file]) {byFile[file] = [];}
        byFile[file].push(obj);
    });

    container.innerHTML = Object.entries(byFile)
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([file, objs]) => {
            const filePath = objs[0].source_file;
            const isOpen = state.leftTreeExpansion.has(filePath);

            const itemsHtml = objs
                .sort((a, b) => a.line_number - b.line_number)
                .map(obj => renderTreeItem(obj))
                .join('');

            return `
            <div class="tree-folder${isOpen ? ' open' : ''}" data-file="${escapeHtml(filePath)}">
                <div class="tree-folder-header" onclick="Explorer.toggleFolder(this.parentElement)"
                     ondragover="Explorer.handleDragOver(event)" ondrop="Explorer.handleDrop(event, '${escapeJs(filePath)}')"
                     ondragleave="if(!this.contains(event.relatedTarget))this.closest('.tree-folder')?.classList.remove('drop-target')">
                    <span class="tree-folder-icon"><i class="fa-solid fa-chevron-right"></i></span>
                    <span class="tree-folder-name">${escapeHtml(file)}</span>
                    <button class="tree-folder-add-btn" onclick="event.stopPropagation(); Explorer.createNewObject('${escapeJs(filePath)}')" title="Add new object">+</button>
                    <span class="tree-folder-count">${objs.length}</span>
                </div>
                <div class="tree-folder-children">
                    ${itemsHtml}
                </div>
            </div>
        `}).join('');
}

export function buildTypeTree(container, objects) {
    const byType = {};
    objects.forEach(obj => {
        if (!byType[obj.object_type]) {byType[obj.object_type] = [];}
        byType[obj.object_type].push(obj);
    });

    container.innerHTML = Object.entries(byType)
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([type, objs]) => {
            const folderKey = 'type:' + type;
            const isOpen = state.leftTreeExpansion.has(folderKey);
            return `
            <div class="tree-folder${isOpen ? ' open' : ''}" data-file="${folderKey}">
                <div class="tree-folder-header" onclick="Explorer.toggleFolder(this.parentElement)">
                    <span class="tree-folder-icon"><i class="fa-solid fa-chevron-right"></i></span>
                    <span class="tree-folder-name">${escapeHtml(type)}</span>
                    <span class="tree-folder-count">${objs.length}</span>
                </div>
                <div class="tree-folder-children">
                    ${objs.map(o => renderTreeItem(o, false)).join('')}
                </div>
            </div>
        `}).join('');
}

/**
 * Check if an object has changed vs the original config (using relative-path stable keys).
 */
function isObjectChanged(obj) {
    if (state.changedObjectKeys.size === 0) { return false; }
    const relPath = toRelativePath(obj.source_file);
    const name = obj.display_name ?? obj.name ?? ('idx:' + obj.global_index);
    const relKey = relPath + '|' + obj.object_type + '|' + name;
    return state.changedObjectKeys.has(relKey);
}

export function renderTreeItem(obj, showType = false) {
    const selected = isSelectedByIndex(obj.global_index) ? 'selected' : '';
    const isTemplate = isTreeItemTemplate(obj);
    const isOrphan = state.orphanIndices.has(getObjectKey(obj));
    const hostListInfo = getHostListInfo(obj);
    const issue = getObjectIssue(obj);
    const orphanClass = isOrphan ? 'is-orphan' : '';
    const changedClass = isObjectChanged(obj) ? 'is-changed' : '';
    const longListClass = hostListInfo.shouldGroup ? 'has-long-list' : '';
    const typeLabel = getTypeBadge(obj.object_type, isTemplate);
    const badgeCompact = getTypeBadgeTier(obj.object_type, isTemplate, 'compact');
    const badgeMedium = getTypeBadgeTier(obj.object_type, isTemplate, 'medium');
    const badgeFull = getTypeBadgeTier(obj.object_type, isTemplate, 'full');
    const matchField = getSearchMatchField(obj);
    const displayName = obj.display_name || obj.name || '(unnamed)';

    return `
        <div class="tree-item ${selected} ${orphanClass} ${changedClass} ${longListClass}"
             data-index="${obj.global_index}"
             draggable="true"
             onclick="Explorer.handleItemClick(event, ${obj.global_index})"
             oncontextmenu="Explorer.handleContextMenu(event, ${obj.global_index})">
            <span class="tree-item-drag-handle" title="Drag to move to another file">${getIcon('grip-vertical')}</span>
            ${issue ? `<span class="tree-item-issue-badge ${issue.severity}" title="${escapeHtml(issue.message)}">${getIssueIcon(issue)}</span>` : ''}
            ${hostListInfo.shouldGroup ? `<span class="tree-item-group-badge" title="Consider using a hostgroup (${hostListInfo.count} hosts)"><i class="fa-solid fa-list"></i></span>` : ''}
            <span class="tree-item-name" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</span>
            ${matchField ? `<span class="tree-item-match-field" title="Matched in ${escapeHtml(matchField)}">${escapeHtml(matchField)}</span>` : ''}
            ${showType ? '' : `<span class="tree-item-type type-${obj.object_type}" title="${obj.object_type}" data-badge-compact="${badgeCompact}" data-badge-medium="${badgeMedium}" data-badge-full="${badgeFull}">${typeLabel}</span>`}
        </div>
    `;
}

// Get which attribute matched the current search term (for attribute-only matches)
function getSearchMatchField(obj) {
    if (!currentSearchTerm) {return null;}
    // If name or type matches, no need to show indicator
    if (obj.display_name.toLowerCase().includes(currentSearchTerm) ||
        obj.object_type.toLowerCase().includes(currentSearchTerm)) {
        return null;
    }
    for (const [key, value] of Object.entries(obj.attributes || {})) {
        if (String(value).toLowerCase().includes(currentSearchTerm)) {
            return key;
        }
        if (key.toLowerCase().includes(currentSearchTerm)) {
            return key;
        }
    }
    return null;
}

// Get display name for an object (shadow copy: attributes are always current)
export function getStagedDisplayName(obj) {
    return obj.display_name || obj.name || '(unnamed)';
}

export function getObjectIssue(obj) {
    const key = `${obj.object_type}:${obj.display_name}`;
    return state.issuesByObject.get(key) || null;
}

// Check if object has a long host list that should probably be a hostgroup
export function getHostListInfo(obj) {
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
export function isTreeItemTemplate(obj) {
    return isObjectTemplate(obj);
}

// Helper to get effective attributes for an object (shadow copy: always current)
export function getEffectiveAttributes(obj) {
    return obj.attributes;
}

// Helper to get the name field that should be used for an object
// Templates use 'name', regular objects use type-specific field (host_name, etc.)
export function getNameFieldForObject(obj) {
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
export function getEffectiveName(obj) {
    const attrs = getEffectiveAttributes(obj);
    const nameField = getNameFieldForObject(obj);
    return attrs[nameField] || obj.name || obj.display_name;
}

export function toggleFolder(folder) {
    folder.classList.toggle('open');
    const filePath = folder.dataset.file;
    if (filePath) {
        state.leftTreeExpansion.toggle(filePath);
        state.leftTreeExpansion.save(state.configPath);
    }
}

window.addEventListener('beforeunload', () => {
    state.leftTreeExpansion.save(state.configPath);
    state.rightTreeExpansion.save(state.configPath);
});

export function filterTree() {
    buildTree();
}

export function handleItemClick(event, index) {
    event.stopPropagation();
    hideContextMenu();

    if (event.ctrlKey || event.metaKey) {
        if (isSelectedByIndex(index)) {
            removeFromSelectionByIndex(index);
        } else {
            selectObjectByIndex(index);
        }
    } else if (event.shiftKey && state.selectedKeys.size > 0) {
        // Range select
        const all = Array.from(document.querySelectorAll('.tree-item:not(.staged-creation)')).map(el => parseInt(el.dataset.index, 10));
        const selectedIndices = getSelectedIndices();
        const lastSelected = Array.from(getSelectedIndices()).pop();
        const start = all.indexOf(lastSelected);
        const end = all.indexOf(index);
        const range = all.slice(Math.min(start, end), Math.max(start, end) + 1);
        range.forEach(i => selectObjectByIndex(i));
    } else {
        clearSelection();
        selectObjectByIndex(index);
    }

    updateSelection();
}

// Simple selection helpers using stable keys
export function selectObjectByIndex(index) {
    const obj = state.allObjects.find(o => o.global_index === index);
    if (obj) {
        state.selectedKeys.add(getObjectKey(obj));
            }
}

/**
 * Select an object by its stable key (file|type|name format).
 * Clears current selection and selects the matching object.
 * @param {string} stableKey - "source_file|object_type|name" format
 */
export function selectObjectByStableKey(stableKey) {
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
        clearSelection();
        state.selectedKeys.add(getObjectKey(obj));
        updateSelection();
        // Scroll to the object in the tree
        scrollToObject(obj.global_index);
    } else {
        showToast(`Object not found: ${objName}`, 'error');
    }
}

// clearSelection, removeFromSelectionByIndex, isSelectedByIndex now in state-management.js

export function updateSelection(options = {}) {
    // Update tree items - highlight selected
    document.querySelectorAll('.tree-item').forEach(el => {
        const index = parseInt(el.dataset.index, 10);
        el.classList.toggle('selected', isSelectedByIndex(index));
    });

    // When called from handleDragEnd, only update CSS — the drop handler
    // will call afterFrontendMutation which rebuilds the center pane.
    if (options.visualOnly) {return;}

    // Update selection count indicator

    // Update center pane based on selection
    if (state.selectedKeys.size === 1) {
        const key = Array.from(state.selectedKeys)[0];
        const obj = findObjectByKey(key);
        if (obj) {
            // If this is a tab switch, center pane is already handled
            if (!state.isTabSwitch) {
                openTab(obj);
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

export function getIssueShortLabel(issue) {
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
export function getObjectTypeIcon(objectType) {
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

export function getIssueIcon(issue) {
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

function suggestionMatchesObject(s, globalIndex, objName, objectType) {
    if (s.data?.object?.global_index === globalIndex) {return true;}
    if (s.data?.objects?.some(o => o.global_index === globalIndex)) {return true;}
    if (s.data?.issues?.some(i => i.object === objName && i.object_type === objectType)) {return true;}
    if (s.data?.issue?.object === objName && s.data?.issue?.object_type === objectType) {return true;}
    return false;
}

function findMatchingSuggestion(obj, issue, hostListInfo, allSuggestions) {
    if (issue) {
        const objName = obj.display_name || obj.name;
        for (const s of allSuggestions) {
            if (suggestionMatchesObject(s, obj.global_index, objName, obj.object_type)) {return s.id;}
        }
    } else if (hostListInfo?.shouldGroup) {
        for (const s of allSuggestions) {
            if (s.type === 'long_host_list' && s.data?.object?.global_index === obj.global_index) {return s.id;}
        }
    }
    return null;
}

export async function navigateToObjectIssue() {
    if (!state.currentCenterObject) {return;}

    const obj = state.currentCenterObject;

    switchTabs('.nbe-tab', '.right-tab-content', 'suggestions', 'tab', 'Tab');
    await loadAllSuggestions();

    const allSuggestions = collectAllSuggestions();
    const matchId = findMatchingSuggestion(obj, state.currentCenterIssue, state.currentCenterHostListInfo, allSuggestions);

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
        row.offsetWidth; // force reflow
        row.classList.add('highlighted');
        setTimeout(() => row.classList.remove('highlighted'), 1500);
    }
}

// Open current object in Graph View with all connections expanded
export function openInGraphView() {
    if (!state.currentCenterObject) {return;}

    const attrs = state.currentCenterObject.attributes || {};
    const objName = state.currentCenterObject.name || state.currentCenterObject.display_name;
    if (!objName) {
        showToast('Cannot determine object name for graph view', 'warning');
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
export function ensureCleanupRendered(callback) {
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

export function highlightAnalysisItem(tab, objectType, objectName) {
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
                items[targetIdx].offsetWidth; // force reflow
                items[targetIdx].classList.add('highlighted');
                setTimeout(() => items[targetIdx].classList.remove('highlighted'), 2000);
            }
        }
    }, 200);
}

export function highlightCleanupItem(globalIndex, suggestionType, checkObjectsArray = false) {
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
                item.offsetWidth; // force reflow
                item.classList.add('highlighted');
                setTimeout(() => item.classList.remove('highlighted'), 2000);
            }
        }
    }, 200);
}

// Alias for backwards compatibility
export function highlightCleanupItemByObject(globalIndex, suggestionType) {
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

export function closeObjectDetail() {
    document.getElementById('objectDetailModal').classList.remove('visible');
}

// ============================================================================
// Right Pane Tabs
// ============================================================================

export function switchRightTab(tabName) {
    switchTabs('.nbe-tab', '.right-tab-content', tabName, 'tab', 'Tab');

    // Auto-load data for tabs
    if (tabName === 'suggestions') {
        // Always render the list when switching to suggestions tab
        // Data may have been loaded during init but not rendered yet
        renderUnifiedSuggestionsList();
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

export function toggleActionsMenu(event) {
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

export function closeActionsMenu() {
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
export function toggleSuggestionSection(sectionName) {
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
export function saveSuggestionSectionState() {
    const sectionState = {};
    document.querySelectorAll('.suggestion-section').forEach(section => {
        const name = section.dataset.section;
        sectionState[name] = !section.classList.contains('collapsed');
    });
    try {
        localStorage.setItem('suggestionSectionState', JSON.stringify(sectionState));
    } catch (e) {
        // Ignore localStorage errors
    }
}

/**
 * Restore suggestion section expanded/collapsed state
 */
export function restoreSuggestionSectionState() {
    try {
        const saved = localStorage.getItem('suggestionSectionState');
        if (!saved) {return;}
        const sectionState = JSON.parse(saved);
        for (const [name, expanded] of Object.entries(sectionState)) {
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


// onclick/oncontextmenu handlers in generated HTML — must be on window.Explorer
window.Explorer = window.Explorer || {};
window.Explorer.toggleFolder = toggleFolder;
window.Explorer.handleItemClick = handleItemClick;
window.Explorer.handleContextMenu = handleContextMenu;
window.Explorer.handleDragOver = handleDragOver;
window.Explorer.handleDrop = handleDrop;
window.Explorer.createNewObject = createNewObject;
