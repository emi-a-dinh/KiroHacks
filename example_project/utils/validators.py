"""
Input validation utilities.
"""

import re


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def is_valid_email(email: str) -> bool:
    """Check if an email address is valid."""
    return bool(EMAIL_REGEX.match(email))


def is_valid_username(username: str) -> bool:
    """
    Username must be 3-30 characters, alphanumeric and underscores only.
    NOTE: This validator exists but is NOT called in auth.py register route — Issue 1 adjacent.
    """
    if not username:
        return False
    if len(username) < 3 or len(username) > 30:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_]+$", username))


def sanitize_tag_name(name: str) -> str:
    """Normalize a tag name: lowercase, strip whitespace, replace spaces with hyphens."""
    return re.sub(r"\s+", "-", name.strip().lower())
