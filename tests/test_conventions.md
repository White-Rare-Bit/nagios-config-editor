# Convention Compliance Test Plan

This test plan validates that all conventions documented in CLAUDE.md are being followed throughout the codebase.

---

## 1. Naming Conventions

### 1.1 Python: snake_case

**Files to check:** All `.py` files in root and `routes/`

**Test criteria:**
- [ ] Function names use snake_case
- [ ] Variable names use snake_case
- [ ] Method names use snake_case
- [ ] Module-level constants use UPPER_SNAKE_CASE

**Automated check:**
```bash
# Find potential camelCase function/method definitions
grep -rn "def [a-z]*[A-Z]" *.py routes/*.py

# Find potential camelCase variable assignments (heuristic)
grep -rn "^[[:space:]]*[a-z]*[A-Z][a-zA-Z]* =" *.py routes/*.py
```

**Exclusions:**
- Class names (should be PascalCase)
- Imported names from external libraries

---

### 1.2 JavaScript: camelCase

**Files to check:** All `.js` files in `static/js/` and `static/`

**Test criteria:**
- [ ] Function names use camelCase
- [ ] Variable names use camelCase
- [ ] Method names use camelCase
- [ ] Constants may use UPPER_SNAKE_CASE

**Automated check:**
```bash
# Find potential snake_case function definitions
grep -rn "function [a-z]*_[a-z]" static/js/*.js static/js/**/*.js static/app.js

# Find potential snake_case variable declarations
grep -rn "\(let\|const\|var\) [a-z]*_[a-z]" static/js/*.js static/js/**/*.js static/app.js
```

**Exclusions:**
- API response field names (these come from Python backend as snake_case)
- DOM data attributes

---

### 1.3 CSS Classes: kebab-case

**Files to check:** All `.css` files in `static/css/` and `static/style.css`

**Test criteria:**
- [ ] All custom class names use kebab-case
- [ ] No camelCase or snake_case class names

**Automated check:**
```bash
# Find potential non-kebab-case class definitions
grep -rn "\.[a-z]*[A-Z]" static/css/*.css static/style.css
grep -rn "\.[a-z]*_[a-z]" static/css/*.css static/style.css
```

**Exclusions:**
- Bootstrap classes (external library)
- FontAwesome classes (external library)

---

### 1.4 CSS Variables: `--nbe-*` Namespace

**Files to check:** All `.css` files

**Test criteria:**
- [ ] All custom CSS variables start with `--nbe-`
- [ ] No non-namespaced custom properties (except `:root` bootstrap overrides)

**Automated check:**
```bash
# Find CSS variable definitions not using --nbe- prefix
grep -rn "^\s*--[^n]" static/css/*.css static/style.css
grep -rn "^\s*--n[^b]" static/css/*.css static/style.css
grep -rn "^\s*--nb[^e]" static/css/*.css static/style.css
```

**Exclusions:**
- Bootstrap CSS variable overrides (e.g., `--bs-*`)

---

### 1.5 API ↔ Frontend Field Names

**Test criteria:**
- [ ] Python API responses use snake_case keys
- [ ] JavaScript preserves snake_case when sending to API
- [ ] JavaScript does NOT convert to camelCase for API calls

**Manual inspection points:**
- Check `routes/*.py` for JSON response structure
- Check `static/js/api-client.js` for request formatting
- Check explorer modules for API payload construction

---

## 2. State Storage Conventions

### 2.1 Explorer State: `Explorer.state`

**Files to check:** `static/js/explorer/*.js`

**Test criteria:**
- [ ] All explorer state stored in `Explorer.state` object
- [ ] No direct global variables for explorer state
- [ ] State mutations go through proper channels

**Automated check:**
```bash
# Find potential global state outside Explorer.state
grep -rn "^let \|^var " static/js/explorer/*.js
grep -rn "window\.[a-zA-Z]*State" static/js/explorer/*.js
```

---

### 2.2 Session Storage: localStorage Keys

**Files to check:** `static/js/base.js`, `static/app.js`

**Test criteria:**
- [ ] Session ID stored as `nagios_session_id`
- [ ] User name stored as `nagios_user_name`
- [ ] No other localStorage keys for session data

