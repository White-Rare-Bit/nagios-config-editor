/**
 * Nagios Bulk Editor - Explorer Constants Module
 *
 * Initially empty shells populated by /api/metadata at startup.
 * Fallback defaults ensure the explorer works if metadata hasn't loaded yet.
 */

(function(Explorer) {
    'use strict';

    // Identity fields are UI-only (not in backend model) — keep hardcoded
    const IDENTITY_FIELDS = {
        host: ['host_name', 'alias', 'display_name', 'address', 'name'],
        hostgroup: ['hostgroup_name', 'alias', 'name'],
        service: ['service_description', 'alias', 'display_name', 'name'],
        servicegroup: ['servicegroup_name', 'alias', 'name'],
        contact: ['contact_name', 'alias', 'name'],
        contactgroup: ['contactgroup_name', 'alias', 'name'],
        command: ['command_name', 'command_line', 'name'],
        timeperiod: ['timeperiod_name', 'alias', 'name'],
        servicedependency: ['name'],
        hostdependency: ['name'],
        serviceescalation: ['name'],
        hostescalation: ['name']
    };

    // Short badge abbreviations for tree view
    const TYPE_BADGES = {
        host: 'HOST',
        hostgroup: 'HOSTGRP',
        service: 'SVC',
        servicegroup: 'SVCGRP',
        contact: 'CONT',
        contactgroup: 'CONTGRP',
        command: 'CMD',
        timeperiod: 'TP',
        servicedependency: 'SVCDEP',
        hostdependency: 'HOSTDEP',
        serviceescalation: 'SVCESC',
        hostescalation: 'HOSTESC'
    };

    const TEMPLATE_BADGES = {
        host: 'HOSTTMPL',
        service: 'SVCTMPL',
        contact: 'CONTTMPL',
        command: 'CMDTMPL',
        timeperiod: 'TPTMPL'
    };

    // Attributes that affect inheritance/reference sections (UI behavior)
    const INHERITANCE_ATTRS = ['use', 'parents'];
    const REFERENCE_TRIGGER_ATTRS = [
        'use', 'parents', 'hostgroups', 'servicegroups', 'contactgroups',
        'contact_groups', 'host_name', 'hostgroup_name', 'check_command',
        'event_handler', 'check_period', 'notification_period', 'contacts', 'members'
    ];

    Explorer.constants = {
        // --- Populated by /api/metadata ---
        typeLabels: {},
        nameFields: {},
        REQUIRED_FIELDS: {},
        referenceFields: {},
        ATTR_REFERENCE_MAP: {},
        NAGIOS_ATTRIBUTES: {},
        defaultAttributes: {},
        notificationOptions: {},
        groupStructure: {},

        // --- UI-only constants (not from backend) ---
        identityFields: IDENTITY_FIELDS,
        typeBadges: TYPE_BADGES,
        templateBadges: TEMPLATE_BADGES,
        inheritanceAttrs: INHERITANCE_ATTRS,
        referenceAttrs: REFERENCE_TRIGGER_ATTRS,

        // Notification option accessors (populated by applyMetadata)
        HOST_NOTIFICATION_OPTIONS: [],
        SERVICE_NOTIFICATION_OPTIONS: [],
        NOTIFICATION_OPTION_ATTRS: [],
        HOST_FAILURE_CRITERIA: [],
        SERVICE_FAILURE_CRITERIA: [],
        HOST_STALKING_OPTIONS: [],
        SERVICE_STALKING_OPTIONS: [],
        HOST_FLAP_DETECTION_OPTIONS: [],
        SERVICE_FLAP_DETECTION_OPTIONS: [],
        HOST_ESCALATION_OPTIONS: [],
        SERVICE_ESCALATION_OPTIONS: [],
    };

    /**
     * Populate Explorer.constants from /api/metadata response.
     * Called once at startup from data-loading.js.
     */
    // Mapping from constants key → notification_options API key
    const NOTIFICATION_OPTION_KEYS = [
        'HOST_NOTIFICATION_OPTIONS', 'SERVICE_NOTIFICATION_OPTIONS',
        'NOTIFICATION_OPTION_ATTRS',
        'HOST_FAILURE_CRITERIA', 'SERVICE_FAILURE_CRITERIA',
        'HOST_STALKING_OPTIONS', 'SERVICE_STALKING_OPTIONS',
        'HOST_FLAP_DETECTION_OPTIONS', 'SERVICE_FLAP_DETECTION_OPTIONS',
        'HOST_ESCALATION_OPTIONS', 'SERVICE_ESCALATION_OPTIONS',
    ];

    function applyNotificationOptions(c, opts) {
        for (const key of NOTIFICATION_OPTION_KEYS) {
            const apiKey = key.toLowerCase();
            c[key] = opts[apiKey] || [];
        }
    }

    function buildAttrReferenceMap(c) {
        const nameFieldValues = new Set(Object.values(c.nameFields));
        c.ATTR_REFERENCE_MAP = {};
        for (const [field, type] of Object.entries(c.referenceFields)) {
            if (!nameFieldValues.has(field) || field === 'host_name') {
                c.ATTR_REFERENCE_MAP[field] = type;
            }
        }
    }

    Explorer.applyMetadata = function(meta) {
        const c = Explorer.constants;

        c.typeLabels = meta.object_type_labels || c.typeLabels;
        c.nameFields = meta.name_fields || c.nameFields;
        c.REQUIRED_FIELDS = meta.required_fields || c.REQUIRED_FIELDS;
        c.referenceFields = meta.reference_fields || c.referenceFields;
        c.NAGIOS_ATTRIBUTES = meta.valid_attributes || c.NAGIOS_ATTRIBUTES;
        c.defaultAttributes = meta.default_attributes || c.defaultAttributes;
        c.groupStructure = meta.group_structure || c.groupStructure;

        buildAttrReferenceMap(c);
        applyNotificationOptions(c, meta.notification_options || {});
    };

    /**
     * Detect if an object is a template.
     * Shared implementation — do not duplicate in other modules.
     */
    Explorer.isObjectTemplate = function(obj) {
        if (!obj || !obj.attributes) {return false;}
        if (obj.attributes.register === '0') {return true;}
        const nameField = Explorer.constants.nameFields[obj.object_type];
        return Boolean(obj.attributes.name && nameField && !obj.attributes[nameField]);
    };

    /**
     * Get abbreviated badge text for an object type.
     * @param {string} objectType - e.g. 'host', 'service'
     * @param {boolean} [isTemplate=false] - whether this is a template
     * @returns {string} abbreviated badge text e.g. 'HOST', 'SVCTMPL'
     */
    Explorer.getTypeBadge = function(objectType, isTemplate) {
        const c = Explorer.constants;
        if (isTemplate && c.templateBadges[objectType]) {
            return c.templateBadges[objectType];
        }
        return c.typeBadges[objectType] || objectType;
    };

    /**
     * Get all field names that reference a given object type.
     * Example: getFieldsForType('command') returns ['check_command', 'event_handler', ...]
     */
    Explorer.getFieldsForType = function(targetType) {
        const fields = [];
        for (const [field, type] of Object.entries(Explorer.constants.referenceFields)) {
            if (type === targetType) {fields.push(field);}
        }
        return fields;
    };

    /**
     * Strip Nagios additive/exclusion prefixes (+/!) from a value.
     * Shared implementation — do not duplicate in other modules.
     */
    Explorer.stripPrefix = function(val) {
        return val.trim().replace(/^[+!]+/, '').trim();
    };

    // D-01: Object types whose identity is scoped by host (composite key).
    // Mirrors health_checks.py host_scoped_types.
    const HOST_SCOPED_TYPES = new Set(['service', 'serviceescalation', 'servicedependency']);

    /**
     * Check whether a name would be a duplicate for the given object type.
     * For host-scoped types (service, serviceescalation, servicedependency),
     * uses composite key (name + host_name/hostgroup_name).
     *
     * @param {string} objectType - e.g. 'host', 'service'
     * @param {string} name - the name value to check
     * @param {Object} attributes - full attributes of the object being checked
     * @param {number|null} [excludeStagedIndex=null] - staged creation index to skip
     * @returns {{isDuplicate: boolean, location: string}} result
     */
    Explorer.checkDuplicateName = function(objectType, name, attributes, excludeStagedIndex) {
        if (!name) {return {isDuplicate: false, location: ''};}

        const state = Explorer.state;
        const c = Explorer.constants;
        const nameField = c.nameFields[objectType] || 'name';
        const isHostScoped = HOST_SCOPED_TYPES.has(objectType);
        const hostScope = isHostScoped
            ? (attributes.host_name || attributes.hostgroup_name || '')
            : '';

        // Check against existing on-disk objects
        const existingObj = state.allObjects.find(obj => {
            if (obj.object_type !== objectType) {return false;}
            const objName = obj.attributes?.[nameField] || obj.attributes?.name || '';
            if (objName !== name) {return false;}
            if (isHostScoped) {
                const objHost = obj.attributes?.host_name || obj.attributes?.hostgroup_name || '';
                return objHost === hostScope;
            }
            return true;
        });
        if (existingObj) {
            const file = (existingObj.source_file || '').split('/').pop();
            return {isDuplicate: true, location: file};
        }

        // Check against other staged creations
        const dupStaged = state.stagedCreations.findIndex((sc, idx) => {
            if (idx === excludeStagedIndex) {return false;}
            if (sc.object_type !== objectType) {return false;}
            if (sc.displayName !== name) {return false;}
            if (isHostScoped) {
                const scHost = sc.attributes?.host_name || sc.attributes?.hostgroup_name || '';
                return scHost === hostScope;
            }
            return true;
        });
        if (dupStaged !== -1) {
            return {isDuplicate: true, location: 'staged'};
        }

        return {isDuplicate: false, location: ''};
    };

})(window.Explorer);
