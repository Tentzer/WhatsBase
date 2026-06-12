"""Fernet-based encrypt/decrypt for per-tenant Green API tokens at rest.

TOKEN_ENCRYPTION_KEY must be a URL-safe base64-encoded 32-byte key.
Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


def encrypt_token(plaintext: str, key: str) -> str:
    """Encrypt a plaintext token string, return base64 ciphertext."""
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str, key: str) -> str:
    """Decrypt a ciphertext token string back to plaintext.

    Raises `InvalidToken` if the key is wrong or the value is corrupted.
    Never log the return value.
    """
    try:
        return Fernet(key.encode()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception) as exc:
        raise ValueError("Token decryption failed — wrong key or corrupted value.") from exc
