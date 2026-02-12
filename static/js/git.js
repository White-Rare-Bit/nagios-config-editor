// Git page JavaScript
// Extracted from git.html

// Constants
const GIT_CONFIG = {
    HISTORY_PAGE_SIZE: 25,
    HISTORY_LIMIT: 100
};

// Helper to build consistent empty state HTML
function buildEmptyState(title, message, icon = 'fa-folder-open') {
    return `
        <div class="empty-state empty-state--dark empty-state--flex">
            <div class="empty-icon"><i class="fa-solid ${icon}"></i></div>
            <h3>${title}</h3>
            <p>${message}</p>
        </div>
    `;
}

let gitStatus = null;
let selectedGitFile = null;
let gitHistory = null;
let currentTab = 'changes';
let stagingInfo = null;

// History sort state
let historySortColumn = 'date';
let historySortDirection = 'desc';

// Pagination state
let historyCurrentPage = 1;
let historyPageSize = GIT_CONFIG.HISTORY_PAGE_SIZE;

async function loadGitStatus(forceRefresh = false) {
    const content = document.getElementById('gitContent');
    const repoStatus = document.getElementById('repoStatus');
    const branchDisplay = document.getElementById('branchDisplay');

    if (!forceRefresh && gitStatus !== null) {
        return;
    }

    content.innerHTML = '<div class="git-loading">Loading git status...</div>';

    const [statusResult, stagingResult] = await Promise.all([
        ApiClient.get('/api/git/status', { silent: true }),
        ApiClient.get('/api/staging/diff', { silent: true })
    ]);

    // Only show error if we have no data at all (network error)
    if (!statusResult.data) {
        console.error('Failed to load git status:', statusResult.error);
        content.innerHTML = buildEmptyState('Error', 'Failed to load git status', 'fa-exclamation-triangle');
        return;
    }

    const data = statusResult.data;
    stagingInfo = stagingResult.data || {};

    if (data.error && !data.is_repo) {
        branchDisplay.style.display = 'none';
        repoStatus.innerHTML = `
            <p class="sidebar-info-text" style="color: var(--nbe-warning, #e65100);">Not a git repository</p>
            <p class="sidebar-info-text">Make changes and use the Commit button in the navbar to initialize git.</p>
        `;
        content.innerHTML = buildEmptyState(
            'Not a Git Repository',
            'Use the Commit button in the navbar to initialize git<br>and create your first commit.'
        );
        updateChangesBadge(0);
        return;
    }

    if (data.error) {
        repoStatus.innerHTML = `<p class="sidebar-info-text" style="color: var(--color-delete);">${data.error}</p>`;
        content.innerHTML = buildEmptyState('Error', escapeHtml(data.error), 'fa-exclamation-triangle');
        return;
    }

    gitStatus = data;

    // Update sidebar
    branchDisplay.style.display = 'flex';
    document.getElementById('branchName').textContent = data.branch;

    if (data.has_changes) {
        repoStatus.innerHTML = `<p class="sidebar-info-text">${data.files.length} file${data.files.length !== 1 ? 's' : ''} with uncommitted changes</p>`;
    } else {
        repoStatus.innerHTML = `<p class="sidebar-info-text" style="color: var(--nbe-success, #4caf50);">Working directory clean</p>`;
    }

    updateChangesBadge(data.files.length);

    renderGitStatus();
}

/**
 * Builds HTML for the staging preview section showing pending staged changes.
 */
function buildStagingPreviewHtml(stagingInfo) {
    if (!stagingInfo || !stagingInfo.hasStagedChanges || !stagingInfo.stagedChanges) {
        return '';
    }
    const items = stagingInfo.stagedChanges.map(c => `<li>${escapeHtml(c.label)}</li>`).join('');
    return `
        <div class="git-staging-preview">
            <div class="git-staging-preview-header">
                <i class="fa-solid fa-layer-group"></i>
                <span>Pending Staged Changes</span>
                <span class="git-staging-preview-count">${stagingInfo.totalStagedCount}</span>
            </div>
            <ul class="git-staging-preview-list">${items}</ul>
            <div class="git-staging-preview-note">These changes have not been written to disk yet.</div>
            <button class="git-staging-preview-commit" data-action="commit">Review &amp; Commit</button>
        </div>
    `;
}

