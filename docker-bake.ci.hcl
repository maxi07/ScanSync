target "web-service" {
  cache-from = ["type=gha,scope=scansync-web"]
  cache-to   = ["type=gha,scope=scansync-web,mode=max"]
}

target "ocr_service" {
  cache-from = ["type=gha,scope=scansync-ocr"]
  cache-to   = ["type=gha,scope=scansync-ocr,mode=max"]
}

target "metadata_service" {
  cache-from = ["type=gha,scope=scansync-metadata"]
  cache-to   = ["type=gha,scope=scansync-metadata,mode=max"]
}

target "detection_service" {
  cache-from = ["type=gha,scope=scansync-detection"]
  cache-to   = ["type=gha,scope=scansync-detection,mode=max"]
}

target "file_naming_service" {
  cache-from = ["type=gha,scope=scansync-naming"]
  cache-to   = ["type=gha,scope=scansync-naming,mode=max"]
}

target "upload_service" {
  cache-from = ["type=gha,scope=scansync-upload"]
  cache-to   = ["type=gha,scope=scansync-upload,mode=max"]
}

target "smb_service" {
  cache-from = ["type=gha,scope=scansync-smb"]
  cache-to   = ["type=gha,scope=scansync-smb,mode=max"]
}

target "e2e" {
  cache-from = ["type=gha,scope=scansync-test-runner"]
  cache-to   = ["type=gha,scope=scansync-test-runner,mode=max"]
}

target "test_service" {
  cache-from = ["type=gha,scope=scansync-test-runner"]
  cache-to   = ["type=gha,scope=scansync-test-runner,mode=max"]
}
