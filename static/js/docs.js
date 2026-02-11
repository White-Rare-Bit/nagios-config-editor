/* Docs page — Nagios object reference browser */
(function() {
    'use strict';

    var REF = window.NAGIOS_OBJECT_REFERENCE;

    var CATEGORIES = [
        { name: 'Monitoring Objects', types: ['host', 'service'] },
        { name: 'Groups', types: ['hostgroup', 'servicegroup', 'contactgroup'] },
        { name: 'Contacts', types: ['contact'] },
        { name: 'Commands & Time', types: ['command', 'timeperiod'] },
        { name: 'Dependencies', types: ['hostdependency', 'servicedependency'] },
        { name: 'Escalations', types: ['hostescalation', 'serviceescalation'] },
        { name: 'Extended Info (Deprecated)', types: ['hostextinfo', 'serviceextinfo'] }
    ];

    // SVG icons (subset from explorer/ui-utils.js)
    var ICONS = {
        chevron: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>',
        folder: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>',
        folderOpen: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v1"></path><path d="M2 10h20"></path></svg>',
        file: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>'
    };

    var selectedType = null;
    var expandedCategories = {};
    var focusedIndex = -1;
    var allTypeNodes = []; // flat list for keyboard nav

    // =========================================================================
    // Tree rendering
    // =========================================================================

    function renderTree() {
        var container = document.getElementById('docsTree');
        var html = '';
        for (var i = 0; i < CATEGORIES.length; i++) {
            html += renderCategory(CATEGORIES[i], i);
        }
        container.innerHTML = html;
        buildTypeNodeList();
    }

    function renderCategory(cat, catIndex) {
        var isExpanded = expandedCategories[catIndex] !== false; // default expanded
        var totalDirectives = 0;
        for (var i = 0; i < cat.types.length; i++) {
            totalDirectives += REF[cat.types[i]].directives.length;
        }

        var html = '<div class="workspace-tree-row' + (isExpanded ? ' expanded' : '') + '" data-depth="0" data-cat="' + catIndex + '" onclick="DocsPage.toggleCategory(' + catIndex + ')">';
        html += '<button class="tree-expand-btn' + (isExpanded ? ' expanded' : '') + '">' + ICONS.chevron + '</button>';
        html += '<span class="tree-icon tree-icon--folder' + (isExpanded ? ' expanded' : '') + '">' + (isExpanded ? ICONS.folderOpen : ICONS.folder) + '</span>';
        html += '<span class="tree-label tree-label--folder">' + escapeHtml(cat.name) + '</span>';
        html += '<span class="tree-count">' + totalDirectives + '</span>';
        html += '</div>';

        html += '<div class="tree-children' + (isExpanded ? ' expanded' : '') + '">';
        for (var i = 0; i < cat.types.length; i++) {
            html += renderTypeRow(cat.types[i]);
        }
        html += '</div>';
        return html;
    }

    function renderTypeRow(typeName) {
        var typeData = REF[typeName];
        var isSelected = selectedType === typeName;
        var directiveCount = typeData.directives.length;
        var label = typeData.label || typeName;

        var html = '<div class="workspace-tree-row' + (isSelected ? ' selected' : '') + '" data-depth="1" data-type="' + typeName + '" onclick="DocsPage.selectType(\'' + typeName + '\')">';
        html += '<span class="tree-expand-placeholder"></span>';
        html += '<span class="tree-icon tree-icon--file">' + ICONS.file + '</span>';
        html += '<span class="tree-label">' + escapeHtml(label) + '</span>';
        html += '<span class="tree-count">' + directiveCount + '</span>';
        html += '</div>';
        return html;
    }

    function buildTypeNodeList() {
        allTypeNodes = [];
        var rows = document.querySelectorAll('.docs-tree-container .workspace-tree-row[data-type]');
        for (var i = 0; i < rows.length; i++) {
            allTypeNodes.push(rows[i]);
        }
    }

    // =========================================================================
    // Tree interactions
    // =========================================================================

    function toggleCategory(catIndex) {
        expandedCategories[catIndex] = expandedCategories[catIndex] === false;
        renderTree();
        updateHash();
    }

    function selectType(typeName) {
        selectedType = typeName;
        // Ensure parent category is expanded
        for (var i = 0; i < CATEGORIES.length; i++) {
            if (CATEGORIES[i].types.indexOf(typeName) !== -1) {
                expandedCategories[i] = true;
                break;
            }
        }
        renderTree();
        renderContent(typeName);
        updateHash();
    }

    // =========================================================================
    // Content rendering
    // =========================================================================

    function renderContent(typeName) {
        var typeData = REF[typeName];
        var container = document.getElementById('docsContent');
        var label = typeData.label || typeName;
        var requiredCount = typeData.directives.filter(function(d) { return d.required; }).length;
        var templateDirs = REF._template_directives ? REF._template_directives.directives : [];

        var html = '<div class="docs-type-header">';
        html += '<h2 class="docs-type-title">' + escapeHtml(label) + ' Definition</h2>';
        if (typeData.deprecated) {
            html += '<div class="docs-deprecated-notice"><i class="fa-solid fa-triangle-exclamation"></i> Deprecated in Nagios 4. Use the corresponding host/service directives instead.</div>';
        }
        html += '<p class="docs-type-desc">' + escapeHtml(typeData.description) + '</p>';
        html += '<div class="docs-type-meta">';
        html += '<span class="docs-directive-count">' + typeData.directives.length + ' directives</span>';
        if (requiredCount > 0) {
            html += '<span class="docs-required-count">' + requiredCount + ' required</span>';
        }
        html += '</div>';
        html += '</div>';

        html += '<div class="docs-search-bar">';
        html += '<input type="text" class="form-input" id="docsDirectiveSearch" placeholder="Filter directives..." autocomplete="off">';
        html += '</div>';

        html += '<div class="docs-table-container">';
        html += '<table class="docs-directive-table">';
        html += '<thead><tr>';
        html += '<th class="docs-col-name">Directive</th>';
        html += '<th class="docs-col-req">Required</th>';
        html += '<th class="docs-col-format">Format</th>';
        html += '<th class="docs-col-desc">Description</th>';
        html += '</tr></thead>';
        html += '<tbody id="docsDirectiveBody">';

        // Type-specific directives
        for (var i = 0; i < typeData.directives.length; i++) {
            html += renderDirectiveRow(typeData.directives[i]);
        }

        // Template directives (common to all types)
        if (templateDirs.length > 0) {
            html += '<tr class="docs-section-divider"><td colspan="4">Template Directives (common to all types)</td></tr>';
            for (var j = 0; j < templateDirs.length; j++) {
                html += renderDirectiveRow(templateDirs[j]);
            }
        }

        html += '</tbody></table>';
        html += '</div>';

        container.innerHTML = html;

        // Attach search listener
        var searchInput = document.getElementById('docsDirectiveSearch');
        if (searchInput) {
            searchInput.addEventListener('input', function() {
                filterDirectives(this.value);
            });
        }
    }

    function renderDirectiveRow(directive) {
        var reqBadge = directive.required
            ? '<span class="docs-badge docs-badge--required">Required</span>'
            : '<span class="docs-badge docs-badge--optional">Optional</span>';

        var html = '<tr class="docs-directive-row">';
        html += '<td class="docs-cell-name"><code>' + escapeHtml(directive.name) + '</code></td>';
        html += '<td class="docs-cell-req">' + reqBadge + '</td>';
        html += '<td class="docs-cell-format"><code>' + escapeHtml(directive.format) + '</code></td>';
        html += '<td class="docs-cell-desc">' + escapeHtml(directive.description) + '</td>';
        html += '</tr>';
        return html;
    }

    function filterDirectives(query) {
        var rows = document.querySelectorAll('#docsDirectiveBody .docs-directive-row');
        var lower = query.toLowerCase();
        for (var i = 0; i < rows.length; i++) {
            var text = rows[i].textContent.toLowerCase();
            rows[i].style.display = (!lower || text.indexOf(lower) !== -1) ? '' : 'none';
        }
        // Also handle section divider visibility
        var dividers = document.querySelectorAll('#docsDirectiveBody .docs-section-divider');
        for (var j = 0; j < dividers.length; j++) {
            dividers[j].style.display = lower ? 'none' : '';
        }
    }

    // =========================================================================
    // URL hash navigation
    // =========================================================================

    function updateHash() {
        if (selectedType) {
            history.replaceState(null, '', '#' + selectedType);
        }
    }

    function loadFromHash() {
        var hash = window.location.hash.replace('#', '');
        if (hash && REF[hash] && hash !== '_template_directives') {
            selectType(hash);
        }
    }

    // =========================================================================
    // Keyboard navigation
    // =========================================================================

    function handleKeydown(e) {
        // Don't intercept when typing in search
        if (e.target.id === 'docsDirectiveSearch') {
            if (e.key === 'Escape') {
                e.target.value = '';
                filterDirectives('');
                e.target.blur();
                e.preventDefault();
            }
            return;
        }

        // Don't interfere with other overlays
        if (document.querySelector('.keyboard-shortcuts-overlay.visible') ||
            document.querySelector('.confirm-dialog-overlay.visible')) {
            return;
        }

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                navigateTypes(1);
                break;
            case 'ArrowUp':
                e.preventDefault();
                navigateTypes(-1);
                break;
            case 'Enter':
                e.preventDefault();
                if (focusedIndex >= 0 && focusedIndex < allTypeNodes.length) {
                    var typeName = allTypeNodes[focusedIndex].getAttribute('data-type');
                    if (typeName) selectType(typeName);
                }
                break;
            case '/':
                if (!e.ctrlKey && !e.metaKey) {
                    e.preventDefault();
                    var search = document.getElementById('docsDirectiveSearch');
                    if (search) search.focus();
                }
                break;
        }
    }

    function navigateTypes(direction) {
        if (allTypeNodes.length === 0) return;

        // Find current index based on selected type
        if (focusedIndex < 0 && selectedType) {
            for (var i = 0; i < allTypeNodes.length; i++) {
                if (allTypeNodes[i].getAttribute('data-type') === selectedType) {
                    focusedIndex = i;
                    break;
                }
            }
        }

        focusedIndex += direction;
        if (focusedIndex < 0) focusedIndex = 0;
        if (focusedIndex >= allTypeNodes.length) focusedIndex = allTypeNodes.length - 1;

        var typeName = allTypeNodes[focusedIndex].getAttribute('data-type');
        if (typeName) selectType(typeName);
    }

    // =========================================================================
    // Utilities
    // =========================================================================

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // =========================================================================
    // Public API
    // =========================================================================

    window.DocsPage = {
        toggleCategory: toggleCategory,
        selectType: selectType
    };

    // =========================================================================
    // Init
    // =========================================================================

    document.addEventListener('DOMContentLoaded', function() {
        // Default: expand all categories
        for (var i = 0; i < CATEGORIES.length; i++) {
            expandedCategories[i] = true;
        }
        renderTree();
        loadFromHash();
        document.addEventListener('keydown', handleKeydown);
    });

})();
