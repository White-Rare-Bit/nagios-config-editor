/**
 * Nagios Bulk Editor - Explorer Orphan Detection Module
 *
 * Fetches orphan data from the backend API and caches it.
 * Applies a lightweight overlay for pending edits so orphan
 * status reflects staged changes, not just on-disk state.
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

        loadingPromise = _fetchAndBuild();
        return loadingPromise;
    }

    async function _fetchAndBuild() {
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
        } finally {
            loadingPromise = null;
        }

        // Apply pending-edit overlay
        _applyPendingEditOverlay();

        return orphanCache;
    }

    /**
     * Adjust orphan cache based on pending edits.
     * If a pending edit adds a reference to an object that's in the orphan set,
     * remove it. This is a best-effort adjustment — the full recomputation
     * happens on the backend after changes are applied.
     */
    function _applyPendingEditOverlay() {
        if (!orphanCache || !state.pendingEdits || state.pendingEdits.size === 0) return;

        // Collect names newly referenced by pending edits (that weren't in original)
        const newlyReferenced = new Set(); // "type:name" entries

        for (const [idx, edit] of state.pendingEdits) {
            const obj = state.allObjects.find(o => o.global_index === idx);
            if (!obj) continue;

            const original = edit.original || {};
            const edited = edit.edited || {};

            // Check reference fields for new values
            _collectNewReferences(obj.object_type, original, edited, newlyReferenced);
        }

        // Remove from orphan cache any object whose name is newly referenced
        if (newlyReferenced.size > 0) {
            for (const obj of state.allObjects) {
                if (!orphanCache.has(obj.global_index)) continue;
                const name = obj.display_name || obj.name;
                if (name && newlyReferenced.has(`${obj.object_type}:${name}`)) {
                    orphanCache.delete(obj.global_index);
                }
            }
        }
    }

    /**
     * Compare original vs edited attributes and collect newly referenced names.
     */
    function _collectNewReferences(objType, original, edited, result) {
        // Reference field -> target type (simplified subset of common fields)
        const refFields = {
            'host_name': 'host', 'parents': 'host',
            'hostgroup_name': 'hostgroup', 'hostgroups': 'hostgroup',
            'contacts': 'contact', 'contact_groups': 'contactgroup',
            'check_command': 'command', 'event_handler': 'command',
            'host_notification_commands': 'command',
            'service_notification_commands': 'command',
            'check_period': 'timeperiod', 'notification_period': 'timeperiod',
            'servicegroups': 'servicegroup',
            'use': objType, // templates reference same type
        };

        for (const [field, targetType] of Object.entries(refFields)) {
            const oldVal = original[field] || '';
            const newVal = edited[field] || '';
            if (oldVal === newVal) continue;

            // Find names in new value that weren't in old value
            const oldNames = new Set(oldVal.split(',').map(s => s.trim().replace(/^[+!]+/, '').split('!')[0].trim()).filter(Boolean));
            const newNames = newVal.split(',').map(s => s.trim().replace(/^[+!]+/, '').split('!')[0].trim()).filter(Boolean);

            for (const name of newNames) {
                if (!oldNames.has(name)) {
                    result.add(`${targetType}:${name}`);
                }
            }
        }
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
