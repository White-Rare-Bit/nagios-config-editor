// Validate Configuration page JavaScript
// Extracted from validate.html

document.addEventListener('DOMContentLoaded', () => {
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
    const statusDiv = document.getElementById('nagiosStatus');
    const validateBtn = document.getElementById('validateBtn');

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
    const btn = document.getElementById('validateBtn');
    btn.disabled = true;
    btn.textContent = 'Validating...';

    try {
        // Race between API call and 60-second timeout
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error('TIMEOUT')), 60000);
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
    document.getElementById('errorCount').textContent = `${result.total_errors} errors`;
    document.getElementById('warningCount').textContent = `${result.total_warnings} warnings`;

    // Update summary
    const summaryDiv = document.getElementById('validationSummary');
    const summaryContent = document.getElementById('summaryContent');
    summaryDiv.classList.remove('u-hidden');

    if (result.success) {
        summaryContent.innerHTML = '<div class="validation-summary success"><strong>Configuration is valid!</strong></div>';
    } else {
        summaryContent.innerHTML = '<div class="validation-summary error"><strong>Configuration has errors!</strong></div>';
    }

    // Hide empty message
    document.getElementById('validationEmpty').classList.add('u-hidden');

    // Show errors
    const errorsDiv = document.getElementById('validationErrors');
    const errorList = document.getElementById('errorList');
    if (result.errors.length > 0) {
        errorsDiv.classList.remove('u-hidden');
        errorList.innerHTML = result.errors.map(err => `
            <div class="validate-issue-item validate-issue-item--error" role="listitem">
                ${err.file ? `<strong>${escapeHtml(err.file)}</strong> line ${err.line}<br>` : ''}
                ${escapeHtml(err.message)}
            </div>
        `).join('');
    } else {
        errorsDiv.classList.add('u-hidden');
    }

    // Show warnings
    const warningsDiv = document.getElementById('validationWarnings');
    const warningList = document.getElementById('warningList');
    if (result.warnings.length > 0) {
        warningsDiv.classList.remove('u-hidden');
        warningList.innerHTML = result.warnings.map(warn => `
            <div class="validate-issue-item validate-issue-item--warning" role="listitem">
                ${escapeHtml(warn.message)}
            </div>
        `).join('');
    } else {
        warningsDiv.classList.add('u-hidden');
    }

    // Show raw output
    document.getElementById('validationRaw').classList.remove('u-hidden');
    document.getElementById('rawOutput').textContent = result.raw_output;
}
