document.addEventListener('DOMContentLoaded', function () {
    const lottiePlayer = document.getElementById('welcome_lottie_player')
    lottiePlayer.addEventListener("ready", function () {
        const loadinglottieanimation = document.getElementById('waitingAnimationLottie');
        loadinglottieanimation.style.display = 'none';
    });

    console.log("Creating " + pdfsData.length + " pdf cards.");
    // Iterate over the PDF data and add cards dynamically
    pdfsData.forEach(function (pdfData) {
        addPdfCard(pdfData);
    });

    eventSource = new EventSource("http://localhost:5001/stream");
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        console.log("Received data:", data);
        updateCard(data);
    };
    
    eventSource.onerror = function(err) {
        console.error("SSE error", err);
    };
});



function updateDashboard(data) {
    console.log("Updating dashboard");
    // Find the dashboard
    const queued_dashboard = document.getElementById('widget_queue_content');
    queued_dashboard.innerText = data.pending_pdfs;
    const processing_dashboard = document.getElementById('widget_processed_content');
    processing_dashboard.innerText = data.processed_pdfs;
    const timestamp_queued = document.getElementById('dashboard_latest_timestamp_pending_string');
    timestamp_queued.innerText = data.pending_pdfs_latest_timestamp;
    const timestamp_processed = document.getElementById('dashboard_latest_timestamp_completed_string');
    timestamp_processed.innerText = data.processed_pdfs_latest_timestamp;
}

