/**
 * Nagios Bulk Editor - Commit Dialog Module
 *
 * Handles the global commit dialog UI including:
 * - Staging changes display
 * - Git operations (commit, discard)
 * - File-based changes builder
 * - Diff rendering
 *
 * Dependencies (loaded before this file):
 * - base-state.js: baseState object
 * - session-manager.js: getUserIdentity, hasUserIdentity
 * - ui-notifications.js: showToast, showConfirmDialog
 * - git-ui.js: showGitRunningPanel, showGitOperationResult, closeGitResultOverlay
 * - api-client.js: ApiClient
 * - app.js: escapeHtml
 */

// =============================================================================
// Global Commit Dialog
// =============================================================================

function handleCommitClick() {
    showGlobalCommitDialog();
}

async function showGlobalCommitDialog() {
    const overlay = document.getElementById('globalCommitOverlay');
    const content = document.getElementById('globalCommitContent');

    overlay.classList.add('visible');
    content.innerHTML = '<div class="dialog-loading">Loading changes...</div>';

    const [diffResult, refResult] = await Promise.all([
        ApiClient.get('/api/staging/diff', { silent: true }),
        ApiClient.get('/api/staging/analyze-references', { silent: true })
    ]);

    if (!diffResult.success) {
        content.innerHTML = `<div class="commit-empty commit-error-text">Error loading changes: ${escapeHtml(diffResult.error)}</div>`;
        return;
    }

    const result = diffResult.data;
    baseState.referenceData = refResult.data || {};

    const isGitConfigured = hasUserIdentity();

    if (!result.hasChanges) {
        content.innerHTML = '<div class="commit-empty">No pending changes.</div>';
        return;
    }

    baseState.diffData = result;
    content.innerHTML = await buildGlobalCommitDialogHtml(result, baseState.referenceData, isGitConfigured);

    document.querySelectorAll('#globalCommitContent .commit-item-header').forEach(header => {
        header.addEventListener('click', () => {
            header.closest('.commit-item').classList.toggle('expanded');
        });
    });
}

/**
 * Extract normalized staging arrays from a staging object.
 */
function extractStagingArrays(staging) {
    return {
        pendingEdits: staging.pendingEdits || {},
        stagedMoves: staging.stagedMoves || {},
        stagedCreations: staging.stagedCreations || [],
        stagedObjectDeletions: staging.stagedObjectDeletions || [],
        stagedFileCreations: staging.stagedFileCreations || [],
        stagedFileDeletions: staging.stagedFileDeletions || [],
        stagedFileMoves: staging.stagedFileMoves || [],
        stagedFolderCreations: staging.stagedFolderCreations || [],
        stagedFolderDeletions: staging.stagedFolderDeletions || [],
        stagedFolderMoves: staging.stagedFolderMoves || []
    };
}

/**
 * Check if a staging object has any file/folder operations.
 */
function hasFileOperations(s) {
    return s.stagedFileCreations.length > 0 || s.stagedFileDeletions.length > 0 || s.stagedFileMoves.length > 0 ||
           s.stagedFolderCreations.length > 0 || s.stagedFolderDeletions.length > 0 || s.stagedFolderMoves.length > 0;
}

/**
 * Check if a staging object has any GUI staging changes (object changes or file ops).
 */
function hasGuiStagingChanges(s) {
    const hasObjectChanges = Object.keys(s.pendingEdits).length > 0 || Object.keys(s.stagedMoves).length > 0 ||
                             s.stagedCreations.length > 0 || s.stagedObjectDeletions.length > 0;
    return hasObjectChanges || hasFileOperations(s);
}

/**
 * Build commit summary stats HTML for the header.
 */
function buildCommitSummaryStats(fileChanges) {
    let newCount = 0, deletedCount = 0, movedCount = 0, modifyCount = 0, refCount = 0;
    fileChanges.forEach(fc => {
        fc.additions.forEach(a => { if (a.isNew) {newCount++;} else {movedCount++;} });
        fc.removals.forEach(r => { if (r.isDeletion) {deletedCount++;} });
        modifyCount += fc.modifications.filter(m => !m.isReferenceUpdate).length;
        refCount += fc.modifications.filter(m => m.isReferenceUpdate).length;
    });
    return { newCount, deletedCount, movedCount, modifyCount, refCount };
}

/**
 * Build commit footer HTML with git identity and action buttons.
 */
