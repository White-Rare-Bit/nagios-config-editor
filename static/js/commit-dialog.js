/**
 * Nagios Bulk Editor - Commit Dialog Module
 */
import { baseState } from './base-state.js';
import { getUserIdentity, hasUserIdentity } from './session-manager.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { showGitRunningPanel, showGitOperationResult, closeGitResultOverlay } from './git-ui.js';
import { ApiClient } from './api-client.js';
import { escapeHtml } from './app.js';
import { pluralize, updateNavCommitButton, updateUndoButton } from './base.js'; // circular

export function handleCommitClick() {
    showGlobalCommitDialog();
}

export async function showGlobalCommitDialog() {
    const overlay = document.getElementById('globalCommitOverlay');
    const content = document.getElementById('globalCommitContent');

    overlay.classList.add('visible');
    content.innerHTML = '<div class="dialog-loading">Loading changes...</div>';

    const [shadowResult, gitResult] = await Promise.all([
        ApiClient.get('/api/staging/diff', { silent: true }),
        ApiClient.get('/api/git/status', { silent: true })
    ]);

    if (!shadowResult.success) {
        content.innerHTML = `<div class="commit-empty commit-error-text">Error loading changes: ${escapeHtml(shadowResult.error)}</div>`;
        return;
    }

    const shadowData = shadowResult.data?.data || shadowResult.data;
    const shadowFiles = (shadowData && shadowData.files) || [];
    const gitFiles = (gitResult.success && gitResult.data && gitResult.data.files) || [];
    const hasShadowChanges = shadowFiles.length > 0;
    const hasGitChanges = gitFiles.length > 0;

    if (!hasShadowChanges && !hasGitChanges) {
        content.innerHTML = '<div class="commit-empty">No pending changes.</div>';
        return;
    }

    const isGitConfigured = hasUserIdentity();

    // Store for context line updates
    baseState.diffData = { shadowFiles, gitFiles };

    if (!hasShadowChanges && hasGitChanges) {
        // Git-only changes (files modified outside the editor)
        content.innerHTML = await buildGitOnlyCommitDialogHtml(gitFiles, isGitConfigured);
    } else {
        content.innerHTML = await buildGlobalCommitDialogHtml(shadowFiles, gitFiles, isGitConfigured);
    }

    document.querySelectorAll('#globalCommitContent .commit-item-header').forEach(header => {
        header.addEventListener('click', () => {
            header.closest('.commit-item').classList.toggle('expanded');
        });
    });
}

/**
 * Build commit footer HTML with git identity and action buttons.
 */
function buildCommitFooterHtml(isGitConfigured) {
    let identityHtml;
    if (isGitConfigured) {
        identityHtml = `<textarea id="globalGitCommitMessage" class="commit-message-textarea" placeholder="Enter commit message..."></textarea>`;
    } else {
        identityHtml = `
            <div class="git-config-warning">
                <span class="git-config-warning-icon"><i class="fa-solid fa-triangle-exclamation"></i></span>
                <div>
                    <strong>Git identity not configured</strong><br>
                    <span class="git-config-warning-text">Configure your name and email in <a href="/settings">Settings</a> to enable commits.</span>
                </div>
            </div>`;
    }
    return `
        <div class="commit-footer">
            <div class="commit-footer-left">${identityHtml}</div>
            <div class="commit-footer-right">
                <button class="nbe-btn nbe-btn--dark nbe-btn--danger" onclick="discardGlobalChanges()">Discard All</button>
                <button class="nbe-btn nbe-btn--dark" onclick="closeGlobalCommitDialog()">Cancel</button>
                <button class="nbe-btn nbe-btn--dark nbe-btn--tonal" id="globalApplyBtn" onclick="applyGlobalCommit()" ${isGitConfigured ? '' : 'disabled'}>Apply Changes</button>
            </div>
        </div>`;
}

/**
 * Build summary stats HTML badges from shadow file changes.
 */
