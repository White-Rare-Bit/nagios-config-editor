# HTML Mockup Diagrams Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace 2 SVG UI wireframe diagrams in docs with annotated HTML miniatures using real CSS tokens.

**Architecture:** HTML mockups inside `.docs-mockup` containers in the docs templates, styled with new CSS classes in `docs.css` that reference existing `--nbe-*` tokens. Each mockup replicates the visual structure of the real UI at small scale with annotation labels.

**Tech Stack:** HTML, CSS (existing token system)

---

### Task 1: Add mockup CSS classes to docs.css

**Files:**
- Modify: `static/css/docs.css:567-578` (after `.docs-diagram` block)

**Step 1: Add the CSS**

Insert after the `.docs-diagram svg` rule (line 578) in `docs.css`:

```css
/* HTML mockup diagrams — replace SVG wireframes with real HTML/CSS */
.docs-mockup {
    margin: 32px -40px;
    background: var(--nbe-dark-bg-primary);
    border: 1px solid var(--nbe-dark-border-secondary);
    border-radius: var(--nbe-radius-md);
    padding: 24px 20px 16px;
    font-family: var(--nbe-font-sans);
    font-size: 11px;
    line-height: 1.4;
    color: var(--nbe-dark-text-primary);
}

.docs-mockup-title {
    text-align: center;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 16px;
    color: var(--nbe-dark-text-primary);
}

/* Three-pane explorer layout */
.docs-mockup-panes {
    display: flex;
    gap: 10px;
}

/* Individual panel */
.docs-mockup-panel {
    display: flex;
    flex-direction: column;
    border-radius: 5px;
    background: var(--nbe-dark-bg-secondary);
    overflow: hidden;
    min-height: 160px;
}

.docs-mockup-panel--tree   { flex: 28; border: 2px solid var(--nbe-dark-accent-primary); }
.docs-mockup-panel--editor { flex: 37; border: 2px solid var(--nbe-dark-accent-secondary); }
.docs-mockup-panel--workspace { flex: 28; border: 2px solid var(--nbe-dark-accent-warning); }

/* Panel header bar */
.docs-mockup-panel-header {
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
    text-align: center;
    background: var(--nbe-dark-bg-elevated);
}

.docs-mockup-panel--tree .docs-mockup-panel-header       { color: var(--nbe-dark-accent-primary); border-bottom: 2px solid var(--nbe-dark-accent-primary); }
.docs-mockup-panel--editor .docs-mockup-panel-header     { color: var(--nbe-dark-accent-secondary); border-bottom: 2px solid var(--nbe-dark-accent-secondary); }
.docs-mockup-panel--workspace .docs-mockup-panel-header  { color: var(--nbe-dark-accent-warning); border-bottom: 2px solid var(--nbe-dark-accent-warning); }

/* Panel body */
.docs-mockup-panel-body {
    padding: 8px 10px;
    flex: 1;
}

/* Tab bar */
.docs-mockup-tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 6px;
}

.docs-mockup-tab {
    padding: 3px 8px;
    border-radius: 3px;
    font-size: 9px;
    background: var(--nbe-dark-bg-tertiary);
    border: 1px solid var(--nbe-dark-border-primary);
    color: var(--nbe-dark-text-secondary);
}

.docs-mockup-tab--active-teal {
    background: var(--nbe-dark-accent-alpha-15);
    border-color: var(--nbe-dark-accent-alpha-30);
    color: var(--nbe-dark-accent-primary);
}

.docs-mockup-tab--active-blue {
    background: rgba(144, 202, 249, 0.15);
    border-color: rgba(144, 202, 249, 0.3);
    color: var(--nbe-dark-accent-secondary);
}

.docs-mockup-tab--active-orange {
    background: rgba(255, 224, 130, 0.15);
    border-color: rgba(255, 224, 130, 0.3);
    color: var(--nbe-dark-accent-warning);
}

/* Fake search input */
.docs-mockup-search {
    padding: 3px 8px;
    border-radius: 3px;
    background: var(--nbe-dark-bg-tertiary);
    border: 1px solid var(--nbe-dark-border-primary);
    color: var(--nbe-dark-text-muted);
    font-size: 10px;
    margin-bottom: 8px;
}

/* Tree items */
.docs-mockup-tree-file {
    font-size: 10px;
    color: var(--nbe-dark-text-primary);
    margin: 4px 0 2px;
}

.docs-mockup-tree-obj {
    font-size: 10px;
    color: var(--nbe-dark-text-secondary);
    padding-left: 14px;
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 2px 0;
}

/* Type / source badges */
.docs-mockup-badge {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 8px;
    font-weight: 600;
}

.docs-mockup-badge--teal {
    background: var(--nbe-dark-accent-alpha-15);
    border: 1px solid var(--nbe-dark-accent-alpha-30);
    color: var(--nbe-dark-accent-primary);
}

.docs-mockup-badge--orange {
    background: rgba(255, 224, 130, 0.15);
    border: 1px solid rgba(255, 224, 130, 0.3);
    color: var(--nbe-dark-accent-warning);
}

/* Attribute rows (editor pane) */
.docs-mockup-attr {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 4px 0;
    font-size: 10px;
}

.docs-mockup-attr-label {
    flex: 0 0 auto;
    color: var(--nbe-dark-text-secondary);
}

.docs-mockup-attr-value {
    flex: 1;
    padding: 2px 8px;
    border-radius: 3px;
    background: var(--nbe-dark-bg-tertiary);
    border: 1px solid var(--nbe-dark-border-primary);
    font-family: var(--nbe-font-mono);
    font-size: 10px;
    color: var(--nbe-dark-text-primary);
}

.docs-mockup-attr-value--ref {
    color: var(--nbe-dark-accent-primary);
}

/* ── Inheritance diagram ── */

.docs-mockup-inheritance {
    display: flex;
    gap: 20px;
}

.docs-mockup-chain {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
}

/* Inheritance card */
.docs-mockup-card {
    width: 100%;
    border-radius: 5px;
    background: var(--nbe-dark-bg-secondary);
    padding: 10px 14px;
}

.docs-mockup-card--primary {
    border: 2px solid var(--nbe-dark-accent-primary);
}

.docs-mockup-card--secondary {
    border: 1px solid var(--nbe-dark-border-primary);
}

.docs-mockup-card-name {
    font-size: 12px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
}

.docs-mockup-card-attrs {
    margin-top: 6px;
    font-size: 10px;
    color: var(--nbe-dark-text-secondary);
    font-family: var(--nbe-font-mono);
}

.docs-mockup-card-attrs .val {
    color: var(--nbe-dark-text-primary);
}

.docs-mockup-card-attrs .ref {
    color: var(--nbe-dark-accent-primary);
}

/* Arrow connector between cards */
.docs-mockup-arrow {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 4px 0;
    color: var(--nbe-dark-text-secondary);
    font-size: 9px;
}

.docs-mockup-arrow::before {
    content: '';
    display: block;
    width: 1.5px;
    height: 12px;
    background: var(--nbe-dark-accent-primary);
}

.docs-mockup-arrow::after {
    content: '▼';
    font-size: 7px;
    color: var(--nbe-dark-accent-primary);
    margin: -2px 0 1px;
}

/* Resolved attributes table */
.docs-mockup-resolved {
    flex: 1;
}

.docs-mockup-resolved-title {
    font-size: 11px;
    font-weight: 600;
    text-align: center;
    margin-bottom: 4px;
}

.docs-mockup-resolved-subtitle {
    font-size: 10px;
    color: var(--nbe-dark-text-secondary);
    text-align: center;
    margin-bottom: 10px;
}

.docs-mockup-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
}

.docs-mockup-table th {
    text-align: left;
    padding: 4px 8px;
    font-weight: 600;
    color: var(--nbe-dark-text-secondary);
    border-bottom: 1px solid var(--nbe-dark-border-primary);
}

.docs-mockup-table td {
    padding: 4px 8px;
    font-family: var(--nbe-font-mono);
    color: var(--nbe-dark-text-primary);
}

.docs-mockup-table .source {
    font-family: var(--nbe-font-sans);
    color: var(--nbe-dark-text-secondary);
}

.docs-mockup-table-note {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--nbe-dark-border-primary);
    font-size: 10px;
    color: var(--nbe-dark-text-secondary);
    line-height: 1.5;
}
```

