/* global bootstrap getContrastYIQ */

const onedriveLocalListGroup = document.getElementById('onedrivelistgroup');
let onedriveDirLevel = 1;
let currentOneDrivePath = "/"; // The path we are currently in
let currentOneDriveSelectedPath = ""; // The path the user actually selected
let currentOneDriveSelectedID = ""; // The ID of the selected item

// Add a stack to manage parent IDs
const parentIDStack = [];


document.addEventListener('DOMContentLoaded', function() {
    const remotepathselector = document.getElementById("remotepathselector");
    remotepathselector.addEventListener('show.bs.collapse', function() {
        loadOneDriveDir();
    });
    // Enable popovers
    if (typeof bootstrap === 'undefined') {
        console.error('Bootstrap JS is not loaded. Please include Bootstrap\'s JavaScript before this script.');
    } else {
        const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
        [...popoverTriggerList].forEach(popoverTriggerEl => new bootstrap.Popover(popoverTriggerEl));
        replaceHostnamePopovers();
    }
    setSortByDropdown();
    setBadgeContrastColor();
});

function setBadgeContrastColor() {
    const badges = document.querySelectorAll('.smb-badge');
    badges.forEach(badge => {
        try {
            const bgColor = window.getComputedStyle(badge).backgroundColor;
            let hexColor = bgColor;
            if (bgColor.startsWith('rgb')) {
                const rgb = bgColor.match(/\d+/g).map(Number);
                hexColor = "#" + rgb.slice(0, 3).map(x => x.toString(16).padStart(2, '0')).join('');
            }
            if (bgColor) {
                // console.log(`Setting contrast color for badge ${badge.id} with background color: ${hexColor}`);
                let result = getContrastYIQ(hexColor);
                badge.style.color = result;
            } else {
                console.warn(`No background color found for badge ${badge.id}. Skipping contrast color setting.`);
            }
        } catch (error) {
            console.error(`Error setting contrast color for badge ${badge.id}: ${error.message}`);
        }

    });
}

/* exported importPathMappingsCSV */
function importPathMappingsCSV(input) {
    if (input.files.length === 0) return;
    const file = input.files[0];
    if (!file.name.toLowerCase().endsWith('.csv')) {
        alert('Please select a CSV file.');
        input.value = ""; // Reset the input
        return;
    }
    const modalHtml = `
        <div class="modal fade" id="csvUploadModal" tabindex="-1" aria-labelledby="csvUploadModalLabel" aria-hidden="true" data-bs-backdrop="static" data-bs-keyboard="false">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="csvUploadModalLabel">Uploading CSV...</h5>
                    </div>
                    <div class="modal-body d-flex align-items-center">
                        <div class="spinner-border text-primary me-3" role="status">
                            <span class="visually-hidden">Uploading...</span>
                        </div>
                        <span>Please wait while your CSV is being uploaded.</span>
                    </div>
                </div>
            </div>
        </div>
    `;
    let modalDiv = document.createElement('div');
    modalDiv.innerHTML = modalHtml;
    document.body.appendChild(modalDiv);

    const uploadModal = new bootstrap.Modal(document.getElementById('csvUploadModal'));
    uploadModal.show();
    const formData = new FormData();
    formData.append('csv', file);

    fetch('/sync/upload', {
        method: 'PUT',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            const modalBody = document.querySelector('#csvUploadModal .modal-body');
            const modalTitle = document.getElementById('csvUploadModalLabel');
            if (data.success) {
                modalBody.innerHTML = `<div class="w-100"><div class="alert alert-success mb-0">CSV uploaded successfully.<br><strong>${data.added}</strong> item(s) added.</div></div>`;
                modalTitle.textContent = "Upload Complete";
                setTimeout(() => {
                    window.location.reload();
                }, 3000);
            } else {
                showCsvUploadErrorModal(data.error || 'Failed to upload CSV.');
            }
        })
        .catch(error => {
            console.error(error);
            showCsvUploadErrorModal('An error occurred while uploading the CSV.<br>' + error);
        });
}

