/**
 * Nagios Bulk Editor - Session Manager Module
 *
 * Handles session ID generation, user identity persistence,
 * and staging headers for API calls.
 * Extracted from base.js to reduce complexity.
 */

// =============================================================================
// Session & Identity Management
// =============================================================================

/**
 * Get or create a persistent session ID.
 * Session IDs are stored in localStorage and persist across page reloads.
 * @returns {string} The session ID
 */
function getSessionId() {
    let sessionId = localStorage.getItem('nagios_session_id');
    if (!sessionId) {
        sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('nagios_session_id', sessionId);
    }
    return sessionId;
}

/**
 * Get the user's identity (name and email) from localStorage.
 * @returns {{userName: string, userEmail: string}} User identity object
 */
function getUserIdentity() {
    return {
        userName: localStorage.getItem('nagios_user_name') || '',
        userEmail: localStorage.getItem('nagios_user_email') || ''
    };
}

/**
 * Set the user's identity in localStorage.
 * @param {string} name - User's name
 * @param {string} email - User's email
 */
function setUserIdentity(name, email) {
    localStorage.setItem('nagios_user_name', name);
    localStorage.setItem('nagios_user_email', email);
}

/**
 * Check if user has set their identity.
 * @returns {boolean} True if both name and email are set
 */
function hasUserIdentity() {
    const identity = getUserIdentity();
    return !!(identity.userName && identity.userEmail);
}

/**
 * Get standard headers for staging API requests.
 * Includes Content-Type and session ID.
 * @returns {object} Headers object for fetch requests
 */
function getStagingHeaders() {
    return {
        'Content-Type': 'application/json',
        'X-Session-Id': getSessionId()
    };
}

// Export to global scope for backward compatibility
window.getSessionId = getSessionId;
window.getUserIdentity = getUserIdentity;
window.setUserIdentity = setUserIdentity;
window.hasUserIdentity = hasUserIdentity;
window.getStagingHeaders = getStagingHeaders;
