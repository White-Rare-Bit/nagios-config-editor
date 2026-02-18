# Editor Pane Unusable at 800px Viewport Width

**Phase**: Phase 1 — Orientation & Tree Integrity
**Severity**: Major
**Category**: UI/UX

## What Was Tested

Resized browser viewport to 800×768 while viewing a host object (app-prod-01) in the center editor pane.

## Expected Behavior

The interface should either:
(a) Remain usable with responsive reflow (e.g., the workspace panel hides or collapses), or
(b) Show a minimum-width warning

Attribute labels and their corresponding input fields should always be visible together.

## Actual Behavior

At 800px:
- The three-panel layout (tree | editor | workspace) forces each panel to be ~260px wide
- Attribute labels (address, alias, host_name, hostgroups, parents, use) render in the left portion of the editor, but the corresponding **input fields are completely off-screen** to the right
- The tab strip above the editor overflows, showing only the first open tab with ellipsis truncation
- The editor is technically visible but completely unusable — a user cannot edit any attribute

## Screenshot

`screenshots/01-narrow-800px.png`

## Impact

Laptops commonly run at 1280px or narrower, and browser zoom-in scenarios push effective widths below 1000px. The interface becomes completely non-functional for editing at these widths — the core use case.

The workspace panel (file tree) could be made collapsible or hidden at narrow widths to free space for the editor.
