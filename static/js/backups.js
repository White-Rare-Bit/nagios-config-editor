// Backups page JavaScript
// Converted to table layout with sortable columns

// Sort state
let currentSortColumn = 'date';
let currentSortDirection = 'desc';

async function createBackup() {
    const btn = document.getElementById('createBackupBtn');
    const description = document.getElementById('backupDescription').value.trim();

    // Show loading state
    btn.disabled = true;
    btn.textContent = 'Creating...';

    const identity = getUserIdentity();
    const result = await ApiClient.post('/api/backups', {
        description,
        userName: identity.userName,
        userEmail: identity.userEmail
    }, { timeout: 30000, silent: true });

    if (result.success) {
        btn.textContent = 'Created!';
        showToast('Backup created successfully', 'success');
        setTimeout(() => location.reload(), 800);
    } else {
        btn.disabled = false;
        btn.textContent = 'Create Backup';
        if (result.aborted) {
            showToast('Backup creation timed out. Please try again.', 'error');
        } else {
            showToast('Error creating backup: ' + result.error, 'error');
        }
    }
}

async function restoreBackup(name, btn = null) {
    const backupRow = btn ? btn.closest('.backup-row') : document.querySelector(`[data-action="restore-backup"][data-name="${name}"]`)?.closest('.backup-row');

    const confirmed = await showConfirmDialog({
        title: 'Restore Backup',
        message: `Restore from "${name}"? This will create a safety backup first, then replace all config files.`,
        confirmText: 'Restore',
        type: 'warning'
    });

    if (!confirmed) return;

    // Show restoring state
    if (backupRow) backupRow.classList.add('restoring');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Restoring...';
    }

    const identity = getUserIdentity();
    const result = await ApiClient.post(`/api/backups/${name}/restore`, {
        userName: identity.userName,
        userEmail: identity.userEmail
    }, { silent: true });

    if (result.success) {
        if (btn) btn.textContent = 'Restored!';
        showToast(`Restored ${result.data.files_restored} files. Safety backup created.`, 'success');
        setTimeout(() => location.reload(), 1000);
    } else if (result.data?.locked) {
        if (backupRow) backupRow.classList.remove('restoring');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Restore';
        }
        showToast('Another user has pending changes. Wait for them to commit or discard.', 'error');
    } else {
        if (backupRow) backupRow.classList.remove('restoring');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Restore';
        }
        showToast('Error: ' + (result.error || 'Unknown error'), 'error');
    }
}

async function deleteBackup(name, btn = null) {
    const backupRow = btn ? btn.closest('.backup-row') : document.querySelector(`[data-action="delete-backup"][data-name="${name}"]`)?.closest('.backup-row');

    const confirmed = await showConfirmDialog({
        title: 'Delete Backup',
        message: `Delete backup "${name}"? This cannot be undone.`,
        confirmText: 'Delete',
        type: 'danger'
    });

    if (!confirmed) return;

    // Immediately show deleting state
    if (backupRow) backupRow.classList.add('deleting');

    const result = await ApiClient.del(`/api/backups/${name}`, { silent: true });

    if (result.success) {
        // Animate out and remove
        if (backupRow) {
            backupRow.style.transition = 'all 0.3s ease';
            backupRow.style.opacity = '0';
            backupRow.style.transform = 'translateX(20px)';
            setTimeout(() => {
                backupRow.remove();
                updateBackupCount();
            }, 300);
        }
        showToast('Backup deleted', 'success');
    } else {
        if (backupRow) backupRow.classList.remove('deleting');
        showToast('Error: ' + (result.error || 'Unknown error'), 'error');
    }
}

