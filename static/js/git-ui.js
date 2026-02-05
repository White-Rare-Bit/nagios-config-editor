/**
 * Nagios Bulk Editor - Git UI Module
 *
 * Handles git operation result panel UI.
 * Shows running state, success/failure results.
 *
 * Dependencies (loaded before this file):
 * - base-state.js: baseState object
 * - app.js: escapeHtml
 */

// =============================================================================
// Git Result Panel
// =============================================================================

/**
 * Show the git result panel in "running" state.
 * @param {string} title - Panel title (e.g., "Git Commit")
 * @param {string} command - Command being executed
 */
function showGitRunningPanel(title, command) {
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const titleEl = document.getElementById('gitResultTitle');
    const commandEl = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    baseState.gitResultNeedsReload = false;

    icon.className = 'git-result-icon running';
    icon.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    titleEl.textContent = title;
    commandEl.textContent = command;
    output.className = 'git-result-output running';
    output.innerHTML = 'Running...';

    overlay.classList.add('visible');
}

/**
 * Show a simple git operation result (success or failure with message).
 * @param {string} title - Panel title
 * @param {string} command - Command that was executed
 * @param {boolean} success - Whether operation succeeded
 * @param {string} message - Result message to display
 */
function showGitOperationResult(title, command, success, message) {
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const titleEl = document.getElementById('gitResultTitle');
    const commandEl = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    baseState.gitResultNeedsReload = true;

    commandEl.textContent = command;

    if (success) {
        icon.className = 'git-result-icon success';
        icon.innerHTML = '<i class="fa-solid fa-check"></i>';
        titleEl.textContent = title;
        output.className = 'git-result-output';
        output.innerHTML = `<span class="success-text">${escapeHtml(message)}</span>`;
    } else {
        icon.className = 'git-result-icon error';
        icon.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        titleEl.textContent = title + ' Failed';
        output.className = 'git-result-output';
        output.innerHTML = `<span class="error-text">${escapeHtml(message)}</span>`;
    }

    overlay.classList.add('visible');
}

/**
 * Close the git result panel.
 * If the operation required reload, triggers page reload.
 */
function closeGitResultPanel() {
    const icon = document.getElementById('gitResultIcon');
    if (icon.classList.contains('running')) {
        return;
    }
    document.getElementById('gitResultOverlay').classList.remove('visible');
    if (baseState.gitResultNeedsReload) {
        baseState.gitResultNeedsReload = false;
        window.location.reload();
    }
}

/**
 * Close the git result overlay without reload check.
 * Used when we know we don't want to reload.
 */
function closeGitResultOverlay() {
    document.getElementById('gitResultOverlay').classList.remove('visible');
}

// Export to global scope for backward compatibility
window.showGitRunningPanel = showGitRunningPanel;
window.showGitOperationResult = showGitOperationResult;
window.closeGitResultPanel = closeGitResultPanel;
window.closeGitResultOverlay = closeGitResultOverlay;