**Automated check:**
```bash
# Find all localStorage usages
grep -rn "localStorage\." static/js/*.js static/js/**/*.js static/app.js
```

---

### 2.3 Lock State: `baseState` and `window.isEditingLocked`

**Files to check:** `static/js/base.js`

**Test criteria:**
- [ ] Lock state maintained in `baseState`
- [ ] `window.isEditingLocked` synchronized with `baseState`
- [ ] Other modules read from `window.isEditingLocked`

**Manual inspection required.**

---

## 3. Code Patterns

### 3.1 OperationResult Pattern

**Files to check:** All service modules (`nagios_service.py`, `staging_manager.py`, etc.)

**Test criteria:**
- [ ] Service methods return `OperationResult`
- [ ] `OperationResult` has `success`, `error`, `data` attributes
- [ ] Routes check `result.success` before using `result.data`

**Automated check:**
```bash
# Find service method returns
grep -rn "return OperationResult" *.py

# Find potential non-OperationResult returns in service modules
grep -rn "^    return {" nagios_service.py staging_manager.py
```

---

### 3.2 Event Delegation: `data-action` Attributes

**Files to check:** `templates/*.html`, `static/js/base.js`

**Test criteria:**
- [ ] Click handlers use `data-action` attributes
- [ ] Actions registered in `actionHandlers` map in base.js
- [ ] No inline `onclick` attributes

**Automated check:**
```bash
# Find inline onclick handlers (violation)
grep -rn "onclick=" templates/*.html

# Find data-action usages
grep -rn "data-action=" templates/*.html
```

---

### 3.3 ApiClient Pattern

**Files to check:** All JavaScript files

**Test criteria:**
- [ ] API calls use `ApiClient.get()` or `ApiClient.post()`
- [ ] No direct `fetch()` calls for API endpoints
- [ ] Results checked with `result.success`

**Automated check:**
```bash
# Find direct fetch calls (potential violations)
grep -rn "fetch('/api" static/js/*.js static/js/**/*.js

# Find ApiClient usages
grep -rn "ApiClient\." static/js/*.js static/js/**/*.js
```

---

### 3.4 Design Tokens Usage

**Files to check:** All `.css` files

**Test criteria:**
- [ ] Colors use `var(--nbe-*)` tokens
- [ ] Spacing uses `var(--nbe-space-*)` tokens
- [ ] No hard-coded hex colors (except in token definitions)
- [ ] No hard-coded pixel values for spacing (except in token definitions)

**Automated check:**
```bash
# Find hard-coded colors (potential violations)
grep -rn "#[0-9a-fA-F]\{3,6\}" static/css/*.css | grep -v "tokens.css"

# Find hard-coded spacing (heuristic - padding/margin with px)
grep -rn "padding:.*[0-9]px" static/css/*.css | grep -v "tokens.css"
grep -rn "margin:.*[0-9]px" static/css/*.css | grep -v "tokens.css"
```

---

### 3.5 Template Inheritance

**Files to check:** All `.html` files in `templates/`

**Test criteria:**
- [ ] All pages extend `base.html`
- [ ] Pages use blocks: `title`, `extra_css`, `content`, `scripts`
- [ ] No standalone HTML pages without base extension

**Automated check:**
```bash
# Find templates not extending base.html
grep -L "extends.*base.html" templates/*.html | grep -v "base.html"
```

---

### 3.6 Thread Safety: multiprocessing.Lock

**Files to check:** `nagios_service.py`, `git_service.py`, `staging_manager.py`

**Test criteria:**
- [ ] Services use `multiprocessing.Lock` (not `threading.Lock`)
- [ ] All mutation methods acquire lock before modifying state
- [ ] Lock released properly (using `with` statement)

**Automated check:**
```bash
# Find lock imports
grep -rn "from multiprocessing import.*Lock" *.py
grep -rn "from threading import.*Lock" *.py

# Find lock usage patterns
grep -rn "with self._lock:" *.py
```

---

### 3.7 HTTP Status Codes

**Files to check:** All `routes/*.py` files

**Test criteria:**
- [ ] 200: Success responses
- [ ] 400: Invalid input
- [ ] 404: Not found
- [ ] 409: Staging conflicts
- [ ] 423: Locked
- [ ] 500: Internal error

**Automated check:**
```bash
# Find all status code usages
grep -rn ", [0-9][0-9][0-9])" routes/*.py
```