function buildCommitFooterHtml(isGitConfigured, refData) {
    let identityHtml;
    if (isGitConfigured) {
        identityHtml = `<textarea id="globalGitCommitMessage" class="commit-message-textarea" placeholder="Enter commit message..."></textarea>`;
        if (refData && refData.hasNameChanges) {
            identityHtml += `
                <div class="commit-reference-option u-mt-sm">
                    <label class="commit-reference-label">
                        <input type="checkbox" id="globalUpdateReferences" checked onchange="toggleReferencePreview(this.checked)">
                        <span>
                            <strong>Update references</strong> (${refData.totalReferences} reference${refData.totalReferences !== 1 ? 's' : ''} in other objects)
                        </span>
                    </label>
                </div>`;
        }
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
 * Build summary stats HTML badges from file changes and stats.
 */
function buildSummaryStatsHtml(fileChangesSize, stats) {
    const badges = [];
    if (fileChangesSize > 0) {badges.push(`<div class="commit-stat edits"><span class="commit-stat-count">${fileChangesSize}</span> file${fileChangesSize !== 1 ? 's' : ''} changed</div>`);}
    if (stats.newCount > 0) {badges.push(`<div class="commit-stat creates"><span class="commit-stat-count">+${stats.newCount}</span> new</div>`);}
    if (stats.deletedCount > 0) {badges.push(`<div class="commit-stat deletes"><span class="commit-stat-count">${stats.deletedCount}</span> deleted</div>`);}
    if (stats.movedCount > 0) {badges.push(`<div class="commit-stat moves"><span class="commit-stat-count">${stats.movedCount}</span> moved</div>`);}
    if (stats.modifyCount > 0) {badges.push(`<div class="commit-stat edits"><span class="commit-stat-count">~${stats.modifyCount}</span> modified</div>`);}
    if (stats.refCount > 0) {badges.push(`<div class="commit-stat refs"><span class="commit-stat-count">${stats.refCount}</span> ref update${stats.refCount !== 1 ? 's' : ''}</div>`);}
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
 * Get staging operation counts and summary labels from raw staging object.
 */
function getStagingCounts(staging) {
    const counts = [
        [Object.keys(staging.pendingEdits || {}).length, 'edit'],
        [(staging.stagedCreations || []).length, 'creation'],
        [Object.keys(staging.stagedMoves || {}).length, 'move'],
        [(staging.stagedObjectDeletions || []).length, 'object deletion'],
        [(staging.stagedFileCreations || []).length, 'file creation'],
        [(staging.stagedFileDeletions || []).length, 'file deletion'],
        [(staging.stagedFileMoves || []).length, 'file move'],
        [(staging.stagedFolderCreations || []).length, 'folder creation'],
        [(staging.stagedFolderDeletions || []).length, 'folder deletion'],
        [(staging.stagedFolderMoves || []).length, 'folder move']
    ];
    const changeSummary = [];
    counts.forEach(([count, label]) => {
        if (count > 0) {changeSummary.push(pluralize(count, label));}
    });
    return {
        changeCount: counts.reduce((sum, [count]) => sum + count, 0),
        changeSummary
    };
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
 * Apply GUI staging changes with deferred clear. Returns true on success.
 */
async function applyGuiStagingChanges() {
    showGitRunningPanel('Applying Changes', 'Applying staged changes...');
    const updateRefsCheckbox = document.getElementById('globalUpdateReferences');
    const updateReferences = updateRefsCheckbox ? updateRefsCheckbox.checked : false;
    const applyResult = await ApiClient.post('/api/staging/apply', {
        updateReferences,
        deferClear: true
    }, { silent: true });
    if (!applyResult.success || !applyResult.data?.success) {
        showStagingResultPanel(false, applyResult.data?.error || applyResult.error || 'Failed to apply staged changes');
        return null;
    }
    return applyResult.data;
}

/**
 * Check if baseState.diffData has GUI staging changes.
 */
function diffDataHasGuiStaging() {
    if (!baseState.diffData || !baseState.diffData.staging) {return false;}
    const s = extractStagingArrays(baseState.diffData.staging);
    return hasGuiStagingChanges(s);
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

async function buildGlobalCommitDialogHtml(data, refData = null, isGitConfigured = true) {
    const allObjects = data.objects;
    const configPath = data.configPath;
    const existingFolders = data.existingFolders || [];
    const gitChanges = data.gitChanges || [];

    const s = extractStagingArrays(data.staging || {});
    const hasGuiStaging = hasGuiStagingChanges(s);

    if (!hasGuiStaging && data.hasGitChanges) {
        return await buildGitOnlyCommitDialogHtml(gitChanges, configPath, isGitConfigured);
    }

    const fileChanges = buildGlobalFileBasedChanges(s.pendingEdits, s.stagedMoves, s.stagedCreations, s.stagedObjectDeletions, allObjects, configPath);
    if (refData && refData.hasNameChanges) {
        injectReferenceChanges(fileChanges, refData, configPath);
    }

    // Filter external git changes to exclude files already in the staging preview
    const stagedFilePaths = new Set(fileChanges.keys());
    const externalOnlyChanges = gitChanges.filter(gc => {
        const fullPath = gc.path.startsWith('/') ? gc.path : configPath + '/' + gc.path;
        return !stagedFilePaths.has(fullPath) && !stagedFilePaths.has(gc.path);
    });
    const hasExternalChanges = hasGuiStaging && data.hasGitChanges && externalOnlyChanges.length > 0;
    const externalChangesHtml = hasExternalChanges
        ? await buildExternalChangesHtml(externalOnlyChanges, baseState.commitContextLines)
        : '';

    // Include external file count in summary so the header reflects total commit scope
    const totalFileCount = fileChanges.size + (hasExternalChanges ? externalOnlyChanges.length : 0);

    return `
        <div class="commit-header">
            <div class="commit-summary">
                ${buildSummaryStatsHtml(totalFileCount, buildCommitSummaryStats(fileChanges))}
                ${hasExternalChanges ? `<div class="commit-stat external"><span class="commit-stat-count">${externalOnlyChanges.length}</span> external</div>` : ''}
            </div>
            ${buildContextControlHtml(baseState.commitContextLines, 'updateGlobalContextLines', 'globalContextLinesValue')}
        </div>
        <div class="commit-changes-list" id="globalCommitChangesList">
            ${buildGlobalCommitChangesListHtml(fileChanges, configPath, existingFolders, allObjects, hasFileOperations(s) || hasExternalChanges)}
            ${buildFileAndFolderOperationsHtml(s.stagedFolderCreations, s.stagedFolderDeletions, s.stagedFolderMoves, s.stagedFileCreations, s.stagedFileDeletions, s.stagedFileMoves, configPath)}
            ${externalChangesHtml}
        </div>
        ${buildCommitFooterHtml(isGitConfigured, refData)}`;
}

function toggleReferencePreview(checked) {
    const optionDiv = document.querySelector('.commit-reference-option');
    if (!checked && optionDiv) {
        // Show warning about broken references
        const refData = baseState.referenceData;
        if (refData && refData.totalReferences > 0) {
            // Remove existing warning if any
            const existing = optionDiv.parentNode.querySelector('.commit-reference-warning');
            if (existing) {existing.remove();}

            const warning = document.createElement('div');
            warning.className = 'commit-reference-warning';
            warning.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>Warning:</strong> Committing without updating references may result in a broken Nagios configuration. ${refData.totalReferences} reference${refData.totalReferences !== 1 ? 's' : ''} will point to renamed objects.`;
            optionDiv.parentNode.insertBefore(warning, optionDiv.nextSibling);
        }
    } else {
        // Remove warning
        const warning = document.querySelector('.commit-reference-warning');
        if (warning) {warning.remove();}
    }

    // Rebuild the file changes view to include/exclude reference updates
    updateGlobalContextLines(
        baseState.commitContextLines > 9 ? 10 : baseState.commitContextLines
    );
}

function buildReferenceChangesSection(refData) {
    // No longer used — reference changes are now shown inline in file diffs
    return '';
}

/**
 * Injects reference updates into the file-based changes map as synthetic modifications.
 * Each reference becomes a modification entry showing old_value -> new_value for the affected field.
 */
function injectReferenceChanges(fileChanges, refData, configPath) {
    if (!refData || !refData.nameChanges) {return;}

    for (const change of refData.nameChanges) {
        for (const ref of change.references) {
            const filePath = ref.sourceFile;
            if (!filePath) {continue;}

            const file = ensureFileChange(fileChanges, filePath, configPath);

            // Skip if a pending edit already covers this object+field change
            // (reference was already staged by the rename dialog)
            const alreadyCovered = file.modifications.some(m =>
                !m.isReferenceUpdate &&
                m.object.object_type === ref.objectType &&
                ref.field in (m.finalAttrs || {}) &&
                ref.field in (m.originalAttrs || {}) &&
                m.originalAttrs[ref.field] === ref.oldValue
            );
            if (alreadyCovered) {continue;}

            // Build original and updated attributes showing just the changed field
            const originalAttrs = {};
            originalAttrs[ref.field] = ref.oldValue;

            const finalAttrs = {};
            finalAttrs[ref.field] = ref.newValue;

            file.modifications.push({
                globalIndex: -1,  // Synthetic — no real global_index
                object: {
                    object_type: ref.objectType,
                    global_index: -1,
                    source_file: filePath,
                    line_number: 0,
                },
                originalAttrs,
                finalAttrs,
                lineNumber: 0,
                isReferenceUpdate: true,
                referenceMeta: {
                    objectName: ref.objectName,
                    renamedFrom: change.oldName,
                    renamedTo: change.newName,
                },
            });
        }
    }
}

async function buildGitOnlyCommitDialogHtml(gitChanges, configPath, isGitConfigured = true) {
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
 * Build HTML for git file changes (used by both git-only and external changes views).
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
        // For 'modified': use 'external' if external style, otherwise empty
        // For others: 'create' for added/untracked, 'delete' for deleted, 'move' for renamed
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
        const useFullFile = contextLines > 9;
        const diffResult = await ApiClient.post('/api/git/diff', {
            file: change.path,
            fullFile: useFullFile,
            contextLines: useFullFile ? null : contextLines
        }, { silent: true });

        if (diffResult.success && diffResult.data?.diff) {
            diffContent = diffResult.data.diff.split('\n').map(line => {
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
        } else {
            diffContent = '<div class="diff-line context">Unable to load diff</div>';
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

async function updateGitOnlyContextLines(value) {
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

// =============================================================================
// Git Operations
// =============================================================================

async function discardGitChanges() {
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

function showResultPanel({ command, success, title, outputHtml, needsReload = true, showRetryCommit = false }) {
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

    // C-10: Add retry button if commit failed but staging was preserved
    let retryButtonHtml = '';
    if (showRetryCommit) {
        retryButtonHtml = `
            <div class="git-retry-section">
                <button class="nbe-btn nbe-btn--dark nbe-btn--tonal" onclick="retryGitCommit()">
                    <i class="fa-solid fa-redo"></i> Retry Commit
                </button>
                <button class="nbe-btn nbe-btn--dark" onclick="discardStagingAfterFailedCommit()">
                    Discard Staging
                </button>
            </div>
        `;
    }
    output.innerHTML = outputHtml + retryButtonHtml;

    overlay.classList.add('visible');
}

/**
 * C-10: Retry git commit after a failed attempt.
 * Staging was preserved after apply, so we can retry the commit.
 */
async function retryGitCommit() {
    const message = baseState.pendingCommitMessage;
    if (!message) {
        showToast('No pending commit message found', 'error');
        return;
    }

    // Close the result panel and retry
    const overlay = document.getElementById('gitResultOverlay');
    overlay.classList.remove('visible');

    await autoGitCommitGlobal(message, true);
}

/**
 * C-10: Discard staging after a failed commit.
 * User chose not to retry, so clear the preserved staging.
 */
async function discardStagingAfterFailedCommit() {
    const confirmed = await showConfirmDialog({
        title: 'Discard Staging?',
        message: 'Your changes have been written to disk but not committed to git. Discarding staging will clear the staging state. The files on disk will remain changed.',
        confirmText: 'Discard Staging',
        type: 'warning'
    });

    if (confirmed) {
        await ApiClient.del('/api/staging', { silent: true });
        baseState.pendingCommitMessage = null;
        closeGitResultOverlay();
        showToast('Staging cleared', 'info');
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

async function applyGitCommit() {
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

// =============================================================================
// File-Based Changes Builder
// =============================================================================

/**
 * Ensures a file entry exists in the fileChanges map with initialized arrays.
 */
function ensureFileChange(fileChanges, filePath, configPath) {
    if (!fileChanges.has(filePath)) {
        fileChanges.set(filePath, {
            fileName: filePath.split('/').pop(),
            relativePath: filePath.startsWith(configPath + '/') ? filePath.substring(configPath.length + 1) : filePath,
            removals: [],
            additions: [],
            modifications: []
        });
    }
    return fileChanges.get(filePath);
}

/**
 * Builds a map of globalIndex -> edit data from pendingEdits dict.
 */
function buildEditsMap(pendingEdits) {
    const editsMap = new Map();
    for (const [key, entry] of Object.entries(pendingEdits)) {
        editsMap.set(key, entry);
    }
    return editsMap;
}

/**
 * Processes a single staged move, adding removal to source file and addition to target file.
 */
function processStagedMove(moveEntry, allObjects, editsMap, fileChanges, configPath) {
    const [moveKey, move] = moveEntry;

    // Find object by stable key (Base64-encoded or plain) or by global_index
    let obj = StableKey.findObject(moveKey, allObjects);

    // Fallback: create object from move.object data
    if (!obj && move.object) {
        obj = {
            global_index: move.object.global_index !== undefined ? move.object.global_index : -1,
            attributes: move.object.attributes || {},
            object_type: move.object.object_type,
            line_number: move.object.line_number,
            source_file: move.object.source_file,
            name: move.object.name || move.object.display_name
        };
    }
    if (!obj) {return;}

    // Use the actual global_index for proper matching in diff rendering
    const globalIndex = obj.global_index;

    const edit = editsMap.get(moveKey) || editsMap.get(globalIndex);
    const originalAttrs = edit ? { ...edit.original } : { ...obj.attributes };
    const finalAttrs = edit ? { ...edit.edited } : { ...obj.attributes };

    const sourceFile = ensureFileChange(fileChanges, move.originalFile, configPath);
    sourceFile.removals.push({
        globalIndex: globalIndex,
        object: obj,
        originalAttrs,
        lineNumber: obj.line_number,
        targetFile: move.targetFile
    });

    const targetFile = ensureFileChange(fileChanges, move.targetFile, configPath);
    targetFile.additions.push({
        globalIndex: globalIndex,
        object: obj,
        finalAttrs,
        objectType: obj.object_type,
        isNew: false,
        insertPosition: move.insertPosition,
        originalFile: move.originalFile
    });
}

/**
 * Processes a single pending edit (for objects not being moved).
 */
function processPendingEdit(editEntry, allObjects, movedIndices, fileChanges, configPath) {
    const [editIdx, edit] = editEntry;

    if (movedIndices.has(editIdx)) {return;}

    // Find object by stable key (Base64-encoded or plain) or by global_index
    let obj = StableKey.findObject(editIdx, allObjects);

    if (!obj && edit.object) {
        obj = {
            // Use null-check instead of || to handle global_index = 0
            global_index: edit.object.global_index !== undefined ? edit.object.global_index : -1,
            attributes: edit.object.attributes || {},
            object_type: edit.object.object_type,
            line_number: edit.object.line_number,
            source_file: edit.object.source_file,
            name: edit.object.name || edit.object.display_name
        };
    }
    if (!obj) {return;}

    const file = ensureFileChange(fileChanges, obj.source_file, configPath);
    file.modifications.push({
        globalIndex: obj.global_index,
        object: obj,
        originalAttrs: { ...edit.original },
        finalAttrs: { ...edit.edited },
        lineNumber: obj.line_number
    });
}

/**
 * Processes a single staged creation.
 */
function processStagedCreation(creation, fileChanges, configPath) {
    const file = ensureFileChange(fileChanges, creation.targetFile, configPath);
    file.additions.push({
        object: { object_type: creation.object_type, display_name: creation.displayName },
        finalAttrs: { ...creation.attributes },
        objectType: creation.object_type,
        isNew: true,
        insertPosition: creation.insertPosition
    });
}

/**
 * Processes a single staged object deletion.
 */
function processStagedDeletion(globalIndex, allObjects, fileChanges, configPath) {
    const obj = allObjects.find(o => o.global_index === globalIndex);
    if (!obj) {return;}

    const file = ensureFileChange(fileChanges, obj.source_file, configPath);
    file.removals.push({
        globalIndex,
        object: obj,
        originalAttrs: { ...obj.attributes },
        lineNumber: obj.line_number,
        isDeletion: true
    });
}

/**
 * Builds a file-based view of all staged changes for the commit dialog.
 * Groups edits, moves, creations, and deletions by their target files.
 */
function buildGlobalFileBasedChanges(pendingEdits, stagedMoves, stagedCreations, stagedObjectDeletions, allObjects, configPath) {
    const fileChanges = new Map();
    const editsMap = buildEditsMap(pendingEdits);

    // Iterate over moves dict {stableKey: moveData, ...}
    const iterateMoves = (moves, callback) => {
        for (const [key, move] of Object.entries(moves || {})) {
            callback(key, move);
        }
    };

    // Process moves (adds to both source and target files)
    iterateMoves(stagedMoves, (moveKey, move) => {
        processStagedMove([moveKey, move], allObjects, editsMap, fileChanges, configPath);
    });

    // Build set of moved indices to skip them in edit processing
    // Need to convert stable keys to global indices for proper matching
    const movedIndices = new Set();
    iterateMoves(stagedMoves, (moveKey, move) => {
        // Try to find the object using stable key or global_index
        const obj = StableKey.findObject(moveKey, allObjects);
        if (obj) {
            movedIndices.add(obj.global_index);
        }
        // Also add the key itself for matching against key-based edits
        movedIndices.add(moveKey);
    });

    // Iterate over edits dict {globalIndex: editData, ...}
    const iterateEdits = (edits, callback) => {
        for (const [key, edit] of Object.entries(edits || {})) {
            callback(key, edit);
        }
    };

    // Process edits (skip objects that are being moved)
    iterateEdits(pendingEdits, (editKey, edit) => {
        processPendingEdit([editKey, edit], allObjects, movedIndices, fileChanges, configPath);
    });

    // Process creations
    for (const creation of stagedCreations) {
        processStagedCreation(creation, fileChanges, configPath);
    }

    // Process deletions
    for (const globalIndex of stagedObjectDeletions) {
        processStagedDeletion(globalIndex, allObjects, fileChanges, configPath);
    }

    return fileChanges;
}

function buildGlobalCommitChangesListHtml(fileChanges, configPath, existingFolders, allObjects, hasOtherChanges = false) {
    let html = '';

    if (fileChanges.size > 0) {
        html += `<div class="commit-section">
            <div class="commit-section-title">File Changes <span class="badge">${fileChanges.size} file${fileChanges.size !== 1 ? 's' : ''}</span></div>`;

        const sortedFiles = [...fileChanges.entries()].sort((a, b) => a[0].localeCompare(b[0]));

        sortedFiles.forEach(([filePath, fileData]) => {
            html += renderGlobalFileDiff(filePath, fileData, allObjects, configPath);
        });

        html += '</div>';
    }

    // Only show "No changes" if there are no other changes (file/folder ops, external changes)
    if (html === '' && !hasOtherChanges) {
        html = '<div class="commit-empty">No changes to display.</div>';
    }

    return html;
}

function buildFileAndFolderOperationsHtml(folderCreations, folderDeletions, folderMoves, fileCreations, fileDeletions, fileMoves, configPath) {
    const totalOps = folderCreations.length + folderDeletions.length + folderMoves.length +
                     fileCreations.length + fileDeletions.length + fileMoves.length;

    if (totalOps === 0) {
        return '';
    }

    // Helper to get relative path from config path
    const getRelativePath = (fullPath) => {
        if (fullPath.startsWith(configPath)) {
            const rel = fullPath.slice(configPath.length);
            return rel.startsWith('/') ? rel.slice(1) : rel;
        }
        return fullPath;
    };

    let itemsHtml = '';

    // Folder creations
    for (const op of folderCreations) {
        const relPath = getRelativePath(op.path);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-folder-plus file-op-icon file-op-create"></i>
                    <span class="file-op-action">Create folder</span>
                    <span class="file-op-path">${escapeHtml(relPath)}</span>
                </div>
            </div>
        `;
    }

    // Folder deletions
    for (const op of folderDeletions) {
        const relPath = getRelativePath(op.path);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-folder-minus file-op-icon file-op-delete"></i>
                    <span class="file-op-action">Delete folder</span>
                    <span class="file-op-path">${escapeHtml(relPath)}</span>
                </div>
            </div>
        `;
    }

    // Folder moves
    for (const op of folderMoves) {
        const sourceRel = getRelativePath(op.sourcePath);
        const targetRel = getRelativePath(op.targetPath);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-folder-tree file-op-icon file-op-move"></i>
                    <span class="file-op-action">Move folder</span>
                    <span class="file-op-path">${escapeHtml(sourceRel)} <i class="fa-solid fa-arrow-right file-op-arrow"></i> ${escapeHtml(targetRel)}</span>
                </div>
            </div>
        `;
    }

    // File creations
    for (const op of fileCreations) {
        const relPath = getRelativePath(op.path);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-file-circle-plus file-op-icon file-op-create"></i>
                    <span class="file-op-action">Create file</span>
                    <span class="file-op-path">${escapeHtml(relPath)}</span>
                </div>
            </div>
        `;
    }

    // File deletions
    for (const op of fileDeletions) {
        const relPath = getRelativePath(op.path);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-file-circle-minus file-op-icon file-op-delete"></i>
                    <span class="file-op-action">Delete file</span>
                    <span class="file-op-path">${escapeHtml(relPath)}</span>
                </div>
            </div>
        `;
    }

    // File moves
    for (const op of fileMoves) {
        const sourceRel = getRelativePath(op.sourcePath);
        const targetRel = op.targetFolder ? getRelativePath(op.targetFolder) : getRelativePath(op.targetPath);
        itemsHtml += `
            <div class="commit-item file-op-item">
                <div class="commit-item-header file-op-header">
                    <i class="fa-solid fa-file-export file-op-icon file-op-move"></i>
                    <span class="file-op-action">Move file</span>
                    <span class="file-op-path">${escapeHtml(sourceRel)} <i class="fa-solid fa-arrow-right file-op-arrow"></i> ${escapeHtml(targetRel)}</span>
                </div>
            </div>
        `;
    }

    return `
        <div class="commit-section commit-file-ops-section">
            <div class="commit-section-title">
                <i class="fa-solid fa-folder-open" style="margin-right: 6px;"></i>
                File & Folder Operations <span class="badge">${totalOps}</span>
            </div>
            ${itemsHtml}
        </div>
    `;
}

function renderGlobalFileDiff(filePath, fileData, allObjects, configPath) {
    const { fileName, relativePath, removals, additions, modifications } = fileData;

    let summaryParts = [];
    if (additions.length > 0) {summaryParts.push(`+${additions.length}`);}
    if (removals.length > 0) {summaryParts.push(`-${removals.length}`);}
    if (modifications.length > 0) {summaryParts.push(`~${modifications.length}`);}

    let existingObjects = allObjects
        .filter(obj => obj.source_file === filePath)
        .sort((a, b) => a.line_number - b.line_number);

    const removalIndices = new Set(removals.map(r => r.object.global_index));
    const regularMods = modifications.filter(m => !m.isReferenceUpdate);
    const modificationIndices = new Set(regularMods.map(m => m.object.global_index));
    const modificationMap = new Map(regularMods.map(m => [m.object.global_index, m]));

    const existingIndices = new Set(existingObjects.map(o => o.global_index));
    for (const removal of removals) {
        if (!existingIndices.has(removal.object.global_index)) {
            existingObjects.push(removal.object);
        }
    }
    existingObjects.sort((a, b) => a.line_number - b.line_number);

    const unifiedItems = [];

    existingObjects.forEach((obj, idx) => {
        unifiedItems.push({
            type: 'existing',
            sortKey: obj.line_number,
            idx: idx,
            object: obj,
            isRemoval: removalIndices.has(obj.global_index),
            isModification: modificationIndices.has(obj.global_index)
        });
    });

    additions.forEach((addition, addIdx) => {
        const insertPos = addition.insertPosition !== undefined ? addition.insertPosition : Infinity;
        unifiedItems.push({
            type: 'addition',
            sortKey: insertPos,
            addIdx: addIdx,
            addition: addition
        });
    });

    // Add reference updates as separate items (they don't correspond to existing objects in this file)
    modifications.filter(m => m.isReferenceUpdate).forEach(mod => {
        unifiedItems.push({
            type: 'referenceUpdate',
            sortKey: Infinity,  // Show at end of file
            modification: mod,
        });
    });

    // Sort with additions before existing objects at the same position
    // This ensures items with small insertPosition values (0, 0.25, 0.5)
    // appear before existing objects at line 1, 2, etc.
    unifiedItems.sort((a, b) => {
        const diff = a.sortKey - b.sortKey;
        if (Math.abs(diff) > 0.001) {return diff;}
        // When sortKeys are equal, additions come before existing objects
        if (a.type === 'addition' && b.type !== 'addition') {return -1;}
        if (a.type !== 'addition' && b.type === 'addition') {return 1;}
        return 0;
    });

    const maxContext = baseState.commitContextLines;
    const interestingPositions = new Set();
    unifiedItems.forEach((item, pos) => {
        const isInteresting = item.type === 'addition' || item.type === 'referenceUpdate' ||
                             (item.type === 'existing' && (item.isRemoval || item.isModification));
        if (isInteresting) {
            for (let i = Math.max(0, pos - maxContext); i <= Math.min(unifiedItems.length - 1, pos + maxContext); i++) {
                interestingPositions.add(i);
            }
        }
    });

    let diffHtml = `<div class="diff-file-header">${escapeHtml(fileName)}</div>`;
    let lastShownPos = -1;
    let skippedCount = 0;

    unifiedItems.forEach((item, pos) => {
        if (!interestingPositions.has(pos)) {
            skippedCount++;
            return;
        }

        const hadSkipped = skippedCount > 0;
        if (hadSkipped && lastShownPos >= 0) {
            diffHtml += `<div class="diff-line context diff-skipped">  ... ${skippedCount} unchanged object${skippedCount !== 1 ? 's' : ''} ...</div>`;
        }
        skippedCount = 0;

        if (lastShownPos >= 0 && !hadSkipped) {
            diffHtml += `<div class="diff-line context"> </div>`;
        }
        lastShownPos = pos;

        if (item.type === 'addition') {
            const addition = item.addition;
            if (addition.isNew) {
                diffHtml += renderGlobalObject(addition.objectType, addition.finalAttrs, '+');
            } else {
                // Check if this is a same-file reorder vs cross-file move
                const isSameFile = addition.originalFile === filePath;
                if (isSameFile) {
                    diffHtml += `<div class="diff-line add">+ [Reordered within file]</div>`;
                } else {
                    diffHtml += `<div class="diff-line add">+ [Moved from ${escapeHtml(addition.originalFile || 'another file')}]</div>`;
                }
                diffHtml += renderGlobalObject(addition.objectType, addition.finalAttrs, '+');
            }
        } else if (item.isRemoval) {
            const removal = removals.find(r => r.object.global_index === item.object.global_index);
            if (removal && removal.isDeletion) {
                diffHtml += renderGlobalObject(item.object.object_type, removal.originalAttrs, '-');
            } else if (removal) {
                // Check if this is a same-file reorder vs cross-file move
                const isSameFile = removal.targetFile === filePath;
                if (isSameFile) {
                    diffHtml += `<div class="diff-line remove">- [Reordered within file]</div>`;
                } else {
                    diffHtml += `<div class="diff-line remove">- [Moving to ${escapeHtml(removal.targetFile || 'another file')}]</div>`;
                }
                diffHtml += renderGlobalObject(item.object.object_type, removal.originalAttrs, '-');
            }
        } else if (item.isModification) {
            const mod = modificationMap.get(item.object.global_index);
            if (mod) {
                diffHtml += renderGlobalModifiedObject(mod.object, mod.originalAttrs, mod.finalAttrs);
            }
        } else if (item.type === 'referenceUpdate') {
            diffHtml += renderReferenceUpdateDiff(item.modification);
        } else {
            diffHtml += renderGlobalObject(item.object.object_type, item.object.attributes, ' ');
        }
    });

    if (skippedCount > 0) {
        diffHtml += `<div class="diff-line context diff-skipped">  ... ${skippedCount} unchanged object${skippedCount !== 1 ? 's' : ''} ...</div>`;
    }

    return `
        <div class="commit-item expanded">
            <div class="commit-item-header">
                <span class="commit-item-expand">&#9658;</span>
                <span class="commit-item-type">file</span>
                <span class="commit-item-name">${escapeHtml(fileName)}</span>
                <span class="commit-item-file">${escapeHtml(relativePath)} · ${summaryParts.join(' ')}</span>
            </div>
            <div class="commit-item-diff">
                <div class="diff-content">${diffHtml}</div>
            </div>
        </div>
    `;
}

function renderGlobalObject(objType, attrs, prefix) {
    let cssClass;
    if (prefix === '-') {
        cssClass = 'remove';
    } else if (prefix === '+') {
        cssClass = 'add';
    } else {
        cssClass = 'context';
    }
    let html = `<div class="diff-line ${cssClass}">${prefix} define ${escapeHtml(objType)} {</div>`;
    const keys = Object.keys(attrs).sort();
    for (const key of keys) {
        html += `<div class="diff-line ${cssClass}">${prefix}     ${escapeHtml(key.padEnd(30))} ${escapeHtml(attrs[key])}</div>`;
    }
    html += `<div class="diff-line ${cssClass}">${prefix} }</div>`;
    return html;
}

function renderGlobalModifiedObject(obj, originalAttrs, finalAttrs) {
    const allKeys = [...new Set([...Object.keys(originalAttrs), ...Object.keys(finalAttrs)])].sort();
    let html = `<div class="diff-line modify">  define ${escapeHtml(obj.object_type)} {</div>`;

    allKeys.forEach(key => {
        const origVal = originalAttrs[key];
        const newVal = finalAttrs[key];

        if (origVal === newVal) {
            html += `<div class="diff-line context">      ${escapeHtml(key.padEnd(30))} ${escapeHtml(origVal || '')}</div>`;
        } else if (!origVal && newVal) {
            html += `<div class="diff-line add">+     ${escapeHtml(key.padEnd(30))} ${escapeHtml(newVal)}</div>`;
        } else if (origVal && !newVal) {
            html += `<div class="diff-line remove">-     ${escapeHtml(key.padEnd(30))} ${escapeHtml(origVal)}</div>`;
        } else {
            html += `<div class="diff-line remove">-     ${escapeHtml(key.padEnd(30))} ${escapeHtml(origVal)}</div>`;
            html += `<div class="diff-line add">+     ${escapeHtml(key.padEnd(30))} ${escapeHtml(newVal)}</div>`;
        }
    });

    html += `<div class="diff-line modify">  }</div>`;
    return html;
}

function renderReferenceUpdateDiff(mod) {
    const meta = mod.referenceMeta;
    const objType = mod.object.object_type;
    let html = `<div class="diff-line modify">  define ${escapeHtml(objType)} {</div>`;
    html += `<div class="diff-line context">      # ${escapeHtml(meta.objectName)} — ref update (${escapeHtml(meta.renamedFrom)} → ${escapeHtml(meta.renamedTo)})</div>`;

    const allKeys = [...new Set([...Object.keys(mod.originalAttrs), ...Object.keys(mod.finalAttrs)])].sort();
    allKeys.forEach(key => {
        const origVal = mod.originalAttrs[key];
        const newVal = mod.finalAttrs[key];
        if (origVal !== newVal) {
            html += `<div class="diff-line remove">-     ${escapeHtml(key.padEnd(30))} ${escapeHtml(origVal || '')}</div>`;
            html += `<div class="diff-line add">+     ${escapeHtml(key.padEnd(30))} ${escapeHtml(newVal || '')}</div>`;
        }
    });

    html += `<div class="diff-line modify">  }</div>`;
    return html;
}

function updateGlobalContextLines(value) {
    const intValue = parseInt(value, 10);
    baseState.commitContextLines = intValue === 10 ? 9999 : intValue;
    document.getElementById('globalContextLinesValue').textContent = intValue === 10 ? 'All' : value;

    if (!baseState.diffData || !baseState.diffData.staging) {return;}

    const allObjects = baseState.diffData.objects;
    const configPath = baseState.diffData.configPath;
    const existingFolders = baseState.diffData.existingFolders || [];
    const s = extractStagingArrays(baseState.diffData.staging);

    const expandedIndices = saveCommitItemExpansionState();

    const fileChanges = buildGlobalFileBasedChanges(s.pendingEdits, s.stagedMoves, s.stagedCreations, s.stagedObjectDeletions, allObjects, configPath);
    const updateRefsCheckbox = document.getElementById('globalUpdateReferences');
    if (baseState.referenceData && baseState.referenceData.hasNameChanges && updateRefsCheckbox && updateRefsCheckbox.checked) {
        injectReferenceChanges(fileChanges, baseState.referenceData, configPath);
    }

    const changesList = document.getElementById('globalCommitChangesList');
    if (changesList) {
        let html = buildGlobalCommitChangesListHtml(fileChanges, configPath, existingFolders, allObjects, hasFileOperations(s));
        html += buildFileAndFolderOperationsHtml(s.stagedFolderCreations, s.stagedFolderDeletions, s.stagedFolderMoves, s.stagedFileCreations, s.stagedFileDeletions, s.stagedFileMoves, configPath);
        changesList.innerHTML = html;
        restoreCommitItemExpansionState(expandedIndices);
    }
}

function closeGlobalCommitDialog() {
    document.getElementById('globalCommitOverlay').classList.remove('visible');
}

async function discardGlobalChanges() {
    const staging = baseState.diffData && baseState.diffData.staging;
    const { changeCount, changeSummary } = staging ? getStagingCounts(staging) : { changeCount: 0, changeSummary: [] };

    closeGlobalCommitDialog();
    showGitRunningPanel('Discard Changes', 'Clearing staged changes...');

    const result = await ApiClient.del('/api/staging', { silent: true });

    if (result.success && result.data?.success) {
        await resetFrontendAfterDiscard();
    }
    const data = result.data || {};
    showStagingDiscardResultPanel(result.success && data.success, changeCount, changeSummary, data.error || result.error, data.gitDiscarded);
}

function showStagingDiscardResultPanel(success, changeCount, changeSummary, errorMsg = null, gitDiscarded = false) {
    const command = gitDiscarded ? 'git checkout -- . && git clean -fd' : 'Clear staging data';

    let outputHtml = '';
    if (success) {
        if (gitDiscarded) {
            outputHtml = '<span class="success-text">All uncommitted changes have been discarded.</span>\n\n';
            outputHtml += '<span class="terminal-hint">Git working directory restored to HEAD.</span>\n';
        } else if (changeCount > 0) {
            outputHtml = `<span class="success-text">All staged changes discarded (${changeCount} change${changeCount !== 1 ? 's' : ''})</span>\n\n`;
            if (changeSummary.length > 0) {
                outputHtml += '<span class="terminal-hint">Cleared:</span>\n';
                changeSummary.forEach(item => {
                    outputHtml += `  - ${escapeHtml(item)}\n`;
                });
            }
        } else {
            outputHtml = '<span class="success-text">Staging cleared.</span>\n';
        }
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

async function applyGlobalCommit() {
    const commitMessage = validateCommitInput();
    if (!commitMessage) {return;}

    closeGlobalCommitDialog();

    const hasGuiStaging = diffDataHasGuiStaging();

    let applyData = null;
    if (hasGuiStaging) {
        applyData = await applyGuiStagingChanges();
        if (!applyData) {return;}
    } else {
        showGitRunningPanel('Git Commit', 'Committing changes...');
    }

    updateNavCommitButton(0);
    await autoGitCommitGlobal(commitMessage, hasGuiStaging, applyData);
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

async function autoGitCommitGlobal(message, clearStagingOnSuccess = false, applyData = null) {
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

    // C-10: Only clear staging if commit was successful
    if (isSuccess && clearStagingOnSuccess) {
        // Clear staging after successful commit
        await ApiClient.del('/api/staging', { silent: true });
    }

    const verification = applyData?.verification || null;
    showGitResultPanel(message, result.success, result.data || { error: result.error }, clearStagingOnSuccess && !isSuccess, verification);
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

function showGitResultPanel(message, success, result, showRetryOption = false, verification = null) {
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

        // C-10: Show retry option if staging was preserved after apply
        if (showRetryOption) {
            outputHtml += '\n\n<span class="info-text">Changes have been applied to disk but not committed to git.</span>';
            outputHtml += '\n<span class="info-text">Staging preserved - you can retry the commit.</span>';
            // Store message for retry
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


// Export functions to global scope for backward compatibility
window.handleCommitClick = handleCommitClick;
window.showGlobalCommitDialog = showGlobalCommitDialog;
window.closeGlobalCommitDialog = closeGlobalCommitDialog;
window.discardGlobalChanges = discardGlobalChanges;
window.applyGlobalCommit = applyGlobalCommit;
window.updateGlobalContextLines = updateGlobalContextLines;
window.toggleReferencePreview = toggleReferencePreview;
window.discardGitChanges = discardGitChanges;
window.applyGitCommit = applyGitCommit;
window.updateGitOnlyContextLines = updateGitOnlyContextLines;
window.retryGitCommit = retryGitCommit;
window.discardStagingAfterFailedCommit = discardStagingAfterFailedCommit;
window.autoGitCommitGlobal = autoGitCommitGlobal;
window.showGitResultPanel = showGitResultPanel;
window.showResultPanel = showResultPanel;
