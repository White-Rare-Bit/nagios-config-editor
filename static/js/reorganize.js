// Reorganize page JavaScript
// Extracted from reorganize.html

(function() {
    'use strict';

    let allObjects = [];

    /**
     * Common bulk operation handler - validates selection, confirms, calls API, handles result
     * @param {Object} options
     * @param {string} options.operationName - Name for messages (e.g., 'move', 'clone', 'delete')
     * @param {string} options.endpoint - API endpoint to call
     * @param {Function} options.getPayload - Function(indices) returning request payload
     * @param {Function} options.getSuccessMessage - Function(result.data) returning success message
     * @param {Object} options.confirm - Confirmation dialog options {title, message, type}
     * @param {Function} [options.preValidate] - Optional additional validation, returns false to abort
     */
    async function performBulkOperation(options) {
        const indices = getSelectedIndices();
        if (indices.length === 0) {
            showToast(`Please select at least one object to ${options.operationName}`, 'warning');
            return;
        }

        // Optional pre-validation (e.g., checking for prefix/suffix in clone)
        if (options.preValidate && !(await options.preValidate(indices))) {
            return;
        }

        const confirmed = await showConfirmDialog({
            title: options.confirm.title,
            message: options.confirm.message.replace('{count}', indices.length),
            confirmText: options.confirm.confirmText || options.operationName.charAt(0).toUpperCase() + options.operationName.slice(1),
            type: options.confirm.type || 'warning'
        });
        if (!confirmed) return;

        const result = await ApiClient.post(options.endpoint, options.getPayload(indices));

        if (!result.success) {
            showToast(result.error || `${options.operationName.charAt(0).toUpperCase() + options.operationName.slice(1)} failed`, 'error');
            return;
        }

        showToast(options.getSuccessMessage(result.data), 'success');
        location.reload();
    }

document.addEventListener('DOMContentLoaded', () => {
    loadObjects();
});

async function loadObjects() {
    const type = document.getElementById('filterType').value;
    const params = new URLSearchParams();
    if (type) params.set('type', type);

    const result = await ApiClient.get('/api/objects?' + params.toString());
    if (result.success) {
        allObjects = result.data;
        displayObjects(allObjects);
    } else {
        document.getElementById('objectsList').innerHTML =
            `<div class="text-danger p-3">Error loading objects: ${result.error}</div>`;
    }
}

function displayObjects(objects) {
    const fileFilter = document.getElementById('filterFile').value;
    const searchFilter = document.getElementById('filterSearch').value.toLowerCase();

    const filtered = objects.filter(obj => {
        if (fileFilter && obj.source_file !== fileFilter) return false;
        if (searchFilter && !obj.display_name.toLowerCase().includes(searchFilter)) return false;
        return true;
    });

    document.getElementById('objectCount').textContent = filtered.length;

    if (filtered.length === 0) {
        document.getElementById('objectsList').innerHTML =
            '<div class="text-muted p-3">No objects match the current filters.</div>';
        return;
    }

    const html = filtered.map((obj) => {
        const globalIdx = obj.global_index;
        return `
            <div class="object-item border-bottom p-2" data-index="${globalIdx}">
                <div class="form-check">
                    <input type="checkbox" class="form-check-input object-checkbox"
                           value="${globalIdx}" id="obj${globalIdx}">
                    <label class="form-check-label w-100" for="obj${globalIdx}">
                        <span class="badge bg-info me-2">${escapeHtml(obj.object_type)}</span>
                        <strong>${escapeHtml(obj.display_name)}</strong>
                        <br><small class="text-muted">${escapeHtml(obj.source_file)}</small>
                    </label>
                </div>
            </div>
        `;
    }).join('');

    document.getElementById('objectsList').innerHTML = html;
}

function filterDisplayedObjects() {
    displayObjects(allObjects);
}

function selectAll() {
    document.querySelectorAll('.object-checkbox').forEach(cb => cb.checked = true);
}

function selectNone() {
    document.querySelectorAll('.object-checkbox').forEach(cb => cb.checked = false);
}

function getSelectedIndices() {
    return Array.from(document.querySelectorAll('.object-checkbox:checked'))
        .map(cb => parseInt(cb.value));
}

async function moveSelected() {
    let targetFile = document.getElementById('targetFile').value;
    const newFile = document.getElementById('newFile').value.trim();
    if (newFile) targetFile = newFile;

    if (!targetFile) {
        showToast('Please select a target file or enter a new filename', 'warning');
        return;
    }

    await performBulkOperation({
        operationName: 'move',
        endpoint: '/api/move-objects',
        getPayload: (indices) => ({ objects: indices, target_file: targetFile }),
        getSuccessMessage: (data) => `Moved ${data.moved} objects. Backup: ${data.backup}`,
        confirm: {
            title: 'Move Objects',
            message: `Move {count} objects to ${targetFile}? A backup will be created first.`,
            confirmText: 'Move',
            type: 'warning'
        }
    });
}

async function cloneSelected() {
    const prefix = document.getElementById('clonePrefix').value;
    const suffix = document.getElementById('cloneSuffix').value;

    await performBulkOperation({
        operationName: 'clone',
        endpoint: '/api/clone-objects',
        getPayload: (indices) => ({ objects: indices, prefix, suffix }),
        getSuccessMessage: (data) => `Cloned ${data.cloned} objects. Backup: ${data.backup}`,
        preValidate: async () => {
            if (!prefix && !suffix) {
                return await showConfirmDialog({
                    title: 'No Prefix/Suffix',
                    message: 'No prefix or suffix specified. Objects will be cloned with "_copy" suffix. Continue?',
                    confirmText: 'Continue',
                    type: 'info'
                });
            }
            return true;
        },
        confirm: {
            title: 'Clone Objects',
            message: 'Clone {count} objects? A backup will be created first.',
            confirmText: 'Clone',
            type: 'warning'
        }
    });
}

async function deleteSelected() {
    const cleanRefs = document.getElementById('cleanReferences').checked;

    await performBulkOperation({
        operationName: 'delete',
        endpoint: '/api/delete-objects',
        getPayload: (indices) => ({ objects: indices, update_references: cleanRefs }),
        getSuccessMessage: (data) => `Deleted ${data.deleted} objects. References cleaned: ${data.references_cleaned}`,
        confirm: {
            title: 'Delete Objects',
            message: 'DELETE {count} objects? This cannot be easily undone! A backup will be created first.',
            confirmText: 'Delete',
            type: 'danger'
        }
    });
}

// Event delegation for data-action attributes
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    switch (action) {
        case 'selectAll':
            selectAll();
            break;
        case 'selectNone':
            selectNone();
            break;
        case 'moveSelected':
            moveSelected();
            break;
        case 'cloneSelected':
            cloneSelected();
            break;
        case 'deleteSelected':
            deleteSelected();
            break;
    }
});

document.addEventListener('change', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'loadObjects') {
        loadObjects();
    }
});

// Debounced filter for input events
const debouncedFilter = debounce(filterDisplayedObjects, 150);

document.addEventListener('input', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'filterDisplayedObjects') {
        debouncedFilter();
    }
});

})();