---

## 4. Reference Field Sync

**Files to check:**
1. `nagios_model.py:REFERENCE_FIELDS`
2. `static/js/explorer/object-editor.js:ATTR_REFERENCE_MAP`
3. `static/js/explorer/main.js:referenceAttrs`
4. `static/app.js:loadCenterReferences:referenceFields`

**Test criteria:**
- [ ] All four locations define the same reference fields
- [ ] No field missing from any location
- [ ] No extra fields in any location

**Manual inspection required - compare the four definitions.**

---

## 5. Global Functions Location

### 5.1 app.js Functions

**Test criteria:**
- [ ] `escapeHtml()` defined in app.js
- [ ] `formatDate()` defined in app.js
- [ ] `debounce()` defined in app.js
- [ ] `escapeRegex()` defined in app.js
- [ ] `copyToClipboard()` defined in app.js
- [ ] `setButtonLoading()` defined in app.js

### 5.2 base.js Functions

**Test criteria:**
- [ ] `showToast()` defined in base.js
- [ ] `showConfirmDialog()` defined in base.js
- [ ] `getSessionId()` defined in base.js
- [ ] `getUserIdentity()` defined in base.js
- [ ] `getStagingHeaders()` defined in base.js

---

## 6. Keyboard Shortcuts

### 6.1 Global Shortcuts in handleGlobalKeydown

**File to check:** `static/app.js`

**Test criteria:**
- [ ] Escape handled in `handleGlobalKeydown`
- [ ] Ctrl+Z handled in `handleGlobalKeydown`
- [ ] `?` handled in `handleGlobalKeydown`
- [ ] No keyboard handlers defined elsewhere for these keys

### 6.2 Explorer Shortcuts

**File to check:** `static/js/explorer/main.js` or relevant explorer module

**Test criteria:**
- [ ] Space (preview) implemented
- [ ] M (move) implemented
- [ ] Delete implemented
- [ ] Ctrl+Click (toggle selection) implemented
- [ ] Shift+Click (range selection) implemented

---

## 7. Service Access Pattern

**Files to check:** All `routes/*.py` files

**Test criteria:**
- [ ] Services accessed via helper functions, not directly from `current_app`
- [ ] Use `get_service()` for NagiosService
- [ ] Use `get_staging_manager()` for StagingManager
- [ ] Use `get_backup_manager()` for BackupManager
- [ ] Use `get_server_config()` for server config

**Automated check:**
```bash
# Find direct current_app.extensions access (potential violation)
grep -rn "current_app.extensions\[" routes/*.py

# Find proper helper usage
grep -rn "get_service()" routes/*.py
grep -rn "get_staging_manager()" routes/*.py
```

---

## 8. Backup on Mutation

**Files to check:** All routes that perform mutations

**Test criteria:**
- [ ] All mutating operations create backup first
- [ ] Backup created via `bm.create_backup("pre_operation_name")`

**Manual inspection of mutation routes required.**

---

## Execution Checklist

| Section | Status | Notes |
|---------|--------|-------|
| 1.1 Python snake_case | ⬜ | |
| 1.2 JavaScript camelCase | ⬜ | |
| 1.3 CSS kebab-case | ⬜ | |
| 1.4 CSS --nbe-* namespace | ⬜ | |
| 1.5 API field names | ⬜ | |
| 2.1 Explorer.state | ⬜ | |
| 2.2 localStorage keys | ⬜ | |
| 2.3 Lock state sync | ⬜ | |
| 3.1 OperationResult | ⬜ | |
| 3.2 data-action events | ⬜ | |
| 3.3 ApiClient pattern | ⬜ | |
| 3.4 Design tokens | ⬜ | |
| 3.5 Template inheritance | ⬜ | |
| 3.6 multiprocessing.Lock | ⬜ | |
| 3.7 HTTP status codes | ⬜ | |
| 4 Reference field sync | ⬜ | |
| 5.1 app.js functions | ⬜ | |
| 5.2 base.js functions | ⬜ | |
| 6.1 Global shortcuts | ⬜ | |
| 6.2 Explorer shortcuts | ⬜ | |
| 7 Service access | ⬜ | |
| 8 Backup on mutation | ⬜ | |
