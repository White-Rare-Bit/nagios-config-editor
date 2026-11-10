/**
 * Nagios Bulk Editor - Graph View configuration
 *
 * Presentation and exploration settings for the graph page: layout constants,
 * quick view presets, the expansion rules each preset follows, and node icons.
 *
 * Domain metadata (object type colours, edge field labels, colours and
 * categories) is not here: it comes from GET /api/metadata ("graph"), defined
 * in app/nagios_model.py.
 */

export const LAYOUT_CONFIG = {
    // Fitting a small graph to the view never zooms in further than this.
    maxFitZoom: 1.4,
    // Hierarchical layouts (dagre). Node boxes are sized from their labels so
    // long labels don't overlap their neighbours.
    dagre: {
        nodeSep: 30,
        rankSep: 110,         // between ranks, top-to-bottom
        rankSepLR: 170,       // between ranks, left-to-right
        nodeHeight: 80,       // icon plus label
        minNodeWidth: 70,
        maxNodeWidth: 190,    // matches the label's text-max-width
        charWidth: 6.5        // approximate width of one label character
    },
    // Clustered layout (with a focus node): type clusters around the focus.
    cluster: {
        clusterDistance: 600,     // focus node to cluster centre
        clusterRadius: 100,       // first ring of nodes inside a cluster
        clusterRadiusStep: 90,    // each further ring
        nodesPerRing: 8,          // nodes in a cluster's first ring
        orbitGap: 150,            // parent cluster to an orbiting cluster
        minNodeDistance: 80       // collision resolution pushes nodes this far apart
    },
    // Force-directed layout (cose), used when there is no focus node.
    cose: {
        idealEdgeLength: 150,
        nodeOverlap: 20,
        nodeRepulsion: 8000,
        edgeElasticity: 100,
        nestingFactor: 5,
        gravity: 80,
        numIter: 500,
        initialTemp: 200,
        coolingFactor: 0.95,
        minTemp: 1.0,
        componentSpacing: 100
    }
};

export const GRAPH_LIMITS = {
    // Search results shown in the dropdown.
    searchResults: 30
};

// Quick view presets, in button order. Each answers one question about the
// focus node. `types` limits which object types the view collects and shows
// (null = any type). The edges a rule-based view shows are the ones its
// expansion rules follow; Full Graph shows every category.
export const quickViewPresets = {
    inheritance: {
        layout: 'hierarchical',  // templates above the objects that use them
        types: null,
        description: 'Templates this object inherits from (for a template, also what inherits from it)',
        icon: 'fa-sitemap',
        label: 'Inheritance'
    },
    network: {
        layout: 'hierarchical',  // parent hosts above their children
        types: ['host', 'hostgroup', 'service', 'servicegroup', 'hostdependency', 'servicedependency',
                'hostescalation', 'serviceescalation'],
        description: 'Host parent-child topology and service bindings',
        icon: 'fa-network-wired',
        label: 'Network'
    },
    notifications: {
        layout: 'hierarchicalLR',
        types: ['host', 'hostgroup', 'service', 'servicegroup', 'contact', 'contactgroup',
                'hostescalation', 'serviceescalation'],
        description: 'Notification routing to contacts',
        icon: 'fa-bell',
        label: 'Notifications'
    },
    services: {
        layout: 'hierarchicalLR',
        types: ['host', 'hostgroup', 'service'],
        description: 'Services monitoring this host (including via hostgroups)',
        icon: 'fa-gear',
        label: 'Services'
    },
    members: {
        layout: 'hierarchicalLR',
        types: null,
        description: 'Members of this group',
        icon: 'fa-users',
        label: 'Members'
    },
    notifiedBy: {
        layout: 'hierarchicalLR',
        types: ['host', 'hostgroup', 'service', 'servicegroup', 'contact', 'contactgroup',
                'hostescalation', 'serviceescalation'],
        description: 'What notifies this contact/group',
        icon: 'fa-bell',
        label: 'Notified By'
    },
    usedBy: {
        layout: 'hierarchicalLR',
        types: null,
        description: 'Objects using this command/timeperiod',
        icon: 'fa-arrow-left',
        label: 'Used By'
    },
    monitoring: {
        layout: 'hierarchicalLR',
        types: ['host', 'service', 'command', 'timeperiod', 'hostdependency', 'servicedependency'],
        description: 'Check commands and time periods',
        icon: 'fa-clock',
        label: 'Monitoring'
    },
    escalations: {
        layout: 'hierarchicalLR',
        types: ['host', 'hostgroup', 'service', 'servicegroup', 'contact', 'contactgroup',
                'hostescalation', 'serviceescalation', 'timeperiod'],
        description: 'Escalation paths for this object',
        icon: 'fa-arrow-up',
        label: 'Escalations'
    },
    dependencies: {
        layout: 'hierarchical',
        types: ['host', 'hostgroup', 'service', 'servicegroup', 'hostdependency', 'servicedependency'],
        description: 'Dependency rules affecting this object',
        icon: 'fa-link',
        label: 'Dependencies'
    },
    full: {
        layout: 'static',  // clustered around the focus node
        types: null,
        description: 'Everything Nagios applies to this object: templates, services, contacts, commands, time periods',
        smartExpansion: true,  // model.expandEffective, not expansionRules
        icon: 'fa-diagram-project',
        label: 'Full Graph'
    }
};

