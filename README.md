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


## 🚀 Features
- **SMB Server**: Easily connect and manage your documents.
- **OCR Support**: Automatic text recognition in multiple languages.
- **OneDrive Integration**: Seamless syncing to your preferred location.
- **AI-Powered File Renaming**: Smart renaming using OpenAI.
- **Redundancy**: Reliable document handling with RabbitMQ.
- **Multiple Sync Targets**: Flexibility to sync across various locations.


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
   docker-compose up --build -d
   ```

Once started:
- Connect to the SMB server using:
  - **Username**: `ocr`
  - **Password**: `ocr`
  - **Share**: `scans`
- Any document added to the `scans` share will be automatically processed.
- Access the web server at your server's IP on port `5001`.


## 🛠 Development

For development purposes, you can use the built-in Flask server:
1. Update the `ENV` variable in the [docker-compose.yml](/docker-compose.yml) file to `development`.
2. Restart the application to enable debug output and Flask development mode.


## 🔮 Upcoming Features
- [ ] **Notifications**: Stay informed with real-time updates.


Thank you for using ScanSync! If you encounter any issues or have feature requests, feel free to open an issue on the [GitHub repository](https://github.com/maxi07/ScanSync).