// Validate Configuration page JavaScript
// Extracted from validate.html

(function() {
    'use strict';

    // Constants
    const CONFIG = {
        TIMEOUT_MS: 60000
    };

    // Cached DOM elements (initialized on DOMContentLoaded)
    const elements = {};

    function cacheElements() {
        elements.nagiosStatus = document.getElementById('nagiosStatus');
        elements.validateBtn = document.getElementById('validateBtn');
        elements.errorCount = document.getElementById('errorCount');
        elements.warningCount = document.getElementById('warningCount');
        elements.validationSummary = document.getElementById('validationSummary');
        elements.summaryContent = document.getElementById('summaryContent');
        elements.validationEmpty = document.getElementById('validationEmpty');
        elements.validationErrors = document.getElementById('validationErrors');
        elements.errorList = document.getElementById('errorList');
        elements.validationWarnings = document.getElementById('validationWarnings');
        elements.warningList = document.getElementById('warningList');
        elements.validationRaw = document.getElementById('validationRaw');
        elements.rawOutput = document.getElementById('rawOutput');
    }

    document.addEventListener('DOMContentLoaded', () => {
        cacheElements();
        checkNagiosAvailable();

        // Event delegation for data-action elements
        document.addEventListener('click', function(e) {
            const actionEl = e.target.closest('[data-action]');
            if (actionEl && actionEl.dataset.action === 'runValidation') {
                runValidation();
            }
        });
    });

    async function checkNagiosAvailable() {
        const statusDiv = elements.nagiosStatus;
        const validateBtn = elements.validateBtn;

    const result = await ApiClient.get('/api/validate/check');

    if (!result.success) {
        statusDiv.className = 'nagios-status unavailable';
        statusDiv.innerHTML = `Error checking Nagios: ${escapeHtml(result.error)}`;
        return;
    }

    if (result.data.available) {
        statusDiv.className = 'nagios-status available';
        statusDiv.innerHTML = `
            <strong>Nagios binary found</strong><br>
            <small>${escapeHtml(result.data.nagios_bin)}</small>
        `;
        validateBtn.disabled = false;
    } else {
        statusDiv.className = 'nagios-status unavailable';
        statusDiv.innerHTML = `
            <strong>Nagios binary not found</strong><br>
            <small>${escapeHtml(result.data.message)}</small><br>
            <small class="dialog-info-text">Set NAGIOS_BIN environment variable to specify location.</small>
        `;
        validateBtn.disabled = true;
    }
}

async function runValidation() {
    const btn = elements.validateBtn;
    btn.disabled = true;
    btn.textContent = 'Validating...';

    try {
        // Race between API call and timeout
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error('TIMEOUT')), CONFIG.TIMEOUT_MS);
        });

        const result = await Promise.race([
            ApiClient.post('/api/validate'),
            timeoutPromise
        ]);

        if (!result.success) {
            showToast(result.error || 'Validation failed', 'error');
            return;
        }

        displayValidationResult(result.data);
    } catch (error) {
        if (error.message === 'TIMEOUT') {
            showToast('Validation timed out. The server may be busy.', 'warning');
        } else {
            showToast('Error: ' + error.message, 'error');
        }
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Validation';
    }
}

function displayValidationResult(result) {
    // Update counts
    elements.errorCount.textContent = `${result.total_errors} errors`;
    elements.warningCount.textContent = `${result.total_warnings} warnings`;

    // Update summary
    elements.validationSummary.classList.remove('u-hidden');

    if (result.success) {
        elements.summaryContent.innerHTML = '<div class="validation-summary success"><strong>Configuration is valid!</strong></div>';
    } else {
        elements.summaryContent.innerHTML = '<div class="validation-summary error"><strong>Configuration has errors!</strong></div>';
    }

    // Hide empty message
    elements.validationEmpty.classList.add('u-hidden');

    // Show errors
    if (result.errors.length > 0) {
        elements.validationErrors.classList.remove('u-hidden');
        elements.errorList.innerHTML = result.errors.map(err => `
            <div class="validate-issue-item validate-issue-item--error" role="listitem">
                ${err.file ? `<strong>${escapeHtml(err.file)}</strong> line ${err.line}<br>` : ''}
                ${escapeHtml(err.message)}
            </div>
        `).join('');
    } else {
        elements.validationErrors.classList.add('u-hidden');
    }

    // Show warnings
    if (result.warnings.length > 0) {
        elements.validationWarnings.classList.remove('u-hidden');
        elements.warningList.innerHTML = result.warnings.map(warn => `
            <div class="validate-issue-item validate-issue-item--warning" role="listitem">
                ${escapeHtml(warn.message)}
            </div>
        `).join('');
    } else {
        elements.validationWarnings.classList.add('u-hidden');
    }

    // Show raw output
    elements.validationRaw.classList.remove('u-hidden');
    elements.rawOutput.textContent = result.raw_output;
}

})(); // End IIFE
