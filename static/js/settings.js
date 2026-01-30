// Settings page JavaScript
// Extracted from settings.html

let browseTargetField = null;
let browseMode = 'dir';
let currentBrowsePath = '/';

// =============================================================================
// Path Validation (C-03: Client-side feedback for invalid paths)
// =============================================================================

/**
 * Validate a file system path for security issues.
 * Provides client-side feedback before sending to server.
 *
 * @param {string} path - The path to validate
 * @param {string} fieldName - Human-readable field name for error messages
 * @returns {{valid: boolean, error: string|null}} Validation result
 */
function validatePath(path, fieldName) {
    if (!path || path.trim() === '') {
        return { valid: true, error: null }; // Empty paths are allowed (will use defaults)
    }

    path = path.trim();

    // Check for null byte injection
    if (path.includes('\0')) {
        return {
            valid: false,
            error: `${fieldName}: Path contains invalid null character`
        };
    }

    // Check for path traversal attempts
    // Split by both forward and back slashes to handle cross-platform paths
    const segments = path.split(/[/\\]/);
    for (const segment of segments) {
        if (segment === '..') {
            return {
                valid: false,
                error: `${fieldName}: Path traversal (..) is not allowed`
            };
        }
    }

    // Check for other potentially dangerous patterns
    // Control characters (except common whitespace)
    if (/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/.test(path)) {
        return {
            valid: false,
            error: `${fieldName}: Path contains invalid control characters`
        };
    }

    return { valid: true, error: null };
}

/**
 * Validate all path fields before saving.
 * @returns {{valid: boolean, errors: string[]}} Validation result with all errors
 */
function validateAllPaths() {
    const errors = [];

    const pathFields = [
        { id: 'nagiosConfigPath', name: 'Nagios Config Path' },
        { id: 'backupPath', name: 'Backup Path' },
        { id: 'nagiosBin', name: 'Nagios Binary' },
        { id: 'nagiosCfg', name: 'Nagios Config File' }
    ];

    for (const field of pathFields) {
        const el = document.getElementById(field.id);
        if (el) {
            const result = validatePath(el.value, field.name);
            if (!result.valid) {
                errors.push(result.error);
                // Highlight the invalid field
                el.classList.add('is-invalid');
            } else {
                el.classList.remove('is-invalid');
            }
        }
    }

    return { valid: errors.length === 0, errors };
}

document.addEventListener('DOMContentLoaded', () => {
    refreshStatus();
    loadGitIdentity();
    loadLoggingSettings();
    restoreActiveTab();

    // C-03: Real-time path validation as user types
    const pathFields = ['nagiosConfigPath', 'backupPath', 'nagiosBin', 'nagiosCfg'];
    const fieldNames = {
        'nagiosConfigPath': 'Nagios Config Path',
        'backupPath': 'Backup Path',
        'nagiosBin': 'Nagios Binary',
        'nagiosCfg': 'Nagios Config File'
    };

    pathFields.forEach(fieldId => {
        const el = document.getElementById(fieldId);
        if (el) {
            el.addEventListener('input', function() {
                const result = validatePath(this.value, fieldNames[fieldId]);
                if (!result.valid) {
                    this.classList.add('is-invalid');
                    // Show inline error if there's a feedback element
                    const feedback = this.nextElementSibling;
                    if (feedback && feedback.classList.contains('invalid-feedback')) {
                        feedback.textContent = result.error;
                    }
                } else {
                    this.classList.remove('is-invalid');
                }
            });
        }
    });

    // Event delegation for data-action elements
    document.addEventListener('click', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;

        const action = actionEl.dataset.action;
        if (action === 'browseDir') {
            const target = actionEl.dataset.target;
            if (target) browseDir(target);
        } else if (action === 'browseFile') {
            const target = actionEl.dataset.target;
            if (target) browseFile(target);
        } else if (action === 'downloadLog') {
            downloadLog();
        } else if (action === 'saveIdentity') {
            saveIdentity();
        } else if (action === 'saveServerSettings') {
            saveServerSettings();
        } else if (action === 'saveSettings') {
            saveSettings();  // Legacy - kept for backwards compatibility
        } else if (action === 'resetToDefaults') {
            resetToDefaults();
        } else if (action === 'navigateTo') {
            navigateTo();
        } else if (action === 'selectPath') {
            selectPath();
        } else if (action === 'switchTab') {
            const tab = actionEl.dataset.tab;
            if (tab) switchTab(tab);
        }
    });
});

// Called by base.html when lock is broken
function onLockCleared() {
    loadGitIdentity();
}

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.nbe-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });

    // Update tab content
    document.querySelectorAll('.nbe-tab-content').forEach(content => {
        content.classList.remove('active');
    });

    const targetContent = document.getElementById(tabName + 'Tab');
    if (targetContent) {
        targetContent.classList.add('active');
    }

    // Save preference
    try {
        localStorage.setItem('settings_active_tab', tabName);
    } catch (e) {
        // Ignore localStorage errors
    }
}

