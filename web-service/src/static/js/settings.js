document.addEventListener('DOMContentLoaded', function () {
    const openai_button = document.getElementById("save-button");
    if (document.getElementById('openai_key').value.length > 0 && automatic_file_names) {
        openai_button.textContent = "Disable";
        openai_button.disabled = false;
    } else {
        openai_button.textContent = "Enable";
    }
});


function submitOpenAI(event) {
    event.preventDefault(); // Prevent default form submission
    const submitButton = document.getElementById('save-button');
    const keyInput = document.getElementById('openai_key');
    if (submitButton.innerText == "Enable") {
        submitButton.innerText = "Testing key...";
    } else {
        submitButton.innerText = "Deactivating...";
    }
    submitButton.disabled = true;

    var formData = new FormData(document.getElementById('openai-form'));
    var xhr = new XMLHttpRequest();

    xhr.open('POST', '/settings/openai', true);

    xhr.onreadystatechange = function() {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status === 200) {
                var response = JSON.parse(xhr.responseText);
                console.log(response);
                if (response.success == 200) {
                    animateButton(submitButton, true, "Success", "Disable");
                } else if (response.success == 204) {
                    animateButton(submitButton, true, "Deactivated", "Enable")
                    keyInput.value = "";
                } else if (response.success == 401) {
                    animateButton(submitButton, false, "Invalid key", "Enable");
                } else if (response.success == 429) {
                    animateButton(submitButton, false, "Not enough OpenAI credit", "Enable");
                } else {
                    animateButton(submitButton, false, "Unknown Error", "Enable");
                }
            } else {
                console.error('Error:', xhr.status);
                console.error('Error:', xhr.responseText);
                animateButton(submitButton, false, "Internal Error");
            }
        }
    };

    xhr.send(formData);
}

function animateButton(button, success, message, buttonText='Enable') {
    button.classList.add('disabled');
  
    if (success) {
        button.classList.add('success-color');
        button.innerHTML = '<i class="bi bi-check"></i> ' + message;
    } else {
        button.classList.add('failure-color');
        button.innerHTML = '<i class="bi bi-exclamation-triangle"></i> ' + message;
    }
    
    setTimeout(function() {
        button.classList.remove('success-color', 'failure-color', 'disabled');
        button.innerHTML = buttonText;
    }, 3000);
}

function checkIfEmpty(input_id, button_id) {
    var element = document.getElementById(input_id);
    var button = document.getElementById(button_id);
    if (element.value.length == 0) {
        element.classList.add('is-invalid');
        button.disabled = true;
    } else {
        element.classList.remove('is-invalid');
        button.disabled = false;
    }
}
