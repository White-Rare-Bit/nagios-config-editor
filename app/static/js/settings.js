// Settings page
import { ApiClient } from './api-client.js';
import { showToast } from './ui-notifications.js';
import { escapeHtml } from './app.js';
import { getUserIdentity, setUserIdentity } from './session-manager.js';

let browseTargetField = null;
    let browseMode = 'dir';
    let currentBrowsePath = '/';

// Path field configuration - used for validation and real-time feedback
const PATH_FIELDS = [
    { id: 'backupPath', name: 'Backup Path' },
    { id: 'nagiosBin', name: 'Nagios Binary' },
    { id: 'nagiosCfg', name: 'Nagios Config File' }
];

// Current extra_cfg_dirs for managing add/remove
let currentExtraDirs = [];

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

    const trimmedPath = path.trim();

    // Check for null byte injection
    if (trimmedPath.includes('\0')) {
        return {
            valid: false,
            error: `${fieldName}: Path contains invalid null character`
        };
    }

    // Check for path traversal attempts
    // Split by both forward and back slashes to handle cross-platform paths
    const segments = trimmedPath.split(/[/\\]/);
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
    if (/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/.test(trimmedPath)) {
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

    for (const field of PATH_FIELDS) {
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
    loadServerSettings();
    refreshStatus();
    loadGitIdentity();
    loadLoggingSettings();
    restoreActiveTab();

    // C-03: Real-time path validation as user types
    PATH_FIELDS.forEach(field => {
        const el = document.getElementById(field.id);
        if (el) {
            el.addEventListener('input', function() {
                const result = validatePath(this.value, field.name);
                if (!result.valid) {
                    this.classList.add('is-invalid');
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
        if (!actionEl) {return;}

        e.preventDefault();
        const action = actionEl.dataset.action;
        if (action === 'browseDir') {
            const target = actionEl.dataset.target;
            if (target) {browseDir(target);}
        } else if (action === 'browseFile') {
            const target = actionEl.dataset.target;
            if (target) {browseFile(target);}
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
        } else if (action === 'closeBrowse') {
            closeBrowse();
        } else if (action === 'switchTab') {
            const tab = actionEl.dataset.tab;
            if (tab) {switchTab(tab);}
        } else if (action === 'addExtraDir') {
            addExtraDir();
        } else if (action === 'removeExtraDir') {
            const idx = parseInt(actionEl.dataset.index, 10);
            removeExtraDir(idx);
        } else if (action === 'loadDirectory') {
            const path = actionEl.dataset.path;
            if (path) {loadDirectory(path);}
        } else if (action === 'selectFile') {
            const path = actionEl.dataset.path;
            if (path) {selectFile(path);}
        }
    });

    // Close browse dialog on backdrop click
    document.getElementById('browseOverlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) {closeBrowse();}
    });
});

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
        const nagiosCfg = document.getElementById('nagiosCfg')?.value || '';
        document.getElementById('statusContent').innerHTML = `
            <table class="settings-status-table">
                <tr><td>nagios.cfg</td><td>${escapeHtml(nagiosCfg || '(not set)')}</td></tr>
                <tr><td>Objects</td><td><strong>${result.data.total_objects}</strong></td></tr>
                <tr><td>Config Files</td><td><strong>${result.data.files.length}</strong></td></tr>
            </table>
        `;
    } else {
        document.getElementById('statusContent').innerHTML =
            `<div class="settings-empty" style="color:#dc3545">Error: ${escapeHtml(result.error)}</div>`;
    }
}

async function loadServerSettings() {
    const result = await ApiClient.get('/api/settings', { silent: true });
    if (!result.success) return;

    const data = result.data;
    const paths = data.paths || {};
    const discovered = data.discovered || {};

    // Populate path fields
    const nagiosCfg = document.getElementById('nagiosCfg');
    if (nagiosCfg) nagiosCfg.value = paths.nagios_cfg || '';
    const nagiosBin = document.getElementById('nagiosBin');
    if (nagiosBin) nagiosBin.value = paths.nagios_bin || '';
    const backupPath = document.getElementById('backupPath');
    if (backupPath) backupPath.value = paths.backup_path || '';
    const resourceCfg = document.getElementById('resourceCfg');
    if (resourceCfg) resourceCfg.value = discovered.resource_file || paths.resource_cfg || '';

    // Populate discovered directories
    renderDiscoveredDirs(discovered.cfg_dirs || []);

    // Populate extra dirs
    currentExtraDirs = paths.extra_cfg_dirs || [];
    renderExtraDirs();

    // Populate primary dir dropdown
    const allDirs = (discovered.cfg_dirs || [])
        .filter(d => d.accessible)
        .map(d => d.path);
    const extraDirs = paths.extra_cfg_dirs || [];
    const allOptions = [...new Set([...allDirs, ...extraDirs])];
    const primarySelect = document.getElementById('primaryDir');
    if (primarySelect) {
        primarySelect.innerHTML = '<option value="">Auto (first discovered)</option>';
        for (const dir of allOptions) {
            const opt = document.createElement('option');
            opt.value = dir;
            opt.textContent = dir;
            if (dir === paths.primary_dir) opt.selected = true;
            primarySelect.appendChild(opt);
        }
    }
}

function renderDiscoveredDirs(dirs) {
    const container = document.getElementById('discoveredDirs');
    if (!container) return;

    if (!dirs.length) {
        container.innerHTML = '<span class="settings-empty">No directories discovered (set nagios.cfg path)</span>';
        return;
    }

    container.innerHTML = dirs.map(d => {
        const statusClass = d.accessible ? 'settings-dir-ok' : 'settings-dir-error';
        const icon = d.accessible ? '&#x2713;' : '&#x2717;';
        const error = d.error ? ` &mdash; <span class="settings-dir-error-text">${escapeHtml(d.error)}</span>` : '';
        return `<div class="${statusClass}">${icon} ${escapeHtml(d.path)}${error}</div>`;
    }).join('');
}

function renderExtraDirs() {
    const container = document.getElementById('extraCfgDirs');
    if (!container) return;

    if (!currentExtraDirs.length) {
        container.innerHTML = '<span class="settings-empty">None</span>';
        return;
    }

    container.innerHTML = currentExtraDirs.map((dir, i) =>
        `<div class="settings-extra-dir-item">
            <span>${escapeHtml(dir)}</span>
            <button class="nbe-btn nbe-btn--dark nbe-btn--outlined nbe-btn--xs" data-action="removeExtraDir" data-index="${i}">&times;</button>
        </div>`
    ).join('');
}

function addExtraDir() {
    const input = document.getElementById('newExtraDir');
    const dir = input?.value?.trim();
    if (!dir) return;
    if (currentExtraDirs.includes(dir)) {
        showToast('Directory already added', 'info');
        return;
    }
    currentExtraDirs.push(dir);
    input.value = '';
    renderExtraDirs();
}

function removeExtraDir(index) {
    currentExtraDirs.splice(index, 1);
    renderExtraDirs();
}

async function saveIdentity() {
    // Validate identity fields
    const userName = document.getElementById('gitUserName').value.trim();
    const userEmail = document.getElementById('gitUserEmail').value.trim();

    if (!userName || !userEmail) {
        showToast('Please enter your name and email', 'error');
        if (!userName) {document.getElementById('gitUserName').focus();}
        else {document.getElementById('gitUserEmail').focus();}
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

    showToast('Identity saved to this browser', 'success');
}

async function saveServerSettings() {
    // C-03: Client-side path validation before sending to server
    const validation = validateAllPaths();
    if (!validation.valid) {
        showToast('Invalid path: ' + validation.errors[0], 'error');
        return;
    }

    // Save server settings (config paths)
    const primaryDir = document.getElementById('primaryDir')?.value || '';
    const settings = {
        paths: {
            nagios_cfg: document.getElementById('nagiosCfg').value,
            nagios_bin: document.getElementById('nagiosBin').value,
            backup_path: document.getElementById('backupPath').value || null,
            extra_cfg_dirs: currentExtraDirs,
            primary_dir: primaryDir,
        }
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
        if (result.data.git_initialized) {
            showToast('Git repository initialized in config directory', 'success');
        }
        refreshStatus();
    } else {
        const errors = result.data?.errors || [result.error];
        showToast('Error saving server settings: ' + errors.join(', '), 'error');
    }

    // Save logging settings
    await saveLoggingSettings();
}

function resetToDefaults() {
    document.getElementById('nagiosCfg').value = '';
    document.getElementById('backupPath').value = '';
    document.getElementById('nagiosBin').value = '/usr/local/nagios/bin/nagios';
    currentExtraDirs = [];
    renderExtraDirs();
    const primarySelect = document.getElementById('primaryDir');
    if (primarySelect) primarySelect.value = '';
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
    document.getElementById('browseOverlay').classList.add('visible');
}

function closeBrowse() {
    document.getElementById('browseOverlay').classList.remove('visible');
}

const BROWSE_ICONS = {
    folder: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>',
    file: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>',
    parent: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>'
};

async function loadDirectory(path) {
    const container = document.getElementById('browseContent');

    // Show loading state
    container.innerHTML = '<p class="browse-empty">Loading...</p>';

    const result = await ApiClient.post('/api/settings/browse', { path }, { silent: true });

    if (!result.success || result.data?.error) {
        container.innerHTML =
            `<p class="browse-empty" style="color: var(--nbe-danger)">${escapeHtml(result.data?.error || result.error)}</p>`;
        return;
    }

    currentBrowsePath = result.data.path;
    document.getElementById('browsePath').value = result.data.path;

    let html = '';

    if (result.data.parent) {
        html += `<a href="#" class="browse-tree-row" data-action="loadDirectory" data-path="${escapeHtml(result.data.parent)}">
            <span class="browse-tree-icon browse-tree-icon--parent">${BROWSE_ICONS.parent}</span>
            <span class="browse-tree-label">..</span>
        </a>`;
    }

    for (const entry of result.data.entries) {
        if (entry.is_dir) {
            html += `<a href="#" class="browse-tree-row" data-action="loadDirectory" data-path="${escapeHtml(entry.path)}">
                <span class="browse-tree-icon browse-tree-icon--folder">${BROWSE_ICONS.folder}</span>
                <span class="browse-tree-label browse-tree-label--folder">${escapeHtml(entry.name)}</span>
            </a>`;
        } else if (browseMode === 'file') {
            html += `<a href="#" class="browse-tree-row" data-action="selectFile" data-path="${escapeHtml(entry.path)}">
                <span class="browse-tree-icon browse-tree-icon--file">${BROWSE_ICONS.file}</span>
                <span class="browse-tree-label">${escapeHtml(entry.name)}</span>
            </a>`;
        }
    }

    if (result.data.entries.length === 0) {
        html += '<p class="browse-empty">Empty directory</p>';
    }

    container.innerHTML = html;
}

function navigateTo() {
    const path = document.getElementById('browsePath').value;
    loadDirectory(path);
}

function selectPath() {
    if (browseTargetField) {
        document.getElementById(browseTargetField).value = currentBrowsePath;
    }
    closeBrowse();
}

function selectFile(path) {
    if (browseTargetField) {
        document.getElementById(browseTargetField).value = path;
    }
    closeBrowse();
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

}

// ============================================================================
// Logging Settings
// ============================================================================

async function loadLoggingSettings() {
    const result = await ApiClient.get('/api/settings/logging', { silent: true });
    if (!result.success) {
        console.warn('Failed to load logging settings:', result.error);
        return;
    }

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
        max_file_size_mb: parseInt(document.getElementById('loggingMaxSize').value, 10) || 10,
        max_backup_files: parseInt(document.getElementById('loggingMaxBackups').value, 10) || 5
    };

    const result = await ApiClient.post('/api/settings/logging', settings, { silent: true });
    if (!result.success || !result.data?.success) {
        showToast('Failed to save logging settings', 'error');
    }
}

function downloadLog() {
    window.location.href = '/api/logs/operations/download';
}
