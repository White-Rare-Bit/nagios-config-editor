import test from 'node:test';
import assert from 'node:assert/strict';
import {
    buildGraphIndex, edgesFrom, edgesTo, expandEffective, expandWithRules, ruleFields,
    presetsForType, computeDisplay, searchNodes
} from '../../app/static/js/graph/model.js';
import { expansionRules, quickViewPresets } from '../../app/static/js/dependencies-config.js';

// A small graph with the edge directions /api/dependencies produces: from the
// object that has the field to the object it names (`parents`: parent -> child).
const N = (id, extra = {}) => {
    const [type] = id.split(':');
    return { id, type, label: id.slice(type.length + 1), exists: true, ...extra };
};
const E = (from, label, to, category = 'dependencies') => ({ from, to, label, category });

const nodes = [
    N('host:generic-host', { is_template: true }),
    N('host:linux-server', { is_template: true }),
    N('host:windows-server', { is_template: true }),
    N('host:web-01'),
    N('host:web-02'),
    N('host:router'),
    N('hostgroup:web'),
    N('service:web:HTTP', { label: 'HTTP / web' }),
    N('service:web-01:Health', { label: 'Health / web-01' }),
    N('command:check_http'),
    N('timeperiod:24x7'),
    N('contactgroup:admins'),
    N('contact:alice'),
    N('servicedependency:dep1'),
    N('hostdependency:hdep'),
    N('service:web-09:Ghost', { label: 'Ghost / web-09', exists: false })
];
const edges = [
    E('host:web-01', 'use', 'host:linux-server', 'templates'),
    E('host:web-02', 'use', 'host:linux-server', 'templates'),
    E('host:linux-server', 'use', 'host:generic-host', 'templates'),
    E('host:windows-server', 'use', 'host:generic-host', 'templates'),
    E('host:web-01', 'hostgroups', 'hostgroup:web', 'groups'),
    E('hostgroup:web', 'members', 'host:web-02', 'groups'),
    E('host:router', 'parents', 'host:web-01'),
    E('service:web:HTTP', 'hostgroup_name', 'hostgroup:web', 'groups'),
    E('service:web:HTTP', 'check_command', 'command:check_http', 'commands'),
    E('service:web:HTTP', 'check_period', 'timeperiod:24x7', 'schedules'),
    E('service:web:HTTP', 'contact_groups', 'contactgroup:admins', 'contacts'),
    E('contactgroup:admins', 'members', 'contact:alice', 'contacts'),
    E('service:web-01:Health', 'host_name', 'host:web-01'),
    E('servicedependency:dep1', 'host_name', 'host:web-01'),
    E('servicedependency:dep1', 'service_description', 'service:web:HTTP'),
    E('servicedependency:dep1', 'dependent_service_description', 'service:web-01:Health'),
    E('hostdependency:hdep', 'dependent_host_name', 'host:web-01')
];
const index = buildGraphIndex(nodes, edges);

const expanded = (fn) => {
    const result = new Set();
    fn(result);
    return result;
};

test('index looks edges up by endpoint and label', () => {
    assert.deepEqual(edgesFrom(index, 'host:web-01', 'use').map(e => e.to), ['host:linux-server']);
    assert.deepEqual(edgesTo(index, 'host:linux-server', 'use').map(e => e.from).sort(),
        ['host:web-01', 'host:web-02']);
    assert.equal(edgesFrom(index, 'host:missing').length, 0);
});

test('index drops edges to unknown nodes', () => {
    const idx = buildGraphIndex([N('host:a')], [E('host:a', 'parents', 'host:gone')]);
    assert.equal(edgesFrom(idx, 'host:a').length, 0);
});

test('Full Graph of a host includes services bound by host_name and by hostgroup (GRAPH_REVIEW 1)', () => {
    const r = expanded(res => expandEffective(index, 'host:web-01', res));
    assert.ok(r.has('service:web-01:Health'), 'direct host_name service');
    assert.ok(r.has('service:web:HTTP'), 'service via hostgroup');
    assert.ok(r.has('hostgroup:web'));
});

test('Full Graph of a host includes its templates, settings and neighbours, not siblings', () => {
    const r = expanded(res => expandEffective(index, 'host:web-01', res));
    for (const id of ['host:linux-server', 'host:generic-host', 'command:check_http', 'timeperiod:24x7',
        'contactgroup:admins', 'contact:alice', 'host:router', 'hostdependency:hdep']) {
        assert.ok(r.has(id), id);
    }
    assert.ok(!r.has('host:web-02'), 'sibling host using the same template');
    assert.ok(!r.has('host:windows-server'), 'sibling template');
});

test('Full Graph of a service includes its host (GRAPH_REVIEW 1)', () => {
    const r = expanded(res => expandEffective(index, 'service:web-01:Health', res));
    assert.ok(r.has('host:web-01'));
    assert.ok(r.has('servicedependency:dep1'));
});

test('Full Graph of a template follows use upward only', () => {
    const r = expanded(res => expandEffective(index, 'host:linux-server', res));
    assert.deepEqual([...r].sort(), ['host:generic-host', 'host:linux-server']);
});

