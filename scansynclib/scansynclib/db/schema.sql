CREATE TABLE IF NOT EXISTS scanneddata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    created DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    modified DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    file_status TEXT NOT NULL DEFAULT 'Pending',
    previewimage_path TEXT,
    local_filepath TEXT,
    remote_filepath TEXT,
    additional_smb TEXT,
    web_url TEXT,
    pdf_pages INTEGER DEFAULT 0,
    status_code INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS smb_onedrive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    smb_name TEXT NOT NULL UNIQUE,
    onedrive_path TEXT NOT NULL,
    drive_id TEXT NOT NULL,
    folder_id TEXT NOT NULL,
    web_url TEXT,
    created DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS ocr_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanneddata_id INTEGER NOT NULL,
    started DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    finished DATETIME,
    ocr_status TEXT NOT NULL,
    ocr_error TEXT
);

CREATE TABLE IF NOT EXISTS file_naming_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanneddata_id INTEGER NOT NULL,
    started DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
    finished DATETIME,
    method TEXT,
    model TEXT,
    file_naming_status TEXT NOT NULL,
    success Boolean NOT NULL DEFAULT 0,
    error_description TEXT
);