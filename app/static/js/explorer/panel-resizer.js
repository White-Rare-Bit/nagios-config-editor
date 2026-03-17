/**
 * Nagios Bulk Editor - Panel Resizer Module
 *
 * Handles resizable and collapsible left/right panels with progressive
 * badge label tiers driven by panel width breakpoints.
 */

import { constants } from './constants.js';

const STORAGE_KEY = 'nbe-panel-layout';
const DEFAULT_LEFT_WIDTH = 320;
const DEFAULT_RIGHT_WIDTH = 440;
const MIN_WIDTH = 200;
const TIER_COMPACT = 280;
const TIER_MEDIUM = 400;

let leftPanel, rightPanel, centerPane;
let leftHandle, rightHandle;
let leftPill, rightPill;
let currentDrag = null; // { side: 'left'|'right', startX, startWidth }

// Current layout state
const layout = {
    leftWidth: DEFAULT_LEFT_WIDTH,
    rightWidth: DEFAULT_RIGHT_WIDTH,
    leftCollapsed: false,
    rightCollapsed: false
};

/**
 * Get max panel width (50% of viewport)
 */
function getMaxWidth() {
    return Math.floor(window.innerWidth * 0.5);
}

/**
 * Determine tier from width
 */
function getTier(width) {
    if (width < TIER_COMPACT) return 'compact';
    if (width < TIER_MEDIUM) return 'medium';
    return 'full';
}

/**
 * Save layout to localStorage
 */
function saveLayout() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
    } catch (e) {
        // localStorage may be full or disabled
    }
}

/**
 * Load layout from localStorage
 */
function loadLayout() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            if (typeof parsed.leftWidth === 'number') layout.leftWidth = parsed.leftWidth;
            if (typeof parsed.rightWidth === 'number') layout.rightWidth = parsed.rightWidth;
            if (typeof parsed.leftCollapsed === 'boolean') layout.leftCollapsed = parsed.leftCollapsed;
            if (typeof parsed.rightCollapsed === 'boolean') layout.rightCollapsed = parsed.rightCollapsed;
        }
    } catch (e) {
        // Use defaults
    }
}

/**
 * Clamp width within bounds
 */
function clampWidth(width) {
    return Math.max(MIN_WIDTH, Math.min(width, getMaxWidth()));
}

/**
 * Apply width to a panel and update tier
 */
function applyWidth(side) {
    const panel = side === 'left' ? leftPanel : rightPanel;
    const width = side === 'left' ? layout.leftWidth : layout.rightWidth;
    const collapsed = side === 'left' ? layout.leftCollapsed : layout.rightCollapsed;

    if (collapsed) {
        panel.classList.add('is-collapsed');
        panel.style.width = '0px';
    } else {
        panel.classList.remove('is-collapsed');
        panel.style.width = width + 'px';
    }

    updateTier(side);
    updatePill(side);
}

/**
 * Update badge tier for a panel based on its width
 */
function updateTier(side) {
    const panel = side === 'left' ? leftPanel : rightPanel;
    const width = side === 'left' ? layout.leftWidth : layout.rightWidth;
    const collapsed = side === 'left' ? layout.leftCollapsed : layout.rightCollapsed;
    const tier = collapsed ? 'compact' : getTier(width);

    // Update tier class on panel
    panel.classList.remove('panel-tier-compact', 'panel-tier-medium', 'panel-tier-full');
    panel.classList.add('panel-tier-' + tier);

    // Update badge text content for left panel
    if (side === 'left') {
        updateBadgesInPanel(panel, tier);
    }

    // Update right panel tab labels
    if (side === 'right') {
        updateTabLabels(tier);
        updateBadgesInPanel(panel, tier);
    }
}

/**
 * Update all badge text in a panel to match the given tier
 */
function updateBadgesInPanel(panel, tier) {
    const attr = 'data-badge-' + tier;
    const badges = panel.querySelectorAll('.tree-item-type[' + attr + '], .tree-object-type[' + attr + ']');
    for (let i = 0; i < badges.length; i++) {
        const newText = badges[i].getAttribute(attr);
        if (newText && badges[i].textContent !== newText) {
            badges[i].textContent = newText;
        }
    }
}

/**
 * Update right panel tab labels based on tier
 */
