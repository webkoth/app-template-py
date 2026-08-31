"""Пароли и подпись сессии.

Параметры scrypt совпадают с теми, что задаёт app-template-ts (N=16384,
r=8, p=1, 64 байта, соль 16 байт), поэтому строки хешей совместимы: базу с
пользователями можно перенести между шаблонами без сброса паролей.

Совместимость проверена прогоном в обе стороны, а не выведена из
документации: хеш, созданный в Node, принимается здесь, хеш, созданный
здесь, принимается в Node — включая пароль кириллицей, то есть кодировка
UTF-8 у обеих сторон совпадает.
"""

import hashlib
import hmac
import secrets

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SALT_BYTES = 16
# 128 * N * r = 16 МБ на вызов; умолчание OpenSSL (32 МБ) впритык, и на
# части сборок вызов падает с «memory limit exceeded». Задаём явно.
SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"scrypt${SCRYPT_N}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Сверяет пароль с сохранённой строкой. Битая строка — отказ, не сбой."""
    # Пустое значение и None отсеиваются первыми. NULL в password_hash —
    # штатное состояние («вход невозможен»), а не порча данных, и приходит
    # оно прямо из nullable-колонки. Без этой строки попытка входа такого
    # пользователя даёт AttributeError и пятисотку вместо отказа. В
    # app-template-ts эта же проверка стоит первой строкой verifyPassword.
    if not stored:
        return False

    try:
        algo, n_raw, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n_raw),
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=len(expected),
            maxmem=SCRYPT_MAXMEM,
        )
    except ValueError:
        return False
    # Сравнение за постоянное время: обычное == выходит на первом
    # несовпавшем байте, и по времени ответа хеш подбирается побайтово.
    return hmac.compare_digest(digest, expected)
