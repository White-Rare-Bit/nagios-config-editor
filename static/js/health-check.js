// Health Check page JavaScript
// Extracted from health_check.html

// Severity badge HTML templates
const SEVERITY_BADGES = {
    error: '<span class="health-filter-badge health-filter-badge--error">Error</span>',
    warning: '<span class="health-filter-badge health-filter-badge--warning">Warning</span>',
    info: '<span class="health-filter-badge health-filter-badge--info">Info</span>'
};

let allIssues = [];

async function runHealthCheck() {
    const btn = document.getElementById('runBtn');
    const container = document.getElementById('issuesContainer');

    btn.disabled = true;
    btn.textContent = 'Analyzing...';

    // Show loading state in issues container
    container.innerHTML = '<div class="health-loading">Analyzing configuration...</div>';

    const result = await ApiClient.get('/api/health-check');

    if (result.success) {
        allIssues = result.data.issues;
        displaySummary(result.data.summary);
        displayIssues(result.data.issues);
    } else {
        showToast('Error running health check: ' + result.error, 'error');
    }

    // Always re-enable button
    btn.disabled = false;
    btn.textContent = 'Run Health Check';
}

function displaySummary(summary) {
    const card = document.getElementById('summaryCard');

    if (summary.total_issues === 0) {
        card.innerHTML = `
            <div class="text-center">
                <div class="health-empty-icon"><i class="fa-solid fa-check" style="color: var(--nbe-success);"></i></div>
                <p class="u-mb-sm"><strong>No issues found!</strong></p>
                <small class="dialog-info-text">Your configuration looks healthy.</small>
            </div>
        `;
    } else {
        card.innerHTML = `
            <div class="health-summary-stats">
                <div class="health-summary-stat">
                    <span>Total Issues:</span>
                    <span class="health-summary-count">${summary.total_issues}</span>
                </div>
                <div class="health-summary-stat health-summary-stat--errors">
                    <span>Errors</span>
                    <span class="health-summary-count">${summary.errors}</span>
                </div>
                <div class="health-summary-stat health-summary-stat--warnings">
                    <span>Warnings</span>
                    <span class="health-summary-count">${summary.warnings}</span>
                </div>
                <div class="health-summary-stat health-summary-stat--info">
                    <span>Info</span>
                    <span class="health-summary-count">${summary.info}</span>
                </div>
            </div>
        `;
    }
}

function displayIssues(issues) {
    const container = document.getElementById('issuesContainer');
    document.getElementById('issueCount').textContent = issues.length;

    if (issues.length === 0) {
        container.innerHTML = `
            <div class="health-empty">
                No issues match the current filters.
            </div>
        `;
        return;
    }

    const html = issues.map(issue => {
        const severityBadge = SEVERITY_BADGES[issue.severity] || '';

        return `
            <div class="issue-item severity-${issue.severity}"
                 data-severity="${issue.severity}"
                 data-type="${issue.type}">
                <div class="issue-header">
                    ${severityBadge}
                    <span class="health-filter-badge">${escapeHtml(issue.object_type)}</span>
                    <span class="issue-object">${escapeHtml(issue.object)}</span>
                </div>
                <div class="issue-file">${escapeHtml(issue.file)}</div>
                <div class="issue-message">${escapeHtml(issue.message)}</div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

function filterIssues() {
    const showErrors = document.getElementById('showErrors').checked;
    const showWarnings = document.getElementById('showWarnings').checked;
    const showInfo = document.getElementById('showInfo').checked;
    const filterType = document.getElementById('filterType').value;
    const searchText = document.getElementById('searchIssues').value.toLowerCase();

    const filtered = allIssues.filter(issue => {
        // Severity filter
        if (issue.severity === 'error' && !showErrors) return false;
        if (issue.severity === 'warning' && !showWarnings) return false;
        if (issue.severity === 'info' && !showInfo) return false;

        // Type filter
        if (filterType && issue.type !== filterType) return false;

        // Text search
        if (searchText) {
            const searchable = `${issue.object} ${issue.message} ${issue.file}`.toLowerCase();
            if (!searchable.includes(searchText)) return false;
        }

        return true;
    });

    displayIssues(filtered);
}

// Event delegation for data-action attributes
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'runHealthCheck') {
        runHealthCheck();
    }
});

document.addEventListener('change', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'filterIssues') {
        filterIssues();
    }
});

document.addEventListener('input', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'filterIssues') {
        filterIssues();
    }
});