/**
 * Builds HTML for the git file list showing changed files.
 */
function buildGitFilesHtml(files, selectedPath) {
    if (!files || files.length === 0) {
        return '';
    }
    let html = '';
    for (const file of files) {
        const statusClass = file.status;
        const isSelected = selectedPath === file.path;
        const escapedPath = escapeHtml(file.path);
        html += `
            <li class="git-file-item ${isSelected ? 'selected' : ''}" data-filepath="${escapedPath}">
                <span class="git-status-badge ${statusClass}">${file.status_code}</span>
                <span class="git-file-path" title="${escapedPath}">${escapedPath}</span>
                <span class="git-file-actions">
                    <button class="git-file-action danger" data-action="discard-file" data-path="${escapedPath}">Discard</button>
                </span>
            </li>
        `;
    }
    return html;
}

/**
 * Renders the git status view with file changes and staging preview.
 */
function renderGitStatus() {
    const content = document.getElementById('gitContent');

    if (!gitStatus) {
        content.innerHTML = '<div class="git-loading">No git data</div>';
        return;
    }

    const hasStagedChanges = stagingInfo && stagingInfo.hasStagedChanges;

    // Clean state - no changes at all
    if (!gitStatus.has_changes && !hasStagedChanges) {
        content.innerHTML = `
            <div class="empty-state empty-state--dark empty-state--flex">
                <div class="empty-icon"><i class="fa-solid fa-circle-check"></i></div>
                <h3>Working Directory Clean</h3>
                <p>No uncommitted changes to your configuration files</p>
                <div class="empty-tips">
                    <div class="tip"><strong>Restore:</strong> Use the History tab to restore to a previous commit</div>
                    <div class="tip"><strong>Edit:</strong> Make changes in the Object Explorer to see them here</div>
                </div>
            </div>
        `;
        return;
    }

    const stagingPreviewHtml = buildStagingPreviewHtml(stagingInfo);
    const filesHtml = buildGitFilesHtml(gitStatus.files, selectedGitFile);

    // Only staged changes, no filesystem changes
    if (!gitStatus.has_changes && hasStagedChanges) {
        content.innerHTML = `
            <div style="flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px;">
                ${stagingPreviewHtml}
            </div>
        `;
        return;
    }

    // Mixed view with files and optional staging preview
    content.innerHTML = `
        ${stagingPreviewHtml ? `<div class="git-staging-preview-wrapper">${stagingPreviewHtml}</div>` : ''}
        <div class="git-files-panel">
            <div class="git-files-header">Files</div>
            <ul class="git-file-list">${filesHtml}</ul>
        </div>
        <div class="git-diff-panel">
            <div class="git-diff-header">
                <span class="git-diff-filename" id="diffFileName">Select a file to view diff</span>
            </div>
            <div class="git-diff-content" id="diffContent">
                <div class="git-diff-empty">Select a file to view changes</div>
            </div>
        </div>
    `;

    if (selectedGitFile) {
        showGitDiff(selectedGitFile);
    }
}

function selectGitFile(filepath) {
    selectedGitFile = filepath;
    document.querySelectorAll('.git-file-item').forEach(item => {
        const itemPath = item.querySelector('.git-file-path')?.title;
        item.classList.toggle('selected', itemPath === filepath);
    });
    showGitDiff(filepath);
}

