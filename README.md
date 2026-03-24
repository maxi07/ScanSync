[![Tests](https://github.com/maxi07/ScanSync/actions/workflows/pytest.yml/badge.svg)](https://github.com/maxi07/ScanSync/actions/workflows/pytest.yml)

<img src="web_service/src/static/images/ScanSync_logo_white.png#gh-dark-mode-only" width="30%" alt="ScanSync logo white for dark mode">
<img src="web_service/src/static/images/ScanSync_logo_black.png#gh-light-mode-only" width="30%" alt="ScanSync logo black for light mode">

# ScanSync

ScanSync is a Python application designed to streamline document management by:
- Creating an SMB server with custom targets.
- Performing OCR (Optical Character Recognition) with [OCRmyPdf](https://github.com/ocrmypdf/OCRmyPDF) on new documents in English (ENG) and German (GER).
- Syncing documents to a specified location within your OneDrive.
- Renaming files intelligently using [OpenAI](https://www.chatgpt.com) or your local [Ollama](https://www.ollama.com) server.
- Ensuring redundancy with [RabbitMQ](https://www.rabbitmq.com).
- Supporting multiple sync targets.

![Dashboard](/doc/dashboard.jpg)

## 🚀 Features
- **SMB Server**: Easily connect and manage your documents.
- **OCR Support**: Automatic text recognition in multiple languages.
- **OneDrive Integration**: Seamless syncing to your preferred location.
- **AI-Powered File Renaming**: Smart renaming using using [OpenAI](https://www.chatgpt.com) or your local [Ollama](https://www.ollama.com) server..
- **Redundancy**: Reliable document handling with RabbitMQ.
- **Multiple Sync Targets**: Flexibility to sync across various locations.

## Why this project?
I ran into the following issue: I wanted to scan a document using a regular network scanner, OCR that file and move it automatically to SharePoint or OneDrive. There are ver expensive scanners that do have that option, but buying new hardware was out of scope. Then there also is 3rd party software, but it usually requires paid cloud services and subscriptions: Not suitable for a small business or even personal use. Therefore this application, that enables you to use a regular network scanner, make the document searchable by running OCR and then automatically pushing it into your desired OneDrive location. No big hastle, everything local and for free (except the optional OpenAI file naming, but the cost is in the cents.)


## 📦 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/maxi07/ScanSync.git
   ```
2. Install dependencies:
   - [Docker](https://www.docker.com)
   - [Docker Compose](https://docs.docker.com/compose/install/)
3. Start the application:
   ```bash
   docker compose up --build -d
   ```

Once started:
- Connect to the SMB server using:
  - **Username**: `ocr`
  - **Password**: `ocr`
  - **Share**: `Scans`
- Access the web server at your server's IP on port `5001`.
- Setup your onedrive connection, add a smb share and start scanning

## 🛠 Development

For development purposes, you can use the built-in Flask server:
1. Update the `ENV` variable in the [docker-compose.yml](/docker-compose.yml) file to `development`.
2. Restart the application to enable debug output and Flask development mode.
3. Run pytests via the [run-tests.sh](run-tests.sh) script (Spins up a docker [test-service](/test_service/Dockerfile))


## 📡 API

### `GET /api/status`

Returns aggregated document processing status including per-stage breakdowns, currently processing items, and recent completion history.

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `processed_pdfs` | `int` | Count of completed documents |
| `processing_pdfs` | `int` | Count of in-progress documents |
| `latest_processing_timestamp` | `string\|null` | Most recent processing update timestamp |
| `latest_completed_timestamp` | `string\|null` | Most recent completion timestamp |
| `latest_created_name` | `string\|null` | Filename of the latest document |
| `latest_created_status` | `int\|null` | Status code of the latest document |
| `total_pdfs` | `int` | Total document count across all statuses |
| `failed_pdfs` | `int` | Count of failed documents |
| `avg_processing_seconds` | `float\|null` | Average processing time for completed documents |
| `processing_details` | `array` | Breakdown of in-progress documents grouped by status |
| `currently_processing` | `array` | List of individual documents currently being processed |
| `recent_files` | `array` | Last 5 completed or failed documents with timestamps |

<details>
<summary>Example response</summary>

```json
{
  "processed_pdfs": 10,
  "processing_pdfs": 3,
  "latest_processing_timestamp": "2024-06-01 12:00:00",
  "latest_completed_timestamp": "2024-06-01 11:30:00",
  "latest_created_name": "invoice.pdf",
  "latest_created_status": 2,
  "total_pdfs": 15,
  "failed_pdfs": 2,
  "avg_processing_seconds": 45.68,
  "processing_details": [
    {"status": "OCR Processing", "status_code": 2, "count": 2},
    {"status": "Reading Metadata", "status_code": 1, "count": 1}
  ],
  "currently_processing": [
    {
      "id": 12,
      "file_name": "scan1.pdf",
      "status": "OCR Processing",
      "status_code": 2,
      "created": "2024-06-01 12:00:00",
      "pdf_pages": 3
    }
  ],
  "recent_files": [
    {
      "id": 11,
      "file_name": "doc1.pdf",
      "status": "Completed",
      "status_code": 5,
      "created": "2024-06-01 10:00:00",
      "completed": "2024-06-01 10:01:00",
      "pdf_pages": 2
    }
  ]
}
```

</details>

## 🔮 Upcoming Features
- **Notifications**: Stay informed with real-time updates.
- **OCR Settings**: Take control of OCR settings in the web interface


Thank you for using ScanSync! If you encounter any issues or have feature requests, feel free to open an issue on the [GitHub repository](https://github.com/maxi07/ScanSync).
