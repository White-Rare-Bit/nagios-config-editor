# SVG Diagrams for Documentation Pages

**Date**: 2026-02-12
**Status**: Approved

## Design Decisions

- **Visual style**: Dark theme, app-native — matches the app's `#1e1e1e` background using existing `--nbe-*` CSS variables
- **Embedding**: Inline SVG directly in HTML templates inside `.docs-prose` — enables CSS variable theming
- **Responsiveness**: `width="100%" viewBox="..."` to scale within the 900px prose container
- **CSS**: New `.docs-diagram` class for consistent spacing and border treatment

## Color Palette Reference

All tokens defined in `static/css/tokens.css`. Examples show how they're used across the existing CSS.

### Core Diagram Colors

These are the primary tokens for building SVG diagrams:

| Token | Value | Diagram use | CSS usage examples |
|-------|-------|-------------|-------------------|
| `--nbe-dark-bg-primary` | `#1e1e1e` | SVG background (or transparent) | `.explorer`, `.docs-container .page-main`, `.git-container` main bg |
| `--nbe-dark-bg-secondary` | `#2d2d2d` | Box/node fills | `.panel-header`, `.docs-type-header`, `.git-files-panel` surface bg |
| `--nbe-dark-bg-tertiary` | `#252525` | Alternate box fills | `.tree-item:nth-child(even)`, code blocks, alternating table rows |
| `--nbe-dark-bg-hover` | `#2a2a2a` | Hover state fills | `.tree-item:hover`, `.git-file-item:hover`, `.filter-chip:hover` |
| `--nbe-dark-bg-elevated` | `#333` | Active/focus fills | `.tree-item.selected` bg, focus states |
| `--nbe-dark-bg-subtle` | `#383838` | Collapsible headers | `.quick-view-btn`, `.git-file-section-header` |
| `--nbe-dark-text-primary` | `#d4d4d4` | Primary labels | `.tree-item-name`, `.docs-type-title`, all body text (11.4:1 contrast) |
| `--nbe-dark-text-secondary` | `#888` | Secondary labels | `.toolbar-label`, `.docs-prose p`, `.filter-chip` text (4.7:1 contrast) |
| `--nbe-dark-text-muted` | `#666` | Annotations, subtle text | `.tab-placeholder`, `.git-status-badge.untracked` (4.5:1 contrast) |
| `--nbe-dark-accent-primary` | `#4ec9b0` | Arrows, highlights, active | `.tree-item.selected` border, `.docs-cell-name code`, `.git-branch-icon` |
| `--nbe-dark-accent-secondary` | `#569cd6` | Secondary elements | `.staged-item-target`, `.history-author-name`, info filter active |
| `--nbe-dark-accent-warning` | `#ffc107` | Warning indicators | `.tree-item.staged` border, move operations |
| `--nbe-dark-accent-danger` | `#f14c4c` | Danger indicators | `.danger-zone-toggle`, `.page-tab-badge` |
| `--nbe-dark-border-primary` | `#404040` | Box borders | `.tree-search`, `.docs-directive-table`, `.git-file-item` borders |
| `--nbe-dark-border-secondary` | `#333` | Subtle dividers | `.commit-item` dividers, alternating row borders |
| `--nbe-dark-border-hover` | `#505050` | Hover borders | scrollbar thumb hover, pagination hover |

### Validation State Colors

Used for status indicators and state-coded elements. Good for diagram annotations showing staged/applied/error states:

| State | Background | Text | Border | CSS usage examples |
|-------|-----------|------|--------|-------------------|
| **Success** (green) | `rgba(40, 167, 69, 0.1)` | `#81c784` | `rgba(76, 175, 80, 0.3)` | `.tree-item.staged-creation`, `.git-status-badge.added` |
| **Error** (red) | `rgba(244, 67, 54, 0.1)` | `#e57373` | `rgba(241, 76, 76, 0.3)` | `.tree-item.staged-for-deletion`, `.git-status-badge.deleted` |
| **Warning** (yellow) | `rgba(255, 193, 7, 0.1)` | `#ffb74d` | `rgba(255, 193, 7, 0.3)` | `.tree-item.staged`, `.git-status-badge.modified` |
| **Info** (blue) | `rgba(56, 139, 253, 0.1)` | `#64b5f6` | `rgba(56, 139, 253, 0.3)` | `.git-status-badge.renamed`, `.git-status-badge.staged` |

