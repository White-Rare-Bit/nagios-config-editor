# Editor Tabs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a tabbed interface to the center pane so users can have multiple objects open simultaneously and switch between them.

**Architecture:** New `tab-manager.js` module owns all tab state and logic. The key integration point is `navigateToObjectByIndex()` in `file-operations.js` — updating it to call `openTab()` captures most navigation paths. `updateSelection()` in `app.js` handles the remaining tree-click path. Tab bar HTML is injected into the center pane above the existing breadcrumb. CSS goes in `explorer.css`.

**Tech Stack:** Vanilla JavaScript (IIFE pattern), CSS custom properties (`--nbe-*`), `sessionStorage` for persistence.

**Design doc:** `docs/plans/2026-02-11-editor-tabs-design.md`

---

### Task 1: Add tab state to Explorer.state and persistence helpers

**Files:**
- Modify: `static/js/explorer/main.js:48-61` (add tab state fields)

**Step 1: Add tab state fields to Explorer.state**

In `static/js/explorer/main.js`, add these fields after line 56 (`selectedFolder`), inside the `Explorer.state` object:

```javascript
    // Tab state
    openTabs: [],              // Array of { key, objectIndex, label, typeIcon }
    activeTabKey: null,        // Stable key of currently active tab
    isTabSwitch: false,        // Guard flag to prevent tab↔tree infinite loop
```

