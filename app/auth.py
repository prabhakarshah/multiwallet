"""Authentication utilities and storage."""
from typing import Optional

# Simple session storage (in production, use Redis or a database)
sessions = {}

# Simple user storage (in production, use a database with hashed passwords)
users = {
    "admin": "admin123"  # username: password
}


def check_auth(session_id: Optional[str]) -> bool:
    """Check if a session ID is valid."""
    if not session_id:
        return False
    return session_id in sessions
