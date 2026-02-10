// Bulk Rename page JavaScript
// Extracted from bulk_rename.html

// Store preview data for apply confirmation
let lastPreviewResult = null;

/**
 * Collect form data from rename form fields
 * @param {boolean} includeUpdateReferences - Whether to include the updateReferences checkbox
 * @returns {Object} Form data object
 */
function getFormData(includeUpdateReferences = false) {
    const data = {
        type: document.getElementById('objectType').value,
        find: document.getElementById('findPattern').value,
        replace: document.getElementById('replaceWith').value,
        regex: document.getElementById('useRegex').checked,
        prefix: document.getElementById('addPrefix').value,
        suffix: document.getElementById('addSuffix').value
    };
    if (includeUpdateReferences) {
        data.updateReferences = document.getElementById('updateReferences').checked;
    }
    return data;
}

/**
 * Calculate total references from preview result
 * @param {Object} previewResult - Preview result with changes array
 * @returns {number} Total reference count
 */
function calculateTotalReferences(previewResult) {
    if (!previewResult || !previewResult.changes) return 0;
    return previewResult.changes.reduce((sum, c) => sum + c.references, 0);
}

// Event delegation for data-action buttons
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'preview-rename') {
        previewRename();
    } else if (action === 'show-diff') {
        showDiff();
    } else if (action === 'apply-rename') {
        applyRename();
    }
});

async function previewRename() {
    const data = getFormData();

    if (!data.type) {
        showToast('Please select an object type', 'warning');
        return;
    }

    const result = await ApiClient.post('/api/preview-rename', data, {
        errorPrefix: 'Preview failed'
    });

    if (!result.success) {
        return;
    }

    // Store for apply confirmation
    lastPreviewResult = result.data;

    // Calculate total references
    const totalRefs = calculateTotalReferences(result.data);

    document.getElementById('previewCount').textContent = result.data.total;
    document.getElementById('applyBtn').disabled = result.data.total === 0;
    document.getElementById('diffBtn').disabled = result.data.total === 0;

    if (result.data.total === 0) {
        document.getElementById('previewEmpty').style.display = 'block';
        document.getElementById('previewEmpty').textContent = 'No matching objects to rename.';
        document.getElementById('previewResults').style.display = 'none';
    } else {
        document.getElementById('previewEmpty').style.display = 'none';
        document.getElementById('previewResults').style.display = 'block';

        // Build summary with reference impact
        let summaryHtml = '';
        if (totalRefs > 0) {
            summaryHtml = `
                <div class="rename-impact-summary">
                    <strong><i class="fa-solid fa-info-circle"></i> Impact Summary:</strong>
                    ${result.data.total} object(s) will be renamed, affecting ${totalRefs} reference(s) across other objects.
                </div>
            `;
        }

        const tbody = document.getElementById('previewBody');
        tbody.innerHTML = result.data.changes.map(change => {
            const refClass = change.references > 0 ? 'has-refs' : 'no-refs';
            return `
                <tr class="${refClass}">
                    <td><span class="preview-old">${escapeHtml(change.old_name)}</span></td>
                    <td><span class="preview-new">${escapeHtml(change.new_name)}</span></td>
                    <td><span class="preview-refs ${change.references > 0 ? 'refs-warning' : ''}">${change.references}</span></td>
                </tr>
            `;
        }).join('');

        // Insert summary before the table if it exists
        const summaryEl = document.getElementById('renameSummary');
        if (summaryEl) {
            summaryEl.innerHTML = summaryHtml;
        }
    }
}

async function applyRename() {
    const updateRefs = document.getElementById('updateReferences').checked;

    // Build detailed confirmation message with impact
    const totalObjects = lastPreviewResult ? lastPreviewResult.total : 0;
    const totalRefs = calculateTotalReferences(lastPreviewResult);

    let confirmMsg = '';
    if (updateRefs) {
        confirmMsg = `<p><strong>${totalObjects} object(s)</strong> will be renamed.</p>`;
        if (totalRefs > 0) {
            confirmMsg += `<p><strong>${totalRefs} reference(s)</strong> in other objects will be updated to match.</p>`;
        }
        confirmMsg += '<p>A backup will be created first.</p>';
    } else {
        confirmMsg = `<p><strong>${totalObjects} object(s)</strong> will be renamed.</p>`;
        if (totalRefs > 0) {
            confirmMsg += `<p class="text-danger"><strong>Warning:</strong> ${totalRefs} reference(s) will NOT be updated and may become broken.</p>`;
        }
        confirmMsg += '<p>A backup will be created first.</p>';
    }

    const confirmed = await showConfirmDialog({
        title: 'Apply Rename',
        message: confirmMsg,
        confirmText: 'Apply Rename',
        type: totalRefs > 0 && !updateRefs ? 'danger' : 'warning'
    });
    if (!confirmed) return;

    const data = getFormData(true);

    const result = await ApiClient.post('/api/apply-rename', data, {
        errorPrefix: 'Rename failed'
    });

    if (!result.success) {
        return;
    }

    const staged = result.data.staged || 0;
    const refStaged = result.data.references_staged || 0;
    const msg = refStaged > 0
        ? `Staged ${staged} rename(s) and ${refStaged} reference update(s). Apply changes to write to disk.`
        : `Staged ${staged} rename(s). Apply changes to write to disk.`;
    showToast(msg, 'success');
    location.reload();
}

async function showDiff() {
    const data = getFormData();

    const result = await ApiClient.post('/api/diff/rename', data, {
        errorPrefix: 'Failed to generate diff'
    });

    if (!result.success) {
        return;
    }

    const diffContent = document.getElementById('diffContent');
    if (result.data.diffs.length === 0) {
        diffContent.innerHTML = '<p class="text-muted">No file changes to display.</p>';
    } else {
        diffContent.innerHTML = result.data.diffs.map(d => `
            <div class="diff-file">
                <div class="diff-header">${escapeHtml(d.file)}</div>
                <div class="diff-content">${formatDiff(d.diff)}</div>
            </div>
        `).join('');
    }

    new bootstrap.Modal(document.getElementById('diffModal')).show();
}

function formatDiff(diff) {
    return diff.split('\n').map(line => {
        const escaped = escapeHtml(line);
        if (line.startsWith('+') && !line.startsWith('+++')) {
            return `<span class="diff-add">${escaped}</span>`;
        } else if (line.startsWith('-') && !line.startsWith('---')) {
            return `<span class="diff-remove">${escaped}</span>`;
        } else if (line.startsWith('@@')) {
            return `<span class="diff-header-line">${escaped}</span>`;
        }
        return escaped;
    }).join('\n');
}
