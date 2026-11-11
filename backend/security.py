"""Password hashing and session hashing; passwords never enter source control."""
import base64
import getpass
import hashlib
import hmac
import secrets

ITERATIONS = 600_000


def password_hash(password: str) -> str:
    if len(password) < 12:
        raise ValueError('Use uma senha com pelo menos 12 caracteres.')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}'


def check_password(password: str, encoded: str) -> bool:
    try:
        alg, rounds, salt, expected = encoded.split('$')
        if alg != 'pbkdf2_sha256' or not 600_000 <= int(rounds) <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


if __name__ == '__main__':
    password = getpass.getpass('Nova senha do administrador (mínimo 12 caracteres): ')
    if password != getpass.getpass('Repita a senha: '):
        raise SystemExit('As senhas não conferem.')
    print('\nCopie este hash para ADMIN_PASSWORD_HASH no ambiente do servidor:')
    print(password_hash(password))