function buildSummaryStatsHtml(files) {
    let addedCount = 0, deletedCount = 0, modifiedCount = 0;
    for (const f of files) {
        if (f.status === 'added') {addedCount++;}
        else if (f.status === 'deleted') {deletedCount++;}
        else if (f.status === 'modified') {modifiedCount++;}
    }
    const badges = [];
    if (files.length > 0) {badges.push(`<div class="commit-stat edits"><span class="commit-stat-count">${files.length}</span> file${files.length !== 1 ? 's' : ''} changed</div>`);}
    if (addedCount > 0) {badges.push(`<div class="commit-stat creates"><span class="commit-stat-count">+${addedCount}</span> new</div>`);}
    if (deletedCount > 0) {badges.push(`<div class="commit-stat deletes"><span class="commit-stat-count">${deletedCount}</span> deleted</div>`);}
    if (modifiedCount > 0) {badges.push(`<div class="commit-stat edits"><span class="commit-stat-count">~${modifiedCount}</span> modified</div>`);}
    return badges.join('\n                ');
}

/**
 * Build external changes section HTML for files modified outside the editor.
 */
async function buildExternalChangesHtml(gitChanges, contextLines) {
    const externalDiffsHtml = await buildChangesFilesHtml(gitChanges, contextLines, { useExternalStyle: true });
    return `
        <div class="commit-section commit-external-section">
            <div class="commit-section-title">
                <i class="fa-solid fa-triangle-exclamation" style="color: var(--nbe-warning); margin-right: 6px;"></i>
                External Changes <span class="badge">${pluralize(gitChanges.length, 'file')}</span>
                <span class="commit-section-subtitle">(modified outside this editor)</span>
            </div>
            ${externalDiffsHtml}
        </div>`;
}

/**
 * Reset frontend state after discarding staging changes.
 */
async function resetFrontendAfterDiscard() {
    updateNavCommitButton(0);
    updateUndoButton(0);
    if (typeof Explorer !== 'undefined' && Explorer.resetStagingState) {
        Explorer.resetStagingState();
    }
    if (typeof Explorer !== 'undefined' && Explorer.loadObjects) {
        await Explorer.loadObjects();
    }
    if (typeof buildTree === 'function') {buildTree();}
    if (typeof renderTargetPane === 'function') {renderTargetPane();}
}

/**
 * Validate commit message input. Returns trimmed message or null if invalid.
 */
function validateCommitInput() {
    const input = document.getElementById('globalGitCommitMessage');
    const message = input ? input.value.trim() : '';
    if (!message) {
        showToast('Please enter a commit message', 'error');
        if (input) {input.focus();}
        return null;
    }
    return message;
}

/**
 * Apply shadow copy changes to original config. Returns apply result data on success.
 */
async function applyShadowChanges(force = false) {
    showGitRunningPanel('Applying Changes', 'Applying shadow copy to original config...');
    const url = force ? '/api/staging/apply?force=true' : '/api/staging/apply';
    const applyResult = await ApiClient.post(url, {}, { silent: true });
    if (!applyResult.success) {
        if (applyResult.data?.conflicts) {
            const conflicts = applyResult.data.conflicts;
            const fileList = conflicts.map(f => `  \u2022 ${f}`).join('\n');
            const msg = `${conflicts.length} file(s) were modified externally since you started editing:\n\n${fileList}\n\nForce apply will overwrite these changes. A backup is created first.`;
            if (confirm(msg)) {
                return applyShadowChanges(true);
            }
            showStagingResultPanel(false, 'Apply cancelled due to conflicts');
            return null;
        }
        showStagingResultPanel(false, applyResult.error || 'Failed to apply staged changes');
        return null;
    }
    return applyResult.data || {};
}

/**
 * Save expanded state of commit items, returning the set of expanded indices.
 */
function saveCommitItemExpansionState() {
    const expandedIndices = new Set();
    document.querySelectorAll('#globalCommitContent .commit-item.expanded').forEach((item, idx) => {
        expandedIndices.add(idx);
    });
    return expandedIndices;
}

/**
 * Restore expanded state and click handlers on commit items.
 */
function restoreCommitItemExpansionState(expandedIndices) {
    document.querySelectorAll('#globalCommitContent .commit-item').forEach((item, idx) => {
        if (expandedIndices.has(idx)) {
            item.classList.add('expanded');
        }
        const header = item.querySelector('.commit-item-header');
        if (header) {
            header.addEventListener('click', () => {
                item.classList.toggle('expanded');
            });
        }
    });
}

/**
 * Build the context range control HTML.
 */
