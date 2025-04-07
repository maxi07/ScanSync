const onedriveLocalListGroup = document.getElementById('onedrivelistgroup');
var onedriveDirLevel = 1;
var currentOneDrivePath = "/"; // The path we are currently in
var currentOneDriveSelectedPath = ""; // The path the user actually selected

document.addEventListener('DOMContentLoaded', function () {
    var onedriveNameInput = document.getElementById('onedrive_name');
    var submitButtonOneDriveConnections = document.getElementById('add_onedrive_button');
    var submitButtonpathmapping = document.getElementById('add_path_mapping_button');
    const errormsgOneDriveConn = document.getElementById("allowedCharsErrorMsgOneDriveConn");
    const errormsglocalpath = document.getElementById("allowedCharsErrorMsgLocalPath");
    var localpathinput = document.getElementById('local_path');
    const sharepoint_name_input = document.getElementById('sharepoint_name');

    // Add an input event listener to the text input
    onedriveNameInput.addEventListener('input', function () {
        // Enable or disable the button based on whether the input has content

        submitButtonOneDriveConnections.disabled = !onedriveNameInput.value.trim();

        // Validate the input
        if (validateTextInput(onedriveNameInput.value)) {
            onedriveNameInput.classList.remove('is-invalid');
            errormsgOneDriveConn.style.display = 'none';
            submitButtonOneDriveConnections.disabled = false;
        } else {
            onedriveNameInput.classList.add('is-invalid');
            errormsgOneDriveConn.style.display = 'block';
            submitButtonOneDriveConnections.disabled = true;
        }
        evaluateAddOneDriveSubmitButton()
    });

    sharepoint_name_input.addEventListener('input', function () {
        // Enable or disable the button based on whether the input has content

        // Validate the input
        if (validateTextInput(sharepoint_name_input.value)) {
            sharepoint_name_input.classList.remove('is-invalid');
            errormsgOneDriveConn.style.display = 'none';
            submitButtonpathmapping.disabled = false;
        } else {
            sharepoint_name_input.classList.add('is-invalid');
            errormsgOneDriveConn.style.display = 'block';
            submitButtonpathmapping.disabled = true;
        }
        evaluateAddOneDriveSubmitButton()
    });

    // Add an input event listener to the local path input
    localpathinput.addEventListener('input', function () {
        // Validate the input
        if (validateTextInput(localpathinput.value)) {
            localpathinput.classList.remove('is-invalid');
            errormsglocalpath.style.display = 'none';
        } else {
            localpathinput.classList.add('is-invalid');
            errormsglocalpath.style.display = 'block';
        }
        evaluatePathMappingSubmitButton();
    });

    // Add event listener for when path mapping modal is hidden
    const pathmappingmodal = document.getElementById('pathmappingmodal')
    pathmappingmodal.addEventListener('hidden.bs.modal', event => {
        resetPathMappingModal();
    })

    const remotepathselector = document.getElementById("remotepathselector");
    // Event listener for when the collapse is about to be shown
    remotepathselector.addEventListener('show.bs.collapse', function () {
        console.log('Collapse is about to be shown.');
        loadOneDriveDir();
    });
});

function evaluateAddOneDriveSubmitButton() {
    var submitButtonOneDriveConnections = document.getElementById('add_onedrive_button');
    var sp_container = document.getElementById('sharepoint_name_container');
    var connectionName = document.getElementById('onedrive_name');
    var sp_name = document.getElementById('sharepoint_name');

    // Test if SharePoint Container is visible. If yes, then check if SharePoint Name is set.
    if (sp_container.style.display === 'block') {
        if (sp_name.value.trim() && connectionName.value.trim()) {
            submitButtonOneDriveConnections.disabled = false;
        } else {
            submitButtonOneDriveConnections.disabled = true;
        }
    } else {
        if (connectionName.value.trim()) {
            submitButtonOneDriveConnections.disabled = false;
        } else {
            submitButtonOneDriveConnections.disabled = true;
        }
    }
}

