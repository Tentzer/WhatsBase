"""Crypto round-trip tests — no live services required."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.crypto import decrypt_token, encrypt_token


def _fresh_key() -> str:
    return Fernet.generate_key().decode()


def test_encrypt_decrypt_roundtrip():
    key = _fresh_key()
    plaintext = "super-secret-green-api-token-123"
    ciphertext = encrypt_token(plaintext, key)
    assert ciphertext != plaintext
    assert decrypt_token(ciphertext, key) == plaintext


def test_different_keys_produce_different_ciphertexts():
    k1, k2 = _fresh_key(), _fresh_key()
    ct1 = encrypt_token("token", k1)
    ct2 = encrypt_token("token", k2)
    assert ct1 != ct2


def test_wrong_key_raises():
    key = _fresh_key()
    wrong_key = _fresh_key()
    ciphertext = encrypt_token("my-token", key)
    with pytest.raises(ValueError, match="decryption failed"):
        decrypt_token(ciphertext, wrong_key)


def test_hebrew_token_roundtrip():
    key = _fresh_key()
    token = "גרין-אפי-טוקן-123"
    assert decrypt_token(encrypt_token(token, key), key) == token
