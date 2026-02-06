/**
 * Nagios Bulk Editor - Explorer Constants Module
 *
 * Centralized configuration and constants for the explorer.
 * Extracted from main.js to reduce complexity.
 */

(function(Explorer) {
    'use strict';

    Explorer.constants = {
        // Type display labels
        typeLabels: {
            host: 'Hosts',
            service: 'Services',
            hostgroup: 'Host Groups',
            servicegroup: 'Service Groups',
            contact: 'Contacts',
            contactgroup: 'Contact Groups',
            command: 'Commands',
            timeperiod: 'Time Periods',
            servicedependency: 'Service Dependencies',
            hostdependency: 'Host Dependencies',
            serviceescalation: 'Service Escalations',
            hostescalation: 'Host Escalations'
        },

        // Fields that define the object identity
        identityFields: {
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
        },

        // Attributes that affect inheritance/reference sections
        inheritanceAttrs: ['use', 'parents'],
        referenceAttrs: [
            'use', 'parents', 'hostgroups', 'servicegroups', 'contactgroups',
            'contact_groups', 'host_name', 'hostgroup_name', 'check_command',
            'event_handler', 'check_period', 'notification_period', 'contacts', 'members'
        ],

        // Name fields by object type (populated from /api/constants)
        nameFields: {},

        // Notification options
        HOST_NOTIFICATION_OPTIONS: [
            'd - Down', 'u - Unreachable', 'r - Recovery',
            'f - Flapping', 's - Scheduled Downtime', 'n - None'
        ],
        SERVICE_NOTIFICATION_OPTIONS: [
            'w - Warning', 'u - Unknown', 'c - Critical', 'r - Recovery',
            'f - Flapping', 's - Scheduled Downtime', 'n - None'
        ],
        NOTIFICATION_OPTION_ATTRS: [
            'notification_options', 'host_notification_options', 'service_notification_options',
            'execution_failure_criteria', 'notification_failure_criteria',
            'escalation_options', 'stalking_options'
        ],

        // Dependency failure criteria options
        HOST_FAILURE_CRITERIA: [
            'o - Up (OK)', 'd - Down', 'u - Unreachable', 'p - Pending', 'n - None'
        ],
        SERVICE_FAILURE_CRITERIA: [
            'o - OK', 'w - Warning', 'u - Unknown', 'c - Critical', 'p - Pending', 'n - None'
        ],

        // Required fields per object type (populated from /api/constants)
        REQUIRED_FIELDS: {},

        // Reference fields for dependency detection (populated from /api/constants)
        referenceFields: {},

        // Attribute reference map (for autocomplete hints)
        ATTR_REFERENCE_MAP: {
            'hostgroup_name': 'hostgroup',
            'hostgroups': 'hostgroup',
            'hostgroup_members': 'hostgroup',
            'parents': 'host',
            'members': null,
            'servicegroups': 'servicegroup',
            'servicegroup_name': 'servicegroup',
            'servicegroup_members': 'servicegroup',
            'contacts': 'contact',
            'contact_groups': 'contactgroup',
            'contactgroups': 'contactgroup',
            'contactgroup_members': 'contactgroup',
            'check_command': 'command',
            'event_handler': 'command',
            'host_notification_commands': 'command',
            'service_notification_commands': 'command',
            'check_period': 'timeperiod',
            'notification_period': 'timeperiod',
            'host_notification_period': 'timeperiod',
            'service_notification_period': 'timeperiod',
            'dependency_period': 'timeperiod',
            'escalation_period': 'timeperiod',
            'use': null,
            'dependent_host_name': 'host',
            'dependent_hostgroup_name': 'hostgroup'
        }
    };

})(window.Explorer);