function evaluatePathMappingSubmitButton() {
    const submitButtonpathmapping = document.getElementById('add_path_mapping_button');
    const localpathinput = document.getElementById('local_path');
    const remotePathInput = document.getElementById('remote_path');

    // Enable or disable the button based on whether the input has content
    submitButtonpathmapping.disabled = !(localpathinput.value.trim() && !localpathinput.classList.contains('is-invalid') && remotePathInput.value.startsWith('/'));
}

function deleteOneDriveConf(id) {
    const xhr = new XMLHttpRequest();
    xhr.open('DELETE', '/sync/onedrive', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                alert(xhr.responseText);
            } else {
                console.log(xhr.responseText);
                // Fade out the row before removing it
                const row = document.getElementById(id + '_row');
                // Fade animation
                row.style.transition = 'opacity 1.5s';
                row.style.opacity = 0;

                // Remove after fade
                setTimeout(() => {
                    row.remove();
                }, 500);
            };
        };
    }
    xhr.send(JSON.stringify({ "id": id }));
}

function addOneDrive() {
    const animation = document.getElementById("waitingAnimationonedriveadd");
    const animation_statustext = document.getElementById("waitingAnimationonedriveadd_statustext");
    const form = document.getElementById("onedrive_name_container");
    const addButton = document.getElementById("add_onedrive_button");
    const sshTunnelInfoElement = document.getElementById("sshTunnelSetupInfo");
    const sshInstallInfoElement = document.getElementById("sshInstallInfo");
    const cloud_header = document.getElementById("cloud_header");
    const sshErrorMsg = document.getElementById("sshErrorMsg");
    addButton.style.disabled = true;
    animation.style.display = "block";
    form.style.display = "none";
    cloud_header.style.display = "none";

    // Check if ssh is enabled. We need a ssh tunnel for proper authentication with onedrive (duh..)
    animation_statustext.innerText = "Checking if SSH is enabled...";
    const xhr = new XMLHttpRequest();
    xhr.open('GET', '/sync/check-ssh', true);
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            animation.style.display = "none";
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                sshErrorMsg.innerText = xhr.responseText;
                addButton.innerText = "Retry";
                // Show the ssh setup modal
                sshInstallInfoElement.style.display = "block";
            } else {
                console.log(xhr.responseText);
                
                // Show the ssh tunnel setup modal and reroute the next button
                sshTunnelInfoElement.style.display = "block";
                addButton.onclick = function () {
                    animation.style.display = "block";
                    sshTunnelInfoElement.style.display = "none";
                    // Run websocket for status updates during rclone config
                    animation_statustext.innerText = "Waiting for connection...";
                    addButton.style.display = "none";
                    var rclonePopup = null;
                    var socket = io.connect('http://' + window.location.host + '/websocket-onedrive', {reconnection: false});
                    socket.on('message_update', function (data) {
                        console.log("Received message: " + data);
                        // Test if data begins with 'http'
                        if (data.startsWith("http")) {
                            // If it does, it's a link to the file
                            animation_statustext.innerHTML = '<a href="#" onclick="openAuthWindow(\'' + data + '\')">To authenticate, please visit <br>' + data + '</a>';
                            // openAuthWindow(data);
                        } else if (data.startsWith("Success")) {
                            try {
                                rCloneAuthPopup.close();
                            } catch {}
                            window.location.reload();
                        } else if (data.startsWith("Authenticated")) {
                            try {
                                rCloneAuthPopup.close();
                            } catch {}
                        } else {
                            // Otherwise, it's just text
                            if (data.startsWith("Error")) {
                                const error_display = document.getElementById("errormsg_display");
                                const errormsg = document.getElementById("error_msg_fromdisplay");
                                errormsg.innerText = data;
                                error_display.style.display = "block";
                                animation.style.display = "none";
                                addButton.innerText = "Retry";
                            } else {
                                animation_statustext.innerText = data;
                            }
                        }
                    });
                    socket.on('rclone_sp_update', function (data) {
                        console.log("Received rclone status: " + JSON.stringify(data));

                        animation_statustext.innerText = data.message;
                        const listgroup = document.getElementById("sharepoint_list_group");
                        if (data.step === "sp_select") {
                            console.log("Received " + Object.keys(data.options).length + " items.");

                            listgroup.innerHTML = '';
                            // Iterate through the JSON and create list-group-items dynamically
                            for (const [key, value] of Object.entries(data.options)) {
                                const listItem = document.createElement('a');
                                listItem.href = '#';
                                listItem.classList.add('list-group-item', 'list-group-item-action', 'd-flex', 'justify-content-between', 'align-items-center');

                                const icon = document.createElement('i');
                                icon.classList.add('bi', 'bi-house');

                                const span = document.createElement('span');
                                span.appendChild(icon);
                                span.appendChild(document.createTextNode(` ${value}`));
                                listItem.appendChild(span);

                                // Add event listeners
                                listItem.addEventListener('click', function() {
                                    socket.emit('rclone_sp_update', JSON.stringify({ "step": data.step, "value": key }));
                                    listgroup.innerHTML = '';
                                    listgroup.style.display = "none";
                                    animation_statustext.innerText = "Retrieving SharePoint libraries..."
                                });

                                listgroup.appendChild(listItem);
                            }
                            listgroup.style.display = "block";
                        } else if (data.step === "library_select") {
                            console.log("Received " + Object.keys(data.options).length + " items.");
                            listgroup.innerHTML = '';

                            // Iterate through the JSON and create list-group-items dynamically
                            for (const [key, value] of Object.entries(data.options)) {
                                const listItem = document.createElement('a');
                                listItem.href = '#';
                                listItem.classList.add('list-group-item', 'list-group-item-action', 'd-flex', 'justify-content-between', 'align-items-center');

                                const icon = document.createElement('i');
                                icon.classList.add('bi', 'bi-folder');

                                const span = document.createElement('span');
                                span.appendChild(icon);
                                span.appendChild(document.createTextNode(` ${value}`));
                                listItem.appendChild(span);

                                // Add event listeners
                                listItem.addEventListener('click', function() {
                                    socket.emit('rclone_sp_update', JSON.stringify({ "step": data.step, "value": key }));
                                    listgroup.innerHTML = '';
                                    listgroup.style.display = "none";
                                    animation_statustext.innerText = "Finishing up..."
                                });
                                listgroup.appendChild(listItem);
                                listgroup.style.display = "block";
                            }
                        } else {
                            animation_statustext.innerText = "Unknown step.";
                        }
                    });

                    socket.on('connect', function () {
                        console.log('Connected to onedrive websocket');
                        const onedrive_selector = document.getElementById("onedrive_selector");
                        socket.emit('message_update', JSON.stringify({ "name": document.getElementById("onedrive_name").value, "sp_name": document.getElementById("sharepoint_name").value, "onedrive_type": getActiveElementOneDriveSelector()}));
                    });
                };
            };
        };
    }
    xhr.send();
}

