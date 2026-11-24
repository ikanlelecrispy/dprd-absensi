import base64
from cryptography.fernet import Fernet
import numpy as np
from app.config import get_settings


class SecurityService:
    def __init__(self, key: str | None = None):
        settings = get_settings()
        raw_key = key or settings.embedding_encryption_key
        # Jika key dummy/placeholder saat dev/test, generate atau pad Fernet key yang valid
        if not raw_key or raw_key.startswith("GANTI"):
            # Fallback dev deterministic 32-byte urlsafe base64 key
            dev_secret = b"DPRD_Surakarta_Secret_Key_32byte"
            self.fernet = Fernet(base64.urlsafe_b64encode(dev_secret))
        else:
            self.fernet = Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)

    def encrypt_embedding(self, embedding: np.ndarray) -> bytes:
        """
        Enkripsi vector embedding (np.ndarray float32) menjadi ciphertext bytes.
        """
        arr_bytes = embedding.astype(np.float32).tobytes()
        return self.fernet.encrypt(arr_bytes)

    def decrypt_embedding(self, encrypted_bytes: bytes) -> np.ndarray:
        """
        Dekripsi ciphertext bytes kembali ke np.ndarray float32 (dim 512).
        """
        decrypted = self.fernet.decrypt(encrypted_bytes)
        return np.frombuffer(decrypted, dtype=np.float32)


# Singleton instance
security_service = SecurityService()
