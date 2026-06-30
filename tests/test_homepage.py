import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


def _render_progress_segments(driver, pdf_data):
    script = """
        const pdfData = arguments[0];
        const existingCol = document.getElementById(pdfData.id + '_col');
        if (existingCol) {
            existingCol.remove();
        }
        addPdfCard(pdfData);
        return Array.from(
            document.querySelectorAll(`#${pdfData.id}_progress_bar .progress-segment`)
        ).map((segment) => ({
            classes: Array.from(segment.classList),
            tooltip: segment.getAttribute('data-tooltip'),
            ariaLabel: segment.getAttribute('aria-label'),
        }));
    """
    return driver.execute_script(script, pdf_data)


@pytest.fixture
def driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1200x600")
    service = Service(executable_path="/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)

    yield driver

    driver.quit()


def test_dashboard_text_first_start(driver):
    driver.get("http://web-service:5001")
    WebDriverWait(driver, 10).until(EC.title_contains("ScanSync"))
    assert "ScanSync" in driver.title
    assert "Get started in three steps:" in driver.page_source
    widget_processing_content = driver.find_element(By.ID, "widget_processing_content").text
    assert "None" in widget_processing_content
    widget_processed_content = driver.find_element(By.ID, "widget_processed_content").text
    assert "None" in widget_processed_content
    dashboard_latest_timestamp_completed_string = driver.find_element(By.ID, "dashboard_latest_timestamp_completed_string").text
    assert "Never" in dashboard_latest_timestamp_completed_string
    dashboard_latest_timestamp_processing_string = driver.find_element(By.ID, "dashboard_latest_timestamp_processing_string").text
    assert "Never" in dashboard_latest_timestamp_processing_string

    dashboard_nav_link = driver.find_element(By.CSS_SELECTOR, "a.nav-link.active[aria-current='page'][href='/']")
    assert "active" in dashboard_nav_link.get_attribute("class")


def test_dashboard_sync_first_start(driver):
    driver.get("http://web-service:5001/sync")
    WebDriverWait(driver, 10).until(EC.title_contains("ScanSync"))
    assert "ScanSync" in driver.title
    assert "Set up or manage your OneDrive connections for syncing." in driver.page_source
    assert "No failed syncs found." in driver.page_source
    assert "Sort by:" not in driver.page_source

    sync_nav_link = driver.find_element(By.CSS_SELECTOR, "a.nav-link.active[href='/sync']")
    assert "active" in sync_nav_link.get_attribute("class")


def test_dashboard_settings_first_start_onedrive(driver):
    driver.get("http://web-service:5001/settings?tab=onedrive-tab")
    WebDriverWait(driver, 10).until(EC.title_contains("ScanSync"))
    assert "ScanSync" in driver.title
    assert "Settings" in driver.find_element(By.TAG_NAME, "h1").text

    settings_nav_link = driver.find_element(By.CSS_SELECTOR, "a.nav-link.active[href='/settings']")
    assert "active" in settings_nav_link.get_attribute("class")


def test_dashboard_settings_tabs(driver):
    driver.get("http://web-service:5001/settings?tab=ocr-tab")
    WebDriverWait(driver, 10).until(EC.title_contains("ScanSync"))

    assert "OCR settings will be available in the future." in driver.page_source

    file_naming_tab = driver.find_element(By.ID, "file-naming-tab")
    file_naming_tab.click()
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "file-naming-tabpanel"))
    )
    assert "Choose your automatic file naming method:" in driver.page_source


def test_dashboard_settings_file_naming_first_start(driver):
    driver.get("http://web-service:5001/settings?tab=file-naming-tab")
    WebDriverWait(driver, 10).until(EC.title_contains("ScanSync"))
    assert "ScanSync" in driver.title
    assert "Choose your automatic file naming method:" in driver.page_source
    none_button = driver.find_element(By.ID, "file_naming_none")
    assert none_button.get_attribute("checked") is not None
    assert "Saving will disable and delete existing OpenAI or Ollama configurations." in driver.page_source

    open_ai_button = driver.find_element(By.ID, "file_naming_openai")
    assert open_ai_button.get_attribute("checked") is None

    file_naming_nav_link = driver.find_element(By.CSS_SELECTOR, "a.nav-link.active[href='/settings']")
    assert "active" in file_naming_nav_link.get_attribute("class")