**Step 2: Run tests to verify no regressions**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass (state additions don't affect backend)

**Step 3: Commit**

```bash
git add static/js/explorer/main.js
git commit -m "feat(tabs): add tab state fields to Explorer.state"
```

---

### Task 2: Create tab-manager.js module with core tab logic

**Files:**
- Create: `static/js/explorer/tab-manager.js`

**Step 1: Create the tab-manager.js module**

Create `static/js/explorer/tab-manager.js` with the following content:

```javascript
/**
 * Tab Manager Module
 *
 * Manages the tabbed interface for the center pane object editor.
 * Tabs are purely a frontend navigation concept — no server changes.
 *
 * Dependencies:
 * - window.Explorer (from main.js)
 * - Explorer.state (shared state object)
 * - Explorer.showCenterPaneObject (from object-editor.js)
 * - Explorer.hideCenterPaneObject (from object-editor.js)
 * - Explorer.checkForChanges (from object-editor.js)
 * - Explorer.getObjectKey (from main.js)
 * - Explorer.getObjectTypeIcon (from app.js)
 */
(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // =========================================================================
    // Persistence
    // =========================================================================

    /**
     * Save open tabs to sessionStorage
     */
    function persistTabs() {
        try {
            sessionStorage.setItem('explorerTabs', JSON.stringify({
                openTabs: state.openTabs,
                activeTabKey: state.activeTabKey
            }));
        } catch (e) {
            // Ignore storage errors
        }
    }

    /**
     * Restore tabs from sessionStorage.
     * Called after loadObjects() so allObjects is populated.
     * Validates that each tab's stable key still exists.
     */
    function restoreTabs() {
        try {
            const saved = sessionStorage.getItem('explorerTabs');
            if (!saved) return;
            const { openTabs, activeTabKey } = JSON.parse(saved);
            if (!Array.isArray(openTabs)) return;

            // Validate each tab still exists in loaded objects
            state.openTabs = [];
            for (const tab of openTabs) {
                const obj = Explorer.findObjectByKey(tab.key);
                if (obj) {
                    state.openTabs.push({
                        key: tab.key,
                        objectIndex: obj.global_index,
                        label: obj.display_name || tab.label,
                        typeIcon: obj.object_type
                    });
                }
            }

            // Restore active tab if it still exists
            if (activeTabKey && state.openTabs.some(t => t.key === activeTabKey)) {
                state.activeTabKey = activeTabKey;
            } else if (state.openTabs.length > 0) {
                state.activeTabKey = state.openTabs[0].key;
            }
        } catch (e) {
            // Ignore parse errors
        }
    }

    // =========================================================================
    // Core Tab Operations
    // =========================================================================

    /**
     * Open an object in a tab. If already open, switch to it.
     * This is the main entry point — all navigation should call this.
     * @param {Object} obj - The NagiosObject to open
     */
    function openTab(obj) {
        if (!obj) return;

        const key = Explorer.getObjectKey(obj);

        // Auto-stage current edits before switching
        if (state.activeTabKey && state.activeTabKey !== key && state.editedObject) {
            Explorer.checkForChanges();
        }

        // Check if tab already exists
        const existingIdx = state.openTabs.findIndex(t => t.key === key);
        if (existingIdx >= 0) {
            // Update label in case it changed (rename)
            state.openTabs[existingIdx].label = obj.display_name;
            state.openTabs[existingIdx].objectIndex = obj.global_index;
            state.activeTabKey = key;
        } else {
            // Create new tab
            state.openTabs.push({
                key: key,
                objectIndex: obj.global_index,
                label: obj.display_name,
                typeIcon: obj.object_type
            });
            state.activeTabKey = key;
        }

        // Render the object in center pane
        Explorer.showCenterPaneObject(obj);

        // Render tab bar and persist
        renderTabBar();
        persistTabs();
    }

    /**
     * Close a tab by its stable key.
     * @param {string} key - Stable key of the tab to close
     */
    function closeTab(key) {
        const idx = state.openTabs.findIndex(t => t.key === key);
        if (idx < 0) return;

        // Auto-stage if closing the active tab
        if (state.activeTabKey === key && state.editedObject) {
            Explorer.checkForChanges();
        }

        state.openTabs.splice(idx, 1);

        // If we closed the active tab, activate an adjacent one
        if (state.activeTabKey === key) {
            if (state.openTabs.length === 0) {
                state.activeTabKey = null;
                Explorer.hideCenterPaneObject();
                Explorer.clearSelection();
                Explorer.updateSelection();
            } else {
                // Activate the tab at the same index (or last one)
                const newIdx = Math.min(idx, state.openTabs.length - 1);
                const newTab = state.openTabs[newIdx];
                state.activeTabKey = newTab.key;

                const obj = Explorer.findObjectByKey(newTab.key);
                if (obj) {
                    Explorer.showCenterPaneObject(obj);
                    // Sync tree selection
                    syncTreeSelection(obj);
                }
            }
        }

        renderTabBar();
        persistTabs();
    }

    /**
     * Activate a tab by its stable key (tab click handler).
     * @param {string} key - Stable key of the tab to activate
     */
    function activateTab(key) {
        if (state.activeTabKey === key) return;

        // Auto-stage current edits
        if (state.editedObject) {
            Explorer.checkForChanges();
        }

        state.activeTabKey = key;
        const tab = state.openTabs.find(t => t.key === key);
        if (!tab) return;

        const obj = Explorer.findObjectByKey(key);
        if (obj) {
            Explorer.showCenterPaneObject(obj);
            syncTreeSelection(obj);
        }

        renderTabBar();
        persistTabs();
    }

    /**
     * Sync tree selection to match the active tab.
     * Uses isTabSwitch flag to prevent updateSelection from re-triggering openTab.
     */
    function syncTreeSelection(obj) {
        state.isTabSwitch = true;
        Explorer.clearSelection();
        state.selectedKeys.add(Explorer.getObjectKey(obj));

        // Highlight in tree without triggering showCenterPaneObject again
        document.querySelectorAll('.tree-item').forEach(el => {
            const index = parseInt(el.dataset.index);
            el.classList.toggle('selected', Explorer.isSelectedByIndex(index));
        });

        // Scroll tree item into view
        setTimeout(() => {
            const item = document.querySelector(`.tree-item[data-index="${obj.global_index}"]`);
            if (item) {
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 50);

        // Save selected key for page reload consistency
        sessionStorage.setItem('explorerSelectedKey', Explorer.getObjectKey(obj));

        state.isTabSwitch = false;
    }

    /**
     * Validate tabs against current allObjects.
     * Called after loadObjects() refresh to remove stale tabs.
     */
    function validateTabs() {
        const before = state.openTabs.length;
        state.openTabs = state.openTabs.filter(tab => {
            // Try to find by key first
            let obj = Explorer.findObjectByKey(tab.key);
            if (obj) {
                // Update index in case it changed
                tab.objectIndex = obj.global_index;
                tab.label = obj.display_name;
                return true;
            }

            // Fallback: try to find by global_index (handles renames)
            obj = state.allObjects.find(o => o.global_index === tab.objectIndex);
            if (obj) {
                // Update key to match new name
                tab.key = Explorer.getObjectKey(obj);
                tab.label = obj.display_name;
                return true;
            }

            return false;
        });

        // If active tab was removed, pick a new one
        if (state.activeTabKey && !state.openTabs.some(t => t.key === state.activeTabKey)) {
            if (state.openTabs.length > 0) {
                state.activeTabKey = state.openTabs[0].key;
            } else {
                state.activeTabKey = null;
            }
        }

        if (state.openTabs.length !== before) {
            renderTabBar();
            persistTabs();
        }
    }

    // =========================================================================
    // Tab Bar Rendering
    // =========================================================================

    /**
     * Render the tab bar into the center pane.
     * Creates/updates the .tab-bar element above the breadcrumb.
     */
    function renderTabBar() {
        let tabBar = document.getElementById('editorTabBar');

        if (state.openTabs.length === 0) {
            if (tabBar) tabBar.style.display = 'none';
            return;
        }

        if (!tabBar) {
            tabBar = document.createElement('div');
            tabBar.id = 'editorTabBar';
            tabBar.className = 'editor-tab-bar';
            const centerPane = document.getElementById('centerPane');
            // Insert as first child of center pane (above empty state and content)
            centerPane.insertBefore(tabBar, centerPane.firstChild);
        }

        tabBar.style.display = '';

        const tabsHtml = state.openTabs.map(tab => {
            const isActive = tab.key === state.activeTabKey;
            const hasPendingEdit = state.pendingEdits.has(tab.objectIndex);
            const icon = Explorer.getObjectTypeIcon(tab.typeIcon);
            const escapedKey = Explorer.escapeHtml(tab.key);
            const escapedLabel = Explorer.escapeHtml(tab.label);

            return `<div class="editor-tab${isActive ? ' active' : ''}${hasPendingEdit ? ' modified' : ''}"
                         data-tab-key="${escapedKey}"
                         title="${escapedLabel}">
                <span class="editor-tab-icon">${icon}</span>
                <span class="editor-tab-label">${escapedLabel}</span>
                ${hasPendingEdit ? '<span class="editor-tab-dot"></span>' : ''}
                <button class="editor-tab-close" title="Close tab">&times;</button>
            </div>`;
        }).join('');

        // Wrap tabs in a scrollable container with optional arrows
        tabBar.innerHTML = `
            <button class="editor-tab-scroll-btn editor-tab-scroll-left" aria-label="Scroll tabs left"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="editor-tab-scroll">${tabsHtml}</div>
            <button class="editor-tab-scroll-btn editor-tab-scroll-right" aria-label="Scroll tabs right"><i class="fa-solid fa-chevron-right"></i></button>
        `;

        // Attach event listeners
        attachTabBarEvents(tabBar);

        // Update scroll button visibility
        updateScrollButtons(tabBar);

        // Auto-scroll active tab into view
        scrollActiveTabIntoView(tabBar);
    }

    /**
     * Attach click/mousedown handlers to the tab bar.
     */
    function attachTabBarEvents(tabBar) {
        const scrollContainer = tabBar.querySelector('.editor-tab-scroll');

        // Tab click and close
        tabBar.addEventListener('mousedown', function(e) {
            // Close button click
            const closeBtn = e.target.closest('.editor-tab-close');
            if (closeBtn) {
                e.preventDefault();
                e.stopPropagation();
                const tab = closeBtn.closest('.editor-tab');
                if (tab) closeTab(tab.dataset.tabKey);
                return;
            }

            // Middle-click to close
            if (e.button === 1) {
                e.preventDefault();
                const tab = e.target.closest('.editor-tab');
                if (tab) closeTab(tab.dataset.tabKey);
                return;
            }

            // Left-click to activate
            if (e.button === 0) {
                const tab = e.target.closest('.editor-tab');
                if (tab) activateTab(tab.dataset.tabKey);
            }
        });

        // Scroll buttons
        const leftBtn = tabBar.querySelector('.editor-tab-scroll-left');
        const rightBtn = tabBar.querySelector('.editor-tab-scroll-right');

        if (leftBtn) {
            leftBtn.addEventListener('click', () => {
                scrollContainer.scrollBy({ left: -150, behavior: 'smooth' });
            });
        }
        if (rightBtn) {
            rightBtn.addEventListener('click', () => {
                scrollContainer.scrollBy({ left: 150, behavior: 'smooth' });
            });
        }

        // Update scroll buttons on scroll
        scrollContainer.addEventListener('scroll', () => updateScrollButtons(tabBar));
    }

    /**
     * Show/hide scroll arrows based on overflow state.
     */
    function updateScrollButtons(tabBar) {
        const scrollContainer = tabBar.querySelector('.editor-tab-scroll');
        const leftBtn = tabBar.querySelector('.editor-tab-scroll-left');
        const rightBtn = tabBar.querySelector('.editor-tab-scroll-right');

        if (!scrollContainer || !leftBtn || !rightBtn) return;

        const hasOverflow = scrollContainer.scrollWidth > scrollContainer.clientWidth;
        const atStart = scrollContainer.scrollLeft <= 0;
        const atEnd = scrollContainer.scrollLeft + scrollContainer.clientWidth >= scrollContainer.scrollWidth - 1;

        leftBtn.classList.toggle('visible', hasOverflow && !atStart);
        rightBtn.classList.toggle('visible', hasOverflow && !atEnd);
    }

    /**
     * Scroll the active tab into view within the tab bar.
     */
    function scrollActiveTabIntoView(tabBar) {
        if (!state.activeTabKey) return;
        const activeEl = tabBar.querySelector('.editor-tab.active');
        if (activeEl) {
            activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        }
    }

    // =========================================================================
    // Export to Explorer namespace
    // =========================================================================

    Explorer.openTab = openTab;
    Explorer.closeTab = closeTab;
    Explorer.activateTab = activateTab;
    Explorer.renderTabBar = renderTabBar;
    Explorer.restoreTabs = restoreTabs;
    Explorer.validateTabs = validateTabs;
    Explorer.persistTabs = persistTabs;
    Explorer.syncTreeSelection = syncTreeSelection;

})(window.Explorer);
```

**Step 2: Add script tag to explorer.html**

In `templates/explorer.html`, add the `tab-manager.js` script tag after `state-management.js` (line 296) and before `ui-utils.js` (line 297). Tab manager needs state but is needed by other modules that will call `openTab()`:

```html
<script src="{{ url_for('static', filename='js/explorer/tab-manager.js') }}"></script>
```

**Step 3: Run tests to verify no regressions**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add static/js/explorer/tab-manager.js templates/explorer.html
git commit -m "feat(tabs): create tab-manager.js module with core tab logic"
```

---

### Task 3: Add tab bar CSS to explorer.css

**Files:**
- Modify: `static/css/explorer.css` (add tab bar styles after `.center-pane` block, around line 1113)

**Step 1: Add tab bar CSS**

Add the following CSS after the `.center-pane` rule (after line 1113) in `static/css/explorer.css`:

```css
/* Editor Tab Bar */
.editor-tab-bar {
    display: flex;
    align-items: stretch;
    background: var(--nbe-dark-bg-secondary);
    border-bottom: 1px solid var(--nbe-dark-border-primary);
    min-height: 35px;
    position: relative;
    flex-shrink: 0;
}

.editor-tab-scroll {
    display: flex;
    overflow-x: auto;
    flex: 1;
    scrollbar-width: none; /* Firefox */
}

.editor-tab-scroll::-webkit-scrollbar {
    display: none; /* Chrome/Safari */
}

.editor-tab {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 12px;
    height: 35px;
    min-width: 0;
    max-width: 200px;
    cursor: pointer;
    border-right: 1px solid var(--nbe-dark-border-secondary);
    color: var(--nbe-white-alpha-50);
    font-size: var(--nbe-typography-secondary-size);
    white-space: nowrap;
    flex-shrink: 0;
    user-select: none;
    position: relative;
}

.editor-tab:hover {
    color: var(--nbe-white-alpha-70);
    background: var(--nbe-white-alpha-05);
}

.editor-tab.active {
    color: var(--nbe-text-inverse);
    background: var(--nbe-dark-bg-primary);
    border-bottom: 2px solid var(--nbe-dark-accent-info);
}

.editor-tab-icon {
    font-size: var(--nbe-typography-muted-size);
    flex-shrink: 0;
    display: flex;
    align-items: center;
}

.editor-tab-icon i {
    font-size: var(--nbe-typography-muted-size);
}

.editor-tab-label {
    overflow: hidden;
    text-overflow: ellipsis;
}

.editor-tab-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--nbe-dark-accent-info);
    flex-shrink: 0;
}

