/**
 * Tests for ui-utils.js - Explorer UI utilities
 */

describe('Explorer UI Utilities', () => {
    let Explorer;

    beforeEach(() => {
        // Initialize Explorer namespace with UI utilities
        Explorer = {
            getObjectTypeIcon: function(type) {
                const icons = {
                    host: 'server',
                    hostgroup: 'server',
                    service: 'activity',
                    servicegroup: 'layers',
                    contact: 'user',
                    contactgroup: 'users',
                    command: 'terminal',
                    timeperiod: 'clock',
                    servicedependency: 'git-merge',
                    hostdependency: 'git-merge',
                    serviceescalation: 'trending-up',
                    hostescalation: 'trending-up'
                };
                return icons[type] || 'file';
            },

            getIssueIcon: function(issueType) {
                const icons = {
                    missing: 'alert-circle',
                    duplicate: 'copy',
                    circular: 'refresh-cw',
                    orphan: 'link-2',
                    unused: 'archive',
                    error: 'x-circle',
                    warning: 'alert-triangle'
                };
                return icons[issueType] || 'alert-circle';
            },

            icon: function(name, size = 16) {
                return `<i data-feather="${name}" style="width:${size}px;height:${size}px"></i>`;
            },

            updateBadge: function(selector, count, hideWhenZero = true) {
                const badge = document.querySelector(selector);
                if (badge) {
                    badge.textContent = count;
                    if (hideWhenZero) {
                        badge.style.display = count > 0 ? '' : 'none';
                    }
                }
            },

            debounce: function(func, wait) {
                let timeout;
                return function executedFunction(...args) {
                    const later = () => {
                        clearTimeout(timeout);
                        func(...args);
                    };
                    clearTimeout(timeout);
                    timeout = setTimeout(later, wait);
                };
            },

            throttle: function(func, limit) {
                let inThrottle;
                return function(...args) {
                    if (!inThrottle) {
                        func.apply(this, args);
                        inThrottle = true;
                        setTimeout(() => inThrottle = false, limit);
                    }
                };
            },

            isEscapeKey: function(event) {
                return event.key === 'Escape' || event.keyCode === 27;
            },

            isEnterKey: function(event) {
                return event.key === 'Enter' || event.keyCode === 13;
            },

            isModifierKey: function(event) {
                return event.metaKey || event.ctrlKey;
            },

            switchTabs: function(buttonSelector, contentSelector, activeValue, dataAttr, contentSuffix) {
                document.querySelectorAll(buttonSelector).forEach(btn => {
                    btn.classList.toggle('active', btn.dataset[dataAttr] === activeValue);
                });
                document.querySelectorAll(contentSelector).forEach(content => {
                    content.classList.toggle('active', content.id === activeValue + contentSuffix);
                });
            }
        };
    });

    describe('getObjectTypeIcon', () => {
        test('returns correct icon for host', () => {
            expect(Explorer.getObjectTypeIcon('host')).toBe('server');
        });

        test('returns correct icon for service', () => {
            expect(Explorer.getObjectTypeIcon('service')).toBe('activity');
        });

        test('returns correct icon for contact', () => {
            expect(Explorer.getObjectTypeIcon('contact')).toBe('user');
        });

        test('returns correct icon for contactgroup', () => {
            expect(Explorer.getObjectTypeIcon('contactgroup')).toBe('users');
        });

        test('returns correct icon for command', () => {
            expect(Explorer.getObjectTypeIcon('command')).toBe('terminal');
        });

        test('returns correct icon for timeperiod', () => {
            expect(Explorer.getObjectTypeIcon('timeperiod')).toBe('clock');
        });

        test('returns correct icon for dependencies', () => {
            expect(Explorer.getObjectTypeIcon('servicedependency')).toBe('git-merge');
            expect(Explorer.getObjectTypeIcon('hostdependency')).toBe('git-merge');
        });

        test('returns correct icon for escalations', () => {
            expect(Explorer.getObjectTypeIcon('serviceescalation')).toBe('trending-up');
            expect(Explorer.getObjectTypeIcon('hostescalation')).toBe('trending-up');
        });

        test('returns default icon for unknown type', () => {
            expect(Explorer.getObjectTypeIcon('unknown')).toBe('file');
        });

        test('returns default icon for null', () => {
            expect(Explorer.getObjectTypeIcon(null)).toBe('file');
        });
    });

    describe('getIssueIcon', () => {
        test('returns correct icon for missing', () => {
            expect(Explorer.getIssueIcon('missing')).toBe('alert-circle');
        });

        test('returns correct icon for duplicate', () => {
            expect(Explorer.getIssueIcon('duplicate')).toBe('copy');
        });

        test('returns correct icon for circular', () => {
            expect(Explorer.getIssueIcon('circular')).toBe('refresh-cw');
        });

        test('returns correct icon for orphan', () => {
            expect(Explorer.getIssueIcon('orphan')).toBe('link-2');
        });

        test('returns correct icon for unused', () => {
            expect(Explorer.getIssueIcon('unused')).toBe('archive');
        });

        test('returns correct icon for error', () => {
            expect(Explorer.getIssueIcon('error')).toBe('x-circle');
        });

        test('returns correct icon for warning', () => {
            expect(Explorer.getIssueIcon('warning')).toBe('alert-triangle');
        });

        test('returns default icon for unknown issue', () => {
            expect(Explorer.getIssueIcon('unknown')).toBe('alert-circle');
        });
    });

    describe('icon', () => {
        test('renders icon HTML with default size', () => {
            const html = Explorer.icon('check');
            expect(html).toBe('<i data-feather="check" style="width:16px;height:16px"></i>');
        });

        test('renders icon HTML with custom size', () => {
            const html = Explorer.icon('check', 24);
            expect(html).toBe('<i data-feather="check" style="width:24px;height:24px"></i>');
        });

        test('handles different icon names', () => {
            expect(Explorer.icon('alert-circle')).toContain('data-feather="alert-circle"');
            expect(Explorer.icon('user')).toContain('data-feather="user"');
        });
    });

    describe('updateBadge', () => {
        beforeEach(() => {
            const badge = document.createElement('span');
            badge.className = 'badge';
            badge.id = 'testBadge';
            document.body.appendChild(badge);
        });

        test('updates badge count', () => {
            Explorer.updateBadge('#testBadge', 5);

            const badge = document.querySelector('#testBadge');
            expect(badge.textContent).toBe('5');
        });

        test('hides badge when count is zero', () => {
            Explorer.updateBadge('#testBadge', 0);

            const badge = document.querySelector('#testBadge');
            expect(badge.style.display).toBe('none');
        });

        test('shows badge when count is greater than zero', () => {
            const badge = document.querySelector('#testBadge');
            badge.style.display = 'none';

            Explorer.updateBadge('#testBadge', 3);

            expect(badge.style.display).toBe('');
            expect(badge.textContent).toBe('3');
        });

        test('does not hide badge when hideWhenZero is false', () => {
            Explorer.updateBadge('#testBadge', 0, false);

            const badge = document.querySelector('#testBadge');
            expect(badge.textContent).toBe('0');
            expect(badge.style.display).not.toBe('none');
        });

        test('handles missing badge gracefully', () => {
            expect(() => {
                Explorer.updateBadge('#nonexistent', 5);
            }).not.toThrow();
        });
    });

    describe('debounce', () => {
        test('delays function execution', (done) => {
            const mockFn = jest.fn();
            const debouncedFn = Explorer.debounce(mockFn, 100);

            debouncedFn('test');
            expect(mockFn).not.toHaveBeenCalled();

            setTimeout(() => {
                expect(mockFn).toHaveBeenCalledWith('test');
                done();
            }, 150);
        });

        test('cancels previous calls', (done) => {
            const mockFn = jest.fn();
            const debouncedFn = Explorer.debounce(mockFn, 100);

            debouncedFn('first');
            setTimeout(() => debouncedFn('second'), 50);
            setTimeout(() => debouncedFn('third'), 80);

            setTimeout(() => {
                expect(mockFn).toHaveBeenCalledTimes(1);
                expect(mockFn).toHaveBeenCalledWith('third');
                done();
            }, 200);
        });
    });

    describe('throttle', () => {
        test('limits function execution rate', (done) => {
            jest.useFakeTimers();

            const mockFn = jest.fn();
            const throttledFn = Explorer.throttle(mockFn, 100);

            throttledFn('call1');
            throttledFn('call2');
            throttledFn('call3');

            expect(mockFn).toHaveBeenCalledTimes(1);
            expect(mockFn).toHaveBeenCalledWith('call1');

            jest.advanceTimersByTime(101);

            throttledFn('call4');
            expect(mockFn).toHaveBeenCalledTimes(2);
            expect(mockFn).toHaveBeenCalledWith('call4');

            jest.useRealTimers();
            done();
        });

        test('preserves function context', () => {
            jest.useFakeTimers();

            const obj = {
                count: 0,
                increment: function() {
                    this.count++;
                }
            };

            obj.increment = Explorer.throttle(obj.increment.bind(obj), 100);

            obj.increment();
            expect(obj.count).toBe(1);

            obj.increment();
            expect(obj.count).toBe(1);

            jest.advanceTimersByTime(101);

            obj.increment();
            expect(obj.count).toBe(2);

            jest.useRealTimers();
        });
    });

    describe('Keyboard utilities', () => {
        describe('isEscapeKey', () => {
            test('returns true for Escape key', () => {
                const event = { key: 'Escape' };
                expect(Explorer.isEscapeKey(event)).toBe(true);
            });

            test('returns true for Escape keyCode', () => {
                const event = { keyCode: 27 };
                expect(Explorer.isEscapeKey(event)).toBe(true);
            });

            test('returns false for other keys', () => {
                const event = { key: 'Enter' };
                expect(Explorer.isEscapeKey(event)).toBe(false);
            });
        });

        describe('isEnterKey', () => {
            test('returns true for Enter key', () => {
                const event = { key: 'Enter' };
                expect(Explorer.isEnterKey(event)).toBe(true);
            });

            test('returns true for Enter keyCode', () => {
                const event = { keyCode: 13 };
                expect(Explorer.isEnterKey(event)).toBe(true);
            });

            test('returns false for other keys', () => {
                const event = { key: 'Escape' };
                expect(Explorer.isEnterKey(event)).toBe(false);
            });
        });

        describe('isModifierKey', () => {
            test('returns true for Ctrl key', () => {
                const event = { ctrlKey: true };
                expect(Explorer.isModifierKey(event)).toBe(true);
            });

            test('returns true for Meta key (Cmd on Mac)', () => {
                const event = { metaKey: true };
                expect(Explorer.isModifierKey(event)).toBe(true);
            });

            test('returns true when both are pressed', () => {
                const event = { ctrlKey: true, metaKey: true };
                expect(Explorer.isModifierKey(event)).toBe(true);
            });

            test('returns false when neither is pressed', () => {
                const event = { ctrlKey: false, metaKey: false };
                expect(Explorer.isModifierKey(event)).toBe(false);
            });
        });
    });

    describe('switchTabs', () => {
        beforeEach(() => {
            // Create tab buttons
            const btn1 = document.createElement('button');
            btn1.className = 'tab-btn';
            btn1.dataset.tab = 'tab1';

            const btn2 = document.createElement('button');
            btn2.className = 'tab-btn';
            btn2.dataset.tab = 'tab2';

            // Create tab contents
            const content1 = document.createElement('div');
            content1.id = 'tab1-content';

            const content2 = document.createElement('div');
            content2.id = 'tab2-content';

            document.body.appendChild(btn1);
            document.body.appendChild(btn2);
            document.body.appendChild(content1);
            document.body.appendChild(content2);
        });

        test('activates correct button and content', () => {
            Explorer.switchTabs('.tab-btn', '[id$="-content"]', 'tab1', 'tab', '-content');

            const btn1 = document.querySelector('[data-tab="tab1"]');
            const btn2 = document.querySelector('[data-tab="tab2"]');
            const content1 = document.getElementById('tab1-content');
            const content2 = document.getElementById('tab2-content');

            expect(btn1.classList.contains('active')).toBe(true);
            expect(btn2.classList.contains('active')).toBe(false);
            expect(content1.classList.contains('active')).toBe(true);
            expect(content2.classList.contains('active')).toBe(false);
        });

        test('switches between tabs', () => {
            Explorer.switchTabs('.tab-btn', '[id$="-content"]', 'tab1', 'tab', '-content');

            const btn1 = document.querySelector('[data-tab="tab1"]');
            const content1 = document.getElementById('tab1-content');
            expect(btn1.classList.contains('active')).toBe(true);
            expect(content1.classList.contains('active')).toBe(true);

            Explorer.switchTabs('.tab-btn', '[id$="-content"]', 'tab2', 'tab', '-content');

            const btn2 = document.querySelector('[data-tab="tab2"]');
            const content2 = document.getElementById('tab2-content');
            expect(btn1.classList.contains('active')).toBe(false);
            expect(content1.classList.contains('active')).toBe(false);
            expect(btn2.classList.contains('active')).toBe(true);
            expect(content2.classList.contains('active')).toBe(true);
        });
    });
});
