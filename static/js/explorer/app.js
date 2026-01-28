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
        loadImpactAndRelationships(obj);
    }
}

// Utility: Hide autocomplete dropdown with delay
function hideAutocompleteDropdown(selector, resetCallback) {
    setTimeout(() => {
        const dropdown = selector.startsWith('#')
            ? document.getElementById(selector.slice(1))
            : document.querySelector(selector);
        if (dropdown) dropdown.remove();
        if (resetCallback) resetCallback();
    }, 150);
}

// Utility: Handle autocomplete keyboard navigation
function handleAutocompleteKeyNav(event, config) {
    const dropdown = config.selector.startsWith('#')
        ? document.getElementById(config.selector.slice(1))
        : document.querySelector(config.selector);
    if (!dropdown) return false;

    const items = dropdown.querySelectorAll('.attr-autocomplete-item');
    if (items.length === 0) return false;

    const currentIndex = config.getIndex();

    if (event.key === 'ArrowDown') {
        event.preventDefault();
        const newIndex = Math.min(currentIndex + 1, items.length - 1);
        config.setIndex(newIndex);
        items.forEach((item, i) => item.classList.toggle('highlighted', i === newIndex));
        if (items[newIndex]) items[newIndex].scrollIntoView({ block: 'nearest' });
        return true;
    } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        const newIndex = Math.max(currentIndex - 1, 0);
        config.setIndex(newIndex);
        items.forEach((item, i) => item.classList.toggle('highlighted', i === newIndex));
        if (items[newIndex]) items[newIndex].scrollIntoView({ block: 'nearest' });
        return true;
    } else if (event.key === 'Enter' && currentIndex >= 0) {
        event.preventDefault();
        const value = items[currentIndex].dataset.value;
        config.onSelect(value);
        return true;
    } else if (event.key === 'Escape' || event.key === 'Tab') {
        dropdown.remove();
        config.setIndex(-1);
        if (config.onClose) config.onClose();
        return true;
    }
    return false;
}

