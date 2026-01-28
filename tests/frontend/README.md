# Frontend JavaScript Tests

Comprehensive test suite for Nagios Bulk Editor frontend JavaScript code.

## Test Coverage

### Core Utilities (`app.test.js`)
- **escapeHtml**: HTML special character escaping, XSS prevention
- **escapeRegex**: Regex special character escaping for search patterns
- **debounce**: Function debouncing for search inputs
- **formatDate**: Relative time formatting ("2 hours ago", "yesterday")
- **copyToClipboard**: Clipboard API with fallback
- **setButtonLoading**: Button loading state management

### API Client (`api-client.test.js`)
- **POST/GET/DELETE requests**: HTTP method handlers
- **Error handling**: Network errors, HTTP errors, timeout handling
- **Staging headers**: Automatic X-Session-Id injection
- **Silent mode**: Optional toast suppression
- **Timeout support**: AbortController integration (partially tested)
- **Response parsing**: JSON parsing with fallback

### Base JavaScript (`base.test.js`)
- **Session management**: getSessionId, getUserIdentity, setUserIdentity
- **Toast notifications**: Message filtering, HTML escaping, auto-dismissal
- **Confirmation dialogs**: Promise-based, keyboard shortcuts, overlay clicks
- **Identity management**: localStorage persistence

### UI Utilities (`ui-utils.test.js`)
- **Icon helpers**: getObjectTypeIcon, getIssueIcon, icon rendering
- **Badge updates**: Count display, hide-when-zero behavior
- **Debounce/Throttle**: Function rate limiting
- **Keyboard utilities**: isEscapeKey, isEnterKey, isModifierKey
- **Tab switching**: Generic tab switcher

### Explorer State Management (`state-management.test.js`)
- **Stable key operations**: generateStableKey, findObjectByKey, getObjectKeyByIndex
- **Pending edit operations**: get/set/delete pending edits by index, key, or object
- **Deletion marking**: mark/unmark/check deletion status
- **Selection management**: isSelectedByIndex
- **Edge cases**: null/undefined handling, idempotent operations

### Data Loading (`data-loading.test.js`)
- **loadObjects**: Concurrent API calls for objects, files, folders
- **Path utilities**: toDisplayPath, toAbsolutePath, getConfigRootName
- **Staging headers**: getStagingHeaders with session ID
- **Cache busting**: Query parameter timestamp
- **Error handling**: API failures, empty responses
- **Roundtrip conversions**: Path conversion integrity

### Dialogs (`dialogs.test.js`)
- **Delete dialog**: Single/multiple object confirmation
- **Rename dialog**: Input validation, cancel handling
- **Move dialog**: File selection, dialog cleanup
- **Clone dialog**: Name generation, target file handling
- **Display names**: Host, service, generic object formatting
- **Edge cases**: HTML in names, empty inputs, long names

## Running Tests

### Install dependencies
```bash
npm install
```

### Run all tests
```bash
npm test
```

### Run tests in watch mode
```bash
npm run test:watch
```

### Run with verbose output
```bash
npm run test:verbose
```

### View coverage report
```bash
npm test
# Coverage report is displayed in terminal
# HTML report generated in coverage/ directory
```

## Test Structure

```
tests/frontend/
├── setup.js                    # Global test setup and mocks
├── app.test.js                 # Tests for app.js utilities (58 tests)
├── api-client.test.js          # Tests for ApiClient (38 tests)
├── base.test.js                # Tests for base.js (74 tests)
├── ui-utils.test.js            # Tests for Explorer UI utilities (44 tests)
├── state-management.test.js    # Tests for Explorer state management (46 tests)
├── data-loading.test.js        # Tests for data loading and paths (21 tests)
├── dialogs.test.js             # Tests for Explorer dialogs (28 tests)
└── README.md                   # This file
```

**Total: 231 passing tests across 7 test files**

## Mocks and Setup

### Global Mocks (setup.js)
- **localStorage**: In-memory key-value store
- **fetch**: Jest mock function
- **navigator.clipboard**: Clipboard API mock
- **bootstrap**: Bootstrap modal/tooltip mocks

### Helper Functions
- **createMockElement**: Create DOM elements with attributes
- **mockFetchSuccess**: Mock successful fetch response
- **mockFetchError**: Mock HTTP error response
- **mockFetchNetworkError**: Mock network failure

## Writing New Tests

### Example: Testing a utility function
```javascript
describe('myUtility', () => {
    beforeEach(() => {
        // Setup
        global.myUtility = function(input) {
            return input.toUpperCase();
        };
    });

    test('converts to uppercase', () => {
        expect(myUtility('hello')).toBe('HELLO');
    });
});
```

### Example: Testing async API calls
```javascript
test('makes API request', async () => {
    mockFetchSuccess({ data: 'value' });

    const result = await ApiClient.get('/api/endpoint');

    expect(result.success).toBe(true);
    expect(result.data).toEqual({ data: 'value' });
});
```

### Example: Testing DOM interactions
```javascript
test('updates DOM element', () => {
    const element = document.createElement('div');
    element.id = 'test';
    document.body.appendChild(element);

    updateElement('#test', 'New content');

    expect(element.textContent).toBe('New content');
});
```

## Coverage Goals

Target coverage: **80%** for all frontend JavaScript files

Current coverage areas:
- ✅ Core utilities (app.js) - 58 tests
- ✅ API client (api-client.js) - 38 tests
- ✅ Session management (base.js) - 74 tests
- ✅ UI utilities (ui-utils.js) - 44 tests
- ✅ Explorer state management (state-management.js) - 46 tests
- ✅ Data loading and path utilities (data-loading.js) - 21 tests
- ✅ Explorer dialogs (dialogs.js) - 28 tests

**Total: 309 test assertions across 231 tests**

Areas not yet covered (opportunities for expansion):
- ⏸️ Explorer drag-drop functionality
- ⏸️ File operations (move, create, delete)
- ⏸️ Context menu interactions
- ⏸️ Object editor validation
- ⏸️ Analysis and suggestions
- ⏸️ Page-specific JS (git.js, backups.js, etc.)

## CI Integration

Add to `.github/workflows/test.yml`:

```yaml
- name: Run frontend tests
  run: npm test

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage/lcov.info
```

## Troubleshooting

### Tests fail with "localStorage is not defined"
- Ensure `setup.js` is loaded via `setupFilesAfterEnv` in package.json

### Tests timeout
- Check for unresolved promises or missing async/await
- Use `jest.useFakeTimers()` for timeout tests

### DOM tests fail
- Verify jsdom environment is configured in package.json
- Clean up DOM elements in `afterEach()` hooks

### Fetch mocks not working
- Clear fetch mock in beforeEach: `fetch.mockClear()`
- Use helper functions: `mockFetchSuccess()`, `mockFetchError()`
