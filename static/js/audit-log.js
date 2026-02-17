// Audit Log page JavaScript
// Extracted from audit_log.html
// Note: configPath must be set before this script loads

let allEntries = [];
let activeFilters = new Set(['all']);
let currentArchive = 'current';
let searchQuery = '';

// Pagination state
let auditCurrentPage = 1;
let auditPageSize = 25;

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Build error display HTML for container
 * @param {string} message - Error message to display
 * @returns {string} HTML string for error display
 */
function buildErrorDisplay(message) {
    return `<div class="empty-state empty-state--dark empty-state--flex">Error: ${escapeHtml(message)}</div>`;
}

/**
 * Parse date from archive filename
 * @param {string} filename - Archive filename (e.g., audit_log_20240205_153045.json)
 * @returns {Date|null} Parsed date or null if format doesn't match
 */
function parseArchiveDate(filename) {
    const match = filename.match(/audit_log_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json/);
    if (match) {
        return new Date(match[1], match[2] - 1, match[3], match[4], match[5], match[6]);
    }
    return null;
}

/**
 * Search within an entry array for matching fields
 * @param {Array} arr - Array to search (e.g., entry.object_edits)
 * @param {string} query - Lowercase search query
 * @param {Array<string>} fields - Field names to search
 * @returns {boolean} True if any item matches
 */
function searchInEntryArray(arr, query, fields) {
    if (!arr) {return false;}
    return arr.some(item =>
        fields.some(field => item[field] && item[field].toLowerCase().includes(query))
    );
}

/**
 * Generate badge HTML for a count
 * @param {number} count - Item count
 * @param {string} cssClass - Badge CSS class
 * @param {string} singular - Singular label (e.g., "object created")
 * @param {string} plural - Plural label (e.g., "objects created")
 * @returns {string} Badge HTML or empty string if count is 0
 */
function generateBadge(count, cssClass, singular, plural) {
    if (count === 0) {return '';}
    return `<span class="audit-badge ${cssClass}">${count} ${count === 1 ? singular : plural}</span>`;
}

// Convert path to display path with config folder prefix
function toDisplayPath(path) {
    if (!path) {return '';}
    if (path.startsWith(configPath + '/')) {
        return configRootName + '/' + path.substring(configPath.length + 1);
    } else if (path === configPath) {
        return configRootName;
    }
    if (!path.startsWith('/')) {
        return configRootName + '/' + path;
    }
    return path;
}

document.addEventListener('DOMContentLoaded', function() {
    refreshAuditLog();
    loadArchivesList();

    // Search input handler with debounce
    const searchInput = document.getElementById('auditSearch');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                searchQuery = this.value.trim();
                auditCurrentPage = 1; // Reset to first page on search
                renderEntries();
            }, 300);
        });
    }
});

function filterByType(checkbox) {
    const chip = checkbox.closest('.filter-chip');
    const value = checkbox.value;

    if (value === 'all') {
        // Clear all other filters
        document.querySelectorAll('.type-filter').forEach(cb => {
            cb.checked = (cb.value === 'all');
            cb.closest('.filter-chip').classList.toggle('active', cb.value === 'all');
        });
        activeFilters = new Set(['all']);
    } else {
        // Uncheck 'all' filter
        const allCheckbox = document.querySelector('.type-filter[value="all"]');
        allCheckbox.checked = false;
        allCheckbox.closest('.filter-chip').classList.remove('active');
        activeFilters.delete('all');

        if (checkbox.checked) {
            activeFilters.add(value);
            chip.classList.add('active');
        } else {
            activeFilters.delete(value);
            chip.classList.remove('active');
        }

        // If nothing selected, revert to 'all'
        if (activeFilters.size === 0) {
            allCheckbox.checked = true;
            allCheckbox.closest('.filter-chip').classList.add('active');
            activeFilters.add('all');
        }
    }

    renderEntries();
}

