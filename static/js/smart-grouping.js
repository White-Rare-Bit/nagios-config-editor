// Smart Grouping page JavaScript

(function() {
    'use strict';

    // Type configuration constants
    const TYPE_COLORS = {
        'hostname-prefix': 'primary',
        'hostname-suffix': 'info',
        'ip-subnet': 'success',
        'common-services': 'warning',
        'check-command': 'secondary',
        'network-parent': 'dark',
        'ungrouped': 'danger'
    };

    const TYPE_LABELS = {
        'hostname-prefix': 'Hostname Prefix',
        'hostname-suffix': 'Hostname Suffix',
        'ip-subnet': 'IP Subnet',
        'common-services': 'Common Services',
        'check-command': 'Check Command',
        'network-parent': 'Network Parent',
        'ungrouped': 'Ungrouped'
    };

    const PREVIEW_LIMIT = 8;

    let allSuggestions = [];
    let currentMembers = [];

document.getElementById('minMembers').addEventListener('input', function() {
    document.getElementById('minMembersValue').textContent = this.value;
});

async function analyzeHosts() {
    const btn = document.getElementById('analyzeBtn');
    btn.disabled = true;
    btn.textContent = 'Analyzing...';

    try {
        const response = await ApiClient.get('/api/smart-grouping/suggest');
        if (!response.success) {
            showToast('Error analyzing hosts: ' + response.error, 'error');
            return;
        }
        const result = response.data;
        allSuggestions = result.suggestions;

        document.getElementById('summaryCard').innerHTML = `
            <div class="text-start">
                <div class="d-flex justify-content-between mb-1">
                    <span>Total Hosts:</span>
                    <strong>${result.total_hosts}</strong>
                </div>
                <div class="d-flex justify-content-between mb-1">
                    <span>Existing Groups:</span>
                    <strong>${result.existing_groups}</strong>
                </div>
                <div class="d-flex justify-content-between">
                    <span>Suggestions:</span>
                    <strong>${result.suggestions.length}</strong>
                </div>
            </div>
        `;

        filterSuggestions();

    } catch (error) {
        showToast('Error analyzing hosts: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Analyze Hosts';
    }
}

function filterSuggestions() {
    const enabledTypes = Array.from(document.querySelectorAll('.filter-type:checked'))
        .map(cb => cb.value);
    const minMembers = parseInt(document.getElementById('minMembers').value);
    const searchText = document.getElementById('searchSuggestions').value.toLowerCase();

    const filtered = allSuggestions.filter(s => {
        if (!enabledTypes.includes(s.type)) return false;
        if (s.count < minMembers) return false;
        if (searchText) {
            const searchable = `${s.name} ${s.description} ${s.members.join(' ')}`.toLowerCase();
            if (!searchable.includes(searchText)) return false;
        }
        return true;
    });

    displaySuggestions(filtered);
}

function displaySuggestions(suggestions) {
    const container = document.getElementById('suggestionsContainer');
    document.getElementById('suggestionCount').textContent = suggestions.length;

    if (suggestions.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted p-4">
                No suggestions match the current filters.
            </div>
        `;
        return;
    }

    const html = suggestions.map((s, idx) => {
        const color = TYPE_COLORS[s.type] || 'secondary';
        const label = TYPE_LABELS[s.type] || s.type;

        const membersPreview = s.members.slice(0, PREVIEW_LIMIT);
        const moreCount = s.members.length - PREVIEW_LIMIT;

        return `
            <div class="suggestion-card" data-index="${idx}">
                <div class="suggestion-header">
                    <div>
                        <span class="badge bg-${color} type-badge">${label}</span>
                        <strong class="ms-2">${escapeHtml(s.name)}</strong>
                    </div>
                    <span class="badge bg-secondary">${s.count} hosts</span>
                </div>
                <div class="suggestion-body">
                    <div>${escapeHtml(s.description)}</div>
                    <div class="suggestion-pattern">Pattern: ${escapeHtml(s.pattern)}</div>
                    <div class="suggestion-members">
                        ${membersPreview.map(m => `<span class="member-tag">${escapeHtml(m)}</span>`).join('')}
                        ${moreCount > 0 ? `<span class="member-tag member-tag-more">+${moreCount} more</span>` : ''}
                    </div>
                </div>
                <div class="suggestion-actions">
                    <button class="nbe-btn nbe-btn--primary nbe-btn--sm" data-action="showCreateModal" data-index="${idx}">
                        Create Hostgroup
                    </button>
                    <button class="nbe-btn nbe-btn--secondary nbe-btn--sm" data-action="showAllMembers" data-index="${idx}">
                        View All Members
                    </button>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = `<div class="suggestions-scroll">${html}</div>`;
}

function showCreateModal(idx) {
    const suggestion = allSuggestions[idx];
    currentMembers = [...suggestion.members];

    document.getElementById('createGroupName').value = suggestion.name;
    document.getElementById('createGroupAlias').value = suggestion.description;
    document.getElementById('createMemberCount').textContent = currentMembers.length;

    renderMembersList();

    new bootstrap.Modal(document.getElementById('createModal')).show();
}

function renderMembersList() {
    const container = document.getElementById('createMembersList');
    container.innerHTML = currentMembers.map(m => `
        <div class="d-flex justify-content-between align-items-center mb-1">
            <span>${escapeHtml(m)}</span>
            <button class="nbe-btn nbe-btn--danger nbe-btn--sm" data-action="removeMember" data-member="${escapeHtml(m)}">&times;</button>
        </div>
    `).join('');
    document.getElementById('createMemberCount').textContent = currentMembers.length;
}

function removeMember(name) {
    currentMembers = currentMembers.filter(m => m !== name);
    renderMembersList();
}

async function createGroup() {
    const groupName = document.getElementById('createGroupName').value.trim();
    const alias = document.getElementById('createGroupAlias').value.trim();

    if (!groupName) {
        showToast('Please enter a group name', 'warning');
        return;
    }

    if (currentMembers.length === 0) {
        showToast('At least one member is required', 'warning');
        return;
    }

    try {
        const response = await ApiClient.post('/api/smart-grouping/create', {
            name: groupName,
            alias: alias,
            members: currentMembers
        });

        if (!response.success) {
            showToast('Error: ' + response.error, 'error');
            return;
        }

        const result = response.data;
        bootstrap.Modal.getInstance(document.getElementById('createModal')).hide();
        showToast(`Created hostgroup "${groupName}" with ${result.members_count} members`, 'success');

        // Re-analyze to update suggestions
        analyzeHosts();

    } catch (error) {
        showToast('Error creating group: ' + error.message, 'error');
    }
}

function showAllMembers(idx) {
    const suggestion = allSuggestions[idx];
    const membersList = suggestion.members.map(m => `<li>${escapeHtml(m)}</li>`).join('');
    showConfirmDialog({
        title: `Members of "${suggestion.name}"`,
        message: `<ul class="members-dialog-scroll">${membersList}</ul>`,
        confirmText: 'Close',
        type: 'info',
        showCancel: false
    });
}

// Event delegation for data-action attributes
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    switch (action) {
        case 'analyzeHosts':
            analyzeHosts();
            break;
        case 'createGroup':
            createGroup();
            break;
        case 'showCreateModal':
            showCreateModal(parseInt(actionEl.dataset.index));
            break;
        case 'showAllMembers':
            showAllMembers(parseInt(actionEl.dataset.index));
            break;
        case 'removeMember':
            removeMember(actionEl.dataset.member);
            break;
    }
});

document.addEventListener('change', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'filterSuggestions') {
        filterSuggestions();
    }
});

document.addEventListener('input', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'filterSuggestions') {
        filterSuggestions();
    }
});

})();