.editor-tab-close {
    background: none;
    border: none;
    color: var(--nbe-white-alpha-30);
    font-size: 16px;
    line-height: 1;
    padding: 0 2px;
    cursor: pointer;
    border-radius: 3px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-left: 4px;
}

.editor-tab-close:hover {
    color: var(--nbe-text-inverse);
    background: var(--nbe-white-alpha-15);
}

.editor-tab-scroll-btn {
    background: var(--nbe-dark-bg-secondary);
    border: none;
    color: var(--nbe-white-alpha-50);
    padding: 0 6px;
    cursor: pointer;
    display: none;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    z-index: 1;
}

.editor-tab-scroll-btn.visible {
    display: flex;
}

.editor-tab-scroll-btn:hover {
    color: var(--nbe-text-inverse);
    background: var(--nbe-white-alpha-10);
}
```

**Step 2: Verify visually**

Start the app and open the explorer page. No tab bar should be visible yet (no tabs open). The existing layout should be unchanged.

Run: `python3 app.py`
Expected: Explorer page loads normally, no visual changes

**Step 3: Commit**

```bash
git add static/css/explorer.css
git commit -m "feat(tabs): add editor tab bar CSS styles"
```

---

### Task 4: Wire navigateToObjectByIndex to open tabs

**Files:**
- Modify: `static/js/explorer/file-operations.js:38-89` (update `navigateToObjectByIndex`)

**Step 1: Update navigateToObjectByIndex to call openTab**

In `static/js/explorer/file-operations.js`, modify the `navigateToObjectByIndex` function. The key change: after finding the object, clearing filters, and expanding folders, call `Explorer.openTab(obj)` instead of the current `selectObjectByIndex`/`updateSelection` pattern:

Replace the function body from `Explorer.clearSelection();` (line 75) through the end of the setTimeout (line 88) with:

```javascript
        // Open as tab (handles selection sync and center pane rendering)
        Explorer.openTab(obj);

        // Scroll to item with slight delay to ensure DOM is updated
        setTimeout(() => {
            const item = document.querySelector(`.tree-item[data-index="${index}"]`);
            if (item) {
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Add highlight pulse effect
                item.classList.add('highlight-pulse');
                setTimeout(() => item.classList.remove('highlight-pulse'), 1500);
            }
        }, 50);
