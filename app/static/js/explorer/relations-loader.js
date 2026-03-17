/**
 * Relations Loader Module
 *
 * Provides helper functions for relationship analysis:
 * - buildLocalInheritanceChain: builds template ancestry chains (used by impact-section.js)
 * - formatFailureCriteria / formatEscalationInfo: compact display strings for dependencies
 */

import { state } from './state.js';
import { getEffectiveAttributes, getEffectiveName } from './app.js'; // circular — safe (function-level)
import { isObjectTemplate } from './constants.js';
import { parseCommaValues } from './main.js';

// =============================================================================
// FORMAT HELPERS
// =============================================================================

/**
 * Format failure criteria from dependency object into compact display string.
 */
export function formatFailureCriteria(depObj) {
    const attrs = getEffectiveAttributes(depObj);
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
export function formatEscalationInfo(escObj) {
    const attrs = getEffectiveAttributes(escObj);
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
 * Build inheritance chain locally for new objects.
 */
export function buildLocalInheritanceChain(obj, templateNames) {
    const chain = {
        name: obj.display_name || '(new object)',
        object_type: obj.object_type,
        is_template: isObjectTemplate(obj),
        parents: []
    };

    function findTemplate(name, objType) {
        return state.allObjects.find(o =>
            o.object_type === objType &&
            (o.attributes.name === name || o.name === name || o.display_name === name)
        );
    }

    function buildParentChain(parentNames, objType, visited = new Set()) {
        const parents = [];
        for (const name of parentNames) {
            if (visited.has(name)) {
                parents.push({
                    name: name,
                    object_type: objType,
                    is_template: true,
                    error: 'Circular dependency'
                });
                continue;
            }
            const template = findTemplate(name, objType);
            if (template) {
                const nextVisited = new Set(visited);
                nextVisited.add(name);
                const templateUse = parseCommaValues(template.attributes.use || '');
                parents.push({
                    name: getEffectiveName(template),
                    object_type: template.object_type,
                    is_template: true,
                    file: template.source_file,
                    parents: buildParentChain(templateUse, objType, nextVisited)
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

    // Seed visited set with the current object's name to detect self-reference
    const selfNames = new Set();
    const objName = obj.display_name || obj.name || obj.attributes?.name;
    if (objName) {selfNames.add(objName);}
    chain.parents = buildParentChain(templateNames, obj.object_type, selfNames);
    return chain;
}