function getActiveElementOneDriveSelector() {
    const radioButtons = document.querySelectorAll('#onedrive_selector input[type="radio"]');
    
    let activeElement = null;
    radioButtons.forEach(button => {
        if (button.checked) {
            activeElement = button.id.includes('personal') ? 'personal' : 'sharepoint';
        }
    });
    
    return activeElement;
}


function openAuthWindow(url) {
    rCloneAuthPopup = window.open(url, "rClone Authentication", "width=400,height=600");
}

function toggleSPName() {
    const sp_container = document.getElementById("sharepoint_name_container");
    sp_container.style.display = sp_container.style.display === "none"? "block" : "none";
}

function validateTextInput(input) {
    // Regular expression pattern for allowed characters
    const pattern = /^[0-9A-Za-z_\- ]+$/;

    // Check if the input matches the pattern and does not start or end with a space
    if (pattern.test(input) && !input.startsWith(' ') && !input.endsWith(' ')) {
        return true; // Input is valid
    } else {
        return false; // Input is not valid
    }
}


function getConnections() {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', '/sync/onedrive', true);
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                alert(xhr.responseText);
            } else {
                console.log("Received connections response.");
                const selectElement = document.getElementById('connection_selector_modal');

                // Clear existing options
                selectElement.innerHTML = '';

                responseJSON = JSON.parse(xhr.responseText);
                // Add new options
                responseJSON.forEach(optionText => {
                    const optionElement = document.createElement('option');
                    optionElement.value = optionText + ":";
                    optionElement.textContent = optionText;
                    selectElement.appendChild(optionElement);
                });
            };
        };
    }
    xhr.send();
}


