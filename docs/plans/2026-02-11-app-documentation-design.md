# App Documentation for Docs Page

**Date**: 2026-02-11
**Status**: Approved

## Goal

Add comprehensive application documentation to the docs page alongside existing Nagios reference docs. Two audiences: sysadmins/Nagios users (how to use the app) and developers (how it's built). Text-only, client-side rendered.

## Tree Structure

Two top-level parent folders in the docs sidebar:

**App Docs** (expanded by default)
- Getting Started
  - Overview
  - Installation & Setup
  - Quick Start Guide
- User Guide
  - Explorer & Navigation
  - Editing Objects
  - Bulk Operations
  - Staging System
  - File & Folder Management
  - Git Integration
  - Search & Filtering
  - Keyboard Shortcuts
- Developer Guide
  - Architecture Overview
  - Backend Services
  - API Reference
  - Frontend Architecture
  - Data Flow & Staging Internals
  - Configuration System
  - Contributing

**Nagios Docs** (collapsed by default)
- *(existing categories and content, unchanged)*

## Data Structure

New file `static/js/app-docs-data.js` with structured JS data:

```javascript
window.APP_DOCS = {
  "getting-started": {
    label: "Getting Started",
    children: {
      "overview": {
        label: "Overview",
        content: [
          { type: "paragraph", text: "..." },
          { type: "heading", text: "...", level: 3 },
          { type: "list", items: ["...", "..."] },
          { type: "code", language: "bash", text: "..." },
        ]
      }
    }
  }
};
```

Content block types: `paragraph`, `heading` (h2-h4), `list` (bulleted), `ordered-list`, `code` (with language hint), `table` (header + rows), `note` (callout box), `divider`.

## URL Hash Scheme

| URL | What it shows |
|-----|--------------|
| `/docs#nagios/host/host_name` | Nagios host reference, scrolled to host_name directive |
| `/docs#app/user-guide/staging-system` | App docs: Staging System page |
| `/docs` (no hash) | Default landing — App Docs Overview |

Legacy fallback: bare `objectType/directive` hashes (e.g. `#host/host_name`) still work by trying Nagios reference lookup.

## Rendering

`docs.js` gains two render modes:
- **Nagios reference mode**: existing directive table rendering (unchanged)
- **App docs mode**: prose content block rendering (paragraphs, headings, lists, code blocks with copy button, tables, callout notes, dividers)

Directive filter search bar hidden for app docs pages. Tree search filters across both parent folders.

## Content Outline

### Getting Started
- **Overview**: What the app is, key capabilities (bulk editing, staging, git integration), architecture at a glance
- **Installation & Setup**: Requirements, pip install, `config/settings.json` options, running the server
- **Quick Start Guide**: End-to-end workflow walkthrough: load → browse → edit → stage → review → apply

### User Guide
- **Explorer & Navigation**: Tree sidebar, object list, type filtering, selecting, multi-select, context menus, tabs
- **Editing Objects**: Attribute editor, adding/removing directives, tooltip popovers, inline validation, required fields
- **Bulk Operations**: Multi-select editing, find & replace, bulk attribute changes
- **Staging System**: No disk writes until apply, pending edits vs staged operations, staging indicator, reviewing changes, undo, applying, lock system
- **File & Folder Management**: Creating/moving/deleting config files and folders, object-to-file mapping
- **Git Integration**: Viewing diffs, committing changes, branch management, commit dialog
- **Search & Filtering**: Tree search, object list filtering, explorer search
- **Keyboard Shortcuts**: All available shortcuts

### Developer Guide
- **Architecture Overview**: App factory pattern, service layer, `app.extensions`, request lifecycle
- **Backend Services**: Each service module's role and key methods
- **API Reference**: All endpoints grouped by function, request/response formats, error codes
- **Frontend Architecture**: Module structure, event delegation, `ApiClient`, Explorer component hierarchy
- **Data Flow & Staging Internals**: Edit flow UI → API → staging → apply → disk, stable keys, lock mechanics, undo stack
- **Configuration System**: `settings.json` fields, env var overrides, precedence
- **Contributing**: Code conventions, testing, adding new object types, domain metadata system

## Files Modified

- `static/js/docs.js` — Two-mode rendering, namespaced hash routing, prose content block renderer
- `static/js/explorer/object-editor.js` — Update "View in docs" href to `#nagios/objectType/directive`
- `templates/docs.html` — Load `app-docs-data.js`, two parent folders in tree
- `static/css/docs.css` — Prose content block styles

## Files Created

- `static/js/app-docs-data.js` — All application documentation content

## Files Unchanged

- `static/js/docs-data.js` — Nagios reference data stays as-is
- `routes/pages.py` — Route unchanged, no backend changes
- All backend files — Entirely frontend change

## Constraints

- Existing Nagios deep-links must still work via legacy fallback
- Tree search filters across both parent folders
- No new backend dependencies
- Text-only, no images