```

This single change captures: Impact/Relationships clicks, suggestion clicks, context menu go-to actions, post-create navigation, cross-page Graph View navigation, and `selectObjectByName()` (which calls `navigateToObjectByIndex`).

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add static/js/explorer/file-operations.js
git commit -m "feat(tabs): wire navigateToObjectByIndex to open tabs"
```

---

### Task 5: Wire tree item click to open tabs

**Files:**
- Modify: `static/js/explorer/app.js:959-985` (update `updateSelection`)

**Step 1: Modify updateSelection to use openTab**

In `static/js/explorer/app.js`, the `updateSelection()` function currently calls `showCenterPaneObject(obj)` directly when a single object is selected (line 974). Modify it to call `Explorer.openTab(obj)` instead — but only when NOT in a tab-switch (to avoid infinite loop):

Replace the block starting at `if (state.selectedKeys.size === 1)` (line 970) through `sessionStorage.removeItem('explorerSelectedKey');` (line 983) with:

```javascript
    if (state.selectedKeys.size === 1) {
        const key = Array.from(state.selectedKeys)[0];
        const obj = Explorer.findObjectByKey(key);
        if (obj) {
            // If this is a tab switch, center pane is already handled
            if (!state.isTabSwitch) {
                Explorer.openTab(obj);
            }
            sessionStorage.setItem('explorerSelectedKey', key);
        }
    } else if (state.selectedKeys.size === 0) {
        // Don't hide if we have open tabs — let tab bar handle it
        if (state.openTabs.length === 0) {
            hideCenterPaneObject();
        }
        sessionStorage.removeItem('explorerSelectedKey');
    } else {
        showCenterPaneMultiple(state.selectedKeys.size);
        sessionStorage.removeItem('explorerSelectedKey');
    }
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add static/js/explorer/app.js
git commit -m "feat(tabs): wire tree item click to open tabs via updateSelection"
```

