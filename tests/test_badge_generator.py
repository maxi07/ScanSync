"""Tests for the badge_generator module."""

import pytest
import sys
import os

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../scansynclib'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../web_service/src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'web_service/src'))

try:
    from web_service.src.badge_generator import generate_badges
except ImportError:
    # For Docker environment
    sys.path.insert(0, '/tests/tests/web_service/src')
    from badge_generator import generate_badges

from scansynclib.helpers import SMB_TAG_COLORS


class TestBadgeGenerator:
    """Test cases for badge generation functionality."""

    @pytest.mark.parametrize("smb_target_ids, expected_count", [
        ([], 0),
        ([{'id': 1}], 1),
        ([{'id': 1}, {'id': 2}], 2),
        ([{'id': 1}, {'id': 2}, {'id': 3}], 3),
    ])
    def test_generate_badges_count(self, smb_target_ids, expected_count):
        """Test that the correct number of badges is generated."""
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=smb_target_ids,
            local_filepath='test.pdf'
        )
        assert len(badges) == expected_count

    @pytest.mark.parametrize("local_filepath, additional_smb_names, expected_texts", [
        ('document.pdf', [], ['document.pdf']),
        ('path/to/document.pdf', [], ['path/to/document.pdf']),
        ('document.pdf', ['extra1.pdf'], ['document.pdf', 'extra1.pdf']),
        ('zebra.pdf', ['alpha.pdf', 'beta.pdf'], ['alpha.pdf', 'beta.pdf', 'zebra.pdf']),
    ])
    def test_generate_badges_alphabetical_sorting(self, local_filepath, additional_smb_names, expected_texts):
        """Test that badges are sorted alphabetically by filename."""
        smb_target_ids = [{'id': i+1} for i in range(len(additional_smb_names) + 1)]
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=smb_target_ids,
            local_filepath=local_filepath,
            additional_smb_names=additional_smb_names
        )
        actual_texts = [badge['text'] for badge in badges]
        assert actual_texts == expected_texts

    @pytest.mark.parametrize("local_filepath, expected_filename", [
        ('document.pdf', 'document.pdf'),
        ('path/to/document.pdf', 'path/to/document.pdf'),
        ('/full/path/to/document.pdf', '/full/path/to/document.pdf'),
        ('C:\\Windows\\Path\\document.pdf', 'C:\\Windows\\Path\\document.pdf'),
        ('document with spaces.pdf', 'document with spaces.pdf'),
        ('document-with-dashes_and_underscores.pdf', 'document-with-dashes_and_underscores.pdf'),
    ])
    def test_filename_extraction(self, local_filepath, expected_filename):
        """Test that filenames are used as provided (no extraction)."""
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}],
            local_filepath=local_filepath
        )
        assert len(badges) == 1
        assert badges[0]['text'] == expected_filename

    def test_color_consistency_same_text(self):
        """Test that the same text always gets the same color."""
        badges1 = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}],
            local_filepath='test.pdf'
        )
        badges2 = generate_badges(
            pdf_id=2,
            smb_target_ids=[{'id': 999}],
            local_filepath='test.pdf'
        )

        assert len(badges1) == 1
        assert len(badges2) == 1
        assert badges1[0]['color'] == badges2[0]['color']
        assert badges1[0]['text'] == badges2[0]['text']

    def test_color_consistency_different_ids_same_path(self):
        """Test that different IDs with same path get consistent colors."""
        badges1 = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 8}],
            local_filepath='document.pdf'
        )
        badges2 = generate_badges(
            pdf_id=2,
            smb_target_ids=[{'id': 10}],
            local_filepath='document.pdf'
        )
        badges3 = generate_badges(
            pdf_id=3,
            smb_target_ids=[{'id': 6}],
            local_filepath='document.pdf'
        )

        # All should have same color for same filename
        assert badges1[0]['color'] == badges2[0]['color'] == badges3[0]['color']
        assert badges1[0]['text'] == badges2[0]['text'] == badges3[0]['text']

    def test_color_from_valid_range(self):
        """Test that generated colors are from the SMB_TAG_COLORS list."""
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}, {'id': 2}, {'id': 3}],
            local_filepath='test1.pdf',
            additional_smb_names=['test2.pdf', 'test3.pdf']
        )

        for badge in badges:
            assert badge['color'] in SMB_TAG_COLORS

    def test_handle_empty_smb_target_ids(self):
        """Test handling of empty smb_target_ids."""
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=[],
            local_filepath='test.pdf'
        )
        assert len(badges) == 0

    def test_empty_string_local_filepath(self):
        """Test handling of empty string local_filepath."""
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}],
            local_filepath=''
        )

        assert len(badges) == 1
        assert badges[0]['text'] == 'N/A'  # Empty strings become 'N/A'
        assert badges[0]['color'] in SMB_TAG_COLORS

    def test_none_local_filepath(self):
        """Test handling of None local_filepath."""
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}],
            local_filepath=None
        )

        assert len(badges) == 1
        assert badges[0]['text'] == 'N/A'
        # Should use 'N/A' for None values
        expected_hash = hash('N/A') % len(SMB_TAG_COLORS)
        expected_color = SMB_TAG_COLORS[expected_hash]
        assert badges[0]['color'] == expected_color

    def test_badge_structure(self):
        """Test that each badge has the correct structure."""
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}],
            local_filepath='test.pdf'
        )

        assert len(badges) == 1
        badge = badges[0]

        # Check required keys
        required_keys = ['id', 'text', 'color', 'url', 'title']
        for key in required_keys:
            assert key in badge

        # Check types
        assert isinstance(badge['text'], str)
        assert isinstance(badge['color'], str)
        assert isinstance(badge['id'], str)

        # Check color format (should be hex color)
        assert badge['color'].startswith('#')
        assert len(badge['color']) == 7  # #RRGGBB format

    def test_web_urls_and_remote_paths(self):
        """Test that web URLs and remote paths are properly assigned."""
        web_urls = ['http://example.com/file1', 'http://example.com/file2']
        remote_paths = ['remote/path1', 'remote/path2']

        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}, {'id': 2}],
            local_filepath='test.pdf',
            additional_smb_names=['extra.pdf'],
            web_urls=web_urls,
            remote_paths=remote_paths
        )

        assert len(badges) == 2
        # Find badges by text to handle alphabetical sorting
        test_badge = next(b for b in badges if b['text'] == 'test.pdf')
        extra_badge = next(b for b in badges if b['text'] == 'extra.pdf')

        assert test_badge['url'] == web_urls[0]
        assert test_badge['title'] == remote_paths[0]
        assert extra_badge['url'] == web_urls[1]
        assert extra_badge['title'] == remote_paths[1]

    def test_badge_id_format(self):
        """Test that badge IDs follow the expected format."""
        badges = generate_badges(
            pdf_id=123,
            smb_target_ids=[{'id': 1}, {'id': 2}],
            local_filepath='test.pdf',
            additional_smb_names=['extra.pdf']
        )

        assert len(badges) == 2

        # Check that one badge has the main PDF format and others have target format
        badge_ids = [badge['id'] for badge in badges]
        assert any(bid == '123_pdf_smb' for bid in badge_ids)
        assert any(bid.startswith('123_badge_target_') for bid in badge_ids)

    def test_deterministic_color_assignment(self):
        """Test that color assignment is deterministic across multiple calls."""
        badges1 = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}, {'id': 2}],
            local_filepath='test1.pdf',
            additional_smb_names=['test2.pdf']
        )
        badges2 = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}, {'id': 2}],
            local_filepath='test1.pdf',
            additional_smb_names=['test2.pdf']
        )
        badges3 = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}, {'id': 2}],
            local_filepath='test1.pdf',
            additional_smb_names=['test2.pdf']
        )

        # Results should be identical
        assert badges1 == badges2 == badges3

    @pytest.mark.parametrize("special_chars_filename", [
        'file with spaces.pdf',
        'file-with-dashes.pdf',
        'file_with_underscores.pdf',
        'file.with.dots.pdf',
        'file(with)parentheses.pdf',
        'file[with]brackets.pdf',
        'file{with}braces.pdf',
        'file@with#special$.pdf',
    ])
    def test_special_characters_in_filename(self, special_chars_filename):
        """Test handling of filenames with special characters."""
        badges = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}],
            local_filepath=special_chars_filename  # Direct filename, not in path
        )

        assert len(badges) == 1
        assert badges[0]['text'] == special_chars_filename
        assert badges[0]['color'] in SMB_TAG_COLORS

    def test_additional_smb_names_color_consistency(self):
        """Test that additional SMB names get consistent colors based on their text."""
        badges1 = generate_badges(
            pdf_id=1,
            smb_target_ids=[{'id': 1}, {'id': 2}],
            local_filepath='main.pdf',
            additional_smb_names=['extra.pdf']
        )
        badges2 = generate_badges(
            pdf_id=2,
            smb_target_ids=[{'id': 10}, {'id': 20}],
            local_filepath='different.pdf',
            additional_smb_names=['extra.pdf']  # Same additional name
        )

        # Find extra.pdf badges in both results
        extra1 = next(b for b in badges1 if b['text'] == 'extra.pdf')
        extra2 = next(b for b in badges2 if b['text'] == 'extra.pdf')

        # Should have same color despite different target IDs
        assert extra1['color'] == extra2['color']
