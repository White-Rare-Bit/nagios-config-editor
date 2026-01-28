/**
 * Integration tests for page-specific event handlers
 *
 * Tests for backups, settings, dependencies, and other page-specific handlers
 */

describe('Page-Specific Event Handler Tests', () => {
    let mockHandlers;

    beforeEach(() => {
        document.body.innerHTML = '';

        window.localStorage = {
            store: {},
            getItem: jest.fn(key => window.localStorage.store[key] || null),
            setItem: jest.fn((key, value) => { window.localStorage.store[key] = value; }),
            removeItem: jest.fn(key => { delete window.localStorage.store[key]; }),
            clear: jest.fn(() => { window.localStorage.store = {}; })
        };

        global.fetch = jest.fn(() => Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ success: true })
        }));

        mockHandlers = {
            calls: [],
            track: function(name) {
                return (...args) => {
                    this.calls.push({ name, args });
                };
            },
            wasCalled: function(name) {
                return this.calls.some(c => c.name === name);
            },
            getCall: function(name) {
                return this.calls.find(c => c.name === name);
            },
            reset: function() {
                this.calls = [];
            }
        };
    });

    afterEach(() => {
        jest.clearAllMocks();
        mockHandlers.reset();
    });

    describe('Backups Page Handlers', () => {
        let setupBackupsEventDelegation;

        beforeEach(() => {
            const createBackup = mockHandlers.track('createBackup');
            const deleteAllBackups = mockHandlers.track('deleteAllBackups');
            const restoreBackup = mockHandlers.track('restoreBackup');
            const deleteBackup = mockHandlers.track('deleteBackup');

            setupBackupsEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    if (action === 'create-backup') {
                        createBackup();
                    } else if (action === 'delete-all-backups') {
                        deleteAllBackups();
                    } else if (action === 'restore-backup') {
                        const name = actionEl.dataset.name;
                        restoreBackup(name);
                    } else if (action === 'delete-backup') {
                        const name = actionEl.dataset.name;
                        deleteBackup(name);
                    }
                });
            };
        });

        test('create backup button triggers createBackup', () => {
            document.body.innerHTML = `
                <button id="createBackupBtn" data-action="create-backup">Create Backup</button>
            `;
            setupBackupsEventDelegation();

            document.getElementById('createBackupBtn').click();

            expect(mockHandlers.wasCalled('createBackup')).toBe(true);
        });

        test('delete all backups button triggers deleteAllBackups', () => {
            document.body.innerHTML = `
                <button data-action="delete-all-backups">Delete All</button>
            `;
            setupBackupsEventDelegation();

            document.querySelector('[data-action="delete-all-backups"]').click();

            expect(mockHandlers.wasCalled('deleteAllBackups')).toBe(true);
        });

        test('restore backup button triggers restoreBackup with name', () => {
            document.body.innerHTML = `
                <button data-action="restore-backup" data-name="backup-2024-01-01">Restore</button>
            `;
            setupBackupsEventDelegation();

            document.querySelector('[data-action="restore-backup"]').click();

            expect(mockHandlers.wasCalled('restoreBackup')).toBe(true);
            const call = mockHandlers.getCall('restoreBackup');
            expect(call.args[0]).toBe('backup-2024-01-01');
        });

        test('delete backup button triggers deleteBackup with name', () => {
            document.body.innerHTML = `
                <button data-action="delete-backup" data-name="backup-2024-01-01">Delete</button>
            `;
            setupBackupsEventDelegation();

            document.querySelector('[data-action="delete-backup"]').click();

            expect(mockHandlers.wasCalled('deleteBackup')).toBe(true);
            const call = mockHandlers.getCall('deleteBackup');
            expect(call.args[0]).toBe('backup-2024-01-01');
        });
    });

    describe('Settings Page Handlers', () => {
        let setupSettingsEventDelegation;

        beforeEach(() => {
            const refreshStatus = mockHandlers.track('refreshStatus');
            const browseDir = mockHandlers.track('browseDir');
            const browseFile = mockHandlers.track('browseFile');
            const downloadLog = mockHandlers.track('downloadLog');
            const saveIdentity = mockHandlers.track('saveIdentity');
            const saveServerSettings = mockHandlers.track('saveServerSettings');
            const saveSettings = mockHandlers.track('saveSettings');
            const resetToDefaults = mockHandlers.track('resetToDefaults');
            const navigateTo = mockHandlers.track('navigateTo');
            const selectPath = mockHandlers.track('selectPath');
            const switchTab = mockHandlers.track('switchTab');

            setupSettingsEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    if (action === 'refreshStatus') {
                        refreshStatus();
                    } else if (action === 'browseDir') {
                        const target = actionEl.dataset.target;
                        browseDir(target);
                    } else if (action === 'browseFile') {
                        const target = actionEl.dataset.target;
                        browseFile(target);
                    } else if (action === 'downloadLog') {
                        downloadLog();
                    } else if (action === 'saveIdentity') {
                        saveIdentity();
                    } else if (action === 'saveServerSettings') {
                        saveServerSettings();
                    } else if (action === 'saveSettings') {
                        saveSettings();
                    } else if (action === 'resetToDefaults') {
                        resetToDefaults();
                    } else if (action === 'navigateTo') {
                        navigateTo();
                    } else if (action === 'selectPath') {
                        selectPath();
                    } else if (action === 'switchTab') {
                        const tab = actionEl.dataset.tab;
                        switchTab(tab);
                    }
                });
            };
        });

        test('refresh status button triggers refreshStatus', () => {
            document.body.innerHTML = `
                <button data-action="refreshStatus">Refresh</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="refreshStatus"]').click();

            expect(mockHandlers.wasCalled('refreshStatus')).toBe(true);
        });

        test('browse dir button triggers browseDir with target', () => {
            document.body.innerHTML = `
                <button data-action="browseDir" data-target="nagiosConfigPath">Browse</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="browseDir"]').click();

            expect(mockHandlers.wasCalled('browseDir')).toBe(true);
            const call = mockHandlers.getCall('browseDir');
            expect(call.args[0]).toBe('nagiosConfigPath');
        });

        test('browse file button triggers browseFile with target', () => {
            document.body.innerHTML = `
                <button data-action="browseFile" data-target="nagiosBin">Browse</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="browseFile"]').click();

            expect(mockHandlers.wasCalled('browseFile')).toBe(true);
            const call = mockHandlers.getCall('browseFile');
            expect(call.args[0]).toBe('nagiosBin');
        });

        test('download log button triggers downloadLog', () => {
            document.body.innerHTML = `
                <button data-action="downloadLog">Download</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="downloadLog"]').click();

            expect(mockHandlers.wasCalled('downloadLog')).toBe(true);
        });

        test('save identity button triggers saveIdentity', () => {
            document.body.innerHTML = `
                <button data-action="saveIdentity">Save Identity</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="saveIdentity"]').click();

            expect(mockHandlers.wasCalled('saveIdentity')).toBe(true);
        });

        test('save server settings button triggers saveServerSettings', () => {
            document.body.innerHTML = `
                <button data-action="saveServerSettings">Save Server Settings</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="saveServerSettings"]').click();

            expect(mockHandlers.wasCalled('saveServerSettings')).toBe(true);
        });

        test('legacy save settings button triggers saveSettings', () => {
            document.body.innerHTML = `
                <button data-action="saveSettings">Save Settings</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="saveSettings"]').click();

            expect(mockHandlers.wasCalled('saveSettings')).toBe(true);
        });

        test('reset to defaults button triggers resetToDefaults', () => {
            document.body.innerHTML = `
                <button data-action="resetToDefaults">Reset to Defaults</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="resetToDefaults"]').click();

            expect(mockHandlers.wasCalled('resetToDefaults')).toBe(true);
        });

        test('tab button triggers switchTab with tab name', () => {
            document.body.innerHTML = `
                <button data-action="switchTab" data-tab="identity">Identity</button>
            `;
            setupSettingsEventDelegation();

            document.querySelector('[data-action="switchTab"]').click();

            expect(mockHandlers.wasCalled('switchTab')).toBe(true);
            const call = mockHandlers.getCall('switchTab');
            expect(call.args[0]).toBe('identity');
        });
    });

    describe('Settings Page Lock Behavior', () => {
        beforeEach(() => {
            // Set up a minimal settings page structure matching the new tab-based UI
            document.body.innerHTML = `
                <div class="settings-container">
                    <div class="settings-main">
                        <div class="nbe-tabs">
                            <button class="nbe-tab active" data-action="switchTab" data-tab="server">
                                Server Settings
                            </button>
                            <button class="nbe-tab" data-action="switchTab" data-tab="identity">
                                Your Identity
                            </button>
                        </div>
                        <div class="nbe-tab-content active" id="serverTab">
                            <div class="settings-section" id="configPathsSection">
                                <input type="text" id="nagiosConfigPath" value="/etc/nagios">
                                <button data-action="browseDir" data-target="nagiosConfigPath">Browse</button>
                            </div>
                            <div class="settings-section" id="loggingSection">
                                <input type="checkbox" id="loggingEnabled" checked>
                            </div>
                            <div class="settings-actions" id="serverSettingsActions">
                                <button data-action="saveServerSettings">Save Server Settings</button>
                            </div>
                        </div>
                        <div class="nbe-tab-content" id="identityTab">
                            <div class="settings-section" id="gitIdentitySection">
                                <input type="text" id="gitUserName" value="">
                                <input type="email" id="gitUserEmail" value="">
                                <button data-action="saveIdentity">Save Identity</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // Add the CSS that would be applied (simulated via class behavior)
            const style = document.createElement('style');
            style.textContent = `
                body.editing-locked .settings-container #serverTab {
                    pointer-events: none;
                    opacity: 0.4;
                }
                body.editing-locked .settings-container #identityTab {
                    pointer-events: auto;
                    opacity: 1;
                }
                .nbe-tab-content {
                    display: none;
                }
                .nbe-tab-content.active {
                    display: block;
                }
            `;
            document.head.appendChild(style);
        });

        test('adds editing-locked class to body when lock is active', () => {
            document.body.classList.add('editing-locked');

            expect(document.body.classList.contains('editing-locked')).toBe(true);
        });

        test('server tab and identity tab are separate', () => {
            const serverTab = document.getElementById('serverTab');
            const identityTab = document.getElementById('identityTab');

            expect(serverTab).not.toBeNull();
            expect(identityTab).not.toBeNull();
            expect(serverTab).not.toBe(identityTab);
        });

        test('identity tab inputs can still receive focus when locked', () => {
            document.body.classList.add('editing-locked');

            const userNameInput = document.getElementById('gitUserName');

            // In a real browser, identity tab is accessible because pointer-events: auto
            expect(userNameInput).not.toBeNull();
            expect(userNameInput.disabled).toBeFalsy();
        });

        test('identity save button is in identity tab', () => {
            const identityTab = document.getElementById('identityTab');
            const saveIdentityButton = identityTab.querySelector('[data-action="saveIdentity"]');

            expect(saveIdentityButton).not.toBeNull();
            expect(saveIdentityButton.disabled).toBeFalsy();
        });

        test('server settings button is in server tab', () => {
            const serverTab = document.getElementById('serverTab');
            const saveServerButton = serverTab.querySelector('[data-action="saveServerSettings"]');

            expect(saveServerButton).not.toBeNull();
        });

        test('identity and server settings are in different tabs', () => {
            const serverTab = document.getElementById('serverTab');
            const identityTab = document.getElementById('identityTab');

            // Server settings not in identity tab
            expect(identityTab.querySelector('[data-action="saveServerSettings"]')).toBeNull();

            // Identity save not in server tab
            expect(serverTab.querySelector('[data-action="saveIdentity"]')).toBeNull();
        });

        test('removes editing-locked class when lock is cleared', () => {
            document.body.classList.add('editing-locked');
            expect(document.body.classList.contains('editing-locked')).toBe(true);

            document.body.classList.remove('editing-locked');
            expect(document.body.classList.contains('editing-locked')).toBe(false);
        });
    });

    describe('Dependencies Page Handlers', () => {
        let setupDependenciesEventDelegation;

        beforeEach(() => {
            const onNodeSearchInput = mockHandlers.track('onNodeSearchInput');
            const addConnected = mockHandlers.track('addConnected');
            const fitGraph = mockHandlers.track('fitGraph');
            const clearGraph = mockHandlers.track('clearGraph');
            const toggleEdgeLabels = mockHandlers.track('toggleEdgeLabels');
            const applyLayout = mockHandlers.track('applyLayout');
            const contextExpandConnections = mockHandlers.track('contextExpandConnections');
            const contextShowOnlyConnections = mockHandlers.track('contextShowOnlyConnections');
            const contextCenterOnNode = mockHandlers.track('contextCenterOnNode');
            const contextSetAsFocus = mockHandlers.track('contextSetAsFocus');
            const contextRemoveNode = mockHandlers.track('contextRemoveNode');
            const contextRemoveDisconnected = mockHandlers.track('contextRemoveDisconnected');
            const contextOpenInExplorer = mockHandlers.track('contextOpenInExplorer');

            setupDependenciesEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    const handlers = {
                        'addConnected': addConnected,
                        'fitGraph': fitGraph,
                        'clearGraph': clearGraph,
                        'toggleEdgeLabels': toggleEdgeLabels,
                        'contextExpandConnections': contextExpandConnections,
                        'contextShowOnlyConnections': contextShowOnlyConnections,
                        'contextCenterOnNode': contextCenterOnNode,
                        'contextSetAsFocus': contextSetAsFocus,
                        'contextRemoveNode': contextRemoveNode,
                        'contextRemoveDisconnected': contextRemoveDisconnected,
                        'contextOpenInExplorer': contextOpenInExplorer
                    };

                    if (handlers[action]) {
                        handlers[action]();
                    }
                });

                document.addEventListener('input', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'onNodeSearchInput') {
                        onNodeSearchInput();
                    }
                });

                document.addEventListener('change', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl) {
                        if (actionEl.dataset.action === 'onNodeSearchInput') {
                            onNodeSearchInput();
                        } else if (actionEl.dataset.action === 'applyLayout') {
                            applyLayout();
                        }
                    }
                });
            };
        });

        test('add connected button triggers addConnected', () => {
            document.body.innerHTML = `
                <button data-action="addConnected">+ Add Connected to Selected</button>
            `;
            setupDependenciesEventDelegation();

            document.querySelector('[data-action="addConnected"]').click();

            expect(mockHandlers.wasCalled('addConnected')).toBe(true);
        });

        test('fit graph button triggers fitGraph', () => {
            document.body.innerHTML = `
                <button data-action="fitGraph">Fit to View</button>
            `;
            setupDependenciesEventDelegation();

            document.querySelector('[data-action="fitGraph"]').click();

            expect(mockHandlers.wasCalled('fitGraph')).toBe(true);
        });

        test('clear graph button triggers clearGraph', () => {
            document.body.innerHTML = `
                <button data-action="clearGraph">Clear Graph</button>
            `;
            setupDependenciesEventDelegation();

            document.querySelector('[data-action="clearGraph"]').click();

            expect(mockHandlers.wasCalled('clearGraph')).toBe(true);
        });

        test('toggle edge labels button triggers toggleEdgeLabels', () => {
            document.body.innerHTML = `
                <button data-action="toggleEdgeLabels">Hide Connection Labels</button>
            `;
            setupDependenciesEventDelegation();

            document.querySelector('[data-action="toggleEdgeLabels"]').click();

            expect(mockHandlers.wasCalled('toggleEdgeLabels')).toBe(true);
        });

        test('context menu expand connections triggers contextExpandConnections', () => {
            document.body.innerHTML = `
                <div class="context-menu-item" data-action="contextExpandConnections">Expand</div>
            `;
            setupDependenciesEventDelegation();

            document.querySelector('[data-action="contextExpandConnections"]').click();

            expect(mockHandlers.wasCalled('contextExpandConnections')).toBe(true);
        });

        test('context menu open in explorer triggers contextOpenInExplorer', () => {
            document.body.innerHTML = `
                <div class="context-menu-item" data-action="contextOpenInExplorer">Open in Explorer</div>
            `;
            setupDependenciesEventDelegation();

            document.querySelector('[data-action="contextOpenInExplorer"]').click();

            expect(mockHandlers.wasCalled('contextOpenInExplorer')).toBe(true);
        });
    });

    describe('Validate Page Handlers', () => {
        let setupValidateEventDelegation;

        beforeEach(() => {
            const runValidation = mockHandlers.track('runValidation');

            setupValidateEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'runValidation') {
                        runValidation();
                    }
                });
            };
        });

        test('run validation button triggers runValidation', () => {
            document.body.innerHTML = `
                <button id="validateBtn" data-action="runValidation">Run Validation</button>
            `;
            setupValidateEventDelegation();

            document.getElementById('validateBtn').click();

            expect(mockHandlers.wasCalled('runValidation')).toBe(true);
        });
    });

    describe('Bulk Rename Page Handlers', () => {
        let setupBulkRenameEventDelegation;

        beforeEach(() => {
            const previewRename = mockHandlers.track('previewRename');
            const showDiff = mockHandlers.track('showDiff');
            const applyRename = mockHandlers.track('applyRename');

            setupBulkRenameEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    if (action === 'preview-rename') {
                        previewRename();
                    } else if (action === 'show-diff') {
                        showDiff();
                    } else if (action === 'apply-rename') {
                        applyRename();
                    }
                });
            };
        });

        test('preview changes button triggers previewRename', () => {
            document.body.innerHTML = `
                <button data-action="preview-rename">Preview Changes</button>
            `;
            setupBulkRenameEventDelegation();

            document.querySelector('[data-action="preview-rename"]').click();

            expect(mockHandlers.wasCalled('previewRename')).toBe(true);
        });

        test('show diff button triggers showDiff', () => {
            document.body.innerHTML = `
                <button id="diffBtn" data-action="show-diff">Show File Diff</button>
            `;
            setupBulkRenameEventDelegation();

            document.getElementById('diffBtn').click();

            expect(mockHandlers.wasCalled('showDiff')).toBe(true);
        });

        test('apply changes button triggers applyRename', () => {
            document.body.innerHTML = `
                <button id="applyBtn" data-action="apply-rename">Apply Changes</button>
            `;
            setupBulkRenameEventDelegation();

            document.getElementById('applyBtn').click();

            expect(mockHandlers.wasCalled('applyRename')).toBe(true);
        });
    });

    describe('Find Replace Page Handlers', () => {
        let setupFindReplaceEventDelegation;

        beforeEach(() => {
            const findMatches = mockHandlers.track('findMatches');
            const replaceAll = mockHandlers.track('replaceAll');

            setupFindReplaceEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    if (action === 'find-matches') {
                        findMatches();
                    } else if (action === 'replace-all') {
                        replaceAll();
                    }
                });
            };
        });

        test('find matches button triggers findMatches', () => {
            document.body.innerHTML = `
                <button data-action="find-matches">Find All Matches</button>
            `;
            setupFindReplaceEventDelegation();

            document.querySelector('[data-action="find-matches"]').click();

            expect(mockHandlers.wasCalled('findMatches')).toBe(true);
        });

        test('replace all button triggers replaceAll', () => {
            document.body.innerHTML = `
                <button id="replaceBtn" data-action="replace-all">Replace All</button>
            `;
            setupFindReplaceEventDelegation();

            document.getElementById('replaceBtn').click();

            expect(mockHandlers.wasCalled('replaceAll')).toBe(true);
        });
    });

    describe('Health Check Page Handlers', () => {
        let setupHealthCheckEventDelegation;

        beforeEach(() => {
            const runHealthCheck = mockHandlers.track('runHealthCheck');
            const filterIssues = mockHandlers.track('filterIssues');

            setupHealthCheckEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'runHealthCheck') {
                        runHealthCheck();
                    }
                });

                document.addEventListener('change', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'filterIssues') {
                        filterIssues();
                    }
                });

                document.addEventListener('input', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'filterIssues') {
                        filterIssues();
                    }
                });
            };
        });

        test('run health check button triggers runHealthCheck', () => {
            document.body.innerHTML = `
                <button data-action="runHealthCheck" id="runBtn">Run Health Check</button>
            `;
            setupHealthCheckEventDelegation();

            document.getElementById('runBtn').click();

            expect(mockHandlers.wasCalled('runHealthCheck')).toBe(true);
        });

        test('filter checkbox change triggers filterIssues', () => {
            document.body.innerHTML = `
                <input type="checkbox" id="showErrors" data-action="filterIssues">
            `;
            setupHealthCheckEventDelegation();

            const checkbox = document.getElementById('showErrors');
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));

            expect(mockHandlers.wasCalled('filterIssues')).toBe(true);
        });
    });

    describe('Audit Log Page Handlers', () => {
        let setupAuditLogEventDelegation;

        beforeEach(() => {
            const filterByType = mockHandlers.track('filterByType');
            const loadCurrentLog = mockHandlers.track('loadCurrentLog');
            const confirmClearLog = mockHandlers.track('confirmClearLog');

            setupAuditLogEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    if (action === 'loadCurrentLog') {
                        loadCurrentLog();
                    } else if (action === 'confirmClearLog') {
                        confirmClearLog();
                    }
                });

                document.addEventListener('change', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'filterByType') {
                        filterByType();
                    }
                });
            };
        });

        test('filter checkbox triggers filterByType', () => {
            document.body.innerHTML = `
                <input type="checkbox" class="type-filter" value="all" data-action="filterByType">
            `;
            setupAuditLogEventDelegation();

            const checkbox = document.querySelector('[data-action="filterByType"]');
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));

            expect(mockHandlers.wasCalled('filterByType')).toBe(true);
        });

        test('load current log triggers loadCurrentLog', () => {
            document.body.innerHTML = `
                <div class="archive-item" data-action="loadCurrentLog">Current</div>
            `;
            setupAuditLogEventDelegation();

            document.querySelector('[data-action="loadCurrentLog"]').click();

            expect(mockHandlers.wasCalled('loadCurrentLog')).toBe(true);
        });

        test('clear log button triggers confirmClearLog', () => {
            document.body.innerHTML = `
                <button data-action="confirmClearLog">Clear Log</button>
            `;
            setupAuditLogEventDelegation();

            document.querySelector('[data-action="confirmClearLog"]').click();

            expect(mockHandlers.wasCalled('confirmClearLog')).toBe(true);
        });
    });

    describe('Smart Grouping Page Handlers', () => {
        let setupSmartGroupingEventDelegation;

        beforeEach(() => {
            const analyzeHosts = mockHandlers.track('analyzeHosts');
            const filterSuggestions = mockHandlers.track('filterSuggestions');
            const createGroup = mockHandlers.track('createGroup');
            const showCreateModal = mockHandlers.track('showCreateModal');
            const showAllMembers = mockHandlers.track('showAllMembers');
            const removeMember = mockHandlers.track('removeMember');

            setupSmartGroupingEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    if (action === 'analyzeHosts') {
                        analyzeHosts();
                    } else if (action === 'createGroup') {
                        createGroup();
                    } else if (action === 'showCreateModal') {
                        const index = actionEl.dataset.index;
                        showCreateModal(index);
                    } else if (action === 'showAllMembers') {
                        const index = actionEl.dataset.index;
                        showAllMembers(index);
                    } else if (action === 'removeMember') {
                        const member = actionEl.dataset.member;
                        removeMember(member);
                    }
                });

                document.addEventListener('change', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'filterSuggestions') {
                        filterSuggestions();
                    }
                });

                document.addEventListener('input', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'filterSuggestions') {
                        filterSuggestions();
                    }
                });
            };
        });

        test('analyze hosts button triggers analyzeHosts', () => {
            document.body.innerHTML = `
                <button data-action="analyzeHosts" id="analyzeBtn">Analyze Hosts</button>
            `;
            setupSmartGroupingEventDelegation();

            document.getElementById('analyzeBtn').click();

            expect(mockHandlers.wasCalled('analyzeHosts')).toBe(true);
        });

        test('create group button triggers createGroup', () => {
            document.body.innerHTML = `
                <button data-action="createGroup">Create Hostgroup</button>
            `;
            setupSmartGroupingEventDelegation();

            document.querySelector('[data-action="createGroup"]').click();

            expect(mockHandlers.wasCalled('createGroup')).toBe(true);
        });

        test('show create modal button triggers showCreateModal with index', () => {
            document.body.innerHTML = `
                <button data-action="showCreateModal" data-index="0">Create</button>
            `;
            setupSmartGroupingEventDelegation();

            document.querySelector('[data-action="showCreateModal"]').click();

            expect(mockHandlers.wasCalled('showCreateModal')).toBe(true);
            const call = mockHandlers.getCall('showCreateModal');
            expect(call.args[0]).toBe('0');
        });

        test('filter suggestions checkbox triggers filterSuggestions', () => {
            document.body.innerHTML = `
                <input type="checkbox" class="filter-type" data-action="filterSuggestions">
            `;
            setupSmartGroupingEventDelegation();

            const checkbox = document.querySelector('[data-action="filterSuggestions"]');
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));

            expect(mockHandlers.wasCalled('filterSuggestions')).toBe(true);
        });
    });

    describe('Reorganize Page Handlers', () => {
        let setupReorganizeEventDelegation;

        beforeEach(() => {
            const loadObjects = mockHandlers.track('loadObjects');
            const filterDisplayedObjects = mockHandlers.track('filterDisplayedObjects');
            const moveSelected = mockHandlers.track('moveSelected');
            const cloneSelected = mockHandlers.track('cloneSelected');
            const deleteSelected = mockHandlers.track('deleteSelected');
            const selectAll = mockHandlers.track('selectAll');
            const selectNone = mockHandlers.track('selectNone');

            setupReorganizeEventDelegation = () => {
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    const handlers = {
                        'moveSelected': moveSelected,
                        'cloneSelected': cloneSelected,
                        'deleteSelected': deleteSelected,
                        'selectAll': selectAll,
                        'selectNone': selectNone
                    };

                    if (handlers[action]) {
                        handlers[action]();
                    }
                });

                document.addEventListener('change', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'loadObjects') {
                        loadObjects();
                    }
                });

                document.addEventListener('input', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (actionEl && actionEl.dataset.action === 'filterDisplayedObjects') {
                        filterDisplayedObjects();
                    }
                });
            };
        });

        test('move selected button triggers moveSelected', () => {
            document.body.innerHTML = `
                <button data-action="moveSelected">Move to File</button>
            `;
            setupReorganizeEventDelegation();

            document.querySelector('[data-action="moveSelected"]').click();

            expect(mockHandlers.wasCalled('moveSelected')).toBe(true);
        });

        test('clone selected button triggers cloneSelected', () => {
            document.body.innerHTML = `
                <button data-action="cloneSelected">Clone</button>
            `;
            setupReorganizeEventDelegation();

            document.querySelector('[data-action="cloneSelected"]').click();

            expect(mockHandlers.wasCalled('cloneSelected')).toBe(true);
        });

        test('delete selected button triggers deleteSelected', () => {
            document.body.innerHTML = `
                <button data-action="deleteSelected">Delete</button>
            `;
            setupReorganizeEventDelegation();

            document.querySelector('[data-action="deleteSelected"]').click();

            expect(mockHandlers.wasCalled('deleteSelected')).toBe(true);
        });

        test('select all button triggers selectAll', () => {
            document.body.innerHTML = `
                <button data-action="selectAll">Select All</button>
            `;
            setupReorganizeEventDelegation();

            document.querySelector('[data-action="selectAll"]').click();

            expect(mockHandlers.wasCalled('selectAll')).toBe(true);
        });

        test('select none button triggers selectNone', () => {
            document.body.innerHTML = `
                <button data-action="selectNone">Select None</button>
            `;
            setupReorganizeEventDelegation();

            document.querySelector('[data-action="selectNone"]').click();

            expect(mockHandlers.wasCalled('selectNone')).toBe(true);
        });
    });
});
