import pytest
from io import BytesIO
from test_utils.fixtures import Fixtures
from utils.path_security import validate_safe_filename


class TestPathSecurity:
    """Test cases for path traversal protection utilities."""

    @pytest.mark.unit
    def test_should_allow_safe_filenames(self):
        """Test that normal, safe filenames are allowed."""
        safe_files = [
            "document.txt",
            "report.csv", 
            "file_with_underscores.json",
            "file-with-dashes.xml",
            "file123.pdf",
            "UPPERCASE.TXT"
        ]
        
        for filename in safe_files:
            assert validate_safe_filename(filename) == filename

    @pytest.mark.unit
    def test_should_reject_path_traversal_attempts(self):
        """Test that path traversal attempts are rejected."""
        malicious_files = [
            "../etc/passwd",
            "../../secret.txt", 
            "../../../root/.ssh/id_rsa",
            "..\\windows\\system32\\config",
            "subdir/../../../etc/passwd",
            "normal_file/../../../secret"
        ]
        
        for filename in malicious_files:
            with pytest.raises(ValueError, match="potentially malicious"):
                validate_safe_filename(filename)

    @pytest.mark.unit
    def test_should_reject_absolute_paths(self):
        """Test that absolute paths are rejected."""
        absolute_paths = [
            "/etc/passwd",
            "/usr/bin/bash",
            "C:\\Windows\\System32",
            "/home/user/.ssh/id_rsa"
        ]
        
        for filename in absolute_paths:
            with pytest.raises(ValueError, match="potentially malicious"):
                validate_safe_filename(filename)

    @pytest.mark.unit 
    def test_should_reject_empty_or_whitespace_filenames(self):
        """Test that empty or whitespace-only filenames are rejected."""
        invalid_names = ["", "   ", "\t", "\n", " \t\n "]
        
        for filename in invalid_names:
            with pytest.raises(ValueError, match="Invalid filename"):
                validate_safe_filename(filename)

    @pytest.mark.unit
    def test_should_normalize_filename_only(self):
        """Test that the function returns only the filename part, not path components."""
        test_cases = [
            ("subdir/file.txt", "file.txt"),
            ("path/to/nested/file.csv", "file.csv"),
            ("file.txt", "file.txt"),
        ]
        
        for input_path, expected in test_cases:
            result = validate_safe_filename(input_path)
            assert result == expected

    @pytest.mark.unit
    def test_malicious_zip_fixtures(self):
        """Test helper to create malicious ZIP files for integration testing."""
        # Create a ZIP with directory traversal filenames
        malicious_zip = Fixtures.create_zip_with_files({
            "../../../etc/passwd": "sensitive content",
            "../../secret.txt": "another secret",
            "/etc/hosts": "absolute path",
            "normal_file.txt": "normal content"
        })
        
        # Verify the ZIP was created successfully (will be used in integration tests)
        assert malicious_zip is not None
        assert len(malicious_zip.getvalue()) > 0
