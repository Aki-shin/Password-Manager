"""Симметричное шифрование паролей для хранения в БД.

Ключ Fernet генерируется автоматически при первом запуске и
хранится в файле instance/master.key. Бэкап этого файла вместе с
vault.db обязателен — без ключа расшифровать базу невозможно.
"""
import os
from cryptography.fernet import Fernet, InvalidToken


class Vault:
    def __init__(self, key_path: str):
        self.key_path = key_path
        self._load_or_create()

    def _load_or_create(self) -> None:
        os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, "wb") as f:
                f.write(key)
            try:
                os.chmod(self.key_path, 0o600)
            except OSError:
                pass
        self._fernet = Fernet(key)

    def reload(self) -> None:
        """Перечитать ключ с диска — вызывается после восстановления бэкапа."""
        self._load_or_create()

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            plaintext = ""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        if not token:
            return ""
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return "<невозможно расшифровать: неверный ключ>"