function loadOneDriveDir(back = false) {
    const backbuttondiv = document.getElementById("remoteonedrivebackbutton");
    const loadingAnimation = document.getElementById("waitingAnimationPathMapping");
    const listgroup = document.getElementById('onedrivelistgroup');

    backbuttondiv.style.display = "none";
    loadingAnimation.style.display = "block";
    listgroup.style.display = "none";
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/sync/onedrive-directory', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                alert(xhr.responseText);
            } else {
                jsonResponse = JSON.parse(xhr.responseText);
                console.log("Received " + Object.keys(jsonResponse).length + " items.");

                listgroup.innerHTML = '';
                // Iterate through the JSON and create list-group-items dynamically
                for (const [key, value] of Object.entries(jsonResponse)) {
                    const listItem = document.createElement('a');
                    listItem.href = '#';
                    listItem.classList.add('list-group-item', 'list-group-item-action', 'd-flex', 'justify-content-between', 'align-items-center');

                    const icon = document.createElement('i');
                    icon.classList.add('bi', 'bi-folder');

                    const span = document.createElement('span');
                    span.appendChild(icon);
                    span.appendChild(document.createTextNode(` ${key}`));

                    const arrowIcon = document.createElement('i');
                    arrowIcon.classList.add('bi', 'bi-arrow-return-right');

                    if (value > 0) {
                        listItem.appendChild(span);
                        listItem.appendChild(arrowIcon);
                    } else {
                        listItem.appendChild(span);
                    }


                    // Add event listeners
                    listItem.addEventListener('click', handleRemotePathClick);
                    listItem.addEventListener('dblclick', handleRemotePathDoubleClick);
                    listgroup.appendChild(listItem);
                }
                const backbutton = backbuttondiv.querySelector("button");
                if (onedriveDirLevel === 1) {
                    backbutton.disabled = true;
                } else {
                    backbutton.disabled = false;
                }
                backbuttondiv.style.display = "block";
                loadingAnimation.style.display = "none";
                listgroup.style.display = "block";
            };
        };
    }
    if (back) {
        currentOneDrivePath = currentOneDrivePath.replace(/\/[^/]*\/?$/, '/')
        onedriveDirLevel--;
    }
    xhr.send(JSON.stringify({ "remote_id": document.getElementById("connection_selector_modal").value, "path": currentOneDrivePath }));
}

function handleRemotePathClick(event) {
    const targetItem = event.currentTarget;

    // Remove 'active' class from all items
    onedriveLocalListGroup.querySelectorAll('.list-group-item').forEach(item => {
        item.classList.remove('active');
    });

    // Add 'active' class to the clicked item
    targetItem.classList.add('active');

    setCurrentPathRemote(targetItem.textContent);
}

