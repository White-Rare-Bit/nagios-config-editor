/** Explorer Dialogs Module - New object creation, deletion, bulk rename, edit attributes, validation */

import { state } from './state.js';
import { constants, isRenameable } from './constants.js';
import { getObjectKey, findObjectByKey } from './main.js';
import { clearSelection } from './state-management.js';
import { selectObjectByIndex, updateSelection, closeActionsMenu, switchRightTab, getNameFieldForObject } from './app.js'; // circular — safe (function-level)
import { showDialog, closeDialog, hideContextMenu } from './context-menu.js'; // circular — safe (function-level)
import { showCenterPaneObject } from './object-editor.js'; // circular — safe (function-level)
import { loadImpactAndRelationships } from './impact-section.js'; // circular — safe (function-level)
import { afterFrontendMutation } from './data-loading.js'; // circular — safe (function-level)
import { applyKeyChanges, closeTab } from './tab-manager.js';
import { navigateToObjectByIndex } from './file-operations.js'; // circular — safe (function-level)
import { StableKey } from '../stable-key.js';
import { ApiClient } from '../api-client.js';
import { showToast, showConfirmDialog } from '../ui-notifications.js';
import { escapeHtml } from '../app.js';

// ============================================================================
// HTML Template Helpers
// ============================================================================

/**
 * Build HTML for an alert box with severity styling
 * @param {string} severity - 'info', 'warning', or 'danger'
 * @param {string} html - Alert content (can include HTML)
 * @returns {string} HTML string
 */
export function dialogAlert(severity, html) {
    return `<div class="dialog-alert dialog-alert--${severity}">${html}</div>`;
}

/**
 * Build HTML for a key-value list (attribute display, diff rows)
 * @param {Array<{key: string, value: string}>} pairs - Key-value pairs
 * @returns {string} HTML string
 */
export function dialogKvList(pairs) {
    const rows = pairs.map(({key, value}) =>
        `<div class="dialog-kv-row">
            <span class="dialog-kv-key">${escapeHtml(key)}</span>
            <span class="dialog-kv-val">${value !== undefined ? escapeHtml(String(value)) : '<em>not set</em>'}</span>
        </div>`
    ).join('');
    return `<div class="dialog-kv-list">${rows}</div>`;
}

/**
 * Build HTML for a file select dropdown
 * @param {string} id - Element id for the select
 * @param {string} label - Label text
 * @param {string} [defaultFile=''] - File path to pre-select
 * @returns {string} HTML string
 */
export function dialogFileSelect(id, label, defaultFile = '') {
    const configFiles = [...new Set(state.allObjects.map(o => o.source_file))].sort();
    // A default that is not an existing file is offered as a new file; the server creates it.
    if (defaultFile && !configFiles.includes(defaultFile)) {
        configFiles.push(defaultFile);
        configFiles.sort();
    }
    const options = configFiles.map(f => {
        const fileName = f.split('/').pop();
        const selected = f === defaultFile ? 'selected' : '';
        return `<option value="${escapeHtml(f)}" ${selected}>${escapeHtml(fileName)}</option>`;
    }).join('');
    return `<div class="u-mb-md">
        <label class="form-label">${escapeHtml(label)}</label>
        <select class="form-select" id="${id}">
            ${options}
        </select>
    </div>`;
}

/**
 * Build HTML for a muted info paragraph
 * @param {string} text - Info text (plain text, will be escaped)
 * @returns {string} HTML string
 */
export function dialogInfoText(text) {
    return `<p class="dialog-info-text">${escapeHtml(text)}</p>`;
}

/**
 * Build HTML for a list of clickable entry items
 * @param {Array<{html: string, onclick: string}>} entries - Entry items
 * @returns {string} HTML string
 */
export function dialogEntryList(entries) {
    const items = entries.map(e =>
        `<div class="dialog-entry-item"${e.onclick ? ` onclick="${e.onclick}"` : ''}>${e.html}</div>`
    ).join('');
    return `<div class="dialog-entry-list">${items}</div>`;
}

