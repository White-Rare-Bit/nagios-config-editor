/* Docs page — App documentation + Nagios object reference browser */
(function() {
    'use strict';

    var REF = window.NAGIOS_OBJECT_REFERENCE;
    var INHERITANCE = window.NAGIOS_INHERITANCE_REFERENCE;

    // =========================================================================
    // App Docs tree structure (labels + slugs only — content from server)
    // =========================================================================

    var APP_DOCS_TREE = [
        { section: 'Getting Started', items: [
            { slug: 'overview', label: 'Overview' },
            { slug: 'installation', label: 'Installation & Setup' },
            { slug: 'quick-start', label: 'Quick Start Guide' }
        ]},
        { section: 'User Guide', items: [
            { slug: 'explorer-navigation', label: 'Explorer & Navigation' },
            { slug: 'editing-objects', label: 'Editing Objects' },
            { slug: 'bulk-operations', label: 'Bulk Operations' },
            { slug: 'staging-system', label: 'Staging System' },
            { slug: 'file-folder-management', label: 'File & Folder Management' },
            { slug: 'git-integration', label: 'Git Integration' },
            { slug: 'validation', label: 'Validation' },
            { slug: 'backups', label: 'Backups' },
            { slug: 'search-filtering', label: 'Search & Filtering' },
            { slug: 'inheritance-viewer', label: 'Inheritance Viewer' },
            { slug: 'dependency-graph', label: 'Dependency Graph' },
            { slug: 'analysis-tools', label: 'Analysis Tools' },
            { slug: 'audit-log', label: 'Audit Log' },
            { slug: 'settings', label: 'Settings' },
            { slug: 'keyboard-shortcuts', label: 'Keyboard Shortcuts' }
        ]},
        { section: 'Developer Guide', items: [
            { slug: 'architecture', label: 'Architecture Overview' },
            { slug: 'backend-services', label: 'Backend Services' },
            { slug: 'api-reference', label: 'API Reference' },
            { slug: 'frontend-architecture', label: 'Frontend Architecture' },
            { slug: 'data-flow-staging', label: 'Data Flow & Staging Internals' },
            { slug: 'configuration', label: 'Configuration System' },
            { slug: 'contributing', label: 'Contributing' }
        ]}
    ];

    // Nagios reference categories (unchanged)
    var NAGIOS_CATEGORIES = [
        { name: 'Monitoring Objects', types: ['host', 'service'] },
        { name: 'Groups', types: ['hostgroup', 'servicegroup', 'contactgroup'] },
        { name: 'Contacts', types: ['contact'] },
        { name: 'Commands & Time', types: ['command', 'timeperiod'] },
        { name: 'Dependencies', types: ['hostdependency', 'servicedependency'] },
        { name: 'Escalations', types: ['hostescalation', 'serviceescalation'] },
        { name: 'Extended Info (Deprecated)', types: ['hostextinfo', 'serviceextinfo'] }
    ];

    var SPECIAL_INHERITANCE = '_inheritance';

    // SVG icons
    var ICONS = {
        chevron: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>',
        folder: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>',
        folderOpen: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v1"></path><path d="M2 10h20"></path></svg>',
        file: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>'
    };

    // State
    var selectedType = null;     // Nagios type name or null
    var selectedAppDoc = null;   // App doc slug or null
    var expandedSections = {};   // keyed by 'app', 'app-<index>', 'nagios', 'nagios-<catIndex>'
    var focusedIndex = -1;
    var allSelectableNodes = []; // flat list for keyboard nav
    var treeSearchQuery = '';
    var appDocCache = {};        // slug → HTML string

    // =========================================================================
    // Tree rendering
    // =========================================================================

    function renderTree() {
        var container = document.getElementById('docsTree');
        var html = '';
        var lower = treeSearchQuery.toLowerCase();

        html += renderAppDocsFolder(lower);
        html += renderNagiosFolder(lower);

        container.innerHTML = html;
        buildSelectableNodeList();
    }

    // --- App Docs folder ---

    function renderAppDocsFolder(searchLower) {
        var hasVisibleItems = false;
        var sectionsHtml = '';

        for (var i = 0; i < APP_DOCS_TREE.length; i++) {
            var section = APP_DOCS_TREE[i];
            var sectionHtml = renderAppSection(section, i, searchLower);
            if (sectionHtml) {
                hasVisibleItems = true;
                sectionsHtml += sectionHtml;
            }
        }

        if (!hasVisibleItems && searchLower) return '';

        var isExpanded = expandedSections['app'] !== false;

        var html = '<div class="workspace-tree-row' + (isExpanded ? ' expanded' : '') + '" data-depth="0" data-folder="app" onclick="DocsPage.toggleFolder(\'app\')">';
        html += '<button class="tree-expand-btn' + (isExpanded ? ' expanded' : '') + '">' + ICONS.chevron + '</button>';
        html += '<span class="tree-icon tree-icon--folder' + (isExpanded ? ' expanded' : '') + '">' + (isExpanded ? ICONS.folderOpen : ICONS.folder) + '</span>';
        html += '<span class="tree-label tree-label--folder">App Docs</span>';
        html += '</div>';

        html += '<div class="tree-children' + (isExpanded ? ' expanded' : '') + '">';
        html += sectionsHtml;
        html += '</div>';
        return html;
    }

    function renderAppSection(section, sectionIndex, searchLower) {
        var visibleItems = [];
        for (var i = 0; i < section.items.length; i++) {
            var item = section.items[i];
            if (!searchLower || item.label.toLowerCase().indexOf(searchLower) !== -1 || item.slug.indexOf(searchLower) !== -1) {
                visibleItems.push(item);
            }
        }
        if (visibleItems.length === 0) return '';

        var key = 'app-' + sectionIndex;
        var isExpanded = expandedSections[key] !== false;

        var html = '<div class="workspace-tree-row' + (isExpanded ? ' expanded' : '') + '" data-depth="1" data-folder="' + key + '" onclick="DocsPage.toggleFolder(\'' + key + '\')">';
        html += '<button class="tree-expand-btn' + (isExpanded ? ' expanded' : '') + '">' + ICONS.chevron + '</button>';
        html += '<span class="tree-icon tree-icon--folder' + (isExpanded ? ' expanded' : '') + '">' + (isExpanded ? ICONS.folderOpen : ICONS.folder) + '</span>';
        html += '<span class="tree-label tree-label--folder">' + escapeHtml(section.section) + '</span>';
        html += '<span class="tree-count">' + visibleItems.length + '</span>';
        html += '</div>';

        html += '<div class="tree-children' + (isExpanded ? ' expanded' : '') + '">';
        for (var j = 0; j < visibleItems.length; j++) {
            var item = visibleItems[j];
            var isSelected = selectedAppDoc === item.slug;
            html += '<div class="workspace-tree-row' + (isSelected ? ' selected' : '') + '" data-depth="2" data-app-doc="' + item.slug + '" onclick="DocsPage.selectAppDoc(\'' + item.slug + '\')">';
            html += '<span class="tree-expand-placeholder"></span>';
            html += '<span class="tree-icon tree-icon--file">' + ICONS.file + '</span>';
            html += '<span class="tree-label">' + escapeHtml(item.label) + '</span>';
            html += '</div>';
        }
        html += '</div>';
        return html;
    }

    // --- Nagios Reference folder ---

    function renderNagiosFolder(searchLower) {
        var hasVisibleItems = false;
        var categoriesHtml = '';

        for (var i = 0; i < NAGIOS_CATEGORIES.length; i++) {
            var catHtml = renderNagiosCategory(NAGIOS_CATEGORIES[i], i, searchLower);
            if (catHtml) {
                hasVisibleItems = true;
                categoriesHtml += catHtml;
            }
        }

        // Inheritance entry
        var inheritanceVisible = !searchLower || 'inheritance'.indexOf(searchLower) !== -1 ||
            'template'.indexOf(searchLower) !== -1 || 'use register name'.indexOf(searchLower) !== -1;
        if (inheritanceVisible) {
            hasVisibleItems = true;
            categoriesHtml += renderInheritanceRow();
        }

        if (!hasVisibleItems && searchLower) return '';

        var isExpanded = expandedSections['nagios'] === true; // collapsed by default

        var html = '<div class="workspace-tree-row' + (isExpanded ? ' expanded' : '') + '" data-depth="0" data-folder="nagios" onclick="DocsPage.toggleFolder(\'nagios\')">';
        html += '<button class="tree-expand-btn' + (isExpanded ? ' expanded' : '') + '">' + ICONS.chevron + '</button>';
        html += '<span class="tree-icon tree-icon--folder' + (isExpanded ? ' expanded' : '') + '">' + (isExpanded ? ICONS.folderOpen : ICONS.folder) + '</span>';
        html += '<span class="tree-label tree-label--folder">Nagios Reference</span>';
        html += '</div>';

        html += '<div class="tree-children' + (isExpanded ? ' expanded' : '') + '">';
        html += categoriesHtml;
        html += '</div>';
        return html;
    }

    function renderNagiosCategory(cat, catIndex, searchLower) {
        var visibleTypes = [];
        for (var i = 0; i < cat.types.length; i++) {
            var typeName = cat.types[i];
            var typeData = REF[typeName];
            if (!searchLower || matchesNagiosSearch(typeName, typeData, searchLower)) {
                visibleTypes.push(typeName);
            }
        }
        if (visibleTypes.length === 0) return '';

        var key = 'nagios-' + catIndex;
        var isExpanded = expandedSections[key] !== false;
        var totalDirectives = 0;
        for (var i = 0; i < visibleTypes.length; i++) {
            totalDirectives += REF[visibleTypes[i]].directives.length;
        }

        var html = '<div class="workspace-tree-row' + (isExpanded ? ' expanded' : '') + '" data-depth="1" data-folder="' + key + '" onclick="DocsPage.toggleFolder(\'' + key + '\')">';
        html += '<button class="tree-expand-btn' + (isExpanded ? ' expanded' : '') + '">' + ICONS.chevron + '</button>';
        html += '<span class="tree-icon tree-icon--folder' + (isExpanded ? ' expanded' : '') + '">' + (isExpanded ? ICONS.folderOpen : ICONS.folder) + '</span>';
        html += '<span class="tree-label tree-label--folder">' + escapeHtml(cat.name) + '</span>';
        html += '<span class="tree-count">' + totalDirectives + '</span>';
        html += '</div>';

        html += '<div class="tree-children' + (isExpanded ? ' expanded' : '') + '">';
        for (var i = 0; i < visibleTypes.length; i++) {
            html += renderNagiosTypeRow(visibleTypes[i]);
        }
        html += '</div>';
        return html;
    }

    function matchesNagiosSearch(typeName, typeData, lower) {
        if (typeName.indexOf(lower) !== -1) return true;
        var label = (typeData.label || '').toLowerCase();
        if (label.indexOf(lower) !== -1) return true;
        if (typeData.description.toLowerCase().indexOf(lower) !== -1) return true;
        for (var i = 0; i < typeData.directives.length; i++) {
            if (typeData.directives[i].name.toLowerCase().indexOf(lower) !== -1) return true;
        }
        return false;
    }

    function renderNagiosTypeRow(typeName) {
        var typeData = REF[typeName];
        var isSelected = selectedType === typeName;
        var label = typeData.label || typeName;

        var html = '<div class="workspace-tree-row' + (isSelected ? ' selected' : '') + '" data-depth="2" data-type="' + typeName + '" onclick="DocsPage.selectType(\'' + typeName + '\')">';
        html += '<span class="tree-expand-placeholder"></span>';
        html += '<span class="tree-icon tree-icon--file">' + ICONS.file + '</span>';
        html += '<span class="tree-label">' + escapeHtml(label) + '</span>';
        html += '<span class="tree-count">' + typeData.directives.length + '</span>';
        html += '</div>';
        return html;
    }

    function renderInheritanceRow() {
        var isSelected = selectedType === SPECIAL_INHERITANCE;
        var sectionCount = INHERITANCE ? INHERITANCE.length : 0;

        var html = '<div class="workspace-tree-row' + (isSelected ? ' selected' : '') + '" data-depth="1" data-type="' + SPECIAL_INHERITANCE + '" onclick="DocsPage.selectType(\'' + SPECIAL_INHERITANCE + '\')">';
        html += '<span class="tree-expand-placeholder"></span>';
        html += '<span class="tree-icon tree-icon--file">' + ICONS.file + '</span>';
        html += '<span class="tree-label">Inheritance</span>';
        html += '<span class="tree-count">' + sectionCount + '</span>';
        html += '</div>';
        return html;
    }

    function buildSelectableNodeList() {
        allSelectableNodes = [];
        var rows = document.querySelectorAll('.docs-tree-container .workspace-tree-row[data-app-doc], .docs-tree-container .workspace-tree-row[data-type]');
        for (var i = 0; i < rows.length; i++) {
            allSelectableNodes.push(rows[i]);
        }
    }

    // =========================================================================
    // Tree interactions
    // =========================================================================

    function toggleFolder(key) {
        if (key === 'nagios') {
            expandedSections[key] = expandedSections[key] !== true;
        } else {
            expandedSections[key] = expandedSections[key] === false;
        }
        renderTree();
    }

    function selectAppDoc(slug) {
        selectedAppDoc = slug;
        selectedType = null;

        // Ensure parent sections are expanded
        expandedSections['app'] = true;
        for (var i = 0; i < APP_DOCS_TREE.length; i++) {
            for (var j = 0; j < APP_DOCS_TREE[i].items.length; j++) {
                if (APP_DOCS_TREE[i].items[j].slug === slug) {
                    expandedSections['app-' + i] = true;
                    break;
                }
            }
        }

        renderTree();
        loadAppDocContent(slug);
        updateHash();
    }

    function selectType(typeName) {
        selectedType = typeName;
        selectedAppDoc = null;

        // Ensure Nagios folder is expanded
        expandedSections['nagios'] = true;
        if (typeName === SPECIAL_INHERITANCE) {
            renderTree();
            renderInheritanceContent();
            updateHash();
            return;
        }

        for (var i = 0; i < NAGIOS_CATEGORIES.length; i++) {
            if (NAGIOS_CATEGORIES[i].types.indexOf(typeName) !== -1) {
                expandedSections['nagios-' + i] = true;
                break;
            }
        }
        renderTree();
        renderNagiosContent(typeName);
        updateHash();
    }

    // =========================================================================
    // App doc content loading
    // =========================================================================

    function loadAppDocContent(slug) {
        var container = document.getElementById('docsContent');

        if (appDocCache[slug]) {
            container.innerHTML = appDocCache[slug];
            return;
        }

        container.innerHTML = '<div class="empty-state empty-state--dark empty-state--flex"><div class="empty-icon"><i class="fa-solid fa-spinner fa-spin"></i></div><p>Loading...</p></div>';

        fetch('/api/docs/' + encodeURIComponent(slug))
            .then(function(resp) {
                if (!resp.ok) throw new Error('Not found');
                return resp.text();
            })
            .then(function(html) {
                appDocCache[slug] = html;
                // Only update if still the selected doc
                if (selectedAppDoc === slug) {
                    container.innerHTML = html;
                }
            })
            .catch(function() {
                if (selectedAppDoc === slug) {
                    container.innerHTML = '<div class="empty-state empty-state--dark empty-state--flex"><div class="empty-icon"><i class="fa-solid fa-triangle-exclamation"></i></div><h3>Page not found</h3><p>This documentation page is not available yet.</p></div>';
                }
            });
    }

    // =========================================================================
    // Global tree search
    // =========================================================================

    function handleTreeSearch(value) {
        treeSearchQuery = value;
        if (value) {
            // Expand everything to show results
            expandedSections['app'] = true;
            expandedSections['nagios'] = true;
            for (var i = 0; i < APP_DOCS_TREE.length; i++) {
                expandedSections['app-' + i] = true;
            }
            for (var j = 0; j < NAGIOS_CATEGORIES.length; j++) {
                expandedSections['nagios-' + j] = true;
            }
        }
        renderTree();
    }

    // =========================================================================
    // Nagios reference content rendering (unchanged logic)
    // =========================================================================

    function renderNagiosContent(typeName) {
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

        for (var i = 0; i < typeData.directives.length; i++) {
            html += renderDirectiveRow(typeData.directives[i]);
        }

        if (templateDirs.length > 0) {
            html += '<tr class="docs-section-divider"><td colspan="4">Template Directives (common to all types)</td></tr>';
            for (var j = 0; j < templateDirs.length; j++) {
                html += renderDirectiveRow(templateDirs[j]);
            }
        }

        html += '</tbody></table>';
        html += '</div>';

        container.innerHTML = html;

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

        var primaryName = directive.name.split('|')[0].trim();

        var html = '<tr class="docs-directive-row" id="directive-' + escapeHtml(primaryName) + '">';
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
        var dividers = document.querySelectorAll('#docsDirectiveBody .docs-section-divider');
        for (var j = 0; j < dividers.length; j++) {
            dividers[j].style.display = lower ? 'none' : '';
        }
    }

    // =========================================================================
    // Inheritance content rendering (unchanged)
    // =========================================================================

    function renderInheritanceContent() {
        var container = document.getElementById('docsContent');
        if (!INHERITANCE || !INHERITANCE.length) {
            container.innerHTML = '<div class="empty-state empty-state--dark empty-state--flex"><h3>No inheritance data available</h3></div>';
            return;
        }

        var html = '<div class="docs-type-header">';
        html += '<h2 class="docs-type-title">Object Inheritance</h2>';
        html += '<p class="docs-type-desc">Nagios supports template-based object inheritance, allowing you to define shared defaults in template objects and have other objects inherit those properties. This reduces configuration duplication and makes large deployments manageable.</p>';
        html += '<div class="docs-type-meta">';
        html += '<span class="docs-directive-count">' + INHERITANCE.length + ' topics</span>';
        html += '</div>';
        html += '</div>';

        html += '<div class="docs-inheritance-container">';
        for (var i = 0; i < INHERITANCE.length; i++) {
            html += renderInheritanceSection(INHERITANCE[i], i);
        }
        html += '</div>';

        container.innerHTML = html;
    }

    function renderInheritanceSection(section, index) {
        var html = '<div class="docs-inheritance-section">';
        html += '<h3 class="docs-inheritance-title">';
        html += '<span class="docs-inheritance-number">' + (index + 1) + '</span>';
        html += escapeHtml(section.title);
        html += '</h3>';
        html += '<div class="docs-inheritance-text">' + section.content + '</div>';

        if (section.table) {
            html += '<div class="docs-inheritance-table-wrap">';
            html += '<table class="docs-directive-table docs-inheritance-table">';
            html += '<thead><tr>';
            for (var h = 0; h < section.table.headers.length; h++) {
                html += '<th>' + escapeHtml(section.table.headers[h]) + '</th>';
            }
            html += '</tr></thead><tbody>';
            for (var r = 0; r < section.table.rows.length; r++) {
                html += '<tr>';
                for (var c = 0; c < section.table.rows[r].length; c++) {
                    html += '<td>' + escapeHtml(section.table.rows[r][c]) + '</td>';
                }
                html += '</tr>';
            }
            html += '</tbody></table>';
            html += '</div>';
        }

        if (section.example) {
            html += '<pre class="docs-code-block"><code>' + escapeHtml(section.example) + '</code></pre>';
        }
        html += '</div>';
        return html;
    }

    // =========================================================================
    // URL hash navigation
    // =========================================================================

    function updateHash() {
        if (selectedAppDoc) {
            history.replaceState(null, '', '#app/' + selectedAppDoc);
        } else if (selectedType) {
            history.replaceState(null, '', '#' + selectedType);
        }
    }

    function scrollToDirective(directiveName) {
        setTimeout(function() {
            var row = document.getElementById('directive-' + directiveName);
            if (!row) return;
            var container = document.querySelector('.docs-table-container');
            if (container) {
                var rowTop = row.offsetTop - container.offsetTop;
                var centerOffset = rowTop - (container.clientHeight / 2) + (row.offsetHeight / 2);
                container.scrollTo({ top: centerOffset, behavior: 'smooth' });
            }
            row.classList.add('docs-directive-highlight');
            setTimeout(function() {
                row.classList.remove('docs-directive-highlight');
            }, 2000);
        }, 100);
    }

    function loadFromHash() {
        var hash = window.location.hash.replace('#', '');
        if (!hash) return;

        var parts = hash.split('/');

        // App docs: #app/<slug>
        if (parts[0] === 'app' && parts[1]) {
            selectAppDoc(decodeURIComponent(parts[1]));
            return;
        }

        // Nagios reference: #<type> or #<type>/<directive>
        var typePart = decodeURIComponent(parts[0]);
        var directivePart = parts[1] ? decodeURIComponent(parts[1]) : null;

        if (typePart === SPECIAL_INHERITANCE) {
            selectType(SPECIAL_INHERITANCE);
        } else if (typePart && REF[typePart] && typePart !== '_template_directives') {
            selectType(typePart);
            if (directivePart) {
                scrollToDirective(directivePart);
            }
        }
    }

    // =========================================================================
    // Keyboard navigation
    // =========================================================================

    function handleKeydown(e) {
        if (e.target.tagName === 'INPUT') {
            if (e.key === 'Escape') {
                e.target.value = '';
                if (e.target.id === 'docsDirectiveSearch') {
                    filterDirectives('');
                } else if (e.target.id === 'docsTreeSearch') {
                    handleTreeSearch('');
                }
                e.target.blur();
                e.preventDefault();
            }
            return;
        }

        if (document.querySelector('.keyboard-shortcuts-overlay.visible') ||
            document.querySelector('.confirm-dialog-overlay.visible')) {
            return;
        }

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                navigateNodes(1);
                break;
            case 'ArrowUp':
                e.preventDefault();
                navigateNodes(-1);
                break;
            case 'Enter':
                e.preventDefault();
                if (focusedIndex >= 0 && focusedIndex < allSelectableNodes.length) {
                    var node = allSelectableNodes[focusedIndex];
                    var appDoc = node.getAttribute('data-app-doc');
                    var typeName = node.getAttribute('data-type');
                    if (appDoc) selectAppDoc(appDoc);
                    else if (typeName) selectType(typeName);
                }
                break;
            case '/':
                if (!e.ctrlKey && !e.metaKey) {
                    e.preventDefault();
                    var search = document.getElementById('docsTreeSearch');
                    if (search) search.focus();
                }
                break;
        }
    }

    function navigateNodes(direction) {
        if (allSelectableNodes.length === 0) return;

        if (focusedIndex < 0) {
            // Try to find currently selected node
            for (var i = 0; i < allSelectableNodes.length; i++) {
                var node = allSelectableNodes[i];
                if ((selectedAppDoc && node.getAttribute('data-app-doc') === selectedAppDoc) ||
                    (selectedType && node.getAttribute('data-type') === selectedType)) {
                    focusedIndex = i;
                    break;
                }
            }
        }

        focusedIndex += direction;
        if (focusedIndex < 0) focusedIndex = 0;
        if (focusedIndex >= allSelectableNodes.length) focusedIndex = allSelectableNodes.length - 1;

        var node = allSelectableNodes[focusedIndex];
        var appDoc = node.getAttribute('data-app-doc');
        var typeName = node.getAttribute('data-type');
        if (appDoc) selectAppDoc(appDoc);
        else if (typeName) selectType(typeName);
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
        toggleFolder: toggleFolder,
        selectType: selectType,
        selectAppDoc: selectAppDoc,
        handleTreeSearch: handleTreeSearch
    };

    // =========================================================================
    // Init
    // =========================================================================

    document.addEventListener('DOMContentLoaded', function() {
        // App docs expanded by default, Nagios reference collapsed
        expandedSections['app'] = true;
        for (var i = 0; i < APP_DOCS_TREE.length; i++) {
            expandedSections['app-' + i] = true;
        }
        expandedSections['nagios'] = false;

        renderTree();
        loadFromHash();

        // If nothing was selected from hash, show overview by default
        if (!selectedAppDoc && !selectedType) {
            selectAppDoc('overview');
        }

        document.addEventListener('keydown', handleKeydown);
        window.addEventListener('hashchange', loadFromHash);
    });

})();
