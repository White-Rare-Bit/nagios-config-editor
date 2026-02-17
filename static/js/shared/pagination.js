// Shared pagination component
// Used by: backups.js, logs.js, git.js

/**
 * Renders pagination controls HTML.
 * @param {Object} options - Pagination configuration
 * @param {number} options.currentPage - Current active page (1-indexed)
 * @param {number} options.totalItems - Total number of items
 * @param {number} options.pageSize - Items per page
 * @param {string} options.actionPrefix - Prefix for data-action attributes (e.g., "backup" -> "backup-page")
 * @param {string} [options.extraClass] - Optional additional CSS class for the container
 * @param {string} [options.extraStyle] - Optional inline style for the container
 * @returns {string} HTML string for pagination controls
 */
function renderPagination(options) {
    const { currentPage, totalItems, pageSize, actionPrefix, extraClass = '', extraStyle = '' } = options;

    const totalPages = Math.ceil(totalItems / pageSize);
    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, totalItems);

    // Don't show pagination if not needed
    if (totalPages <= 1 && totalItems <= 25) {
        return '';
    }

    let pagesHtml = '';

    // Previous button
    pagesHtml += `<button class="nbe-pagination-btn nbe-pagination-nav" data-action="${actionPrefix}-page" data-page="${currentPage - 1}" ${currentPage === 1 ? 'disabled' : ''}>
        <i class="fa-solid fa-chevron-left"></i>
    </button>`;

    // Page numbers with ellipsis
    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if (endPage - startPage + 1 < maxVisible) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }

    if (startPage > 1) {
        pagesHtml += `<button class="nbe-pagination-btn" data-action="${actionPrefix}-page" data-page="1">1</button>`;
        if (startPage > 2) {
            pagesHtml += `<span class="nbe-pagination-ellipsis">...</span>`;
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        pagesHtml += `<button class="nbe-pagination-btn${i === currentPage ? ' active' : ''}" data-action="${actionPrefix}-page" data-page="${i}">${i}</button>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            pagesHtml += `<span class="nbe-pagination-ellipsis">...</span>`;
        }
        pagesHtml += `<button class="nbe-pagination-btn" data-action="${actionPrefix}-page" data-page="${totalPages}">${totalPages}</button>`;
    }

    // Next button
    pagesHtml += `<button class="nbe-pagination-btn nbe-pagination-nav" data-action="${actionPrefix}-page" data-page="${currentPage + 1}" ${currentPage === totalPages ? 'disabled' : ''}>
        <i class="fa-solid fa-chevron-right"></i>
    </button>`;

    const styleAttr = extraStyle ? ` style="${extraStyle}"` : '';
    const classAttr = extraClass ? ` ${extraClass}` : '';

    return `
        <div class="nbe-pagination${classAttr}"${styleAttr}>
            <div class="nbe-pagination-info">
                <span class="nbe-pagination-showing">Showing ${startIdx + 1}-${endIdx} of ${totalItems}</span>
                <div class="nbe-pagination-page-size">
                    <span>Per page:</span>
                    <select data-action="${actionPrefix}-page-size">
                        <option value="25" ${pageSize === 25 ? 'selected' : ''}>25</option>
                        <option value="50" ${pageSize === 50 ? 'selected' : ''}>50</option>
                        <option value="100" ${pageSize === 100 ? 'selected' : ''}>100</option>
                    </select>
                </div>
            </div>
            <div class="nbe-pagination-controls">
                ${pagesHtml}
            </div>
        </div>
    `;
}

// Export for use in other modules
window.renderPagination = renderPagination;