// Inheritance, the same for every type: follow `use` up to the ancestors.
// Only a template also shows its descendants (`use` followed backward), and a
// path never turns around, so an ancestor's other children are not pulled in.
const inheritanceRule = {
    forward: ['use'],
    backward: ['use'],
    monotonic: true,
    backwardFromTemplateOnly: true
};

// Declarative expansion rules, keyed by (focus object type, preset). A preset
// is offered for a type exactly when a rule exists for it here (Full Graph is
// offered for every type).
//
// forward: fields followed from the object that has them to the object named
// backward: fields followed from the object named back to the one that has them
// atType: extra forward/backward fields used at nodes of that type
// stopAt: types that are not entered (the focus node itself is exempt)
// monotonic: a path that went forward never goes backward, and vice versa
// backwardFromTemplateOnly: backward edges are followed only when the focus is a template
export const expansionRules = {
    host: {
        inheritance: inheritanceRule,
        services: {
            // Services bound directly + services via hostgroups.
            // stopAt prevents sibling host expansion.
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
        },
        notifications: {
            // Notification routing to contacts; contactgroups expand to members
            forward: ['contacts', 'contact_groups'],
            atType: {
                contactgroup: { forward: ['members'] }
            }
        },
        monitoring: {
            forward: ['check_command', 'check_period', 'notification_period', 'event_handler']
        },
        escalations: {
            // Hostescalations targeting this host (directly or via hostgroups)
            forward: ['hostgroups'],
            backward: ['host_name'],
            atType: {
                hostgroup: { backward: ['hostgroup_name'] },
                hostescalation: { forward: ['contacts', 'contact_groups', 'escalation_period'] }
            }
        },
        dependencies: {
            // Hostdependencies where this host is dependent or master
            backward: ['dependent_host_name', 'host_name', 'master_host_name'],
            atType: {
                hostdependency: { forward: ['dependent_host_name', 'host_name', 'master_host_name',
                                            'dependent_hostgroup_name', 'hostgroup_name', 'master_hostgroup_name'] }
            }
        }
    },
    hostgroup: {
        inheritance: inheritanceRule,
        services: {
            // Services targeting this hostgroup; stopAt prevents host expansion
            backward: ['hostgroup_name'],
            stopAt: ['host']
        },
        members: {
            // Hosts in this group + nested hostgroups
            forward: ['members', 'hostgroup_members'],
            backward: ['hostgroups']
        },
        notifications: {
            forward: ['contacts', 'contact_groups'],
            atType: {
                contactgroup: { forward: ['members'] }
            }
        },
        escalations: {
            backward: ['hostgroup_name'],
            atType: {
                hostescalation: { forward: ['contacts', 'contact_groups', 'escalation_period'] }
            }
        },
        dependencies: {
            backward: ['dependent_hostgroup_name', 'hostgroup_name', 'master_hostgroup_name'],
            atType: {
                hostdependency: { forward: ['dependent_host_name', 'host_name', 'master_host_name'] }
            }
        }
    },
    service: {
        inheritance: inheritanceRule,
        network: {
            // Host binding, service parents, and service dependencies
            forward: ['host_name', 'hostgroup_name', 'parents'],
            backward: ['dependent_service_description', 'service_description']
        },
        monitoring: {
            forward: ['check_command', 'check_period', 'notification_period', 'event_handler']
        },
        notifications: {
            forward: ['contacts', 'contact_groups'],
            atType: {
                contactgroup: { forward: ['members'] }
            }
        },
        escalations: {
            backward: ['service_description'],
            atType: {
                serviceescalation: { forward: ['contacts', 'contact_groups', 'escalation_period'] }
            }
        },
        dependencies: {
            backward: ['dependent_service_description', 'service_description', 'master_service_description'],
            atType: {
                servicedependency: { forward: ['dependent_service_description', 'service_description',
                                               'master_service_description', 'dependent_host_name',
                                               'host_name', 'master_host_name'] }
            }
        }
    },
    servicegroup: {
        inheritance: inheritanceRule,
        members: {
            // Services in this group + nested servicegroups
            forward: ['members', 'servicegroup_members'],
            backward: ['servicegroups']
        },
        notifications: {
            forward: ['contacts', 'contact_groups'],
            atType: {
                contactgroup: { forward: ['members'] }
            }
        },
        escalations: {
            backward: ['servicegroup_name'],
            atType: {
                serviceescalation: { forward: ['contacts', 'contact_groups', 'escalation_period'] }
            }
        },
        dependencies: {
            backward: ['servicegroup_name', 'dependent_servicegroup_name'],
            atType: {
                servicedependency: { forward: ['dependent_service_description', 'service_description',
                                               'master_service_description'] }
            }
        }
    },
    contact: {
        inheritance: inheritanceRule,
        notifiedBy: {
            // Objects that notify this contact
            forward: ['contactgroups'],
            backward: ['contacts', 'members'],
            atType: {
                contactgroup: { backward: ['contact_groups'] }
            }
        }
    },
    contactgroup: {
        inheritance: inheritanceRule,
        members: {
            forward: ['members', 'contactgroup_members']
        },
        notifiedBy: {
            backward: ['contact_groups']
        }
    },
    command: {
        usedBy: {
            backward: ['check_command', 'event_handler', 'host_notification_commands',
                       'service_notification_commands', 'notification_commands']
        }
    },
    timeperiod: {
        usedBy: {
            backward: ['check_period', 'notification_period', 'host_notification_period',
                       'service_notification_period', 'escalation_period', 'dependency_period', 'exclude']
        }
    },
    hostdependency: {
        inheritance: inheritanceRule,
        dependencies: {
            // The hosts and hostgroups on both sides of this dependency
            forward: ['dependent_host_name', 'dependent_hostgroup_name', 'host_name', 'hostgroup_name',
                      'master_host_name', 'master_hostgroup_name']
        },
        monitoring: {
            forward: ['dependency_period']
        }
    },
    servicedependency: {
        inheritance: inheritanceRule,
        dependencies: {
            // The services, hosts and groups on both sides of this dependency
            forward: ['dependent_service_description', 'dependent_host_name', 'dependent_hostgroup_name',
                      'dependent_servicegroup_name', 'service_description', 'host_name', 'hostgroup_name',
                      'servicegroup_name', 'master_service_description', 'master_host_name',
                      'master_hostgroup_name']
        },
        monitoring: {
            forward: ['dependency_period']
        }
    },
    hostescalation: {
        inheritance: inheritanceRule,
        notifications: {
            forward: ['contacts', 'contact_groups', 'escalation_period'],
            atType: {
                contactgroup: { forward: ['members'] }
            }
        },
        escalations: {
            // Hosts/hostgroups this escalation targets
            forward: ['host_name', 'hostgroup_name', 'contacts', 'contact_groups', 'escalation_period'],
            atType: {
                contactgroup: { forward: ['members'] }
            }
        }
    },
    serviceescalation: {
        inheritance: inheritanceRule,
        notifications: {
            forward: ['contacts', 'contact_groups', 'escalation_period'],
            atType: {
                contactgroup: { forward: ['members'] }
            }
        },
        escalations: {
            // Hosts/services this escalation targets
            forward: ['host_name', 'hostgroup_name', 'service_description', 'servicegroup_name',
                      'contacts', 'contact_groups', 'escalation_period'],
            atType: {
                contactgroup: { forward: ['members'] }
            }
        }
    }
};

// FontAwesome SVG paths for each type (with viewBox dimensions)
export const typeIconSvg = {
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

export const defaultIconSvg = { viewBox: '0 0 512 512', path: 'M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM169.8 165.3c7.9-22.3 29.1-37.3 52.8-37.3h58.3c34.9 0 63.1 28.3 63.1 63.1c0 22.6-12.1 43.5-31.7 54.8L280 264.4c-.2 13-10.9 23.6-24 23.6c-13.3 0-24-10.7-24-24V250.5c0-8.6 4.6-16.5 12.1-20.8l44.3-25.4c4.7-2.7 7.6-7.7 7.6-13.1c0-8.4-6.8-15.1-15.1-15.1H222.6c-3.4 0-6.4 2.1-7.5 5.3l-.4 1.2c-4.4 12.5-18.2 19-30.6 14.6s-19-18.2-14.6-30.6l.4-1.2zM224 352a32 32 0 1 1 64 0 32 32 0 1 1 -64 0z' };
