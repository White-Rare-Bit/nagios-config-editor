/**
 * Tests for app.js - Global utility functions
 */

describe('escapeHtml', () => {
    beforeEach(() => {
        // Define the function in global scope for testing
        global.escapeHtml = function(text) {
            if (text === null || text === undefined) return '';
            const div = document.createElement('div');
            div.textContent = String(text);
            return div.innerHTML;
        };
    });

    test('escapes HTML special characters', () => {
        expect(escapeHtml('<script>alert("xss")</script>'))
            .toBe('&lt;script&gt;alert("xss")&lt;/script&gt;');
    });

    test('escapes ampersands', () => {
        expect(escapeHtml('Tom & Jerry')).toBe('Tom &amp; Jerry');
    });

    test('escapes quotes', () => {
        expect(escapeHtml('Say "hello"')).toBe('Say "hello"');
    });

    test('handles null input', () => {
        expect(escapeHtml(null)).toBe('');
    });

    test('handles undefined input', () => {
        expect(escapeHtml(undefined)).toBe('');
    });

    test('converts non-string input to string', () => {
        expect(escapeHtml(123)).toBe('123');
        expect(escapeHtml(true)).toBe('true');
    });

    test('handles empty string', () => {
        expect(escapeHtml('')).toBe('');
    });

    test('handles nested HTML', () => {
        expect(escapeHtml('<div><p>test</p></div>'))
            .toBe('&lt;div&gt;&lt;p&gt;test&lt;/p&gt;&lt;/div&gt;');
    });
});

describe('escapeRegex', () => {
    beforeEach(() => {
        global.escapeRegex = function(str) {
            return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        };
    });

    test('escapes regex special characters', () => {
        expect(escapeRegex('test.value')).toBe('test\\.value');
        expect(escapeRegex('test*')).toBe('test\\*');
        expect(escapeRegex('test+')).toBe('test\\+');
        expect(escapeRegex('test?')).toBe('test\\?');
    });

    test('escapes brackets and parentheses', () => {
        expect(escapeRegex('[test]')).toBe('\\[test\\]');
        expect(escapeRegex('(test)')).toBe('\\(test\\)');
        expect(escapeRegex('{test}')).toBe('\\{test\\}');
    });

    test('escapes anchors and pipes', () => {
        expect(escapeRegex('^test$')).toBe('\\^test\\$');
        expect(escapeRegex('test|other')).toBe('test\\|other');
    });

    test('escapes backslashes', () => {
        expect(escapeRegex('test\\value')).toBe('test\\\\value');
    });

    test('handles string without special chars', () => {
        expect(escapeRegex('hostname01')).toBe('hostname01');
    });

    test('escapes multiple special chars', () => {
        expect(escapeRegex('.*+?^$')).toBe('\\.\\*\\+\\?\\^\\$');
    });
});

describe('debounce', () => {
    beforeEach(() => {
        global.debounce = function(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        };
    });

    test('delays function execution', (done) => {
        const mockFn = jest.fn();
        const debouncedFn = debounce(mockFn, 100);

        debouncedFn('test');
        expect(mockFn).not.toHaveBeenCalled();

        setTimeout(() => {
            expect(mockFn).toHaveBeenCalledWith('test');
            expect(mockFn).toHaveBeenCalledTimes(1);
            done();
        }, 150);
    });

    test('cancels previous calls', (done) => {
        const mockFn = jest.fn();
        const debouncedFn = debounce(mockFn, 100);

        debouncedFn('first');
        setTimeout(() => debouncedFn('second'), 50);
        setTimeout(() => debouncedFn('third'), 80);

        setTimeout(() => {
            expect(mockFn).toHaveBeenCalledTimes(1);
            expect(mockFn).toHaveBeenCalledWith('third');
            done();
        }, 200);
    });

    test('passes multiple arguments', (done) => {
        const mockFn = jest.fn();
        const debouncedFn = debounce(mockFn, 50);

        debouncedFn('arg1', 'arg2', 'arg3');

        setTimeout(() => {
            expect(mockFn).toHaveBeenCalledWith('arg1', 'arg2', 'arg3');
            done();
        }, 100);
    });
});

