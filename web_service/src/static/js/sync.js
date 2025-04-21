const onedriveLocalListGroup = document.getElementById('onedrivelistgroup');
var onedriveDirLevel = 1;
var currentOneDrivePath = "/"; // The path we are currently in
var currentOneDriveSelectedPath = ""; // The path the user actually selected
var currentOneDriveSelectedID = ""; // The ID of the selected item

// Add a stack to manage parent IDs
const parentIDStack = [];


document.addEventListener('DOMContentLoaded', function () {
    const remotepathselector = document.getElementById("remotepathselector");
    remotepathselector.addEventListener('show.bs.collapse', function () {
        loadOneDriveDir();
    });
});

// Add event listener for smb form submit
document.getElementById("pathmappingmodal_add_smb_form").addEventListener('submit', async function (event) {
    // Validate for invalid chars
    const input = document.getElementById("local_path");
    const error = document.getElementById("error_message_local_path");
    const name = input.value;

    if (!isValidSmbName(name)) {
      event.preventDefault(); // Verhindert das Absenden
      error.textContent = "Invalid SMB name: Avoid < > : \" / \\ | ? * or reserved names.";
      error.style.display = "block";
      return;
    } else {
      error.style.display = "none";
    }

    console.log("Submitting SMB form");
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);
    const response = await fetch("/add-path-mapping" || window.location.pathname, {
        method: 'POST',
        body: formData
    });

    if (response.ok) {
        const data = await response.json();
        if (data.success) {
            window.location.href = '/sync';
        } else {
            alert(data.error || 'Unknown error while submitting');
        }
    } else {
        const data = await response.json().catch(() => ({}));
        alert(data.error || 'Unknwon error while submitting');
    }
});

// Reset form when opening
document.getElementById("pathmappingmodal").addEventListener('show.bs.modal', function () {
    const form = document.getElementById("pathmappingmodal_add_smb_form");
    form.reset(); // Reset the form fields
    console.log("Resetting form fields");
});

document.getElementById("add_path_mapping_button").addEventListener('click', function () {
    document.getElementById("submit_form_path_mapping_button").innerText = "Add";
});

// Update the back button event listener
document.getElementById("remoteonedrivebackbutton").addEventListener('click', function () {
    if (parentIDStack.length > 0) {
        const previous = parentIDStack.pop(); // Remove the last parent ID from the stack
        onedriveDirLevel -= 1; // Decrease directory level
        currentOneDrivePath = currentOneDrivePath.split('/').slice(0, -2).join('/') + '/'; // Adjust the path
        console.log("Navigating back to: " + currentOneDrivePath);
        loadOneDriveDir(previous.parentId, previous.isSharedWithMe, previous.driveID); // Load the previous directory
    }
});

function loadOneDriveDir(folderID = null, isSharedWithMe = false, driveID = null) {
    console.log("Loading OneDrive directory with ID: " + folderID);
    const backbuttondiv = document.getElementById("remoteonedrivebackbutton");
    const loadingAnimation = document.getElementById("waitingAnimationPathMapping");
    const listgroup = document.getElementById('onedrivelistgroup');
    backbuttondiv.style.display = "none";
    loadingAnimation.style.display = "block";
    listgroup.style.display = "none";
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/get-user-drive-items', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function () {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                alert(xhr.responseText);
            } else {
                const jsonResponse = JSON.parse(xhr.responseText);
                console.log("Received " + jsonResponse.length + " items.");

                listgroup.innerHTML = '';
                itemcount = 0;
                jsonResponse.forEach(item => {
                    if (!item.folder) return;
                    if (item.package) return;
                    itemcount++;

                    const listItem = document.createElement('a');
                    listItem.href = '#';
                    listItem.classList.add('list-group-item', 'list-group-item-action', 'd-flex', 'justify-content-between', 'align-items-center');

                    if (item.id === currentOneDriveSelectedID) {
                        listItem.classList.add('active');
                    }

                    const icon = document.createElement('i');
                    if (item.shared) {
                        icon.classList.add('bi', 'bi-folder-symlink');
                    } else {
                        icon.classList.add('bi', 'bi-folder');
                    }
                    

                    const span = document.createElement('span');
                    span.appendChild(icon);
                    span.appendChild(document.createTextNode(` ${item.name}`));

                    const arrowIcon = document.createElement('i');
                    arrowIcon.classList.add('bi', 'bi-arrow-return-right');

                    listItem.appendChild(span);
                    listItem.appendChild(arrowIcon);

                    listItem.dataset.itemId = item.id;
                    listItem.dataset.parentId = item.parentReference?.id || '';
                    listItem.dataset.parentPath = item.parentReference?.path || '';
                    listItem.dataset.isSharedWithMe = item.shared || false;
                    listItem.dataset.webUrl = item.webUrl || '';
                    listItem.dataset.driveID = item.parentReference?.driveId || item.remoteItem?.parentReference?.driveId; // The drive id of the shared item

                    // Event-Handler
                    listItem.addEventListener('click', handleRemotePathClick);
                    listItem.addEventListener('dblclick', handleRemotePathDoubleClick);

                    listgroup.appendChild(listItem);

                });

                // Sort the list items alphabetically by their text content
                const listItems = Array.from(listgroup.children);
                listItems.sort((a, b) => a.textContent.trim().localeCompare(b.textContent.trim()));
                listItems.forEach(item => listgroup.appendChild(item));

                if (itemcount === 0) {
                    const noItemsMessage = document.createElement('div');
                    noItemsMessage.classList.add('alert', 'alert-info');
                    noItemsMessage.textContent = "No items found in this directory.";
                    listgroup.appendChild(noItemsMessage);
                }

                const backbutton = document.getElementById("remoteonedrivebackbutton");
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
    xhr.send(JSON.stringify({"folderID": folderID, "driveID": driveID, "isSharedWithMe": isSharedWithMe, "onedriveDirLevel": onedriveDirLevel}));
}


