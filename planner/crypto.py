import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_TITLE_PREFIX = 'encv1:'


def _derived_fernet_key() -> bytes:
    configured = (getattr(settings, 'TASK_ENCRYPTION_KEY', '') or '').strip()
    if configured:
        return configured.encode('utf-8')
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_derived_fernet_key())


def encrypt_task_title(raw: str) -> str:
    value = (raw or '').strip()
    if not value:
        return ''
    token = _fernet().encrypt(value.encode('utf-8')).decode('utf-8')
    return f'{_TITLE_PREFIX}{token}'


def decrypt_task_title(raw: str) -> str:
    value = raw or ''
    if not value:
        return ''
    if not value.startswith(_TITLE_PREFIX):
        # Backward compatibility for old plaintext rows.
        return value
    token = value[len(_TITLE_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return '[DECRYPTION_FAILED]'


def is_task_title_encrypted(raw: str) -> bool:
    return bool(raw and raw.startswith(_TITLE_PREFIX))