**Step 2: Verify CSS loads**

Run the app, open docs page, check browser devtools for `.docs-mockup` class availability.

**Step 3: Commit**

```bash
git add static/css/docs.css
git commit -m "feat: add docs-mockup CSS classes for HTML wireframe diagrams"
```

---

### Task 2: Replace explorer SVG with HTML mockup

**Files:**
- Modify: `templates/docs/explorer-navigation.html:11-88`

**Step 1: Replace the SVG**

Replace lines 11-88 (the `<div class="docs-diagram">...<svg>...</svg></div>`) with:

```html
<div class="docs-mockup">
    <div class="docs-mockup-title">Object Explorer: Three-Pane Layout</div>
    <div class="docs-mockup-panes">

        <!-- Left Pane: Object Tree -->
        <div class="docs-mockup-panel docs-mockup-panel--tree">
            <div class="docs-mockup-panel-header">Object Tree</div>
            <div class="docs-mockup-panel-body">
                <div class="docs-mockup-tabs">
                    <span class="docs-mockup-tab docs-mockup-tab--active-teal">By File</span>
                    <span class="docs-mockup-tab">By Type</span>
                </div>
                <div class="docs-mockup-search">Search objects...</div>
                <div class="docs-mockup-tree-file">hosts.cfg</div>
                <div class="docs-mockup-tree-obj">webserver01 <span class="docs-mockup-badge docs-mockup-badge--teal">host</span></div>
                <div class="docs-mockup-tree-obj">webserver02 <span class="docs-mockup-badge docs-mockup-badge--teal">host</span></div>
                <div class="docs-mockup-tree-file">services.cfg</div>
            </div>
        </div>

        <!-- Center Pane: Attribute Editor -->
        <div class="docs-mockup-panel docs-mockup-panel--editor">
            <div class="docs-mockup-panel-header">Attribute Editor</div>
            <div class="docs-mockup-panel-body">
                <div class="docs-mockup-tabs">
                    <span class="docs-mockup-tab docs-mockup-tab--active-blue">webserver01</span>
                    <span class="docs-mockup-tab">webserver02</span>
                </div>
                <div class="docs-mockup-attr">
                    <span class="docs-mockup-attr-label">host_name</span>
                    <span class="docs-mockup-attr-value">webserver01</span>
                </div>
                <div class="docs-mockup-attr">
                    <span class="docs-mockup-attr-label">address</span>
                    <span class="docs-mockup-attr-value">192.168.1.10</span>
                </div>
                <div class="docs-mockup-attr">
                    <span class="docs-mockup-attr-label">check_command</span>
                    <span class="docs-mockup-attr-value docs-mockup-attr-value--ref">check-host-alive</span>
                </div>
            </div>
        </div>

        <!-- Right Pane: Workspace -->
        <div class="docs-mockup-panel docs-mockup-panel--workspace">
            <div class="docs-mockup-panel-header">Workspace</div>
            <div class="docs-mockup-panel-body">
                <div class="docs-mockup-tabs">
                    <span class="docs-mockup-tab docs-mockup-tab--active-orange">Files</span>
                    <span class="docs-mockup-tab">Suggestions</span>
                    <span class="docs-mockup-tab">Errors</span>
                    <span class="docs-mockup-tab">Validation</span>
                </div>
                <div class="docs-mockup-tree-file">hosts/</div>
                <div class="docs-mockup-tree-obj">hosts.cfg</div>
                <div class="docs-mockup-tree-obj">templates.cfg</div>
                <div class="docs-mockup-tree-file">services/</div>
                <div class="docs-mockup-tree-obj">services.cfg</div>
            </div>
        </div>

    </div>
</div>
```