function updateTabLabels(tier) {
    const c = constants;
    if (!c || !c.tabLabelTiers) return;

    const tabs = rightPanel.querySelectorAll('[data-tab]');
    tabs.forEach(function(tab) {
        const tabName = tab.dataset.tab;
        const tiers = c.tabLabelTiers[tabName];
        if (!tiers) return;

        const label = tiers[tier] || tiers.full;
        // Find the text node (after the icon)
        const icon = tab.querySelector('i');
        const badge = tab.querySelector('.nbe-tab-badge');
        // Rebuild text content preserving icon and badge
        if (icon) {
            // Clear text nodes between icon and badge
            let node = icon.nextSibling;
            while (node && node !== badge) {
                const next = node.nextSibling;
                if (node.nodeType === Node.TEXT_NODE) {
                    node.remove();
                }
                node = next;
            }
            // Insert new text after icon
            const textNode = document.createTextNode(' ' + label + ' ');
            icon.after(textNode);
        }
    });
}

/**
 * Update pill toggle appearance
 */
function updatePill(side) {
    const pill = side === 'left' ? leftPill : rightPill;
    const handle = side === 'left' ? leftHandle : rightHandle;
    const collapsed = side === 'left' ? layout.leftCollapsed : layout.rightCollapsed;
    const icon = pill.querySelector('i');

    if (collapsed) {
        handle.classList.add('panel-collapsed');
        pill.setAttribute('aria-label', 'Expand ' + side + ' panel');
        pill.setAttribute('title', 'Expand panel');
        if (side === 'left') {
            icon.className = 'fa-solid fa-chevron-right';
        } else {
            icon.className = 'fa-solid fa-chevron-left';
        }
    } else {
        handle.classList.remove('panel-collapsed');
        pill.setAttribute('aria-label', 'Collapse ' + side + ' panel');
        pill.setAttribute('title', 'Collapse panel');
        if (side === 'left') {
            icon.className = 'fa-solid fa-chevron-left';
        } else {
            icon.className = 'fa-solid fa-chevron-right';
        }
    }
}

/**
 * Toggle panel collapse
 */
function toggleCollapse(side) {
    const panel = side === 'left' ? leftPanel : rightPanel;

    if (side === 'left') {
        layout.leftCollapsed = !layout.leftCollapsed;
    } else {
        layout.rightCollapsed = !layout.rightCollapsed;
    }

    // Add transition class
    panel.classList.add('is-collapsing');
    applyWidth(side);
    saveLayout();

    // Remove transition class after animation
    setTimeout(function() {
        panel.classList.remove('is-collapsing');
    }, 250);
}

/**
 * Start drag resize
 */
function startDrag(e, side) {
    // Don't start drag if clicking the pill
    if (e.target.closest('.panel-collapse-pill')) return;

    e.preventDefault();
    const panel = side === 'left' ? leftPanel : rightPanel;
    const width = side === 'left' ? layout.leftWidth : layout.rightWidth;

    // If collapsed, expand first
    if ((side === 'left' && layout.leftCollapsed) ||
        (side === 'right' && layout.rightCollapsed)) {
        toggleCollapse(side);
        return;
    }

    currentDrag = { side: side, startX: e.clientX, startWidth: width };

    // Disable transitions during drag
    panel.classList.add('is-dragging');

    // Add overlay to prevent selection
    const overlay = document.createElement('div');
    overlay.className = 'panel-resize-overlay';
    overlay.id = 'panelResizeOverlay';
    document.body.appendChild(overlay);

    // Add dragging indicator to handle
    const handle = side === 'left' ? leftHandle : rightHandle;
    handle.classList.add('is-dragging');

    document.addEventListener('mousemove', onDrag);
    document.addEventListener('mouseup', endDrag);
}

/**
 * Handle drag movement
 */
function onDrag(e) {
    if (!currentDrag) return;

    const { side, startX, startWidth } = currentDrag;
    const delta = e.clientX - startX;
    let newWidth;

    if (side === 'left') {
        newWidth = clampWidth(startWidth + delta);
        layout.leftWidth = newWidth;
        leftPanel.style.width = newWidth + 'px';
        updateTier('left');
    } else {
        // Right panel: dragging left increases width
        newWidth = clampWidth(startWidth - delta);
        layout.rightWidth = newWidth;
        rightPanel.style.width = newWidth + 'px';
        updateTier('right');
    }
}

