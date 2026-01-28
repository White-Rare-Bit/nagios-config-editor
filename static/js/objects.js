// Browse Objects page JavaScript
// Extracted from objects.html
// Note: Requires `objects` array to be set before loading this file

let currentEditIndex = -1;
let editedAttributes = {};

function filterObjects() {
    const search = document.getElementById('objectSearch').value.toLowerCase();
    document.querySelectorAll('.object-row').forEach(row => {
        const name = row.dataset.name;
        row.style.display = name.includes(search) ? '' : 'none';
    });
}

function syntaxHighlight(obj) {
    let html = `<div class="file-info"># File: ${escapeHtml(obj.source_file)}</div>`;
    html += `<div class="file-info"># Line: ${obj.line_number}</div>\n`;
    html += `<span class="keyword">define</span> <span class="object-type">${escapeHtml(obj.object_type)}</span> <span class="brace">{</span>\n`;

    for (const [key, value] of Object.entries(obj.attributes)) {
        const paddedKey = key.padEnd(30);
        html += `    <span class="attr-name">${escapeHtml(paddedKey)}</span> <span class="attr-value">${escapeHtml(value)}</span>\n`;
    }

    html += `<span class="brace">}</span>`;
    return html;
}

function showObjectDetails(index) {
    const obj = objects[index];
    currentEditIndex = index;
    document.getElementById('objectModalTitle').textContent =
        `${obj.object_type}: ${obj.display_name}`;

    document.getElementById('objectModalContent').innerHTML = syntaxHighlight(obj);
    new bootstrap.Modal(document.getElementById('objectModal')).show();
}

function switchToEdit() {
    bootstrap.Modal.getInstance(document.getElementById('objectModal')).hide();
    showEditModal(currentEditIndex);
}

function showEditModal(index) {
    const obj = objects[index];
    currentEditIndex = index;
    editedAttributes = {...obj.attributes};

    document.getElementById('editModalTitle').textContent =
        `Edit ${obj.object_type}: ${obj.display_name}`;
    document.getElementById('editModalFile').textContent =
        `File: ${obj.source_file} | Line: ${obj.line_number}`;

    renderEditableAttributes();
    new bootstrap.Modal(document.getElementById('editModal')).show();
}

function renderEditableAttributes() {
    const container = document.getElementById('editableAttributes');
    let html = '';

    for (const [key, value] of Object.entries(editedAttributes)) {
        html += `
            <div class="attr-row" data-attr="${escapeHtml(key)}">
                <label>${escapeHtml(key)}</label>
                <input type="text" class="form-control form-control-sm"
                       value="${escapeHtml(value)}"
                       data-attr-name="${escapeHtml(key)}">
                <button class="nbe-btn nbe-btn--danger nbe-btn--sm btn-remove"
                        data-action="remove-attribute" data-attr-name="${escapeHtml(key)}"
                        title="Remove attribute">
                    &times;
                </button>
            </div>
        `;
    }

    container.innerHTML = html;
}

function updateAttribute(name, value) {
    editedAttributes[name] = value;
}

async function removeAttribute(name) {
    const confirmed = await showConfirmDialog({
        title: 'Remove Attribute',
        message: `Remove attribute "${name}"?`,
        confirmText: 'Remove',
        type: 'warning'
    });
    if (confirmed) {
        delete editedAttributes[name];
        renderEditableAttributes();
    }
}

function addAttribute() {
    const nameInput = document.getElementById('newAttrName');
    const valueInput = document.getElementById('newAttrValue');
    const name = nameInput.value.trim();
    const value = valueInput.value.trim();

    if (!name) {
        showToast('Please enter an attribute name', 'warning');
        return;
    }

    if (name in editedAttributes) {
        showToast('Attribute already exists', 'warning');
        return;
    }

    editedAttributes[name] = value;
    renderEditableAttributes();

    nameInput.value = '';
    valueInput.value = '';
}

async function saveObject() {
    const obj = objects[currentEditIndex];

    const result = await ApiClient.post('/api/object/update', {
        source_file: obj.source_file,
        line_number: obj.line_number,
        object_type: obj.object_type,
        original_attributes: obj.attributes,
        new_attributes: editedAttributes
    }, { silent: false });

    if (!result.success) {
        return; // ApiClient already showed error toast
    }

    // Update local object
    objects[currentEditIndex].attributes = {...editedAttributes};
    objects[currentEditIndex].display_name = result.data.display_name || obj.display_name;

    // Update the table row
    const row = document.querySelector(`tr[data-index="${currentEditIndex}"]`);
    if (row) {
        row.querySelector('td:nth-child(2) strong').textContent = result.data.display_name || obj.display_name;
    }

    bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
    showToast('Object saved successfully!', 'success');
}

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Search input with debounced filtering
    const searchInput = document.getElementById('objectSearch');
    if (searchInput) {
        searchInput.addEventListener('keyup', filterObjects);
    }

    // Event delegation for data-action elements
    document.addEventListener('click', function(e) {
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;

        const action = actionEl.dataset.action;
        const index = actionEl.dataset.index;

        switch (action) {
            case 'edit-object':
                if (index !== undefined) showEditModal(parseInt(index, 10));
                break;
            case 'view-object':
                if (index !== undefined) showObjectDetails(parseInt(index, 10));
                break;
            case 'switch-to-edit':
                switchToEdit();
                break;
            case 'add-attribute':
                addAttribute();
                break;
            case 'save-object':
                saveObject();
                break;
            case 'remove-attribute':
                const attrName = actionEl.dataset.attrName;
                if (attrName) removeAttribute(attrName);
                break;
        }
    });

    // Event delegation for attribute value changes
    document.addEventListener('change', function(e) {
        if (e.target.dataset.attrName && e.target.closest('.attr-row')) {
            updateAttribute(e.target.dataset.attrName, e.target.value);
        }
    });
});
