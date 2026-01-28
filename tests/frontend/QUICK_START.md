# Frontend Tests - Quick Start Guide

## Installation

```bash
npm install
```

## Running Tests

### Run all tests
```bash
npm test
```

Expected output:
```
Test Suites: 7 passed, 7 total
Tests:       2 skipped, 231 passed, 233 total
Time:        ~2-3s
```

### Run specific test file
```bash
npm test app.test.js
npm test api-client.test.js
npm test base.test.js
npm test ui-utils.test.js
npm test state-management.test.js
npm test data-loading.test.js
npm test dialogs.test.js
```

### Watch mode (re-run on changes)
```bash
npm run test:watch
```

### Verbose output (show all test names)
```bash
npm run test:verbose
```

## Test Files Overview

| File | Tests | Purpose |
|------|-------|---------|
| `app.test.js` | 58 | Global utilities (escapeHtml, debounce, formatDate) |
| `api-client.test.js` | 38 | API client (POST/GET/DELETE, error handling) |
| `base.test.js` | 74 | Session management, toasts, dialogs |
| `ui-utils.test.js` | 44 | UI helpers (icons, badges, keyboard utils) |
| `state-management.test.js` | 46 | Explorer state operations |
| `data-loading.test.js` | 21 | Data loading, path utilities |
| `dialogs.test.js` | 28 | Dialog interactions |
| **Total** | **231** | **All passing** |

## Common Commands

```bash
# Run tests with coverage
npm test

# Run single test file
npm test -- app.test.js

# Run tests matching pattern
npm test -- --testNamePattern="escapeHtml"

# Update snapshots (if any)
npm test -- -u

# Clear Jest cache
npm test -- --clearCache

# Show test coverage in browser
npm test && open coverage/lcov-report/index.html
```

## Quick Test Examples

### Testing a utility function
```javascript
test('escapes HTML special characters', () => {
    expect(escapeHtml('<script>alert("xss")</script>'))
        .toBe('&lt;script&gt;alert("xss")&lt;/script&gt;');
});
```

### Testing API calls
```javascript
test('makes successful POST request', async () => {
    mockFetchSuccess({ data: 'value' });

    const result = await ApiClient.post('/api/endpoint', { key: 'value' });

    expect(result.success).toBe(true);
    expect(result.data).toEqual({ data: 'value' });
});
```

### Testing DOM interactions
```javascript
test('updates badge count', () => {
    const badge = document.createElement('span');
    badge.id = 'testBadge';
    document.body.appendChild(badge);

    Explorer.updateBadge('#testBadge', 5);

    expect(badge.textContent).toBe('5');
});
```

## Debugging

### Test fails unexpectedly
```bash
# Run with verbose output
npm test -- --verbose

# Run single test
npm test -- app.test.js

# Add console.log in test
test('my test', () => {
    console.log('Debug info:', someVariable);
    expect(...).toBe(...);
});
```

### Mock not working
```bash
# Verify setup.js is loaded
# Check package.json: "setupFilesAfterEnv": ["<rootDir>/tests/frontend/setup.js"]

# Clear mock in beforeEach
beforeEach(() => {
    fetch.mockClear();
    localStorage.clear();
});
```

### Test times out
```bash
# Increase timeout for specific test
test('slow operation', async () => {
    // test code
}, 10000); // 10 second timeout
```

## Coverage

Coverage is automatically collected for:
- `static/**/*.js`
- `!static/js/explorer/main.js` (excluded)

View coverage report:
```bash
npm test
# Opens coverage/lcov-report/index.html in browser
```

## File Structure

```
tests/frontend/
├── setup.js                    # Global mocks (localStorage, fetch, etc.)
├── app.test.js                 # Tests for app.js
├── api-client.test.js          # Tests for api-client.js
├── base.test.js                # Tests for base.js
├── ui-utils.test.js            # Tests for ui-utils.js
├── state-management.test.js    # Tests for state-management.js
├── data-loading.test.js        # Tests for data-loading.js
├── dialogs.test.js             # Tests for dialogs.js
├── README.md                   # Full documentation
├── TEST_SUMMARY.md             # Detailed test summary
└── QUICK_START.md              # This file
```

## CI/CD Integration

Add to your CI pipeline:

```yaml
- name: Install dependencies
  run: npm install

- name: Run frontend tests
  run: npm test

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage/lcov.info
```

## What's Tested

✅ **Core Utilities**
- HTML escaping (XSS prevention)
- Regex escaping
- Date formatting
- Clipboard operations
- Debouncing

✅ **API Client**
- HTTP methods (GET/POST/DELETE)
- Error handling
- Timeout support
- Header injection

✅ **Session Management**
- Session ID generation
- User identity storage
- Toast notifications
- Confirmation dialogs

✅ **Explorer State**
- Stable key operations
- Pending edit tracking
- Deletion marking
- Selection management

✅ **Data Loading**
- Concurrent API calls
- Path conversions
- Cache busting

✅ **UI Utilities**
- Icon mapping
- Badge updates
- Keyboard helpers
- Tab switching

✅ **Dialogs**
- Delete confirmations
- Rename inputs
- Move selections
- Clone operations

## Getting Help

- **Full documentation**: See [README.md](./README.md)
- **Test summary**: See [TEST_SUMMARY.md](./TEST_SUMMARY.md)
- **Jest docs**: https://jestjs.io/docs/getting-started
- **jsdom docs**: https://github.com/jsdom/jsdom

## Contributing

When adding new tests:
1. Create test file in `tests/frontend/`
2. Import dependencies and create mocks
3. Use descriptive test names
4. Test edge cases (null, undefined, empty)
5. Clean up DOM in `afterEach` hooks
6. Update documentation

## Tips

- **Run fast**: Tests complete in 2-3 seconds
- **Watch mode**: Use `npm run test:watch` during development
- **Isolate**: Use `test.only()` to focus on one test
- **Skip**: Use `test.skip()` to temporarily disable tests
- **Debug**: Add `console.log()` for debugging
- **Coverage**: Aim for 80%+ coverage on new code

## Quick Check

Verify everything works:
```bash
npm test
# Should show: 7 passed, 231 tests passed
```

If tests fail:
1. Check Node.js version (14+)
2. Run `npm install` again
3. Clear Jest cache: `npm test -- --clearCache`
4. Check for conflicting dependencies
