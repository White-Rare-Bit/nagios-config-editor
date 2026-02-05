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

    const result = await ApiClient.post('/api/move-objects', {
        objects: indices,
        target_file: targetFile
    });

    if (!result.success) {
        showToast(result.error || 'Move failed', 'error');
        return;
    }

    showToast(`Moved ${result.data.moved} objects. Backup: ${result.data.backup}`, 'success');
    location.reload();
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

    const result = await ApiClient.post('/api/clone-objects', {
        objects: indices,
        prefix: prefix,
        suffix: suffix
    });

    if (!result.success) {
        showToast(result.error || 'Clone failed', 'error');
        return;
    }

    showToast(`Cloned ${result.data.cloned} objects. Backup: ${result.data.backup}`, 'success');
    location.reload();
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

    const result = await ApiClient.post('/api/delete-objects', {
        objects: indices,
        update_references: cleanRefs
    });

    if (!result.success) {
        showToast(result.error || 'Delete failed', 'error');
        return;
    }

    showToast(`Deleted ${result.data.deleted} objects. References cleaned: ${result.data.references_cleaned}`, 'success');
    location.reload();
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
