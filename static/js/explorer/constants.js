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
    Explorer.applyMetadata = function(meta) {
        const c = Explorer.constants;

        c.typeLabels = meta.object_type_labels || c.typeLabels;
        c.nameFields = meta.name_fields || c.nameFields;
        c.REQUIRED_FIELDS = meta.required_fields || c.REQUIRED_FIELDS;
        c.referenceFields = meta.reference_fields || c.referenceFields;
        c.NAGIOS_ATTRIBUTES = meta.valid_attributes || c.NAGIOS_ATTRIBUTES;
        c.defaultAttributes = meta.default_attributes || c.defaultAttributes;
        c.groupStructure = meta.group_structure || c.groupStructure;

        // Build ATTR_REFERENCE_MAP from referenceFields (same data, used for autocomplete)
        // Exclude fields that are also name fields (they refer to the object itself)
        const nameFieldValues = new Set(Object.values(c.nameFields));
        c.ATTR_REFERENCE_MAP = {};
        for (const [field, type] of Object.entries(c.referenceFields)) {
            // Include fields useful for autocomplete hints
            if (!nameFieldValues.has(field) || field === 'host_name') {
                c.ATTR_REFERENCE_MAP[field] = type;
            }
        }

        // Notification options
        const opts = meta.notification_options || {};
        c.HOST_NOTIFICATION_OPTIONS = opts.host_notification_options || [];
        c.SERVICE_NOTIFICATION_OPTIONS = opts.service_notification_options || [];
        c.NOTIFICATION_OPTION_ATTRS = opts.notification_option_attrs || [];
        c.HOST_FAILURE_CRITERIA = opts.host_failure_criteria || [];
        c.SERVICE_FAILURE_CRITERIA = opts.service_failure_criteria || [];
        c.HOST_STALKING_OPTIONS = opts.host_stalking_options || [];
        c.SERVICE_STALKING_OPTIONS = opts.service_stalking_options || [];
        c.HOST_FLAP_DETECTION_OPTIONS = opts.host_flap_detection_options || [];
        c.SERVICE_FLAP_DETECTION_OPTIONS = opts.service_flap_detection_options || [];
        c.HOST_ESCALATION_OPTIONS = opts.host_escalation_options || [];
        c.SERVICE_ESCALATION_OPTIONS = opts.service_escalation_options || [];
    };

    /**
     * Detect if an object is a template.
     * Shared implementation — do not duplicate in other modules.
     */
    Explorer.isObjectTemplate = function(obj) {
        if (obj.attributes.register === '0') return true;
        const nameField = Explorer.constants.nameFields[obj.object_type];
        return !!(obj.attributes.name && nameField && !obj.attributes[nameField]);
    };

    /**
     * Get all field names that reference a given object type.
     * Example: getFieldsForType('command') returns ['check_command', 'event_handler', ...]
     */
    Explorer.getFieldsForType = function(targetType) {
        const fields = [];
        for (const [field, type] of Object.entries(Explorer.constants.referenceFields)) {
            if (type === targetType) fields.push(field);
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

})(window.Explorer);