### Semantic Colors (Not Dark-Converted)

These have sufficient contrast in both themes. Use sparingly in diagrams for strong semantic meaning:

| Token | Value | CSS usage examples |
|-------|-------|-------------------|
| `--nbe-success` | `#1a6b1e` | `.tree-item-staged-badge`, `.staged-count`, `.source-self` (inheritance) |
| `--nbe-warning` | `#b45309` | `.docs-deprecated-notice`, `.docs-prose .docs-warning` |
| `--nbe-danger` | `#991b1b` | `.tree-item.staged-for-deletion`, `.batch-btn-danger:hover` |
| `--nbe-info` | `#0059a8` | Informational badges and accents |

### Accent Alpha Variants (Teal)

Used for translucent fills over the dark background. Useful for diagram highlight regions:

| Token | Value | CSS usage examples |
|-------|-------|-------------------|
| `--nbe-dark-accent-alpha-10` | `rgba(78, 201, 176, 0.1)` | `.git-history-table tbody tr.is-current` bg |
| `--nbe-dark-accent-alpha-15` | `rgba(78, 201, 176, 0.15)` | `.git-file-item.selected`, `.quick-view-btn.active`, `.filter-chip.active` |
| `--nbe-dark-accent-alpha-20` | `rgba(78, 201, 176, 0.2)` | `.archive-item.active` |
| `--nbe-dark-accent-alpha-30` | `rgba(78, 201, 176, 0.3)` | `.git-staging-preview` border |
| `--nbe-dark-accent-alpha-60` | `rgba(78, 201, 176, 0.6)` | Higher emphasis overlays |

### Object Type Badge Colors

Color-coded by domain — useful for dependency graph and architecture diagrams where object types appear:

| Domain | Types | Background | Text |
|--------|-------|-----------|------|
| **Infrastructure** (green) | host, hostgroup | `rgba(76, 175, 80, 0.2)` / `rgba(139, 195, 74, 0.2)` | `#81c784` / `#aed581` |
| **Monitoring** (blue) | service, servicegroup | `rgba(33, 150, 243, 0.2)` / `rgba(3, 169, 244, 0.2)` | `#64b5f6` / `#4fc3f7` |
| **People** (orange) | contact, contactgroup | `rgba(255, 152, 0, 0.2)` / `rgba(255, 193, 7, 0.2)` | `#ffb74d` / `#ffd54f` |
| **System** (purple) | command | `rgba(156, 39, 176, 0.2)` | `#ba68c8` |
| **Neutral** (gray) | timeperiod | `rgba(96, 125, 139, 0.2)` | `#90a4ae` |
| **Dependencies** (red/purple) | host/servicedependency, host/serviceescalation | `rgba(241, 76, 76, 0.2)` / `rgba(197, 134, 192, 0.2)` | `#f77` / `#c586c0` |

### Diff Colors

For diagrams showing before/after comparisons:

| State | Background | Text | CSS usage examples |
|-------|-----------|------|-------------------|
| **Added** | `rgba(76, 175, 80, 0.15)` | `#81c784` | `.git-diff-line.added`, `.staged-detail-to` |
| **Removed** | `rgba(241, 76, 76, 0.15)` | `#f77` | `.git-diff-line.removed`, `.staged-detail-from` |

### White/Black Alphas

For overlays and subtle layering effects in diagrams:

