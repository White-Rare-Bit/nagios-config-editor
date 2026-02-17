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
        filteredEntries = allEntries.filter(entry => {
            if (activeFilters.has('creates') && (entry.object_creations || []).length > 0) {return true;}
            if (activeFilters.has('attrs') && (entry.object_edits || []).length > 0) {return true;}
            if (activeFilters.has('moves') && ((entry.object_moves || []).length > 0 || (entry.file_moves || []).length > 0 || (entry.folder_moves || []).length > 0)) {return true;}
            if (activeFilters.has('deletes') && ((entry.object_deletions || []).length > 0 || (entry.file_deletions || []).length > 0)) {return true;}
            if (activeFilters.has('git') && entry.action && entry.action.startsWith('git_')) {return true;}
            if (activeFilters.has('backups') && entry.action && entry.action.startsWith('backup')) {return true;}
            return false;
        });
    }

    // Filter entries by search query
    if (searchQuery) {
        const query = searchQuery.toLowerCase();
        filteredEntries = filteredEntries.filter(entry => {
            // Search in timestamp
            const time = new Date(entry.timestamp).toLocaleString().toLowerCase();
            if (time.includes(query)) {return true;}

            // Search in user info
            if (entry.userName && entry.userName.toLowerCase().includes(query)) {return true;}
            if (entry.userEmail && entry.userEmail.toLowerCase().includes(query)) {return true;}

            // Search in action type
            if (entry.action && entry.action.toLowerCase().includes(query)) {return true;}

            // Search in entry arrays using helper
            if (searchInEntryArray(entry.object_edits, query, ['object_name', 'object_type'])) {return true;}
            if (searchInEntryArray(entry.object_moves, query, ['object_name', 'from_file', 'to_file'])) {return true;}
            if (searchInEntryArray(entry.object_creations, query, ['object_name', 'file'])) {return true;}
            if (searchInEntryArray(entry.object_deletions, query, ['object_name', 'file'])) {return true;}
            if (searchInEntryArray(entry.file_moves, query, ['from', 'to'])) {return true;}
            if (searchInEntryArray(entry.file_deletions, query, ['path'])) {return true;}

            // Search in git-related fields
            if (entry.commit_hash && entry.commit_hash.toLowerCase().includes(query)) {return true;}
            if (entry.message && entry.message.toLowerCase().includes(query)) {return true;}
            if (entry.backup_name && entry.backup_name.toLowerCase().includes(query)) {return true;}
            if (entry.description && entry.description.toLowerCase().includes(query)) {return true;}

            return false;
        });
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

function renderActionEntry(entry, time) {
    let badge = '';
    let icon = '';
    let title = '';
    let details = '';

    switch (entry.action) {
        case 'backup_created':
            badge = '<span class="audit-badge backup">backup created</span>';
            icon = '<i class="fa-solid fa-floppy-disk"></i>';
            title = 'Backup Created';
            details = entry.description ? `<div class="audit-detail-item">${escapeHtml(entry.description)}</div>` : '';
            break;
        case 'backup_restored':
            badge = '<span class="audit-badge restore">backup restored</span>';
            icon = '<i class="fa-solid fa-rotate-left"></i>';
            title = 'Backup Restored';
            details = `<div class="audit-detail-item">Restored from: ${escapeHtml(entry.backup_name)}</div>`;
            break;
        case 'backup_deleted':
            badge = '<span class="audit-badge deletes">backup deleted</span>';
            icon = '<i class="fa-solid fa-trash"></i>';
            title = 'Backup Deleted';
            details = `<div class="audit-detail-item">Deleted: ${escapeHtml(entry.backup_name)}</div>`;
            break;
        case 'backups_deleted':
            badge = `<span class="audit-badge deletes">${entry.deleted_count} backups deleted</span>`;
            icon = '<i class="fa-solid fa-trash"></i>';
            title = 'All Backups Deleted';
            details = `<div class="audit-detail-item">${entry.deleted_count} backup${entry.deleted_count !== 1 ? 's' : ''} deleted</div>`;
            break;
        case 'git_initialized':
            badge = '<span class="audit-badge git">git initialized</span>';
            icon = '<i class="fa-solid fa-code-branch"></i>';
            title = 'Git Repository Initialized';
            details = `<div class="audit-detail-item">First commit: ${escapeHtml(entry.commit_hash)}</div>`;
            if (entry.message) {
                details += `<div class="audit-detail-item" class="audit-detail-muted">${escapeHtml(entry.message)}</div>`;
            }
            break;
        case 'git_restored':
            badge = '<span class="audit-badge restore">git restored</span>';
            icon = '<i class="fa-solid fa-clock-rotate-left"></i>';
            title = 'Restored to Git Commit';
            details = `<div class="audit-detail-item">Commit: ${escapeHtml(entry.commit_hash)}</div>`;
            if (entry.commit_message) {
                details += `<div class="audit-detail-item" class="audit-detail-muted">${escapeHtml(entry.commit_message)}</div>`;
            }
            if (entry.deleted_files_count > 0) {
                details += `<div class="audit-detail-item" style="color: var(--color-delete);">${entry.deleted_files_count} file${entry.deleted_files_count !== 1 ? 's' : ''} removed</div>`;
            }
            break;
        case 'git_commit':
            badge = '<span class="audit-badge git">git commit</span>';
            icon = '<i class="fa-solid fa-check"></i>';
            // Check if this was a commit after restore
            if (entry.restoreType === 'backup') {
                title = 'Committed Backup Restore';
                details = `<div class="audit-detail-item">Commit: ${escapeHtml(entry.commit_hash)}</div>`;
                details += `<div class="audit-detail-item">Restored from: ${escapeHtml(entry.restoreFrom)}</div>`;
            } else if (entry.restoreType === 'git') {
                title = 'Committed Git Restore';
                details = `<div class="audit-detail-item">Commit: ${escapeHtml(entry.commit_hash)}</div>`;
                details += `<div class="audit-detail-item">Restored from: ${escapeHtml(entry.restoreFrom)}</div>`;
            } else {
                title = 'Git Commit';
                details = `<div class="audit-detail-item">Commit: ${escapeHtml(entry.commit_hash)}</div>`;
            }
            if (entry.message) {
                details += `<div class="audit-detail-item" class="audit-detail-muted">${escapeHtml(entry.message)}</div>`;
            }
            break;
        case 'git_discarded':
            badge = '<span class="audit-badge git">discarded</span>';
            icon = '<i class="fa-solid fa-trash"></i>';
            title = 'Discarded Uncommitted Changes';
            details = `<div class="audit-detail-item">Reverted working directory to HEAD</div>`;
            break;
        case 'git_clear_history':
            badge = '<span class="audit-badge git">history cleared</span>';
            icon = '<i class="fa-solid fa-rotate"></i>';
            title = 'Cleared Git History';
            details = `<div class="audit-detail-item">${escapeHtml(entry.description || 'Repository reinitialized with fresh history')}</div>`;
            break;
        default:
            badge = `<span class="audit-badge">${escapeHtml(entry.action)}</span>`;
            icon = '<i class="fa-solid fa-clipboard-list"></i>';
            title = entry.action.replace(/_/g, ' ');
            break;
    }

    // User identity
    let userHtml = '';
    if (entry.userName || entry.userEmail) {
        const userName = entry.userName || 'Unknown';
        const userEmail = entry.userEmail ? ` (${entry.userEmail})` : '';
        userHtml = `<span class="audit-entry-user">${escapeHtml(userName)}${escapeHtml(userEmail)}</span>`;
    }

    // Determine entry type for color-coding
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

function renderAuditEntry(entry) {
    const time = new Date(entry.timestamp).toLocaleString();

    // Handle action-based entries (backups, git operations)
    if (entry.action) {
        return renderActionEntry(entry, time);
    }

    const attrCount = (entry.object_edits || []).length;
    const moveCount = (entry.object_moves || []).length;
    const createCount = (entry.object_creations || []).length;
    const folderCount = (entry.folder_creations || []).length;
    const relocCount = (entry.file_moves || []).length;
    const folderRelocCount = (entry.folder_moves || []).length;
    const objDeleteCount = (entry.object_deletions || []).length;
    const fileDeleteCount = (entry.file_deletions || []).length;
    const deleteCount = objDeleteCount + fileDeleteCount;
    const errorCount = (entry.errors || []).length;

    const badges = [
        generateBadge(createCount, 'creates', 'object created', 'objects created'),
        generateBadge(attrCount, 'attrs', 'attribute change', 'attribute changes'),
        generateBadge(moveCount, 'moves', 'object move', 'object moves'),
        generateBadge(folderCount, 'folders', 'folder created', 'folders created'),
        generateBadge(relocCount, 'relocs', 'file relocated', 'files relocated'),
        generateBadge(folderRelocCount, 'folder-relocs', 'folder relocated', 'folders relocated'),
        generateBadge(deleteCount, 'deletes', 'deletion', 'deletions'),
        generateBadge(errorCount, 'errors', 'error', 'errors')
    ].join('');

    let detailsHtml = '<div class="audit-entry-details">';

    // Attribute changes (object_edits)
    if (attrCount > 0) {
        detailsHtml += '<div class="audit-detail-section">';
        detailsHtml += '<div class="audit-detail-title">Attribute Changes</div>';
        entry.object_edits.forEach(change => {
            detailsHtml += `<div class="audit-detail-item">`;
            detailsHtml += `<div class="object-info"><span class="object-type type-${escapeHtml(change.object_type)}">${escapeHtml(change.object_type)}</span>${escapeHtml(change.object_name)}</div>`;
            if (change.changes && change.changes.length > 0) {
                change.changes.forEach(c => {
                    if (c.type === 'add') {
                        detailsHtml += `<div class="change-line change-add">+ ${escapeHtml(c.key)}: ${escapeHtml(c.value)}</div>`;
                    } else if (c.type === 'remove') {
                        detailsHtml += `<div class="change-line change-remove">- ${escapeHtml(c.key)}: ${escapeHtml(c.value)}</div>`;
                    } else {
                        detailsHtml += `<div class="change-line change-modify">~ ${escapeHtml(c.key)}: ${escapeHtml(c.from)} &rarr; ${escapeHtml(c.to)}</div>`;
                    }
                });
            }
            detailsHtml += '</div>';
        });
        detailsHtml += '</div>';
    }

    // Object moves between files (object_moves)
    if (moveCount > 0) {
        detailsHtml += '<div class="audit-detail-section">';
        detailsHtml += '<div class="audit-detail-title">Object Moves</div>';
        entry.object_moves.forEach(move => {
            detailsHtml += `<div class="audit-detail-item">`;
            detailsHtml += `<div class="object-info"><span class="object-type type-${escapeHtml(move.object_type)}">${escapeHtml(move.object_type)}</span>${escapeHtml(move.object_name)}</div>`;
            detailsHtml += `<div class="change-line change-modify">${escapeHtml(toDisplayPath(move.from_file))} &rarr; ${escapeHtml(toDisplayPath(move.to_file))}</div>`;
            detailsHtml += '</div>';
        });
        detailsHtml += '</div>';
    }

    // Object creations
    if (createCount > 0) {
        detailsHtml += '<div class="audit-detail-section">';
        detailsHtml += '<div class="audit-detail-title">Objects Created</div>';
        entry.object_creations.forEach(creation => {
            detailsHtml += `<div class="audit-detail-item">`;
            detailsHtml += `<div class="object-info"><span class="object-type type-${escapeHtml(creation.object_type)}">${escapeHtml(creation.object_type)}</span>${escapeHtml(creation.object_name)}</div>`;
            detailsHtml += `<div class="change-line change-add">+ Created in ${escapeHtml(toDisplayPath(creation.file))}</div>`;
            detailsHtml += '</div>';
        });
        detailsHtml += '</div>';
    }

    // Folder creations
    if (folderCount > 0) {
        detailsHtml += '<div class="audit-detail-section">';
        detailsHtml += '<div class="audit-detail-title">Folders Created</div>';
        entry.folder_creations.forEach(folder => {
            detailsHtml += `<div class="audit-detail-item">`;
            detailsHtml += `<div class="change-line change-add">+ ${escapeHtml(toDisplayPath(folder.path))}/</div>`;
            detailsHtml += '</div>';
        });
        detailsHtml += '</div>';
    }

    // File relocations (file_moves)
    if (relocCount > 0) {
        detailsHtml += '<div class="audit-detail-section">';
        detailsHtml += '<div class="audit-detail-title">Files Relocated</div>';
        entry.file_moves.forEach(reloc => {
            detailsHtml += `<div class="audit-detail-item">`;
            detailsHtml += `<div class="change-line change-modify">${escapeHtml(toDisplayPath(reloc.from))} &rarr; ${escapeHtml(toDisplayPath(reloc.to))}</div>`;
            detailsHtml += '</div>';
        });
        detailsHtml += '</div>';
    }

    // Folder relocations (folder_moves)
    if (folderRelocCount > 0) {
        detailsHtml += '<div class="audit-detail-section">';
        detailsHtml += '<div class="audit-detail-title">Folders Relocated</div>';
        entry.folder_moves.forEach(reloc => {
            detailsHtml += `<div class="audit-detail-item">`;
            detailsHtml += `<div class="change-line change-modify">${escapeHtml(toDisplayPath(reloc.from))} &rarr; ${escapeHtml(toDisplayPath(reloc.to))}</div>`;
            detailsHtml += '</div>';
        });
        detailsHtml += '</div>';
    }

    // Object deletions
    if (objDeleteCount > 0) {
        detailsHtml += '<div class="audit-detail-section">';
        detailsHtml += '<div class="audit-detail-title">Objects Deleted</div>';
        entry.object_deletions.forEach(deletion => {
            detailsHtml += `<div class="audit-detail-item">`;
            detailsHtml += `<div class="object-info"><span class="object-type type-${escapeHtml(deletion.object_type)}">${escapeHtml(deletion.object_type)}</span>${escapeHtml(deletion.object_name)}</div>`;
            detailsHtml += `<div class="change-line change-remove">- Deleted from ${escapeHtml(toDisplayPath(deletion.file))}</div>`;
            detailsHtml += '</div>';
        });
        detailsHtml += '</div>';
    }

    // File deletions
    if (fileDeleteCount > 0) {
        detailsHtml += '<div class="audit-detail-section">';
        detailsHtml += '<div class="audit-detail-title">Files/Folders Deleted</div>';
        entry.file_deletions.forEach(deletion => {
            detailsHtml += `<div class="audit-detail-item">`;
            if (deletion.type === 'folder') {
                detailsHtml += `<div class="change-line change-remove">- ${escapeHtml(toDisplayPath(deletion.path))}/ (folder)</div>`;
            } else {
                detailsHtml += `<div class="change-line change-remove">- ${escapeHtml(toDisplayPath(deletion.path))}</div>`;
            }
            detailsHtml += '</div>';
        });
        detailsHtml += '</div>';
    }

    detailsHtml += '</div>';

    // Errors
    let errorsHtml = '';
    if (errorCount > 0) {
        errorsHtml = '<div class="audit-entry-errors">';
        errorsHtml += '<strong>Errors:</strong><br>';
        errorsHtml += entry.errors.map(e => escapeHtml(e)).join('<br>');
        errorsHtml += '</div>';
    }

    // User identity
    let userHtml = '';
    if (entry.userName || entry.userEmail) {
        const userName = entry.userName || 'Unknown';
        const userEmail = entry.userEmail ? ` (${entry.userEmail})` : '';
        userHtml = `<span class="audit-entry-user">${escapeHtml(userName)}${escapeHtml(userEmail)}</span>`;
    }

    // Determine primary entry type for color-coding (in priority order)
    let entryType = '';
    if (deleteCount > 0) {entryType = 'deletes';}
    else if (createCount > 0) {entryType = 'creates';}
    else if (moveCount > 0 || relocCount > 0 || folderRelocCount > 0) {entryType = 'moves';}
    else if (attrCount > 0) {entryType = 'attrs';}

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