async function showGitDiff(filepath) {
    const diffContent = document.getElementById('diffContent');
    const diffFileName = document.getElementById('diffFileName');

    if (!diffContent) return;

    diffFileName.textContent = filepath;
    diffContent.innerHTML = '<div class="git-diff-empty">Loading...</div>';

    const result = await ApiClient.post('/api/git/diff', { file: filepath }, { silent: true });

    if (!result.success || result.data?.error) {
        diffContent.innerHTML = `<div class="git-diff-empty">${result.data?.error || result.error || 'Failed to load diff'}</div>`;
        return;
    }

    if (!result.data.diff) {
        diffContent.innerHTML = '<div class="git-diff-empty">No changes to display</div>';
        return;
    }

    const lines = result.data.diff.split('\n');
    let diffHtml = '';
    for (const line of lines) {
        let lineClass = 'context';
        if (line.startsWith('+') && !line.startsWith('+++')) {
            lineClass = 'added';
        } else if (line.startsWith('-') && !line.startsWith('---')) {
            lineClass = 'removed';
        } else if (line.startsWith('@@')) {
            lineClass = 'hunk';
        } else if (line.startsWith('diff ') || line.startsWith('index ') || line.startsWith('---') || line.startsWith('+++')) {
            lineClass = 'header';
        }
        const escaped = escapeHtml(line);
        diffHtml += `<div class="git-diff-line ${lineClass}">${escaped || ' '}</div>`;
    }

    diffContent.innerHTML = diffHtml;
}

async function discardGitFile(filepath) {
    const confirmed = await showConfirmDialog({
        title: 'Discard Changes',
        message: `Discard changes to "${filepath}"? This cannot be undone.`,
        confirmText: 'Discard',
        type: 'danger'
    });

    if (!confirmed) return;

    // Show running panel immediately
    showGitRunningPanel('Discard File', `git checkout -- "${filepath}"`);

    const result = await ApiClient.post('/api/git/discard', { file: filepath }, { silent: true });

    // Show result panel
    const success = result.success && !result.data?.error;
    showGitDiscardFileResultPanel(filepath, success, result.data || { error: result.error });

    if (success) {
        selectedGitFile = null;
    }
}

function showGitDiscardFileResultPanel(filepath, success, result) {
    showResultPanel({
        command: `git checkout -- "${filepath}"`,
        success,
        title: success ? 'Discard Successful' : 'Discard Failed',
        outputHtml: success
            ? `<span class="success-text">Discarded changes to ${escapeHtml(filepath)}</span>`
            : `<span class="error-text">${result.error || 'Unknown error'}</span>`
    });
}

// Clear all git history
async function clearGitHistory() {
    const confirmed = await showConfirmDialog({
        title: 'Wipe Git Log',
        message: 'Remove all commits and create a fresh initial commit? This cannot be undone.',
        confirmText: 'Wipe Log',
        type: 'danger'
    });

    if (!confirmed) return;

    // Get identity from localStorage
    const identity = getUserIdentity();

    // Show running panel immediately with full command
    const fullCommand = `rm -rf .git && git init && git add -A && git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "Initial commit"`;
    showGitRunningPanel('Wipe Git Log', fullCommand);

    const result = await ApiClient.post('/api/git/clear-history', {
        user_name: identity.userName,
        user_email: identity.userEmail
    }, { silent: true });

    // Show result panel
    const success = result.success && !result.data?.error;
    showGitClearHistoryResultPanel(success, result.data || { error: result.error });

    if (success) {
        // Refresh the git page after panel is closed
        gitStatus = null;
        gitHistory = null;
    }
}

function showGitClearHistoryResultPanel(success, result) {
    const identity = getUserIdentity();
    showResultPanel({
        command: `rm -rf .git && git init && git add -A && git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "Initial commit"`,
        success,
        title: success ? 'Git Log Wiped' : 'Wipe Git Log Failed',
        outputHtml: success
            ? '<span class="success-text">Git history cleared and reinitialized with a fresh initial commit.</span>'
            : `<span class="error-text">${result.error || 'Unknown error'}</span>`
    });
}

