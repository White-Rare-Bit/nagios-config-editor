// Bulk Rename page JavaScript
// Extracted from bulk_rename.html

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

// Store preview data for apply confirmation
let lastPreviewResult = null;

async function previewRename() {
    const data = {
        type: document.getElementById('objectType').value,
        find: document.getElementById('findPattern').value,
        replace: document.getElementById('replaceWith').value,
        regex: document.getElementById('useRegex').checked,
        prefix: document.getElementById('addPrefix').value,
        suffix: document.getElementById('addSuffix').value
    };

    if (!data.type) {
        showToast('Please select an object type', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/preview-rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await response.json();

        if (result.error) {
            showToast(result.error, 'error');
            return;
        }

        // Store for apply confirmation
        lastPreviewResult = result;

        // Calculate total references
        const totalRefs = result.changes.reduce((sum, c) => sum + c.references, 0);

        document.getElementById('previewCount').textContent = result.total;
        document.getElementById('applyBtn').disabled = result.total === 0;
        document.getElementById('diffBtn').disabled = result.total === 0;

        if (result.total === 0) {
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
                        ${result.total} object(s) will be renamed, affecting ${totalRefs} reference(s) across other objects.
                    </div>
                `;
            }

            const tbody = document.getElementById('previewBody');
            tbody.innerHTML = result.changes.map(change => {
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
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function applyRename() {
    const updateRefs = document.getElementById('updateReferences').checked;

    // Build detailed confirmation message with impact
    const totalObjects = lastPreviewResult ? lastPreviewResult.total : 0;
    const totalRefs = lastPreviewResult
        ? lastPreviewResult.changes.reduce((sum, c) => sum + c.references, 0)
        : 0;

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

    const data = {
        type: document.getElementById('objectType').value,
        find: document.getElementById('findPattern').value,
        replace: document.getElementById('replaceWith').value,
        regex: document.getElementById('useRegex').checked,
        prefix: document.getElementById('addPrefix').value,
        suffix: document.getElementById('addSuffix').value,
        updateReferences: updateRefs
    };

    try {
        const response = await fetch('/api/apply-rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await response.json();

        if (result.error) {
            showToast('Error: ' + result.error, 'error');
            return;
        }

        showToast(`Renamed ${result.renamed} objects, updated ${result.references_updated} references`, 'success');
        location.reload();
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function showDiff() {
    const data = {
        type: document.getElementById('objectType').value,
        find: document.getElementById('findPattern').value,
        replace: document.getElementById('replaceWith').value,
        regex: document.getElementById('useRegex').checked,
        prefix: document.getElementById('addPrefix').value,
        suffix: document.getElementById('addSuffix').value
    };

    try {
        const response = await fetch('/api/diff/rename', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await response.json();

        if (result.error) {
            showToast(result.error, 'error');
            return;
        }

        const diffContent = document.getElementById('diffContent');
        if (result.diffs.length === 0) {
            diffContent.innerHTML = '<p class="text-muted">No file changes to display.</p>';
        } else {
            diffContent.innerHTML = result.diffs.map(d => `
                <div class="diff-file">
                    <div class="diff-header">${escapeHtml(d.file)}</div>
                    <div class="diff-content">${formatDiff(d.diff)}</div>
                </div>
            `).join('');
        }

        new bootstrap.Modal(document.getElementById('diffModal')).show();
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
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
