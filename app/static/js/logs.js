/**
 * Logs page — unified audit + application log viewer.
 *
 * Tabs switch between audit and app logs. Each tab has its own column layout,
 * filter chips, and API endpoint. Client-side pagination via shared
 * renderPagination component.
 */

import { ApiClient, apiUrl } from './api-client.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { escapeHtml } from './app.js';
import { renderPagination } from './shared/pagination.js';

// ── State ──────────────────────────────────────────────────────────────────
let activeTab = 'audit';
let entries = [];
let searchQuery = '';
let activeFilters = new Set();

// Pagination state
let logCurrentPage = 1;
let logPageSize = 25;

// ── Tab config ─────────────────────────────────────────────────────────────
const TAB_CONFIG = {
    audit: {
        title: 'Audit Log',
        endpoint: '/api/logs/audit',
        downloadUrl: '/api/logs/audit/download',
        clearUrl: '/api/logs/audit/clear',
        columns: ['Timestamp', 'User', 'Action', 'Object', 'Details'],
        filters: [
            { key: 'create', label: 'Creates', field: 'op', suffix: true },
            { key: 'modify', label: 'Edits', field: 'op' },
            { key: 'move', label: 'Moves', field: 'op', suffix: true },
            { key: 'delete', label: 'Deletes', field: 'op', suffix: true },
            { key: 'git', label: 'Git', field: 'action', prefix: true },
            { key: 'backup', label: 'Backups', field: 'action', prefix: true },
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
    initSearch();
    renderFilters();
    loadEntries();
});

function initSearch() {
    const input = document.getElementById('logsSearch');
    if (!input) {return;}
    let timeout;
    input.addEventListener('input', () => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            searchQuery = input.value.trim().toLowerCase();
            logCurrentPage = 1;
            renderTable();
        }, 300);
    });
}

function switchTab(tabName) {
    activeTab = tabName;
    entries = [];
    logCurrentPage = 1;
    searchQuery = '';
    activeFilters.clear();

    // Update header tabs
    document.querySelectorAll('.page-tab[data-tab]').forEach(t => {
        const isActive = t.dataset.tab === tabName;
        t.classList.toggle('active', isActive);
        t.setAttribute('aria-selected', isActive);
    });

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
            logCurrentPage = 1;
            renderTable();
        });
    });
}

// ── Data loading ───────────────────────────────────────────────────────────
async function loadEntries() {
    const config = TAB_CONFIG[activeTab];
    const params = new URLSearchParams({ limit: '10000' });

    const result = await ApiClient.get(`${config.endpoint}?${params}`, { silent: true });
    if (!result.success) {
        showToast(result.error || 'Failed to load logs', 'error');
        return;
    }

    const data = result.data.data || result.data;
    entries = data.entries || [];
    logCurrentPage = 1;
    renderTable();
}

