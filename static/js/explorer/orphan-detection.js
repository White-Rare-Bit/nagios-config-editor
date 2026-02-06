/**
 * Nagios Bulk Editor - Explorer Orphan Detection Module
 *
 * Fetches orphan data from the backend API and caches it.
 * An orphan is an object not referenced by any other object.
 */

(function(Explorer) {
    'use strict';

    const state = Explorer.state;

    // Cache for orphan status (Set of global_index values)
    let orphanCache = null;
    let loadingPromise = null;

    function invalidateOrphanCache() {
        orphanCache = null;
        loadingPromise = null;
    }

    /**
     * Load orphan data from backend. Returns a promise that resolves
     * to the orphan cache Set. Uses cached data if available.
     */
    async function loadOrphanCache() {
        if (orphanCache) return orphanCache;
        if (loadingPromise) return loadingPromise;

        loadingPromise = (async () => {
            try {
                const result = await ApiClient.get('/api/analysis/orphans', { silent: true });
                if (result.success && result.data.orphan_indices) {
                    orphanCache = new Set(result.data.orphan_indices);
                } else {
                    orphanCache = new Set();
                }
            } catch (e) {
                console.error('Failed to load orphan data:', e);
                orphanCache = new Set();
            }
            loadingPromise = null;
            return orphanCache;
        })();

        return loadingPromise;
    }

    /**
     * Synchronous access to orphan cache. Returns the cached Set
     * or an empty Set if not yet loaded. Call loadOrphanCache() first.
     */
    function buildOrphanCache() {
        if (orphanCache) return orphanCache;
        // Trigger async load for next time
        loadOrphanCache();
        return new Set();
    }

    function isObjectOrphan(obj) {
        const cache = buildOrphanCache();
        return cache.has(obj.global_index);
    }

    // Export to Explorer namespace
    Explorer.invalidateOrphanCache = invalidateOrphanCache;
    Explorer.buildOrphanCache = buildOrphanCache;
    Explorer.loadOrphanCache = loadOrphanCache;
    Explorer.isObjectOrphan = isObjectOrphan;

})(window.Explorer);
