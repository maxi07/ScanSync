import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock
from scansynclib.ProcessItem import ProcessItem, ItemType, OCRStatus, ProcessStatus


def test_pdfa_preserves_multicharacter_tounicode(tmp_path, caplog, recwarn):
    import shutil
    import subprocess

    import pytest
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    ocrmypdf = pytest.importorskip("ocrmypdf")
    pikepdf = pytest.importorskip("pikepdf")
    if not shutil.which("gs"):
        pytest.skip("Run this regression test in the OCR image with Ghostscript installed")
    version = subprocess.check_output(["gs", "--version"], text=True).strip()
    assert tuple(int(part) for part in version.split(".")) >= (10, 7, 0)

    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fpdf import FPDF

    glyph_names = [".notdef", "fi", "fl"]
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((550, 0))
    pen.lineTo((550, 700))
    pen.lineTo((50, 700))
    pen.closePath()
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_names)
    builder.setupGlyf({name: pen.glyph() for name in glyph_names})
    builder.setupHorizontalMetrics({name: (600, 0) for name in glyph_names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap({0xFB01: "fi", 0xFB02: "fl"})
    builder.setupNameTable({
        "familyName": "Regression", "styleName": "Regular",
        "uniqueFontIdentifier": "Regression", "fullName": "Regression Regular",
        "psName": "Regression-Regular",
    })
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    font_path = tmp_path / "regression.ttf"
    builder.save(font_path)
    document = FPDF()
    document.add_font("Regression", fname=font_path)
    document.add_page()
    document.set_font("Regression", size=24)
    document.text(20, 40, "\ufb01\ufb02")
    original = tmp_path / "embedded-font.pdf"
    document.output(original)
    writer = PdfWriter(original)
    for reference in writer.pages[0]["/Resources"]["/Font"].values():
        font = reference.get_object()
        mappings = font["/ToUnicode"].get_data()
        assert b"<FB01>" in mappings and b"<FB02>" in mappings
        cmap = DecodedStreamObject()
        cmap.set_data(mappings.replace(b"<FB01>", b"<00660069>").replace(b"<FB02>", b"<0066006C>"))
        font[NameObject("/ToUnicode")] = writer._add_object(cmap)
    source = tmp_path / "multicharacter.pdf"
    output = tmp_path / "multicharacter-pdfa.pdf"
    writer.write(source)

    assert PdfReader(source).pages[0].extract_text() == "fifl"
    assert ocrmypdf.ocr(source, output, output_type="pdfa", pdfa_backend="ghostscript", skip_text=True, optimize=2, jpeg_quality=80) == 0
    assert not any("jpg_quality" in str(warning.message) for warning in recwarn)
    assert PdfReader(output).pages[0].extract_text().strip() == "fifl"
    with pikepdf.open(output) as pdf:
        assert pdf.open_metadata()["pdfaid:part"] in ("1", "2", "3")
    assert not any("drops ToUnicode" in record.message or "jpg_quality" in record.message for record in caplog.records)


class TestOCRTextVerification:
    """Test OCR text verification functionality without importing the main OCR service."""

    def test_extract_text_returns_empty_string_on_empty_pdf(self):
        """Test that extract_text returns empty string for a PDF with no text."""
        from scansynclib.helpers import extract_text

        # Create a temporary file that simulates an empty PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(b"%PDF-1.4\n")  # Minimal PDF header
            temp_file_path = temp_file.name

        try:
            # extract_text should return empty string for malformed/empty PDF
            result = extract_text(temp_file_path)
            assert result == ""
        finally:
            os.unlink(temp_file_path)

    def test_extract_text_returns_empty_string_on_nonexistent_file(self):
        """Test that extract_text returns empty string for non-existent file."""
        from scansynclib.helpers import extract_text

        result = extract_text("/nonexistent/file.pdf")
        assert result == ""

    @patch('scansynclib.helpers.PdfReader')
    def test_extract_text_preserves_whitespace(self, mock_pdf_reader):
        """Test that extract_text returns the raw text without stripping whitespace."""
        from scansynclib.helpers import extract_text

        # Mock the PDF reader to return text with whitespace
        mock_page = Mock()
        mock_page.extract_text.return_value = "  \n\t  Some text  \n\t  "
        mock_reader = Mock()
        mock_reader.pages = [mock_page]
        mock_pdf_reader.return_value = mock_reader

        result = extract_text("dummy_path.pdf")
        assert result == "  \n\t  Some text  \n\t  "  # Should return raw text, not stripped

    @patch('scansynclib.helpers.PdfReader')
    def test_extract_text_respects_max_pages(self, mock_pdf_reader):
        """Test that extract_text stops after max_pages."""
        from scansynclib.helpers import extract_text

        pages = [Mock() for _ in range(5)]
        for i, p in enumerate(pages):
            p.extract_text.return_value = f"Page {i}"
        mock_reader = Mock()
        mock_reader.pages = pages
        mock_pdf_reader.return_value = mock_reader

        result = extract_text("dummy.pdf", max_pages=2)
        assert result == "Page 0\nPage 1"

    @patch('scansynclib.helpers.PdfReader')
    def test_extract_text_respects_max_chars(self, mock_pdf_reader):
        """Test that extract_text truncates at max_chars."""
        from scansynclib.helpers import extract_text

        mock_page = Mock()
        mock_page.extract_text.return_value = "A" * 100
        mock_reader = Mock()
        mock_reader.pages = [mock_page, mock_page, mock_page]
        mock_pdf_reader.return_value = mock_reader

        result = extract_text("dummy.pdf", max_chars=50)
        assert len(result) == 50

    def test_process_item_has_ocr_file_attribute(self):
        """Test that ProcessItem correctly sets the OCR file path."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file_path = temp_file.name

        try:
            item = ProcessItem(temp_file_path, ItemType.PDF)

            # Verify OCR file path is set correctly
            assert hasattr(item, 'ocr_file')
            assert item.ocr_file.endswith('_OCR.pdf')
            assert item.ocr_status == OCRStatus.UNKNOWN
        finally:
            os.unlink(temp_file_path)


def _load_ocr_main():
    """
    Load ocr_service.main with all heavy external dependencies mocked so it
    can be imported in a unit-test environment (no RabbitMQ, no Redis, no DB).
    Returns (module, mock_ocrmypdf) so callers can reuse the exception classes.
    """
    # Build lightweight exception classes that match the real ones structurally
    mock_ocrmypdf = MagicMock()
    mock_ocrmypdf.UnsupportedImageFormatError = type(
        'UnsupportedImageFormatError', (Exception,), {})
    mock_ocrmypdf.DpiError = type('DpiError', (Exception,), {})
    mock_ocrmypdf.InputFileError = type('InputFileError', (Exception,), {})
    mock_ocrmypdf.OutputFileAccessError = type('OutputFileAccessError', (Exception,), {})
    mock_ocrmypdf.MissingDependencyError = type('MissingDependencyError', (Exception,), {})

    mock_pika = MagicMock()
    mock_pika.exceptions = MagicMock()
    mock_pika.exceptions.AMQPConnectionError = Exception

    mock_settings_mod = MagicMock()
    mock_settings_mod.settings = MagicMock()
    mock_settings_mod.settings.file_naming = MagicMock()
    mock_settings_mod.settings.file_naming.ollama_server_url = None
    mock_settings_mod.settings.file_naming.ollama_server_port = None
    mock_settings_mod.settings.file_naming.ollama_model = None
    mock_settings_mod.settings.file_naming.openai_api_key = None

    module_patches = {
        'ocrmypdf': mock_ocrmypdf,
        'pika': mock_pika,
        'pika.exceptions': mock_pika.exceptions,
        'scansynclib.settings': mock_settings_mod,
        'scansynclib.sqlite_wrapper': MagicMock(),
    }

    # Evict any cached copies so the module is re-executed with our mocks
    for key in list(sys.modules.keys()):
        if key in ('ocr_service.main', 'ocr_service'):
            del sys.modules[key]

    with patch.dict('sys.modules', module_patches):
        import ocr_service.main as ocr_main  # noqa: PLC0415
        return ocr_main, mock_ocrmypdf


class TestStartProcessing:
    """Test the start_processing function from the OCR service."""

    def _create_mock_item(self):
        """Create a mock ProcessItem for testing."""
        item = Mock(spec=ProcessItem)
        item.filename = "test.pdf"
        item.local_file_path = "/tmp/test.pdf"
        item.ocr_file = "/tmp/test_OCR.pdf"
        item.ocr_status = OCRStatus.UNKNOWN
        item.status = ProcessStatus.OCR_PENDING
        item.db_id = 1
        item.time_ocr_started = None
        item.time_ocr_finished = None
        return item

    # ------------------------------------------------------------------
    # Helpers to reduce boilerplate in each test
    # ------------------------------------------------------------------
    def _setup_ocr_mod(self, mock_ocr_mod, mock_ocrmypdf):
        """Attach the fake exception classes to the mock ocrmypdf module."""
        mock_ocr_mod.UnsupportedImageFormatError = mock_ocrmypdf.UnsupportedImageFormatError
        mock_ocr_mod.DpiError = mock_ocrmypdf.DpiError
        mock_ocr_mod.InputFileError = mock_ocrmypdf.InputFileError
        mock_ocr_mod.OutputFileAccessError = mock_ocrmypdf.OutputFileAccessError
        mock_ocr_mod.MissingDependencyError = mock_ocrmypdf.MissingDependencyError

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_ocr_success_with_text_sets_completed(self):
        """When OCR succeeds and text is found, ocr_status should be COMPLETED."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database') as mock_update_db, \
             patch.object(ocr_main, 'extract_text', return_value="Real OCR text."), \
             patch.object(ocr_main, 'os') as mock_os, \
             patch.object(ocr_main, 'forward_to_rabbitmq'):

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            mock_ocr_mod.ocr.return_value = 0
            mock_os.path.exists.return_value = True

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            assert item.ocr_status == OCRStatus.COMPLETED
            final_call = mock_update_db.call_args_list[-1][0][1]
            assert final_call.get("ocr_status") == OCRStatus.COMPLETED.name
            mock_ocr_mod.ocr.assert_called_once()
            assert mock_ocr_mod.ocr.call_args.kwargs["jpeg_quality"] == 80
            assert "jpg_quality" not in mock_ocr_mod.ocr.call_args.kwargs

    def test_ocr_success_no_text_sets_no_text(self):
        """When OCR succeeds but no text found, ocr_status should be NO_TEXT."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database') as mock_update_db, \
             patch.object(ocr_main, 'extract_text', return_value=""), \
             patch.object(ocr_main, 'os') as mock_os, \
             patch.object(ocr_main, 'forward_to_rabbitmq'):

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            mock_ocr_mod.ocr.return_value = 0
            mock_os.path.exists.return_value = True

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            assert item.ocr_status == OCRStatus.NO_TEXT
            final_call = mock_update_db.call_args_list[-1][0][1]
            assert final_call.get("ocr_status") == OCRStatus.NO_TEXT.name

    def test_ocr_success_whitespace_only_sets_no_text(self):
        """When OCR succeeds but only whitespace found, ocr_status should be NO_TEXT."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database'), \
             patch.object(ocr_main, 'extract_text', return_value="   \n\t  \n  "), \
             patch.object(ocr_main, 'os') as mock_os, \
             patch.object(ocr_main, 'forward_to_rabbitmq'):

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            mock_ocr_mod.ocr.return_value = 0
            mock_os.path.exists.return_value = True

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            assert item.ocr_status == OCRStatus.NO_TEXT

    def test_ocr_success_missing_output_file_sets_output_error(self):
        """When OCR succeeds but output file is missing, status should be OUTPUT_ERROR."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database') as mock_update_db, \
             patch.object(ocr_main, 'os') as mock_os, \
             patch.object(ocr_main, 'forward_to_rabbitmq'):

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            mock_ocr_mod.ocr.return_value = 0
            mock_os.path.exists.return_value = False  # output file missing

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            assert item.ocr_status == OCRStatus.OUTPUT_ERROR
            final_call = mock_update_db.call_args_list[-1][0][1]
            assert final_call.get("ocr_status") == OCRStatus.OUTPUT_ERROR.name

    def test_ocr_nonzero_exit_code_sets_failed(self):
        """When OCR exits with non-zero code, ocr_status should be FAILED."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database'), \
             patch.object(ocr_main, 'forward_to_rabbitmq'):

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            mock_ocr_mod.ocr.return_value = 1

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            assert item.ocr_status == OCRStatus.FAILED

    def test_ocr_unsupported_format_sets_unsupported(self):
        """When OCR raises UnsupportedImageFormatError, status should be UNSUPPORTED."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database'), \
             patch.object(ocr_main, 'forward_to_rabbitmq'):

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            UnsupportedError = mock_ocrmypdf.UnsupportedImageFormatError
            mock_ocr_mod.UnsupportedImageFormatError = UnsupportedError
            mock_ocr_mod.ocr.side_effect = UnsupportedError("Unsupported format")

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            assert item.ocr_status == OCRStatus.UNSUPPORTED

    def test_ocr_dpi_error_sets_dpi_error(self):
        """When OCR raises DpiError, ocr_status should be DPI_ERROR."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database'), \
             patch.object(ocr_main, 'forward_to_rabbitmq'):

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            DpiError = mock_ocrmypdf.DpiError
            mock_ocr_mod.DpiError = DpiError
            mock_ocr_mod.ocr.side_effect = DpiError("DPI too low")

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            assert item.ocr_status == OCRStatus.DPI_ERROR

    def test_ocr_success_forwards_to_upload_queue(self):
        """When OCR succeeds with text, item should be forwarded to upload queue."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database'), \
             patch.object(ocr_main, 'extract_text', return_value="Real text."), \
             patch.object(ocr_main, 'os') as mock_os, \
             patch.object(ocr_main, 'forward_to_rabbitmq') as mock_forward:

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            mock_ocr_mod.ocr.return_value = 0
            mock_os.path.exists.return_value = True

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            mock_forward.assert_called_once_with("upload_queue", item)

    def test_ocr_db_updated_with_ocr_status(self):
        """Verify the DB final update includes both file_status and ocr_status."""
        ocr_main, mock_ocrmypdf = _load_ocr_main()

        with patch.object(ocr_main, 'ocrmypdf') as mock_ocr_mod, \
             patch.object(ocr_main, 'update_scanneddata_database') as mock_update_db, \
             patch.object(ocr_main, 'extract_text', return_value="Extracted text."), \
             patch.object(ocr_main, 'os') as mock_os, \
             patch.object(ocr_main, 'forward_to_rabbitmq'):

            self._setup_ocr_mod(mock_ocr_mod, mock_ocrmypdf)
            mock_ocr_mod.ocr.return_value = 0
            mock_os.path.exists.return_value = True

            item = self._create_mock_item()
            ocr_main.start_processing(item)

            # At least two DB calls: initial status update + final status update
            assert mock_update_db.call_count >= 2
            final_update = mock_update_db.call_args_list[-1][0][1]
            assert "file_status" in final_update
            assert "ocr_status" in final_update
            assert final_update["ocr_status"] == OCRStatus.COMPLETED.name
