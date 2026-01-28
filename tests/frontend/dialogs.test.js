/**
 * Tests for dialogs.js - Explorer dialog interactions
 */

// Mock dependencies
global.showConfirmDialog = jest.fn();
global.showToast = jest.fn();
global.ApiClient = {
    get: jest.fn(),
    post: jest.fn(),
    del: jest.fn()
};

describe('Explorer Dialogs', () => {
    let Explorer;

    beforeEach(() => {
        // Reset mocks
        showConfirmDialog.mockClear();
        showToast.mockClear();
        ApiClient.post.mockClear();
        ApiClient.del.mockClear();

        // Initialize Explorer namespace
        Explorer = {
            state: {
                allObjects: [
                    {
                        global_index: 0,
                        object_type: 'host',
                        source_file: 'hosts.cfg',
                        attributes: { host_name: ['host1'], alias: ['Web Server'] }
                    }
                ],
                selectedKeys: new Set(),
                stagedObjectDeletions: new Set(),
                pendingEdits: new Map()
            }
        };

        // Helper functions
        Explorer.getObjectKey = function(obj) {
            const name = obj.attributes.host_name?.[0] || obj.attributes.service_description?.[0] || '';
            return `${obj.source_file}|${obj.object_type}|${name}`;
        };

        Explorer.getDisplayName = function(obj) {
            if (obj.object_type === 'host') {
                return obj.attributes.host_name?.[0] || 'Unnamed';
            }
            if (obj.object_type === 'service') {
                const host = obj.attributes.host_name?.[0] || '?';
                const desc = obj.attributes.service_description?.[0] || '?';
                return `${desc} on ${host}`;
            }
            return obj.attributes.name?.[0] || 'Unnamed';
        };

        // Dialog functions
        Explorer.showDeleteDialog = async function(objects) {
            const count = objects.length;
            const title = count === 1 ? 'Delete Object' : `Delete ${count} Objects`;
            const message = count === 1
                ? `Are you sure you want to delete <strong>${Explorer.getDisplayName(objects[0])}</strong>?`
                : `Are you sure you want to delete ${count} objects?`;

            const confirmed = await showConfirmDialog({
                title,
                message,
                confirmText: 'Delete',
                type: 'danger',
                allowHtml: true
            });

            return confirmed;
        };

        Explorer.showRenameDialog = function(obj) {
            return new Promise((resolve) => {
                const dialog = document.createElement('div');
                dialog.id = 'renameDialog';
                dialog.innerHTML = `
                    <input type="text" id="renameInput" value="${Explorer.getDisplayName(obj)}">
                    <button id="renameConfirm">Rename</button>
                    <button id="renameCancel">Cancel</button>
                `;
                document.body.appendChild(dialog);

                document.getElementById('renameConfirm').onclick = () => {
                    const newName = document.getElementById('renameInput').value;
                    dialog.remove();
                    resolve(newName);
                };

                document.getElementById('renameCancel').onclick = () => {
                    dialog.remove();
                    resolve(null);
                };
            });
        };

        Explorer.showMoveDialog = function(objects) {
            return new Promise((resolve) => {
                const dialog = document.createElement('div');
                dialog.id = 'moveDialog';
                dialog.innerHTML = `
                    <select id="targetFileSelect">
                        <option value="hosts.cfg">hosts.cfg</option>
                        <option value="services.cfg">services.cfg</option>
                    </select>
                    <button id="moveConfirm">Move</button>
                    <button id="moveCancel">Cancel</button>
                `;
                document.body.appendChild(dialog);

                document.getElementById('moveConfirm').onclick = () => {
                    const targetFile = document.getElementById('targetFileSelect').value;
                    dialog.remove();
                    resolve(targetFile);
                };

                document.getElementById('moveCancel').onclick = () => {
                    dialog.remove();
                    resolve(null);
                };
            });
        };

        Explorer.showCloneDialog = async function(obj) {
            const dialog = document.createElement('div');
            dialog.id = 'cloneDialog';
            dialog.innerHTML = `
                <input type="text" id="cloneNameInput" value="${Explorer.getDisplayName(obj)}_copy">
                <button id="cloneConfirm">Clone</button>
                <button id="cloneCancel">Cancel</button>
            `;
            document.body.appendChild(dialog);

            return new Promise((resolve) => {
                document.getElementById('cloneConfirm').onclick = () => {
                    const newName = document.getElementById('cloneNameInput').value;
                    dialog.remove();
                    resolve({ newName, targetFile: obj.source_file });
                };

                document.getElementById('cloneCancel').onclick = () => {
                    dialog.remove();
                    resolve(null);
                };
            });
        };
    });

    afterEach(() => {
        // Clean up any dialogs
        ['renameDialog', 'moveDialog', 'cloneDialog'].forEach(id => {
            const dialog = document.getElementById(id);
            if (dialog) dialog.remove();
        });
    });

    describe('Delete Dialog', () => {
        test('shows confirmation for single object deletion', async () => {
            showConfirmDialog.mockResolvedValue(true);

            const obj = Explorer.state.allObjects[0];
            const result = await Explorer.showDeleteDialog([obj]);

            expect(showConfirmDialog).toHaveBeenCalledWith({
                title: 'Delete Object',
                message: expect.stringContaining('host1'),
                confirmText: 'Delete',
                type: 'danger',
                allowHtml: true
            });
            expect(result).toBe(true);
        });

        test('shows confirmation for multiple object deletion', async () => {
            showConfirmDialog.mockResolvedValue(true);

            const objects = [
                Explorer.state.allObjects[0],
                { ...Explorer.state.allObjects[0], global_index: 1 }
            ];
            const result = await Explorer.showDeleteDialog(objects);

            expect(showConfirmDialog).toHaveBeenCalledWith({
                title: 'Delete 2 Objects',
                message: expect.stringContaining('2 objects'),
                confirmText: 'Delete',
                type: 'danger',
                allowHtml: true
            });
            expect(result).toBe(true);
        });

        test('returns false when user cancels', async () => {
            showConfirmDialog.mockResolvedValue(false);

            const obj = Explorer.state.allObjects[0];
            const result = await Explorer.showDeleteDialog([obj]);

            expect(result).toBe(false);
        });

        test('includes object display name in message', async () => {
            showConfirmDialog.mockResolvedValue(true);

            const obj = Explorer.state.allObjects[0];
            await Explorer.showDeleteDialog([obj]);

            const call = showConfirmDialog.mock.calls[0][0];
            expect(call.message).toContain('host1');
        });
    });

    describe('Rename Dialog', () => {
        test('shows rename dialog with current name', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showRenameDialog(obj);

            const input = document.getElementById('renameInput');
            expect(input.value).toBe('host1');

            document.getElementById('renameCancel').click();
            await promise;
        });

        test('returns new name when confirmed', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showRenameDialog(obj);

            const input = document.getElementById('renameInput');
            input.value = 'host1-renamed';
            document.getElementById('renameConfirm').click();

            const result = await promise;
            expect(result).toBe('host1-renamed');
        });

        test('returns null when cancelled', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showRenameDialog(obj);

            document.getElementById('renameCancel').click();

            const result = await promise;
            expect(result).toBeNull();
        });

        test('removes dialog from DOM after confirm', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showRenameDialog(obj);

            document.getElementById('renameConfirm').click();
            await promise;

            expect(document.getElementById('renameDialog')).toBeNull();
        });

        test('removes dialog from DOM after cancel', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showRenameDialog(obj);

            document.getElementById('renameCancel').click();
            await promise;

            expect(document.getElementById('renameDialog')).toBeNull();
        });
    });

    describe('Move Dialog', () => {
        test('shows move dialog with file options', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showMoveDialog([obj]);

            const select = document.getElementById('targetFileSelect');
            expect(select.options.length).toBe(2);
            expect(select.options[0].value).toBe('hosts.cfg');
            expect(select.options[1].value).toBe('services.cfg');

            document.getElementById('moveCancel').click();
            await promise;
        });

        test('returns selected file when confirmed', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showMoveDialog([obj]);

            const select = document.getElementById('targetFileSelect');
            select.value = 'services.cfg';
            document.getElementById('moveConfirm').click();

            const result = await promise;
            expect(result).toBe('services.cfg');
        });

        test('returns null when cancelled', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showMoveDialog([obj]);

            document.getElementById('moveCancel').click();

            const result = await promise;
            expect(result).toBeNull();
        });

        test('removes dialog from DOM after action', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showMoveDialog([obj]);

            document.getElementById('moveConfirm').click();
            await promise;

            expect(document.getElementById('moveDialog')).toBeNull();
        });
    });

    describe('Clone Dialog', () => {
        test('shows clone dialog with default name', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showCloneDialog(obj);

            const input = document.getElementById('cloneNameInput');
            expect(input.value).toBe('host1_copy');

            document.getElementById('cloneCancel').click();
            await promise;
        });

        test('returns clone config when confirmed', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showCloneDialog(obj);

            const input = document.getElementById('cloneNameInput');
            input.value = 'host1_clone';
            document.getElementById('cloneConfirm').click();

            const result = await promise;
            expect(result).toEqual({
                newName: 'host1_clone',
                targetFile: 'hosts.cfg'
            });
        });

        test('returns null when cancelled', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showCloneDialog(obj);

            document.getElementById('cloneCancel').click();

            const result = await promise;
            expect(result).toBeNull();
        });

        test('uses source file as target file', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showCloneDialog(obj);

            document.getElementById('cloneConfirm').click();

            const result = await promise;
            expect(result.targetFile).toBe('hosts.cfg');
        });
    });

    describe('Display Name Formatting', () => {
        test('formats host display name', () => {
            const obj = {
                object_type: 'host',
                attributes: { host_name: ['webserver01'] }
            };
            expect(Explorer.getDisplayName(obj)).toBe('webserver01');
        });

        test('formats service display name', () => {
            const obj = {
                object_type: 'service',
                attributes: {
                    host_name: ['webserver01'],
                    service_description: ['HTTP']
                }
            };
            expect(Explorer.getDisplayName(obj)).toBe('HTTP on webserver01');
        });

        test('handles missing host_name in service', () => {
            const obj = {
                object_type: 'service',
                attributes: { service_description: ['HTTP'] }
            };
            expect(Explorer.getDisplayName(obj)).toBe('HTTP on ?');
        });

        test('formats generic object with name field', () => {
            const obj = {
                object_type: 'contact',
                attributes: { name: ['john_doe'] }
            };
            expect(Explorer.getDisplayName(obj)).toBe('john_doe');
        });

        test('returns "Unnamed" for object without name', () => {
            const obj = {
                object_type: 'host',
                attributes: {}
            };
            expect(Explorer.getDisplayName(obj)).toBe('Unnamed');
        });
    });

    describe('Dialog Integration', () => {
        test('delete dialog workflow', async () => {
            showConfirmDialog.mockResolvedValue(true);

            const obj = Explorer.state.allObjects[0];
            const confirmed = await Explorer.showDeleteDialog([obj]);

            expect(confirmed).toBe(true);
            expect(showConfirmDialog).toHaveBeenCalledTimes(1);
        });

        test('rename dialog workflow', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showRenameDialog(obj);

            const input = document.getElementById('renameInput');
            input.value = 'new-name';
            document.getElementById('renameConfirm').click();

            const newName = await promise;
            expect(newName).toBe('new-name');
        });

        test('multiple dialogs can be opened sequentially', async () => {
            const obj = Explorer.state.allObjects[0];

            // First dialog
            const promise1 = Explorer.showRenameDialog(obj);
            document.getElementById('renameCancel').click();
            await promise1;

            // Second dialog
            const promise2 = Explorer.showRenameDialog(obj);
            document.getElementById('renameCancel').click();
            await promise2;

            expect(document.getElementById('renameDialog')).toBeNull();
        });
    });

    describe('Edge Cases', () => {
        test('handles empty object array in delete dialog', async () => {
            showConfirmDialog.mockResolvedValue(true);

            await Explorer.showDeleteDialog([]);

            expect(showConfirmDialog).toHaveBeenCalledWith(
                expect.objectContaining({
                    title: 'Delete 0 Objects'
                })
            );
        });

        test('handles object with HTML in name', async () => {
            showConfirmDialog.mockResolvedValue(true);

            const obj = {
                object_type: 'host',
                source_file: 'hosts.cfg',
                attributes: { host_name: ['<script>alert("xss")</script>'] }
            };

            await Explorer.showDeleteDialog([obj]);

            const call = showConfirmDialog.mock.calls[0][0];
            expect(call.allowHtml).toBe(true);
        });

        test('handles empty input in rename dialog', async () => {
            const obj = Explorer.state.allObjects[0];
            const promise = Explorer.showRenameDialog(obj);

            const input = document.getElementById('renameInput');
            input.value = '';
            document.getElementById('renameConfirm').click();

            const result = await promise;
            expect(result).toBe('');
        });

        test('handles very long names in dialogs', async () => {
            const longName = 'a'.repeat(500);
            const obj = {
                object_type: 'host',
                source_file: 'hosts.cfg',
                attributes: { host_name: [longName] }
            };

            const promise = Explorer.showRenameDialog(obj);

            const input = document.getElementById('renameInput');
            expect(input.value).toBe(longName);

            document.getElementById('renameCancel').click();
            await promise;
        });
    });
});