async function refreshAuditLog() {
    const container = document.getElementById('auditLogContainer');
    container.innerHTML = '<div class="audit-loading">Loading audit log...</div>';

    const result = await ApiClient.get('/api/audit-log', { silent: true });

    if (!result.success) {
        container.innerHTML = buildErrorDisplay(result.error);
        return;
    }

    if (result.data.error) {
        container.innerHTML = buildErrorDisplay(result.data.error);
        return;
    }

    allEntries = (result.data.entries || []).reverse();
    renderEntries();
}

// Filter matchers: each returns true if the entry matches the given filter category
const TYPE_FILTER_MATCHERS = {
    creates: entry => (entry.object_creations || []).length > 0,
    attrs: entry => (entry.object_edits || []).length > 0,
    moves: entry => (entry.object_moves || []).length > 0 || (entry.file_moves || []).length > 0 || (entry.folder_moves || []).length > 0,
    deletes: entry => (entry.object_deletions || []).length > 0 || (entry.file_deletions || []).length > 0,
    git: entry => entry.action && entry.action.startsWith('git_'),
    backups: entry => entry.action && entry.action.startsWith('backup'),
};

function matchesTypeFilter(entry) {
    for (const filter of activeFilters) {
        const matcher = TYPE_FILTER_MATCHERS[filter];
        if (matcher && matcher(entry)) {return true;}
    }
    return false;
}

// Searchable array fields in audit entries
const SEARCH_ARRAY_FIELDS = [
    { key: 'object_edits', fields: ['object_name', 'object_type'] },
    { key: 'object_moves', fields: ['object_name', 'from_file', 'to_file'] },
    { key: 'object_creations', fields: ['object_name', 'file'] },
    { key: 'object_deletions', fields: ['object_name', 'file'] },
    { key: 'file_moves', fields: ['from', 'to'] },
    { key: 'file_deletions', fields: ['path'] },
];

// Searchable scalar fields in audit entries
const SEARCH_SCALAR_FIELDS = ['userName', 'userEmail', 'action', 'commit_hash', 'message', 'backup_name', 'description'];

function matchesSearchQuery(entry, query) {
    const time = new Date(entry.timestamp).toLocaleString().toLowerCase();
    if (time.includes(query)) {return true;}

    for (const field of SEARCH_SCALAR_FIELDS) {
        if (entry[field] && entry[field].toLowerCase().includes(query)) {return true;}
    }

    for (const { key, fields } of SEARCH_ARRAY_FIELDS) {
        if (searchInEntryArray(entry[key], query, fields)) {return true;}
    }

    return false;
}

function renderEntries() {
    const container = document.getElementById('auditLogContainer');
    const countEl = document.getElementById('entryCount');

    if (allEntries.length === 0) {
        countEl.textContent = '0 entries';
        container.innerHTML = `
            <div class="empty-state empty-state--dark empty-state--flex">
                <div class="empty-icon"><i class="fa-solid fa-clipboard-list"></i></div>
                <h3>No audit log entries</h3>
                <p>Changes will be logged here when you commit modifications to your Nagios configuration</p>
                <div class="empty-tips">
                    <div class="tip"><strong>Tracked:</strong> All attribute changes, object moves, and deletions</div>
                    <div class="tip"><strong>Automatic:</strong> Entries are created when you commit staged changes</div>
                    <div class="tip"><strong>Persistent:</strong> Log survives server restarts</div>
                </div>
            </div>
        `;
        return;
    }

    // Filter entries by type
    let filteredEntries = allEntries;
    if (!activeFilters.has('all')) {
        filteredEntries = allEntries.filter(matchesTypeFilter);
    }

    // Filter entries by search query
    if (searchQuery) {
        const query = searchQuery.toLowerCase();
        filteredEntries = filteredEntries.filter(entry => matchesSearchQuery(entry, query));
    }

    countEl.textContent = `${filteredEntries.length} entr${filteredEntries.length === 1 ? 'y' : 'ies'}`;

    if (filteredEntries.length === 0) {
        const emptyMessage = searchQuery
            ? `No entries match "${escapeHtml(searchQuery)}". Try a different search term.`
            : 'No entries match the current filter. Try selecting different filters.';
        container.innerHTML = `
            <div class="empty-state empty-state--dark empty-state--flex">
                <div class="empty-icon"><i class="fa-solid fa-magnifying-glass"></i></div>
                <h3>No matching entries</h3>
                <p>${emptyMessage}</p>
            </div>
        `;
        return;
    }

    // Apply pagination
    const totalItems = filteredEntries.length;
    const totalPages = Math.ceil(totalItems / auditPageSize);
    auditCurrentPage = Math.min(auditCurrentPage, Math.max(1, totalPages));
    const startIdx = (auditCurrentPage - 1) * auditPageSize;
    const endIdx = Math.min(startIdx + auditPageSize, totalItems);
    const pageEntries = filteredEntries.slice(startIdx, endIdx);

    let html = pageEntries.map(entry => renderAuditEntry(entry)).join('');

    // Add pagination if needed
    const paginationHtml = renderAuditPagination(totalItems);
    if (paginationHtml) {
        html += paginationHtml;
    }

    container.innerHTML = html;
}

