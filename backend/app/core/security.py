"""Пароли и подпись сессии.

Параметры scrypt совпадают с теми, что задаёт app-template-ts (N=16384,
r=8, p=1, 64 байта, соль 16 байт), поэтому строки хешей совместимы: базу с
пользователями можно перенести между шаблонами без сброса паролей.

Совместимость проверена прогоном в обе стороны, а не выведена из
документации: хеш, созданный в Node, принимается здесь, хеш, созданный
здесь, принимается в Node — включая пароль кириллицей, то есть кодировка
UTF-8 у обеих сторон совпадает.
"""

import base64
import hashlib
import hmac
import secrets
import time

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


AUTH_COOKIE = "app_session"
_SEPARATOR = "\n"

# Срок жизни токена. Проверяется на сервере, а не только сроком куки:
# max_age у куки — просьба к браузеру, и она ничего не значит для того, кто
# записал её значение и предъявляет его напрямую. Без этой проверки
# перехваченный токен действует вечно, потому что подпись у него остаётся
# верной навсегда.
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

# Допуск на расхождение часов. Нужен, чтобы отвергать токены «из будущего»,
# не придираясь к секундной разнице.
CLOCK_SKEW_SECONDS = 60


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def sign_session_token(login: str, issued_at_ms: int, secret: str) -> str:
    """Подписанный токен сессии: <payload>.<подпись>.

    Токен несёт логин и время выдачи, но не роль: роль читается из базы на
    каждом запросе, поэтому её смена действует немедленно.
    """
    payload = _b64encode(f"{login}{_SEPARATOR}{issued_at_ms}".encode())
    signature = _b64encode(
        hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    )
    return f"{payload}.{signature}"


def verify_session_token(
    token: str | None, secret: str, now_ms: int | None = None
) -> tuple[str, int] | None:
    """Проверяет подпись и срок, возвращает (логин, время выдачи) или None.

    Здесь подпись, форма и срок. Блокировку, роль и отзыв сессии проверяет
    слой доступа: у отозванной куки подпись тоже остаётся верной.
    """
    # isascii обязателен. Заголовки приходят декодированными как latin-1,
    # поэтому кука с любым байтом от 0x80 даёт строку с не-ASCII символами.
    # Форму «одна точка» она при этом проходит, а hmac.compare_digest на
    # таких строках не возвращает False, а бросает TypeError — то есть
    # мусорная кука давала бы пятисотку вместо отказа входа. Проверено.
    if not token or token.count(".") != 1 or not token.isascii():
        return None
    payload, signature = token.split(".")
    expected = _b64encode(
        hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        login, issued_raw = _b64decode(payload).decode().split(_SEPARATOR)
        issued_at_ms = int(issued_raw)
    except ValueError:
        # Один ValueError покрывает всё, что здесь может случиться:
        # binascii.Error и UnicodeDecodeError — его подклассы. Перечислять
        # их поимённо не только лишнее, но и невозможно: base64.binascii
        # существует в рантайме, а в описании типов его нет, и mypy падает.
        return None

    # Время впрыскивается ради тестов: иначе проверку срока пришлось бы
    # ждать неделю.
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    age_ms = now_ms - issued_at_ms
    if age_ms > SESSION_MAX_AGE_SECONDS * 1000:
        return None
    # Забор с обеих сторон. Односторонняя проверка ловит только прошлое, а
    # токен с временем выдачи в будущем живёт вечно. Подделать его без
    # секрета нельзя, но время ставит сервер, и его часы могут скакнуть
    # вперёд — поправкой NTP или восстановлением машины из снимка. Выданные
    # в этот момент токены переживут семь дней, и проверка срока перестанет
    # что-либо значить именно тогда, когда понадобится.
    if age_ms < -CLOCK_SKEW_SECONDS * 1000:
        return None

    return login, issued_at_ms
