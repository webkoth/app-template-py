import time

from app.core.security import (
    AUTH_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    sign_session_token,
    verify_session_token,
)

SECRET = "s" * 32
OTHER = "o" * 32
NOW = 1_756_600_000_000


def test_cookie_name_is_stable():
    # Имя куки — часть контракта с браузером: смена разлогинит всех разом.
    assert AUTH_COOKIE == "app_session"


def test_roundtrip():
    # Время берётся настоящее, а не константа: это единственный тест, где
    # now_ms не передан, то есть единственное покрытие ветки с системными
    # часами. С константой он был бы зелёным ровно ту неделю, когда его
    # написали, а потом падал бы по сроку на исправном коде.
    issued = int(time.time() * 1000)
    token = sign_session_token("admin", issued, SECRET)
    assert verify_session_token(token, SECRET) == ("admin", issued)


def test_other_secret_rejected():
    token = sign_session_token("admin", 1756600000000, SECRET)
    assert verify_session_token(token, OTHER) is None


def test_tampered_payload_rejected():
    token = sign_session_token("viewer", 1756600000000, SECRET)
    _payload, sig = token.split(".")
    forged = sign_session_token("admin", 1756600000000, OTHER).split(".")[0]
    assert verify_session_token(f"{forged}.{sig}", SECRET) is None


def test_malformed_input_rejected():
    assert verify_session_token(None, SECRET) is None
    assert verify_session_token("", SECRET) is None
    assert verify_session_token("безточки", SECRET) is None
    assert verify_session_token("a.b.c", SECRET) is None
    assert verify_session_token("!!!.!!!", SECRET) is None


def test_non_ascii_cookie_rejected_without_raising():
    # Кука с байтом от 0x80 приходит декодированной как latin-1 и даёт
    # не-ASCII строку. Форму «одна точка» она проходит, а сравнение подписи
    # на таких строках бросает TypeError вместо False — то есть мусорная
    # кука роняла бы вход пятисоткой. Байты ниже — то, что реально приходит
    # в заголовке.
    forged = b"\xd0\xb0.\xd0\xb1".decode("latin-1")
    assert verify_session_token(forged, SECRET) is None


def test_expired_token_rejected():
    # Подпись у просроченного токена остаётся верной — отвергает его только
    # эта проверка. Без неё перехваченное значение куки работает вечно:
    # max_age просит браузер её забыть, но ничего не обещает тому, кто
    # предъявляет значение напрямую.
    old = sign_session_token(
        "admin", NOW - (SESSION_MAX_AGE_SECONDS + 60) * 1000, SECRET
    )
    assert verify_session_token(old, SECRET, now_ms=NOW) is None


def test_token_at_age_limit_still_accepted():
    issued = NOW - SESSION_MAX_AGE_SECONDS * 1000
    edge = sign_session_token("admin", issued, SECRET)
    assert verify_session_token(edge, SECRET, now_ms=NOW) == ("admin", issued)


def test_login_with_separator_inside_survives():
    # Разделитель полезной нагрузки не должен ломаться на логине,
    # содержащем его: иначе такой логин молча не сможет войти.
    token = sign_session_token("иван\nпетров", 1756600000000, SECRET)
    assert verify_session_token(token, SECRET) is None