function buildContextControlHtml(contextLines, inputHandler, valueId) {
    const sliderValue = contextLines > 9 ? 10 : contextLines;
    const displayValue = contextLines > 9 ? 'All' : contextLines;
    return `
        <div class="commit-context-control" title="Number of surrounding lines to show in diffs (drag to adjust)">
            <label>Context:</label>
            <input type="range" min="1" max="10" value="${sliderValue}" oninput="${inputHandler}(this.value)">
            <span id="${valueId}" class="context-value">${displayValue}</span>
        </div>`;
}

/**
 * Build the global commit dialog HTML with shadow diff data.
 * Renders file-level diffs from the shadow copy system.
 */
async function buildGlobalCommitDialogHtml(shadowFiles, gitFiles, isGitConfigured) {
    // Build shadow changes section
    const shadowFilesHtml = buildShadowFilesHtml(shadowFiles);

    // Filter external git changes to exclude files already in shadow diff
    const shadowPaths = new Set(shadowFiles.map(f => f.path));
    const externalOnlyChanges = gitFiles.filter(gc => !shadowPaths.has(gc.path));
    const hasExternalChanges = externalOnlyChanges.length > 0;
    const externalChangesHtml = hasExternalChanges
        ? await buildExternalChangesHtml(externalOnlyChanges, baseState.commitContextLines)
        : '';

    return `
        <div class="commit-header">
            <div class="commit-summary">
                ${buildSummaryStatsHtml(shadowFiles)}
                ${hasExternalChanges ? `<div class="commit-stat external"><span class="commit-stat-count">${externalOnlyChanges.length}</span> external</div>` : ''}
            </div>
            ${buildContextControlHtml(baseState.commitContextLines, 'updateGlobalContextLines', 'globalContextLinesValue')}
        </div>
        <div class="commit-changes-list" id="globalCommitChangesList">
            <div class="commit-section">
                <div class="commit-section-title">File Changes <span class="badge">${shadowFiles.length} file${shadowFiles.length !== 1 ? 's' : ''}</span></div>
                ${shadowFilesHtml}
            </div>
            ${externalChangesHtml}
        </div>
        ${buildCommitFooterHtml(isGitConfigured)}`;
}

/**
 * Build HTML for shadow diff files. Each file has a pre-computed diff from the server.
 */
function buildShadowFilesHtml(shadowFiles) {
    const statusLabels = {
        'modified': 'Modified',
        'added': 'Added',
        'deleted': 'Deleted'
    };

    let html = '';
    for (const file of shadowFiles) {
        const statusLabel = statusLabels[file.status] || file.status;
        let typeClass;
        if (file.status === 'added') {
            typeClass = 'create';
        } else if (file.status === 'deleted') {
            typeClass = 'delete';
        } else {
            typeClass = '';
        }

        const fileName = file.path.split('/').pop();
        const diffText = (file.diff && file.diff.diff_text) || '';
        const diffContent = renderDiffText(diffText);

        html += `
            <div class="commit-item expanded">
                <div class="commit-item-header">
                    <span class="commit-item-expand">&#9658;</span>
                    <span class="commit-item-type ${typeClass}">${statusLabel}</span>
                    <span class="commit-item-name">${escapeHtml(fileName)}</span>
                    <span class="commit-item-file">${escapeHtml(file.path)}</span>
                </div>
                <div class="commit-item-diff">
                    <div class="diff-content">${diffContent || '<div class="diff-line context">No changes to display</div>'}</div>
                </div>
            </div>
        `;
    }
    return html;
}

/**
 * Render unified diff text into styled HTML lines.
 */
function renderDiffText(diffText) {
    if (!diffText) {return '';}
    return diffText.split('\n').filter(line => line !== '').map(line => {
        let lineClass;
        if (line.startsWith('+') && !line.startsWith('+++')) {
            lineClass = 'add';
        } else if (line.startsWith('-') && !line.startsWith('---')) {
            lineClass = 'remove';
        } else if (line.startsWith('@@')) {
            lineClass = 'hunk';
        } else {
            lineClass = 'context';
        }
        return `<div class="diff-line ${lineClass}">${escapeHtml(line)}</div>`;
    }).join('');
}