function restoreActiveTab() {
    try {
        const savedTab = localStorage.getItem('settings_active_tab');
        if (savedTab) {
            switchTab(savedTab);
        }
    } catch (e) {
        // Ignore localStorage errors
    }
}

async function refreshStatus() {
    const result = await ApiClient.get('/api/summary', { silent: true });

    if (result.success) {
        document.getElementById('statusContent').innerHTML = `
            <table class="settings-status-table">
                <tr><td>Config Path</td><td>${escapeHtml(document.getElementById('nagiosConfigPath').value)}</td></tr>
                <tr><td>Objects</td><td><strong>${result.data.total_objects}</strong></td></tr>
                <tr><td>Config Files</td><td><strong>${result.data.files.length}</strong></td></tr>
            </table>
        `;
    } else {
        document.getElementById('statusContent').innerHTML =
            `<div class="settings-empty" style="color:#dc3545">Error: ${escapeHtml(result.error)}</div>`;
    }
}

async function saveIdentity() {
    // Validate identity fields
    const userName = document.getElementById('gitUserName').value.trim();
    const userEmail = document.getElementById('gitUserEmail').value.trim();

    if (!userName || !userEmail) {
        showToast('Please enter your name and email', 'error');
        if (!userName) document.getElementById('gitUserName').focus();
        else document.getElementById('gitUserEmail').focus();
        return;
    }

    // Basic email validation
    if (!userEmail.includes('@') || !userEmail.includes('.')) {
        showToast('Please enter a valid email address', 'error');
        document.getElementById('gitUserEmail').focus();
        return;
    }

    // Save identity to localStorage (browser-only)
    setUserIdentity(userName, userEmail);

    // Update identity badge
    const badge = document.getElementById('gitIdentityBadge');
    const info = document.getElementById('gitIdentityInfo');
    badge.textContent = 'Set';
    badge.className = 'nbe-tab-badge nbe-tab-badge--success';
    info.textContent = 'Your identity is configured and saved to this browser.';
    info.style.color = 'var(--color-create)';

    // Also update staging data if we have the lock
    const lockResult = await ApiClient.get('/api/staging/lock', { silent: true });
    if (lockResult.success && lockResult.data.locked && lockResult.data.isOwner) {
        await ApiClient.post('/api/git/identity', {
            user_name: userName,
            user_email: userEmail
        }, { silent: true });
    }

    showToast('Identity saved to this browser', 'success');
}

async function saveServerSettings() {
    // Check if locked by another user - server settings should not be saved
    const lockResult = await ApiClient.get('/api/staging/lock', { silent: true });
    if (lockResult.success && lockResult.data.locked && !lockResult.data.isOwner) {
        showToast('Cannot save server settings while another user has pending changes', 'error');
        return;
    }

    // C-03: Client-side path validation before sending to server
    const validation = validateAllPaths();
    if (!validation.valid) {
        showToast('Invalid path: ' + validation.errors[0], 'error');
        return;
    }

    // Save server settings (config paths)
    const settings = {
        nagios_config_path: document.getElementById('nagiosConfigPath').value,
        backup_path: document.getElementById('backupPath').value || null,
        nagios_bin: document.getElementById('nagiosBin').value,
        nagios_cfg: document.getElementById('nagiosCfg').value
    };

    const result = await ApiClient.post('/api/settings', settings, { silent: true });

    if (result.success && result.data.success) {
        const savedItems = [];
        if (result.data.updated && result.data.updated.length > 0) {
            savedItems.push(...result.data.updated);
        }
        if (savedItems.length > 0) {
            showToast('Server settings saved: ' + savedItems.join(', '), 'success');
        } else {
            showToast('Server settings unchanged', 'info');
        }
        refreshStatus();
    } else {
        const errors = result.data?.errors || [result.error];
        showToast('Error saving server settings: ' + errors.join(', '), 'error');
    }

    // Save logging settings
    await saveLoggingSettings();
}

// Legacy function for backwards compatibility
async function saveSettings() {
    await saveIdentity();
    await saveServerSettings();
}

function resetToDefaults() {
    document.getElementById('nagiosConfigPath').value = './sample-config';
    document.getElementById('backupPath').value = '';
    document.getElementById('nagiosBin').value = '/usr/local/nagios/bin/nagios';
    document.getElementById('nagiosCfg').value = './sample-config/nagios.cfg';
    showToast('Settings reset to defaults (not saved yet)', 'info');
}

function browseDir(fieldId) {
    browseTargetField = fieldId;
    browseMode = 'dir';
    const currentValue = document.getElementById(fieldId).value || '/';
    openBrowser(currentValue);
}

function browseFile(fieldId) {
    browseTargetField = fieldId;
    browseMode = 'file';
    const currentValue = document.getElementById(fieldId).value;
    const startPath = currentValue ? currentValue.substring(0, currentValue.lastIndexOf('/')) || '/' : '/';
    openBrowser(startPath);
}

function openBrowser(path) {
    currentBrowsePath = path;
    document.getElementById('browsePath').value = path;
    loadDirectory(path);
    new bootstrap.Modal(document.getElementById('browseModal')).show();
}

