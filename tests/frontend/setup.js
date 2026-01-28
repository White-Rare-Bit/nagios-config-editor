/**
 * Jest test setup for frontend JavaScript tests
 * Sets up global mocks and utilities
 */

// Mock localStorage
const localStorageMock = (() => {
    let store = {};
    return {
        getItem: (key) => store[key] || null,
        setItem: (key, value) => { store[key] = String(value); },
        removeItem: (key) => { delete store[key]; },
        clear: () => { store = {}; }
    };
})();

global.localStorage = localStorageMock;

// Mock fetch API
global.fetch = jest.fn();

// Mock navigator.clipboard
global.navigator.clipboard = {
    writeText: jest.fn(() => Promise.resolve())
};

// Mock bootstrap
global.bootstrap = {
    Tooltip: jest.fn(),
    Modal: {
        getInstance: jest.fn(() => ({
            hide: jest.fn()
        }))
    }
};

// Reset mocks before each test
beforeEach(() => {
    localStorage.clear();
    fetch.mockClear();
    navigator.clipboard.writeText.mockClear();
});

// Helper to create mock DOM elements
global.createMockElement = (tag, attrs = {}) => {
    const element = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
        if (key === 'textContent') {
            element.textContent = value;
        } else if (key === 'innerHTML') {
            element.innerHTML = value;
        } else if (key === 'dataset') {
            Object.entries(value).forEach(([dataKey, dataValue]) => {
                element.dataset[dataKey] = dataValue;
            });
        } else {
            element.setAttribute(key, value);
        }
    });
    return element;
};

// Helper to mock fetch responses
global.mockFetchSuccess = (data) => {
    fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => data
    });
};

global.mockFetchError = (status = 500, error = 'Server error') => {
    fetch.mockResolvedValueOnce({
        ok: false,
        status,
        json: async () => ({ error })
    });
};

global.mockFetchNetworkError = (message = 'Network error') => {
    fetch.mockRejectedValueOnce(new Error(message));
};