async function buildGitOnlyCommitDialogHtml(gitChanges, isGitConfigured) {
    baseState.gitOnlyChanges = gitChanges;

    const filesHtml = await buildChangesFilesHtml(gitChanges, baseState.gitOnlyContextLines, { expandedByDefault: true });

    // Count by status
    let modifiedCount = 0, addedCount = 0, deletedCount = 0;
    for (const change of gitChanges) {
        if (change.status === 'modified') {modifiedCount++;}
        else if (change.status === 'added' || change.status === 'untracked') {addedCount++;}
        else if (change.status === 'deleted') {deletedCount++;}
    }

    return `
        <div class="commit-header">
            <div class="commit-summary">
                ${gitChanges.length > 0 ? `<div class="commit-stat edits"><span class="commit-stat-count">${gitChanges.length}</span> file${gitChanges.length !== 1 ? 's' : ''} changed</div>` : ''}
                ${addedCount > 0 ? `<div class="commit-stat creates"><span class="commit-stat-count">+${addedCount}</span> new</div>` : ''}
                ${deletedCount > 0 ? `<div class="commit-stat deletes"><span class="commit-stat-count">${deletedCount}</span> deleted</div>` : ''}
                ${modifiedCount > 0 ? `<div class="commit-stat edits"><span class="commit-stat-count">~${modifiedCount}</span> modified</div>` : ''}
            </div>
            <div class="commit-context-control" title="Number of surrounding lines to show in diffs (drag to adjust)">
                <label>Context:</label>
                <input type="range" min="1" max="10" value="${baseState.gitOnlyContextLines > 9 ? 10 : baseState.gitOnlyContextLines}" oninput="updateGitOnlyContextLines(this.value)">
                <span id="gitOnlyContextLinesValue" class="context-value">${baseState.gitOnlyContextLines > 9 ? 'All' : baseState.gitOnlyContextLines}</span>
            </div>
        </div>
        <div class="commit-changes-list" id="globalCommitChangesList">
            <div class="commit-section">
                <div class="commit-section-title">File Changes <span class="badge">${gitChanges.length} file${gitChanges.length !== 1 ? 's' : ''}</span></div>
                ${filesHtml}
            </div>
        </div>
        <div class="commit-footer">
            <div class="commit-footer-left">
                ${isGitConfigured ? `
                <textarea id="globalGitCommitMessage" class="commit-message-textarea" placeholder="Enter commit message..."></textarea>
                ` : `
                <div class="git-config-warning">
                    <span class="git-config-warning-icon"><i class="fa-solid fa-triangle-exclamation"></i></span>
                    <div>
                        <strong>Git identity not configured</strong><br>
                        <span class="git-config-warning-text">Configure your name and email in <a href="/settings">Settings</a> to enable commits.</span>
                    </div>
                </div>
                `}
            </div>
            <div class="commit-footer-right">
                <button class="nbe-btn nbe-btn--dark nbe-btn--danger" onclick="discardGitChanges()">Discard All</button>
                <button class="nbe-btn nbe-btn--dark" onclick="closeGlobalCommitDialog()">Cancel</button>
                <button class="nbe-btn nbe-btn--dark nbe-btn--tonal" id="globalApplyBtn" onclick="applyGitCommit()" ${isGitConfigured ? '' : 'disabled'}>Apply Changes</button>
            </div>
        </div>
    `;
}

/**
 * Build HTML for git file changes (used by git-only and external changes views).
 * If a change object has a `diff` property with `diff_text`, uses that instead of fetching.
 * @param {Array} gitChanges - Array of git change objects with path and status
 * @param {number} contextLines - Number of context lines for diffs
 * @param {Object} options - Display options
 * @param {boolean} [options.expandedByDefault=false] - Whether items start expanded
 * @param {boolean} [options.useExternalStyle=false] - Use 'external' class for modified files
 * @returns {Promise<string>} HTML string for file changes
 */
