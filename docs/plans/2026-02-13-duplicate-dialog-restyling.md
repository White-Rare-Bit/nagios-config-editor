# Duplicate Dialog Restyling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restyle the "Resolve Duplicate" dialog to use card-based entries with correct design tokens for typography, spacing, and button emphasis.

**Architecture:** CSS-only changes for new card class and typography fixes, plus a minor JS template update in `fixDuplicate()` to use the new card wrapper and tonal buttons.

**Tech Stack:** CSS (design tokens), vanilla JS (template string)

---

### Task 1: Add card styles and fix typography in CSS

**Files:**
- Modify: `static/css/explorer.css:2782-2786` (`.cleanup-detail-file`)
- Modify: `static/css/explorer.css:4103-4106` (`.dialog-duplicate-list`)

**Step 1: Add `font-size` to `.cleanup-detail-file`**

In `static/css/explorer.css` at line 2782, change:

```css
.cleanup-detail-file {
    font-family: var(--nbe-font-mono);
    font-weight: 500;
    color: var(--nbe-dark-text-primary);
}
```

To:

```css
.cleanup-detail-file {
    font-family: var(--nbe-font-mono);
    font-size: var(--nbe-font-size-sm);
    font-weight: 500;
    color: var(--nbe-dark-text-primary);
}
```

**Step 2: Add `.dialog-duplicate-entry` card class and scoped `.code-preview` override**

In `static/css/explorer.css`, after the `.dialog-duplicate-list` block (line 4106), add:

```css
.dialog-duplicate-entry {
    background: var(--nbe-dark-bg-tertiary);
    border-radius: var(--nbe-radius-md);
    margin-bottom: var(--nbe-space-sm);
    overflow: hidden;
}

.dialog-duplicate-entry:last-child {
    margin-bottom: 0;
}

.dialog-duplicate-entry .code-preview {
    padding: var(--nbe-space-sm) var(--nbe-space-md);
    border-top: 1px solid var(--nbe-dark-border-secondary);
}
```

**Step 3: Verify visually**

Run: `python3 app.py`
Open browser, navigate to Explorer, find a duplicate suggestion, click "Fix". Confirm cards render with subtle background, file names are 13px mono, diff rows have top border separator inside card.

**Step 4: Commit**

```bash
git add static/css/explorer.css
git commit -m "style: add card-based duplicate dialog entry styles and fix file badge font-size"
```

---

### Task 2: Update JS template to use card wrapper and tonal buttons

**Files:**
- Modify: `static/js/explorer/analysis.js:1105-1116` (`fixDuplicate()` template)

**Step 1: Update the HTML template**

In `static/js/explorer/analysis.js` at line 1105, change:

```javascript
        return {
            html: `<div class="u-mb-md">
                <div class="dialog-entry-header">
                    <div class="ref-item-clickable" onclick="Explorer.navigateToObjectByIndex(${o.global_index}); Explorer.closeDialog();">
                        <span class="cleanup-detail-file">${Explorer.escapeHtml(file)}</span>
                        <span class="cleanup-detail-line">Line ${o.line_number || '?'}</span>
                    </div>
                    <button class="nbe-btn nbe-btn--dark nbe-btn--outlined nbe-btn--sm" onclick="Explorer.keepDuplicateAndDeleteOthers(${idx}, ${i})">Keep This</button>
                </div>
                ${diffHtml ? `<div class="code-preview">${diffHtml}</div>` : ''}
            </div>`
        };
```

To:

```javascript
        return {
            html: `<div class="dialog-duplicate-entry">
                <div class="dialog-entry-header">
                    <div class="ref-item-clickable" onclick="Explorer.navigateToObjectByIndex(${o.global_index}); Explorer.closeDialog();">
                        <span class="cleanup-detail-file">${Explorer.escapeHtml(file)}</span>
                        <span class="cleanup-detail-line">Line ${o.line_number || '?'}</span>
                    </div>
                    <button class="nbe-btn nbe-btn--dark nbe-btn--tonal nbe-btn--sm" onclick="Explorer.keepDuplicateAndDeleteOthers(${idx}, ${i})">Keep This</button>
                </div>
                ${diffHtml ? `<div class="code-preview">${diffHtml}</div>` : ''}
            </div>`
        };
```

Changes: `u-mb-md` → `dialog-duplicate-entry`, `nbe-btn--outlined` → `nbe-btn--tonal`.

**Step 2: Verify visually**

Run: `python3 app.py`
Open the duplicate resolution dialog. Confirm:
- Cards have subtle background with rounded corners
- File names are compact 13px monospace
- "Keep This" buttons are tonal (filled with muted background) not outlined
- Diff rows sit inside the card with a separator border
- Spacing between cards is tight (8px)

**Step 3: Commit**

```bash
git add static/js/explorer/analysis.js
git commit -m "style: use card wrapper and tonal buttons in duplicate dialog"
```