test('Full Graph of a dependency includes everything it names', () => {
    const r = expanded(res => expandEffective(index, 'servicedependency:dep1', res));
    assert.deepEqual([...r].sort(), ['host:web-01', 'service:web-01:Health', 'service:web:HTTP',
        'servicedependency:dep1']);
});

test('Inheritance of a registered object shows ancestors only (GRAPH_REVIEW 4)', () => {
    const r = expanded(res => expandWithRules(index, 'host:web-01', expansionRules.host.inheritance, res));
    assert.deepEqual([...r].sort(), ['host:generic-host', 'host:linux-server', 'host:web-01']);
});

test('Inheritance of a template adds its descendants but not its ancestors\' other children', () => {
    const r = expanded(res => expandWithRules(index, 'host:linux-server', expansionRules.host.inheritance, res));
    assert.deepEqual([...r].sort(), ['host:generic-host', 'host:linux-server', 'host:web-01', 'host:web-02']);
});

test('Services view collects only the preset\'s types (GRAPH_REVIEW 5)', () => {
    const allowedTypes = new Set(quickViewPresets.services.types);
    const r = expanded(res => expandWithRules(index, 'host:web-01', expansionRules.host.services, res,
        { allowedTypes }));
    assert.ok(r.has('service:web-01:Health'));
    assert.ok(r.has('service:web:HTTP'));
    assert.ok(!r.has('servicedependency:dep1'), 'dependency also names the host by host_name');
    assert.ok(!r.has('host:web-02'), 'stopAt keeps sibling hosts out');
});

test('a rule\'s fields are the edges its view shows', () => {
    assert.deepEqual([...ruleFields(expansionRules.host.services)].sort(),
        ['host_name', 'hostgroup_name', 'hostgroups']);
});

test('quick views offered for a type are the ones with rules, plus Full Graph', () => {
    assert.ok(presetsForType(expansionRules, quickViewPresets, 'host').includes('services'));
    assert.deepEqual(presetsForType(expansionRules, quickViewPresets, 'command'), ['usedBy', 'full']);
    // Previously offered without a rule, so the button did nothing.
    assert.ok(presetsForType(expansionRules, quickViewPresets, 'hostdependency').includes('dependencies'));
    assert.deepEqual(presetsForType(expansionRules, quickViewPresets, 'unknowntype'), ['full']);
});

test('every quick view offered for a type has a rule or uses smart expansion', () => {
    for (const type of Object.keys(expansionRules)) {
        for (const preset of presetsForType(expansionRules, quickViewPresets, type)) {
            assert.ok(quickViewPresets[preset].smartExpansion || expansionRules[type][preset], `${type}/${preset}`);
        }
    }
});

test('display hides filtered types and nodes left without a visible edge', () => {
    const addedIds = new Set(['host:web-01', 'host:linux-server', 'service:web-01:Health', 'servicedependency:dep1']);
    const d = computeDisplay(index, {
        addedIds,
        enabledTypes: new Set(['host', 'service']),
        edgeFilter: { fields: null, categories: new Set(['templates']) }
    });
    assert.deepEqual(d.nodes.map(n => n.id).sort(), ['host:linux-server', 'host:web-01']);
    assert.deepEqual(d.edges.map(e => e.label), ['use']);
    assert.match(d.hidden.get('servicedependency:dep1'), /filtered out/);
    assert.match(d.hidden.get('service:web-01:Health'), /no connection/);
});

test('display keeps pinned nodes and filters edges by field in a quick view', () => {
    const d = computeDisplay(index, {
        addedIds: new Set(['host:web-01', 'service:web-01:Health', 'host:router']),
        enabledTypes: new Set(['host', 'service']),
        edgeFilter: { fields: new Set(['host_name']), categories: new Set() },
        pinnedIds: new Set(['host:router'])
    });
    assert.deepEqual(d.nodes.map(n => n.id).sort(), ['host:router', 'host:web-01', 'service:web-01:Health']);
    assert.deepEqual(d.edges.map(e => e.label), ['host_name']);
    assert.equal(d.hidden.size, 0);
});

test('search ranks exact and prefix matches first and reports the total (GRAPH_REVIEW 12)', () => {
    const many = Array.from({ length: 40 }, (_, i) => N(`host:web-check-${i}`));
    const pool = [...many, N('command:check')];
    const { results, total } = searchNodes(pool, 'check', { limit: 30 });
    assert.equal(total, 41);
    assert.equal(results.length, 30);
    assert.equal(results[0].id, 'command:check', 'exact match first though it comes last');
});

test('search can be limited to a type and puts undefined objects after defined ones', () => {
    assert.deepEqual(searchNodes(nodes, 'web', { type: 'hostgroup' }).results.map(n => n.id), ['hostgroup:web']);
    const svc = searchNodes(nodes, 'web-0', { type: 'service' }).results.map(n => n.id);
    assert.equal(svc.at(-1), 'service:web-09:Ghost');
    assert.equal(searchNodes(nodes, '   ').total, 0);
});