async function buildChangesFilesHtml(gitChanges, contextLines, options = {}) {
    const { expandedByDefault = false, useExternalStyle = false } = options;

    const statusLabels = {
        'modified': 'Modified',
        'added': 'Added',
        'deleted': 'Deleted',
        'untracked': 'Untracked',
        'renamed': 'Renamed'
    };

    let filesHtml = '';
    for (const change of gitChanges) {
        const statusClass = change.status;
        const statusLabel = statusLabels[change.status] || change.status;
        let typeClass;
        if (statusClass === 'modified') {
            typeClass = useExternalStyle ? 'external' : '';
        } else if (statusClass === 'added' || statusClass === 'untracked') {
            typeClass = 'create';
        } else if (statusClass === 'deleted') {
            typeClass = 'delete';
        } else {
            typeClass = 'move';
        }

        let diffContent = '';
        if (change.diff && change.diff.diff_text) {
            // Use pre-computed diff from shadow copy
            diffContent = renderDiffText(change.diff.diff_text);
        } else {
            // Fetch diff from git
            const useFullFile = contextLines > 9;
            const diffResult = await ApiClient.post('/api/git/diff', {
                file: change.path,
                fullFile: useFullFile,
                contextLines: useFullFile ? null : contextLines
            }, { silent: true });

            if (diffResult.success && diffResult.data?.diff) {
                diffContent = renderDiffText(diffResult.data.diff);
            } else {
                diffContent = '<div class="diff-line context">Unable to load diff</div>';
            }
        }

        const expandedClass = expandedByDefault ? ' expanded' : '';
        filesHtml += `
            <div class="commit-item${expandedClass}">
                <div class="commit-item-header">
                    <span class="commit-item-expand">&#9658;</span>
                    <span class="commit-item-type ${typeClass}">${statusLabel}</span>
                    <span class="commit-item-name">${escapeHtml(change.path.split('/').pop())}</span>
                    <span class="commit-item-file">${escapeHtml(change.path)}</span>
                </div>
                <div class="commit-item-diff">
                    <div class="diff-content">${diffContent || '<div class="diff-line context">No changes to display</div>'}</div>
                </div>
            </div>
        `;
    }
    return filesHtml;
}

export async function updateGitOnlyContextLines(value) {
    const intValue = parseInt(value, 10);
    baseState.gitOnlyContextLines = intValue === 10 ? 9999 : intValue;
    document.getElementById('gitOnlyContextLinesValue').textContent = intValue === 10 ? 'All' : value;

    if (!baseState.gitOnlyChanges) {return;}

    const changesList = document.getElementById('globalCommitChangesList');
    if (!changesList) {return;}

    const filesHtml = await buildChangesFilesHtml(baseState.gitOnlyChanges, baseState.gitOnlyContextLines, { expandedByDefault: true });
    changesList.innerHTML = `
        <div class="commit-section">
            <div class="commit-section-title">File Changes <span class="badge">${pluralize(baseState.gitOnlyChanges.length, 'file')}</span></div>
            ${filesHtml}
        </div>
    `;

    changesList.querySelectorAll('.commit-item-header').forEach(header => {
        header.addEventListener('click', () => {
            header.closest('.commit-item').classList.toggle('expanded');
        });
    });
}

export async function discardGitChanges() {
    closeGlobalCommitDialog();
    showGitRunningPanel('Discard All Changes', 'git checkout -- . && git clean -fd');

    const identity = getUserIdentity();
    const result = await ApiClient.post('/api/git/discard-all', {
        userName: identity.userName,
        userEmail: identity.userEmail
    }, { silent: true });

    if (result.success && result.data?.success) {
        updateNavCommitButton(0);
    }
    showGitDiscardResultPanel(result.success && result.data?.success, result.data || { error: result.error });
}

export function showResultPanel({ command, success, title, outputHtml, needsReload = true, showRetryCommit = false }) {
    const overlay = document.getElementById('gitResultOverlay');
    const icon = document.getElementById('gitResultIcon');
    const titleEl = document.getElementById('gitResultTitle');
    const commandEl = document.getElementById('gitResultCommand');
    const output = document.getElementById('gitResultOutput');

    baseState.gitResultNeedsReload = needsReload;

    icon.className = success ? 'git-result-icon success' : 'git-result-icon error';
    icon.innerHTML = success ? '<i class="fa-solid fa-check"></i>' : '<i class="fa-solid fa-xmark"></i>';
    titleEl.textContent = title;
    commandEl.textContent = command;
    output.className = 'git-result-output';

    let retryButtonHtml = '';
    if (showRetryCommit) {
        retryButtonHtml = `
            <div class="git-retry-section">
                <button class="nbe-btn nbe-btn--dark nbe-btn--tonal" onclick="retryGitCommit()">
                    <i class="fa-solid fa-redo"></i> Retry Commit
                </button>
                <button class="nbe-btn nbe-btn--dark" onclick="discardStagingAfterFailedCommit()">
                    Revert Changes
                </button>
            </div>
        `;
    }
    output.innerHTML = outputHtml + retryButtonHtml;

    overlay.classList.add('visible');
}

