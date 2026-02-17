/**
 * Logs page — unified audit + application log viewer.
 *
 * Tabs switch between audit and app logs. Each tab has its own column layout,
 * filter chips, and API endpoint. Audit tab groups rows by transaction ID.
 */

/* global ApiClient, showToast, showConfirmDialog, escapeHtml */

// ── State ──────────────────────────────────────────────────────────────────
let activeTab = 'audit';
let entries = [];
let offset = 0;
let searchQuery = '';
let activeFilters = new Set();

const PAGE_SIZE = 100;

// ── Tab config ─────────────────────────────────────────────────────────────
const TAB_CONFIG = {
    audit: {
        title: 'Audit Log',
        endpoint: '/api/logs/audit',
        downloadUrl: '/api/logs/audit/download',
        clearUrl: '/api/logs/audit/clear',
        columns: ['Timestamp', 'User', 'Action', 'Object', 'Details'],
        filters: [
            { key: 'apply', label: 'Apply' },
            { key: 'git_commit', label: 'Git' },
            { key: 'backup_created', label: 'Backup' },
            { key: 'apply_error', label: 'Errors' },
        ],
        filterParam: 'action',
        renderRow: renderAuditRow,
    },
    app: {
        title: 'Application Log',
        endpoint: '/api/logs/app',
        downloadUrl: '/api/logs/app/download',
        clearUrl: '/api/logs/app/clear',
        columns: ['Timestamp', 'Level', 'Source', 'Message'],
        filters: [
            { key: 'DEBUG', label: 'Debug' },
            { key: 'INFO', label: 'Info' },
            { key: 'WARNING', label: 'Warning' },
            { key: 'ERROR', label: 'Error' },
        ],
        filterParam: 'level',
        renderRow: renderAppRow,
    },
};

// ── Initialization ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initSearch();
    renderFilters();
    loadEntries();
});

function initTabs() {
    document.querySelectorAll('.logs-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            if (tabName === activeTab) {return;}
            switchTab(tabName);
        });
    });
}

function initSearch() {
    const input = document.getElementById('logsSearch');
    if (!input) {return;}
    let timeout;
    input.addEventListener('input', () => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            searchQuery = input.value.trim().toLowerCase();
            renderTable();
        }, 300);
    });
}

function switchTab(tabName) {
    activeTab = tabName;
    entries = [];
    offset = 0;
    searchQuery = '';
    activeFilters.clear();

    // Update tab buttons
    document.querySelectorAll('.logs-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tabName);
    });

    // Update title
    const titleEl = document.getElementById('logsTitle');
    if (titleEl) {titleEl.textContent = TAB_CONFIG[tabName].title;}

    // Clear search
    const input = document.getElementById('logsSearch');
    if (input) {input.value = '';}

    renderFilters();
    loadEntries();
}

// ── Filters ────────────────────────────────────────────────────────────────
function renderFilters() {
    const container = document.getElementById('logsFilters');
    if (!container) {return;}

    const config = TAB_CONFIG[activeTab];
    container.innerHTML = config.filters.map(f =>
        `<button class="logs-filter-chip" data-filter="${f.key}">${f.label}</button>`
    ).join('');

    container.querySelectorAll('.logs-filter-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const key = chip.dataset.filter;
            if (activeFilters.has(key)) {
                activeFilters.delete(key);
                chip.classList.remove('active');
            } else {
                activeFilters.add(key);
                chip.classList.add('active');
            }
            renderTable();
        });
    });
}

