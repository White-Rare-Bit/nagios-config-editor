/**
 * Nagios Bulk Editor - Unified Drag and Drop Module
 *
 * Consolidates all drag-drop functionality into a single handler system.
 * Uses stable keys for reliable object identification.
 */

(function(Explorer) {
    'use strict';

    // Drag state tracking
    let draggedData = null;
    let dragCounter = 0;

    // =============================================================================
    // Drag State Management
    // =============================================================================

    /**
     * Clean up all drag state
     */
    Explorer.cleanupDragState = function() {
        draggedData = null;
        dragCounter = 0;

        // Remove all drag-related classes
        document.querySelectorAll('.drop-active, .drag-over, .dragging, .drop-target').forEach(el => {
            el.classList.remove('drop-active', 'drag-over', 'dragging', 'drop-target');
        });

        // Remove dimming effect
        document.body.classList.remove('dragging-objects');

        // Remove insertion markers
        document.querySelectorAll('.drop-indicator').forEach(el => el.remove());

        // Clean up drag badge
        const badge = document.getElementById('drag-badge-temp');
        if (badge) badge.remove();
    };

    /**
     * Get current drag data
     */
    Explorer.getDragData = function() {
        return draggedData;
    };

    /**
     * Set drag data
     */
    Explorer.setDragData = function(data) {
        draggedData = data;
    };

    // =============================================================================
    // Unified Drop Handler
    // =============================================================================

    /**
     * Main unified drop handler - dispatches to appropriate handler based on data type
     */
    Explorer.handleUnifiedDrop = function(event, targetFile, targetFolder) {
        event.preventDefault();
        Explorer.cleanupDragState();

        const dataStr = event.dataTransfer.getData('text/plain');
        if (!dataStr) return;

        let data;
        try {
            data = JSON.parse(dataStr);
        } catch (e) {
            console.error('Invalid drag data:', e);
            return;
        }

        // Dispatch based on data type
        switch (data.type) {
            case 'staged-creations':
                Explorer.handleStagedCreationsDrop(data, targetFile, targetFolder);
                break;

            case 'objects':
                Explorer.handleObjectsDrop(data, targetFile, targetFolder);
                break;

            case 'file':
                Explorer.handleFileDrop(data, targetFolder);
                break;

            case 'folder':
                Explorer.handleFolderDrop(data, targetFolder);
                break;

            default:
                console.warn('Unknown drag type:', data.type);
        }
    };

    // =============================================================================
    // Drop Type Handlers
    // =============================================================================

    /**
     * Handle dropping staged creations
     */
    Explorer.handleStagedCreationsDrop = function(data, targetFile, targetFolder) {
        const state = Explorer.state;
        let moved = 0;

        if (targetFile) {
            data.indices.forEach(idx => {
                const creation = state.stagedCreations[idx];
                if (creation && creation.targetFile !== targetFile) {
                    creation.targetFile = targetFile;
                    moved++;
                }
            });

            if (moved > 0) {
                Explorer.saveStagedChanges();
                Explorer.buildTree();
                Explorer.showToast(`Moved ${moved} new object(s) to ${targetFile.split('/').pop()}`, 'info');
            }
        } else if (targetFolder) {
            // Moving to folder - pick a default file or create one
            const defaultFile = targetFolder + '/objects.cfg';
            data.indices.forEach(idx => {
                const creation = state.stagedCreations[idx];
                if (creation) {
                    creation.targetFile = defaultFile;
                    moved++;
                }
            });

            if (moved > 0) {
                state.newFiles.add(defaultFile);
                Explorer.saveStagedChanges();
                Explorer.buildTree();
                Explorer.showToast(`Moved ${moved} new object(s) to ${targetFolder.split('/').pop()}`, 'info');
            }
        }
    };

    /**
     * Handle dropping objects (existing objects from tree)
     */
    Explorer.handleObjectsDrop = function(data, targetFile, targetFolder) {
        if (!data.objects || data.objects.length === 0) return;

        const state = Explorer.state;
        let staged = 0;

        // Determine actual target file
        let actualTargetFile = targetFile;
        if (!actualTargetFile && targetFolder) {
            // Dropping into folder - create new file or use existing
            actualTargetFile = targetFolder + '/moved-objects.cfg';
            state.newFiles.add(actualTargetFile);
        }

        if (!actualTargetFile) return;

        // Calculate insert position: find max line number in target file and append after
        let maxLine = 0;
        const targetObjects = state.allObjects.filter(o => o.source_file === actualTargetFile);
        targetObjects.forEach(o => {
            if (o.line_number > maxLine) maxLine = o.line_number;
        });
        // Also check pending moves and creations for this file
        state.stagedMoves.forEach(move => {
            if (move.targetFile === actualTargetFile && move.insertPosition) {
                maxLine = Math.max(maxLine, move.insertPosition);
            }
        });
        state.stagedCreations.forEach(c => {
            if (c.targetFile === actualTargetFile && c.insertPosition !== undefined) {
                maxLine = Math.max(maxLine, c.insertPosition);
            }
        });
        // Start after the last item
        let insertPos = maxLine + 1;

        // Stage moves using stable keys
        data.objects.forEach(objData => {
            if (!objData || !objData.source_file) return;

            // Skip if already in target file
            if (objData.source_file === actualTargetFile) return;

            const objKey = Explorer.getObjectKey(objData);

            state.stagedMoves.set(objKey, {
                targetFile: actualTargetFile,
                originalFile: objData.source_file,
                object: {
                    source_file: objData.source_file,
                    object_type: objData.object_type,
                    name: objData.name,
                    display_name: objData.display_name || objData.name,
                    attributes: objData.attributes
                },
                insertPosition: insertPos
            });
            insertPos += 0.001; // Small increment to preserve order when dropping multiple
            staged++;
        });

        if (staged > 0) {
            state.expandedFiles.add(actualTargetFile);
            Explorer.saveStagedChanges();
            Explorer.showToast(`Staged ${staged} object(s) to move. Use Commit to apply.`, 'info');
            Explorer.updateCommitUI();
            Explorer.buildTree();
            Explorer.renderTargetPane();
        }
    };

    /**
     * Handle dropping a file into a folder
     */
    Explorer.handleFileDrop = function(data, targetFolder) {
        if (!targetFolder || !data.path) return;

        // Stage the file move
        Explorer.stageFileMove(data.path, targetFolder);
    };

    /**
     * Handle dropping a folder into another folder
     */
    Explorer.handleFolderDrop = function(data, targetFolder) {
        if (!targetFolder || !data.path) return;

        // Prevent moving folder into itself
        if (targetFolder.startsWith(data.path)) {
            Explorer.showToast('Cannot move folder into itself', 'error');
            return;
        }

        // Stage the folder move
        Explorer.stageFolderMove(data.path, targetFolder);
    };

    // =============================================================================
    // Staged Move Operations
    // =============================================================================

    /**
     * Stage a file move via API
     */
    Explorer.stageFileMove = async function(sourcePath, targetFolder) {
        try {
            const response = await fetch('/api/files/move', {
                method: 'POST',
                headers: Explorer.getStagingHeaders(),
                body: JSON.stringify({
                    source: sourcePath,
                    targetFolder: targetFolder
                })
            });

            if (response.ok) {
                await Explorer.loadStagedChanges(false);
                Explorer.buildTree();
                Explorer.renderTargetPane();
                Explorer.updateCommitUI();
                Explorer.showToast('Staged file move. Use Commit to apply.', 'info');
            } else {
                const error = await response.json();
                Explorer.showToast(error.error || 'Failed to stage file move', 'error');
            }
        } catch (e) {
            console.error('File move staging error:', e);
            Explorer.showToast('Network error staging file move', 'error');
        }
    };

    /**
     * Stage a folder move via API
     */
    Explorer.stageFolderMove = async function(sourcePath, targetFolder) {
        try {
            const response = await fetch('/api/folders/move', {
                method: 'POST',
                headers: Explorer.getStagingHeaders(),
                body: JSON.stringify({
                    source: sourcePath,
                    targetFolder: targetFolder
                })
            });

            if (response.ok) {
                await Explorer.loadStagedChanges(false);
                Explorer.buildTree();
                Explorer.renderTargetPane();
                Explorer.updateCommitUI();
                Explorer.showToast('Staged folder move. Use Commit to apply.', 'info');
            } else {
                const error = await response.json();
                Explorer.showToast(error.error || 'Failed to stage folder move', 'error');
            }
        } catch (e) {
            console.error('Folder move staging error:', e);
            Explorer.showToast('Network error staging folder move', 'error');
        }
    };

    // Legacy aliases for backward compatibility
    Explorer.moveFileImmediate = Explorer.stageFileMove;
    Explorer.moveFolderImmediate = Explorer.stageFolderMove;

    // =============================================================================
    // Drag Start Helpers
    // =============================================================================

    /**
     * Prepare drag data for objects
     */
    Explorer.prepareDragDataForObjects = function(objects) {
        return {
            type: 'objects',
            objects: objects.map(obj => ({
                source_file: obj.source_file,
                object_type: obj.object_type,
                name: obj.name,
                display_name: obj.display_name || obj.name,
                attributes: obj.attributes,
                global_index: obj.global_index
            }))
        };
    };

    /**
     * Prepare drag data for staged creations
     */
    Explorer.prepareDragDataForStagedCreations = function(indices) {
        return {
            type: 'staged-creations',
            indices: Array.from(indices)
        };
    };

    /**
     * Prepare drag data for a file
     */
    Explorer.prepareDragDataForFile = function(filePath) {
        return {
            type: 'file',
            path: filePath
        };
    };

    /**
     * Prepare drag data for a folder
     */
    Explorer.prepareDragDataForFolder = function(folderPath) {
        return {
            type: 'folder',
            path: folderPath
        };
    };

    // =============================================================================
    // Drag Visual Feedback
    // =============================================================================

    /**
     * Show drop indicator at position
     */
    Explorer.showDropIndicator = function(element, position) {
        // Remove existing indicators
        document.querySelectorAll('.drop-indicator').forEach(el => el.remove());

        const indicator = document.createElement('div');
        indicator.className = 'drop-indicator';

        if (position === 'before') {
            element.parentNode.insertBefore(indicator, element);
        } else if (position === 'after') {
            element.parentNode.insertBefore(indicator, element.nextSibling);
        } else {
            element.appendChild(indicator);
        }
    };

    /**
     * Remove drop indicators
     */
    Explorer.removeDropIndicators = function() {
        document.querySelectorAll('.drop-indicator').forEach(el => el.remove());
    };

})(window.Explorer);