// ============================================================================
// New Object Creation
// ============================================================================

export function createNewObject(targetFile) {
    const defaultType = getDominantTypeForFile(targetFile);
    const singularize = (s) => {
        if (s.endsWith('ies')) {return s.slice(0, -3) + 'y';}
        return s.endsWith('s') ? s.slice(0, -1) : s;
    };
    const typeOptions = Object.entries(constants.typeLabels)
        .map(([type, label]) => `<option value="${type}"${type === defaultType ? ' selected' : ''}>${escapeHtml(singularize(label))}</option>`)
        .join('');

    showDialog('Create New Object', `
        <div class="dialog-field">
            <label for="newObjectTypeSelect">Object Type</label>
            <select id="newObjectTypeSelect" class="dialog-select">${typeOptions}</select>
        </div>
    `, async () => {
        const objectType = document.getElementById('newObjectTypeSelect').value;
        closeDialog();
        await createObjectOnServer(targetFile, objectType);
    });
}

async function createObjectOnServer(targetFile, objectType) {
    const attributes = getDefaultAttributes(objectType);

    // Ensure a unique placeholder name so the object has a valid stable key
    const nameField = constants.nameFields[objectType] || 'name';
    if (!attributes[nameField]) {
        const existingNames = new Set(
            state.allObjects
                .filter(o => o.object_type === objectType)
                .map(o => o.display_name)
        );
        let placeholderName = `new-${objectType}`;
        let n = 2;
        while (existingNames.has(placeholderName)) {
            placeholderName = `new-${objectType}-${n++}`;
        }
        attributes[nameField] = placeholderName;
    }

    // Create immediately on the server (shadow copy) — enables undo, diff, tree visibility
    const result = await ApiClient.post('/api/objects/create', {
        target_file: targetFile,
        object_type: objectType,
        attributes
    }, { silent: true });

    if (!result.success) {
        showToast(result.data?.error || 'Failed to create object', 'error');
        return;
    }

    // Reload objects so the new one appears in the tree
    await afterFrontendMutation();

    // Find the newly created object and navigate to it (opens tab, expands tree, scrolls).
    // Match by type + name only — source_file changes when shadow copy is first created.
    const displayName = attributes[nameField];
    const targetFileName = targetFile.split('/').pop();
    const newObj = state.allObjects.find(o =>
        o.object_type === objectType &&
        o.source_file.endsWith('/' + targetFileName) &&
        (o.display_name === displayName || o.name === displayName)
    );
    if (newObj) {
        // Track as a creation so tree renders green staged-creation style
        state.createdObjectKeys.add(StableKey.build(newObj));
        navigateToObjectByIndex(newObj.global_index);
    }
}

export function getNewObjectNameField(objectType) {
    // D-01: Delegate to centralized nameFields constant (sync with nagios_model.py:NAME_FIELDS)
    return constants.nameFields[objectType] || 'name';
}

export function getDefaultAttributes(objectType) {
    return {...(constants.defaultAttributes[objectType] || {})};
}

function getDominantTypeForFile(filePath) {
    // Count object types in the target file
    const typeCounts = {};
    for (const obj of state.allObjects) {
        if (obj.source_file === filePath) {
            typeCounts[obj.object_type] = (typeCounts[obj.object_type] || 0) + 1;
        }
    }
    // Return the most common type, or 'host' as fallback for empty/new files
    let dominant = 'host';
    let maxCount = 0;
    for (const [type, count] of Object.entries(typeCounts)) {
        if (count > maxCount) {
            maxCount = count;
            dominant = type;
        }
    }
    return dominant;
}

// ============================================================================
// Object Deletion
// ============================================================================

