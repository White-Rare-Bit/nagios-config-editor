import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { hierarchicalPositions, clusterPositions, bundleEdges } from '../../app/static/js/graph/layout.js';
import { LAYOUT_CONFIG } from '../../app/static/js/dependencies-config.js';

// The page loads this vendored dagre (UMD) as a global; here it runs as CommonJS.
const dagreModule = { exports: {} };
vm.runInNewContext(
    readFileSync(new URL('../../app/static/vendor/js/dagre.min.js', import.meta.url), 'utf8'),
    { module: dagreModule, exports: dagreModule.exports });
const dagre = dagreModule.exports;

const node = (id) => ({ id, type: id.split(':')[0], label: id.split(':')[1] });

test('hierarchical layout puts templates above the objects using them (GRAPH_REVIEW 2)', () => {
    const nodes = ['host:web-01', 'host:web-02', 'host:linux-server', 'host:generic-host', 'host:win-tpl']
        .map(node);
    const edges = [
        { from: 'host:web-01', to: 'host:linux-server', label: 'use' },
        { from: 'host:web-02', to: 'host:linux-server', label: 'use' },
        { from: 'host:linux-server', to: 'host:generic-host', label: 'use' },
        { from: 'host:win-tpl', to: 'host:generic-host', label: 'use' }
    ];
    const pos = hierarchicalPositions(dagre, nodes, edges,
        { rankDir: 'TB', ancestorFields: new Set(['use']), config: LAYOUT_CONFIG.dagre });
    assert.ok(pos['host:generic-host'].y < pos['host:linux-server'].y);
    assert.ok(pos['host:linux-server'].y < pos['host:web-01'].y);
    assert.equal(pos['host:web-01'].y, pos['host:web-02'].y);
    // The grandparent's other child sits beside the parent, not among the hosts.
    assert.equal(pos['host:win-tpl'].y, pos['host:linux-server'].y);
});

test('hierarchical layout follows edge direction for other fields', () => {
    const nodes = ['host:router', 'host:web-01', 'service:Health'].map(node);
    const edges = [
        { from: 'host:router', to: 'host:web-01', label: 'parents' },
        { from: 'service:Health', to: 'host:web-01', label: 'host_name' }
    ];
    const tb = hierarchicalPositions(dagre, nodes, edges,
        { rankDir: 'TB', ancestorFields: new Set(['use']), config: LAYOUT_CONFIG.dagre });
    assert.ok(tb['host:router'].y < tb['host:web-01'].y, 'parent above child');
    const lr = hierarchicalPositions(dagre, nodes, edges,
        { rankDir: 'LR', ancestorFields: new Set(['use']), config: LAYOUT_CONFIG.dagre });
    assert.ok(lr['service:Health'].x < lr['host:web-01'].x);
});

test('hierarchical layout places every node, connected or not', () => {
    const nodes = ['host:a', 'host:b', 'host:lonely'].map(node);
    const pos = hierarchicalPositions(dagre, nodes, [{ from: 'host:a', to: 'host:b', label: 'parents' }],
        { rankDir: 'TB', ancestorFields: new Set(), config: LAYOUT_CONFIG.dagre });
    assert.deepEqual(Object.keys(pos).sort(), ['host:a', 'host:b', 'host:lonely']);
});

test('clustered layout: focus at the origin, every node placed, unreachable nodes apart', () => {
    const nodes = [node('host:focus'), node('hostgroup:web'), node('contactgroup:admins'), node('contact:alice'),
        node('service:HTTP'), node('command:check_http'), node('host:island')];
    const edges = [
        { from: 'host:focus', to: 'hostgroup:web', label: 'hostgroups' },
        { from: 'service:HTTP', to: 'hostgroup:web', label: 'hostgroup_name' },
        { from: 'service:HTTP', to: 'contactgroup:admins', label: 'contact_groups' },
        { from: 'contactgroup:admins', to: 'contact:alice', label: 'members' },
        { from: 'service:HTTP', to: 'command:check_http', label: 'check_command' }
    ];
    const pos = clusterPositions(nodes, edges, 'host:focus', LAYOUT_CONFIG.cluster);
    assert.deepEqual(pos['host:focus'], { x: 0, y: 0 });
    assert.deepEqual(Object.keys(pos).sort(), nodes.map(n => n.id).sort());
    for (const p of Object.values(pos)) {assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y));}
    // Hostgroups sit to the left of the focus (angle π), contact groups above it.
    assert.ok(pos['hostgroup:web'].x < -100);
    assert.ok(pos['contactgroup:admins'].y < -100);
    // Contacts orbit the contact group cluster, further out than it.
    const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
    assert.ok(dist(pos['contact:alice'], pos['contactgroup:admins']) >= LAYOUT_CONFIG.cluster.orbitGap);
    assert.notDeepEqual(pos['host:island'], { x: 0, y: 0 });
});

test('clustered layout is empty without a focus node', () => {
    assert.deepEqual(clusterPositions([node('host:a')], [], null, LAYOUT_CONFIG.cluster), {});
});

test('edge bundling bends edges toward the target cluster, not straight-on ones', () => {
    const nodes = [node('host:a'), node('service:s1'), node('service:s2'), node('service:s3')];
    const positions = {
        'host:a': { x: 0, y: 0 },
        'service:s1': { x: 400, y: -200 },
        'service:s2': { x: 400, y: 0 },
        'service:s3': { x: 400, y: 200 }
    };
    const edges = ['service:s1', 'service:s2', 'service:s3'].map(to => ({ id: to, from: 'host:a', to }));
    const bends = bundleEdges(nodes, edges, positions);
    assert.ok(bends.has('service:s1'));
    assert.ok(bends.has('service:s3'));
    assert.ok(Math.sign(bends.get('service:s1')) !== Math.sign(bends.get('service:s3')));
    assert.ok(!bends.has('service:s2'), 'already pointing at the cluster centre');
});
