import os
import base64
from pathlib import Path

from cryptography.fernet import Fernet


def _get_encryption_key():
    """
    Load or generate a Fernet encryption key.
    The key is stored in backend/.encryption_key (gitignored).
    """
    key_path = Path(__file__).resolve().parents[2] / ".encryption_key"

    if key_path.exists():
        return key_path.read_bytes().strip()

    key = Fernet.generate_key()
    key_path.write_bytes(key)
    return key


_fernet = Fernet(_get_encryption_key())


def encrypt_password(plaintext):
    """Encrypt a plaintext password. Returns a base64-encoded string."""
    if not plaintext:
        return plaintext
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext):
    """Decrypt an encrypted password. Returns the plaintext string."""
    if not ciphertext:
        return ciphertext
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        # Fallback: if the value isn't encrypted (legacy data), return as-is
        return ciphertext
