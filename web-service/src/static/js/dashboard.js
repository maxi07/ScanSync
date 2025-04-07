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

function updatePDFCard(pdfData) {
    console.log("Updating card id " + pdfData.id);
    // Find pdfcard suing id
    var pdfCard = document.getElementById(pdfData.id + '_pdf_card');
    // Update the title
    pdfCard.getElementsByClassName('card-title')[0].innerHTML = pdfData.file_name;
    // Update the badge
    pdfCard.getElementsByClassName('badge')[0].innerHTML = pdfData.pdf_pages;

    // Now update the pdf info
    var pdfModified = document.getElementById(pdfData.id + '_pdf_modified');
    pdfModified.innerHTML = pdfData.local_modified + "<br>";

    var pdfSMB = document.getElementById(pdfData.id + '_pdf_smb');
    pdfSMB.innerHTML = pdfData.local_filepath + "<br>";

    var pdfCloud = document.getElementById(pdfData.id + '_pdf_cloud');
    pdfCloud.innerHTML = pdfData.remote_filepath + "<br>";

    var pdfStatus = document.getElementById(pdfData.id + '_pdf_status');
    pdfStatus.innerHTML = pdfData.file_status + "<br>";

    // When previewimage_path of the pdfdata starts with "/static" then remove the current svg and add the image
    if (pdfData.previewimage_path.startsWith("/static")) {
        // Remove the svg
        try {
            var imgcontainer = document.getElementById(pdfData.id + '_pdf_card_image');
            var svg = imgcontainer.getElementsByTagName('svg')[0];
            svg.remove();
        } catch (err) {
            return;
        }

        // Add the image
        var image = document.createElement('img');
        image.id = pdfData.id + '_pdf_preview_image';
        image.classList.add('card-img-top', 'mx-auto');
        image.src = pdfData.previewimage_path;
        image.style.width = 'auto';
        image.style.height = '128px';
        imgcontainer.appendChild(image);
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
    badgeSpan.textContent = pdfData.pdf_pages;

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
    titleElement.textContent = pdfData.file_name;

    var infoParagraph = document.createElement('p');
    infoParagraph.classList.add('pdf-info');

    const brElement = "<br>";

    var modifiedText = document.createElement('span');
    modifiedText.innerHTML = `<i class="bi bi-clock"></i><strong> Updated:</strong> `;
    var modifiedSpan = document.createElement('span');
    modifiedSpan.id = pdfData.id + '_pdf_modified';
    modifiedSpan.textContent = pdfData.local_modified;
    modifiedSpan.innerHTML += brElement;

    var smbText = document.createElement('span');
    smbText.innerHTML = `<i class="bi bi-folder"></i><strong> SMB:</strong> `;
    var smbSpan = document.createElement('span');
    smbSpan.id = pdfData.id + '_pdf_smb';
    smbSpan.textContent = pdfData.local_filepath;
    smbSpan.innerHTML += brElement;

    var cloudText = document.createElement('span');
    cloudText.innerHTML = `<i class="bi bi-cloud"></i><strong> Cloud:</strong> `;
    var cloudSpan = document.createElement('span');
    cloudSpan.id = pdfData.id + '_pdf_cloud';
    cloudSpan.textContent = pdfData.remote_filepath;
    cloudSpan.innerHTML += brElement;
    cloudText.appendChild(cloudSpan);

    var statusText = document.createElement('span');
    statusText.innerHTML = `<i class="bi bi-hourglass"></i><strong> Status:</strong> `;
    var statusSpan = document.createElement('span');
    statusSpan.id = pdfData.id + '_pdf_status';
    statusSpan.textContent = pdfData.file_status;
    statusSpan.innerHTML += brElement;

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


