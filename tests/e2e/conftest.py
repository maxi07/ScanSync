"""Browser setup and read-only observations of the real document pipeline."""

import json
import os
from pathlib import Path
import re
import sqlite3

import pytest
import requests
from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = os.environ.get('E2E_BASE_URL', 'http://web-service:5001')
API_URL = os.environ.get('E2E_API_URL', 'http://mock-api:8080')
ARTIFACTS = Path('/artifacts')
DOWNLOADS = ARTIFACTS / 'downloads'
RESOURCES = Path(__file__).resolve().parents[1] / 'resources'


def rows(query, params=()):
    with sqlite3.connect('file:/app/data/scansync.db?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(query, params)]


def mock_state(**changes):
    response = requests.post(f'{API_URL}/control', json=changes, timeout=10) if changes else requests.get(f'{API_URL}/control', timeout=10)
    response.raise_for_status()
    return response.json()


@pytest.fixture(scope='session')
def browser(request):
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    DOWNLOADS.chmod(0o777)
    options = Options()
    for argument in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1440,1000'):
        options.add_argument(argument)
    options.add_experimental_option('prefs', {
        'download.default_directory': str(DOWNLOADS),
        'download.prompt_for_download': False,
        'plugins.always_open_pdf_externally': True,
    })
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    driver = webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=options)
    driver.execute_cdp_cmd('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(DOWNLOADS)})
    driver.set_page_load_timeout(60)
    request.session.e2e_browser = driver
    yield driver
    driver.quit()


def click(browser, selector):
    def try_click(driver):
        element = EC.element_to_be_clickable((By.CSS_SELECTOR, selector))(driver)
        if not element:
            return False
        driver.execute_script('arguments[0].scrollIntoView({block: "center"});', element)
        element.click()
        return True

    WebDriverWait(browser, 30, ignored_exceptions=(ElementClickInterceptedException, StaleElementReferenceException)).until(try_click)


def fill(browser, field_id, value):
    field = WebDriverWait(browser, 30).until(EC.visibility_of_element_located((By.ID, field_id)))
    field.clear()
    field.send_keys(value)


def accept_alert(browser, expected):
    alert = WebDriverWait(browser, 30).until(EC.alert_is_present())
    message = alert.text
    alert.accept()
    assert expected.lower() in message.lower(), message


def add_mapping(browser, smb_name, folder_id):
    click(browser, '#manage_path_mapping_button')
    click(browser, '#add_path_mapping_button')
    fill(browser, 'local_path', smb_name)
    click(browser, '#remote_path')
    click(browser, f'#onedrivelistgroup [data-item-id="{folder_id}"]')
    assert browser.find_element(By.ID, 'remote_path').get_attribute('value')
    click(browser, '#submit_form_path_mapping_button')
    WebDriverWait(browser, 30).until(lambda driver: driver.execute_script(
        'return document.readyState === "complete" && Array.from(document.querySelectorAll("#pathmappingscontainer .smb-badge"))'
        '.some(element => element.textContent.trim() === arguments[0]);', smb_name,
    ))


@pytest.fixture(scope='session')
def configured(browser):
    assert rows('SELECT COUNT(*) AS count FROM scanneddata')[0]['count'] == 0
    assert rows('SELECT COUNT(*) AS count FROM smb_onedrive')[0]['count'] == 0
    assert not mock_state()['authorized']
    browser.get(BASE_URL)
    assert 'Get started in three steps:' in browser.page_source
    assert browser.find_element(By.ID, 'dashboard_latest_timestamp_completed_string').text == 'Never'
    browser.save_screenshot(str(ARTIFACTS / 'first-start.png'))

    click(browser, 'nav a[href="/sync"]')
    assert 'No failed syncs found.' in browser.page_source
    click(browser, 'nav a[href="/settings"]')
    for tab in ('smb', 'ocr', 'file-naming', 'onedrive'):
        click(browser, f'#{tab}-tab')
        WebDriverWait(browser, 30).until(EC.visibility_of_element_located((By.ID, f'{tab}-tabpanel')))

    click(browser, '[data-bs-target="#collapseOne"]')
    WebDriverWait(browser, 30).until(EC.invisibility_of_element_located((By.ID, 'collapseOne')))
    click(browser, '[data-bs-target="#collapseCredentials"]')
    fill(browser, 'clientID', '00000000-0000-4000-8000-000000000001')
    click(browser, '#onedrive-settings-form button[type="submit"]')
    accept_alert(browser, 'success')
    click(browser, '[data-bs-target="#collapseUser"]')
    main_window = browser.current_window_handle
    click(browser, '#onedrive-login-button a')
    WebDriverWait(browser, 30).until(EC.number_of_windows_to_be(2))
    login_window = next(handle for handle in browser.window_handles if handle != main_window)
    browser.switch_to.window(login_window)
    code = WebDriverWait(browser, 30).until(lambda driver: driver.find_element(By.ID, 'user-code').text)
    assert code == 'E2E-CODE'
    click(browser, '#verification-url')
    WebDriverWait(browser, 30).until(EC.number_of_windows_to_be(3))
    browser.switch_to.window(next(handle for handle in browser.window_handles if handle not in (main_window, login_window)))
    fill(browser, 'code', code)
    click(browser, 'button[type="submit"]')
    WebDriverWait(browser, 30).until(EC.text_to_be_present_in_element((By.TAG_NAME, 'h1'), 'Signed in as ScanSync E2E'))
    browser.close()
    browser.switch_to.window(main_window)
    WebDriverWait(browser, 45).until(EC.number_of_windows_to_be(1))
    WebDriverWait(browser, 30).until(EC.visibility_of_element_located((By.ID, 'onedrive-user-info')))
    assert 'e2e@example.test' in browser.find_element(By.ID, 'onedrive-user-info').text

    click(browser, '#file-naming-tab')
    click(browser, 'label[for="file_naming_openai"]')
    fill(browser, 'openai_key', 'sk-e2e-not-a-real-key-00000000')
    click(browser, '#save-openai-button')
    accept_alert(browser, 'continue')
    accept_alert(browser, 'success')
    WebDriverWait(browser, 30).until(EC.visibility_of_element_located((By.ID, 'delete-openai-button')))
    click(browser, 'nav a[href="/sync"]')
    add_mapping(browser, 'Invoices', 'folder-a')
    add_mapping(browser, 'Archive', 'folder-b')
    browser.save_screenshot(str(ARTIFACTS / 'configured.png'))
    return browser


@pytest.fixture
def scenario(configured):
    mock_state(clear=True, openai_error=False, upload_error=False)
    configured.get(BASE_URL)
    yield configured
    unexpected = [call for call in mock_state()['calls'] if call['status'] == 501]
    mock_state(openai_error=False, upload_error=False)
    assert not unexpected, unexpected


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    if report.failed:
        prefix = ARTIFACTS / re.sub(r'[^A-Za-z0-9_.-]', '_', item.nodeid)
        driver = getattr(item.session, 'e2e_browser', None)
        if driver is not None:
            try:
                driver.save_screenshot(f'{prefix}.png')
                Path(f'{prefix}.html').write_text(driver.page_source)
                Path(f'{prefix}.browser.json').write_text(json.dumps(driver.get_log('browser'), indent=2))
            except Exception as error:
                Path(f'{prefix}.capture-error.txt').write_text(str(error))
        try:
            Path(f'{prefix}.mock.json').write_text(json.dumps(mock_state(), indent=2))
            snapshot = {table: rows(f'SELECT * FROM {table}') for table in ('scanneddata', 'ocr_jobs', 'file_naming_jobs', 'sync_jobs')}
            Path(f'{prefix}.pipeline.json').write_text(json.dumps(snapshot, indent=2))
        except Exception as error:
            Path(f'{prefix}.state-error.txt').write_text(str(error))
