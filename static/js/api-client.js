/**
 * Centralized API client for Nagios Bulk Editor.
 * Provides standardized fetch wrappers with error handling, staging headers, and toast notifications.
 */
const ApiClient = (function() {
    'use strict';

    /**
     * Internal helper to handle response and errors consistently.
     * @param {Response} response - Fetch response
     * @param {object} options - Request options
     * @returns {Promise<{success: boolean, data?: object, error?: string, status?: number}>}
     */
    async function handleResponse(response, options = {}) {
        let result;
        try {
            result = await response.json();
        } catch (e) {
            // Server returned non-JSON response (e.g., HTML error page)
            const errorMsg = `Server returned invalid response (${response.status})`;
            if (!options.silent) {
                showToast(`${options.errorPrefix || 'Error'}: ${errorMsg}`, 'error');
            }
            return { success: false, error: errorMsg, status: response.status };
        }
        if (!response.ok || result.error) {
            const errorMsg = result.error || `Request failed (${response.status})`;
            if (!options.silent) {
                showToast(`${options.errorPrefix || 'Error'}: ${errorMsg}`, 'error');
            }
            return { success: false, error: errorMsg, data: result, status: response.status };
        }
        return { success: true, data: result, status: response.status };
    }

    /**
     * Internal helper to handle fetch errors consistently.
     * @param {Error} e - The caught error
     * @param {object} options - Request options
     * @returns {{success: boolean, error: string, aborted?: boolean}}
     */
    function handleError(e, options = {}) {
        if (e.name === 'AbortError') {
            if (!options.silent) {
                showToast(`${options.errorPrefix || 'Request'} timed out`, 'error');
            }
            return { success: false, error: 'Request timed out', aborted: true };
        }
        if (!options.silent) {
            showToast(`${options.errorPrefix || 'Error'}: ${e.message}`, 'error');
        }
        return { success: false, error: e.message };
    }

    /**
     * Make a JSON POST request with staging headers.
     * @param {string} url - API endpoint
     * @param {object} data - Request body (will be JSON-serialized)
     * @param {object} [options] - Additional options
     * @param {boolean} [options.silent] - Don't show error toasts
     * @param {string} [options.errorPrefix] - Prefix for error messages
     * @param {AbortSignal} [options.signal] - AbortController signal for cancellation
     * @param {number} [options.timeout] - Timeout in ms (creates AbortController internally)
     * @returns {Promise<{success: boolean, data?: object, error?: string, aborted?: boolean}>}
     */
    async function post(url, data = {}, options = {}) {
        let controller, timeoutId;
        if (options.timeout && !options.signal) {
            controller = new AbortController();
            timeoutId = setTimeout(() => controller.abort(), options.timeout);
            options = { ...options, signal: controller.signal };
        }

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getStagingHeaders()
                },
                body: JSON.stringify(data),
                signal: options.signal
            });
            if (timeoutId) clearTimeout(timeoutId);
            return handleResponse(response, options);
        } catch (e) {
            if (timeoutId) clearTimeout(timeoutId);
            return handleError(e, options);
        }
    }

    /**
     * Make a JSON GET request with staging headers.
     * @param {string} url - API endpoint
     * @param {object} [options] - Additional options
     * @param {boolean} [options.silent] - Don't show error toasts
     * @param {string} [options.errorPrefix] - Prefix for error messages
     * @param {AbortSignal} [options.signal] - AbortController signal for cancellation
     * @param {number} [options.timeout] - Timeout in ms (creates AbortController internally)
     * @returns {Promise<{success: boolean, data?: object, error?: string, aborted?: boolean}>}
     */
    async function get(url, options = {}) {
        let controller, timeoutId;
        if (options.timeout && !options.signal) {
            controller = new AbortController();
            timeoutId = setTimeout(() => controller.abort(), options.timeout);
            options = { ...options, signal: controller.signal };
        }

        try {
            const response = await fetch(url, {
                headers: getStagingHeaders(),
                signal: options.signal
            });
            if (timeoutId) clearTimeout(timeoutId);
            return handleResponse(response, options);
        } catch (e) {
            if (timeoutId) clearTimeout(timeoutId);
            return handleError(e, options);
        }
    }

    /**
     * Make a DELETE request with staging headers.
     * @param {string} url - API endpoint
     * @param {object} [options] - Additional options
     * @param {boolean} [options.silent] - Don't show error toasts
     * @param {string} [options.errorPrefix] - Prefix for error messages
     * @param {AbortSignal} [options.signal] - AbortController signal for cancellation
     * @param {number} [options.timeout] - Timeout in ms (creates AbortController internally)
     * @returns {Promise<{success: boolean, data?: object, error?: string, aborted?: boolean}>}
     */
    async function del(url, options = {}) {
        let controller, timeoutId;
        if (options.timeout && !options.signal) {
            controller = new AbortController();
            timeoutId = setTimeout(() => controller.abort(), options.timeout);
            options = { ...options, signal: controller.signal };
        }

        try {
            const response = await fetch(url, {
                method: 'DELETE',
                headers: getStagingHeaders(),
                signal: options.signal
            });
            if (timeoutId) clearTimeout(timeoutId);
            return handleResponse(response, options);
        } catch (e) {
            if (timeoutId) clearTimeout(timeoutId);
            return handleError(e, options);
        }
    }

    return { post, get, del };
})();
