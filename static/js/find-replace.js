// Find & Replace page JavaScript
// Extracted from find_replace.html

let searchTimeout = null;
let allObjects = [];
let lastSearchTerm = '';

// Load all objects on page load for fast client-side searching
document.addEventListener('DOMContentLoaded', async () => {
    const result = await ApiClient.get('/api/objects');
    if (result.success) {
        allObjects = result.data;
    } else {
        console.error('Failed to load objects:', result.error);
    }

    // Set up input listeners
    const findInput = document.getElementById('findText');
    const objectType = document.getElementById('objectType');
    const fieldName = document.getElementById('fieldName');
    const useRegex = document.getElementById('useRegex');

    if (findInput) findInput.addEventListener('input', onSearchInput);
    if (objectType) objectType.addEventListener('change', onSearchInput);
    if (fieldName) fieldName.addEventListener('input', onSearchInput);
    if (useRegex) useRegex.addEventListener('change', onSearchInput);
});

// Event delegation for data-action buttons
document.addEventListener('click', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'find-matches') {
        findMatches();
    } else if (action === 'replace-all') {
        applyReplace();
    } else if (action === 'select-suggestion') {
        selectSuggestion(actionEl.dataset.name);
    }
});

// Hide suggestions when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('#findText') && !e.target.closest('#searchSuggestions')) {
        const suggestions = document.getElementById('searchSuggestions');
        if (suggestions) suggestions.style.display = 'none';
    }
});

function onSearchInput() {
    const findText = document.getElementById('findText').value;

    // Clear previous timeout
    if (searchTimeout) {
        clearTimeout(searchTimeout);
    }

    // Hide suggestions if search is too short
    if (findText.length < 2) {
        document.getElementById('searchSuggestions').style.display = 'none';
        document.getElementById('searchStatus').textContent = '';
        return;
    }

    // Debounce the search
    document.getElementById('searchStatus').textContent = 'Searching...';
    searchTimeout = setTimeout(() => {
        performLiveSearch(findText);
    }, 150);
}

function performLiveSearch(searchTerm) {
    const objectType = document.getElementById('objectType').value;
    const fieldName = document.getElementById('fieldName').value.toLowerCase();
    const useRegex = document.getElementById('useRegex').checked;

    let pattern;
    try {
        pattern = useRegex ? new RegExp(searchTerm, 'i') : null;
    } catch (e) {
        document.getElementById('searchStatus').textContent = 'Invalid regex';
        return;
    }

    const matches = [];
    const searchLower = searchTerm.toLowerCase();

    for (const obj of allObjects) {
        if (objectType && obj.object_type !== objectType) continue;

        for (const [field, value] of Object.entries(obj.attributes)) {
            if (fieldName && field.toLowerCase() !== fieldName) continue;

            let isMatch = false;
            if (useRegex && pattern) {
                isMatch = pattern.test(value);
            } else {
                isMatch = value.toLowerCase().includes(searchLower);
            }

            if (isMatch) {
                matches.push({
                    object: obj,
                    field: field,
                    value: value
                });
                break; // Only one match per object for suggestions
            }
        }

        if (matches.length >= 20) break; // Limit suggestions
    }

    displaySuggestions(matches, searchTerm, useRegex);
    document.getElementById('searchStatus').textContent = matches.length >= 20
        ? '20+ matches (showing first 20)'
        : `${matches.length} matches`;
}

function displaySuggestions(matches, searchTerm, useRegex) {
    const container = document.getElementById('searchSuggestions');

    if (matches.length === 0) {
        container.innerHTML = '<div class="suggestion-item text-muted">No matches found</div>';
        container.style.display = 'block';
        return;
    }

    container.innerHTML = matches.map(match => {
        const highlightedValue = highlightMatch(match.value, searchTerm, useRegex);

        return `
            <div class="suggestion-item" data-action="select-suggestion" data-name="${escapeHtml(match.object.display_name)}">
                <span class="suggestion-type">${escapeHtml(match.object.object_type)}</span>
                <strong>${escapeHtml(match.object.display_name)}</strong>
                <div class="suggestion-field">
                    <code>${escapeHtml(match.field)}</code>: ${highlightedValue}
                </div>
            </div>
        `;
    }).join('');

    container.style.display = 'block';
}

function selectSuggestion(name) {
    const suggestions = document.getElementById('searchSuggestions');
    if (suggestions) suggestions.style.display = 'none';
    // Keep current search text, just trigger a full search
    findMatches();
}

async function findMatches() {
    const findText = document.getElementById('findText').value;
    if (!findText) {
        showToast('Please enter text to find', 'warning');
        return;
    }

    // Hide suggestions
    document.getElementById('searchSuggestions').style.display = 'none';

    const data = {
        find: findText,
        type: document.getElementById('objectType').value,
        field: document.getElementById('fieldName').value,
        regex: document.getElementById('useRegex').checked
    };

    document.getElementById('searchStatus').textContent = 'Searching...';

    const result = await ApiClient.post('/api/preview-replace', data);

    if (!result.success) {
        showToast(result.error || 'Search failed', 'error');
        document.getElementById('searchStatus').textContent = 'Error';
        return;
    }

    document.getElementById('matchCount').textContent = result.data.total;
    document.getElementById('replaceBtn').disabled = result.data.total === 0;
    document.getElementById('searchStatus').textContent = '';

    if (result.data.total === 0) {
        document.getElementById('matchesEmpty').style.display = 'block';
        document.getElementById('matchesEmpty').textContent = 'No matches found.';
        document.getElementById('matchesResults').style.display = 'none';
    } else {
        document.getElementById('matchesEmpty').style.display = 'none';
        document.getElementById('matchesResults').style.display = 'block';

        const container = document.getElementById('matchesResults');
        container.innerHTML = result.data.matches.map(match => `
            <div class="match-item">
                <div class="match-item-header">
                    <div>
                        <span class="match-item-type">${escapeHtml(match.object.object_type)}</span>
                        <span class="match-item-name">${escapeHtml(match.object.display_name)}</span>
                    </div>
                    <span class="match-item-file">${escapeHtml(match.object.source_file)}</span>
                </div>
                <div class="match-item-detail">
                    ${match.matched_fields.map(f => `
                        <div><span class="match-field">${escapeHtml(f.field)}</span>: ${highlightMatch(f.value, data.find, data.regex)}</div>
                    `).join('')}
                </div>
            </div>
        `).join('');
    }
}

async function applyReplace() {
    const replaceText = document.getElementById('replaceText').value;

    const confirmed = await showConfirmDialog({
        title: 'Confirm Replace',
        message: `Replace all matches with "${replaceText}"? A backup will be created first.`,
        confirmText: 'Replace All',
        type: 'warning'
    });
    if (!confirmed) return;

    const data = {
        find: document.getElementById('findText').value,
        replace: replaceText,
        type: document.getElementById('objectType').value,
        field: document.getElementById('fieldName').value,
        regex: document.getElementById('useRegex').checked
    };

    const result = await ApiClient.post('/api/apply-replace', data);

    if (!result.success) {
        showToast(result.error || 'Replace failed', 'error');
        return;
    }

    showToast(`Made ${result.data.replacements} replacements. Backup: ${result.data.backup}`, 'success');
    location.reload();
}

function highlightMatch(text, find, isRegex) {
    const escaped = escapeHtml(text);
    try {
        const pattern = isRegex ? new RegExp(find, 'gi') : new RegExp(escapeRegex(find), 'gi');
        return escaped.replace(pattern, '<mark>$&</mark>');
    } catch (e) {
        return escaped;
    }
}
