document.getElementById('onedrive-settings-form').addEventListener('submit', async function (event) {
    event.preventDefault();
    const submitButton = this.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    var submitButtonText = submitButton.textContent;
    submitButton.textContent = 'Saving...';
    const formData = new FormData(this);
    const data = Object.fromEntries(formData.entries());

    try {
        const response = await fetch('/api/onedrive-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });

        submitButton.disabled = false;
        submitButton.textContent = submitButtonText;
        if (response.ok) {
            const result = await response.json();
            alert('Settings saved successfully!');
        } else {
            alert('Failed to save settings.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred while saving settings.');
    }
});