/**
 * Objects that refer to the given object, from GET /api/objects/referenced-by.
 * The server matches references by type (a service's description is not a
 * reference to another service), and lists objects that `use` it as a template.
 * @returns {Promise<{success: boolean, references: Array<{stable_key: string,
 *   object_type: string, display_name: string, fields: string[]}>, error?: string}>}
 */
async function fetchReferencedBy(stableKey) {
    const result = await ApiClient.get(
        `/api/objects/referenced-by?key=${encodeURIComponent(stableKey)}`,
        { silent: true }
    );
    if (!result.success) {
        return { success: false, references: [], error: result.error };
    }
    return { success: true, references: result.payload?.references || [] };
}

export async function checkDependenciesAndDelete() {
    // Collect all objects being deleted and the objects that refer to them
    const objectsToDelete = [];
    const allDependencies = [];

    const selected = Array.from(state.selectedKeys)
        .map(key => findObjectByKey(key))
        .filter(obj => obj);
    const lookups = await Promise.all(selected.map(obj => fetchReferencedBy(getObjectKey(obj))));

    const failed = lookups.find(l => !l.success);
    if (failed) {
        showToast(`Could not check references: ${failed.error}`, 'error');
    }

    selected.forEach((obj, i) => {
        // Objects also being deleted don't count (the server already leaves
        // out the object itself)
        const externalDeps = lookups[i].references
            .filter(ref => !state.selectedKeys.has(ref.stable_key));
        if (externalDeps.length > 0) {
            objectsToDelete.push({ obj, deps: externalDeps });
            allDependencies.push(...externalDeps);
        }
    });

    if (allDependencies.length > 0) {
        // Show warning dialog (already has confirmation built in)
        showDeleteDependencyWarning(objectsToDelete, () => {
            executeObjectDeletions();
        });
    } else {
        // G-02: Confirmation dialog before deleting objects with no dependencies
        const selectedCount = state.selectedKeys.size;
        let message;
        if (selectedCount === 1) {
            const key = Array.from(state.selectedKeys)[0];
            const obj = findObjectByKey(key);
            const name = obj ? (obj.display_name || obj.name || 'unnamed') : 'this object';
            message = `Are you sure you want to delete "${name}"?`;
        } else {
            message = `Are you sure you want to delete ${selectedCount} objects?`;
        }

        const confirmed = await showConfirmDialog({
            title: selectedCount === 1 ? 'Delete Object?' : `Delete ${selectedCount} Objects?`,
            message: message,
            confirmText: 'Delete',
            cancelText: 'Cancel',
            type: 'danger'
        });

        if (!confirmed) {
            return;
        }

        executeObjectDeletions();
    }
}

