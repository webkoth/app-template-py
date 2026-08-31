from app.core.security import hash_password, verify_password


def test_hash_has_expected_shape():
    stored = hash_password("тайна")
    algo, n, salt, digest = stored.split("$")
    assert algo == "scrypt"
    assert int(n) == 16384
    assert len(bytes.fromhex(salt)) == 16
    assert len(bytes.fromhex(digest)) == 64


def test_correct_password_verifies():
    assert verify_password("тайна", hash_password("тайна")) is True


def test_wrong_password_rejected():
    assert verify_password("другое", hash_password("тайна")) is False


def test_salt_is_random():
    # Одинаковые пароли обязаны давать разные строки, иначе по базе видно,
    # у кого пароли совпадают.
    assert hash_password("тайна") != hash_password("тайна")


def test_garbage_stored_value_rejected_without_raising():
    # Битая строка в базе не должна ронять вход пятисоткой: это отказ.
    assert verify_password("тайна", "мусор") is False
    assert verify_password("тайна", "scrypt$нечисло$aa$bb") is False
    assert verify_password("тайна", "") is False


def test_empty_password_still_hashes():
    # Пустой пароль — не ошибка уровня хеширования: политику паролей
    # определяет сервис, а не эта функция.
    assert verify_password("", hash_password("")) is True
