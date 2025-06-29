/* global ollama_enabled ollamaModel */

let isRequestPending = false;
const LOGS_PER_PAGE = 5;
let logsPage = 1;
let logsSuccessFilter = 'all';

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
        // Only fetch logs when the accordion is opened for the first time
        let loaded = false;
        const logsCollapse = document.getElementById('logsCollapse');
        logsCollapse.addEventListener('show.bs.collapse', function() {
            if (!loaded) {
                fetchLogs();
                loaded = true;
            }
        });
    } catch (error) {
        console.error('Error attaching logsCollapse event listener:', error);
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

document.getElementById('refresh-logs-btn').onclick = () => fetchLogs(logsPage, logsSuccessFilter);

document.getElementById('logs-success-filter').addEventListener('change', function() {
    logsSuccessFilter = this.value;
    fetchLogs(1, logsSuccessFilter);
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
        const versionResp = await fetch(`${scheme}://${url}:${port}/api/version`);
        if (!versionResp.ok) throw new Error('Could not connect to Ollama server.');
        const versionData = await versionResp.json();
        versionInfo.innerHTML = `<span class="text-success me-2">&#10003;</span>Detected Ollama version: ${versionData.version || 'unknown'}`;
        versionInfo.classList.remove('d-none');

        // Get models
        const tagsResp = await fetch(`${scheme}://${url}:${port}/api/tags`);
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
            console.error('Fehler beim Verbinden mit Ollama:', err);
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
    const originalButtonHtml = submitButton.innerHTML;
    const errBox = document.getElementById('ollama-error');
    const disableOllamaButton = document.getElementById('ollama-delete-btn');
    disableOllamaButton && (disableOllamaButton.disabled = true);

    submitButton.disabled = true;
    console.log('Submitting Ollama settings form');
    submitButton.textContent = 'Saving...';

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
        submitButton.innerHTML = originalButtonHtml;
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

function fetchLogs(page = 1, filter = logsSuccessFilter) {
    document.querySelector('#refresh-logs-btn').disabled = true;
    let url = `/api/file-naming-logs?page=${page}&per_page=${LOGS_PER_PAGE}`;
    if (filter && filter !== 'all') {
        url += `&filter=${filter}`;
    }
    fetch(url)
        .then(res => res.json())
        .then(data => {
            renderLogsTable(data.logs, data.page, data.total_pages, data.total_count);
        })
        .catch(() => {
            renderLogsTable([], 1, 1, 0);
        })
        .finally(() => {
            document.querySelector('#refresh-logs-btn').disabled = false;
        });
}

function renderLogsTable(logs, page, totalPages) {
    const tbody = document.querySelector('#logs-table tbody');
    const empty = document.getElementById('logs-empty');
    const pagination = document.getElementById('logs-pagination');
    tbody.innerHTML = '';
    if (!logs || logs.length === 0) {
        empty.classList.remove('d-none');
        document.getElementById('logs-table').classList.add('d-none');
        pagination.innerHTML = '';
        return;
    }
    empty.classList.add('d-none');
    document.getElementById('logs-table').classList.remove('d-none');
    logs.forEach((log) => {
        const statusBadge = getStatusBadge(log.file_naming_status);
        // Show full error on click for mobile (and always show truncated with tooltip on desktop)
        let error = '';
        if (log.error_description) {
            const truncated = truncate(log.error_description, 40);
            error = `
                <span class="text-danger" title="${log.error_description}" style="cursor:pointer;" onclick="alert('${log.error_description.replace(/'/g,"\\'").replace(/\n/g,'\\n')}')">
                    ${truncated}
                </span>
            `;
        }
        // Truncate file name to 15 characters
        const truncatedFileName = truncate(log.file_name, 15);
        let fileNameHtml = '';
        if (log.file_name && log.file_name.length > 15) {
            fileNameHtml = `
                <span title="${escapeHtml(log.file_name)}" style="cursor:pointer;" onclick="alert('${escapeHtml(log.file_name).replace(/'/g,"\\'").replace(/\n/g,'\\n')}')">
                    ${escapeHtml(truncatedFileName)}
                </span>
            `;
        } else {
            fileNameHtml = escapeHtml(log.file_name);
        }
        tbody.innerHTML += `
            <tr>
                <td>${log.id}</td>
                <td>${statusBadge}</td>
                <td>${fileNameHtml}</td>
                <td>${escapeHtml(log.method)}</td>
                <td>${escapeHtml(log.model)}</td>
                <td><span class="text-secondary">${escapeHtml(log.started)}</span></td>
                <td><span class="text-secondary">${escapeHtml(log.finished)}</span></td>
                <td>${error}</td>
            </tr>
        `;
    });
    renderPagination(page, totalPages);
}

function renderPagination(page, totalPages) {
    const pagination = document.getElementById('logs-pagination');
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
            if (p >= 1 && p <= totalPages) fetchLogs(p, logsSuccessFilter);
        };
    });
}

function getStatusBadge(status) {
    switch (status) {
    case 'COMPLETED':
        return '<span class="badge bg-success">Completed</span>';
    case 'FAILED':
        return '<span class="badge bg-danger">Failed</span>';
    case 'PROCESSING':
        return '<span class="badge bg-warning text-dark">Processing</span>';
    default:
        return `<span class="badge bg-danger">${escapeHtml("Failed")}</span>`;
    }
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