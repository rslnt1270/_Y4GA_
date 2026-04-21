# © YAGA Project — Todos los derechos reservados
"""
core/crypto.py — Cifrado AES-256-GCM para PII y coordenadas GPS.

Principios:
  - IV aleatorio de 12 bytes por registro (GCM recomendado)
  - Tag de autenticación GCM (16 bytes) protege integridad
  - Clave maestra desde variable de entorno DB_ENCRYPT_KEY (32 bytes hex)
  - Formato en DB: IV (12 bytes) + TAG (16 bytes) + CIPHERTEXT → BYTEA

En producción la clave viene de AWS Secrets Manager via External Secrets Operator.
En desarrollo se lee de .env como DB_ENCRYPT_KEY=<64 hex chars>.
"""
import os
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY: bytes | None = None


def _get_key() -> bytes:
    global _KEY
    if _KEY is not None:
        return _KEY
    raw = os.environ.get("DB_ENCRYPT_KEY", "")
    if not raw or len(raw) < 64:
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production":
            raise RuntimeError(
                "DB_ENCRYPT_KEY no configurada en producción. "
                "Genera 32 bytes aleatorios: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        # Clave de desarrollo — NUNCA usar en producción
        import warnings
        warnings.warn(
            "DB_ENCRYPT_KEY no configurada — usando clave de desarrollo insegura (NUNCA en producción)",
            stacklevel=3,
        )
        raw = "0" * 64
    _KEY = bytes.fromhex(raw[:64])
    return _KEY


def encrypt_value(plaintext: str) -> bytes:
    """
    Cifra un string con AES-256-GCM.
    Devuelve: IV(12) + TAG(16) + CIPHERTEXT como bytes (BYTEA en Postgres).
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    iv = secrets.token_bytes(12)
    ct_and_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    # AESGCM devuelve ciphertext+tag concatenados (tag al final, 16 bytes)
    return iv + ct_and_tag


def decrypt_value(cipherblob: bytes) -> str:
    """
    Descifra bytes producidos por encrypt_value.
    Devuelve el plaintext original como str.
    Lanza InvalidTag si el ciphertext fue manipulado.
    """
    if len(cipherblob) < 29:  # 12 IV + 16 TAG + mínimo 1 byte
        raise ValueError("Cipherblob demasiado corto")
    key = _get_key()
    aesgcm = AESGCM(key)
    iv = cipherblob[:12]
    ct_and_tag = cipherblob[12:]
    return aesgcm.decrypt(iv, ct_and_tag, None).decode("utf-8")