// Utility: Render a grouped info section
function renderGroupedInfoSection(title, items, renderItem, options = {}) {
    if (items.length === 0) return '';
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
    if (isSavingStaging) return;

    try {
        // Check lock status from base.html (updates banner)
        await checkLockStatus();

        const response = await fetch('/api/staging/info');
        const info = await response.json();

        if (info.hasStaging) {
            // Check if staging was modified
            if (info.lastModified && info.lastModified !== lastStagingTimestamp) {
                // Double-check we're not saving (race condition guard)
                if (isSavingStaging) return;

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

    buildTree();

    // Restore selected object from session storage using stable key
    const savedKey = sessionStorage.getItem('explorerSelectedKey');
    let selectionRestored = false;
    if (savedKey) {
        const obj = Explorer.findObjectByKey(savedKey);
        if (obj) {
            state.selectedKeys.add(savedKey);
            updateSelection();
            selectionRestored = true;
            // Scroll to item after DOM is ready
            setTimeout(() => {
                const item = document.querySelector(`.tree-item[data-index="${obj.global_index}"]`);
                if (item) {
                    // Ensure parent folder is open
                    const folder = item.closest('.tree-folder');
                    if (folder && !folder.classList.contains('open')) {
                        folder.classList.add('open');
                    }
                    item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }, 100);
        }
    }

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
                const index = parseInt(treeItem.dataset.index);
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
                state.hoveredIndex = parseInt(treeItem.dataset.index);
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

async function loadIssuesForBadges() {
    try {
        const response = await fetch('/api/health-check');
        const result = await response.json();
        state.allIssues = result.issues || [];
        state.issuesByObject.clear();
        state.allIssues.forEach(issue => {
            const key = `${issue.object_type}:${issue.object}`;
            if (!state.issuesByObject.has(key) || issue.severity === 'error') {
                state.issuesByObject.set(key, issue);
            }
        });

        // Add client-side duplicate detection
        addCleanupIssuesToBadges();

        // Build grouped errors and update badge
        Explorer.filterIssues();
        Explorer.updateBadge('#issuesSectionBadge', state.groupedErrors.length);
        // Re-render tree to show badges
        buildTree();
    } catch (e) {
        console.error('Failed to load issues for badges:', e);
    }
}

// =============================================================================
// Badge Issue Detection Helpers
// =============================================================================

function getObjectIdentity(obj) {
    switch (obj.object_type) {
        case 'host': return obj.attributes.host_name;
        case 'service':
            return `${obj.attributes.host_name || obj.attributes.hostgroup_name || '*'}::${obj.attributes.service_description}`;
        case 'contact': return obj.attributes.contact_name;
        case 'hostgroup': return obj.attributes.hostgroup_name;
        case 'servicegroup': return obj.attributes.servicegroup_name;
        case 'contactgroup': return obj.attributes.contactgroup_name;
        case 'command': return obj.attributes.command_name;
        case 'timeperiod': return obj.attributes.timeperiod_name;
        default: return null;
    }
}

function addDuplicateIssuesToBadges() {
    const identityMap = new Map();

    for (const obj of state.allObjects) {
        if (obj.attributes.register === '0') continue;
        const identity = getObjectIdentity(obj);
        if (identity) {
            const key = `${obj.object_type}:${identity}`;
            if (!identityMap.has(key)) identityMap.set(key, []);
            identityMap.get(key).push(obj);
        }
    }

    for (const [key, objects] of identityMap) {
        if (objects.length > 1) {
            const identity = key.substring(key.indexOf(':') + 1);
            objects.forEach(obj => {
                const issueKey = `${obj.object_type}:${obj.display_name}`;
                const otherFiles = objects
                    .filter(o => o.global_index !== obj.global_index)
                    .map(o => o.source_file.split('/').pop())
                    .join(', ');
                state.issuesByObject.set(issueKey, {
                    type: 'duplicate_name',
                    severity: 'error',
                    object: obj.name || obj.display_name,
                    object_type: obj.object_type,
                    file: obj.source_file,
                    message: `Duplicate ${obj.object_type} name (also in ${otherFiles})`,
                    identity: identity
                });
            });
        }
    }
}

function buildUsageSets() {
    const usedCommands = new Set();
    const usedContacts = new Set();
    const usedContactgroups = new Set();
    const usedTimeperiods = new Set();
    const usedTemplates = new Set();

    const commandAttrs = ['check_command', 'event_handler', 'host_notification_commands', 'service_notification_commands'];
    const timeperiodAttrs = ['check_period', 'notification_period', 'host_notification_period', 'service_notification_period', 'dependency_period', 'exclude'];
    const stripPfx = s => s.trim().replace(/^[+!]+/, '').trim();

    for (const obj of state.allObjects) {
        for (const attr of commandAttrs) {
            if (obj.attributes[attr]) {
                obj.attributes[attr].split(',').map(s => s.trim().split('!')[0]).forEach(cmd => usedCommands.add(cmd));
            }
        }
        if (obj.attributes.contacts) {
            obj.attributes.contacts.split(',').map(stripPfx).forEach(c => usedContacts.add(c));
        }
        if (obj.attributes.contact_groups) {
            obj.attributes.contact_groups.split(',').map(stripPfx).forEach(cg => usedContactgroups.add(cg));
        }
        for (const attr of timeperiodAttrs) {
            if (obj.attributes[attr]) {
                obj.attributes[attr].split(',').map(stripPfx).forEach(tp => usedTimeperiods.add(tp));
            }
        }
        if (obj.attributes.use) {
            obj.attributes.use.split(',').map(stripPfx).forEach(u => usedTemplates.add(u));
        }
    }

    // Contact group members count as used contacts
    const contactgroups = state.allObjects.filter(o => o.object_type === 'contactgroup');
    for (const cg of contactgroups) {
        if (cg.attributes.members) {
            cg.attributes.members.split(',').map(stripPfx).forEach(c => usedContacts.add(c));
        }
        if (cg.attributes.contactgroup_members) {
            cg.attributes.contactgroup_members.split(',').map(stripPfx).forEach(c => usedContactgroups.add(c));
        }
    }

    // Contacts can reference contactgroups
    const contacts = state.allObjects.filter(o => o.object_type === 'contact');
    for (const contact of contacts) {
        if (contact.attributes.contactgroups) {
            contact.attributes.contactgroups.split(',').map(stripPfx).forEach(cg => usedContactgroups.add(cg));
        }
    }

    return { usedCommands, usedContacts, usedContactgroups, usedTimeperiods, usedTemplates };
}

function addUnusedIssuesToBadges(usageSets) {
    const { usedCommands, usedContacts, usedContactgroups, usedTimeperiods, usedTemplates } = usageSets;

    for (const obj of state.allObjects) {
        const issueKey = `${obj.object_type}:${obj.display_name}`;
        if (state.issuesByObject.has(issueKey) && state.issuesByObject.get(issueKey).severity === 'error') continue;

        if (obj.attributes.register === '0') {
            const templateName = obj.attributes.name;
            if (templateName && !usedTemplates.has(templateName)) {
                state.issuesByObject.set(issueKey, { type: 'unused_template', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused template' });
            }
            continue;
        }

        if (obj.object_type === 'command') {
            const cmdName = obj.attributes.command_name;
            if (cmdName && !usedCommands.has(cmdName)) {
                state.issuesByObject.set(issueKey, { type: 'unused_command', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused command' });
            }
        }

        if (obj.object_type === 'contact') {
            const contactName = obj.attributes.contact_name;
            if (contactName && !usedContacts.has(contactName)) {
                state.issuesByObject.set(issueKey, { type: 'unused_contact', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused contact' });
            }
        }

        if (obj.object_type === 'contactgroup') {
            const cgName = obj.attributes.contactgroup_name;
            if (cgName && !usedContactgroups.has(cgName)) {
                state.issuesByObject.set(issueKey, { type: 'unused_contactgroup', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused contactgroup' });
            }
        }

        if (obj.object_type === 'timeperiod') {
            const tpName = obj.attributes.timeperiod_name;
            if (tpName && !usedTimeperiods.has(tpName)) {
                state.issuesByObject.set(issueKey, { type: 'unused_timeperiod', severity: 'warning', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Unused timeperiod' });
            }
        }
    }
}

function addEmptyGroupIssuesToBadges() {
    const groupTypes = [
        { type: 'hostgroup', nameAttr: 'hostgroup_name', memberAttrs: ['members', 'hostgroup_members'], memberOf: 'hostgroups' },
        { type: 'servicegroup', nameAttr: 'servicegroup_name', memberAttrs: ['members', 'servicegroup_members'], memberOf: 'servicegroups' },
        { type: 'contactgroup', nameAttr: 'contactgroup_name', memberAttrs: ['members', 'contactgroup_members'], memberOf: 'contactgroups' }
    ];

    for (const gt of groupTypes) {
        const groups = state.allObjects.filter(o => o.object_type === gt.type);
        for (const group of groups) {
            const groupName = group.attributes[gt.nameAttr];
            if (!groupName) continue;

            const issueKey = `${group.object_type}:${group.display_name}`;
            if (state.issuesByObject.has(issueKey) && state.issuesByObject.get(issueKey).severity === 'error') continue;

            const hasDirectMembers = gt.memberAttrs.some(attr => group.attributes[attr] && group.attributes[attr].trim() !== '');

            let hasIndirectMembers = false;
            for (const obj of state.allObjects) {
                if (obj.attributes[gt.memberOf]) {
                    const memberOfGroups = obj.attributes[gt.memberOf].split(',').map(s => s.trim().replace(/^[+!]+/, '').trim());
                    if (memberOfGroups.includes(groupName)) {
                        hasIndirectMembers = true;
                        break;
                    }
                }
            }

            if (!hasDirectMembers && !hasIndirectMembers) {
                state.issuesByObject.set(issueKey, { type: 'empty_group', severity: 'warning', object: group.name || group.display_name, object_type: group.object_type, file: group.source_file, message: `Empty ${gt.type} - no members` });
            }
        }
    }
}

function addOrphanIssuesToBadges() {
    const orphanCache = buildOrphanCache();
    for (const obj of state.allObjects) {
        if (obj.attributes.register === '0') continue;
        if (orphanCache.has(obj.global_index)) {
            const issueKey = `${obj.object_type}:${obj.display_name}`;
            const existingIssue = state.issuesByObject.get(issueKey);
            if (existingIssue && existingIssue.severity === 'error') continue;
            state.issuesByObject.set(issueKey, { type: 'orphan', severity: 'info', object: obj.name || obj.display_name, object_type: obj.object_type, file: obj.source_file, message: 'Orphan - not referenced by anything' });
        }
    }
}

// =============================================================================
// Main Badge Issue Function
// =============================================================================

function addCleanupIssuesToBadges() {
    addDuplicateIssuesToBadges();
    const usageSets = buildUsageSets();
    addUnusedIssuesToBadges(usageSets);
    addEmptyGroupIssuesToBadges();
    addOrphanIssuesToBadges();
}


// Staged issues from pending edits (broken references, orphans, etc.)
let stagedIssues = [];

// Compute issues that would result from staged changes
function computeStagedIssues() {
    stagedIssues = [];

    if (state.pendingEdits.size === 0) {
        updateStagedIssuesUI();
        return;
    }

    // Build a map of original names -> new names for renamed objects
    const renames = new Map(); // "type:originalName" -> newName
    for (const [idx, edit] of state.pendingEdits) {
        const obj = state.allObjects.find(o => o.global_index === idx);
        if (!obj) continue;

        const nameField = getNameFieldForObject(obj);
        const originalName = edit.original[nameField] || obj.name || obj.display_name;
        const newName = edit.edited[nameField];

        if (originalName && newName && originalName !== newName) {
            renames.set(`${obj.object_type}:${originalName}`, { newName, obj });
        }
    }

    if (renames.size === 0) {
        updateStagedIssuesUI();
        return;
    }

    // Reference fields that point to other objects
    const referenceFields = {
        'use': null, // template - same type as object
        'host_name': 'host',
        'hostgroup_name': 'hostgroup',
        'hostgroups': 'hostgroup',
        'parents': 'host',
        'contacts': 'contact',
        'contact_groups': 'contactgroup',
        'check_command': 'command',
        'event_handler': 'command',
        'notification_commands': 'command',
        'check_period': 'timeperiod',
        'notification_period': 'timeperiod',
        'members': null, // depends on group type
        'dependent_host_name': 'host',
        'dependent_hostgroup_name': 'hostgroup',
    };

    // Check all objects for references to renamed objects
    state.allObjects.forEach(o => {
        // Skip deleted objects
        if (state.stagedObjectDeletions.has(o.global_index)) return;

        const attrs = getEffectiveAttributes(o);

        for (const [field, refType] of Object.entries(referenceFields)) {
            if (!attrs[field]) continue;

            // Determine the actual type being referenced
            let targetType = refType;
            if (field === 'use') {
                targetType = o.object_type; // Templates are same type
            } else if (field === 'members') {
                // Members type depends on group type
                if (o.object_type === 'hostgroup') targetType = 'host';
                else if (o.object_type === 'contactgroup') targetType = 'contact';
                else if (o.object_type === 'servicegroup') targetType = 'service';
                else continue;
            }

            if (!targetType) continue;

            // Check each referenced value
            const values = attrs[field].split(',').map(v => v.trim().split('!')[0]); // Remove command args
            values.forEach(val => {
                if (!val || val === '*') return;

                const renameKey = `${targetType}:${val}`;
                const rename = renames.get(renameKey);

                if (rename) {
                    // This object references something that was renamed
                    const displayName = getStagedDisplayName(o);
                    stagedIssues.push({
                        severity: 'error',
                        type: 'broken_reference',
                        object_type: o.object_type,
                        object: displayName,
                        message: `References "${val}" which was renamed to "${rename.newName}". Update the ${field} field.`,
                        file: o.source_file,
                        field: field,
                        oldValue: val,
                        newValue: rename.newName,
                        staged: true
                    });
                }
            });
        }
    });

    updateStagedIssuesUI();
}

// Update the issues UI with staged issues (call before buildTree for efficiency)
function updateStagedIssuesUI() {
    // Clear staged issues from state.issuesByObject first
    for (const [key, issue] of state.issuesByObject) {
        if (issue.staged) {
            state.issuesByObject.delete(key);
        }
    }

    // Add new staged issues to map
    stagedIssues.forEach(issue => {
        const key = `${issue.object_type}:${issue.object}`;
        // Staged issues take precedence
        state.issuesByObject.set(key, issue);
    });

    // Rebuild grouped errors and update badge
    Explorer.filterIssues();

    const badge = document.getElementById('issuesSectionBadge');
    if (badge) {
        badge.textContent = state.groupedErrors.length;
        badge.style.display = state.groupedErrors.length > 0 ? 'inline-flex' : 'none';
    }

    // Update validation summary banner in suggestions tab
    Explorer.updateValidationSummary();

    // Update the main suggestions badge as well
    Explorer.updateSuggestionsBadge();
}

async function loadSuggestionsForBadges() {
    try {
        // Load issues from server
        const issuesResponse = await fetch('/api/health-check');
        const issuesResult = await issuesResponse.json();
        state.allIssues = issuesResult.issues || [];

        // Load grouping suggestions from server
        const response = await fetch('/api/smart-grouping/suggest');
        const result = await response.json();
        state.allGroupingSuggestions = result.suggestions || [];

        // Load client-side analysis suggestions
        state.allTemplateSuggestions = Explorer.analyzeTemplateConsolidation();
        state.allCleanupSuggestions = Explorer.analyzeCleanupIssues();
        state.allNotificationSuggestions = Explorer.analyzeNotificationGaps();

        // Build grouped errors (this populates state.groupedErrors array)
        Explorer.filterIssues();

        // Update main badge (total of all suggestions including grouped errors)
        const totalCount = state.groupedErrors.length + state.allGroupingSuggestions.length + state.allTemplateSuggestions.length +
                           state.allCleanupSuggestions.length + state.allNotificationSuggestions.length;
        Explorer.updateBadge('#suggestionsBadge', totalCount);

        // Update section badges
        Explorer.updateBadge('#issuesSectionBadge', state.groupedErrors.length);
        Explorer.updateBadge('#groupingSectionBadge', state.allGroupingSuggestions.length);
        Explorer.updateBadge('#templatesSectionBadge', state.allTemplateSuggestions.length);
        Explorer.updateBadge('#cleanupSectionBadge', state.allCleanupSuggestions.length);
        Explorer.updateBadge('#notificationsSectionBadge', state.allNotificationSuggestions.length);

        // Update validation summary banner
        Explorer.updateValidationSummary();
    } catch (e) {
        console.error('Failed to load suggestions for badges:', e);
    }
}

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
    document.querySelectorAll('.tree-panel .right-pane-header .nbe-tab').forEach(btn => {
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
        buildOrphanCache(); // Ensure cache is built
        filtered = filtered.filter(o => isObjectOrphan(o));
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
        if (!byFile[file]) byFile[file] = [];
        byFile[file].push(obj);
    });

    // Group staged creations by file
    const stagedByFile = {};
    state.stagedCreations.forEach((creation, idx) => {
        const file = creation.targetFile.split('/').pop();
        if (!stagedByFile[file]) stagedByFile[file] = [];
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
                } else {
                    return renderStagedCreationTreeItem(item.creation, item.idx);
                }
            }).join('');

            return `
            <div class="tree-folder${isOpen ? ' open' : ''}" data-file="${filePath}">
                <div class="tree-folder-header" onclick="Explorer.toggleFolder(this.parentElement)"
                     ondragover="Explorer.handleDragOver(event)" ondrop="Explorer.handleDrop(event, '${filePath}')"
                     ondragleave="if(!this.contains(event.relatedTarget))this.closest('.tree-folder')?.classList.remove('drop-target')">
                    <span class="tree-folder-icon"><i class="fa-solid fa-chevron-right"></i></span>
                    <span class="tree-folder-name">${Explorer.escapeHtml(file)}</span>
                    <button class="tree-folder-add-btn" onclick="event.stopPropagation(); Explorer.createNewObject('${filePath.replace(/'/g, "\\'")}')" title="Add new object">+</button>
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
            <span class="tree-item-type type-${creation.object_type}">${Explorer.escapeHtml(creation.object_type)}</span>
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
        const allStaged = Array.from(document.querySelectorAll('.tree-item.staged-creation')).map(el => parseInt(el.dataset.stagedIndex));
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
        const idx = parseInt(el.dataset.stagedIndex);
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
    if (!creation) return;

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
        if (el) el.classList.add('dragging');
    });
}

function buildTypeTree(container, objects) {
    const byType = {};
    objects.forEach(obj => {
        if (!byType[obj.object_type]) byType[obj.object_type] = [];
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
    const isOrphan = isObjectOrphan(obj);
    const hostListInfo = getHostListInfo(obj);
    const issue = getObjectIssue(obj);
    const isDeleted = state.stagedObjectDeletions.has(obj.global_index);
    const isStagedMove = state.stagedMoves.has(Explorer.getObjectKey(obj));
    const orphanClass = isOrphan ? 'is-orphan' : '';
    const longListClass = hostListInfo.shouldGroup ? 'has-long-list' : '';
    const deletedClass = isDeleted ? 'staged-for-deletion' : '';
    const stagedClass = isStagedMove ? 'staged' : '';
    const typeLabel = isTemplate ? `${obj.object_type} template` : obj.object_type;

    // Check if there's a staged edit with a new name
    const displayName = getStagedDisplayName(obj);

    // Don't allow interaction with deleted objects except to undo
    if (isDeleted) {
        return `
        <div class="tree-item ${deletedClass}"
             data-index="${obj.global_index}">
            <span class="tree-item-delete-badge" title="Staged for deletion">−</span>
            <span class="tree-item-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
            ${showType ? '' : `<span class="tree-item-type type-${obj.object_type}">${typeLabel}</span>`}
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
            ${showType ? '' : `<span class="tree-item-type type-${obj.object_type}">${typeLabel}</span>`}
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
    if (!hostName) return { shouldGroup: false, count: 0 };

    // If already using hostgroup_name, no need to suggest
    if (obj.attributes.hostgroup_name) return { shouldGroup: false, count: 0 };

    // Count hosts (excluding wildcards)
    const hosts = hostName.split(',').map(h => h.trim()).filter(h => h && h !== '*');

    return {
        shouldGroup: hosts.length > HOST_LIST_THRESHOLD,
        count: hosts.length
    };
}

// Check if tree item is a template (lightweight check for rendering)
function isTreeItemTemplate(obj) {
    if (obj.attributes.register === '0') return true;
    if (obj.object_type === 'host' && obj.attributes.name && !obj.attributes.host_name) return true;
    // Service templates have 'name' but no 'service_description' (may have hostgroup_name)
    if (obj.object_type === 'service' && obj.attributes.name && !obj.attributes.service_description) return true;
    if (obj.object_type === 'contact' && obj.attributes.name && !obj.attributes.contact_name) return true;
    return false;
}

// Helper to get effective attributes for an object (considering pending edits)
function getEffectiveAttributes(obj) {
    const pendingEdit = state.pendingEdits.get(obj.global_index);
    return pendingEdit ? pendingEdit.edited : obj.attributes;
}

// Helper to get the name field that should be used for an object
// Templates use 'name', regular objects use type-specific field (host_name, etc.)
function getNameFieldForObject(obj) {
    const typeSpecificFields = {
        'host': 'host_name',
        'hostgroup': 'hostgroup_name',
        'service': 'service_description',
        'servicegroup': 'servicegroup_name',
        'contact': 'contact_name',
        'contactgroup': 'contactgroup_name',
        'command': 'command_name',
        'timeperiod': 'timeperiod_name',
        'hostdependency': 'host_name',
        'servicedependency': 'service_description',
        'hostescalation': 'host_name',
        'serviceescalation': 'service_description'
    };
    const typeField = typeSpecificFields[obj.object_type];
    const attrs = getEffectiveAttributes(obj);

    // Use type-specific field if it exists, otherwise use 'name' (for templates)
    if (typeField && attrs[typeField]) {
        return typeField;
    }
    if (attrs.name) {
        return 'name';
    }
    // Default to type-specific field for objects without either
    return typeField || 'name';
}

// Helper to get effective name for an object (considering pending edits)
function getEffectiveName(obj) {
    const attrs = getEffectiveAttributes(obj);
    const nameField = getNameFieldForObject(obj);
    return attrs[nameField] || obj.name || obj.display_name;
}

// Cache for orphan status (recomputed when pending edits change)
let orphanCache = null;

function invalidateOrphanCache() {
    orphanCache = null;
}

function buildOrphanCache() {
    if (orphanCache) return orphanCache;

    orphanCache = new Set();

    // Build a set of all referenced names by type
    const referencedNames = {
        host: new Set(),
        hostgroup: new Set(),
        service: new Set(),
        servicegroup: new Set(),
        contact: new Set(),
        contactgroup: new Set(),
        command: new Set(),
        timeperiod: new Set()
    };

    // Scan all objects for references (using effective attrs to include pending edits)
    state.allObjects.forEach(obj => {
        const attrs = getEffectiveAttributes(obj);

        // Template references (use)
        if (attrs.use) {
            attrs.use.split(',').forEach(t => {
                const name = t.trim();
                if (name) referencedNames[obj.object_type]?.add(name);
            });
        }

        // Helper to strip +/! prefixes used in Nagios for additive/exclusion syntax
        const stripPrefix = s => s.trim().replace(/^[+!]+/, '').trim();

        // Host references
        if (attrs.host_name) {
            attrs.host_name.split(',').forEach(h => referencedNames.host.add(stripPrefix(h)));
        }
        if (attrs.parents) {
            attrs.parents.split(',').forEach(h => referencedNames.host.add(stripPrefix(h)));
        }

        // Hostgroup references
        if (attrs.hostgroup_name) {
            attrs.hostgroup_name.split(',').forEach(h => referencedNames.hostgroup.add(stripPrefix(h)));
        }
        if (attrs.hostgroups) {
            attrs.hostgroups.split(',').forEach(h => referencedNames.hostgroup.add(stripPrefix(h)));
        }
        if (attrs.hostgroup_members) {
            attrs.hostgroup_members.split(',').forEach(h => referencedNames.hostgroup.add(stripPrefix(h)));
        }

        // Service references (for dependencies)
        if (attrs.dependent_service_description) {
            referencedNames.service.add(stripPrefix(attrs.dependent_service_description));
        }

        // Servicegroup references
        if (attrs.servicegroups) {
            attrs.servicegroups.split(',').forEach(s => referencedNames.servicegroup.add(stripPrefix(s)));
        }
        if (attrs.servicegroup_members) {
            attrs.servicegroup_members.split(',').forEach(s => referencedNames.servicegroup.add(stripPrefix(s)));
        }

        // Contact references
        if (attrs.contacts) {
            attrs.contacts.split(',').forEach(c => referencedNames.contact.add(stripPrefix(c)));
        }
        if (attrs.members && obj.object_type === 'contactgroup') {
            attrs.members.split(',').forEach(c => referencedNames.contact.add(stripPrefix(c)));
        }

        // Contactgroup references
        if (attrs.contact_groups) {
            attrs.contact_groups.split(',').forEach(c => referencedNames.contactgroup.add(stripPrefix(c)));
        }
        if (attrs.contactgroup_members) {
            attrs.contactgroup_members.split(',').forEach(c => referencedNames.contactgroup.add(stripPrefix(c)));
        }

        // Command references
        ['check_command', 'event_handler', 'notification_commands'].forEach(field => {
            if (attrs[field]) {
                attrs[field].split(',').forEach(cmd => {
                    const cmdName = cmd.trim().split('!')[0]; // Remove args
                    if (cmdName) referencedNames.command.add(cmdName);
                });
            }
        });

        // Timeperiod references
        ['check_period', 'notification_period', 'host_notification_period', 'service_notification_period'].forEach(field => {
            if (attrs[field]) {
                referencedNames.timeperiod.add(attrs[field].trim());
            }
        });

        // Hostgroup members (hosts in the group)
        if (attrs.members && obj.object_type === 'hostgroup') {
            attrs.members.split(',').forEach(h => referencedNames.host.add(stripPrefix(h)));
        }

        // Helper to check if an attribute exists in object or template chain
        function hasAttrInTemplateChain(objAttrs, objType, attrName, visited = new Set()) {
            if (objAttrs[attrName]) return true;
            if (!objAttrs.use) return false;
            const usedTpls = objAttrs.use.split(',').map(s => s.trim());
            for (const tplName of usedTpls) {
                if (visited.has(tplName)) continue;
                visited.add(tplName);
                const tpl = state.allObjects.find(o => o.attributes.name === tplName && o.attributes.register === '0' && o.object_type === objType);
                if (tpl) {
                    if (tpl.attributes[attrName]) return true;
                    if (hasAttrInTemplateChain(tpl.attributes, objType, attrName, visited)) return true;
                }
            }
            return false;
        }

        // Fix #1: Hosts with 'hostgroups' attribute (direct or inherited) are in use
        // Mark them as referenced so they're not flagged as orphans
        if (obj.object_type === 'host' && hasAttrInTemplateChain(attrs, 'host', 'hostgroups')) {
            const hostName = getEffectiveName(obj);
            if (hostName) {
                referencedNames.host.add(hostName.trim());
            }
        }

        // Fix #2: Services with valid host_name or hostgroup_name (direct or inherited) are actively monitoring
        // They shouldn't be considered orphans just because nothing references them
        if (obj.object_type === 'service' && (hasAttrInTemplateChain(attrs, 'service', 'host_name') || hasAttrInTemplateChain(attrs, 'service', 'hostgroup_name'))) {
            const serviceName = getEffectiveName(obj);
            if (serviceName) {
                referencedNames.service.add(serviceName.trim());
            }
        }

        // Fix #3: Services with 'servicegroups' attribute (direct or inherited) are in use
        if (obj.object_type === 'service' && hasAttrInTemplateChain(attrs, 'service', 'servicegroups')) {
            const serviceName = getEffectiveName(obj);
            if (serviceName) {
                referencedNames.service.add(serviceName.trim());
            }
        }
    });

    // Now find orphans - objects not referenced by anything
    state.allObjects.forEach(obj => {
        // Use effective name (considering pending edits)
        const effectiveName = getEffectiveName(obj);
        const attrs = getEffectiveAttributes(obj);
        const attrName = attrs.name;

        // Check if this object is referenced
        const refs = referencedNames[obj.object_type];
        if (!refs) return; // Unknown type, skip

        const isReferenced = refs.has(effectiveName) || (attrName && refs.has(attrName));

        if (!isReferenced) {
            orphanCache.add(obj.global_index);
        }
    });

    return orphanCache;
}

function isObjectOrphan(obj) {
    const cache = buildOrphanCache();
    return cache.has(obj.global_index);
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
        const all = Array.from(document.querySelectorAll('.tree-item:not(.staged-creation)')).map(el => parseInt(el.dataset.index));
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
        Explorer.updateSelectionCount && Explorer.updateSelectionCount();
    }
}

/**
 * Select an object by its stable key (file|type|name format).
 * Clears current selection and selects the matching object.
 * @param {string} stableKey - "source_file|object_type|name" format
 */
function selectObjectByStableKey(stableKey) {
    if (!stableKey) return;

    // Parse stable key: "source_file|object_type|name"
    const parts = stableKey.split('|');
    if (parts.length < 3) return;

    const [sourceFile, objType, objName] = parts;

    // Find the object
    const obj = state.allObjects.find(o =>
        o.source_file === sourceFile &&
        o.object_type === objType &&
        (o.get_name?.() === objName || o.display_name === objName || o.attributes?.name === objName)
    );

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
        const index = parseInt(el.dataset.index);
        el.classList.toggle('selected', Explorer.isSelectedByIndex(index));
        el.classList.toggle('staged', state.stagedMoves.has(Explorer.getObjectKeyByIndex(index)));
    });

    // Update selection count indicator
    Explorer.updateSelectionCount && Explorer.updateSelectionCount();

    // Update center pane based on selection
    if (state.selectedKeys.size === 1) {
        const key = Array.from(state.selectedKeys)[0];
        const obj = Explorer.findObjectByKey(key);
        if (obj) {
            showCenterPaneObject(obj);
            // Save selected object key for persistence
            sessionStorage.setItem('explorerSelectedKey', key);
        }
    } else if (state.selectedKeys.size === 0) {
        hideCenterPaneObject();
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
    if (labels[issue.type]) return labels[issue.type];
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

    if (typeIcons[issue.type]) return typeIcons[issue.type];

    // Fall back to severity-based icons for other issues
    if (issue.severity === 'error') return '<i class="fa-solid fa-circle-xmark"></i>';
    if (issue.severity === 'warning') return '<i class="fa-solid fa-triangle-exclamation"></i>';
    return '<i class="fa-solid fa-circle-info"></i>';
}

function navigateToObjectIssue() {
    if (!state.currentCenterObject) return;

    // Switch to Analysis tab
    switchRightTab('suggestions');

    if (state.currentCenterIssue) {
        // Map issue badge types to cleanup suggestion types
        const cleanupTypeMap = {
            'orphan': 'orphan',
            'duplicate_name': 'duplicate',
            'empty_group': 'empty_group',
            'unused_template': 'unused_template',
            'unused_command': 'unused_command',
            'unused_contact': 'unused_contact',
            'unused_contactgroup': 'unused_contactgroup',
            'unused_timeperiod': 'unused_timeperiod'
        };

        const cleanupType = cleanupTypeMap[state.currentCenterIssue.type];
        if (cleanupType) {
            switchSuggestionsSubtab('cleanup');
            // Ensure cleanup suggestions are rendered before highlighting
            ensureCleanupRendered(() => {
                if (state.currentCenterIssue.type === 'duplicate_name') {
                    highlightCleanupItemByObject(state.currentCenterObject.global_index, 'duplicate');
                } else {
                    highlightCleanupItem(state.currentCenterObject.global_index, cleanupType);
                }
            });
        } else {
            // Find and highlight in Errors tab
            switchSuggestionsSubtab('errors');
            const objectName = state.currentCenterObject.display_name || state.currentCenterObject.name;
            highlightAnalysisItem('errors', state.currentCenterObject.object_type, objectName);
        }
    } else if (state.currentCenterHostListInfo?.shouldGroup) {
        // Find and highlight in Cleanup tab
        switchSuggestionsSubtab('cleanup');
        // Ensure cleanup suggestions are rendered before highlighting
        ensureCleanupRendered(() => {
            highlightCleanupItem(state.currentCenterObject.global_index, 'long_host_list');
        });
    }
}

// Open current object in Graph View with all connections expanded
function openInGraphView() {
    if (!state.currentCenterObject) return;

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
        if (!container) return;

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
            if (s.type !== suggestionType) return false;
            if (s.object?.global_index === globalIndex) return true;
            // Optionally check objects array (for duplicates)
            if (checkObjectsArray && s.objects?.some(o => o.global_index === globalIndex)) return true;
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

// New object creation, deletion, object editing, attribute management - moved to object-editor.js and dialogs.js
// Center pane details loading
async function loadCenterInheritance(obj) {
    const container = document.getElementById('inheritanceContent');
    const section = document.getElementById('inheritanceSection');

    // For new objects, build inheritance chain locally from use attribute
    if (state.isNewObject) {
        const useAttr = obj.attributes.use;
        if (!useAttr) {
            if (section) section.style.display = 'none';
            container.innerHTML = '';
            return;
        }

        // Build a simple chain from the use attribute
        const templateNames = Explorer.parseCommaValues(useAttr);
        const chain = buildLocalInheritanceChain(obj, templateNames);
        renderCenterInheritance(chain, obj);
        return;
    }

    container.innerHTML = '<div class="loading">Loading inheritance...</div>';

    try {
        // Use original name for API call (server doesn't know about staged changes)
        const response = await fetch(`/api/inheritance/${obj.object_type}/${encodeURIComponent(obj.name || obj.display_name)}`);
        const result = await response.json();

        if (result.error) {
            container.innerHTML = `<div class="empty-message">${Explorer.escapeHtml(result.error)}</div>`;
            return;
        }

        renderCenterInheritance(result.chain, obj);
    } catch (error) {
        container.innerHTML = `<div class="empty-message">Error loading inheritance</div>`;
    }
}

// Build inheritance chain locally for new objects
function buildLocalInheritanceChain(obj, templateNames) {
    const chain = {
        name: obj.display_name || '(new object)',
        object_type: obj.object_type,
        is_template: false,
        parents: []
    };

    function findTemplate(name, objType) {
        return state.allObjects.find(o =>
            o.object_type === objType &&
            (o.attributes.name === name || o.name === name || o.display_name === name)
        );
    }

    function buildParentChain(parentNames, objType) {
        const parents = [];
        for (const name of parentNames) {
            const template = findTemplate(name, objType);
            if (template) {
                const templateUse = Explorer.parseCommaValues(template.attributes.use || '');
                parents.push({
                    name: getEffectiveName(template),
                    object_type: template.object_type,
                    is_template: true,
                    file: template.source_file,
                    parents: buildParentChain(templateUse, objType)
                });
            } else {
                parents.push({
                    name: name,
                    object_type: objType,
                    is_template: true,
                    error: 'Template not found'
                });
            }
        }
        return parents;
    }

    chain.parents = buildParentChain(templateNames, obj.object_type);
    return chain;
}

function renderCenterInheritance(chain, obj) {
    const container = document.getElementById('inheritanceContent');

    // Helper to get staged name for a node (finds object by original name, returns effective name)
    function getStagedNodeName(nodeName, objectType) {
        // Find the object in state.allObjects by its original name
        const matchingObj = state.allObjects.find(o =>
            o.object_type === objectType &&
            (o.name === nodeName || o.display_name === nodeName || o.attributes.name === nodeName)
        );
        if (matchingObj) {
            return getEffectiveName(matchingObj);
        }
        return nodeName; // Fallback to original name
    }

    // Helper to get effective attributes respecting pending edits
    function getEffectiveAttrs(o) {
        const edit = state.pendingEdits.get(o.global_index);
        return edit ? edit.edited : o.attributes;
    }

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
        // Use staged name if available
        const displayName = getStagedNodeName(node.name, obj.object_type);
        const hasChildren = idx < flatArray.length - 1;
        const connector = idx > 0 ? '<span class="dep-tree-connector">↳</span>' : '';

        let nodeClass = '';
        if (isCurrent) nodeClass = 'current';
        else if (isMissing) nodeClass = 'missing';
        else if (isTemplate) nodeClass = 'template';

        let html = `
            <div class="ref-item ${nodeClass} ${isMissing ? '' : 'ref-item-clickable'}" ${isMissing ? '' : `onclick="Explorer.selectObjectByName('${Explorer.escapeJs(node.name)}')"`}>
                ${connector}
                <span class="ref-type-badge type-${obj.object_type}">${obj.object_type}</span>
                <span class="ref-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
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

    // Build parent hosts hierarchy (for hosts only)
    function buildParentHostsTree(hostObj, visited = new Set()) {
        const attrs = getEffectiveAttrs(hostObj);
        const hostName = getEffectiveName(hostObj);

        if (visited.has(hostObj.global_index)) {
            return { name: hostName, circular: true };
        }
        visited.add(hostObj.global_index);

        const parentsAttr = attrs.parents || '';
        const parentNames = Explorer.parseCommaValues(parentsAttr);

        const parentNodes = [];
        for (const parentName of parentNames) {
            const parentObj = state.allObjects.find(o =>
                o.object_type === 'host' && getEffectiveName(o) === parentName
            );
            if (parentObj) {
                parentNodes.push(buildParentHostsTree(parentObj, new Set(visited)));
            } else {
                parentNodes.push({ name: parentName, missing: true });
            }
        }

        return {
            name: hostName,
            file: hostObj.source_file ? hostObj.source_file.split('/').pop() : '',
            obj: hostObj,
            parents: parentNodes
        };
    }

    // Render parent hosts tree (shows parents above, current below)
    function renderParentHostsTree(node, isCurrent = false, depth = 0) {
        const nodeClass = isCurrent ? 'current' : (node.missing ? 'missing' : (node.circular ? 'missing' : ''));
        const clickable = !node.missing && !node.circular && node.obj;
        const connector = depth > 0 ? '<span class="dep-tree-connector">↳</span>' : '';

        let html = '';

        // Render parents first (they appear above)
        if (node.parents && node.parents.length > 0) {
            for (const parent of node.parents) {
                html += renderParentHostsTree(parent, false, depth);
            }
        }

        // Then render current node
        html += `
            <div class="ref-item ${nodeClass} ${clickable ? 'ref-item-clickable' : ''}" ${clickable ? `onclick="Explorer.navigateToObjectByIndex(${node.obj.global_index})"` : ''}>
                ${connector}
                <span class="ref-type-badge type-host">host</span>
                <span class="ref-name" title="${Explorer.escapeHtml(node.name)}">${Explorer.escapeHtml(node.name)}</span>
                ${node.missing ? '<span class="error-marker"><i class="fa-solid fa-xmark"></i> not found</span>' : ''}
                ${node.circular ? '<span class="error-marker"><i class="fa-solid fa-xmark"></i> circular</span>' : ''}
                ${isCurrent ? '<span class="current-marker">current</span>' : ''}
            </div>
        `;

        return html;
    }

    // Render parent hosts as nested tree (parents contain children)
    function renderParentHostsNested(node, isCurrent = false) {
        const nodeClass = isCurrent ? 'current' : (node.missing ? 'missing' : (node.circular ? 'missing' : ''));
        const clickable = !node.missing && !node.circular && node.obj;

        let html = `
            <div class="ref-item ${nodeClass} ${clickable ? 'ref-item-clickable' : ''}" ${clickable ? `onclick="Explorer.navigateToObjectByIndex(${node.obj.global_index})"` : ''}>
                <span class="ref-type-badge type-host">host</span>
                <span class="ref-name" title="${Explorer.escapeHtml(node.name)}">${Explorer.escapeHtml(node.name)}</span>
                ${node.missing ? '<span class="error-marker"><i class="fa-solid fa-xmark"></i> not found</span>' : ''}
                ${node.circular ? '<span class="error-marker"><i class="fa-solid fa-xmark"></i> circular</span>' : ''}
                ${isCurrent ? '<span class="current-marker">current</span>' : ''}
            </div>
        `;

        return html;
    }

    // Recursively render from root parents down to current
    function renderParentsTopDown(node, isCurrent = false, depth = 0) {
        let html = '';

        // First render all parents (they appear at top)
        if (node.parents && node.parents.length > 0) {
            for (const parent of node.parents) {
                html += renderParentsTopDown(parent, false, depth);
            }
        }

        // Then render this node nested under parents
        const nodeClass = isCurrent ? 'current' : (node.missing ? 'missing' : (node.circular ? 'missing' : ''));
        const clickable = !node.missing && !node.circular && node.obj;
        const currentDepth = html ? depth + 1 : depth;
        const connector = currentDepth > 0 ? '<span class="dep-tree-connector">↳</span>' : '';

        const nodeHtml = `
            <div class="ref-item ${nodeClass} ${clickable ? 'ref-item-clickable' : ''}" ${clickable ? `onclick="Explorer.navigateToObjectByIndex(${node.obj.global_index})"` : ''}>
                ${connector}
                <span class="ref-type-badge type-host">host</span>
                <span class="ref-name" title="${Explorer.escapeHtml(node.name)}">${Explorer.escapeHtml(node.name)}</span>
                ${node.missing ? '<span class="error-marker"><i class="fa-solid fa-xmark"></i> not found</span>' : ''}
                ${node.circular ? '<span class="error-marker"><i class="fa-solid fa-xmark"></i> circular</span>' : ''}
                ${isCurrent ? '<span class="current-marker">current</span>' : ''}
            </div>
        `;

        if (html) {
            // Wrap current node as child of parents
            html = `${html}<div class="inheritance-children">${nodeHtml}</div>`;
        } else {
            html = nodeHtml;
        }

        return html;
    }

    // Get staged name for the current object
    const currentDisplayName = getEffectiveName(obj);

    let html = '';

    // Template inheritance section - only show if there are templates
    const hasTemplates = chain && (chain.parents && chain.parents.length > 0);

    if (hasTemplates) {
        html += '<div class="inheritance-section-label">Templates</div>';
        const flatChain = flattenChain(chain);
        flatChain.reverse();
        html += `<div class="inheritance-tree">${renderNestedTree(flatChain)}</div>`;
    }

    // Parent hosts section (only for hosts with parents)
    if (obj.object_type === 'host') {
        const attrs = getEffectiveAttrs(obj);
        const parentsAttr = attrs.parents || '';
        const hasParents = parentsAttr.trim().length > 0;

        if (hasParents) {
            if (html) html += '<div class="u-mt-md"></div>';
            html += '<div class="inheritance-section-label">Parent Hosts</div>';
            const tree = buildParentHostsTree(obj);
            html += `<div class="inheritance-tree">${renderParentsTopDown(tree, true)}</div>`;
        }
    }

    // Hide the section entirely if nothing to display
    const section = document.getElementById('inheritanceSection');
    if (!html) {
        if (section) section.style.display = 'none';
        container.innerHTML = '';
    } else {
        if (section) section.style.display = 'block';
        container.innerHTML = html;
    }
}

// Get effective attributes respecting pending edits.
// Shared across loadCenterReferences, findDependencyObjects, formatFailureCriteria to ensure
// UI reflects staged changes before commit. Returns staged attributes if edit exists, otherwise
// returns original attributes from parsed object.
function getEffectiveAttrs(o) {
    const edit = state.pendingEdits.get(o.global_index);
    return edit ? edit.edited : o.attributes;
}

// Find hostdependency/servicedependency objects referencing this host or service.
// Dependency objects define master/dependent relationships that control execution and notification behavior.
// For hosts: matches host_name (master) and dependent_host_name (dependent) fields.
// For services: matches service_description with host scoping when host_name present; services using only
// hostgroup_name cannot be matched precisely (would require group expansion not implemented).
// Returns {asMaster: [...], asDependent: [...]} where asMaster means this object is the master (others depend
// on it) and asDependent means this object is the dependent (depends on others).
function findDependencyObjects(obj, allObjects) {
    const result = { asMaster: [], asDependent: [] };

    if (obj.object_type === 'host') {
        const hostName = getEffectiveName(obj);
        allObjects.filter(o => o.object_type === 'hostdependency').forEach(depObj => {
            const attrs = getEffectiveAttrs(depObj);
            const masterHost = attrs.host_name;
            const dependentHost = attrs.dependent_host_name;

            if (masterHost === hostName) {
                result.asMaster.push(depObj);
            }
            if (dependentHost === hostName) {
                result.asDependent.push(depObj);
            }
        });
    } else if (obj.object_type === 'service') {
        const serviceName = getEffectiveName(obj);
        const objAttrs = getEffectiveAttrs(obj);
        const hostName = objAttrs.host_name;

        // Uses host_name when present for precise matching; hostgroup_name ignored (would require group expansion not implemented)
        if (!hostName) {
            // Return empty result - cannot match dependencies without explicit host_name
            return result;
        }

        allObjects.filter(o => o.object_type === 'servicedependency').forEach(depObj => {
            const attrs = getEffectiveAttrs(depObj);
            const masterService = attrs.service_description;
            const masterHost = attrs.host_name;
            const dependentService = attrs.dependent_service_description;
            const dependentHost = attrs.dependent_host_name;

            // Match if host context is absent (unscoped) or matches current host (scoped dependency)
            if (masterService === serviceName && (!masterHost || masterHost === hostName)) {
                result.asMaster.push(depObj);
            }
            if (dependentService === serviceName && (!dependentHost || dependentHost === hostName)) {
                result.asDependent.push(depObj);
            }
        });
    }

    return result;
}

// Format failure criteria from dependency object into compact display string.
// Nagios dependency objects use execution_failure_criteria (when to skip execution) and
// notification_failure_criteria (when to skip notifications). Criteria are comma-separated
// state codes: n=up/ok, o=down/unreachable, w=warning, c=critical, u=unknown, p=pending, d=dependent.
// Compact format fits in reference list items without visual clutter (design decision: rejected
// expandable details in favor of inline display).
// Returns "(skip: c,u)" or "(skip: c,u; notify: w,c)" format, or empty string if no criteria defined.
// Invalid criteria formats shown with warning indicator (⚠) to flag configuration errors.
function formatFailureCriteria(depObj) {
    const attrs = getEffectiveAttrs(depObj);
    const parts = [];

    // Nagios failure criteria: valid values are n,o,w,c,u,p,d (comma-separated)
    const validCriteriaPattern = /^[nouwcpd,]+$/;

    if (attrs.execution_failure_criteria) {
        const criteria = attrs.execution_failure_criteria.trim();
        if (validCriteriaPattern.test(criteria)) {
            parts.push(`skip: ${criteria}`);
        } else {
            // Invalid format - show with warning indicator
            parts.push(`skip: ${criteria} ⚠`);
        }
    }
    if (attrs.notification_failure_criteria) {
        const criteria = attrs.notification_failure_criteria.trim();
        if (validCriteriaPattern.test(criteria)) {
            parts.push(`notify: ${criteria}`);
        } else {
            // Invalid format - show with warning indicator
            parts.push(`notify: ${criteria} ⚠`);
        }
    }

    return parts.length > 0 ? `(${parts.join('; ')})` : '';
}

function loadCenterReferences(obj) {
    // Use effective name considering pending edits
    const name = getEffectiveName(obj);

    // Reference fields for dependency detection
    // Must stay in sync with:
    //   - nagios_model.py:REFERENCE_FIELDS (authoritative)
    //   - static/js/explorer/object-editor.js:ATTR_REFERENCE_MAP
    //   - static/js/explorer/main.js:referenceAttrs
    // (4 locations total - update all when adding new reference fields)
    const referenceFields = {
        // Host references
        'host_name': 'host',
        'parents': 'host',
        'dependent_host_name': 'host',
        'master_host_name': 'host',

        // Hostgroup references
        'hostgroup_name': 'hostgroup',
        'hostgroups': 'hostgroup',
        'hostgroup_members': 'hostgroup',
        'dependent_hostgroup_name': 'hostgroup',
        'master_hostgroup_name': 'hostgroup',

        // Servicegroup references
        'servicegroups': 'servicegroup',
        'servicegroup_name': 'servicegroup',
        'servicegroup_members': 'servicegroup',

        // Contact references
        'contacts': 'contact',
        'escalation_contacts': 'contact',

        // Contactgroup references
        'contact_groups': 'contactgroup',
        'contactgroups': 'contactgroup',
        'contactgroup_members': 'contactgroup',
        'escalation_contact_groups': 'contactgroup',

        // Command references
        'check_command': 'command',
        'event_handler': 'command',
        'notification_commands': 'command',
        'host_notification_commands': 'command',
        'service_notification_commands': 'command',

        // Timeperiod references
        'check_period': 'timeperiod',
        'notification_period': 'timeperiod',
        'host_notification_period': 'timeperiod',
        'service_notification_period': 'timeperiod',
        'dependency_period': 'timeperiod',
        'escalation_period': 'timeperiod',
        'exclude': 'timeperiod',

        // Template references (type depends on context)
        'use': null,

        // Group members (type depends on context)
        'members': null
    };

    // Helper to strip +/! prefixes from Nagios additive/exclusion syntax
    const stripRefPrefix = v => v.trim().replace(/^[+!]+/, '').trim();

    // Outgoing references (obj already has staged attrs if passed as state.editedObject)
    const outgoing = [];
    // Command fields use ! to separate command name from arguments
    const commandFields = ['check_command', 'event_handler', 'notification_commands',
                          'host_notification_commands', 'service_notification_commands'];
    for (const [field, refType] of Object.entries(referenceFields)) {
        if (!obj.attributes[field]) continue;
        const values = obj.attributes[field].split(',').map(stripRefPrefix).filter(v => v && v !== '*');
        const actualType = refType || obj.object_type;

        values.forEach(val => {
            // For command fields, strip arguments (everything after first !)
            let lookupVal = val;
            if (commandFields.includes(field) && val.includes('!')) {
                lookupVal = val.split('!')[0];
            }
            const referenced = state.allObjects.find(o =>
                o.object_type === actualType &&
                (getEffectiveName(o) === lookupVal || getEffectiveAttrs(o).name === lookupVal)
            );
            // Exclude self-references (e.g., hostgroup's own hostgroup_name is not a dependency)
            if (referenced && referenced.global_index !== obj.global_index) {
                outgoing.push({ field, object: referenced });
            }
        });
    }

    // Find dependency objects (hostdependency/servicedependency)
    const depObjects = findDependencyObjects(obj, state.allObjects);

    // Add master relationships to outgoing (this object is the master in the dependency)
    depObjects.asMaster.forEach(depObj => {
        outgoing.push({ field: 'dependency_rule', object: depObj, isDependencyRule: true });
    });

    // Incoming references (check pending edits for other objects)
    const incoming = [];
    const objEffectiveAttrs = getEffectiveAttrs(obj);
    state.allObjects.forEach(o => {
        if (o.global_index === obj.global_index) return;
        const attrs = getEffectiveAttrs(o);
        for (const [field, refType] of Object.entries(referenceFields)) {
            if (!attrs[field]) continue;
            const actualType = refType || o.object_type;
            // Escalations reference contacts/contactgroups but have distinct object types (hostescalation/serviceescalation),
            // requiring exception to standard type matching logic
            const isEscalationReference = (o.object_type === 'hostescalation' || o.object_type === 'serviceescalation') &&
                                         (obj.object_type === 'contact' || obj.object_type === 'contactgroup') &&
                                         (field === 'escalation_contacts' || field === 'escalation_contact_groups' ||
                                          field === 'contacts' || field === 'contact_groups');
            if (actualType !== obj.object_type && refType !== null && !isEscalationReference) continue;

            let values = attrs[field].split(',').map(stripRefPrefix);
            // For command fields, strip arguments (everything after first !)
            if (commandFields.includes(field)) {
                values = values.map(v => v.includes('!') ? v.split('!')[0] : v);
            }
            if (values.includes(name) || values.includes(objEffectiveAttrs.name)) {
                incoming.push({ field, object: o });
            }
        }
    });

    // Add dependent relationships to incoming (this object is the dependent in the dependency)
    depObjects.asDependent.forEach(depObj => {
        incoming.push({ field: 'dependency_rule', object: depObj, isDependencyRule: true });
    });

    renderCenterReferences({ outgoing, incoming });
}

function renderCenterReferences(refs) {
    const dependenciesContainer = document.getElementById('dependenciesContent');
    const dependentsContainer = document.getElementById('dependentsContent');
    const { outgoing = [], incoming = [] } = refs;

    // Helper to get effective attributes
    function getEffectiveAttrs(o) {
        const edit = state.pendingEdits.get(o.global_index);
        return edit ? edit.edited : o.attributes;
    }

    // Build parent group chain for a group object
    function getParentGroups(groupObj, visited = new Set()) {
        if (visited.has(groupObj.global_index)) return [];
        visited.add(groupObj.global_index);

        const parents = [];
        const groupType = groupObj.object_type;
        const groupName = getEffectiveName(groupObj);
        const membersAttr = groupType === 'hostgroup' ? 'hostgroup_members' :
                           groupType === 'servicegroup' ? 'servicegroup_members' :
                           groupType === 'contactgroup' ? 'contactgroup_members' : null;

        if (!membersAttr) return [];

        // Find groups that have this group as a member
        state.allObjects.filter(o => o.object_type === groupType).forEach(parentGroup => {
            const attrs = getEffectiveAttrs(parentGroup);
            const members = (attrs[membersAttr] || '').split(',').map(m => m.trim().replace(/^[+!]+/, '').trim());
            if (members.includes(groupName)) {
                parents.push({
                    object: parentGroup,
                    parents: getParentGroups(parentGroup, new Set(visited))
                });
            }
        });

        return parents;
    }

    // Render a simple ref-item (no nesting)
    function renderRefItem(obj, nested = false) {
        const connector = nested ? '<span class="dep-tree-connector">↳</span>' : '';
        return `
            <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${obj.global_index})">
                ${connector}
                <span class="ref-type-badge type-${obj.object_type}">${obj.object_type}</span>
                <span class="ref-name" title="${Explorer.escapeHtml(getStagedDisplayName(obj))}">${Explorer.escapeHtml(getStagedDisplayName(obj))}</span>
            </div>
        `;
    }

    // Get member contacts for a contactgroup
    function getContactGroupMembers(contactGroup) {
        const members = [];
        const attrs = getEffectiveAttributes(contactGroup);
        if (attrs.members) {
            const memberNames = attrs.members.split(',').map(m => m.trim().replace(/^\+/, ''));
            for (const name of memberNames) {
                if (!name || name.startsWith('!')) continue;
                const contact = state.allObjects.find(o =>
                    o.object_type === 'contact' &&
                    o.attributes.contact_name === name
                );
                if (contact) members.push(contact);
            }
        }
        return members;
    }

    // Render a contactgroup with its member contacts
    function renderContactGroupWithMembers(obj, nested = false) {
        let html = renderRefItem(obj, nested);

        // Get and render member contacts
        const members = getContactGroupMembers(obj);
        if (members.length > 0) {
            html += '<div class="inheritance-children">';
            for (const contact of members) {
                html += `
                    <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${contact.global_index})">
                        <span class="dep-tree-connector">↳</span>
                        <span class="ref-type-badge type-contact">contact</span>
                        <span class="ref-name" title="${Explorer.escapeHtml(getStagedDisplayName(contact))}">${Explorer.escapeHtml(getStagedDisplayName(contact))}</span>
                    </div>
                `;
            }
            html += '</div>';
        }
        return html;
    }

    // Consolidate items by their parent and render as tree
    // Returns HTML with parents at top and children nested below
    function renderConsolidatedDepTree(itemsWithParents, itemsWithoutParents) {
        let html = '';

        // Helper to render an object, showing members for contactgroups
        function renderGroupItem(obj, nested = false) {
            if (obj.object_type === 'contactgroup') {
                return renderContactGroupWithMembers(obj, nested);
            }
            return renderRefItem(obj, nested);
        }

        // First, build parent groups so we know which items will appear as parents
        const parentGroups = new Map(); // parent.global_index -> { parent, children: [] }

        for (const { ref, parentChain } of itemsWithParents) {
            for (const parent of parentChain) {
                const parentKey = parent.object.global_index;
                if (!parentGroups.has(parentKey)) {
                    parentGroups.set(parentKey, {
                        parent: parent.object,
                        grandparents: parent.parents || [],
                        children: []
                    });
                }
                // Add this item as a child of the parent
                const group = parentGroups.get(parentKey);
                // Avoid duplicate children
                if (!group.children.some(c => c.global_index === ref.object.global_index)) {
                    group.children.push(ref.object);
                }
            }
        }

        // Now render items without parents, but exclude any that will appear as parents
        for (const ref of itemsWithoutParents) {
            // Skip if this item will be rendered as a parent
            if (!parentGroups.has(ref.object.global_index)) {
                html += renderGroupItem(ref.object, false);
            }
        }

        // Render each parent group
        for (const [parentKey, group] of parentGroups) {
            // Render parent
            html += renderGroupItem(group.parent, false);

            // Render all children nested under parent
            if (group.children.length > 0) {
                html += '<div class="inheritance-children">';
                for (const child of group.children) {
                    html += renderGroupItem(child, true);
                }
                html += '</div>';
            }
        }

        return html;
    }

    function renderGroupedItems(items) {
        if (items.length === 0) return '';

        const groups = Explorer.groupByType(items);
        let html = '';

        // Group types that can have parent hierarchies
        const groupTypes = ['hostgroup', 'servicegroup', 'contactgroup'];

        for (const [type, refs] of Object.entries(groups)) {
            const typeLabel = typeLabels[type] || type;
            const isGroupType = groupTypes.includes(type);

            html += `<div class="ref-type-group"><div class="ref-type-header">${typeLabel}</div>`;

            if (isGroupType) {
                // Check which refs have parent hierarchies
                const refsWithParents = [];
                const refsWithoutParents = [];
                for (const ref of refs) {
                    const parentChain = getParentGroups(ref.object);
                    if (parentChain.length > 0) {
                        refsWithParents.push({ ref, parentChain });
                    } else {
                        refsWithoutParents.push(ref);
                    }
                }

                // Render all group items consolidated by parent
                html += '<div class="ref-type-list">';
                html += renderConsolidatedDepTree(refsWithParents, refsWithoutParents);
                html += '</div>';
            } else {
                // Render as flat list for non-group types
                html += `<div class="ref-type-list">
                    ${refs.map(ref => `
                        <div class="ref-item ${ref.isDependencyRule ? 'dep-rule-item' : ''}" onclick="Explorer.navigateToObjectByIndex(${ref.object.global_index})">
                            ${ref.isDependencyRule ?
                                '<span class="dep-rule-badge">rule</span>' : ''
                            }
                            <span class="ref-type-badge type-${ref.object.object_type}">${ref.object.object_type}</span>
                            <span class="ref-name" title="${Explorer.escapeHtml(getStagedDisplayName(ref.object))}">${Explorer.escapeHtml(getStagedDisplayName(ref.object))}</span>
                            ${ref.isDependencyRule ?
                                `<span class="ref-field">${formatFailureCriteria(ref.object)}</span>` : ''
                            }
                        </div>
                    `).join('')}
                </div>`;
            }

            html += '</div>';
        }
        return html;
    }

    // Render dependencies section
    const dependenciesSection = document.getElementById('dependenciesSection');
    if (outgoing.length === 0) {
        if (dependenciesSection) dependenciesSection.style.display = 'none';
        dependenciesContainer.innerHTML = '';
    } else {
        if (dependenciesSection) dependenciesSection.style.display = 'block';
        dependenciesContainer.innerHTML = renderGroupedItems(outgoing);
    }

    // Render dependents section
    const dependentsSection = document.getElementById('dependentsSection');
    if (incoming.length === 0) {
        if (dependentsSection) dependentsSection.style.display = 'none';
        dependentsContainer.innerHTML = '';
    } else {
        if (dependentsSection) dependentsSection.style.display = 'block';
        dependentsContainer.innerHTML = renderGroupedItems(incoming);
    }
}

function loadCenterMembers(obj) {
    const container = document.getElementById('membersContent');
    // Use effective name considering pending edits
    const objName = getEffectiveName(obj);
    const objEffectiveAttrs = getEffectiveAttributes(obj);
    const members = [];

    // Helper to get effective attributes (respecting pending edits)
    function getEffectiveAttrs(o) {
        const edit = state.pendingEdits.get(o.global_index);
        return edit ? edit.edited : o.attributes;
    }

    if (obj.object_type === 'hostgroup') {
        // Direct members from hostgroup (using staged attrs)
        const directMembers = (objEffectiveAttrs.members || '').split(',').map(x => x.trim()).filter(x => x);
        directMembers.forEach(m => {
            const host = state.allObjects.find(o => o.object_type === 'host' && getEffectiveName(o) === m);
            if (host) members.push({ object: host, via: 'members' });
        });

        // Hosts that have this hostgroup in their hostgroups attribute
        state.allObjects.filter(o => o.object_type === 'host').forEach(host => {
            const attrs = getEffectiveAttrs(host);
            const hgs = (attrs.hostgroups || '').split(',').map(x => x.trim().replace(/^[+!]+/, '').trim());
            if (hgs.includes(objName) && !members.find(m => m.object.global_index === host.global_index)) {
                members.push({ object: host, via: 'hostgroups attr' });
            }
        });
    } else if (obj.object_type === 'contactgroup') {
        // Direct members from contactgroup (using staged attrs)
        const directMembers = (objEffectiveAttrs.members || '').split(',')
            .map(x => x.trim().replace(/^[+!]+/, '').trim())
            .filter(x => x);
        directMembers.forEach(m => {
            const contact = state.allObjects.find(o => o.object_type === 'contact' && getEffectiveName(o) === m);
            if (contact && !members.find(m => m.object.global_index === contact.global_index)) {
                members.push({ object: contact, via: 'members' });
            }
        });

        // Contacts that have this contactgroup in their contactgroups attribute
        state.allObjects.filter(o => o.object_type === 'contact').forEach(contact => {
            const attrs = getEffectiveAttrs(contact);
            const cgs = (attrs.contactgroups || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            if (cgs.includes(objName) && !members.find(m => m.object.global_index === contact.global_index)) {
                members.push({ object: contact, via: 'contactgroups attr' });
            }
        });
    } else if (obj.object_type === 'servicegroup') {
        // Direct members from servicegroup (using staged attrs)
        const directMembers = (objEffectiveAttrs.members || '').split(',')
            .map(x => x.trim().replace(/^[+!]+/, '').trim())
            .filter(x => x);
        directMembers.forEach(m => {
            const svc = state.allObjects.find(o => o.object_type === 'service' && getEffectiveName(o) === m);
            if (svc && !members.find(m => m.object.global_index === svc.global_index)) {
                members.push({ object: svc, via: 'members' });
            }
        });

        // Services that have this servicegroup in their servicegroups attribute
        state.allObjects.filter(o => o.object_type === 'service').forEach(svc => {
            const attrs = getEffectiveAttrs(svc);
            const sgs = (attrs.servicegroups || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            if (sgs.includes(objName) && !members.find(m => m.object.global_index === svc.global_index)) {
                members.push({ object: svc, via: 'servicegroups attr' });
            }
        });
    } else if (isObjectTemplate(obj)) {
        // Find objects using this template
        state.allObjects.forEach(o => {
            // Skip self - check both index and name to be safe
            if (o.global_index === obj.global_index) return;
            if (o.object_type === obj.object_type && getEffectiveName(o) === objName) return;

            const attrs = getEffectiveAttrs(o);
            const uses = (attrs.use || '').split(',').map(x => x.trim());
            if (uses.includes(objName) || uses.includes(objEffectiveAttrs.name)) {
                members.push({ object: o, via: 'inherits' });
            }
        });
    }

    renderCenterMembers(members, obj);
}

function renderCenterMembers(members, obj) {
    const container = document.getElementById('membersContent');
    const section = document.getElementById('membersSection');

    if (members.length === 0) {
        if (section) section.style.display = 'none';
        container.innerHTML = '';
        return;
    }

    // Show section when there are members
    if (section) section.style.display = 'block';

    // Group by type
    const grouped = {};
    members.forEach(m => {
        const type = m.object.object_type;
        if (!grouped[type]) grouped[type] = [];
        grouped[type].push(m);
    });

    let html = '';

    for (const [type, items] of Object.entries(grouped)) {
        html += `
            <div class="ref-type-group">
                <div class="ref-type-header">${typeLabels[type] || type}</div>
                <div class="ref-type-list">
                    ${items.map(m => `
                        <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${m.object.global_index})">
                            <span class="ref-type-badge type-${m.object.object_type}">${m.object.object_type}</span>
                            <span class="ref-name" title="${Explorer.escapeHtml(getStagedDisplayName(m.object))}">${Explorer.escapeHtml(getStagedDisplayName(m.object))}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    container.innerHTML = html;
}

// =============================================================================
// UNIFIED IMPACT & RELATIONSHIPS SECTION
// =============================================================================

/**
 * Load and render the unified Impact & Relationships section.
 * Consolidates Inheritance, Dependencies, Dependents, and Members into one section
 * with question-oriented subsections.
 */
async function loadImpactAndRelationships(obj) {
    const container = document.getElementById('impactContent');
    const section = document.getElementById('impactSection');

    if (!container || !section) return;

    // Show the section
    section.style.display = 'block';

    // Show loading state
    container.innerHTML = '<div class="loading">Loading relationships...</div>';

    // Gather all data in parallel where possible
    const [inheritanceData, referencesData, membersData] = await Promise.all([
        gatherInheritanceData(obj),
        gatherReferencesData(obj),
        gatherMembersData(obj)
    ]);

    // Render the unified section
    renderImpactSection(obj, inheritanceData, referencesData, membersData);
}

/**
 * Gather inheritance/ancestry data (templates + parent hosts)
 */
async function gatherInheritanceData(obj) {
    const result = {
        templateChain: null,
        parentHosts: null
    };

    // For new objects, build inheritance chain locally
    if (state.isNewObject) {
        const useAttr = obj.attributes.use;
        if (useAttr) {
            const templateNames = Explorer.parseCommaValues(useAttr);
            result.templateChain = buildLocalInheritanceChain(obj, templateNames);
        }
    } else {
        // Fetch from API
        try {
            const response = await fetch(`/api/inheritance/${obj.object_type}/${encodeURIComponent(obj.name || obj.display_name)}`);
            const apiResult = await response.json();
            if (!apiResult.error) {
                result.templateChain = apiResult.chain;
            }
        } catch (error) {
            console.error('Error loading inheritance:', error);
        }
    }

    // Build parent hosts tree (for hosts only)
    if (obj.object_type === 'host') {
        const attrs = getEffectiveAttrs(obj);
        if (attrs.parents) {
            result.parentHosts = buildParentHostsTreeData(obj);
        }
    }

    return result;
}

/**
 * Build parent hosts tree data structure
 */
function buildParentHostsTreeData(hostObj, visited = new Set()) {
    const attrs = getEffectiveAttrs(hostObj);
    const hostName = getEffectiveName(hostObj);

    if (visited.has(hostObj.global_index)) {
        return { name: hostName, circular: true };
    }
    visited.add(hostObj.global_index);

    const parentsAttr = attrs.parents || '';
    const parentNames = Explorer.parseCommaValues(parentsAttr);

    const parentNodes = [];
    for (const parentName of parentNames) {
        const parentObj = state.allObjects.find(o =>
            o.object_type === 'host' && getEffectiveName(o) === parentName
        );
        if (parentObj) {
            parentNodes.push(buildParentHostsTreeData(parentObj, new Set(visited)));
        } else {
            parentNodes.push({ name: parentName, missing: true });
        }
    }

    return {
        name: hostName,
        file: hostObj.source_file ? hostObj.source_file.split('/').pop() : '',
        obj: hostObj,
        parents: parentNodes
    };
}

/**
 * Gather references data (outgoing dependencies + incoming dependents)
 */
function gatherReferencesData(obj) {
    const name = getEffectiveName(obj);

    // Reference fields for dependency detection (sync with nagios_model.py:REFERENCE_FIELDS)
    const referenceFields = {
        'host_name': 'host',
        'parents': 'host',
        'dependent_host_name': 'host',
        'master_host_name': 'host',
        'hostgroup_name': 'hostgroup',
        'hostgroups': 'hostgroup',
        'hostgroup_members': 'hostgroup',
        'dependent_hostgroup_name': 'hostgroup',
        'master_hostgroup_name': 'hostgroup',
        'servicegroups': 'servicegroup',
        'servicegroup_name': 'servicegroup',
        'servicegroup_members': 'servicegroup',
        'contacts': 'contact',
        'escalation_contacts': 'contact',
        'contact_groups': 'contactgroup',
        'contactgroups': 'contactgroup',
        'contactgroup_members': 'contactgroup',
        'escalation_contact_groups': 'contactgroup',
        'check_command': 'command',
        'event_handler': 'command',
        'notification_commands': 'command',
        'host_notification_commands': 'command',
        'service_notification_commands': 'command',
        'check_period': 'timeperiod',
        'notification_period': 'timeperiod',
        'host_notification_period': 'timeperiod',
        'service_notification_period': 'timeperiod',
        'dependency_period': 'timeperiod',
        'escalation_period': 'timeperiod',
        'exclude': 'timeperiod',
        'use': null,
        'members': null
    };

    const stripRefPrefix = v => v.trim().replace(/^[+!]+/, '').trim();
    const commandFields = ['check_command', 'event_handler', 'notification_commands',
                          'host_notification_commands', 'service_notification_commands'];

    // Outgoing references (what this object depends on)
    const outgoing = [];
    for (const [field, refType] of Object.entries(referenceFields)) {
        if (!obj.attributes[field]) continue;
        const values = obj.attributes[field].split(',').map(stripRefPrefix).filter(v => v && v !== '*');
        const actualType = refType || obj.object_type;

        values.forEach(val => {
            let lookupVal = val;
            if (commandFields.includes(field) && val.includes('!')) {
                lookupVal = val.split('!')[0];
            }
            const referenced = state.allObjects.find(o =>
                o.object_type === actualType &&
                (getEffectiveName(o) === lookupVal || getEffectiveAttrs(o).name === lookupVal)
            );
            if (referenced && referenced.global_index !== obj.global_index) {
                outgoing.push({ field, object: referenced });
            }
        });
    }

    // Find dependency objects (hostdependency/servicedependency)
    const depObjects = findDependencyObjects(obj, state.allObjects);

    // Add master relationships to outgoing
    depObjects.asMaster.forEach(depObj => {
        outgoing.push({ field: 'dependency_rule', object: depObj, isDependencyRule: true });
    });

    // Incoming references (what references this object - impact of deletion/rename)
    const incoming = [];
    const objEffectiveAttrs = getEffectiveAttrs(obj);
    state.allObjects.forEach(o => {
        if (o.global_index === obj.global_index) return;
        const attrs = getEffectiveAttrs(o);
        for (const [field, refType] of Object.entries(referenceFields)) {
            if (!attrs[field]) continue;
            const actualType = refType || o.object_type;
            const isEscalationReference = (o.object_type === 'hostescalation' || o.object_type === 'serviceescalation') &&
                                         (obj.object_type === 'contact' || obj.object_type === 'contactgroup') &&
                                         (field === 'escalation_contacts' || field === 'escalation_contact_groups' ||
                                          field === 'contacts' || field === 'contact_groups');
            if (actualType !== obj.object_type && refType !== null && !isEscalationReference) continue;

            let values = attrs[field].split(',').map(stripRefPrefix);
            // For command fields, strip arguments (everything after first !)
            if (commandFields.includes(field)) {
                values = values.map(v => v.includes('!') ? v.split('!')[0] : v);
            }
            if (values.includes(name) || values.includes(objEffectiveAttrs.name)) {
                incoming.push({ field, object: o });
            }
        }
    });

    // Add dependent relationships to incoming
    depObjects.asDependent.forEach(depObj => {
        incoming.push({ field: 'dependency_rule', object: depObj, isDependencyRule: true });
    });

    return { outgoing, incoming };
}

/**
 * Gather members data (for groups and templates)
 */
function gatherMembersData(obj) {
    const objName = getEffectiveName(obj);
    const objEffectiveAttrs = getEffectiveAttributes(obj);
    const members = [];
    const memberOf = [];

    // Group membership (what groups this object belongs to)
    if (obj.object_type === 'host') {
        const hostgroups = (objEffectiveAttrs.hostgroups || '').split(',')
            .map(x => x.trim().replace(/^[+!]+/, '').trim())
            .filter(x => x);
        hostgroups.forEach(groupName => {
            const group = state.allObjects.find(o =>
                o.object_type === 'hostgroup' && getEffectiveName(o) === groupName
            );
            if (group) memberOf.push({ object: group, via: 'hostgroups' });
        });
    } else if (obj.object_type === 'service') {
        const servicegroups = (objEffectiveAttrs.servicegroups || '').split(',')
            .map(x => x.trim().replace(/^[+!]+/, '').trim())
            .filter(x => x);
        servicegroups.forEach(groupName => {
            const group = state.allObjects.find(o =>
                o.object_type === 'servicegroup' && getEffectiveName(o) === groupName
            );
            if (group) memberOf.push({ object: group, via: 'servicegroups' });
        });
    } else if (obj.object_type === 'contact') {
        const contactgroups = (objEffectiveAttrs.contactgroups || '').split(',')
            .map(x => x.trim().replace(/^[+!]+/, '').trim())
            .filter(x => x);
        contactgroups.forEach(groupName => {
            const group = state.allObjects.find(o =>
                o.object_type === 'contactgroup' && getEffectiveName(o) === groupName
            );
            if (group) memberOf.push({ object: group, via: 'contactgroups' });
        });
    }

    // For groups: get direct members
    if (obj.object_type === 'hostgroup') {
        const directMembers = (objEffectiveAttrs.members || '').split(',').map(x => x.trim()).filter(x => x);
        directMembers.forEach(m => {
            const host = state.allObjects.find(o => o.object_type === 'host' && getEffectiveName(o) === m);
            if (host) members.push({ object: host, via: 'members' });
        });
        // Hosts with this hostgroup in their hostgroups attribute
        state.allObjects.filter(o => o.object_type === 'host').forEach(host => {
            const attrs = getEffectiveAttrs(host);
            const hgs = (attrs.hostgroups || '').split(',').map(x => x.trim().replace(/^[+!]+/, '').trim());
            if (hgs.includes(objName) && !members.find(m => m.object.global_index === host.global_index)) {
                members.push({ object: host, via: 'hostgroups attr' });
            }
        });
    } else if (obj.object_type === 'contactgroup') {
        const directMembers = (objEffectiveAttrs.members || '').split(',')
            .map(x => x.trim().replace(/^[+!]+/, '').trim())
            .filter(x => x);
        directMembers.forEach(m => {
            const contact = state.allObjects.find(o => o.object_type === 'contact' && getEffectiveName(o) === m);
            if (contact && !members.find(mem => mem.object.global_index === contact.global_index)) {
                members.push({ object: contact, via: 'members' });
            }
        });
        // Contacts with this contactgroup in their contactgroups attribute
        state.allObjects.filter(o => o.object_type === 'contact').forEach(contact => {
            const attrs = getEffectiveAttrs(contact);
            const cgs = (attrs.contactgroups || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            if (cgs.includes(objName) && !members.find(m => m.object.global_index === contact.global_index)) {
                members.push({ object: contact, via: 'contactgroups attr' });
            }
        });
    } else if (obj.object_type === 'servicegroup') {
        const directMembers = (objEffectiveAttrs.members || '').split(',')
            .map(x => x.trim().replace(/^[+!]+/, '').trim())
            .filter(x => x);
        directMembers.forEach(m => {
            const svc = state.allObjects.find(o => o.object_type === 'service' && getEffectiveName(o) === m);
            if (svc && !members.find(mem => mem.object.global_index === svc.global_index)) {
                members.push({ object: svc, via: 'members' });
            }
        });
        // Services with this servicegroup in their servicegroups attribute
        state.allObjects.filter(o => o.object_type === 'service').forEach(svc => {
            const attrs = getEffectiveAttrs(svc);
            const sgs = (attrs.servicegroups || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            if (sgs.includes(objName) && !members.find(m => m.object.global_index === svc.global_index)) {
                members.push({ object: svc, via: 'servicegroups attr' });
            }
        });
    } else if (isObjectTemplate(obj)) {
        // Find objects using this template
        state.allObjects.forEach(o => {
            if (o.global_index === obj.global_index) return;
            if (o.object_type === obj.object_type && getEffectiveName(o) === objName) return;
            const attrs = getEffectiveAttrs(o);
            const uses = (attrs.use || '').split(',').map(x => x.trim());
            if (uses.includes(objName) || uses.includes(objEffectiveAttrs.name)) {
                members.push({ object: o, via: 'inherits' });
            }
        });
    }

    return { members, memberOf };
}

/**
 * Render the unified impact section
 */
function renderImpactSection(obj, inheritanceData, referencesData, membersData) {
    const container = document.getElementById('impactContent');
    const section = document.getElementById('impactSection');

    const { templateChain, parentHosts } = inheritanceData;
    const { outgoing, incoming } = referencesData;
    const { members, memberOf } = membersData;

    // Check if there's any data to show
    const hasTemplateChain = templateChain && templateChain.parents && templateChain.parents.length > 0;
    const hasParentHosts = parentHosts && parentHosts.parents && parentHosts.parents.length > 0;
    const hasIncoming = incoming.length > 0;
    const hasOutgoing = outgoing.length > 0;
    const hasMembers = members.length > 0;
    const hasMemberOf = memberOf.length > 0;

    if (!hasTemplateChain && !hasParentHosts && !hasIncoming && !hasOutgoing && !hasMembers && !hasMemberOf) {
        section.style.display = 'none';
        container.innerHTML = '';
        return;
    }

    let html = '';

    // 1. Configuration Ancestry (Templates + Parent Hosts)
    if (hasTemplateChain || hasParentHosts) {
        html += renderAncestrySubsection(obj, templateChain, parentHosts);
    }

    // 2. "If Deleted/Renamed" (incoming references)
    if (hasIncoming) {
        html += renderIncomingSubsection(incoming);
    }

    // 3. "This Object Requires" (outgoing references)
    if (hasOutgoing) {
        html += renderOutgoingSubsection(outgoing);
    }

    // 4. Group Membership
    if (hasMembers || hasMemberOf) {
        html += renderMembershipSubsection(obj, members, memberOf);
    }

    container.innerHTML = html;

    // Add click handlers for subsection toggles
    container.querySelectorAll('.impact-subsection-header').forEach(header => {
        header.addEventListener('click', () => {
            const subsection = header.closest('.impact-subsection');
            subsection.classList.toggle('expanded');
        });
    });
}

/**
 * Render the Configuration Ancestry subsection
 */
function renderAncestrySubsection(obj, templateChain, parentHosts) {
    const hasTemplates = templateChain && templateChain.parents && templateChain.parents.length > 0;
    const hasParents = parentHosts && parentHosts.parents && parentHosts.parents.length > 0;
    const count = (hasTemplates ? 1 : 0) + (hasParents ? 1 : 0);

    let content = '';

    // Template inheritance chain
    if (hasTemplates) {
        content += '<div class="ancestry-label">Templates</div>';
        content += renderAncestryChain(templateChain, obj.object_type);
    }

    // Parent hosts chain (for hosts only)
    if (hasParents) {
        content += '<div class="ancestry-label">Network Parents</div>';
        content += renderParentHostsChain(parentHosts);
    }

    return `
        <div class="impact-subsection">
            <div class="impact-subsection-header">
                <div class="impact-subsection-title">
                    <i class="fa-solid fa-sitemap"></i>
                    <span>Configuration Ancestry</span>
                </div>
                <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
            </div>
            <div class="impact-subsection-content">${content}</div>
        </div>
    `;
}

/**
 * Render a template ancestry chain as horizontal flow
 */
function renderAncestryChain(chain, objectType) {
    // Flatten the chain from current to root
    function flattenChain(node, path = []) {
        path.push(node);
        const parents = node.parents || [];
        if (parents.length > 0) {
            flattenChain(parents[0], path);
        }
        return path;
    }

    const flat = flattenChain(chain);
    // Reverse so root is first
    flat.reverse();

    let html = '<div class="ancestry-chain">';
    flat.forEach((node, idx) => {
        const isCurrent = idx === flat.length - 1;
        const isMissing = !!node.error;
        // Chain nodes from API have 'name' directly, not display_name
        const displayName = node.name;

        let itemClass = 'ancestry-chain-item';
        if (isCurrent) itemClass += ' current';
        if (isMissing) itemClass += ' missing';

        const clickHandler = isMissing ? '' : `onclick="Explorer.selectObjectByName('${Explorer.escapeJs(node.name)}')"`;

        html += `<span class="${itemClass}" ${clickHandler} title="${Explorer.escapeHtml(displayName)}">`;
        html += `<span class="ref-type-badge type-${objectType}">${objectType}</span>`;
        html += `<span>${Explorer.escapeHtml(displayName)}</span>`;
        if (isMissing) html += `<i class="fa-solid fa-xmark" style="color: var(--nbe-dark-accent-danger); margin-left: 4px;"></i>`;
        html += '</span>';

        if (idx < flat.length - 1) {
            html += '<span class="ancestry-chain-separator"><i class="fa-solid fa-arrow-right"></i></span>';
        }
    });
    html += '</div>';
    return html;
}

/**
 * Render parent hosts chain
 */
function renderParentHostsChain(tree) {
    // Collect all parents into a flat list (from root to current)
    function collectParents(node, list = []) {
        if (node.parents && node.parents.length > 0) {
            node.parents.forEach(p => collectParents(p, list));
        }
        list.push(node);
        return list;
    }

    const flat = collectParents(tree);

    let html = '<div class="ancestry-chain">';
    flat.forEach((node, idx) => {
        const isCurrent = idx === flat.length - 1;
        const isMissing = node.missing;
        const isCircular = node.circular;

        let itemClass = 'ancestry-chain-item';
        if (isCurrent) itemClass += ' current';
        if (isMissing || isCircular) itemClass += ' missing';

        const clickHandler = (isMissing || isCircular || !node.obj)
            ? ''
            : `onclick="Explorer.navigateToObjectByIndex(${node.obj.global_index})"`;

        html += `<span class="${itemClass}" ${clickHandler} title="${Explorer.escapeHtml(node.name)}">`;
        html += '<span class="ref-type-badge type-host">host</span>';
        html += `<span>${Explorer.escapeHtml(node.name)}</span>`;
        if (isMissing) html += '<i class="fa-solid fa-xmark" style="color: var(--nbe-dark-accent-danger); margin-left: 4px;"></i>';
        if (isCircular) html += '<i class="fa-solid fa-rotate" style="color: var(--nbe-dark-accent-warning); margin-left: 4px;" title="Circular reference"></i>';
        html += '</span>';

        if (idx < flat.length - 1) {
            html += '<span class="ancestry-chain-separator"><i class="fa-solid fa-arrow-right"></i></span>';
        }
    });
    html += '</div>';
    return html;
}

/**
 * Render the "If Deleted/Renamed" subsection (incoming references)
 */
function renderIncomingSubsection(incoming) {
    const count = incoming.length;

    // Group by object type
    const grouped = {};
    incoming.forEach(ref => {
        const type = ref.object.object_type;
        if (!grouped[type]) grouped[type] = [];
        grouped[type].push(ref);
    });

    let content = `
        <div class="impact-summary warning">
            <span class="impact-summary-icon"><i class="fa-solid fa-triangle-exclamation"></i></span>
            <span>${count} object${count !== 1 ? 's' : ''} reference${count === 1 ? 's' : ''} this and would need updates</span>
        </div>
    `;

    content += renderGroupedReferences(grouped);

    return `
        <div class="impact-subsection">
            <div class="impact-subsection-header">
                <div class="impact-subsection-title">
                    <i class="fa-solid fa-link-slash"></i>
                    <span>If Deleted/Renamed</span>
                    <span class="impact-subsection-count warning">${count}</span>
                </div>
                <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
            </div>
            <div class="impact-subsection-content">${content}</div>
        </div>
    `;
}

/**
 * Render the "This Object Requires" subsection (outgoing references)
 */
function renderOutgoingSubsection(outgoing) {
    const count = outgoing.length;

    // Group by object type
    const grouped = {};
    outgoing.forEach(ref => {
        const type = ref.object.object_type;
        if (!grouped[type]) grouped[type] = [];
        grouped[type].push(ref);
    });

    let content = `
        <div class="impact-summary info">
            <span class="impact-summary-icon"><i class="fa-solid fa-link"></i></span>
            <span>${count} object${count !== 1 ? 's' : ''} must exist for this to work</span>
        </div>
    `;

    content += renderGroupedReferences(grouped);

    return `
        <div class="impact-subsection">
            <div class="impact-subsection-header">
                <div class="impact-subsection-title">
                    <i class="fa-solid fa-arrow-right-to-bracket"></i>
                    <span>This Object Requires</span>
                    <span class="impact-subsection-count">${count}</span>
                </div>
                <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
            </div>
            <div class="impact-subsection-content">${content}</div>
        </div>
    `;
}

/**
 * Render grouped references (used by both incoming and outgoing)
 */
function renderGroupedReferences(grouped) {
    let html = '';

    for (const [type, refs] of Object.entries(grouped)) {
        const typeLabel = typeLabels[type] || type;
        html += `<div class="ref-type-group"><div class="ref-type-header">${typeLabel} (${refs.length})</div>`;
        html += '<div class="ref-type-list">';

        refs.forEach(ref => {
            const displayName = getStagedDisplayName(ref.object);
            const isDependencyRule = ref.isDependencyRule;

            html += `<div class="ref-item ${isDependencyRule ? 'dep-rule-item' : ''}" onclick="Explorer.navigateToObjectByIndex(${ref.object.global_index})">`;

            if (isDependencyRule) {
                html += '<span class="dep-rule-badge">rule</span>';
            }

            html += `<span class="ref-type-badge type-${ref.object.object_type}">${ref.object.object_type}</span>`;
            html += `<span class="ref-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>`;

            if (isDependencyRule) {
                const criteria = formatFailureCriteriaReadable(ref.object);
                if (criteria) {
                    html += `<span class="ref-field">${criteria}</span>`;
                }
            } else if (ref.field && ref.field !== 'use' && ref.field !== 'members') {
                html += `<span class="ref-attr">${ref.field}</span>`;
            }

            html += '</div>';

            // Add readable criteria details for dependency rules
            if (isDependencyRule) {
                const details = formatFailureCriteriaDetails(ref.object);
                if (details) {
                    html += `<div class="dep-rule-details">${details}</div>`;
                }
            }
        });

        html += '</div></div>';
    }

    return html;
}

/**
 * Format failure criteria as human-readable compact string
 */
function formatFailureCriteriaReadable(depObj) {
    const attrs = getEffectiveAttrs(depObj);
    const parts = [];

    const criteriaMap = {
        'o': 'ok/up',
        'w': 'warning',
        'c': 'critical',
        'u': 'unknown',
        'd': 'down',
        'p': 'pending',
        'n': 'none'
    };

    function expandCriteria(criteria) {
        return criteria.split(',').map(c => criteriaMap[c.trim()] || c.trim()).join(', ');
    }

    if (attrs.execution_failure_criteria && attrs.execution_failure_criteria !== 'n') {
        parts.push(`skip: ${expandCriteria(attrs.execution_failure_criteria)}`);
    }
    if (attrs.notification_failure_criteria && attrs.notification_failure_criteria !== 'n') {
        parts.push(`suppress: ${expandCriteria(attrs.notification_failure_criteria)}`);
    }

    return parts.length > 0 ? `(${parts.join(' | ')})` : '';
}

/**
 * Format failure criteria as detailed explanation
 */
function formatFailureCriteriaDetails(depObj) {
    const attrs = getEffectiveAttrs(depObj);
    let html = '';

    const criteriaMap = {
        'o': 'ok/up',
        'w': 'warning',
        'c': 'critical',
        'u': 'unknown',
        'd': 'down',
        'p': 'pending',
        'n': 'none'
    };

    function expandCriteria(criteria) {
        return criteria.split(',').map(c => criteriaMap[c.trim()] || c.trim()).join(', ');
    }

    if (attrs.execution_failure_criteria && attrs.execution_failure_criteria !== 'n') {
        html += `<div class="dep-rule-detail"><i class="fa-solid fa-ban"></i> Skip checks when master is: ${expandCriteria(attrs.execution_failure_criteria)}</div>`;
    }
    if (attrs.notification_failure_criteria && attrs.notification_failure_criteria !== 'n') {
        html += `<div class="dep-rule-detail"><i class="fa-solid fa-bell-slash"></i> Suppress notifications when master is: ${expandCriteria(attrs.notification_failure_criteria)}</div>`;
    }
    if (attrs.dependency_period) {
        html += `<div class="dep-rule-detail"><i class="fa-solid fa-clock"></i> Active during: ${Explorer.escapeHtml(attrs.dependency_period)}</div>`;
    }

    return html;
}

/**
 * Render the Group Membership subsection
 */
function renderMembershipSubsection(obj, members, memberOf) {
    const totalCount = members.length + memberOf.length;

    let content = '';

    // "Member of" for regular objects
    if (memberOf.length > 0) {
        content += '<div class="ancestry-label">Member of</div>';
        content += '<div class="ref-type-list">';
        memberOf.forEach(item => {
            const displayName = getStagedDisplayName(item.object);
            content += `
                <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${item.object.global_index})">
                    <span class="ref-type-badge type-${item.object.object_type}">${item.object.object_type}</span>
                    <span class="ref-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
                </div>
            `;
        });
        content += '</div>';
    }

    // Direct members for groups/templates
    if (members.length > 0) {
        const label = isObjectTemplate(obj) ? 'Used by (inherits from this template)' : 'Direct Members';
        content += `<div class="ancestry-label">${label}</div>`;

        // Group by type
        const grouped = {};
        members.forEach(m => {
            const type = m.object.object_type;
            if (!grouped[type]) grouped[type] = [];
            grouped[type].push(m);
        });

        for (const [type, items] of Object.entries(grouped)) {
            const typeLabel = typeLabels[type] || type;
            content += `<div class="ref-type-group"><div class="ref-type-header">${typeLabel} (${items.length})</div>`;
            content += '<div class="ref-type-list">';
            items.forEach(m => {
                const displayName = getStagedDisplayName(m.object);
                content += `
                    <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${m.object.global_index})">
                        <span class="ref-type-badge type-${m.object.object_type}">${m.object.object_type}</span>
                        <span class="ref-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
                    </div>
                `;
            });
            content += '</div></div>';
        }
    }

    return `
        <div class="impact-subsection">
            <div class="impact-subsection-header">
                <div class="impact-subsection-title">
                    <i class="fa-solid fa-users"></i>
                    <span>Group Membership</span>
                    <span class="impact-subsection-count">${totalCount}</span>
                </div>
                <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
            </div>
            <div class="impact-subsection-content">${content}</div>
        </div>
    `;
}

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
    if (!section) return;

    const body = document.getElementById(sectionName + 'SectionBody');
    const toggle = section.querySelector('.section-toggle');

    section.classList.toggle('collapsed');
    if (body) body.classList.toggle('collapsed');

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
        if (!saved) return;
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

    // Badge/issue functions
    Explorer.addCleanupIssuesToBadges = addCleanupIssuesToBadges;
    Explorer.computeStagedIssues = computeStagedIssues;
    Explorer.updateStagedIssuesUI = updateStagedIssuesUI;
    // Expose stagedIssues as a getter so it always returns the current value
    Object.defineProperty(Explorer, 'stagedIssues', {
        get: function() { return stagedIssues; },
        enumerable: true
    });

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
    Explorer.invalidateOrphanCache = invalidateOrphanCache;
    Explorer.buildOrphanCache = buildOrphanCache;
    Explorer.isObjectOrphan = isObjectOrphan;
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

    // Center pane reference/inheritance functions
    Explorer.buildLocalInheritanceChain = buildLocalInheritanceChain;
    Explorer.loadCenterInheritance = loadCenterInheritance;
    Explorer.renderCenterInheritance = renderCenterInheritance;
    Explorer.loadCenterReferences = loadCenterReferences;
    Explorer.renderCenterReferences = renderCenterReferences;
    Explorer.loadCenterMembers = loadCenterMembers;
    Explorer.renderCenterMembers = renderCenterMembers;
    Explorer.loadImpactAndRelationships = loadImpactAndRelationships;

    // UI functions
    Explorer.closeObjectDetail = closeObjectDetail;
    Explorer.switchRightTab = switchRightTab;
    Explorer.toggleActionsMenu = toggleActionsMenu;
    Explorer.closeActionsMenu = closeActionsMenu;
    Explorer.toggleSuggestionSection = toggleSuggestionSection;
    Explorer.saveSuggestionSectionState = saveSuggestionSectionState;
    Explorer.restoreSuggestionSectionState = restoreSuggestionSectionState;

})(window.Explorer);
