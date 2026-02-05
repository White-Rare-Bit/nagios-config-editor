/**
 * Nagios Bulk Editor - Dependencies Graph Configuration
 *
 * Static configuration objects for the dependency graph visualization.
 * Extracted from dependencies.js to reduce file size and improve maintainability.
 */

(function() {
    'use strict';

    // Layout configuration - centralized constants for all layout algorithms
    const LAYOUT_CONFIG = {
        // Tree layouts (hierarchical/hierarchicalLR)
        nodeWidth: 120,           // Minimum width per node in tree
        tierSpacingVertical: 150, // Vertical spacing between tiers
        tierSpacingHorizontal: 200, // Horizontal spacing between tiers (LR layout)

        // Cluster/satellite layouts (static)
        clusterDistance: 600,     // Distance from center to cluster center
        clusterRadius: 100,       // Base radius of nodes within cluster
        clusterRadiusStep: 90,    // Additional radius per ring of nodes
        nodesPerRing: 8,          // Max nodes in inner ring
        orbitGap: 150             // Gap between parent cluster and orbiting cluster
    };

    // Edge categories for filtering - maps edge labels to semantic categories
    const edgeCategories = {
        // Dependencies: network topology and monitoring logic
        dependencies: [
            'parents',                    // Host parent-child (network topology)
            'host_name',                  // Service -> Host binding
            'dependent_host_name',        // Host dependency dependent host
            'dependent_hostgroup_name',   // Host dependency dependent via group
            'dependent_service_description', // Service dependency dependent
            'service_description',        // Service dependency master service
            'master_host_name',           // Host dependency master host
            'master_hostgroup_name',      // Host dependency master via group
            'master_service_description'  // Service dependency master service
        ],
        // Templates: inheritance chain
        templates: [
            'use'                         // Template inheritance
        ],
        // Groups: organizational grouping (bidirectional - includes member->group edges)
        groups: [
            'hostgroups',                 // Host -> Hostgroup membership
            'hostgroup_name',             // Object -> Hostgroup reference
            'servicegroups',              // Service -> Servicegroup membership
            'servicegroup_name',          // Object -> Servicegroup reference
            'members',                    // Group -> Members
            'hostgroup_members',          // Hostgroup -> Members
            'servicegroup_members'        // Servicegroup -> Members
        ],
        // Group references only - for finding services/escalations that target hostgroups
        // Does NOT include hostgroups/servicegroups edges (those pull in all hosts in a group)
        'group-refs': [
            'hostgroup_name',             // Service/escalation -> Hostgroup reference
            'servicegroup_name'           // Object -> Servicegroup reference
        ],
        // Service bindings - minimal edges for finding services related to a host
        // Does NOT include parents/dependency fields that would pull in siblings
        'service-bindings': [
            'host_name',                  // Service -> Host binding (followed backward from hosts)
            'hostgroups'                  // Host -> Hostgroup membership (followed forward from hosts)
        ],
        // Membership: group -> members only (for notifications view - no reverse edges)
        membership: [
            'members',                    // Group -> Members
            'hostgroup_members',          // Hostgroup -> Members
            'servicegroup_members'        // Servicegroup -> Members
        ],
        // Contacts: notification routing (includes escalation contacts)
        contacts: [
            'contacts',                   // Object -> Contact
            'contact_groups',             // Object -> Contact group
            'contact_name',               // Contact reference
            'contactgroup_name',          // Contact group reference
            'contactgroup_members',       // Contact group -> Members
            'escalation_contacts',        // Escalation -> Contact
            'escalation_contact_groups'   // Escalation -> Contact group
        ],
        // Commands: implementation details
        commands: [
            'check_command',              // Check command
            'event_handler',              // Event handler command
            'host_notification_commands', // Contact host notification
            'service_notification_commands', // Contact service notification
            'notification_commands'       // Generic notification commands
        ],
        // Schedules: time periods
        schedules: [
            'check_period',               // Check time period
            'notification_period',        // Notification time period
            'host_notification_period',   // Contact host notification period
            'service_notification_period', // Contact service notification period
            'escalation_period',          // Escalation time period
            'dependency_period',          // Dependency time period
            'exclude'                     // Timeperiod exclusion
        ]
    };

    // View mode presets - which categories are enabled by default
    const viewModePresets = {
        dependencies: ['dependencies'],
        overview: ['dependencies', 'templates', 'groups'],
        all: ['dependencies', 'templates', 'groups', 'contacts', 'commands', 'schedules'],
        custom: null  // No preset, use checkbox state
    };

    // Quick view presets - combines edge filter + optimal layout for common exploration patterns
    // Each preset answers a specific admin question with the best visual representation
    const quickViewPresets = {
        inheritance: {
            categories: ['templates'],
            layout: 'hierarchical',  // Dagre TB - template chains flow top-down
            description: 'Template inheritance chains',
            icon: 'fa-sitemap',
            label: 'Inheritance'
        },
        network: {
            categories: ['dependencies'],
            layout: 'hierarchical',  // Dagre TB - network topology flows parent->child
            description: 'Host parent-child topology and service bindings',
            icon: 'fa-network-wired',
            label: 'Network'
        },
        notifications: {
            categories: ['contacts', 'membership'],  // membership = group->members only (no reverse)
            layout: 'hierarchicalLR',  // Dagre LR - notification flows left->right
            description: 'Notification routing to contacts',
            directional: true,  // Only follow outward: object -> contacts (not reverse)
            icon: 'fa-bell',
            label: 'Notifications'
        },
        services: {
            categories: ['service-bindings', 'group-refs'],
            layout: 'hierarchicalLR',
            description: 'Services monitoring this host (including via hostgroups)',
            directional: true,  // Only follow specific directions to avoid pulling in sibling hosts
            icon: 'fa-gear',
            label: 'Services'
        },
        members: {
            categories: ['membership'],
            layout: 'hierarchicalLR',
            description: 'Members of this group',
            directional: true,  // group -> members direction
            icon: 'fa-users',
            label: 'Members'
        },
        notifiedBy: {
            categories: ['contacts', 'membership'],
            layout: 'hierarchicalLR',
            description: 'What notifies this contact/group',
            directional: false,  // Follow edges in both directions to find sources
            icon: 'fa-bell',
            label: 'Notified By'
        },
        usedBy: {
            categories: ['commands', 'schedules'],
            layout: 'hierarchicalLR',
            description: 'Objects using this command/timeperiod',
            directional: false,  // Follow edges backwards to find users
            icon: 'fa-arrow-left',
            label: 'Used By'
        },
        monitoring: {
            categories: ['commands', 'schedules'],
            layout: 'hierarchicalLR',
            description: 'Check commands and time periods',
            directional: true,
            icon: 'fa-clock',
            label: 'Monitoring'
        },
        escalations: {
            categories: ['contacts', 'dependencies', 'schedules'],
            layout: 'hierarchicalLR',
            description: 'Escalation paths for this object',
            directional: true,
            icon: 'fa-arrow-up',
            label: 'Escalations'
        },
        dependencies: {
            categories: ['dependencies'],
            layout: 'hierarchical',
            description: 'Dependency rules affecting this object',
            directional: false,
            icon: 'fa-link',
            label: 'Dependencies'
        },
        full: {
            categories: ['dependencies', 'templates', 'groups', 'contacts', 'commands', 'schedules'],  // All categories
            layout: 'static',  // COSe force-directed - best for exploration
            description: 'Complete graph with all relationships',
            useSmartExpansion: true,  // Use addAllConnectedRecursively for semantic-aware expansion
            icon: 'fa-diagram-project',
            label: 'Full Graph'
        }
    };

    // Declarative expansion rules for quick view presets
    // Each (objectType, preset) combination defines which edges to follow
    // Keyed by (objectType, preset) for O(1) lookup during BFS traversal
    const expansionRules = {
        host: {
            inheritance: {
                // Template inheritance chains
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            services: {
                // Services linked directly + services via hostgroups
                // stopAt prevents sibling host expansion
                forward: ['hostgroups'],
                backward: ['host_name'],
                atType: {
                    hostgroup: { backward: ['hostgroup_name'] }
                },
                stopAt: ['host']
            },
            network: {
                // Network topology: parents, group membership, and dependencies
                forward: ['parents', 'hostgroups'],
                backward: ['parents', 'dependent_host_name', 'master_host_name'],
                stopAt: []
            },
            notifications: {
                // Notification routing to contacts
                // atType expands contactgroups to members
                forward: ['contacts', 'contact_groups'],
                backward: [],
                atType: {
                    contactgroup: { forward: ['members'] }
                },
                stopAt: []
            },
            monitoring: {
                // Commands and time periods for monitoring config
                forward: ['check_command', 'check_period', 'notification_period', 'event_handler'],
                backward: [],
                stopAt: []
            },
            escalations: {
                // Find hostescalations targeting this host
                forward: [],
                backward: ['host_name'],
                atType: {
                    hostescalation: { forward: ['contacts', 'contact_groups', 'escalation_period'] }
                },
                stopAt: []
            },
            dependencies: {
                // Find hostdependencies where this host is dependent or master
                forward: [],
                backward: ['dependent_host_name', 'host_name', 'master_host_name'],
                atType: {
                    hostdependency: { forward: ['dependent_host_name', 'host_name', 'master_host_name', 'dependent_hostgroup_name', 'hostgroup_name', 'master_hostgroup_name'] }
                },
                stopAt: []
            }
        },
        hostgroup: {
            inheritance: {
                // Template inheritance chains
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            services: {
                // Services targeting this hostgroup
                // stopAt prevents host expansion
                forward: [],
                backward: ['hostgroup_name'],
                stopAt: ['host']
            },
            members: {
                // Hosts in this group + nested hostgroups
                forward: ['members', 'hostgroup_members'],
                backward: ['hostgroups'],
                stopAt: []
            },
            notifications: {
                // Notification routing from group
                forward: ['contacts', 'contact_groups'],
                backward: [],
                atType: {
                    contactgroup: { forward: ['members'] }
                },
                stopAt: []
            },
            escalations: {
                // Find hostescalations targeting this hostgroup
                forward: [],
                backward: ['hostgroup_name'],
                atType: {
                    hostescalation: { forward: ['contacts', 'contact_groups', 'escalation_period'] }
                },
                stopAt: []
            },
            dependencies: {
                // Find hostdependencies referencing this hostgroup
                forward: [],
                backward: ['dependent_hostgroup_name', 'hostgroup_name', 'master_hostgroup_name'],
                atType: {
                    hostdependency: { forward: ['dependent_host_name', 'host_name', 'master_host_name'] }
                },
                stopAt: []
            }
        },
        service: {
            inheritance: {
                // Template inheritance chains
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            network: {
                // Host binding and service dependencies
                forward: ['host_name', 'hostgroup_name'],
                backward: ['dependent_service_description', 'service_description'],
                stopAt: []
            },
            monitoring: {
                // Check commands and time periods
                forward: ['check_command', 'check_period', 'notification_period', 'event_handler'],
                backward: [],
                stopAt: []
            },
            notifications: {
                // Notification routing to contacts
                forward: ['contacts', 'contact_groups'],
                backward: [],
                atType: {
                    contactgroup: { forward: ['members'] }
                },
                stopAt: []
            },
            escalations: {
                // Find serviceescalations targeting this service
                forward: [],
                backward: ['service_description'],
                atType: {
                    serviceescalation: { forward: ['contacts', 'contact_groups', 'escalation_period'] }
                },
                stopAt: []
            },
            dependencies: {
                // Find servicedependencies where this service is dependent or master
                forward: [],
                backward: ['dependent_service_description', 'service_description', 'master_service_description'],
                atType: {
                    servicedependency: { forward: ['dependent_service_description', 'service_description', 'master_service_description', 'dependent_host_name', 'host_name', 'master_host_name'] }
                },
                stopAt: []
            }
        },
        servicegroup: {
            inheritance: {
                // Template inheritance chains
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            network: {
                // Service dependencies referencing this group
                forward: ['servicegroups'],
                backward: ['servicegroup_name'],
                stopAt: []
            },
            members: {
                // Services in this group + nested servicegroups
                forward: ['members', 'servicegroup_members'],
                backward: ['servicegroups'],
                stopAt: []
            },
            notifications: {
                // Notification routing from group
                forward: ['contacts', 'contact_groups'],
                backward: [],
                atType: {
                    contactgroup: { forward: ['members'] }
                },
                stopAt: []
            },
            escalations: {
                // Find serviceescalations targeting this servicegroup
                forward: [],
                backward: ['servicegroup_name'],
                atType: {
                    serviceescalation: { forward: ['contacts', 'contact_groups', 'escalation_period'] }
                },
                stopAt: []
            },
            dependencies: {
                // Find servicedependencies referencing this servicegroup
                forward: [],
                backward: ['servicegroup_name'],
                atType: {
                    servicedependency: { forward: ['dependent_service_description', 'service_description', 'master_service_description'] }
                },
                stopAt: []
            }
        },
        contact: {
            inheritance: {
                // Template inheritance chains
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            notifiedBy: {
                // Objects that notify this contact
                forward: [],
                backward: ['contacts', 'members'],
                atType: {
                    contactgroup: { backward: ['contact_groups'] }
                },
                stopAt: []
            }
        },
        contactgroup: {
            inheritance: {
                // Template inheritance chains
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            members: {
                // Contacts in this group + nested contactgroups
                forward: ['members', 'contactgroup_members'],
                backward: [],
                stopAt: []
            },
            notifiedBy: {
                // Objects that notify this group
                forward: [],
                backward: ['contact_groups'],
                stopAt: []
            }
        },
        command: {
            usedBy: {
                // Objects using this command
                forward: [],
                backward: ['check_command', 'event_handler', 'host_notification_commands', 'service_notification_commands', 'notification_commands'],
                stopAt: []
            }
        },
        timeperiod: {
            usedBy: {
                // Objects using this time period
                forward: [],
                backward: ['check_period', 'notification_period', 'host_notification_period', 'service_notification_period', 'escalation_period', 'exclude'],
                stopAt: []
            }
        },
        hostdependency: {
            inheritance: {
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            network: {
                // Dependency topology: dependent and master hosts
                forward: ['dependent_host_name', 'dependent_hostgroup_name', 'host_name', 'hostgroup_name', 'master_host_name', 'master_hostgroup_name'],
                backward: [],
                stopAt: []
            },
            monitoring: {
                // Time period constraints
                forward: ['dependency_period'],
                backward: [],
                stopAt: []
            }
        },
        servicedependency: {
            inheritance: {
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            network: {
                // Dependency topology: dependent and master services
                forward: ['dependent_service_description', 'dependent_host_name', 'dependent_hostgroup_name', 'service_description', 'host_name', 'hostgroup_name', 'master_service_description', 'master_host_name', 'master_hostgroup_name'],
                backward: [],
                stopAt: []
            },
            monitoring: {
                // Time period constraints
                forward: ['dependency_period'],
                backward: [],
                stopAt: []
            }
        },
        hostescalation: {
            inheritance: {
                // Template inheritance chains
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            notifications: {
                // Contacts and time periods for this escalation
                forward: ['contacts', 'contact_groups', 'escalation_period'],
                backward: [],
                atType: {
                    contactgroup: { forward: ['members'] }
                },
                stopAt: []
            },
            network: {
                // Hosts/hostgroups this escalation targets
                forward: ['host_name', 'hostgroup_name'],
                backward: [],
                stopAt: []
            }
        },
        serviceescalation: {
            inheritance: {
                // Template inheritance chains
                forward: ['use'],
                backward: ['use'],
                stopAt: []
            },
            notifications: {
                // Contacts and time periods for this escalation
                forward: ['contacts', 'contact_groups', 'escalation_period'],
                backward: [],
                atType: {
                    contactgroup: { forward: ['members'] }
                },
                stopAt: []
            },
            network: {
                // Hosts/services this escalation targets
                forward: ['host_name', 'hostgroup_name', 'service_description', 'servicegroup_name'],
                backward: [],
                stopAt: []
            }
        }
    };

    const typeColors = {
        'host': '#4CAF50',
        'hostgroup': '#8BC34A',
        'service': '#2196F3',
        'servicegroup': '#03A9F4',
        'contact': '#FF9800',
        'contactgroup': '#FFC107',
        'command': '#9C27B0',
        'timeperiod': '#607D8B'
    };

    // FontAwesome SVG paths for each type (with viewBox dimensions)
    const typeIconSvg = {
        'host': { viewBox: '0 0 576 512', path: 'M64 0C28.7 0 0 28.7 0 64V352c0 35.3 28.7 64 64 64H240l-10.7 32H160c-17.7 0-32 14.3-32 32s14.3 32 32 32H416c17.7 0 32-14.3 32-32s-14.3-32-32-32H346.7L336 416H512c35.3 0 64-28.7 64-64V64c0-35.3-28.7-64-64-64H64zM512 64V352H64V64H512z' },
        // Host template: fa-cube (blueprint/template icon)
        'host_template': { viewBox: '0 0 512 512', path: 'M234.5 5.7c13.9-5 29.1-5 43.1 0l192 68.6C495 83.4 512 107.5 512 134.6V377.4c0 27-17 51.2-42.5 60.3l-192 68.6c-13.9 5-29.1 5-43.1 0l-192-68.6C17 428.6 0 404.5 0 377.4V134.6c0-27 17-51.2 42.5-60.3l192-68.6zM256 66L82.3 128 256 190l173.7-62L256 66zm32 368.6l160-57.1v-188L288 246.6v188z' },
        'hostgroup': { viewBox: '0 0 576 512', path: 'M264.5 5.2c14.9-6.9 32.1-6.9 47 0l218.6 101c8.5 3.9 13.9 12.4 13.9 21.8s-5.4 17.9-13.9 21.8l-218.6 101c-14.9 6.9-32.1 6.9-47 0L45.9 149.8C37.4 145.8 32 137.3 32 128s5.4-17.9 13.9-21.8L264.5 5.2zM476.9 209.6l53.2 24.6c8.5 3.9 13.9 12.4 13.9 21.8s-5.4 17.9-13.9 21.8l-218.6 101c-14.9 6.9-32.1 6.9-47 0L45.9 277.8C37.4 273.8 32 265.3 32 256s5.4-17.9 13.9-21.8l53.2-24.6 152 70.2c23.4 10.8 50.4 10.8 73.8 0l152-70.2zm-152 198.2l152-70.2 53.2 24.6c8.5 3.9 13.9 12.4 13.9 21.8s-5.4 17.9-13.9 21.8l-218.6 101c-14.9 6.9-32.1 6.9-47 0L45.9 405.8C37.4 401.8 32 393.3 32 384s5.4-17.9 13.9-21.8l53.2-24.6 152 70.2c23.4 10.8 50.4 10.8 73.8 0z' },
        'service': { viewBox: '0 0 512 512', path: 'M495.9 166.6c3.2 8.7 .5 18.4-6.4 24.6l-43.3 39.4c1.1 8.3 1.7 16.8 1.7 25.4s-.6 17.1-1.7 25.4l43.3 39.4c6.9 6.2 9.6 15.9 6.4 24.6c-4.4 11.9-9.7 23.3-15.8 34.3l-4.7 8.1c-6.6 11-14 21.4-22.1 31.2c-5.9 7.2-15.7 9.6-24.5 6.8l-55.7-17.7c-13.4 10.3-28.2 18.9-44 25.4l-12.5 57.1c-2 9.1-9 16.3-18.2 17.8c-13.8 2.3-28 3.5-42.5 3.5s-28.7-1.2-42.5-3.5c-9.2-1.5-16.2-8.7-18.2-17.8l-12.5-57.1c-15.8-6.5-30.6-15.1-44-25.4L83.1 425.9c-8.8 2.8-18.6 .3-24.5-6.8c-8.1-9.8-15.5-20.2-22.1-31.2l-4.7-8.1c-6.1-11-11.4-22.4-15.8-34.3c-3.2-8.7-.5-18.4 6.4-24.6l43.3-39.4C64.6 273.1 64 264.6 64 256s.6-17.1 1.7-25.4L22.4 191.2c-6.9-6.2-9.6-15.9-6.4-24.6c4.4-11.9 9.7-23.3 15.8-34.3l4.7-8.1c6.6-11 14-21.4 22.1-31.2c5.9-7.2 15.7-9.6 24.5-6.8l55.7 17.7c13.4-10.3 28.2-18.9 44-25.4l12.5-57.1c2-9.1 9-16.3 18.2-17.8C227.3 1.2 241.5 0 256 0s28.7 1.2 42.5 3.5c9.2 1.5 16.2 8.7 18.2 17.8l12.5 57.1c15.8 6.5 30.6 15.1 44 25.4l55.7-17.7c8.8-2.8 18.6-.3 24.5 6.8c8.1 9.8 15.5 20.2 22.1 31.2l4.7 8.1c6.1 11 11.4 22.4 15.8 34.3zM256 336a80 80 0 1 0 0-160 80 80 0 1 0 0 160z' },
        // Service template: fa-puzzle-piece (reusable component icon)
        'service_template': { viewBox: '0 0 512 512', path: 'M192 104.8c0-9.2-5.8-17.3-13.2-22.8C167.2 73.3 160 61.3 160 48c0-26.5 28.7-48 64-48s64 21.5 64 48c0 13.3-7.2 25.3-18.8 34c-7.4 5.5-13.2 13.6-13.2 22.8c0 12.8 10.4 23.2 23.2 23.2H336c26.5 0 48 21.5 48 48v56.8c0 12.8 10.4 23.2 23.2 23.2c9.2 0 17.3-5.8 22.8-13.2c8.7-11.6 20.7-18.8 34-18.8c26.5 0 48 28.7 48 64s-21.5 64-48 64c-13.3 0-25.3-7.2-34-18.8c-5.5-7.4-13.6-13.2-22.8-13.2c-12.8 0-23.2 10.4-23.2 23.2V464c0 26.5-21.5 48-48 48H279.2c-12.8 0-23.2-10.4-23.2-23.2c0-9.2 5.8-17.3 13.2-22.8c11.6-8.7 18.8-20.7 18.8-34c0-26.5-28.7-48-64-48s-64 21.5-64 48c0 13.3 7.2 25.3 18.8 34c7.4 5.5 13.2 13.6 13.2 22.8c0 12.8-10.4 23.2-23.2 23.2H48c-26.5 0-48-21.5-48-48V343.2C0 330.4 10.4 320 23.2 320c9.2 0 17.3 5.8 22.8 13.2C54.7 344.8 66.7 352 80 352c26.5 0 48-28.7 48-64s-21.5-64-48-64c-13.3 0-25.3 7.2-34 18.8C40.5 250.2 32.4 256 23.2 256C10.4 256 0 245.6 0 232.8V176c0-26.5 21.5-48 48-48H168.8c12.8 0 23.2-10.4 23.2-23.2z' },
        'servicegroup': { viewBox: '0 0 640 512', path: 'M308.5 135.3c7.1-6.3 9.9-16.2 6.2-25c-2.3-5.3-4.8-10.5-7.6-15.5L304 89.4c-3-5-6.3-9.9-9.8-14.6c-5.7-7.6-15.7-10.1-24.7-7.1l-28.2 9.3c-10.7-8.8-23-16-36.2-20.9L199 27.1c-1.9-9.3-9.1-16.7-18.5-17.8C173.9 8.4 167.2 8 160.4 8h-.7c-6.8 0-13.5 .4-20.1 1.2c-9.4 1.1-16.6 8.6-18.5 17.8L115 56.1c-13.3 5-25.5 12.1-36.2 20.9L50.5 67.8c-9-3-19-.5-24.7 7.1c-3.5 4.7-6.8 9.6-9.9 14.6l-3 5.3c-2.8 5-5.3 10.2-7.6 15.6c-3.7 8.7-.9 18.6 6.2 25l22.2 19.8C32.6 161.9 32 168.9 32 176s.6 14.1 1.7 20.9L11.5 216.7c-7.1 6.3-9.9 16.2-6.2 25c2.3 5.3 4.8 10.5 7.6 15.6l3 5.2c3 5.1 6.3 9.9 9.9 14.6c5.7 7.6 15.7 10.1 24.7 7.1l28.2-9.3c10.7 8.8 23 16 36.2 20.9l6.1 29.1c1.9 9.3 9.1 16.7 18.5 17.8c6.7 .8 13.5 1.2 20.4 1.2s13.7-.4 20.4-1.2c9.4-1.1 16.6-8.6 18.5-17.8l6.1-29.1c13.3-5 25.5-12.1 36.2-20.9l28.2 9.3c9 3 19 .5 24.7-7.1c3.5-4.7 6.8-9.5 9.8-14.6l3.1-5.4c2.8-5 5.3-10.2 7.6-15.5c3.7-8.7 .9-18.6-6.2-25l-22.2-19.8c1.1-6.8 1.7-13.8 1.7-20.9s-.6-14.1-1.7-20.9l22.2-19.8zM112 176a48 48 0 1 1 96 0 48 48 0 1 1 -96 0zM504.7 500.5c6.3 7.1 16.2 9.9 25 6.2c5.3-2.3 10.5-4.8 15.5-7.6l5.4-3.1c5-3 9.9-6.3 14.6-9.8c7.6-5.7 10.1-15.7 7.1-24.7l-9.3-28.2c8.8-10.7 16-23 20.9-36.2l29.1-6.1c9.3-1.9 16.7-9.1 17.8-18.5c.8-6.7 1.2-13.5 1.2-20.4s-.4-13.7-1.2-20.4c-1.1-9.4-8.6-16.6-17.8-18.5L583.9 307c-5-13.3-12.1-25.5-20.9-36.2l9.3-28.2c3-9 .5-19-7.1-24.7c-4.7-3.5-9.6-6.8-14.6-9.9l-5.3-3c-5-2.8-10.2-5.3-15.6-7.6c-8.7-3.7-18.6-.9-25 6.2l-19.8 22.2c-6.8-1.1-13.8-1.7-20.9-1.7s-14.1 .6-20.9 1.7l-19.8-22.2c-6.3-7.1-16.2-9.9-25-6.2c-5.3 2.3-10.5 4.8-15.6 7.6l-5.2 3c-5.1 3-9.9 6.3-14.6 9.9c-7.6 5.7-10.1 15.7-7.1 24.7l9.3 28.2c-8.8 10.7-16 23-20.9 36.2L315.1 313c-9.3 1.9-16.7 9.1-17.8 18.5c-.8 6.7-1.2 13.5-1.2 20.4s.4 13.7 1.2 20.4c1.1 9.4 8.6 16.6 17.8 18.5l29.1 6.1c5 13.3 12.1 25.5 20.9 36.2l-9.3 28.2c-3 9-.5 19 7.1 24.7c4.7 3.5 9.5 6.8 14.6 9.8l5.4 3.1c5 2.8 10.2 5.3 15.5 7.6c8.7 3.7 18.6 .9 25-6.2l19.8-22.2c6.8 1.1 13.8 1.7 20.9 1.7s14.1-.6 20.9-1.7l19.8 22.2zM464 304a48 48 0 1 1 0 96 48 48 0 1 1 0-96z' },
        'contact': { viewBox: '0 0 448 512', path: 'M224 256A128 128 0 1 0 224 0a128 128 0 1 0 0 256zm-45.7 48C79.8 304 0 383.8 0 482.3C0 498.7 13.3 512 29.7 512H418.3c16.4 0 29.7-13.3 29.7-29.7C448 383.8 368.2 304 269.7 304H178.3z' },
        'contactgroup': { viewBox: '0 0 640 512', path: 'M144 0a80 80 0 1 1 0 160A80 80 0 1 1 144 0zM512 0a80 80 0 1 1 0 160A80 80 0 1 1 512 0zM0 298.7C0 239.8 47.8 192 106.7 192h42.7c15.9 0 31 3.5 44.6 9.7c-1.3 7.2-1.9 14.7-1.9 22.3c0 38.2 16.8 72.5 43.3 96c-.2 0-.4 0-.7 0H21.3C9.6 320 0 310.4 0 298.7zM405.3 320c-.2 0-.4 0-.7 0c26.6-23.5 43.3-57.8 43.3-96c0-7.6-.7-15-1.9-22.3c13.6-6.3 28.7-9.7 44.6-9.7h42.7C592.2 192 640 239.8 640 298.7c0 11.8-9.6 21.3-21.3 21.3H405.3zM224 224a96 96 0 1 1 192 0 96 96 0 1 1 -192 0zM128 485.3C128 411.7 187.7 352 261.3 352H378.7C452.3 352 512 411.7 512 485.3c0 14.7-11.9 26.7-26.7 26.7H154.7c-14.7 0-26.7-11.9-26.7-26.7z' },
        'command': { viewBox: '0 0 448 512', path: 'M349.4 44.6c5.9-13.7 1.5-29.7-10.6-38.5s-28.6-8-39.9 1.8l-256 224c-10 8.8-13.6 22.9-8.9 35.3S50.7 288 64 288H175.5L98.6 467.4c-5.9 13.7-1.5 29.7 10.6 38.5s28.6 8 39.9-1.8l256-224c10-8.8 13.6-22.9 8.9-35.3s-16.6-20.7-30-20.7H272.5L349.4 44.6z' },
        'timeperiod': { viewBox: '0 0 512 512', path: 'M256 0a256 256 0 1 1 0 512A256 256 0 1 1 256 0zM232 120V256c0 8 4 15.5 10.7 20l96 64c11 7.4 25.9 4.4 33.3-6.7s4.4-25.9-6.7-33.3L280 243.2V120c0-13.3-10.7-24-24-24s-24 10.7-24 24z' },
        // Dependency and escalation types
        'servicedependency': { viewBox: '0 0 640 512', path: 'M579.8 267.7c56.5-56.5 56.5-148 0-204.5c-50-50-128.8-56.5-186.3-15.4l-1.6 1.1c-14.4 10.3-17.7 30.3-7.4 44.6s30.3 17.7 44.6 7.4l1.6-1.1c32.1-22.9 76-19.3 103.8 8.6c31.5 31.5 31.5 82.5 0 114L422.3 334.8c-31.5 31.5-82.5 31.5-114 0c-27.9-27.9-31.5-71.8-8.6-103.8l1.1-1.6c10.3-14.4 6.9-34.4-7.4-44.6s-34.4-6.9-44.6 7.4l-1.1 1.6C206.5 251.2 213 330 263 380c56.5 56.5 148 56.5 204.5 0L579.8 267.7zM60.2 244.3c-56.5 56.5-56.5 148 0 204.5c50 50 128.8 56.5 186.3 15.4l1.6-1.1c14.4-10.3 17.7-30.3 7.4-44.6s-30.3-17.7-44.6-7.4l-1.6 1.1c-32.1 22.9-76 19.3-103.8-8.6C74 372.1 74 321.1 105.5 289.5L217.7 177.2c31.5-31.5 82.5-31.5 114 0c27.9 27.9 31.5 71.8 8.6 103.9l-1.1 1.6c-10.3 14.4-6.9 34.4 7.4 44.6s34.4 6.9 44.6-7.4l1.1-1.6C433.5 260.8 427 182 377 132c-56.5-56.5-148-56.5-204.5 0L60.2 244.3z' },
        'hostdependency': { viewBox: '0 0 640 512', path: 'M579.8 267.7c56.5-56.5 56.5-148 0-204.5c-50-50-128.8-56.5-186.3-15.4l-1.6 1.1c-14.4 10.3-17.7 30.3-7.4 44.6s30.3 17.7 44.6 7.4l1.6-1.1c32.1-22.9 76-19.3 103.8 8.6c31.5 31.5 31.5 82.5 0 114L422.3 334.8c-31.5 31.5-82.5 31.5-114 0c-27.9-27.9-31.5-71.8-8.6-103.8l1.1-1.6c10.3-14.4 6.9-34.4-7.4-44.6s-34.4-6.9-44.6 7.4l-1.1 1.6C206.5 251.2 213 330 263 380c56.5 56.5 148 56.5 204.5 0L579.8 267.7zM60.2 244.3c-56.5 56.5-56.5 148 0 204.5c50 50 128.8 56.5 186.3 15.4l1.6-1.1c14.4-10.3 17.7-30.3 7.4-44.6s-30.3-17.7-44.6-7.4l-1.6 1.1c-32.1 22.9-76 19.3-103.8-8.6C74 372.1 74 321.1 105.5 289.5L217.7 177.2c31.5-31.5 82.5-31.5 114 0c27.9 27.9 31.5 71.8 8.6 103.9l-1.1 1.6c-10.3 14.4-6.9 34.4 7.4 44.6s34.4 6.9 44.6-7.4l1.1-1.6C433.5 260.8 427 182 377 132c-56.5-56.5-148-56.5-204.5 0L60.2 244.3z' },
        'serviceescalation': { viewBox: '0 0 384 512', path: 'M214.6 41.4c-12.5-12.5-32.8-12.5-45.3 0l-160 160c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L160 141.2V448c0 17.7 14.3 32 32 32s32-14.3 32-32V141.2L329.4 246.6c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3l-160-160z' },
        'hostescalation': { viewBox: '0 0 384 512', path: 'M214.6 41.4c-12.5-12.5-32.8-12.5-45.3 0l-160 160c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L160 141.2V448c0 17.7 14.3 32 32 32s32-14.3 32-32V141.2L329.4 246.6c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3l-160-160z' }
    };

    const defaultIconSvg = { viewBox: '0 0 512 512', path: 'M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM169.8 165.3c7.9-22.3 29.1-37.3 52.8-37.3h58.3c34.9 0 63.1 28.3 63.1 63.1c0 22.6-12.1 43.5-31.7 54.8L280 264.4c-.2 13-10.9 23.6-24 23.6c-13.3 0-24-10.7-24-24V250.5c0-8.6 4.6-16.5 12.1-20.8l44.3-25.4c4.7-2.7 7.6-7.7 7.6-13.1c0-8.4-6.8-15.1-15.1-15.1H222.6c-3.4 0-6.4 2.1-7.5 5.3l-.4 1.2c-4.4 12.5-18.2 19-30.6 14.6s-19-18.2-14.6-30.6l.4-1.2zM224 352a32 32 0 1 1 64 0 32 32 0 1 1 -64 0z' };

    // Edge label formatting - convert field names to readable labels
    const edgeLabelMap = {
        'host_name': 'on host',
        'hostgroup_name': 'in group',
        'hostgroups': 'in group',
        'service_description': 'service',
        'servicegroup_name': 'in group',
        'servicegroups': 'in group',
        'contact_name': 'contact',
        'contacts': 'notifies',
        'contact_groups': 'notifies',
        'contactgroup_name': 'in group',
        'contactgroup_members': 'includes',
        'hostgroup_members': 'has member',
        'servicegroup_members': 'has member',
        'notification_commands': 'notif cmd',
        'use': 'uses',
        'members': 'has member',
        'parents': 'parent',
        'check_command': 'check cmd',
        'event_handler': 'event cmd',
        'host_notification_commands': 'host notif cmd',
        'service_notification_commands': 'svc notif cmd',
        'check_period': 'check period',
        'notification_period': 'notify period',
        'host_notification_period': 'host notif period',
        'service_notification_period': 'svc notif period',
        'escalation_period': 'escalation period',
        'escalation_contacts': 'escalates to',          // N-04: Added missing label
        'escalation_contact_groups': 'escalates to',    // N-04: Added missing label
        'dependent_host_name': 'depends on',
        'dependent_hostgroup_name': 'depends on group',
        'dependent_service_description': 'depends on',
        'exclude': 'excludes'
    };

    // Edge colors by relationship type
    const edgeColors = {
        'use': '#9C27B0',           // Purple for template inheritance
        'members': '#4CAF50',        // Green for membership
        'host_name': '#2196F3',      // Blue for host relationships
        'hostgroups': '#8BC34A',     // Light green for hostgroups
        'contacts': '#FF9800',       // Orange for contacts
        'contact_groups': '#FFC107', // Yellow for contact groups
        'check_command': '#E91E63',  // Pink for commands
        'event_handler': '#E91E63',
        'host_notification_commands': '#E91E63',
        'service_notification_commands': '#E91E63',
        'parents': '#795548',        // Brown for parent relationships
        'check_period': '#607D8B',   // Gray for timeperiods
        'notification_period': '#607D8B',
        'host_notification_period': '#607D8B',
        'service_notification_period': '#607D8B',
        'escalation_period': '#607D8B',
        'escalation_contacts': '#00BCD4',     // N-04: Cyan - matches escalation object color
        'escalation_contact_groups': '#00BCD4', // N-04: Cyan - matches escalation object color
        'dependent_host_name': '#F44336',      // Red for dependencies
        'dependent_hostgroup_name': '#F44336',
        'dependent_service_description': '#E91E63',
        'exclude': '#607D8B',             // Gray - matches timeperiod colors
        'contact_name': '#FF9800',        // Orange for contacts
        'contactgroup_name': '#FFC107',   // Yellow for contact groups
        'contactgroup_members': '#FF9800', // Orange for contact membership
        'hostgroup_name': '#8BC34A',      // Light green for hostgroup refs
        'hostgroup_members': '#4CAF50',   // Green for hostgroup membership
        'servicegroup_name': '#03A9F4',   // Cyan for servicegroup refs
        'servicegroup_members': '#03A9F4', // Cyan for servicegroup membership
        'servicegroups': '#03A9F4',       // Cyan for servicegroups
        'service_description': '#2196F3', // Blue for service refs
        'notification_commands': '#E91E63' // Pink for notification commands
    };

    // Export all configuration objects
    window.DepsConfig = {
        LAYOUT_CONFIG,
        edgeCategories,
        viewModePresets,
        quickViewPresets,
        expansionRules,
        typeColors,
        typeIconSvg,
        defaultIconSvg,
        edgeLabelMap,
        edgeColors
    };
})();
