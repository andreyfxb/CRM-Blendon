import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    db_path: str
    admin_username: str
    admin_password_hash: str
    allowed_origins: tuple[str, ...]
    meta_app_secret: str = ''
    meta_verify_token: str = ''
    meta_phone_number_id: str = ''
    session_hours: int = 8
    max_request_bytes: int = 5 * 1024 * 1024

    @property
    def webhook_configured(self):
        return all((self.meta_app_secret, self.meta_verify_token, self.meta_phone_number_id))

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv()
        hashed = os.environ.get('ADMIN_PASSWORD_HASH', '')
        if not hashed.startswith('pbkdf2_sha256$600000$'):
            raise RuntimeError('Configure ADMIN_PASSWORD_HASH usando python -m backend.security.')
        origins = tuple(x.strip().rstrip('/') for x in os.getenv('ALLOWED_ORIGINS', '').split(',') if x.strip())
        if not origins or any(urlparse(x).scheme not in ('http', 'https') or not urlparse(x).netloc or urlparse(x).path for x in origins):
            raise RuntimeError('ALLOWED_ORIGINS deve conter origens exatas, sem caminho ou curinga.')
        return cls(
            db_path=str(Path(os.getenv('DATABASE_PATH', './data/axion.sqlite3')).resolve()),
            admin_username=os.getenv('ADMIN_USERNAME', 'admin'),
            admin_password_hash=hashed,
            allowed_origins=origins,
            meta_app_secret=os.getenv('META_APP_SECRET', ''),
            meta_verify_token=os.getenv('META_VERIFY_TOKEN', ''),
            meta_phone_number_id=os.getenv('META_PHONE_NUMBER_ID', ''),
        )