/**
 * Retry git commit after a failed attempt.
 * Changes are on disk (shadow destroyed after apply), just need git commit.
 */
export async function retryGitCommit() {
    const message = baseState.pendingCommitMessage;
    if (!message) {
        showToast('No pending commit message found', 'error');
        return;
    }

    const overlay = document.getElementById('gitResultOverlay');
    overlay.classList.remove('visible');

    await autoGitCommitGlobal(message, true);
}

/**
 * Revert changes after a failed commit.
 * After apply, shadow is destroyed — files are on disk. Revert via git.
 */
export async function discardStagingAfterFailedCommit() {
    const confirmed = await showConfirmDialog({
        title: 'Revert Changes?',
        message: 'Your changes have been written to disk but not committed to git. This will revert all files to their last committed state via git.',
        confirmText: 'Revert Changes',
        type: 'warning'
    });

    if (confirmed) {
        await ApiClient.del('/api/staging', { silent: true });
        const revertResult = await ApiClient.post('/api/git/discard-all');
        baseState.pendingCommitMessage = null;
        closeGitResultOverlay();
        if (!revertResult.success) {
            showToast('Warning: could not revert files via git', 'warning');
        } else {
            showToast('Changes reverted', 'info');
        }
    }
}

function showGitDiscardResultPanel(success, result) {
    const command = (result.commands && result.commands.length > 0)
        ? result.commands.map(c => c.command).join(' && ')
        : 'git discard';

    let outputHtml = '';
    if (success) {
        outputHtml = '<span class="success-text">All uncommitted changes discarded</span>\n\n';
        if (result.commands && result.commands.length > 0) {
            result.commands.forEach(cmd => {
                outputHtml += `<span class="terminal-command">$ ${escapeHtml(cmd.command)}</span>\n`;
                if (cmd.output && cmd.output.trim()) {
                    outputHtml += escapeHtml(cmd.output.trim()) + '\n';
                }
            });
        }
    } else {
        if (result.commands && result.commands.length > 0) {
            result.commands.forEach(cmd => {
                const statusClass = cmd.success ? 'terminal-command-success' : 'terminal-command-error';
                outputHtml += `<span class="${statusClass}">$ ${escapeHtml(cmd.command)}</span>\n`;
                if (cmd.output && cmd.output.trim()) {
                    outputHtml += escapeHtml(cmd.output.trim()) + '\n';
                }
            });
        }
        if (result.error) {
            outputHtml += `\n<span class="error-text">${escapeHtml(result.error)}</span>`;
        }
        outputHtml = outputHtml || '<span class="error-text">Unknown error occurred</span>';
    }

    showResultPanel({
        command,
        success,
        title: success ? 'Discard Successful' : 'Discard Failed',
        outputHtml
    });
}

export async function applyGitCommit() {
    const messageInput = document.getElementById('globalGitCommitMessage');
    const message = messageInput?.value?.trim();

    if (!message) {
        showToast('Please enter a commit message', 'error');
        messageInput?.focus();
        return;
    }

    closeGlobalCommitDialog();

    const identity = getUserIdentity();
    const displayMessage = message.length > 60 ? message.substring(0, 60) + '...' : message;
    const fullCommand = `git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "${displayMessage}"`;
    showGitRunningPanel('Git Commit', fullCommand);

    const result = await ApiClient.post('/api/git/commit', {
        message,
        user_name: identity.userName,
        user_email: identity.userEmail
    }, { silent: true });

    if (result.success && result.data?.success) {
        updateNavCommitButton(0);
    }
    showGitResultPanel(message, result.success && result.data?.success, result.data || { error: result.error });
}

/**
 * Re-fetch shadow diff with updated context lines and re-render the changes list.
 */