def test_dashboard_settings_ollama_first_start(driver):
    driver.get("http://web-service:5001/settings?tab=file-naming-tab")
    WebDriverWait(driver, 10).until(EC.title_contains("ScanSync"))
    assert "ScanSync" in driver.title

    driver.execute_script("document.querySelector(\"label[for='file_naming_ollama']\").click()")

    radio = driver.find_element(By.ID, "file_naming_ollama")
    print("Radio checked:", radio.is_selected())

    WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.ID, "file_naming_ollama").is_selected()
    )

    WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.ID, "ollama-options").is_displayed()
    )

    assert "Use your own Ollama server for automatic file naming." in driver.page_source
    assert driver.find_element(By.ID, "ollama_server_address").get_attribute("value") == "localhost"
    assert driver.find_element(By.ID, "ollama_server_port").get_attribute("value") == "11434"

    driver.find_element(By.ID, "ollama-connect-btn").click()
    # Wait for either the error div or the models section to become visible,
    # depending on whether Ollama is reachable in the test environment.
    WebDriverWait(driver, 15).until(
        lambda d: d.find_element(By.ID, "ollama-error").is_displayed()
        or d.find_element(By.ID, "ollama-models-section").is_displayed()
    )
    error_div = driver.find_element(By.ID, "ollama-error")
    models_section = driver.find_element(By.ID, "ollama-models-section")
    assert error_div.is_displayed() or models_section.is_displayed()


@pytest.mark.parametrize(
    "pdf_data,expected",
    [
        (
            {
                "id": 9901,
                "file_name": "progress-step-2.pdf",
                "file_status": "OCR Processing",
                "status_progressbar": 2,
                "badges": [],
            },
            [
                ("completed", "File Detection – Completed"),
                ("completed", "Reading Metadata – Completed"),
                ("current", "OCR – In Progress"),
                ("pending", "File Naming – Pending"),
                ("pending", "Upload – Pending"),
            ],
        ),
        (
            {
                "id": 9902,
                "file_name": "invalid-file.pdf",
                "file_status": "Invalid File",
                "status_progressbar": -1,
                "badges": [],
            },
            [
                ("failed", "File Detection – Failed"),
                ("pending", "Reading Metadata – Pending"),
                ("pending", "OCR – Pending"),
                ("pending", "File Naming – Pending"),
                ("pending", "Upload – Pending"),
            ],
        ),
        (
            {
                "id": 9903,
                "file_name": "ocr-failed.pdf",
                "file_status": "Failed",
                "status_progressbar": 3,
                "ocr_status": "INPUT_ERROR",
                "badges": [],
            },
            [
                ("completed", "File Detection – Completed"),
                ("completed", "Reading Metadata – Completed"),
                ("failed", "OCR – Failed"),
                ("pending", "File Naming – Pending"),
                ("pending", "Upload – Pending"),
            ],
        ),
        (
            {
                "id": 9904,
                "file_name": "naming-failed.pdf",
                "file_status": "Failed",
                "status_progressbar": 4,
                "file_naming_status": "NO_SERVER_CONNECTION",
                "badges": [],
            },
            [
                ("completed", "File Detection – Completed"),
                ("completed", "Reading Metadata – Completed"),
                ("completed", "OCR – Completed"),
                ("failed", "File Naming – Failed"),
                ("pending", "Upload – Pending"),
            ],
        ),
        (
            {
                "id": 9905,
                "file_name": "sync-failed.pdf",
                "file_status": "Sync Failed",
                "status_progressbar": 5,
                "badges": [],
            },
            [
                ("completed", "File Detection – Completed"),
                ("completed", "Reading Metadata – Completed"),
                ("completed", "OCR – Completed"),
                ("completed", "File Naming – Completed"),
                ("failed", "Upload – Failed"),
            ],
        ),
        (
            {
                "id": 9906,
                "file_name": "deleted.pdf",
                "file_status": "Deleted",
                "status_progressbar": 2,
                "badges": [],
            },
            [
                ("failed", "File Detection – Failed"),
                ("failed", "Reading Metadata – Failed"),
                ("failed", "OCR – Failed"),
                ("failed", "File Naming – Failed"),
                ("failed", "Upload – Failed"),
            ],
        ),
        (
            {
                "id": 9907,
                "file_name": "completed-with-ocr-failure.pdf",
                "file_status": "Completed",
                "status_progressbar": 5,
                "ocr_status": "UNSUPPORTED",
                "badges": [],
            },
            [
                ("completed", "File Detection – Completed"),
                ("completed", "Reading Metadata – Completed"),
                ("failed", "OCR – Failed"),
                ("completed", "File Naming – Completed"),
                ("completed", "Upload – Completed"),
            ],
        ),
    ],
)
def test_dashboard_progress_bar_step_statuses(driver, pdf_data, expected):
    driver.get("http://web-service:5001")
    WebDriverWait(driver, 10).until(EC.title_contains("ScanSync"))

    rendered = _render_progress_segments(driver, pdf_data)
    assert len(rendered) == 5

    for index, (expected_class, expected_tooltip) in enumerate(expected):
        segment = rendered[index]
        assert expected_class in segment["classes"]
        assert segment["tooltip"] == expected_tooltip
        assert segment["ariaLabel"] == expected_tooltip
