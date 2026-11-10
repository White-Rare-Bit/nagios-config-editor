/**
 * HTML escaping. No DOM access, so Node can import it for tests.
 */

const HTML_ESCAPES = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
};

/**
 * Escape text for HTML element content AND quoted attribute values
 * (title="", value="", data-*="" in either quote style).
 * @param {*} text - Value to escape (null/undefined become '')
 * @returns {string}
 */
export function escapeHtml(text) {
    if (text === null || text === undefined) {return '';}
    return String(text).replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);
}