// ── Data loading ───────────────────────────────────────────────────────────
async function loadEntries(append) {
    const config = TAB_CONFIG[activeTab];
    const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(append ? offset : 0),
    });

    const result = await ApiClient.get(`${config.endpoint}?${params}`, { silent: true });
    if (!result.success) {
        showToast(result.error || 'Failed to load logs', 'error');
        return;
    }

    const data = result.data.data || result.data;
    const newEntries = data.entries || [];

    if (append) {
        entries = entries.concat(newEntries);
    } else {
        entries = newEntries;
        offset = 0;
    }
    offset = entries.length;

    renderTable();

    // Show/hide load more button
    const loadMore = document.getElementById('loadMoreBtn');
    if (loadMore) {
        loadMore.style.display = data.has_more ? '' : 'none';
    }
}

// ── Table rendering ────────────────────────────────────────────────────────
function renderTable() {
    const config = TAB_CONFIG[activeTab];
    renderTableHead(config.columns);

    let filtered = entries;

    // Apply filter chips
    if (activeFilters.size > 0) {
        const param = config.filterParam;
        filtered = filtered.filter(e => {
            const val = (e[param] || '').toLowerCase();
            for (const f of activeFilters) {
                if (val === f.toLowerCase()) {return true;}
                // Match action prefixes (e.g. "git_commit" matches "git_*")
                if (val.startsWith(f.toLowerCase())) {return true;}
            }
            return false;
        });
    }

    // Apply search
    if (searchQuery) {
        filtered = filtered.filter(e => {
            const text = JSON.stringify(e).toLowerCase();
            return text.includes(searchQuery);
        });
    }

    const tbody = document.getElementById('logsTableBody');
    const empty = document.getElementById('logsEmpty');
    const countEl = document.getElementById('logsCount');

    if (!filtered.length) {
        if (tbody) {tbody.innerHTML = '';}
        if (empty) {empty.style.display = '';}
        if (countEl) {countEl.textContent = '';}
        return;
    }

    if (empty) {empty.style.display = 'none';}
    if (countEl) {countEl.textContent = `(${filtered.length} entries)`;}

    if (!tbody) {return;}
    tbody.innerHTML = '';

    if (activeTab === 'audit') {
        renderAuditRows(tbody, filtered);
    } else {
        filtered.forEach(entry => {
            tbody.insertAdjacentHTML('beforeend', config.renderRow(entry));
        });
    }
}

function renderTableHead(columns) {
    const thead = document.getElementById('logsTableHead');
    if (!thead) {return;}
    thead.innerHTML = '<tr>' + columns.map(col => `<th>${col}</th>`).join('') + '</tr>';
}

// ── Audit row rendering with transaction grouping ──────────────────────────
function renderAuditRows(tbody, filtered) {
    let lastTxn = null;

    filtered.forEach(entry => {
        const txn = entry.txn || '';
        const isContinuation = txn && txn === lastTxn;
        const isGroupStart = txn && txn !== lastTxn;
        lastTxn = txn;

        const classes = [];
        if (isGroupStart || isContinuation) {classes.push('logs-txn-group');}
        if (isContinuation) {classes.push('logs-txn-continuation');}

        tbody.insertAdjacentHTML('beforeend', renderAuditRow(entry, classes));
    });
}

function renderAuditRow(entry, extraClasses) {
    const classes = (extraClasses || []).join(' ');
    const action = entry.action || '';
    const badgeClass = getActionBadgeClass(action);

    // Build object cell
    let objectCell = '';
    if (entry.type && entry.name) {
        objectCell = `<span class="logs-detail-field">${escapeHtml(entry.type)}</span> ${escapeHtml(entry.name)}`;
    } else if (entry.path) {
        objectCell = escapeHtml(entry.path);
    }

    // Build details cell
    let detailsCell = buildDetailsCell(entry);

    return `<tr class="${classes}">
        <td class="logs-col-timestamp">${escapeHtml(entry.timestamp || '')}</td>
        <td class="logs-col-user">${escapeHtml(entry.user || '')}</td>
        <td class="logs-col-action"><span class="logs-badge ${badgeClass}">${escapeHtml(action)}</span></td>
        <td class="logs-col-object">${objectCell}</td>
        <td class="logs-col-details">${detailsCell}</td>
    </tr>`;
}

