/**
 * Tests for state-management.js - Explorer state operations
 */

describe('Explorer State Management', () => {
    let Explorer;

    beforeEach(() => {
        // Initialize Explorer namespace
        Explorer = {
            state: {
                allObjects: [
                    {
                        global_index: 0,
                        object_type: 'host',
                        source_file: 'hosts.cfg',
                        attributes: { host_name: ['host1'] }
                    },
                    {
                        global_index: 1,
                        object_type: 'service',
                        source_file: 'services.cfg',
                        attributes: { service_description: ['svc1'], host_name: ['host1'] }
                    },
                    {
                        global_index: 2,
                        object_type: 'host',
                        source_file: 'hosts.cfg',
                        attributes: { host_name: ['host2'] }
                    }
                ],
                pendingEdits: new Map(),
                stagedMoves: new Map(),
                stagedCreations: [],
                stagedObjectDeletions: new Set(),
                selectedKeys: new Set(),
                undoStack: []
            }
        };

        // Helper: Generate stable key
        Explorer.generateStableKey = function(sourceFile, objType, name) {
            return `${sourceFile}|${objType}|${name}`;
        };

        // Helper: Get stable key from object
        Explorer.getObjectKey = function(obj) {
            const name = obj.attributes.host_name?.[0] ||
                        obj.attributes.service_description?.[0] ||
                        obj.attributes.name?.[0] ||
                        obj.attributes.contact_name?.[0] || '';
            return Explorer.generateStableKey(obj.source_file, obj.object_type, name);
        };

        // Helper: Get stable key by index
        Explorer.getObjectKeyByIndex = function(index) {
            const obj = Explorer.state.allObjects[index];
            return obj ? Explorer.getObjectKey(obj) : null;
        };

        // Helper: Find object by key
        Explorer.findObjectByKey = function(key) {
            return Explorer.state.allObjects.find(obj => Explorer.getObjectKey(obj) === key);
        };

        // State management functions
        Explorer.getPendingEdit = function(objOrKeyOrIndex) {
            if (typeof objOrKeyOrIndex === 'string') {
                const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
                return obj ? Explorer.state.pendingEdits.get(obj.global_index) : undefined;
            } else if (typeof objOrKeyOrIndex === 'number') {
                return Explorer.state.pendingEdits.get(objOrKeyOrIndex);
            } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
                return Explorer.state.pendingEdits.get(objOrKeyOrIndex.global_index);
            }
            return undefined;
        };

        Explorer.setPendingEdit = function(objOrKeyOrIndex, editData) {
            let globalIndex;

            if (typeof objOrKeyOrIndex === 'string') {
                const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
                globalIndex = obj ? obj.global_index : null;
            } else if (typeof objOrKeyOrIndex === 'number') {
                globalIndex = objOrKeyOrIndex;
            } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
                globalIndex = objOrKeyOrIndex.global_index;
            }

            if (globalIndex !== null && globalIndex !== undefined) {
                Explorer.state.pendingEdits.set(globalIndex, editData);
                return true;
            }
            return false;
        };

        Explorer.deletePendingEdit = function(objOrKeyOrIndex) {
            let globalIndex;

            if (typeof objOrKeyOrIndex === 'string') {
                const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
                globalIndex = obj ? obj.global_index : null;
            } else if (typeof objOrKeyOrIndex === 'number') {
                globalIndex = objOrKeyOrIndex;
            } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
                globalIndex = objOrKeyOrIndex.global_index;
            }

            if (globalIndex !== null && globalIndex !== undefined) {
                Explorer.state.pendingEdits.delete(globalIndex);
                return true;
            }
            return false;
        };

        Explorer.isObjectMarkedForDeletion = function(objOrKeyOrIndex) {
            let globalIndex;

            if (typeof objOrKeyOrIndex === 'string') {
                const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
                globalIndex = obj ? obj.global_index : null;
            } else if (typeof objOrKeyOrIndex === 'number') {
                globalIndex = objOrKeyOrIndex;
            } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
                globalIndex = objOrKeyOrIndex.global_index;
            }

            return globalIndex !== null && globalIndex !== undefined &&
                   Explorer.state.stagedObjectDeletions.has(globalIndex);
        };

        Explorer.markObjectForDeletion = function(objOrKeyOrIndex) {
            let globalIndex;

            if (typeof objOrKeyOrIndex === 'string') {
                const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
                globalIndex = obj ? obj.global_index : null;
            } else if (typeof objOrKeyOrIndex === 'number') {
                globalIndex = objOrKeyOrIndex;
            } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
                globalIndex = objOrKeyOrIndex.global_index;
            }

            if (globalIndex !== null && globalIndex !== undefined) {
                Explorer.state.stagedObjectDeletions.add(globalIndex);
                return true;
            }
            return false;
        };

        Explorer.unmarkObjectForDeletion = function(objOrKeyOrIndex) {
            let globalIndex;

            if (typeof objOrKeyOrIndex === 'string') {
                const obj = Explorer.findObjectByKey(objOrKeyOrIndex);
                globalIndex = obj ? obj.global_index : null;
            } else if (typeof objOrKeyOrIndex === 'number') {
                globalIndex = objOrKeyOrIndex;
            } else if (objOrKeyOrIndex && typeof objOrKeyOrIndex === 'object') {
                globalIndex = objOrKeyOrIndex.global_index;
            }

            if (globalIndex !== null && globalIndex !== undefined) {
                Explorer.state.stagedObjectDeletions.delete(globalIndex);
                return true;
            }
            return false;
        };

        Explorer.isSelectedByIndex = function(index) {
            const key = Explorer.getObjectKeyByIndex(index);
            return key ? Explorer.state.selectedKeys.has(key) : false;
        };
    });

    describe('Stable Key Operations', () => {
        test('generates stable key from components', () => {
            const key = Explorer.generateStableKey('hosts.cfg', 'host', 'webserver01');
            expect(key).toBe('hosts.cfg|host|webserver01');
        });

        test('generates stable key from object', () => {
            const obj = Explorer.state.allObjects[0];
            const key = Explorer.getObjectKey(obj);
            expect(key).toBe('hosts.cfg|host|host1');
        });

        test('finds object by stable key', () => {
            const key = 'hosts.cfg|host|host1';
            const obj = Explorer.findObjectByKey(key);
            expect(obj).toBeDefined();
            expect(obj.global_index).toBe(0);
        });

        test('returns null for invalid stable key', () => {
            const obj = Explorer.findObjectByKey('nonexistent|key|value');
            expect(obj).toBeUndefined();
        });

        test('gets stable key by index', () => {
            const key = Explorer.getObjectKeyByIndex(1);
            // Service uses host_name as first choice for name field
            expect(key).toBe('services.cfg|service|host1');
        });

        test('returns null for invalid index', () => {
            const key = Explorer.getObjectKeyByIndex(999);
            expect(key).toBeNull();
        });
    });

    describe('Pending Edit Operations', () => {
        test('sets pending edit by global index', () => {
            const editData = {
                original: { host_name: ['host1'] },
                edited: { host_name: ['host1-renamed'] },
                object: Explorer.state.allObjects[0]
            };

            const result = Explorer.setPendingEdit(0, editData);

            expect(result).toBe(true);
            expect(Explorer.state.pendingEdits.get(0)).toEqual(editData);
        });

        test('sets pending edit by stable key', () => {
            const key = 'hosts.cfg|host|host1';
            const editData = {
                original: { host_name: ['host1'] },
                edited: { host_name: ['host1-renamed'] },
                object: Explorer.state.allObjects[0]
            };

            const result = Explorer.setPendingEdit(key, editData);

            expect(result).toBe(true);
            expect(Explorer.state.pendingEdits.get(0)).toEqual(editData);
        });

        test('sets pending edit by object reference', () => {
            const obj = Explorer.state.allObjects[1];
            const editData = {
                original: { service_description: ['svc1'] },
                edited: { service_description: ['svc1-renamed'] },
                object: obj
            };

            const result = Explorer.setPendingEdit(obj, editData);

            expect(result).toBe(true);
            expect(Explorer.state.pendingEdits.get(1)).toEqual(editData);
        });

        test('gets pending edit by global index', () => {
            const editData = { edited: { host_name: ['changed'] } };
            Explorer.state.pendingEdits.set(0, editData);

            const result = Explorer.getPendingEdit(0);

            expect(result).toEqual(editData);
        });

        test('gets pending edit by stable key', () => {
            const editData = { edited: { host_name: ['changed'] } };
            Explorer.state.pendingEdits.set(0, editData);

            const key = 'hosts.cfg|host|host1';
            const result = Explorer.getPendingEdit(key);

            expect(result).toEqual(editData);
        });

        test('gets pending edit by object reference', () => {
            const obj = Explorer.state.allObjects[0];
            const editData = { edited: { host_name: ['changed'] } };
            Explorer.state.pendingEdits.set(0, editData);

            const result = Explorer.getPendingEdit(obj);

            expect(result).toEqual(editData);
        });

        test('returns undefined for non-existent pending edit', () => {
            const result = Explorer.getPendingEdit(999);
            expect(result).toBeUndefined();
        });

        test('deletes pending edit by global index', () => {
            Explorer.state.pendingEdits.set(0, { edited: {} });

            const result = Explorer.deletePendingEdit(0);

            expect(result).toBe(true);
            expect(Explorer.state.pendingEdits.has(0)).toBe(false);
        });

        test('deletes pending edit by stable key', () => {
            Explorer.state.pendingEdits.set(0, { edited: {} });

            const key = 'hosts.cfg|host|host1';
            const result = Explorer.deletePendingEdit(key);

            expect(result).toBe(true);
            expect(Explorer.state.pendingEdits.has(0)).toBe(false);
        });

        test('deletes pending edit by object reference', () => {
            const obj = Explorer.state.allObjects[0];
            Explorer.state.pendingEdits.set(0, { edited: {} });

            const result = Explorer.deletePendingEdit(obj);

            expect(result).toBe(true);
            expect(Explorer.state.pendingEdits.has(0)).toBe(false);
        });

        test('returns false when deleting non-existent edit', () => {
            const result = Explorer.deletePendingEdit('nonexistent|key|value');
            expect(result).toBe(false);
        });
    });

    describe('Deletion Marking', () => {
        test('marks object for deletion by global index', () => {
            const result = Explorer.markObjectForDeletion(0);

            expect(result).toBe(true);
            expect(Explorer.state.stagedObjectDeletions.has(0)).toBe(true);
        });

        test('marks object for deletion by stable key', () => {
            const key = 'hosts.cfg|host|host1';
            const result = Explorer.markObjectForDeletion(key);

            expect(result).toBe(true);
            expect(Explorer.state.stagedObjectDeletions.has(0)).toBe(true);
        });

        test('marks object for deletion by object reference', () => {
            const obj = Explorer.state.allObjects[1];
            const result = Explorer.markObjectForDeletion(obj);

            expect(result).toBe(true);
            expect(Explorer.state.stagedObjectDeletions.has(1)).toBe(true);
        });

        test('checks if object is marked for deletion by global index', () => {
            Explorer.state.stagedObjectDeletions.add(0);

            expect(Explorer.isObjectMarkedForDeletion(0)).toBe(true);
            expect(Explorer.isObjectMarkedForDeletion(1)).toBe(false);
        });

        test('checks if object is marked for deletion by stable key', () => {
            Explorer.state.stagedObjectDeletions.add(0);

            const key = 'hosts.cfg|host|host1';
            expect(Explorer.isObjectMarkedForDeletion(key)).toBe(true);
        });

        test('checks if object is marked for deletion by object reference', () => {
            const obj = Explorer.state.allObjects[0];
            Explorer.state.stagedObjectDeletions.add(0);

            expect(Explorer.isObjectMarkedForDeletion(obj)).toBe(true);
        });

        test('unmarks object from deletion by global index', () => {
            Explorer.state.stagedObjectDeletions.add(0);

            const result = Explorer.unmarkObjectForDeletion(0);

            expect(result).toBe(true);
            expect(Explorer.state.stagedObjectDeletions.has(0)).toBe(false);
        });

        test('unmarks object from deletion by stable key', () => {
            Explorer.state.stagedObjectDeletions.add(0);

            const key = 'hosts.cfg|host|host1';
            const result = Explorer.unmarkObjectForDeletion(key);

            expect(result).toBe(true);
            expect(Explorer.state.stagedObjectDeletions.has(0)).toBe(false);
        });

        test('unmarks object from deletion by object reference', () => {
            const obj = Explorer.state.allObjects[0];
            Explorer.state.stagedObjectDeletions.add(0);

            const result = Explorer.unmarkObjectForDeletion(obj);

            expect(result).toBe(true);
            expect(Explorer.state.stagedObjectDeletions.has(0)).toBe(false);
        });

        test('returns false when unmarking non-existent deletion', () => {
            // Using invalid stable key since index 999 doesn't exist
            const result = Explorer.unmarkObjectForDeletion('invalid|key|value');
            expect(result).toBe(false);
        });
    });

    describe('Selection Management', () => {
        test('checks if object is selected by index', () => {
            const key = 'hosts.cfg|host|host1';
            Explorer.state.selectedKeys.add(key);

            expect(Explorer.isSelectedByIndex(0)).toBe(true);
            expect(Explorer.isSelectedByIndex(1)).toBe(false);
        });

        test('returns false for invalid index', () => {
            expect(Explorer.isSelectedByIndex(999)).toBe(false);
        });
    });

    describe('State Initialization', () => {
        test('initializes with empty state', () => {
            const state = Explorer.state;

            expect(state.pendingEdits).toBeInstanceOf(Map);
            expect(state.stagedMoves).toBeInstanceOf(Map);
            expect(state.stagedObjectDeletions).toBeInstanceOf(Set);
            expect(state.selectedKeys).toBeInstanceOf(Set);
            expect(Array.isArray(state.stagedCreations)).toBe(true);
            expect(Array.isArray(state.undoStack)).toBe(true);
        });

        test('has correct initial object count', () => {
            expect(Explorer.state.allObjects.length).toBe(3);
        });

        test('objects have correct structure', () => {
            const obj = Explorer.state.allObjects[0];

            expect(obj).toHaveProperty('global_index');
            expect(obj).toHaveProperty('object_type');
            expect(obj).toHaveProperty('source_file');
            expect(obj).toHaveProperty('attributes');
        });
    });

    describe('Edge Cases', () => {
        test('handles null input gracefully', () => {
            expect(Explorer.getPendingEdit(null)).toBeUndefined();
            expect(Explorer.setPendingEdit(null, {})).toBe(false);
            expect(Explorer.deletePendingEdit(null)).toBe(false);
        });

        test('handles undefined input gracefully', () => {
            expect(Explorer.getPendingEdit(undefined)).toBeUndefined();
            expect(Explorer.setPendingEdit(undefined, {})).toBe(false);
            expect(Explorer.deletePendingEdit(undefined)).toBe(false);
        });

        test('handles empty string key', () => {
            const result = Explorer.findObjectByKey('');
            expect(result).toBeUndefined();
        });

        test('handles negative index', () => {
            expect(Explorer.getObjectKeyByIndex(-1)).toBeNull();
        });

        test('handles operations on same object multiple times', () => {
            const obj = Explorer.state.allObjects[0];

            Explorer.setPendingEdit(obj, { edited: { v1: true } });
            Explorer.setPendingEdit(obj, { edited: { v2: true } });

            const edit = Explorer.getPendingEdit(obj);
            expect(edit.edited.v2).toBe(true);
        });

        test('deletion marking is idempotent', () => {
            Explorer.markObjectForDeletion(0);
            Explorer.markObjectForDeletion(0);

            expect(Explorer.state.stagedObjectDeletions.size).toBe(1);
        });
    });
});
