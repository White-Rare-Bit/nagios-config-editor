/**
 * Tests for dependency graph expansion rules
 * Uses production expansionRules and expandWithRules from dependencies.js
 */

// Mock D3 library before loading dependencies.js
global.d3 = {
    select: jest.fn(() => ({
        selectAll: jest.fn(() => ({ remove: jest.fn() })),
        append: jest.fn(() => ({ attr: jest.fn(() => ({ attr: jest.fn() })) }))
    })),
    zoom: jest.fn(() => ({ on: jest.fn(), transform: jest.fn() })),
    zoomIdentity: { k: 1, x: 0, y: 0 }
};

// Load production code and get testable exports
const { expansionRules, expandWithRulesTestable } = require('../../static/js/dependencies.js');

describe('Expansion Rules', () => {
    let testNodes, testEdges, addedNodeIds;

    beforeEach(() => {
        // Set up test graph structure
        testNodes = [
            { id: 'host:web-prod-01', type: 'host', label: 'web-prod-01' },
            { id: 'host:web-prod-02', type: 'host', label: 'web-prod-02' },
            { id: 'hostgroup:production', type: 'hostgroup', label: 'production' },
            { id: 'service:http-check', type: 'service', label: 'HTTP Check' },
            { id: 'service:disk-check', type: 'service', label: 'Disk Check' },
            { id: 'contact:admin', type: 'contact', label: 'admin' },
            { id: 'contactgroup:oncall', type: 'contactgroup', label: 'oncall' },
            { id: 'command:check_http', type: 'command', label: 'check_http' }
        ];

        testEdges = [
            // Host → Hostgroup membership
            { from: 'host:web-prod-01', to: 'hostgroup:production', label: 'hostgroups' },
            { from: 'host:web-prod-02', to: 'hostgroup:production', label: 'hostgroups' },
            // Service → Host bindings
            { from: 'service:http-check', to: 'host:web-prod-01', label: 'host_name' },
            { from: 'service:disk-check', to: 'hostgroup:production', label: 'hostgroup_name' },
            // Contact routing
            { from: 'host:web-prod-01', to: 'contactgroup:oncall', label: 'contact_groups' },
            { from: 'contactgroup:oncall', to: 'contact:admin', label: 'members' },
            // Command usage
            { from: 'service:http-check', to: 'command:check_http', label: 'check_command' }
        ];

        addedNodeIds = new Set();
    });

    describe('expansionRules structure', () => {
        test('has rules for host type', () => {
            expect(expansionRules.host).toBeDefined();
            expect(expansionRules.host.services).toBeDefined();
            expect(expansionRules.host.services.stopAt).toContain('host');
        });

        test('has rules for hostgroup type', () => {
            expect(expansionRules.hostgroup).toBeDefined();
            expect(expansionRules.hostgroup.members).toBeDefined();
        });

        test('has rules for contact type', () => {
            expect(expansionRules.contact).toBeDefined();
            expect(expansionRules.contact.notifiedBy).toBeDefined();
        });
    });

    describe('expandWithRules behavior', () => {
        test('host services preset finds services but not sibling hosts', () => {
            addedNodeIds.clear();
            addedNodeIds.add('host:web-prod-01');  // Root added by applyQuickView before expansion
            expandWithRulesTestable('host:web-prod-01', 'services', testNodes, testEdges, addedNodeIds);

            expect(addedNodeIds.has('host:web-prod-01')).toBe(true);
            expect(addedNodeIds.has('service:http-check')).toBe(true);
            expect(addedNodeIds.has('hostgroup:production')).toBe(true);
            expect(addedNodeIds.has('service:disk-check')).toBe(true);
            // Sibling host blocked by stopAt
            expect(addedNodeIds.has('host:web-prod-02')).toBe(false);
        });

        test('hostgroup members preset finds hosts in group', () => {
            addedNodeIds.clear();
            addedNodeIds.add('hostgroup:production');  // Root added by applyQuickView before expansion
            expandWithRulesTestable('hostgroup:production', 'members', testNodes, testEdges, addedNodeIds);

            expect(addedNodeIds.has('hostgroup:production')).toBe(true);
            expect(addedNodeIds.has('host:web-prod-01')).toBe(true);
            expect(addedNodeIds.has('host:web-prod-02')).toBe(true);
        });

        test('contact notifiedBy preset finds objects notifying contact', () => {
            addedNodeIds.clear();
            addedNodeIds.add('contact:admin');  // Root added by applyQuickView before expansion
            expandWithRulesTestable('contact:admin', 'notifiedBy', testNodes, testEdges, addedNodeIds);

            expect(addedNodeIds.has('contact:admin')).toBe(true);
            expect(addedNodeIds.has('contactgroup:oncall')).toBe(true);
            expect(addedNodeIds.has('host:web-prod-01')).toBe(true);
        });

        test('undefined preset shows only starting node', () => {
            addedNodeIds.clear();
            addedNodeIds.add('host:web-prod-01');  // Only root added by caller
            expandWithRulesTestable('host:web-prod-01', 'nonexistent', testNodes, testEdges, addedNodeIds);

            // expandWithRules returns early for undefined rules, so only root remains
            expect(addedNodeIds.size).toBe(1);
            expect(addedNodeIds.has('host:web-prod-01')).toBe(true);
        });

        test('atType rule merging applies union of base and type-specific rules', () => {
            // When expanding from host through hostgroup, both base backward rules
            // and atType.hostgroup.backward rules should be applied (union behavior)
            addedNodeIds.clear();
            addedNodeIds.add('host:web-prod-01');  // Root added by applyQuickView before expansion
            expandWithRulesTestable('host:web-prod-01', 'services', testNodes, testEdges, addedNodeIds);

            // host.services has backward: ['host_name'] (base rule)
            // atType.hostgroup.backward: ['hostgroup_name'] (type-specific rule)
            // Union enables finding both direct services and hostgroup services
            expect(addedNodeIds.has('service:http-check')).toBe(true);  // Via host_name backward
            expect(addedNodeIds.has('service:disk-check')).toBe(true);  // Via hostgroup_name backward
        });

        test('stopAt nodes excluded from graph (observable behavior)', () => {
            // Test via observable behavior: stopAt nodes should not appear in graph
            addedNodeIds.clear();
            addedNodeIds.add('hostgroup:production');  // Root added by applyQuickView before expansion
            expandWithRulesTestable('hostgroup:production', 'services', testNodes, testEdges, addedNodeIds);

            // Services view from hostgroup: finds services, excludes hosts (stopAt: ['host'])
            expect(addedNodeIds.has('hostgroup:production')).toBe(true);
            expect(addedNodeIds.has('service:disk-check')).toBe(true);
            // Hosts traversed but not added (stopAt behavior)
            expect(addedNodeIds.has('host:web-prod-01')).toBe(false);
            expect(addedNodeIds.has('host:web-prod-02')).toBe(false);
        });

        test('root node persists even if its type is in stopAt', () => {
            // Root node added before expandWithRules call (line 1819 in applyQuickView)
            // should persist even if its type matches stopAt array
            addedNodeIds.clear();
            addedNodeIds.add('host:web-prod-01');  // Pre-added by applyQuickView

            // Create temporary rule with host in stopAt
            const originalRules = expansionRules.host;
            const testRules = {
                ...expansionRules,
                host: {
                    ...originalRules,
                    testPreset: {
                        forward: [],
                        backward: [],
                        stopAt: ['host']
                    }
                }
            };

            // Manually inject test rules by modifying the exported object
            expansionRules.host.testPreset = testRules.host.testPreset;

            expandWithRulesTestable('host:web-prod-01', 'testPreset', testNodes, testEdges, addedNodeIds);

            // Root should still be in graph despite stopAt
            expect(addedNodeIds.has('host:web-prod-01')).toBe(true);

            // Restore original rules
            delete expansionRules.host.testPreset;
        });
    });

    describe('type × preset completeness', () => {
        // All object types and their expected presets (excluding 'full' which uses smart expansion)
        const presetsByType = {
            host: ['inheritance', 'network', 'notifications', 'services', 'monitoring', 'escalations', 'dependencies'],
            hostgroup: ['inheritance', 'notifications', 'services', 'members', 'escalations', 'dependencies'],
            service: ['inheritance', 'network', 'notifications', 'monitoring', 'escalations', 'dependencies'],
            servicegroup: ['inheritance', 'network', 'notifications', 'members', 'escalations', 'dependencies'],
            contact: ['inheritance', 'notifiedBy'],
            contactgroup: ['inheritance', 'members', 'notifiedBy'],
            command: ['usedBy'],
            timeperiod: ['usedBy'],
            hostdependency: ['inheritance', 'network', 'monitoring'],
            servicedependency: ['inheritance', 'network', 'monitoring'],
            hostescalation: ['inheritance', 'notifications', 'network'],
            serviceescalation: ['inheritance', 'notifications', 'network']
        };

        // Test each type has expansion rules
        Object.keys(presetsByType).forEach(type => {
            test(`${type} has expansion rules defined`, () => {
                expect(expansionRules[type]).toBeDefined();
            });
        });

        // Test each type × preset combination has a rule
        Object.entries(presetsByType).forEach(([type, presets]) => {
            presets.forEach(preset => {
                test(`${type}.${preset} expansion rule exists`, () => {
                    expect(expansionRules[type]).toBeDefined();
                    expect(expansionRules[type][preset]).toBeDefined();
                    expect(expansionRules[type][preset]).toHaveProperty('forward');
                    expect(expansionRules[type][preset]).toHaveProperty('backward');
                    expect(expansionRules[type][preset]).toHaveProperty('stopAt');
                });
            });
        });

        // Test expansion rules have valid structure
        Object.entries(expansionRules).forEach(([type, rules]) => {
            Object.entries(rules).forEach(([preset, rule]) => {
                test(`${type}.${preset} rule has valid structure`, () => {
                    expect(Array.isArray(rule.forward)).toBe(true);
                    expect(Array.isArray(rule.backward)).toBe(true);
                    expect(Array.isArray(rule.stopAt)).toBe(true);
                    // atType is optional
                    if (rule.atType) {
                        expect(typeof rule.atType).toBe('object');
                    }
                });
            });
        });
    });

    describe('expansion rule execution', () => {
        // Test that expandWithRulesTestable executes without error for each type × preset
        const typesToTest = ['host', 'hostgroup', 'service', 'servicegroup', 'contact', 'contactgroup'];

        typesToTest.forEach(type => {
            const presets = Object.keys(expansionRules[type] || {});
            presets.forEach(preset => {
                test(`expandWithRulesTestable executes for ${type}.${preset}`, () => {
                    const nodeId = `${type}:test-node`;
                    const nodes = [{ id: nodeId, type: type, label: 'test-node' }];
                    const edges = [];
                    const resultSet = new Set([nodeId]);

                    // Should not throw
                    expect(() => {
                        expandWithRulesTestable(nodeId, preset, nodes, edges, resultSet);
                    }).not.toThrow();

                    // Root should still be in result
                    expect(resultSet.has(nodeId)).toBe(true);
                });
            });
        });
    });

    describe('inheritance preset coverage', () => {
        // All types should have inheritance preset (templates are universal)
        const typesWithInheritance = [
            'host', 'hostgroup', 'service', 'servicegroup',
            'contact', 'contactgroup',
            'hostdependency', 'servicedependency',
            'hostescalation', 'serviceescalation'
        ];

        typesWithInheritance.forEach(type => {
            test(`${type} has inheritance preset with use edges`, () => {
                expect(expansionRules[type].inheritance).toBeDefined();
                expect(expansionRules[type].inheritance.forward).toContain('use');
                expect(expansionRules[type].inheritance.backward).toContain('use');
            });
        });
    });

    describe('dependencies preset coverage', () => {
        // Types that can be involved in dependencies
        const typesWithDependencies = ['host', 'hostgroup', 'service', 'servicegroup'];

        typesWithDependencies.forEach(type => {
            test(`${type} has dependencies preset`, () => {
                expect(expansionRules[type].dependencies).toBeDefined();
                expect(Array.isArray(expansionRules[type].dependencies.backward)).toBe(true);
                // Dependencies preset should have backward edges to find dependency rules
                expect(expansionRules[type].dependencies.backward.length).toBeGreaterThan(0);
            });
        });
    });

    describe('nested group support', () => {
        test('hostgroup.members follows hostgroup_members for nesting', () => {
            expect(expansionRules.hostgroup.members.forward).toContain('hostgroup_members');
        });

        test('servicegroup.members follows servicegroup_members for nesting', () => {
            expect(expansionRules.servicegroup.members.forward).toContain('servicegroup_members');
        });

        test('contactgroup.members follows contactgroup_members for nesting', () => {
            expect(expansionRules.contactgroup.members.forward).toContain('contactgroup_members');
        });
    });
});
