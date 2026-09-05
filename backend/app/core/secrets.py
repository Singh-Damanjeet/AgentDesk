from pathlib import Path

from cryptography.fernet import Fernet

from app.db.session import DATA_DIR


KEY_PATH = Path(DATA_DIR) / "secret.key"


def _load_or_create_key() -> bytes:
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()

    key = Fernet.generate_key()

    KEY_PATH.write_bytes(key)

    return key


def encrypt_secret(value: str) -> str:
    fernet = Fernet(_load_or_create_key())

    encrypted = fernet.encrypt(
        value.encode("utf-8")
    )

    return encrypted.decode("utf-8")


def decrypt_secret(value: str) -> str:
    fernet = Fernet(_load_or_create_key())

    decrypted = fernet.decrypt(
        value.encode("utf-8")
    )

    return decrypted.decode("utf-8")