function handleRemotePathClick(event) {
    const targetItem = event.currentTarget;

    // Remove 'active' class from all items
    onedriveLocalListGroup.querySelectorAll('.list-group-item').forEach(item => {
        item.classList.remove('active');
    });

    // Add 'active' class to the clicked item
    targetItem.classList.add('active');
    
    // Update currentOneDriveSelectedPath, so we can set it to active later 
    currentOneDriveSelectedID = event.currentTarget.dataset.itemId;
    var parent = event.currentTarget.dataset.parentPath.split('root:')[1] || "";
    currentOneDriveSelectedPath = parent + "/" + targetItem.textContent.trimStart();
    document.getElementById("remote_path").value = currentOneDriveSelectedPath;
    document.getElementById("folder_id_input").value = targetItem.dataset.itemId;
    document.getElementById("drive_id_input").value = targetItem.dataset.driveID;
    document.getElementById("web_url_input").value = targetItem.dataset.webUrl;
}

// Update handleRemotePathDoubleClick to push parent IDs to the stack
function handleRemotePathDoubleClick(event) {
    const targetItem = event.currentTarget;
    if (targetItem.innerHTML.includes("bi-arrow-return-right")) {
        // Push the current parent ID to the stack
        parentIDStack.push({
            parentId: targetItem.dataset.parentId,
            isSharedWithMe: targetItem.dataset.isSharedWithMe === "true",
            driveID: targetItem.dataset.driveID
        });

        // Set the new parent ID for the back button
        document.getElementById("remoteonedrivebackbutton").dataset.parentID = targetItem.dataset.parentId;

        onedriveDirLevel += 1;
        currentOneDrivePath += targetItem.textContent.trim() + "/";
        console.log("User is now in dir: " + currentOneDrivePath);
        loadOneDriveDir(targetItem.dataset.itemId, targetItem.dataset.isSharedWithMe, targetItem.dataset.driveID);
    }
}

function editPathMapping(id) {
    var smb_title = document.getElementById(id + "_smb_path").innerText;
    document.getElementById("local_path").value = smb_title.trim();
    document.getElementById("add_path_mapping_button").innerText = "Edit";
    document.getElementById("old_smb_id").value = id;
}

function deletePathMapping(id) {
    if (confirm("Are you sure you want to delete this path mapping?")) {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/delete-path-mapping', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.onreadystatechange = function () {
            if (xhr.readyState === XMLHttpRequest.DONE) {
                if (xhr.status === 200) {
                    window.location.reload();
                } else {
                    const response = JSON.parse(xhr.responseText);
                    alert("Error deleting path mapping: " + (response.error || "Unknown error"));
                }
            }
        };
        xhr.send(JSON.stringify({ smb_id: id }));
    }
}

function isValidSmbName(name) {
    const reservedNames = [
      "CON", "PRN", "AUX", "NUL",
      "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
      "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    ];
    const forbiddenChars = /[<>:"/\\|?*\x00-\x1F]/;
    const endsWithDotOrSpace = /[. ]$/;

    return (
      name.length > 0 &&
      name.length <= 255 &&
      !reservedNames.includes(name.toUpperCase()) &&
      !forbiddenChars.test(name) &&
      !endsWithDotOrSpace.test(name) &&
      !/^[. ]+$/.test(name)
    );
}

function downloadFailedSync(id) {
    window.open("/failedpdf?download_id=" + id);
}

function deleteFailedSync(id) {
    const xhr = new XMLHttpRequest();
    xhr.open('DELETE', '/failedpdf', true);
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