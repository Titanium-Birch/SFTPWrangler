"""Path security utilities for preventing directory traversal attacks."""

import logging
import os

logger = logging.getLogger(__name__)


def validate_safe_filename(filename: str) -> str:
    """
    Validates and normalizes a filename to prevent path traversal attacks.

    Args:
        filename: The filename to validate

    Returns:
        str: The safe, normalized filename (basename only)

    Raises:
        ValueError: If the filename is potentially malicious or invalid
    """
    if not filename or not filename.strip():
        raise ValueError("Invalid filename: empty or whitespace-only")

    # Check for directory traversal patterns
    if ".." in filename:
        logger.warning(f"Skipping potentially malicious file: {filename}")
        raise ValueError(f"potentially malicious file: {filename}")

    # Check for absolute paths (Unix and Windows style)
    if (
        filename.startswith("/") or os.path.isabs(filename) or (len(filename) > 1 and filename[1] == ":")
    ):  # Windows C:\ style
        logger.warning(f"Skipping potentially malicious file: {filename}")
        raise ValueError(f"potentially malicious file: {filename}")

    # Return only the basename to prevent any path manipulation
    safe_filename = os.path.basename(filename)

    return safe_filename