export function showDeleteDependencyWarning(objectsWithDeps, onConfirm) {
    const totalDeps = objectsWithDeps.reduce((sum, o) => sum + o.deps.length, 0);

    // Categorize dependencies by impact severity
    const orphanedServices = [];
    const brokenReferences = [];

    for (const { deps } of objectsWithDeps) {
        for (const dep of deps) {
            // Services that lose their host/hostgroup become orphaned
            if (dep.object_type === 'service' &&
                (dep.fields.includes('host_name') || dep.fields.includes('hostgroup_name'))) {
                orphanedServices.push(dep);
            } else {
                brokenReferences.push(dep);
            }
        }
    }

    let warningHtml = dialogAlert('warning',
        '<strong><i class="fa-solid fa-triangle-exclamation"></i> Warning: This deletion will affect other objects</strong>');

    // Show orphaned services warning prominently
    if (orphanedServices.length > 0) {
        let orphanList = '';
        for (const dep of orphanedServices.slice(0, 5)) {
            orphanList += `<li>${escapeHtml(dep.display_name)}</li>`;
        }
        if (orphanedServices.length > 5) {
            orphanList += `<li class="dialog-detail-more">... and ${orphanedServices.length - 5} more</li>`;
        }
        warningHtml += dialogAlert('danger',
            `<strong><i class="fa-solid fa-exclamation-circle"></i> ${orphanedServices.length} service(s) will become orphaned</strong>
            <p>These services will have no host/hostgroup and may fail to load:</p>
            <ul>${orphanList}</ul>`);
    }

    // Show other broken references (non-orphan dependencies)
    let nonOrphanHtml = '';
    for (const { obj, deps } of objectsWithDeps) {
        const nonOrphanDeps = deps.filter(d =>
            !(d.object_type === 'service' &&
              (d.fields.includes('host_name') || d.fields.includes('hostgroup_name')))
        );

        if (nonOrphanDeps.length === 0) {continue;}

        nonOrphanHtml += `
            <div class="dialog-detail-item">
                <strong>${escapeHtml(obj.object_type)}: ${escapeHtml(obj.display_name)}</strong>
                <ul>
        `;
        for (const dep of nonOrphanDeps.slice(0, 5)) {
            nonOrphanHtml += `<li>${escapeHtml(dep.object_type)} "${escapeHtml(dep.display_name)}" (${escapeHtml(dep.fields.join(', '))})</li>`;
        }
        if (nonOrphanDeps.length > 5) {
            nonOrphanHtml += `<li class="dialog-detail-more">... and ${nonOrphanDeps.length - 5} more</li>`;
        }
        nonOrphanHtml += '</ul></div>';
    }

    // Only add the scrollable list container if there's content
    if (nonOrphanHtml) {
        warningHtml += `<div class="dialog-scrollable-list">${nonOrphanHtml}</div>`;
    }

    warningHtml += `
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

export function stageObjectDeletions() {
    // Check for dependencies before deleting
    if (state.selectedKeys.size > 0) {
        checkDependenciesAndDelete();
    }
}

export async function executeObjectDeletions() {
    // Collect stable keys for deletion via API
    const stableKeys = [];
    for (const key of state.selectedKeys) {
        const obj = findObjectByKey(key);
        if (!obj) {continue;}
        stableKeys.push(getObjectKey(obj));
    }

    // Close tabs for deleted objects
    for (const key of state.selectedKeys) {
        closeTab(key);
    }

    // Clear selection
    clearSelection();

    if (stableKeys.length > 0) {
        const result = await ApiClient.post('/api/objects/delete-multiple', {
            stable_keys: stableKeys,
        }, { silent: true });

        if (!result.success) {
            showToast(result.data?.error || result.error || 'Failed to delete objects', 'error');
            afterFrontendMutation();
            return;
        }

        const deletedCount = result.data?.deleted || 0;
        afterFrontendMutation();

        if (deletedCount > 0) {
            showToast(`Deleted ${deletedCount} object(s)`, 'success');
        }
    }
}



// ============================================================================
// Bulk Operations Dialogs
// ============================================================================

async function executeBulkRename(find, replace, shouldUpdateRefs) {
    const renames = [];
    let skipped = 0;
    let centerPaneNeedsRefresh = false;

    for (const key of state.selectedKeys) {
        const obj = findObjectByKey(key);
        if (!obj) {continue;}
        // Escalations, dependencies etc. have no name of their own; the
        // server would refuse the whole request.
        if (!isRenameable(obj)) {
            skipped++;
            continue;
        }

        const objKey = getObjectKey(obj);
        const nameField = getNameFieldForObject(obj);
        const currentName = obj.attributes[nameField] || '';
        const newName = currentName.split(find).join(replace);

        if (newName !== currentName) {
            renames.push({ stable_key: objKey, new_name: newName });

            if (state.editedObject && getObjectKey(state.editedObject) === objKey) {
                centerPaneNeedsRefresh = true;
            }
        }
    }

    const skippedMsg = skipped > 0 ? ` (skipped ${skipped} that have no name of their own)` : '';
    if (renames.length === 0) {
        closeDialog();
        showToast(`No matches found${skippedMsg}`, 'warning');
        return;
    }

    // One request for all renames: the server finds the references of the
    // same type to every renamed object at once (renamed objects that refer
    // to each other are updated too) and makes it one undo step.
    const result = await ApiClient.post('/api/objects/rename', {
        renames,
        update_references: shouldUpdateRefs
    }, { silent: true });

    closeDialog();

    if (!result.success) {
        showToast(`Failed to apply renames: ${result.error}`, 'error');
        afterFrontendMutation();
        return;
    }

    // Every written object whose key changed: the renamed objects and those
    // whose key names a renamed object (a service's hosts/hostgroups).
    applyKeyChanges(result.payload.key_changes);

    state.healthCheckData = null;
    await afterFrontendMutation();

    if (centerPaneNeedsRefresh && state.editedObject) {
        const editedKey = getObjectKey(state.editedObject);
        const obj = findObjectByKey(result.payload.key_changes[editedKey] || editedKey);
        if (obj) {showCenterPaneObject(obj);}
    } else if (state.editedObject) {
        loadImpactAndRelationships(state.editedObject);
    }

    const totalRefUpdates = result.payload.references_updated;
    const refMsg = totalRefUpdates > 0 ? ` Updated ${totalRefUpdates} reference${totalRefUpdates !== 1 ? 's' : ''}.` : '';
    showToast(`Renamed ${renames.length}${skippedMsg}.${refMsg}`, 'success');
}

export function showBulkRenameDialog() {
    hideContextMenu();
    closeActionsMenu();
    if (state.selectedKeys.size === 0) {
        showToast('Please select objects first', 'warning');
        return;
    }

    const count = state.selectedKeys.size;

    showDialog('Bulk Rename', `
        <p class="dialog-info-text" style="margin-top:0">${count} object${count !== 1 ? 's' : ''} selected</p>
        <label>Find</label>
        <input type="text" id="renameFind" placeholder="Text to find...">
        <label>Replace with</label>
        <input type="text" id="renameReplace" placeholder="Replacement text...">
        <div class="dialog-reference-option u-mt-sm">
            <label class="commit-reference-label">
                <input type="checkbox" id="bulkRenameUpdateRefs" checked>
                <span><strong>Update references</strong> in other objects</span>
            </label>
        </div>
    `, () => {
        const find = document.getElementById('renameFind').value;
        const replace = document.getElementById('renameReplace').value;
        const shouldUpdateRefs = document.getElementById('bulkRenameUpdateRefs').checked;

        if (!find) {
            showToast('Please enter text to find', 'warning');
            return;
        }

        executeBulkRename(find, replace, shouldUpdateRefs);
    });
}

function validateBulkActionInputs(action, field, findText, sortedFields) {
    if (field && !sortedFields.includes(field)) {
        showToast(`Field "${field}" does not exist in selected objects`, 'warning');
        return false;
    }
    if (action === 'findreplace' && !findText) {
        showToast('Please enter text to find', 'warning');
        return false;
    }
    if ((action === 'set' || action === 'remove') && !field) {
        showToast(`Please select an attribute to ${action === 'set' ? 'set' : 'remove'}`, 'warning');
        return false;
    }
    return true;
}

function applyBulkAction(action, field, findText, valueText, editedAttrs) {
    let changed = false;
    if (action === 'findreplace') {
        const fieldsToCheck = field ? [field] : Object.keys(editedAttrs);
        for (const f of fieldsToCheck) {
            if (!(f in editedAttrs)) {continue;}
            const currentValue = editedAttrs[f] || '';
            const newValue = currentValue.split(findText).join(valueText);
            if (newValue !== currentValue) {
                editedAttrs[f] = newValue;
                changed = true;
            }
        }
    } else if (action === 'set') {
        if (editedAttrs[field] !== valueText) {
            editedAttrs[field] = valueText;
            changed = true;
        }
    } else if (action === 'remove') {
        if (field in editedAttrs) {
            delete editedAttrs[field];
            changed = true;
        }
    }
    return changed;
}

// Bug 033: Filter scope to only object types that support the given attribute
function filterScopeByAttribute(scope, field, action) {
    if (!field || (action !== 'set' && action !== 'remove') || !constants.NAGIOS_ATTRIBUTES) {
        return { filteredScope: scope, skippedIncompatible: 0 };
    }
    const filteredScope = scope.filter(key => {
        const obj = findObjectByKey(key);
        if (!obj) {return false;}
        const validAttrs = constants.NAGIOS_ATTRIBUTES[obj.object_type];
        if (!validAttrs) {return true;} // No metadata for type — be permissive
        return validAttrs.includes(field);
    });
    return { filteredScope, skippedIncompatible: scope.length - filteredScope.length };
}

// Bug 032: Build detailed toast message for bulk edit results
function showBulkEditResultToast(action, updatedCount, unchangedCount, skippedIncompatible) {
    const ACTION_LABELS = { findreplace: 'Updated', set: 'Set attribute in', remove: 'Removed attribute from' };
    if (updatedCount > 0) {
        let msg = `${ACTION_LABELS[action] || action} ${updatedCount} object(s).`;
        if (unchangedCount > 0) {msg += ` ${unchangedCount} already had the requested value.`;}
        if (skippedIncompatible > 0) {msg += ` ${skippedIncompatible} skipped (incompatible type).`;}
        showToast(msg, 'success');
    } else {
        let msg = 'No changes made';
        if (skippedIncompatible > 0) {
            msg += ` (${skippedIncompatible} object(s) skipped — attribute not valid for their type)`;
        } else if (unchangedCount > 0) {
            msg += ` (${unchangedCount} already had the requested value)`;
        }
        showToast(msg, 'warning');
    }
}

async function executeBulkEditAction(scope, sortedFields) {
    const action = document.getElementById('editAttrAction').value;
    const field = document.getElementById('editAttrField').value.trim();
    const findText = document.getElementById('editAttrFind').value;
    const valueText = document.getElementById('editAttrValue').value;

    if (!validateBulkActionInputs(action, field, findText, sortedFields)) {return;}

    const { filteredScope, skippedIncompatible } = filterScopeByAttribute(scope, field, action);

    const operations = [];
    let unchangedCount = 0;
    for (const key of filteredScope) {
        const obj = findObjectByKey(key);
        if (!obj) {continue;}

        const objKey = getObjectKey(obj);
        const editedAttrs = {...obj.attributes};

        if (applyBulkAction(action, field, findText, valueText, editedAttrs)) {
            operations.push({
                action: 'update',
                stable_key: objKey,
                attributes: editedAttrs
            });
        } else {
            unchangedCount++;
        }
    }

    if (operations.length > 0) {
        const ACTION_DESCS = { findreplace: 'find/replace', set: 'set attribute', remove: 'remove attribute' };
        const result = await ApiClient.post('/api/batch-mutations', {
            description: `bulk ${ACTION_DESCS[action] || action} on ${operations.length} objects`,
            operations
        }, { silent: true });
        if (!result.success) {
            showToast(result.error || 'Failed to apply edits', 'error');
            closeDialog();
            afterFrontendMutation();
            return;
        }
        // Editing host_name/hostgroup_name changes a service's key.
        applyKeyChanges(result.payload.key_changes);
    }

    state.healthCheckData = null;
    afterFrontendMutation();
    closeDialog();

    if (state.editedObject) {
        const editedKey = getObjectKey(state.editedObject);
        if (scope.includes(editedKey)) {
            const obj = findObjectByKey(editedKey);
            if (obj) {showCenterPaneObject(obj);}
        }
    }

    showBulkEditResultToast(action, operations.length, unchangedCount, skippedIncompatible);
}

export function showEditAttributesDialog() {
    hideContextMenu();
    closeActionsMenu();

    // Editing nothing used to silently apply to every object; require a selection.
    if (state.selectedKeys.size === 0) {
        showToast('Select objects first', 'warning');
        return;
    }
    // Collect all unique attribute names from selected objects
    const scope = Array.from(state.selectedKeys);
    const availableFields = new Set();
    for (const key of scope) {
        const obj = findObjectByKey(key);
        if (!obj) {continue;}
        const attrs = obj.attributes;
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
        executeBulkEditAction(scope, sortedFields);
    });

    // Setup after dialog shown
    requestAnimationFrame(() => {
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
                    `<div class="suggestion-item" data-value="${escapeHtml(f)}">${escapeHtml(f)}</div>`
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
                    `<div class="suggestion-item" data-value="${escapeHtml(f)}">${escapeHtml(f)}</div>`
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

export function selectAllVisible() {
    closeActionsMenu();
    const items = document.querySelectorAll('.tree-item:not([style*="display: none"])');
    items.forEach(item => {
        const idx = parseInt(item.dataset.index, 10);
        if (!isNaN(idx)) {selectObjectByIndex(idx);}
    });
    updateSelection();
}

export function selectByType() {
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
        clearSelection();
        state.allObjects.filter(o => o.object_type === type).forEach(o => {
            state.selectedKeys.add(getObjectKey(o));
        });
        updateSelection();
        closeDialog();
    });

    // Select first item by default
    requestAnimationFrame(() => {
        const firstItem = document.querySelector('.dialog-type-item');
        if (firstItem) {firstItem.classList.add('selected');}
    });
}

export function selectDialogType(el) {
    document.querySelectorAll('.dialog-type-item').forEach(item => item.classList.remove('selected'));
    el.classList.add('selected');
    document.getElementById('selectType').value = el.dataset.type;
}

export function selectByPattern() {
    closeActionsMenu();

    showDialog('Select by Pattern', `
        <label>Name pattern (regex)</label>
        <input type="text" id="selectPattern" placeholder="e.g., ^web-.*">
    `, () => {
        const pattern = document.getElementById('selectPattern').value;
        if (!pattern) {return;}

        try {
            const regex = new RegExp(pattern, 'i');
            clearSelection();
            state.allObjects.filter(o => regex.test(o.display_name)).forEach(o => {
                state.selectedKeys.add(getObjectKey(o));
            });
            updateSelection();
            closeDialog();
        } catch (e) {
            showToast('Invalid regex pattern', 'error');
        }
    });
}

// ============================================================================
// Validation
// ============================================================================

export async function runValidation() {
    closeActionsMenu();
    switchRightTab('validation');
    runValidationFull();
}

export async function runValidationFull() {
    const container = document.getElementById('validationContent');
    const badge = document.getElementById('validationBadge');

    container.innerHTML = '<div class="tab-placeholder">Running validation...</div>';

    const response = await ApiClient.post('/api/validate', {}, { silent: true });

    if (!response.success) {
        container.innerHTML = `<div class="tab-placeholder">Error: ${escapeHtml(response.error || 'Validation request failed')}</div>`;
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
        output += 'ERRORS:\n' + result.errors.map(e => typeof e === 'object' ? e.message || JSON.stringify(e) : e).join('\n') + '\n\n';
    }
    if (result.warnings && result.warnings.length > 0) {
        output += 'WARNINGS:\n' + result.warnings.map(w => typeof w === 'object' ? w.message || JSON.stringify(w) : w).join('\n') + '\n\n';
    }
    if (result.raw_output) {
        output += result.raw_output;
    }

    html += `<pre class="validation-output">${escapeHtml(output || 'Validation completed successfully.')}</pre>`;

    container.innerHTML = html;

    if (result.success) {
        showToast('Configuration is valid!', 'success');
    } else {
        showToast(`Validation failed: ${result.errors?.length || 0} errors`, 'error');
    }
}

// onclick handlers in generated HTML — must be on window.Explorer
window.Explorer = window.Explorer || {};
window.Explorer.selectDialogType = selectDialogType;
