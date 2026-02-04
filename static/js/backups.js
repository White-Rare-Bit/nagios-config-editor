// Backups page JavaScript
// Converted to table layout with sortable columns

// Sort state
let currentSortColumn = 'date';
let currentSortDirection = 'desc';

// Pagination state
let backupCurrentPage = 1;
let backupPageSize = 25;
let allBackupRows = [];

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
        // Remove from list and re-render
        removeBackupFromList(name);
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
        // Clear all backups from array and DOM
        allBackupRows = [];
        const tbody = document.getElementById('backupTableBody');
        if (tbody) tbody.innerHTML = '';
        updateBackupCount();
        showToast(`Deleted ${result.data.deleted_count} backup${result.data.deleted_count !== 1 ? 's' : ''}`, 'success');
    } else {
        showToast('Error: ' + (result.error || 'Unknown error'), 'error');
    }
}

function sortBackups(column) {
    if (allBackupRows.length === 0) return;

    // Toggle direction if same column, otherwise default to desc for date, asc for others
    if (column === currentSortColumn) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = column;
        currentSortDirection = column === 'date' ? 'desc' : 'asc';
    }

    // Sort allBackupRows array
    allBackupRows.sort((a, b) => {
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

    // Reset to first page after sorting
    backupCurrentPage = 1;

    // Re-render with pagination
    renderBackupPage();

    // Update header sort indicators
    updateSortIndicators();
}

function renderBackupPage() {
    const tbody = document.getElementById('backupTableBody');
    if (!tbody) return;

    const totalItems = allBackupRows.length;
    const totalPages = Math.ceil(totalItems / backupPageSize);
    backupCurrentPage = Math.min(backupCurrentPage, Math.max(1, totalPages));
    const startIdx = (backupCurrentPage - 1) * backupPageSize;
    const endIdx = Math.min(startIdx + backupPageSize, totalItems);

    // Clear tbody and add only current page rows
    tbody.innerHTML = '';
    for (let i = startIdx; i < endIdx; i++) {
        tbody.appendChild(allBackupRows[i].cloneNode(true));
    }

    // Update or create pagination
    renderBackupPagination(totalItems, totalPages, startIdx, endIdx);
}

function renderBackupPagination(totalItems, totalPages, startIdx, endIdx) {
    const container = document.querySelector('.backup-table-container');
    if (!container) return;

    // Remove existing pagination
    const existingPagination = container.querySelector('.nbe-pagination');
    if (existingPagination) {
        existingPagination.remove();
    }

    // Only show pagination if needed
    if (totalPages <= 1 && totalItems <= 25) return;

    let pagesHtml = '';

    // Previous button
    pagesHtml += `<button class="nbe-pagination-btn nbe-pagination-nav" data-action="backup-page" data-page="${backupCurrentPage - 1}" ${backupCurrentPage === 1 ? 'disabled' : ''}>
        <i class="fa-solid fa-chevron-left"></i>
    </button>`;

    // Page numbers
    const maxVisible = 5;
    let startPage = Math.max(1, backupCurrentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage + 1 < maxVisible) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }

    if (startPage > 1) {
        pagesHtml += `<button class="nbe-pagination-btn" data-action="backup-page" data-page="1">1</button>`;
        if (startPage > 2) {
            pagesHtml += `<span class="nbe-pagination-ellipsis">...</span>`;
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        pagesHtml += `<button class="nbe-pagination-btn${i === backupCurrentPage ? ' active' : ''}" data-action="backup-page" data-page="${i}">${i}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            pagesHtml += `<span class="nbe-pagination-ellipsis">...</span>`;
        }
        pagesHtml += `<button class="nbe-pagination-btn" data-action="backup-page" data-page="${totalPages}">${totalPages}</button>`;
    }

    // Next button
    pagesHtml += `<button class="nbe-pagination-btn nbe-pagination-nav" data-action="backup-page" data-page="${backupCurrentPage + 1}" ${backupCurrentPage === totalPages ? 'disabled' : ''}>
        <i class="fa-solid fa-chevron-right"></i>
    </button>`;

    const paginationHtml = `
        <div class="nbe-pagination">
            <div class="nbe-pagination-info">
                <span class="nbe-pagination-showing">Showing ${startIdx + 1}-${endIdx} of ${totalItems}</span>
                <div class="nbe-pagination-page-size">
                    <span>Per page:</span>
                    <select data-action="backup-page-size">
                        <option value="25" ${backupPageSize === 25 ? 'selected' : ''}>25</option>
                        <option value="50" ${backupPageSize === 50 ? 'selected' : ''}>50</option>
                        <option value="100" ${backupPageSize === 100 ? 'selected' : ''}>100</option>
                    </select>
                </div>
            </div>
            <div class="nbe-pagination-controls">
                ${pagesHtml}
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', paginationHtml);
}

function setBackupPage(page) {
    backupCurrentPage = page;
    renderBackupPage();
}

function setBackupPageSize(size) {
    backupPageSize = size;
    backupCurrentPage = 1;
    renderBackupPage();
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
    const countEl = document.querySelector('.badge-count');
    if (countEl) {
        const count = allBackupRows.length;
        countEl.textContent = `${count} backup${count !== 1 ? 's' : ''}`;
    }

    // Show empty state if no backups left
    if (allBackupRows.length === 0) {
        showEmptyState();
    }
}

function removeBackupFromList(name) {
    // Remove from allBackupRows array
    const index = allBackupRows.findIndex(row => row.dataset.name === name);
    if (index !== -1) {
        allBackupRows.splice(index, 1);
    }
    // Re-render page
    if (allBackupRows.length > 0) {
        renderBackupPage();
    }
    updateBackupCount();
}

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Store all backup rows for pagination
    const tbody = document.getElementById('backupTableBody');
    if (tbody) {
        allBackupRows = Array.from(tbody.querySelectorAll('.backup-row'));
        // Initial render with pagination
        if (allBackupRows.length > 0) {
            renderBackupPage();
        }
    }

    // Initialize sort indicators
    updateSortIndicators();

    // Event delegation for select changes (pagination page size)
    document.addEventListener('change', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (actionEl) {
            const action = actionEl.dataset.action;
            if (action === 'backup-page-size') {
                const size = parseInt(actionEl.value);
                if (size) setBackupPageSize(size);
            }
        }
    });

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
            case 'backup-page':
                const page = parseInt(actionEl.dataset.page);
                if (page) setBackupPage(page);
                break;
        }
    });
});
