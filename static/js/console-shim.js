/**
 * Console Shim - Development-mode console logging to backend.
 *
 * This shim intercepts console.log/warn/error/info/debug and sends
 * messages to a backend endpoint for server-side logging.
 *
 * IMPORTANT: This file must be loaded FIRST, before any other JavaScript,
 * so it can capture all console output from the start.
 *
 * Safety features:
 * - Only active when window.__CONSOLE_SHIM_ENABLED__ is true
 * - Prevents infinite loops by not logging its own errors
 * - Uses a queue with debouncing to batch messages
 * - Falls back gracefully if the endpoint is unavailable
 */
(function() {
    'use strict';

    // Check if shim should be enabled (set by server in debug mode)
    if (!window.__CONSOLE_SHIM_ENABLED__) {
        return;
    }

    var ENDPOINT = '/api/debug/console';
    var BATCH_DELAY_MS = 100;  // Batch messages within this window
    var MAX_QUEUE_SIZE = 50;   // Don't let queue grow unbounded

    // State
    var queue = [];
    var flushTimer = null;
    var isSending = false;
    var shimActive = false;  // Guard against recursion

    // Store original console methods
    var originalConsole = {
        log: console.log,
        warn: console.warn,
        error: console.error,
        info: console.info,
        debug: console.debug
    };

    /**
     * Safely serialize a value for transmission.
     * Handles circular references and complex objects.
     */
    function safeSerialize(value) {
        if (value === undefined) {return 'undefined';}
        if (value === null) {return null;}
        if (typeof value === 'string') {return value;}
        if (typeof value === 'number' || typeof value === 'boolean') {return value;}
        if (value instanceof Error) {
            return {
                __type: 'Error',
                name: value.name,
                message: value.message,
                stack: value.stack
            };
        }
        if (value instanceof Date) {
            return value.toISOString();
        }
        if (typeof value === 'function') {
            return '[Function: ' + (value.name || 'anonymous') + ']';
        }
        if (Array.isArray(value)) {
            try {
                // Limit array serialization depth
                return value.slice(0, 20).map(function(item) {
                    if (typeof item === 'object' && item !== null) {
                        return '[Object]';
                    }
                    return safeSerialize(item);
                });
            } catch (e) {
                return '[Array]';
            }
        }
        if (typeof value === 'object') {
            try {
                // For DOM elements
                if (value.nodeType) {
                    return '[' + value.nodeName + (value.id ? '#' + value.id : '') + ']';
                }
                // Try to get a useful string representation
                var str = JSON.stringify(value, function(key, val) {
                    if (typeof val === 'function') {return '[Function]';}
                    if (val instanceof Error) {return val.toString();}
                    if (val && val.nodeType) {return '[DOMElement]';}
                    return val;
                });
                if (str && str.length > 1000) {
                    str = str.substring(0, 1000) + '...';
                }
                return JSON.parse(str);
            } catch (e) {
                return '[Object]';
            }
        }
        return String(value);
    }

    /**
     * Queue a console message for sending to backend.
     */
    function queueMessage(level, args) {
        if (shimActive) {return;}  // Prevent recursion

        var messages = [];
        for (var i = 0; i < args.length; i++) {
            messages.push(safeSerialize(args[i]));
        }

        var entry = {
            level: level,
            messages: messages,
            timestamp: new Date().toISOString(),
            url: window.location.href
        };

        queue.push(entry);

        // Prevent queue from growing too large
        if (queue.length > MAX_QUEUE_SIZE) {
            queue.shift();
        }

        // Schedule flush
        if (!flushTimer) {
            flushTimer = setTimeout(flushQueue, BATCH_DELAY_MS);
        }
    }

    /**
     * Send queued messages to backend.
     */
    function flushQueue() {
        flushTimer = null;

        if (queue.length === 0 || isSending) {
            return;
        }

        // Take current queue and reset
        var batch = queue;
        queue = [];
        isSending = true;
        shimActive = true;  // Prevent our own fetch errors from being logged

        // Send each message (could batch further, but keeping simple)
        var sendNext = function(index) {
            if (index >= batch.length) {
                isSending = false;
                shimActive = false;
                // Check if more messages queued during send
                if (queue.length > 0 && !flushTimer) {
                    flushTimer = setTimeout(flushQueue, BATCH_DELAY_MS);
                }
                return;
            }

            var entry = batch[index];

            fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(entry)
            })
            .then(function() {
                // Success - continue to next
                sendNext(index + 1);
            })
            .catch(function() {
                // Endpoint unavailable - silently skip remaining
                // DO NOT log this error (would cause infinite loop)
                isSending = false;
                shimActive = false;
            });
        };

        sendNext(0);
    }

    /**
     * Create a wrapped console method.
     */
    function wrapConsoleMethod(level) {
        return function() {
            // Always call original first
            originalConsole[level].apply(console, arguments);

            // Queue for backend (if not our own internal call)
            if (!shimActive) {
                queueMessage(level, arguments);
            }
        };
    }

    // Install shims
    console.log = wrapConsoleMethod('log');
    console.warn = wrapConsoleMethod('warn');
    console.error = wrapConsoleMethod('error');
    console.info = wrapConsoleMethod('info');
    console.debug = wrapConsoleMethod('debug');

    // Expose method to restore original console (for debugging the shim itself)
    window.__restoreConsole = function() {
        console.log = originalConsole.log;
        console.warn = originalConsole.warn;
        console.error = originalConsole.error;
        console.info = originalConsole.info;
        console.debug = originalConsole.debug;
        originalConsole.log('[console-shim] Original console restored');
    };

    // Log that shim is active (using original to avoid recursion)
    originalConsole.debug('[console-shim] Frontend console logging enabled');

})();
