/**
 * Nagios Bulk Editor - Base JavaScript
 *
 * Shared functionality across all pages.
 */
import { escapeHtml, handleGlobalKeydown, reloadConfig } from './app.js';
import { baseState } from './base-state.js';
import { getSessionId, getUserIdentity, setUserIdentity, hasUserIdentity } from './session-manager.js';
import { showToast, showConfirmDialog } from './ui-notifications.js';
import { ApiClient } from './api-client.js';
import { closeGitResultPanel } from './git-ui.js';
import { handleCommitClick, closeGlobalCommitDialog } from './commit-dialog.js';
import { checkLockStatus, breakLock } from './lock-manager.js';

let explorerCallbacks = null;

export function registerExplorerCallbacks(callbacks) {
    explorerCallbacks = callbacks;
}

// =============================================================================
// Debug Logger - sends debug logs to backend for file logging
// =============================================================================

// Set to true to enable debug logging to backend
const ENABLED = true;

// Buffer logs and send in batches to reduce HTTP requests
let logBuffer = [];
let flushTimeout = null;
const FLUSH_INTERVAL = 2000; // 2 seconds

function log(level, message, context = {}) {
    if (!ENABLED) {return;}

    logBuffer.push({ level, message, context, timestamp: new Date().toISOString() });

    // Schedule flush if not already scheduled
    if (!flushTimeout) {
        flushTimeout = setTimeout(flush, FLUSH_INTERVAL);
    }
}

async function flush() {
    flushTimeout = null;
    if (logBuffer.length === 0) {return;}

    const logsToSend = logBuffer;
    logBuffer = [];

    // Send each log entry (could batch in future if needed)
    for (const entry of logsToSend) {
        try {
            await fetch('/api/logs/frontend', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(entry)
            });
        } catch (e) {
            // Silently fail - don't break the app for logging failures
        }
    }
}

// Flush on page unload
window.addEventListener('beforeunload', () => {
    if (logBuffer.length > 0) {
        // Use sendBeacon for reliable delivery on page unload
        const data = JSON.stringify(logBuffer.map(entry => ({
            level: entry.level,
            message: entry.message,
            context: entry.context
        })));
        navigator.sendBeacon('/api/logs/frontend', new Blob([data], { type: 'application/json' }));
    }
});

// After all the functions are defined at module scope:
export const DebugLogger = {
    debug: (message, context) => log('debug', message, context),
    info: (message, context) => log('info', message, context),
    warning: (message, context) => log('warning', message, context),
    error: (message, context) => log('error', message, context)
};

// =============================================================================
// Utility Functions
// =============================================================================

export function escapeJs(text) {
    if (text === null || text === undefined) {return '';}
    return String(text)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r');
}

/**
 * Pluralize a word based on count
 * @param {number} count - The count to check
 * @param {string} singular - Singular form of the word
 * @param {string} [plural] - Plural form (defaults to singular + 's')
 * @returns {string} Formatted string like "3 items" or "1 item"
 */
export function pluralize(count, singular, plural) {
    const word = count === 1 ? singular : (plural || singular + 's');
    return `${count} ${word}`;
}

// =============================================================================
// Loading State Utilities
// =============================================================================

// =============================================================================
// Nav Commit Button
// =============================================================================

export function updateNavCommitButton(changeCount) {
    const btn = document.getElementById('navCommitBtn');
    const gitIndicator = document.getElementById('gitPendingIndicator');

    if (btn) {
        if (changeCount > 0) {
            btn.classList.remove('disabled');
            btn.classList.add('active');
            btn.disabled = false;
            btn.innerHTML = `<span class="commit-count">${changeCount}</span><span class="commit-btn-text">Commit</span>`;
        } else {
            btn.classList.add('disabled');
            btn.classList.remove('active');
            btn.disabled = true;
            btn.innerHTML = '<span class="commit-btn-text">Commit</span>';
        }
    }

    if (gitIndicator) {
        if (changeCount > 0) {
            gitIndicator.textContent = changeCount;
            gitIndicator.classList.remove('u-hidden');
            gitIndicator.classList.add('u-visible-flex');
        } else {
            gitIndicator.classList.add('u-hidden');
            gitIndicator.classList.remove('u-visible-flex');
        }
    }
}

export function updateUndoButton(undoCount) {
    const btn = document.getElementById('navUndoBtn');
    if (!btn) {return;}

    if (undoCount > 0) {
        btn.classList.remove('disabled');
        btn.classList.add('active');
        btn.disabled = false;
        btn.title = `Undo last action (${undoCount} in stack) - Ctrl+Z`;
    } else {
        btn.classList.add('disabled');
        btn.classList.remove('active');
        btn.disabled = true;
        btn.title = 'Nothing to undo';
    }
}

let _undoInProgress = false;  // H-028: Guard against concurrent undo

export async function handleUndoClick() {
    if (explorerCallbacks?.undoLastAction) {
        // Explorer.undoLastAction has its own concurrency guard
        // afterServerSync inside undoLastAction handles badges — no checkPendingChanges needed
        await explorerCallbacks.undoLastAction();
    } else {
        // Fallback: call API directly with concurrency guard
        if (_undoInProgress) {return;}
        _undoInProgress = true;
        try {
            const result = await ApiClient.post('/api/staging/undo', {}, { silent: true });

            if (result.success && result.data?.success) {
                const description = result.data.undone?.description || 'action';
                showToast(`Undone: ${description}`, 'info');
                checkPendingChanges();
                // Reload page to reflect changes
                if (typeof buildTree === 'function') {buildTree();}
            } else if (result.status === 404) {
                showToast('Nothing to undo', 'info');
            } else {
                showToast(result.data?.error || result.error || 'Failed to undo', 'error');
            }
        } finally {
            _undoInProgress = false;
        }
    }
}

