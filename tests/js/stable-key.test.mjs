import { test } from 'node:test';
import assert from 'node:assert/strict';
import { StableKey } from '../../app/static/js/stable-key.js';

test('build uses display_name before name', () => {
    const key = StableKey.build({
        source_file: '/etc/a.cfg', object_type: 'service',
        display_name: 'Disk', name: 'check_disk',
    });
    assert.equal(key, '/etc/a.cfg|service|Disk');
});

test('parse round-trips a key whose name contains |', () => {
    const key = StableKey.build({
        source_file: '/etc/a.cfg', object_type: 'host', name: 'web|01',
    });
    assert.deepEqual(StableKey.parse(key),
        { source_file: '/etc/a.cfg', object_type: 'host', name: 'web|01' });
});

test('findObject matches by display_name', () => {
    const objects = [
        { source_file: '/a.cfg', object_type: 'service', name: 'x', display_name: 'Disk' },
        { source_file: '/a.cfg', object_type: 'service', name: 'y', display_name: 'CPU' },
    ];
    assert.equal(StableKey.findObject('/a.cfg|service|CPU', objects), objects[1]);
});

test('parse accepts a base64 key', () => {
    const b64 = Buffer.from('/a.cfg|host|web01').toString('base64');
    assert.deepEqual(StableKey.parse(b64),
        { source_file: '/a.cfg', object_type: 'host', name: 'web01' });
});
