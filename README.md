[![Tests](https://github.com/maxi07/ScanSync/actions/workflows/pytest.yml/badge.svg)](https://github.com/maxi07/ScanSync/actions/workflows/pytest.yml)

<img src="web_service/src/static/images/ScanSync_logo_white.png#gh-dark-mode-only" width="30%">
<img src="web_service/src/static/images/ScanSync_logo_black.png#gh-light-mode-only" width="30%">

# ScanSync

ScanSync is a Python application designed to streamline document management by:
- Creating an SMB server with custom targets.
- Performing OCR (Optical Character Recognition) with [OCRmyPdf](https://github.com/ocrmypdf/OCRmyPDF) on new documents in English (ENG) and German (GER).
- Syncing documents to a specified location within your OneDrive.
- Renaming files intelligently using OpenAI.
- Ensuring redundancy with [RabbitMQ](https://www.rabbitmq.com).
- Supporting multiple sync targets.

![Dashboard](/doc/dashboard.jpg)

## 🚀 Features
- **SMB Server**: Easily connect and manage your documents.
- **OCR Support**: Automatic text recognition in multiple languages.
- **OneDrive Integration**: Seamless syncing to your preferred location.
- **AI-Powered File Renaming**: Smart renaming using OpenAI.
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


## 🔮 Upcoming Features
- [ ] **Notifications**: Stay informed with real-time updates.
- [ ] **OCR Settings**: Take control of OCR settings in the web interface


Thank you for using ScanSync! If you encounter any issues or have feature requests, feel free to open an issue on the [GitHub repository](https://github.com/maxi07/ScanSync).
