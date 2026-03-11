/**
 * Centralized API client for Nagios Bulk Editor.
 * Provides standardized fetch wrappers with error handling, staging headers, and toast notifications.
 */
import { showToast } from './ui-notifications.js';
import { getStagingHeaders } from './session-manager.js';

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
            showToast(`${options.errorPrefix || 'Error'}: Request timed out`, 'error');
        }
        return { success: false, error: 'Request timed out', aborted: true };
    }
    if (!options.silent) {
        showToast(`${options.errorPrefix || 'Error'}: ${e.message}`, 'error');
    }
    return { success: false, error: e.message };
}

/**
 * Internal request function that handles common logic.
 * @param {string} url - API endpoint
 * @param {string} method - HTTP method (GET, POST, DELETE)
 * @param {object|undefined} data - Request body for POST (will be JSON-serialized)
 * @param {object} [options] - Additional options
 * @param {boolean} [options.silent] - Don't show error toasts
 * @param {string} [options.errorPrefix] - Prefix for error messages
 * @param {AbortSignal} [options.signal] - AbortController signal for cancellation
 * @param {number} [options.timeout] - Timeout in ms (creates AbortController internally)
 * @returns {Promise<{success: boolean, data?: object, error?: string, aborted?: boolean}>}
 */
async function request(url, method, data, options = {}) {
    let controller, timeoutId;
    let opts = options;
    if (opts.timeout && !opts.signal) {
        controller = new AbortController();
        timeoutId = setTimeout(() => controller.abort(), opts.timeout);
        opts = { ...opts, signal: controller.signal };
    }

    try {
        const fetchOptions = {
            method,
            headers: getStagingHeaders(),
            signal: opts.signal
        };
        if (data !== undefined) {
            fetchOptions.body = JSON.stringify(data);
        }
        const response = await fetch(url, fetchOptions);
        return handleResponse(response, opts);
    } catch (e) {
        return handleError(e, opts);
    } finally {
        if (timeoutId) {clearTimeout(timeoutId);}
    }
}

/**
 * Make a JSON POST request with staging headers.
 * @param {string} url - API endpoint
 * @param {object} data - Request body (will be JSON-serialized)
 * @param {object} [options] - Additional options
 * @returns {Promise<{success: boolean, data?: object, error?: string, aborted?: boolean}>}
 */
export function post(url, data = {}, options = {}) {
    return request(url, 'POST', data, options);
}

/**
 * Make a JSON GET request with staging headers.
 * @param {string} url - API endpoint
 * @param {object} [options] - Additional options
 * @returns {Promise<{success: boolean, data?: object, error?: string, aborted?: boolean}>}
 */
export function get(url, options = {}) {
    return request(url, 'GET', undefined, options);
}

/**
 * Make a DELETE request with staging headers.
 * @param {string} url - API endpoint
 * @param {object} [options] - Additional options
 * @returns {Promise<{success: boolean, data?: object, error?: string, aborted?: boolean}>}
 */
export function del(url, options = {}) {
    return request(url, 'DELETE', undefined, options);
}

// Also export as namespace for backward compat in callers
export const ApiClient = { post, get, del };
