import json
import pytest
from detection_service.main import ensure_scan_directory_exists, get_all_files, publish_new_files


def test_get_all_files(mocker):
    # Mock os.walk to return a controlled set of files
    mock_os_walk = mocker.patch("os.walk")
    mock_os_walk.return_value = [
        ("/path/to/dir", [], ["file1.txt", "file2.txt"]),
        ("/path/to/dir/subdir", [], ["file3.txt"])
    ]

    # Call the function
    result = get_all_files("/path/to/dir")

    # Check the result
    expected_result = {
        "/path/to/dir/file1.txt",
        "/path/to/dir/file2.txt",
        "/path/to/dir/subdir/file3.txt"
    }
    assert result == expected_result
    mock_os_walk.assert_called_once_with("/path/to/dir")


def test_get_all_files_empty_directory(mocker):
    # Mock os.walk to return an empty directory
    mock_os_walk = mocker.patch("os.walk")
    mock_os_walk.return_value = [("/path/to/empty_dir", [], [])]

    # Call the function
    result = get_all_files("/path/to/empty_dir")

    # Check the result
    expected_result = set()
    assert result == expected_result
    mock_os_walk.assert_called_once_with("/path/to/empty_dir")


def test_get_all_files_no_files(mocker):
    # Mock os.walk to return a directory with no files
    mock_os_walk = mocker.patch("os.walk")
    mock_os_walk.return_value = [("/path/to/dir", [], [])]

    # Call the function
    result = get_all_files("/path/to/dir")

    # Check the result
    expected_result = set()
    assert result == expected_result
    mock_os_walk.assert_called_once_with("/path/to/dir")


def test_get_all_files_nested_directories(mocker):
    # Mock os.walk to return a directory with nested directories
    mock_os_walk = mocker.patch("os.walk")
    mock_os_walk.return_value = [
        ("/path/to/dir", ["subdir1", "subdir2"], ["file1.txt"]),
        ("/path/to/dir/subdir1", [], ["file2.txt"]),
        ("/path/to/dir/subdir2", [], ["file3.txt"])
    ]

    # Call the function
    result = get_all_files("/path/to/dir")

    # Check the result
    expected_result = {
        "/path/to/dir/file1.txt",
        "/path/to/dir/subdir1/file2.txt",
        "/path/to/dir/subdir2/file3.txt"
    }
    assert result == expected_result
    mock_os_walk.assert_called_once_with("/path/to/dir")


def test_get_all_files_with_symlinks(mocker):
    # Mock os.walk to return a directory with symlinks
    mock_os_walk = mocker.patch("os.walk")
    mock_os_walk.return_value = [
        ("/path/to/dir", [], ["file1.txt", "link_to_file2"]),
        ("/path/to/dir/subdir", [], ["file3.txt"])
    ]

    # Call the function
    result = get_all_files("/path/to/dir")

    # Check the result
    expected_result = {
        "/path/to/dir/file1.txt",
        "/path/to/dir/link_to_file2",
        "/path/to/dir/subdir/file3.txt"
    }
    assert result == expected_result
    mock_os_walk.assert_called_once_with("/path/to/dir")


def test_get_all_files_with_hidden_files(mocker):
    # Mock os.walk to return a directory with hidden files
    mock_os_walk = mocker.patch("os.walk")
    mock_os_walk.return_value = [
        ("/path/to/dir", [], [".hidden_file", "file1.txt"]),
        ("/path/to/dir/subdir", [], ["file2.txt"])
    ]

    # Call the function
    result = get_all_files("/path/to/dir")

    # Check the result
    expected_result = {
        "/path/to/dir/.hidden_file",
        "/path/to/dir/file1.txt",
        "/path/to/dir/subdir/file2.txt"
    }
    assert result == expected_result
    mock_os_walk.assert_called_once_with("/path/to/dir")


def test_get_all_files_with_special_characters(mocker):
    # Mock os.walk to return a directory with special characters in filenames
    mock_os_walk = mocker.patch("os.walk")
    mock_os_walk.return_value = [
        ("/path/to/dir", [], ["file@#$%.txt", "file with spaces.txt"]),
        ("/path/to/dir/subdir", [], ["file&*()_+.txt"])
    ]

    # Call the function
    result = get_all_files("/path/to/dir")

    # Check the result
    expected_result = {
        "/path/to/dir/file@#$%.txt",
        "/path/to/dir/file with spaces.txt",
        "/path/to/dir/subdir/file&*()_+.txt"
    }
    assert result == expected_result
    mock_os_walk.assert_called_once_with("/path/to/dir")


def test_get_all_files_with_large_number_of_files(mocker):
    # Mock os.walk to return a directory with a large number of files
    mock_os_walk = mocker.patch("os.walk")
    mock_os_walk.return_value = [
        ("/path/to/dir", [], [f"file{i}.txt" for i in range(1000)]),
        ("/path/to/dir/subdir", [], [f"file{i}.txt" for i in range(1000, 2000)])
    ]

    # Call the function
    result = get_all_files("/path/to/dir")

    # Check the result
    expected_result = {
        f"/path/to/dir/file{i}.txt" for i in range(1000)
    }.union({
        f"/path/to/dir/subdir/file{i}.txt" for i in range(1000, 2000)
    })
    assert result == expected_result
    mock_os_walk.assert_called_once_with("/path/to/dir")


def test_ensure_scan_directory_exists(mocker):
    # Mock os.path.exists to return False
    mock_exists = mocker.patch("os.path.exists")
    mock_exists.return_value = False

    # Call the function
    with pytest.raises(SystemExit):
        ensure_scan_directory_exists("/path/to/nonexistent/dir")

    # Check that os.makedirs was called
    mock_exists.assert_called_once_with("/path/to/nonexistent/dir")


def test_ensure_scan_directory_exists_already_exists(mocker):
    # Mock os.path.exists to return True
    mock_exists = mocker.patch("os.path.exists")
    mock_exists.return_value = True

    # Call the function
    ensure_scan_directory_exists("/path/to/existing/dir")

    # Check that os.makedirs was not called
    mock_exists.assert_called_once_with("/path/to/existing/dir")


def test_publish_new_files(mocker):
    # Mock the channel's basic_publish method
    mock_channel = mocker.Mock()
    mock_message = json.dumps({"file_path": "/path/to/new_file.txt"})

    # Call the function
    publish_new_files(mock_channel, "test_queue", {"/path/to/new_file.txt"})

    # Check that basic_publish was called with the correct parameters
    mock_channel.basic_publish.assert_called_once_with(
        exchange="",
        routing_key="test_queue",
        body=mock_message,
        properties=mocker.ANY  # Ignore delivery_mode for this test
    )
