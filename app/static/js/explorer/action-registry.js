/**
 * Nagios Bulk Editor - Explorer Action Registry
 *
 * Centralized mapping of data-action attribute values to handler functions.
 * Extracted from Explorer.initEventDelegation() in main.js.
 */

import { setView, switchRightTab, toggleSuggestionSection, toggleActionsMenu,
         navigateToObjectIssue, openInGraphView, closeObjectDetail, filterTree,
         selectObjectByStableKey } from './app.js';
import { toggleSection, showAddAttribute, deleteCurrentObject } from './object-editor.js';
import { selectAllVisible, selectByType, selectByPattern, discardNewObject,
         showBulkRenameDialog, showEditAttributesDialog, runValidationFull } from './dialogs.js';
import { createInlineFile, createInlineFolder } from './file-operations.js';
import { analyzeAll, filterSuggestions } from './analysis.js';
import { closePreview, closeDialog, contextAction, showBulkAction,
         showAddToGroupDialog, viewInGraph } from './context-menu.js';
import { filterTemplateSuggestions, filterGroupingSuggestions } from './analysis-suggestions.js';
// Map data-action attribute values to handler functions
export const actionHandlers = {
    // View and navigation
    setView: (el) => setView(el.dataset.view),
    switchRightTab: (el) => switchRightTab(el.dataset.tab),
    toggleSection: (el) => toggleSection(el.dataset.section),
    toggleSuggestionSection: (el) => toggleSuggestionSection(el.dataset.suggestionSection),

    // Actions menu
    toggleActionsMenu: (el, e) => toggleActionsMenu(e),
    selectAllVisible: () => selectAllVisible(),
    selectByType: () => selectByType(),
    selectByPattern: () => selectByPattern(),

    // Object actions
    navigateToObjectIssue: () => navigateToObjectIssue(),
    openInGraphView: () => openInGraphView(),
    discardNewObject: () => discardNewObject(),
    showAddAttribute: () => showAddAttribute(),
    deleteObject: () => deleteCurrentObject(),

    // File/folder operations
    createInlineFile: () => createInlineFile(),
    createInlineFolder: () => createInlineFolder(),

    // Analysis
    analyzeAll: () => analyzeAll(),
    runValidationFull: () => runValidationFull(),

    // Dialogs and modals
    closeObjectDetail: () => closeObjectDetail(),
    closePreview: () => closePreview(),
    closeDialog: () => closeDialog(),

    // Context menu actions
    contextAction: (el) => contextAction(el.dataset.contextAction),
    showBulkRenameDialog: () => showBulkRenameDialog(),
    showEditAttributesDialog: () => showEditAttributesDialog(),
    showBulkAction: (el) => showBulkAction(el.dataset.bulkAction),
    showAddToGroupDialog: () => showAddToGroupDialog(),
    viewInGraph: () => viewInGraph(),

    // Filter actions (for input/change events)
    filterTree: () => filterTree(),
    filterTemplateSuggestions: () => filterTemplateSuggestions(),
    filterGroupingSuggestions: () => filterGroupingSuggestions(),

    // Object selection (for suggestion items)
    selectObjectByKey: (el) => selectObjectByStableKey(el.dataset.stableKey),

    // Unified suggestions list actions
    filterSuggestions: (el, e) => filterSuggestions(e),
};
