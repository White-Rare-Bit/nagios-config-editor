        1 # Material Design Palette Overhaul + CSS Cleanup
        2
        3 > **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-tas
          k.
        4
        5 **Goal:** Adopt Material Design colors as the standard palette across the entire interface, replacing th
          e current mixed color system. Simultaneously extract shared dark-page CSS boilerplate to eliminate ~191
          `!important` declarations and ~300 lines of duplication.
        6
        7 **Architecture:** Two phases — (1) replace all color tokens in `tokens.css` with Material Design equival
          ents, maintaining WCAG AA compliance, then (2) extract shared dark-page overrides and clean up hardcoded
           colors in page-specific CSS files.
        8
        9 **Tech Stack:** CSS only (no JS/Python changes). Pure visual refactor — layout and behavior unchanged.
       10
       11 ---
       12
       13 ## Phase 1: Material Design Token Replacement
       14
       15 ### Task 1: Replace primary, semantic, text, background, and border tokens
       16
       17 **Files:**
       18 - Modify: `static/css/tokens.css` (`:root` section, lines 37-100)
       19
       20 Replace the following token values. All replacements maintain WCAG AA (4.5:1 text, 3:1 UI).
       21
       22 **Primary:**
       23 ```css
       24 --nbe-primary: #1976D2;           /* was #006fcc — MD Blue 700 */
       25 --nbe-primary-hover: #1565C0;     /* was #0056a3 — MD Blue 800 */
       26 --nbe-primary-light: #E3F2FD;     /* was #eff6ff — MD Blue 50 */
       27 --nbe-primary-border: #90CAF9;    /* was #90caf9 — MD Blue 200 (already MD!) */
       28 ```
       29
       30 **Success:**
       31 ```css
       32 --nbe-success: #2E7D32;           /* was #1a6b1e — MD Green 800 (5.0:1 on success-light) */
       33 --nbe-success-light: #E8F5E9;     /* was #e8f5e9 — MD Green 50 (already MD!) */
       34 --nbe-success-border: #A5D6A7;    /* was #a5d6a7 — MD Green 200 (already MD!) */
       35 ```
       36
       37 **Warning:**
       38 ```css
       39 --nbe-warning: #E65100;           /* was #b45309 — MD Orange 900 (4.6:1 on warning-light) */
       40 --nbe-warning-light: #FFF3E0;     /* was #fff3e0 — MD Orange 50 (already MD!) */
       41 --nbe-warning-border: #FFCC80;    /* was #ffcc80 — MD Orange 200 (already MD!) */
       42 ```
       43
       44 **Danger:**
       45 ```css
       46 --nbe-danger: #C62828;            /* was #991b1b — MD Red 800 (5.2:1 on danger-light) */
       47 --nbe-danger-light: #FFEBEE;      /* was #ffebee — MD Red 50 (already MD!) */
       48 --nbe-danger-border: #EF9A9A;     /* was #ef9a9a — MD Red 200 (already MD!) */
       49 ```
       50
       51 **Info:**
       52 ```css
       53 --nbe-info: #1565C0;              /* was #0059a8 — MD Blue 800 (4.8:1 on info-light) */
       54 --nbe-info-light: #E3F2FD;        /* was #e3f2fd — MD Blue 50 (already MD!) */
       55 --nbe-info-border: #90CAF9;       /* was #90caf9 — MD Blue 200 (already MD!) */
       56 ```
       57
       58 **Text:**
       59 ```css
       60 --nbe-text-primary: #212121;      /* was #1f2937 — MD Grey 900 */
       61 --nbe-text-secondary: #616161;    /* was #5c6370 — MD Grey 700 (5.1:1 on white) */
       62 --nbe-text-muted: #757575;        /* was #717171 — MD Grey 600 (4.6:1 on white) */
       63 --nbe-text-inverse: #FFFFFF;      /* was #fff — no change */
       64 ```
       65
       66 **Backgrounds:**
       67 ```css
       68 --nbe-bg-page: #FAFAFA;           /* was #f8f9fa — MD Grey 50 */
       69 --nbe-bg-surface: #FFFFFF;        /* was #fff — no change */
       70 --nbe-bg-subtle: #F5F5F5;         /* was #f3f4f6 — MD Grey 100 */
       71 --nbe-bg-hover: #EEEEEE;          /* was #e8eaed — MD Grey 200 */
       72 --nbe-bg-selected: #E3F2FD;       /* was #eff6ff — MD Blue 50 */
       73 --nbe-bg-dark: #455A64;           /* was #3a4d5c — MD Blue Grey 700 */
       74 --nbe-bg-zebra: #F5F5F5;          /* was #f0f4f8 — MD Grey 100 */
       75 --nbe-bg-hover-row: #BBDEFB;      /* was #dbeafe — MD Blue 100 */
       76 --nbe-bg-selected-row: #90CAF9;   /* was #bfdbfe — MD Blue 200 */
       77 --nbe-bg-header: #E0E0E0;         /* was #e5e7eb — MD Grey 300 */
       78 ```
       79
       80 **Borders:**
       81 ```css
       82 --nbe-border: #E0E0E0;            /* was #d9dde3 — MD Grey 300 */
       83 --nbe-border-light: #EEEEEE;      /* was #e5e7eb — MD Grey 200 */
       84 --nbe-border-lighter: #F5F5F5;    /* was #eaeaea — MD Grey 100 */
       85 --nbe-border-focus: #1976D2;      /* was #006fcc — MD Blue 700 (matches primary) */
       86 ```
       87
       88 **Focus ring (update rgba to match new primary):**
       89 ```css
       90 --nbe-focus-ring: 0 0 0 2px rgba(25, 118, 210, 0.25);
       91 --nbe-focus-ring-inset: inset 0 0 0 2px rgba(25, 118, 210, 0.25);
       92 ```
       93
       94 **Interactive elements:**
       95 ```css
       96 --nbe-btn-success-hover: #1B5E20; /* was #145817 — MD Green 900 */
       97 --nbe-hover-darken: #BDBDBD;      /* was #bdbdbd — MD Grey 400 (already MD!) */
       98 --nbe-text-link: #2196F3;         /* was #2196f3 — MD Blue 500 (already MD!) */
       99 ```
      100
      101 **Primary alpha overlays (update base color to new primary):**
      102 ```css
      103 --nbe-primary-alpha-10: rgba(25, 118, 210, 0.1);
      104 --nbe-primary-alpha-15: rgba(25, 118, 210, 0.15);
      105 --nbe-primary-alpha-20: rgba(25, 118, 210, 0.2);
      106 --nbe-primary-alpha-25: rgba(25, 118, 210, 0.25);
      107 --nbe-primary-alpha-40: rgba(25, 118, 210, 0.4);
      108 --nbe-primary-alpha-50: rgba(25, 118, 210, 0.5);
      109 ```
      110
      111 **Step 1:** Apply all replacements above in `tokens.css`.
      112
      113 **Step 2:** Update the legacy color aliases in `templates/base.html` inline `<style>` block (~line 271-2
          74) — these reference `--nbe-success`, `--nbe-danger` etc. via `var()` so they auto-update. Verify they
          still work.
      114
      115 **Step 3:** Visual check — open a light-themed page (Inheritance, Bulk Rename). Verify text readability,
           button colors, status badges.
      116
      117 **Step 4:** Commit: `feat: adopt Material Design palette for light theme tokens`
      118
      119 ---
      120
      121 ### Task 2: Replace light-theme object type badge tokens
      122
      123 **Files:**
      124 - Modify: `static/css/tokens.css` (lines 344-375)
      125
      126 Replace custom pastels with Material Design shade-based colors (50/100 for bg, 900 for text):
      127
      128 ```css
      129 /* Infrastructure (green) - hosts, hostgroups */
      130 --nbe-type-infra-bg: #E8F5E9;         /* was #dcfce7 — MD Green 50 */
      131 --nbe-type-infra-text: #1B5E20;       /* was #166534 — MD Green 900 */
      132 --nbe-type-infra-bg-alt: #C8E6C9;     /* was #d1fae5 — MD Green 100 */
      133 --nbe-type-infra-text-alt: #1B5E20;   /* was #065f46 — MD Green 900 */
      134
      135 /* Monitoring (blue) - services, servicegroups */
      136 --nbe-type-monitor-bg: #E3F2FD;       /* was #dbeafe — MD Blue 50 */
      137 --nbe-type-monitor-text: #0D47A1;     /* was #1e40af — MD Blue 900 */
      138 --nbe-type-monitor-bg-alt: #BBDEFB;   /* was #bfdbfe — MD Blue 100 */
      139 --nbe-type-monitor-text-alt: #0D47A1; /* was #1e3a8a — MD Blue 900 */
      140
      141 /* People (orange) - contacts, contactgroups */
      142 --nbe-type-people-bg: #FFF3E0;        /* was #fed7aa — MD Orange 50 */
      143 --nbe-type-people-text: #BF360C;      /* was #7c2d12 — MD Deep Orange 900 (5.1:1 on Orange 50) */
      144 --nbe-type-people-bg-alt: #FFE0B2;    /* was #fdba74 — MD Orange 100 */
      145 --nbe-type-people-text-alt: #BF360C;  /* was #6b2710 — MD Deep Orange 900 */
      146
      147 /* System (purple) - commands */
      148 --nbe-type-system-bg: #F3E5F5;        /* was #e9d5ff — MD Purple 50 */
      149 --nbe-type-system-text: #4A148C;      /* was #6b21a8 — MD Purple 900 */
      150
      151 /* Neutral (gray) - timeperiods */
      152 --nbe-type-neutral-bg: #ECEFF1;       /* was #e5e7eb — MD Blue Grey 50 */
      153 --nbe-type-neutral-text: #37474F;     /* was #374151 — MD Blue Grey 800 */
      154
      155 /* Dependencies (cyan) - dependencies, escalations */
      156 --nbe-type-deps-bg: #E0F7FA;          /* was #a5f3fc — MD Cyan 50 */
      157 --nbe-type-deps-text: #006064;        /* was #155e75 — MD Cyan 900 */
      158 --nbe-type-deps-bg-alt: #B2EBF2;     /* was #bbf7d0 — MD Cyan 100 */
      159 --nbe-type-deps-text-alt: #006064;    /* was #166534 — MD Cyan 900 */
      160 ```
      161
      162 **Validation/status chips:**
      163 ```css
      164 --nbe-chip-error-bg: #FFEBEE;         /* was #fee2e2 — MD Red 50 */
      165 --nbe-chip-error-text: #B71C1C;       /* was #991b1b — MD Red 900 (5.5:1 on Red 50) */
      166 --nbe-chip-warning-bg: #FFF8E1;       /* was #fef3c7 — MD Yellow 50 */
      167 --nbe-chip-warning-text: #E65100;     /* was #7c2d12 — MD Orange 900 */
      168 --nbe-chip-valid-bg: #E8F5E9;         /* was #dcfce7 — MD Green 50 */
      169 --nbe-chip-valid-text: #1B5E20;       /* was #166534 — MD Green 900 */
      170 ```
      171
      172 **Step 1:** Apply replacements.
      173 **Step 2:** Visual check — open Explorer, check object type badges in the tree and table.
      174 **Step 3:** Commit: `feat: adopt MD palette for object type badges and status chips`
      175
      176 ---
      177
      178 ### Task 3: Replace dark theme accent and UI tokens
      179
      180 **Files:**
      181 - Modify: `static/css/tokens.css` (dark theme section, lines ~390-440)
      182
      183 The dark theme currently uses VS Code-inspired teal (`#4ec9b0`) as the primary accent. Switch to Materia
          l Design Teal 200 (`#80CBC4`) which is close but more consistently Material:
      184
      185 ```css
      186 /* Dark theme accents */
      187 --nbe-dark-accent-primary: #80CBC4;       /* was #4ec9b0 — MD Teal 200 */
      188 --nbe-dark-accent-secondary: #90CAF9;     /* was #569cd6 — MD Blue 200 */
      189 --nbe-dark-accent-warning: #FFE082;       /* was #ffc107 — MD Amber 200 */
      190 --nbe-dark-accent-danger: #EF9A9A;        /* was #f14c4c — MD Red 200 */
      191 --nbe-dark-accent-primary-hover: #B2DFDB; /* was #5ed4ba — MD Teal 100 */
      192 --nbe-dark-accent-danger-hover: #E57373;  /* was #ff6b6b — MD Red 300 */
      193 --nbe-dark-warning-bg: rgba(255, 224, 130, 0.15); /* derived from MD Amber 200 */
      194 ```
      195
      196 **Dark theme buttons (update to match new accent):**
      197 ```css
      198 --nbe-dark-btn-primary-bg: #80CBC4;       /* was #4ec9b0 — MD Teal 200 */
      199 --nbe-dark-btn-primary-hover: #4DB6AC;    /* was #3fb896 — MD Teal 300 */
      200 ```
      201
      202 **Dark theme tabs (update active border):**
      203 ```css
      204 --nbe-dark-tab-border-active: #80CBC4;    /* was #4ec9b0 — MD Teal 200 */
      205 ```
      206
      207 **Dark theme input focus:**
      208 ```css
      209 --nbe-dark-input-focus: #80CBC4;          /* was #4ec9b0 — MD Teal 200 */
      210 ```
      211
      212 **Dark theme accent alpha (update base color):**
      213 ```css
      214 --nbe-dark-accent-alpha-10: rgba(128, 203, 196, 0.1);
      215 --nbe-dark-accent-alpha-15: rgba(128, 203, 196, 0.15);
      216 --nbe-dark-accent-alpha-20: rgba(128, 203, 196, 0.2);
      217 --nbe-dark-accent-alpha-30: rgba(128, 203, 196, 0.3);
      218 --nbe-dark-accent-alpha-60: rgba(128, 203, 196, 0.6);
      219 ```
      220
      221 **Step 1:** Apply replacements.
      222 **Step 2:** Visual check — open Explorer (dark theme). Check buttons, tabs, input focus rings, active st
          ates.
      223 **Step 3:** Commit: `feat: adopt MD Teal 200 as dark theme accent`
      224
      225 ---
      226
      227 ### Task 4: Replace dark theme validation and diff tokens
      228
      229 **Files:**
      230 - Modify: `static/css/tokens.css` (lines ~445-505)
      231
      232 **Dark validation text (use MD 300 shades — light, desaturated for dark bg):**
      233 ```css
      234 --nbe-dark-validation-success-text: #81C784;  /* MD Green 300 (already MD!) */
      235 --nbe-dark-validation-error-text: #E57373;    /* MD Red 300 (already MD!) */
      236 --nbe-dark-validation-warning-text: #FFB74D;  /* MD Orange 300 (already MD!) */
      237 --nbe-dark-validation-info-text: #64B5F6;     /* MD Blue 300 (already MD!) */
      238 ```
      239 These are already Material Design — no changes needed for validation text.
      240
      241 **Dark validation backgrounds (use MD 500 base colors with opacity):**
      242 ```css
      243 --nbe-dark-validation-success-bg: rgba(76, 175, 80, 0.1);      /* MD Green 500 (already MD!) */
      244 --nbe-dark-validation-error-bg: rgba(244, 67, 54, 0.1);        /* MD Red 500 (already MD!) */
      245 --nbe-dark-validation-warning-bg: rgba(255, 193, 7, 0.1);      /* MD Amber 500 (already MD!) */
      246 --nbe-dark-validation-info-bg: rgba(33, 150, 243, 0.1);        /* MD Blue 500 — was rgba(56, 139, 253, 0
          .1) */
      247 ```
      248
      249 **Dark validation borders:**
      250 ```css
      251 --nbe-dark-validation-success-border: rgba(76, 175, 80, 0.3);  /* already MD */
      252 --nbe-dark-validation-error-border: rgba(244, 67, 54, 0.3);    /* was rgba(241, 76, 76, 0.3) — use MD Re
          d 500 */
      253 --nbe-dark-validation-warning-border: rgba(255, 193, 7, 0.3);  /* already MD */
      254 --nbe-dark-validation-info-border: rgba(33, 150, 243, 0.3);    /* was rgba(56, 139, 253, 0.3) — use MD B
          lue 500 */
      255 ```
      256
      257 **Diff colors (standardize to MD palette):**
      258 ```css
      259 --nbe-diff-add: #4DB6AC;             /* was #4ec9b0 — MD Teal 300 */
      260 --nbe-diff-add-bg: rgba(76, 175, 80, 0.3);  /* MD Green 500 */
      261 --nbe-diff-remove: #EF5350;          /* was #f14c4c — MD Red 400 */
      262 --nbe-diff-remove-bg: rgba(244, 67, 54, 0.3); /* MD Red 500 */
      263 --nbe-diff-header: #64B5F6;          /* was #569cd6 — MD Blue 300 */
      264 --nbe-diff-hunk: #42A5F5;            /* was #61afef — MD Blue 400 */
      265 --nbe-diff-context: #9E9E9E;         /* was #808080 — MD Grey 500 */
      266
      267 /* GitHub-style overrides */
      268 --nbe-diff-add-text: #81C784;        /* was #3fb950 — MD Green 300 */
      269 --nbe-diff-add-bg: rgba(76, 175, 80, 0.15); /* MD Green 500 */
      270 --nbe-diff-remove-text: #E57373;     /* was #f85149 — MD Red 300 */
      271 --nbe-diff-remove-bg: rgba(244, 67, 54, 0.15); /* MD Red 500 */
      272 --nbe-diff-header-text: #64B5F6;     /* was #58a6ff — MD Blue 300 */
      273 --nbe-diff-hunk-bg: rgba(33, 150, 243, 0.1); /* MD Blue 500 */
      274 ```
      275
      276 **Dark diff:**
      277 ```css
      278 --nbe-dark-diff-added-bg: rgba(76, 175, 80, 0.15);   /* already MD */
      279 --nbe-dark-diff-added-text: #81C784;                   /* already MD Green 300 */
      280 --nbe-dark-diff-removed-bg: rgba(244, 67, 54, 0.15);  /* was rgba(241, 76, 76, 0.15) — use MD Red 500 */
      281 --nbe-dark-diff-removed-text: #E57373;                 /* was #f77 — MD Red 300 */
      282 ```
      283
      284 **Step 1:** Apply only the values that actually change (many are already MD).
      285 **Step 2:** Visual check — open Git page, check diff viewer.
      286 **Step 3:** Commit: `feat: standardize validation and diff colors to MD palette`
      287
      288 ---
      289
      290 ### Task 5: Replace terminal, code, commit, and misc tokens
      291
      292 **Files:**
      293 - Modify: `static/css/tokens.css`
      294
      295 **Terminal (classic terminal colors, keep as-is — these are terminal conventions, not design system colo
          rs):**
      296 No changes. Terminal colors (`#00aa00`, `#eeee00`, etc.) are standard ANSI-inspired colors and should st
          ay.
      297
      298 **Code block:**
      299 ```css
      300 --nbe-code-bg: #263238;          /* was #1e1e1e — MD Blue Grey 900 (richer than pure dark) */
      301 --nbe-code-text: #ECEFF1;        /* was #d4d4d4 — MD Blue Grey 50 */
      302 --nbe-code-border: #37474F;      /* was #3c3c3c — MD Blue Grey 800 */
      303 ```
      304
      305 **Commit button (keep PAN-OS orange — this is a branded/distinctive element):**
      306 No changes. The commit button gradient is an intentional brand element.
      307
      308 **Lock banner:**
      309 ```css
      310 --nbe-lock-banner-bg: linear-gradient(135deg, #FF9800, #F57C00); /* already MD Orange 500/700! */
      311 ```
      312 Already Material Design — no change needed.
      313
      314 **Undo button:**
      315 ```css
      316 --nbe-undo-bg: #546E7A;          /* was #5a6268 — MD Blue Grey 600 */
      317 --nbe-undo-bg-hover: #607D8B;    /* was #6c757d — MD Blue Grey 500 */
      318 --nbe-undo-text: #FFFFFF;        /* no change */
      319 ```
      320
      321 **Disabled state:**
      322 ```css
      323 --nbe-disabled-bg: #616161;      /* was #5a5a5a — MD Grey 700 */
      324 --nbe-disabled-text: #E0E0E0;    /* was #d0d0d0 — MD Grey 300 */
      325 ```
      326
      327 **Syntax highlighting (keep VS Code-inspired — these are code editor conventions):**
      328 No changes. Syntax colors follow editor conventions, not design system colors.
      329
      330 **Step 1:** Apply replacements.
      331 **Step 2:** Visual check — check code blocks, undo button in navbar, disabled buttons.
      332 **Step 3:** Commit: `feat: adopt MD Blue Grey for code blocks and utility tokens`
      333
      334 ---
      335
      336 ## Phase 2: CSS Structure Cleanup
      337
      338 ### Task 6: Create `dark-page.css` with shared Bootstrap dark overrides
      339
      340 **Files:**
      341 - Create: `static/css/dark-page.css`
      342 - Modify: `templates/base.html` (add CSS link + body_class block)
      343
      344 **Step 1:** Create `static/css/dark-page.css` containing shared dark-page rules. Use `.nbe-dark-page` as
           the scoping class — higher specificity than Bootstrap without `!important`:
      345
      346 ```css
      347 /* Shared dark page overrides - eliminates Bootstrap !important fights.
      348    Activated by adding .nbe-dark-page to <body> via {% block body_class %} */
      349
      350 .nbe-dark-page {
      351     background: var(--nbe-dark-bg-primary);
      352 }
      353
      354 .nbe-dark-page .page-container {
      355     background: var(--nbe-dark-bg-primary);
      356 }
      357
      358 .nbe-dark-page .page-sidebar {
      359     background: var(--nbe-dark-bg-primary);
      360     border-right: 1px solid var(--nbe-dark-border-primary);
      361 }
      362
      363 .nbe-dark-page .panel-header {
      364     background: var(--nbe-dark-bg-secondary);
      365     color: var(--nbe-dark-text-primary);
      366     border-bottom: 1px solid var(--nbe-dark-border-primary);
      367 }
      368
      369 .nbe-dark-page .sidebar-section {
      370     border: none;
      371     border-radius: 0;
      372     border-bottom: 1px solid var(--nbe-dark-border-secondary);
      373     margin-bottom: 0;
      374     background: transparent;
      375 }
      376
      377 .nbe-dark-page .sidebar-section-title {
      378     padding: var(--nbe-space-sm) var(--nbe-space-md);
      379     border-bottom: none;
      380     font-size: var(--nbe-font-size-xs-plus);
      381     color: var(--nbe-dark-text-secondary);
      382 }
      383
      384 .nbe-dark-page .sidebar-section-content {
      385     padding: var(--nbe-space-sm) var(--nbe-space-md) var(--nbe-space-md);
      386 }
      387
      388 .nbe-dark-page .sidebar-info-text {
      389     font-size: var(--nbe-font-size-sm);
      390     color: var(--nbe-dark-text-secondary);
      391     margin: 0 0 var(--nbe-space-sm) 0;
      392     line-height: 1.5;
      393 }
      394
      395 .nbe-dark-page .sidebar-info-text:last-child {
      396     margin-bottom: 0;
      397 }
      398
      399 /* Bootstrap form overrides */
      400 .nbe-dark-page .form-control,
      401 .nbe-dark-page .form-select {
      402     background: var(--nbe-dark-bg-tertiary);
      403     border: 1px solid var(--nbe-dark-border-primary);
      404     color: var(--nbe-dark-text-primary);
      405 }
      406
      407 .nbe-dark-page .form-control:focus,
      408 .nbe-dark-page .form-select:focus {
      409     border-color: var(--nbe-dark-accent-primary);
      410     background: var(--nbe-dark-bg-secondary);
      411 }
      412
      413 .nbe-dark-page .form-control::placeholder {
      414     color: var(--nbe-dark-text-muted);
      415 }
      416
      417 .nbe-dark-page .form-label {
      418     color: var(--nbe-dark-text-secondary);
      419 }
      420
      421 .nbe-dark-page .form-check-label {
      422     color: var(--nbe-dark-text-secondary);
      423 }
      424 ```
      425
      426 **Step 2:** Add to `templates/base.html` head (between `forms.css` and `style.css`):
      427 ```html
      428 <link href="{{ url_for('static', filename='css/dark-page.css') }}" rel="stylesheet">
      429 ```
      430
      431 **Step 3:** Add `body_class` block to base.html body tag:
      432 ```html
      433 <body class="u-overflow-x-hidden{% block body_class %}{% endblock %}">
      434 ```
      435
      436 **Step 4:** Commit: `feat: add dark-page.css and body_class block`
      437
      438 ---
      439
      440 ### Task 7: Migrate all 7 dark-themed page CSS files
      441
      442 For each of these 7 files, apply the same pattern:
      443
      444 **Templates to add `{% block body_class %} nbe-dark-page{% endblock %}`:**
      445 - `templates/settings.html`
      446 - `templates/audit_log.html`
      447 - `templates/git.html`
      448 - `templates/backups.html`
      449 - `templates/validate.html`
      450 - `templates/dependencies.html`
      451 - `templates/docs/base_docs.html` (or whichever template extends base.html)
      452
      453 **CSS files to clean up (remove boilerplate now handled by dark-page.css):**
      454 - `static/css/settings.css` — remove lines ~4-45 (shared overrides)
      455 - `static/css/audit_log.css` — remove lines ~7-73
      456 - `static/css/git.css` — remove lines ~7-61
      457 - `static/css/backups.css` — remove lines ~4-85
      458 - `static/css/validate.css` — remove lines ~3-48
      459 - `static/css/dependencies.css` — remove lines ~7-75
      460 - `static/css/docs.css` — remove lines ~7-44
      461
      462 **For each file:**
      463 1. Add body_class block to template
      464 2. Remove shared boilerplate rules from CSS
      465 3. Remove `!important` from remaining rules where `.nbe-dark-page` specificity makes them unnecessary
      466 4. Keep page-specific rules intact
      467 5. Visual check the page
      468
      469 **Step (final):** Commit: `refactor: migrate 7 dark page CSS files to shared dark-page.css`
      470
      471 ---
      472
      473 ### Task 8: Replace hardcoded type-badge colors in dependencies.css
      474
      475 **Files:**
      476 - Modify: `static/css/dependencies.css:381-401`
      477
      478 Replace hardcoded hex colors with existing `--nbe-palette-*` tokens (which are already Material Design 5
          00 shades):
      479
      480 ```css
      481 .type-badge {
      482     font-size: var(--nbe-typography-badge-size);
      483     font-weight: var(--nbe-typography-badge-weight);
      484     padding: 1px var(--nbe-space-xs);
      485     border-radius: var(--nbe-radius-sm);
      486     text-transform: lowercase;
      487     white-space: nowrap;
      488 }
      489
      490 .type-badge--host { background: var(--nbe-palette-green); color: var(--nbe-text-inverse); }
      491 .type-badge--hostgroup { background: var(--nbe-palette-light-green); color: var(--nbe-text-inverse); }
      492 .type-badge--service { background: var(--nbe-palette-blue); color: var(--nbe-text-inverse); }
      493 .type-badge--servicegroup { background: var(--nbe-palette-light-blue); color: var(--nbe-text-inverse); }
      494 .type-badge--contact { background: var(--nbe-palette-orange); color: var(--nbe-text-inverse); }
      495 .type-badge--contactgroup { background: var(--nbe-palette-amber); color: var(--nbe-text-primary); }
      496 .type-badge--command { background: var(--nbe-palette-purple); color: var(--nbe-text-inverse); }
      497 .type-badge--timeperiod { background: var(--nbe-palette-gray); color: var(--nbe-text-inverse); }
      498 .type-badge--hostdependency { background: var(--nbe-palette-brown); color: var(--nbe-text-inverse); }
      499 .type-badge--servicedependency { background: var(--nbe-palette-brown); color: var(--nbe-text-inverse); }
      500 .type-badge--hostescalation { background: var(--nbe-palette-pink); color: var(--nbe-text-inverse); }
      501 .type-badge--serviceescalation { background: var(--nbe-palette-pink); color: var(--nbe-text-inverse); }
      502 ```
      503
      504 **Step 1:** Apply replacements.
      505 **Step 2:** Visual check — open Graph View, check filter sidebar.
      506 **Step 3:** Commit: `refactor: replace hardcoded type-badge colors with palette tokens`
      507
      508 ---
      509
      510 ### Task 9: Add docs prose tokens and replace hardcoded colors in docs.css
      511
      512 **Files:**
      513 - Modify: `static/css/tokens.css` (add after validation borders, ~line 468)
      514 - Modify: `static/css/docs.css`
      515
      516 **Step 1:** Add new tokens to `tokens.css`:
      517 ```css
      518 /* ---- Dark Theme Prose/Docs Colors ---- */
      519 --nbe-dark-prose-text: #B0BEC5;           /* MD Blue Grey 200 (was #b0b0b0) */
      520 --nbe-dark-prose-note-bg: rgba(33, 150, 243, 0.08);   /* MD Blue 500 */
      521 --nbe-dark-prose-note-border: rgba(33, 150, 243, 0.25); /* MD Blue 500 */
      522 --nbe-dark-prose-tip-bg: rgba(76, 175, 80, 0.08);     /* MD Green 500 */
      523 --nbe-dark-prose-tip-border: rgba(76, 175, 80, 0.25); /* MD Green 500 */
      524 --nbe-dark-prose-danger-bg: rgba(244, 67, 54, 0.08);  /* MD Red 500 */
      525 --nbe-dark-prose-danger-border: rgba(244, 67, 54, 0.25); /* MD Red 500 */
      526 --nbe-dark-prose-highlight: rgba(33, 150, 243, 0.25);   /* MD Blue 500 */
      527 --nbe-dark-prose-highlight-fade: rgba(33, 150, 243, 0.1); /* MD Blue 500 */
      528 --nbe-dark-badge-required-bg: rgba(244, 67, 54, 0.15);  /* MD Red 500 */
      529 ```
      530
      531 **Step 2:** Replace in `docs.css`:
      532 - `#b0b0b0` (8 instances) → `var(--nbe-dark-prose-text)`
      533 - `#fff` (line 310) → `var(--nbe-text-inverse)`
      534 - `#81c784` (line 756) → `var(--nbe-dark-validation-success-text)`
      535 - `#e57373` (line 775) → `var(--nbe-dark-validation-error-text)`
      536 - `rgba(239, 68, 68, 0.15)` (line 174) → `var(--nbe-dark-badge-required-bg)`
      537 - `rgba(99, 179, 237, ...)` values → corresponding `--nbe-dark-prose-*` tokens
      538 - `rgba(76, 175, 80, ...)` values → corresponding `--nbe-dark-prose-tip-*` tokens
      539 - `rgba(244, 67, 54, ...)` / `rgba(241, 76, 76, ...)` values → corresponding `--nbe-dark-prose-danger-*`
           tokens
      540
      541 **Step 3:** Visual check — open Docs page, check prose content, callout boxes, highlight animations.
      542 **Step 4:** Commit: `refactor: replace hardcoded docs.css colors with tokens`
      543
      544 ---
      545
      546 ### Task 10: Convert style.css rem values to tokens and fix rgba border
      547
      548 **Files:**
      549 - Modify: `static/style.css`
      550
      551 **Replacements:**
      552 | Line | Current | Replacement |
      553 |------|---------|-------------|
      554 | 21 | `rgba(0, 0, 0, 0.125)` | `var(--nbe-border-light)` |
      555 | 42 | `border-radius: 0.25rem` | `var(--nbe-radius-sm)` |
      556 | 43 | `padding: 1rem` | `var(--nbe-space-lg)` |
      557 | 50 | `padding: 0.125rem 0.25rem` | `2px var(--nbe-space-xs)` |
      558 | 51 | `border-radius: 0.25rem` | `var(--nbe-radius-sm)` |
      559 | 93 | `padding: 0.5rem` | `var(--nbe-space-sm)` |
      560 | 103 | `margin-left: 0.25rem` | `var(--nbe-space-xs)` |
      561 | 109 | `margin-bottom: 0.25rem` | `var(--nbe-space-xs)` |
      562 | 114 | `border-radius: 0.25rem` | `var(--nbe-radius-sm)` |
      563
      564 **Step 1:** Apply replacements.
      565 **Step 2:** Visual check — spot-check cards, code blocks, tables, badges.
      566 **Step 3:** Commit: `refactor: convert style.css rem values to design tokens`
      567
      568 ---
      569
      570 ### Task 11: Update documentation
      571
      572 **Files:**
      573 - Modify: `static/css/CLAUDE.md`
      574
      575 **Update:**
      576 - Add `dark-page.css` to file table: "Shared Bootstrap dark overrides, activated by `.nbe-dark-page` bod
          y class"
      577 - Update "Dark Theme" section: note that dark pages use `{% block body_class %} nbe-dark-page{% endblock
           %}` and shared overrides in `dark-page.css`
      578 - Note that all colors are now Material Design based
      579 - Update load order to include `dark-page.css`
      580
      581 **Commit:** `docs: update CSS CLAUDE.md for MD palette and dark-page.css`
      582
      583 ---
      584
      585 ## Verification
      586
      587 After all tasks:
      588
      589 1. **Visual regression** — Open every page, confirm no layout breakage:
      590    - Explorer, Graph View, Git, Backups, Audit Log, Settings, Validate, Docs (dark pages)
      591    - Inheritance, Bulk Rename, Reorganize (light pages)
      592
      593 2. **Run tests:**
      594    ```bash
      595    python3 -m pytest tests/ -v
      596    ```
      597
      598 3. **Grep for remaining hardcoded colors:**
      599    ```bash
      600    rg '#[0-9a-fA-F]{3,8}' static/css/ --glob '!tokens.css' | grep -v vendor
      601    ```
      602
      603 4. **Count remaining `!important`:**
      604    ```bash
      605    rg '!important' static/css/ | wc -l
      606    ```
      607    Target: significant reduction from 191.
      608
      609 ## Expected Impact
      610
      611 | Metric | Before | After (est.) |
      612 |--------|--------|-------------|
      613 | `!important` declarations | 191 | ~60-70 |
      614 | Hardcoded colors outside tokens.css | 37 | 0-2 |
      615 | Dark-page boilerplate duplication | ~300 LOC across 7 files | 0 |
      616 | Color system consistency | Mixed (custom + MD + VS Code) | Material Design throughout |
      617 | Total CSS lines | ~6,500 | ~6,100         1 # Material Design Palette Overhaul + CSS Cleanup
        2
        3 > **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-tas
          k.
        4
        5 **Goal:** Adopt Material Design colors as the standard palette across the entire interface, replacing th
          e current mixed color system. Simultaneously extract shared dark-page CSS boilerplate to eliminate ~191
          `!important` declarations and ~300 lines of duplication.
        6
        7 **Architecture:** Two phases — (1) replace all color tokens in `tokens.css` with Material Design equival
          ents, maintaining WCAG AA compliance, then (2) extract shared dark-page overrides and clean up hardcoded
           colors in page-specific CSS files.
        8
        9 **Tech Stack:** CSS only (no JS/Python changes). Pure visual refactor — layout and behavior unchanged.
       10
       11 ---
       12
       13 ## Phase 1: Material Design Token Replacement
       14
       15 ### Task 1: Replace primary, semantic, text, background, and border tokens
       16
       17 **Files:**
       18 - Modify: `static/css/tokens.css` (`:root` section, lines 37-100)
       19
       20 Replace the following token values. All replacements maintain WCAG AA (4.5:1 text, 3:1 UI).
       21
       22 **Primary:**
       23 ```css
       24 --nbe-primary: #1976D2;           /* was #006fcc — MD Blue 700 */
       25 --nbe-primary-hover: #1565C0;     /* was #0056a3 — MD Blue 800 */
       26 --nbe-primary-light: #E3F2FD;     /* was #eff6ff — MD Blue 50 */
       27 --nbe-primary-border: #90CAF9;    /* was #90caf9 — MD Blue 200 (already MD!) */
       28 ```
       29
       30 **Success:**
       31 ```css
       32 --nbe-success: #2E7D32;           /* was #1a6b1e — MD Green 800 (5.0:1 on success-light) */
       33 --nbe-success-light: #E8F5E9;     /* was #e8f5e9 — MD Green 50 (already MD!) */
       34 --nbe-success-border: #A5D6A7;    /* was #a5d6a7 — MD Green 200 (already MD!) */
       35 ```
       36
       37 **Warning:**
       38 ```css
       39 --nbe-warning: #E65100;           /* was #b45309 — MD Orange 900 (4.6:1 on warning-light) */
       40 --nbe-warning-light: #FFF3E0;     /* was #fff3e0 — MD Orange 50 (already MD!) */
       41 --nbe-warning-border: #FFCC80;    /* was #ffcc80 — MD Orange 200 (already MD!) */
       42 ```
       43
       44 **Danger:**
       45 ```css
       46 --nbe-danger: #C62828;            /* was #991b1b — MD Red 800 (5.2:1 on danger-light) */
       47 --nbe-danger-light: #FFEBEE;      /* was #ffebee — MD Red 50 (already MD!) */
       48 --nbe-danger-border: #EF9A9A;     /* was #ef9a9a — MD Red 200 (already MD!) */
       49 ```
       50
       51 **Info:**
       52 ```css
       53 --nbe-info: #1565C0;              /* was #0059a8 — MD Blue 800 (4.8:1 on info-light) */
       54 --nbe-info-light: #E3F2FD;        /* was #e3f2fd — MD Blue 50 (already MD!) */
       55 --nbe-info-border: #90CAF9;       /* was #90caf9 — MD Blue 200 (already MD!) */
       56 ```
       57
       58 **Text:**
       59 ```css
       60 --nbe-text-primary: #212121;      /* was #1f2937 — MD Grey 900 */
       61 --nbe-text-secondary: #616161;    /* was #5c6370 — MD Grey 700 (5.1:1 on white) */
       62 --nbe-text-muted: #757575;        /* was #717171 — MD Grey 600 (4.6:1 on white) */
       63 --nbe-text-inverse: #FFFFFF;      /* was #fff — no change */
       64 ```
       65
       66 **Backgrounds:**
       67 ```css
       68 --nbe-bg-page: #FAFAFA;           /* was #f8f9fa — MD Grey 50 */
       69 --nbe-bg-surface: #FFFFFF;        /* was #fff — no change */
       70 --nbe-bg-subtle: #F5F5F5;         /* was #f3f4f6 — MD Grey 100 */
       71 --nbe-bg-hover: #EEEEEE;          /* was #e8eaed — MD Grey 200 */
       72 --nbe-bg-selected: #E3F2FD;       /* was #eff6ff — MD Blue 50 */
       73 --nbe-bg-dark: #455A64;           /* was #3a4d5c — MD Blue Grey 700 */
       74 --nbe-bg-zebra: #F5F5F5;          /* was #f0f4f8 — MD Grey 100 */
       75 --nbe-bg-hover-row: #BBDEFB;      /* was #dbeafe — MD Blue 100 */
       76 --nbe-bg-selected-row: #90CAF9;   /* was #bfdbfe — MD Blue 200 */
       77 --nbe-bg-header: #E0E0E0;         /* was #e5e7eb — MD Grey 300 */
       78 ```
       79
       80 **Borders:**
       81 ```css
       82 --nbe-border: #E0E0E0;            /* was #d9dde3 — MD Grey 300 */
       83 --nbe-border-light: #EEEEEE;      /* was #e5e7eb — MD Grey 200 */
       84 --nbe-border-lighter: #F5F5F5;    /* was #eaeaea — MD Grey 100 */
       85 --nbe-border-focus: #1976D2;      /* was #006fcc — MD Blue 700 (matches primary) */
       86 ```
       87
       88 **Focus ring (update rgba to match new primary):**
       89 ```css
       90 --nbe-focus-ring: 0 0 0 2px rgba(25, 118, 210, 0.25);
       91 --nbe-focus-ring-inset: inset 0 0 0 2px rgba(25, 118, 210, 0.25);
       92 ```
       93
       94 **Interactive elements:**
       95 ```css
       96 --nbe-btn-success-hover: #1B5E20; /* was #145817 — MD Green 900 */
       97 --nbe-hover-darken: #BDBDBD;      /* was #bdbdbd — MD Grey 400 (already MD!) */
       98 --nbe-text-link: #2196F3;         /* was #2196f3 — MD Blue 500 (already MD!) */
       99 ```
      100
      101 **Primary alpha overlays (update base color to new primary):**
      102 ```css
      103 --nbe-primary-alpha-10: rgba(25, 118, 210, 0.1);
      104 --nbe-primary-alpha-15: rgba(25, 118, 210, 0.15);
      105 --nbe-primary-alpha-20: rgba(25, 118, 210, 0.2);
      106 --nbe-primary-alpha-25: rgba(25, 118, 210, 0.25);
      107 --nbe-primary-alpha-40: rgba(25, 118, 210, 0.4);
      108 --nbe-primary-alpha-50: rgba(25, 118, 210, 0.5);
      109 ```
      110
      111 **Step 1:** Apply all replacements above in `tokens.css`.
      112
      113 **Step 2:** Update the legacy color aliases in `templates/base.html` inline `<style>` block (~line 271-2
          74) — these reference `--nbe-success`, `--nbe-danger` etc. via `var()` so they auto-update. Verify they
          still work.
      114
      115 **Step 3:** Visual check — open a light-themed page (Inheritance, Bulk Rename). Verify text readability,
           button colors, status badges.
      116
      117 **Step 4:** Commit: `feat: adopt Material Design palette for light theme tokens`
      118
      119 ---
      120
      121 ### Task 2: Replace light-theme object type badge tokens
      122
      123 **Files:**
      124 - Modify: `static/css/tokens.css` (lines 344-375)
      125
      126 Replace custom pastels with Material Design shade-based colors (50/100 for bg, 900 for text):
      127
      128 ```css
      129 /* Infrastructure (green) - hosts, hostgroups */
      130 --nbe-type-infra-bg: #E8F5E9;         /* was #dcfce7 — MD Green 50 */
      131 --nbe-type-infra-text: #1B5E20;       /* was #166534 — MD Green 900 */
      132 --nbe-type-infra-bg-alt: #C8E6C9;     /* was #d1fae5 — MD Green 100 */
      133 --nbe-type-infra-text-alt: #1B5E20;   /* was #065f46 — MD Green 900 */
      134
      135 /* Monitoring (blue) - services, servicegroups */
      136 --nbe-type-monitor-bg: #E3F2FD;       /* was #dbeafe — MD Blue 50 */
      137 --nbe-type-monitor-text: #0D47A1;     /* was #1e40af — MD Blue 900 */
      138 --nbe-type-monitor-bg-alt: #BBDEFB;   /* was #bfdbfe — MD Blue 100 */
      139 --nbe-type-monitor-text-alt: #0D47A1; /* was #1e3a8a — MD Blue 900 */
      140
      141 /* People (orange) - contacts, contactgroups */
      142 --nbe-type-people-bg: #FFF3E0;        /* was #fed7aa — MD Orange 50 */
      143 --nbe-type-people-text: #BF360C;      /* was #7c2d12 — MD Deep Orange 900 (5.1:1 on Orange 50) */
      144 --nbe-type-people-bg-alt: #FFE0B2;    /* was #fdba74 — MD Orange 100 */
      145 --nbe-type-people-text-alt: #BF360C;  /* was #6b2710 — MD Deep Orange 900 */
      146
      147 /* System (purple) - commands */
      148 --nbe-type-system-bg: #F3E5F5;        /* was #e9d5ff — MD Purple 50 */
      149 --nbe-type-system-text: #4A148C;      /* was #6b21a8 — MD Purple 900 */
      150
      151 /* Neutral (gray) - timeperiods */
      152 --nbe-type-neutral-bg: #ECEFF1;       /* was #e5e7eb — MD Blue Grey 50 */
      153 --nbe-type-neutral-text: #37474F;     /* was #374151 — MD Blue Grey 800 */
      154
      155 /* Dependencies (cyan) - dependencies, escalations */
      156 --nbe-type-deps-bg: #E0F7FA;          /* was #a5f3fc — MD Cyan 50 */
      157 --nbe-type-deps-text: #006064;        /* was #155e75 — MD Cyan 900 */
      158 --nbe-type-deps-bg-alt: #B2EBF2;     /* was #bbf7d0 — MD Cyan 100 */
      159 --nbe-type-deps-text-alt: #006064;    /* was #166534 — MD Cyan 900 */
      160 ```
      161
      162 **Validation/status chips:**
      163 ```css
      164 --nbe-chip-error-bg: #FFEBEE;         /* was #fee2e2 — MD Red 50 */
      165 --nbe-chip-error-text: #B71C1C;       /* was #991b1b — MD Red 900 (5.5:1 on Red 50) */
      166 --nbe-chip-warning-bg: #FFF8E1;       /* was #fef3c7 — MD Yellow 50 */
      167 --nbe-chip-warning-text: #E65100;     /* was #7c2d12 — MD Orange 900 */
      168 --nbe-chip-valid-bg: #E8F5E9;         /* was #dcfce7 — MD Green 50 */
      169 --nbe-chip-valid-text: #1B5E20;       /* was #166534 — MD Green 900 */
      170 ```
      171
      172 **Step 1:** Apply replacements.
      173 **Step 2:** Visual check — open Explorer, check object type badges in the tree and table.
      174 **Step 3:** Commit: `feat: adopt MD palette for object type badges and status chips`
      175
      176 ---
      177
      178 ### Task 3: Replace dark theme accent and UI tokens
      179
      180 **Files:**
      181 - Modify: `static/css/tokens.css` (dark theme section, lines ~390-440)
      182
      183 The dark theme currently uses VS Code-inspired teal (`#4ec9b0`) as the primary accent. Switch to Materia
          l Design Teal 200 (`#80CBC4`) which is close but more consistently Material:
      184
      185 ```css
      186 /* Dark theme accents */
      187 --nbe-dark-accent-primary: #80CBC4;       /* was #4ec9b0 — MD Teal 200 */
      188 --nbe-dark-accent-secondary: #90CAF9;     /* was #569cd6 — MD Blue 200 */
      189 --nbe-dark-accent-warning: #FFE082;       /* was #ffc107 — MD Amber 200 */
      190 --nbe-dark-accent-danger: #EF9A9A;        /* was #f14c4c — MD Red 200 */
      191 --nbe-dark-accent-primary-hover: #B2DFDB; /* was #5ed4ba — MD Teal 100 */
      192 --nbe-dark-accent-danger-hover: #E57373;  /* was #ff6b6b — MD Red 300 */
      193 --nbe-dark-warning-bg: rgba(255, 224, 130, 0.15); /* derived from MD Amber 200 */
      194 ```
      195
      196 **Dark theme buttons (update to match new accent):**
      197 ```css
      198 --nbe-dark-btn-primary-bg: #80CBC4;       /* was #4ec9b0 — MD Teal 200 */
      199 --nbe-dark-btn-primary-hover: #4DB6AC;    /* was #3fb896 — MD Teal 300 */
      200 ```
      201
      202 **Dark theme tabs (update active border):**
      203 ```css
      204 --nbe-dark-tab-border-active: #80CBC4;    /* was #4ec9b0 — MD Teal 200 */
      205 ```
      206
      207 **Dark theme input focus:**
      208 ```css
      209 --nbe-dark-input-focus: #80CBC4;          /* was #4ec9b0 — MD Teal 200 */
      210 ```
      211
      212 **Dark theme accent alpha (update base color):**
      213 ```css
      214 --nbe-dark-accent-alpha-10: rgba(128, 203, 196, 0.1);
      215 --nbe-dark-accent-alpha-15: rgba(128, 203, 196, 0.15);
      216 --nbe-dark-accent-alpha-20: rgba(128, 203, 196, 0.2);
      217 --nbe-dark-accent-alpha-30: rgba(128, 203, 196, 0.3);
      218 --nbe-dark-accent-alpha-60: rgba(128, 203, 196, 0.6);
      219 ```
      220
      221 **Step 1:** Apply replacements.
      222 **Step 2:** Visual check — open Explorer (dark theme). Check buttons, tabs, input focus rings, active st
          ates.
      223 **Step 3:** Commit: `feat: adopt MD Teal 200 as dark theme accent`
      224
      225 ---
      226
      227 ### Task 4: Replace dark theme validation and diff tokens
      228
      229 **Files:**
      230 - Modify: `static/css/tokens.css` (lines ~445-505)
      231
      232 **Dark validation text (use MD 300 shades — light, desaturated for dark bg):**
      233 ```css
      234 --nbe-dark-validation-success-text: #81C784;  /* MD Green 300 (already MD!) */
      235 --nbe-dark-validation-error-text: #E57373;    /* MD Red 300 (already MD!) */
      236 --nbe-dark-validation-warning-text: #FFB74D;  /* MD Orange 300 (already MD!) */
      237 --nbe-dark-validation-info-text: #64B5F6;     /* MD Blue 300 (already MD!) */
      238 ```
      239 These are already Material Design — no changes needed for validation text.
      240
      241 **Dark validation backgrounds (use MD 500 base colors with opacity):**
      242 ```css
      243 --nbe-dark-validation-success-bg: rgba(76, 175, 80, 0.1);      /* MD Green 500 (already MD!) */
      244 --nbe-dark-validation-error-bg: rgba(244, 67, 54, 0.1);        /* MD Red 500 (already MD!) */
      245 --nbe-dark-validation-warning-bg: rgba(255, 193, 7, 0.1);      /* MD Amber 500 (already MD!) */
      246 --nbe-dark-validation-info-bg: rgba(33, 150, 243, 0.1);        /* MD Blue 500 — was rgba(56, 139, 253, 0
          .1) */
      247 ```
      248
      249 **Dark validation borders:**
      250 ```css
      251 --nbe-dark-validation-success-border: rgba(76, 175, 80, 0.3);  /* already MD */
      252 --nbe-dark-validation-error-border: rgba(244, 67, 54, 0.3);    /* was rgba(241, 76, 76, 0.3) — use MD Re
          d 500 */
      253 --nbe-dark-validation-warning-border: rgba(255, 193, 7, 0.3);  /* already MD */
      254 --nbe-dark-validation-info-border: rgba(33, 150, 243, 0.3);    /* was rgba(56, 139, 253, 0.3) — use MD B
          lue 500 */
      255 ```
      256
      257 **Diff colors (standardize to MD palette):**
      258 ```css
      259 --nbe-diff-add: #4DB6AC;             /* was #4ec9b0 — MD Teal 300 */
      260 --nbe-diff-add-bg: rgba(76, 175, 80, 0.3);  /* MD Green 500 */
      261 --nbe-diff-remove: #EF5350;          /* was #f14c4c — MD Red 400 */
      262 --nbe-diff-remove-bg: rgba(244, 67, 54, 0.3); /* MD Red 500 */
      263 --nbe-diff-header: #64B5F6;          /* was #569cd6 — MD Blue 300 */
      264 --nbe-diff-hunk: #42A5F5;            /* was #61afef — MD Blue 400 */
      265 --nbe-diff-context: #9E9E9E;         /* was #808080 — MD Grey 500 */
      266
      267 /* GitHub-style overrides */
      268 --nbe-diff-add-text: #81C784;        /* was #3fb950 — MD Green 300 */
      269 --nbe-diff-add-bg: rgba(76, 175, 80, 0.15); /* MD Green 500 */
      270 --nbe-diff-remove-text: #E57373;     /* was #f85149 — MD Red 300 */
      271 --nbe-diff-remove-bg: rgba(244, 67, 54, 0.15); /* MD Red 500 */
      272 --nbe-diff-header-text: #64B5F6;     /* was #58a6ff — MD Blue 300 */
      273 --nbe-diff-hunk-bg: rgba(33, 150, 243, 0.1); /* MD Blue 500 */
      274 ```
      275
      276 **Dark diff:**
      277 ```css
      278 --nbe-dark-diff-added-bg: rgba(76, 175, 80, 0.15);   /* already MD */
      279 --nbe-dark-diff-added-text: #81C784;                   /* already MD Green 300 */
      280 --nbe-dark-diff-removed-bg: rgba(244, 67, 54, 0.15);  /* was rgba(241, 76, 76, 0.15) — use MD Red 500 */
      281 --nbe-dark-diff-removed-text: #E57373;                 /* was #f77 — MD Red 300 */
      282 ```
      283
      284 **Step 1:** Apply only the values that actually change (many are already MD).
      285 **Step 2:** Visual check — open Git page, check diff viewer.
      286 **Step 3:** Commit: `feat: standardize validation and diff colors to MD palette`
      287
      288 ---
      289
      290 ### Task 5: Replace terminal, code, commit, and misc tokens
      291
      292 **Files:**
      293 - Modify: `static/css/tokens.css`
      294
      295 **Terminal (classic terminal colors, keep as-is — these are terminal conventions, not design system colo
          rs):**
      296 No changes. Terminal colors (`#00aa00`, `#eeee00`, etc.) are standard ANSI-inspired colors and should st
          ay.
      297
      298 **Code block:**
      299 ```css
      300 --nbe-code-bg: #263238;          /* was #1e1e1e — MD Blue Grey 900 (richer than pure dark) */
      301 --nbe-code-text: #ECEFF1;        /* was #d4d4d4 — MD Blue Grey 50 */
      302 --nbe-code-border: #37474F;      /* was #3c3c3c — MD Blue Grey 800 */
      303 ```
      304
      305 **Commit button (keep PAN-OS orange — this is a branded/distinctive element):**
      306 No changes. The commit button gradient is an intentional brand element.
      307
      308 **Lock banner:**
      309 ```css
      310 --nbe-lock-banner-bg: linear-gradient(135deg, #FF9800, #F57C00); /* already MD Orange 500/700! */
      311 ```
      312 Already Material Design — no change needed.
      313
      314 **Undo button:**
      315 ```css
      316 --nbe-undo-bg: #546E7A;          /* was #5a6268 — MD Blue Grey 600 */
      317 --nbe-undo-bg-hover: #607D8B;    /* was #6c757d — MD Blue Grey 500 */
      318 --nbe-undo-text: #FFFFFF;        /* no change */
      319 ```
      320
      321 **Disabled state:**
      322 ```css
      323 --nbe-disabled-bg: #616161;      /* was #5a5a5a — MD Grey 700 */
      324 --nbe-disabled-text: #E0E0E0;    /* was #d0d0d0 — MD Grey 300 */
      325 ```
      326
      327 **Syntax highlighting (keep VS Code-inspired — these are code editor conventions):**
      328 No changes. Syntax colors follow editor conventions, not design system colors.
      329
      330 **Step 1:** Apply replacements.
      331 **Step 2:** Visual check — check code blocks, undo button in navbar, disabled buttons.
      332 **Step 3:** Commit: `feat: adopt MD Blue Grey for code blocks and utility tokens`
      333
      334 ---
      335
      336 ## Phase 2: CSS Structure Cleanup
      337
      338 ### Task 6: Create `dark-page.css` with shared Bootstrap dark overrides
      339
      340 **Files:**
      341 - Create: `static/css/dark-page.css`
      342 - Modify: `templates/base.html` (add CSS link + body_class block)
      343
      344 **Step 1:** Create `static/css/dark-page.css` containing shared dark-page rules. Use `.nbe-dark-page` as
           the scoping class — higher specificity than Bootstrap without `!important`:
      345
      346 ```css
      347 /* Shared dark page overrides - eliminates Bootstrap !important fights.
      348    Activated by adding .nbe-dark-page to <body> via {% block body_class %} */
      349
      350 .nbe-dark-page {
      351     background: var(--nbe-dark-bg-primary);
      352 }
      353
      354 .nbe-dark-page .page-container {
      355     background: var(--nbe-dark-bg-primary);
      356 }
      357
      358 .nbe-dark-page .page-sidebar {
      359     background: var(--nbe-dark-bg-primary);
      360     border-right: 1px solid var(--nbe-dark-border-primary);
      361 }
      362
      363 .nbe-dark-page .panel-header {
      364     background: var(--nbe-dark-bg-secondary);
      365     color: var(--nbe-dark-text-primary);
      366     border-bottom: 1px solid var(--nbe-dark-border-primary);
      367 }
      368
      369 .nbe-dark-page .sidebar-section {
      370     border: none;
      371     border-radius: 0;
      372     border-bottom: 1px solid var(--nbe-dark-border-secondary);
      373     margin-bottom: 0;
      374     background: transparent;
      375 }
      376
      377 .nbe-dark-page .sidebar-section-title {
      378     padding: var(--nbe-space-sm) var(--nbe-space-md);
      379     border-bottom: none;
      380     font-size: var(--nbe-font-size-xs-plus);
      381     color: var(--nbe-dark-text-secondary);
      382 }
      383
      384 .nbe-dark-page .sidebar-section-content {
      385     padding: var(--nbe-space-sm) var(--nbe-space-md) var(--nbe-space-md);
      386 }
      387
      388 .nbe-dark-page .sidebar-info-text {
      389     font-size: var(--nbe-font-size-sm);
      390     color: var(--nbe-dark-text-secondary);
      391     margin: 0 0 var(--nbe-space-sm) 0;
      392     line-height: 1.5;
      393 }
      394
      395 .nbe-dark-page .sidebar-info-text:last-child {
      396     margin-bottom: 0;
      397 }
      398
      399 /* Bootstrap form overrides */
      400 .nbe-dark-page .form-control,
      401 .nbe-dark-page .form-select {
      402     background: var(--nbe-dark-bg-tertiary);
      403     border: 1px solid var(--nbe-dark-border-primary);
      404     color: var(--nbe-dark-text-primary);
      405 }
      406
      407 .nbe-dark-page .form-control:focus,
      408 .nbe-dark-page .form-select:focus {
      409     border-color: var(--nbe-dark-accent-primary);
      410     background: var(--nbe-dark-bg-secondary);
      411 }
      412
      413 .nbe-dark-page .form-control::placeholder {
      414     color: var(--nbe-dark-text-muted);
      415 }
      416
      417 .nbe-dark-page .form-label {
      418     color: var(--nbe-dark-text-secondary);
      419 }
      420
      421 .nbe-dark-page .form-check-label {
      422     color: var(--nbe-dark-text-secondary);
      423 }
      424 ```
      425
      426 **Step 2:** Add to `templates/base.html` head (between `forms.css` and `style.css`):
      427 ```html
      428 <link href="{{ url_for('static', filename='css/dark-page.css') }}" rel="stylesheet">
      429 ```
      430
      431 **Step 3:** Add `body_class` block to base.html body tag:
      432 ```html
      433 <body class="u-overflow-x-hidden{% block body_class %}{% endblock %}">
      434 ```
      435
      436 **Step 4:** Commit: `feat: add dark-page.css and body_class block`
      437
      438 ---
      439
      440 ### Task 7: Migrate all 7 dark-themed page CSS files
      441
      442 For each of these 7 files, apply the same pattern:
      443
      444 **Templates to add `{% block body_class %} nbe-dark-page{% endblock %}`:**
      445 - `templates/settings.html`
      446 - `templates/audit_log.html`
      447 - `templates/git.html`
      448 - `templates/backups.html`
      449 - `templates/validate.html`
      450 - `templates/dependencies.html`
      451 - `templates/docs/base_docs.html` (or whichever template extends base.html)
      452
      453 **CSS files to clean up (remove boilerplate now handled by dark-page.css):**
      454 - `static/css/settings.css` — remove lines ~4-45 (shared overrides)
      455 - `static/css/audit_log.css` — remove lines ~7-73
      456 - `static/css/git.css` — remove lines ~7-61
      457 - `static/css/backups.css` — remove lines ~4-85
      458 - `static/css/validate.css` — remove lines ~3-48
      459 - `static/css/dependencies.css` — remove lines ~7-75
      460 - `static/css/docs.css` — remove lines ~7-44
      461
      462 **For each file:**
      463 1. Add body_class block to template
      464 2. Remove shared boilerplate rules from CSS
      465 3. Remove `!important` from remaining rules where `.nbe-dark-page` specificity makes them unnecessary
      466 4. Keep page-specific rules intact
      467 5. Visual check the page
      468
      469 **Step (final):** Commit: `refactor: migrate 7 dark page CSS files to shared dark-page.css`
      470
      471 ---
      472
      473 ### Task 8: Replace hardcoded type-badge colors in dependencies.css
      474
      475 **Files:**
      476 - Modify: `static/css/dependencies.css:381-401`
      477
      478 Replace hardcoded hex colors with existing `--nbe-palette-*` tokens (which are already Material Design 5
          00 shades):
      479
      480 ```css
      481 .type-badge {
      482     font-size: var(--nbe-typography-badge-size);
      483     font-weight: var(--nbe-typography-badge-weight);
      484     padding: 1px var(--nbe-space-xs);
      485     border-radius: var(--nbe-radius-sm);
      486     text-transform: lowercase;
      487     white-space: nowrap;
      488 }
      489
      490 .type-badge--host { background: var(--nbe-palette-green); color: var(--nbe-text-inverse); }
      491 .type-badge--hostgroup { background: var(--nbe-palette-light-green); color: var(--nbe-text-inverse); }
      492 .type-badge--service { background: var(--nbe-palette-blue); color: var(--nbe-text-inverse); }
      493 .type-badge--servicegroup { background: var(--nbe-palette-light-blue); color: var(--nbe-text-inverse); }
      494 .type-badge--contact { background: var(--nbe-palette-orange); color: var(--nbe-text-inverse); }
      495 .type-badge--contactgroup { background: var(--nbe-palette-amber); color: var(--nbe-text-primary); }
      496 .type-badge--command { background: var(--nbe-palette-purple); color: var(--nbe-text-inverse); }
      497 .type-badge--timeperiod { background: var(--nbe-palette-gray); color: var(--nbe-text-inverse); }
      498 .type-badge--hostdependency { background: var(--nbe-palette-brown); color: var(--nbe-text-inverse); }
      499 .type-badge--servicedependency { background: var(--nbe-palette-brown); color: var(--nbe-text-inverse); }
      500 .type-badge--hostescalation { background: var(--nbe-palette-pink); color: var(--nbe-text-inverse); }
      501 .type-badge--serviceescalation { background: var(--nbe-palette-pink); color: var(--nbe-text-inverse); }
      502 ```
      503
      504 **Step 1:** Apply replacements.
      505 **Step 2:** Visual check — open Graph View, check filter sidebar.
      506 **Step 3:** Commit: `refactor: replace hardcoded type-badge colors with palette tokens`
      507
      508 ---
      509
      510 ### Task 9: Add docs prose tokens and replace hardcoded colors in docs.css
      511
      512 **Files:**
      513 - Modify: `static/css/tokens.css` (add after validation borders, ~line 468)
      514 - Modify: `static/css/docs.css`
      515
      516 **Step 1:** Add new tokens to `tokens.css`:
      517 ```css
      518 /* ---- Dark Theme Prose/Docs Colors ---- */
      519 --nbe-dark-prose-text: #B0BEC5;           /* MD Blue Grey 200 (was #b0b0b0) */
      520 --nbe-dark-prose-note-bg: rgba(33, 150, 243, 0.08);   /* MD Blue 500 */
      521 --nbe-dark-prose-note-border: rgba(33, 150, 243, 0.25); /* MD Blue 500 */
      522 --nbe-dark-prose-tip-bg: rgba(76, 175, 80, 0.08);     /* MD Green 500 */
      523 --nbe-dark-prose-tip-border: rgba(76, 175, 80, 0.25); /* MD Green 500 */
      524 --nbe-dark-prose-danger-bg: rgba(244, 67, 54, 0.08);  /* MD Red 500 */
      525 --nbe-dark-prose-danger-border: rgba(244, 67, 54, 0.25); /* MD Red 500 */
      526 --nbe-dark-prose-highlight: rgba(33, 150, 243, 0.25);   /* MD Blue 500 */
      527 --nbe-dark-prose-highlight-fade: rgba(33, 150, 243, 0.1); /* MD Blue 500 */
      528 --nbe-dark-badge-required-bg: rgba(244, 67, 54, 0.15);  /* MD Red 500 */
      529 ```
      530
      531 **Step 2:** Replace in `docs.css`:
      532 - `#b0b0b0` (8 instances) → `var(--nbe-dark-prose-text)`
      533 - `#fff` (line 310) → `var(--nbe-text-inverse)`
      534 - `#81c784` (line 756) → `var(--nbe-dark-validation-success-text)`
      535 - `#e57373` (line 775) → `var(--nbe-dark-validation-error-text)`
      536 - `rgba(239, 68, 68, 0.15)` (line 174) → `var(--nbe-dark-badge-required-bg)`
      537 - `rgba(99, 179, 237, ...)` values → corresponding `--nbe-dark-prose-*` tokens
      538 - `rgba(76, 175, 80, ...)` values → corresponding `--nbe-dark-prose-tip-*` tokens
      539 - `rgba(244, 67, 54, ...)` / `rgba(241, 76, 76, ...)` values → corresponding `--nbe-dark-prose-danger-*`
           tokens
      540
      541 **Step 3:** Visual check — open Docs page, check prose content, callout boxes, highlight animations.
      542 **Step 4:** Commit: `refactor: replace hardcoded docs.css colors with tokens`
      543
      544 ---
      545
      546 ### Task 10: Convert style.css rem values to tokens and fix rgba border
      547
      548 **Files:**
      549 - Modify: `static/style.css`
      550
      551 **Replacements:**
      552 | Line | Current | Replacement |
      553 |------|---------|-------------|
      554 | 21 | `rgba(0, 0, 0, 0.125)` | `var(--nbe-border-light)` |
      555 | 42 | `border-radius: 0.25rem` | `var(--nbe-radius-sm)` |
      556 | 43 | `padding: 1rem` | `var(--nbe-space-lg)` |
      557 | 50 | `padding: 0.125rem 0.25rem` | `2px var(--nbe-space-xs)` |
      558 | 51 | `border-radius: 0.25rem` | `var(--nbe-radius-sm)` |
      559 | 93 | `padding: 0.5rem` | `var(--nbe-space-sm)` |
      560 | 103 | `margin-left: 0.25rem` | `var(--nbe-space-xs)` |
      561 | 109 | `margin-bottom: 0.25rem` | `var(--nbe-space-xs)` |
      562 | 114 | `border-radius: 0.25rem` | `var(--nbe-radius-sm)` |
      563
      564 **Step 1:** Apply replacements.
      565 **Step 2:** Visual check — spot-check cards, code blocks, tables, badges.
      566 **Step 3:** Commit: `refactor: convert style.css rem values to design tokens`
      567
      568 ---
      569
      570 ### Task 11: Update documentation
      571
      572 **Files:**
      573 - Modify: `static/css/CLAUDE.md`
      574
      575 **Update:**
      576 - Add `dark-page.css` to file table: "Shared Bootstrap dark overrides, activated by `.nbe-dark-page` bod
          y class"
      577 - Update "Dark Theme" section: note that dark pages use `{% block body_class %} nbe-dark-page{% endblock
           %}` and shared overrides in `dark-page.css`
      578 - Note that all colors are now Material Design based
      579 - Update load order to include `dark-page.css`
      580
      581 **Commit:** `docs: update CSS CLAUDE.md for MD palette and dark-page.css`
      582
      583 ---
      584
      585 ## Verification
      586
      587 After all tasks:
      588
      589 1. **Visual regression** — Open every page, confirm no layout breakage:
      590    - Explorer, Graph View, Git, Backups, Audit Log, Settings, Validate, Docs (dark pages)
      591    - Inheritance, Bulk Rename, Reorganize (light pages)
      592
      593 2. **Run tests:**
      594    ```bash
      595    python3 -m pytest tests/ -v
      596    ```
      597
      598 3. **Grep for remaining hardcoded colors:**
      599    ```bash
      600    rg '#[0-9a-fA-F]{3,8}' static/css/ --glob '!tokens.css' | grep -v vendor
      601    ```
      602
      603 4. **Count remaining `!important`:**
      604    ```bash
      605    rg '!important' static/css/ | wc -l
      606    ```
      607    Target: significant reduction from 191.
      608
      609 ## Expected Impact
      610
      611 | Metric | Before | After (est.) |
      612 |--------|--------|-------------|
      613 | `!important` declarations | 191 | ~60-70 |
      614 | Hardcoded colors outside tokens.css | 37 | 0-2 |
      615 | Dark-page boilerplate duplication | ~300 LOC across 7 files | 0 |
      616 | Color system consistency | Mixed (custom + MD + VS Code) | Material Design throughout |
      617 | Total CSS lines | ~6,500 | ~6,100 ||