// Keyboard Shortcuts Help Dialog
export function showKeyboardShortcuts() {
    const overlay = document.getElementById('keyboardShortcutsOverlay');
    if (overlay) {
        // Update modifier key labels for macOS
        if (navigator.platform && navigator.platform.indexOf('Mac') !== -1) {
            overlay.querySelectorAll('.mod-key').forEach(el => {
                el.textContent = '\u2318';
            });
        }
        overlay.classList.add('visible');
    }
}

export function closeKeyboardShortcuts() {
    const overlay = document.getElementById('keyboardShortcutsOverlay');
    if (overlay) {overlay.classList.remove('visible');}
}

export async function checkPendingChanges() {
    // Use extended staging info to get accurate count of staged changes
    const infoResult = await ApiClient.get('/api/staging/info', { silent: true });

    if (infoResult.success) {
        const info = infoResult.data;
        let count = info.totalCount || 0;
        updateUndoButton(info.undoCount || 0);

        // If no GUI staging, check git for external changes (files modified outside editor)
        if (count === 0) {
            const gitResult = await ApiClient.get('/api/git/status', { silent: true });
            if (gitResult.success && gitResult.data?.has_changes) {
                count = gitResult.data.files.length;
            }
        }

        updateNavCommitButton(count);
        return;
    }

    // Fallback: count from Explorer state if available
    if (explorerCallbacks?.getTotalStagedCount) {
        const count = explorerCallbacks.getTotalStagedCount();
        updateNavCommitButton(count);
        updateUndoButton(explorerCallbacks.getUndoCount ? explorerCallbacks.getUndoCount() : 0);
        return;
    }

    // Last resort: use diff endpoint
    const diffResult = await ApiClient.get('/api/staging/diff', { silent: true });
    const count = (diffResult.data?.gitChanges || []).length;
    updateNavCommitButton(count);
}

export function checkIdentityRequired() {
    const isSettingsPage = window.location.pathname.includes('/settings');
    if (isSettingsPage) {
        return false;
    }

    if (!hasUserIdentity()) {
        document.getElementById('identityRequiredOverlay').classList.add('visible');
        return true;
    }
    return false;
}

// =============================================================================
// Polling
// =============================================================================

function startLockPoll() {
    if (baseState.lockPollInterval) { return; }
    baseState.lockPollInterval = setInterval(async () => {
        await checkLockStatus();
        await checkPendingChanges();
    }, 5000);
}

// =============================================================================
// Initialization
// =============================================================================

/**
 * Action handlers for data-action elements (used by event delegation).
 * Maps action names to handler functions.
 */
export const actionHandlers = {
    'undo': handleUndoClick,
    'commit': handleCommitClick,
    'show-shortcuts': showKeyboardShortcuts,
    'close-shortcuts': closeKeyboardShortcuts,
    'reload-config': reloadConfig,
    'break-lock': breakLock,
    'close-git-result': closeGitResultPanel,
    'close-toast': (e) => e.target.closest('.toast')?.remove()
};

document.addEventListener('DOMContentLoaded', () => {
    // Always check for pending changes and update commit button
    checkPendingChanges();
    checkLockStatus();
    startLockPoll();

    // Check identity - if not set, show popup (but don't block the above checks)
    checkIdentityRequired();

    // Event delegation for data-action elements (replaces inline onclick handlers)
    document.addEventListener('click', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (actionEl) {
            const action = actionEl.dataset.action;
            const handler = actionHandlers[action];
            if (handler) {
                e.preventDefault();
                handler(e);
            }
        }
    });

    // Set up event listeners for overlays (click outside to close)
    const gitResultOverlay = document.getElementById('gitResultOverlay');
    if (gitResultOverlay) {
        gitResultOverlay.addEventListener('click', function(e) {
            if (e.target === this) {
                closeGitResultPanel();
            }
        });
    }

    const globalCommitOverlay = document.getElementById('globalCommitOverlay');
    if (globalCommitOverlay) {
        globalCommitOverlay.addEventListener('click', function(e) {
            if (e.target === this) {
                closeGlobalCommitDialog();
            }
        });
    }

    const keyboardShortcutsOverlay = document.getElementById('keyboardShortcutsOverlay');
    if (keyboardShortcutsOverlay) {
        keyboardShortcutsOverlay.addEventListener('click', function(e) {
            if (e.target === this) {
                closeKeyboardShortcuts();
            }
        });
    }

    // H-005: Check if undo shortcut should fire (not in text input, no dialogs, button enabled)
    function canFireUndo() {
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable)) {
            return false;
        }
        const hasOpenModal = document.querySelector('.modal.show') !== null;
        const hasOpenOverlay = document.querySelector('.confirm-dialog-overlay.visible, .global-commit-overlay.visible, .git-result-panel.visible') !== null;
        if (hasOpenModal || hasOpenOverlay) {return false;}
        const undoBtn = document.getElementById('navUndoBtn');
        return undoBtn && !undoBtn.disabled;
    }

    // Close dialogs on Escape key, Undo on Ctrl+Z, ? for help
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeGlobalCommitDialog();
            closeGitResultPanel();
            closeKeyboardShortcuts();
        }

        // Ctrl+Z (or Cmd+Z on Mac) for undo
        if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey && canFireUndo()) {
            e.preventDefault();
            handleUndoClick();
        }

        // ? key to show keyboard shortcuts help (not when typing in inputs)
        if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
            const activeEl = document.activeElement;
            const isTextInput = activeEl && (
                activeEl.tagName === 'INPUT' ||
                activeEl.tagName === 'TEXTAREA' ||
                activeEl.isContentEditable
            );
            if (!isTextInput) {
                e.preventDefault();
                showKeyboardShortcuts();
            }
        }
    });
});