/**
 * End drag resize
 */
function endDrag() {
    if (!currentDrag) return;

    const side = currentDrag.side;
    const panel = side === 'left' ? leftPanel : rightPanel;
    const handle = side === 'left' ? leftHandle : rightHandle;

    panel.classList.remove('is-dragging');
    handle.classList.remove('is-dragging');

    // Remove overlay
    const overlay = document.getElementById('panelResizeOverlay');
    if (overlay) overlay.remove();

    document.removeEventListener('mousemove', onDrag);
    document.removeEventListener('mouseup', endDrag);

    saveLayout();
    currentDrag = null;
}

/**
 * Handle window resize — clamp panels if they exceed max
 */
function onWindowResize() {
    const max = getMaxWidth();
    if (layout.leftWidth > max) {
        layout.leftWidth = max;
        applyWidth('left');
    }
    if (layout.rightWidth > max) {
        layout.rightWidth = max;
        applyWidth('right');
    }
}

/**
 * Handle double-click on resize handle — reset to default width
 */
function onHandleDoubleClick(e, side) {
    if (e.target.closest('.panel-collapse-pill')) return;
    e.preventDefault();

    if (side === 'left') {
        layout.leftWidth = DEFAULT_LEFT_WIDTH;
    } else {
        layout.rightWidth = DEFAULT_RIGHT_WIDTH;
    }

    applyWidth(side);
    saveLayout();
}

/**
 * Re-apply tiers after tree re-render (called by app.js after renderTree)
 */
export function refreshPanelTiers() {
    if (leftPanel) {
        const leftTier = layout.leftCollapsed ? 'compact' : getTier(layout.leftWidth);
        updateBadgesInPanel(leftPanel, leftTier);
    }
    if (rightPanel) {
        const rightTier = layout.rightCollapsed ? 'compact' : getTier(layout.rightWidth);
        updateBadgesInPanel(rightPanel, rightTier);
    }
}

/**
 * Initialize the panel resizer
 */
export function initPanelResizer() {
    leftPanel = document.querySelector('.tree-panel');
    rightPanel = document.getElementById('rightPane');
    centerPane = document.getElementById('centerPane');
    leftHandle = document.getElementById('leftResizeHandle');
    rightHandle = document.getElementById('rightResizeHandle');
    leftPill = document.getElementById('leftCollapsePill');
    rightPill = document.getElementById('rightCollapsePill');

    if (!leftPanel || !rightPanel || !leftHandle || !rightHandle) {
        return; // Elements not found, bail out
    }

    // Load saved layout
    loadLayout();

    // Apply initial widths (no transition on first load)
    leftPanel.style.transition = 'none';
    rightPanel.style.transition = 'none';
    applyWidth('left');
    applyWidth('right');

    // Re-enable transitions after initial paint
    requestAnimationFrame(function() {
        requestAnimationFrame(function() {
            leftPanel.style.transition = '';
            rightPanel.style.transition = '';
        });
    });

    // Drag events
    leftHandle.addEventListener('mousedown', function(e) { startDrag(e, 'left'); });
    rightHandle.addEventListener('mousedown', function(e) { startDrag(e, 'right'); });

    // Double-click to reset
    leftHandle.addEventListener('dblclick', function(e) { onHandleDoubleClick(e, 'left'); });
    rightHandle.addEventListener('dblclick', function(e) { onHandleDoubleClick(e, 'right'); });

    // Pill click handlers
    leftPill.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleCollapse('left');
    });
    rightPill.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleCollapse('right');
    });

    // Window resize handler
    window.addEventListener('resize', onWindowResize);

    // Set up ResizeObserver for continuous tier updates
    if (typeof ResizeObserver !== 'undefined') {
        const observer = new ResizeObserver(function(entries) {
            for (const entry of entries) {
                if (entry.target === leftPanel) {
                    updateTier('left');
                } else if (entry.target === rightPanel) {
                    updateTier('right');
                }
            }
        });
        observer.observe(leftPanel);
        observer.observe(rightPanel);
    }
}
