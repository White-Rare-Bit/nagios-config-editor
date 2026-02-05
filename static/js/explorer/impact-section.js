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

        // Show the section
        section.style.display = 'block';

        // Show loading state
        container.innerHTML = '<div class="loading">Loading relationships...</div>';

        // Gather all data in parallel where possible
        const [inheritanceData, referencesData, membersData] = await Promise.all([
            gatherInheritanceData(obj),
            gatherReferencesData(obj),
            gatherMembersData(obj)
        ]);

        // Render the unified section
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
            parentHosts: null
        };

        // For new objects, build inheritance chain locally
        if (state.isNewObject) {
            const useAttr = obj.attributes.use;
            if (useAttr) {
                const templateNames = Explorer.parseCommaValues(useAttr);
                result.templateChain = Explorer.buildLocalInheritanceChain(obj, templateNames);
            }
        } else {
            // Fetch from API
            try {
                const response = await fetch(`/api/inheritance/${obj.object_type}/${encodeURIComponent(obj.name || obj.display_name)}`);
                const apiResult = await response.json();
                if (!apiResult.error) {
                    result.templateChain = apiResult.chain;
                }
            } catch (error) {
                console.error('Error loading inheritance:', error);
            }
        }

        // Build parent hosts tree (for hosts only)
        if (obj.object_type === 'host') {
            const attrs = getEffectiveAttributes(obj);
            if (attrs.parents) {
                result.parentHosts = buildParentHostsTreeData(obj);
            }
        }

        return result;
    }

    /**
     * Build parent hosts tree data structure
     */
    function buildParentHostsTreeData(hostObj, visited = new Set()) {
        const attrs = getEffectiveAttributes(hostObj);
        const hostName = getEffectiveName(hostObj);

        if (visited.has(hostObj.global_index)) {
            return { name: hostName, circular: true };
        }
        visited.add(hostObj.global_index);

        const parentsAttr = attrs.parents || '';
        const parentNames = Explorer.parseCommaValues(parentsAttr);

        const parentNodes = [];
        for (const parentName of parentNames) {
            const parentObj = state.allObjects.find(o =>
                o.object_type === 'host' && getEffectiveName(o) === parentName
            );
            if (parentObj) {
                parentNodes.push(buildParentHostsTreeData(parentObj, new Set(visited)));
            } else {
                parentNodes.push({ name: parentName, missing: true });
            }
        }

        return {
            name: hostName,
            file: hostObj.source_file ? hostObj.source_file.split('/').pop() : '',
            obj: hostObj,
            parents: parentNodes
        };
    }

    /**
     * Gather references data (outgoing dependencies + incoming dependents)
     */
    function gatherReferencesData(obj) {
        const name = getEffectiveName(obj);

        // Use centralized reference fields from constants
        const referenceFields = constants.referenceFields;

        const stripRefPrefix = v => v.trim().replace(/^[+!]+/, '').trim();
        const commandFields = ['check_command', 'event_handler', 'notification_commands',
                              'host_notification_commands', 'service_notification_commands',
                              'obsess_over_host_command', 'obsess_over_service_command',
                              'global_host_event_handler', 'global_service_event_handler'];

        // Outgoing references (what this object depends on)
        const outgoing = [];
        for (const [field, refType] of Object.entries(referenceFields)) {
            if (!obj.attributes[field]) continue;
            const values = obj.attributes[field].split(',').map(stripRefPrefix).filter(v => v && v !== '*');
            const actualType = refType || obj.object_type;

            values.forEach(val => {
                let lookupVal = val;
                if (commandFields.includes(field) && val.includes('!')) {
                    lookupVal = val.split('!')[0];
                }
                const referenced = state.allObjects.find(o =>
                    o.object_type === actualType &&
                    (getEffectiveName(o) === lookupVal || getEffectiveAttributes(o).name === lookupVal)
                );
                if (referenced && referenced.global_index !== obj.global_index) {
                    outgoing.push({ field, object: referenced });
                }
            });
        }

        // Find dependency objects (hostdependency/servicedependency)
        const depObjects = Explorer.findDependencyObjects(obj, state.allObjects);

        // Add master relationships to outgoing
        depObjects.masterOf.forEach(depObj => {
            outgoing.push({ field: 'dependency_rule', object: depObj, isDependencyRule: true });
        });

        // Incoming references (what references this object - impact of deletion/rename)
        const incoming = [];
        const objEffectiveAttrs = getEffectiveAttributes(obj);
        state.allObjects.forEach(o => {
            if (o.global_index === obj.global_index) return;
            const attrs = getEffectiveAttributes(o);
            for (const [field, refType] of Object.entries(referenceFields)) {
                if (!attrs[field]) continue;
                const actualType = refType || o.object_type;
                const isEscalationReference = (o.object_type === 'hostescalation' || o.object_type === 'serviceescalation') &&
                                             (obj.object_type === 'contact' || obj.object_type === 'contactgroup') &&
                                             (field === 'escalation_contacts' || field === 'escalation_contact_groups' ||
                                              field === 'contacts' || field === 'contact_groups');
                if (actualType !== obj.object_type && refType !== null && !isEscalationReference) continue;

                let values = attrs[field].split(',').map(stripRefPrefix);
                if (commandFields.includes(field)) {
                    values = values.map(v => v.includes('!') ? v.split('!')[0] : v);
                }
                if (values.includes(name) || values.includes(objEffectiveAttrs.name)) {
                    incoming.push({ field, object: o });
                }
            }
        });

        // Add dependent relationships to incoming
        depObjects.dependentOf.forEach(depObj => {
            incoming.push({ field: 'dependency_rule', object: depObj, isDependencyRule: true });
        });

        // Find escalation objects (hostescalation/serviceescalation) that apply to this host/service
        const escObjects = Explorer.findEscalationObjects(obj, state.allObjects);
        escObjects.escalations.forEach(escObj => {
            incoming.push({ field: 'escalation_rule', object: escObj, isEscalationRule: true });
        });

        // For hostgroups: find services deployed via hostgroup_name
        if (obj.object_type === 'hostgroup') {
            state.allObjects.filter(o => o.object_type === 'service').forEach(svc => {
                const svcAttrs = getEffectiveAttributes(svc);
                if (svcAttrs.hostgroup_name) {
                    const groups = svcAttrs.hostgroup_name.split(',').map(g => g.trim().replace(/^[+!]+/, '').trim());
                    if (groups.includes(name)) {
                        incoming.push({ field: 'hostgroup_name', object: svc, isServiceBinding: true });
                    }
                }
            });
        }

        // For hosts: find services deployed via hostgroup_name where host is member of that hostgroup
        if (obj.object_type === 'host') {
            const hostName = name;
            state.allObjects.filter(o => o.object_type === 'service').forEach(svc => {
                const svcAttrs = getEffectiveAttributes(svc);
                if (svcAttrs.host_name) return;

                if (svcAttrs.hostgroup_name) {
                    const groups = svcAttrs.hostgroup_name.split(',').map(g => g.trim().replace(/^[+!]+/, '').trim());
                    for (const groupName of groups) {
                        if (Explorer.isHostInHostgroup(hostName, groupName, state.allObjects)) {
                            incoming.push({ field: 'hostgroup_name', object: svc, isServiceBinding: true, viaGroup: groupName });
                            break;
                        }
                    }
                }
            });
        }

        return { outgoing, incoming };
    }

    /**
     * Gather members data (for groups and templates)
     */
    function gatherMembersData(obj) {
        const objName = getEffectiveName(obj);
        const objEffectiveAttrs = getEffectiveAttributes(obj);
        const members = [];
        const memberOf = [];

        // Group membership (what groups this object belongs to)
        if (obj.object_type === 'host') {
            const hostgroups = (objEffectiveAttrs.hostgroups || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            hostgroups.forEach(groupName => {
                const group = state.allObjects.find(o =>
                    o.object_type === 'hostgroup' && getEffectiveName(o) === groupName
                );
                if (group) memberOf.push({ object: group, via: 'hostgroups' });
            });
        } else if (obj.object_type === 'service') {
            const servicegroups = (objEffectiveAttrs.servicegroups || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            servicegroups.forEach(groupName => {
                const group = state.allObjects.find(o =>
                    o.object_type === 'servicegroup' && getEffectiveName(o) === groupName
                );
                if (group) memberOf.push({ object: group, via: 'servicegroups' });
            });
        } else if (obj.object_type === 'contact') {
            const contactgroups = (objEffectiveAttrs.contactgroups || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            contactgroups.forEach(groupName => {
                const group = state.allObjects.find(o =>
                    o.object_type === 'contactgroup' && getEffectiveName(o) === groupName
                );
                if (group) memberOf.push({ object: group, via: 'contactgroups' });
            });
        }

        // For groups: get direct members
        if (obj.object_type === 'hostgroup') {
            const directMembers = (objEffectiveAttrs.members || '').split(',').map(x => x.trim()).filter(x => x);
            directMembers.forEach(m => {
                const host = state.allObjects.find(o => o.object_type === 'host' && getEffectiveName(o) === m);
                if (host) members.push({ object: host, via: 'members' });
            });
            // Hosts with this hostgroup in their hostgroups attribute
            state.allObjects.filter(o => o.object_type === 'host').forEach(host => {
                const attrs = getEffectiveAttributes(host);
                const hgs = (attrs.hostgroups || '').split(',').map(x => x.trim().replace(/^[+!]+/, '').trim());
                if (hgs.includes(objName) && !members.find(m => m.object.global_index === host.global_index)) {
                    members.push({ object: host, via: 'hostgroups attr' });
                }
            });
        } else if (obj.object_type === 'contactgroup') {
            const directMembers = (objEffectiveAttrs.members || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            directMembers.forEach(m => {
                const contact = state.allObjects.find(o => o.object_type === 'contact' && getEffectiveName(o) === m);
                if (contact && !members.find(mem => mem.object.global_index === contact.global_index)) {
                    members.push({ object: contact, via: 'members' });
                }
            });
            // Contacts with this contactgroup in their contactgroups attribute
            state.allObjects.filter(o => o.object_type === 'contact').forEach(contact => {
                const attrs = getEffectiveAttributes(contact);
                const cgs = (attrs.contactgroups || '').split(',')
                    .map(x => x.trim().replace(/^[+!]+/, '').trim())
                    .filter(x => x);
                if (cgs.includes(objName) && !members.find(m => m.object.global_index === contact.global_index)) {
                    members.push({ object: contact, via: 'contactgroups attr' });
                }
            });
        } else if (obj.object_type === 'servicegroup') {
            const directMembers = (objEffectiveAttrs.members || '').split(',')
                .map(x => x.trim().replace(/^[+!]+/, '').trim())
                .filter(x => x);
            directMembers.forEach(m => {
                const svc = state.allObjects.find(o => o.object_type === 'service' && getEffectiveName(o) === m);
                if (svc && !members.find(mem => mem.object.global_index === svc.global_index)) {
                    members.push({ object: svc, via: 'members' });
                }
            });
            // Services with this servicegroup in their servicegroups attribute
            state.allObjects.filter(o => o.object_type === 'service').forEach(svc => {
                const attrs = getEffectiveAttributes(svc);
                const sgs = (attrs.servicegroups || '').split(',')
                    .map(x => x.trim().replace(/^[+!]+/, '').trim())
                    .filter(x => x);
                if (sgs.includes(objName) && !members.find(m => m.object.global_index === svc.global_index)) {
                    members.push({ object: svc, via: 'servicegroups attr' });
                }
            });
        } else if (isObjectTemplate(obj)) {
            // Find objects using this template
            state.allObjects.forEach(o => {
                if (o.global_index === obj.global_index) return;
                if (o.object_type === obj.object_type && getEffectiveName(o) === objName) return;
                const attrs = getEffectiveAttributes(o);
                const uses = (attrs.use || '').split(',').map(x => x.trim());
                if (uses.includes(objName) || uses.includes(objEffectiveAttrs.name)) {
                    members.push({ object: o, via: 'inherits' });
                }
            });
        }

        return { members, memberOf };
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

        const { templateChain, parentHosts } = inheritanceData;
        const { outgoing, incoming } = referencesData;
        const { members, memberOf } = membersData;

        // Check if there's any data to show
        const hasTemplateChain = templateChain && templateChain.parents && templateChain.parents.length > 0;
        const hasParentHosts = parentHosts && parentHosts.parents && parentHosts.parents.length > 0;
        const hasIncoming = incoming.length > 0;
        const hasOutgoing = outgoing.length > 0;
        const hasMembers = members.length > 0;
        const hasMemberOf = memberOf.length > 0;

        if (!hasTemplateChain && !hasParentHosts && !hasIncoming && !hasOutgoing && !hasMembers && !hasMemberOf) {
            section.style.display = 'none';
            container.innerHTML = '';
            return;
        }

        let html = '';

        // 1. Configuration Ancestry (Templates + Parent Hosts)
        if (hasTemplateChain || hasParentHosts) {
            html += renderAncestrySubsection(obj, templateChain, parentHosts);
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
    function renderAncestrySubsection(obj, templateChain, parentHosts) {
        const hasTemplates = templateChain && templateChain.parents && templateChain.parents.length > 0;
        const hasParents = parentHosts && parentHosts.parents && parentHosts.parents.length > 0;

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
    // EXPORT TO EXPLORER NAMESPACE
    // =============================================================================

    Explorer.loadImpactAndRelationships = loadImpactAndRelationships;

})(window.Explorer);