// Tab switching
function switchGitTab(tab) {
    // Only allow 'changes' or 'history' tabs
    if (tab !== 'changes' && tab !== 'history') {
        tab = 'changes';
    }
    currentTab = tab;

    // Persist tab selection
    localStorage.setItem('gitPageTab', tab);

    // Update tab buttons
    document.getElementById('tabChanges').classList.toggle('active', tab === 'changes');
    document.getElementById('tabHistory').classList.toggle('active', tab === 'history');

    // Show/hide content
    document.getElementById('gitContent').style.display = tab === 'changes' ? 'flex' : 'none';
    document.getElementById('historyContent').style.display = tab === 'history' ? 'flex' : 'none';

    // Load data if needed
    if (tab === 'history' && gitHistory === null) {
        loadGitHistory();
    }
}

function refreshCurrentTab() {
    if (currentTab === 'changes') {
        loadGitStatus(true);
    } else {
        loadGitHistory(true);
    }
}

// History functions
async function loadGitHistory(forceRefresh = false) {
    const container = document.querySelector('.git-history-table-container');
    if (!container) return;

    if (!forceRefresh && gitHistory !== null) {
        return;
    }

    container.innerHTML = '<div class="git-loading">Loading history...</div>';

    const result = await ApiClient.get(`/api/git/log?limit=${GIT_CONFIG.HISTORY_LIMIT}`, { silent: true });

    // Only show error if we have no data at all (network error)
    if (!result.data) {
        console.error('Failed to load git history:', result.error);
        container.innerHTML = buildEmptyState('Error', 'Failed to load history', 'fa-circle-exclamation');
        return;
    }

    const data = result.data;

    if (!data.is_repo) {
        container.innerHTML = buildEmptyState('Not a Git Repository', 'Initialize git to start tracking history');
        return;
    }

    if (data.error) {
        container.innerHTML = buildEmptyState('Error', escapeHtml(data.error), 'fa-circle-exclamation');
        return;
    }

    gitHistory = data.commits;
    renderGitHistory();
}

function renderGitHistory() {
    const container = document.querySelector('.git-history-table-container');
    if (!container) return;

    if (!gitHistory || gitHistory.length === 0) {
        container.innerHTML = `
            <div class="empty-state empty-state--dark empty-state--flex">
                <div class="empty-icon"><i class="fa-solid fa-clock-rotate-left"></i></div>
                <h3>No Commits Yet</h3>
                <p>Make your first commit to start tracking history</p>
                <div class="empty-tips">
                    <div class="tip"><strong>Commit:</strong> Use the Commit button in the navbar to create commits</div>
                    <div class="tip"><strong>Restore:</strong> Roll back to any previous commit point</div>
                </div>
            </div>
        `;
        return;
    }

    // Calculate pagination
    const totalItems = gitHistory.length;
    const totalPages = Math.ceil(totalItems / historyPageSize);
    historyCurrentPage = Math.min(historyCurrentPage, totalPages);
    historyCurrentPage = Math.max(historyCurrentPage, 1);
    const startIdx = (historyCurrentPage - 1) * historyPageSize;
    const endIdx = Math.min(startIdx + historyPageSize, totalItems);
    const pageItems = gitHistory.slice(startIdx, endIdx);

    let html = `
        <table class="git-history-table" role="grid" aria-label="Commit history">
            <thead>
                <tr>
                    <th class="history-col-date sortable" data-sort="date" data-action="sort-history">
                        Date/Time <span class="sort-icon"></span>
                    </th>
                    <th class="history-col-hash">Commit</th>
                    <th class="history-col-message sortable" data-sort="message" data-action="sort-history">
                        Message <span class="sort-icon"></span>
                    </th>
                    <th class="history-col-author sortable" data-sort="author" data-action="sort-history">
                        Author <span class="sort-icon"></span>
                    </th>
                    <th class="history-col-actions">Actions</th>
                </tr>
            </thead>
            <tbody id="historyTableBody">
    `;

    for (const commit of pageItems) {
        const date = formatDate(commit.date);
        const escapedMessage = escapeHtml(commit.message);
        const isCurrent = commit.matches_working_dir;
        html += `
            <tr class="history-row${isCurrent ? ' is-current' : ''}" data-date="${commit.date}" data-message="${escapedMessage}" data-author="${escapeHtml(commit.author)}">
                <td class="history-cell-date">
                    <span class="history-date-value">${date}</span>
                </td>
                <td class="history-cell-hash">
                    <span class="history-hash-badge">${escapeHtml(commit.hash_short)}</span>
                    ${isCurrent ? '<span class="history-current-badge">Current</span>' : ''}
                </td>
                <td class="history-cell-message">
                    <span class="history-message-text">${escapedMessage}</span>
                </td>
                <td class="history-cell-author">
                    <span class="history-author-name">${escapeHtml(commit.author)}</span>
                </td>
                <td class="history-cell-actions">
                    ${isCurrent
                        ? '<span class="history-current-label">Current</span>'
                        : `<button class="nbe-btn nbe-btn--dark nbe-btn--sm" data-action="restore-commit" data-hash="${escapeHtml(commit.hash)}" data-message="${escapedMessage}">Restore</button>`
                    }
                </td>
            </tr>
        `;
    }

    html += '</tbody></table>';

    // Add pagination controls if more than one page
    const paginationHtml = renderHistoryPagination(totalItems);
    if (paginationHtml) {
        html += paginationHtml;
    }

    container.innerHTML = html;

    // Initialize sort indicators
    updateHistorySortIndicators();
}

