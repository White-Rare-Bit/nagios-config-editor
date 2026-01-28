// Reorganize page JavaScript
// Extracted from reorganize.html

let allObjects = [];

document.addEventListener('DOMContentLoaded', () => {
    loadObjects();
});

async function loadObjects() {
    const type = document.getElementById('filterType').value;
    const params = new URLSearchParams();
    if (type) params.set('type', type);

    try {
        const response = await fetch('/api/objects?' + params.toString());
        allObjects = await response.json();
        displayObjects(allObjects);
    } catch (error) {
        document.getElementById('objectsList').innerHTML =
            `<div class="text-danger p-3">Error loading objects: ${error.message}</div>`;
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
    const indices = getSelectedIndices();
    if (indices.length === 0) {
        showToast('Please select at least one object to move', 'warning');
        return;
    }

    let targetFile = document.getElementById('targetFile').value;
    const newFile = document.getElementById('newFile').value.trim();

    if (newFile) {
        targetFile = newFile;
    }

    if (!targetFile) {
        showToast('Please select a target file or enter a new filename', 'warning');
        return;
    }

    const confirmed = await showConfirmDialog({
        title: 'Move Objects',
        message: `Move ${indices.length} objects to ${targetFile}? A backup will be created first.`,
        confirmText: 'Move',
        type: 'warning'
    });
    if (!confirmed) return;

    try {
        const response = await fetch('/api/move-objects', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                objects: indices,
                target_file: targetFile
            })
        });
        const result = await response.json();

        if (result.error) {
            showToast('Error: ' + result.error, 'error');
            return;
        }

        showToast(`Moved ${result.moved} objects. Backup: ${result.backup}`, 'success');
        location.reload();
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function cloneSelected() {
    const indices = getSelectedIndices();
    if (indices.length === 0) {
        showToast('Please select at least one object to clone', 'warning');
        return;
    }

    const prefix = document.getElementById('clonePrefix').value;
    const suffix = document.getElementById('cloneSuffix').value;

    if (!prefix && !suffix) {
        const useCopy = await showConfirmDialog({
            title: 'No Prefix/Suffix',
            message: 'No prefix or suffix specified. Objects will be cloned with "_copy" suffix. Continue?',
            confirmText: 'Continue',
            type: 'info'
        });
        if (!useCopy) return;
    }

    const confirmed = await showConfirmDialog({
        title: 'Clone Objects',
        message: `Clone ${indices.length} objects? A backup will be created first.`,
        confirmText: 'Clone',
        type: 'warning'
    });
    if (!confirmed) return;

    try {
        const response = await fetch('/api/clone-objects', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                objects: indices,
                prefix: prefix,
                suffix: suffix
            })
        });
        const result = await response.json();

        if (result.error) {
            showToast('Error: ' + result.error, 'error');
            return;
        }

        showToast(`Cloned ${result.cloned} objects. Backup: ${result.backup}`, 'success');
        location.reload();
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function deleteSelected() {
    const indices = getSelectedIndices();
    if (indices.length === 0) {
        showToast('Please select at least one object to delete', 'warning');
        return;
    }

    const cleanRefs = document.getElementById('cleanReferences').checked;

    const confirmed = await showConfirmDialog({
        title: 'Delete Objects',
        message: `DELETE ${indices.length} objects? This cannot be easily undone! A backup will be created first.`,
        confirmText: 'Delete',
        type: 'danger'
    });
    if (!confirmed) return;

    try {
        const response = await fetch('/api/delete-objects', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                objects: indices,
                update_references: cleanRefs
            })
        });
        const result = await response.json();

        if (result.error) {
            showToast('Error: ' + result.error, 'error');
            return;
        }

        showToast(`Deleted ${result.deleted} objects. References cleaned: ${result.references_cleaned}`, 'success');
        location.reload();
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
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

document.addEventListener('input', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'filterDisplayedObjects') {
        filterDisplayedObjects();
    }
});
