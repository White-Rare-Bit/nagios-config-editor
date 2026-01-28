// Audit Log page JavaScript
// Extracted from audit_log.html
// Note: configPath must be set before this script loads

let allEntries = [];
let activeFilters = new Set(['all']);
let currentArchive = 'current';
let searchQuery = '';

// Convert path to display path with config folder prefix
function toDisplayPath(path) {
    if (!path) return '';
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

    try {
        const response = await fetch('/api/audit-log');
        const data = await response.json();

        if (data.error) {
            container.innerHTML = `<div class="audit-empty">Error: ${escapeHtml(data.error)}</div>`;
            return;
        }

        allEntries = (data.entries || []).reverse();
        renderEntries();
    } catch (error) {
        container.innerHTML = `<div class="audit-empty">Error loading audit log: ${escapeHtml(error.message)}</div>`;
    }
}

function renderEntries() {
    const container = document.getElementById('auditLogContainer');
    const countEl = document.getElementById('entryCount');

    if (allEntries.length === 0) {
        countEl.textContent = '0 entries';
        container.innerHTML = `
            <div class="audit-empty">
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
            if (activeFilters.has('creates') && (entry.object_creations || []).length > 0) return true;
            if (activeFilters.has('attrs') && (entry.object_edits || []).length > 0) return true;
            if (activeFilters.has('moves') && ((entry.object_moves || []).length > 0 || (entry.file_moves || []).length > 0 || (entry.folder_moves || []).length > 0)) return true;
            if (activeFilters.has('deletes') && ((entry.object_deletions || []).length > 0 || (entry.file_deletions || []).length > 0)) return true;
            if (activeFilters.has('git') && entry.action && entry.action.startsWith('git_')) return true;
            if (activeFilters.has('backups') && entry.action && entry.action.startsWith('backup')) return true;
            return false;
        });
    }

    // Filter entries by search query
    if (searchQuery) {
        const query = searchQuery.toLowerCase();
        filteredEntries = filteredEntries.filter(entry => {
            // Search in timestamp
            const time = new Date(entry.timestamp).toLocaleString().toLowerCase();
            if (time.includes(query)) return true;

            // Search in user info
            if (entry.userName && entry.userName.toLowerCase().includes(query)) return true;
            if (entry.userEmail && entry.userEmail.toLowerCase().includes(query)) return true;

            // Search in action type
            if (entry.action && entry.action.toLowerCase().includes(query)) return true;

            // Search in object edits
            if (entry.object_edits) {
                for (const edit of entry.object_edits) {
                    if (edit.object_name && edit.object_name.toLowerCase().includes(query)) return true;
                    if (edit.object_type && edit.object_type.toLowerCase().includes(query)) return true;
                }
            }

            // Search in object moves
            if (entry.object_moves) {
                for (const move of entry.object_moves) {
                    if (move.object_name && move.object_name.toLowerCase().includes(query)) return true;
                    if (move.from_file && move.from_file.toLowerCase().includes(query)) return true;
                    if (move.to_file && move.to_file.toLowerCase().includes(query)) return true;
                }
            }

            // Search in object creations
            if (entry.object_creations) {
                for (const creation of entry.object_creations) {
                    if (creation.object_name && creation.object_name.toLowerCase().includes(query)) return true;
                    if (creation.file && creation.file.toLowerCase().includes(query)) return true;
                }
            }

            // Search in object deletions
            if (entry.object_deletions) {
                for (const deletion of entry.object_deletions) {
                    if (deletion.object_name && deletion.object_name.toLowerCase().includes(query)) return true;
                    if (deletion.file && deletion.file.toLowerCase().includes(query)) return true;
                }
            }

            // Search in file moves
            if (entry.file_moves) {
                for (const move of entry.file_moves) {
                    if (move.from && move.from.toLowerCase().includes(query)) return true;
                    if (move.to && move.to.toLowerCase().includes(query)) return true;
                }
            }

            // Search in file deletions
            if (entry.file_deletions) {
                for (const deletion of entry.file_deletions) {
                    if (deletion.path && deletion.path.toLowerCase().includes(query)) return true;
                }
            }

            // Search in git-related fields
            if (entry.commit_hash && entry.commit_hash.toLowerCase().includes(query)) return true;
            if (entry.message && entry.message.toLowerCase().includes(query)) return true;
            if (entry.backup_name && entry.backup_name.toLowerCase().includes(query)) return true;
            if (entry.description && entry.description.toLowerCase().includes(query)) return true;

            return false;
        });
    }

    countEl.textContent = `${filteredEntries.length} entr${filteredEntries.length === 1 ? 'y' : 'ies'}`;

    if (filteredEntries.length === 0) {
        const emptyMessage = searchQuery
            ? `No entries match "${escapeHtml(searchQuery)}". Try a different search term.`
            : 'No entries match the current filter. Try selecting different filters.';
        container.innerHTML = `
            <div class="audit-empty">
                <div class="empty-icon"><i class="fa-solid fa-magnifying-glass"></i></div>
                <h3>No matching entries</h3>
                <p>${emptyMessage}</p>
            </div>
        `;
        return;
    }

    container.innerHTML = filteredEntries.map(entry => renderAuditEntry(entry)).join('');
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
                details += `<div class="audit-detail-item" style="color: #666;">${escapeHtml(entry.message)}</div>`;
            }
            break;
        case 'git_restored':
            badge = '<span class="audit-badge restore">git restored</span>';
            icon = '<i class="fa-solid fa-clock-rotate-left"></i>';
            title = 'Restored to Git Commit';
            details = `<div class="audit-detail-item">Commit: ${escapeHtml(entry.commit_hash)}</div>`;
            if (entry.commit_message) {
                details += `<div class="audit-detail-item" style="color: #666;">${escapeHtml(entry.commit_message)}</div>`;
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
                details += `<div class="audit-detail-item" style="color: #666;">${escapeHtml(entry.message)}</div>`;
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

    let badges = '';
    if (createCount > 0) badges += `<span class="audit-badge creates">${createCount} object${createCount !== 1 ? 's' : ''} created</span>`;
    if (attrCount > 0) badges += `<span class="audit-badge attrs">${attrCount} attribute change${attrCount !== 1 ? 's' : ''}</span>`;
    if (moveCount > 0) badges += `<span class="audit-badge moves">${moveCount} object move${moveCount !== 1 ? 's' : ''}</span>`;
    if (folderCount > 0) badges += `<span class="audit-badge folders">${folderCount} folder${folderCount !== 1 ? 's' : ''} created</span>`;
    if (relocCount > 0) badges += `<span class="audit-badge relocs">${relocCount} file${relocCount !== 1 ? 's' : ''} relocated</span>`;
    if (folderRelocCount > 0) badges += `<span class="audit-badge folder-relocs">${folderRelocCount} folder${folderRelocCount !== 1 ? 's' : ''} relocated</span>`;
    if (deleteCount > 0) badges += `<span class="audit-badge deletes">${deleteCount} deletion${deleteCount !== 1 ? 's' : ''}</span>`;
    if (errorCount > 0) badges += `<span class="audit-badge errors">${errorCount} error${errorCount !== 1 ? 's' : ''}</span>`;

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
    if (deleteCount > 0) entryType = 'deletes';
    else if (createCount > 0) entryType = 'creates';
    else if (moveCount > 0 || relocCount > 0 || folderRelocCount > 0) entryType = 'moves';
    else if (attrCount > 0) entryType = 'attrs';

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
    try {
        const response = await fetch('/api/audit-log/clear', { method: 'POST' });
        const result = await response.json();

        if (result.error) {
            showToast('Error clearing log: ' + result.error, 'error');
        } else {
            showToast('Audit log cleared', 'success');
            refreshAuditLog();
        }
    } catch (error) {
        showToast('Error clearing log: ' + error.message, 'error');
    }
}

async function loadArchivesList() {
    const listEl = document.getElementById('archivesList');
    const loadingEl = document.getElementById('archivesLoading');

    loadingEl.style.display = 'block';

    try {
        const response = await fetch('/api/audit-log/archives');
        const data = await response.json();

        if (data.error) {
            console.error('Error loading archives:', data.error);
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

        (data.archives || []).forEach(archive => {
            // Parse date from filename: audit_log_YYYYMMDD_HHMMSS.json
            const match = archive.filename.match(/audit_log_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json/);
            let displayDate = archive.filename;
            if (match) {
                const date = new Date(match[1], match[2] - 1, match[3], match[4], match[5], match[6]);
                displayDate = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            }

            const sizeKB = (archive.size / 1024).toFixed(1);
            html += `
                <div class="archive-item ${currentArchive === archive.filename ? 'active' : ''}"
                     data-archive="${escapeHtml(archive.filename)}"
                     onclick="loadArchive('${escapeHtml(archive.filename)}')">
                    <span class="archive-name">${escapeHtml(displayDate)}</span>
                    <span class="archive-size">${sizeKB} KB</span>
                </div>
            `;
        });

        listEl.innerHTML = html;
        loadingEl.style.display = 'none';
    } catch (error) {
        console.error('Error loading archives:', error);
        loadingEl.style.display = 'none';
    }
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

    try {
        const response = await fetch(`/api/audit-log/archives/${encodeURIComponent(filename)}`);
        const data = await response.json();

        if (data.error) {
            container.innerHTML = `<div class="audit-empty">Error: ${escapeHtml(data.error)}</div>`;
            return;
        }

        allEntries = (data.entries || []).reverse();
        renderEntries();
    } catch (error) {
        container.innerHTML = `<div class="audit-empty">Error loading archive: ${escapeHtml(error.message)}</div>`;
    }
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
        const match = currentArchive.match(/audit_log_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json/);
        if (match) {
            const date = new Date(match[1], match[2] - 1, match[3], match[4], match[5], match[6]);
            titleEl.textContent = 'Archive: ' + date.toLocaleDateString();
        } else {
            titleEl.textContent = 'Archive: ' + currentArchive;
        }
    }
}

// Event delegation for data-action attributes
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

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
    }
});

document.addEventListener('change', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'filterByType') {
        filterByType(actionEl);
    }
});