function renderHistoryPagination(totalItems) {
    return renderPagination({
        currentPage: historyCurrentPage,
        totalItems,
        pageSize: historyPageSize,
        actionPrefix: 'history'
    });
}

function setHistoryPage(page) {
    historyCurrentPage = page;
    renderGitHistory();
}

function setHistoryPageSize(size) {
    historyPageSize = size;
    historyCurrentPage = 1;
    renderGitHistory();
}

function sortHistory(column) {
    if (!gitHistory || gitHistory.length === 0) return;

    // Toggle direction if same column, otherwise default to desc for date, asc for others
    if (column === historySortColumn) {
        historySortDirection = historySortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        historySortColumn = column;
        historySortDirection = column === 'date' ? 'desc' : 'asc';
    }

    // Sort the gitHistory array
    gitHistory.sort((a, b) => {
        let aVal, bVal;
        if (column === 'date') {
            aVal = a.date || '';
            bVal = b.date || '';
        } else if (column === 'message') {
            aVal = a.message || '';
            bVal = b.message || '';
        } else if (column === 'author') {
            aVal = a.author || '';
            bVal = b.author || '';
        } else {
            aVal = '';
            bVal = '';
        }

        const result = aVal.localeCompare(bVal);
        return historySortDirection === 'asc' ? result : -result;
    });

    // Reset to first page after sorting
    historyCurrentPage = 1;

    // Re-render
    renderGitHistory();
}

function updateHistorySortIndicators() {
    // Remove all sort classes
    document.querySelectorAll('.git-history-table th.sortable').forEach(th => {
        th.classList.remove('sort-active', 'sort-asc', 'sort-desc');
    });

    // Add to current sort column
    const activeHeader = document.querySelector(`.git-history-table th[data-sort="${historySortColumn}"]`);
    if (activeHeader) {
        activeHeader.classList.add('sort-active', `sort-${historySortDirection}`);
    }
}

// formatDate() is defined in app.js (loaded first) with relative time support

async function restoreCommit(hash, message) {
    const confirmed = await showConfirmDialog({
        title: 'Restore to Commit',
        message: `Restore to "${message}"? Current files will be overwritten and uncommitted changes will be stashed.`,
        confirmText: 'Restore',
        type: 'warning'
    });

    if (!confirmed) return;

    // Show running panel immediately
    showGitRunningPanel('Restore to Commit', `git checkout ${hash.substring(0, 7)} -- .`);

    const identity = getUserIdentity();
    const result = await ApiClient.post('/api/git/restore', {
        commit: hash,
        userName: identity.userName,
        userEmail: identity.userEmail
    }, { silent: true });

    // Show result panel (success or error)
    const success = result.success && !result.data?.error;
    showGitRestoreResultPanel(hash, success, result.data || { error: result.error });
}