function renderAuditPagination(totalItems) {
    return renderPagination({
        currentPage: auditCurrentPage,
        totalItems,
        pageSize: auditPageSize,
        actionPrefix: 'audit',
        extraStyle: 'margin-top: var(--nbe-space-lg); border-radius: var(--nbe-radius-lg);'
    });
}

function setAuditPage(page) {
    auditCurrentPage = page;
    renderEntries();
    // Scroll to top of list
    const container = document.getElementById('auditLogContainer');
    if (container) {container.scrollTop = 0;}
}

function setAuditPageSize(size) {
    auditPageSize = size;
    auditCurrentPage = 1;
    renderEntries();
}

const ACTION_CONFIG = {
    backup_created: { badgeClass: 'backup', badgeText: 'backup created', icon: 'fa-floppy-disk', title: 'Backup Created' },
    backup_restored: { badgeClass: 'restore', badgeText: 'backup restored', icon: 'fa-rotate-left', title: 'Backup Restored' },
    backup_deleted: { badgeClass: 'deletes', badgeText: 'backup deleted', icon: 'fa-trash', title: 'Backup Deleted' },
    backups_deleted: { badgeClass: 'deletes', icon: 'fa-trash', title: 'All Backups Deleted' },
    git_initialized: { badgeClass: 'git', badgeText: 'git initialized', icon: 'fa-code-branch', title: 'Git Repository Initialized' },
    git_restored: { badgeClass: 'restore', badgeText: 'git restored', icon: 'fa-clock-rotate-left', title: 'Restored to Git Commit' },
    git_commit: { badgeClass: 'git', badgeText: 'git commit', icon: 'fa-check', title: 'Git Commit' },
    git_discarded: { badgeClass: 'git', badgeText: 'discarded', icon: 'fa-trash', title: 'Discarded Uncommitted Changes' },
    git_clear_history: { badgeClass: 'git', badgeText: 'history cleared', icon: 'fa-rotate', title: 'Cleared Git History' },
};