---

### Task 6: Restore tabs on page load

**Files:**
- Modify: `static/js/explorer/app.js:206-248` (DOMContentLoaded handler)

**Step 1: Add tab restoration to the DOMContentLoaded handler**

In `static/js/explorer/app.js`, after the `await Explorer.loadStagedChanges();` line (line 211) and before `restoreTreeFolderState();` (line 214), add tab restoration:

```javascript
    // Restore tabs from sessionStorage
    Explorer.restoreTabs();
```

Then, modify the selection restoration block. After `buildTree()` (line 216), replace the existing selection restoration logic (lines 218-247) with:

```javascript
    // Restore active tab or fall back to saved selection
    if (state.openTabs.length > 0 && state.activeTabKey) {
        const obj = Explorer.findObjectByKey(state.activeTabKey);
        if (obj) {
            Explorer.openTab(obj);
            selectionRestored = true;
            // Scroll to item after DOM is ready
            setTimeout(() => {
                const item = document.querySelector(`.tree-item[data-index="${obj.global_index}"]`);
                if (item) {
                    const folder = item.closest('.tree-folder');
                    if (folder && !folder.classList.contains('open')) {
                        folder.classList.add('open');
                    }
                    item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }, 100);
        }
    } else {
        // Fall back to single saved key (no tabs)
        const savedKey = sessionStorage.getItem('explorerSelectedKey');
        if (savedKey) {
            const obj = Explorer.findObjectByKey(savedKey);
            if (obj) {
                Explorer.openTab(obj);
                selectionRestored = true;
                setTimeout(() => {
                    const item = document.querySelector(`.tree-item[data-index="${obj.global_index}"]`);
                    if (item) {
                        const folder = item.closest('.tree-folder');
                        if (folder && !folder.classList.contains('open')) {
                            folder.classList.add('open');
                        }
                        item.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 100);
            }
        }
    }

    // Render tab bar (may be empty if no tabs restored)
    Explorer.renderTabBar();
```