function showGitRestoreResultPanel(hash, success, result) {
    // Build command string from actual operations
    let cmds = [];
    if (result.stashed) cmds.push('git stash push');
    cmds.push(`git checkout ${hash.substring(0, 7)} -- .`);
    if (result.deleted_files?.length > 0) cmds.push(`rm (${result.deleted_files.length} files)`);

    // Build output HTML
    let outputHtml;
    if (success) {
        outputHtml = `<span class="success-text">Restored to commit:</span> <span class="hash">${escapeHtml(hash.substring(0, 7))}</span>\n`;
        if (result.message) outputHtml += `<span style="color: #888;">Message:</span> ${escapeHtml(result.message)}\n`;
        if (result.stashed) outputHtml += `<span style="color: #ff9800;">Uncommitted changes were stashed</span>\n`;
        if (result.deleted_files?.length > 0) outputHtml += `<span style="color: #888;">Deleted ${result.deleted_files.length} file(s) not in target commit</span>\n`;
    } else {
        outputHtml = `<span class="error-text">${escapeHtml(result.error || 'Unknown error occurred')}</span>`;
    }

    showResultPanel({
        command: cmds.join(' && '),
        success,
        title: success ? 'Git Restore Successful' : 'Git Restore Failed',
        outputHtml
    });
}

// Update changes badge
function updateChangesBadge(count) {
    const badge = document.getElementById('changesBadge');
    if (badge) {
        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'inline';
        } else {
            badge.style.display = 'none';
        }
    }
}

// Load on page load
document.addEventListener('DOMContentLoaded', () => {
    // Restore saved tab selection
    const savedTab = localStorage.getItem('gitPageTab');
    if (savedTab && ['changes', 'history'].includes(savedTab)) {
        switchGitTab(savedTab);
    }

    // Always force refresh on page load to get latest data
    loadGitStatus(true);
    loadGitHistory(true);

    // Event delegation for select changes (pagination page size)
    document.addEventListener('change', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (actionEl) {
            const action = actionEl.dataset.action;
            if (action === 'history-page-size') {
                const size = parseInt(actionEl.value);
                if (size) setHistoryPageSize(size);
            }
        }
    });

    // Event delegation for git page actions
    document.addEventListener('click', function(e) {
        // Handle file item clicks (select file)
        const fileItem = e.target.closest('.git-file-item');
        if (fileItem && !e.target.closest('[data-action]')) {
            const filepath = fileItem.dataset.filepath;
            if (filepath) {
                selectGitFile(filepath);
            }
            return;
        }

        // Handle data-action elements
        const actionEl = e.target.closest('[data-action]');
        if (actionEl) {
            const action = actionEl.dataset.action;
            if (action === 'switchGitTab') {
                const tab = actionEl.dataset.tab;
                if (tab) switchGitTab(tab);
            } else if (action === 'discard-file') {
                e.stopPropagation();
                const path = actionEl.dataset.path;
                if (path) discardGitFile(path);
            } else if (action === 'commit') {
                handleCommitClick();
            } else if (action === 'restore-commit') {
                const hash = actionEl.dataset.hash;
                const message = actionEl.dataset.message;
                if (hash) restoreCommit(hash, message);
            } else if (action === 'clearGitHistory') {
                clearGitHistory();
            } else if (action === 'sort-history') {
                const column = actionEl.dataset.sort;
                if (column) sortHistory(column);
            } else if (action === 'history-page') {
                const page = parseInt(actionEl.dataset.page);
                if (page) setHistoryPage(page);
            }
        }
    });
});