function buildActionDetails(entry, action) {
    let details = '';
    switch (action) {
        case 'backup_created':
            details = entry.description ? `<div class="audit-detail-item">${escapeHtml(entry.description)}</div>` : '';
            break;
        case 'backup_restored':
            details = `<div class="audit-detail-item">Restored from: ${escapeHtml(entry.backup_name)}</div>`;
            break;
        case 'backup_deleted':
            details = `<div class="audit-detail-item">Deleted: ${escapeHtml(entry.backup_name)}</div>`;
            break;
        case 'backups_deleted':
            details = `<div class="audit-detail-item">${entry.deleted_count} backup${entry.deleted_count !== 1 ? 's' : ''} deleted</div>`;
            break;
        case 'git_initialized':
            details = `<div class="audit-detail-item">First commit: ${escapeHtml(entry.commit_hash)}</div>`;
            if (entry.message) {details += `<div class="audit-detail-item" class="audit-detail-muted">${escapeHtml(entry.message)}</div>`;}
            break;
        case 'git_restored':
            details = `<div class="audit-detail-item">Commit: ${escapeHtml(entry.commit_hash)}</div>`;
            if (entry.commit_message) {details += `<div class="audit-detail-item" class="audit-detail-muted">${escapeHtml(entry.commit_message)}</div>`;}
            if (entry.deleted_files_count > 0) {details += `<div class="audit-detail-item" style="color: var(--color-delete);">${entry.deleted_files_count} file${entry.deleted_files_count !== 1 ? 's' : ''} removed</div>`;}
            break;
        case 'git_commit':
            details = `<div class="audit-detail-item">Commit: ${escapeHtml(entry.commit_hash)}</div>`;
            if (entry.restoreType) {details += `<div class="audit-detail-item">Restored from: ${escapeHtml(entry.restoreFrom)}</div>`;}
            if (entry.message) {details += `<div class="audit-detail-item" class="audit-detail-muted">${escapeHtml(entry.message)}</div>`;}
            break;
        case 'git_discarded':
            details = '<div class="audit-detail-item">Reverted working directory to HEAD</div>';
            break;
        case 'git_clear_history':
            details = `<div class="audit-detail-item">${escapeHtml(entry.description || 'Repository reinitialized with fresh history')}</div>`;
            break;
    }
    return details;
}

function renderUserHtml(entry) {
    if (!entry.userName && !entry.userEmail) {return '';}
    const userName = entry.userName || 'Unknown';
    const userEmail = entry.userEmail ? ` (${entry.userEmail})` : '';
    return `<span class="audit-entry-user">${escapeHtml(userName)}${escapeHtml(userEmail)}</span>`;
}

function renderActionEntry(entry, time) {
    const config = ACTION_CONFIG[entry.action];
    let badge, icon, title;

    if (config) {
        const badgeText = config.badgeText || (entry.action === 'backups_deleted' ? `${entry.deleted_count} backups deleted` : entry.action);
        badge = `<span class="audit-badge ${config.badgeClass}">${escapeHtml(badgeText)}</span>`;
        icon = `<i class="fa-solid ${config.icon}"></i>`;
        title = entry.action === 'git_commit' && entry.restoreType
            ? `Committed ${entry.restoreType === 'backup' ? 'Backup' : 'Git'} Restore`
            : config.title;
    } else {
        badge = `<span class="audit-badge">${escapeHtml(entry.action)}</span>`;
        icon = '<i class="fa-solid fa-clipboard-list"></i>';
        title = entry.action.replace(/_/g, ' ');
    }

    const details = buildActionDetails(entry, entry.action);
    const userHtml = renderUserHtml(entry);

    let entryType = 'backup';
    if (entry.action && entry.action.startsWith('git_')) {
        entryType = 'git';
    } else if (entry.action === 'backup_deleted' || entry.action === 'backups_deleted') {
        entryType = 'deletes';
    }

    return `
        <div class="audit-entry" data-type="${entryType}">
            <div class="audit-entry-header">
                <span class="audit-entry-time">${escapeHtml(time)}</span>
                ${userHtml}
                <div class="audit-entry-badges">${badge}</div>
            </div>
            <div class="audit-entry-details">
                <div class="audit-detail-section">
                    <div class="audit-detail-title">${icon} ${title}</div>
                    ${details}
                </div>
            </div>
        </div>
    `;
}

