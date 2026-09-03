import pytest
from pydantic import ValidationError

from app.core.config import ENV_FILE, Settings, describe_validation_error

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

    Список берётся ИЗ САМОЙ модели, а не пишется руками. Руками он однажды
    отстанет: пока в нём не было `JOB_`, строка `JOB_MAX_ATTEMPTS=5` в шелле
    роняла `test_layer_defaults_are_usable_without_env` — у одного человека,
    на одной машине, и по причине, которой в тесте не видно. Поле, добавленное
    завтра, попадает сюда само; список, который нельзя забыть обновить, лучше
    правила «не забывай обновлять список».

    Имена — заглавными: `alias_generator=str.upper` в настройках означает, что
    поле `job_poll_seconds` читается из переменной `JOB_POLL_SECONDS`.
    """
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


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
    # Про длину, а не просто про имя поля. Отказ `extra="forbid"` выглядит
    # как «APP_AUTH_SECRET\n  Extra inputs are not permitted» и содержит ту
    # же подстроку — то есть проверка по одному имени зелена и в мире, где
    # поля нет вовсе. Ровно эта болезнь нашлась у двух тестов слоя данных.
    assert "at least 32" in str(e.value)


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
    # Ключа и адреса поставщика нет намеренно: режим mock их не требует, а
    # обязательное поле заставило бы заполнять их всех, включая тех, кому
    # внешние модели не нужны вовсе.
    assert s.integrations_url == ""
    assert s.integrations_api_key == ""
    assert s.integrations_timeout_seconds == 30.0


def test_integrations_timeout_must_be_positive():
    # Ноль и отрицательное — это запрос, отваливающийся, не начавшись: на
    # экране «внешняя модель не ответила за 0 с», а к модели не обратились ни
    # разу. Верхней границы нет намеренно, у поставщиков разный нрав; про
    # связь с JOB_STALE_AFTER_SECONDS сказано в .env.example.
    with pytest.raises(ValidationError) as e:
        Settings(_env_file=None, **{**BASE, "INTEGRATIONS_TIMEOUT_SECONDS": "0"})
    # Про саму границу, а не только про имя поля: отказ `extra="forbid"`
    # содержал бы то же имя и был бы зелёным в мире, где поля нет вовсе.
    assert "greater than 0" in str(e.value)


def test_upload_dir_is_absolute_and_inside_the_repository():
    # Путь считается от файла настроек, а не от текущего каталога: приложение
    # запускают из backend/ (pm2 --cwd), тесты — из backend/, команды make —
    # из корня. Относительный путь дал бы три разных каталога загрузок, и
    # найти файл, загруженный вчера, стало бы делом удачи.
    s = Settings(_env_file=None, **BASE)
    assert s.upload_dir.is_absolute()
    assert s.upload_dir.name == "uploads"
    # Каталог лежит В корне репозитория, а не рядом с ним. Саму связь с
    # .gitignore проверяет test_uploads_are_ignored_by_git: эта строка ловит
    # только Path("uploads") и Path.cwd()/"uploads".
    assert s.upload_dir.parent == ENV_FILE.parent


def test_stale_must_exceed_heartbeat():
    # Отбор задачи раньше, чем воркер успевает поставить отметку, — это
    # отбор у живого. Два воркера начнут считать одно и то же, а первый ещё
    # и запишет результат поверх второго. Настройка, которая молча
    # разрешает такое, хуже отсутствующей.
    with pytest.raises(ValidationError) as denial:
        Settings(
            _env_file=None,
            **BASE,
            JOB_HEARTBEAT_SECONDS="30",
            JOB_STALE_AFTER_SECONDS="20",
        )
    # Проверяется ПРИЧИНА, а не сам факт отказа. Под `extra="forbid"` голый
    # `pytest.raises(ValidationError)` на ещё не заведённое поле зелен и без
    # кода: pydantic отвергает неизвестный ключ, и тест это засчитывает.
    # Ровно так и вышло при написании — красной фазы у этой проверки не было.
    assert "JOB_STALE_AFTER_SECONDS должен быть втрое больше" in str(denial.value)


@pytest.mark.parametrize(
    ("heartbeat", "stale"),
    [
        ("10", "10"),  # равные: задачу отбирают в момент отметки
        ("10", "10.001"),  # запас в миллисекунду — тот же отбор у живого
        ("10", "29"),  # меньше трёхкратного
    ],
)
def test_a_margin_that_is_not_a_margin_is_refused(heartbeat, stale):
    # Первая редакция требовала только «строго больше», и все три эти
    # настройки проходили — то есть охранник пропускал ровно тот сценарий,
    # ради которого поставлен. Запас обязан переживать несколько пропущенных
    # отметок подряд: воркер притормаживает на сборке мусора и на записи в
    # базу, и это норма, а не сбой.
    with pytest.raises(ValidationError) as denial:
        Settings(
            _env_file=None,
            **BASE,
            JOB_HEARTBEAT_SECONDS=heartbeat,
            JOB_STALE_AFTER_SECONDS=stale,
        )
    assert "втрое" in str(denial.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("UPLOAD_MAX_BYTES", "0"),
        ("JOB_POLL_SECONDS", "0"),
        ("JOB_HEARTBEAT_SECONDS", "0"),
        ("JOB_STALE_AFTER_SECONDS", "0"),
        ("JOB_MAX_ATTEMPTS", "0"),
        ("JOB_MAX_ATTEMPTS", "1000"),
    ],
)
def test_meaningless_limits_are_refused(name, value):
    # Ограничения gt=0 / ge=1 / le=10 не проверялись ничем: их можно было
    # снять со всех пяти полей, и прогон оставался зелёным. Что они ловят:
    # JOB_POLL_SECONDS=0 — воркер бьёт в базу запросом без пауз, ничего при
    # этом не делая; JOB_MAX_ATTEMPTS=0 — задача не выполняется никогда;
    # 1000 — задача с ошибкой в данных занимает воркер до конца недели.
    with pytest.raises(ValidationError) as denial:
        Settings(_env_file=None, **BASE, **{name: value})
    # Не «Лишнее поле»: иначе проверка зелена и в мире, где поля нет.
    assert "Extra inputs" not in str(denial.value)


def test_infinite_interval_is_refused():
    # inf > 0 истинно, и без allow_inf_nan=False настройка проходила.
    # JOB_STALE_AFTER_SECONDS="1e999" — опечатка в показателе — означала бы,
    # что брошенная задача не возвращается в очередь никогда. Выглядит это
    # как зависший воркер, и искать причину пошли бы в воркер.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE, JOB_STALE_AFTER_SECONDS="1e999")


@pytest.mark.parametrize("value", ["", ".", "uploads", "var/www/slug/uploads"])
def test_relative_upload_dir_is_refused(value):
    # Ловушка была описана в .env.example и не закрыта ничем. Пустая строка
    # даёт Path("."), «uploads» — путь от рабочего каталога, а каталогов три:
    # pm2 запускает приложение и воркер с --cwd .../backend, команды make
    # идут из корня. Загруженный минуту назад файл оказывался «не найден».
    with pytest.raises(ValidationError) as denial:
        Settings(_env_file=None, **BASE, UPLOAD_DIR=value)
    assert "UPLOAD_DIR" in str(denial.value)


def test_tilde_in_upload_dir_is_expanded_not_taken_literally():
    # Path("~/uploads") — это каталог с именем «~» в текущем каталоге, и он
    # создался бы молча. Тильда в .env — вещь обычная, поэтому она
    # раскрывается, а не отвергается как относительный путь.
    s = Settings(_env_file=None, **BASE, UPLOAD_DIR="~/uploads")
    assert s.upload_dir.is_absolute()
    assert "~" not in str(s.upload_dir)


def test_uploads_are_ignored_by_git():
    # Каталог загрузок лежит В корне репозитория, поэтому без строки в
    # .gitignore `git status` забивается загруженными файлами, а доставка,
    # делающая `git reset --hard`, начинает их видеть. Связь между
    # умолчанием и .gitignore не держалась ничем: предыдущая проверка
    # обещала её в комментарии, а сверяла только путь.
    s = Settings(_env_file=None, **BASE)
    ignore = (s.upload_dir.parent / ".gitignore").read_text(encoding="utf-8")
    assert "uploads/" in ignore.split()


def test_unknown_integrations_mode_is_refused():
    with pytest.raises(ValidationError) as denial:
        Settings(_env_file=None, **BASE, INTEGRATIONS_MODE="почти-настоящий")
    # Опять причина, а не факт: «Лишнее поле» от `extra="forbid"` — тоже
    # ValidationError, и без этой строки тест не отличает «режима такого
    # нет» от «поля такого нет».
    assert "live" in str(denial.value), "отказ обязан быть про набор режимов"
