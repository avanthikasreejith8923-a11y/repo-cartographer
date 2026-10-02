"""Security utilities: Fernet symmetric encryption, JWT session management, and OAuth state signing."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def get_fernet_cipher() -> Fernet:
    """Initialize Fernet cipher using configured key.

    FERNET_KEY must be a 32-byte url-safe base64-encoded string.
    """
    key = settings.FERNET_KEY.strip()
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext string (e.g. GitHub OAuth access token) using Fernet.

    Returns a base64-encoded encrypted ASCII string suitable for database storage.
    """
    if not token:
        raise ValueError("Cannot encrypt an empty token.")
    cipher = get_fernet_cipher()
    encrypted_bytes = cipher.encrypt(token.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a Fernet-encrypted string back to its plaintext representation.

    Raises ValueError if decryption fails or the token was tampered with.
    """
    if not encrypted_token:
        raise ValueError("Cannot decrypt an empty token.")
    cipher = get_fernet_cipher()
    try:
        decrypted_bytes = cipher.decrypt(encrypted_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted token or decryption key mismatch.") from exc


def generate_oauth_state(length: int = 32) -> str:
    """Generate a cryptographically secure random string for OAuth state parameter."""
    return secrets.token_urlsafe(length)


def sign_oauth_state(state: str) -> str:
    """Sign an OAuth state string using HMAC-SHA256 and the application SECRET_KEY.

    Format: {state}.{signature}
    """
    mac = hmac.new(
        key=settings.SECRET_KEY.encode("utf-8"),
        msg=state.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{state}.{mac}"


def verify_oauth_state(state: str, signed_state: str) -> bool:
    """Verify that the provided state matches the signed state cookie."""
    if not state or not signed_state or "." not in signed_state:
        return False
    orig_state, received_mac = signed_state.rsplit(".", 1)
    if not hmac.compare_digest(state, orig_state):
        return False
    expected_mac = hmac.new(
        key=settings.SECRET_KEY.encode("utf-8"),
        msg=orig_state.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(received_mac, expected_mac)


def create_session_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT for user sessions."""
    to_encode = data.copy()
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a session JWT. Returns payload dict or None if invalid/expired."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except (jwt.PyJWTError, ValueError):
        return None
