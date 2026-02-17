/** Explorer Object Editor Module - Center pane object display, attribute editing, staging */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;
    const identityFields = constants.identityFields;

    // Inheritance cache: stableKey -> {chain, inherited, errors}
    if (!state.inheritanceCache) {state.inheritanceCache = new Map();}

    // Access constants via constants.* at call time — NOT cached as local const.
    // applyMetadata() replaces these with new objects/arrays after page load,
    // so local const aliases would hold stale references to the initial empties.

    /**
     * C-05: Validate object has required fields.
     * @param {string} objectType - The object type
     * @param {Object} attributes - The object attributes
     * @returns {{valid: boolean, errors: string[]}} Validation result
     */
    function validateRequiredFields(objectType, attributes) {
        const errors = [];
        const requirements = constants.REQUIRED_FIELDS[objectType];

        if (!requirements) {
            // Unknown object type - allow it (might be a custom type)
            return { valid: true, errors: [] };
        }

        // Check if this is a template (register=0)
        const isTemplate = attributes.register === '0';

        // Templates need 'name' field instead of type-specific name field
        if (isTemplate) {
            if (!attributes.name || attributes.name.trim() === '') {
                errors.push("Templates require the 'name' attribute");
            }
            // For templates, skip other required field checks (they're inherited)
            return { valid: errors.length === 0, errors };
        }

        // Check each requirement
        for (const req of requirements) {
            if (Array.isArray(req)) {
                // OR condition - at least one of these fields must be present
                const hasAny = req.some(field => attributes[field] && attributes[field].trim() !== '');
                if (!hasAny) {
                    errors.push(`One of these fields is required: ${req.join(' or ')}`);
                }
            } else if (!attributes[req] || attributes[req].trim() === '') {
                errors.push(`'${req}' is required`);
            }
        }

        return { valid: errors.length === 0, errors };
    }

    // Nagios attribute definitions by object type (from constants, populated by /api/metadata)

    function showCenterPaneObject(obj) {
        hideDocsPopover();
        DebugLogger.debug('Showing object in center pane', {
            displayName: obj.display_name,
            objectType: obj.object_type,
            globalIndex: obj.global_index
        });

        // Check if there are pending edits for this object
        const pendingEdit = state.pendingEdits.get(obj.global_index);
        if (pendingEdit) {
            // Use the edited attributes, but keep object reference for other properties
            state.editedObject = {...obj, attributes: {...pendingEdit.edited}};
            state.originalAttributes = {...pendingEdit.original};
        } else {
            state.editedObject = obj;
            state.originalAttributes = {...obj.attributes};
        }

        state.isNewObject = false;
        state.newObjectStagedIndex = null;

        // Hide close button for regular objects
        document.getElementById('centerCloseBtn').style.display = 'none';

        const isTemplate = Explorer.isObjectTemplate(obj);
        const isOrphan = Explorer.state.orphanIndices.has(obj.global_index);
        const hostListInfo = Explorer.getHostListInfo(obj);
        const issue = Explorer.getObjectIssue(obj);

        // Store current object info for issue navigation
        state.currentCenterObject = obj;
        state.currentCenterIssue = issue;
        state.currentCenterIsOrphan = isOrphan;
        state.currentCenterHostListInfo = hostListInfo;

        let typeText = isTemplate ? `${obj.object_type} template` : obj.object_type;

        const typeEl = document.getElementById('centerCardType');
        typeEl.textContent = typeText;
        typeEl.className = 'card-type type-' + obj.object_type + (isTemplate ? ' is-template' : '');

        // Show separate issue button
        const issueBtn = document.getElementById('centerCardIssue');
        const badgeDisplayName = obj.display_name || obj.attributes?.name || '';
        if (issue) {
            const icon = Explorer.getIssueIcon(issue);
            let issueLabel = Explorer.getIssueShortLabel(issue);
            let issueTitle = 'Click to view in Analysis tab';
            const displayName = badgeDisplayName;

            // Format labels to match cleanup tab titles
            if (issue.type === 'duplicate_name' || issue.type === 'duplicate') {
                issueLabel = `Duplicate ${obj.object_type}: ${displayName}`;
                issueTitle = issue.message || `Duplicate ${obj.object_type} name`;
            } else if (issue.type === 'orphan') {
                issueLabel = `Orphan ${obj.object_type}: ${displayName}`;
                issueTitle = 'This object is not referenced by any other object';
            } else if (issue.type === 'empty_group') {
                issueLabel = `Empty ${obj.object_type}: ${displayName}`;
                issueTitle = 'This group has no members';
            } else if (issue.type === 'unused_template') {
                issueLabel = `Unused template: ${displayName}`;
                issueTitle = issue.message || `This template is not used by any ${obj.object_type}`;
            } else if (issue.type === 'unused_command') {
                issueLabel = `Unused command: ${displayName}`;
                issueTitle = 'This command is not used by any service or host';
            } else if (issue.type === 'unused_contact') {
                issueLabel = `Unused contact: ${displayName}`;
                issueTitle = 'This contact is not used by any object';
            } else if (issue.type === 'unused_contactgroup') {
                issueLabel = `Unused contactgroup: ${displayName}`;
                issueTitle = 'This contact group is not used by any object';
            } else if (issue.type === 'unused_timeperiod') {
                issueLabel = `Unused timeperiod: ${displayName}`;
                issueTitle = 'This time period is not used by any object';
            } else if (issue.type === 'long_host_list') {
                const hostCount = obj.attributes?.host_name?.split(',').length || 0;
                issueLabel = `Consider hostgroup: ${hostCount} individual hosts listed`;
                issueTitle = `This ${obj.object_type} has ${hostCount} hosts listed individually. Consider using a hostgroup instead.`;
            } else if (issue.type && issue.type.startsWith('missing_') && issue.message) {
                // For missing references, extract the missing name from the message
                const patterns = {
                    'missing_template': /undefined \w+ template[:\s]+['"]?([^'"]+)['"]?$/i,
                    'missing_command': /non-existent command[:\s]+['"]?([^'"!]+)/i,
                    'missing_timeperiod': /non-existent timeperiod[:\s]+['"]?([^'"]+)['"]?$/i,
                    'missing_contact': /non-existent contact[:\s]+['"]?([^'"]+)['"]?$/i,
                    'missing_contactgroup': /non-existent contactgroup[:\s]+['"]?([^'"]+)['"]?$/i,
                    'missing_hostgroup': /non-existent hostgroup[:\s]+['"]?([^'"]+)['"]?$/i,
                    'missing_servicegroup': /non-existent servicegroup[:\s]+['"]?([^'"]+)['"]?$/i,
                    'missing_host': /non-existent host[:\s]+['"]?([^'"]+)['"]?$/i
                };
                const pattern = patterns[issue.type];
                if (pattern) {
                    const match = issue.message.match(pattern);
                    if (match) {
                        const typeLabel = issue.type.replace('missing_', '');
                        issueLabel = `Missing ${typeLabel}: ${match[1]}`;
                    }
                }
                issueTitle = issue.message;
            }

            issueBtn.innerHTML = `${icon} ${issueLabel}`;
            issueBtn.className = `card-issue-btn severity-${issue.severity}`;
            issueBtn.style.display = 'inline-flex';
            issueBtn.title = issueTitle;
        } else if (hostListInfo.shouldGroup) {
            issueBtn.innerHTML = `<i class="fa-solid fa-list"></i> Consider hostgroup: ${hostListInfo.count} individual hosts listed`;
            issueBtn.className = 'card-issue-btn severity-info';
            issueBtn.style.display = 'inline-flex';
            issueBtn.title = `This ${obj.object_type} has ${hostListInfo.count} hosts listed individually. Consider using a hostgroup instead.`;
        } else {
            issueBtn.style.display = 'none';
        }

        // Compute display name from staged attributes if available
        const nameField = Explorer.getNameFieldForObject(obj);
        const displayName = state.editedObject.attributes[nameField] || obj.display_name;
        document.getElementById('centerCardName').textContent = displayName;

        // Show just filename in breadcrumb (not full path)
        const filename = obj.source_file.split('/').pop() || obj.source_file;
        document.getElementById('centerCardFile').textContent = filename;
        document.getElementById('centerCardFile').title = obj.source_file; // Full path on hover

        renderCenterAttributes();

        // Load unified Impact & Relationships section
        Explorer.loadImpactAndRelationships(state.editedObject);

        // Default impact section to collapsed, then restore saved state from localStorage
        setTimeout(() => {
            const titleEl = document.querySelector('#impactSection .section-title');
            const contentEl = document.getElementById('impactContent');
            if (titleEl) {titleEl.classList.add('collapsed');}
            if (contentEl) {
                contentEl.classList.add('collapsed');
                contentEl.style.display = 'none';
            }
            restoreDetailSectionState();
        }, 0);

        const emptyState = document.getElementById('centerEmptyState');
        const content = document.getElementById('centerContent');
        emptyState.classList.add('u-hidden');
        emptyState.style.display = 'none';
        content.classList.remove('u-hidden');
        content.style.display = 'flex';
    }

    function hideCenterPaneObject() {
        state.editedObject = null;
        state.originalAttributes = {};
        state.isNewObject = false;
        state.newObjectStagedIndex = null;
        Explorer.checkPendingExternalChanges();
        const emptyState = document.getElementById('centerEmptyState');
        const content = document.getElementById('centerContent');
        emptyState.classList.remove('u-hidden');
        emptyState.style.display = 'flex';
        content.classList.add('u-hidden');
        content.style.display = 'none';
    }

    /**
     * Sync center pane state after an undo operation.
     * Updates the displayed attributes to reflect the current staging state.
     */
    function syncCenterPaneAfterUndo() {
        if (!state.editedObject) {return;}

        // If showing a new object (staged creation), hide it since creation was likely undone
        if (state.isNewObject) {
            hideCenterPaneObject();
            return;
        }

        // For existing objects, sync attributes with current pendingEdits state
        const globalIndex = state.editedObject.global_index;
        if (globalIndex === undefined || globalIndex === -1) {return;}

        const obj = state.allObjects.find(o => o.global_index === globalIndex);
        if (!obj) {
            hideCenterPaneObject();
            return;
        }

        // Check if there are still pending edits for this object
        const pendingEdit = state.pendingEdits.get(globalIndex);
        if (pendingEdit) {
            // Still has pending edits - use them
            state.editedObject.attributes = {...pendingEdit.edited};
            state.originalAttributes = {...pendingEdit.original};
        } else {
            // No pending edits - use original attributes
            state.editedObject.attributes = {...obj.attributes};
            state.originalAttributes = {...obj.attributes};
        }

        // Re-render the attributes display
        renderCenterAttributes();

        // Refresh Impact & Relationships section
        Explorer.loadImpactAndRelationships(state.editedObject);
    }

    function showCenterPaneMultiple(count) {
        const emptyState = document.getElementById('centerEmptyState');
        const content = document.getElementById('centerContent');
        emptyState.innerHTML = `
            <div class="empty-icon"><i class="fa-solid fa-clipboard-list"></i></div>
            <h3>${count} objects selected</h3>
            <p>Use the Actions menu for bulk operations</p>
        `;
        emptyState.classList.remove('u-hidden');
        emptyState.style.display = 'flex';
        content.classList.add('u-hidden');
        content.style.display = 'none';
    }

    function getAttributeSuggestions(attrName, objectType) {
        // Handle notification options and failure criteria
        if (constants.NOTIFICATION_OPTION_ATTRS.includes(attrName)) {
            if (attrName === 'host_notification_options') {
                return constants.HOST_NOTIFICATION_OPTIONS;
            } else if (attrName === 'service_notification_options') {
                return constants.SERVICE_NOTIFICATION_OPTIONS;
            } else if (attrName === 'notification_options') {
                // notification_options depends on the object type
                if (objectType === 'host' || objectType === 'hostescalation' || objectType === 'hostdependency') {
                    return constants.HOST_NOTIFICATION_OPTIONS;
                } 
                    return constants.SERVICE_NOTIFICATION_OPTIONS;
                
            } else if (attrName === 'execution_failure_criteria' || attrName === 'notification_failure_criteria') {
                // Failure criteria depends on dependency type
                if (objectType === 'hostdependency') {
                    return constants.HOST_FAILURE_CRITERIA;
                } 
                    return constants.SERVICE_FAILURE_CRITERIA;
                
            } else if (attrName === 'escalation_options') {
                if (objectType === 'hostescalation') {
                    return constants.HOST_ESCALATION_OPTIONS;
                } 
                    return constants.SERVICE_ESCALATION_OPTIONS;
                
            } else if (attrName === 'stalking_options') {
                if (objectType === 'host') {
                    return constants.HOST_STALKING_OPTIONS;
                } 
                    return constants.SERVICE_STALKING_OPTIONS;
                
            } else if (attrName === 'flap_detection_options') {
                if (objectType === 'host') {
                    return constants.HOST_FLAP_DETECTION_OPTIONS;
                } 
                    return constants.SERVICE_FLAP_DETECTION_OPTIONS;
                
            }
        }

        let refType = constants.ATTR_REFERENCE_MAP[attrName];

        // Handle special cases
        if (attrName === 'use') {
            // Templates of the same type with register=0
            return getTemplatesForType(objectType);
        } else if (attrName === 'members') {
            // Members depends on the group type
            if (objectType === 'hostgroup') {refType = 'host';}
            else if (objectType === 'servicegroup') {refType = 'service';}
            else if (objectType === 'contactgroup') {refType = 'contact';}
        }

        if (!refType) {return [];}

        // C-06: Build a set of objects staged for deletion
        // stagedObjectDeletions is a Set of global_index values
        const stagedDeletionIndices = state.stagedObjectDeletions || new Set();
        const deletedKeys = new Set();
        for (const idx of stagedDeletionIndices) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (obj) {
                deletedKeys.add(`${obj.source_file}:${obj.line_number}`);
            }
        }

        // Get all objects of the referenced type from current disk state
        // C-06: Filter out objects that are staged for deletion
        const suggestions = state.allObjects
            .filter(o => {
                if (o.object_type !== refType) {return false;}
                // Check if this object is staged for deletion
                const objKey = `${o.source_file}:${o.line_number}`;
                if (deletedKeys.has(objKey)) {return false;}
                return true;
            })
            .map(o => o.display_name)
            .filter(name => name && name !== '(unnamed)');

        // F-04: Also include staged creations that haven't been applied yet
        // This allows referencing objects created in the same editing session
        const stagedCreations = state.stagedCreations || [];
        for (const creation of stagedCreations) {
            if (creation.object_type === refType) {
                const nameField = constants.nameFields[refType];
                const name = creation.attributes?.[nameField];
                if (name && name !== '(unnamed)' && !suggestions.includes(name)) {
                    suggestions.push(name);
                }
            }
        }

        return [...new Set(suggestions)].sort(); // Remove duplicates and sort
    }

    // Attributes that typically have long values and should use textarea
    const LONG_VALUE_ATTRS = ['command_line', 'alias', 'notes', 'notes_url', 'action_url', 'icon_image', 'icon_image_alt', 'statusmap_image', 'vrml_image', '2d_coords', '3d_coords'];

    /**
     * Syntax highlight Nagios command values
     * Highlights: $MACROS$, escape sequences, pipes, flags
     */
    function highlightCommandSyntax(text) {
        if (!text) {return '';}

        // Tokenize and highlight before escaping to avoid regex issues with HTML entities
        const tokens = [];
        let remaining = text;

        while (remaining.length > 0) {
            let match;

            // Check for Nagios macros ($MACRO$) - highest priority
            if ((match = remaining.match(/^(\$[A-Z_][A-Z0-9_]*\$)/))) {
                tokens.push({ type: 'macro', value: match[1] });
                remaining = remaining.slice(match[1].length);
            }
            // Check for escape sequences (\n, \t, etc.)
            else if ((match = remaining.match(/^(\\[nrt\\])/))) {
                tokens.push({ type: 'escape', value: match[1] });
                remaining = remaining.slice(match[1].length);
            }
            // Check for pipe operators
            else if ((match = remaining.match(/^(\s\|\s)/))) {
                tokens.push({ type: 'pipe', value: match[1] });
                remaining = remaining.slice(match[1].length);
            }
            // Check for command flags
            else if ((match = remaining.match(/^(\s-[a-zA-Z]+)(?=\s|$)/))) {
                tokens.push({ type: 'flag', value: match[1] });
                remaining = remaining.slice(match[1].length);
            }
            // Check for paths starting with /
            else if ((match = remaining.match(/^(\/[a-zA-Z0-9_\/.+-]+)/))) {
                tokens.push({ type: 'path', value: match[1] });
                remaining = remaining.slice(match[1].length);
            }
            // Regular character
            else {
                tokens.push({ type: 'text', value: remaining[0] });
                remaining = remaining.slice(1);
            }
        }

        // Build highlighted HTML
        return tokens.map(token => {
            const escaped = Explorer.escapeHtml(token.value);
            switch (token.type) {
                case 'macro': return `<span class="hl-macro">${escaped}</span>`;
                case 'escape': return `<span class="hl-escape">${escaped}</span>`;
                case 'pipe': return `<span class="hl-pipe">${escaped}</span>`;
                case 'flag': return `<span class="hl-flag">${escaped}</span>`;
                case 'path': return `<span class="hl-path">${escaped}</span>`;
                default: return escaped;
            }
        }).join('');
    }

    /**
     * Sync textarea content to highlight overlay
     */
    function syncHighlight(textarea) {
        const wrapper = textarea.closest('.attr-value-long-wrapper');
        if (!wrapper) {return;}
        const highlight = wrapper.querySelector('.attr-value-highlight');
        if (!highlight) {return;}
        highlight.innerHTML = highlightCommandSyntax(textarea.value);
    }
    Explorer.syncHighlight = syncHighlight;

    // =========================================================================
    // Attribute Docs Popover
    // =========================================================================

    var docsPopoverEl = null;
    var docsPopoverShowTimer = null;
    var docsPopoverHideTimer = null;

    /**
     * Look up a directive in NAGIOS_OBJECT_REFERENCE for the given object type.
     * Handles aliases like "obsess_over_host|obsess" by splitting on "|".
     * Also checks _template_directives for common template attrs (name, use, register).
     */
    function lookupDirective(objectType, attrName) {
        var ref = window.NAGIOS_OBJECT_REFERENCE;
        if (!ref) {return null;}

        var lower = attrName.toLowerCase();

        // Check type-specific directives first
        var typeData = ref[objectType];
        if (typeData && typeData.directives) {
            for (var i = 0; i < typeData.directives.length; i++) {
                var d = typeData.directives[i];
                var names = d.name.split('|');
                for (var j = 0; j < names.length; j++) {
                    if (names[j].trim().toLowerCase() === lower) {return d;}
                }
            }
        }

        // Check template directives (name, use, register)
        var tmpl = ref._template_directives;
        if (tmpl && tmpl.directives) {
            for (var i = 0; i < tmpl.directives.length; i++) {
                var d = tmpl.directives[i];
                var names = d.name.split('|');
                for (var j = 0; j < names.length; j++) {
                    if (names[j].trim().toLowerCase() === lower) {return d;}
                }
            }
        }

        return null;
    }

    /**
     * Create the singleton popover element (once).
     */
    function ensurePopoverElement() {
        if (docsPopoverEl) {return docsPopoverEl;}
        docsPopoverEl = document.createElement('div');
        docsPopoverEl.className = 'attr-docs-popover';
        docsPopoverEl.id = 'attrDocsPopover';
        document.body.appendChild(docsPopoverEl);

        // Keep popover open when mouse is over it
        docsPopoverEl.addEventListener('mouseenter', function() {
            clearTimeout(docsPopoverHideTimer);
        });
        docsPopoverEl.addEventListener('mouseleave', function() {
            scheduleHidePopover();
        });

        // Dismiss on Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && docsPopoverEl.classList.contains('visible')) {
                hideDocsPopover();
            }
        });

        return docsPopoverEl;
    }

    /**
     * Position the popover relative to the target element.
     * Default below, flip above if not enough room.
     */
    function positionPopover(targetEl) {
        var el = ensurePopoverElement();
        var rect = targetEl.getBoundingClientRect();
        var gap = 8;

        // Temporarily show off-screen to measure
        el.style.left = '-9999px';
        el.style.top = '-9999px';
        el.classList.add('visible');
        var popoverHeight = el.offsetHeight;
        el.classList.remove('visible');

        var spaceBelow = window.innerHeight - rect.bottom - gap;
        var placeAbove = spaceBelow < popoverHeight && rect.top > popoverHeight + gap;

        el.classList.toggle('above', placeAbove);

        if (placeAbove) {
            el.style.top = (rect.top - popoverHeight - gap) + 'px';
        } else {
            el.style.top = (rect.bottom + gap) + 'px';
        }

        // Align left edge with attr-name, clamp to viewport
        var left = rect.left;
        var maxLeft = window.innerWidth - 340; // 320px width + 20px margin
        if (left > maxLeft) {left = maxLeft;}
        if (left < 8) {left = 8;}
        el.style.left = left + 'px';
    }

    /**
     * Show the docs popover for a directive.
     */
    function showDocsPopover(targetEl, directive, objectType) {
        var el = ensurePopoverElement();

        var badgeClass = directive.required ? 'attr-docs-badge--required' : 'attr-docs-badge--optional';
        var badgeText = directive.required ? 'Required' : 'Optional';

        // Build the deep link: /docs#objectType/directiveName
        // Use the first alias for the link (before any "|")
        var directiveName = directive.name.split('|')[0].trim();
        var docsHref = '/docs#' + encodeURIComponent(objectType) + '/' + encodeURIComponent(directiveName);

        el.innerHTML =
            '<div class="attr-docs-header">' +
                '<code class="attr-docs-name">' + Explorer.escapeHtml(directive.name) + '</code>' +
                '<span class="attr-docs-badge ' + badgeClass + '">' + badgeText + '</span>' +
            '</div>' +
            '<div class="attr-docs-format">Format: <code>' + Explorer.escapeHtml(directive.format) + '</code></div>' +
            '<div class="attr-docs-desc">' + Explorer.escapeHtml(directive.description) + '</div>' +
            '<a class="attr-docs-link" href="' + docsHref + '">View in docs \u2192</a>';

        positionPopover(targetEl);

        // Trigger transition
        requestAnimationFrame(function() {
            el.classList.add('visible');
        });
    }

    /**
     * Hide the popover immediately.
     */
    function hideDocsPopover() {
        clearTimeout(docsPopoverShowTimer);
        clearTimeout(docsPopoverHideTimer);
        if (docsPopoverEl) {
            docsPopoverEl.classList.remove('visible');
        }
    }
    Explorer.hideDocsPopover = hideDocsPopover;

    /**
     * Schedule hiding the popover after a grace period.
     */
    function scheduleHidePopover() {
        clearTimeout(docsPopoverHideTimer);
        docsPopoverHideTimer = setTimeout(hideDocsPopover, 200);
    }

    // Dismiss docs popover when center pane scrolls or window resizes
    document.addEventListener('DOMContentLoaded', function() {
        var cb = document.querySelector('.center-body');
        if (cb) {cb.addEventListener('scroll', hideDocsPopover);}
    });
    window.addEventListener('resize', hideDocsPopover);

    function renderCenterAttributes() {
        const container = document.getElementById('centerCardAttributes');
        if (!state.editedObject) {return;}
        const objectType = state.editedObject.object_type;

        container.innerHTML = Object.entries(state.editedObject.attributes || {})
            .map(([key, value]) => {
                const suggestions = getAttributeSuggestions(key, objectType);
                const hasSuggestions = suggestions.length > 0;
                // S-01: Pre-compute escaped key for safe use in HTML attributes
                // First escape for JS context, then escape for HTML attribute context
                const keyJsEscaped = Explorer.escapeJs(key);
                const keyHtmlAttr = Explorer.escapeHtml(keyJsEscaped);
                const inputEvents = hasSuggestions
                    ? `oninput="Explorer.showAttrAutocomplete(this, '${keyHtmlAttr}')" onblur="Explorer.hideAttrAutocomplete(event)" onkeydown="Explorer.handleAttrAutocompleteKey(event, '${keyHtmlAttr}')"`
                    : '';
                const placeholder = hasSuggestions ? ` placeholder="Type for suggestions..."` : '';
                const acTitle = hasSuggestions ? ` title="Arrow keys to navigate suggestions, Enter to select, Escape to close"` : '';
                // Escape value for use in HTML attribute (must escape quotes)
                const escapedValue = Explorer.escapeHtml(value).replace(/"/g, '&quot;');

                // Use textarea for long value attributes or values > 60 chars
                const useLongInput = LONG_VALUE_ATTRS.includes(key) || value.length > 60;

                if (useLongInput) {
                    const highlighted = highlightCommandSyntax(value);
                    return `
                    <div class="attr-row${hasSuggestions ? ' has-autocomplete' : ''}" data-attr="${Explorer.escapeHtml(key)}">
                        <span class="attr-name">${Explorer.escapeHtml(key)}</span>
                        <div class="attr-value-long-wrapper">
                            <textarea class="attr-value attr-value-long"
                                   onchange="Explorer.updateAttribute('${keyHtmlAttr}', this.value, this)"
                                   oninput="Explorer.syncHighlight(this)"
                                   spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off"
                                   ${inputEvents}${placeholder}${acTitle}>${Explorer.escapeHtml(value)}</textarea>
                            <pre class="attr-value-highlight" aria-hidden="true">${highlighted}</pre>
                        </div>
                        <button class="attr-copy" onclick="Explorer.copyAttributeValue('${keyHtmlAttr}')" title="Copy value"><i class="fa-regular fa-copy"></i></button>
                        <button class="attr-delete" onclick="Explorer.deleteAttribute('${keyHtmlAttr}')">&times;</button>
                    </div>
                `}

                return `
                <div class="attr-row${hasSuggestions ? ' has-autocomplete' : ''}" data-attr="${Explorer.escapeHtml(key)}">
                    <span class="attr-name">${Explorer.escapeHtml(key)}</span>
                    <input type="text" class="attr-value" value="${escapedValue}"
                           onchange="Explorer.updateAttribute('${keyHtmlAttr}', this.value, this)"
                           ${inputEvents}${placeholder}${acTitle} autocomplete="off">
                    <button class="attr-copy" onclick="Explorer.copyAttributeValue('${keyHtmlAttr}')" title="Copy value"><i class="fa-regular fa-copy"></i></button>
                    <button class="attr-delete" onclick="Explorer.deleteAttribute('${keyHtmlAttr}')">&times;</button>
                </div>
            `}).join('');

        // Attach docs popover hover listeners to attr-name spans
        container.querySelectorAll('.attr-name').forEach(function(nameEl) {
            var attrName = nameEl.textContent;
            var directive = lookupDirective(objectType, attrName);
            if (directive) {
                nameEl.classList.add('has-docs');

                nameEl.addEventListener('mouseenter', function() {
                    clearTimeout(docsPopoverHideTimer);
                    clearTimeout(docsPopoverShowTimer);
                    docsPopoverShowTimer = setTimeout(function() {
                        showDocsPopover(nameEl, directive, objectType);
                    }, 300);
                });

                nameEl.addEventListener('mouseleave', function() {
                    clearTimeout(docsPopoverShowTimer);
                    scheduleHidePopover();
                });
            }
        });

        // Auto-size textareas on initial render to fit all content
        // Use requestAnimationFrame to ensure DOM is fully rendered first
        requestAnimationFrame(() => {
            container.querySelectorAll('.attr-value-long').forEach(textarea => {
                textarea.style.height = 'auto';
                textarea.style.height = textarea.scrollHeight + 'px';
            });
        });
    }


    function filterCommaValueSuggestions(inputValue, allSuggestions, attrKey) {
        const isNotificationOption = constants.NOTIFICATION_OPTION_ATTRS.includes(attrKey);
        const parts = inputValue.split(',').map(p => p.trim());
        const currentPart = parts[parts.length - 1].toLowerCase();
        const existingValues = parts.slice(0, -1).map(p => p.trim().toLowerCase());

        const isAlreadySelected = (suggestion) => {
            if (isNotificationOption && suggestion.includes(' - ')) {
                const shortCode = suggestion.split(' - ')[0].toLowerCase();
                return existingValues.includes(shortCode);
            }
            return existingValues.includes(suggestion.toLowerCase());
        };

        const filtered = allSuggestions.filter(s =>
            s.toLowerCase().includes(currentPart) && !isAlreadySelected(s)
        );
        const remaining = allSuggestions.filter(s => !isAlreadySelected(s));

        return { filtered, remaining, currentPart, parts };
    }

    function showAttrAutocomplete(input, attrKey) {
        const allSuggestions = getAttributeSuggestions(attrKey, state.editedObject.object_type);
        const { filtered, remaining, currentPart, parts } = filterCommaValueSuggestions(input.value, allSuggestions, attrKey);

        // Remove existing dropdown
        const existingDropdown = document.querySelector('.attr-autocomplete');
        if (existingDropdown) {existingDropdown.remove();}

        if (filtered.length === 0 || (currentPart === '' && parts.length > 1 && parts[parts.length - 2] !== '')) {
            // Show all remaining options after comma
            if (remaining.length === 0) {return;}
            showAutocompleteDropdown(input, remaining, attrKey);
        } else if (filtered.length > 0) {
            showAutocompleteDropdown(input, filtered, attrKey);
        }
    }

    function showAutocompleteDropdown(input, suggestions, attrKey, options = {}) {
        const { container, dropdownId, selectHandler, highlightKey = 'highlightedIndex' } = options;
        const row = container || input.closest('.attr-row');
        if (!row) {return;}

        state.currentAutocompleteKey = attrKey;
        state[highlightKey] = -1;

        const dropdown = document.createElement('div');
        dropdown.className = 'attr-autocomplete';
        if (dropdownId) {dropdown.id = dropdownId;}
        dropdown.innerHTML = suggestions.slice(0, 20).map((s, i) => {
            const handler = selectHandler
                ? selectHandler(s)
                : `Explorer.selectAttrAutocomplete('${Explorer.escapeJs(attrKey)}', '${Explorer.escapeJs(s)}')`;
            // S-01: HTML-escape the handler for safe insertion into HTML attribute
            // JS-escaped strings like \" would break out of HTML attributes otherwise
            return `<div class="attr-autocomplete-item" data-index="${i}" data-value="${Explorer.escapeHtml(s)}" onmousedown="${Explorer.escapeHtml(handler)}">${Explorer.escapeHtml(s)}</div>`;
        }).join('');

        if (container) {
            dropdown.style.left = '0';
            dropdown.style.right = '0';
        } else {
            // Position dropdown to align with the input field
            const inputRect = input.getBoundingClientRect();
            const rowRect = row.getBoundingClientRect();
            dropdown.style.left = (inputRect.left - rowRect.left) + 'px';
            dropdown.style.width = inputRect.width + 'px';
            dropdown.style.right = 'auto';
        }

        row.appendChild(dropdown);
    }

    function hideAttrAutocomplete(event) {
        Explorer.hideAutocompleteDropdown('.attr-autocomplete', () => {
            state.currentAutocompleteKey = null;
            state.highlightedIndex = -1;
        });
    }

    function selectAttrAutocomplete(attrKey, value) {
        const row = document.querySelector(`[data-attr="${attrKey}"]`);
        if (!row) {return;}

        const input = row.querySelector('input');
        if (!input) {return;}

        // For notification options, extract just the short code (e.g., "d" from "d - Down")
        let insertValue = value;
        if (constants.NOTIFICATION_OPTION_ATTRS.includes(attrKey) && value.includes(' - ')) {
            insertValue = value.split(' - ')[0];
        }
        // For 'use' attribute, strip the alias suffix (e.g., "template-name (alias)" -> "template-name")
        if (attrKey === 'use' && value.includes(' (')) {
            insertValue = value.split(' (')[0];
        }

        // Get existing values and replace the current partial with selection
        const parts = input.value.split(',').map(p => p.trim());
        parts.pop(); // Remove the partial (could be empty after comma)
        parts.push(insertValue);

        input.value = parts.filter(p => p).join(',');
        updateAttribute(attrKey, input.value);

        // Hide dropdown
        const dropdown = document.querySelector('.attr-autocomplete');
        if (dropdown) {dropdown.remove();}

        // Keep focus and show more suggestions
        input.focus();
    }

    function handleAttrAutocompleteKey(event, attrKey) {
        Explorer.handleAutocompleteKeyNav(event, {
            selector: '.attr-autocomplete',
            getIndex: () => state.highlightedIndex,
            setIndex: (i) => { state.highlightedIndex = i; },
            onSelect: (value) => selectAttrAutocomplete(attrKey, value),
            onClose: () => { state.currentAutocompleteKey = null; }
        });
    }

    function updateAttribute(key, value, inputElement) {
        // Skip validation for identity/text fields
        const objIdentityFields = identityFields[state.editedObject.object_type] || [];
        const isIdentityField = objIdentityFields.includes(key);

        // Validate reference values (commands, groups, timeperiods, etc.)
        const suggestions = getAttributeSuggestions(key, state.editedObject.object_type);
        if (suggestions.length > 0 && value && !isIdentityField) {
            // Skip validation for notification options (they use short codes like d,r,f)
            if (!constants.NOTIFICATION_OPTION_ATTRS.includes(key)) {
                const values = Explorer.parseCommaValues(value);
                const isCommandAttr = ['check_command', 'event_handler', 'host_notification_commands', 'service_notification_commands'].includes(key);

                for (const v of values) {
                    let checkValue = isCommandAttr ? v.split('!')[0] : v;
                    checkValue = Explorer.stripPrefix(checkValue);
                    if (!suggestions.includes(checkValue)) {
                        showToast(`"${checkValue}" does not exist`, 'error');
                        // Revert the input to the old value
                        if (inputElement) {
                            inputElement.value = state.editedObject.attributes[key] || '';
                        }
                        return;
                    }
                }
            }
        }

        state.editedObject.attributes[key] = value;

        // Refresh info sections if relevant attributes changed
        Explorer.refreshRelatedSections(key, state.editedObject);

        // Check if this is the name field for this object type
        const nameField = Explorer.getNewObjectNameField(state.editedObject.object_type);
        if (key === nameField) {
            // Update display name
            state.editedObject.display_name = value || '(unnamed)';

            if (state.isNewObject) {
                // Update the name input at the top for new objects
                const nameInput = document.getElementById('newObjectNameInput');
                if (nameInput) {nameInput.value = value;}
            } else {
                // Update the name display for existing objects
                document.getElementById('centerCardName').textContent = state.editedObject.display_name;

                // Update tab label if this object has an open tab
                const objKey = Explorer.getObjectKey(state.editedObject);
                const objTab = state.openTabs.find(t => t.key === objKey);
                if (objTab) {
                    objTab.label = value || '(unnamed)';
                    Explorer.renderTabBar();
                }

                // Update the tree item name in the left panel
                const treeItem = document.querySelector(`.tree-item[data-index="${state.editedObject.global_index}"]`);
                if (treeItem) {
                    const nameSpan = treeItem.querySelector('.tree-item-name');
                    if (nameSpan) {nameSpan.textContent = state.editedObject.display_name;}
                }

                // Update the target pane item name in the right panel
                const targetItem = document.querySelector(`.target-object-item[data-index="${state.editedObject.global_index}"]`);
                if (targetItem) {
                    const nameSpan = targetItem.querySelector('.obj-name');
                    if (nameSpan) {nameSpan.textContent = state.editedObject.display_name;}
                }
            }
        }

        checkForChanges();
    }

    function copyAttributeValue(key) {
        const value = state.editedObject.attributes[key];
        if (value !== undefined) {
            copyToClipboard(value);
            showToast(`Copied ${key}`, 'success');
        }
    }

    function deleteAttribute(key) {
        delete state.editedObject.attributes[key];

        // Refresh info sections if relevant attributes deleted
        Explorer.refreshRelatedSections(key, state.editedObject);

        // Check if this is the name field for this object type
        const nameField = Explorer.getNewObjectNameField(state.editedObject.object_type);
        if (key === nameField) {
            state.editedObject.display_name = '(unnamed)';

            if (state.isNewObject) {
                const nameInput = document.getElementById('newObjectNameInput');
                if (nameInput) {nameInput.value = '';}
            } else {
                document.getElementById('centerCardName').textContent = state.editedObject.display_name;

                // Update the tree item name in the left panel
                const treeItem = document.querySelector(`.tree-item[data-index="${state.editedObject.global_index}"]`);
                if (treeItem) {
                    const nameSpan = treeItem.querySelector('.tree-item-name');
                    if (nameSpan) {nameSpan.textContent = state.editedObject.display_name;}
                }

                // Update the target pane item name in the right panel
                const targetItem = document.querySelector(`.target-object-item[data-index="${state.editedObject.global_index}"]`);
                if (targetItem) {
                    const nameSpan = targetItem.querySelector('.obj-name');
                    if (nameSpan) {nameSpan.textContent = state.editedObject.display_name;}
                }
            }
        }

        renderCenterAttributes();
        checkForChanges();
    }

    function showAddAttribute() {
        const objectType = state.editedObject.object_type;
        const availableAttrs = constants.NAGIOS_ATTRIBUTES[objectType] || [];
        const existingAttrs = Object.keys(state.editedObject.attributes);

        // Filter out attributes that already exist
        const unusedAttrs = availableAttrs.filter(a => !existingAttrs.includes(a));

        // Store for autocomplete
        state.addAttrNameSuggestions = unusedAttrs;

        Explorer.showDialog('Add Attribute', `
            <label>Name</label>
            <div class="u-relative" id="addAttrNameContainer">
                <input type="text" id="newAttrName" placeholder="Select or type attribute name" autocomplete="off"
                       oninput="Explorer.showAddAttrNameAutocomplete()"
                       onblur="Explorer.hideAddAttrNameAutocomplete()"
                       onfocus="Explorer.showAddAttrNameAutocomplete()"
                       onkeydown="Explorer.handleAddAttrNameAutocompleteKey(event)">
            </div>
            <label>Value</label>
            <div class="u-relative" id="addAttrValueContainer">
                <input type="text" id="newAttrValue" placeholder="value" autocomplete="off"
                       oninput="Explorer.showAddAttrAutocomplete()"
                       onblur="Explorer.hideAddAttrAutocomplete()"
                       onkeydown="Explorer.handleAddAttrAutocompleteKey(event)">
            </div>
        `, () => {
            const name = document.getElementById('newAttrName').value.trim();
            const value = document.getElementById('newAttrValue').value;
            if (name) {
                const objIdentityFields = identityFields[state.editedObject.object_type] || [];
                const isIdentityField = objIdentityFields.includes(name);

                // Validate reference values (commands, groups, timeperiods, etc.)
                const suggestions = getAttributeSuggestions(name, state.editedObject.object_type);
                if (suggestions.length > 0 && value && !isIdentityField) {
                    // Skip validation for notification options (they use short codes like d,r,f)
                    if (!constants.NOTIFICATION_OPTION_ATTRS.includes(name)) {
                        // This attribute references other objects - validate the values
                        const values = Explorer.parseCommaValues(value);
                        // For commands, strip arguments (e.g., "check_ping!100!200" -> "check_ping")
                        const isCommandAttr = ['check_command', 'event_handler', 'host_notification_commands', 'service_notification_commands'].includes(name);

                        for (const v of values) {
                            let checkValue = isCommandAttr ? v.split('!')[0] : v;
                            checkValue = Explorer.stripPrefix(checkValue);
                            if (!suggestions.includes(checkValue)) {
                                showToast(`"${checkValue}" does not exist`, 'error');
                                return;
                            }
                        }
                    }
                }
                state.editedObject.attributes[name] = value;

                // Refresh info sections if relevant attributes added
                Explorer.refreshRelatedSections(name, state.editedObject);

                renderCenterAttributes();
                checkForChanges();
                Explorer.closeDialog();
            }
        });
    }

    function showAddAttrNameAutocomplete() {
        const input = document.getElementById('newAttrName');
        const container = document.getElementById('addAttrNameContainer');
        if (!input || !container) {return;}

        const value = input.value.toLowerCase();
        const suggestions = state.addAttrNameSuggestions || [];
        const filtered = value ? suggestions.filter(s => s.toLowerCase().includes(value)) : suggestions;

        // Remove existing dropdown
        const existingDropdown = document.getElementById('addAttrNameDropdown');
        if (existingDropdown) {existingDropdown.remove();}

        if (filtered.length === 0) {return;}

        state.addAttrNameHighlightedIndex = -1;

        const dropdown = document.createElement('div');
        dropdown.id = 'addAttrNameDropdown';
        dropdown.className = 'attr-autocomplete';
        dropdown.style.left = '0';
        dropdown.style.right = '0';
        // S-01: Build handler and HTML-escape for safe attribute insertion
        dropdown.innerHTML = filtered.slice(0, 20).map((s, i) => {
            const handler = `Explorer.selectAddAttrNameAutocomplete('${Explorer.escapeJs(s)}')`;
            return `<div class="attr-autocomplete-item" data-index="${i}" data-value="${Explorer.escapeHtml(s)}" onmousedown="${Explorer.escapeHtml(handler)}">${Explorer.escapeHtml(s)}</div>`;
        }).join('');

        container.appendChild(dropdown);
    }

    function hideAddAttrNameAutocomplete() {
        Explorer.hideAutocompleteDropdown('#addAttrNameDropdown', () => {
            state.addAttrNameHighlightedIndex = -1;
        });
    }

    function selectAddAttrNameAutocomplete(value) {
        const input = document.getElementById('newAttrName');
        if (input) {
            input.value = value;
        }

        const dropdown = document.getElementById('addAttrNameDropdown');
        if (dropdown) {dropdown.remove();}

        // Focus on the value input
        const valueInput = document.getElementById('newAttrValue');
        if (valueInput) {valueInput.focus();}
    }

    function handleAddAttrNameAutocompleteKey(event) {
        Explorer.handleAutocompleteKeyNav(event, {
            selector: '#addAttrNameDropdown',
            getIndex: () => state.addAttrNameHighlightedIndex,
            setIndex: (i) => { state.addAttrNameHighlightedIndex = i; },
            onSelect: selectAddAttrNameAutocomplete
        });
    }

    function showAddAttrAutocomplete() {
        const attrName = document.getElementById('newAttrName').value.trim();
        const input = document.getElementById('newAttrValue');
        const container = document.getElementById('addAttrValueContainer');

        if (!attrName || !input || !container) {return;}

        const allSuggestions = getAttributeSuggestions(attrName, state.editedObject.object_type);
        if (allSuggestions.length === 0) {return;}

        const { filtered, remaining } = filterCommaValueSuggestions(input.value, allSuggestions, attrName);

        // Remove existing dropdown
        const existingDropdown = document.getElementById('addAttrDropdown');
        if (existingDropdown) {existingDropdown.remove();}

        const suggestions = filtered.length > 0 ? filtered : remaining;
        if (suggestions.length === 0) {return;}

        showAutocompleteDropdown(input, suggestions, attrName, {
            container,
            dropdownId: 'addAttrDropdown',
            selectHandler: (s) => `Explorer.selectAddAttrAutocomplete('${Explorer.escapeJs(s)}')`,
            highlightKey: 'addAttrHighlightedIndex'
        });
    }

    function hideAddAttrAutocomplete() {
        Explorer.hideAutocompleteDropdown('#addAttrDropdown', () => {
            state.addAttrHighlightedIndex = -1;
        });
    }

    function selectAddAttrAutocomplete(value) {
        const input = document.getElementById('newAttrValue');
        const attrNameInput = document.getElementById('newAttrName');
        if (!input) {return;}

        // For notification options, extract just the short code (e.g., "d" from "d - Down")
        let insertValue = value;
        const attrName = attrNameInput ? attrNameInput.value.trim() : '';
        if (constants.NOTIFICATION_OPTION_ATTRS.includes(attrName) && value.includes(' - ')) {
            insertValue = value.split(' - ')[0];
        }
        // For 'use' attribute, strip the alias suffix (e.g., "template-name (alias)" -> "template-name")
        if (attrName === 'use' && value.includes(' (')) {
            insertValue = value.split(' (')[0];
        }

        const parts = input.value.split(',').map(p => p.trim());
        parts.pop(); // Remove the partial (could be empty after comma)
        parts.push(insertValue);

        input.value = parts.filter(p => p).join(',');

        const dropdown = document.getElementById('addAttrDropdown');
        if (dropdown) {dropdown.remove();}

        input.focus();
    }

    function handleAddAttrAutocompleteKey(event) {
        Explorer.handleAutocompleteKeyNav(event, {
            selector: '#addAttrDropdown',
            getIndex: () => state.addAttrHighlightedIndex,
            setIndex: (i) => { state.addAttrHighlightedIndex = i; },
            onSelect: selectAddAttrAutocomplete
        });
    }

    function checkForChanges() {
        // Handle new objects differently
        if (state.isNewObject) {
            Explorer.stageNewObjectChanges();
            return;
        }

        const hasChanges = JSON.stringify(state.editedObject.attributes) !== JSON.stringify(state.originalAttributes);

        if (hasChanges) {
            // Auto-stage changes
            stageCurrentChanges();
        } else {
            // If reverted to original, remove from pending
            state.pendingEdits.delete(state.editedObject.global_index);
            // Centralized refresh ensures all UI components stay in sync
            Explorer.refreshAfterObjectChange();
        }
    }

    function stageCurrentChanges() {
        const globalIndex = state.editedObject.global_index;

        // C-05: Validate required fields (warning only - allow staging for template inheritance)
        const validation = validateRequiredFields(
            state.editedObject.object_type,
            state.editedObject.attributes
        );
        if (!validation.valid) {
            // Check if object uses a template (which may provide the missing fields)
            const usesTemplate = state.editedObject.attributes.use && state.editedObject.attributes.use.trim() !== '';
            if (usesTemplate) {
                // Just show a subtle warning - template may provide the fields
                console.warn(`Object may be missing required fields (may be inherited from template): ${validation.errors.join(', ')}`);
            } else {
                // Show warning toast for non-template objects
                showToast(`Warning: ${validation.errors[0]}`, 'warning');
            }
        }

        // Get the original state (either from state.pendingEdits or current state.originalAttributes)
        const existingEdit = state.pendingEdits.get(globalIndex);
        const originalState = existingEdit ? existingEdit.original : {...state.originalAttributes};

        // Store the pending edit
        state.pendingEdits.set(globalIndex, {
            original: originalState,
            edited: {...state.editedObject.attributes},
            object: {
                source_file: state.editedObject.source_file,
                line_number: state.editedObject.line_number,
                object_type: state.editedObject.object_type,
                display_name: state.editedObject.display_name,
                global_index: globalIndex
            }
        });

        // Persist to localStorage
        Explorer.saveStagedChanges();

        // Update state.allObjects locally (for UI display)
        const idx = state.allObjects.findIndex(o => o.global_index === globalIndex);
        if (idx >= 0) {
            state.allObjects[idx].attributes = {...state.editedObject.attributes};
        }

        // Centralized refresh ensures all UI components stay in sync
        Explorer.refreshAfterObjectChange();

        // Phase 2: Refresh relationship sections (References, Inheritance, Members)
        // NOTE: These refresh AFTER refreshAfterObjectChange() because:
        // 1. refreshAfterObjectChange() → syncCenterPaneAfterUndo() → renderCenterAttributes()
        //    updates the attributes display in the center pane
        // 2. loadImpactAndRelationships analyzes relationships based on the newly staged
        //    attributes (e.g., if attribute "use" changed, inheritance tree changes)
        // 3. Order matters: attribute display must update first, then relationship analysis
        //    reads from state.editedObject containing staged values
        Explorer.loadImpactAndRelationships(state.editedObject);
    }

    function toggleSection(section) {
        const titleEl = document.querySelector(`#${section}Section .section-title`);
        const contentEl = document.getElementById(`${section}Content`);
        const centerPane = document.querySelector('.center-pane');

        // Remember where the title is on screen before toggle
        const titleRect = titleEl.getBoundingClientRect();
        const centerRect = centerPane ? centerPane.getBoundingClientRect() : null;
        const titleViewportTop = titleRect.top - (centerRect ? centerRect.top : 0);

        titleEl.classList.toggle('collapsed');
        contentEl.classList.toggle('collapsed');
        // Clear inline style so CSS can control display
        contentEl.style.display = '';

        // Restore the title to the same position on screen
        if (centerPane) {
            const newTitleRect = titleEl.getBoundingClientRect();
            const newTitleViewportTop = newTitleRect.top - centerRect.top;
            const diff = newTitleViewportTop - titleViewportTop;
            if (Math.abs(diff) > 1) {
                centerPane.scrollTop += diff;
            }
        }

        // Persist section expansion state
        saveDetailSectionState();
    }

    function saveDetailSectionState() {
        try {
            const sectionState = {};
            ['inheritance', 'dependencies', 'dependents', 'members'].forEach(name => {
                const titleEl = document.querySelector(`#${name}Section .section-title`);
                if (titleEl) {
                    sectionState[name] = !titleEl.classList.contains('collapsed');
                }
            });
            localStorage.setItem('detailSectionState', JSON.stringify(sectionState));
        } catch (e) {
            // Ignore localStorage errors
        }
    }

    function restoreDetailSectionState() {
        try {
            const saved = localStorage.getItem('detailSectionState');
            if (!saved) {return;}
            const sectionState = JSON.parse(saved);
            for (const [name, expanded] of Object.entries(sectionState)) {
                const titleEl = document.querySelector(`#${name}Section .section-title`);
                const contentEl = document.getElementById(`${name}Content`);
                if (titleEl && contentEl) {
                    if (expanded) {
                        titleEl.classList.remove('collapsed');
                        contentEl.classList.remove('collapsed');
                        // Clear inline style so CSS can control display
                        contentEl.style.display = '';
                    } else {
                        titleEl.classList.add('collapsed');
                        contentEl.classList.add('collapsed');
                    }
                }
            }
        } catch (e) {
            // Ignore localStorage errors
        }
    }

    // =========================================================================
    // Inheritance Functions
    // =========================================================================

    /**
     * Fetch inheritance chain for an object by stable key.
     * Uses cache to avoid repeated API calls for same object.
     * @param {string} stableKey - Base64-encoded "file|type|name" key
     * @returns {Promise<Object>} - {chain, inherited, errors}
     */
    async function fetchInheritance(stableKey) {
        // Check cache first
        if (state.inheritanceCache.has(stableKey)) {
            return state.inheritanceCache.get(stableKey);
        }

        try {
            const result = await ApiClient.get(`/api/templates/inheritance/${encodeURIComponent(stableKey)}`, {silent: true});
            if (result.success) {
                state.inheritanceCache.set(stableKey, result.data);
                return result.data;
            } 
                return {chain: [], inherited: {}, errors: ['Unable to load inheritance data']};
            
        } catch (error) {
            return {chain: [], inherited: {}, errors: ['Unable to load inheritance data']};
        }
    }

    /**
     * Invalidate cached inheritance data for an object.
     * Call after editing object or templates it depends on.
     * @param {string} stableKey - Base64-encoded "file|type|name" key (optional)
     */
    function invalidateInheritanceCache(stableKey) {
        if (stableKey) {
            state.inheritanceCache.delete(stableKey);
        } else {
            state.inheritanceCache.clear();
        }
    }

    /**
     * Build a stable key for an object (base64-encoded).
     * @param {Object} obj - NagiosObject
     * @returns {string} - Base64-encoded "file|type|name" key
     */
    function buildStableKey(obj) {
        const objName = obj.display_name ?? Explorer.getEffectiveName(obj);
        return btoa(`${obj.source_file}|${obj.object_type}|${objName}`);
    }

    /**
     * Load and render inheritance section for an object.
     * Fetches data from API, builds stable key, renders in editor pane.
     * @param {Object} obj - NagiosObject to load inheritance for
     */
    async function loadInheritanceSection(obj) {
        const stableKey = buildStableKey(obj);
        const data = await fetchInheritance(stableKey);
        renderInheritanceSection(data, obj);
    }

    /**
     * Render inheritance section in editor pane.
     * Shows template chain breadcrumb and inherited attributes table.
     * @param {Object} data - {chain, inherited, errors} from API
     * @param {Object} obj - Current object being edited
     */
    function renderInheritanceSection(data, obj) {
        const content = document.getElementById('inheritanceContent');
        if (!content) {return;}

        // Render errors if any
        if (data.errors && data.errors.length > 0) {
            content.innerHTML = `<div class="inheritance-error"><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(data.errors[0])}</div>`;
            return;
        }

        // Check if object has no template usage
        if (!data.chain || data.chain.length === 0) {
            content.innerHTML = '<div class="empty-state-small">No template inheritance</div>';
            return;
        }

        let html = '';

        // Render template chain breadcrumb
        if (data.chain && data.chain.length > 0) {
            html += '<div class="template-breadcrumb">';
            data.chain.forEach((tmpl, idx) => {
                html += `<span class="template-name">${escapeHtml(tmpl.name)}</span>`;
                if (idx < data.chain.length - 1) {
                    html += ' <i class="fa-solid fa-chevron-right"></i> ';
                }
            });
            const displayName = obj.display_name || obj.get_name?.() || obj.attributes?.name || 'this object';
            html += ` <i class="fa-solid fa-chevron-right"></i> <span class="template-name this-object">${escapeHtml(displayName)}</span>`;
            html += '</div>';
        }

        // Render inherited attributes
        if (data.inherited && Object.keys(data.inherited).length > 0) {
            html += '<div class="inherited-attrs-table">';
            for (const [key, rawValue] of Object.entries(data.inherited)) {
                // Skip control directives
                if (['use', 'name', 'register'].includes(key)) {continue;}

                // Handle both old string format and new {value, source} format
                const displayValue = (typeof rawValue === 'object' && rawValue !== null) ? rawValue.value : rawValue;

                // Check if object overrides this attribute
                const isOverridden = obj.attributes && obj.attributes.hasOwnProperty(key);

                html += `<div class="attr-row ${isOverridden ? 'overridden' : ''}">`;
                html += `<div class="attr-key inherited-attr">${escapeHtml(key)}</div>`;
                html += `<div class="attr-value inherited-attr">${escapeHtml(displayValue)}</div>`;
                if (isOverridden) {
                    html += `<div class="attr-override-badge"><i class="fa-solid fa-circle-check"></i> Overridden</div>`;
                }
                html += '</div>';
            }
            html += '</div>';
        } else {
            html += '<div class="empty-state-small">No inherited attributes</div>';
        }

        content.innerHTML = html;
    }

    /**
     * Get all templates for a specific object type.
     * Filters by register=0 and matches object type for type-safe autocomplete.
     *
     * D-04: Nagios Template Convention:
     * - In Nagios, objects with "register 0" are templates (not monitored)
     * - Templates must have a "name" attribute (for inheritance reference)
     * - Regular objects have "register 1" (default, often omitted)
     * - Templates are referenced via the "use" directive in other objects
     * - An object can inherit from multiple templates (comma-separated)
     * - Inheritance is processed in order; later templates override earlier ones
     *
     * @param {string} objectType - Object type (host, service, etc.)
     * @returns {Array<string>} - Template names with optional alias suffix
     */
    function getTemplatesForType(objectType) {
        // C-06: Build a set of objects staged for deletion
        // stagedObjectDeletions is a Set of global_index values
        const stagedDeletionIndices = state.stagedObjectDeletions || new Set();
        const deletedKeys = new Set();
        for (const idx of stagedDeletionIndices) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (obj) {
                deletedKeys.add(`${obj.source_file}:${obj.line_number}`);
            }
        }

        // Get all templates for the given object type (register=0 is the Nagios template marker)
        // C-06: Filter out templates that are staged for deletion
        const templates = state.allObjects
            .filter(o => {
                if (o.object_type !== objectType || o.attributes.register !== '0') {return false;}
                // Check if this template is staged for deletion
                const objKey = `${o.source_file}:${o.line_number}`;
                if (deletedKeys.has(objKey)) {return false;}
                return true;
            })
            .map(o => {
                const name = o.attributes.name;
                const alias = o.attributes.alias;
                // Show "name (alias)" if alias exists and differs from name
                if (alias && alias !== name) {
                    return `${name} (${alias})`;
                }
                return name;
            })
            .filter(name => name)
            .sort();
        return [...new Set(templates)];
    }

    // Export all functions to Explorer namespace
    Explorer.showCenterPaneObject = showCenterPaneObject;
    Explorer.hideCenterPaneObject = hideCenterPaneObject;
    Explorer.syncCenterPaneAfterUndo = syncCenterPaneAfterUndo;
    Explorer.showCenterPaneMultiple = showCenterPaneMultiple;
    Explorer.getAttributeSuggestions = getAttributeSuggestions;
    Explorer.renderCenterAttributes = renderCenterAttributes;
    Explorer.filterCommaValueSuggestions = filterCommaValueSuggestions;
    Explorer.showAttrAutocomplete = showAttrAutocomplete;
    Explorer.showAutocompleteDropdown = showAutocompleteDropdown;
    Explorer.hideAttrAutocomplete = hideAttrAutocomplete;
    Explorer.selectAttrAutocomplete = selectAttrAutocomplete;
    Explorer.handleAttrAutocompleteKey = handleAttrAutocompleteKey;
    Explorer.updateAttribute = updateAttribute;
    Explorer.copyAttributeValue = copyAttributeValue;
    Explorer.deleteAttribute = deleteAttribute;
    Explorer.showAddAttribute = showAddAttribute;
    Explorer.showAddAttrNameAutocomplete = showAddAttrNameAutocomplete;
    Explorer.hideAddAttrNameAutocomplete = hideAddAttrNameAutocomplete;
    Explorer.selectAddAttrNameAutocomplete = selectAddAttrNameAutocomplete;
    Explorer.handleAddAttrNameAutocompleteKey = handleAddAttrNameAutocompleteKey;
    Explorer.showAddAttrAutocomplete = showAddAttrAutocomplete;
    Explorer.hideAddAttrAutocomplete = hideAddAttrAutocomplete;
    Explorer.selectAddAttrAutocomplete = selectAddAttrAutocomplete;
    Explorer.handleAddAttrAutocompleteKey = handleAddAttrAutocompleteKey;
    Explorer.checkForChanges = checkForChanges;
    Explorer.stageCurrentChanges = stageCurrentChanges;
    Explorer.validateRequiredFields = validateRequiredFields;  // C-05: Export for use in dialogs.js
    Explorer.toggleSection = toggleSection;
    Explorer.saveDetailSectionState = saveDetailSectionState;
    Explorer.restoreDetailSectionState = restoreDetailSectionState;

    // Inheritance functions
    Explorer.fetchInheritance = fetchInheritance;
    Explorer.invalidateInheritanceCache = invalidateInheritanceCache;
    Explorer.buildStableKey = buildStableKey;
    Explorer.loadInheritanceSection = loadInheritanceSection;
    Explorer.renderInheritanceSection = renderInheritanceSection;
    Explorer.getTemplatesForType = getTemplatesForType;

})(Explorer);
