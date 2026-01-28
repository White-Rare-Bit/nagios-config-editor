// Git page JavaScript
// Extracted from git.html

let gitStatus = null;
let selectedGitFile = null;
let gitHistory = null;
let currentTab = 'changes';
let stagingInfo = null;

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
        content.innerHTML = '<div class="git-empty-state"><h3>Error</h3><p>Failed to load git status</p></div>';
        return;
    }

    const data = statusResult.data;
    stagingInfo = stagingResult.data || {};

    if (data.error && !data.is_repo) {
        branchDisplay.style.display = 'none';
        repoStatus.innerHTML = `
            <p class="sidebar-info-text" style="color: #e65100;">Not a git repository</p>
            <p class="sidebar-info-text">Make changes and use the Commit button in the navbar to initialize git.</p>
        `;
        content.innerHTML = `
            <div class="git-empty-state">
                <div class="icon">&#128193;</div>
                <h3>Not a Git Repository</h3>
                <p>Use the Commit button in the navbar to initialize git<br>and create your first commit.</p>
            </div>
        `;
        updateChangesBadge(0);
        return;
    }

    if (data.error) {
        repoStatus.innerHTML = `<p class="sidebar-info-text" style="color: var(--color-delete);">${data.error}</p>`;
        content.innerHTML = `<div class="git-empty-state"><h3>Error</h3><p>${data.error}</p></div>`;
        return;
    }

    gitStatus = data;

    // Update sidebar
    branchDisplay.style.display = 'flex';
    document.getElementById('branchName').textContent = data.branch;

    if (data.has_changes) {
        repoStatus.innerHTML = `<p class="sidebar-info-text">${data.files.length} file${data.files.length !== 1 ? 's' : ''} with uncommitted changes</p>`;
    } else {
        repoStatus.innerHTML = `<p class="sidebar-info-text" style="color: #4caf50;">Working directory clean</p>`;
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
        const jsPath = file.path.replace(/'/g, "\\'");
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
            <div class="git-clean-state">
                <div class="icon">&#10024;</div>
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
        const escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const title = document.getElementById('gitResultTitle');
    const command = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    baseState.gitResultNeedsReload = true;

    command.textContent = `git checkout -- "${filepath}"`;

    if (success) {
        icon.className = 'git-result-icon success';
        icon.innerHTML = '<i class="fa-solid fa-check"></i>';
        title.textContent = 'Discard Successful';
        output.className = 'git-result-output';
        output.innerHTML = `<span class="success-text">Discarded changes to ${escapeHtml(filepath)}</span>`;
    } else {
        icon.className = 'git-result-icon error';
        icon.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        title.textContent = 'Discard Failed';
        output.className = 'git-result-output';
        output.innerHTML = `<span class="error-text">${result.error || 'Unknown error'}</span>`;
    }

    overlay.classList.add('visible');
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
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const title = document.getElementById('gitResultTitle');
    const command = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    baseState.gitResultNeedsReload = true;

    // Show full command with identity
    const identity = getUserIdentity();
    command.textContent = `rm -rf .git && git init && git add -A && git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "Initial commit"`;

    if (success) {
        icon.className = 'git-result-icon success';
        icon.innerHTML = '<i class="fa-solid fa-check"></i>';
        title.textContent = 'Git Log Wiped';
        output.className = 'git-result-output';
        output.innerHTML = '<span class="success-text">Git history cleared and reinitialized with a fresh initial commit.</span>';
    } else {
        icon.className = 'git-result-icon error';
        icon.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        title.textContent = 'Wipe Git Log Failed';
        output.className = 'git-result-output';
        output.innerHTML = `<span class="error-text">${result.error || 'Unknown error'}</span>`;
    }

    overlay.classList.add('visible');
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
    const content = document.getElementById('historyContent');

    if (!forceRefresh && gitHistory !== null) {
        return;
    }

    content.innerHTML = '<div class="git-loading">Loading history...</div>';

    const result = await ApiClient.get('/api/git/log?limit=100', { silent: true });

    // Only show error if we have no data at all (network error)
    if (!result.data) {
        console.error('Failed to load git history:', result.error);
        content.innerHTML = '<div class="git-history-empty"><h3>Error</h3><p>Failed to load history</p></div>';
        return;
    }

    const data = result.data;

    if (!data.is_repo) {
        content.innerHTML = `
            <div class="git-history-empty">
                <div class="icon">&#128193;</div>
                <h3>Not a Git Repository</h3>
                <p>Initialize git to start tracking history</p>
            </div>
        `;
        return;
    }

    if (data.error) {
        content.innerHTML = `<div class="git-history-empty"><h3>Error</h3><p>${escapeHtml(data.error)}</p></div>`;
        return;
    }

    gitHistory = data.commits;
    renderGitHistory();
}

function renderGitHistory() {
    const content = document.getElementById('historyContent');

    if (!gitHistory || gitHistory.length === 0) {
        content.innerHTML = `
            <div class="git-history-empty">
                <div class="icon">&#128214;</div>
                <h3>No Commits Yet</h3>
                <p>Make your first commit to start tracking history</p>
            </div>
        `;
        return;
    }

    let html = '<ul class="git-history-list">';

    for (const commit of gitHistory) {
        const date = formatDate(commit.date);
        const escapedMessage = escapeHtml(commit.message);
        html += `
            <li class="git-commit-item${commit.matches_working_dir ? ' is-current' : ''}">
                <span class="git-commit-hash">${escapeHtml(commit.hash_short)}${commit.matches_working_dir ? '<span class="git-commit-current-badge">Current</span>' : ''}</span>
                <div class="git-commit-info">
                    <div class="git-commit-message">${escapedMessage}</div>
                    <div class="git-commit-meta">
                        <span>${escapeHtml(commit.author)}</span>
                        <span>${date}</span>
                    </div>
                </div>
                <div class="git-commit-actions">
                    <button class="git-restore-btn" ${commit.matches_working_dir ? 'disabled' : `data-action="restore-commit" data-hash="${escapeHtml(commit.hash)}" data-message="${escapedMessage}"`}>
                        ${commit.matches_working_dir ? 'Current' : 'Restore'}
                    </button>
                </div>
            </li>
        `;
    }

    html += '</ul>';
    content.innerHTML = html;
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

// Show git result panel for restore operations
function showGitRestoreResultPanel(hash, success, result) {
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const title = document.getElementById('gitResultTitle');
    const command = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    // Set flag to reload page when panel is closed
    baseState.gitResultNeedsReload = true;

    // Show the actual commands that were run
    let cmds = [];
    if (result.stashed) {
        cmds.push('git stash push');
    }
    cmds.push(`git checkout ${hash.substring(0, 7)} -- .`);
    if (result.deleted_files && result.deleted_files.length > 0) {
        cmds.push(`rm (${result.deleted_files.length} files)`);
    }
    command.textContent = cmds.join(' && ');

    if (success) {
        icon.className = 'git-result-icon success';
        icon.innerHTML = '<i class="fa-solid fa-check"></i>';
        title.textContent = 'Git Restore Successful';

        let outputHtml = `<span class="success-text">Restored to commit:</span> <span class="hash">${escapeHtml(hash.substring(0, 7))}</span>\n`;
        if (result.message) {
            outputHtml += `<span style="color: #888;">Message:</span> ${escapeHtml(result.message)}\n`;
        }
        if (result.stashed) {
            outputHtml += `<span style="color: #ff9800;">Uncommitted changes were stashed</span>\n`;
        }
        if (result.deleted_files && result.deleted_files.length > 0) {
            outputHtml += `<span style="color: #888;">Deleted ${result.deleted_files.length} file(s) not in target commit</span>\n`;
        }
        output.innerHTML = outputHtml;
    } else {
        icon.className = 'git-result-icon error';
        icon.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        title.textContent = 'Git Restore Failed';

        const errorMsg = result.error || 'Unknown error occurred';
        output.innerHTML = `<span class="error-text">${escapeHtml(errorMsg)}</span>`;
    }

    overlay.classList.add('visible');
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
            }
        }
    });
});