function renderEditsSection(edits) {
    if (!edits || edits.length === 0) {return '';}
    let html = '<div class="audit-detail-section"><div class="audit-detail-title">Attribute Changes</div>';
    edits.forEach(change => {
        html += `<div class="audit-detail-item">`;
        html += `<div class="object-info"><span class="object-type type-${escapeHtml(change.object_type)}">${escapeHtml(change.object_type)}</span>${escapeHtml(change.object_name)}</div>`;
        if (change.changes && change.changes.length > 0) {
            change.changes.forEach(c => {
                if (c.type === 'add') {
                    html += `<div class="change-line change-add">+ ${escapeHtml(c.key)}: ${escapeHtml(c.value)}</div>`;
                } else if (c.type === 'remove') {
                    html += `<div class="change-line change-remove">- ${escapeHtml(c.key)}: ${escapeHtml(c.value)}</div>`;
                } else {
                    html += `<div class="change-line change-modify">~ ${escapeHtml(c.key)}: ${escapeHtml(c.from)} &rarr; ${escapeHtml(c.to)}</div>`;
                }
            });
        }
        html += '</div>';
    });
    html += '</div>';
    return html;
}

function renderMovesSection(moves) {
    if (!moves || moves.length === 0) {return '';}
    let html = '<div class="audit-detail-section"><div class="audit-detail-title">Object Moves</div>';
    moves.forEach(move => {
        html += `<div class="audit-detail-item">`;
        html += `<div class="object-info"><span class="object-type type-${escapeHtml(move.object_type)}">${escapeHtml(move.object_type)}</span>${escapeHtml(move.object_name)}</div>`;
        html += `<div class="change-line change-modify">${escapeHtml(toDisplayPath(move.from_file))} &rarr; ${escapeHtml(toDisplayPath(move.to_file))}</div>`;
        html += '</div>';
    });
    html += '</div>';
    return html;
}

function renderCreationsSection(creations) {
    if (!creations || creations.length === 0) {return '';}
    let html = '<div class="audit-detail-section"><div class="audit-detail-title">Objects Created</div>';
    creations.forEach(creation => {
        html += `<div class="audit-detail-item">`;
        html += `<div class="object-info"><span class="object-type type-${escapeHtml(creation.object_type)}">${escapeHtml(creation.object_type)}</span>${escapeHtml(creation.object_name)}</div>`;
        html += `<div class="change-line change-add">+ Created in ${escapeHtml(toDisplayPath(creation.file))}</div>`;
        html += '</div>';
    });
    html += '</div>';
    return html;
}

function renderRelocationsSection(title, items, fromField, toField) {
    if (!items || items.length === 0) {return '';}
    let html = `<div class="audit-detail-section"><div class="audit-detail-title">${title}</div>`;
    items.forEach(item => {
        html += `<div class="audit-detail-item">`;
        html += `<div class="change-line change-modify">${escapeHtml(toDisplayPath(item[fromField]))} &rarr; ${escapeHtml(toDisplayPath(item[toField]))}</div>`;
        html += '</div>';
    });
    html += '</div>';
    return html;
}

function renderDeletionsSection(objDeletions, fileDeletions) {
    let html = '';
    if (objDeletions && objDeletions.length > 0) {
        html += '<div class="audit-detail-section"><div class="audit-detail-title">Objects Deleted</div>';
        objDeletions.forEach(deletion => {
            html += `<div class="audit-detail-item">`;
            html += `<div class="object-info"><span class="object-type type-${escapeHtml(deletion.object_type)}">${escapeHtml(deletion.object_type)}</span>${escapeHtml(deletion.object_name)}</div>`;
            html += `<div class="change-line change-remove">- Deleted from ${escapeHtml(toDisplayPath(deletion.file))}</div>`;
            html += '</div>';
        });
        html += '</div>';
    }
    if (fileDeletions && fileDeletions.length > 0) {
        html += '<div class="audit-detail-section"><div class="audit-detail-title">Files/Folders Deleted</div>';
        fileDeletions.forEach(deletion => {
            const suffix = deletion.type === 'folder' ? '/ (folder)' : '';
            html += `<div class="audit-detail-item"><div class="change-line change-remove">- ${escapeHtml(toDisplayPath(deletion.path))}${suffix}</div></div>`;
        });
        html += '</div>';
    }
    return html;
}