async function loadDirectory(path) {
    const result = await ApiClient.post('/api/settings/browse', { path }, { silent: true });

    if (!result.success || result.data?.error) {
        document.getElementById('browseContent').innerHTML =
            `<p class="text-danger">${escapeHtml(result.data?.error || result.error)}</p>`;
        return;
    }

    currentBrowsePath = result.data.path;
    document.getElementById('browsePath').value = result.data.path;

    let html = '<div class="list-group">';

    if (result.data.parent) {
        html += `
            <a href="#" class="list-group-item list-group-item-action" onclick="loadDirectory('${escapeJs(result.data.parent)}'); return false;">
                <i class="text-muted">..</i> (parent directory)
            </a>
        `;
    }

    for (const entry of result.data.entries) {
        if (entry.is_dir) {
            html += `
                <a href="#" class="list-group-item list-group-item-action" onclick="loadDirectory('${escapeJs(entry.path)}'); return false;">
                    <strong>${escapeHtml(entry.name)}/</strong>
                </a>
            `;
        } else if (browseMode === 'file') {
            html += `
                <a href="#" class="list-group-item list-group-item-action" onclick="selectFile('${escapeJs(entry.path)}'); return false;">
                    ${escapeHtml(entry.name)}
                </a>
            `;
        }
    }

    if (result.data.entries.length === 0) {
        html += '<p class="text-muted p-3">Empty directory</p>';
    }

    html += '</div>';
    document.getElementById('browseContent').innerHTML = html;
}

function navigateTo() {
    const path = document.getElementById('browsePath').value;
    loadDirectory(path);
}

function selectPath() {
    if (browseTargetField) {
        document.getElementById(browseTargetField).value = currentBrowsePath;
    }
    bootstrap.Modal.getInstance(document.getElementById('browseModal')).hide();
}

function selectFile(path) {
    if (browseTargetField) {
        document.getElementById(browseTargetField).value = path;
    }
    bootstrap.Modal.getInstance(document.getElementById('browseModal')).hide();
}

async function loadGitIdentity() {
    const badge = document.getElementById('gitIdentityBadge');
    const info = document.getElementById('gitIdentityInfo');
    const nameInput = document.getElementById('gitUserName');
    const emailInput = document.getElementById('gitUserEmail');

    // Load identity from localStorage (each browser has its own)
    const identity = getUserIdentity();
    nameInput.value = identity.userName || '';
    emailInput.value = identity.userEmail || '';

    if (identity.userName && identity.userEmail) {
        badge.textContent = 'Set';
        badge.className = 'nbe-tab-badge nbe-tab-badge--success';
        info.textContent = 'Your identity is configured and stored in this browser.';
        info.style.color = 'var(--color-create)';
    } else {
        badge.textContent = 'Not Set';
        badge.className = 'nbe-tab-badge nbe-tab-badge--warning';
        info.textContent = 'Please set your name and email. This is required to use the application.';
        info.style.color = '';
    }

    // Check if another user has the lock - show their info
    const lockResult = await ApiClient.get('/api/staging/lock', { silent: true });

    if (lockResult.success && lockResult.data.locked && !lockResult.data.isOwner) {
        let lockedBy = lockResult.data.userName || 'Another user';
        if (lockResult.data.userEmail) {
            lockedBy += ` (${lockResult.data.userEmail})`;
        }
        info.innerHTML = `<strong>${escapeHtml(lockedBy)}</strong> has pending changes. You can still set your own identity.`;
        info.style.color = 'var(--color-edit)';
    }
}

// ============================================================================
// Logging Settings
// ============================================================================

async function loadLoggingSettings() {
    const result = await ApiClient.get('/api/settings/logging', { silent: true });
    if (!result.success) return;

    const data = result.data;
    document.getElementById('loggingEnabled').checked = data.enabled;
    document.getElementById('loggingLevel').value = data.log_level || 'INFO';
    document.getElementById('loggingMaxSize').value = data.max_file_size_mb || 10;
    document.getElementById('loggingMaxBackups').value = data.max_backup_files || 5;
    document.getElementById('loggingFilePath').value = data.log_file_path || '';

    const sizeKB = (data.log_file_size / 1024).toFixed(1);
    document.getElementById('loggingFileSize').textContent =
        data.log_file_size > 0 ? `File size: ${sizeKB} KB` : 'File size: empty';
}

async function saveLoggingSettings() {
    const settings = {
        enabled: document.getElementById('loggingEnabled').checked,
        log_level: document.getElementById('loggingLevel').value,
        max_file_size_mb: parseInt(document.getElementById('loggingMaxSize').value) || 10,
        max_backup_files: parseInt(document.getElementById('loggingMaxBackups').value) || 5
    };

    const result = await ApiClient.post('/api/settings/logging', settings, { silent: true });
    if (!result.success || !result.data?.success) {
        showToast('Failed to save logging settings', 'error');
    }
}

function downloadLog() {
    window.location.href = '/api/logs/operations/download';
}