Keep the existing `selectionRestored` variable declaration before this block, and keep the `if (!selectionRestored)` empty state block after it.

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add static/js/explorer/app.js
git commit -m "feat(tabs): restore tabs on page load from sessionStorage"
```

---

### Task 7: Add tab validation after data reload

**Files:**
- Modify: `static/js/explorer/data-loading.js` (add validateTabs call after loadObjects)

**Step 1: Find the loadObjects function and add validation**

In `static/js/explorer/data-loading.js`, find the `loadObjects()` function. At the end of it, after `state.allObjects` is populated, add:

```javascript
        // Validate open tabs against refreshed objects
        if (Explorer.validateTabs) Explorer.validateTabs();
```

Also find the `checkStagingChanges` or equivalent polling function that reloads objects. After any `await Explorer.loadObjects()` call in that function, add the same validation call.

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add static/js/explorer/data-loading.js
git commit -m "feat(tabs): validate tabs after data reload"
```

---

### Task 8: Update tab label when object is renamed

**Files:**
- Modify: `static/js/explorer/object-editor.js:866-899` (updateAttribute function)

**Step 1: Update the tab label when name field changes**

In `static/js/explorer/object-editor.js`, in the `updateAttribute` function, after the block that updates `state.editedObject.display_name` (around line 876), add tab label sync:

