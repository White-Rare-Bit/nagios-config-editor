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

        // Name fields by object type (must stay in sync with nagios_model.py:NAME_FIELDS)
        // N-01: Added dependency and escalation object types
        nameFields: {
            host: 'host_name',
            hostgroup: 'hostgroup_name',
            service: 'service_description',
            servicegroup: 'servicegroup_name',
            contact: 'contact_name',
            contactgroup: 'contactgroup_name',
            command: 'command_name',
            timeperiod: 'timeperiod_name',
            servicedependency: 'service_description',
            hostdependency: 'host_name',
            serviceescalation: 'service_description',
            hostescalation: 'host_name'
        },

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

        // Required fields per object type (sync with nagios_model.py:REQUIRED_FIELDS)
        // String: field is required; Array: at least one must be present (OR condition)
        REQUIRED_FIELDS: {
            'host': ['host_name'],
            'hostgroup': ['hostgroup_name'],
            'service': ['service_description', ['host_name', 'hostgroup_name']],
            'servicegroup': ['servicegroup_name'],
            'contact': ['contact_name'],
            'contactgroup': ['contactgroup_name'],
            'command': ['command_name', 'command_line'],
            'timeperiod': ['timeperiod_name'],
            'hostdependency': [['host_name', 'hostgroup_name'], ['dependent_host_name', 'dependent_hostgroup_name']],
            'servicedependency': [
                'service_description', ['host_name', 'hostgroup_name'],
                'dependent_service_description', ['dependent_host_name', 'dependent_hostgroup_name']
            ],
            'hostescalation': [['host_name', 'hostgroup_name']],
            'serviceescalation': ['service_description', ['host_name', 'hostgroup_name']]
        },

        // Reference fields for dependency detection (sync with nagios_model.py:REFERENCE_FIELDS)
        // Used by app.js for outgoing/incoming reference tracking
        referenceFields: {
            // Host references
            'host_name': 'host',
            'parents': 'host',
            'dependent_host_name': 'host',
            'master_host_name': 'host',
            // Hostgroup references
            'hostgroup_name': 'hostgroup',
            'hostgroups': 'hostgroup',
            'hostgroup_members': 'hostgroup',
            'dependent_hostgroup_name': 'hostgroup',
            'master_hostgroup_name': 'hostgroup',
            // Servicegroup references
            'servicegroups': 'servicegroup',
            'servicegroup_name': 'servicegroup',
            'servicegroup_members': 'servicegroup',
            // Contact references
            'contacts': 'contact',
            'escalation_contacts': 'contact',
            // Contactgroup references
            'contact_groups': 'contactgroup',
            'contactgroups': 'contactgroup',
            'contactgroup_members': 'contactgroup',
            'escalation_contact_groups': 'contactgroup',
            // Command references (N-05: Synced with nagios_model.py)
            'check_command': 'command',
            'event_handler': 'command',
            'notification_commands': 'command',
            'host_notification_commands': 'command',
            'service_notification_commands': 'command',
            'obsess_over_host_command': 'command',
            'obsess_over_service_command': 'command',
            'ocsp_command': 'command',
            'ochp_command': 'command',
            'global_host_event_handler': 'command',
            'global_service_event_handler': 'command',
            // Timeperiod references
            'check_period': 'timeperiod',
            'notification_period': 'timeperiod',
            'host_notification_period': 'timeperiod',
            'service_notification_period': 'timeperiod',
            'dependency_period': 'timeperiod',
            'escalation_period': 'timeperiod',
            'exclude': 'timeperiod',
            // Template references (type depends on context)
            'use': null,
            // Group members (type depends on context)
            'members': null
        },

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
