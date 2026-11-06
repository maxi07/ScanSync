"""User journeys through Chromium, Samba and all real ScanSync workers."""

import hashlib
import io
from pathlib import Path
import subprocess
import uuid

from pypdf import PdfReader
import pytest
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from conftest import API_URL, ARTIFACTS, BASE_URL, DOWNLOADS, RESOURCES, click, mock_state, rows


pytestmark = pytest.mark.e2e


def deliver(browser, source, targets=('Invoices',), label='scan'):
    last_id = rows('SELECT COALESCE(MAX(id), 0) AS id FROM scanneddata')[0]['id']
    name = f'{label}_{uuid.uuid4().hex[:8]}.pdf'
    commands = []
    for target in targets:
        commands.extend((f'put "{source}" "{target}/.{name}"', f'rename "{target}/.{name}" "{target}/{name}"'))
    result = subprocess.run(
        ['smbclient', '//smb_service/Scans', '-U', 'ocr%ocr', '-m', 'SMB3', '-c', '; '.join(commands)],
        text=True, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    found = WebDriverWait(browser, 45).until(lambda driver: rows('SELECT * FROM scanneddata WHERE id > ? ORDER BY id', (last_id,)))
    assert len(found) == 1, found
    item = found[0]
    assert item['file_name'] == name
    WebDriverWait(browser, 30).until(EC.visibility_of_element_located((By.ID, f'{item["id"]}_col')))
    return item, name


def wait_status(browser, item, expected, timeout=180):
    selector = (By.ID, f'{item["id"]}_pdf_status')
    WebDriverWait(browser, timeout).until(EC.text_to_be_present_in_element(selector, expected))
    result = rows('SELECT * FROM scanneddata WHERE id = ?', (item['id'],))[0]
    assert result['file_status'] == expected
    browser.save_screenshot(str(ARTIFACTS / f'{item["id"]}-{expected.replace(" ", "_")}.png'))
    return result


def uploaded_pdf(upload):
    response = requests.get(f'{API_URL}/uploads/{upload["id"]}', timeout=20)
    response.raise_for_status()
    return response.content, PdfReader(io.BytesIO(response.content))


def assert_success(browser, item, source_name, targets=('Invoices',), pages=4, has_text=True, ocr_status='COMPLETED', named=True):
    completed = wait_status(browser, item, 'Completed')
    uploads = mock_state()['uploads']
    assert len(uploads) == len(targets), uploads
    assert {upload['folder'] for upload in uploads} == ({'folder-a', 'folder-b'} if len(targets) == 2 else {'folder-a'})
    for upload in uploads:
        assert upload['name'] == ('E2E_document.pdf' if named else source_name)
        content, pdf = uploaded_pdf(upload)
        assert len(pdf.pages) == pages
        assert bool(''.join(page.extract_text() or '' for page in pdf.pages).strip()) == has_text
        assert b'pdfaid:part' in content
        assert upload['size'] == len(content)
    assert completed['pdf_pages'] == pages
    assert completed['source_file_name'] == source_name
    assert completed['ocr_status'] == ocr_status
    jobs = rows('SELECT * FROM ocr_jobs WHERE scanneddata_id = ?', (item['id'],))
    assert len(jobs) == 1 and jobs[0]['ocr_status'] == ocr_status and jobs[0]['finished']
    sync = rows('SELECT * FROM sync_jobs WHERE scanneddata_id = ?', (item['id'],))
    assert len(sync) == 1 and sync[0]['success'] == 1 and sync[0]['finished']
    for target in targets:
        assert not (Path('/mnt/scans') / target / source_name).exists()
        assert not (Path('/mnt/scans') / target / f'{Path(source_name).stem}_OCR.pdf').exists()
    preview = browser.find_element(By.ID, f'{item["id"]}_pdf_preview_image')
    WebDriverWait(browser, 15).until(lambda driver: driver.execute_script('return arguments[0].complete && arguments[0].naturalWidth > 0;', preview))
    assert len(completed['web_url'].split(',')) == len(targets)
    return completed


def download_failed(browser, item, expected_bytes):
    browser.get(f'{BASE_URL}/sync')
    previous = {path: path.stat().st_mtime_ns for path in DOWNLOADS.glob('*.pdf')}
    click(browser, f'[id="{item["id"]}_download_button"]')
    downloaded = WebDriverWait(browser, 30).until(
        lambda driver: next((path for path in DOWNLOADS.glob('*.pdf')
                             if path.stat().st_mtime_ns != previous.get(path) and path.read_bytes() == expected_bytes), None)
    )
    assert downloaded.read_bytes() == expected_bytes
    return downloaded


def test_sz1_first_start_tabs_and_configuration(configured):
    assert rows('SELECT smb_name FROM smb_onedrive ORDER BY smb_name') == [{'smb_name': 'Archive'}, {'smb_name': 'Invoices'}]
    state = mock_state()
    assert state['authorized']
    assert any(call['path'] == '/openai/v1/responses' and call['status'] == 200 for call in state['calls'])
    configured.get(f'{BASE_URL}/settings?tab=file-naming-tab')
    assert configured.find_element(By.ID, 'file_naming_openai').is_selected()
    assert configured.find_element(By.ID, 'delete-openai-button').is_displayed()


def test_sz2_single_valid_document(scenario):
    main_window = scenario.current_window_handle
    scenario.switch_to.new_window('tab')
    try:
        scenario.get(BASE_URL)
        item, name = deliver(scenario, RESOURCES / 'cardinal.pdf', label='sz2')
        assert_success(scenario, item, name)
        scenario.close()
        scenario.switch_to.window(main_window)
        wait_status(scenario, item, 'Completed', timeout=30)
        naming = rows('SELECT * FROM file_naming_jobs WHERE scanneddata_id = ?', (item['id'],))
        assert len(naming) == 1 and naming[0]['success'] == 1 and naming[0]['method'] == 'openai'
    finally:
        for handle in scenario.window_handles:
            if handle != main_window:
                scenario.switch_to.window(handle)
                scenario.close()
        scenario.switch_to.window(main_window)


def test_sz3_same_document_to_two_targets(scenario):
    item, name = deliver(scenario, RESOURCES / 'cardinal.pdf', targets=('Invoices', 'Archive'), label='sz3')
    completed = assert_success(scenario, item, name, targets=('Invoices', 'Archive'))
    assert set(completed['remote_filepath'].split(',')) == {'/Invoices', '/Archive'}
    assert completed['additional_smb'] in ('Archive', 'Invoices')
    state = mock_state()
    assert len([call for call in state['calls'] if call['path'] == '/openai/v1/responses']) == 1
    digests = {hashlib.sha256(uploaded_pdf(upload)[0]).hexdigest() for upload in state['uploads']}
    assert len(digests) == 1
    assert len(rows('SELECT * FROM ocr_jobs WHERE scanneddata_id = ?', (item['id'],))) == 1


@pytest.mark.parametrize('resource,pages,has_text', [
    ('aspect.pdf', 1, True),
    ('blank.pdf', 1, False),
    ('graph_ocred.pdf', 1, True),
    ('multipage.pdf', 6, True),
    ('invalid.pdf', None, False),
])
def test_sz4_other_pdfs(scenario, resource, pages, has_text):
    item, name = deliver(scenario, RESOURCES / resource, label=f'sz4_{Path(resource).stem}')
    if resource == 'invalid.pdf':
        failed = wait_status(scenario, item, 'Invalid File', timeout=360)
        assert mock_state()['uploads'] == []
        assert not rows('SELECT * FROM ocr_jobs WHERE scanneddata_id = ?', (item['id'],))
        assert not rows('SELECT * FROM file_naming_jobs WHERE scanneddata_id = ?', (item['id'],))
        failed_path = Path('/mnt/scans/failed-documents') / failed['file_name']
        assert failed_path.read_bytes() == (RESOURCES / resource).read_bytes()
        download_failed(scenario, item, (RESOURCES / resource).read_bytes())
    else:
        assert_success(scenario, item, name, pages=pages, has_text=has_text,
                       ocr_status='COMPLETED' if has_text else 'NO_TEXT', named=has_text)
        if not has_text:
            assert not [call for call in mock_state()['calls'] if call['path'] == '/openai/v1/responses']
            naming = rows('SELECT * FROM file_naming_jobs WHERE scanneddata_id = ?', (item['id'],))
            assert len(naming) == 1 and naming[0]['file_naming_status'] == 'NO_PDF_TEXT'


def test_sz5_openai_failure_keeps_original_name(scenario):
    mock_state(openai_error=True)
    item, name = deliver(scenario, RESOURCES / 'cardinal.pdf', label='sz5')
    assert_success(scenario, item, name, named=False)
    naming = rows('SELECT * FROM file_naming_jobs WHERE scanneddata_id = ?', (item['id'],))
    assert len(naming) == 1 and naming[0]['success'] == 0
    assert naming[0]['file_naming_status'] == 'FAILED'
    assert 'HTTP 500' in naming[0]['error_description']
    attempts = [call for call in mock_state()['calls'] if call['path'] == '/openai/v1/responses']
    assert len(attempts) >= 2 and all(call['status'] == 500 for call in attempts)
    click(scenario, 'nav a[href="/settings"]')
    click(scenario, '#file-naming-tab')
    click(scenario, '[data-bs-target="#logsCollapse"]')
    WebDriverWait(scenario, 30).until(lambda driver: 'HTTP 500' in driver.find_element(By.ID, 'logs-table').text)


def test_sz6_upload_failure_download_and_resubmit(scenario):
    mock_state(upload_error=True)
    original = (RESOURCES / 'cardinal.pdf').read_bytes()
    item, name = deliver(scenario, RESOURCES / 'cardinal.pdf', label='sz6')
    failed = wait_status(scenario, item, 'Sync Failed')
    assert mock_state()['uploads'] == []
    attempts = [call for call in mock_state()['calls'] if call['method'] == 'PUT']
    assert attempts and all(call['status'] == 503 for call in attempts)
    failed_path = Path('/mnt/scans/failed-documents') / failed['file_name']
    assert failed_path.read_bytes() == original
    assert not (Path('/mnt/scans/Invoices') / name).exists()
    assert not (Path('/mnt/scans/Invoices') / f'{Path(name).stem}_OCR.pdf').exists()
    sync = rows('SELECT * FROM sync_jobs WHERE scanneddata_id = ?', (item['id'],))
    assert len(sync) == 1 and sync[0]['success'] == 0 and sync[0]['sync_status'] == 'SYNC_FAILED'
    assert sync[0]['finished'] and sync[0]['error_description']
    downloaded = download_failed(scenario, item, original)
    mock_state(upload_error=False, clear=True)
    scenario.get(BASE_URL)
    retry, retry_name = deliver(scenario, downloaded, label='sz6_retry')
    assert_success(scenario, retry, retry_name)
    assert failed_path.read_bytes() == original
    scenario.get(f'{BASE_URL}/sync')
    click(scenario, f'[id="{item["id"]}_failedpdf_row"] [id="{item["id"]}_delete_button"]')
    WebDriverWait(scenario, 30).until(EC.invisibility_of_element_located((By.ID, f'{item["id"]}_failedpdf_row')))
    WebDriverWait(scenario, 30).until(lambda driver: not failed_path.exists())
    assert rows('SELECT file_status FROM scanneddata WHERE id = ?', (item['id'],))[0]['file_status'] == 'Deleted'
