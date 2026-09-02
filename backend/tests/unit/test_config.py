import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings, describe_validation_error

BASE = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "APP_AUTH_SECRET": "x" * 32,
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Убирает переменные приложения из окружения процесса.

    `_env_file=None` отключает файл, но не `os.environ`. Экспортированный в
    шелле или унаследованный от соседней задачи CI `APP_ENV=production` ронял
    бы тест про значения по умолчанию — или, что хуже, тихо подменял бы
    проверяемое значение, и тест проходил бы, проверив не то.
    """
    for name in list(os.environ):
        if name.startswith(("APP_", "DATABASE_URL", "COOKIE_")):
            monkeypatch.delenv(name, raising=False)


def test_defaults_are_local_and_insecure_cookie():
    s = Settings(_env_file=None, **BASE)
    assert s.app_env == "local"
    assert s.cookie_secure is False
    assert s.app_bootstrap_login == "admin"
    assert s.app_bootstrap_password == "admin"


def test_short_secret_rejected():
    with pytest.raises(ValidationError) as e:
        Settings(_env_file=None, **{**BASE, "APP_AUTH_SECRET": "коротко"})
    assert "APP_AUTH_SECRET" in str(e.value)


def test_database_url_must_be_postgres():
    with pytest.raises(ValidationError) as e:
        Settings(_env_file=None, **{**BASE, "DATABASE_URL": "mysql://u:p@h/db"})
    assert "postgresql://" in str(e.value)


def test_production_requires_secure_cookie():
    with pytest.raises(ValidationError) as e:
        Settings(
            _env_file=None,
            **{**BASE, "APP_ENV": "production", "COOKIE_SECURE": "false"},
        )
    assert "Secure" in str(e.value)


def test_production_with_secure_cookie_is_valid():
    s = Settings(
        _env_file=None,
        **{**BASE, "APP_ENV": "production", "COOKIE_SECURE": "true"},
    )
    assert s.cookie_secure is True


def test_async_url_swaps_driver():
    # Провижинер пишет в .env строку postgresql://, а asyncpg требует
    # postgresql+asyncpg://. Преобразование живёт в коде, потому что править
    # общий app-provision ради одного шаблона нельзя.
    s = Settings(_env_file=None, **BASE)
    assert s.async_database_url == "postgresql+asyncpg://u:p@localhost:5432/db"


def test_async_url_keeps_query_parameters():
    # Хвост строки терять нельзя: без sslmode соединение к внешней базе
    # молча пойдёт открытым.
    s = Settings(
        _env_file=None,
        **{**BASE, "DATABASE_URL": "postgresql://u:p@h/db?sslmode=require"},
    )
    assert s.async_database_url.endswith("/db?sslmode=require")


def test_typo_in_variable_name_is_rejected():
    # Главное свойство extra="forbid". При ignore опечатка неотличима от
    # отсутствия переменной: контур поднялся бы как local, без Secure-куки,
    # и никто бы этого не заметил.
    with pytest.raises(ValidationError) as e:
        Settings(_env_file=None, **{**BASE, "APP_ENVV": "production"})
    assert "APP_ENVV" in str(e.value) or "app_envv" in str(e.value)


class TestBootstrapEnabled:
    def test_enabled_by_default(self):
        assert Settings(_env_file=None, **BASE).bootstrap_enabled is True

    def test_empty_login_disables(self):
        s = Settings(_env_file=None, **{**BASE, "APP_BOOTSTRAP_LOGIN": ""})
        assert s.bootstrap_enabled is False

    def test_empty_password_disables(self):
        s = Settings(_env_file=None, **{**BASE, "APP_BOOTSTRAP_PASSWORD": ""})
        assert s.bootstrap_enabled is False

    def test_whitespace_only_password_disables(self):
        # Пробел не пуст для bool(), и без strip() сентинел молча завёл бы
        # рабочую учётную запись с паролем из одного пробела.
        s = Settings(_env_file=None, **{**BASE, "APP_BOOTSTRAP_PASSWORD": "   "})
        assert s.bootstrap_enabled is False


def test_error_text_does_not_leak_secrets():
    # pydantic кладёт в ValidationError весь входной словарь целиком — вместе
    # с боевым паролем базы и секретом подписи, — даже когда упавшая проверка
    # вообще не про них. Наружу должно уходить только имя поля и текст.
    try:
        Settings(
            _env_file=None,
            DATABASE_URL="postgresql://dbuser:ПАРОЛЬБАЗЫ@10.0.0.5/prod",
            APP_AUTH_SECRET="СЕКРЕТПОДПИСИ" + "q" * 20,
            APP_ENV="production",
            COOKIE_SECURE="false",
        )
    except ValidationError as error:
        text = describe_validation_error(error)
    else:
        pytest.fail("конфигурация обязана была быть отвергнута")

    assert "ПАРОЛЬБАЗЫ" not in text
    assert "СЕКРЕТПОДПИСИ" not in text
    assert "Secure" in text