function buildDetailsCell(entry) {
    const op = entry.op || '';

    if (op === 'modify' && entry.field) {
        const from = entry.from != null ? entry.from : '';
        const to = entry.to != null ? entry.to : '';
        return `<span class="logs-detail-field">${escapeHtml(entry.field)}</span>: `
            + `<span class="logs-detail-from">${escapeHtml(from)}</span>`
            + `<span class="logs-detail-arrow">&rarr;</span>`
            + `<span class="logs-detail-to">${escapeHtml(to)}</span>`;
    }

    if (op === 'move') {
        const from = entry.from || '';
        const to = entry.to || '';
        return `<span class="logs-detail-op">move</span> `
            + `<span class="logs-detail-from">${escapeHtml(from)}</span>`
            + `<span class="logs-detail-arrow">&rarr;</span>`
            + `<span class="logs-detail-to">${escapeHtml(to)}</span>`;
    }

    if (op) {
        return `<span class="logs-detail-op">${escapeHtml(op)}</span>`;
    }

    // Fallback: show any extra fields
    const skip = new Set(['timestamp', 'txn', 'user', 'action', 'type', 'name', 'op', 'field', 'from', 'to', 'path']);
    const extra = Object.entries(entry)
        .filter(([k]) => !skip.has(k))
        .map(([k, v]) => `${escapeHtml(k)}=${escapeHtml(String(v))}`)
        .join(' ');
    return extra ? `<span class="logs-detail-field">${extra}</span>` : '';
}

function getActionBadgeClass(action) {
    if (action.startsWith('apply')) {return 'logs-badge-apply';}
    if (action.startsWith('git')) {return 'logs-badge-git';}
    if (action.startsWith('backup')) {return 'logs-badge-backup';}
    if (action.includes('error')) {return 'logs-badge-error';}
    return '';
}

// ── App row rendering ──────────────────────────────────────────────────────
function renderAppRow(entry) {
    const level = (entry.level || '').toUpperCase();
    const badgeClass = getAppLevelBadgeClass(level);

    return `<tr>
        <td class="logs-col-timestamp">${escapeHtml(entry.timestamp || '')}</td>
        <td class="logs-col-level"><span class="logs-badge ${badgeClass}">${escapeHtml(level)}</span></td>
        <td class="logs-col-source">${escapeHtml(entry.source || '')}</td>
        <td class="logs-col-message">${escapeHtml(entry.message || '')}</td>
    </tr>`;
}

function getAppLevelBadgeClass(level) {
    switch (level) {
        case 'ERROR': return 'logs-badge-error';
        case 'WARNING': return 'logs-badge-warning';
        case 'INFO': return 'logs-badge-info';
        case 'DEBUG': return 'logs-badge-debug';
        default: return '';
    }
}

// ── Actions (event delegation) ─────────────────────────────────────────────
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) {return;}

    const action = actionEl.dataset.action;
    switch (action) {
        case 'downloadLog':
            downloadLog();
            break;
        case 'clearLog':
            clearLog();
            break;
        case 'loadMore':
            loadEntries(true);
            break;
    }
});

function downloadLog() {
    const config = TAB_CONFIG[activeTab];
    window.location.href = config.downloadUrl;
}

async function clearLog() {
    const config = TAB_CONFIG[activeTab];
    const confirmed = await showConfirmDialog({
        title: `Clear ${config.title}`,
        message: `Are you sure you want to clear the ${config.title.toLowerCase()}? This cannot be undone.`,
        confirmText: 'Clear',
        type: 'danger',
    });

    if (!confirmed) {return;}

    const result = await ApiClient.post(config.clearUrl);
    if (result.success) {
        entries = [];
        offset = 0;
        renderTable();
        showToast(`${config.title} cleared`, 'success');
    } else {
        showToast(result.error || 'Failed to clear log', 'error');
    }
}
