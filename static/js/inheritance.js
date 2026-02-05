// Inheritance Viewer page JavaScript
// Extracted from inheritance.html

let allObjects = [];
let selectedObject = null;

async function loadObjects() {
    const objectType = document.getElementById('objectType').value;
    if (!objectType) {
        document.getElementById('objectList').innerHTML = `
            <div class="text-muted text-center p-3">
                Select an object type to see the list.
            </div>
        `;
        return;
    }

    const result = await ApiClient.get(`/api/inheritance/list/${objectType}`);
    if (result.success) {
        allObjects = result.data;
        displayObjectList(allObjects);
    } else {
        console.error('Error loading objects:', result.error);
    }
}

function displayObjectList(objects) {
    const container = document.getElementById('objectList');

    if (objects.length === 0) {
        container.innerHTML = '<div class="text-muted text-center p-3">No objects found.</div>';
        return;
    }

    // Sort: templates first, then by name
    objects.sort((a, b) => {
        if (a.is_template !== b.is_template) return a.is_template ? -1 : 1;
        return a.name.localeCompare(b.name);
    });

    const html = objects.map(obj => `
        <div class="object-list-item" onclick="selectObject('${escapeJs(obj.name)}')">
            <div>
                ${obj.is_template ? '<span class="badge bg-warning template-badge">template</span> ' : ''}
                <span>${escapeHtml(obj.name)}</span>
            </div>
            ${obj.uses.length > 0 ? `<small class="object-list-muted">uses: ${obj.uses.map(u => escapeHtml(u)).join(', ')}</small>` : ''}
        </div>
    `).join('');

    container.innerHTML = html;
}

function filterObjectList() {
    const search = document.getElementById('searchBox').value.toLowerCase();
    const filtered = allObjects.filter(obj =>
        obj.name.toLowerCase().includes(search)
    );
    displayObjectList(filtered);
}

async function selectObject(name) {
    const objectType = document.getElementById('objectType').value;
    selectedObject = name;

    // Update UI to show selection
    document.querySelectorAll('.object-list-item').forEach(item => {
        item.classList.remove('active');
        if (item.textContent.includes(name)) {
            item.classList.add('active');
        }
    });

    const result = await ApiClient.get(`/api/inheritance/${objectType}/${encodeURIComponent(name)}`);

    if (!result.success) {
        showToast(result.error || 'Failed to load inheritance', 'error');
        return;
    }

    displayInheritanceChain(result.data.chain);
    displayResolvedAttributes(result.data.resolved_attributes, result.data.chain.name);
}

function displayInheritanceChain(chain) {
    document.getElementById('chainTitle').textContent = `Inheritance Chain: ${chain.name}`;

    function renderNode(node, isRoot = false) {
        const headerClass = node.error ? 'has-error' :
                           (node.is_template ? 'is-template' : '');

        if (node.error) {
            return `
                <div class="tree-node ${isRoot ? 'tree-root' : ''}" style="position: relative;">
                    <div class="node-header has-error">
                        <strong>${escapeHtml(node.name)}</strong>
                        <span class="text-danger ms-2">(${node.error})</span>
                    </div>
                </div>
            `;
        }

        const attrsCount = Object.keys(node.attributes).length;
        let attrsHtml = '';
        if (attrsCount > 0) {
            const attrsList = Object.entries(node.attributes)
                .filter(([k]) => !['use', 'name', 'register'].includes(k))
                .slice(0, 5)
                .map(([k, v]) => `${k}: ${v.length > 30 ? v.substring(0, 30) + '...' : v}`)
                .join('<br>');
            const moreCount = Math.max(0, attrsCount - 5);
            attrsHtml = `
                <div class="node-attrs">
                    ${attrsList}
                    ${moreCount > 0 ? `<br><em>... and ${moreCount} more</em>` : ''}
                </div>
            `;
        }

        const parentsHtml = node.parents.length > 0 ?
            node.parents.map(p => renderNode(p)).join('') : '';

        return `
            <div class="tree-node ${isRoot ? 'tree-root' : ''}" style="position: relative;">
                <div class="node-header ${headerClass}">
                    ${node.is_template ? '<span class="badge bg-warning template-badge me-1">template</span>' : ''}
                    <strong>${escapeHtml(node.name)}</strong>
                    <small class="text-muted ms-2">(${attrsCount} attrs)</small>
                </div>
                ${attrsHtml}
                ${parentsHtml}
            </div>
        `;
    }

    document.getElementById('chainContainer').innerHTML = `
        <div class="inheritance-tree">
            ${renderNode(chain, true)}
        </div>
    `;
}

function displayResolvedAttributes(resolved, selfName) {
    const container = document.getElementById('resolvedContainer');

    if (Object.keys(resolved).length === 0) {
        container.innerHTML = '<div class="text-muted text-center p-4">No attributes defined.</div>';
        return;
    }

    // Sort attributes alphabetically
    const sortedAttrs = Object.entries(resolved).sort((a, b) =>
        a[0].localeCompare(b[0])
    );

    const html = `
        <div style="max-height: 400px; overflow-y: auto;">
            <div class="resolved-attr" style="background: #f8f9fa; font-weight: 600;">
                <div class="attr-name">Attribute</div>
                <div class="attr-value">Value</div>
                <div class="attr-source">Source</div>
            </div>
            ${sortedAttrs.map(([name, info]) => `
                <div class="resolved-attr">
                    <div class="attr-name">${escapeHtml(name)}</div>
                    <div class="attr-value">${escapeHtml(info.value)}</div>
                    <div class="attr-source ${info.source === selfName ? 'source-self' : 'source-inherited'}">
                        ${info.source === selfName ? 'self' : escapeHtml(info.source)}
                    </div>
                </div>
            `).join('')}
        </div>
    `;

    container.innerHTML = html;
}

// Event delegation for data-action attributes
document.addEventListener('change', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'loadObjects') {
        loadObjects();
    }
});

document.addEventListener('input', function(e) {
    const actionEl = e.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'filterObjectList') {
        filterObjectList();
    }
});