function setCurrentPathRemote(pathToAdd) {
    // Remove space from start and end of path
    pathToAdd = pathToAdd.trim();

    if (currentOneDriveSelectedPath.startsWith("/")) {
        if (currentOneDriveSelectedPath.split("/").length - 2 === onedriveDirLevel) {
            currentOneDriveSelectedPath = updateSameLevel(currentOneDriveSelectedPath, pathToAdd);
        } else if (currentOneDriveSelectedPath.split("/").length - 2 > onedriveDirLevel) {
            currentOneDriveSelectedPath = currentOneDriveSelectedPath.replace(/\/[^/]*\/?$/, '/') // Remove last dir

        } else {
            currentOneDriveSelectedPath = updateDeeperLevel(currentOneDriveSelectedPath, pathToAdd);
        }
    } else {
        currentOneDriveSelectedPath = "/" + pathToAdd + "/";
    }
    document.getElementById("remote_path").value = currentOneDriveSelectedPath;
    evaluatePathMappingSubmitButton();
}

function handleRemotePathDoubleClick(event) {
    const targetItem = event.currentTarget;
    // Test if the inner html of the targetItem contains an icon
    if (targetItem.innerHTML.includes("bi-arrow-return-right")) {
        // If it does, it means the item is a directory, so we can load the directory
        onedriveDirLevel += 1;
        currentOneDrivePath += targetItem.textContent.trim() + "/";
        console.log("User is now in dir: " + currentOneDrivePath);
        loadOneDriveDir();
    }
}

function updateSameLevel(path, newDir) {
    // Remove leading and trailing slashes, then split the path into an array of directories
    const pathArray = path.replace(/^\/|\/$/g, '').split('/');

    // Remove the last element (directory) from the array
    pathArray.pop();

    // Append the new directory to the array
    pathArray.push(newDir);

    // Join the array back into a string with '/' as the separator
    let newPath = '/' + pathArray.join('/') + '/';

    return newPath;
}

function updateDeeperLevel(currentFilePath, newDirectoryName) {
    currentFilePath += newDirectoryName + '/';
    return currentFilePath;
}


function addPathMapping() {
    // Hide form
    const modalbody = document.getElementById("pathmappingmodal_body");
    modalbody.style.display = "none";
    const modalfooter = document.getElementById("pathmappingmodal_footer");
    modalfooter.style.display = "none";

    // Show waiting animation
    const waitingAnimation = document.getElementById("waitingAnimationPathMappingSent");
    waitingAnimation.style.display = "block";

    // Get all relevant elements
    const remotePath = document.getElementById("remote_path").value;
    const localPath = document.getElementById("local_path").value;
    const connection_selector = document.getElementById("connection_selector_modal").value;


    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/sync/pathmapping', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            waitingAnimation.style.display = "none";
            const finalPathMappingStatus = document.getElementById("finalPathMappingStatus");
            const finalPathMappingStatusSuccess = document.getElementById("finalPathMappingStatusSuccess");
            const finalPathMappingStatusFailed = document.getElementById("finalPathMappingStatusError");
            finalPathMappingStatusFailed.style.display = (xhr.status === 200) ? "none" : "block";
            finalPathMappingStatusSuccess.style.display = (xhr.status === 200) ? "block" : "none";
            const finalPathMappingStatusText = document.getElementById("finalPathMappingStatusText");
            finalPathMappingStatusText.innerText = xhr.responseText;
            finalPathMappingStatus.style.display = "block";
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                alert(xhr.responseText);
            } else {
                console.log(xhr.responseText);
                addPathMappingToUI(localPath, remotePath, connection_selector);
            };
        };
    }
    xhr.send(JSON.stringify({ "remote_id": connection_selector, "remote_path": remotePath, "local_path": localPath }));
}

function resetPathMappingModal() {
    const modalbody = document.getElementById("pathmappingmodal_body");
    modalbody.style.display = "block";
    const modalfooter = document.getElementById("pathmappingmodal_footer");
    modalfooter.style.display = "block";
    const waitingAnimation = document.getElementById("waitingAnimationPathMappingSent");
    waitingAnimation.style.display = "none";
    const finalPathMappingStatus = document.getElementById("finalPathMappingStatus");
    finalPathMappingStatus.style.display = "none";
    const local_path = document.getElementById("local_path");
    local_path.value = "";
}


