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


def test_layer_defaults_are_usable_without_env():
    # Слой обязан работать сразу после установки ядра: человек, поставивший
    # шаблон, не должен дописывать четыре переменные, чтобы увидеть, как
    # загружается файл. Умолчания стоят здесь, а не только в .env.example —
    # иначе контур, поднятый без них, падает на старте.
    s = Settings(_env_file=None, **BASE)
    assert s.upload_max_bytes == 32 * 1024 * 1024
    assert s.job_poll_seconds == 1.0
    assert s.job_heartbeat_seconds == 10.0
    assert s.job_stale_after_seconds == 60.0
    assert s.job_max_attempts == 3
    assert s.integrations_mode == "mock"


def test_upload_dir_is_absolute_and_next_to_the_repository():
    # Путь считается от файла настроек, а не от текущего каталога: приложение
    # запускают из backend/ (pm2 --cwd), тесты — из backend/, команды make —
    # из корня. Относительный путь дал бы три разных каталога загрузок, и
    # найти файл, загруженный вчера, стало бы делом удачи.
    s = Settings(_env_file=None, **BASE)
    assert s.upload_dir.is_absolute()
    assert s.upload_dir.name == "uploads"


def test_stale_must_exceed_heartbeat():
    # Отбор задачи раньше, чем воркер успевает поставить отметку, — это
    # отбор у живого. Два воркера начнут считать одно и то же, а первый ещё
    # и запишет результат поверх второго. Настройка, которая молча
    # разрешает такое, хуже отсутствующей.
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **BASE,
            JOB_HEARTBEAT_SECONDS="30",
            JOB_STALE_AFTER_SECONDS="20",
        )


def test_unknown_integrations_mode_is_refused():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE, INTEGRATIONS_MODE="почти-настоящий")