| Token | Value | CSS usage examples |
|-------|-------|-------------------|
| `--nbe-white-alpha-10` | `rgba(255,255,255,0.1)` | `.tree-folder-add-btn`, tab hover bg |
| `--nbe-white-alpha-50` | `rgba(255,255,255,0.5)` | `.editor-tab` inactive text |
| `--nbe-white-alpha-70` | `rgba(255,255,255,0.7)` | `.tree-folder-count`, breadcrumb text |
| `--nbe-white-alpha-90` | `rgba(255,255,255,0.9)` | `.commit-stat` strong text |
| `--nbe-black-alpha-20` | `rgba(0,0,0,0.2)` | `.node-header` default bg (inheritance) |
| `--nbe-black-alpha-50` | `rgba(0,0,0,0.5)` | `--nbe-overlay-dark` modal overlays |

## Diagram Inventory

### Tier 1 — Highest Value (implement first)

| # | Page | Type | What it depicts |
|---|------|------|-----------------|
| 1 | `architecture.html` | Layered architecture | Flask app → app.extensions → 5 services (NagiosService, StagingManager, GitService, BackupManager, ServerConfig) with lock/atomic-write annotations |
| 2 | `data-flow-staging.html` | Sequence flow | User edit → API → StagingManager → staging.json → Apply → disk write → Git commit |
| 3 | `data-flow-staging.html` | State machine | Staging states: EMPTY → ACTIVE → APPLIED with triggering events |
| 4 | `staging-system.html` | Timeline flow | Edit → staging indicator → review → commit dialog → apply, showing the 10 operation types feeding in |
| 5 | `git-integration.html` | Workflow | Two paths: (1) Edit→Apply→Commit, (2) Discard paths (staging-only vs git cleanup) |
| 6a | `frontend-architecture.html` | Module hierarchy | Three tiers: Core modules → Page modules → Explorer modules with dependency arrows |
| 6b | `frontend-architecture.html` | Color palette swatches | Visual grid of the design system colors — backgrounds, text, accents, borders, validation states, object type badges — with actual rendered color swatches, token names, and hex values so developers can see the palette at a glance |
| 7 | `backend-services.html` | Service map | Each service as a box with method categories (Query, Mutation, Lock, Undo, etc.) |
| 8 | `bulk-operations.html` | Decision tree | Select objects → branches to Move/Clone/Delete/Edit with confirmation steps |

### Tier 2 — High Value (add later)

| # | Page | Type | What it depicts |
|---|------|------|-----------------|
| 9 | `explorer-navigation.html` | UI layout | Three-pane layout with labeled regions showing what content appears in each pane |
| 10 | `dependency-graph.html` | Example graph | Sample Cytoscape graph with 3-4 interconnected nodes, color coding, edge labels |
| 11 | `file-folder-management.html` | Tree structure | Before/after tree showing moves, creations, deletions with visual indicators |
| 12 | `inheritance-viewer.html` | Inheritance chain | Template A → B → C with attributes flowing down, "first match wins" |

### Tier 3 — Moderate Value

| # | Page | Type | What it depicts |
|---|------|------|-----------------|
| 13 | `editing-objects.html` | Editor layout | Editor header, attribute table, issue badge, impact section layout |
| 14 | `analysis-tools.html` | Taxonomy | Health check issue types, orphan detection, escalation path example |
| 15 | `configuration.html` | Precedence | Environment vars (top) → Config file → Defaults (bottom) override flow |
| 16 | `api-reference.html` | API taxonomy | 60+ endpoints grouped by domain in hierarchical tree |
| 17 | `validation.html` | Cycle | Edit → Apply → Validate → Fix → Re-validate loop |

## Implementation Steps

1. Add `.docs-diagram` CSS class to `static/css/docs.css`
2. Read each target template
3. Add inline SVG at the most contextually appropriate location in each page
4. Test rendering at various widths within the 900px prose container

## Pages That Don't Need Diagrams

- `overview.html` — high-level intro, no complex concepts
- `quick-start.html` — narrative workflow, already clear
- `installation.html` — linear setup steps
- `keyboard-shortcuts.html` — reference table
- `search-filtering.html` — straightforward mechanics
- `audit-log.html` — log viewing, no complex relationships
- `settings.html` — configuration UI reference
- `contributing.html` — code style guidelines
- `backups.html` — sequential operations, text sufficient