```javascript
                // Update tab label if this object has an open tab
                if (state.activeTabKey) {
                    const activeTab = state.openTabs.find(t => t.key === state.activeTabKey);
                    if (activeTab) {
                        activeTab.label = value || '(unnamed)';
                        Explorer.renderTabBar();
                    }
                }
```

This goes inside the `if (key === nameField)` block, after the `else` branch that handles existing objects (around line 884), before the closing brace of the `if (key === nameField)` block.

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add static/js/explorer/object-editor.js
git commit -m "feat(tabs): update tab label when object is renamed"
```

---

### Task 9: Refresh tab bar modified indicators after staging changes

**Files:**
- Modify: `static/js/explorer/state-management.js:301-321` (refreshAfterObjectChange)

**Step 1: Add tab bar refresh to refreshAfterObjectChange**

In `static/js/explorer/state-management.js`, inside the `refreshAfterObjectChange` function, add a tab bar re-render after the existing refreshes (before the closing brace):

```javascript
        // Refresh tab bar to update modified indicators
        if (Explorer.renderTabBar) {
            Explorer.renderTabBar();
        }
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add static/js/explorer/state-management.js
git commit -m "feat(tabs): refresh tab bar modified dots on staging changes"
```

---

### Task 10: Manual integration testing

**Files:** None (testing only)

**Step 1: Start the app and test basic tab behavior**

Run: `python3 app.py`

Test these scenarios in the browser:

1. **Tree click opens tab**: Click an object in the left tree. Verify a tab appears above the breadcrumb.
2. **Multiple tabs**: Click different objects. Verify tabs accumulate. Verify switching tabs switches the center pane content.
3. **No duplicates**: Click an already-open object. Verify it switches to the existing tab, doesn't create a duplicate.
4. **Close tab**: Click the x on a tab. Verify it closes and an adjacent tab activates.
5. **Close last tab**: Close all tabs. Verify the empty state placeholder appears.
6. **Impact/Relationships navigation**: Expand the Impact section, click a referenced object. Verify it opens in a new tab.
7. **Suggestion click**: Go to the Suggestions tab, click an item. Verify it opens the object in a tab.
8. **Persistence**: Open 3 tabs. Navigate to Audit Log via navbar. Come back to Explorer. Verify tabs are restored.
9. **Auto-staging**: Edit an attribute in object A. Switch to a different tab. Verify A's changes are staged (dot indicator appears).
10. **Bulk select**: Ctrl+click multiple objects. Verify tabs are NOT opened for each (only single-click opens tabs).
11. **Overflow**: Open 15+ tabs. Verify scroll arrows appear and active tab scrolls into view.
12. **Middle-click**: Middle-click a tab. Verify it closes.

**Step 2: Commit if all tests pass**

```bash
git add -A
git commit -m "feat(tabs): editor tabs feature complete"
```
