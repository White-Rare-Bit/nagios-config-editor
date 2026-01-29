# Font Analysis - Nagios Bulk Editor

## 1. Font Families

### Bundled Fonts (Cross-Platform)

Web fonts are bundled in `static/vendor/fonts/` to ensure consistent rendering across Ubuntu 22.04+, RHEL 8+, macOS, and Windows.

#### Inter (UI Font)
```css
--nbe-font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

| File | Weight | Size |
|------|--------|------|
| Inter-Regular.woff2 | 400 | ~95KB |
| Inter-Medium.woff2 | 500 | ~96KB |
| Inter-SemiBold.woff2 | 600 | ~96KB |

**Purpose:** All UI text - buttons, labels, dialogs, navigation, form inputs

**License:** SIL Open Font License 1.1

#### JetBrains Mono (Code Font)
```css
--nbe-font-mono: 'JetBrains Mono', 'SF Mono', 'Consolas', 'Ubuntu Mono', monospace;
```

| File | Weight | Size |
|------|--------|------|
| JetBrainsMono-Regular.woff2 | 400 | ~90KB |

**Purpose:** Code blocks, configuration content, syntax highlighting, git diffs

**License:** SIL Open Font License 1.1

### System Font Fallbacks

If bundled fonts fail to load, the following system fonts are used:

| Platform | Sans Fallback | Mono Fallback |
|----------|---------------|---------------|
| macOS | San Francisco (-apple-system) | SF Mono |
| Windows | Segoe UI | Consolas |
| Linux | Roboto (if installed) | Ubuntu Mono |
| Generic | sans-serif | monospace |

---

## 2. Font Size Scale

All sizes defined as CSS variables in `tokens.css`:

| Variable | Size | Purpose |
|----------|------|---------|
| `--nbe-font-size-2xs` | 9px | Line numbers, tiny hints |
| `--nbe-font-size-xs` | 10px | Badges, captions, type tags |
| `--nbe-font-size-xs-plus` | 11px | Small buttons |
| `--nbe-font-size-sm` | 12px | Form labels, tab text, secondary info |
| `--nbe-font-size-base` | 13px | Default body text, input fields |
| `--nbe-font-size-md` | 14px | Larger body text, emphasis |
| `--nbe-font-size-lg` | 16px | Section headers |
| `--nbe-font-size-xl` | 18px | Page titles |
| `--nbe-font-size-2xl` | 20px | Main headings |
| `--nbe-font-size-icon-lg` | 48px | Empty state icons |
| `--nbe-font-size-icon-xl` | 64px | Large empty state icons |

---

## 3. Font Weights

| Weight | Value | Usage |
|--------|-------|-------|
| Normal | 400 | Body text, regular labels |
| Medium | 500 | Section titles, emphasis, tab text |
| Semi-bold | 600 | Headers, badges, form labels |
| Icon weight | 900 | Font Awesome solid icons |

---

## 4. Font Awesome 6 Icons

### Webfont Files
Located in `/static/vendor/webfonts/`:

| File | Size | Purpose |
|------|------|---------|
| `fa-solid-900.woff2` | 156 KB | Solid icons (primary) |
| `fa-solid-900.ttf` | 420 KB | Solid fallback |
| `fa-regular-400.woff2` | 25 KB | Regular weight icons |
| `fa-regular-400.ttf` | 68 KB | Regular fallback |
| `fa-brands-400.woff2` | 117 KB | Brand logos |
| `fa-brands-400.ttf` | 208 KB | Brands fallback |

### Icons by Category

#### Navigation & UI
| Icon | Class | Usage |
|------|-------|-------|
| Undo | `fa-solid fa-rotate-left` | Undo button |
| Keyboard | `fa-solid fa-keyboard` | Shortcuts help |
| Lock | `fa-solid fa-lock` | Lock banner |
| Branch | `fa-solid fa-code-branch` | Git branch |
| Chevron | `fa-solid fa-chevron-right` | Expand/breadcrumbs |
| Caret | `fa-solid fa-caret-down` | Dropdowns |
| Search | `fa-solid fa-magnifying-glass` | Search inputs |

#### Object Operations
| Icon | Class | Usage |
|------|-------|-------|
| Select | `fa-solid fa-check-square` | Select action |
| Folder | `fa-solid fa-folder` | File grouping |
| Layers | `fa-solid fa-layer-group` | Type grouping |
| Tree | `fa-solid fa-folder-tree` | File tree |
| Trash | `fa-solid fa-trash` | Delete |
| Plus | `fa-solid fa-plus` | Create/add |
| Export | `fa-solid fa-file-export` | Move to file |
| Graph | `fa-solid fa-diagram-project` | Graph view |

#### Validation & Status
| Icon | Class | Usage |
|------|-------|-------|
| Warning | `fa-solid fa-triangle-exclamation` | Warnings |
| Check | `fa-solid fa-circle-check` | Success |
| Error | `fa-solid fa-circle-xmark` | Errors |
| Info | `fa-solid fa-circle-info` | Info messages |
| Clipboard | `fa-solid fa-clipboard-list` | Empty states |
| Lightbulb | `fa-solid fa-lightbulb` | Suggestions |
| Health | `fa-solid fa-stethoscope` | Health check |
| Archive | `fa-solid fa-box-archive` | Backups |

#### Git Operations
| Icon | Class | Usage |
|------|-------|-------|
| Save | `fa-solid fa-floppy-disk` | Commit |
| History | `fa-solid fa-clock-rotate-left` | Restore |
| Refresh | `fa-solid fa-rotate` | Reload |
| Clean | `fa-solid fa-broom` | Clean operation |
| Open | `fa-solid fa-folder-open` | Open folder |

#### Settings & Config
| Icon | Class | Usage |
|------|-------|-------|
| Server | `fa-solid fa-server` | Server settings |
| User | `fa-solid fa-user` | Identity |
| Gears | `fa-solid fa-gears` | Settings |
| Sliders | `fa-solid fa-sliders` | Configuration |
| Link | `fa-solid fa-link` | References |
| Broken | `fa-solid fa-link-slash` | Broken refs |
| Filter | `fa-solid fa-filter` | Filters |

---

## 5. Typography Purpose Mapping

### Headings
| Level | Size | Weight | Use |
|-------|------|--------|-----|
| H1 | `--nbe-font-size-2xl` (20px) | 600 | Page titles |
| H2 | `--nbe-font-size-lg` (16px) | 600 | Section headers |
| H3 | `--nbe-font-size-md` (14px) | 600 | Subsections |
| Label | `--nbe-font-size-sm` (12px) | 500-600 | Form labels |

### Body Text
| Type | Size | Weight | Color |
|------|------|--------|-------|
| Primary | `--nbe-font-size-base` (13px) | 400 | `--nbe-text-primary` |
| Secondary | `--nbe-font-size-sm` (12px) | 400 | `--nbe-text-secondary` |
| Muted | `--nbe-font-size-xs` (10px) | 400 | `--nbe-text-muted` |

### Buttons
| Size | Font Size | Padding |
|------|-----------|---------|
| Small | `--nbe-font-size-sm` (12px) | 6px 12px |
| Medium | `--nbe-font-size-base` (13px) | 8px 16px |
| Large | `--nbe-font-size-md` (14px) | 10px 20px |

### Code
| Element | Font | Size |
|---------|------|------|
| Code blocks | `--nbe-font-mono` | 12px |
| Inline code | `--nbe-font-mono` | 12px |
| Git diffs | `--nbe-font-mono` | 12px |

### Badges
| Type | Size | Weight | Style |
|------|------|--------|-------|
| Count badges | 10px | 600 | Normal |
| Type badges | 10px | 600 | Uppercase |
| Status badges | 10px | 600 | Normal |

---

## 6. Syntax Highlighting Colors

For Nagios configuration display:

| Token | Variable | Color | Style |
|-------|----------|-------|-------|
| Keywords | `--nbe-syntax-keyword` | #569cd6 | Normal |
| Object types | `--nbe-syntax-object-type` | #4ec9b0 | Normal |
| Braces | `--nbe-syntax-brace` | #ffd700 | Normal |
| Attr names | `--nbe-syntax-attr-name` | #9cdcfe | Normal |
| Attr values | `--nbe-syntax-attr-value` | #ce9178 | Normal |
| Comments | `--nbe-syntax-comment` | #6a9955 | Italic |
| Strings | `--nbe-syntax-string` | #ce9178 | Normal |
| Numbers | `--nbe-syntax-number` | #b5cea8 | Normal |
| Escapes | `--nbe-syntax-escape` | #d7ba7d | Normal |
| Pipes | `--nbe-syntax-pipe` | #c586c0 | Normal |
| Paths | `--nbe-syntax-path` | #dcdcaa | Normal |

---

## 7. Dark Theme Text Colors

| Token | Color | Contrast | Usage |
|-------|-------|----------|-------|
| `--nbe-dark-text-primary` | #d4d4d4 | 11.4:1 | Main text |
| `--nbe-dark-text-secondary` | #888888 | 4.7:1 | Secondary text |
| `--nbe-dark-text-muted` | #666666 | 4.5:1 | Muted/disabled |

All colors meet WCAG AA contrast requirements (4.5:1 minimum).

---

## 8. CSS Loading Order

```html
1. vendor/css/bootstrap.min.css    <!-- Base reset -->
2. vendor/css/fontawesome.min.css  <!-- Icon fonts -->
3. css/tokens.css                  <!-- Design tokens -->
4. css/forms.css                   <!-- Form components -->
5. css/style.css                   <!-- Global styles -->
6. css/[page].css                  <!-- Page-specific -->
```

---

## 9. Key File References

| File | Contents |
|------|----------|
| `static/css/tokens.css` | Font families, sizes, weights (lines 66-80) |
| `static/css/forms.css` | Form typography |
| `static/css/objects.css` | Syntax highlighting (lines 184-189) |
| `static/vendor/css/fontawesome.min.css` | Icon definitions |
| `static/vendor/webfonts/` | 6 webfont files |

---

## 10. Summary

| Aspect | Value |
|--------|-------|
| UI Font | Inter (bundled) with system fallbacks |
| Code Font | JetBrains Mono (bundled) with system fallbacks |
| Font Files | 4 woff2 files (~377KB total) |
| Size Scale | 11 sizes (9px - 64px) |
| Weights | 400, 500, 600, 900 |
| Icon Library | Font Awesome 6 Free |
| Total Icons | ~60 unique icons used |
| WCAG Compliance | AA (4.5:1 minimum contrast) |
| Cross-Platform | Ubuntu 22.04+, RHEL 8+, macOS, Windows |