function computeEntryCounts(entry) {
    const attrCount = (entry.object_edits || []).length;
    const moveCount = (entry.object_moves || []).length;
    const createCount = (entry.object_creations || []).length;
    const folderCount = (entry.folder_creations || []).length;
    const relocCount = (entry.file_moves || []).length;
    const folderRelocCount = (entry.folder_moves || []).length;
    const objDeleteCount = (entry.object_deletions || []).length;
    const fileDeleteCount = (entry.file_deletions || []).length;
    return { attrCount, moveCount, createCount, folderCount, relocCount, folderRelocCount, objDeleteCount, fileDeleteCount, deleteCount: objDeleteCount + fileDeleteCount, errorCount: (entry.errors || []).length };
}

function renderAuditEntry(entry) {
    const time = new Date(entry.timestamp).toLocaleString();

    if (entry.action) {
        return renderActionEntry(entry, time);
    }

    const counts = computeEntryCounts(entry);

    const badges = [
        generateBadge(counts.createCount, 'creates', 'object created', 'objects created'),
        generateBadge(counts.attrCount, 'attrs', 'attribute change', 'attribute changes'),
        generateBadge(counts.moveCount, 'moves', 'object move', 'object moves'),
        generateBadge(counts.folderCount, 'folders', 'folder created', 'folders created'),
        generateBadge(counts.relocCount, 'relocs', 'file relocated', 'files relocated'),
        generateBadge(counts.folderRelocCount, 'folder-relocs', 'folder relocated', 'folders relocated'),
        generateBadge(counts.deleteCount, 'deletes', 'deletion', 'deletions'),
        generateBadge(counts.errorCount, 'errors', 'error', 'errors')
    ].join('');

    let detailsHtml = '<div class="audit-entry-details">';
    detailsHtml += renderEditsSection(entry.object_edits);
    detailsHtml += renderMovesSection(entry.object_moves);
    detailsHtml += renderCreationsSection(entry.object_creations);
    if (counts.folderCount > 0) {
        detailsHtml += '<div class="audit-detail-section"><div class="audit-detail-title">Folders Created</div>';
        entry.folder_creations.forEach(folder => {
            detailsHtml += `<div class="audit-detail-item"><div class="change-line change-add">+ ${escapeHtml(toDisplayPath(folder.path))}/</div></div>`;
        });
        detailsHtml += '</div>';
    }
    detailsHtml += renderRelocationsSection('Files Relocated', entry.file_moves, 'from', 'to');
    detailsHtml += renderRelocationsSection('Folders Relocated', entry.folder_moves, 'from', 'to');
    detailsHtml += renderDeletionsSection(entry.object_deletions, entry.file_deletions);
    detailsHtml += '</div>';

    let errorsHtml = '';
    if (counts.errorCount > 0) {
        errorsHtml = '<div class="audit-entry-errors"><strong>Errors:</strong><br>';
        errorsHtml += entry.errors.map(e => escapeHtml(e)).join('<br>');
        errorsHtml += '</div>';
    }

    const userHtml = renderUserHtml(entry);

    let entryType = '';
    if (counts.deleteCount > 0) {entryType = 'deletes';}
    else if (counts.createCount > 0) {entryType = 'creates';}
    else if (counts.moveCount > 0 || counts.relocCount > 0 || counts.folderRelocCount > 0) {entryType = 'moves';}
    else if (counts.attrCount > 0) {entryType = 'attrs';}

    return `
        <div class="audit-entry"${entryType ? ` data-type="${entryType}"` : ''}>
            <div class="audit-entry-header">
                <span class="audit-entry-time">${escapeHtml(time)}</span>
                ${userHtml}
                <div class="audit-entry-badges">${badges}</div>
            </div>
            ${detailsHtml}
            ${errorsHtml}
        </div>
    `;
}

async function confirmClearLog() {
    const confirmed = await showConfirmDialog({
        title: 'Clear Audit Log',
        message: 'Are you sure you want to clear the entire audit log? This action cannot be undone.',
        confirmText: 'Clear',
        cancelText: 'Cancel',
        type: 'danger'
    });

    if (confirmed) {
        clearAuditLog();
    }
}