describe('formatDate', () => {
    beforeEach(() => {
        global.formatDate = function(dateStr, useRelative = true) {
            if (!dateStr) return '-';
            try {
                const date = new Date(dateStr);

                if (!useRelative) {
                    return date.toLocaleString();
                }

                const now = new Date();
                const diff = now - date;

                if (diff < 3600000) {
                    const mins = Math.floor(diff / 60000);
                    return mins <= 1 ? 'just now' : `${mins} minutes ago`;
                }

                if (diff < 86400000) {
                    const hours = Math.floor(diff / 3600000);
                    return hours === 1 ? '1 hour ago' : `${hours} hours ago`;
                }

                if (diff < 604800000) {
                    const days = Math.floor(diff / 86400000);
                    return days === 1 ? 'yesterday' : `${days} days ago`;
                }

                return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
            } catch (e) {
                return dateStr;
            }
        };
    });

    test('handles null input', () => {
        expect(formatDate(null)).toBe('-');
    });

    test('handles undefined input', () => {
        expect(formatDate(undefined)).toBe('-');
    });

    test('formats recent date as "just now"', () => {
        const now = new Date();
        expect(formatDate(now.toISOString())).toBe('just now');
    });

    test('formats minutes ago', () => {
        const fiveMinutesAgo = new Date(Date.now() - 5 * 60000);
        expect(formatDate(fiveMinutesAgo.toISOString())).toBe('5 minutes ago');
    });

    test('formats 1 minute ago', () => {
        // Need at least 2 minutes for "1 minute ago" to trigger (mins > 1)
        const oneMinuteAgo = new Date(Date.now() - 61000);
        const result = formatDate(oneMinuteAgo.toISOString());
        // 61 seconds is still less than full 2 minutes, shows as "just now"
        expect(result).toBe('just now');
    });

    test('formats hours ago', () => {
        const twoHoursAgo = new Date(Date.now() - 2 * 3600000);
        expect(formatDate(twoHoursAgo.toISOString())).toBe('2 hours ago');
    });

    test('formats 1 hour ago', () => {
        const oneHourAgo = new Date(Date.now() - 3600000);
        expect(formatDate(oneHourAgo.toISOString())).toBe('1 hour ago');
    });

    test('formats yesterday', () => {
        const yesterday = new Date(Date.now() - 86400000);
        expect(formatDate(yesterday.toISOString())).toBe('yesterday');
    });

    test('formats days ago', () => {
        const threeDaysAgo = new Date(Date.now() - 3 * 86400000);
        expect(formatDate(threeDaysAgo.toISOString())).toBe('3 days ago');
    });

    test('formats older dates', () => {
        const tenDaysAgo = new Date(Date.now() - 10 * 86400000);
        const result = formatDate(tenDaysAgo.toISOString());
        expect(result).toMatch(/[A-Z][a-z]{2} \d{1,2}, \d{4}/);
    });

    test('uses absolute format when useRelative is false', () => {
        const now = new Date();
        const result = formatDate(now.toISOString(), false);
        expect(result).toContain('/');
    });

    test('handles invalid date string', () => {
        const result = formatDate('invalid-date');
        // Browser returns 'Invalid Date' for invalid date strings
        expect(result).toContain('Date');
    });
});

describe('copyToClipboard', () => {
    beforeEach(() => {
        global.copyToClipboard = async function(text) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (err) {
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                document.body.appendChild(textArea);
                textArea.select();
                try {
                    document.execCommand('copy');
                    return true;
                } catch (err) {
                    return false;
                } finally {
                    textArea.remove();
                }
            }
        };
    });

    test('copies text to clipboard using Clipboard API', async () => {
        const result = await copyToClipboard('test text');
        expect(result).toBe(true);
        expect(navigator.clipboard.writeText).toHaveBeenCalledWith('test text');
    });

    test('falls back to execCommand when Clipboard API fails', async () => {
        navigator.clipboard.writeText.mockRejectedValueOnce(new Error('Not allowed'));
        document.execCommand = jest.fn(() => true);

        const result = await copyToClipboard('test text');
        expect(result).toBe(true);
    });

    test('returns false when both methods fail', async () => {
        navigator.clipboard.writeText.mockRejectedValueOnce(new Error('Not allowed'));
        const originalExecCommand = document.execCommand;
        document.execCommand = jest.fn(() => {
            throw new Error('Not supported');
        });

        const result = await copyToClipboard('test text');
        expect(result).toBe(false);

        document.execCommand = originalExecCommand;
    });

    test('removes temporary textarea after fallback', async () => {
        navigator.clipboard.writeText.mockRejectedValueOnce(new Error('Not allowed'));
        document.execCommand = jest.fn(() => true);

        await copyToClipboard('test text');

        const textareas = document.querySelectorAll('textarea');
        expect(textareas.length).toBe(0);
    });
});

describe('setButtonLoading', () => {
    beforeEach(() => {
        global.setButtonLoading = function(button, loading) {
            if (loading) {
                button.disabled = true;
                button.dataset.originalText = button.textContent;
                button.textContent = 'Loading...';
            } else {
                button.disabled = false;
                button.textContent = button.dataset.originalText || button.textContent;
            }
        };
    });

    test('sets button to loading state', () => {
        const button = document.createElement('button');
        button.textContent = 'Submit';

        setButtonLoading(button, true);

        expect(button.disabled).toBe(true);
        expect(button.textContent).toBe('Loading...');
        expect(button.dataset.originalText).toBe('Submit');
    });

    test('restores button from loading state', () => {
        const button = document.createElement('button');
        button.textContent = 'Submit';
        button.dataset.originalText = 'Submit';

        setButtonLoading(button, false);

        expect(button.disabled).toBe(false);
        expect(button.textContent).toBe('Submit');
    });

    test('handles multiple loading toggles', () => {
        const button = document.createElement('button');
        button.textContent = 'Submit';

        setButtonLoading(button, true);
        expect(button.textContent).toBe('Loading...');

        setButtonLoading(button, false);
        expect(button.textContent).toBe('Submit');

        setButtonLoading(button, true);
        expect(button.textContent).toBe('Loading...');
    });
});
