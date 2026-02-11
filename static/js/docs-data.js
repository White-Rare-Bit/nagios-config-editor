/* Nagios 4 Object Definition Reference Data
 *
 * Source: https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/objectdefinitions.html
 *
 * Structure:
 *   window.NAGIOS_OBJECT_REFERENCE = {
 *     object_type: {
 *       description: "...",
 *       directives: [
 *         { name, required, format, description }
 *       ]
 *     }
 *   }
 *
 * Notes:
 *   - "required" reflects the Nagios 4 docs red/black color coding (red = required).
 *   - Template directives (name, use, register) are common to ALL object types and
 *     listed in the _template_directives key rather than repeated per type.
 *   - The pipe notation "obsess_over_host|obsess" means "obsess" is an accepted alias.
 *   - Contact addressN directives (address1-address6) are listed as "addressX".
 *   - Timeperiod weekday/exception directives are dynamic; representative entries shown.
 */
window.NAGIOS_OBJECT_REFERENCE = {

    _template_directives: {
        description: "These three directives are common to all object definitions and support template-based inheritance.",
        directives: [
            {
                name: "name",
                required: false,
                format: "template_name",
                description: "A name for the object template. This is not a real object; it is used as a source for inheritance by other objects that reference it via the 'use' directive."
            },
            {
                name: "use",
                required: false,
                format: "template_name",
                description: "Specifies the template object whose properties this object should inherit. Multiple templates can be specified as a comma-delimited list."
            },
            {
                name: "register",
                required: false,
                format: "[0/1]",
                description: "Controls whether the object is registered with Nagios. Set to 0 for template-only objects that should not be instantiated. Default is 1 (registered)."
            }
        ]
    },

    host: {
        label: 'Host',
        description: "Defines a physical server, workstation, device, or other network resource to be monitored.",
        directives: [
            {
                name: "host_name",
                required: true,
                format: "host_name",
                description: "A short name used to identify the host. It is used in hostgroup and service definitions to reference this particular host."
            },
            {
                name: "alias",
                required: false,
                format: "alias",
                description: "A longer name or description used to identify the host. It is provided for the purposes of helping identify what the host actually is."
            },
            {
                name: "display_name",
                required: false,
                format: "display_name",
                description: "An alternate name that should be displayed in the web interface. If not specified, the host_name value is used."
            },
            {
                name: "address",
                required: false,
                format: "address",
                description: "The IP address or FQDN of the host. If you don't specify an address, the host_name is used as the address."
            },
            {
                name: "parents",
                required: false,
                format: "host_names",
                description: "A comma-delimited list of short names of hosts that lie between the monitoring host and this host on the network. Used to determine network reachability."
            },
            {
                name: "importance",
                required: false,
                format: "#",
                description: "A numeric value representing the importance of the host to the organization. Used to determine notification priority and for sorting in the web interface."
            },
            {
                name: "hostgroups",
                required: false,
                format: "hostgroup_names",
                description: "A comma-delimited list of short names of hostgroups that the host should be a member of."
            },
            {
                name: "check_command",
                required: false,
                format: "command_name",
                description: "The short name of the command used to check if the host is up or down. A blank value assumes the host is always up."
            },
            {
                name: "initial_state",
                required: false,
                format: "[o,d,u]",
                description: "The initial state Nagios assumes for the host before any checks: o = UP, d = DOWN, u = UNREACHABLE. Default is UP."
            },
            {
                name: "max_check_attempts",
                required: false,
                format: "#",
                description: "The number of times Nagios will retry the check command when it returns a non-OK state before changing to a hard state."
            },
            {
                name: "check_interval",
                required: false,
                format: "#",
                description: "The number of time units between regularly scheduled checks of the host. Time units are typically 60 seconds."
            },
            {
                name: "retry_interval",
                required: false,
                format: "#",
                description: "The number of time units to wait before scheduling a re-check after a soft non-UP state is detected."
            },
            {
                name: "active_checks_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether active checks of this host are enabled. 0 = disabled, 1 = enabled."
            },
            {
                name: "passive_checks_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether passive checks of this host are enabled. 0 = disabled, 1 = enabled."
            },
            {
                name: "check_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which active checks of this host can be made."
            },
            {
                name: "obsess_over_host|obsess",
                required: false,
                format: "[0/1]",
                description: "Determines whether checks for this host will be obsessed over using the OCHP command. Useful for distributed monitoring."
            },
            {
                name: "check_freshness",
                required: false,
                format: "[0/1]",
                description: "Determines whether freshness checks are enabled for this host. Freshness checks ensure passive results are received in a timely manner."
            },
            {
                name: "freshness_threshold",
                required: false,
                format: "#",
                description: "The freshness threshold in seconds for this host. If no passive check result has been received within this time, an active check is forced."
            },
            {
                name: "event_handler",
                required: false,
                format: "command_name",
                description: "The short name of the command that should be run whenever a change in the state of the host is detected (i.e. when it goes down or recovers)."
            },
            {
                name: "event_handler_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether the event handler for this host is enabled. 0 = disabled, 1 = enabled."
            },
            {
                name: "low_flap_threshold",
                required: false,
                format: "#",
                description: "The low state change threshold percentage used in flap detection. If set to 0, the program-wide value is used."
            },
            {
                name: "high_flap_threshold",
                required: false,
                format: "#",
                description: "The high state change threshold percentage used in flap detection. If set to 0, the program-wide value is used."
            },
            {
                name: "flap_detection_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether flap detection is enabled for this host. 0 = disabled, 1 = enabled."
            },
            {
                name: "flap_detection_options",
                required: false,
                format: "[o,d,u]",
                description: "Determines which host states are used in flap detection logic: o = UP, d = DOWN, u = UNREACHABLE."
            },
            {
                name: "process_perf_data",
                required: false,
                format: "[0/1]",
                description: "Determines whether the processing of performance data is enabled for this host. 0 = disabled, 1 = enabled."
            },
            {
                name: "retain_status_information",
                required: false,
                format: "[0/1]",
                description: "Determines whether status-related information about the host is retained across program restarts."
            },
            {
                name: "retain_nonstatus_information",
                required: false,
                format: "[0/1]",
                description: "Determines whether non-status information about the host is retained across program restarts."
            },
            {
                name: "contacts",
                required: false,
                format: "contacts",
                description: "A comma-delimited list of short names of contacts that should be notified whenever there are problems (or recoveries) with this host."
            },
            {
                name: "contact_groups",
                required: false,
                format: "contact_groups",
                description: "A comma-delimited list of short names of contact groups that should be notified whenever there are problems (or recoveries) with this host."
            },
            {
                name: "notification_interval",
                required: false,
                format: "#",
                description: "The number of time units to wait before re-notifying a contact that this host is still down or unreachable. Set to 0 to disable re-notifications."
            },
            {
                name: "first_notification_delay",
                required: false,
                format: "#",
                description: "The number of time units to wait before sending out the first problem notification when the host enters a non-UP state."
            },
            {
                name: "notification_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which notifications of events for this host can be sent out to contacts."
            },
            {
                name: "notification_options",
                required: false,
                format: "[d,u,r,f,s]",
                description: "Determines when notifications should be sent: d = DOWN, u = UNREACHABLE, r = recovery, f = flapping, s = scheduled downtime. Use n for none."
            },
            {
                name: "notifications_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether notifications for this host are enabled. 0 = disabled, 1 = enabled."
            },
            {
                name: "stalking_options",
                required: false,
                format: "[o,d,u,N]",
                description: "Determines which host states are stalked: o = UP, d = DOWN, u = UNREACHABLE, N = include output in notifications."
            },
            {
                name: "notes",
                required: false,
                format: "note_string",
                description: "An optional string of notes pertaining to the host. Used in the extended information CGI."
            },
            {
                name: "notes_url",
                required: false,
                format: "url",
                description: "An optional URL that provides additional information about the host. Macros ($HOSTNAME$, etc.) can be used."
            },
            {
                name: "action_url",
                required: false,
                format: "url",
                description: "An optional URL for actions to be performed on the host (e.g. PNP4Nagios graphs). Macros can be used."
            },
            {
                name: "icon_image",
                required: false,
                format: "image_file",
                description: "The name of a GIF, PNG, or JPG image that should be associated with this host in the CGIs."
            },
            {
                name: "icon_image_alt",
                required: false,
                format: "alt_string",
                description: "An optional string used as the ALT tag for the icon image."
            },
            {
                name: "vrml_image",
                required: false,
                format: "image_file",
                description: "The name of a GIF, PNG, or JPG image used as the texture map for this host in the statuswrl CGI."
            },
            {
                name: "statusmap_image",
                required: false,
                format: "image_file",
                description: "The name of a GIF, PNG, or JPG image that should be associated with this host in the statusmap CGI."
            },
            {
                name: "2d_coords",
                required: false,
                format: "x_coord,y_coord",
                description: "The 2D coordinates (x,y) used when drawing the host in the statusmap CGI. Values are positive integers."
            },
            {
                name: "3d_coords",
                required: false,
                format: "x_coord,y_coord,z_coord",
                description: "The 3D coordinates (x,y,z) used when drawing the host in the statuswrl (VRML) CGI."
            }
        ]
    },

    hostgroup: {
        label: 'Host Group',
        description: "Groups one or more hosts together for simplified configuration and display in the CGIs.",
        directives: [
            {
                name: "hostgroup_name",
                required: true,
                format: "hostgroup_name",
                description: "A short name used to identify the host group."
            },
            {
                name: "alias",
                required: false,
                format: "alias",
                description: "A longer name or description used to identify the host group."
            },
            {
                name: "members",
                required: false,
                format: "hosts",
                description: "A comma-delimited list of short names of hosts that should be included in this group."
            },
            {
                name: "hostgroup_members",
                required: false,
                format: "hostgroups",
                description: "A comma-delimited list of short names of other hostgroups whose members should be included in this group."
            },
            {
                name: "notes",
                required: false,
                format: "note_string",
                description: "An optional string of notes pertaining to the host group."
            },
            {
                name: "notes_url",
                required: false,
                format: "url",
                description: "An optional URL that provides additional information about the host group."
            },
            {
                name: "action_url",
                required: false,
                format: "url",
                description: "An optional URL for actions to be performed on the host group."
            }
        ]
    },

    service: {
        label: 'Service',
        description: "Identifies a service running on or associated with a host, such as a process, port, metric, or resource to be monitored.",
        directives: [
            {
                name: "host_name",
                required: false,
                format: "host_name",
                description: "The short name(s) of the host(s) that this service runs on. Multiple hosts can be specified as a comma-delimited list."
            },
            {
                name: "hostgroup_name",
                required: false,
                format: "hostgroup_name",
                description: "The short name(s) of the hostgroup(s) that this service is associated with. The service is applied to all hosts in the groups."
            },
            {
                name: "service_description",
                required: true,
                format: "service_description",
                description: "A description of the service. It is used as a unique identifier for the service on each host."
            },
            {
                name: "display_name",
                required: false,
                format: "display_name",
                description: "An alternate name that should be displayed in the web interface for this service."
            },
            {
                name: "parents",
                required: false,
                format: "service_descriptions",
                description: "A comma-delimited list of short names of services that this service depends on. Used for dependency definitions."
            },
            {
                name: "importance",
                required: false,
                format: "#",
                description: "A numeric value representing the importance of the service to the organization."
            },
            {
                name: "servicegroups",
                required: false,
                format: "servicegroup_names",
                description: "A comma-delimited list of short names of service groups that this service should be a member of."
            },
            {
                name: "is_volatile",
                required: false,
                format: "[0/1]",
                description: "Designates whether the service is volatile. Volatile services are re-checked and re-notified on every non-OK result."
            },
            {
                name: "check_command",
                required: false,
                format: "command_name",
                description: "The short name of the command used to check the status of the service. Arguments are separated by '!' characters."
            },
            {
                name: "initial_state",
                required: false,
                format: "[o,w,u,c]",
                description: "The initial assumed state of the service: o = OK, w = WARNING, u = UNKNOWN, c = CRITICAL. Default is OK."
            },
            {
                name: "max_check_attempts",
                required: false,
                format: "#",
                description: "The number of times Nagios will retry the check command when it returns a non-OK state before changing to a hard state."
            },
            {
                name: "check_interval",
                required: false,
                format: "#",
                description: "The number of time units to wait between regularly scheduled checks of the service."
            },
            {
                name: "retry_interval",
                required: false,
                format: "#",
                description: "The number of time units to wait before scheduling a re-check after a soft non-OK state is detected."
            },
            {
                name: "active_checks_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether active checks of this service are enabled. 0 = disabled, 1 = enabled."
            },
            {
                name: "passive_checks_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether passive checks of this service are enabled. 0 = disabled, 1 = enabled."
            },
            {
                name: "check_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which active checks of this service can be made."
            },
            {
                name: "obsess_over_service|obsess",
                required: false,
                format: "[0/1]",
                description: "Determines whether checks for this service will be obsessed over using the OCSP command. Useful for distributed monitoring."
            },
            {
                name: "check_freshness",
                required: false,
                format: "[0/1]",
                description: "Determines whether freshness checks are enabled for this service."
            },
            {
                name: "freshness_threshold",
                required: false,
                format: "#",
                description: "The freshness threshold in seconds for this service. If no passive result has been received within this time, an active check is forced."
            },
            {
                name: "event_handler",
                required: false,
                format: "command_name",
                description: "The short name of the command to run whenever a change in the state of the service is detected."
            },
            {
                name: "event_handler_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether the event handler for this service is enabled. 0 = disabled, 1 = enabled."
            },
            {
                name: "low_flap_threshold",
                required: false,
                format: "#",
                description: "The low state change threshold percentage used in flap detection for this service."
            },
            {
                name: "high_flap_threshold",
                required: false,
                format: "#",
                description: "The high state change threshold percentage used in flap detection for this service."
            },
            {
                name: "flap_detection_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether flap detection is enabled for this service. 0 = disabled, 1 = enabled."
            },
            {
                name: "flap_detection_options",
                required: false,
                format: "[o,w,c,u]",
                description: "Determines which service states are used in flap detection logic: o = OK, w = WARNING, c = CRITICAL, u = UNKNOWN."
            },
            {
                name: "process_perf_data",
                required: false,
                format: "[0/1]",
                description: "Determines whether the processing of performance data is enabled for this service."
            },
            {
                name: "retain_status_information",
                required: false,
                format: "[0/1]",
                description: "Determines whether status-related information about the service is retained across program restarts."
            },
            {
                name: "retain_nonstatus_information",
                required: false,
                format: "[0/1]",
                description: "Determines whether non-status information about the service is retained across program restarts."
            },
            {
                name: "notification_interval",
                required: false,
                format: "#",
                description: "The number of time units to wait before re-notifying a contact that this service is still in a non-OK state. Set to 0 to disable re-notifications."
            },
            {
                name: "first_notification_delay",
                required: false,
                format: "#",
                description: "The number of time units to wait before sending out the first problem notification when the service enters a non-OK state."
            },
            {
                name: "notification_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which notifications of events for this service can be sent to contacts."
            },
            {
                name: "notification_options",
                required: false,
                format: "[w,u,c,r,f,s]",
                description: "Determines when notifications should be sent: w = WARNING, u = UNKNOWN, c = CRITICAL, r = recovery, f = flapping, s = scheduled downtime. Use n for none."
            },
            {
                name: "notifications_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether notifications for this service are enabled. 0 = disabled, 1 = enabled."
            },
            {
                name: "contacts",
                required: false,
                format: "contacts",
                description: "A comma-delimited list of short names of contacts that should be notified whenever there are problems (or recoveries) with this service."
            },
            {
                name: "contact_groups",
                required: false,
                format: "contact_groups",
                description: "A comma-delimited list of short names of contact groups that should be notified for this service."
            },
            {
                name: "stalking_options",
                required: false,
                format: "[o,w,u,c,N]",
                description: "Determines which service states are stalked: o = OK, w = WARNING, u = UNKNOWN, c = CRITICAL, N = include output in notifications."
            },
            {
                name: "notes",
                required: false,
                format: "note_string",
                description: "An optional string of notes pertaining to the service."
            },
            {
                name: "notes_url",
                required: false,
                format: "url",
                description: "An optional URL that provides additional information about the service. Macros ($HOSTNAME$, etc.) can be used."
            },
            {
                name: "action_url",
                required: false,
                format: "url",
                description: "An optional URL for actions to be performed on the service (e.g. PNP4Nagios graphs). Macros can be used."
            },
            {
                name: "icon_image",
                required: false,
                format: "image_file",
                description: "The name of a GIF, PNG, or JPG image that should be associated with this service in the CGIs."
            },
            {
                name: "icon_image_alt",
                required: false,
                format: "alt_string",
                description: "An optional string used as the ALT tag for the icon image."
            }
        ]
    },

    servicegroup: {
        label: 'Service Group',
        description: "Groups one or more services together for simplified configuration and display in the CGIs.",
        directives: [
            {
                name: "servicegroup_name",
                required: true,
                format: "servicegroup_name",
                description: "A short name used to identify the service group."
            },
            {
                name: "alias",
                required: false,
                format: "alias",
                description: "A longer name or description used to identify the service group."
            },
            {
                name: "members",
                required: false,
                format: "services",
                description: "A list of service members specified as comma-delimited host_name,service_description pairs."
            },
            {
                name: "servicegroup_members",
                required: false,
                format: "servicegroups",
                description: "A comma-delimited list of short names of other service groups whose members should be included in this group."
            },
            {
                name: "notes",
                required: false,
                format: "note_string",
                description: "An optional string of notes pertaining to the service group."
            },
            {
                name: "notes_url",
                required: false,
                format: "url",
                description: "An optional URL that provides additional information about the service group."
            },
            {
                name: "action_url",
                required: false,
                format: "url",
                description: "An optional URL for actions to be performed on the service group."
            }
        ]
    },

    contact: {
        label: 'Contact',
        description: "Identifies a person to be contacted for notifications about monitored hosts and services.",
        directives: [
            {
                name: "contact_name",
                required: true,
                format: "contact_name",
                description: "A short name used to identify the contact. It is referenced in contact group definitions."
            },
            {
                name: "alias",
                required: false,
                format: "alias",
                description: "A longer name or description used to identify the contact (e.g. full name)."
            },
            {
                name: "contactgroups",
                required: false,
                format: "contactgroup_names",
                description: "A comma-delimited list of short names of contact groups that this contact should be a member of."
            },
            {
                name: "minimum_importance",
                required: false,
                format: "#",
                description: "The minimum importance level a host or service must have for this contact to be notified. If the importance is lower, the contact will not be notified."
            },
            {
                name: "host_notifications_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether the contact will receive notifications about host problems and recoveries."
            },
            {
                name: "service_notifications_enabled",
                required: false,
                format: "[0/1]",
                description: "Determines whether the contact will receive notifications about service problems and recoveries."
            },
            {
                name: "host_notification_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which the contact can be notified about host problems or recoveries."
            },
            {
                name: "service_notification_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which the contact can be notified about service problems or recoveries."
            },
            {
                name: "host_notification_options",
                required: false,
                format: "[d,u,r,f,s,n]",
                description: "Defines the host states for which notifications should be sent: d = DOWN, u = UNREACHABLE, r = recovery, f = flapping, s = downtime, n = none."
            },
            {
                name: "service_notification_options",
                required: false,
                format: "[w,u,c,r,f,s,n]",
                description: "Defines the service states for which notifications should be sent: w = WARNING, u = UNKNOWN, c = CRITICAL, r = recovery, f = flapping, s = downtime, n = none."
            },
            {
                name: "host_notification_commands",
                required: false,
                format: "command_name",
                description: "A comma-delimited list of short names of commands used to notify the contact of host problems or recoveries."
            },
            {
                name: "service_notification_commands",
                required: false,
                format: "command_name",
                description: "A comma-delimited list of short names of commands used to notify the contact of service problems or recoveries."
            },
            {
                name: "email",
                required: false,
                format: "email_address",
                description: "The email address for the contact. Macro: $CONTACTEMAIL$."
            },
            {
                name: "pager",
                required: false,
                format: "pager_number_or_address",
                description: "The pager number or pager email gateway for the contact. Macro: $CONTACTPAGER$."
            },
            {
                name: "addressX",
                required: false,
                format: "additional_address",
                description: "Additional address fields (address1 through address6) for the contact. Useful for storing alternative contact methods. Macros: $CONTACTADDRESSx$."
            },
            {
                name: "can_submit_commands",
                required: false,
                format: "[0/1]",
                description: "Determines whether the contact can submit external commands to Nagios from the CGIs."
            },
            {
                name: "retain_status_information",
                required: false,
                format: "[0/1]",
                description: "Determines whether status-related information about the contact is retained across program restarts."
            },
            {
                name: "retain_nonstatus_information",
                required: false,
                format: "[0/1]",
                description: "Determines whether non-status information about the contact is retained across program restarts."
            }
        ]
    },

    contactgroup: {
        label: 'Contact Group',
        description: "Groups one or more contacts together for sending notifications to multiple people at once.",
        directives: [
            {
                name: "contactgroup_name",
                required: true,
                format: "contactgroup_name",
                description: "A short name used to identify the contact group."
            },
            {
                name: "alias",
                required: false,
                format: "alias",
                description: "A longer name or description used to identify the contact group."
            },
            {
                name: "members",
                required: false,
                format: "contacts",
                description: "A comma-delimited list of short names of contacts that should be included in this group."
            },
            {
                name: "contactgroup_members",
                required: false,
                format: "contactgroups",
                description: "A comma-delimited list of short names of other contact groups whose members should be included in this group."
            }
        ]
    },

    timeperiod: {
        label: 'Time Period',
        description: "Defines time ranges during which various monitoring operations (checks, notifications) can occur.",
        directives: [
            {
                name: "timeperiod_name",
                required: true,
                format: "timeperiod_name",
                description: "A short name used to identify the time period."
            },
            {
                name: "alias",
                required: false,
                format: "alias",
                description: "A longer name or description used to identify the time period."
            },
            {
                name: "sunday",
                required: false,
                format: "timeranges",
                description: "Time ranges for Sunday. Format: HH:MM-HH:MM, with multiple ranges comma-separated."
            },
            {
                name: "monday",
                required: false,
                format: "timeranges",
                description: "Time ranges for Monday. Format: HH:MM-HH:MM, with multiple ranges comma-separated."
            },
            {
                name: "tuesday",
                required: false,
                format: "timeranges",
                description: "Time ranges for Tuesday. Format: HH:MM-HH:MM, with multiple ranges comma-separated."
            },
            {
                name: "wednesday",
                required: false,
                format: "timeranges",
                description: "Time ranges for Wednesday. Format: HH:MM-HH:MM, with multiple ranges comma-separated."
            },
            {
                name: "thursday",
                required: false,
                format: "timeranges",
                description: "Time ranges for Thursday. Format: HH:MM-HH:MM, with multiple ranges comma-separated."
            },
            {
                name: "friday",
                required: false,
                format: "timeranges",
                description: "Time ranges for Friday. Format: HH:MM-HH:MM, with multiple ranges comma-separated."
            },
            {
                name: "saturday",
                required: false,
                format: "timeranges",
                description: "Time ranges for Saturday. Format: HH:MM-HH:MM, with multiple ranges comma-separated."
            },
            {
                name: "[exception]",
                required: false,
                format: "timeranges",
                description: "Date exception rules. Supports specific dates (2009-01-28), date ranges, month/day patterns, and skip intervals. Overrides weekday definitions."
            },
            {
                name: "exclude",
                required: false,
                format: "timeperiod_names",
                description: "A comma-delimited list of short names of other time periods whose time ranges should be excluded from this time period."
            }
        ]
    },

    command: {
        label: 'Command',
        description: "Defines a command (check, notification, or event handler) that can be executed by Nagios.",
        directives: [
            {
                name: "command_name",
                required: true,
                format: "command_name",
                description: "A short name used to identify the command. It is referenced in host, service, and contact definitions."
            },
            {
                name: "command_line",
                required: true,
                format: "command_line",
                description: "The actual command line that Nagios will execute. Macros and arguments ($ARG1$, etc.) are substituted before execution."
            }
        ]
    },

    servicedependency: {
        label: 'Service Dependency',
        description: "Defines execution and notification dependencies between services, allowing suppression based on the status of other services.",
        directives: [
            {
                name: "dependent_host_name",
                required: false,
                format: "host_name",
                description: "The short name(s) of the host(s) on which the dependent service runs. Multiple hosts can be comma-delimited."
            },
            {
                name: "dependent_hostgroup_name",
                required: false,
                format: "hostgroup_name",
                description: "The short name(s) of the hostgroup(s) on which the dependent service runs."
            },
            {
                name: "servicegroup_name",
                required: false,
                format: "servicegroup_name",
                description: "The short name(s) of servicegroup(s) whose services inherit this dependency. All services in these groups become dependent."
            },
            {
                name: "dependent_servicegroup_name",
                required: false,
                format: "servicegroup_name",
                description: "The short name(s) of servicegroup(s) containing the dependent services."
            },
            {
                name: "dependent_service_description",
                required: true,
                format: "service_description",
                description: "The description of the dependent service (the one that should be suppressed)."
            },
            {
                name: "host_name",
                required: false,
                format: "host_name",
                description: "The short name(s) of the host(s) on which the master service runs."
            },
            {
                name: "hostgroup_name",
                required: false,
                format: "hostgroup_name",
                description: "The short name(s) of the hostgroup(s) on which the master service runs."
            },
            {
                name: "service_description",
                required: true,
                format: "service_description",
                description: "The description of the master service (the one being depended upon)."
            },
            {
                name: "inherits_parent",
                required: false,
                format: "[0/1]",
                description: "Indicates whether this dependency inherits dependencies of the master service. 0 = don't inherit, 1 = inherit."
            },
            {
                name: "execution_failure_criteria",
                required: false,
                format: "[o,w,u,c,p,n]",
                description: "Master service states that prevent execution of the dependent service check: o = OK, w = WARNING, u = UNKNOWN, c = CRITICAL, p = PENDING, n = none."
            },
            {
                name: "notification_failure_criteria",
                required: false,
                format: "[o,w,u,c,p,n]",
                description: "Master service states that prevent notifications for the dependent service: o = OK, w = WARNING, u = UNKNOWN, c = CRITICAL, p = PENDING, n = none."
            },
            {
                name: "dependency_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which this dependency is valid. Outside this period, the dependency is not enforced."
            }
        ]
    },

    serviceescalation: {
        label: 'Service Escalation',
        description: "Escalates service notifications to additional contacts or contact groups after a specified number of notifications have been sent.",
        directives: [
            {
                name: "host_name",
                required: false,
                format: "host_name",
                description: "The short name(s) of the host(s) that the service escalation applies to."
            },
            {
                name: "hostgroup_name",
                required: false,
                format: "hostgroup_name",
                description: "The short name(s) of the hostgroup(s) that the service escalation applies to. All services on member hosts are eligible."
            },
            {
                name: "service_description",
                required: true,
                format: "service_description",
                description: "The description of the service that this escalation applies to."
            },
            {
                name: "contacts",
                required: false,
                format: "contacts",
                description: "A comma-delimited list of short names of contacts that should be notified when this escalation is triggered."
            },
            {
                name: "contact_groups",
                required: false,
                format: "contactgroup_name",
                description: "A comma-delimited list of short names of contact groups that should be notified when this escalation is triggered."
            },
            {
                name: "first_notification",
                required: false,
                format: "#",
                description: "The first notification number for which this escalation is effective. For example, a value of 3 means this escalation kicks in on the third notification."
            },
            {
                name: "last_notification",
                required: false,
                format: "#",
                description: "The last notification number for which this escalation is effective. A value of 0 means the escalation has no upper limit."
            },
            {
                name: "notification_interval",
                required: false,
                format: "#",
                description: "The interval between notifications while this escalation is active. If set to 0, Nagios will send the first notification then disable further notifications."
            },
            {
                name: "escalation_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which this escalation is valid."
            },
            {
                name: "escalation_options",
                required: false,
                format: "[w,u,c,r]",
                description: "The service states for which this escalation is valid: w = WARNING, u = UNKNOWN, c = CRITICAL, r = recovery."
            }
        ]
    },

    hostdependency: {
        label: 'Host Dependency',
        description: "Defines execution and notification dependencies between hosts, allowing suppression based on the status of other hosts.",
        directives: [
            {
                name: "dependent_host_name",
                required: true,
                format: "host_name",
                description: "The short name(s) of the dependent host(s). Multiple hosts can be specified as a comma-delimited list."
            },
            {
                name: "dependent_hostgroup_name",
                required: false,
                format: "hostgroup_name",
                description: "The short name(s) of the hostgroup(s) containing the dependent hosts."
            },
            {
                name: "host_name",
                required: true,
                format: "host_name",
                description: "The short name(s) of the master host(s) being depended upon."
            },
            {
                name: "hostgroup_name",
                required: false,
                format: "hostgroup_name",
                description: "The short name(s) of the hostgroup(s) containing the master hosts."
            },
            {
                name: "inherits_parent",
                required: false,
                format: "[0/1]",
                description: "Indicates whether this dependency inherits dependencies of the master host. 0 = don't inherit, 1 = inherit."
            },
            {
                name: "execution_failure_criteria",
                required: false,
                format: "[o,d,u,p,n]",
                description: "Master host states that prevent execution of the dependent host check: o = UP, d = DOWN, u = UNREACHABLE, p = PENDING, n = none."
            },
            {
                name: "notification_failure_criteria",
                required: false,
                format: "[o,d,u,p,n]",
                description: "Master host states that prevent notifications for the dependent host: o = UP, d = DOWN, u = UNREACHABLE, p = PENDING, n = none."
            },
            {
                name: "dependency_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which this dependency is valid."
            }
        ]
    },

    hostescalation: {
        label: 'Host Escalation',
        description: "Escalates host notifications to additional contacts or contact groups after a specified number of notifications have been sent.",
        directives: [
            {
                name: "host_name",
                required: false,
                format: "host_name",
                description: "The short name(s) of the host(s) that this escalation applies to."
            },
            {
                name: "hostgroup_name",
                required: false,
                format: "hostgroup_name",
                description: "The short name(s) of the hostgroup(s) that this escalation applies to. All hosts in the groups are eligible."
            },
            {
                name: "contacts",
                required: false,
                format: "contacts",
                description: "A comma-delimited list of short names of contacts that should be notified when this escalation is triggered."
            },
            {
                name: "contact_groups",
                required: false,
                format: "contactgroup_name",
                description: "A comma-delimited list of short names of contact groups that should be notified when this escalation is triggered."
            },
            {
                name: "first_notification",
                required: false,
                format: "#",
                description: "The first notification number for which this escalation is effective."
            },
            {
                name: "last_notification",
                required: false,
                format: "#",
                description: "The last notification number for which this escalation is effective. A value of 0 means no upper limit."
            },
            {
                name: "notification_interval",
                required: false,
                format: "#",
                description: "The interval between notifications while this escalation is active."
            },
            {
                name: "escalation_period",
                required: false,
                format: "timeperiod_name",
                description: "The short name of the time period during which this escalation is valid."
            },
            {
                name: "escalation_options",
                required: false,
                format: "[d,u,r]",
                description: "The host states for which this escalation is valid: d = DOWN, u = UNREACHABLE, r = recovery."
            }
        ]
    },

    hostextinfo: {
        label: 'Host Extended Info',
        deprecated: true,
        description: "Provides extended display information for hosts in the CGIs. Deprecated in Nagios 4; use host definition directives instead.",
        directives: [
            {
                name: "host_name",
                required: true,
                format: "host_name",
                description: "The short name of the host to which this extended info applies."
            },
            {
                name: "notes",
                required: false,
                format: "note_string",
                description: "An optional string of notes pertaining to the host."
            },
            {
                name: "notes_url",
                required: false,
                format: "url",
                description: "An optional URL that provides additional information about the host."
            },
            {
                name: "action_url",
                required: false,
                format: "url",
                description: "An optional URL for actions to be performed on the host."
            },
            {
                name: "icon_image",
                required: false,
                format: "image_file",
                description: "The name of a GIF, PNG, or JPG image that should be associated with this host."
            },
            {
                name: "icon_image_alt",
                required: false,
                format: "alt_string",
                description: "An optional string used as the ALT tag for the icon image."
            },
            {
                name: "vrml_image",
                required: false,
                format: "image_file",
                description: "The name of an image file used as the texture map for this host in the statuswrl CGI."
            },
            {
                name: "statusmap_image",
                required: false,
                format: "image_file",
                description: "The name of an image that should be associated with this host in the statusmap CGI."
            },
            {
                name: "2d_coords",
                required: false,
                format: "x_coord,y_coord",
                description: "The 2D coordinates (x,y) used when drawing the host in the statusmap CGI."
            },
            {
                name: "3d_coords",
                required: false,
                format: "x_coord,y_coord,z_coord",
                description: "The 3D coordinates (x,y,z) used when drawing the host in the statuswrl (VRML) CGI."
            }
        ]
    },

    serviceextinfo: {
        label: 'Service Extended Info',
        deprecated: true,
        description: "Provides extended display information for services in the CGIs. Deprecated in Nagios 4; use service definition directives instead.",
        directives: [
            {
                name: "host_name",
                required: true,
                format: "host_name",
                description: "The short name of the host on which the service runs."
            },
            {
                name: "service_description",
                required: true,
                format: "service_description",
                description: "The description of the service to which this extended info applies."
            },
            {
                name: "notes",
                required: false,
                format: "note_string",
                description: "An optional string of notes pertaining to the service."
            },
            {
                name: "notes_url",
                required: false,
                format: "url",
                description: "An optional URL that provides additional information about the service."
            },
            {
                name: "action_url",
                required: false,
                format: "url",
                description: "An optional URL for actions to be performed on the service."
            },
            {
                name: "icon_image",
                required: false,
                format: "image_file",
                description: "The name of a GIF, PNG, or JPG image that should be associated with this service."
            },
            {
                name: "icon_image_alt",
                required: false,
                format: "alt_string",
                description: "An optional string used as the ALT tag for the icon image."
            }
        ]
    }
};