async function clearAuditLog() {
    const result = await ApiClient.post('/api/audit-log/clear', {}, { errorPrefix: 'Clear log' });

    if (result.success) {
        showToast('Audit log cleared', 'success');
        refreshAuditLog();
    }
}

async function loadArchivesList() {
    const listEl = document.getElementById('archivesList');
    const loadingEl = document.getElementById('archivesLoading');

    loadingEl.style.display = 'block';

    const result = await ApiClient.get('/api/audit-log/archives', { silent: true });

    if (!result.success || result.data.error) {
        console.error('Error loading archives:', result.error || result.data.error);
        loadingEl.style.display = 'none';
        return;
    }

    // Build archives list HTML
    let html = `
        <div class="archive-item ${currentArchive === 'current' ? 'active' : ''}"
             data-archive="current" onclick="loadCurrentLog()">
            <span class="archive-name">Current Log</span>
        </div>
    `;

    (result.data.archives || []).forEach(archive => {
        const date = parseArchiveDate(archive.filename);
        let displayDate = archive.filename;
        if (date) {
            displayDate = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }

        const sizeKB = (archive.size / 1024).toFixed(1);
        html += `
            <div class="archive-item ${currentArchive === archive.filename ? 'active' : ''}"
                 data-archive="${escapeHtml(archive.filename)}"
                 onclick="loadArchive('${escapeJs(archive.filename)}')">
                <span class="archive-name">${escapeHtml(displayDate)}</span>
                <span class="archive-size">${sizeKB} KB</span>
            </div>
        `;
    });

    listEl.innerHTML = html;
    loadingEl.style.display = 'none';
}

function loadCurrentLog() {
    currentArchive = 'current';
    updateArchiveSelection();
    refreshAuditLog();
}

async function loadArchive(filename) {
    currentArchive = filename;
    updateArchiveSelection();

    const container = document.getElementById('auditLogContainer');
    container.innerHTML = '<div class="audit-loading">Loading archive...</div>';

    const result = await ApiClient.get(`/api/audit-log/archives/${encodeURIComponent(filename)}`, { silent: true });

    if (!result.success) {
        container.innerHTML = buildErrorDisplay(result.error);
        return;
    }

    if (result.data.error) {
        container.innerHTML = buildErrorDisplay(result.data.error);
        return;
    }

    allEntries = (result.data.entries || []).reverse();
    renderEntries();
}

function updateArchiveSelection() {
    document.querySelectorAll('.archive-item').forEach(item => {
        item.classList.toggle('active', item.dataset.archive === currentArchive);
    });

    // Update page title to show which log is being viewed
    const titleEl = document.querySelector('.page-title');
    if (currentArchive === 'current') {
        titleEl.textContent = 'Change History';
    } else {
        const date = parseArchiveDate(currentArchive);
        if (date) {
            titleEl.textContent = 'Archive: ' + date.toLocaleDateString();
        } else {
            titleEl.textContent = 'Archive: ' + currentArchive;
        }
    }
}

// Event delegation for data-action attributes
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) {return;}

    const action = actionEl.dataset.action;
    switch (action) {
        case 'confirmClearLog':
            confirmClearLog();
            break;
        case 'loadCurrentLog':
            loadCurrentLog();
            break;
        case 'loadArchive':
            loadArchive(actionEl.dataset.archive);
            break;
        case 'audit-page':
            const page = parseInt(actionEl.dataset.page, 10);
            if (page) {setAuditPage(page);}
            break;
    }
});

document.addEventListener('change', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) {return;}

    const action = actionEl.dataset.action;
    if (action === 'filterByType') {
        auditCurrentPage = 1; // Reset to first page on filter change
        filterByType(actionEl);
    } else if (action === 'audit-page-size') {
        const size = parseInt(actionEl.value, 10);
        if (size) {setAuditPageSize(size);}
    }
});
