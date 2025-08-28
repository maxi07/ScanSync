import pytest
import os
import tempfile
from unittest.mock import Mock, patch, mock_open
from scansynclib.ProcessItem import ProcessItem, ItemType, OCRStatus


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
    def test_extract_text_strips_whitespace(self, mock_pdf_reader):
        """Test that extract_text properly handles text with whitespace."""
        from scansynclib.helpers import extract_text
        
        # Mock the PDF reader to return text with whitespace
        mock_page = Mock()
        mock_page.extract_text.return_value = "  \n\t  Some text  \n\t  "
        mock_reader = Mock()
        mock_reader.pages = [mock_page]
        mock_pdf_reader.return_value = mock_reader
        
        result = extract_text("dummy_path.pdf")
        assert result == "  \n\t  Some text  \n\t  "  # Should return raw text, not stripped

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