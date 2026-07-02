/* global ollama_enabled ollamaModel */

let isRequestPending = false;
const LOGS_PER_PAGE = 5;

document.getElementById('onedrive-settings-form').addEventListener('submit', async function(event) {
    event.preventDefault();
    const submitButton = this.querySelector('button[type="submit"]');
    const originalButtonText = submitButton.textContent;

    submitButton.disabled = true;
    submitButton.textContent = 'Saving...';

    const formData = new FormData(this);
    const data = {};
    formData.forEach((value, key) => {
        data[key] = value.trim();
    });

    try {
        const response = await fetch('/api/onedrive-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });

        if (response.ok) {
            const result = await response.json();
            alert(result.message || 'Settings saved successfully.');
        } else {
            const result = await response.json().catch(() => ({}));
            alert(result.error || 'An error occurred while saving settings.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('An unexpected error occurred. Please try again.');
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = originalButtonText;
    }
});


// Show warning if user leaves site
window.addEventListener('beforeunload', function(e) {
    if (isRequestPending) {
        console.log('Request is pending, preventing page unload.');
        e.preventDefault();
    }
});


document.getElementById('openai-form').addEventListener('submit', async function(event) {
    event.preventDefault();
    const confirmed = confirm('Enabling OpenAI file naming will disable other file naming services. Do you want to continue?');
    if (!confirmed) {
        this.reset();
        return;
    }
    isRequestPending = true;
    const submitButton = this.querySelector('button[type="submit"]');
    const originalButtonText = submitButton.textContent;

    submitButton.disabled = true;
    submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Testing key, please wait...';

    const formData = new FormData(this);
    const data = {};
    formData.forEach((value, key) => {
        data[key] = value.trim();
    });

    try {
        const response = await fetch('/api/openai-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });

        if (response.ok) {
            const result = await response.json();
            alert(result.message || 'OpenAI saved successfully.');
            window.location.reload();
        } else {
            const result = await response.json().catch(() => ({}));
            alert(result.error || 'An error occurred while saving settings.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('An unexpected error occurred. Please try again.');
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = originalButtonText;
        isRequestPending = false;
    }
});

/* exported deleteOpenAi */
function deleteOpenAi() {
    const deleteButton = document.getElementById('delete-openai-button');
    const originalButtonText = deleteButton.textContent;

    deleteButton.disabled = true;
    deleteButton.textContent = 'Deleting...';

    fetch('/api/openai-settings', {
        method: 'DELETE'
    })
        .then((response) => {
            if (response.ok) {
                alert('OpenAI settings deleted successfully.');
                window.location.reload();
            } else {
                alert('An error occurred while deleting OpenAI settings.');
            }
        })
        .catch((error) => {
            console.error('Error:', error);
            alert('An unexpected error occurred. Please try again.');
        })
        .finally(() => {
            deleteButton.disabled = false;
            deleteButton.textContent = originalButtonText;
        });
}

// Function to update the URL parameter based on the active tab
function updateTabUrlParameter(tabId) {
    const url = new URL(window.location);
    url.searchParams.set('tab', tabId);
    window.history.replaceState({}, '', url);
}

// Add event listeners to tabs to update the URL parameter on click
document.querySelectorAll('.nav-link').forEach(tab => {
    tab.addEventListener('click', function() {
        const tabId = this.getAttribute('id');
        updateTabUrlParameter(tabId);
    });
});

// On page load, activate the tab based on the URL parameter
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const activeTabId = urlParams.get('tab');
    if (activeTabId) {
        const activeTab = document.getElementById(activeTabId);
        if (activeTab) {
            activeTab.click();
        }
    }

    try {
        const fileNamingDisabled = urlParams.get('disable-file-naming');
        if (fileNamingDisabled === 'success') {
            showStatusBox('File naming disabled successfully. ScanSync will use default file names.', 'alert-success');
        } else if (fileNamingDisabled === 'already-disabled') {
            showStatusBox('File naming is already disabled. ScanSync will use default file names.', 'alert-info');
        }
    } catch (error) {
        console.error('Error processing URL parameters:', error);
    }


    try {
        document.querySelectorAll('input[name="file_naming_method"]').forEach(el => {
            el.addEventListener('change', function() {
                document.getElementById('openai-options').style.display = this.value === 'openai' ? 'block' : 'none';
                document.getElementById('ollama-options').style.display = this.value === 'ollama' ? 'block' : 'none';
                document.getElementById('none-options').style.display = this.value === 'none' ? 'block' : 'none';
            });
        });
    } catch (error) {
        console.error('Error attaching file_naming_method change listeners:', error);
    }

    try {
        // Initialise the log tables. Each table lazily loads its data the first
        // time its accordion is expanded (see createLogsTable).
        initLogTables();
    } catch (error) {
        console.error('Error initialising log tables:', error);
    }

    if (ollama_enabled) {
        // Auto-click Ollama connect button if it exists
        try {
            document.getElementById('ollama-connect-btn').click();
        } catch (error) {
            console.error('Error auto-clicking Ollama connect button:', error);
        }
    }
});

/* exported openLoginPopup */
function openLoginPopup() {
    document.getElementById("onedrive-container").classList.add("d-none");
    document.getElementById("onedrive-loading-spinner").classList.remove("d-none");
    const popup = window.open('/login', 'popup', 'width=600,height=600');
    const timer = setInterval(() => {
        if (popup.closed) {
            clearInterval(timer);
            console.log('Popup closed');
            window.location.reload();
        }
    }, 1000);
}

document.getElementById('ollama-connect-btn').addEventListener('click', async function() {
    const scheme = document.getElementById('ollama_server_scheme').value.trim();
    const schemeDropdown = document.getElementById('ollama_server_scheme');
    const urlInput = document.getElementById('ollama_server_address');
    const portInput = document.getElementById('ollama_server_port');
    const url = document.getElementById('ollama_server_address').value.trim().replace(/\/$/, '');
    const port = document.getElementById('ollama_server_port').value.trim();
    const connectBtn = this;
    const spinner = document.getElementById('ollama-connect-spinner');
    const btnText = document.getElementById('ollama-connect-btn-text');
    const versionInfo = document.getElementById('ollama-version-info');
    const modelsSection = document.getElementById('ollama-models-section');
    const modelSelect = document.getElementById('ollama_model_select');
    const modelInfo = document.getElementById('ollama-model-info');
    const errorDiv = document.getElementById('ollama-error');
    const saveBtn = document.getElementById('ollama-save-btn') || document.getElementById('ollama-delete-btn');
    errorDiv.classList.add('d-none');
    versionInfo.classList.add('d-none');
    modelsSection.style.display = 'none';
    saveBtn.disabled = true;
    modelSelect.innerHTML = '';
    modelInfo.textContent = '';
    schemeDropdown.readOnly = true;
    urlInput.readOnly = true;
    portInput.readOnly = true;
    connectBtn.disabled = true;

    const connectBtnHTMLBefore = connectBtn.innerHTML;
    btnText.textContent = '';
    spinner.classList.remove('d-none');

    try {
        // Check version
        const versionResp = await fetch(`/settings/ollama/version?scheme=${encodeURIComponent(scheme)}&url=${encodeURIComponent(url)}&port=${encodeURIComponent(port)}`);
        if (!versionResp.ok) {
            throw new Error('Could not connect to Ollama server. Is the server running and the URL correct?');
        }
        const versionData = await versionResp.json();
        versionInfo.innerHTML = `<span class="text-success me-2">&#10003;</span>Detected Ollama version: ${versionData.version || 'unknown'}`;
        versionInfo.classList.remove('d-none');

        // Get models
        const tagsResp = await fetch(`/settings/ollama/models?scheme=${encodeURIComponent(scheme)}&url=${encodeURIComponent(url)}&port=${encodeURIComponent(port)}`);
        if (!tagsResp.ok) throw new Error('Could not fetch models from Ollama.');
        const tagsData = await tagsResp.json();
        if (!tagsData.models || tagsData.models.length === 0) {
            throw new Error('No models found on Ollama server.');
        }
        // Populate models
        tagsData.models.forEach(model => {
            const opt = document.createElement('option');
            opt.value = model.name;
            opt.textContent = `${model.name} (${model.details?.parameter_size || 'n/a'})`;
            opt.dataset.info = JSON.stringify(model);
            modelSelect.appendChild(opt);
        });
        modelsSection.style.display = 'block';
        // Show info for first model
        const showModelInfo = (model) => {
            let modifiedStr = model.modified_at;
            try {
                if (modifiedStr) {
                    const date = new Date(modifiedStr);
                    if (!isNaN(date.getTime())) {
                        // Format nach Locale
                        modifiedStr = date.toLocaleString(undefined, {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit'
                        });
                    }
                }
            } catch (e) {
                console.log(e);
            }
            modelInfo.innerHTML = `
                <strong>Name:</strong> ${model.name}<br>
                <strong>Model:</strong> ${model.model}<br>
                <strong>Modified:</strong> ${modifiedStr}<br>
                <strong>Parameter size:</strong> ${model.details?.parameter_size || 'n/a'}
            `;
        };
        showModelInfo(tagsData.models[0]);
        modelSelect.onchange = function() {
            const selected = tagsData.models.find(m => m.name === this.value);
            if (selected) showModelInfo(selected);
        };
        if (typeof ollamaModel !== 'undefined' && ollamaModel) {
            let found = false;
            for (let i = 0; i < modelSelect.options.length; i++) {
                if (modelSelect.options[i].value === ollamaModel) {
                    modelSelect.selectedIndex = i;
                    showModelInfo(tagsData.models.find(m => m.name === ollamaModel));
                    found = true;
                    break;
                }
            }
            if (!found) {
                const opt = document.createElement('option');
                opt.value = ollamaModel;
                opt.textContent = `${ollamaModel} (Not available)`;
                opt.selected = true;
                opt.dataset.info = JSON.stringify({
                    name: ollamaModel,
                    model: 'N/A',
                    modified_at: 'N/A',
                    details: { parameter_size: 'N/A' }
                });
                modelSelect.appendChild(opt);
                modelInfo.innerHTML = `
                    <strong>Name:</strong> ${ollamaModel}<br>
                    <strong>Model:</strong> N/A<br>
                    <strong>Modified:</strong> N/A<br>
                    <strong>Parameter size:</strong> N/A
                `;
            }
        }
        saveBtn.disabled = false;
    } catch (err) {
        if (err instanceof TypeError) {
            console.error('Network error or invalid URL:', err);
            errorDiv.textContent = 'Network error or invalid URL. Please check your Ollama server settings and spelling.';
        } else {
            errorDiv.textContent = err.message;
            console.error('Failed connecting to Ollama:', err);
        }
        errorDiv.classList.remove('d-none');
        schemeDropdown.readOnly = false;
        urlInput.readOnly = false;
        portInput.readOnly = false;
        connectBtn.disabled = false;
    } finally {
        btnText.innerHTML = connectBtnHTMLBefore;
        spinner.classList.add('d-none');
        const deletebtn = document.getElementById('ollama-delete-btn');
        if (deletebtn) {
            deletebtn.disabled = false;
        }
    }
    if (!ollama_enabled) {
        isRequestPending = true;
    }
});

/* exported disableFileNaming */
function disableFileNaming() {
    fetch('/api/disable-file-naming', {
        method: 'POST'
    })
        .then(async response => {
            const message = await response.text();
            if (response.ok) {
                console.log('File naming disabled successfully:', message);
                if (response.status === 200) {
                    window.location.href = '/settings?disable-file-naming=success&tab=file-naming-tab';
                } else if (response.status === 204) {
                    window.location.href = '/settings?disable-file-naming=already-disabled&tab=file-naming-tab';
                }
            } else {
                console.error('Error disabling file naming:', message);
                showStatusBox(message || 'An error occurred while disabling file naming.', 'alert-danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showStatusBox('An unexpected error occurred. Please try again.', 'alert-danger');
        });
}

function showStatusBox(message, type) {
    let statusBox = document.getElementById('file-naming-status');
    if (!statusBox) {
        alert(message);
        return;
    }
    statusBox.className = `alert ${type}`;
    statusBox.textContent = message;
    statusBox.style.display = 'block';
    if (!statusBox.classList.contains('alert-danger')) {
        setTimeout(() => {
            statusBox.style.display = 'none';
            const url = new URL(window.location);
            url.searchParams.delete('disable-file-naming');
            window.history.replaceState({}, '', url);
        }, 5000);
    }
}


document.getElementById('ollama-form').addEventListener('submit', async function(event) {
    event.preventDefault();
    if (!ollama_enabled) {
        const confirmed = confirm('Enabling Ollama file naming will disable other file naming services. Do you want to continue?');
        if (!confirmed) {
            this.reset();
            return;
        }
    }

    isRequestPending = true;
    const submitButton = document.getElementById('ollama-save-btn') || document.getElementById('ollama-refresh-models-btn');
    const errBox = document.getElementById('ollama-error');
    const disableOllamaButton = document.getElementById('ollama-delete-btn');
    const submitButtonSpinner = document.getElementById('ollama-save-spinner');
    const ollamaSaveBtnText = document.getElementById('ollama-save-btn-text');
    const originalButtonHtml = ollamaSaveBtnText.innerHTML;
    disableOllamaButton && (disableOllamaButton.disabled = true);

    submitButton.disabled = true;
    console.log('Submitting Ollama settings form');
    submitButtonSpinner && (submitButtonSpinner.classList.remove('d-none'));
    ollamaSaveBtnText.textContent = 'Saving...';

    const formData = new FormData(this);
    const data = {};
    formData.forEach((value, key) => {
        data[key] = value.trim();
    });

    try {
        const response = await fetch('/api/ollama-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });

        if (response.ok) {
            const result = await response.json();
            alert(result.message || 'Ollama settings saved successfully.');
            window.location.reload();
        } else {
            const result = await response.json().catch(() => ({}));
            errBox.textContent = result.error || 'An error occurred while saving Ollama settings.';
            errBox.classList.remove('d-none');
        }
    } catch (error) {
        console.error('Error:', error);
        errBox.textContent = 'An unexpected error occurred. Please try again.';
        errBox.classList.remove('d-none');
    } finally {
        submitButton.disabled = false;
        ollamaSaveBtnText.innerHTML = originalButtonHtml;
        submitButtonSpinner && (submitButtonSpinner.classList.add('d-none'));
        isRequestPending = false;
        disableOllamaButton && (disableOllamaButton.disabled = false);
    }
});

/* exported deleteOllama */
function deleteOllama() {
    const deleteButton = document.getElementById('ollama-delete-btn');
    const originalButtonHtml = deleteButton.innerHTML;

    deleteButton.disabled = true;
    deleteButton.textContent = 'Deleting...';

    fetch('/api/ollama-settings', {
        method: 'DELETE'
    })
        .then((response) => {
            if (response.ok) {
                alert('Ollama file naming disabled successfully.');
                window.location.reload();
            } else {
                alert('An error occurred while deleting Ollama settings.');
            }
        })
        .catch((error) => {
            console.error('Error:', error);
            alert('An unexpected error occurred. Please try again.');
        })
        .finally(() => {
            deleteButton.disabled = false;
            deleteButton.innerHTML = originalButtonHtml;
        });
}

// Factory that wires up a paginated, filterable logs table. Each instance owns
// its own page/filter state and lazily loads data the first time its accordion
// is expanded. This is shared by the File Naming, OCR and Sync log tables.
function createLogsTable(config) {
    let currentPage = 1;
    let currentFilter = 'all';

    const refreshBtn = document.getElementById(config.refreshBtnId);
    const filterSelect = document.getElementById(config.filterId);
    const collapse = document.getElementById(config.collapseId);
    let loaded = false;

    function load(page = currentPage, filter = currentFilter) {
        currentPage = page;
        currentFilter = filter;
        if (refreshBtn) {
            refreshBtn.disabled = true;
        }
        let url = `${config.endpoint}?page=${page}&per_page=${LOGS_PER_PAGE}`;
        if (filter && filter !== 'all') {
            url += `&filter=${filter}`;
        }
        fetch(url)
            .then(res => res.json())
            .then(data => render(data.logs, data.page, data.total_pages))
            .catch(() => render([], 1, 1))
            .finally(() => {
                if (refreshBtn) {
                    refreshBtn.disabled = false;
                }
            });
    }

    function render(logs, page, totalPages) {
        const table = document.getElementById(config.tableId);
        const tbody = table.querySelector('tbody');
        const empty = document.getElementById(config.emptyId);
        const pagination = document.getElementById(config.paginationId);
        tbody.innerHTML = '';
        if (!logs || logs.length === 0) {
            empty.classList.remove('d-none');
            table.classList.add('d-none');
            pagination.innerHTML = '';
            return;
        }
        empty.classList.add('d-none');
        table.classList.remove('d-none');
        logs.forEach((log) => {
            tbody.innerHTML += config.renderRow(log);
        });
        // Attach click handlers to show the full (untruncated) text. The full
        // value is stored in a data attribute rather than an inline onclick to
        // avoid embedding untrusted content in a JavaScript string literal.
        tbody.querySelectorAll('.js-show-full').forEach((el) => {
            el.addEventListener('click', () => alert(el.getAttribute('data-fulltext')));
        });
        renderPagination(pagination, page, totalPages, load, () => currentFilter);
    }

    if (refreshBtn) {
        refreshBtn.onclick = () => load(currentPage, currentFilter);
    }
    if (filterSelect) {
        filterSelect.addEventListener('change', function() {
            load(1, this.value);
        });
    }
    if (collapse) {
        collapse.addEventListener('show.bs.collapse', function() {
            if (!loaded) {
                load();
                loaded = true;
            }
        });
    }

    return { load };
}

function initLogTables() {
    createLogsTable({
        endpoint: '/api/file-naming-logs',
        collapseId: 'logsCollapse',
        tableId: 'logs-table',
        emptyId: 'logs-empty',
        paginationId: 'logs-pagination',
        filterId: 'logs-success-filter',
        refreshBtnId: 'refresh-logs-btn',
        renderRow: (log) => `
            <tr>
                <td>${log.id}</td>
                <td>${getStatusBadge(log.file_naming_status)}</td>
                <td>${renderFileNameCell(log.file_name)}</td>
                <td>${escapeHtml(log.method)}</td>
                <td>${escapeHtml(log.model)}</td>
                <td><span class="text-secondary">${escapeHtml(log.started)}</span></td>
                <td><span class="text-secondary">${escapeHtml(log.finished)}</span></td>
                <td>${renderErrorCell(log.error_description)}</td>
            </tr>
        `
    });

    createLogsTable({
        endpoint: '/api/ocr-logs',
        collapseId: 'ocr-logsCollapse',
        tableId: 'ocr-logs-table',
        emptyId: 'ocr-logs-empty',
        paginationId: 'ocr-logs-pagination',
        filterId: 'ocr-logs-success-filter',
        refreshBtnId: 'refresh-ocr-logs-btn',
        renderRow: (log) => `
            <tr>
                <td>${log.id}</td>
                <td>${getStatusBadge(log.ocr_status)}</td>
                <td>${renderFileNameCell(log.file_name)}</td>
                <td><span class="text-secondary">${escapeHtml(log.started)}</span></td>
                <td><span class="text-secondary">${escapeHtml(log.finished)}</span></td>
                <td>${renderErrorCell(log.ocr_error)}</td>
            </tr>
        `
    });

    createLogsTable({
        endpoint: '/api/sync-logs',
        collapseId: 'sync-logsCollapse',
        tableId: 'sync-logs-table',
        emptyId: 'sync-logs-empty',
        paginationId: 'sync-logs-pagination',
        filterId: 'sync-logs-success-filter',
        refreshBtnId: 'refresh-sync-logs-btn',
        renderRow: (log) => `
            <tr>
                <td>${log.id}</td>
                <td>${getStatusBadge(log.sync_status)}</td>
                <td>${renderFileNameCell(log.file_name)}</td>
                <td><span class="text-secondary">${escapeHtml(log.started)}</span></td>
                <td><span class="text-secondary">${escapeHtml(log.finished)}</span></td>
                <td>${renderErrorCell(log.error_description)}</td>
            </tr>
        `
    });
}

// Show full file name on click (mobile) and via tooltip (desktop), truncated to 15 chars.
function renderFileNameCell(fileName) {
    const truncated = truncate(fileName, 15);
    if (fileName && fileName.length > 15) {
        return `
            <span class="js-show-full" title="${escapeHtml(fileName)}" data-fulltext="${escapeHtml(fileName)}" style="cursor:pointer;">
                ${escapeHtml(truncated)}
            </span>
        `;
    }
    return escapeHtml(fileName);
}

// Show full error on click (mobile) and via tooltip (desktop), truncated to 40 chars.
function renderErrorCell(errorText) {
    if (!errorText) {
        return '';
    }
    const truncated = truncate(errorText, 40);
    return `
        <span class="text-danger js-show-full" title="${escapeHtml(errorText)}" data-fulltext="${escapeHtml(errorText)}" style="cursor:pointer;">
            ${escapeHtml(truncated)}
        </span>
    `;
}

function renderPagination(pagination, page, totalPages, loadFn, getFilter) {
    pagination.innerHTML = '';
    if (totalPages <= 1) return;
    let html = '';
    html += `<li class="page-item${page === 1 ? ' disabled' : ''}"><a class="page-link" href="#" data-page="${page-1}">&laquo;</a></li>`;
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || Math.abs(i - page) <= 1) {
            html += `<li class="page-item${i === page ? ' active' : ''}"><a class="page-link" href="#" data-page="${i}">${i}</a></li>`;
        } else if (i === page - 2 || i === page + 2) {
            html += `<li class="page-item disabled"><span class="page-link">…</span></li>`;
        }
    }
    html += `<li class="page-item${page === totalPages ? ' disabled' : ''}"><a class="page-link" href="#" data-page="${page+1}">&raquo;</a></li>`;
    pagination.innerHTML = html;
    pagination.querySelectorAll('a.page-link').forEach(link => {
        link.onclick = (e) => {
            e.preventDefault();
            const p = parseInt(link.getAttribute('data-page'));
            if (p >= 1 && p <= totalPages) loadFn(p, getFilter());
        };
    });
}

function getStatusBadge(status) {
    if (!status) {
        return '<span class="badge bg-secondary">Unknown</span>';
    }
    const normalized = status.toUpperCase();
    if (normalized === 'COMPLETED') {
        return '<span class="badge bg-success">Completed</span>';
    }
    if (['PENDING', 'PROCESSING', 'SYNC', 'SYNCING'].includes(normalized)) {
        return `<span class="badge bg-warning text-dark">${escapeHtml(toTitleCase(status))}</span>`;
    }
    return `<span class="badge bg-danger">${escapeHtml(toTitleCase(status))}</span>`;
}

function toTitleCase(status) {
    if (!status) {
        return '';
    }
    return status.toLowerCase().split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function truncate(str, n) {
    return str && str.length > n ? str.slice(0, n - 1) + '…' : str;
}

function escapeHtml(text) {
    return text ? text.replace(/[&<>"']/g, function(m) {
        return ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[m];
    }) : '';
}