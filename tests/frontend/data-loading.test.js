/**
 * Tests for data-loading.js - API calls and staging synchronization
 */

// Mock ApiClient
global.ApiClient = {
    get: jest.fn(),
    post: jest.fn(),
    del: jest.fn()
};

describe('Explorer Data Loading', () => {
    let Explorer;

    beforeEach(() => {
        // Reset mocks
        ApiClient.get.mockClear();
        ApiClient.post.mockClear();
        ApiClient.del.mockClear();

        // Initialize Explorer namespace
        Explorer = {
            state: {
                allObjects: [],
                allFiles: [],
                existingFolders: [],
                configPath: '/etc/nagios/objects',
                sessionId: 'test-session-123'
            }
        };

        // Data loading function
        Explorer.loadObjects = async function() {
            const [objectsResult, filesResult, foldersResult] = await Promise.all([
                ApiClient.get('/api/objects?_=' + Date.now(), { silent: true }),
                ApiClient.get('/api/files?_=' + Date.now(), { silent: true }),
                ApiClient.get('/api/folders?_=' + Date.now(), { silent: true })
            ]);

            Explorer.state.allObjects = objectsResult.data || [];
            Explorer.state.allFiles = filesResult.data?.files || [];
            Explorer.state.existingFolders = foldersResult.data?.folders || [];
        };

        // Path utilities
        Explorer.getConfigRootName = function() {
            const path = Explorer.state.configPath;
            const parts = path.split('/').filter(Boolean);
            return parts[parts.length - 1] || 'config';
        };

        Explorer.toDisplayPath = function(path) {
            if (!path) return '';
            const configPath = Explorer.state.configPath;
            const configRootName = Explorer.getConfigRootName();

            if (path.startsWith(configPath + '/')) {
                return configRootName + '/' + path.substring(configPath.length + 1);
            } else if (path === configPath) {
                return configRootName;
            }
            if (!path.startsWith('/')) {
                return configRootName + '/' + path;
            }
            return path;
        };

        Explorer.toAbsolutePath = function(displayPath) {
            if (!displayPath) return '';
            const configPath = Explorer.state.configPath;
            const configRootName = Explorer.getConfigRootName();

            if (displayPath.startsWith(configRootName + '/')) {
                return configPath + '/' + displayPath.substring(configRootName.length + 1);
            } else if (displayPath === configRootName) {
                return configPath;
            }
            if (displayPath.startsWith('/')) {
                return displayPath;
            }
            return configPath + '/' + displayPath;
        };

        Explorer.getStagingHeaders = function() {
            return {
                'Content-Type': 'application/json',
                'X-Session-Id': Explorer.state.sessionId
            };
        };
    });

    describe('loadObjects', () => {
        test('loads objects, files, and folders concurrently', async () => {
            const mockObjects = [
                { global_index: 0, object_type: 'host', attributes: { host_name: ['host1'] } },
                { global_index: 1, object_type: 'service', attributes: { service_description: ['svc1'] } }
            ];
            const mockFiles = ['hosts.cfg', 'services.cfg'];
            const mockFolders = ['hosts', 'services', 'contacts'];

            ApiClient.get
                .mockResolvedValueOnce({ success: true, data: mockObjects })
                .mockResolvedValueOnce({ success: true, data: { files: mockFiles } })
                .mockResolvedValueOnce({ success: true, data: { folders: mockFolders } });

            await Explorer.loadObjects();

            expect(ApiClient.get).toHaveBeenCalledTimes(3);
            expect(Explorer.state.allObjects).toEqual(mockObjects);
            expect(Explorer.state.allFiles).toEqual(mockFiles);
            expect(Explorer.state.existingFolders).toEqual(mockFolders);
        });

        test('uses cache-busting query parameter', async () => {
            ApiClient.get.mockResolvedValue({ success: true, data: [] });

            await Explorer.loadObjects();

            const calls = ApiClient.get.mock.calls;
            expect(calls[0][0]).toMatch(/\/api\/objects\?_=\d+/);
            expect(calls[1][0]).toMatch(/\/api\/files\?_=\d+/);
            expect(calls[2][0]).toMatch(/\/api\/folders\?_=\d+/);
        });

        test('uses silent mode for API calls', async () => {
            ApiClient.get.mockResolvedValue({ success: true, data: [] });

            await Explorer.loadObjects();

            const calls = ApiClient.get.mock.calls;
            expect(calls[0][1]).toEqual({ silent: true });
            expect(calls[1][1]).toEqual({ silent: true });
            expect(calls[2][1]).toEqual({ silent: true });
        });

        test('handles empty responses', async () => {
            ApiClient.get
                .mockResolvedValueOnce({ success: true, data: null })
                .mockResolvedValueOnce({ success: true, data: null })
                .mockResolvedValueOnce({ success: true, data: null });

            await Explorer.loadObjects();

            expect(Explorer.state.allObjects).toEqual([]);
            expect(Explorer.state.allFiles).toEqual([]);
            expect(Explorer.state.existingFolders).toEqual([]);
        });

        test('handles API errors gracefully', async () => {
            ApiClient.get.mockRejectedValue(new Error('Network error'));

            await expect(Explorer.loadObjects()).rejects.toThrow('Network error');
        });
    });

    describe('Path Utilities', () => {
        describe('getConfigRootName', () => {
            test('extracts root name from config path', () => {
                Explorer.state.configPath = '/etc/nagios/objects';
                expect(Explorer.getConfigRootName()).toBe('objects');
            });

            test('handles path with trailing slash', () => {
                Explorer.state.configPath = '/etc/nagios/objects/';
                expect(Explorer.getConfigRootName()).toBe('objects');
            });

            test('handles single-level path', () => {
                Explorer.state.configPath = '/config';
                expect(Explorer.getConfigRootName()).toBe('config');
            });

            test('returns default for empty path', () => {
                Explorer.state.configPath = '';
                expect(Explorer.getConfigRootName()).toBe('config');
            });
        });

        describe('toDisplayPath', () => {
            test('converts absolute path to display path', () => {
                const result = Explorer.toDisplayPath('/etc/nagios/objects/hosts/webservers.cfg');
                expect(result).toBe('objects/hosts/webservers.cfg');
            });

            test('converts config root path', () => {
                const result = Explorer.toDisplayPath('/etc/nagios/objects');
                expect(result).toBe('objects');
            });

            test('handles relative path', () => {
                const result = Explorer.toDisplayPath('hosts/webservers.cfg');
                expect(result).toBe('objects/hosts/webservers.cfg');
            });

            test('handles path outside config directory', () => {
                const result = Explorer.toDisplayPath('/var/log/nagios.log');
                expect(result).toBe('/var/log/nagios.log');
            });

            test('handles empty path', () => {
                const result = Explorer.toDisplayPath('');
                expect(result).toBe('');
            });

            test('handles null path', () => {
                const result = Explorer.toDisplayPath(null);
                expect(result).toBe('');
            });
        });

        describe('toAbsolutePath', () => {
            test('converts display path to absolute path', () => {
                const result = Explorer.toAbsolutePath('objects/hosts/webservers.cfg');
                expect(result).toBe('/etc/nagios/objects/hosts/webservers.cfg');
            });

            test('converts config root display path', () => {
                const result = Explorer.toAbsolutePath('objects');
                expect(result).toBe('/etc/nagios/objects');
            });

            test('handles already absolute path', () => {
                const result = Explorer.toAbsolutePath('/var/log/nagios.log');
                expect(result).toBe('/var/log/nagios.log');
            });

            test('handles path without config root prefix', () => {
                const result = Explorer.toAbsolutePath('hosts/webservers.cfg');
                expect(result).toBe('/etc/nagios/objects/hosts/webservers.cfg');
            });

            test('handles empty path', () => {
                const result = Explorer.toAbsolutePath('');
                expect(result).toBe('');
            });

            test('handles null path', () => {
                const result = Explorer.toAbsolutePath(null);
                expect(result).toBe('');
            });

            test('roundtrip conversion preserves path', () => {
                const originalPath = '/etc/nagios/objects/hosts/webservers.cfg';
                const displayPath = Explorer.toDisplayPath(originalPath);
                const backToAbsolute = Explorer.toAbsolutePath(displayPath);
                expect(backToAbsolute).toBe(originalPath);
            });
        });
    });

    describe('Staging Headers', () => {
        test('returns headers with session ID', () => {
            const headers = Explorer.getStagingHeaders();

            expect(headers).toEqual({
                'Content-Type': 'application/json',
                'X-Session-Id': 'test-session-123'
            });
        });

        test('uses current session ID from state', () => {
            Explorer.state.sessionId = 'new-session-456';

            const headers = Explorer.getStagingHeaders();

            expect(headers['X-Session-Id']).toBe('new-session-456');
        });
    });

    describe('Integration Tests', () => {
        test('complete data load workflow', async () => {
            const mockData = {
                objects: [
                    { global_index: 0, object_type: 'host' },
                    { global_index: 1, object_type: 'service' }
                ],
                files: ['hosts.cfg', 'services.cfg'],
                folders: ['hosts', 'services']
            };

            ApiClient.get
                .mockResolvedValueOnce({ success: true, data: mockData.objects })
                .mockResolvedValueOnce({ success: true, data: { files: mockData.files } })
                .mockResolvedValueOnce({ success: true, data: { folders: mockData.folders } });

            await Explorer.loadObjects();

            expect(Explorer.state.allObjects.length).toBe(2);
            expect(Explorer.state.allFiles.length).toBe(2);
            expect(Explorer.state.existingFolders.length).toBe(2);
        });

        test('handles partial failure in concurrent loads', async () => {
            ApiClient.get
                .mockResolvedValueOnce({ success: true, data: [{ global_index: 0 }] })
                .mockRejectedValueOnce(new Error('Files API failed'))
                .mockResolvedValueOnce({ success: true, data: { folders: ['folder1'] } });

            await expect(Explorer.loadObjects()).rejects.toThrow('Files API failed');
        });
    });

    describe('Edge Cases', () => {
        test('handles config path with special characters', () => {
            Explorer.state.configPath = '/etc/nagios-config/obj ects';

            const displayPath = Explorer.toDisplayPath('/etc/nagios-config/obj ects/hosts.cfg');
            // Last path component is 'obj ects', so display path should be 'obj ects/hosts.cfg'
            expect(displayPath).toBe('obj ects/hosts.cfg');
        });

        test('handles very long paths', () => {
            const longPath = '/etc/nagios/objects/' + 'a/'.repeat(50) + 'file.cfg';
            const displayPath = Explorer.toDisplayPath(longPath);
            expect(displayPath).toContain('objects/');
        });

        test('handles paths with dots and special chars', () => {
            const path = '/etc/nagios/objects/hosts/../services/./web.cfg';
            const displayPath = Explorer.toDisplayPath(path);
            expect(displayPath).toContain('objects/');
        });

        test('handles concurrent load calls', async () => {
            ApiClient.get.mockResolvedValue({ success: true, data: [] });

            await Promise.all([
                Explorer.loadObjects(),
                Explorer.loadObjects(),
                Explorer.loadObjects()
            ]);

            // Should make 9 API calls (3 loads × 3 endpoints each)
            expect(ApiClient.get).toHaveBeenCalledTimes(9);
        });
    });
});
