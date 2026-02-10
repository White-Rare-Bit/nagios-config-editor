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
        let membersData = { members: [], memberOf: [], transitiveSummary: null };

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
                        severity: r.severity || 'info',
                    })).filter(r => r.object);

                    membersData.members = (data.members || []).map(r => ({
                        object: objectsByIndex.get(r.global_index),
                        via: r.via,
                    })).filter(r => r.object);

                    membersData.memberOf = (data.member_of || []).map(r => ({
                        object: objectsByIndex.get(r.global_index),
                        via: r.via,
                    })).filter(r => r.object);

                    if (data.transitive_summary) {
                        membersData.transitiveSummary = data.transitive_summary;
                    }

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
        const { members, memberOf, transitiveSummary } = membersData;

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
            html += renderIncomingSubsection(obj, incoming);
        }

        // 3. "This Object Requires" (outgoing references)
        if (hasOutgoing) {
            html += renderOutgoingSubsection(outgoing);
        }

        // 4. Group Membership
        if (hasMembers || hasMemberOf) {
            html += renderMembershipSubsection(obj, members, memberOf, transitiveSummary);
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
     * Get a human-readable reason string for an incoming reference impact
     */
    function getImpactReason(ref) {
        if (ref.severity === 'error') {
            if (ref.isServiceBinding) return 'Will be orphaned';
            if (ref.isDependencyRule) return 'Dependency breaks';
            return 'Broken reference';
        }
        if (ref.isDependencyRule) return 'Dependency rule';
        if (ref.isEscalationRule) return 'Escalation rule';
        if (ref.field) return 'via ' + ref.field;
        return 'Needs update';
    }

    /**
     * Render the "If Deleted/Renamed" subsection as a terraform-plan-style diff view.
     * Incoming references sorted: destroy (errors) first, then modify (warnings/info).
     */
    function renderIncomingSubsection(obj, incoming) {
        const count = incoming.length;
        const objName = Explorer.escapeHtml(getEffectiveName(obj));
        const nameField = (Explorer.constants.nameFields || {})[obj.object_type] || obj.object_type;

        // Partition by severity
        const errors = incoming.filter(r => r.severity === 'error');
        const warnings = incoming.filter(r => r.severity === 'warning');
        const infos = incoming.filter(r => r.severity === 'info' || !r.severity);

        // Determine header badge class based on worst severity
        const badgeClass = errors.length > 0 ? 'danger' : 'warning';

        // Sort: destroy first, then modify
        const sorted = [...errors, ...warnings, ...infos];
        const modifyCount = warnings.length + infos.length;

        // Summary banner
        let content = '<div class="impact-diff-header"><span>Plan: ';
        const parts = [];
        if (errors.length > 0) {
            parts.push(`<strong class="impact-diff-count-destroy">${errors.length}</strong> to break`);
        }
        if (modifyCount > 0) {
            parts.push(`<strong class="impact-diff-count-modify">${modifyCount}</strong> to update`);
        }
        content += parts.join(', ') + '.</span></div>';

        // Diff list
        content += '<div class="impact-diff-list">';
        sorted.forEach(ref => {
            const isDestroy = ref.severity === 'error';
            const status = isDestroy ? 'destroy' : 'modify';
            const symbol = isDestroy ? '[-]' : '[~]';
            const type = ref.object.object_type.toUpperCase();
            const displayName = getStagedDisplayName(ref.object);
            const reason = getImpactReason(ref);

            content += `<div class="impact-diff-row impact-diff-row--${status}" onclick="Explorer.navigateToObjectByIndex(${ref.object.global_index})">`;
            content += `<span class="impact-diff-status">${symbol} <span class="impact-diff-type">${type}</span></span>`;
            content += `<span class="impact-diff-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>`;
            content += `<span class="impact-diff-reason">${Explorer.escapeHtml(reason)}</span>`;
            content += '</div>';
        });
        content += '</div>';

        return `
            <div class="impact-subsection">
                <div class="impact-subsection-header">
                    <div class="impact-subsection-title">
                        <i class="fa-solid fa-link-slash"></i>
                        <span>If ${nameField} ${objName} is Deleted/Renamed</span>
                        <span class="impact-subsection-count ${badgeClass}">${count}</span>
                    </div>
                    <span class="impact-subsection-toggle"><i class="fa-solid fa-chevron-right"></i></span>
                </div>
                <div class="impact-subsection-content">${content}</div>
            </div>
        `;
    }

    /**
     * Render the "This Object Requires" subsection as a 4-column grid
     */
    function renderOutgoingSubsection(outgoing) {
        const count = outgoing.length;

        let content = '<div class="dep-grid-list">';
        outgoing.forEach(ref => {
            const type = ref.object.object_type.toUpperCase();
            const displayName = getStagedDisplayName(ref.object);
            const attrKey = ref.field || '';

            content += `<div class="dep-grid-row dep-grid-row--ok" onclick="Explorer.navigateToObjectByIndex(${ref.object.global_index})">`;
            content += `<span class="dep-grid-status">[✓] <span class="dep-grid-type">${type}</span></span>`;
            content += `<span class="dep-grid-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>`;
            content += `<span class="dep-grid-attr">${Explorer.escapeHtml(attrKey)}</span>`;
            content += '</div>';
        });
        content += '</div>';

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

    // (renderGroupedReferences removed — outgoing and membership now use dep-grid layout)

    /**
     * Render the Group Membership subsection as a 4-column grid
     */
    function renderMembershipSubsection(obj, members, memberOf, transitiveSummary) {
        const totalCount = members.length + memberOf.length;

        let content = '';

        // "Member of" for regular objects
        if (memberOf.length > 0) {
            content += '<div class="ancestry-label">Member of</div>';
            content += '<div class="dep-grid-list">';
            memberOf.forEach(item => {
                const type = item.object.object_type.toUpperCase();
                const displayName = getStagedDisplayName(item.object);
                const via = item.via || 'members';

                content += `<div class="dep-grid-row dep-grid-row--ok" onclick="Explorer.navigateToObjectByIndex(${item.object.global_index})">`;
                content += `<span class="dep-grid-status">[✓] <span class="dep-grid-type">${type}</span></span>`;
                content += `<span class="dep-grid-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>`;
                content += `<span class="dep-grid-attr">${Explorer.escapeHtml(via)}</span>`;
                content += '</div>';
            });
            content += '</div>';
        }

        // Direct members for groups/templates
        if (members.length > 0) {
            const label = isObjectTemplate(obj) ? 'Used by (inherits from this template)' : 'Direct Members';
            content += `<div class="ancestry-label">${label}</div>`;

            // Show transitive impact summary for templates
            if (transitiveSummary && transitiveSummary.transitive_count > 0) {
                const intermediateList = transitiveSummary.intermediate_templates.join(', ');
                content += `
                    <div class="impact-summary info">
                        <span class="impact-summary-icon"><i class="fa-solid fa-diagram-project"></i></span>
                        <span>Affects ${transitiveSummary.transitive_count} total objects through ${transitiveSummary.intermediate_templates.length} intermediate template${transitiveSummary.intermediate_templates.length !== 1 ? 's' : ''}</span>
                    </div>
                `;
                if (intermediateList) {
                    content += `<div class="dep-rule-details"><div class="dep-rule-detail"><i class="fa-solid fa-layer-group"></i> Via: ${Explorer.escapeHtml(intermediateList)}</div></div>`;
                }
            }

            content += '<div class="dep-grid-list">';
            members.forEach(m => {
                const type = m.object.object_type.toUpperCase();
                const displayName = getStagedDisplayName(m.object);
                const via = m.via || 'members';

                content += `<div class="dep-grid-row dep-grid-row--ok" onclick="Explorer.navigateToObjectByIndex(${m.object.global_index})">`;
                content += `<span class="dep-grid-status">[✓] <span class="dep-grid-type">${type}</span></span>`;
                content += `<span class="dep-grid-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>`;
                content += `<span class="dep-grid-attr">${Explorer.escapeHtml(via)}</span>`;
                content += '</div>';
            });
            content += '</div>';
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