function updateCard(updateData) {
    const cardId = updateData.id + '_pdf_card';
    const cardElement = document.getElementById(cardId);

    if (!cardElement) {
        console.warn(`Card with ID ${cardId} not found.`);
        const existingCards = document.querySelectorAll('[id$="_pdf_card"]');
        let highestId = 0;

        existingCards.forEach(card => {
            const cardId = parseInt(card.dataset.id, 10);
            if (!isNaN(cardId) && cardId > highestId) {
            highestId = cardId;
            }
        });

        if (updateData.id > highestId) {
            console.log(`New card with ID ${updateData.id} is higher than the current highest ID ${highestId}. Adding new card.`);
            addPdfCard(updateData);
        }
    }

    const fieldsMap = {
        file_name: '_pdf_title',
        file_status: '_pdf_status',
        pdf_pages: '_pdf_pages_badge',
        remote_filepath: '_pdf_cloud',
        web_url: '_pdf_cloud',
        local_filepath: '_pdf_smb',
        previewimage_path: '_pdf_card_image',
    };

    // Update the card with new data
    const elementId = updateData.id + fieldsMap[key];
    const element = document.getElementById(elementId);

    if (!element) {
        console.warn(`Element with ID ${elementId} not found for key ${key}.`);
        return;
    }

    // Update Image
    const imageDiv = document.getElementById(updateData.id + '_pdf_card_image');
    if (!imageDiv) {
        console.warn(`Image container with ID ${updateData.id}_pdf_card_image not found.`);
    } else {
        const existingImg = imageDiv.querySelector('img');
        const existingSvg = imageDiv.querySelector('svg');
        if (existingSvg) imageDiv.removeChild(existingSvg);
        if (!existingImg) {
            const imgElement = document.createElement('img');
            imgElement.id = updateData.id + '_pdf_preview_image';
            imgElement.classList.add('card-img-top', 'mx-auto');
            imgElement.style.height = '128px';
            imgElement.style.width = 'auto';
            imgElement.alt = 'pdf preview';
            imageDiv.appendChild(imgElement);
        }
        document.getElementById(updateData.id + '_pdf_preview_image').src = value;
    }

    // Update Cloud Link
    if (!updateData.web_url || updateData.web_url.trim() === "") {
        console.warn(`web_url is missing or empty for key ${key}.`);
    } else {
        const parent = element.parentElement;
        if (parent && parent.tagName === 'SPAN') {
            const cloudLink = document.createElement('a');
            cloudLink.id = updateData.id + '_pdf_cloud';
            cloudLink.href = updateData.web_url;
            cloudLink.textContent = updateData.updated_fields.remote_filepath || "Link";
            cloudLink.target = '_blank';
            const brElement = document.createElement('br');
            cloudLink.appendChild(brElement);
            parent.replaceChild(cloudLink, element);
        }
    }

    // Update Local Filepath
    if (!updateData.local_filepath || updateData.local_filepath.trim() === "") {
        console.warn(`local_filepath is missing or empty for key ${key}.`);
    } else {
        element.textContent = updateData.local_filepath;
        element.innerHTML += "<br>";
    }

    // Update Remote Filepath
    if (!updateData.remote_filepath || updateData.remote_filepath.trim() === "") {
        console.warn(`remote_filepath is missing or empty for key ${key}.`);
    } else {
        element.textContent = updateData.remote_filepath;
        element.innerHTML += "<br>";
    }

    // Update File Status
    if (!updateData.file_status || updateData.file_status.trim() === "") {
        console.warn(`file_status is missing or empty for key ${key}.`);
    } else {
        const status_icon = getStatusIcon(updateData.file_status);
        const statusText = element.previousElementSibling;
        if (statusText && statusText.tagName === 'SPAN') {
            const newStatusText = `<i class="bi ${status_icon}"></i><strong> Status:</strong> `;
            statusText.innerHTML = newStatusText;
        } else {
            console.warn("Parent element is not a <span> or does not exist for status icon update.");
        }
        element.textContent = updateData.file_status;
    }

    // Update file name
    if (!updateData.file_name || updateData.file_name.trim() === "") {
        console.warn(`file_name is missing or empty for key ${key}.`);
    } else {
        element.textContent = updateData.file_name;
    }

    // Update PDF Pages
    if (!updateData.pdf_pages || updateData.pdf_pages.trim() === "") {
        console.warn(`pdf_pages is missing or empty for key ${key}.`);
    } else {
        const badgeSpan = document.getElementById(updateData.id + '_pdf_pages_badge');
        if (badgeSpan) {
            badgeSpan.textContent = updateData.pdf_pages;
        } else {
            console.warn(`Badge span with ID ${updateData.id + '_pdf_pages_badge'} not found.`);
        }
    }

    // Update Progress Bar
    if (updateData.status_progressbar) {
        const progressBar = document.getElementById(`${updateData.id}_progress_bar`);
        if (progressBar) {
            updateProgressBar(updateData.id, updateData.status_progressbar);
        } else {
            console.warn(`Progress bar with ID ${updateData.id}_progress_bar not found.`);
        }
    }
            
    

    

    // Object.entries(updateData.updated_fields).forEach(([key, value]) => {
    //     const elementId = updateData.id + fieldsMap[key];
    //     const element = document.getElementById(elementId);

    //     if (!element) {
    //         console.warn(`Element with ID ${elementId} not found for key ${key}.`);
    //         return;
    //     }

    //     if (key === 'previewimage_path') {
    //         const imageDiv = document.getElementById(updateData.id + '_pdf_card_image');
    //         if (!imageDiv) {
    //             console.warn(`Image container with ID ${updateData.id}_pdf_card_image not found.`);
    //             return;
    //         }

    //         const existingImg = imageDiv.querySelector('img');
    //         const existingSvg = imageDiv.querySelector('svg');

    //         if (existingSvg) imageDiv.removeChild(existingSvg);
    //         if (!existingImg) {
    //             const imgElement = document.createElement('img');
    //             imgElement.id = updateData.id + '_pdf_preview_image';
    //             imgElement.classList.add('card-img-top', 'mx-auto');
    //             imgElement.style.height = '128px';
    //             imgElement.style.width = 'auto';
    //             imgElement.alt = 'pdf preview';
    //             imageDiv.appendChild(imgElement);
    //         }
    //         document.getElementById(updateData.id + '_pdf_preview_image').src = value;
    //     } else if (key === 'web_url') {
    //         const parent = element.parentElement;
    //         if (parent && parent.tagName === 'SPAN') {
    //             const cloudLink = document.createElement('a');
    //             cloudLink.id = updateData.id + '_pdf_cloud';
    //             cloudLink.href = value;
    //             cloudLink.textContent = updateData.updated_fields.remote_filepath || "Link";
    //             cloudLink.target = '_blank';
    //             const brElement = document.createElement('br');
    //             cloudLink.appendChild(brElement);
    //             parent.replaceChild(cloudLink, element);
    //         }
    //     } else if (key === 'local_filepath') {
    //         element.textContent = value;
    //         element.innerHTML += "<br>";
    //     } else if (key === 'remote_filepath') {
    //         element.textContent = value;
    //         element.innerHTML += "<br>";
    //     } else if (key === 'file_status') {
    //         const status_icon = getStatusIcon(value);
    //         const statusText = element.previousElementSibling;
    //         if (statusText && statusText.tagName === 'SPAN') {
    //             const newStatusText = `<i class="bi ${status_icon}"></i><strong> Status:</strong> `;
    //             statusText.innerHTML = newStatusText;
    //         } else {
    //             console.warn("Parent element is not a <span> or does not exist for status icon update.");
    //         }
    //         element.textContent = value;
    //     } else {
    //         element.textContent = value;
    //     }
    // });

    // Update dashboard data
    if (updateData.dashboard_data) {
        updateDashboard(updateData.dashboard_data);
    }
}

