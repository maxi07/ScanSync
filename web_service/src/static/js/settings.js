let isRequestPending = false;

document.getElementById('onedrive-settings-form').addEventListener('submit', async function (event) {
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
window.addEventListener('beforeunload', function (e) {
    if (isRequestPending) {
        console.log('Request is pending, preventing page unload.');
        e.preventDefault();
    }
});


document.getElementById('openai-form').addEventListener('submit', async function (event) {
    event.preventDefault();
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
    tab.addEventListener('click', function () {
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
});

