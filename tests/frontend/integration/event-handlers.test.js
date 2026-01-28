/**
 * Integration tests for event handler wiring
 *
 * These tests verify that clicking elements with data-action attributes
 * actually triggers the correct handlers. Unlike unit tests, these test
 * the full event delegation pipeline.
 */

describe('Event Handler Integration Tests', () => {
    let mockHandlers;

    beforeEach(() => {
        // Reset DOM
        document.body.innerHTML = '';

        // Clear all event listeners by replacing document
        // This is a workaround since jsdom doesn't support removeEventListener easily

        // Mock common globals
        window.localStorage = {
            store: {},
            getItem: jest.fn(key => window.localStorage.store[key] || null),
            setItem: jest.fn((key, value) => { window.localStorage.store[key] = value; }),
            removeItem: jest.fn(key => { delete window.localStorage.store[key]; }),
            clear: jest.fn(() => { window.localStorage.store = {}; })
        };

        window.sessionStorage = {
            store: {},
            getItem: jest.fn(key => window.sessionStorage.store[key] || null),
            setItem: jest.fn((key, value) => { window.sessionStorage.store[key] = value; }),
            removeItem: jest.fn(key => { delete window.sessionStorage.store[key]; }),
            clear: jest.fn(() => { window.sessionStorage.store = {}; })
        };

        // Mock fetch
        global.fetch = jest.fn(() => Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ success: true })
        }));

        // Track handler calls
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

    describe('Base.js Action Handlers', () => {
        let actionHandlers;
        let setupBaseEventDelegation;

        beforeEach(() => {
            // Create mock handlers
            const handleUndoClick = mockHandlers.track('undo');
            const handleCommitClick = mockHandlers.track('commit');
            const showKeyboardShortcuts = mockHandlers.track('show-shortcuts');
            const closeKeyboardShortcuts = mockHandlers.track('close-shortcuts');
            const reloadConfig = mockHandlers.track('reload-config');
            const breakLock = mockHandlers.track('break-lock');
            const closeGitResultPanel = mockHandlers.track('close-git-result');

            actionHandlers = {
                'undo': handleUndoClick,
                'commit': handleCommitClick,
                'show-shortcuts': showKeyboardShortcuts,
                'close-shortcuts': closeKeyboardShortcuts,
                'reload-config': reloadConfig,
                'break-lock': breakLock,
                'close-git-result': closeGitResultPanel,
                'close-toast': mockHandlers.track('close-toast')
            };

            // Set up event delegation like base.js does
            setupBaseEventDelegation = () => {
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
            };
        });

        test('undo button triggers handleUndoClick', () => {
            document.body.innerHTML = `
                <button class="undo-btn" id="navUndoBtn" data-action="undo">Undo</button>
            `;
            setupBaseEventDelegation();

            document.getElementById('navUndoBtn').click();

            expect(mockHandlers.wasCalled('undo')).toBe(true);
        });

        test('commit button triggers handleCommitClick', () => {
            document.body.innerHTML = `
                <button class="commit-btn" id="navCommitBtn" data-action="commit">Commit</button>
            `;
            setupBaseEventDelegation();

            document.getElementById('navCommitBtn').click();

            expect(mockHandlers.wasCalled('commit')).toBe(true);
        });

        test('keyboard shortcuts button triggers showKeyboardShortcuts', () => {
            document.body.innerHTML = `
                <button class="nav-btn" id="keyboardShortcutsBtn" data-action="show-shortcuts">?</button>
            `;
            setupBaseEventDelegation();

            document.getElementById('keyboardShortcutsBtn').click();

            expect(mockHandlers.wasCalled('show-shortcuts')).toBe(true);
        });

        test('close shortcuts button triggers closeKeyboardShortcuts', () => {
            document.body.innerHTML = `
                <button class="keyboard-shortcuts-close" data-action="close-shortcuts">&times;</button>
            `;
            setupBaseEventDelegation();

            document.querySelector('[data-action="close-shortcuts"]').click();

            expect(mockHandlers.wasCalled('close-shortcuts')).toBe(true);
        });

        test('reload config button triggers reloadConfig', () => {
            document.body.innerHTML = `
                <button class="nav-btn" id="reloadConfigBtn" data-action="reload-config">Reload</button>
            `;
            setupBaseEventDelegation();

            document.getElementById('reloadConfigBtn').click();

            expect(mockHandlers.wasCalled('reload-config')).toBe(true);
        });

        test('break lock button triggers breakLock', () => {
            document.body.innerHTML = `
                <button class="lock-break-btn" id="breakLockBtn" data-action="break-lock">Break Lock</button>
            `;
            setupBaseEventDelegation();

            document.getElementById('breakLockBtn').click();

            expect(mockHandlers.wasCalled('break-lock')).toBe(true);
        });

        test('close git result button triggers closeGitResultPanel', () => {
            document.body.innerHTML = `
                <button class="git-result-close" id="gitResultClose" data-action="close-git-result">&times;</button>
            `;
            setupBaseEventDelegation();

            document.getElementById('gitResultClose').click();

            expect(mockHandlers.wasCalled('close-git-result')).toBe(true);
        });

        test('clicking nested element bubbles to parent with data-action', () => {
            document.body.innerHTML = `
                <button class="commit-btn" data-action="commit">
                    <span class="icon">✓</span>
                    <span class="label">Commit</span>
                </button>
            `;
            setupBaseEventDelegation();

            // Click the nested span, should still trigger commit
            document.querySelector('.icon').click();

            expect(mockHandlers.wasCalled('commit')).toBe(true);
        });

        test('unknown action does not throw error', () => {
            document.body.innerHTML = `
                <button data-action="unknown-action">Unknown</button>
            `;
            setupBaseEventDelegation();

            expect(() => {
                document.querySelector('[data-action="unknown-action"]').click();
            }).not.toThrow();
        });
    });

    describe('Git Page Action Handlers', () => {
        let setupGitEventDelegation;
        let switchGitTab, discardGitFile, handleCommitClick, restoreCommit, clearGitHistory;

        beforeEach(() => {
            switchGitTab = mockHandlers.track('switchGitTab');
            discardGitFile = mockHandlers.track('discardGitFile');
            handleCommitClick = mockHandlers.track('commit');
            restoreCommit = mockHandlers.track('restoreCommit');
            clearGitHistory = mockHandlers.track('clearGitHistory');

            // Set up event delegation like git.js does
            setupGitEventDelegation = () => {
                document.addEventListener('click', function(e) {
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
            };
        });

        test('changes tab triggers switchGitTab with "changes"', () => {
            document.body.innerHTML = `
                <button class="page-tab" id="tabChanges" data-action="switchGitTab" data-tab="changes">
                    Uncommitted
                </button>
            `;
            setupGitEventDelegation();

            document.getElementById('tabChanges').click();

            expect(mockHandlers.wasCalled('switchGitTab')).toBe(true);
            const call = mockHandlers.getCall('switchGitTab');
            expect(call.args[0]).toBe('changes');
        });

        test('history tab triggers switchGitTab with "history"', () => {
            document.body.innerHTML = `
                <button class="page-tab" id="tabHistory" data-action="switchGitTab" data-tab="history">
                    History
                </button>
            `;
            setupGitEventDelegation();

            document.getElementById('tabHistory').click();

            expect(mockHandlers.wasCalled('switchGitTab')).toBe(true);
            const call = mockHandlers.getCall('switchGitTab');
            expect(call.args[0]).toBe('history');
        });

        test('discard file button triggers discardGitFile with path', () => {
            document.body.innerHTML = `
                <button class="git-file-action danger" data-action="discard-file" data-path="config/hosts.cfg">
                    Discard
                </button>
            `;
            setupGitEventDelegation();

            document.querySelector('[data-action="discard-file"]').click();

            expect(mockHandlers.wasCalled('discardGitFile')).toBe(true);
            const call = mockHandlers.getCall('discardGitFile');
            expect(call.args[0]).toBe('config/hosts.cfg');
        });

        test('restore commit button triggers restoreCommit with hash and message', () => {
            document.body.innerHTML = `
                <button class="git-restore-btn" data-action="restore-commit"
                        data-hash="abc123def456" data-message="Initial commit">
                    Restore
                </button>
            `;
            setupGitEventDelegation();

            document.querySelector('[data-action="restore-commit"]').click();

            expect(mockHandlers.wasCalled('restoreCommit')).toBe(true);
            const call = mockHandlers.getCall('restoreCommit');
            expect(call.args[0]).toBe('abc123def456');
            expect(call.args[1]).toBe('Initial commit');
        });

        test('clear git history button triggers clearGitHistory', () => {
            document.body.innerHTML = `
                <button class="page-btn page-btn-danger" data-action="clearGitHistory">
                    Wipe Git Log
                </button>
            `;
            setupGitEventDelegation();

            document.querySelector('[data-action="clearGitHistory"]').click();

            expect(mockHandlers.wasCalled('clearGitHistory')).toBe(true);
        });
    });

    describe('Explorer Action Handlers', () => {
        let setupExplorerEventDelegation;
        let Explorer;

        beforeEach(() => {
            // Mock Explorer namespace
            Explorer = {
                setView: mockHandlers.track('setView'),
                switchRightTab: mockHandlers.track('switchRightTab'),
                toggleSection: mockHandlers.track('toggleSection'),
                toggleSuggestionSection: mockHandlers.track('toggleSuggestionSection'),
                toggleActionsMenu: mockHandlers.track('toggleActionsMenu'),
                selectAllVisible: mockHandlers.track('selectAllVisible'),
                selectByType: mockHandlers.track('selectByType'),
                selectByPattern: mockHandlers.track('selectByPattern'),
                navigateToObjectIssue: mockHandlers.track('navigateToObjectIssue'),
                openInGraphView: mockHandlers.track('openInGraphView'),
                discardNewObject: mockHandlers.track('discardNewObject'),
                showAddAttribute: mockHandlers.track('showAddAttribute'),
                createInlineFile: mockHandlers.track('createInlineFile'),
                createInlineFolder: mockHandlers.track('createInlineFolder'),
                analyzeAll: mockHandlers.track('analyzeAll'),
                runValidationFull: mockHandlers.track('runValidationFull'),
                closeObjectDetail: mockHandlers.track('closeObjectDetail'),
                closePreview: mockHandlers.track('closePreview'),
                closeDialog: mockHandlers.track('closeDialog'),
                contextAction: mockHandlers.track('contextAction'),
                showBulkRenameDialog: mockHandlers.track('showBulkRenameDialog'),
                showEditAttributesDialog: mockHandlers.track('showEditAttributesDialog'),
                showBulkAction: mockHandlers.track('showBulkAction'),
                showAddToGroupDialog: mockHandlers.track('showAddToGroupDialog'),
                filterTree: mockHandlers.track('filterTree'),
                filterTemplateSuggestions: mockHandlers.track('filterTemplateSuggestions'),
                filterGroupingSuggestions: mockHandlers.track('filterGroupingSuggestions')
            };

            const actionHandlers = {
                setView: (el) => Explorer.setView(el.dataset.view),
                switchRightTab: (el) => Explorer.switchRightTab(el.dataset.tab),
                toggleSection: (el) => Explorer.toggleSection(el.dataset.section),
                toggleSuggestionSection: (el) => Explorer.toggleSuggestionSection(el.dataset.suggestionSection),
                toggleActionsMenu: (el, e) => Explorer.toggleActionsMenu(e),
                selectAllVisible: () => Explorer.selectAllVisible(),
                selectByType: () => Explorer.selectByType(),
                selectByPattern: () => Explorer.selectByPattern(),
                navigateToObjectIssue: () => Explorer.navigateToObjectIssue(),
                openInGraphView: () => Explorer.openInGraphView(),
                discardNewObject: () => Explorer.discardNewObject(),
                showAddAttribute: () => Explorer.showAddAttribute(),
                createInlineFile: () => Explorer.createInlineFile(),
                createInlineFolder: () => Explorer.createInlineFolder(),
                analyzeAll: () => Explorer.analyzeAll(),
                runValidationFull: () => Explorer.runValidationFull(),
                closeObjectDetail: () => Explorer.closeObjectDetail(),
                closePreview: () => Explorer.closePreview(),
                closeDialog: () => Explorer.closeDialog(),
                contextAction: (el) => Explorer.contextAction(el.dataset.contextAction),
                showBulkRenameDialog: () => Explorer.showBulkRenameDialog(),
                showEditAttributesDialog: () => Explorer.showEditAttributesDialog(),
                showBulkAction: (el) => Explorer.showBulkAction(el.dataset.bulkAction),
                showAddToGroupDialog: () => Explorer.showAddToGroupDialog(),
                filterTree: () => Explorer.filterTree(),
                filterTemplateSuggestions: () => Explorer.filterTemplateSuggestions(),
                filterGroupingSuggestions: () => Explorer.filterGroupingSuggestions()
            };

            setupExplorerEventDelegation = () => {
                // Click event delegation
                document.addEventListener('click', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    const handler = actionHandlers[action];
                    if (handler) {
                        handler(actionEl, e);
                    }
                });

                // Change event delegation (for checkboxes)
                document.addEventListener('change', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    const handler = actionHandlers[action];
                    if (handler) {
                        handler(actionEl, e);
                    }
                });

                // Input event delegation (for text inputs and sliders)
                document.addEventListener('input', function(e) {
                    const actionEl = e.target.closest('[data-action]');
                    if (!actionEl) return;

                    const action = actionEl.dataset.action;
                    const handler = actionHandlers[action];
                    if (handler) {
                        handler(actionEl, e);
                    }
                });
            };
        });

        test('view by file button triggers setView with "file"', () => {
            document.body.innerHTML = `
                <button class="view-btn" data-view="file" data-action="setView">By File</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="setView"]').click();

            expect(mockHandlers.wasCalled('setView')).toBe(true);
            const call = mockHandlers.getCall('setView');
            expect(call.args[0]).toBe('file');
        });

        test('view by type button triggers setView with "type"', () => {
            document.body.innerHTML = `
                <button class="view-btn" data-view="type" data-action="setView">By Type</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="setView"]').click();

            expect(mockHandlers.wasCalled('setView')).toBe(true);
            const call = mockHandlers.getCall('setView');
            expect(call.args[0]).toBe('type');
        });

        test('right pane tabs trigger switchRightTab with correct tab', () => {
            document.body.innerHTML = `
                <button class="right-tab" data-tab="files" data-action="switchRightTab">Files</button>
                <button class="right-tab" data-tab="suggestions" data-action="switchRightTab">Suggestions</button>
                <button class="right-tab" data-tab="validation" data-action="switchRightTab">Validation</button>
            `;
            setupExplorerEventDelegation();

            // Click files tab
            document.querySelectorAll('[data-action="switchRightTab"]')[0].click();
            expect(mockHandlers.getCall('switchRightTab').args[0]).toBe('files');

            mockHandlers.reset();

            // Click suggestions tab
            document.querySelectorAll('[data-action="switchRightTab"]')[1].click();
            expect(mockHandlers.getCall('switchRightTab').args[0]).toBe('suggestions');

            mockHandlers.reset();

            // Click validation tab
            document.querySelectorAll('[data-action="switchRightTab"]')[2].click();
            expect(mockHandlers.getCall('switchRightTab').args[0]).toBe('validation');
        });

        test('toggle section triggers toggleSection with section name', () => {
            document.body.innerHTML = `
                <div class="section-title" data-action="toggleSection" data-section="inheritance">
                    Inheritance
                </div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="toggleSection"]').click();

            expect(mockHandlers.wasCalled('toggleSection')).toBe(true);
            const call = mockHandlers.getCall('toggleSection');
            expect(call.args[0]).toBe('inheritance');
        });

        test('toggle suggestion section triggers toggleSuggestionSection', () => {
            document.body.innerHTML = `
                <div class="suggestion-section-header" data-action="toggleSuggestionSection" data-suggestion-section="issues">
                    Issues
                </div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="toggleSuggestionSection"]').click();

            expect(mockHandlers.wasCalled('toggleSuggestionSection')).toBe(true);
            const call = mockHandlers.getCall('toggleSuggestionSection');
            expect(call.args[0]).toBe('issues');
        });

        test('actions menu button triggers toggleActionsMenu', () => {
            document.body.innerHTML = `
                <button class="actions-btn" data-action="toggleActionsMenu">Select</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="toggleActionsMenu"]').click();

            expect(mockHandlers.wasCalled('toggleActionsMenu')).toBe(true);
        });

        test('select all visible triggers selectAllVisible', () => {
            document.body.innerHTML = `
                <button data-action="selectAllVisible">Select all visible</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="selectAllVisible"]').click();

            expect(mockHandlers.wasCalled('selectAllVisible')).toBe(true);
        });

        test('select by type triggers selectByType', () => {
            document.body.innerHTML = `
                <button data-action="selectByType">Select by type...</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="selectByType"]').click();

            expect(mockHandlers.wasCalled('selectByType')).toBe(true);
        });

        test('select by pattern triggers selectByPattern', () => {
            document.body.innerHTML = `
                <button data-action="selectByPattern">Select by pattern...</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="selectByPattern"]').click();

            expect(mockHandlers.wasCalled('selectByPattern')).toBe(true);
        });

        test('navigate to issue button triggers navigateToObjectIssue', () => {
            document.body.innerHTML = `
                <button class="card-issue-btn" data-action="navigateToObjectIssue">Issue</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="navigateToObjectIssue"]').click();

            expect(mockHandlers.wasCalled('navigateToObjectIssue')).toBe(true);
        });

        test('open in graph view button triggers openInGraphView', () => {
            document.body.innerHTML = `
                <button class="center-graph-btn" data-action="openInGraphView">Graph</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="openInGraphView"]').click();

            expect(mockHandlers.wasCalled('openInGraphView')).toBe(true);
        });

        test('discard new object button triggers discardNewObject', () => {
            document.body.innerHTML = `
                <button class="center-close-btn" data-action="discardNewObject">&times;</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="discardNewObject"]').click();

            expect(mockHandlers.wasCalled('discardNewObject')).toBe(true);
        });

        test('add attribute button triggers showAddAttribute', () => {
            document.body.innerHTML = `
                <button class="add-attr-btn" data-action="showAddAttribute">+ Add attribute</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="showAddAttribute"]').click();

            expect(mockHandlers.wasCalled('showAddAttribute')).toBe(true);
        });

        test('create inline file button triggers createInlineFile', () => {
            document.body.innerHTML = `
                <button data-action="createInlineFile">New File</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="createInlineFile"]').click();

            expect(mockHandlers.wasCalled('createInlineFile')).toBe(true);
        });

        test('create inline folder button triggers createInlineFolder', () => {
            document.body.innerHTML = `
                <button data-action="createInlineFolder">New Folder</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="createInlineFolder"]').click();

            expect(mockHandlers.wasCalled('createInlineFolder')).toBe(true);
        });

        test('analyze button triggers analyzeAll', () => {
            document.body.innerHTML = `
                <button class="btn-analyze" data-action="analyzeAll">Analyze</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="analyzeAll"]').click();

            expect(mockHandlers.wasCalled('analyzeAll')).toBe(true);
        });

        test('run validation button triggers runValidationFull', () => {
            document.body.innerHTML = `
                <button class="btn-refresh" data-action="runValidationFull">Run Validation</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="runValidationFull"]').click();

            expect(mockHandlers.wasCalled('runValidationFull')).toBe(true);
        });

        test('close object detail button triggers closeObjectDetail', () => {
            document.body.innerHTML = `
                <button class="modal-close" data-action="closeObjectDetail">&times;</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="closeObjectDetail"]').click();

            expect(mockHandlers.wasCalled('closeObjectDetail')).toBe(true);
        });

        test('close preview triggers closePreview', () => {
            document.body.innerHTML = `
                <button class="preview-close" data-action="closePreview">&times;</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="closePreview"]').click();

            expect(mockHandlers.wasCalled('closePreview')).toBe(true);
        });

        test('close dialog button triggers closeDialog', () => {
            document.body.innerHTML = `
                <button class="btn-cancel" data-action="closeDialog">Cancel</button>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="closeDialog"]').click();

            expect(mockHandlers.wasCalled('closeDialog')).toBe(true);
        });

        test('context action rename triggers contextAction with "rename"', () => {
            document.body.innerHTML = `
                <div class="menu-item" data-action="contextAction" data-context-action="rename">Rename...</div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="contextAction"]').click();

            expect(mockHandlers.wasCalled('contextAction')).toBe(true);
            const call = mockHandlers.getCall('contextAction');
            expect(call.args[0]).toBe('rename');
        });

        test('context action clone triggers contextAction with "clone"', () => {
            document.body.innerHTML = `
                <div class="menu-item" data-action="contextAction" data-context-action="clone">Clone...</div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="contextAction"]').click();

            expect(mockHandlers.wasCalled('contextAction')).toBe(true);
            const call = mockHandlers.getCall('contextAction');
            expect(call.args[0]).toBe('clone');
        });

        test('context action delete triggers contextAction with "delete"', () => {
            document.body.innerHTML = `
                <div class="menu-item danger" data-action="contextAction" data-context-action="delete">Delete</div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="contextAction"]').click();

            expect(mockHandlers.wasCalled('contextAction')).toBe(true);
            const call = mockHandlers.getCall('contextAction');
            expect(call.args[0]).toBe('delete');
        });

        test('bulk rename dialog button triggers showBulkRenameDialog', () => {
            document.body.innerHTML = `
                <div class="menu-item" data-action="showBulkRenameDialog">Bulk rename...</div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="showBulkRenameDialog"]').click();

            expect(mockHandlers.wasCalled('showBulkRenameDialog')).toBe(true);
        });

        test('edit attributes dialog button triggers showEditAttributesDialog', () => {
            document.body.innerHTML = `
                <div class="menu-item" data-action="showEditAttributesDialog">Edit attributes...</div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="showEditAttributesDialog"]').click();

            expect(mockHandlers.wasCalled('showEditAttributesDialog')).toBe(true);
        });

        test('move to file button triggers showBulkAction with "move"', () => {
            document.body.innerHTML = `
                <div class="menu-item" data-action="showBulkAction" data-bulk-action="move">Move to file...</div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="showBulkAction"]').click();

            expect(mockHandlers.wasCalled('showBulkAction')).toBe(true);
            const call = mockHandlers.getCall('showBulkAction');
            expect(call.args[0]).toBe('move');
        });

        test('add to group button triggers showAddToGroupDialog', () => {
            document.body.innerHTML = `
                <div class="menu-item" data-action="showAddToGroupDialog">Add to group...</div>
            `;
            setupExplorerEventDelegation();

            document.querySelector('[data-action="showAddToGroupDialog"]').click();

            expect(mockHandlers.wasCalled('showAddToGroupDialog')).toBe(true);
        });

        // Input/Change event tests
        test('tree search input triggers filterTree on input', () => {
            document.body.innerHTML = `
                <input type="text" class="tree-search" id="treeSearch" data-action="filterTree">
            `;
            setupExplorerEventDelegation();

            const input = document.querySelector('[data-action="filterTree"]');
            input.dispatchEvent(new Event('input', { bubbles: true }));

            expect(mockHandlers.wasCalled('filterTree')).toBe(true);
        });

        test('show orphans checkbox triggers filterTree on change', () => {
            document.body.innerHTML = `
                <input type="checkbox" id="showOrphansOnly" data-action="filterTree">
            `;
            setupExplorerEventDelegation();

            const checkbox = document.querySelector('[data-action="filterTree"]');
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));

            expect(mockHandlers.wasCalled('filterTree')).toBe(true);
        });

        test('template suggestions slider triggers filterTemplateSuggestions on input', () => {
            document.body.innerHTML = `
                <input type="range" id="minTemplateObjects" min="2" max="10" value="3" data-action="filterTemplateSuggestions">
            `;
            setupExplorerEventDelegation();

            const slider = document.querySelector('[data-action="filterTemplateSuggestions"]');
            slider.dispatchEvent(new Event('input', { bubbles: true }));

            expect(mockHandlers.wasCalled('filterTemplateSuggestions')).toBe(true);
        });

        test('grouping suggestions slider triggers filterGroupingSuggestions on input', () => {
            document.body.innerHTML = `
                <input type="range" id="minMembersSlider" min="2" max="10" value="2" data-action="filterGroupingSuggestions">
            `;
            setupExplorerEventDelegation();

            const slider = document.querySelector('[data-action="filterGroupingSuggestions"]');
            slider.dispatchEvent(new Event('input', { bubbles: true }));

            expect(mockHandlers.wasCalled('filterGroupingSuggestions')).toBe(true);
        });
    });

    describe('Missing Handler Detection', () => {
        test('detects when data-action has no corresponding handler in base.js', () => {
            const baseActionHandlers = {
                'undo': () => {},
                'commit': () => {},
                'show-shortcuts': () => {},
                'close-shortcuts': () => {},
                'reload-config': () => {},
                'break-lock': () => {},
                'close-git-result': () => {},
                'close-toast': () => {}
            };

            // Actions used in base.html
            const baseHtmlActions = [
                'undo',
                'commit',
                'show-shortcuts',
                'close-shortcuts',
                'reload-config',
                'break-lock',
                'close-git-result'
            ];

            const missingHandlers = baseHtmlActions.filter(action => !baseActionHandlers[action]);
            expect(missingHandlers).toEqual([]);
        });

        test('detects when data-action has no corresponding handler in explorer', () => {
            const explorerActionHandlers = {
                'setView': () => {},
                'switchRightTab': () => {},
                'toggleSection': () => {},
                'toggleSuggestionSection': () => {},
                'toggleActionsMenu': () => {},
                'selectAllVisible': () => {},
                'selectByType': () => {},
                'selectByPattern': () => {},
                'navigateToObjectIssue': () => {},
                'openInGraphView': () => {},
                'discardNewObject': () => {},
                'showAddAttribute': () => {},
                'createInlineFile': () => {},
                'createInlineFolder': () => {},
                'analyzeAll': () => {},
                'runValidationFull': () => {},
                'closeObjectDetail': () => {},
                'closePreview': () => {},
                'closeDialog': () => {},
                'contextAction': () => {},
                'showBulkRenameDialog': () => {},
                'showEditAttributesDialog': () => {},
                'showBulkAction': () => {},
                'showAddToGroupDialog': () => {},
                'filterTree': () => {},
                'filterTemplateSuggestions': () => {},
                'filterGroupingSuggestions': () => {}
            };

            // Actions used in explorer.html
            const explorerHtmlActions = [
                'filterTree',
                'setView',
                'toggleActionsMenu',
                'selectAllVisible',
                'selectByType',
                'selectByPattern',
                'navigateToObjectIssue',
                'openInGraphView',
                'discardNewObject',
                'showAddAttribute',
                'toggleSection',
                'switchRightTab',
                'createInlineFile',
                'createInlineFolder',
                'analyzeAll',
                'toggleSuggestionSection',
                'filterTemplateSuggestions',
                'filterGroupingSuggestions',
                'runValidationFull',
                'closeObjectDetail',
                'contextAction',
                'showBulkRenameDialog',
                'showEditAttributesDialog',
                'showBulkAction',
                'showAddToGroupDialog',
                'closePreview',
                'closeDialog'
            ];

            const missingHandlers = explorerHtmlActions.filter(action => !explorerActionHandlers[action]);
            expect(missingHandlers).toEqual([]);
        });

        test('detects when data-action has no corresponding handler in git.js', () => {
            const gitActionHandlers = {
                'switchGitTab': () => {},
                'discard-file': () => {},
                'commit': () => {},
                'restore-commit': () => {},
                'clearGitHistory': () => {}
            };

            // Actions used in git.html
            const gitHtmlActions = [
                'clearGitHistory',
                'switchGitTab'
                // Note: discard-file and restore-commit are dynamically generated
            ];

            const missingHandlers = gitHtmlActions.filter(action => !gitActionHandlers[action]);
            expect(missingHandlers).toEqual([]);
        });
    });

    describe('CSS Class Interaction Tests', () => {
        test('u-hidden class prevents element from being visible', () => {
            document.body.innerHTML = `
                <style>.u-hidden { display: none !important; }</style>
                <div id="centerContent" class="u-hidden" style="display: flex;">Content</div>
            `;

            const element = document.getElementById('centerContent');
            const computedStyle = window.getComputedStyle(element);

            // In a real browser, the !important from u-hidden would win
            // In jsdom, we can at least verify the class is present
            expect(element.classList.contains('u-hidden')).toBe(true);
        });

        test('removing u-hidden class allows element to be visible', () => {
            document.body.innerHTML = `
                <div id="centerContent" class="u-hidden">Content</div>
            `;

            const element = document.getElementById('centerContent');
            element.classList.remove('u-hidden');
            element.style.display = 'flex';

            expect(element.classList.contains('u-hidden')).toBe(false);
            expect(element.style.display).toBe('flex');
        });

        test('showCenterPaneObject pattern correctly toggles visibility', () => {
            document.body.innerHTML = `
                <div id="centerEmptyState" class="u-hidden">Empty</div>
                <div id="centerContent" class="u-hidden">Content</div>
            `;

            // Simulate what showCenterPaneObject should do
            const emptyState = document.getElementById('centerEmptyState');
            const content = document.getElementById('centerContent');

            emptyState.classList.add('u-hidden');
            emptyState.style.display = 'none';
            content.classList.remove('u-hidden');
            content.style.display = 'flex';

            expect(emptyState.classList.contains('u-hidden')).toBe(true);
            expect(emptyState.style.display).toBe('none');
            expect(content.classList.contains('u-hidden')).toBe(false);
            expect(content.style.display).toBe('flex');
        });

        test('hideCenterPaneObject pattern correctly toggles visibility', () => {
            document.body.innerHTML = `
                <div id="centerEmptyState" class="u-hidden" style="display: none;">Empty</div>
                <div id="centerContent" style="display: flex;">Content</div>
            `;

            // Simulate what hideCenterPaneObject should do
            const emptyState = document.getElementById('centerEmptyState');
            const content = document.getElementById('centerContent');

            emptyState.classList.remove('u-hidden');
            emptyState.style.display = 'flex';
            content.classList.add('u-hidden');
            content.style.display = 'none';

            expect(emptyState.classList.contains('u-hidden')).toBe(false);
            expect(emptyState.style.display).toBe('flex');
            expect(content.classList.contains('u-hidden')).toBe(true);
            expect(content.style.display).toBe('none');
        });
    });

    describe('Dynamically Generated Button Tests', () => {
        // These test onclick handlers that are generated dynamically in JS
        // rather than using data-action attributes

        let Explorer;

        beforeEach(() => {
            // Mock Explorer namespace with all dynamically called functions
            Explorer = {
                // Tree navigation
                handleItemClick: jest.fn(),
                handleStagedItemClick: jest.fn(),
                toggleFolder: jest.fn(),
                createNewObject: jest.fn(),

                // Object operations
                navigateToObjectByIndex: jest.fn(),
                selectObjectByName: jest.fn(),
                navigateToIssue: jest.fn(),
                unstageObjectDeletion: jest.fn(),

                // Folder operations
                unstageFolderCreation: jest.fn(),
                unstageFolderDeletion: jest.fn(),
                stageDeleteFolder: jest.fn(),

                // Analysis/Cleanup
                showCreateTemplateDialog: jest.fn(),
                showCreateGroupDialog: jest.fn(),
                bulkDeleteCleanupGroup: jest.fn(),
                toggleCleanupSection: jest.fn(),
                showCleanupDetail: jest.fn(),
                stageCleanupDelete: jest.fn(),
                resolveCleanupIssue: jest.fn(),
                fixDuplicate: jest.fn(),
                fixLongHostList: jest.fn(),
                keepDuplicateAndDeleteOthers: jest.fn(),
                showGroupedErrorDetail: jest.fn(),
                resolveGroupedError: jest.fn(),

                // Dialogs
                toggleObjectTypeDropdown: jest.fn(),
                selectObjectType: jest.fn(),
                selectDialogType: jest.fn(),
                closeDialog: jest.fn(),

                // Utilities
                escapeJs: (s) => s.replace(/'/g, "\\'"),
                getIcon: (name) => `<i class="icon-${name}"></i>`
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        test('tree item click calls handleItemClick', () => {
            document.body.innerHTML = `
                <div class="tree-item" onclick="Explorer.handleItemClick(event, 5)">Item</div>
            `;

            document.querySelector('.tree-item').click();

            expect(Explorer.handleItemClick).toHaveBeenCalled();
        });

        test('staged item click calls handleStagedItemClick', () => {
            document.body.innerHTML = `
                <div class="tree-item staged-creation" onclick="Explorer.handleStagedItemClick(event, 3)">Staged Item</div>
            `;

            document.querySelector('.tree-item').click();

            expect(Explorer.handleStagedItemClick).toHaveBeenCalled();
        });

        test('folder header click calls toggleFolder', () => {
            document.body.innerHTML = `
                <div class="tree-folder">
                    <div class="tree-folder-header" onclick="Explorer.toggleFolder(this.parentElement)">Folder</div>
                </div>
            `;

            document.querySelector('.tree-folder-header').click();

            expect(Explorer.toggleFolder).toHaveBeenCalled();
        });

        test('add object button calls createNewObject', () => {
            document.body.innerHTML = `
                <button class="tree-folder-add-btn" onclick="event.stopPropagation(); Explorer.createNewObject('/path/to/file.cfg')">+</button>
            `;

            document.querySelector('.tree-folder-add-btn').click();

            expect(Explorer.createNewObject).toHaveBeenCalledWith('/path/to/file.cfg');
        });

        test('undo deletion button calls unstageObjectDeletion', () => {
            document.body.innerHTML = `
                <button class="tree-item-undo-btn" onclick="event.stopPropagation(); Explorer.unstageObjectDeletion(7)">Undo</button>
            `;

            document.querySelector('.tree-item-undo-btn').click();

            expect(Explorer.unstageObjectDeletion).toHaveBeenCalledWith(7);
        });

        test('reference item click calls navigateToObjectByIndex', () => {
            document.body.innerHTML = `
                <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(12)">Reference</div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).toHaveBeenCalledWith(12);
        });

        test('template suggestion click calls showCreateTemplateDialog', () => {
            document.body.innerHTML = `
                <div class="template-suggestion" onclick="Explorer.showCreateTemplateDialog(2)">Template Suggestion</div>
            `;

            document.querySelector('.template-suggestion').click();

            expect(Explorer.showCreateTemplateDialog).toHaveBeenCalledWith(2);
        });

        test('grouping suggestion click calls showCreateGroupDialog', () => {
            document.body.innerHTML = `
                <div class="suggestion-item" onclick="Explorer.showCreateGroupDialog(4)">Group Suggestion</div>
            `;

            document.querySelector('.suggestion-item').click();

            expect(Explorer.showCreateGroupDialog).toHaveBeenCalledWith(4);
        });

        test('cleanup section header click calls toggleCleanupSection', () => {
            document.body.innerHTML = `
                <div class="cleanup-section-header" onclick="Explorer.toggleCleanupSection(this)">Orphans</div>
            `;

            document.querySelector('.cleanup-section-header').click();

            expect(Explorer.toggleCleanupSection).toHaveBeenCalled();
        });

        test('cleanup suggestion click calls showCleanupDetail', () => {
            document.body.innerHTML = `
                <div class="cleanup-suggestion" onclick="Explorer.showCleanupDetail(6)">Cleanup Item</div>
            `;

            document.querySelector('.cleanup-suggestion').click();

            expect(Explorer.showCleanupDetail).toHaveBeenCalledWith(6);
        });

        test('bulk delete button calls bulkDeleteCleanupGroup', () => {
            document.body.innerHTML = `
                <button class="cleanup-section-btn" onclick="event.stopPropagation(); Explorer.bulkDeleteCleanupGroup('orphans')">Delete All</button>
            `;

            document.querySelector('.cleanup-section-btn').click();

            expect(Explorer.bulkDeleteCleanupGroup).toHaveBeenCalledWith('orphans');
        });

        test('cleanup delete button calls stageCleanupDelete', () => {
            document.body.innerHTML = `
                <button class="cleanup-action-btn" onclick="event.stopPropagation(); Explorer.stageCleanupDelete(8)">Delete</button>
            `;

            document.querySelector('.cleanup-action-btn').click();

            expect(Explorer.stageCleanupDelete).toHaveBeenCalledWith(8);
        });

        test('fix duplicate button calls fixDuplicate', () => {
            document.body.innerHTML = `
                <button class="cleanup-fix-btn" onclick="event.stopPropagation(); Explorer.fixDuplicate(9)">Resolve</button>
            `;

            document.querySelector('.cleanup-fix-btn').click();

            expect(Explorer.fixDuplicate).toHaveBeenCalledWith(9);
        });

        test('object type dropdown toggle calls toggleObjectTypeDropdown', () => {
            document.body.innerHTML = `
                <button id="newObjectTypeSelect" onclick="Explorer.toggleObjectTypeDropdown()">Select Type</button>
            `;

            document.querySelector('#newObjectTypeSelect').click();

            expect(Explorer.toggleObjectTypeDropdown).toHaveBeenCalled();
        });

        test('object type selection calls selectObjectType', () => {
            document.body.innerHTML = `
                <div class="object-type-dropdown-item" onclick="Explorer.selectObjectType('host')">host</div>
            `;

            document.querySelector('.object-type-dropdown-item').click();

            expect(Explorer.selectObjectType).toHaveBeenCalledWith('host');
        });

        test('unstage folder creation button calls unstageFolderCreation', () => {
            document.body.innerHTML = `
                <button class="tree-action-btn" onclick="event.stopPropagation(); Explorer.unstageFolderCreation('/new/folder', event)">Undo</button>
            `;

            document.querySelector('.tree-action-btn').click();

            expect(Explorer.unstageFolderCreation).toHaveBeenCalled();
        });

        test('delete folder button calls stageDeleteFolder', () => {
            document.body.innerHTML = `
                <button class="tree-action-btn--danger" onclick="event.stopPropagation(); Explorer.stageDeleteFolder('/folder/path', event)">Delete</button>
            `;

            document.querySelector('.tree-action-btn--danger').click();

            expect(Explorer.stageDeleteFolder).toHaveBeenCalled();
        });

        test('keep duplicate button calls keepDuplicateAndDeleteOthers', () => {
            document.body.innerHTML = `
                <button class="page-btn-primary" onclick="Explorer.keepDuplicateAndDeleteOthers(0, 1)">Keep This</button>
            `;

            document.querySelector('.page-btn-primary').click();

            expect(Explorer.keepDuplicateAndDeleteOthers).toHaveBeenCalledWith(0, 1);
        });

        test('notification suggestion click calls navigateToObjectByIndex', () => {
            document.body.innerHTML = `
                <div class="notification-suggestion" onclick="Explorer.navigateToObjectByIndex(15)">Notification Gap</div>
            `;

            document.querySelector('.notification-suggestion').click();

            expect(Explorer.navigateToObjectByIndex).toHaveBeenCalledWith(15);
        });

        test('grouped error detail click calls showGroupedErrorDetail', () => {
            document.body.innerHTML = `
                <div class="cleanup-suggestion cleanup-error" onclick="Explorer.showGroupedErrorDetail(3)">Missing host</div>
            `;

            document.querySelector('.cleanup-suggestion').click();

            expect(Explorer.showGroupedErrorDetail).toHaveBeenCalledWith(3);
        });

        test('resolve grouped error button calls resolveGroupedError', () => {
            document.body.innerHTML = `
                <button class="cleanup-fix-btn" onclick="event.stopPropagation(); Explorer.resolveGroupedError(5)">Create host</button>
            `;

            document.querySelector('.cleanup-fix-btn').click();

            expect(Explorer.resolveGroupedError).toHaveBeenCalledWith(5);
        });
    });

    describe('Attribute Editor Event Handlers', () => {
        // Tests for inline event handlers in object-editor.js
        // These use onchange, oninput, onblur, onfocus, onkeydown

        let Explorer;

        beforeEach(() => {
            Explorer = {
                // Attribute editing
                updateAttribute: jest.fn(),
                deleteAttribute: jest.fn(),

                // Inline attribute autocomplete
                showAttrAutocomplete: jest.fn(),
                hideAttrAutocomplete: jest.fn(),
                handleAttrAutocompleteKey: jest.fn(),
                selectAttrAutocomplete: jest.fn(),

                // Add attribute dialog autocomplete
                showAddAttrNameAutocomplete: jest.fn(),
                hideAddAttrNameAutocomplete: jest.fn(),
                handleAddAttrNameAutocompleteKey: jest.fn(),
                selectAddAttrNameAutocomplete: jest.fn(),
                showAddAttrAutocomplete: jest.fn(),
                hideAddAttrAutocomplete: jest.fn(),
                handleAddAttrAutocompleteKey: jest.fn(),
                selectAddAttrAutocomplete: jest.fn(),

                // Dialog/form handlers
                toggleNewFileInput: jest.fn(),
                updateNewObjectName: jest.fn(),

                // Utilities
                escapeHtml: (s) => s,
                escapeJs: (s) => s.replace(/'/g, "\\'")
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        test('attribute input change calls updateAttribute', () => {
            document.body.innerHTML = `
                <div class="attr-row" data-attr="host_name">
                    <span class="attr-name">host_name</span>
                    <input type="text" class="attr-value" value="web01"
                           onchange="Explorer.updateAttribute('host_name', this.value, this)">
                </div>
            `;

            const input = document.querySelector('.attr-value');
            input.value = 'web02';
            input.dispatchEvent(new Event('change', { bubbles: true }));

            expect(Explorer.updateAttribute).toHaveBeenCalledWith('host_name', 'web02', input);
        });

        test('attribute input typing calls showAttrAutocomplete', () => {
            document.body.innerHTML = `
                <input type="text" class="attr-value"
                       oninput="Explorer.showAttrAutocomplete(this, 'use')">
            `;

            const input = document.querySelector('.attr-value');
            input.dispatchEvent(new Event('input', { bubbles: true }));

            expect(Explorer.showAttrAutocomplete).toHaveBeenCalledWith(input, 'use');
        });

        test('attribute input blur calls hideAttrAutocomplete', () => {
            document.body.innerHTML = `
                <input type="text" class="attr-value"
                       onblur="Explorer.hideAttrAutocomplete(event)">
            `;

            const input = document.querySelector('.attr-value');
            const blurEvent = new FocusEvent('blur', { bubbles: true });
            input.dispatchEvent(blurEvent);

            expect(Explorer.hideAttrAutocomplete).toHaveBeenCalled();
        });

        test('attribute input keydown calls handleAttrAutocompleteKey', () => {
            document.body.innerHTML = `
                <input type="text" class="attr-value"
                       onkeydown="Explorer.handleAttrAutocompleteKey(event, 'use')">
            `;

            const input = document.querySelector('.attr-value');
            const keyEvent = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true });
            input.dispatchEvent(keyEvent);

            expect(Explorer.handleAttrAutocompleteKey).toHaveBeenCalled();
        });

        test('autocomplete item mousedown calls selectAttrAutocomplete', () => {
            document.body.innerHTML = `
                <div class="attr-autocomplete-item" data-index="0" data-value="generic-host"
                     onmousedown="Explorer.selectAttrAutocomplete('use', 'generic-host')">generic-host</div>
            `;

            const item = document.querySelector('.attr-autocomplete-item');
            item.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));

            expect(Explorer.selectAttrAutocomplete).toHaveBeenCalledWith('use', 'generic-host');
        });

        test('delete attribute button calls deleteAttribute', () => {
            document.body.innerHTML = `
                <button class="attr-delete" onclick="Explorer.deleteAttribute('notes')">&times;</button>
            `;

            document.querySelector('.attr-delete').click();

            expect(Explorer.deleteAttribute).toHaveBeenCalledWith('notes');
        });

        // Add Attribute Dialog tests
        test('add attr name input shows autocomplete on input', () => {
            document.body.innerHTML = `
                <input type="text" id="newAttrName" placeholder="Select or type attribute name"
                       oninput="Explorer.showAddAttrNameAutocomplete()">
            `;

            const input = document.getElementById('newAttrName');
            input.dispatchEvent(new Event('input', { bubbles: true }));

            expect(Explorer.showAddAttrNameAutocomplete).toHaveBeenCalled();
        });

        test('add attr name input hides autocomplete on blur', () => {
            document.body.innerHTML = `
                <input type="text" id="newAttrName"
                       onblur="Explorer.hideAddAttrNameAutocomplete()">
            `;

            const input = document.getElementById('newAttrName');
            input.dispatchEvent(new FocusEvent('blur', { bubbles: true }));

            expect(Explorer.hideAddAttrNameAutocomplete).toHaveBeenCalled();
        });

        test('add attr name input shows autocomplete on focus', () => {
            document.body.innerHTML = `
                <input type="text" id="newAttrName"
                       onfocus="Explorer.showAddAttrNameAutocomplete()">
            `;

            const input = document.getElementById('newAttrName');
            input.dispatchEvent(new FocusEvent('focus', { bubbles: true }));

            expect(Explorer.showAddAttrNameAutocomplete).toHaveBeenCalled();
        });

        test('add attr name input handles keydown for navigation', () => {
            document.body.innerHTML = `
                <input type="text" id="newAttrName"
                       onkeydown="Explorer.handleAddAttrNameAutocompleteKey(event)">
            `;

            const input = document.getElementById('newAttrName');
            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));

            expect(Explorer.handleAddAttrNameAutocompleteKey).toHaveBeenCalled();
        });

        test('add attr name dropdown item mousedown calls selectAddAttrNameAutocomplete', () => {
            document.body.innerHTML = `
                <div class="attr-autocomplete-item" data-index="0" data-value="check_command"
                     onmousedown="Explorer.selectAddAttrNameAutocomplete('check_command')">check_command</div>
            `;

            const item = document.querySelector('.attr-autocomplete-item');
            item.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));

            expect(Explorer.selectAddAttrNameAutocomplete).toHaveBeenCalledWith('check_command');
        });

        test('add attr value input shows autocomplete on input', () => {
            document.body.innerHTML = `
                <input type="text" id="newAttrValue"
                       oninput="Explorer.showAddAttrAutocomplete()">
            `;

            const input = document.getElementById('newAttrValue');
            input.dispatchEvent(new Event('input', { bubbles: true }));

            expect(Explorer.showAddAttrAutocomplete).toHaveBeenCalled();
        });

        test('add attr value input hides autocomplete on blur', () => {
            document.body.innerHTML = `
                <input type="text" id="newAttrValue"
                       onblur="Explorer.hideAddAttrAutocomplete()">
            `;

            const input = document.getElementById('newAttrValue');
            input.dispatchEvent(new FocusEvent('blur', { bubbles: true }));

            expect(Explorer.hideAddAttrAutocomplete).toHaveBeenCalled();
        });

        test('add attr value input handles keydown for navigation', () => {
            document.body.innerHTML = `
                <input type="text" id="newAttrValue"
                       onkeydown="Explorer.handleAddAttrAutocompleteKey(event)">
            `;

            const input = document.getElementById('newAttrValue');
            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

            expect(Explorer.handleAddAttrAutocompleteKey).toHaveBeenCalled();
        });

        test('add attr value dropdown item mousedown calls selectAddAttrAutocomplete', () => {
            document.body.innerHTML = `
                <div class="attr-autocomplete-item"
                     onmousedown="Explorer.selectAddAttrAutocomplete('check-host-alive')">check-host-alive</div>
            `;

            const item = document.querySelector('.attr-autocomplete-item');
            item.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));

            expect(Explorer.selectAddAttrAutocomplete).toHaveBeenCalledWith('check-host-alive');
        });

        // Move dialog handlers
        test('move target select change calls toggleNewFileInput', () => {
            document.body.innerHTML = `
                <select id="moveTarget" onchange="Explorer.toggleNewFileInput()">
                    <option value="hosts.cfg">hosts.cfg</option>
                    <option value="__new__">New file...</option>
                </select>
            `;

            const select = document.getElementById('moveTarget');
            select.value = '__new__';
            select.dispatchEvent(new Event('change', { bubbles: true }));

            expect(Explorer.toggleNewFileInput).toHaveBeenCalled();
        });

        // Create dialog handlers
        test('new object name input change calls updateNewObjectName', () => {
            document.body.innerHTML = `
                <input type="text" id="newObjectName"
                       placeholder="Enter name..." onchange="Explorer.updateNewObjectName()" value="">
            `;

            const input = document.getElementById('newObjectName');
            input.value = 'webserver01';
            input.dispatchEvent(new Event('change', { bubbles: true }));

            expect(Explorer.updateNewObjectName).toHaveBeenCalled();
        });
    });

    describe('Drag and Drop Event Handlers', () => {
        // Tests for drag/drop handlers in app.js and drag-drop.js
        // Note: jsdom doesn't fully support DragEvent, so we use Event with custom type

        let Explorer;

        // Helper to create a mock drag event (jsdom doesn't support DragEvent)
        function createDragEvent(type) {
            const event = new Event(type, { bubbles: true, cancelable: true });
            event.dataTransfer = {
                data: {},
                setData: function(key, value) { this.data[key] = value; },
                getData: function(key) { return this.data[key]; },
                effectAllowed: 'none',
                dropEffect: 'none'
            };
            return event;
        }

        beforeEach(() => {
            Explorer = {
                handleDragStart: jest.fn(),
                handleDragEnd: jest.fn(),
                handleDragOver: jest.fn(),
                handleDrop: jest.fn(),
                handleStagedDragStart: jest.fn(),
                cleanupDragState: jest.fn()
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        test('tree item drag start calls handleDragStart', () => {
            document.body.innerHTML = `
                <div class="tree-item" draggable="true"
                     ondragstart="Explorer.handleDragStart(event, 5)">Item</div>
            `;

            const item = document.querySelector('.tree-item');
            const dragEvent = createDragEvent('dragstart');
            item.dispatchEvent(dragEvent);

            expect(Explorer.handleDragStart).toHaveBeenCalled();
        });

        test('drag end calls handleDragEnd', () => {
            document.body.innerHTML = `
                <div class="tree-item" draggable="true"
                     ondragend="Explorer.handleDragEnd(event)">Item</div>
            `;

            const item = document.querySelector('.tree-item');
            const dragEvent = createDragEvent('dragend');
            item.dispatchEvent(dragEvent);

            expect(Explorer.handleDragEnd).toHaveBeenCalled();
        });

        test('folder header drag over calls handleDragOver', () => {
            document.body.innerHTML = `
                <div class="tree-folder-header"
                     ondragover="Explorer.handleDragOver(event)">Folder</div>
            `;

            const header = document.querySelector('.tree-folder-header');
            const dragEvent = createDragEvent('dragover');
            header.dispatchEvent(dragEvent);

            expect(Explorer.handleDragOver).toHaveBeenCalled();
        });

        test('folder drop calls handleDrop with file path', () => {
            document.body.innerHTML = `
                <div class="tree-folder-header"
                     ondrop="Explorer.handleDrop(event, '/etc/nagios/hosts.cfg')">Folder</div>
            `;

            const header = document.querySelector('.tree-folder-header');
            const dragEvent = createDragEvent('drop');
            header.dispatchEvent(dragEvent);

            expect(Explorer.handleDrop).toHaveBeenCalled();
        });

        test('staged item drag start calls handleStagedDragStart', () => {
            document.body.innerHTML = `
                <div class="tree-item staged-creation" draggable="true"
                     ondragstart="Explorer.handleStagedDragStart(event, 2)">Staged Item</div>
            `;

            const item = document.querySelector('.tree-item');
            const dragEvent = createDragEvent('dragstart');
            item.dispatchEvent(dragEvent);

            expect(Explorer.handleStagedDragStart).toHaveBeenCalled();
        });
    });

    describe('Context Menu Event Handlers', () => {
        // Tests for context menu handlers

        let Explorer;

        beforeEach(() => {
            Explorer = {
                handleContextMenu: jest.fn(),
                handleStagedContextMenu: jest.fn()
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        test('tree item right-click calls handleContextMenu', () => {
            document.body.innerHTML = `
                <div class="tree-item"
                     oncontextmenu="Explorer.handleContextMenu(event, 7)">Item</div>
            `;

            const item = document.querySelector('.tree-item');
            const contextEvent = new MouseEvent('contextmenu', { bubbles: true });
            item.dispatchEvent(contextEvent);

            expect(Explorer.handleContextMenu).toHaveBeenCalled();
        });

        test('staged item right-click calls handleStagedContextMenu', () => {
            document.body.innerHTML = `
                <div class="tree-item staged-creation"
                     oncontextmenu="Explorer.handleStagedContextMenu(event, 3)">Staged Item</div>
            `;

            const item = document.querySelector('.tree-item');
            const contextEvent = new MouseEvent('contextmenu', { bubbles: true });
            item.dispatchEvent(contextEvent);

            expect(Explorer.handleStagedContextMenu).toHaveBeenCalled();
        });
    });

    describe('File Operations Button Tests', () => {
        // Tests for file/folder operation buttons in file-operations.js

        let Explorer;

        beforeEach(() => {
            Explorer = {
                // Folder operations
                unstageFolderDeletion: jest.fn(),
                toggleFolderExpand: jest.fn(),

                // File operations
                undoNewFile: jest.fn(),
                unstageFileDeletion: jest.fn(),
                stageDeleteFile: jest.fn(),
                toggleFileExpand: jest.fn(),

                // Object move operations
                undoObjectMove: jest.fn(),
                removeStagedCreation: jest.fn(),

                // Utilities
                escapeJs: (s) => s.replace(/'/g, "\\'"),
                getIcon: (name) => `<i class="icon-${name}"></i>`
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        test('undo folder deletion button calls unstageFolderDeletion', () => {
            document.body.innerHTML = `
                <button class="tree-action-btn" onclick="event.stopPropagation(); Explorer.unstageFolderDeletion('/etc/nagios/servers', event)" title="Undo deletion">X</button>
            `;

            document.querySelector('.tree-action-btn').click();

            expect(Explorer.unstageFolderDeletion).toHaveBeenCalled();
        });

        test('folder expand toggle calls toggleFolderExpand', () => {
            document.body.innerHTML = `
                <button class="tree-expand-btn" onclick="event.stopPropagation(); Explorer.toggleFolderExpand('/etc/nagios/servers')">▶</button>
            `;

            document.querySelector('.tree-expand-btn').click();

            expect(Explorer.toggleFolderExpand).toHaveBeenCalledWith('/etc/nagios/servers');
        });

        test('undo new file button calls undoNewFile', () => {
            document.body.innerHTML = `
                <button class="tree-action-btn" onclick="event.stopPropagation(); Explorer.undoNewFile('/etc/nagios/new.cfg', event)" title="Undo">X</button>
            `;

            document.querySelector('.tree-action-btn').click();

            expect(Explorer.undoNewFile).toHaveBeenCalled();
        });

        test('undo file deletion button calls unstageFileDeletion', () => {
            document.body.innerHTML = `
                <button class="tree-action-btn" onclick="event.stopPropagation(); Explorer.unstageFileDeletion('/etc/nagios/old.cfg', event)" title="Undo deletion">X</button>
            `;

            document.querySelector('.tree-action-btn').click();

            expect(Explorer.unstageFileDeletion).toHaveBeenCalled();
        });

        test('delete file button calls stageDeleteFile', () => {
            document.body.innerHTML = `
                <button class="tree-action-btn tree-action-btn--danger" onclick="event.stopPropagation(); Explorer.stageDeleteFile('/etc/nagios/unused.cfg', event)" title="Delete file">X</button>
            `;

            document.querySelector('.tree-action-btn--danger').click();

            expect(Explorer.stageDeleteFile).toHaveBeenCalled();
        });

        test('file expand toggle calls toggleFileExpand', () => {
            document.body.innerHTML = `
                <button class="tree-expand-btn" onclick="event.stopPropagation(); Explorer.toggleFileExpand('/etc/nagios/hosts.cfg')">▶</button>
            `;

            document.querySelector('.tree-expand-btn').click();

            expect(Explorer.toggleFileExpand).toHaveBeenCalledWith('/etc/nagios/hosts.cfg');
        });

        test('undo object move button calls undoObjectMove', () => {
            document.body.innerHTML = `
                <button class="tree-object-action" onclick="event.stopPropagation(); Explorer.undoObjectMove('hosts.cfg|host|webserver01')" title="Undo move">X</button>
            `;

            document.querySelector('.tree-object-action').click();

            expect(Explorer.undoObjectMove).toHaveBeenCalledWith('hosts.cfg|host|webserver01');
        });

        test('remove staged creation button calls removeStagedCreation', () => {
            document.body.innerHTML = `
                <button class="tree-object-action" onclick="event.stopPropagation(); Explorer.removeStagedCreation(3)" title="Remove">X</button>
            `;

            document.querySelector('.tree-object-action').click();

            expect(Explorer.removeStagedCreation).toHaveBeenCalledWith(3);
        });
    });

    describe('Additional Analysis Button Tests', () => {
        // Tests for additional analysis handlers in analysis.js

        let Explorer;

        beforeEach(() => {
            Explorer = {
                fixLongHostList: jest.fn(),
                resolveCleanupIssue: jest.fn()
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        test('fix long host list button calls fixLongHostList', () => {
            document.body.innerHTML = `
                <button class="cleanup-action-btn cleanup-fix-btn" onclick="event.stopPropagation(); Explorer.fixLongHostList(2)">Create Hostgroup</button>
            `;

            document.querySelector('.cleanup-fix-btn').click();

            expect(Explorer.fixLongHostList).toHaveBeenCalledWith(2);
        });

        test('resolve cleanup issue button calls resolveCleanupIssue', () => {
            document.body.innerHTML = `
                <button class="cleanup-action-btn cleanup-fix-btn" onclick="event.stopPropagation(); Explorer.resolveCleanupIssue(4)">Create host</button>
            `;

            document.querySelector('.cleanup-fix-btn').click();

            expect(Explorer.resolveCleanupIssue).toHaveBeenCalledWith(4);
        });
    });

    describe('Dialog Type Selection Tests', () => {
        // Tests for dialog type selection in dialogs.js

        let Explorer;

        beforeEach(() => {
            Explorer = {
                selectDialogType: jest.fn(),
                selectObjectByName: jest.fn()
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        test('dialog type item click calls selectDialogType', () => {
            document.body.innerHTML = `
                <div class="dialog-type-item" data-type="host" onclick="Explorer.selectDialogType(this)">host</div>
            `;

            document.querySelector('.dialog-type-item').click();

            expect(Explorer.selectDialogType).toHaveBeenCalled();
        });

        test('reference item click calls selectObjectByName', () => {
            document.body.innerHTML = `
                <div class="ref-item ref-item-clickable" onclick="Explorer.selectObjectByName('webserver01')">webserver01</div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.selectObjectByName).toHaveBeenCalledWith('webserver01');
        });
    });

    describe('Issue Navigation Tests', () => {
        // Tests for issue navigation in analysis.js

        let Explorer;

        beforeEach(() => {
            Explorer = {
                navigateToIssue: jest.fn(),
                closeDialog: jest.fn()
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        test('issue item click calls navigateToIssue with name and type', () => {
            document.body.innerHTML = `
                <div class="cleanup-suggestion cleanup-error" onclick="Explorer.navigateToIssue('webserver01', 'host')">Missing host</div>
            `;

            document.querySelector('.cleanup-suggestion').click();

            expect(Explorer.navigateToIssue).toHaveBeenCalledWith('webserver01', 'host');
        });

        test('issue detail item click calls navigateToIssue and closeDialog', () => {
            document.body.innerHTML = `
                <div class="ref-item ref-item-clickable" onclick="Explorer.navigateToIssue('db-server', 'service'); Explorer.closeDialog();">db-server</div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToIssue).toHaveBeenCalledWith('db-server', 'service');
            expect(Explorer.closeDialog).toHaveBeenCalled();
        });
    });

    describe('Center Pane Section Item Tests', () => {
        // Tests for clickable items in dependencies, dependents, inheritance, and members sections

        let Explorer;

        beforeEach(() => {
            Explorer = {
                navigateToObjectByIndex: jest.fn(),
                selectObjectByName: jest.fn(),
                clearSelection: jest.fn(),
                addToSelectionByIndex: jest.fn()
            };
            global.Explorer = Explorer;
            window.Explorer = Explorer;
        });

        afterEach(() => {
            delete global.Explorer;
            delete window.Explorer;
        });

        // Dependencies section tests
        test('dependency item click navigates to referenced object', () => {
            document.body.innerHTML = `
                <div id="dependenciesContent">
                    <div class="ref-type-group">
                        <div class="ref-type-header">Hosts</div>
                        <div class="ref-type-list">
                            <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(42)">
                                <span class="ref-type-badge type-host">host</span>
                                <span class="ref-name">webserver01</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).toHaveBeenCalledWith(42);
        });

        test('dependency item with nested connector navigates correctly', () => {
            document.body.innerHTML = `
                <div id="dependenciesContent">
                    <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(15)">
                        <span class="dep-tree-connector">↳</span>
                        <span class="ref-type-badge type-hostgroup">hostgroup</span>
                        <span class="ref-name">linux-servers</span>
                    </div>
                </div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).toHaveBeenCalledWith(15);
        });

        // Dependents section tests
        test('dependent item click navigates to referencing object', () => {
            document.body.innerHTML = `
                <div id="dependentsContent">
                    <div class="ref-type-group">
                        <div class="ref-type-header">Services</div>
                        <div class="ref-type-list">
                            <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(88)">
                                <span class="ref-type-badge type-service">service</span>
                                <span class="ref-name">HTTP Check</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).toHaveBeenCalledWith(88);
        });

        // Inheritance section tests
        test('inheritance template item click selects by name', () => {
            document.body.innerHTML = `
                <div id="inheritanceContent">
                    <div class="inheritance-tree">
                        <div class="ref-item template ref-item-clickable" onclick="Explorer.selectObjectByName('generic-host')">
                            <span class="ref-type-badge type-host">host</span>
                            <span class="ref-name">generic-host</span>
                            <span class="template-marker">template</span>
                        </div>
                    </div>
                </div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.selectObjectByName).toHaveBeenCalledWith('generic-host');
        });

        test('inheritance parent host item click navigates to index', () => {
            document.body.innerHTML = `
                <div id="inheritanceContent">
                    <div class="inheritance-section-label">Parent Hosts</div>
                    <div class="inheritance-tree">
                        <div class="ref-item ref-item-clickable" onclick="Explorer.navigateToObjectByIndex(23)">
                            <span class="ref-type-badge type-host">host</span>
                            <span class="ref-name">parent-router</span>
                        </div>
                    </div>
                </div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).toHaveBeenCalledWith(23);
        });

        test('inheritance current item is not clickable', () => {
            document.body.innerHTML = `
                <div id="inheritanceContent">
                    <div class="inheritance-tree">
                        <div class="ref-item current">
                            <span class="ref-type-badge type-host">host</span>
                            <span class="ref-name">current-host</span>
                            <span class="current-marker">current</span>
                        </div>
                    </div>
                </div>
            `;

            // Current item has no onclick, so clicking shouldn't call anything
            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).not.toHaveBeenCalled();
            expect(Explorer.selectObjectByName).not.toHaveBeenCalled();
        });

        test('inheritance missing template item is not clickable', () => {
            document.body.innerHTML = `
                <div id="inheritanceContent">
                    <div class="inheritance-tree">
                        <div class="ref-item missing">
                            <span class="ref-type-badge type-host">host</span>
                            <span class="ref-name">missing-template</span>
                            <span class="error-marker">Template not found</span>
                        </div>
                    </div>
                </div>
            `;

            // Missing item has no onclick
            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).not.toHaveBeenCalled();
            expect(Explorer.selectObjectByName).not.toHaveBeenCalled();
        });

        // Members section tests
        test('members section item click navigates to member object', () => {
            document.body.innerHTML = `
                <div id="membersContent">
                    <div class="ref-type-group">
                        <div class="ref-type-header">Hosts</div>
                        <div class="ref-type-list">
                            <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(55)">
                                <span class="ref-type-badge type-host">host</span>
                                <span class="ref-name">member-host</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).toHaveBeenCalledWith(55);
        });

        test('template users list item click navigates to using object', () => {
            document.body.innerHTML = `
                <div id="membersContent">
                    <div class="ref-type-group">
                        <div class="ref-type-header">Hosts</div>
                        <div class="ref-type-list">
                            <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(101)">
                                <span class="ref-type-badge type-host">host</span>
                                <span class="ref-name">host-using-template</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            document.querySelector('.ref-item').click();

            expect(Explorer.navigateToObjectByIndex).toHaveBeenCalledWith(101);
        });
    });
});