function addPathMappingToUI(local, remote, connection) {
    var newCard = document.createElement('div');
    newCard.classList.add('col');
    newCard.id = local + "_pathmappingcard";
    newCard.innerHTML = `
            <div class="card">
                <div class="card-header">
                    ${local}
                </div>
                <div class="card-body">
                    <ol class="list-group list-group-flush">
                        <li class="list-group-item d-flex justify-content-between align-items-start">
                            <div class="ms-2 me-auto">
                                <div class="fw-bold">Local</div>
                                <i class="bi bi-folder"></i> ${local}
                            </div>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-start">
                            <div class="ms-2 me-auto">
                                <div class="fw-bold">Remote</div>
                                <i class="bi bi-folder"></i><div id="${local}_remote_pathmapping">${connection + remote}</div>
                            </div>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-start">
                            <div class="ms-2 me-auto">
                                <div class="fw-bold">Type</div>
                                onedrive
                            </div>
                        </li>
                    </ol>
                </div>
                <div class="card-footer">
                    <button id="${local}_edit_button" onclick="editPathMapping('${local}')"
                        class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#pathmappingmodal"><i class="bi bi-pencil"></i> Edit</button>
                    <button id="${local}_delete_button" onclick="deletePathMapping('${local}')"
                        class="btn btn-danger"><i class="bi bi-trash"></i> Delete</button>
                </div>
            </div>`
    document.getElementById("pathmappingscontainer").appendChild(newCard);

    try {
        const emptymsg = document.getElementById("emptypathmappingsmessage")
        emptymsg.style.display = "none";
    } catch {}
}

function deletePathMapping(id) {
    const xhr = new XMLHttpRequest();
    xhr.open('DELETE', '/sync/pathmapping', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                alert(xhr.responseText);
            } else {
                console.log(xhr.responseText);
                const card = document.getElementById(id + "_pathmappingcard");
                card.style.transition = 'opacity 1.5s';
                card.style.opacity = 0;

                // Remove after fade
                setTimeout(() => {
                    card.remove();
                }, 1500);
            };
        };
    }
    xhr.send(JSON.stringify({ "id": id }));
}

function editPathMapping(id) {
    const local_path = document.getElementById("local_path");
    const remote_path = document.getElementById("remote_path");
    const connection = document.getElementById("connection_selector_modal");

    local_path.value = id;
    remote_path.value = document.getElementById(id + "_remote_pathmapping").innerText.split(":")[1];
    var optionElement = document.createElement('option');
    optionElement.value = document.getElementById(id + "_remote_pathmapping").innerText.split(":")[0] + ":"
    optionElement.textContent = document.getElementById(id + "_remote_pathmapping").innerText.split(":")[0];
    connection.appendChild(optionElement);
}

function deleteFailedSync(id) {
    const xhr = new XMLHttpRequest();
    xhr.open('DELETE', '/sync/failedpdf', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                alert(xhr.responseText);
            } else {
                console.log(xhr.responseText);
                const row = document.getElementById(id + '_failedpdf_row');
                // Fade animation
                row.style.transition = 'opacity 1.5s';
                row.style.opacity = 0;

                // Remove after fade
                setTimeout(() => {
                    row.remove();
                }, 500);
            };
        };
    }
    xhr.send(JSON.stringify({ "id": id }));
}

function downloadFailedSync(id) {
    window.open("/sync/failedpdf?download_id=" + id);
}

function copyCommand() {
    var commandElement = document.querySelector('.terminal-command');
    var commandText = commandElement.innerText;

    var textarea = document.createElement('textarea');
    textarea.value = commandText;
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, 99999); // for mobile
    navigator.clipboard.writeText(textarea.value);
    document.body.removeChild(textarea);

    console.log('Command copied to clipboard!');
}