// Function to add a new PDF card
function addPdfCard(pdfData) {
    // Create elements for the card
    var colDiv = document.createElement('div');
    colDiv.id = pdfData.id + '_col';
    colDiv.classList.add('col');

    var cardDiv = document.createElement('div');
    cardDiv.id = pdfData.id + '_pdf_card';
    cardDiv.dataset.id = pdfData.id;
    cardDiv.classList.add('card', 'rounded', 'h-100');

    var imageDiv = document.createElement('div');
    imageDiv.id = pdfData.id + '_pdf_card_image';
    imageDiv.classList.add('bg-light', 'text-center', 'p-3', 'rounded-top');

    // Create badge span
    var badgeSpan = document.createElement('span');
    badgeSpan.id = pdfData.id + '_pdf_pages_badge';
    badgeSpan.classList.add('position-absolute', 'top-0', 'end-0', 'badge', 'bg-secondary');
    badgeSpan.style.marginTop = '10px';
    badgeSpan.style.marginRight = '10px';
    badgeSpan.textContent = pdfData.pdf_pages ? pdfData.pdf_pages : "N/A";

    var imgElement = document.createElement('img');
    imgElement.id = pdfData.id + '_pdf_preview_image';
    imgElement.classList.add('card-img-top', 'mx-auto');
    imgElement.style.height = '128px';
    imgElement.style.width = 'auto';
    imgElement.alt = 'pdf preview';

    // Set image source conditionally
    if (pdfData.previewimage_path) {
        imgElement.src = pdfData.previewimage_path;
        imageDiv.appendChild(imgElement);
    } else {
        // Remove imgElement if it's present
        if (imageDiv.querySelector('img')) {
            imageDiv.removeChild(imageDiv.querySelector('img'));
        }

        // Create SVG element
        var svgElement = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svgElement.id = pdfData.id + '_pdf_svg';
        svgElement.setAttribute("xmlns", "http://www.w3.org/2000/svg");
        svgElement.setAttribute("class", "bi bi-file-earmark-pdf-fill mx-auto");
        svgElement.setAttribute("width", "128");
        svgElement.setAttribute("height", "128");
        svgElement.setAttribute("fill", "currentColor");
        svgElement.setAttribute("viewBox", "0 0 16 16");
        svgElement.innerHTML = `<path d="M5.523 12.424q.21-.124.459-.238a8 8 0 0 1-.45.606c-.28.337-.498.516-.635.572l-.035.012a.3.3 0 0 1-.026-.044c-.056-.11-.054-.216.04-.36.106-.165.319-.354.647-.548m2.455-1.647q-.178.037-.356.078a21 21 0 0 0 .5-1.05 12 12 0 0 0 .51.858q-.326.048-.654.114m2.525.939a4 4 0 0 1-.435-.41q.344.007.612.054c.317.057.466.147.518.209a.1.1 0 0 1 .026.064.44.44 0 0 1-.06.2.3.3 0 0 1-.094.124.1.1 0 0 1-.069.015c-.09-.003-.258-.066-.498-.256M8.278 6.97c-.04.244-.108.524-.2.829a5 5 0 0 1-.089-.346c-.076-.353-.087-.63-.046-.822.038-.177.11-.248.196-.283a.5.5 0 0 1 .145-.04c.013.03.028.092.032.198q.008.183-.038.465z" /><path fill-rule="evenodd" d="M4 0h5.293A1 1 0 0 1 10 .293L13.707 4a1 1 0 0 1 .293.707V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2m5.5 1.5v2a1 1 0 0 0 1 1h2zM4.165 13.668c.09.18.23.343.438.419.207.075.412.04.58-.03.318-.13.635-.436.926-.786.333-.401.683-.927 1.021-1.51a11.7 11.7 0 0 1 1.997-.406c.3.383.61.713.91.95.28.22.603.403.934.417a.86.86 0 0 0 .51-.138c.155-.101.27-.247.354-.416.09-.181.145-.37.138-.563a.84.84 0 0 0-.2-.518c-.226-.27-.596-.4-.96-.465a5.8 5.8 0 0 0-1.335-.05 11 11 0 0 1-.98-1.686c.25-.66.437-1.284.52-1.794.036-.218.055-.426.048-.614a1.24 1.24 0 0 0-.127-.538.7.7 0 0 0-.477-.365c-.202-.043-.41 0-.601.077-.377.15-.576.47-.651.823-.073.34-.04.736.046 1.136.088.406.238.848.43 1.295a20 20 0 0 1-1.062 2.227 7.7 7.7 0 0 0-1.482.645c-.37.22-.699.48-.897.787-.21.326-.275.714-.08 1.103" />`;

        // Append SVG element
        imageDiv.appendChild(svgElement);
    }

    // Append badge
    imageDiv.appendChild(badgeSpan);

    var bodyDiv = document.createElement('div');
    bodyDiv.id = pdfData.id + '_pdf_body';
    bodyDiv.classList.add('card-body');

    var titleElement = document.createElement('h5');
    titleElement.id = pdfData.id + '_pdf_title';
    titleElement.classList.add('card-title');
    titleElement.textContent = pdfData.file_name || "N/A";

    var infoParagraph = document.createElement('p');
    infoParagraph.classList.add('pdf-info');

    const brElement = "<br>";

    var modifiedText = document.createElement('span');
    modifiedText.innerHTML = `<i class="bi bi-clock"></i><strong> Updated:</strong> `;
    var modifiedSpan = document.createElement('span');
    modifiedSpan.id = pdfData.id + '_pdf_modified';
    const now = new Date();
    const formattedDate = now.toLocaleDateString('de-DE').replace(/\./g, '.');
    const formattedTime = now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    modifiedSpan.textContent = pdfData.local_modified || `${formattedDate} ${formattedTime}`;
    modifiedSpan.innerHTML += brElement;

    var smbText = document.createElement('span');
    smbText.innerHTML = `<i class="bi bi-folder"></i><strong> SMB:</strong> `;
    var smbSpan = document.createElement('span');
    smbSpan.id = pdfData.id + '_pdf_smb';
    smbSpan.textContent = pdfData.local_filepath || "N/A";
    smbSpan.innerHTML += brElement;

    var cloudText = document.createElement('span');
    cloudText.innerHTML = `<i class="bi bi-cloud"></i><strong> Cloud:</strong> `;

    if (pdfData.web_url) {
        var cloudLink = document.createElement('a');
        cloudLink.id = pdfData.id + '_pdf_cloud';
        cloudLink.href = pdfData.web_url;
        cloudLink.textContent = pdfData.remote_filepath;
        cloudLink.innerHTML += brElement;
        cloudLink.target = '_blank'; // Open link in a new tab
        cloudText.appendChild(cloudLink);
    } else {
        var cloudSpan = document.createElement('span');
        cloudSpan.id = pdfData.id + '_pdf_cloud';
        cloudSpan.textContent = pdfData.remote_filepath || "Not available";
        cloudSpan.innerHTML += brElement;
        cloudText.appendChild(cloudSpan);
    }

    var statusText = document.createElement('span');
    const status_icon = getStatusIcon(pdfData.file_status);
    statusText.innerHTML = `<i class="bi ${status_icon}"></i><strong> Status:</strong> `;
    var statusSpan = document.createElement('span');
    statusSpan.id = pdfData.id + '_pdf_status';
    statusSpan.textContent = pdfData.file_status || "N/A";
    statusSpan.innerHTML += brElement;

    // Create segmented progress bar container
    const progressContainer = document.createElement('div');
    progressContainer.classList.add('progress-bar-wrapper');
    progressContainer.id = pdfData.id + '_progress_bar';

    const progressStep = pdfData.status_progressbar || 1;
    const isFailed = pdfData.file_status?.toLowerCase().includes("failed") || pdfData.file_status?.toLowerCase().includes("deleted");
    const isCompleted = pdfData.file_status?.toLowerCase().includes("completed");

    for (let i = 0; i < 5; i++) {
        const segment = document.createElement('div');
        segment.classList.add('progress-segment');

        if (isFailed) {
            segment.classList.add('failed');
        } else if (isCompleted) {
            segment.classList.add('completed');
        } else if (i < progressStep) {
            segment.classList.add('active');
        }

        progressContainer.appendChild(segment);
    }

    infoParagraph.appendChild(modifiedText);
    infoParagraph.appendChild(modifiedSpan);
    infoParagraph.appendChild(smbText);
    infoParagraph.appendChild(smbSpan);
    infoParagraph.appendChild(cloudText);
    infoParagraph.appendChild(statusText);
    infoParagraph.appendChild(statusSpan);

    bodyDiv.appendChild(titleElement);
    bodyDiv.appendChild(infoParagraph);

    cardDiv.appendChild(imageDiv);
    cardDiv.appendChild(bodyDiv);

    // Append progress bar to container and then to card
    cardDiv.appendChild(progressContainer);
    colDiv.appendChild(cardDiv);

    var pdfGrid = document.getElementById("pdfs_grid");
    if (pdfGrid.children.length >= entries_per_page) {
        pdfGrid.removeChild(pdfGrid.lastElementChild);
        console.log("Removed last child");
    }
    // Append the card to the container
    var parentElement = document.getElementById('pdfs_grid');
    var firstChild = parentElement.firstChild;
    parentElement.insertBefore(colDiv, firstChild);
}

function getStatusIcon(file_status) {
    const status = file_status?.toLowerCase() || "";
    let status_icon = "bi-hourglass"; // Default icon

    if (status.includes("pending")) {
        status_icon = "bi-hourglass";
    } else if (status.includes("processing")) {
        status_icon = "bi-gear";
    } else if (status.includes("completed")) {
        status_icon = "bi-check-circle";
    } else if (status.includes("failed")) {
        status_icon = "bi-x-circle";
    }

    return status_icon;
}

function updateProgressBar(pdfId, newStep) {
    const progressBar = document.getElementById(`${pdfId}_progress_bar`);
    if (!progressBar) return;

    const segments = progressBar.querySelectorAll('.progress-segment');

    // Clamp value to -1–5
    const clampedStep = Math.max(-1, Math.min(5, newStep));

    segments.forEach((segment, index) => {
        segment.classList.remove('active', 'failed', 'completed');

        if (clampedStep === -1) {
            segment.classList.add('failed');
        } else if (clampedStep === 5) {
            segment.classList.add('completed');
        } else if (index < clampedStep) {
            segment.classList.add('active');
        }
    });
}