/**
 * Relations Loader Module
 *
 * Handles loading and rendering of center pane relationship sections:
 * - Inheritance chains (template ancestry)
 * - References (dependencies and dependents)
 * - Members (group membership)
 *
 * These are the "legacy" separate rendering functions. The unified Impact section
 * (in impact-section.js) consolidates these into a single collapsible section.
 */
(function(Explorer) {
    'use strict';

    const state = Explorer.state;
    const constants = Explorer.constants;

    // Shared helper: get effective attributes respecting pending edits
    function getEffectiveAttrs(o) {
        return Explorer.getEffectiveAttributes(o);
    }

    // Shared helper: get effective name respecting pending edits
    function getEffectiveName(obj) {
        return Explorer.getEffectiveName(obj);
    }

    // Shared helper: get staged display name
    function getStagedDisplayName(obj) {
        return Explorer.getStagedDisplayName(obj);
    }

    // Type labels for display (from constants)
    const typeLabels = constants.typeLabels;

    // =============================================================================
    // DEPENDENCY/ESCALATION FINDING HELPERS
    // =============================================================================

    /**
     * Find hostdependency/servicedependency objects referencing this host or service.
     *
     * Dependency objects define master/dependent relationships that control execution
     * and notification behavior.
     *
     * For hosts: matches host_name (master) and dependent_host_name (dependent) fields.
     * For services: matches service_description with host scoping when host_name present;
     * services using only hostgroup_name cannot be matched precisely.
     *
     * @returns {Object} {masterOf: [...], dependentOf: [...]}
     */
    function findDependencyObjects(obj, allObjects) {
        const result = { masterOf: [], dependentOf: [] };

        if (obj.object_type === 'host') {
            const hostName = getEffectiveName(obj);
            allObjects.filter(o => o.object_type === 'hostdependency').forEach(depObj => {
                const attrs = getEffectiveAttrs(depObj);
                const masterHost = attrs.host_name;
                const dependentHost = attrs.dependent_host_name;

                if (masterHost === hostName) {
                    result.masterOf.push(depObj);
                }
                if (dependentHost === hostName) {
                    result.dependentOf.push(depObj);
                }
            });
        } else if (obj.object_type === 'service') {
            const serviceName = getEffectiveName(obj);
            const objAttrs = getEffectiveAttrs(obj);
            const hostName = objAttrs.host_name;

            if (!hostName) {
                return result;
            }

            allObjects.filter(o => o.object_type === 'servicedependency').forEach(depObj => {
                const attrs = getEffectiveAttrs(depObj);
                const masterService = attrs.service_description;
                const masterHost = attrs.host_name;
                const dependentService = attrs.dependent_service_description;
                const dependentHost = attrs.dependent_host_name;

                if (masterService === serviceName && (!masterHost || masterHost === hostName)) {
                    result.masterOf.push(depObj);
                }
                if (dependentService === serviceName && (!dependentHost || dependentHost === hostName)) {
                    result.dependentOf.push(depObj);
                }
            });
        }

        return result;
    }

    /**
     * Check if a host is a member of a hostgroup (direct or via hostgroups attribute).
     */
    function isHostInHostgroup(hostName, hostgroupName, allObjects) {
        const hostgroup = allObjects.find(o =>
            o.object_type === 'hostgroup' && getEffectiveName(o) === hostgroupName
        );
        if (!hostgroup) return false;

        const hgAttrs = getEffectiveAttrs(hostgroup);

        // Check direct members
        const directMembers = (hgAttrs.members || '').split(',').map(m => m.trim()).filter(m => m);
        if (directMembers.includes(hostName)) return true;

        // Check host's hostgroups attribute
        const host = allObjects.find(o => o.object_type === 'host' && getEffectiveName(o) === hostName);
        if (host) {
            const hostAttrs = getEffectiveAttrs(host);
            const hostGroups = (hostAttrs.hostgroups || '').split(',').map(g => g.trim().replace(/^[+!]+/, '')).filter(g => g);
            if (hostGroups.includes(hostgroupName)) return true;
        }

        // Check nested hostgroup_members (recursive)
        const nestedGroups = (hgAttrs.hostgroup_members || '').split(',').map(g => g.trim().replace(/^[+!]+/, '')).filter(g => g);
        for (const nestedGroupName of nestedGroups) {
            if (isHostInHostgroup(hostName, nestedGroupName, allObjects)) return true;
        }

        return false;
    }

    /**
     * Find escalation objects (hostescalation/serviceescalation) that apply to a host or service.
     * @returns {Object} { escalations: [...] }
     */
    function findEscalationObjects(obj, allObjects) {
        const result = { escalations: [] };

        if (obj.object_type === 'host') {
            const hostName = getEffectiveName(obj);
            allObjects.filter(o => o.object_type === 'hostescalation').forEach(escObj => {
                const attrs = getEffectiveAttrs(escObj);
                const escHostName = attrs.host_name;
                const escHostgroupName = attrs.hostgroup_name;

                if (escHostName && escHostName.split(',').map(h => h.trim()).includes(hostName)) {
                    result.escalations.push(escObj);
                    return;
                }

                if (escHostgroupName) {
                    const groups = escHostgroupName.split(',').map(g => g.trim()).filter(g => g);
                    for (const groupName of groups) {
                        if (isHostInHostgroup(hostName, groupName, allObjects)) {
                            result.escalations.push(escObj);
                            return;
                        }
                    }
                }
            });
        } else if (obj.object_type === 'service') {
            const serviceName = getEffectiveName(obj);
            const objAttrs = getEffectiveAttrs(obj);
            const hostName = objAttrs.host_name;

            if (!hostName) {
                return result;
            }

            allObjects.filter(o => o.object_type === 'serviceescalation').forEach(escObj => {
                const attrs = getEffectiveAttrs(escObj);
                const escServiceDesc = attrs.service_description;
                const escHostName = attrs.host_name;
                const escHostgroupName = attrs.hostgroup_name;

                if (escServiceDesc && escServiceDesc.split(',').map(s => s.trim()).includes(serviceName)) {
                    if (escHostName && escHostName.split(',').map(h => h.trim()).includes(hostName)) {
                        result.escalations.push(escObj);
                        return;
                    }

                    if (escHostgroupName) {
                        const groups = escHostgroupName.split(',').map(g => g.trim()).filter(g => g);
                        for (const groupName of groups) {
                            if (isHostInHostgroup(hostName, groupName, allObjects)) {
                                result.escalations.push(escObj);
                                return;
                            }
                        }
                    }

                    if (!escHostName && !escHostgroupName) {
                        result.escalations.push(escObj);
                    }
                }
            });
        }

        return result;
    }

    // =============================================================================
    // FORMAT HELPERS
    // =============================================================================

    /**
     * Format failure criteria from dependency object into compact display string.
     */
    function formatFailureCriteria(depObj) {
        const attrs = getEffectiveAttrs(depObj);
        const parts = [];
        const validCriteriaPattern = /^[nouwcpd,]+$/;

        if (attrs.execution_failure_criteria) {
            const criteria = attrs.execution_failure_criteria.trim();
            if (validCriteriaPattern.test(criteria)) {
                parts.push(`skip: ${criteria}`);
            } else {
                parts.push(`skip: ${criteria} ⚠`);
            }
        }
        if (attrs.notification_failure_criteria) {
            const criteria = attrs.notification_failure_criteria.trim();
            if (validCriteriaPattern.test(criteria)) {
                parts.push(`notify: ${criteria}`);
            } else {
                parts.push(`notify: ${criteria} ⚠`);
            }
        }

        return parts.length > 0 ? `(${parts.join('; ')})` : '';
    }

    /**
     * Format escalation info from escalation object into compact display string.
     */
    function formatEscalationInfo(escObj) {
        const attrs = getEffectiveAttrs(escObj);
        const parts = [];

        const first = attrs.first_notification;
        const last = attrs.last_notification;
        const interval = attrs.notification_interval;

        if (first || last) {
            if (first && last && last !== '0') {
                parts.push(`levels ${first}-${last}`);
            } else if (first) {
                parts.push(`from level ${first}`);
            }
        }

        if (interval && interval !== '0') {
            parts.push(`every ${interval}m`);
        }

        return parts.length > 0 ? `(${parts.join(', ')})` : '';
    }

    // =============================================================================
    // INHERITANCE SECTION
    // =============================================================================

    /**
     * Load and render the inheritance section for an object.
     */
    async function loadCenterInheritance(obj) {
        const container = document.getElementById('inheritanceContent');
        const section = document.getElementById('inheritanceSection');

        // For new objects, build inheritance chain locally from use attribute
        if (state.isNewObject) {
            const useAttr = obj.attributes.use;
            if (!useAttr) {
                if (section) section.style.display = 'none';
                container.innerHTML = '';
                return;
            }

            const templateNames = Explorer.parseCommaValues(useAttr);
            const chain = buildLocalInheritanceChain(obj, templateNames);
            renderCenterInheritance(chain, obj);
            return;
        }

        container.innerHTML = '<div class="loading">Loading inheritance...</div>';

        try {
            const response = await fetch(`/api/inheritance/${obj.object_type}/${encodeURIComponent(obj.name || obj.display_name)}`);
            const result = await response.json();

            if (result.error) {
                container.innerHTML = `<div class="empty-message">${Explorer.escapeHtml(result.error)}</div>`;
                return;
            }

            renderCenterInheritance(result.chain, obj);
        } catch (error) {
            container.innerHTML = `<div class="empty-message">Error loading inheritance</div>`;
        }
    }

    /**
     * Build inheritance chain locally for new objects.
     */
    function buildLocalInheritanceChain(obj, templateNames) {
        const chain = {
            name: obj.display_name || '(new object)',
            object_type: obj.object_type,
            is_template: false,
            parents: []
        };

        function findTemplate(name, objType) {
            return state.allObjects.find(o =>
                o.object_type === objType &&
                (o.attributes.name === name || o.name === name || o.display_name === name)
            );
        }

        function buildParentChain(parentNames, objType) {
            const parents = [];
            for (const name of parentNames) {
                const template = findTemplate(name, objType);
                if (template) {
                    const templateUse = Explorer.parseCommaValues(template.attributes.use || '');
                    parents.push({
                        name: getEffectiveName(template),
                        object_type: template.object_type,
                        is_template: true,
                        file: template.source_file,
                        parents: buildParentChain(templateUse, objType)
                    });
                } else {
                    parents.push({
                        name: name,
                        object_type: objType,
                        is_template: true,
                        error: 'Template not found'
                    });
                }
            }
            return parents;
        }

        chain.parents = buildParentChain(templateNames, obj.object_type);
        return chain;
    }

    /**
     * Render the inheritance chain in the center pane.
     */
    function renderCenterInheritance(chain, obj) {
        const container = document.getElementById('inheritanceContent');

        function getStagedNodeName(nodeName, objectType) {
            const matchingObj = state.allObjects.find(o =>
                o.object_type === objectType &&
                (o.name === nodeName || o.display_name === nodeName || o.attributes.name === nodeName)
            );
            if (matchingObj) {
                return getEffectiveName(matchingObj);
            }
            return nodeName;
        }

        function flattenChain(node, path = []) {
            path.push(node);
            const parents = node.parents || [];
            if (parents.length > 0) {
                flattenChain(parents[0], path);
            }
            return path;
        }

        function renderNestedTree(flatArray, idx = 0) {
            if (idx >= flatArray.length) return '';

            const node = flatArray[idx];
            const isCurrent = idx === flatArray.length - 1;
            const isTemplate = node.is_template;
            const isMissing = !!node.error;
            const displayName = getStagedNodeName(node.name, obj.object_type);
            const hasChildren = idx < flatArray.length - 1;
            const connector = idx > 0 ? '<span class="dep-tree-connector">↳</span>' : '';

            let nodeClass = '';
            if (isCurrent) nodeClass = 'current';
            else if (isMissing) nodeClass = 'missing';
            else if (isTemplate) nodeClass = 'template';

            let html = `
                <div class="ref-item ${nodeClass} ${isMissing ? '' : 'ref-item-clickable'}" ${isMissing ? '' : `onclick="Explorer.selectObjectByName('${Explorer.escapeJs(node.name)}')"`}>
                    ${connector}
                    <span class="ref-type-badge type-${obj.object_type}">${obj.object_type}</span>
                    <span class="ref-name" title="${Explorer.escapeHtml(displayName)}">${Explorer.escapeHtml(displayName)}</span>
                    ${isTemplate ? '<span class="template-marker">template</span>' : ''}
                    ${isCurrent ? '<span class="current-marker">current</span>' : ''}
                    ${isMissing ? `<span class="error-marker"><i class="fa-solid fa-xmark"></i> ${Explorer.escapeHtml(node.error)}</span>` : ''}
                </div>
            `;

            if (hasChildren) {
                html += `<div class="inheritance-children">${renderNestedTree(flatArray, idx + 1)}</div>`;
            }

            return html;
        }

        function buildParentHostsTree(hostObj, visited = new Set()) {
            const attrs = getEffectiveAttrs(hostObj);
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
                    parentNodes.push(buildParentHostsTree(parentObj, new Set(visited)));
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

        function renderParentsTopDown(node, isCurrent = false, depth = 0) {
            let html = '';

            if (node.parents && node.parents.length > 0) {
                for (const parent of node.parents) {
                    html += renderParentsTopDown(parent, false, depth);
                }
            }

            const nodeClass = isCurrent ? 'current' : (node.missing ? 'missing' : (node.circular ? 'missing' : ''));
            const clickable = !node.missing && !node.circular && node.obj;
            const currentDepth = html ? depth + 1 : depth;
            const connector = currentDepth > 0 ? '<span class="dep-tree-connector">↳</span>' : '';

            const nodeHtml = `
                <div class="ref-item ${nodeClass} ${clickable ? 'ref-item-clickable' : ''}" ${clickable ? `onclick="Explorer.navigateToObjectByIndex(${node.obj.global_index})"` : ''}>
                    ${connector}
                    <span class="ref-type-badge type-host">host</span>
                    <span class="ref-name" title="${Explorer.escapeHtml(node.name)}">${Explorer.escapeHtml(node.name)}</span>
                    ${node.missing ? '<span class="error-marker"><i class="fa-solid fa-xmark"></i> not found</span>' : ''}
                    ${node.circular ? '<span class="error-marker"><i class="fa-solid fa-xmark"></i> circular</span>' : ''}
                    ${isCurrent ? '<span class="current-marker">current</span>' : ''}
                </div>
            `;

            if (html) {
                html = `${html}<div class="inheritance-children">${nodeHtml}</div>`;
            } else {
                html = nodeHtml;
            }

            return html;
        }

        let html = '';
        const hasTemplates = chain && (chain.parents && chain.parents.length > 0);

        if (hasTemplates) {
            html += '<div class="inheritance-section-label">Templates</div>';
            const flatChain = flattenChain(chain);
            flatChain.reverse();
            html += `<div class="inheritance-tree">${renderNestedTree(flatChain)}</div>`;
        }

        if (obj.object_type === 'host') {
            const attrs = getEffectiveAttrs(obj);
            const parentsAttr = attrs.parents || '';
            const hasParents = parentsAttr.trim().length > 0;

            if (hasParents) {
                if (html) html += '<div class="u-mt-md"></div>';
                html += '<div class="inheritance-section-label">Parent Hosts</div>';
                const tree = buildParentHostsTree(obj);
                html += `<div class="inheritance-tree">${renderParentsTopDown(tree, true)}</div>`;
            }
        }

        const section = document.getElementById('inheritanceSection');
        if (!html) {
            if (section) section.style.display = 'none';
            container.innerHTML = '';
        } else {
            if (section) section.style.display = 'block';
            container.innerHTML = html;
        }
    }

    // =============================================================================
    // REFERENCES SECTION (Dependencies & Dependents)
    // =============================================================================

    /**
     * Load references (dependencies and dependents) for an object.
     */
    function loadCenterReferences(obj) {
        const name = getEffectiveName(obj);
        const referenceFields = constants.referenceFields;
        const stripRefPrefix = v => v.trim().replace(/^[+!]+/, '').trim();
        const commandFields = ['check_command', 'event_handler', 'notification_commands',
                              'host_notification_commands', 'service_notification_commands',
                              'obsess_over_host_command', 'obsess_over_service_command',
                              'global_host_event_handler', 'global_service_event_handler'];

        // Outgoing references
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
                    (getEffectiveName(o) === lookupVal || getEffectiveAttrs(o).name === lookupVal)
                );
                if (referenced && referenced.global_index !== obj.global_index) {
                    outgoing.push({ field, object: referenced });
                }
            });
        }

        // Find dependency objects
        const depObjects = findDependencyObjects(obj, state.allObjects);
        depObjects.masterOf.forEach(depObj => {
            outgoing.push({ field: 'dependency_rule', object: depObj, isDependencyRule: true });
        });

        // Incoming references
        const incoming = [];
        const objEffectiveAttrs = getEffectiveAttrs(obj);
        state.allObjects.forEach(o => {
            if (o.global_index === obj.global_index) return;
            const attrs = getEffectiveAttrs(o);
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

        // Find escalation objects
        const escObjects = findEscalationObjects(obj, state.allObjects);
        escObjects.escalations.forEach(escObj => {
            incoming.push({ field: 'escalation_rule', object: escObj, isEscalationRule: true });
        });

        // For hostgroups: find services deployed via hostgroup_name
        if (obj.object_type === 'hostgroup') {
            state.allObjects.filter(o => o.object_type === 'service').forEach(svc => {
                const svcAttrs = getEffectiveAttrs(svc);
                if (svcAttrs.hostgroup_name) {
                    const groups = svcAttrs.hostgroup_name.split(',').map(g => g.trim().replace(/^[+!]+/, '').trim());
                    if (groups.includes(name)) {
                        incoming.push({ field: 'hostgroup_name', object: svc, isServiceBinding: true });
                    }
                }
            });
        }

        // For hosts: find services deployed via hostgroup_name where host is member
        if (obj.object_type === 'host') {
            const hostName = name;
            state.allObjects.filter(o => o.object_type === 'service').forEach(svc => {
                const svcAttrs = getEffectiveAttrs(svc);
                if (svcAttrs.host_name) return;

                if (svcAttrs.hostgroup_name) {
                    const groups = svcAttrs.hostgroup_name.split(',').map(g => g.trim().replace(/^[+!]+/, '').trim());
                    for (const groupName of groups) {
                        if (isHostInHostgroup(hostName, groupName, state.allObjects)) {
                            incoming.push({ field: 'hostgroup_name', object: svc, isServiceBinding: true, viaGroup: groupName });
                            break;
                        }
                    }
                }
            });
        }

        renderCenterReferences({ outgoing, incoming });
    }

    /**
     * Render the references (dependencies and dependents) sections.
     */
    function renderCenterReferences(refs) {
        const dependenciesContainer = document.getElementById('dependenciesContent');
        const dependentsContainer = document.getElementById('dependentsContent');
        const { outgoing = [], incoming = [] } = refs;

        function getParentGroups(groupObj, visited = new Set()) {
            if (visited.has(groupObj.global_index)) return [];
            visited.add(groupObj.global_index);

            const parents = [];
            const groupType = groupObj.object_type;
            const groupName = getEffectiveName(groupObj);
            const membersAttr = groupType === 'hostgroup' ? 'hostgroup_members' :
                               groupType === 'servicegroup' ? 'servicegroup_members' :
                               groupType === 'contactgroup' ? 'contactgroup_members' : null;

            if (!membersAttr) return [];

            state.allObjects.filter(o => o.object_type === groupType).forEach(parentGroup => {
                const attrs = getEffectiveAttrs(parentGroup);
                const members = (attrs[membersAttr] || '').split(',').map(m => m.trim().replace(/^[+!]+/, '').trim());
                if (members.includes(groupName)) {
                    parents.push({
                        object: parentGroup,
                        parents: getParentGroups(parentGroup, new Set(visited))
                    });
                }
            });

            return parents;
        }

        function renderRefItem(obj, nested = false) {
            const connector = nested ? '<span class="dep-tree-connector">↳</span>' : '';
            return `
                <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${obj.global_index})">
                    ${connector}
                    <span class="ref-type-badge type-${obj.object_type}">${obj.object_type}</span>
                    <span class="ref-name" title="${Explorer.escapeHtml(getStagedDisplayName(obj))}">${Explorer.escapeHtml(getStagedDisplayName(obj))}</span>
                </div>
            `;
        }

        function getContactGroupMembers(contactGroup, visited = new Set()) {
            if (visited.has(contactGroup.global_index)) return [];
            visited.add(contactGroup.global_index);

            const members = [];
            const attrs = Explorer.getEffectiveAttributes(contactGroup);

            if (attrs.members) {
                const memberNames = attrs.members.split(',').map(m => m.trim().replace(/^\+/, ''));
                for (const name of memberNames) {
                    if (!name || name.startsWith('!')) continue;
                    const contact = state.allObjects.find(o =>
                        o.object_type === 'contact' &&
                        o.attributes.contact_name === name
                    );
                    if (contact) members.push(contact);
                }
            }

            if (attrs.contactgroup_members) {
                const groupNames = attrs.contactgroup_members.split(',').map(m => m.trim().replace(/^[+!]+/, ''));
                for (const groupName of groupNames) {
                    if (!groupName || groupName.startsWith('!')) continue;
                    const nestedGroup = state.allObjects.find(o =>
                        o.object_type === 'contactgroup' &&
                        (getEffectiveName(o) === groupName || Explorer.getEffectiveAttributes(o).name === groupName)
                    );
                    if (nestedGroup) {
                        const nestedMembers = getContactGroupMembers(nestedGroup, new Set(visited));
                        members.push(...nestedMembers);
                    }
                }
            }

            return members;
        }

        function renderContactGroupWithMembers(obj, nested = false) {
            let html = renderRefItem(obj, nested);

            const members = getContactGroupMembers(obj);
            if (members.length > 0) {
                html += '<div class="inheritance-children">';
                for (const contact of members) {
                    html += `
                        <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${contact.global_index})">
                            <span class="dep-tree-connector">↳</span>
                            <span class="ref-type-badge type-contact">contact</span>
                            <span class="ref-name" title="${Explorer.escapeHtml(getStagedDisplayName(contact))}">${Explorer.escapeHtml(getStagedDisplayName(contact))}</span>
                        </div>
                    `;
                }
                html += '</div>';
            }
            return html;
        }

        function renderConsolidatedDepTree(itemsWithParents, itemsWithoutParents) {
            let html = '';

            function renderGroupItem(obj, nested = false) {
                if (obj.object_type === 'contactgroup') {
                    return renderContactGroupWithMembers(obj, nested);
                }
                return renderRefItem(obj, nested);
            }

            const parentGroups = new Map();

            for (const { ref, parentChain } of itemsWithParents) {
                for (const parent of parentChain) {
                    const parentKey = parent.object.global_index;
                    if (!parentGroups.has(parentKey)) {
                        parentGroups.set(parentKey, {
                            parent: parent.object,
                            grandparents: parent.parents || [],
                            children: []
                        });
                    }
                    const group = parentGroups.get(parentKey);
                    if (!group.children.some(c => c.global_index === ref.object.global_index)) {
                        group.children.push(ref.object);
                    }
                }
            }

            for (const ref of itemsWithoutParents) {
                if (!parentGroups.has(ref.object.global_index)) {
                    html += renderGroupItem(ref.object, false);
                }
            }

            for (const [parentKey, group] of parentGroups) {
                html += renderGroupItem(group.parent, false);

                if (group.children.length > 0) {
                    html += '<div class="inheritance-children">';
                    for (const child of group.children) {
                        html += renderGroupItem(child, true);
                    }
                    html += '</div>';
                }
            }

            return html;
        }

        function renderGroupedItems(items) {
            if (items.length === 0) return '';

            const groups = Explorer.groupByType(items);
            let html = '';
            const groupTypes = ['hostgroup', 'servicegroup', 'contactgroup'];

            for (const [type, refs] of Object.entries(groups)) {
                const typeLabel = typeLabels[type] || type;
                const isGroupType = groupTypes.includes(type);

                html += `<div class="ref-type-group"><div class="ref-type-header">${typeLabel}</div>`;

                if (isGroupType) {
                    const refsWithParents = [];
                    const refsWithoutParents = [];
                    for (const ref of refs) {
                        const parentChain = getParentGroups(ref.object);
                        if (parentChain.length > 0) {
                            refsWithParents.push({ ref, parentChain });
                        } else {
                            refsWithoutParents.push(ref);
                        }
                    }

                    html += '<div class="ref-type-list">';
                    html += renderConsolidatedDepTree(refsWithParents, refsWithoutParents);
                    html += '</div>';
                } else {
                    html += `<div class="ref-type-list">
                        ${refs.map(ref => `
                            <div class="ref-item ${ref.isDependencyRule || ref.isEscalationRule ? 'dep-rule-item' : ''}" onclick="Explorer.navigateToObjectByIndex(${ref.object.global_index})">
                                ${ref.isDependencyRule ?
                                    '<span class="dep-rule-badge">rule</span>' :
                                    ref.isEscalationRule ?
                                    '<span class="dep-rule-badge esc-badge">esc</span>' : ''
                                }
                                <span class="ref-type-badge type-${ref.object.object_type}">${ref.object.object_type}</span>
                                <span class="ref-name" title="${Explorer.escapeHtml(getStagedDisplayName(ref.object))}">${Explorer.escapeHtml(getStagedDisplayName(ref.object))}</span>
                                ${ref.isDependencyRule ?
                                    `<span class="ref-field">${formatFailureCriteria(ref.object)}</span>` :
                                    ref.isEscalationRule ?
                                    `<span class="ref-field">${formatEscalationInfo(ref.object)}</span>` : ''
                                }
                            </div>
                        `).join('')}
                    </div>`;
                }

                html += '</div>';
            }
            return html;
        }

        // Render dependencies section
        const dependenciesSection = document.getElementById('dependenciesSection');
        if (outgoing.length === 0) {
            if (dependenciesSection) dependenciesSection.style.display = 'none';
            dependenciesContainer.innerHTML = '';
        } else {
            if (dependenciesSection) dependenciesSection.style.display = 'block';
            dependenciesContainer.innerHTML = renderGroupedItems(outgoing);
        }

        // Render dependents section
        const dependentsSection = document.getElementById('dependentsSection');
        if (incoming.length === 0) {
            if (dependentsSection) dependentsSection.style.display = 'none';
            dependentsContainer.innerHTML = '';
        } else {
            if (dependentsSection) dependentsSection.style.display = 'block';
            dependentsContainer.innerHTML = renderGroupedItems(incoming);
        }
    }

    // =============================================================================
    // MEMBERS SECTION
    // =============================================================================

    /**
     * Load members for a group or template object.
     */
    function loadCenterMembers(obj) {
        const container = document.getElementById('membersContent');
        const objName = getEffectiveName(obj);
        const objEffectiveAttrs = Explorer.getEffectiveAttributes(obj);
        const members = [];

        function getHostgroupHosts(hostgroup, visited = new Set(), viaLabel = 'members') {
            if (visited.has(hostgroup.global_index)) return [];
            visited.add(hostgroup.global_index);

            const hosts = [];
            const attrs = getEffectiveAttrs(hostgroup);

            const directMembers = (attrs.members || '').split(',').map(x => x.trim()).filter(x => x);
            directMembers.forEach(m => {
                const host = state.allObjects.find(o => o.object_type === 'host' && getEffectiveName(o) === m);
                if (host && !hosts.find(h => h.object.global_index === host.global_index)) {
                    hosts.push({ object: host, via: viaLabel });
                }
            });

            const hgName = getEffectiveName(hostgroup);
            state.allObjects.filter(o => o.object_type === 'host').forEach(host => {
                const hostAttrs = getEffectiveAttrs(host);
                const hgs = (hostAttrs.hostgroups || '').split(',').map(x => x.trim().replace(/^[+!]+/, '').trim());
                if (hgs.includes(hgName) && !hosts.find(h => h.object.global_index === host.global_index)) {
                    hosts.push({ object: host, via: viaLabel === 'members' ? 'hostgroups attr' : viaLabel });
                }
            });

            const nestedGroups = (attrs.hostgroup_members || '').split(',').map(x => x.trim().replace(/^[+!]+/, '').trim()).filter(x => x);
            nestedGroups.forEach(groupName => {
                const nestedGroup = state.allObjects.find(o =>
                    o.object_type === 'hostgroup' && getEffectiveName(o) === groupName
                );
                if (nestedGroup) {
                    const nestedHosts = getHostgroupHosts(nestedGroup, new Set(visited), `via ${groupName}`);
                    nestedHosts.forEach(h => {
                        if (!hosts.find(existing => existing.object.global_index === h.object.global_index)) {
                            hosts.push(h);
                        }
                    });
                }
            });

            return hosts;
        }

        if (obj.object_type === 'hostgroup') {
            const allHosts = getHostgroupHosts(obj);
            allHosts.forEach(h => members.push(h));
        } else if (obj.object_type === 'contactgroup') {
            function getContactgroupContacts(contactgroup, visited = new Set(), viaLabel = 'members') {
                if (visited.has(contactgroup.global_index)) return [];
                visited.add(contactgroup.global_index);

                const contacts = [];
                const attrs = getEffectiveAttrs(contactgroup);

                const directMembers = (attrs.members || '').split(',')
                    .map(x => x.trim().replace(/^[+!]+/, '').trim())
                    .filter(x => x);
                directMembers.forEach(m => {
                    const contact = state.allObjects.find(o => o.object_type === 'contact' && getEffectiveName(o) === m);
                    if (contact && !contacts.find(c => c.object.global_index === contact.global_index)) {
                        contacts.push({ object: contact, via: viaLabel });
                    }
                });

                const cgName = getEffectiveName(contactgroup);
                state.allObjects.filter(o => o.object_type === 'contact').forEach(contact => {
                    const contactAttrs = getEffectiveAttrs(contact);
                    const cgs = (contactAttrs.contactgroups || '').split(',')
                        .map(x => x.trim().replace(/^[+!]+/, '').trim())
                        .filter(x => x);
                    if (cgs.includes(cgName) && !contacts.find(c => c.object.global_index === contact.global_index)) {
                        contacts.push({ object: contact, via: viaLabel === 'members' ? 'contactgroups attr' : viaLabel });
                    }
                });

                const nestedGroups = (attrs.contactgroup_members || '').split(',')
                    .map(x => x.trim().replace(/^[+!]+/, '').trim())
                    .filter(x => x);
                nestedGroups.forEach(groupName => {
                    const nestedGroup = state.allObjects.find(o =>
                        o.object_type === 'contactgroup' && getEffectiveName(o) === groupName
                    );
                    if (nestedGroup) {
                        const nestedContacts = getContactgroupContacts(nestedGroup, new Set(visited), `via ${groupName}`);
                        nestedContacts.forEach(c => {
                            if (!contacts.find(existing => existing.object.global_index === c.object.global_index)) {
                                contacts.push(c);
                            }
                        });
                    }
                });

                return contacts;
            }

            const allContacts = getContactgroupContacts(obj);
            allContacts.forEach(c => members.push(c));
        } else if (obj.object_type === 'servicegroup') {
            function getServicegroupServices(servicegroup, visited = new Set(), viaLabel = 'members') {
                if (visited.has(servicegroup.global_index)) return [];
                visited.add(servicegroup.global_index);

                const services = [];
                const attrs = getEffectiveAttrs(servicegroup);

                const directMembers = (attrs.members || '').split(',')
                    .map(x => x.trim().replace(/^[+!]+/, '').trim())
                    .filter(x => x);
                directMembers.forEach(m => {
                    const svc = state.allObjects.find(o => o.object_type === 'service' && getEffectiveName(o) === m);
                    if (svc && !services.find(s => s.object.global_index === svc.global_index)) {
                        services.push({ object: svc, via: viaLabel });
                    }
                });

                const sgName = getEffectiveName(servicegroup);
                state.allObjects.filter(o => o.object_type === 'service').forEach(svc => {
                    const svcAttrs = getEffectiveAttrs(svc);
                    const sgs = (svcAttrs.servicegroups || '').split(',')
                        .map(x => x.trim().replace(/^[+!]+/, '').trim())
                        .filter(x => x);
                    if (sgs.includes(sgName) && !services.find(s => s.object.global_index === svc.global_index)) {
                        services.push({ object: svc, via: viaLabel === 'members' ? 'servicegroups attr' : viaLabel });
                    }
                });

                const nestedGroups = (attrs.servicegroup_members || '').split(',')
                    .map(x => x.trim().replace(/^[+!]+/, '').trim())
                    .filter(x => x);
                nestedGroups.forEach(groupName => {
                    const nestedGroup = state.allObjects.find(o =>
                        o.object_type === 'servicegroup' && getEffectiveName(o) === groupName
                    );
                    if (nestedGroup) {
                        const nestedServices = getServicegroupServices(nestedGroup, new Set(visited), `via ${groupName}`);
                        nestedServices.forEach(s => {
                            if (!services.find(existing => existing.object.global_index === s.object.global_index)) {
                                services.push(s);
                            }
                        });
                    }
                });

                return services;
            }

            const allServices = getServicegroupServices(obj);
            allServices.forEach(s => members.push(s));
        } else if (Explorer.isObjectTemplate(obj)) {
            state.allObjects.forEach(o => {
                if (o.global_index === obj.global_index) return;
                if (o.object_type === obj.object_type && getEffectiveName(o) === objName) return;

                const attrs = getEffectiveAttrs(o);
                const uses = (attrs.use || '').split(',').map(x => x.trim());
                if (uses.includes(objName) || uses.includes(objEffectiveAttrs.name)) {
                    members.push({ object: o, via: 'inherits' });
                }
            });
        }

        renderCenterMembers(members, obj);
    }

    /**
     * Render the members section.
     */
    function renderCenterMembers(members, obj) {
        const container = document.getElementById('membersContent');
        const section = document.getElementById('membersSection');

        if (members.length === 0) {
            if (section) section.style.display = 'none';
            container.innerHTML = '';
            return;
        }

        if (section) section.style.display = 'block';

        const grouped = {};
        members.forEach(m => {
            const type = m.object.object_type;
            if (!grouped[type]) grouped[type] = [];
            grouped[type].push(m);
        });

        let html = '';

        for (const [type, items] of Object.entries(grouped)) {
            html += `
                <div class="ref-type-group">
                    <div class="ref-type-header">${typeLabels[type] || type}</div>
                    <div class="ref-type-list">
                        ${items.map(m => `
                            <div class="ref-item" onclick="Explorer.navigateToObjectByIndex(${m.object.global_index})">
                                <span class="ref-type-badge type-${m.object.object_type}">${m.object.object_type}</span>
                                <span class="ref-name" title="${Explorer.escapeHtml(getStagedDisplayName(m.object))}">${Explorer.escapeHtml(getStagedDisplayName(m.object))}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    // =============================================================================
    // EXPORT TO EXPLORER NAMESPACE
    // =============================================================================

    // Helper functions (used by impact-section.js)
    Explorer.findDependencyObjects = findDependencyObjects;
    Explorer.isHostInHostgroup = isHostInHostgroup;
    Explorer.findEscalationObjects = findEscalationObjects;
    Explorer.formatFailureCriteria = formatFailureCriteria;
    Explorer.formatEscalationInfo = formatEscalationInfo;

    // Center pane functions
    Explorer.loadCenterInheritance = loadCenterInheritance;
    Explorer.buildLocalInheritanceChain = buildLocalInheritanceChain;
    Explorer.renderCenterInheritance = renderCenterInheritance;
    Explorer.loadCenterReferences = loadCenterReferences;
    Explorer.renderCenterReferences = renderCenterReferences;
    Explorer.loadCenterMembers = loadCenterMembers;
    Explorer.renderCenterMembers = renderCenterMembers;

})(window.Explorer);
