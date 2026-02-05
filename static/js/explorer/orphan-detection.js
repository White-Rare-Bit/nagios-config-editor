/**
 * Nagios Bulk Editor - Explorer Orphan Detection Module
 *
 * Handles orphan status computation and caching for objects.
 * An orphan is an object not referenced by any other object.
 * Extracted from app.js to reduce complexity.
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // Cache for orphan status (recomputed when pending edits change)
    let orphanCache = null;

    function invalidateOrphanCache() {
        orphanCache = null;
    }

    function buildOrphanCache() {
        if (orphanCache) return orphanCache;

        orphanCache = new Set();

        // Build a set of all referenced names by type
        const referencedNames = {
            host: new Set(),
            hostgroup: new Set(),
            service: new Set(),
            servicegroup: new Set(),
            contact: new Set(),
            contactgroup: new Set(),
            command: new Set(),
            timeperiod: new Set()
        };

        // Scan all objects for references (using effective attrs to include pending edits)
        state.allObjects.forEach(obj => {
            const attrs = Explorer.getEffectiveAttributes(obj);

            // Template references (use)
            if (attrs.use) {
                attrs.use.split(',').forEach(t => {
                    const name = t.trim();
                    if (name) referencedNames[obj.object_type]?.add(name);
                });
            }

            // Helper to strip +/! prefixes used in Nagios for additive/exclusion syntax
            const stripPrefix = s => s.trim().replace(/^[+!]+/, '').trim();

            // Host references
            if (attrs.host_name) {
                attrs.host_name.split(',').forEach(h => referencedNames.host.add(stripPrefix(h)));
            }
            if (attrs.parents) {
                attrs.parents.split(',').forEach(h => referencedNames.host.add(stripPrefix(h)));
            }

            // Hostgroup references
            if (attrs.hostgroup_name) {
                attrs.hostgroup_name.split(',').forEach(h => referencedNames.hostgroup.add(stripPrefix(h)));
            }
            if (attrs.hostgroups) {
                attrs.hostgroups.split(',').forEach(h => referencedNames.hostgroup.add(stripPrefix(h)));
            }
            if (attrs.hostgroup_members) {
                attrs.hostgroup_members.split(',').forEach(h => referencedNames.hostgroup.add(stripPrefix(h)));
            }

            // Service references (for dependencies)
            if (attrs.dependent_service_description) {
                referencedNames.service.add(stripPrefix(attrs.dependent_service_description));
            }

            // Servicegroup references
            if (attrs.servicegroups) {
                attrs.servicegroups.split(',').forEach(s => referencedNames.servicegroup.add(stripPrefix(s)));
            }
            if (attrs.servicegroup_members) {
                attrs.servicegroup_members.split(',').forEach(s => referencedNames.servicegroup.add(stripPrefix(s)));
            }

            // Contact references
            if (attrs.contacts) {
                attrs.contacts.split(',').forEach(c => referencedNames.contact.add(stripPrefix(c)));
            }
            if (attrs.members && obj.object_type === 'contactgroup') {
                attrs.members.split(',').forEach(c => referencedNames.contact.add(stripPrefix(c)));
            }

            // Contactgroup references
            if (attrs.contact_groups) {
                attrs.contact_groups.split(',').forEach(c => referencedNames.contactgroup.add(stripPrefix(c)));
            }
            if (attrs.contactgroup_members) {
                attrs.contactgroup_members.split(',').forEach(c => referencedNames.contactgroup.add(stripPrefix(c)));
            }

            // Command references
            ['check_command', 'event_handler', 'notification_commands'].forEach(field => {
                if (attrs[field]) {
                    attrs[field].split(',').forEach(cmd => {
                        const cmdName = cmd.trim().split('!')[0]; // Remove args
                        if (cmdName) referencedNames.command.add(cmdName);
                    });
                }
            });

            // Timeperiod references
            ['check_period', 'notification_period', 'host_notification_period', 'service_notification_period'].forEach(field => {
                if (attrs[field]) {
                    referencedNames.timeperiod.add(attrs[field].trim());
                }
            });

            // Hostgroup members (hosts in the group)
            if (attrs.members && obj.object_type === 'hostgroup') {
                attrs.members.split(',').forEach(h => referencedNames.host.add(stripPrefix(h)));
            }

            // Helper to check if an attribute exists in object or template chain
            function hasAttrInTemplateChain(objAttrs, objType, attrName, visited = new Set()) {
                if (objAttrs[attrName]) return true;
                if (!objAttrs.use) return false;
                const usedTpls = objAttrs.use.split(',').map(s => s.trim());
                for (const tplName of usedTpls) {
                    if (visited.has(tplName)) continue;
                    visited.add(tplName);
                    const tpl = state.allObjects.find(o => o.attributes.name === tplName && o.attributes.register === '0' && o.object_type === objType);
                    if (tpl) {
                        if (tpl.attributes[attrName]) return true;
                        if (hasAttrInTemplateChain(tpl.attributes, objType, attrName, visited)) return true;
                    }
                }
                return false;
            }

            // Fix #1: Hosts with 'hostgroups' attribute (direct or inherited) are in use
            // Mark them as referenced so they're not flagged as orphans
            if (obj.object_type === 'host' && hasAttrInTemplateChain(attrs, 'host', 'hostgroups')) {
                const hostName = Explorer.getEffectiveName(obj);
                if (hostName) {
                    referencedNames.host.add(hostName.trim());
                }
            }

            // Fix #2: Services with valid host_name or hostgroup_name (direct or inherited) are actively monitoring
            // They shouldn't be considered orphans just because nothing references them
            if (obj.object_type === 'service' && (hasAttrInTemplateChain(attrs, 'service', 'host_name') || hasAttrInTemplateChain(attrs, 'service', 'hostgroup_name'))) {
                const serviceName = Explorer.getEffectiveName(obj);
                if (serviceName) {
                    referencedNames.service.add(serviceName.trim());
                }
            }

            // Fix #3: Services with 'servicegroups' attribute (direct or inherited) are in use
            if (obj.object_type === 'service' && hasAttrInTemplateChain(attrs, 'service', 'servicegroups')) {
                const serviceName = Explorer.getEffectiveName(obj);
                if (serviceName) {
                    referencedNames.service.add(serviceName.trim());
                }
            }
        });

        // Now find orphans - objects not referenced by anything
        state.allObjects.forEach(obj => {
            // Use effective name (considering pending edits)
            const effectiveName = Explorer.getEffectiveName(obj);
            const attrs = Explorer.getEffectiveAttributes(obj);
            const attrName = attrs.name;

            // Check if this object is referenced
            const refs = referencedNames[obj.object_type];
            if (!refs) return; // Unknown type, skip

            const isReferenced = refs.has(effectiveName) || (attrName && refs.has(attrName));

            if (!isReferenced) {
                orphanCache.add(obj.global_index);
            }
        });

        return orphanCache;
    }

    function isObjectOrphan(obj) {
        const cache = buildOrphanCache();
        return cache.has(obj.global_index);
    }

    // Export to Explorer namespace
    Explorer.invalidateOrphanCache = invalidateOrphanCache;
    Explorer.buildOrphanCache = buildOrphanCache;
    Explorer.isObjectOrphan = isObjectOrphan;

})(window.Explorer);