export async function updateGlobalContextLines(value) {
    const intValue = parseInt(value, 10);
    baseState.commitContextLines = intValue === 10 ? 9999 : intValue;
    document.getElementById('globalContextLinesValue').textContent = intValue === 10 ? 'All' : value;

    if (!baseState.diffData || !baseState.diffData.shadowFiles) {return;}

    const expandedIndices = saveCommitItemExpansionState();

    // Re-fetch shadow diff with new context lines
    const contextParam = intValue === 10 ? 9999 : intValue;
    const shadowResult = await ApiClient.get(`/api/staging/diff?context_lines=${contextParam}`, { silent: true });
    if (!shadowResult.success) {return;}

    const shadowData2 = shadowResult.data?.data || shadowResult.data;
    const shadowFiles = (shadowData2 && shadowData2.files) || [];
    baseState.diffData.shadowFiles = shadowFiles;

    const changesList = document.getElementById('globalCommitChangesList');
    if (!changesList) {return;}

    // Rebuild shadow files section
    const shadowFilesHtml = buildShadowFilesHtml(shadowFiles);

    // Rebuild external changes if present
    const gitFiles = baseState.diffData.gitFiles || [];
    const shadowPaths = new Set(shadowFiles.map(f => f.path));
    const externalOnlyChanges = gitFiles.filter(gc => !shadowPaths.has(gc.path));
    const hasExternalChanges = externalOnlyChanges.length > 0;
    const externalChangesHtml = hasExternalChanges
        ? await buildExternalChangesHtml(externalOnlyChanges, baseState.commitContextLines)
        : '';

    changesList.innerHTML = `
        <div class="commit-section">
            <div class="commit-section-title">File Changes <span class="badge">${shadowFiles.length} file${shadowFiles.length !== 1 ? 's' : ''}</span></div>
            ${shadowFilesHtml}
        </div>
        ${externalChangesHtml}
    `;

    restoreCommitItemExpansionState(expandedIndices);
}

export function closeGlobalCommitDialog() {
    document.getElementById('globalCommitOverlay').classList.remove('visible');
    baseState.pendingCommitMessage = null;
}

export async function discardGlobalChanges() {
    closeGlobalCommitDialog();
    showGitRunningPanel('Discard Changes', 'Clearing staged changes...');

    const result = await ApiClient.del('/api/staging', { silent: true });

    if (result.success) {
        await resetFrontendAfterDiscard();
    }
    showStagingDiscardResultPanel(result.success, result.error);
}

function showStagingDiscardResultPanel(success, errorMsg = null) {
    const command = 'Clear staging data';

    let outputHtml = '';
    if (success) {
        outputHtml = '<span class="success-text">All staged changes discarded.</span>\n';
    } else {
        outputHtml = `<span class="error-text">${escapeHtml(errorMsg || 'Unknown error occurred')}</span>`;
    }

    showResultPanel({
        command,
        success,
        title: success ? 'Discard Successful' : 'Discard Failed',
        outputHtml
    });
}

/**
 * Apply shadow changes then git commit.
 * Always applies shadow first (shadow copy system handles all change types).
 */
export async function applyGlobalCommit() {
    const commitMessage = validateCommitInput();
    if (!commitMessage) {return;}

    closeGlobalCommitDialog();

    // Apply shadow copy to original config
    const applyData = await applyShadowChanges();
    if (!applyData) {return;}

    updateNavCommitButton(0);
    await autoGitCommitGlobal(commitMessage, true, applyData);
}

function showStagingResultPanel(success, message) {
    showResultPanel({
        command: 'Apply staged changes',
        success: false,
        title: 'Apply Changes Failed',
        outputHtml: `<span class="error-text">${message}</span>`,
        needsReload: false
    });
}

export async function autoGitCommitGlobal(message, clearStagingOnSuccess = false, applyData = null) {
    if (!message) {return;}

    const identity = getUserIdentity();

    const displayMessage = message.length > 60 ? message.substring(0, 60) + '...' : message;
    const fullCommand = `git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "${displayMessage}"`;
    showGitRunningPanel('Git Commit', fullCommand);

    const result = await ApiClient.post('/api/git/commit', {
        message,
        auto_init: true,
        user_name: identity.userName,
        user_email: identity.userEmail
    }, { silent: true });

    if (!result.success && result.data?.needsConfig) {
        showGitResultPanel(message, false, { error: 'Configure git name and email in Settings to enable version control' }, clearStagingOnSuccess);
        return;
    }

    const isSuccess = result.success && result.data?.success;

    // Only clear staging if commit was successful
    if (isSuccess && clearStagingOnSuccess) {
        await ApiClient.del('/api/staging', { silent: true });
    }

    const validation = applyData?.validation || null;
    showGitResultPanel(message, result.success, result.data || { error: result.error }, clearStagingOnSuccess && !isSuccess, validation);
}