// ── Table rendering ────────────────────────────────────────────────────────
function renderTable() {
    const config = TAB_CONFIG[activeTab];
    renderTableHead(config.columns);

    let filtered = entries;

    // Apply filter chips
    if (activeFilters.size > 0) {
        const filterDefs = config.filters.filter(f => activeFilters.has(f.key));
        filtered = filtered.filter(e => {
            for (const def of filterDefs) {
                const val = (e[def.field || config.filterParam] || '').toLowerCase();
                const key = def.key.toLowerCase();
                if (def.prefix) {
                    if (val.startsWith(key)) {return true;}
                } else if (def.suffix) {
                    if (val === key || val.endsWith('_' + key)) {return true;}
                } else if (val === key) {return true;}
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

    if (!filtered.length) {
        if (tbody) {tbody.innerHTML = '';}
        if (empty) {empty.style.display = '';}
        renderLogPagination(0);
        return;
    }

    if (empty) {empty.style.display = 'none';}

    // Paginate
    const totalItems = filtered.length;
    const totalPages = Math.ceil(totalItems / logPageSize);
    logCurrentPage = Math.min(logCurrentPage, Math.max(1, totalPages));
    const startIdx = (logCurrentPage - 1) * logPageSize;
    const endIdx = Math.min(startIdx + logPageSize, totalItems);
    const pageEntries = filtered.slice(startIdx, endIdx);

    if (!tbody) {return;}
    tbody.innerHTML = '';

    if (activeTab === 'audit') {
        renderAuditRows(tbody, pageEntries);
    } else {
        pageEntries.forEach(entry => {
            tbody.insertAdjacentHTML('beforeend', config.renderRow(entry));
        });
    }

    renderLogPagination(totalItems);
}

function renderLogPagination(totalItems) {
    const container = document.getElementById('logsPagination');
    if (!container) {return;}

    const existingPagination = container.querySelector('.nbe-pagination');
    if (existingPagination) {
        existingPagination.remove();
    }

    const paginationHtml = renderPagination({
        currentPage: logCurrentPage,
        totalItems,
        pageSize: logPageSize,
        actionPrefix: 'log',
    });

    if (paginationHtml) {
        container.insertAdjacentHTML('beforeend', paginationHtml);
    }
}

function renderTableHead(columns) {
    const thead = document.getElementById('logsTableHead');
    if (!thead) {return;}
    thead.innerHTML = '<tr>' + columns.map(col => `<th>${col}</th>`).join('') + '</tr>';
}

// ── Audit row rendering ─────────────────────────────────────────────────────
function renderAuditRows(tbody, pageEntries) {
    pageEntries.forEach(entry => {
        tbody.insertAdjacentHTML('beforeend', renderAuditRow(entry));
    });
}

function renderAuditRow(entry) {
    const action = entry.action || '';

    // Build object cell with type badge
    let objectCell = '';
    if (entry.type && entry.name) {
        const typeLower = entry.type.toLowerCase();
        objectCell = `<span class="logs-type-badge logs-type-badge--${typeLower}">${escapeHtml(entry.type.toUpperCase())}</span> ${escapeHtml(entry.name)}`;
    } else if (entry.path) {
        objectCell = escapeHtml(truncatePath(entry.path));
    }

    // Build details cell
    let detailsCell = buildDetailsCell(entry);

    const userCell = entry.user
        ? formatUserCell(entry.user)
        : '<span class="logs-empty-value">&mdash;</span>';

    return `<tr>
        <td class="logs-col-timestamp">${escapeHtml(entry.timestamp || '')}</td>
        <td class="logs-col-user">${userCell}</td>
        <td class="logs-col-action">${escapeHtml(action)}</td>
        <td class="logs-col-object">${objectCell}</td>
        <td class="logs-col-details">${detailsCell}</td>
    </tr>`;
}

function buildDetailsCell(entry) {
    const op = entry.op || '';

    // Field change (modify/add) with field name
    if ((op === 'modify' || op === 'add') && entry.field) {
        const from = entry.from != null ? entry.from : '';
        const to = entry.to != null ? entry.to : '';
        let html = `<span class="logs-detail-field">${escapeHtml(entry.field)}</span>: `;
        if (from) {
            html += `<span class="logs-detail-from">${escapeHtml(from)}</span>`
                + `<span class="logs-detail-arrow">&rarr;</span>`;
        }
        if (to) {
            html += `<span class="logs-detail-to">${escapeHtml(to)}</span>`;
        }
        return html;
    }

    // Move with from → to paths
    if (op === 'move') {
        const from = truncatePath(entry.from || '');
        const to = truncatePath(entry.to || '');
        return `<span class="logs-detail-op">move</span> `
            + `<span class="logs-detail-from">${escapeHtml(from)}</span>`
            + `<span class="logs-detail-arrow">&rarr;</span>`
            + `<span class="logs-detail-to">${escapeHtml(to)}</span>`;
    }

    // Other known op without field detail
    if (op) {
        return `<span class="logs-detail-op">${escapeHtml(op)}</span>`;
    }

    // Fallback: show extra fields as structured key: value pairs
    const skip = new Set(['timestamp', 'txn', 'user', 'action', 'type', 'name', 'op', 'field', 'from', 'to', 'path']);
    const pairs = Object.entries(entry)
        .filter(([k]) => !skip.has(k))
        .map(([k, v]) =>
            `<span class="logs-detail-field">${escapeHtml(k)}</span>: ${escapeHtml(truncatePath(String(v)))}`
        );
    return pairs.join('<span class="logs-detail-sep"> · </span>');
}

function truncatePath(str) {
    // Only truncate strings that look like absolute paths with 4+ segments
    if (!str.startsWith('/') || str.split('/').length < 5) {return str;}
    const parts = str.split('/');
    return parts.slice(-2).join('/');
}

function formatUserCell(user) {
    // Parse "Name <email>" format, fall back to plain display
    const match = user.match(/^(.+?)\s*<(.+)>$/);
    if (match) {
        return `${escapeHtml(match[1])} <span class="logs-user-email">${escapeHtml(match[2])}</span>`;
    }
    return escapeHtml(user);
}

// ── App row rendering ──────────────────────────────────────────────────────
function renderAppRow(entry) {
    const level = (entry.level || '').toUpperCase();

    return `<tr>
        <td class="logs-col-timestamp">${escapeHtml(entry.timestamp || '')}</td>
        <td class="logs-col-level">${escapeHtml(level)}</td>
        <td class="logs-col-source">${escapeHtml(entry.source || '')}</td>
        <td class="logs-col-message">${escapeHtml(entry.message || '')}</td>
    </tr>`;
}

// ── Actions (event delegation) ─────────────────────────────────────────────
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) {return;}

    const action = actionEl.dataset.action;
    switch (action) {
        case 'switchTab': {
            const tabName = actionEl.dataset.tab;
            if (tabName && tabName !== activeTab) {switchTab(tabName);}
            break;
        }
        case 'downloadLog':
            downloadLog();
            break;
        case 'clearLog':
            clearLog();
            break;
        case 'log-page': {
            const page = parseInt(actionEl.dataset.page, 10);
            if (page) {setLogPage(page);}
            break;
        }
    }
});

// Page size change (select element)
document.addEventListener('change', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (actionEl && actionEl.dataset.action === 'log-page-size') {
        const size = parseInt(actionEl.value, 10);
        if (size) {setLogPageSize(size);}
    }
});

function setLogPage(page) {
    logCurrentPage = page;
    renderTable();
}

function setLogPageSize(size) {
    logPageSize = size;
    logCurrentPage = 1;
    renderTable();
}

function downloadLog() {
    const config = TAB_CONFIG[activeTab];
    window.location.href = apiUrl(config.downloadUrl);
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
        logCurrentPage = 1;
        renderTable();
        showToast(`${config.title} cleared`, 'success');
    } else {
        showToast(result.error || 'Failed to clear log', 'error');
    }
}
