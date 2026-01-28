// Bulk Attribute Editor page JavaScript
// Extracted from bulk_attributes.html

let allObjects = [];
let commonAttributes = new Set();

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('action').addEventListener('change', function() {
        const action = this.value;
        const newValueGroup = document.getElementById('newValueGroup');
        newValueGroup.style.display = action === 'remove' ? 'none' : 'block';
    });

    // Event delegation for data-action elements
    document.addEventListener('click', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;

        const action = actionEl.dataset.action;
        if (action === 'preview-changes') {
            previewChanges();
        } else if (action === 'apply-changes') {
            applyChanges();
        }
    });
});

// Track the current request to cancel on rapid changes
let currentLoadController = null;

async function loadAttributes() {
    const objectType = document.getElementById('objectType').value;
    if (!objectType) return;

    // Cancel any pending request
    if (currentLoadController) {
        currentLoadController.abort();
    }
    currentLoadController = new AbortController();

    try {
        const response = await fetch(`/api/objects?type=${objectType}`, {
            signal: currentLoadController.signal
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        allObjects = await response.json();

        // Collect all unique attributes
        commonAttributes = new Set();
        allObjects.forEach(obj => {
            Object.keys(obj.attributes).forEach(attr => commonAttributes.add(attr));
        });

        // Populate dropdowns
        const sortedAttrs = Array.from(commonAttributes).sort();

        const filterField = document.getElementById('filterField');
        filterField.innerHTML = '<option value="">No filter</option>';
        sortedAttrs.forEach(attr => {
            filterField.innerHTML += `<option value="${attr}">${attr}</option>`;
        });

        const targetField = document.getElementById('targetField');
        targetField.innerHTML = '<option value="">Select attribute...</option>';
        sortedAttrs.forEach(attr => {
            targetField.innerHTML += `<option value="${attr}">${attr}</option>`;
        });

    } catch (error) {
        // Ignore abort errors (expected when user changes selection rapidly)
        if (error.name !== 'AbortError') {
            console.error('Error loading attributes:', error);
        }
    }
}

function getTargetField() {
    const selected = document.getElementById('targetField').value;
    const custom = document.getElementById('customField').value.trim();
    return custom || selected;
}

async function previewChanges() {
    const objectType = document.getElementById('objectType').value;
    const targetField = getTargetField();

    if (!objectType) {
        showToast('Please select an object type', 'warning');
        return;
    }
    if (!targetField) {
        showToast('Please select or enter a target attribute', 'warning');
        return;
    }

    const data = {
        type: objectType,
        filter_field: document.getElementById('filterField').value,
        filter_value: document.getElementById('filterValue').value,
        target_field: targetField,
        new_value: document.getElementById('newValue').value,
        action: document.getElementById('action').value
    };

    document.getElementById('previewStatus').textContent = 'Loading...';

    try {
        const response = await fetch('/api/bulk-attributes/preview', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.error) {
            showToast('Error: ' + result.error, 'error');
            return;
        }

        displayPreview(result.matches);
        document.getElementById('applyBtn').disabled = result.matches.length === 0;

    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    } finally {
        document.getElementById('previewStatus').textContent = '';
    }
}

function displayPreview(matches) {
    document.getElementById('matchCount').textContent = matches.length;

    if (matches.length === 0) {
        document.getElementById('previewEmpty').style.display = 'block';
        document.getElementById('previewEmpty').textContent = 'No objects match the current criteria.';
        document.getElementById('previewResults').style.display = 'none';
        return;
    }

    document.getElementById('previewEmpty').style.display = 'none';
    document.getElementById('previewResults').style.display = 'block';

    const html = matches.map(match => `
        <div class="change-item">
            <div class="d-flex justify-content-between align-items-start">
                <div>
                    <span class="badge bg-info">${escapeHtml(match.object.object_type)}</span>
                    <strong>${escapeHtml(match.object.display_name)}</strong>
                </div>
                <small class="text-muted">${escapeHtml(match.object.source_file)}</small>
            </div>
            <div class="mt-2">
                <code>${escapeHtml(match.field)}</code>:
                ${match.old_value ? `<span class="change-old">${escapeHtml(match.old_value)}</span>` : '<em class="text-muted">(not set)</em>'}
                <span class="change-arrow">&rarr;</span>
                ${match.new_value ? `<span class="change-new">${escapeHtml(match.new_value)}</span>` : '<em class="text-muted">(removed)</em>'}
            </div>
        </div>
    `).join('');

    document.getElementById('previewResults').innerHTML = html;
}

async function applyChanges() {
    const objectType = document.getElementById('objectType').value;
    const targetField = getTargetField();
    const matchCount = document.getElementById('matchCount').textContent;

    const confirmed = await showConfirmDialog({
        title: 'Apply Changes',
        message: `Apply changes to ${matchCount} objects? A backup will be created first.`,
        confirmText: 'Apply',
        type: 'warning'
    });
    if (!confirmed) return;

    const data = {
        type: objectType,
        filter_field: document.getElementById('filterField').value,
        filter_value: document.getElementById('filterValue').value,
        target_field: targetField,
        new_value: document.getElementById('newValue').value,
        action: document.getElementById('action').value
    };

    try {
        const response = await fetch('/api/bulk-attributes/apply', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.error) {
            showToast('Error: ' + result.error, 'error');
            return;
        }

        showToast(`Updated ${result.updated} objects. Backup: ${result.backup}`, 'success');

        // Reset preview
        document.getElementById('previewEmpty').style.display = 'block';
        document.getElementById('previewEmpty').textContent = 'Changes applied. Configure new options to make more changes.';
        document.getElementById('previewResults').style.display = 'none';
        document.getElementById('matchCount').textContent = '0';
        document.getElementById('applyBtn').disabled = true;

        // Reload objects to get fresh data
        loadAttributes();

    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}
