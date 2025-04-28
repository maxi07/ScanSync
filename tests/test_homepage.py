import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


@pytest.fixture
def driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service(executable_path="/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)

    yield driver

    driver.quit()


def test_dashboard_text_first_start(driver):
    driver.get("http://web_service:5001")
    WebDriverWait(driver, 10).until(EC.title_contains("ScanSync"))
    assert "ScanSync" in driver.title
    assert "No content available yet. Start scanning your first PDF to see it here." in driver.page_source
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