function showCsvUploadErrorModal(message) {
    const modalBody = document.querySelector('#csvUploadModal .modal-body');
    const modalTitle = document.getElementById('csvUploadModalLabel');
    if (modalBody && modalTitle) {
        modalBody.innerHTML = `
            <div class="w-100">
                <div class="alert alert-danger mb-3">${message}</div>
                <div class="text-end">
                    <button type="button" class="btn btn-secondary" id="csvUploadModalCloseBtn">Close</button>
                </div>
            </div>
        `;
        modalTitle.textContent = "Upload Failed";
        document.getElementById('csvUploadModalCloseBtn').onclick = function() {
            const csvModal = document.getElementById('csvUploadModal');
            const uploadModal = bootstrap.Modal.getInstance(csvModal);
            uploadModal.hide();
            setTimeout(() => {
                csvModal.remove();
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) backdrop.remove();
            }, 500);
        };
    } else {
        alert(message);
    }
}

function setSortByDropdown() {
    const urlParams = new URLSearchParams(window.location.search);
    const orderParam = urlParams.get('order');
    const sortDropdown = document.getElementById('sortDropdown');
    if (orderParam && Array.from(sortDropdown.options).some(option => option.value === orderParam)) {
        sortDropdown.value = orderParam;
    } else {
        sortDropdown.value = "created ASC";
    }
}