async function deleteAllBackups() {
    const backupRows = document.querySelectorAll('.backup-row');
    const count = backupRows.length;

    if (count === 0) {
        showToast('No backups to delete', 'info');
        return;
    }

    const confirmed = await showConfirmDialog({
        title: 'Delete All Backups',
        message: `Delete all ${count} backup${count !== 1 ? 's' : ''}? This cannot be undone.`,
        confirmText: 'Delete All',
        type: 'danger'
    });

    if (!confirmed) return;

    const result = await ApiClient.del('/api/backups/all', { silent: true });

    if (result.success) {
        // Animate out all backup rows
        backupRows.forEach((row, index) => {
            setTimeout(() => {
                row.style.transition = 'all 0.3s ease';
                row.style.opacity = '0';
                row.style.transform = 'translateX(20px)';
                setTimeout(() => row.remove(), 300);
            }, index * 50);
        });

        setTimeout(() => {
            updateBackupCount();
            showEmptyState();
        }, count * 50 + 350);

        showToast(`Deleted ${result.data.deleted_count} backup${result.data.deleted_count !== 1 ? 's' : ''}`, 'success');
    } else {
        showToast('Error: ' + (result.error || 'Unknown error'), 'error');
    }
}

function sortBackups(column) {
    const tbody = document.getElementById('backupTableBody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('.backup-row'));
    if (rows.length === 0) return;

    // Toggle direction if same column, otherwise default to desc for date, asc for others
    if (column === currentSortColumn) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = column;
        currentSortDirection = column === 'date' ? 'desc' : 'asc';
    }

    // Sort rows
    rows.sort((a, b) => {
        let aVal, bVal;

        if (column === 'date') {
            aVal = a.dataset.date || '';
            bVal = b.dataset.date || '';
        } else if (column === 'files') {
            aVal = parseInt(a.dataset.files) || 0;
            bVal = parseInt(b.dataset.files) || 0;
        }

        if (typeof aVal === 'number') {
            return currentSortDirection === 'asc' ? aVal - bVal : bVal - aVal;
        }
        return currentSortDirection === 'asc'
            ? aVal.localeCompare(bVal)
            : bVal.localeCompare(aVal);
    });

    // Re-append in sorted order
    rows.forEach(row => tbody.appendChild(row));

    // Update header sort indicators
    updateSortIndicators();
}

function updateSortIndicators() {
    // Remove all sort classes
    document.querySelectorAll('.backup-table th.sortable').forEach(th => {
        th.classList.remove('sort-active', 'sort-asc', 'sort-desc');
        const icon = th.querySelector('.sort-icon');
        if (icon) icon.textContent = '';
    });

    // Add to current sort column
    const activeHeader = document.querySelector(`.backup-table th[data-sort="${currentSortColumn}"]`);
    if (activeHeader) {
        activeHeader.classList.add('sort-active', `sort-${currentSortDirection}`);
    }
}

function showEmptyState() {
    const container = document.querySelector('.backup-table-container');
    if (container && !document.querySelector('.backup-row')) {
        container.innerHTML = `
            <div class="empty-state empty-state--dark empty-state--flex">
                <div class="empty-icon"><i class="fa-solid fa-box-archive"></i></div>
                <h3>No backups available</h3>
                <p>Backups are automatically created before any changes are committed</p>
                <div class="empty-tips">
                    <div class="tip"><strong>Automatic:</strong> Created before each commit to protect your config</div>
                    <div class="tip"><strong>Manual:</strong> Use the form on the left to create backups anytime</div>
                    <div class="tip"><strong>Restore:</strong> Roll back to any previous backup point</div>
                </div>
            </div>
        `;
    }
}

function updateBackupCount() {
    const rows = document.querySelectorAll('.backup-row');
    const countEl = document.querySelector('.badge-count');
    if (countEl) {
        const count = rows.length;
        countEl.textContent = `${count} backup${count !== 1 ? 's' : ''}`;
    }

    // Show empty state if no backups left
    if (rows.length === 0) {
        showEmptyState();
    }
}

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize sort indicators
    updateSortIndicators();

    // Event delegation for data-action elements
    document.addEventListener('click', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;

        const action = actionEl.dataset.action;
        const name = actionEl.dataset.name;

        switch (action) {
            case 'create-backup':
                createBackup();
                break;
            case 'restore-backup':
                if (name) restoreBackup(name, actionEl);
                break;
            case 'delete-backup':
                if (name) deleteBackup(name, actionEl);
                break;
            case 'delete-all-backups':
                deleteAllBackups();
                break;
            case 'sort-backups':
                const column = actionEl.dataset.sort;
                if (column) sortBackups(column);
                break;
        }
    });
});