function _verificationOpLine(verified, failed, label) {
    if (verified === 0 && failed === 0) {return null;}
    return failed > 0
        ? `<span class="warning-text">\u26a0 ${failed} ${label}(s) NOT verified</span>`
        : `<span class="success-text">\u2714 ${verified} ${label}(s) verified</span>`;
}

function _verificationFileLines(fl) {
    const fileCount = fl.actualFiles?.length || 0;
    if (fl.passed) {
        return `<span class="success-text">\u2714 File changes match (${fileCount} file${fileCount !== 1 ? 's' : ''})</span>\n`;
    }
    let html = `<span class="warning-text">\u26a0 File changes mismatch</span>\n`;
    for (const msg of [...(fl.unexpected || []), ...(fl.missing || [])]) {
        html += `<span class="warning-text">   ${msg}</span>\n`;
    }
    return html;
}

function buildVerificationHtml(verification) {
    const ol = verification.objectLevel;
    const fl = verification.fileLevel;
    let html = '\n<span class="info-text">--- Verification ---</span>\n';

    const objectLines = [
        _verificationOpLine(ol.editsVerified, ol.editsFailed, 'edit'),
        _verificationOpLine(ol.creationsVerified, ol.creationsFailed, 'creation'),
        _verificationOpLine(ol.deletionsVerified, ol.deletionsFailed, 'deletion'),
        _verificationOpLine(ol.movesVerified, ol.movesFailed, 'move'),
    ].filter(Boolean);
    html += objectLines.join('\n') + '\n';

    if (fl) {
        html += _verificationFileLines(fl);
    }

    if (ol.failures?.length > 0) {
        html += '\n';
        for (const f of ol.failures) {
            html += `<span class="warning-text">   ${f}</span>\n`;
        }
    }

    return html;
}

export function showGitResultPanel(message, success, result, showRetryOption = false, verification = null) {
    const identity = getUserIdentity();
    const displayMessage = message.length > 60 ? message.substring(0, 60) + '...' : message;
    const command = `git -c user.name="${identity.userName || '?'}" -c user.email="${identity.userEmail || '?'}" commit -m "${displayMessage}"`;

    const isSuccess = success && result.success;
    let outputHtml = '';
    if (isSuccess) {
        if (result.initialized) {
            outputHtml += '<span class="success-text">Initialized empty Git repository</span>\n';
        }
        outputHtml += `<span class="success-text">Committed:</span> <span class="hash">${escapeHtml(result.commit_hash)}</span>\n`;
        if (result.output) {
            outputHtml += escapeHtml(result.output);
        }
    } else {
        const errorMsg = result.error || 'Unknown error occurred';
        outputHtml = `<span class="error-text">${escapeHtml(errorMsg)}</span>`;

        if (showRetryOption) {
            outputHtml += '\n\n<span class="info-text">Changes have been applied to disk but not committed to git.</span>';
            outputHtml += '\n<span class="info-text">You can retry the commit or revert changes via git.</span>';
            baseState.pendingCommitMessage = message;
        }
    }

    // Append verification summary if available
    if (verification) {
        outputHtml += '\n' + buildVerificationHtml(verification);
    }

    // Downgrade title if commit succeeded but verification has warnings
    let title = isSuccess ? 'Git Commit Successful' : 'Git Commit Failed';
    if (isSuccess && verification && !verification.passed) {
        title = 'Committed with Warnings';
    }

    showResultPanel({
        command,
        success: isSuccess,
        title,
        outputHtml,
        showRetryCommit: showRetryOption && !isSuccess
    });
}


// onclick handler — must be global
window.discardGlobalChanges = discardGlobalChanges;
window.closeGlobalCommitDialog = closeGlobalCommitDialog;
window.applyGlobalCommit = applyGlobalCommit;
window.updateGlobalContextLines = updateGlobalContextLines;
window.updateGitOnlyContextLines = updateGitOnlyContextLines;
window.discardGitChanges = discardGitChanges;
window.applyGitCommit = applyGitCommit;
window.retryGitCommit = retryGitCommit;
window.discardStagingAfterFailedCommit = discardStagingAfterFailedCommit;
