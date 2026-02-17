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

    function restoreTabs() {
        try {
            const saved = sessionStorage.getItem('explorerTabs');
            if (!saved) {return;}
            const { openTabs, activeTabKey } = JSON.parse(saved);
            if (!Array.isArray(openTabs)) {return;}

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

    function openTab(obj) {
        if (!obj) {return;}

        const key = Explorer.getObjectKey(obj);

        // Auto-stage current edits before switching
        if (state.activeTabKey && state.activeTabKey !== key && state.editedObject) {
            Explorer.checkForChanges();
        }

        const existingIdx = state.openTabs.findIndex(t => t.key === key);
        if (existingIdx >= 0) {
            state.openTabs[existingIdx].label = obj.display_name;
            state.openTabs[existingIdx].objectIndex = obj.global_index;
            state.activeTabKey = key;
        } else {
            state.openTabs.push({
                key: key,
                objectIndex: obj.global_index,
                label: obj.display_name,
                typeIcon: obj.object_type
            });
            state.activeTabKey = key;
        }

        Explorer.showCenterPaneObject(obj);
        syncTreeSelection(obj);
        renderTabBar();
        persistTabs();
    }

    function closeTab(key) {
        const idx = state.openTabs.findIndex(t => t.key === key);
        if (idx < 0) {return;}

        if (state.activeTabKey === key && state.editedObject) {
            Explorer.checkForChanges();
        }

        state.openTabs.splice(idx, 1);

        if (state.activeTabKey === key) {
            if (state.openTabs.length === 0) {
                state.activeTabKey = null;
                Explorer.hideCenterPaneObject();
                Explorer.clearSelection();
                Explorer.updateSelection();
            } else {
                const newIdx = Math.min(idx, state.openTabs.length - 1);
                const newTab = state.openTabs[newIdx];
                state.activeTabKey = newTab.key;

                const obj = Explorer.findObjectByKey(newTab.key);
                if (obj) {
                    Explorer.showCenterPaneObject(obj);
                    syncTreeSelection(obj);
                }
            }
        }

        renderTabBar();
        persistTabs();
    }

    function activateTab(key) {
        if (state.activeTabKey === key) {return;}

        if (state.editedObject) {
            Explorer.checkForChanges();
        }

        state.activeTabKey = key;
        const tab = state.openTabs.find(t => t.key === key);
        if (!tab) {return;}

        const obj = Explorer.findObjectByKey(key);
        if (obj) {
            Explorer.showCenterPaneObject(obj);
            syncTreeSelection(obj);
        }

        renderTabBar();
        persistTabs();
    }

    function syncTreeSelection(obj) {
        state.isTabSwitch = true;
        Explorer.clearSelection();
        state.selectedKeys.add(Explorer.getObjectKey(obj));

        document.querySelectorAll('.tree-item').forEach(el => {
            const index = parseInt(el.dataset.index, 10);
            el.classList.toggle('selected', Explorer.isSelectedByIndex(index));
        });

        setTimeout(() => {
            const item = document.querySelector(`.tree-item[data-index="${obj.global_index}"]`);
            if (item) {
                // Ensure parent folder is open
                const folder = item.closest('.tree-folder');
                if (folder && !folder.classList.contains('open')) {
                    folder.classList.add('open');
                }
                item.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 50);

        sessionStorage.setItem('explorerSelectedKey', Explorer.getObjectKey(obj));
        state.isTabSwitch = false;
    }

    function validateTabs() {
        const before = state.openTabs.length;
        state.openTabs = state.openTabs.filter(tab => {
            let obj = Explorer.findObjectByKey(tab.key);
            if (obj) {
                tab.objectIndex = obj.global_index;
                tab.label = obj.display_name;
                return true;
            }

            obj = state.allObjects.find(o => o.global_index === tab.objectIndex);
            if (obj) {
                tab.key = Explorer.getObjectKey(obj);
                tab.label = obj.display_name;
                return true;
            }

            return false;
        });

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

    var tabBarEventsAttached = false;

    function renderTabBar() {
        let tabBar = document.getElementById('editorTabBar');

        if (state.openTabs.length === 0) {
            if (tabBar) {tabBar.style.display = 'none';}
            return;
        }

        if (!tabBar) {
            tabBar = document.createElement('div');
            tabBar.id = 'editorTabBar';
            tabBar.className = 'editor-tab-bar';
            const centerPane = document.getElementById('centerPane');
            centerPane.insertBefore(tabBar, centerPane.firstChild);
            tabBarEventsAttached = false;
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

        tabBar.innerHTML = `
            <button class="editor-tab-scroll-btn editor-tab-scroll-left" aria-label="Scroll tabs left"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="editor-tab-scroll">${tabsHtml}</div>
            <button class="editor-tab-scroll-btn editor-tab-scroll-right" aria-label="Scroll tabs right"><i class="fa-solid fa-chevron-right"></i></button>
        `;

        if (!tabBarEventsAttached) {
            attachTabBarEvents(tabBar);
            tabBarEventsAttached = true;
        }
        updateScrollButtons(tabBar);
        scrollActiveTabIntoView(tabBar);
    }

    function attachTabBarEvents(tabBar) {
        // Use event delegation on the tab bar — only attached once
        tabBar.addEventListener('mousedown', function(e) {
            const closeBtn = e.target.closest('.editor-tab-close');
            if (closeBtn) {
                e.preventDefault();
                e.stopPropagation();
                const tab = closeBtn.closest('.editor-tab');
                if (tab) {closeTab(tab.dataset.tabKey);}
                return;
            }

            if (e.button === 1) {
                e.preventDefault();
                const tab = e.target.closest('.editor-tab');
                if (tab) {closeTab(tab.dataset.tabKey);}
                return;
            }

            if (e.button === 0) {
                const tab = e.target.closest('.editor-tab');
                if (tab) {activateTab(tab.dataset.tabKey);}
            }
        });

        // Scroll button clicks use event delegation too
        tabBar.addEventListener('click', function(e) {
            const scrollContainer = tabBar.querySelector('.editor-tab-scroll');
            if (!scrollContainer) {return;}
            if (e.target.closest('.editor-tab-scroll-left')) {
                scrollContainer.scrollBy({ left: -150, behavior: 'smooth' });
            } else if (e.target.closest('.editor-tab-scroll-right')) {
                scrollContainer.scrollBy({ left: 150, behavior: 'smooth' });
            }
        });

        // Scroll event for updating button visibility — delegation via capture on tabBar
        tabBar.addEventListener('scroll', function() {
            updateScrollButtons(tabBar);
        }, true);
    }

    function updateScrollButtons(tabBar) {
        const scrollContainer = tabBar.querySelector('.editor-tab-scroll');
        const leftBtn = tabBar.querySelector('.editor-tab-scroll-left');
        const rightBtn = tabBar.querySelector('.editor-tab-scroll-right');

        if (!scrollContainer || !leftBtn || !rightBtn) {return;}

        const hasOverflow = scrollContainer.scrollWidth > scrollContainer.clientWidth;
        const atStart = scrollContainer.scrollLeft <= 0;
        const atEnd = scrollContainer.scrollLeft + scrollContainer.clientWidth >= scrollContainer.scrollWidth - 1;

        leftBtn.classList.toggle('visible', hasOverflow && !atStart);
        rightBtn.classList.toggle('visible', hasOverflow && !atEnd);
    }

    function scrollActiveTabIntoView(tabBar) {
        if (!state.activeTabKey) {return;}
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
