/**
 * Impact Section Module
 *
 * Provides the unified Impact & Relationships section in the center pane.
 * Consolidates Inheritance, Dependencies, Dependents, and Members into one
 * collapsible section with question-oriented subsections.
 */
(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;

    // Type labels for display
    const typeLabels = constants.typeLabels;

    // Helper aliases for cleaner code
    function getEffectiveName(obj) {
        return Explorer.getEffectiveName(obj);
    }

    function getEffectiveAttributes(obj) {
        return Explorer.getEffectiveAttributes(obj);
    }

    function getStagedDisplayName(obj) {
        return Explorer.getStagedDisplayName(obj);
    }

    function isObjectTemplate(obj) {
        return Explorer.isObjectTemplate(obj);
    }

    /**
     * Map parent hosts tree from API response to local objects
     */
    function mapParentHostsTree(node, objectsByIndex) {
        if (node.circular) return { name: node.name, circular: true };
        if (node.missing) return { name: node.name, missing: true };
        return {
            name: node.name,
            file: node.file ? node.file.split('/').pop() : '',
            obj: objectsByIndex.get(node.global_index) || null,
            parents: (node.parents || []).map(p => mapParentHostsTree(p, objectsByIndex)),
        };
    }

    // =============================================================================
    // MAIN ENTRY POINT
    // =============================================================================

    /**
     * Load and render the unified Impact & Relationships section.
     * Consolidates Inheritance, Dependencies, Dependents, and Members into one section
     * with question-oriented subsections.
     */
    async function loadImpactAndRelationships(obj) {
        const container = document.getElementById('impactContent');
        const section = document.getElementById('impactSection');

        if (!container || !section) return;

        section.style.display = 'block';
        container.innerHTML = '<div class="loading">Loading relationships...</div>';

        // Gather inheritance data locally (still needed for template chains)
        const inheritanceData = await gatherInheritanceData(obj);

        // Fetch references from backend
        let referencesData = { outgoing: [], incoming: [] };
        let membersData = { members: [], memberOf: [] };

        if (!state.isNewObject && obj.global_index != null) {
            try {
                const result = await ApiClient.get(`/api/object-references/${obj.global_index}`);
                if (result.success) {
                    const data = result.data;
                    const objectsByIndex = new Map();
                    state.allObjects.forEach(o => objectsByIndex.set(o.global_index, o));

                    referencesData.outgoing = (data.outgoing || []).map(r => ({
                        field: r.field,
                        object: objectsByIndex.get(r.global_index),
                        isDependencyRule: r.is_dependency_rule || false,
                        isEscalationRule: r.is_escalation_rule || false,
                        isServiceBinding: r.is_service_binding || false,
                        viaGroup: r.via_group || null,
                    })).filter(r => r.object);

                    referencesData.incoming = (data.incoming || []).map(r => ({
                        field: r.field,
                        object: objectsByIndex.get(r.global_index),
                        isDependencyRule: r.is_dependency_rule || false,
                        isEscalationRule: r.is_escalation_rule || false,
                        isServiceBinding: r.is_service_binding || false,
                        viaGroup: r.via_group || null,
                    })).filter(r => r.object);

                    membersData.members = (data.members || []).map(r => ({
                        object: objectsByIndex.get(r.global_index),
                        via: r.via,
                    })).filter(r => r.object);

                    membersData.memberOf = (data.member_of || []).map(r => ({
                        object: objectsByIndex.get(r.global_index),
                        via: r.via,
                    })).filter(r => r.object);

                    // Parent hosts tree from API
                    if (data.parent_hosts) {
                        inheritanceData.parentHosts = mapParentHostsTree(data.parent_hosts, objectsByIndex);
                    }
                }
            } catch (error) {
                console.error('Failed to load object references:', error);
            }
        }

        renderImpactSection(obj, inheritanceData, referencesData, membersData);
    }

    // =============================================================================
    // DATA GATHERING
    // =============================================================================

    /**
     * Gather inheritance/ancestry data (templates + parent hosts)
     */
    async function gatherInheritanceData(obj) {
        const result = {
            templateChain: null,
            parentHosts: null,
            resolvedAttrs: null
        };

        const useAttr = obj.attributes.use;
        if (useAttr) {
            const templateNames = Explorer.parseCommaValues(useAttr);
            result.templateChain = Explorer.buildLocalInheritanceChain(obj, templateNames);
        }

        if (!state.isNewObject && useAttr) {
            try {
                const stableKey = Explorer.buildStableKey(obj);
                const inheritData = await Explorer.fetchInheritance(stableKey);
                if (inheritData && inheritData.inherited) {
                    result.resolvedAttrs = inheritData.inherited;
                }
            } catch (error) {
                console.error('Error loading resolved attributes:', error);
            }
        }

        return result;
    }

    // =============================================================================
    // RENDERING
    // =============================================================================

    /**
     * Render the unified impact section
     */
    function renderImpactSection(obj, inheritanceData, referencesData, membersData) {
        const container = document.getElementById('impactContent');
        const section = document.getElementById('impactSection');

        const { templateChain, parentHosts, resolvedAttrs } = inheritanceData;
        const { outgoing, incoming } = referencesData;
        const { members, memberOf } = membersData;

        // Check if there's any data to show
        const hasTemplateChain = templateChain && templateChain.parents && templateChain.parents.length > 0;
        const hasParentHosts = parentHosts && parentHosts.parents && parentHosts.parents.length > 0;
        const hasResolvedAttrs = resolvedAttrs && Object.keys(resolvedAttrs).length > 0;
        const hasIncoming = incoming.length > 0;
        const hasOutgoing = outgoing.length > 0;
        const hasMembers = members.length > 0;
        const hasMemberOf = memberOf.length > 0;

        if (!hasTemplateChain && !hasParentHosts && !hasResolvedAttrs && !hasIncoming && !hasOutgoing && !hasMembers && !hasMemberOf) {
            section.style.display = 'none';
            container.innerHTML = '';
            return;
        }

        let html = '';

        // 1. Configuration Ancestry (Templates + Parent Hosts + Resolved Attributes)
        if (hasTemplateChain || hasParentHosts || hasResolvedAttrs) {
            html += renderAncestrySubsection(obj, templateChain, parentHosts, resolvedAttrs);
        }

        // 2. "If Deleted/Renamed" (incoming references)
        if (hasIncoming) {
            html += renderIncomingSubsection(incoming);
        }

        // 3. "This Object Requires" (outgoing references)
        if (hasOutgoing) {
            html += renderOutgoingSubsection(outgoing);
        }

        // 4. Group Membership
        if (hasMembers || hasMemberOf) {
            html += renderMembershipSubsection(obj, members, memberOf);
        }

        container.innerHTML = html;

        // Add click handlers for subsection toggles
        container.querySelectorAll('.impact-subsection-header').forEach(header => {
            header.addEventListener('click', () => {
                const subsection = header.closest('.impact-subsection');
                subsection.classList.toggle('expanded');
            });
        });
    }

    /**
     * Render the Configuration Ancestry subsection
     */
    function renderAncestrySubsection(obj, templateChain, parentHosts, resolvedAttrs) {
        const hasTemplates = templateChain && templateChain.parents && templateChain.parents.length > 0;
        const hasParents = parentHosts && parentHosts.parents && parentHosts.parents.length > 0;
        const hasResolved = resolvedAttrs && Object.keys(resolvedAttrs).length > 0;

        let content = '';

        // Template inheritance chain
        if (hasTemplates) {
            content += '<div class="ancestry-label">Templates</div>';
            content += renderAncestryChain(templateChain, obj.object_type);
        }

        // Parent hosts chain (for hosts only)
        if (hasParents) {
            content += '<div class="ancestry-label">Network Parents</div>';
            content += renderParentHostsChain(parentHosts);
        }

        // Resolved attributes table
        if (hasResolved) {
            content += renderResolvedAttrsTable(resolvedAttrs, obj);
        }

        return `
            <div class="impact-subsection">
                <div class="impact-subsection-header">
                    <div class="impact-subsection-title">
                        <i class="fa-solid fa-sitemap"></i>
                        <span>Configuration Ancestry</span>
                    </div>
                    <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
                </div>
                <div class="impact-subsection-content">${content}</div>
            </div>
        `;
    }

    /**
     * Render a template ancestry chain as horizontal flow
     */
    function renderAncestryChain(chain, objectType) {
        function flattenChain(node, path = []) {
            path.push(node);
            const parents = node.parents || [];
            if (parents.length > 0) {
                flattenChain(parents[0], path);
            }
            return path;
        }

        const flat = flattenChain(chain);
        flat.reverse();

        let html = '<div class="ancestry-chain">';
        flat.forEach((node, idx) => {
            const isCurrent = idx === flat.length - 1;
            const isMissing = !!node.error;
            const displayName = node.name;

            let itemClass = 'ancestry-chain-item';
            if (isCurrent) itemClass += ' current';
            if (isMissing) itemClass += ' missing';

            const clickHandler = isMissing ? '' : `onclick="Explorer.selectObjectByName('${Explorer.escapeJs(node.name)}')"`;

            html += `<span class="${itemClass}" ${clickHandler} title="${Explorer.escapeHtml(displayName)}">`;
            html += `<span class="ref-type-badge type-${objectType}">${objectType}</span>`;
            html += `<span>${Explorer.escapeHtml(displayName)}</span>`;
            if (isMissing) html += `<i class="fa-solid fa-xmark" style="color: var(--nbe-dark-accent-danger); margin-left: 4px;"></i>`;
            html += '</span>';

            if (idx < flat.length - 1) {
                html += '<span class="ancestry-chain-separator"><i class="fa-solid fa-arrow-right"></i></span>';
            }
        });
        html += '</div>';
        return html;
    }

    /**
     * Render parent hosts chain
     */
    function renderParentHostsChain(tree) {
        function collectParents(node, list = []) {
            if (node.parents && node.parents.length > 0) {
                node.parents.forEach(p => collectParents(p, list));
            }
            list.push(node);
            return list;
        }

        const flat = collectParents(tree);

        let html = '<div class="ancestry-chain">';
        flat.forEach((node, idx) => {
            const isCurrent = idx === flat.length - 1;
            const isMissing = node.missing;
            const isCircular = node.circular;

            let itemClass = 'ancestry-chain-item';
            if (isCurrent) itemClass += ' current';
            if (isMissing || isCircular) itemClass += ' missing';

            const clickHandler = (isMissing || isCircular || !node.obj)
                ? ''
                : `onclick="Explorer.navigateToObjectByIndex(${node.obj.global_index})"`;

            html += `<span class="${itemClass}" ${clickHandler} title="${Explorer.escapeHtml(node.name)}">`;
            html += '<span class="ref-type-badge type-host">host</span>';
            html += `<span>${Explorer.escapeHtml(node.name)}</span>`;
            if (isMissing) html += '<i class="fa-solid fa-xmark" style="color: var(--nbe-dark-accent-danger); margin-left: 4px;"></i>';
            if (isCircular) html += '<i class="fa-solid fa-rotate" style="color: var(--nbe-dark-accent-warning); margin-left: 4px;" title="Circular reference"></i>';
            html += '</span>';

            if (idx < flat.length - 1) {
                html += '<span class="ancestry-chain-separator"><i class="fa-solid fa-arrow-right"></i></span>';
            }
        });
        html += '</div>';
        return html;
    }

    /**
     * Render the "If Deleted/Renamed" subsection (incoming references)
     */
    function renderIncomingSubsection(incoming) {
        const count = incoming.length;

        const grouped = {};
        incoming.forEach(ref => {
            const type = ref.object.object_type;
            if (!grouped[type]) grouped[type] = [];
            grouped[type].push(ref);
        });

        let content = `
            <div class="impact-summary warning">
                <span class="impact-summary-icon"><i class="fa-solid fa-triangle-exclamation"></i></span>
                <span>${count} object${count !== 1 ? 's' : ''} reference${count === 1 ? 's' : ''} this and would need updates</span>
            </div>
        `;

        content += renderGroupedReferences(grouped);

        return `
            <div class="impact-subsection">
                <div class="impact-subsection-header">
                    <div class="impact-subsection-title">
                        <i class="fa-solid fa-link-slash"></i>
                        <span>If Deleted/Renamed</span>
                        <span class="impact-subsection-count warning">${count}</span>
                    </div>
                    <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
                </div>
                <div class="impact-subsection-content">${content}</div>
            </div>
        `;
    }

    /**
     * Render the "This Object Requires" subsection (outgoing references)
     */
    function renderOutgoingSubsection(outgoing) {
        const count = outgoing.length;

        const grouped = {};
        outgoing.forEach(ref => {
            const type = ref.object.object_type;
            if (!grouped[type]) grouped[type] = [];
            grouped[type].push(ref);
        });

        let content = `
            <div class="impact-summary info">
                <span class="impact-summary-icon"><i class="fa-solid fa-link"></i></span>
                <span>${count} object${count !== 1 ? 's' : ''} must exist for this to work</span>
            </div>
        `;

        content += renderGroupedReferences(grouped);

        return `
            <div class="impact-subsection">
                <div class="impact-subsection-header">
                    <div class="impact-subsection-title">
                        <i class="fa-solid fa-arrow-right-to-bracket"></i>
                        <span>This Object Requires</span>
                        <span class="impact-subsection-count">${count}</span>
                    </div>
                    <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
                </div>
                <div class="impact-subsection-content">${content}</div>
            </div>
        `;
    }

    /**
     * Render grouped references (used by both incoming and outgoing)
     */
    function renderGroupedReferences(grouped) {
        let html = '';

        for (const [type, refs] of Object.entries(grouped)) {
            const typeLabel = typeLabels[type] || type;
            html += `<div class="ref-type-group"><div class="ref-type-header">${typeLabel} (${refs.length})</div>`;
            html += '<div class="ref-type-list">';

            refs.forEach(ref => {
                const displayName = getStagedDisplayName(ref.object);
                const isDependencyRule = ref.isDependencyRule;
                const isEscalationRule = ref.isEscalationRule;
                const isRuleItem = isDependencyRule || isEscalationRule;

                html += `<div class="ref-item ${isRuleItem ? 'dep-rule-item' : ''}" onclick="Explorer.navigateToObjectByIndex(${ref.object.global_index})">`;

                if (isDependencyRule) {
                    html += '<span class="dep-rule-badge">rule</span>';
                } else if (isEscalationRule) {
                    html += '<span class="dep-rule-badge esc-badge">esc</span>';
                }

                html += `<span class="ref-type-badge type-${ref.object.object_type}">${ref.object.object_type}</span>`;
                html += `<span class="ref-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>`;

                if (isDependencyRule) {
                    const criteria = formatFailureCriteriaReadable(ref.object);
                    if (criteria) {
                        html += `<span class="ref-field">${criteria}</span>`;
                    }
                } else if (isEscalationRule) {
                    const info = formatEscalationInfoReadable(ref.object);
                    if (info) {
                        html += `<span class="ref-field">${info}</span>`;
                    }
                } else if (ref.field && ref.field !== 'use' && ref.field !== 'members') {
                    html += `<span class="ref-attr">${ref.field}</span>`;
                }

                html += '</div>';

                // Add readable criteria details for dependency rules
                if (isDependencyRule) {
                    const details = formatFailureCriteriaDetails(ref.object);
                    if (details) {
                        html += `<div class="dep-rule-details">${details}</div>`;
                    }
                } else if (isEscalationRule) {
                    const details = formatEscalationDetails(ref.object);
                    if (details) {
                        html += `<div class="dep-rule-details">${details}</div>`;
                    }
                }
            });

            html += '</div></div>';
        }

        return html;
    }

    // =============================================================================
    // FORMAT HELPERS (Readable versions for Impact section)
    // =============================================================================

    /**
     * Format failure criteria as human-readable compact string
     */
    function formatFailureCriteriaReadable(depObj) {
        const attrs = getEffectiveAttributes(depObj);
        const parts = [];

        const criteriaMap = {
            'o': 'ok/up',
            'w': 'warning',
            'c': 'critical',
            'u': 'unknown',
            'd': 'down',
            'p': 'pending',
            'n': 'none'
        };

        function expandCriteria(criteria) {
            return criteria.split(',').map(c => criteriaMap[c.trim()] || c.trim()).join(', ');
        }

        if (attrs.execution_failure_criteria && attrs.execution_failure_criteria !== 'n') {
            parts.push(`skip: ${expandCriteria(attrs.execution_failure_criteria)}`);
        }
        if (attrs.notification_failure_criteria && attrs.notification_failure_criteria !== 'n') {
            parts.push(`suppress: ${expandCriteria(attrs.notification_failure_criteria)}`);
        }

        return parts.length > 0 ? `(${parts.join(' | ')})` : '';
    }

    /**
     * Format failure criteria as detailed explanation
     */
    function formatFailureCriteriaDetails(depObj) {
        const attrs = getEffectiveAttributes(depObj);
        let html = '';

        const criteriaMap = {
            'o': 'ok/up',
            'w': 'warning',
            'c': 'critical',
            'u': 'unknown',
            'd': 'down',
            'p': 'pending',
            'n': 'none'
        };

        function expandCriteria(criteria) {
            return criteria.split(',').map(c => criteriaMap[c.trim()] || c.trim()).join(', ');
        }

        if (attrs.execution_failure_criteria && attrs.execution_failure_criteria !== 'n') {
            html += `<div class="dep-rule-detail"><i class="fa-solid fa-ban"></i> Skip checks when master is: ${expandCriteria(attrs.execution_failure_criteria)}</div>`;
        }
        if (attrs.notification_failure_criteria && attrs.notification_failure_criteria !== 'n') {
            html += `<div class="dep-rule-detail"><i class="fa-solid fa-bell-slash"></i> Suppress notifications when master is: ${expandCriteria(attrs.notification_failure_criteria)}</div>`;
        }
        if (attrs.dependency_period) {
            html += `<div class="dep-rule-detail"><i class="fa-solid fa-clock"></i> Active during: ${Explorer.escapeHtml(attrs.dependency_period)}</div>`;
        }

        return html;
    }

    /**
     * Format escalation info as readable summary
     */
    function formatEscalationInfoReadable(escObj) {
        const attrs = getEffectiveAttributes(escObj);
        const parts = [];

        const first = attrs.first_notification;
        const last = attrs.last_notification;
        const interval = attrs.notification_interval;

        if (first || last) {
            if (first && last && last !== '0') {
                parts.push(`levels ${first}-${last}`);
            } else if (first) {
                parts.push(`from level ${first}+`);
            }
        }

        if (interval && interval !== '0') {
            parts.push(`every ${interval}m`);
        }

        return parts.length > 0 ? `(${parts.join(', ')})` : '';
    }

    /**
     * Format escalation as detailed explanation
     */
    function formatEscalationDetails(escObj) {
        const attrs = getEffectiveAttributes(escObj);
        let html = '';

        const first = attrs.first_notification;
        const last = attrs.last_notification;
        const interval = attrs.notification_interval;

        if (first && last && last !== '0') {
            html += `<div class="dep-rule-detail"><i class="fa-solid fa-stairs"></i> Escalates from notification ${first} to ${last}</div>`;
        } else if (first) {
            html += `<div class="dep-rule-detail"><i class="fa-solid fa-stairs"></i> Escalates starting at notification ${first}</div>`;
        }

        if (interval && interval !== '0') {
            html += `<div class="dep-rule-detail"><i class="fa-solid fa-rotate"></i> Re-notify every ${interval} minutes</div>`;
        }

        if (attrs.escalation_period) {
            html += `<div class="dep-rule-detail"><i class="fa-solid fa-clock"></i> Active during: ${Explorer.escapeHtml(attrs.escalation_period)}</div>`;
        }

        // Show who gets notified
        const contacts = [];
        if (attrs.contacts) contacts.push(attrs.contacts);
        if (attrs.contact_groups) contacts.push(attrs.contact_groups);
        if (attrs.escalation_contacts) contacts.push(attrs.escalation_contacts);
        if (attrs.escalation_contact_groups) contacts.push(attrs.escalation_contact_groups);

        if (contacts.length > 0) {
            html += `<div class="dep-rule-detail"><i class="fa-solid fa-users"></i> Notifies: ${Explorer.escapeHtml(contacts.join(', '))}</div>`;
        }

        return html;
    }

    /**
     * Render the Group Membership subsection
     */
    function renderMembershipSubsection(obj, members, memberOf) {
        const totalCount = members.length + memberOf.length;

        let content = '';

        // "Member of" for regular objects
        if (memberOf.length > 0) {
            content += '<div class="ancestry-label">Member of</div>';
            content += '<div class="ref-type-list">';
            memberOf.forEach(item => {
                const displayName = getStagedDisplayName(item.object);
                content += `
                    <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${item.object.global_index})">
                        <span class="ref-type-badge type-${item.object.object_type}">${item.object.object_type}</span>
                        <span class="ref-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
                    </div>
                `;
            });
            content += '</div>';
        }

        // Direct members for groups/templates
        if (members.length > 0) {
            const label = isObjectTemplate(obj) ? 'Used by (inherits from this template)' : 'Direct Members';
            content += `<div class="ancestry-label">${label}</div>`;

            // Group by type
            const grouped = {};
            members.forEach(m => {
                const type = m.object.object_type;
                if (!grouped[type]) grouped[type] = [];
                grouped[type].push(m);
            });

            for (const [type, items] of Object.entries(grouped)) {
                const typeLabel = typeLabels[type] || type;
                content += `<div class="ref-type-group"><div class="ref-type-header">${typeLabel} (${items.length})</div>`;
                content += '<div class="ref-type-list">';
                items.forEach(m => {
                    const displayName = getStagedDisplayName(m.object);
                    content += `
                        <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${m.object.global_index})">
                            <span class="ref-type-badge type-${m.object.object_type}">${m.object.object_type}</span>
                            <span class="ref-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
                        </div>
                    `;
                });
                content += '</div></div>';
            }
        }

        return `
            <div class="impact-subsection">
                <div class="impact-subsection-header">
                    <div class="impact-subsection-title">
                        <i class="fa-solid fa-users"></i>
                        <span>Group Membership</span>
                        <span class="impact-subsection-count">${totalCount}</span>
                    </div>
                    <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
                </div>
                <div class="impact-subsection-content">${content}</div>
            </div>
        `;
    }

    // =============================================================================
    // RESOLVED ATTRIBUTES TABLE
    // =============================================================================

    /**
     * Render the resolved attributes table showing each attribute's final value and source.
     * @param {Object} resolvedAttrs - {attrName: {value, source}} or {attrName: "value"} map
     * @param {Object} obj - The current object
     */
    function renderResolvedAttrsTable(resolvedAttrs, obj) {
        const objName = getEffectiveName(obj);
        const entries = Object.entries(resolvedAttrs)
            .filter(([key]) => !['use', 'name', 'register'].includes(key))
            .sort(([a], [b]) => a.localeCompare(b));

        if (entries.length === 0) return '';

        let html = '<div class="ancestry-label">Resolved Attributes</div>';
        html += '<div class="resolved-attrs-compact">';
        html += '<div class="resolved-attrs-header-row">';
        html += '<span class="resolved-attr-name">Attribute</span>';
        html += '<span class="resolved-attr-value">Value</span>';
        html += '<span class="resolved-attr-source">Source</span>';
        html += '</div>';

        for (const [key, rawValue] of entries) {
            const value = (typeof rawValue === 'object' && rawValue !== null) ? rawValue.value : rawValue;
            const source = (typeof rawValue === 'object' && rawValue !== null) ? rawValue.source : objName;
            const isSelf = source === objName;
            const sourceClass = isSelf ? 'resolved-source-self' : 'resolved-source-inherited';

            html += '<div class="resolved-attrs-row">';
            html += `<span class="resolved-attr-name">${Explorer.escapeHtml(key)}</span>`;
            html += `<span class="resolved-attr-value" title="${Explorer.escapeHtml(value)}">${Explorer.escapeHtml(value)}</span>`;
            html += `<span class="resolved-attr-source ${sourceClass}">${Explorer.escapeHtml(source)}</span>`;
            html += '</div>';
        }

        html += '</div>';
        return html;
    }

    // =============================================================================
    // EXPORT TO EXPLORER NAMESPACE
    // =============================================================================

    Explorer.loadImpactAndRelationships = loadImpactAndRelationships;

})(window.Explorer);