// Add event listener for smb form submit
document.getElementById("pathmappingmodal_add_smb_form").addEventListener('submit', async function(event) {
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
    const response = await fetch("/add-path-mapping", {
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

function replaceHostnamePopovers() {
    const popoverButtons = document.querySelectorAll('[data-bs-toggle="popover"]');

    popoverButtons.forEach((btn) => {
        // eslint-disable-next-line no-unused-vars
        const popover = new bootstrap.Popover(btn, {
            trigger: 'focus', // or 'click', depending on your preference
            html: true
        });

        btn.addEventListener('shown.bs.popover', () => {
            // Wait a moment to ensure DOM is inserted
            setTimeout(() => {
                const hostname = window.location.hostname; // e.g., "server3"
                const popoverEl = document.querySelector('.popover .hostname-popover');
                if (popoverEl) {
                    popoverEl.textContent = hostname;
                }
            }, 0);
        });
    });
};

// Reset form when opening for adding new path mapping
document.getElementById("pathmappingmodal").addEventListener('show.bs.modal', function() {
    const form = document.getElementById("pathmappingmodal_add_smb_form");
    const oldSmbId = document.getElementById("old_smb_id");
    
    // Only reset if we're adding a new mapping (not editing)
    if (!oldSmbId.value) {
        form.reset(); // Reset the form fields
        console.log("Resetting form fields for new path mapping");
        
        // Reset modal title for adding new mapping
        const modalTitle = document.querySelector("#pathmappingmodal .modal-title");
        if (modalTitle) {
            modalTitle.textContent = "Add Path Mapping";
        }
        document.getElementById("submit_form_path_mapping_button").innerText = "Add";
    } else {
        console.log("Not resetting form fields - editing existing mapping");
    }
});

document.getElementById("add_path_mapping_button").addEventListener('click', function() {
    // Clear the old_smb_id to indicate we're adding, not editing
    document.getElementById("old_smb_id").value = "";
    document.getElementById("submit_form_path_mapping_button").innerText = "Add";
    
    // Reset the selected OneDrive folder
    currentOneDriveSelectedID = "";
    currentOneDriveSelectedPath = "";
    
    // Reset modal title for adding new mapping
    const modalTitle = document.querySelector("#pathmappingmodal .modal-title");
    if (modalTitle) {
        modalTitle.textContent = "Add Path Mapping";
    }
});

// Update the back button event listener
document.getElementById("remoteonedrivebackbutton").addEventListener('click', function() {
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
    xhr.onreadystatechange = function() {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status !== 200) {
                console.error(xhr.responseText);
                alert(xhr.responseText);
            } else {
                const jsonResponse = JSON.parse(xhr.responseText);
                console.log("Received " + jsonResponse.length + " items.");

                listgroup.innerHTML = '';
                let itemcount = 0;
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

                // Check if we need to pre-select an item (for editing mode)
                if (currentOneDriveSelectedID) {
                    updateOneDriveBrowserSelection(currentOneDriveSelectedID);
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
    };
    xhr.send(JSON.stringify({ "folderID": folderID, "driveID": driveID, "isSharedWithMe": isSharedWithMe, "onedriveDirLevel": onedriveDirLevel }));
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
    let parent = event.currentTarget.dataset.parentPath.split('root:')[1] || "";
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

/* exported editPathMapping */
function editPathMapping(id) {
    // Get SMB name from the badge element
    const smbBadgeElement = document.getElementById(id + "_pdf_smb");
    if (!smbBadgeElement) {
        console.error(`SMB badge element with ID ${id}_pdf_smb not found`);
        return;
    }
    
    // Get OneDrive path from the remote path mapping element
    const remotePathElement = document.getElementById(id + "_remote_pathmapping");
    if (!remotePathElement) {
        console.error(`Remote path element with ID ${id}_remote_pathmapping not found`);
        return;
    }
    
    // Fill the form fields
    const smbTitle = smbBadgeElement.innerText;
    document.getElementById("local_path").value = smbTitle.trim();
    document.getElementById("remote_path").value = remotePathElement.innerText || remotePathElement.textContent;
    document.getElementById("old_smb_id").value = id;
    
    // Set button text to indicate editing mode
    document.getElementById("submit_form_path_mapping_button").innerText = "Save Changes";
    
    // Change modal title for editing
    const modalTitle = document.querySelector("#pathmappingmodal .modal-title");
    if (modalTitle) {
        modalTitle.textContent = "Edit Path Mapping";
    }
    
    // We need to fetch the current folder_id, drive_id, and web_url from the backend
    // to properly set the selection in the OneDrive browser
    fetchPathMappingDetails(id);
}

function fetchPathMappingDetails(id) {
    // Make an API call to get the current path mapping details
    const xhr = new XMLHttpRequest();
    xhr.open('GET', `/get-path-mapping-details/${id}`, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function() {
        if (xhr.readyState === XMLHttpRequest.DONE) {
            if (xhr.status === 200) {
                const data = JSON.parse(xhr.responseText);
                
                // Set the hidden fields with the current values
                if (data.folder_id) {
                    document.getElementById("folder_id_input").value = data.folder_id;
                    currentOneDriveSelectedID = data.folder_id;
                }
                if (data.drive_id) {
                    document.getElementById("drive_id_input").value = data.drive_id;
                }
                if (data.web_url) {
                    document.getElementById("web_url_input").value = data.web_url;
                }
                
                // If the OneDrive browser is currently visible, update the selection
                updateOneDriveBrowserSelection(data.folder_id);
                
            } else {
                console.error("Failed to fetch path mapping details:", xhr.responseText);
                // Clear the fields as fallback
                document.getElementById("folder_id_input").value = "";
                document.getElementById("drive_id_input").value = "";
                document.getElementById("web_url_input").value = "";
            }
        }
    };
    xhr.send();
}

function updateOneDriveBrowserSelection(folderId) {
    if (!folderId) return;
    
    // Find the corresponding list item in the OneDrive browser
    const listGroup = document.getElementById('onedrivelistgroup');
    if (listGroup) {
        // Remove active class from all items
        listGroup.querySelectorAll('.list-group-item').forEach(item => {
            item.classList.remove('active');
        });
        
        // Find and activate the item with the matching folder ID
        const targetItem = listGroup.querySelector(`[data-item-id="${folderId}"]`);
        if (targetItem) {
            targetItem.classList.add('active');
            console.log(`Pre-selected folder with ID: ${folderId}`);
        }
    }
}

/* exported deletePathMapping */
function deletePathMapping(id) {
    if (confirm("Are you sure you want to delete this path mapping?")) {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/delete-path-mapping', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.onreadystatechange = function() {
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
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9", "failed-documents"
    ];
    // eslint-disable-next-line no-control-regex
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

/* exported downloadFailedSync */
function downloadFailedSync(id) {
    window.open("/failedpdf?download_id=" + id);
}

/* exported deleteFailedSync */
function deleteFailedSync(id) {
    const xhr = new XMLHttpRequest();
    xhr.open('DELETE', '/failedpdf', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function() {
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
    };
    xhr.send(JSON.stringify({ "id": id }));
}

/* exported sortPathMappings */
function sortPathMappings() {
    const sortBy = document.getElementById('sortDropdown').value;
    console.log(`Sorting by: ${sortBy}`);
    const url = new URL(window.location.href);
    url.searchParams.set('order', sortBy);
    window.location.href = url.toString();
}
