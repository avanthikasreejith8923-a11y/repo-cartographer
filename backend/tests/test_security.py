"""Unit tests for cryptographic security helpers, token encryption, and JWT utilities."""

from datetime import timedelta

import pytest

from app.core.security import (
    create_session_token,
    decrypt_token,
    encrypt_token,
    generate_oauth_state,
    sign_oauth_state,
    verify_oauth_state,
    verify_session_token,
)


def test_token_encryption_roundtrip() -> None:
    """Validate that token encryption and decryption preserves plaintext value."""
    plaintext = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    encrypted = encrypt_token(plaintext)
    assert encrypted != plaintext
    assert isinstance(encrypted, str)

    decrypted = decrypt_token(encrypted)
    assert decrypted == plaintext


def test_token_encryption_empty_raises() -> None:
    """Empty string inputs must raise ValueError."""
    with pytest.raises(ValueError):
        encrypt_token("")
    with pytest.raises(ValueError):
        decrypt_token("")


def test_decrypt_tampered_token_fails() -> None:
    """Tampered encrypted tokens must fail decryption."""
    encrypted = encrypt_token("ghp_valid_token_value")
    # Corrupt the ciphertext
    tampered = encrypted[:-4] + "AAAA"
    with pytest.raises(ValueError, match="Invalid encrypted token"):
        decrypt_token(tampered)


def test_oauth_state_generation_and_signature() -> None:
    """Test OAuth state generation and HMAC verification."""
    state = generate_oauth_state()
    assert len(state) >= 32

    signed = sign_oauth_state(state)
    assert "." in signed
    assert verify_oauth_state(state, signed) is True


def test_oauth_state_tampered_rejected() -> None:
    """Test that mismatched or tampered state is rejected."""
    state = generate_oauth_state()
    signed = sign_oauth_state(state)

    # Different state parameter
    assert verify_oauth_state("another_state", signed) is False

    # Tampered signature
    orig_state, _ = signed.split(".")
    tampered_signed = f"{orig_state}.bad_signature_hex"
    assert verify_oauth_state(orig_state, tampered_signed) is False

    # Malformed signed string
    assert verify_oauth_state(state, "no_delimiter") is False


def test_session_jwt_lifecycle() -> None:
    """Test creation and verification of session JWT."""
    payload = {"sub": "00000000-0000-0000-0000-000000000001", "login": "octocat", "github_id": 583231}
    token = create_session_token(payload)
    assert isinstance(token, str)

    decoded = verify_session_token(token)
    assert decoded is not None
    assert decoded["sub"] == payload["sub"]
    assert decoded["login"] == payload["login"]
    assert decoded["github_id"] == payload["github_id"]


def test_expired_jwt_rejected() -> None:
    """Test that expired tokens return None."""
    payload = {"sub": "00000000-0000-0000-0000-000000000001", "login": "octocat"}
    expired_token = create_session_token(payload, expires_delta=timedelta(seconds=-10))
    decoded = verify_session_token(expired_token)
    assert decoded is None