**Step 2: Visual check**

Open `http://localhost:8080/docs`, navigate to "Object Explorer", verify the mockup renders with 3 colored panels, tabs, sample data, and annotation labels.

**Step 3: Commit**

```bash
git add templates/docs/explorer-navigation.html
git commit -m "feat: replace explorer SVG wireframe with HTML mockup"
```

---

### Task 3: Replace inheritance SVG with HTML mockup

**Files:**
- Modify: `templates/docs/inheritance-viewer.html:11-93`

**Step 1: Replace the SVG**

Replace lines 11-93 (the `<div class="docs-diagram">...<svg>...</svg></div>`) with:

```html
<div class="docs-mockup">
    <div class="docs-mockup-title">Template Inheritance Chain</div>
    <div class="docs-mockup-inheritance">

        <!-- Left: Inheritance chain -->
        <div class="docs-mockup-chain">
            <div class="docs-mockup-card docs-mockup-card--primary">
                <div class="docs-mockup-card-name">
                    web-server01 <span class="docs-mockup-badge docs-mockup-badge--teal">host</span>
                </div>
                <div class="docs-mockup-card-attrs">
                    address=<span class="val">192.168.1.10</span>&nbsp;&nbsp;use=<span class="ref">linux-server</span>
                </div>
            </div>

            <div class="docs-mockup-arrow">inherits from</div>

            <div class="docs-mockup-card docs-mockup-card--secondary">
                <div class="docs-mockup-card-name">
                    linux-server <span class="docs-mockup-badge docs-mockup-badge--orange">template</span>
                </div>
                <div class="docs-mockup-card-attrs">
                    check_command=<span class="val">check-host-alive</span>&nbsp;&nbsp;use=<span class="ref">generic-host</span>
                </div>
            </div>

            <div class="docs-mockup-arrow">inherits from</div>

            <div class="docs-mockup-card docs-mockup-card--secondary">
                <div class="docs-mockup-card-name">
                    generic-host <span class="docs-mockup-badge docs-mockup-badge--orange">template</span>
                </div>
                <div class="docs-mockup-card-attrs">
                    max_check_attempts=<span class="val">3</span>&nbsp;&nbsp;notification_period=<span class="val">24x7</span>
                </div>
            </div>
        </div>

        <!-- Right: Resolved attributes table -->
        <div class="docs-mockup-resolved">
            <div class="docs-mockup-resolved-title">Resolved Attributes</div>
            <div class="docs-mockup-resolved-subtitle">"First match wins" — child values override parents</div>
            <table class="docs-mockup-table">
                <thead>
                    <tr><th>Attribute</th><th>Value</th><th>Source</th></tr>
                </thead>
                <tbody>
                    <tr>
                        <td>address</td>
                        <td>192.168.1.10</td>
                        <td><span class="docs-mockup-badge docs-mockup-badge--teal">self</span></td>
                    </tr>
                    <tr>
                        <td>check_command</td>
                        <td>check-host-alive</td>
                        <td class="source">linux-server</td>
                    </tr>
                    <tr>
                        <td>max_check_attempts</td>
                        <td>3</td>
                        <td class="source">generic-host</td>
                    </tr>
                    <tr>
                        <td>notification_period</td>
                        <td>24x7</td>
                        <td class="source">generic-host</td>
                    </tr>
                </tbody>
            </table>
            <div class="docs-mockup-table-note">
                If both child and parent define the same attribute, the child's value wins.
                The viewer shows which level provides each value.
            </div>
        </div>

    </div>
</div>
```

**Step 2: Visual check**

Open `http://localhost:8080/docs`, navigate to "Inheritance Viewer", verify the mockup renders with the chain on the left, arrows between cards, and the resolved table on the right.

**Step 3: Commit**

```bash
git add templates/docs/inheritance-viewer.html
git commit -m "feat: replace inheritance SVG wireframe with HTML mockup"
```
