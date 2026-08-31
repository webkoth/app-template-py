# app-template-py — план реализации ядра

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собрать второй стартовый шаблон внутреннего приложения — рабочее приложение на FastAPI со входом, ролями, аудитом, образцовой фичей, SPA-интерфейсом и боевым контуром на общем VPS.

**Architecture:** Бэкенд — FastAPI, раскладка по фичам (`features/<имя>/{router,service,schemas,models}.py`), слои внутри фичи, чистая логика в `app/domain/` без I/O, границы проверяет import-linter. Фронтенд — SPA на Vite, собирается в GitHub Actions и приезжает на сервер готовой статикой; FastAPI раздаёт её и `/api`. Контур — общий VPS, `app-provision` без правок, pm2 + nginx.

**Tech Stack:** Python 3.14, uv, FastAPI 0.141, Pydantic 2.13, pydantic-settings 2.15, SQLAlchemy 2.0 (async) + asyncpg, Alembic 1.19, ruff, mypy strict, pytest, import-linter. Vite 8, React 19, TypeScript, Tailwind 4, shadcn/ui (`base-vega`, Base UI), TanStack Router + Query, react-hook-form + zod, openapi-typescript + openapi-fetch, Playwright.

**Спека:** `docs/superpowers/specs/2026-08-31-app-template-py-design.md`

---

## Как пользоваться этим планом

Задачи идут по порядку: каждая опирается на предыдущие. Внутри задачи шаги
выполняются подряд, тест пишется до кода.

Все пути даны от корня репозитория `app-template-py`. Команды `uv` и `pytest`
запускаются из `backend/`, команды `npm` — из `frontend/`, `make` — из корня.

Коммиты — conventional commits, описание по-русски. Коммит в конце каждой
задачи, не реже.

Код в шагах записан для чтения человеком, а не под форматтер. После написания
файла прогоняй `uv run ruff format .` (бэкенд) или `npx prettier --write`
(фронтенд) — расстановка переносов и кавычек механическая, спорить с
форматтером незачем. Смысл кода при этом меняться не должен: если форматтер
хочет большего, чем переносы, — это повод остановиться и посмотреть.

---

## Фаза 0. Каркас репозитория

### Задача 1: Скелет и инструменты бэкенда

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/domain/__init__.py`
- Create: `backend/app/features/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `.gitignore`

- [ ] **Шаг 1: Создать каталоги и файлы-пакеты**

```bash
mkdir -p backend/app/{core,domain,features} backend/tests/{unit,api} backend/alembic/versions
touch backend/app/__init__.py backend/app/core/__init__.py \
      backend/app/domain/__init__.py backend/app/features/__init__.py \
      backend/tests/__init__.py backend/tests/unit/__init__.py backend/tests/api/__init__.py
echo "3.14" > backend/.python-version
```

- [ ] **Шаг 2: Написать `backend/pyproject.toml`**

```toml
[project]
name = "apptemplate"
version = "0.0.1"
description = "Стартовый шаблон внутреннего приложения на FastAPI"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.141",
    "uvicorn[standard]>=0.52",
    "pydantic>=2.13",
    "pydantic-settings>=2.15",
    # [asyncio] обязателен, и это не украшение. Он тянет greenlet, без
    # которого падает любая операция через async-сессию. Само по себе
    # SQLAlchemy объявляет greenlet условно, перечисляя архитектуры списком:
    # там есть aarch64 (Linux ARM), но нет arm64 — а это ровно то, что
    # возвращает platform.machine() на маке с Apple Silicon. То есть на
    # боевом Linux всё работает, а у нового человека на маке шаблон
    # разваливается при первом обращении к базе, сообщением
    # «the greenlet library is required», не указывающим ни на
    # архитектуру, ни на этот файл. Проверено на обеих ветках.
    "sqlalchemy[asyncio]>=2.0.52",
    "asyncpg>=0.31",
    "alembic>=1.19",
]

[dependency-groups]
dev = [
    "ruff>=0.16",
    "mypy>=2.3",
    "pytest>=9.1",
    "pytest-asyncio>=1.4",
    "httpx>=0.28",
]
# Отдельная группа, а НЕ dev. `uv sync` без флагов ставит dev по умолчанию, и
# import-linter утянул бы за собой grimp, у которого нет колеса под cp314 на
# macOS (есть только под free-threaded cp314t). Установка собирала бы Rust-
# расширение около двадцати минут — на первом же `uv sync` у нового человека,
# ещё до того, как он увидит работающее приложение. В отдельной группе эта
# цена платится один раз при первом `make check` и не мешает установке.
lint = ["import-linter>=2.14"]

[tool.ruff]
line-length = 88
target-version = "py314"

[tool.ruff.lint]
# E,F — базовые ошибки; I — порядок импортов (замена isort); UP — современный
# синтаксис; B — типичные ловушки; ASYNC — блокирующие вызовы в async-функциях;
# RUF — правила самого ruff. ASYNC здесь не украшение: один synchronous вызов
# внутри обработчика блокирует весь event loop, а значит и всех пользователей.
select = ["E", "F", "I", "UP", "B", "ASYNC", "RUF"]
# RUF001-003 ловят кириллицу как символ, «подозрительно похожий» на латиницу.
# Комментарии, docstring и тексты для людей здесь по-русски намеренно, так
# что это ложное срабатывание почти на каждой строке. Правило защищает от
# омоглифов в чужом коде; здесь оно только шумит.
ignore = ["RUF001", "RUF002", "RUF003"]

[tool.mypy]
python_version = "3.14"
strict = true
# Плагина sqlalchemy.ext.mypy здесь нет намеренно. Он писался под старый стиль
# объявления таблиц (Column плюс отдельная аннотация); для стиля 2.0 с Mapped[]
# mypy выводит типы сам через dataclass_transform. Проверено: с
# `--config-file=/dev/null` mypy читает Mapped[str] как str и ловит подстановку
# str вместо int. Плагин цепляется за внутренний API mypy и ломается при его
# обновлении — это отказ ради ничего.

[[tool.mypy.overrides]]
module = "tests.*"
# В тестах строгость мешает: фикстуры и параметризация тянут за собой
# аннотации, которые ничего не проверяют.
disallow_untyped_defs = false

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
# Оба scope — session, и это не украшение. В tests/conftest.py схема базы
# создаётся фикстурой со scope="session", а движок общий на весь прогон. При
# дефолтном function-scope цикла pytest-asyncio даёт либо ScopeMismatch, либо
# «Task attached to a different loop» — соединение создано в одном цикле, а
# используется в другом. Диагностируется это плохо, поэтому задаётся сразу.
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
addopts = "-q"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Шаг 3: Написать `.gitignore` в корне репозитория**

```gitignore
.DS_Store
.env
.venv/
__pycache__/
*.pyc
.mypy_cache/
.ruff_cache/
.pytest_cache/
node_modules/
frontend/dist/
frontend/src/api/schema.d.ts.new
test-results/
playwright-report/
```

`frontend/src/api/schema.d.ts` **не** игнорируется: он коммитится, чтобы
`tsc` работал без запуска бэкенда, а CI ловил расхождение по дифу.

- [ ] **Шаг 4: Проверить, что окружение ставится**

Run: `cd backend && uv sync`
Expected: создаётся `backend/.venv` и `backend/uv.lock`, ошибок нет.

- [ ] **Шаг 5: Коммит**

```bash
git add .gitignore backend/
git commit -m "chore: каркас бэкенда, зависимости и правила линтеров"
```

---

### Задача 2: Конфигурация приложения

Единственное место, где читается окружение. Разбирается при импорте:
приложение с недостающей переменной обязано не подняться совсем и сказать,
чего не хватает, а не отдать 500 на третьем экране.

**Files:**
- Create: `backend/app/core/config.py`
- Create: `backend/tests/unit/test_config.py`
- Create: `.env.example`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_config.py`:

```python
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
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_config.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Шаг 3: Написать `backend/app/core/config.py`**

```python
"""Конфигурация приложения.

Единственное место в коде приложения, где читается окружение. Значений по
умолчанию почти нигде нет намеренно: молча подставленный секрет на новом
контуре — это боевая система с общеизвестной подписью.
"""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень репозитория: app/core/config.py → core, app, backend, корень.
#
# Путь считается от файла, а не от рабочего каталога процесса. Провижинер
# кладёт .env в корень (/var/www/<слаг>/.env), а pm2 запускает приложение с
# --cwd .../backend: относительный путь ".env" там не нашёлся бы, и контур не
# поднялся бы вовсе с невнятным «Field required». Проверено запуском из обоих
# каталогов.
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        # forbid, а не ignore. При ignore опечатка в имени переменной
        # неотличима от её отсутствия: APP_ENVV=production молча оставляет
        # app_env="local", а APP_BOOTSTRAP_PASSWRD=... оставляет пароль
        # "admin" — то есть боевой контур поднимается с общеизвестной парой и
        # без Secure-куки, ничего не сказав. Посторонние переменные окружения
        # (PATH, PM2_HOME) под forbid не мешают: pydantic-settings собирает из
        # os.environ только объявленные здесь поля. Проверено.
        extra="forbid",
        case_sensitive=False,
        # Имена полей в ошибках — заглавными, то есть ровно так, как
        # переменная называется в .env. Без этого pydantic пишет питоновское
        # имя (app_auth_secret), и человек ищет в .env строку, которой там нет.
        # populate_by_name оставляет возможность создать Settings и по
        # питоновскому имени — этим пользуются тесты.
        alias_generator=str.upper,
        populate_by_name=True,
    )

    database_url: str = Field(description="Адрес PostgreSQL")
    app_env: Literal["local", "production"] = "local"
    app_auth_secret: str = Field(min_length=32)
    cookie_secure: bool = False

    # Отдельная база для e2e: тесты создают и меняют данные, и делать это в
    # рабочей базе нельзя.
    database_url_e2e: str | None = None

    # Первая учётная запись. Значения по умолчанию стоят здесь, а не только в
    # .env.example: контур без этих переменных должен пускать той же парой, а
    # не оставаться без входа вовсе. Проверки силы пароля нет намеренно — она
    # противоречила бы заданному значению.
    app_bootstrap_login: str = "admin"
    app_bootstrap_password: str = "admin"
    app_bootstrap_name: str = "Администратор"

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL должна начинаться с postgresql://")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError(
                "на боевом контуре кука сессии обязана быть Secure "
                "(COOKIE_SECURE=true): контур под HTTPS"
            )
        return self

    @property
    def bootstrap_enabled(self) -> bool:
        """Заводить ли первую учётную запись при пустой таблице.

        Пустое значение логина или пароля выключает bootstrap — это способ
        отказаться от него, когда учётные записи заводят иначе. Инвариант
        живёт здесь, а не в коде фичи: иначе каждый вызывающий выражал бы его
        заново и однажды выразил бы по-своему. strip() не украшение: пароль
        из одного пробела не пуст для bool(), и без него сентинел молча
        создал бы рабочую учётку с паролем " ".
        """
        return bool(self.app_bootstrap_login.strip() and self.app_bootstrap_password.strip())

    @property
    def async_database_url(self) -> str:
        """Адрес для SQLAlchemy с асинхронным драйвером.

        Провижинер пишет в .env обычный postgresql:// — его же читает Alembic
        и psql. Драйвер подставляется здесь, чтобы общий app-provision,
        которым пользуется и TS-шаблон, остался нетронутым.
        """
        _, rest = self.database_url.split("://", 1)
        return f"postgresql+asyncpg://{rest}"


def describe_validation_error(error: ValidationError) -> str:
    """Текст ошибки конфигурации — только имена полей и тексты проверок.

    Вынесено отдельной функцией, чтобы это можно было проверить тестом: она
    и есть та граница, за которую секреты не должны выйти.
    """
    lines = [
        f"  {item['loc'][0] if item['loc'] else '(корень)'}: {item['msg']}"
        for item in error.errors()
    ]
    return (
        "Переменные окружения заданы неверно:\n"
        + "\n".join(lines)
        + f"\nПроверь {ENV_FILE} — образец лежит в .env.example."
    )


def load_settings() -> Settings:
    """Разбирает окружение или падает, не раскрывая секретов.

    Голый ValidationError сюда выпускать нельзя: pydantic прикладывает к
    ошибке model-валидатора весь входной словарь, а в нём боевой пароль базы
    и APP_AUTH_SECRET целиком — независимо от того, какая проверка сработала.
    Это исключение возникает при старте и с наибольшей вероятностью попадёт
    в лог или в трекер ошибок.

    `from None` обязателен: без него исходный ValidationError остался бы в
    цепочке и напечатался бы в traceback вместе со значениями.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as error:
        raise RuntimeError(describe_validation_error(error)) from None


settings = load_settings()
```

Четыре решения в этом файле проверены на живом pydantic 2.13.5, а не взяты
из общих соображений:

1. Без `alias_generator` ошибка называет питоновское имя поля
   (`app_auth_secret`), а не переменную окружения. С ним все случаи —
   короткий секрет, чужое `APP_ENV`, нечисловой `COOKIE_SECURE` — печатают
   имя заглавными, как в `.env`.
2. `extra="ignore"` проглатывает опечатку: `.env` со строкой
   `APP_ENVV=production` оставляет `app_env="local"` без единого слова.
   `extra="forbid"` её отвергает. Посторонние переменные окружения при этом
   не мешают: из `os.environ` собираются только объявленные поля.
3. `.env` в корне репозитория **не находится**, если процесс запущен из
   `backend/` — а pm2 на контуре запускает его именно так (`--cwd .../backend`),
   тогда как провижинер кладёт `.env` в корень. Путь от `__file__` работает
   при запуске из обоих каталогов.
4. `e.errors()` содержит боевой пароль базы и `APP_AUTH_SECRET` целиком даже
   когда упавшая проверка про `COOKIE_SECURE`. Поэтому наружу отдаётся текст,
   собранный только из имени поля и текста проверки.

- [ ] **Шаг 4: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_config.py`
Expected: PASS, 13 passed

- [ ] **Шаг 5: Написать `.env.example` в корне репозитория**

Файл лежит именно в корне, рядом с будущим `.env`: туда же кладёт `.env`
провижинер на контуре, и оттуда же его читает `ENV_FILE`.

```dotenv
# Локальная разработка. На контуре этот файл пишет app-provision.
DATABASE_URL="postgresql://apptemplate:apptemplate@localhost:5432/apptemplatepy_dev"
APP_ENV="local"
# openssl rand -hex 32
APP_AUTH_SECRET=""
COOKIE_SECURE="false"

# Отдельная база под e2e: тесты меняют данные.
DATABASE_URL_E2E="postgresql://apptemplate:apptemplate@localhost:5432/apptemplatepy_e2e"

# Первая учётная запись. Заводится только при пустой таблице пользователей.
# Пустое значение логина или пароля выключает создание.
APP_BOOTSTRAP_LOGIN="admin"
APP_BOOTSTRAP_PASSWORD="admin"
APP_BOOTSTRAP_NAME="Администратор"
```

- [ ] **Шаг 6: Завести локальный `.env`**

Без него модуль нельзя даже импортировать: `settings` разбирается при
импорте. Файл в `.gitignore`, в репозиторий не попадает.

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"
# вписать полученное значение в APP_AUTH_SECRET в .env
```

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/core/config.py backend/tests/unit/test_config.py .env.example
git commit -m "feat: конфигурация приложения на pydantic-settings"
```

---

### Задача 3: Контракты границ между модулями

Границы, которые проверяет прогон, переживают год работы; границы из
договорённостей — нет.

**Files:**
- Create: `backend/.importlinter`

- [ ] **Шаг 1: Написать `backend/.importlinter`**

```ini
[importlinter]
root_packages =
    app
# Обязательно, когда среди forbidden_modules есть внешние пакеты. Без этой
# строки import-linter отказывается разбирать конфиг целиком, а не молча
# пропускает контракт.
include_external_packages = True

[importlinter:contract:domain-is-pure]
name = domain не знает ни про базу, ни про HTTP, ни про фичи
type = forbidden
source_modules =
    app.domain
forbidden_modules =
    app.core
    app.features
    sqlalchemy
    asyncpg
    alembic
    fastapi
```

Запрещены не только `sqlalchemy` и `fastapi`, но и `asyncpg` с `alembic`.
Контракт называется «домен не знает про базу», и без этих двух он не знал бы
про неё лишь наполовину: прямой `import asyncpg` в доменном модуле проходил
бы зелёным. Оба пакета — основные зависимости, всегда установлены, поэтому
отказа «модуля не существует» здесь не будет. `httpx` в список не добавлен
намеренно: он живёт в группе `dev`, и контракт сломался бы там, где её не
ставят.

Здесь один контракт из трёх задуманных, и это не упрощение, а следствие
проверенного поведения инструмента: **`lint-imports` падает с кодом 1, если
контракт называет модуль, которого ещё нет** («Module 'app.features.users'
does not exist»). Записав сразу все три, мы получили бы красный `make check`
с задачи 4 по задачу 22 — восемнадцать задач подряд, в течение которых
проверки перестали бы что-либо значить, а привычка их игнорировать осталась
бы навсегда.

Поэтому контракт появляется вместе с модулями, которые он защищает:

| Контракт | Появляется | Почему там |
|---|---|---|
| `domain-is-pure` | здесь | `app.domain`, `app.core`, `app.features` уже есть |
| `features-are-independent` | задача 10 | там создаются пакеты всех пяти фич |
| `router-goes-through-service` | задача 22 | там появляются последние `router.py` |

- [ ] **Шаг 2: Проверить, что контракт работает**

Run: `cd backend && uv run --group lint lint-imports --config .importlinter`
Expected: `Contracts: 1 kept, 0 broken.`

Проверяй именно эту строку, а не отсутствие ошибки: пустой вывод с нулевым
кодом означает неверный способ запуска, а не пройденную проверку.

- [ ] **Шаг 3: Коммит**

```bash
git add backend/.importlinter
git commit -m "chore: контракты границ модулей для import-linter"
```

---

### Задача 4: Единая точка входа в проверки

Toolchain два, а точка входа должна остаться одна — иначе половину проверок
будут забывать.

**Files:**
- Create: `Makefile`

- [ ] **Шаг 1: Написать `Makefile` в корне репозитория**

```makefile
# Единая точка входа. `make check` прогоняется перед любым коммитом.
#
# Табуляции в начале строк рецептов обязательны — это Make, пробелы он не
# принимает. Переменные шелла экранируются двойным $$: одинарный $ Make
# забирает себе.

.PHONY: install check check-backend check-frontend check-openapi openapi \
        dev dev-backend dev-frontend revision migrate

install:
	cd backend && uv sync
	@if [ -f frontend/package.json ]; then cd frontend && npm ci; fi

# Фронтенд проверяется, только когда он установлен. Проверка по
# node_modules, а не по package.json: пропустить надо и когда фронтенда ещё
# нет, и когда забыли `make install` — во втором случае npx полез бы в сеть
# и упал бы невнятно. Пропуск громкий: молчаливый однажды скроет поломку.
check: check-backend
	@if [ -d frontend/node_modules ]; then \
		$(MAKE) check-frontend; \
	else \
		echo "== фронтенд не установлен, его проверки пропущены =="; \
		echo "   поставить: make install"; \
	fi

check-backend:
	cd backend && uv run ruff format --check .
	cd backend && uv run ruff check .
	cd backend && uv run mypy app
	cd backend && uv run --group lint lint-imports --config .importlinter
	cd backend && uv run pytest

check-frontend: check-openapi
	cd frontend && npx tsc --noEmit
	cd frontend && npm run test

# Расхождение контракта ловится здесь: бэкенд поменял схему, фронт не
# перегенерировал типы — красный прогон на ветке, а не сюрприз в бою.
check-openapi:
	cd backend && uv run python -m app.openapi > /tmp/openapi.json
	cd frontend && npx openapi-typescript /tmp/openapi.json -o src/api/schema.d.ts.new
	@diff -q frontend/src/api/schema.d.ts frontend/src/api/schema.d.ts.new > /dev/null \
		|| { rm -f frontend/src/api/schema.d.ts.new; \
		     echo "Типы клиента разошлись со схемой. Выполни: make openapi"; \
		     exit 1; }
	@rm -f frontend/src/api/schema.d.ts.new

openapi:
	cd backend && uv run python -m app.openapi > /tmp/openapi.json
	cd frontend && npx openapi-typescript /tmp/openapi.json -o src/api/schema.d.ts

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# Бэкенд уходит в фон, фронтенд держит передний план. set -m кладёт фоновую
# задачу в свою группу процессов, а trap убивает группу целиком: без этого
# uvicorn пережил бы выход и остался бы висеть на порту 8000, а следующий
# `make dev` падал бы с «address already in use» без понятной причины.
dev:
	@echo "Бэкенд: http://127.0.0.1:8000   Фронтенд: http://127.0.0.1:5173"
	@set -m; \
	(cd backend && exec uv run uvicorn app.main:app --reload --port 8000) & \
	BACK=$$!; \
	trap "kill -- -$$BACK 2>/dev/null || kill $$BACK 2>/dev/null" EXIT INT TERM; \
	cd frontend && npm run dev

# revision создаёт миграцию, migrate её применяет — как в самом Alembic
# (`alembic revision` и `alembic upgrade`). Обратное именование, где migrate
# создаёт, привычно по Django и Rails и здесь стало бы ловушкой: человек с
# такой привычкой запустил бы `make migrate`, получил лишнюю пустую ревизию
# и не понял бы почему.
#
# m= обязателен: alembic revision без имени создаёт файл со случайным
# именем, и через месяц история миграций нечитаема.
revision:
	@test -n "$(m)" || { echo "нужно имя: make revision m=<слаг>"; exit 1; }
	cd backend && uv run alembic revision --autogenerate -m "$(m)"
	@echo ""
	@echo "ПРОЧИТАЙ сгенерированную миграцию глазами перед применением."
	@echo "Alembic не видит переименований: показывает удаление плюс"
	@echo "добавление, и данные колонки теряются молча."

migrate:
	cd backend && uv run alembic upgrade head
```

Три места здесь стоят объяснения — все проверены запуском.

**Пропуск фронтенда.** `make check` вызывает проверки фронтенда, только если
есть `frontend/node_modules`. Без этой защиты `make check` был бы красным с
этой задачи по задачу 23, пока фронтенда вообще нет, — двадцать задач, за
которые привычка не смотреть на красный прогон закрепляется насовсем.
Проверка по `node_modules`, а не по `package.json`: пропустить надо и когда
фронтенда ещё нет, и когда забыли `make install`.

**`set -m` и `kill -- -$BACK` в `dev`.** Наивное `uvicorn … &` оставляет
процесс жить после выхода: фронтенд завершился, а бэкенд держит порт 8000, и
следующий `make dev` падает с «address already in use». Проверено — процесс
действительно переживает выход. `set -m` кладёт фоновую задачу в отдельную
группу процессов, `kill -- -$BACK` убивает группу целиком вместе с питоном,
которого `uv run` запускает своим потомком.

**Имена целей.** `revision` создаёт миграцию, `migrate` применяет — как в
самом Alembic. Обратный порядок, где `migrate` создаёт, привычен по Django и
Rails и стал бы здесь ловушкой.

**Защита `m=`.** Без имени Alembic создаёт файл со случайным именем, и через
месяц история миграций нечитаема. Пустая строка (`m=""`) тоже отвергается.

- [ ] **Шаг 2: Проверить, что проверки проходят**

Run: `make check`
Expected: ruff, mypy, lint-imports и pytest зелёные (13 тестов), затем
строка «фронтенд не установлен, его проверки пропущены».

- [ ] **Шаг 3: Проверить, что защиты срабатывают**

```bash
make revision           # ожидается отказ: «нужно имя: make revision m=<слаг>»
make revision m=""      # тот же отказ
make -n dev             # ожидается набор команд без запуска
```

- [ ] **Шаг 4: Коммит**

```bash
git add Makefile
git commit -m "chore: Makefile как единая точка входа в проверки"
```

---

## Фаза 1. Домен: чистая логика

Всё в `app/domain/` — без базы, без сети, без FastAPI. Сначала тест, потом код.

### Задача 5: Деньги

**Files:**
- Create: `backend/app/domain/money.py`
- Create: `backend/tests/unit/test_money.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_money.py`:

```python
from app.domain.money import MAX_AMOUNT_MINOR, format_money, parse_money_to_minor


class TestParse:
    def test_plain_integer(self):
        assert parse_money_to_minor("100") == 10000

    def test_comma_separator(self):
        assert parse_money_to_minor("12,34") == 1234

    def test_dot_separator(self):
        assert parse_money_to_minor("12.34") == 1234

    def test_spaces_are_thousand_separators(self):
        assert parse_money_to_minor("1 234.50") == 123450

    def test_nbsp_is_also_a_separator(self):
        # Значение, скопированное из интерфейса, приезжает с неразрывным
        # пробелом. Без этой строки человек копирует показанное ему же число
        # и получает «сумма не похожа на число».
        assert parse_money_to_minor("1\xa0234,50") == 123450

    def test_three_decimals_rejected(self):
        # В копейках два знака. Третий означает, что человек ошибся, а не что
        # надо округлить: молча округлив, мы запишем не ту сумму.
        assert parse_money_to_minor("1.234") is None

    def test_garbage_rejected(self):
        assert parse_money_to_minor("сто рублей") is None

    def test_empty_rejected(self):
        assert parse_money_to_minor("") is None
        assert parse_money_to_minor("   ") is None

    def test_negative_parsed(self):
        # Разбор отрицательное пропускает; запрещает его правило в сервисе,
        # потому что «расход не может быть отрицательным» — правило предметной
        # области, а не свойство записи числа.
        assert parse_money_to_minor("-5,00") == -500

    def test_no_float_drift(self):
        # 0.1 + 0.2 в float даёт 0.30000000000000004. Через Decimal — ровно 30.
        assert parse_money_to_minor("839,29") == 83929
        assert parse_money_to_minor("0,29") == 29

    def test_arabic_indic_digits_rejected(self):
        # \d в Python юникодный и принял бы их, разобрав верно. Но интерфейс
        # шлёт только ASCII, и молчаливая поддержка чужих систем счисления —
        # случайность, а не решение. Явное [0-9] делает границу видимой.
        assert parse_money_to_minor("١٢٣,٤٥") is None

    def test_long_input_is_exact(self):
        # Умножение на 100 через Decimal округляется по точности контекста
        # (28 значащих цифр) и на длинном вводе молча возвращает другое
        # число. Склейка строк точна при любой длине.
        assert parse_money_to_minor("1" * 29 + ",00") == int("1" * 29 + "00")

    def test_over_limit_is_parsed_not_rejected(self):
        # Разбор предела не проверяет — это контракт, а не упущение. None
        # означает «не число», и нагрузив его смыслом «слишком много», мы
        # лишили бы сервис возможности показать верное сообщение. Проверку
        # по MAX_AMOUNT_MINOR делает сервис фичи.
        assert parse_money_to_minor("21474836.48") == MAX_AMOUNT_MINOR + 1

class TestFormat:
    def test_basic(self):
        assert format_money(123456) == "1 234,56 ₽"

    def test_kopecks_padded(self):
        assert format_money(5) == "0,05 ₽"

    def test_zero(self):
        assert format_money(0) == "0,00 ₽"

    def test_negative(self):
        assert format_money(-500) == "-5,00 ₽"

    def test_limit(self):
        assert format_money(MAX_AMOUNT_MINOR) == "21 474 836,47 ₽"


def test_limit_is_int4_max():
    # Не выдуманное число: amount_minor хранится как Integer, а это int4 в
    # PostgreSQL. Без проверки по этой границе сумма пройдёт разбор и упадёт
    # в базе ошибкой драйвера, которую специалисту читать нечем.
    assert MAX_AMOUNT_MINOR == 2_147_483_647
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_money.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.money'`

- [ ] **Шаг 3: Написать `backend/app/domain/money.py`**

```python
"""Деньги.

Всегда целые копейки. Float для денег не используется нигде: 0.1 + 0.2 даёт
0.30000000000000004, и на достаточном числе записей это превращается в
расхождение, которое находят при сверке, а не в коде.
"""

import re

# Предел int4 в PostgreSQL — колонка amount_minor объявлена как Integer.
# Примерно 21,47 млн рублей. Нужны суммы больше — это BigInt в схеме и
# отдельное решение владельца: BigInt требует форматирования на сервере.
MAX_AMOUNT_MINOR = 2_147_483_647

# [0-9], а не \d: \d в Python юникодный и принимает арабо-индийские и
# деванагари цифры. Разбирались бы они верно, но интерфейс шлёт только
# ASCII, и молча принимать чужие системы счисления — не замысел, а
# случайность.
_NUMBER = re.compile(r"-?[0-9]+(\.[0-9]{1,2})?")


def parse_money_to_minor(raw: str) -> int | None:
    """Разбирает пользовательский ввод в копейки. None — не число.

    Единственный допустимый способ прочитать сумму из формы. Прямое
    приведение к числу здесь не работает: float("12,34") падает, а
    float("12.345") молча теряет копейку.

    **Предел не проверяется здесь намеренно.** None — единственный сигнал
    отказа, и нагрузив его ещё и «сумма слишком велика», мы лишили бы
    вызывающего возможности отличить одно от другого: человек увидел бы
    «сумма не похожа на число» на совершенно правильно записанной сумме.
    Проверку по MAX_AMOUNT_MINOR делает сервис фичи — там же, где живёт
    запрет отрицательных сумм, и по той же причине: это правила предметной
    области, а не свойства записи числа.
    """
    s = raw.strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not _NUMBER.fullmatch(s):
        return None
    # Копейки собираются склейкой строк, а не умножением на 100. Decimal
    # умеет умножать только в пределах точности контекста (по умолчанию 28
    # значащих цифр), и на более длинном вводе результат молча округляется:
    # возвращается похожее на правду, но другое число, без исключения.
    # Склейка точна при любой длине и не зависит от глобальной настройки,
    # которую кто-нибудь однажды поменяет в другом конце приложения.
    whole, _, frac = s.partition(".")
    return int(whole + (frac + "00")[:2])


def format_money(minor: int) -> str:
    """Форматирует копейки для показа человеку.

    Используется в текстах ошибок самого бэкенда. Интерфейс форматирует у
    себя через Intl: показ — забота клиента, разбор — забота сервера.
    """
    sign = "-" if minor < 0 else ""
    whole, frac = divmod(abs(minor), 100)
    grouped = f"{whole:,}".replace(",", "\xa0")
    return f"{sign}{grouped},{frac:02d}\xa0₽"
```

Неразрывный пробел записан **escape-последовательностью** `"\xa0"`, а не
литеральным символом, и это не стилистика. Литеральный NBSP визуально
неотличим от обычного пробела: он молча теряется при копировании и вставке,
а обнаружить подмену можно только сравнением кодпоинтов. Escape-запись
видна глазом и исказиться не может.

Цена ошибки несимметрична. Потеря NBSP в `format_money` разорвёт сумму по
строке пополам — это заметят сразу. Потеря NBSP в **тесте** не заметна
вовсе: тест остаётся зелёным, но перестаёт проверять то, ради чего написан,
и молча дублирует соседний.

Ещё три решения в этом модуле стоят объяснения, все проверены запуском.

**Копейки собираются склейкой строк, а не умножением на 100.** `Decimal`
умножает в пределах точности контекста — по умолчанию 28 значащих цифр, — и
на более длинном вводе результат молча округляется: возвращается похожее на
правду, но другое число, без исключения. Проверено: на 29 цифрах старая
запись давала `…1111000` вместо `…1111100`. Склейка точна при любой длине и
не зависит от глобальной настройки, которую кто-нибудь однажды поменяет в
другом конце приложения. Побочно исчезает и `except InvalidOperation`:
арифметики больше нет, ловить нечего.

**`[0-9]`, а не `\d`.** Юникодный `\d` принимает арабо-индийские и
деванагари цифры — проверено, `"١٢٣,٤٥"` разбирался в 12345. Разбирался
верно, но интерфейс шлёт только ASCII, и молчаливая поддержка чужих систем
счисления — случайность, а не решение.

**Предел не проверяется в разборе.** Это контракт, а не упущение, и он
записан в docstring, потому что читается как ошибка. `None` — единственный
сигнал отказа, и нагрузив его смыслом «слишком велика», мы лишили бы
вызывающего возможности отличить одно от другого: человек увидел бы «сумма
не похожа на число» на верно записанной сумме. Проверку по
`MAX_AMOUNT_MINOR` делает сервис фичи (задача 21) — там же, где запрет
отрицательных сумм, и по той же причине.

- [ ] **Шаг 4: Поправить тест под неразрывный пробел**

В `backend/tests/unit/test_money.py` заменить класс `TestFormat` на:

```python
class TestFormat:
    @staticmethod
    def fmt(minor: int) -> str:
        # Разделитель разрядов — неразрывный пробел: иначе сумма переносится
        # по строке пополам. В тесте сравниваем с обычным для читаемости.
        return format_money(minor).replace("\xa0", " ")

    def test_basic(self):
        assert self.fmt(123456) == "1 234,56 ₽"

    def test_kopecks_padded(self):
        assert self.fmt(5) == "0,05 ₽"

    def test_zero(self):
        assert self.fmt(0) == "0,00 ₽"

    def test_negative(self):
        assert self.fmt(-500) == "-5,00 ₽"

    def test_limit(self):
        assert self.fmt(MAX_AMOUNT_MINOR) == "21 474 836,47 ₽"
```

- [ ] **Шаг 5: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_money.py -v`
Expected: PASS, 19 passed

- [ ] **Шаг 6: Коммит**

```bash
git add backend/app/domain/money.py backend/tests/unit/test_money.py
git commit -m "feat: разбор и форматирование денег в копейках"
```

---

### Задача 6: Даты

**Files:**
- Create: `backend/app/domain/dates.py`
- Create: `backend/tests/unit/test_dates.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_dates.py`:

```python
from datetime import UTC, datetime

import pytest

from app.domain.dates import MSK, format_date, format_date_time, parse_date_input_value


class TestParse:
    def test_valid_date(self):
        d = parse_date_input_value("2026-08-31")
        assert d is not None
        assert (d.year, d.month, d.day) == (2026, 8, 31)
        assert d.utcoffset().total_seconds() == 3 * 3600

    def test_impossible_date_rejected(self):
        # 31 февраля проходит проверку формата, но такой даты нет. В JS
        # движок молча переносит её на 3 марта; здесь получаем None.
        assert parse_date_input_value("2026-02-31") is None

    def test_leap_day_valid_in_leap_year(self):
        assert parse_date_input_value("2028-02-29") is not None

    def test_leap_day_invalid_in_common_year(self):
        assert parse_date_input_value("2026-02-29") is None

    def test_wrong_format_rejected(self):
        assert parse_date_input_value("31.08.2026") is None
        assert parse_date_input_value("") is None
        assert parse_date_input_value("вчера") is None
        assert parse_date_input_value("2026-13-01") is None

    def test_basic_iso_format_rejected(self):
        # date.fromisoformat принял бы: с 3.11 он понимает запись без
        # дефисов. Контракт обещает YYYY-MM-DD, шире принимать незачем.
        assert parse_date_input_value("20260831") is None

    def test_iso_week_date_rejected(self):
        # Самый неприятный случай: date.fromisoformat разбирает это в
        # 29 декабря 2025 года — дату другого года.
        assert parse_date_input_value("2026-W01-1") is None

    def test_midnight_moscow_not_utc(self):
        # Начало суток берётся в московской зоне. Взяв полночь UTC, мы бы
        # записали 03:00 по Москве, и запись за 31-е числа попадала бы в
        # выборку за 1-е при фильтре по дате.
        d = parse_date_input_value("2026-08-31")
        assert d.astimezone(UTC).hour == 21
        assert d.astimezone(UTC).day == 30


class TestFormat:
    def test_date(self):
        assert format_date(datetime(2026, 8, 31, 12, 0, tzinfo=MSK)) == "31.08.2026"

    def test_datetime(self):
        v = datetime(2026, 8, 31, 14, 5, tzinfo=MSK)
        assert format_date_time(v) == "31.08.2026 14:05"

    def test_utc_value_shown_in_moscow(self):
        # Из базы значения приходят в UTC. Показывать их надо по Москве.
        v = datetime(2026, 8, 31, 21, 30, tzinfo=UTC)
        assert format_date_time(v) == "01.09.2026 00:30"

    def test_naive_datetime_rejected(self):
        # Значение без зоны astimezone не отвергает: Python считает его
        # временем в зоне процесса и молча конвертирует. На машине в Москве
        # показ верен, на сервере в UTC — съезжает на три часа. Такая
        # ошибка обнаруживается на контуре и ищется в данных, а не в коде,
        # поэтому падать надо здесь и громко.
        with pytest.raises(ValueError):
            format_date(datetime(2026, 8, 31))
        with pytest.raises(ValueError):
            format_date_time(datetime(2026, 8, 31, 12, 0))
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_dates.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.dates'`

- [ ] **Шаг 3: Написать `backend/app/domain/dates.py`**

```python
"""Даты.

В базе — TIMESTAMPTZ. Человеку — московская зона: приложение внутреннее, и
часовой пояс у него один. Понадобятся другие зоны — это отдельное решение,
а не «добавить параметр».
"""

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

# Ровно YYYY-MM-DD и ничего больше. date.fromisoformat в Python 3.11+
# принимает заметно шире: "20260831" без дефисов и — что хуже —
# "2026-W01-1", недельную нумерацию ISO, которая разбирается в 29 декабря
# 2025 года. Строка, похожая на мусор, молча становится датой другого года.
# Поле type="date" такого не пришлёт, но API принимает произвольную строку,
# и контракт обязан совпадать с обещанием docstring.
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_date_input_value(raw: str) -> datetime | None:
    """Разбирает значение поля type="date" (ISO, YYYY-MM-DD).

    None — строка не является существующей датой этого формата. Проверку
    существования делает date.fromisoformat: он отвергает 2026-02-31, а не
    переносит её на март, как молча делает движок JavaScript.
    """
    if not _ISO_DATE.fullmatch(raw):
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    return datetime.combine(parsed, time.min, tzinfo=MSK)


def _in_moscow(value: datetime) -> datetime:
    """Переводит значение в московскую зону, отвергая наивное.

    astimezone на datetime без зоны не падает: Python молча считает его
    временем в зоне процесса. Проверено — один и тот же вызов даёт три
    разные даты при TZ=Europe/Moscow, UTC и America/New_York.

    Для нас это не теория: машина разработчика в Москве, контур на сервере
    почти наверняка в UTC. Локально показ верен, на контуре та же запись
    съезжает на три часа, и расхождение ищут в данных, а не в коде.

    Из базы значения приходят с зоной (TIMESTAMPTZ), поэтому наивное
    значение здесь означает ошибку в коде, и падать надо громко.
    """
    if value.tzinfo is None:
        raise ValueError(
            "datetime без часового пояса: показ зависел бы от зоны сервера"
        )
    return value.astimezone(MSK)


def format_date(value: datetime) -> str:
    return _in_moscow(value).strftime("%d.%m.%Y")


def format_date_time(value: datetime) -> str:
    return _in_moscow(value).strftime("%d.%m.%Y %H:%M")
```

- [ ] **Шаг 4: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_dates.py -v`
Expected: PASS, 12 passed

- [ ] **Шаг 5: Коммит**

```bash
git add backend/app/domain/dates.py backend/tests/unit/test_dates.py
git commit -m "feat: разбор и показ дат в московской зоне"
```

---

### Задача 7: Роли

**Files:**
- Create: `backend/app/domain/roles.py`
- Create: `backend/tests/unit/test_roles.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_roles.py`:

```python
import pytest

from app.domain.roles import ROLES, Role, has_rank


def test_roles_ordered_by_rank():
    assert ROLES == ("viewer", "editor", "admin")


class TestHasRank:
    def test_exact_match(self):
        assert has_rank(Role.editor, Role.editor) is True

    def test_higher_passes(self):
        assert has_rank(Role.admin, Role.editor) is True

    def test_lower_denied(self):
        assert has_rank(Role.viewer, Role.editor) is False

    def test_viewer_is_lowest(self):
        assert has_rank(Role.viewer, Role.viewer) is True
        assert has_rank(Role.viewer, Role.admin) is False


def test_unknown_role_denies_rather_than_passes():
    # Ошибка настройки обязана закрывать доступ, а не открывать. В эталоне
    # это была ловушка с indexOf, возвращающим -1: условие «has < -1» ложно
    # для любой роли, и разграничение пускало бы каждого.
    with pytest.raises(ValueError):
        Role("superuser")
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_roles.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.roles'`

- [ ] **Шаг 3: Написать `backend/app/domain/roles.py`**

```python
"""Роли по рангу: viewer < editor < admin."""

from enum import StrEnum


class Role(StrEnum):
    viewer = "viewer"
    editor = "editor"
    admin = "admin"


# Порядок значим: ранг — это позиция в кортеже. Выражать «больше прав»
# сравнением строк пришлось бы заново в каждой проверке.
ROLES: tuple[str, ...] = tuple(r.value for r in Role)


def has_rank(actual: Role, required: Role) -> bool:
    """Хватает ли роли actual, чтобы пройти проверку на required."""
    return ROLES.index(actual.value) >= ROLES.index(required.value)
```

Неизвестная роль здесь невозможна по построению: `Role("superuser")` бросает
`ValueError` при разборе, а значит до сравнения дело не доходит. Это сильнее
проверки в рантайме — тип закрывает случай на входе.

- [ ] **Шаг 4: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_roles.py -v`
Expected: PASS, 6 passed

- [ ] **Шаг 5: Коммит**

```bash
git add backend/app/domain/roles.py backend/tests/unit/test_roles.py
git commit -m "feat: роли и сравнение по рангу"
```

---

### Задача 8: Категории и агрегации расходов

Образцовая доменная логика: показывает, как выглядит чистый расчёт с тестами.
Удаляется вместе с образцовой фичей.

**Files:**
- Create: `backend/app/domain/expenses.py`
- Create: `backend/tests/unit/test_expenses.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_expenses.py`:

```python
import pytest

from app.domain.expenses import CATEGORIES, CategoryTotal, totals_by_category


def test_categories_are_fixed():
    assert CATEGORIES == ("Аренда", "Софт", "Оборудование", "Услуги", "Прочее")


class TestTotals:
    def test_empty_input(self):
        assert totals_by_category([]) == []

    def test_single_row(self):
        assert totals_by_category([("Софт", 10000)]) == [
            CategoryTotal(category="Софт", total_minor=10000, share=1.0)
        ]

    def test_sums_within_category(self):
        result = totals_by_category([("Софт", 10000), ("Софт", 5000)])
        assert result == [CategoryTotal(category="Софт", total_minor=15000, share=1.0)]

    def test_sorted_by_total_descending(self):
        result = totals_by_category(
            [("Софт", 10000), ("Аренда", 50000), ("Прочее", 2000)]
        )
        assert [r.category for r in result] == ["Аренда", "Софт", "Прочее"]

    def test_equal_totals_ordered_by_name(self):
        # Порядок обязан зависеть только от данных, а не от того, в каком
        # порядке база вернула строки.
        first = totals_by_category([("Софт", 500), ("Аренда", 500), ("Услуги", 500)])
        second = totals_by_category([("Услуги", 500), ("Софт", 500), ("Аренда", 500)])
        assert [r.category for r in first] == ["Аренда", "Софт", "Услуги"]
        assert [r.category for r in first] == [r.category for r in second]

    def test_share_computed(self):
        result = totals_by_category([("Аренда", 75000), ("Софт", 25000)])
        assert result[0].share == 0.75
        assert result[1].share == 0.25

    def test_zero_total_gives_zero_shares(self):
        # Деление на ноль: все суммы могут оказаться нулевыми. Без этой
        # ветки экран сводки падал бы на пустяке.
        #
        # Сравнение со всем списком, а не `all(r.share == 0 for r in ...)`:
        # такая проверка истинна и на пустом списке, поэтому не заметила бы
        # реализацию, которая при нулевом итоге просто возвращает ничего.
        # Проверено мутацией — не заметила.
        assert totals_by_category([("Софт", 0), ("Аренда", 0)]) == [
            CategoryTotal(category="Аренда", total_minor=0, share=0.0),
            CategoryTotal(category="Софт", total_minor=0, share=0.0),
        ]

    def test_negative_amount_rejected(self):
        # Доля от знакопеременного набора перестаёт быть долей: при суммах
        # −5000 и 10000 получаются доли −100 % и 200 %. Коварство в том, что
        # сумма долей при этом остаётся ровно единицей, и проверка «доли
        # сходятся» такую картину пропускает, а круговая диаграмма рисует
        # сектор в 3600 градусов.
        with pytest.raises(ValueError):
            totals_by_category([("Софт", -5000), ("Аренда", 10000)])
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_expenses.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.expenses'`

- [ ] **Шаг 3: Написать `backend/app/domain/expenses.py`**

```python
"""Расходы: категории и сводка.

ОБРАЗЕЦ. Показывает, как выглядит чистый расчёт: без базы, без HTTP, с
обязательными unit-тестами. Удаляется вместе с образцовой фичей.
"""

from dataclasses import dataclass

# Список живёт здесь, а не enum'ом в базе: категории меняются заметно чаще
# схемы. Цена решения — синхронизация ручная: переименуют категорию в коде,
# старые строки останутся с прежней.
CATEGORIES: tuple[str, ...] = ("Аренда", "Софт", "Оборудование", "Услуги", "Прочее")


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    category: str
    total_minor: int
    share: float


def totals_by_category(rows: list[tuple[str, int]]) -> list[CategoryTotal]:
    """Сводка по категориям, от большей суммы к меньшей.

    Принимает пары «категория, копейки» — не модели SQLAlchemy: доменная
    логика не должна знать, откуда пришли данные, иначе её не проверить без
    базы.

    Отрицательные суммы отвергаются. Доля от знакопеременного набора
    перестаёт быть долей: она вылезает за сто процентов и уходит в минус, а
    сумма долей при этом остаётся равной единице — то есть проверка «доли
    сходятся» такую картину пропустит, и круговая диаграмма нарисует сектор
    в 3600 градусов. Это ровно тот случай, когда молчаливая неправда хуже
    отказа. Запрет отрицательных расходов держит сервис фичи; здесь речь о
    другом — о контракте самой функции, который на таких данных нарушен.
    """
    for category, minor in rows:
        if minor < 0:
            raise ValueError(
                f"отрицательная сумма в категории «{category}»: доля не определена"
            )

    sums: dict[str, int] = {}
    for category, minor in rows:
        sums[category] = sums.get(category, 0) + minor

    total = sum(sums.values())
    return [
        CategoryTotal(
            category=category,
            total_minor=value,
            share=(value / total) if total else 0.0,
        )
        # Разрыв ничьей по названию, а не «как получилось». Без него порядок
        # категорий с равными суммами определяется порядком строк из базы, и
        # на экране сводки они переставляются между обновлениями страницы —
        # выглядит как мерцание, объясняется ничем. Проверено.
        for category, value in sorted(sums.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
```

- [ ] **Шаг 4: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_expenses.py -v`
Expected: PASS, 9 passed

- [ ] **Шаг 5: Прогнать все проверки бэкенда**

Run: `make check-backend`
Expected: ruff, mypy, lint-imports, pytest — всё зелёное.

- [ ] **Шаг 6: Коммит**

```bash
git add backend/app/domain/expenses.py backend/tests/unit/test_expenses.py
git commit -m "feat: категории расходов и сводка по категориям"
```

---

## Фаза 2. База данных

### Задача 9: Доступ к базе

**Files:**
- Create: `backend/app/core/db.py`

- [ ] **Шаг 1: Написать `backend/app/core/db.py`**

```python
"""Единственная точка доступа к базе в коде приложения.

Транзакцией управляет сервис фичи: он и знает, что должно уехать вместе.
Сессия здесь только выдаётся и закрывается.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Общий предок таблиц. От него же Alembic берёт метаданные."""


engine = create_async_engine(
    settings.async_database_url,
    # Соединение, простоявшее ночь, PostgreSQL успевает закрыть со своей
    # стороны. Без pre_ping первый утренний запрос падал бы разрывом связи.
    pool_pre_ping=True,
    # Приложение внутреннее, пользователей десятки: большой пул только
    # занимал бы соединения на общем сервере, где живут и соседние базы.
    pool_size=5,
    max_overflow=5,
)

SessionFactory = async_sessionmaker(
    engine,
    # Иначе после commit() у объектов сбрасываются атрибуты, и первое же
    # обращение к ним вне транзакции уходит в базу за уже известным —
    # в async-коде это ещё и MissingGreenlet, который нечем читать.
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: сессия на запрос."""
    async with SessionFactory() as session:
        yield session
```

- [ ] **Шаг 2: Проверить типы**

Run: `cd backend && uv run mypy app`
Expected: Success, no issues

- [ ] **Шаг 3: Проверить подключение к живой базе**

Подстановка драйвера `+asyncpg` сделана руками в `async_database_url`, и
работает ли она против настоящего PostgreSQL, до сих пор нигде не
проверялось. Выяснить это на задаче 17, когда упадут все тесты сразу, —
плохой момент.

Роль и базы заводятся в задаче 11 (шаг 4). Если их ещё нет, выполнить тот
шаг сейчас, иначе проверка ниже отвечает `role "apptemplate" does not exist`.

```bash
cd backend && uv run python -c "
import asyncio
from sqlalchemy import text
from app.core.db import SessionFactory

async def main():
    async with SessionFactory() as session:
        print((await session.execute(text('SELECT version()'))).scalar_one()[:40])

asyncio.run(main())
"
```

Ожидается строка вида `PostgreSQL 18.4 ...`. Ошибка здесь означает одно из
трёх: не поднят PostgreSQL, нет роли или базы, либо драйвер подставлен
неверно — и все три надо чинить сейчас, а не в задаче 17.

- [ ] **Шаг 4: Коммит**

```bash
git add backend/app/core/db.py
git commit -m "feat: движок и сессия SQLAlchemy"
```

---

### Задача 10: Таблицы

**Files:**
- Create: `backend/app/core/audit.py`
- Create: `backend/app/features/users/__init__.py`
- Create: `backend/app/features/users/models.py`
- Create: `backend/app/features/expenses/__init__.py`
- Create: `backend/app/features/expenses/models.py`

- [ ] **Шаг 1: Создать пакеты фич**

```bash
mkdir -p backend/app/features/{auth,users,expenses,audit,meta}
touch backend/app/features/{auth,users,expenses,audit,meta}/__init__.py
```

- [ ] **Шаг 2: Написать `backend/app/core/audit.py`**

Модель журнала лежит в `core`, а не в фиче: пишут в неё все фичи, а читает
экран `features/audit`. Держать её в одной из фич значило бы, что остальные
импортируют чужие внутренности — ровно то, что запрещает контракт
независимости.

```python
"""Журнал аудита: пишется при каждой мутации данных."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Предел колонки detail — он же предел того, что журнал готов запомнить.
DETAIL_MAX = 1024


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_ts", "ts"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # Логин строкой, а не связь с users: журнал обязан пережить учётную
    # запись. Работает, пока логины не переименовывают и учётки не удаляют —
    # ни того, ни другого в приложении нет. Появится переименование — журнал
    # разойдётся с реальностью, и решать это придётся здесь.
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(String(1024), default="")


def write_audit(
    session: AsyncSession,
    actor: str,
    action: str,
    entity: str,
    entity_id: str,
    detail: str = "",
) -> None:
    """Кладёт запись в ту же сессию, что и мутация.

    Без commit намеренно: коммитит сервис, одной транзакцией вместе с самим
    изменением. В эталоне запись в журнал шла отдельным вызовом после
    сохранения — падение процесса между ними оставляло изменение без следа,
    а журнал с дырами доверия не заслуживает.

    Длинный detail обрезается, а не роняет запись. Та же общая транзакция
    означает, что строка длиннее колонки отменила бы саму мутацию: расход не
    сохранился бы из-за слишком подробной заметки о нём. Размен плохой, и
    обрезка тут — единственное разумное поведение. Многоточие в конце
    оставляется намеренно, чтобы читающий журнал видел неполноту.
    """
    if len(detail) > DETAIL_MAX:
        detail = detail[: DETAIL_MAX - 1] + "…"

    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail,
        )
    )
```

- [ ] **Шаг 2а: Написать `backend/tests/unit/test_audit.py`**

Единственные тесты в этой задаче, и они про правило, а не про базу:
настоящая сессия здесь мешала бы, поэтому подставляется запоминающая
заглушка.

```python
from app.core.audit import DETAIL_MAX, write_audit


class Recorder:
    """Подставная сессия: write_audit только кладёт объект, больше ничего.

    Настоящая сессия здесь не нужна и мешала бы: проверяется правило, а не
    работа базы.
    """

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


def record(detail: str) -> str:
    recorder = Recorder()
    write_audit(recorder, "boss", "create", "Expense", "id-1", detail)  # type: ignore[arg-type]
    return recorder.added[0].detail  # type: ignore[attr-defined]


def test_short_detail_kept_as_is():
    assert record("Софт, 12000 коп.") == "Софт, 12000 коп."


def test_detail_at_limit_kept_whole():
    assert record("x" * DETAIL_MAX) == "x" * DETAIL_MAX


def test_longer_detail_truncated_and_marked():
    result = record("x" * (DETAIL_MAX + 1))
    assert len(result) == DETAIL_MAX
    assert result.endswith("…")


def test_truncation_counts_characters_not_bytes():
    # VARCHAR(1024) в PostgreSQL считает символы: 1024 кириллических знака
    # занимают 2048 байт и укладываются. Проверено на живой базе.
    result = record("я" * 5000)
    assert len(result) == DETAIL_MAX
```

- [ ] **Шаг 3: Написать `backend/app/features/users/models.py`**

```python
"""Учётные записи приложения. Вход только собственный."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.domain.roles import Role


class UserStatus(StrEnum):
    active = "active"
    disabled = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    login: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        # values_callable обязателен: без него SQLAlchemy пишет в базу ИМЕНА
        # членов enum, а не значения. Для StrEnum они совпадают, и ошибка
        # всплыла бы только после первого переименования члена.
        Enum(Role, name="role", values_callable=lambda e: [i.value for i in e])
    )
    # scrypt$<N>$<salt_hex>$<hash_hex>; NULL = вход невозможен.
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Отключение: вход закрыт, данные и журнал остаются. Удаления
    # пользователей нет намеренно — удалённый автор записи в журнале
    # превратил бы историю в набор осиротевших строк.
    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status",
            values_callable=lambda e: [i.value for i in e],
        ),
        default=UserStatus.active,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Сессии, выданные раньше этой отметки, недействительны. NULL = не
    # отзывались.
    sessions_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

`created_at` без `default` намеренно: значение ставит сервис, и оно видно в
коде создания. Скрытый `server_default=now()` расходится с тем, что показано
в тестах.

- [ ] **Шаг 4: Написать `backend/app/features/expenses/models.py`**

```python
"""ОБРАЗЕЦ. Удаляется, когда появится первая настоящая фича."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_date", "date"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(255))
    # Целые копейки. Integer — это int4 в PostgreSQL, отсюда предел
    # MAX_AMOUNT_MINOR, который обязан проверять сервис.
    amount_minor: Mapped[int] = mapped_column(Integer)
    # Строка, а не enum базы: список категорий живёт в app/domain/expenses.py
    # и проверяется схемой на записи. Синхронизация только ручная.
    category: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Шаг 5: Добавить контракт независимости фич**

Пакеты всех пяти фич теперь существуют, значит контракт можно включить.
Дописать в `backend/.importlinter`:

```ini
[importlinter:contract:features-are-independent]
name = фичи не лезут друг другу внутрь
type = independence
modules =
    app.features.auth
    app.features.users
    app.features.expenses
    app.features.audit
    app.features.meta
```

`independence` запрещает импорт в обе стороны. Когда расходам понадобится
пользователь, обращение идёт через `users.service` — и это осознанный шаг, а
не случайная связь: контракт придётся править руками, и правка будет видна
в дифе.

- [ ] **Шаг 6: Проверить типы и границы**

Run: `cd backend && uv run mypy app && uv run --group lint lint-imports --config .importlinter`
Expected: mypy Success; `Contracts: 2 kept, 0 broken.`

Прогон тестов: `uv run pytest` — ожидается 63 (59 прежних плюс 4 новых).

Докажи мутацией, что тесты на обрезку не пустые: убери из `write_audit`
две строки с `DETAIL_MAX`, прогони — должны упасть два теста из четырёх.
Верни как было.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/core/audit.py backend/app/features/ backend/.importlinter \
        backend/tests/unit/test_audit.py
git commit -m "feat: таблицы пользователей, журнала аудита и расходов"
```

---

### Задача 11: Миграции Alembic

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/<хеш>_init.py` (генерируется)

- [ ] **Шаг 1: Развернуть асинхронный шаблон Alembic**

```bash
cd backend && uv run alembic init -t async alembic
```

Команда создаёт `alembic.ini`, `alembic/env.py` и `alembic/script.py.mako`.
Дальше два файла правятся.

- [ ] **Шаг 2: Убрать адрес базы из `backend/alembic.ini`**

Найти строку `sqlalchemy.url = driver://user:pass@localhost/dbname` и
заменить на пустое значение с комментарием:

```ini
# Адрес берётся из окружения в env.py. Здесь его нет намеренно: файл
# коммитится, а строка подключения содержит пароль роли базы.
sqlalchemy.url =
```

- [ ] **Шаг 3: Переписать `backend/alembic/env.py`**

```python
"""Окружение Alembic.

Обвязка запускается до того, как приложение существует, и читает настройки
сама — так же, как это описано для скриптов в правилах проекта.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import Base

# Импорт ради регистрации таблиц в Base.metadata: без него autogenerate
# видит пустую схему и предлагает удалить всё, что есть в базе.
from app.core.audit import AuditLog  # noqa: F401
from app.features.expenses.models import Expense  # noqa: F401
from app.features.users.models import User  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.async_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.async_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Без этого Alembic не замечает смену типа колонки: миграция
        # выглядит применённой, а тип в базе остаётся прежним.
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Движок асинхронный, то есть Alembic ходит в базу тем же asyncpg, что
    # и приложение. Синхронный драйвер (psycopg) здесь не нужен и в
    # зависимостях его нет намеренно: вторая библиотека доступа к базе —
    # это второй набор различий в поведении, который однажды придётся
    # разбирать.
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Шаг 4: Завести локальную роль и базы**

Роль создаётся первой: `.env` подключается под ней, и без неё базы будут
существовать, но подключиться к ним по строке из `.env` не выйдет —
`FATAL: role "apptemplate" does not exist`. Ошибка появляется не при
создании баз, а позже, при первой миграции, и ищут её не там.

На контуре роль заводит провижинер (`<слаг>_app` со сгенерированным
паролем), локально — это ручной шаг установки.

Имена баз — `apptemplatepy_*`, а не `apptemplate_*`, и это не описка.
TS-шаблон `app-template-ts` берёт по умолчанию ровно `apptemplate_dev` и
`apptemplate_e2e`. У кого оба шаблона лежат рядом — а это обычный случай,
их для того и два, — базы столкнутся: Alembic увидит в своей базе чужие
таблицы, созданные Prisma, и либо откажется накатывать миграции, либо
предложит удалить незнакомое. Проверено на живой машине.

```bash
psql -d postgres -c "CREATE ROLE apptemplate LOGIN PASSWORD 'apptemplate'"
createdb -O apptemplate apptemplatepy_dev
createdb -O apptemplate apptemplatepy_e2e
```

`-O` задаёт владельца при создании. Отдельным `ALTER DATABASE ... OWNER`
это делать не надо: промахнувшись именем, легко сменить владельца чужой
базы, и заметят это не сразу.

Проверить, что строка из `.env` действительно работает:

```bash
psql "$(grep '^DATABASE_URL=' .env | sed 's/DATABASE_URL=//;s/\"//g')" \
  -tAc 'SELECT current_user, current_database()'
```

Ожидается `apptemplate|apptemplatepy_dev`.

Если `createdb` не найден — PostgreSQL 18 не установлен; поставить через
`brew install postgresql@18` (macOS) или `apt install postgresql-18` (Ubuntu).

- [ ] **Шаг 5: Сгенерировать первую миграцию**

```bash
cd backend && uv run alembic revision --autogenerate -m "init"
```

- [ ] **Шаг 6: ПРОЧИТАТЬ сгенерированную миграцию глазами**

Это не формальность. `--autogenerate` сравнивает метаданные с базой и
хорошо видит появление и исчезновение таблиц и колонок, но слеп к трём
вещам сразу: к переименованиям (показывает удаление плюс добавление, и
данные теряются), к изменению состава значений `enum` (не замечает вовсе)
и к смыслу изменения.

Отдельная ловушка первой миграции: если `env.py` не импортирует модули с
моделями, `Base.metadata` пуст, и autogenerate молча создаёт **пустую**
ревизию вместо схемы. В `env.py` из шага 3 такие импорты есть, помечены
`noqa: F401` — не «прибирай» их как неиспользуемые.

Открыть файл в `backend/alembic/versions/` и проверить:

- созданы три таблицы: `users`, `audit_log`, `expenses`;
- созданы типы `role` и `user_status`;
- есть индексы `ix_audit_log_ts`, `ix_expenses_date`, уникальный по
  `users.login`;
- в `downgrade()` типы enum удаляются явно (`sa.Enum(...).drop(op.get_bind())`)
  — autogenerate этого не пишет, и повторный `upgrade` после `downgrade`
  падает с «type role already exists». Дописать руками:

```python
def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("audit_log")
    op.drop_table("users")
    sa.Enum(name="user_status").drop(op.get_bind())
    sa.Enum(name="role").drop(op.get_bind())
```

- [ ] **Шаг 7: Применить и проверить обратимость**

```bash
cd backend && uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head
```

Expected: все три команды проходят без ошибок. Именно этот прогон ловит
забытое удаление enum.

- [ ] **Шаг 8: Коммит**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: миграции Alembic и начальная схема"
```

---

## Фаза 3. Вход, доступ и ошибки

### Задача 12: Пароли

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/tests/unit/test_password.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_password.py`:

```python
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
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_password.py`
Expected: FAIL — `ImportError: cannot import name 'hash_password'`

- [ ] **Шаг 3: Написать `backend/app/core/security.py`**

```python
"""Пароли и подпись сессии.

Параметры scrypt совпадают с умолчаниями Node (N=16384, r=8, p=1, 64 байта),
поэтому строки хешей совместимы с app-template-ts: базу с пользователями
можно перенести между шаблонами без сброса паролей.
"""

import base64
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
```

- [ ] **Шаг 4: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_password.py -v`
Expected: PASS, 6 passed

- [ ] **Шаг 5: Коммит**

```bash
git add backend/app/core/security.py backend/tests/unit/test_password.py
git commit -m "feat: хеширование и проверка паролей на scrypt"
```

---

### Задача 13: Токен сессии

**Files:**
- Modify: `backend/app/core/security.py` (дописать в конец)
- Create: `backend/tests/unit/test_token.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_token.py`:

```python
from app.core.security import AUTH_COOKIE, sign_session_token, verify_session_token

SECRET = "s" * 32
OTHER = "o" * 32


def test_cookie_name_is_stable():
    # Имя куки — часть контракта с браузером: смена разлогинит всех разом.
    assert AUTH_COOKIE == "app_session"


def test_roundtrip():
    token = sign_session_token("admin", 1756600000000, SECRET)
    assert verify_session_token(token, SECRET) == ("admin", 1756600000000)


def test_other_secret_rejected():
    token = sign_session_token("admin", 1756600000000, SECRET)
    assert verify_session_token(token, OTHER) is None


def test_tampered_payload_rejected():
    token = sign_session_token("viewer", 1756600000000, SECRET)
    payload, sig = token.split(".")
    forged = sign_session_token("admin", 1756600000000, OTHER).split(".")[0]
    assert verify_session_token(f"{forged}.{sig}", SECRET) is None


def test_malformed_input_rejected():
    assert verify_session_token(None, SECRET) is None
    assert verify_session_token("", SECRET) is None
    assert verify_session_token("безточки", SECRET) is None
    assert verify_session_token("a.b.c", SECRET) is None
    assert verify_session_token("!!!.!!!", SECRET) is None


def test_login_with_separator_inside_survives():
    # Разделитель полезной нагрузки не должен ломаться на логине,
    # содержащем его: иначе такой логин молча не сможет войти.
    token = sign_session_token("иван\nпетров", 1756600000000, SECRET)
    assert verify_session_token(token, SECRET) is None
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_token.py`
Expected: FAIL — `ImportError: cannot import name 'AUTH_COOKIE'`

- [ ] **Шаг 3: Дописать в конец `backend/app/core/security.py`**

```python
AUTH_COOKIE = "app_session"
_SEPARATOR = "\n"


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


def verify_session_token(token: str | None, secret: str) -> tuple[str, int] | None:
    """Проверяет подпись и возвращает (логин, время выдачи) или None.

    Здесь только подпись и форма. Блокировку, роль и отзыв сессии проверяет
    слой доступа: у отозванной куки подпись остаётся верной.
    """
    if not token or token.count(".") != 1:
        return None
    payload, signature = token.split(".")
    expected = _b64encode(
        hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        login, issued_raw = _b64decode(payload).decode().split(_SEPARATOR)
        return login, int(issued_raw)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        return None
```

Тест `test_login_with_separator_inside_survives` ожидает `None`: логин с
переводом строки внутри даёт три части при разборе, и токен отвергается.
Это правильное поведение — такой логин не должен существовать, и запрет на
него ставит схема при создании пользователя (задача 19).

- [ ] **Шаг 4: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_token.py -v`
Expected: PASS, 6 passed

- [ ] **Шаг 5: Коммит**

```bash
git add backend/app/core/security.py backend/tests/unit/test_token.py
git commit -m "feat: подпись и проверка токена сессии"
```

---

### Задача 14: Ограничение попыток входа

**Files:**
- Create: `backend/app/core/rate_limit.py`
- Create: `backend/tests/unit/test_rate_limit.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_rate_limit.py`:

```python
import pytest

from app.core.rate_limit import MAX_ATTEMPTS, WINDOW_SECONDS, RateLimiter


@pytest.fixture
def clock():
    class Clock:
        now = 1000.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    return Clock()


def test_allows_until_limit(clock):
    limiter = RateLimiter(now=clock)
    for _ in range(MAX_ATTEMPTS):
        assert limiter.check("admin") is True
        limiter.register_failure("admin")
    assert limiter.check("admin") is False


def test_window_expires(clock):
    limiter = RateLimiter(now=clock)
    for _ in range(MAX_ATTEMPTS):
        limiter.register_failure("admin")
    assert limiter.check("admin") is False
    clock.advance(WINDOW_SECONDS + 1)
    assert limiter.check("admin") is True


def test_keys_are_independent(clock):
    limiter = RateLimiter(now=clock)
    for _ in range(MAX_ATTEMPTS):
        limiter.register_failure("admin")
    assert limiter.check("admin") is False
    assert limiter.check("77.88.8.8") is True


def test_success_clears_counter(clock):
    limiter = RateLimiter(now=clock)
    limiter.register_failure("admin")
    limiter.register_failure("admin")
    limiter.reset("admin")
    for _ in range(MAX_ATTEMPTS):
        assert limiter.check("admin") is True
        limiter.register_failure("admin")


def test_old_attempts_drop_out_of_window(clock):
    # Скользящее окно, а не корзина с полным сбросом: пять попыток за час
    # не должны блокировать, если четыре из них были вчера.
    limiter = RateLimiter(now=clock)
    for _ in range(MAX_ATTEMPTS - 1):
        limiter.register_failure("admin")
    clock.advance(WINDOW_SECONDS + 1)
    limiter.register_failure("admin")
    assert limiter.check("admin") is True
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_rate_limit.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.rate_limit'`

- [ ] **Шаг 3: Написать `backend/app/core/rate_limit.py`**

```python
"""Ограничение попыток входа.

ИЗВЕСТНЫЙ ДОЛГ: счётчики живут в памяти процесса, перезапуск их обнуляет.
Пока процесс один — это и есть счётчик контура. Появится второй воркер или
второй процесс — понадобится общее хранилище, и решать это надо будет
вместе с очередью.
"""

import time
from collections import defaultdict
from collections.abc import Callable

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60


class RateLimiter:
    """Скользящее окно неудачных попыток по ключу.

    Ключ — либо логин, либо адрес. Оба ограничиваются отдельно: по логину,
    чтобы не подбирали пароль к конкретной учётной записи, по адресу — чтобы
    не перебирали логины с одной машины.
    """

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        # Время впрыскивается, чтобы тест не спал 15 минут.
        self._now = now
        self._failures: dict[str, list[float]] = defaultdict(list)

    def _recent(self, key: str) -> list[float]:
        border = self._now() - WINDOW_SECONDS
        kept = [t for t in self._failures[key] if t > border]
        self._failures[key] = kept
        return kept

    def check(self, key: str) -> bool:
        """True — попытка допустима."""
        return len(self._recent(key)) < MAX_ATTEMPTS

    def register_failure(self, key: str) -> None:
        self._recent(key)
        self._failures[key].append(self._now())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


login_limiter = RateLimiter()
```

- [ ] **Шаг 4: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_rate_limit.py -v`
Expected: PASS, 5 passed

- [ ] **Шаг 5: Коммит**

```bash
git add backend/app/core/rate_limit.py backend/tests/unit/test_rate_limit.py
git commit -m "feat: ограничение попыток входа по логину и адресу"
```

---

### Задача 15: Конверт ошибки

**Files:**
- Create: `backend/app/core/errors.py`
- Create: `backend/tests/unit/test_errors.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_errors.py`:

```python
from pydantic import BaseModel, Field, ValidationError

from app.core.errors import RuleViolation, validation_error_to_envelope


class Sample(BaseModel):
    amount: str = Field(min_length=1)
    title: str


def test_rule_violation_carries_field():
    e = RuleViolation("Сумма должна быть больше нуля", field="amount")
    assert e.message == "Сумма должна быть больше нуля"
    assert e.field == "amount"


def test_rule_violation_without_field():
    assert RuleViolation("Так нельзя").field is None


def test_validation_error_maps_to_single_message():
    # Наружу уходит одна ошибка, а не список: форма показывает одно
    # сообщение, и выбирать из пяти пришлось бы клиенту.
    try:
        Sample(amount="", title="x")
    except ValidationError as exc:
        envelope = validation_error_to_envelope(exc)
    assert envelope["field"] == "amount"
    assert envelope["error"]


def test_missing_field_reports_its_name():
    try:
        Sample(amount="10")
    except ValidationError as exc:
        envelope = validation_error_to_envelope(exc)
    assert envelope["field"] == "title"
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_errors.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.errors'`

- [ ] **Шаг 3: Написать `backend/app/core/errors.py`**

```python
"""Единый конверт ошибки: {"error": "текст", "field": "имя_поля"}.

Ожидаемые ошибки возвращаются, а не бросаются наружу как сбой. Клиент
разбирает одну форму ответа независимо от того, кто отказал — валидатор
схемы или правило в сервисе; иначе на клиенте появятся две ветки разбора,
и вторая будет написана хуже.
"""

import logging
from typing import TypedDict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class Envelope(TypedDict):
    error: str
    field: str | None


class RuleViolation(Exception):
    """Нарушение правила предметной области. Ожидаемое, отвечает 400."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def _first_issue(errors: list[dict[str, object]]) -> Envelope:
    issue = errors[0]
    location = [p for p in issue.get("loc", ()) if p not in ("body", "query")]  # type: ignore[union-attr]
    return Envelope(
        error=str(issue.get("msg", "Значение не подходит")),
        field=str(location[-1]) if location else None,
    )


def validation_error_to_envelope(exc: ValidationError) -> Envelope:
    return _first_issue(exc.errors())  # type: ignore[arg-type]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RuleViolation)
    async def _rule(_: Request, exc: RuleViolation) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=Envelope(error=exc.message, field=exc.field),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_first_issue(exc.errors()),  # type: ignore[arg-type]
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Наружу — ничего о причине: текст исключения регулярно содержит
        # кусок запроса, путь на диске или адрес базы. Подробности идут в
        # лог, который читают через /logs.
        logger.exception("необработанный сбой на %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=Envelope(error="Что-то пошло не так", field=None),
        )
```

Ответ на невалидный ввод — 400, а не привычный FastAPI 422. Причина в
контракте: клиент разбирает один код и одну форму, а различать «схема не
сошлась» и «правило не пустило» ему незачем — для человека это одна и та же
ошибка в форме.

- [ ] **Шаг 4: Запустить тест**

Run: `cd backend && uv run pytest tests/unit/test_errors.py -v`
Expected: PASS, 4 passed

- [ ] **Шаг 5: Коммит**

```bash
git add backend/app/core/errors.py backend/tests/unit/test_errors.py
git commit -m "feat: единый конверт ошибки и обработчики"
```

---

### Задача 16: Зависимости доступа

**Files:**
- Create: `backend/app/core/deps.py`

- [ ] **Шаг 1: Написать `backend/app/core/deps.py`**

```python
"""Проверка сессии и роли.

Каждый роутер проверяет роль сам — включая маршруты, куда интерфейс не
ведёт. Клиентский гейт в SPA только показывает форму входа вместо пустого
экрана; защита живёт здесь.
"""

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.security import AUTH_COOKIE, verify_session_token
from app.domain.roles import Role, has_rank
from app.features.users.models import User, UserStatus

logger = logging.getLogger(__name__)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: str
    login: str
    name: str
    role: Role


async def get_current_user(
    session: SessionDep,
    app_session: Annotated[str | None, Cookie(alias=AUTH_COOKIE)] = None,
) -> CurrentUser:
    claims = verify_session_token(app_session, settings.app_auth_secret)
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")
    login, issued_at_ms = claims

    user = (
        await session.execute(select(User).where(User.login == login))
    ).scalar_one_or_none()
    if user is None or user.status is not UserStatus.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")

    # Отзыв сессий: подпись у отозванной куки остаётся верной, поэтому
    # проверка обязана быть здесь, а не в проверке подписи.
    #
    # issued_at_ms уже в миллисекундах. Лишнее умножение на 1000 сделало бы
    # условие невыполнимым при любых данных, и отключение учётной записи
    # перестало бы выгонять, продолжая выглядеть сделанным.
    if user.sessions_valid_from is not None:
        valid_from_ms = user.sessions_valid_from.timestamp() * 1000
        if issued_at_ms < valid_from_ms:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия отозвана")

    return CurrentUser(
        id=str(user.id), login=user.login, name=user.name, role=user.role
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_role(minimum: Role):  # noqa: ANN201 — возвращает зависимость FastAPI
    """Фабрика зависимости: не ниже указанной роли."""

    async def dependency(user: CurrentUserDep) -> CurrentUser:
        if not has_rank(user.role, minimum):
            # В журнал аудита не пишем — там мутации данных, а это отказ. Но
            # в серверный лог попасть обязано: иначе о попытках обойти права
            # не узнает никто, а посмотреть их можно только через /logs.
            logger.warning(
                "доступ отклонён: %s (%s) требовалось %s",
                user.login,
                user.role.value,
                minimum.value,
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return dependency
```

Отличие от эталона названо явно: там `requireRole` делал `redirect`, потому
что проверка стояла на странице. Здесь проверка стоит на API, и правильный
ответ — 403; куда вести человека, решает роутер в браузере.

- [ ] **Шаг 2: Проверить типы и границы**

Run: `cd backend && uv run mypy app && uv run --group lint lint-imports --config .importlinter`
Expected: mypy Success; контракты Kept.

- [ ] **Шаг 3: Коммит**

```bash
git add backend/app/core/deps.py
git commit -m "feat: проверка сессии и роли как зависимости FastAPI"
```

---

## Фаза 4. Фичи API

### Задача 17: Обвязка API-тестов

API-тесты дешевле e2e на порядок и проверяют то, чего e2e не видит: коды
ответов, форму ошибки, запись в журнал, отказ по роли. В эталоне этого слоя
не было вовсе — его роль играли Playwright-сценарии.

**Files:**
- Create: `backend/tests/conftest.py`

- [ ] **Шаг 1: Написать `backend/tests/conftest.py`**

```python
"""Фикстуры API-тестов.

Каждый тест идёт в своей транзакции и откатывается: база остаётся чистой,
и порядок тестов ни на что не влияет.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base, engine, get_session
from app.core.security import hash_password
from app.domain.roles import Role
from app.features.users.models import User, UserStatus
from app.main import app


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Сессия внутри внешней транзакции, которая всегда откатывается.

    join_transaction_mode="create_savepoint" позволяет сервисам делать
    commit() по-настоящему: коммитится вложенная точка сохранения, а внешняя
    транзакция остаётся открытой и откатывается в конце теста.
    """
    async with engine.connect() as connection:
        transaction = await connection.begin()
        db = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        yield db
        await db.close()
        await transaction.rollback()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def make_user(session: AsyncSession):
    async def _make(
        login: str = "tester",
        role: Role = Role.admin,
        password: str = "секрет",
        status: UserStatus = UserStatus.active,
    ) -> User:
        user = User(
            login=login,
            name=login.capitalize(),
            role=role,
            password_hash=hash_password(password),
            status=status,
            created_at=datetime.now(UTC),
        )
        session.add(user)
        await session.commit()
        return user

    return _make


@pytest.fixture
async def login_as(client: AsyncClient, make_user):
    """Заводит пользователя и кладёт куку сессии в клиент."""

    async def _login(role: Role = Role.admin, login: str = "tester") -> User:
        user = await make_user(login=login, role=role)
        response = await client.post(
            "/api/auth/login", json={"login": login, "password": "секрет"}
        )
        assert response.status_code == 200, response.text
        return user

    return _login
```

- [ ] **Шаг 2: Коммит**

```bash
git add backend/tests/conftest.py
git commit -m "test: фикстуры API-тестов с откатом транзакции"
```

---

### Задача 18: Служебная фича meta

**Files:**
- Create: `backend/app/features/meta/router.py`
- Create: `backend/tests/api/test_meta.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/api/test_meta.py`:

```python
import pytest


async def test_health_is_open_and_touches_db(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_build_info_is_open(client):
    response = await client.get("/api/meta/build-info")
    assert response.status_code == 200
    assert "commit" in response.json()


async def test_docs_requires_login(client):
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 401


async def test_docs_returns_markdown(client, login_as):
    await login_as()
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 200
    assert response.json()["content"]


@pytest.mark.parametrize(
    "name", ["../../.env", "..%2F..%2F.env", "secrets", "agents/../../.env"]
)
async def test_unknown_document_rejected(client, login_as, name):
    # Имя документа не превращается в путь: список разрешённых задан явно.
    # Иначе первый же ../ отдал бы .env с секретом подписи наружу.
    await login_as()
    response = await client.get(f"/api/meta/docs/{name}")
    assert response.status_code in (404, 400)
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/api/test_meta.py`
Expected: FAIL — приложение ещё не собрано (`app.main` появится в задаче 22),
либо 404 на всех маршрутах.

- [ ] **Шаг 3: Написать `backend/app/features/meta/router.py`**

```python
"""Служебные маршруты: живость, версия сборки, тексты правил для /docs."""

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.deps import CurrentUserDep, SessionDep

router = APIRouter(tags=["meta"])

# Корень репозитория: app/features/meta/router.py → четыре уровня вверх.
REPO_ROOT = Path(__file__).resolve().parents[4]

# Список разрешённых документов задан явно, а имя НЕ превращается в путь.
# Любая склейка вида REPO_ROOT / name отдала бы .env с секретом подписи по
# первому же ../ в запросе.
DOCUMENTS: dict[str, Path] = {
    "agents": REPO_ROOT / "AGENTS.md",
    "checklist": REPO_ROOT / "CHECKLIST.md",
    "onboarding": REPO_ROOT / "docs" / "commands" / "onboarding.md",
    "ship": REPO_ROOT / "docs" / "commands" / "ship.md",
    "status": REPO_ROOT / "docs" / "commands" / "status.md",
    "logs": REPO_ROOT / "docs" / "commands" / "logs.md",
    "rollback": REPO_ROOT / "docs" / "commands" / "rollback.md",
}

DocumentName = Literal[
    "agents", "checklist", "onboarding", "ship", "status", "logs", "rollback"
]


class Health(BaseModel):
    status: Literal["ok"]


class BuildInfo(BaseModel):
    commit: str
    built_at: str


class Document(BaseModel):
    name: str
    content: str


@router.get("/health", response_model=Health)
async def health(session: SessionDep) -> Health:
    """Единственный маршрут без авторизации.

    Ходит в базу намеренно: проверка, которая отвечает 200 при недоступной
    базе, подтверждает только то, что процесс жив, — а доставка на основании
    такой проверки объявляет успешной заведомо нерабочий контур.
    """
    await session.execute(text("SELECT 1"))
    return Health(status="ok")


@router.get("/meta/build-info", response_model=BuildInfo)
async def build_info() -> BuildInfo:
    """Версия доставленного кода. Пишется при сборке, читается с диска."""
    marker = REPO_ROOT / "build-info.json"
    if not marker.exists():
        return BuildInfo(commit="dev", built_at="")
    data = json.loads(marker.read_text(encoding="utf-8"))
    return BuildInfo(commit=data.get("commit", "dev"), built_at=data.get("built_at", ""))


@router.get("/meta/docs/{name}", response_model=Document)
async def document(name: DocumentName, user: CurrentUserDep) -> Document:
    """Отдаёт текст правил или команды. Читает файлы репозитория с диска."""
    path = DOCUMENTS[name]
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return Document(name=name, content=path.read_text(encoding="utf-8"))
```

`DocumentName` как `Literal` даёт две вещи разом: FastAPI сам отвергает
неизвестное имя до входа в обработчик, и это же имя попадает в OpenAPI, а
оттуда — в типы клиента. Опечатка в имени документа на фронтенде станет
ошибкой `tsc`.

- [ ] **Шаг 4: Запустить тест (после задачи 22)**

Run: `cd backend && uv run pytest tests/api/test_meta.py -v`
Expected: PASS, 8 passed

- [ ] **Шаг 5: Коммит**

```bash
git add backend/app/features/meta/router.py backend/tests/api/test_meta.py
git commit -m "feat: служебные маршруты health, build-info и документы"
```

---

### Задача 19: Вход

**Files:**
- Create: `backend/app/features/auth/schemas.py`
- Create: `backend/app/features/auth/service.py`
- Create: `backend/app/features/auth/router.py`
- Create: `backend/tests/api/test_auth.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/api/test_auth.py`:

```python
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import AUTH_COOKIE
from app.domain.roles import Role
from app.features.users.models import User, UserStatus


async def test_login_sets_cookie(client, make_user):
    await make_user(login="ivan")
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "секрет"}
    )
    assert response.status_code == 200
    assert AUTH_COOKIE in response.cookies


async def test_cookie_is_httponly_and_samesite(client, make_user):
    await make_user(login="ivan")
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "секрет"}
    )
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=Lax" in header


async def test_wrong_password_rejected(client, make_user):
    await make_user(login="ivan")
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "мимо"}
    )
    assert response.status_code == 400
    assert AUTH_COOKIE not in response.cookies


async def test_unknown_login_gives_same_message_as_wrong_password(client, make_user):
    await make_user(login="ivan")
    wrong = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "мимо"}
    )
    missing = await client.post(
        "/api/auth/login", json={"login": "неттакого", "password": "мимо"}
    )
    # Разные тексты подсказали бы, какие логины существуют.
    assert wrong.json()["error"] == missing.json()["error"]


async def test_disabled_user_cannot_login(client, make_user):
    await make_user(login="ivan", status=UserStatus.disabled)
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "секрет"}
    )
    assert response.status_code == 400


async def test_me_returns_current_user(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    response = await client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["login"] == "ivan"
    assert body["role"] == "editor"


async def test_me_without_cookie_is_401(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_logout_clears_cookie(client, login_as):
    await login_as()
    response = await client.post("/api/auth/logout")
    assert response.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_records_last_login(client, session, make_user):
    await make_user(login="ivan")
    await client.post("/api/auth/login", json={"login": "ivan", "password": "секрет"})
    user = (
        await session.execute(select(User).where(User.login == "ivan"))
    ).scalar_one()
    assert user.last_login_at is not None


async def test_revoked_session_stops_working(client, session, login_as):
    user = await login_as(login="ivan")
    assert (await client.get("/api/auth/me")).status_code == 200
    # Отзыв: подпись куки остаётся верной, поэтому проверка обязана быть на
    # стороне сервера, а не в разборе токена.
    user.sessions_valid_from = datetime.now(UTC)
    await session.commit()
    assert (await client.get("/api/auth/me")).status_code == 401
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/api/test_auth.py`
Expected: FAIL — маршрутов `/api/auth/*` ещё нет.

- [ ] **Шаг 3: Написать `backend/app/features/auth/schemas.py`**

```python
from pydantic import BaseModel, Field

from app.domain.roles import Role


class LoginRequest(BaseModel):
    # Логин без пробельных символов: перевод строки внутри сломал бы разбор
    # токена, и такой пользователь молча не смог бы войти.
    login: str = Field(min_length=1, max_length=255, pattern=r"^\S+$")
    password: str = Field(min_length=1, max_length=1024)


class CurrentUserResponse(BaseModel):
    id: str
    login: str
    name: str
    role: Role


class OkResponse(BaseModel):
    ok: bool = True
```

- [ ] **Шаг 4: Написать `backend/app/features/auth/service.py`**

```python
"""Правила входа."""

import asyncio
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import RuleViolation
from app.core.rate_limit import login_limiter
from app.core.security import hash_password, sign_session_token, verify_password
from app.domain.roles import Role
from app.features.users.models import User, UserStatus

# Один и тот же текст на любой отказ: разные сообщения подсказывают, какие
# логины существуют.
DENIED = "Неверный логин или пароль"
TOO_MANY = "Слишком много попыток. Попробуй через 15 минут"
# Нижняя граница времени ответа. Без неё отказ по несуществующему логину
# возвращается заметно быстрее, чем по неверному паролю: scrypt считается
# только во втором случае, и по времени ответа логины перебираются.
MIN_RESPONSE_SECONDS = 0.25


async def authenticate(
    session: AsyncSession, login: str, password: str, client_ip: str
) -> str:
    """Проверяет пару и возвращает токен сессии. Отказ — RuleViolation."""
    started = time.monotonic()

    async def finish() -> None:
        remaining = MIN_RESPONSE_SECONDS - (time.monotonic() - started)
        if remaining > 0:
            await asyncio.sleep(remaining)

    if not login_limiter.check(login) or not login_limiter.check(client_ip):
        await finish()
        raise RuleViolation(TOO_MANY)

    user = (
        await session.execute(select(User).where(User.login == login))
    ).scalar_one_or_none()

    ok = (
        user is not None
        and user.status is UserStatus.active
        and user.password_hash is not None
        and verify_password(password, user.password_hash)
    )
    if not ok or user is None:
        login_limiter.register_failure(login)
        login_limiter.register_failure(client_ip)
        await finish()
        raise RuleViolation(DENIED)

    login_limiter.reset(login)
    login_limiter.reset(client_ip)
    issued_at_ms = int(datetime.now(UTC).timestamp() * 1000)
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await finish()
    return sign_session_token(user.login, issued_at_ms, settings.app_auth_secret)


async def ensure_bootstrap_user(session: AsyncSession) -> None:
    """Заводит первую учётную запись, если таблица пуста.

    Пара по умолчанию admin / admin известна всем, у кого есть шаблон,
    поэтому на боевом контуре под ней не работают: заводят свою запись и
    отключают эту. Условие выключения выражено свойством
    `settings.bootstrap_enabled`, а не проверкой по месту: инвариант должен
    жить в одном месте, иначе его однажды выразят по-своему.
    """
    if not settings.bootstrap_enabled:
        return
    existing = (await session.execute(select(User.id).limit(1))).first()
    if existing is not None:
        return
    session.add(
        User(
            login=settings.app_bootstrap_login,
            name=settings.app_bootstrap_name,
            role=Role.admin,
            password_hash=hash_password(settings.app_bootstrap_password),
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
```

- [ ] **Шаг 5: Написать `backend/app/features/auth/router.py`**

```python
from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.core.deps import CurrentUserDep, SessionDep
from app.core.security import AUTH_COOKIE
from app.features.auth import service
from app.features.auth.schemas import CurrentUserResponse, LoginRequest, OkResponse

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_MAX_AGE = 7 * 24 * 60 * 60


def _client_ip(request: Request) -> str:
    """Адрес сокета из X-Real-IP, который ставит nginx.

    Не X-Forwarded-For: там цепочка, и первый сегмент прислал клиент —
    ограничение по такому адресу обходится одним заголовком.
    """
    return request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "unknown"
    )


@router.post("/login", response_model=OkResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> OkResponse:
    token = await service.authenticate(
        session, payload.login, payload.password, _client_ip(request)
    )
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        # Lax, а не Strict: при Strict кука не уезжает при переходе по
        # ссылке из письма или мессенджера, и человек видит форму входа,
        # хотя вошёл минуту назад.
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return OkResponse()


@router.post("/logout", response_model=OkResponse)
async def logout(response: Response) -> OkResponse:
    response.delete_cookie(AUTH_COOKIE, path="/")
    return OkResponse()


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id, login=user.login, name=user.name, role=user.role
    )
```

- [ ] **Шаг 6: Запустить тест (после задачи 22)**

Run: `cd backend && uv run pytest tests/api/test_auth.py -v`
Expected: PASS, 10 passed

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/features/auth/ backend/tests/api/test_auth.py
git commit -m "feat: вход, выход и текущий пользователь"
```

---

### Задача 20: Пользователи

**Files:**
- Create: `backend/app/features/users/schemas.py`
- Create: `backend/app/features/users/service.py`
- Create: `backend/app/features/users/router.py`
- Create: `backend/tests/api/test_users.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/api/test_users.py`:

```python
from sqlalchemy import select

from app.core.audit import AuditLog
from app.domain.roles import Role
from app.features.users.models import User, UserStatus


async def test_list_requires_admin(client, login_as):
    await login_as(role=Role.editor)
    assert (await client.get("/api/users")).status_code == 403


async def test_admin_sees_list(client, login_as):
    await login_as(role=Role.admin, login="boss")
    response = await client.get("/api/users")
    assert response.status_code == 200
    assert [u["login"] for u in response.json()] == ["boss"]


async def test_create_user(client, session, login_as):
    await login_as(role=Role.admin, login="boss")
    response = await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "editor",
            "password": "длинныйпароль",
        },
    )
    assert response.status_code == 201
    created = (
        await session.execute(select(User).where(User.login == "ivan"))
    ).scalar_one()
    assert created.role is Role.editor


async def test_create_writes_audit_in_same_transaction(client, session, login_as):
    await login_as(role=Role.admin, login="boss")
    await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "viewer",
            "password": "длинныйпароль",
        },
    )
    entries = (await session.execute(select(AuditLog))).scalars().all()
    assert [(e.actor, e.action, e.entity) for e in entries] == [
        ("boss", "create", "User")
    ]


async def test_duplicate_login_rejected_with_message(client, login_as):
    await login_as(role=Role.admin, login="boss")
    body = {
        "login": "ivan",
        "name": "Иван",
        "role": "viewer",
        "password": "длинныйпароль",
    }
    assert (await client.post("/api/users", json=body)).status_code == 201
    second = await client.post("/api/users", json=body)
    # Не 500 от нарушения уникальности: это ожидаемая ошибка формы.
    assert second.status_code == 400
    assert second.json()["field"] == "login"


async def test_short_password_rejected(client, login_as):
    await login_as(role=Role.admin, login="boss")
    response = await client.post(
        "/api/users",
        json={"login": "ivan", "name": "Иван", "role": "viewer", "password": "123"},
    )
    assert response.status_code == 400
    assert response.json()["field"] == "password"


async def test_disable_revokes_sessions(client, session, login_as, make_user):
    await login_as(role=Role.admin, login="boss")
    victim = await make_user(login="ivan", role=Role.viewer)
    response = await client.patch(
        f"/api/users/{victim.id}", json={"status": "disabled"}
    )
    assert response.status_code == 200
    await session.refresh(victim)
    assert victim.status is UserStatus.disabled
    # Отключение обязано отзывать уже выданные сессии: иначе человек
    # продолжает работать до истечения куки.
    assert victim.sessions_valid_from is not None


async def test_change_role(client, session, login_as, make_user):
    await login_as(role=Role.admin, login="boss")
    target = await make_user(login="ivan", role=Role.viewer)
    response = await client.patch(f"/api/users/{target.id}", json={"role": "editor"})
    assert response.status_code == 200
    await session.refresh(target)
    assert target.role is Role.editor


async def test_cannot_disable_self(client, login_as):
    # Отключив себя, администратор запирает контур: войти, чтобы включить
    # обратно, будет некому.
    me = await login_as(role=Role.admin, login="boss")
    response = await client.patch(f"/api/users/{me.id}", json={"status": "disabled"})
    assert response.status_code == 400


async def test_unknown_user_is_404(client, login_as):
    await login_as(role=Role.admin)
    missing = "01a05000-0000-7000-8000-000000000000"
    assert (await client.patch(f"/api/users/{missing}", json={"role": "admin"})).status_code == 404
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/api/test_users.py`
Expected: FAIL — маршрутов `/api/users` ещё нет.

- [ ] **Шаг 3: Написать `backend/app/features/users/schemas.py`**

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.roles import Role
from app.features.users.models import UserStatus

# Восемь символов — не про стойкость, а про то, чтобы не заводили «123».
# Настоящую защиту даёт ограничение попыток входа.
MIN_PASSWORD_LENGTH = 8


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    login: str
    name: str
    role: Role
    status: UserStatus
    last_login_at: datetime | None
    created_at: datetime


class CreateUserRequest(BaseModel):
    login: str = Field(min_length=1, max_length=255, pattern=r"^\S+$")
    name: str = Field(min_length=1, max_length=255)
    role: Role
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)


class UpdateUserRequest(BaseModel):
    """Частичное обновление: приходит только то, что меняют."""

    role: Role | None = None
    status: UserStatus | None = None
```

- [ ] **Шаг 4: Написать `backend/app/features/users/service.py`**

```python
"""Правила работы с учётными записями."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import RuleViolation
from app.core.security import hash_password
from app.features.users.models import User, UserStatus
from app.features.users.schemas import CreateUserRequest, UpdateUserRequest


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def create_user(
    session: AsyncSession, payload: CreateUserRequest, actor: str
) -> User:
    taken = (
        await session.execute(select(User.id).where(User.login == payload.login))
    ).first()
    if taken is not None:
        # Проверка до вставки, а не обработка IntegrityError: до базы
        # доходит понятное сообщение с именем поля, а не текст драйвера.
        raise RuleViolation("Такой логин уже занят", field="login")

    user = User(
        login=payload.login,
        name=payload.name,
        role=payload.role,
        password_hash=hash_password(payload.password),
        created_at=datetime.now(UTC),
    )
    session.add(user)
    # flush, а не commit: нужен id для записи в журнал, но транзакция
    # обязана остаться одной на мутацию вместе с аудитом.
    await session.flush()
    write_audit(session, actor, "create", "User", str(user.id), payload.role.value)
    await session.commit()
    return user


async def update_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    actor_id: str,
    actor_login: str,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise LookupError("Учётная запись не найдена")

    changes: list[str] = []
    if payload.role is not None and payload.role is not user.role:
        user.role = payload.role
        changes.append(f"роль → {payload.role.value}")

    if payload.status is not None and payload.status is not user.status:
        if payload.status is UserStatus.disabled and str(user.id) == actor_id:
            # Отключив себя, администратор запирает контур: включить обратно
            # будет некому.
            raise RuleViolation("Нельзя отключить собственную запись", field="status")
        user.status = payload.status
        changes.append(f"статус → {payload.status.value}")
        if payload.status is UserStatus.disabled:
            # Отключение обязано отзывать уже выданные сессии: подпись куки
            # остаётся верной, и без отзыва человек работает дальше.
            user.sessions_valid_from = datetime.now(UTC)

    if not changes:
        raise RuleViolation("Менять нечего")

    write_audit(session, actor_login, "update", "User", str(user.id), ", ".join(changes))
    await session.commit()
    return user
```

- [ ] **Шаг 5: Написать `backend/app/features/users/router.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.users import service
from app.features.users.schemas import CreateUserRequest, UpdateUserRequest, UserOut

router = APIRouter(prefix="/users", tags=["users"])

AdminDep = Depends(require_role(Role.admin))


@router.get("", response_model=list[UserOut])
async def list_users(
    session: SessionDep, _: CurrentUser = AdminDep
) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await service.list_users(session)]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest, session: SessionDep, actor: CurrentUser = AdminDep
) -> UserOut:
    return UserOut.model_validate(
        await service.create_user(session, payload, actor.login)
    )


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    session: SessionDep,
    actor: CurrentUser = AdminDep,
) -> UserOut:
    try:
        user = await service.update_user(
            session, user_id, payload, actor.id, actor.login
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return UserOut.model_validate(user)
```

`UserOut.model_validate` требует, чтобы `id` был строкой, а в модели он
`uuid.UUID`. Pydantic приводит его сам благодаря `from_attributes=True` и
аннотации `id: str`.

- [ ] **Шаг 6: Запустить тест (после задачи 22)**

Run: `cd backend && uv run pytest tests/api/test_users.py -v`
Expected: PASS, 10 passed

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/features/users/ backend/tests/api/test_users.py
git commit -m "feat: список, создание и изменение учётных записей"
```

---

### Задача 21: Расходы — образцовая фича

Показывает все паттерны разом: проверку роли, разбор денег и дат через
домен, предел суммы, аудит в одной транзакции, чистый расчёт сводки.

**Files:**
- Create: `backend/app/features/expenses/schemas.py`
- Create: `backend/app/features/expenses/service.py`
- Create: `backend/app/features/expenses/router.py`
- Create: `backend/tests/api/test_expenses.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/api/test_expenses.py`:

```python
from sqlalchemy import select

from app.core.audit import AuditLog
from app.domain.expenses import CATEGORIES
from app.domain.money import MAX_AMOUNT_MINOR
from app.domain.roles import Role
from app.features.expenses.schemas import Category

VALID = {
    "date": "2026-08-31",
    "title": "Подписка на редактор",
    "category": "Софт",
    "amount": "1 200,50",
}


def test_schema_categories_match_domain():
    # Схема перечисляет категории литералами, чтобы не терять типизацию под
    # mypy, а домен держит их кортежем. Два списка обязаны совпадать — иначе
    # схема начнёт отвергать категорию, которую домен считает допустимой,
    # и разойдутся они молча.
    from typing import get_args

    assert get_args(Category) == CATEGORIES


async def test_viewer_can_read(client, login_as):
    await login_as(role=Role.viewer)
    assert (await client.get("/api/expenses")).status_code == 200


async def test_viewer_cannot_create(client, login_as):
    await login_as(role=Role.viewer)
    assert (await client.post("/api/expenses", json=VALID)).status_code == 403


async def test_editor_creates(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/expenses", json=VALID)
    assert response.status_code == 201
    body = response.json()
    assert body["amount_minor"] == 120050
    assert body["category"] == "Софт"


async def test_create_writes_audit(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/expenses", json=VALID)
    entries = (await session.execute(select(AuditLog))).scalars().all()
    assert [(e.actor, e.action, e.entity) for e in entries] == [
        ("ivan", "create", "Expense")
    ]


async def test_impossible_date_rejected(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post("/api/expenses", json={**VALID, "date": "2026-02-31"})
    assert response.status_code == 400
    assert response.json()["field"] == "date"
    # Введённое эхом в тексте: поле type="date" не умеет показать невалидную
    # строку, и без эха человек видит пустое поле и сообщение без пояснения.
    assert "2026-02-31" in response.json()["error"]


async def test_unparseable_amount_rejected(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post("/api/expenses", json={**VALID, "amount": "много"})
    assert response.status_code == 400
    assert response.json()["field"] == "amount"


async def test_zero_amount_rejected(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post("/api/expenses", json={**VALID, "amount": "0"})
    assert response.status_code == 400


async def test_amount_over_int4_rejected_with_readable_message(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post(
        "/api/expenses", json={**VALID, "amount": str(MAX_AMOUNT_MINOR // 100 + 1)}
    )
    assert response.status_code == 400
    # Без этой проверки сумма прошла бы разбор и упала в базе ошибкой
    # драйвера, которую специалисту читать нечем.
    assert "предельной" in response.json()["error"]


async def test_unknown_category_rejected(client, login_as):
    await login_as(role=Role.editor)
    response = await client.post("/api/expenses", json={**VALID, "category": "Ремонт"})
    assert response.status_code == 400


async def test_delete_requires_editor(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    created = (await client.post("/api/expenses", json=VALID)).json()
    assert (await client.delete(f"/api/expenses/{created['id']}")).status_code == 200


async def test_summary_returns_shares(client, login_as):
    await login_as(role=Role.editor)
    await client.post("/api/expenses", json={**VALID, "amount": "750"})
    await client.post(
        "/api/expenses", json={**VALID, "category": "Аренда", "amount": "250"}
    )
    response = await client.get("/api/expenses/summary")
    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["category"] == "Софт"
    assert rows[0]["share"] == 0.75
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/api/test_expenses.py`
Expected: FAIL — маршрутов `/api/expenses` ещё нет.

- [ ] **Шаг 3: Написать `backend/app/features/expenses/schemas.py`**

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Категории перечислены здесь литералами намеренно. Literal[CATEGORIES] из
# переменной в рантайме работает, но mypy такой формы не принимает, и под
# type: ignore тип схлопывается в Any — то есть проверка, ради которой
# Literal и нужен, перестаёт существовать.
#
# Расхождение с app/domain/expenses.py ловит тест
# test_schema_categories_match_domain: это дешевле, чем потерять типизацию.
Category = Literal["Аренда", "Софт", "Оборудование", "Услуги", "Прочее"]


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: datetime
    title: str
    # Сырые копейки: показ форматирует клиент, сортировка и графики требуют
    # числа. Готовая строка сюда не кладётся намеренно.
    amount_minor: int
    category: str
    created_at: datetime


class CreateExpenseRequest(BaseModel):
    # Дата и сумма приходят строками и разбираются доменом: разбор — правило
    # предметной области, и он обязан быть авторитетным на сервере.
    date: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=255)
    category: Category
    amount: str = Field(min_length=1)


class CategoryTotalOut(BaseModel):
    category: str
    total_minor: int
    share: float
```

- [ ] **Шаг 4: Написать `backend/app/features/expenses/service.py`**

```python
"""Правила работы с расходами. ОБРАЗЕЦ."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import RuleViolation
from app.domain.dates import parse_date_input_value
from app.domain.expenses import CategoryTotal, totals_by_category
from app.domain.money import MAX_AMOUNT_MINOR, format_money, parse_money_to_minor
from app.features.expenses.models import Expense
from app.features.expenses.schemas import CreateExpenseRequest


async def list_expenses(session: AsyncSession) -> list[Expense]:
    result = await session.execute(select(Expense).order_by(Expense.date.desc()))
    return list(result.scalars().all())


async def summary(session: AsyncSession) -> list[CategoryTotal]:
    result = await session.execute(select(Expense.category, Expense.amount_minor))
    return totals_by_category([(row[0], row[1]) for row in result.all()])


async def create_expense(
    session: AsyncSession, payload: CreateExpenseRequest, actor: str
) -> Expense:
    date = parse_date_input_value(payload.date)
    if date is None:
        # Введённое эхом в тексте ошибки: поле type="date" не умеет показать
        # невалидную строку — браузер отдаёт пустое значение, и человек видит
        # пустое поле с сообщением, которому нечего пояснять.
        raise RuleViolation(f"Дата «{payload.date}» не похожа на дату", field="date")

    amount_minor = parse_money_to_minor(payload.amount)
    if amount_minor is None:
        raise RuleViolation("Сумма не похожа на число", field="amount")
    if amount_minor <= 0:
        raise RuleViolation("Сумма должна быть больше нуля", field="amount")
    if amount_minor > MAX_AMOUNT_MINOR:
        raise RuleViolation(
            f"Сумма больше предельной ({format_money(MAX_AMOUNT_MINOR)})",
            field="amount",
        )

    expense = Expense(
        date=date,
        title=payload.title.strip(),
        category=payload.category,
        amount_minor=amount_minor,
        created_at=datetime.now(UTC),
    )
    session.add(expense)
    await session.flush()
    write_audit(
        session,
        actor,
        "create",
        "Expense",
        str(expense.id),
        f"{expense.category}, {expense.amount_minor} коп.",
    )
    await session.commit()
    return expense


async def delete_expense(
    session: AsyncSession, expense_id: uuid.UUID, actor: str
) -> None:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise LookupError("Расход не найден")
    write_audit(
        session, actor, "delete", "Expense", str(expense.id), expense.title
    )
    await session.delete(expense)
    await session.commit()
```

- [ ] **Шаг 5: Написать `backend/app/features/expenses/router.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.expenses import service
from app.features.expenses.schemas import (
    CategoryTotalOut,
    CreateExpenseRequest,
    ExpenseOut,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])

ViewerDep = Depends(require_role(Role.viewer))
EditorDep = Depends(require_role(Role.editor))


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    session: SessionDep, _: CurrentUser = ViewerDep
) -> list[ExpenseOut]:
    return [ExpenseOut.model_validate(e) for e in await service.list_expenses(session)]


@router.get("/summary", response_model=list[CategoryTotalOut])
async def summary(
    session: SessionDep, _: CurrentUser = ViewerDep
) -> list[CategoryTotalOut]:
    return [
        CategoryTotalOut(
            category=t.category, total_minor=t.total_minor, share=t.share
        )
        for t in await service.summary(session)
    ]


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: CreateExpenseRequest, session: SessionDep, actor: CurrentUser = EditorDep
) -> ExpenseOut:
    return ExpenseOut.model_validate(
        await service.create_expense(session, payload, actor.login)
    )


@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: uuid.UUID, session: SessionDep, actor: CurrentUser = EditorDep
) -> dict[str, bool]:
    try:
        await service.delete_expense(session, expense_id, actor.login)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"ok": True}
```

Маршрут `/summary` объявлен **до** `/{expense_id}`: иначе FastAPI сопоставит
слово «summary» с параметром пути и попробует разобрать его как UUID.

- [ ] **Шаг 6: Запустить тест (после задачи 22)**

Run: `cd backend && uv run pytest tests/api/test_expenses.py -v`
Expected: PASS, 12 passed

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/features/expenses/ backend/tests/api/test_expenses.py
git commit -m "feat: образцовая фича расходов"
```

---

### Задача 22: Журнал аудита и сборка приложения

**Files:**
- Create: `backend/app/features/audit/router.py`
- Create: `backend/app/core/static.py`
- Create: `backend/app/main.py`
- Create: `backend/app/openapi.py`
- Create: `backend/tests/api/test_audit.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/api/test_audit.py`:

```python
from app.domain.roles import Role

EXPENSE = {
    "date": "2026-08-31",
    "title": "Подписка",
    "category": "Софт",
    "amount": "100",
}


async def test_audit_requires_admin(client, login_as):
    await login_as(role=Role.editor)
    assert (await client.get("/api/audit")).status_code == 403


async def test_admin_reads_journal(client, login_as):
    await login_as(role=Role.admin, login="boss")
    await client.post("/api/expenses", json=EXPENSE)
    response = await client.get("/api/audit")
    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["actor"] == "boss"
    assert rows[0]["action"] == "create"


async def test_newest_first(client, login_as):
    await login_as(role=Role.admin, login="boss")
    await client.post("/api/expenses", json={**EXPENSE, "title": "Первый"})
    await client.post("/api/expenses", json={**EXPENSE, "title": "Второй"})
    rows = (await client.get("/api/audit")).json()
    assert len(rows) == 2
    assert rows[0]["ts"] >= rows[1]["ts"]
```

- [ ] **Шаг 2: Написать `backend/app/features/audit/router.py`**

```python
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.audit import AuditLog
from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ts: datetime
    actor: str
    action: str
    entity: str
    entity_id: str
    detail: str


@router.get("", response_model=list[AuditEntryOut])
async def list_entries(
    session: SessionDep,
    # Верхняя граница жёсткая: журнал растёт неограниченно, и запрос без
    # предела однажды выгрузит в память всю историю контура.
    limit: int = Query(default=200, ge=1, le=1000),
    _: CurrentUser = Depends(require_role(Role.admin)),
) -> list[AuditEntryOut]:
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)
    )
    return [AuditEntryOut.model_validate(e) for e in result.scalars().all()]
```

- [ ] **Шаг 3: Написать `backend/app/core/static.py`**

```python
"""Раздача собранного фронтенда.

FastAPI отдаёт и API, и статику: так vhost остаётся чистым proxy_pass, и
общий app-provision, которым пользуется и TS-шаблон, не требует правок.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def mount_frontend(app: FastAPI) -> None:
    if not DIST.exists():
        # В разработке фронтенд поднимает Vite на своём порту, сборки нет.
        return

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(request: Request, path: str) -> FileResponse:
        # Маршруты SPA не существуют на диске: любой неизвестный путь отдаёт
        # index.html, и дальше решает роутер в браузере.
        #
        # /api сюда не попадает: роутеры примонтированы раньше, и FastAPI
        # выбирает первое совпадение. Но если запрос всё же дошёл — это
        # несуществующий маршрут API, и отдавать на него HTML нельзя:
        # клиент ждёт JSON и покажет «неожиданный ответ» вместо 404.
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Маршрут не найден")
        return FileResponse(DIST / "index.html")
```

- [ ] **Шаг 4: Написать `backend/app/main.py`**

```python
"""Сборка приложения."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import SessionFactory
from app.core.errors import register_error_handlers
from app.core.static import mount_frontend
from app.features.audit.router import router as audit_router
from app.features.auth.router import router as auth_router
from app.features.auth.service import ensure_bootstrap_user
from app.features.expenses.router import router as expenses_router
from app.features.meta.router import router as meta_router
from app.features.users.router import router as users_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with SessionFactory() as session:
        await ensure_bootstrap_user(session)
    yield


app = FastAPI(
    title="apptemplate",
    lifespan=lifespan,
    # Схема нужна для генерации типов клиента; интерактивные страницы
    # FastAPI выключены — на контуре они висели бы открытым описанием API.
    docs_url=None,
    redoc_url=None,
)

register_error_handlers(app)

for router in (
    meta_router,
    auth_router,
    users_router,
    expenses_router,
    audit_router,
):
    app.include_router(router, prefix="/api")

# Монтируется последним: перехватчик /{path:path} обязан стоять после всех
# маршрутов API, иначе он поглотит их.
mount_frontend(app)
```

- [ ] **Шаг 5: Написать `backend/app/openapi.py`**

```python
"""Печать схемы OpenAPI. Из неё генерируются типы клиента.

Запуск: uv run python -m app.openapi > openapi.json
"""

import json

from app.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
```

- [ ] **Шаг 6: Прогнать все тесты бэкенда**

Run: `cd backend && uv run pytest -v`
Expected: PASS — все тесты фаз 1–4 зелёные (около 80).

- [ ] **Шаг 7: Добавить последний контракт границ**

Все `router.py` теперь существуют. Дописать в `backend/.importlinter`:

```ini
[importlinter:contract:router-goes-through-service]
name = router не ходит в модели мимо service
type = forbidden
source_modules =
    app.features.auth.router
    app.features.users.router
    app.features.expenses.router
forbidden_modules =
    app.features.users.models
    app.features.expenses.models
```

- [ ] **Шаг 8: Проверить границы модулей**

Run: `cd backend && uv run --group lint lint-imports --config .importlinter`
Expected: `Contracts: 3 kept, 0 broken.`

Если третий контракт сразу broken — это не повод его ослабить. Значит роутер
и правда лезет в модели мимо сервиса, и чинить надо роутер.

- [ ] **Шаг 9: Поднять приложение руками**

```bash
cd backend && uv run uvicorn app.main:app --port 8000
curl -s http://127.0.0.1:8000/api/health
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'content-type: application/json' \
  -d '{"login":"admin","password":"admin"}' -i | head -20
```

Expected: `{"status":"ok"}`; вход отвечает 200 и ставит куку `app_session`.

- [ ] **Шаг 10: Коммит**

```bash
git add backend/app/features/audit/ backend/app/core/static.py \
        backend/app/main.py backend/app/openapi.py backend/.importlinter \
        backend/tests/api/test_audit.py
git commit -m "feat: журнал аудита, раздача статики и сборка приложения"
```

---

## Фаза 5. Фронтенд

### Задача 23: Каркас SPA

**Files:**
- Create: `frontend/` (через `npm create vite`)
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/tsconfig.json`, `frontend/tsconfig.app.json`
- Create: `frontend/src/index.css`
- Create: `frontend/components.json`

- [ ] **Шаг 1: Развернуть проект Vite**

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install @tailwindcss/vite tailwindcss
npm install -D @types/node
```

- [ ] **Шаг 2: Написать `frontend/vite.config.ts`**

```typescript
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    // В разработке фронтенд и бэкенд живут на разных портах. Прокси делает
    // их одним источником для браузера: иначе кука сессии не уезжает с
    // запросом, и вход «работает», но следующий же вызов отвечает 401.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    // Сюда смотрит app/core/static.py.
    outDir: "dist",
  },
})
```

- [ ] **Шаг 3: Добавить псевдоним пути в `frontend/tsconfig.app.json`**

В секцию `compilerOptions` дописать:

```json
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
```

- [ ] **Шаг 4: Написать `frontend/src/index.css`**

```css
@import "tailwindcss";
@import "tw-animate-css";

@custom-variant dark (&:is(.dark *));

/* theme:start — блок ниже пишет `npm run theme`, руками не редактируется */
:root {
  --radius: 0.625rem;
  --background: oklch(1 0 0);
  --foreground: oklch(0.141 0.005 285.823);
}
/* theme:end */

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

Полный блок токенов появится в задаче 25 — его пишет команда применения
темы, а не рука. Здесь достаточно маркеров, между которыми она пишет.

- [ ] **Шаг 5: Поставить shadcn/ui**

```bash
cd frontend && npx shadcn@latest init
```

Ответы: стиль `base-vega`, базовый цвет `neutral`, CSS-переменные — да.
После инициализации открыть `frontend/components.json` и убедиться, что
стоит `"rsc": false` — серверных компонентов здесь нет, и с `true` CLI
дописывал бы `"use client"` в каждый компонент.

- [ ] **Шаг 6: Поставить компоненты, которые нужны экранам**

```bash
cd frontend && npx shadcn@latest add alert avatar badge button card chart \
  checkbox dialog dropdown-menu input label progress radio-group select \
  separator skeleton switch table tabs textarea tooltip
```

- [ ] **Шаг 7: Проверить, что проект собирается**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: сборка проходит, появляется `frontend/dist/`.

- [ ] **Шаг 8: Коммит**

```bash
git add frontend/
git commit -m "chore: каркас SPA на Vite с Tailwind и shadcn/ui"
```

---

### Задача 24: Клиент API

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/schema.d.ts` (генерируется)
- Modify: `frontend/package.json`

- [ ] **Шаг 1: Поставить зависимости**

```bash
cd frontend && npm install openapi-fetch @tanstack/react-query
npm install -D openapi-typescript vitest
```

- [ ] **Шаг 2: Добавить скрипты в `frontend/package.json`**

В секцию `scripts` дописать:

```json
    "test": "vitest run",
    "theme": "tsx scripts/apply-theme.ts"
```

и поставить `tsx`: `npm install -D tsx`.

- [ ] **Шаг 3: Сгенерировать типы из схемы**

Бэкенд должен быть остановлен — схема печатается без запуска сервера:

```bash
make openapi
```

Expected: появляется `frontend/src/api/schema.d.ts` с типами всех маршрутов.

- [ ] **Шаг 4: Написать `frontend/src/api/client.ts`**

```typescript
import createClient from "openapi-fetch"
import type { paths } from "./schema"

/**
 * Единственный способ сходить в API. Пути, параметры и форма ответа
 * проверяются компилятором по сгенерированной схеме: маршрут, которого нет,
 * не соберётся.
 */
export const api = createClient<paths>({
  baseUrl: "/",
  // Без этого кука сессии не уезжает с запросом, и всё, кроме входа,
  // отвечает 401 при формально успешном входе.
  credentials: "include",
})

/** Ошибка, разобранная из единого конверта бэкенда. */
export interface ApiError {
  message: string
  field?: string
}

export function toApiError(error: unknown): ApiError {
  if (
    typeof error === "object" &&
    error !== null &&
    "error" in error &&
    typeof (error as { error: unknown }).error === "string"
  ) {
    const envelope = error as { error: string; field?: string | null }
    return { message: envelope.error, field: envelope.field ?? undefined }
  }
  // Сюда попадает только то, что бэкенд не оформил конвертом: обрыв связи,
  // ответ прокси, падение до обработчиков.
  return { message: "Сервер недоступен" }
}
```

- [ ] **Шаг 5: Проверить типы**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Шаг 6: Коммит**

```bash
git add frontend/src/api/ frontend/package.json frontend/package-lock.json
git commit -m "feat: типизированный клиент API из схемы OpenAPI"
```

---

### Задача 25: Темы оформления

Модуль тем в эталоне не зависит ни от React, ни от Next: это чистые функции
и данные. Переносится почти дословно.

**Files:**
- Create: `frontend/src/lib/design/themes.ts`
- Create: `frontend/src/lib/design/css.ts`
- Create: `frontend/src/lib/design/apply.ts`
- Create: `frontend/src/lib/design/themes.test.ts`
- Create: `frontend/src/lib/design/css.test.ts`
- Create: `frontend/src/lib/design/apply.test.ts`
- Create: `frontend/scripts/apply-theme.ts`
- Create: `frontend/vitest.config.ts`

- [ ] **Шаг 1: Скопировать модуль тем и его тесты**

```bash
SRC=/Users/minas/projects/app-template
mkdir -p frontend/src/lib/design frontend/scripts
cp $SRC/lib/design/{themes,css,apply}.ts frontend/src/lib/design/
cp $SRC/lib/design/{themes,css,apply}.test.ts frontend/src/lib/design/
cp $SRC/scripts/apply-theme.ts frontend/scripts/
```

Файлы `lib/design/*.ts` не содержат импортов React, Next или Prisma —
переносятся без правок.

- [ ] **Шаг 2: Поправить путь к CSS в `frontend/scripts/apply-theme.ts`**

Заменить строку с `GLOBALS`:

```typescript
// Резолвится от расположения самого скрипта, а не от текущего каталога:
// запуск не из корня иначе давал бы сырой ENOENT вместо внятного отказа.
const GLOBALS = fileURLToPath(new URL("../src/index.css", import.meta.url))
```

и импорты — на `../src/lib/design/...`:

```typescript
import { replaceThemeBlock } from "../src/lib/design/apply"
import { buildThemeCss } from "../src/lib/design/css"
import { THEMES, findTheme } from "../src/lib/design/themes"
```

- [ ] **Шаг 3: Написать `frontend/vitest.config.ts`**

```typescript
import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  test: {
    environment: "node",
    // Тесты только на чистую логику. Unit-тесты на React-компоненты
    // запрещены правилами проекта — их роль выполняет e2e.
    include: ["src/lib/**/*.test.ts"],
  },
})
```

- [ ] **Шаг 4: Прогнать тесты и применить тему по умолчанию**

```bash
cd frontend && npm run test && npm run theme -- blue
```

Expected: тесты зелёные; в `src/index.css` между маркерами появляется полный
набор токенов синей темы.

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/src/lib/design/ frontend/scripts/ frontend/vitest.config.ts frontend/src/index.css
git commit -m "feat: пять тем оформления и команда их применения"
```

---

### Задача 26: Роутер, гейт и оболочка

**Files:**
- Create: `frontend/src/lib/auth.ts`
- Create: `frontend/src/components/page-main.tsx`
- Create: `frontend/src/components/site-nav.tsx`
- Create: `frontend/src/router.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Шаг 1: Поставить роутер**

```bash
cd frontend && npm install @tanstack/react-router
```

- [ ] **Шаг 2: Написать `frontend/src/lib/auth.ts`**

```typescript
import { queryOptions } from "@tanstack/react-query"
import { api } from "@/api/client"

export type Role = "viewer" | "editor" | "admin"

export interface CurrentUser {
  id: string
  login: string
  name: string
  role: Role
}

const RANK: Role[] = ["viewer", "editor", "admin"]

/** Хватает ли роли, чтобы показать элемент интерфейса. */
export function hasRank(actual: Role, required: Role): boolean {
  return RANK.indexOf(actual) >= RANK.indexOf(required)
}

/**
 * Текущий пользователь. Это ЕДИНСТВЕННОЕ место, где клиент узнаёт о правах,
 * и служит оно только показу: спрятанная кнопка не защищает ничего.
 * Проверку делает каждый роутер на бэкенде через require_role.
 */
export const currentUserQuery = queryOptions({
  queryKey: ["auth", "me"],
  queryFn: async (): Promise<CurrentUser | null> => {
    const { data, response } = await api.GET("/api/auth/me")
    // 401 — это норма, а не сбой: человек ещё не вошёл. Бросив здесь,
    // мы бы показывали экран ошибки вместо формы входа.
    if (response.status === 401) return null
    return data ?? null
  },
  retry: false,
  staleTime: 30_000,
})
```

- [ ] **Шаг 3: Написать `frontend/src/components/page-main.tsx`**

```typescript
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Ширина основного содержимого страницы задаётся ТОЛЬКО здесь. Свой <main>
 * страницы не заводят: иначе ширина расходится от экрана к экрану, и
 * приводить её обратно приходится по одному файлу.
 */
export function PageMain({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <main className={cn("mx-auto w-full max-w-5xl px-4 py-8", className)}>
      {children}
    </main>
  )
}
```

- [ ] **Шаг 4: Написать `frontend/src/components/site-nav.tsx`**

```typescript
import { Link, useNavigate } from "@tanstack/react-router"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { LogOut } from "lucide-react"
import { api } from "@/api/client"
import { Button } from "@/components/ui/button"
import { hasRank, type CurrentUser } from "@/lib/auth"

// as const обязателен: без него `to` выводится как string, и
// типизированные ссылки TanStack Router перестают проверяться — ровно та
// проверка, ради которой роутер и выбран.
const LINKS = [
  { to: "/", label: "Главная", role: "viewer" as const },
  { to: "/expenses", label: "Расходы", role: "viewer" as const },
  { to: "/users", label: "Люди", role: "admin" as const },
  { to: "/audit", label: "Журнал", role: "admin" as const },
  { to: "/design", label: "Дизайн", role: "viewer" as const },
  { to: "/docs", label: "Правила", role: "viewer" as const },
] as const

export function SiteNav({ user }: { user: CurrentUser }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const logout = useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout")
    },
    onSuccess: async () => {
      // Кэш сбрасывается целиком: в нём лежат данные, которые следующему
      // вошедшему видеть незачем.
      queryClient.clear()
      await navigate({ to: "/login" })
    },
  })

  return (
    <header className="border-border border-b">
      <nav className="mx-auto flex max-w-5xl items-center gap-1 px-4 py-3">
        {LINKS.filter((link) => hasRank(user.role, link.role)).map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className="text-muted-foreground hover:text-foreground rounded-md px-3 py-1.5 text-sm"
            activeProps={{ className: "text-foreground font-medium" }}
          >
            {link.label}
          </Link>
        ))}
        <span className="text-muted-foreground ml-auto text-sm">{user.name}</span>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Выйти"
          onClick={() => logout.mutate()}
        >
          <LogOut className="size-4" />
        </Button>
      </nav>
    </header>
  )
}
```

- [ ] **Шаг 5: Написать `frontend/src/router.tsx`**

Имя файла `router.tsx`, а не `routes.tsx`: рядом лежит каталог
`src/routes/`, и путь `@/routes` разрешался бы то в файл, то в каталог —
в зависимости от настроек сборщика.

```typescript
import type { JSX } from "react"
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router"
import type { QueryClient } from "@tanstack/react-query"
import { currentUserQuery } from "@/lib/auth"
import { SiteNav } from "@/components/site-nav"
import { AuditPage } from "@/routes/audit"
import { DesignPage } from "@/routes/design"
import { DocsPage } from "@/routes/docs"
import { ExpensesPage } from "@/routes/expenses"
import { HomePage } from "@/routes/home"
import { LoginPage } from "@/routes/login"
import { UsersPage } from "@/routes/users"

interface RouterContext {
  queryClient: QueryClient
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
})

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
})

/**
 * Оболочка закрытой части. beforeLoad уводит на /login, если сессии нет.
 *
 * ЭТО НЕ ЗАЩИТА. Гейт нужен, чтобы человек видел форму входа вместо пустого
 * экрана. Данные защищает бэкенд: каждый роутер там проверяет роль сам,
 * включая маршруты, куда этот интерфейс не ведёт.
 */
const privateRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "private",
  beforeLoad: async ({ context }) => {
    const user = await context.queryClient.ensureQueryData(currentUserQuery)
    if (!user) throw redirect({ to: "/login" })
    return { user }
  },
  component: function PrivateLayout() {
    const { user } = privateRoute.useRouteContext()
    return (
      <>
        <SiteNav user={user} />
        <Outlet />
      </>
    )
  },
})

const page = (path: string, component: () => JSX.Element) =>
  createRoute({ getParentRoute: () => privateRoute, path, component })

const routeTree = rootRoute.addChildren([
  loginRoute,
  privateRoute.addChildren([
    page("/", HomePage),
    page("/expenses", ExpensesPage),
    page("/users", UsersPage),
    page("/audit", AuditPage),
    page("/design", DesignPage),
    page("/docs", DocsPage),
  ]),
])

export function buildRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient } })
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof buildRouter>
  }
}
```

- [ ] **Шаг 6: Написать `frontend/src/main.tsx`**

```typescript
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "@tanstack/react-router"
import { buildRouter } from "@/router"
import "@/index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Приложение внутреннее: перезапрашивать при каждом возврате во
      // вкладку незачем, данные меняются раз в час, а не раз в секунду.
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
})

const router = buildRouter(queryClient)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>
)
```

- [ ] **Шаг 7: Коммит (после задач 27–32, когда появятся страницы)**

Файл `router.tsx` ссылается на страницы, которых ещё нет: `tsc` будет
красным до задачи 32. Это ожидаемо — коммит делается в конце задачи 32.

---

### Задача 27: Экран входа

**Files:**
- Create: `frontend/src/routes/login.tsx`

- [ ] **Шаг 1: Поставить формы**

```bash
cd frontend && npm install react-hook-form @hookform/resolvers zod
```

- [ ] **Шаг 2: Написать `frontend/src/routes/login.tsx`**

```typescript
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { z } from "zod"
import { api, toApiError } from "@/api/client"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const schema = z.object({
  login: z.string().min(1, "Укажи логин"),
  password: z.string().min(1, "Укажи пароль"),
})

type Values = z.infer<typeof schema>

export function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { login: "", password: "" },
  })

  const submit = useMutation({
    mutationFn: async (values: Values) => {
      const { error } = await api.POST("/api/auth/login", { body: values })
      if (error) throw error
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] })
      await navigate({ to: "/" })
    },
    onError: (error) => {
      const parsed = toApiError(error)
      // Ошибка входа всегда общая: бэкенд намеренно не говорит, логин
      // неверен или пароль, — и раскладывать её по полям нечего.
      form.setError("root", { message: parsed.message })
    },
  })

  return (
    <div className="flex min-h-svh items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Вход</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((values) => submit.mutate(values))}
          >
            <div className="space-y-2">
              <Label htmlFor="login">Логин</Label>
              <Input id="login" autoComplete="username" {...form.register("login")} />
              {form.formState.errors.login && (
                <p className="text-destructive text-sm">
                  {form.formState.errors.login.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Пароль</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                {...form.register("password")}
              />
              {form.formState.errors.password && (
                <p className="text-destructive text-sm">
                  {form.formState.errors.password.message}
                </p>
              )}
            </div>
            {form.formState.errors.root && (
              <Alert variant="destructive">
                <AlertDescription>
                  {form.formState.errors.root.message}
                </AlertDescription>
              </Alert>
            )}
            <Button type="submit" className="w-full" disabled={submit.isPending}>
              {submit.isPending ? "Проверяю…" : "Войти"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
```

---

### Задача 28: Главная страница

**Files:**
- Create: `frontend/src/routes/home.tsx`
- Create: `frontend/src/components/bootstrap-warning.tsx`

- [ ] **Шаг 1: Написать `frontend/src/components/bootstrap-warning.tsx`**

```typescript
import { TriangleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { CurrentUser } from "@/lib/auth"

/**
 * Пара admin / admin известна всем, у кого есть шаблон. Предупреждение
 * висит, пока под ней работают: контур открыт снаружи.
 */
export function BootstrapWarning({ user }: { user: CurrentUser }) {
  if (user.login !== "admin") return null
  return (
    <Alert variant="destructive" className="mb-6">
      <TriangleAlert className="size-4" />
      <AlertTitle>Вход под учётной записью по умолчанию</AlertTitle>
      <AlertDescription>
        Пара admin / admin известна всем, у кого есть шаблон. Заведи свою
        учётную запись в разделе «Люди», войди под ней и отключи эту. Смены
        пароля в приложении нет намеренно.
      </AlertDescription>
    </Alert>
  )
}
```

- [ ] **Шаг 2: Написать `frontend/src/routes/home.tsx`**

```typescript
import { Link } from "@tanstack/react-router"
import { useSuspenseQuery } from "@tanstack/react-query"
import { BootstrapWarning } from "@/components/bootstrap-warning"
import { PageMain } from "@/components/page-main"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { currentUserQuery, hasRank } from "@/lib/auth"

const SECTIONS = [
  {
    to: "/expenses",
    title: "Расходы",
    text: "Образцовый раздел. Показывает, как устроена фича целиком.",
    role: "viewer" as const,
  },
  {
    to: "/users",
    title: "Люди",
    text: "Учётные записи, роли и отключение доступа.",
    role: "admin" as const,
  },
  {
    to: "/docs",
    title: "Правила",
    text: "Как здесь работают: правила проекта и команды доставки.",
    role: "viewer" as const,
  },
]

export function HomePage() {
  const { data: user } = useSuspenseQuery(currentUserQuery)
  if (!user) return null

  return (
    <PageMain>
      <BootstrapWarning user={user} />
      <h1 className="text-3xl font-semibold">Стартовый шаблон на Python</h1>
      <p className="text-muted-foreground mt-2 max-w-2xl">
        Это заготовка внутреннего приложения: вход, роли, журнал аудита и
        образцовая фича. Когда появится первая настоящая функция, эту
        страницу переписывают под неё — сам маршрут несущий, сюда ведёт вход.
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {SECTIONS.filter((s) => hasRank(user.role, s.role)).map((section) => (
          <Card key={section.to}>
            <CardHeader>
              <CardTitle>{section.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-muted-foreground text-sm">{section.text}</p>
              {/* Ссылка стилизуется классами buttonVariants, а не Button с
                  render: Base UI поверх render всё равно ставит
                  role="button", и для скринридера это перестаёт быть
                  ссылкой. */}
              <Link
                to={section.to}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                Открыть
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </PageMain>
  )
}
```

---

### Задача 29: Экран расходов

**Files:**
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/src/routes/expenses.tsx`

- [ ] **Шаг 1: Написать `frontend/src/lib/format.ts`**

```typescript
/**
 * Показ денег и дат. Единственное место, откуда форматируют и таблица, и
 * подпись на графике.
 *
 * Разбор пользовательского ввода живёт на бэкенде: он решает, что попадёт
 * в базу, и обязан быть авторитетным. Здесь только показ.
 */

const MONEY = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  minimumFractionDigits: 2,
})

const DATE = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
})

const DATE_TIME = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
})

/** Копейки — в строку для человека. Делитель ровно 100, без округлений. */
export function formatMoney(minor: number): string {
  return MONEY.format(minor / 100)
}

export function formatDate(iso: string): string {
  return DATE.format(new Date(iso))
}

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso))
}
```

- [ ] **Шаг 2: Написать `frontend/src/routes/expenses.tsx`**

```typescript
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { api, toApiError } from "@/api/client"
import { PageMain } from "@/components/page-main"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDate, formatMoney } from "@/lib/format"

const CATEGORIES = ["Аренда", "Софт", "Оборудование", "Услуги", "Прочее"] as const

const schema = z.object({
  date: z.string().min(1, "Укажи дату"),
  title: z.string().min(1, "Укажи назначение"),
  category: z.enum(CATEGORIES),
  amount: z.string().min(1, "Укажи сумму"),
})

type Values = z.infer<typeof schema>

export function ExpensesPage() {
  const queryClient = useQueryClient()
  const expenses = useQuery({
    queryKey: ["expenses"],
    queryFn: async () => (await api.GET("/api/expenses")).data ?? [],
  })

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { date: "", title: "", category: "Софт", amount: "" },
  })

  const create = useMutation({
    mutationFn: async (values: Values) => {
      const { error } = await api.POST("/api/expenses", { body: values })
      if (error) throw error
    },
    onSuccess: async () => {
      form.reset()
      await queryClient.invalidateQueries({ queryKey: ["expenses"] })
    },
    onError: (error) => {
      const parsed = toApiError(error)
      // Поле из конверта: сообщение встаёт под нужный ввод. Без field —
      // общим алертом, а не молча.
      if (parsed.field && parsed.field in form.getValues()) {
        form.setError(parsed.field as keyof Values, { message: parsed.message })
      } else {
        form.setError("root", { message: parsed.message })
      }
    },
  })

  const remove = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE("/api/expenses/{expense_id}", {
        params: { path: { expense_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["expenses"] }),
  })

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Расходы</h1>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Новый расход</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4 sm:grid-cols-4"
            onSubmit={form.handleSubmit((values) => create.mutate(values))}
          >
            <div className="space-y-2">
              <Label htmlFor="date">Дата</Label>
              <Input id="date" type="date" {...form.register("date")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="title">Назначение</Label>
              <Input id="title" {...form.register("title")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">Категория</Label>
              <Select
                value={form.watch("category")}
                onValueChange={(v) =>
                  form.setValue("category", v as Values["category"])
                }
              >
                <SelectTrigger id="category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {/* Группа обязательна даже когда она одна: без обёртки
                      края пунктов прижимаются, и это выглядит как поехавшая
                      вёрстка, а не как забытый компонент. */}
                  <SelectGroup>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="amount">Сумма</Label>
              <Input id="amount" inputMode="decimal" {...form.register("amount")} />
            </div>
            <div className="sm:col-span-4 space-y-3">
              {Object.values(form.formState.errors).map((error, index) => (
                <Alert key={index} variant="destructive">
                  <AlertDescription>{error?.message as string}</AlertDescription>
                </Alert>
              ))}
              <Button type="submit" disabled={create.isPending}>
                Добавить
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Table className="mt-8">
        <TableHeader>
          <TableRow>
            <TableHead>Дата</TableHead>
            <TableHead>Назначение</TableHead>
            <TableHead>Категория</TableHead>
            <TableHead className="text-right">Сумма</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {expenses.data?.length === 0 && (
            // Пустое состояние обязательно: таблица из одних заголовков
            // читается как поломка, и на свежем контуре это первое, что
            // видит человек.
            <TableRow>
              <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                Расходов пока нет. Добавь первый в форме выше.
              </TableCell>
            </TableRow>
          )}
          {expenses.data?.map((expense) => (
            <TableRow key={expense.id}>
              <TableCell>{formatDate(expense.date)}</TableCell>
              <TableCell>{expense.title}</TableCell>
              <TableCell>{expense.category}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatMoney(expense.amount_minor)}
              </TableCell>
              <TableCell className="text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => remove.mutate(expense.id)}
                >
                  Удалить
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </PageMain>
  )
}
```

---

### Задача 30: Экран учётных записей

**Files:**
- Create: `frontend/src/routes/users.tsx`

- [ ] **Шаг 1: Написать `frontend/src/routes/users.tsx`**

```typescript
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { api, toApiError } from "@/api/client"
import { PageMain } from "@/components/page-main"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDateTime } from "@/lib/format"

const ROLES = ["viewer", "editor", "admin"] as const
const ROLE_LABEL: Record<(typeof ROLES)[number], string> = {
  viewer: "Смотрит",
  editor: "Правит",
  admin: "Управляет",
}

const schema = z.object({
  login: z.string().min(1, "Укажи логин").regex(/^\S+$/, "Логин без пробелов"),
  name: z.string().min(1, "Укажи имя"),
  role: z.enum(ROLES),
  password: z.string().min(8, "Не короче восьми символов"),
})

type Values = z.infer<typeof schema>

export function UsersPage() {
  const queryClient = useQueryClient()
  const users = useQuery({
    queryKey: ["users"],
    queryFn: async () => (await api.GET("/api/users")).data ?? [],
  })

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { login: "", name: "", role: "viewer", password: "" },
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["users"] })

  const create = useMutation({
    mutationFn: async (values: Values) => {
      const { error } = await api.POST("/api/users", { body: values })
      if (error) throw error
    },
    onSuccess: async () => {
      form.reset()
      await invalidate()
    },
    onError: (error) => {
      const parsed = toApiError(error)
      if (parsed.field && parsed.field in form.getValues()) {
        form.setError(parsed.field as keyof Values, { message: parsed.message })
      } else {
        form.setError("root", { message: parsed.message })
      }
    },
  })

  const update = useMutation({
    mutationFn: async (input: {
      id: string
      role?: (typeof ROLES)[number]
      status?: "active" | "disabled"
    }) => {
      const { error } = await api.PATCH("/api/users/{user_id}", {
        params: { path: { user_id: input.id } },
        body: { role: input.role ?? null, status: input.status ?? null },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Люди</h1>
      <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
        Учётные записи не удаляются: удалённый автор записи в журнале
        превратил бы историю в набор осиротевших строк. Вместо удаления —
        отключение: вход закрывается, уже выданные сессии отзываются.
      </p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Новая учётная запись</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4 sm:grid-cols-4"
            onSubmit={form.handleSubmit((values) => create.mutate(values))}
          >
            <div className="space-y-2">
              <Label htmlFor="login">Логин</Label>
              <Input id="login" {...form.register("login")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="name">Имя</Label>
              <Input id="name" {...form.register("name")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">Роль</Label>
              <Select
                value={form.watch("role")}
                onValueChange={(v) => form.setValue("role", v as Values["role"])}
              >
                <SelectTrigger id="role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {ROLES.map((role) => (
                      <SelectItem key={role} value={role}>
                        {ROLE_LABEL[role]}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Пароль</Label>
              <Input id="password" type="password" {...form.register("password")} />
            </div>
            <div className="sm:col-span-4 space-y-3">
              {Object.values(form.formState.errors).map((error, index) => (
                <Alert key={index} variant="destructive">
                  <AlertDescription>{error?.message as string}</AlertDescription>
                </Alert>
              ))}
              <Button type="submit" disabled={create.isPending}>
                Завести
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Table className="mt-8">
        <TableHeader>
          <TableRow>
            <TableHead>Логин</TableHead>
            <TableHead>Имя</TableHead>
            <TableHead>Роль</TableHead>
            <TableHead>Последний вход</TableHead>
            <TableHead className="text-right">Доступ</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                Учётных записей пока нет.
              </TableCell>
            </TableRow>
          )}
          {users.data?.map((user) => (
            <TableRow key={user.id}>
              <TableCell className="font-medium">{user.login}</TableCell>
              <TableCell>{user.name}</TableCell>
              <TableCell>
                <Select
                  // key привязан к значению: без него после обновления
                  // списка строка не размонтируется, и Select показывает
                  // старую роль при изменившихся данных.
                  key={`${user.id}-${user.role}`}
                  value={user.role}
                  onValueChange={(role) =>
                    update.mutate({ id: user.id, role: role as (typeof ROLES)[number] })
                  }
                >
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {ROLES.map((role) => (
                        <SelectItem key={role} value={role}>
                          {ROLE_LABEL[role]}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {user.last_login_at ? formatDateTime(user.last_login_at) : "не входил"}
              </TableCell>
              <TableCell className="text-right">
                {user.status === "active" ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => update.mutate({ id: user.id, status: "disabled" })}
                  >
                    Отключить
                  </Button>
                ) : (
                  <div className="flex items-center justify-end gap-2">
                    <Badge variant="secondary">отключена</Badge>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => update.mutate({ id: user.id, status: "active" })}
                    >
                      Включить
                    </Button>
                  </div>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </PageMain>
  )
}
```

---

### Задача 31: Журнал аудита

**Files:**
- Create: `frontend/src/routes/audit.tsx`

- [ ] **Шаг 1: Написать `frontend/src/routes/audit.tsx`**

```typescript
import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import { PageMain } from "@/components/page-main"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDateTime } from "@/lib/format"

const ACTION_LABEL: Record<string, string> = {
  create: "создание",
  update: "изменение",
  delete: "удаление",
}

export function AuditPage() {
  const entries = useQuery({
    queryKey: ["audit"],
    queryFn: async () => (await api.GET("/api/audit")).data ?? [],
  })

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Журнал</h1>
      <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
        Каждая мутация данных пишется сюда той же транзакцией, что и само
        изменение. Показаны последние двести записей.
      </p>

      <Table className="mt-6">
        <TableHeader>
          <TableRow>
            <TableHead>Когда</TableHead>
            <TableHead>Кто</TableHead>
            <TableHead>Что</TableHead>
            <TableHead>Объект</TableHead>
            <TableHead>Подробности</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                Записей пока нет — в журнал попадают только изменения данных.
              </TableCell>
            </TableRow>
          )}
          {entries.data?.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell className="text-muted-foreground whitespace-nowrap">
                {formatDateTime(entry.ts)}
              </TableCell>
              <TableCell className="font-medium">{entry.actor}</TableCell>
              <TableCell>
                <Badge variant="secondary">
                  {ACTION_LABEL[entry.action] ?? entry.action}
                </Badge>
              </TableCell>
              <TableCell>{entry.entity}</TableCell>
              <TableCell className="text-muted-foreground">{entry.detail}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </PageMain>
  )
}
```

---

### Задача 32: Витрина дизайна и экран правил

**Files:**
- Create: `frontend/src/routes/design.tsx`
- Create: `frontend/src/routes/docs.tsx`
- Create: `frontend/src/components/markdown-view.tsx`

- [ ] **Шаг 1: Перенести витрину из эталона**

```bash
SRC=/Users/minas/projects/app-template
mkdir -p frontend/src/routes/design-parts
cp $SRC/app/design/_components/showcase-*.tsx frontend/src/routes/design-parts/
cp $SRC/app/design/_components/theme-picker.tsx frontend/src/routes/design-parts/
```

В скопированных файлах заменить импорты:

- `@/lib/design/...` → `@/lib/design/...` (путь совпадает, правки не нужно);
- убрать директивы `"use client"` — в SPA их нет;
- заменить `next/link` на `@tanstack/react-router` (`Link`, проп `to` вместо
  `href`), если встретится.

- [ ] **Шаг 2: Написать `frontend/src/routes/design.tsx`**

```typescript
import { PageMain } from "@/components/page-main"
import { ShowcaseCharts } from "./design-parts/showcase-charts"
import { ShowcaseData } from "./design-parts/showcase-data"
import { ShowcaseFeedback } from "./design-parts/showcase-feedback"
import { ShowcaseForms } from "./design-parts/showcase-forms"
import { ShowcaseNavigation } from "./design-parts/showcase-navigation"
import { ThemePicker } from "./design-parts/theme-picker"

/**
 * Витрина всех установленных компонентов в рабочих состояниях. Удаляется
 * целиком, когда шаблон стал приложением и оформление выбрано; lib/design
 * при этом остаётся — команда npm run theme работает и без витрины.
 */
export function DesignPage() {
  return (
    <PageMain className="max-w-6xl">
      <h1 className="text-3xl font-semibold">Дизайн</h1>
      <div className="mt-8 space-y-12">
        <ThemePicker />
        <ShowcaseForms />
        <ShowcaseData />
        <ShowcaseFeedback />
        <ShowcaseNavigation />
        <ShowcaseCharts />
      </div>
    </PageMain>
  )
}
```

- [ ] **Шаг 3: Написать `frontend/src/components/markdown-view.tsx`**

```bash
cd frontend && npm install react-markdown remark-gfm
```

```typescript
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"

/**
 * Показ markdown из репозитория. Содержимое приходит с бэкенда и написано
 * нами же, но react-markdown по умолчанию не пропускает сырой HTML — и
 * плагин, который это включает, здесь не ставится намеренно.
 */
export function MarkdownView({ content }: { content: string }) {
  return (
    <div className="prose-sm max-w-none space-y-4 text-sm leading-relaxed">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (props) => <h1 className="mt-8 text-2xl font-semibold" {...props} />,
          h2: (props) => <h2 className="mt-8 text-xl font-semibold" {...props} />,
          h3: (props) => <h3 className="mt-6 text-lg font-medium" {...props} />,
          p: (props) => <p className="text-muted-foreground" {...props} />,
          ul: (props) => <ul className="list-disc space-y-1 pl-6" {...props} />,
          ol: (props) => <ol className="list-decimal space-y-1 pl-6" {...props} />,
          code: (props) => (
            <code className="bg-muted rounded px-1.5 py-0.5 text-xs" {...props} />
          ),
          table: (props) => (
            <div className="overflow-x-auto">
              <table className="w-full text-left" {...props} />
            </div>
          ),
          th: (props) => <th className="border-border border-b p-2" {...props} />,
          td: (props) => <td className="border-border border-b p-2" {...props} />,
        }}
      >
        {content}
      </Markdown>
    </div>
  )
}
```

- [ ] **Шаг 4: Написать `frontend/src/routes/docs.tsx`**

```typescript
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"
import { MarkdownView } from "@/components/markdown-view"
import { PageMain } from "@/components/page-main"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

const DOCUMENTS = [
  { name: "agents", label: "Правила" },
  { name: "checklist", label: "Что умеет" },
  { name: "onboarding", label: "Установка" },
  { name: "ship", label: "Доставка" },
  { name: "status", label: "Состояние" },
  { name: "logs", label: "Логи" },
  { name: "rollback", label: "Откат" },
] as const

type DocumentName = (typeof DOCUMENTS)[number]["name"]

export function DocsPage() {
  const [current, setCurrent] = useState<DocumentName>("agents")

  const document = useQuery({
    queryKey: ["docs", current],
    queryFn: async () => {
      const { data } = await api.GET("/api/meta/docs/{name}", {
        params: { path: { name: current } },
      })
      return data ?? null
    },
  })

  return (
    <PageMain>
      <h1 className="text-3xl font-semibold">Правила и команды</h1>
      <Tabs
        value={current}
        onValueChange={(v) => setCurrent(v as DocumentName)}
        className="mt-6"
      >
        <TabsList>
          {DOCUMENTS.map((doc) => (
            <TabsTrigger key={doc.name} value={doc.name}>
              {doc.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <div className="mt-8">
        {document.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        ) : (
          <MarkdownView content={document.data?.content ?? "Документ недоступен."} />
        )}
      </div>
    </PageMain>
  )
}
```

- [ ] **Шаг 5: Собрать фронтенд целиком**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: типы сходятся, `frontend/dist/` собран.

- [ ] **Шаг 6: Проверить в живом браузере**

```bash
cd backend && uv run uvicorn app.main:app --port 8000 &
cd frontend && npm run dev
```

Открыть `http://127.0.0.1:5173`, войти под admin / admin и проверить:
обе темы (светлая и тёмная), мобильную ширину, чистую консоль, пустые
состояния таблиц. Часть ошибок видна только в живом браузере.

- [ ] **Шаг 7: Коммит**

```bash
git add frontend/
git commit -m "feat: экраны входа, расходов, людей, журнала, дизайна и правил"
```

---

## Фаза 6. Сквозные тесты

### Задача 33: Playwright и смоук входа

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/tests/e2e/auth.spec.ts`

- [ ] **Шаг 1: Поставить Playwright**

```bash
cd frontend && npm install -D @playwright/test && npx playwright install chromium
```

- [ ] **Шаг 2: Написать `frontend/playwright.config.ts`**

```typescript
import { defineConfig } from "@playwright/test"

const PORT = 8100

/**
 * E2e идут против собранного приложения, которое раздаёт сам бэкенд, — то
 * есть против того же, что уедет на контур. Прогон через dev-сервер Vite
 * проверял бы конфигурацию, которой в бою не существует.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  webServer: {
    command: `npm run build && cd ../backend && uv run uvicorn app.main:app --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      // Отдельная база: тесты создают и меняют данные, и делать это в
      // рабочей базе нельзя.
      DATABASE_URL: process.env.DATABASE_URL_E2E ?? process.env.DATABASE_URL ?? "",
      APP_ENV: "local",
      APP_AUTH_SECRET: "e2e-secret-not-used-anywhere-real-000000",
      COOKIE_SECURE: "false",
    },
  },
})
```

- [ ] **Шаг 3: Написать `frontend/tests/e2e/auth.spec.ts`**

```typescript
import { expect, test } from "@playwright/test"

// Данные создаются внутри теста, а не берутся из сида: тест, зависящий от
// сида, ломается при любом изменении сида и не воспроизводится на пустой
// базе контура.
const unique = () => `e2e${Date.now()}${Math.floor(Math.random() * 1000)}`

test("незалогиненного уводит на форму входа", async ({ page }) => {
  await page.goto("/expenses")
  await expect(page.getByRole("heading", { name: "Вход" })).toBeVisible()
})

test("неверная пара не пускает и не выдаёт, существует ли логин", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("Логин").fill("нетакого")
  await page.getByLabel("Пароль").fill("мимо")
  await page.getByRole("button", { name: "Войти" }).click()
  await expect(page.getByText("Неверный логин или пароль")).toBeVisible()
})

test("вход и выход работают", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("Логин").fill("admin")
  await page.getByLabel("Пароль").fill("admin")
  await page.getByRole("button", { name: "Войти" }).click()

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  // Предупреждение о паре по умолчанию обязано висеть на первом экране.
  await expect(page.getByText("Вход под учётной записью по умолчанию")).toBeVisible()

  await page.getByRole("button", { name: "Выйти" }).click()
  await expect(page.getByRole("heading", { name: "Вход" })).toBeVisible()
})

test("роль viewer не видит раздел «Люди» и не попадает в него по адресу", async ({
  page,
}) => {
  const login = unique()

  await page.goto("/login")
  await page.getByLabel("Логин").fill("admin")
  await page.getByLabel("Пароль").fill("admin")
  await page.getByRole("button", { name: "Войти" }).click()

  await page.goto("/users")
  await page.getByLabel("Логин").fill(login)
  await page.getByLabel("Имя").fill("Смотрящий")
  await page.getByLabel("Пароль").fill("длинныйпароль")
  await page.getByRole("button", { name: "Завести" }).click()
  await expect(page.getByRole("cell", { name: login })).toBeVisible()

  await page.getByRole("button", { name: "Выйти" }).click()
  await page.getByLabel("Логин").fill(login)
  await page.getByLabel("Пароль").fill("длинныйпароль")
  await page.getByRole("button", { name: "Войти" }).click()

  await expect(page.getByRole("link", { name: "Люди" })).toHaveCount(0)
})
```

- [ ] **Шаг 4: Прогнать**

Run: `cd frontend && DATABASE_URL_E2E=postgresql://... npx playwright test`
Expected: 4 passed

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/playwright.config.ts frontend/tests/
git commit -m "test: сквозной смоук входа и разграничения прав"
```

---

### Задача 34: Смоук образцовой фичи

**Files:**
- Create: `frontend/tests/e2e/expenses.spec.ts`

- [ ] **Шаг 1: Написать `frontend/tests/e2e/expenses.spec.ts`**

```typescript
import { expect, test } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("Логин").fill("admin")
  await page.getByLabel("Пароль").fill("admin")
  await page.getByRole("button", { name: "Войти" }).click()
  await page.goto("/expenses")
})

test("расход добавляется и появляется в таблице", async ({ page }) => {
  const title = `Подписка ${Date.now()}`

  await page.getByLabel("Дата").fill("2026-08-31")
  await page.getByLabel("Назначение").fill(title)
  await page.getByLabel("Сумма").fill("1 200,50")
  await page.getByRole("button", { name: "Добавить" }).click()

  await expect(page.getByRole("cell", { name: title })).toBeVisible()
  await expect(page.getByRole("cell", { name: /1\s?200,50/ })).toBeVisible()
})

test("несуществующая дата отклоняется и показывает введённое", async ({ page }) => {
  // Поле type="date" не умеет показать невалидную строку — браузер отдаёт
  // пустое значение. Поэтому введённое обязано быть в тексте ошибки.
  await page.getByLabel("Дата").fill("2026-02-31")
  await page.getByLabel("Назначение").fill("Не должно сохраниться")
  await page.getByLabel("Сумма").fill("100")
  await page.getByRole("button", { name: "Добавить" }).click()

  await expect(page.getByText(/не похожа на дату/)).toBeVisible()
  await expect(page.getByRole("cell", { name: "Не должно сохраниться" })).toHaveCount(0)
})

test("сумма сверх предела отклоняется с читаемым сообщением", async ({ page }) => {
  await page.getByLabel("Дата").fill("2026-08-31")
  await page.getByLabel("Назначение").fill("Слишком много")
  await page.getByLabel("Сумма").fill("99000000")
  await page.getByRole("button", { name: "Добавить" }).click()

  await expect(page.getByText(/больше предельной/)).toBeVisible()
})

test("изменение попадает в журнал", async ({ page }) => {
  const title = `В журнал ${Date.now()}`

  await page.getByLabel("Дата").fill("2026-08-31")
  await page.getByLabel("Назначение").fill(title)
  await page.getByLabel("Сумма").fill("500")
  await page.getByRole("button", { name: "Добавить" }).click()
  await expect(page.getByRole("cell", { name: title })).toBeVisible()

  await page.goto("/audit")
  await expect(page.getByRole("cell", { name: "admin" }).first()).toBeVisible()
  await expect(page.getByText("создание").first()).toBeVisible()
})
```

- [ ] **Шаг 2: Прогнать все e2e**

Run: `cd frontend && npx playwright test`
Expected: 8 passed

- [ ] **Шаг 3: Коммит**

```bash
git add frontend/tests/e2e/expenses.spec.ts
git commit -m "test: сквозной смоук образцовой фичи и журнала"
```

---

## Фаза 7. Контур, доставка и правила

### Задача 35: Проверки на ветке

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Шаг 1: Написать `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches-ignore: [main]
  pull_request:
    branches: [main]

jobs:
  checks:
    runs-on: ubuntu-latest
    # Postgres поднимается и здесь, а не только в доставке: API-тесты и e2e
    # обязаны прогоняться на ветке, до merge. Иначе красный прогон
    # обнаруживался бы уже после слияния — main успевал бы принять коммит,
    # который на контур не поедет.
    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: apptemplate_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    # Переменные заданы на весь job: app.core.config разбирает окружение при
    # импорте, а такой импорт однажды окажется в цепочке любого теста.
    env:
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/apptemplate_test
      DATABASE_URL_E2E: postgresql://postgres:postgres@localhost:5432/apptemplate_test
      APP_ENV: local
      APP_AUTH_SECRET: ci-build-secret-not-used-anywhere-real
      COOKIE_SECURE: "false"
    steps:
      - uses: actions/checkout@v5

      - name: Поставить uv и Python
        uses: astral-sh/setup-uv@v10
        with:
          python-version: "3.14"
          enable-cache: true

      - uses: actions/setup-node@v5
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      # --group lint ставит import-linter, которого нет в dev по умолчанию.
      # На Linux у grimp есть готовое колесо, поэтому здесь это дёшево.
      - run: uv sync --frozen --group lint
        working-directory: backend

      - run: uv run ruff format --check .
        working-directory: backend
      - run: uv run ruff check .
        working-directory: backend
      - run: uv run mypy app
        working-directory: backend
      - run: uv run --group lint lint-imports --config .importlinter
        working-directory: backend

      # Схема накатывается до тестов: API-тесты идут в настоящую базу.
      - run: uv run alembic upgrade head
        working-directory: backend
      - run: uv run pytest
        working-directory: backend

      - run: npm ci
        working-directory: frontend
      - run: npx tsc --noEmit
        working-directory: frontend
      - run: npm run test
        working-directory: frontend

      # Дрейф контракта: бэкенд поменял схему, фронт не перегенерировал
      # типы. Ловится здесь, а не в бою.
      - name: Типы клиента совпадают со схемой
        run: |
          cd backend && uv run python -m app.openapi > /tmp/openapi.json
          cd ../frontend && npx openapi-typescript /tmp/openapi.json -o /tmp/schema.d.ts
          diff -u src/api/schema.d.ts /tmp/schema.d.ts || {
            echo "::error::Типы клиента разошлись со схемой. Выполни: make openapi"
            exit 1
          }

      - run: npx playwright install --with-deps chromium
        working-directory: frontend
      # Отдельного npm run build нет намеренно: сборку делает сам Playwright
      # через webServer, и второй build удвоил бы самый долгий шаг прогона.
      # Сломанная сборка всё равно валит прогон — сервер не поднимется.
      - run: npx playwright test
        working-directory: frontend
```

- [ ] **Шаг 2: Коммит**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: проверки на feature-ветке"
```

---

### Задача 36: Доставка

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Шаг 1: Написать `.github/workflows/deploy.yml`**

```yaml
name: deploy

on:
  push:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: apptemplate_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/apptemplate_test
      DATABASE_URL_E2E: postgresql://postgres:postgres@localhost:5432/apptemplate_test
      APP_ENV: local
      APP_AUTH_SECRET: e2e-secret-not-used-anywhere-real-000000
      COOKIE_SECURE: "false"
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v10
        with:
          python-version: "3.14"
          enable-cache: true
      - uses: actions/setup-node@v5
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: uv sync --frozen --group lint
        working-directory: backend
      - run: uv run ruff format --check .
        working-directory: backend
      - run: uv run ruff check .
        working-directory: backend
      - run: uv run mypy app
        working-directory: backend
      - run: uv run --group lint lint-imports --config .importlinter
        working-directory: backend
      - run: uv run alembic upgrade head
        working-directory: backend
      - run: uv run pytest
        working-directory: backend
      - run: npm ci
        working-directory: frontend
      - run: npx tsc --noEmit
        working-directory: frontend
      - run: npm run test
        working-directory: frontend
      - run: npx playwright install --with-deps chromium
        working-directory: frontend
      - run: npx playwright test
        working-directory: frontend

  deploy:
    needs: quality
    runs-on: ubuntu-latest
    concurrency: deploy
    env:
      SLUG: apptemplate
    steps:
      - uses: actions/checkout@v5

      # Фронтенд собирается ЗДЕСЬ, а не на сервере. Так на контуре не
      # оказывается ни Node, ни node_modules: человек, выбравший
      # Python-шаблон, не обнаруживает в бою вторую экосистему. Побочно это
      # снимает с сервера самый прожорливый шаг доставки.
      - uses: actions/setup-node@v5
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npm run build
        working-directory: frontend

      - name: Записать версию сборки
        run: |
          printf '{"commit":"%s","built_at":"%s"}\n' \
            "$(git rev-parse --short HEAD)" "$(date -u +%FT%TZ)" > build-info.json

      - name: Упаковать статику и версию
        run: tar -czf dist.tar.gz -C frontend dist -C ../ build-info.json

      - name: Доставка на контур
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.DEPLOY_SSH_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -H ${{ secrets.SERVER_HOST }} >> ~/.ssh/known_hosts 2>/dev/null

          scp dist.tar.gz deploy@${{ secrets.SERVER_HOST }}:/tmp/$SLUG-dist.tar.gz

          ssh deploy@${{ secrets.SERVER_HOST }} 'bash -s' <<EOF
          set -euo pipefail
          SLUG=$SLUG
          DIR=/var/www/\$SLUG
          cd "\$DIR"
          source "\$DIR/.deploy-env"   # даёт PORT

          # Первый деплой: кода ещё нет. Клонировать нельзя — каталог не
          # пуст: app-provision положил туда .env и .deploy-env, а git clone
          # в непустой каталог отказывается. Репозиторий разворачивается на
          # месте; файлы окружения целы — reset --hard не трогает
          # неотслеживаемое.
          if [ ! -d "\$DIR/.git" ]; then
            git init -q -b main
            git remote add origin "git@github.com-\$SLUG:${{ github.repository }}.git"
          fi

          git fetch origin main
          git reset --hard origin/main

          # Собранная статика и версия приезжают архивом, а не собираются
          # здесь: Node на этом сервере нет.
          rm -rf "\$DIR/frontend/dist"
          mkdir -p "\$DIR/frontend"
          tar -xzf /tmp/\$SLUG-dist.tar.gz -C "\$DIR/frontend" dist
          tar -xzf /tmp/\$SLUG-dist.tar.gz -C "\$DIR" build-info.json
          rm -f /tmp/\$SLUG-dist.tar.gz

          cd "\$DIR/backend"
          uv sync --frozen
          uv run alembic upgrade head

          export PM2_HOME=/home/deploy/.pm2
          if pm2 describe "\$SLUG" > /dev/null 2>&1; then
            pm2 reload "\$SLUG" --update-env
          else
            pm2 start "\$DIR/backend/.venv/bin/python" --name "\$SLUG" \
              --cwd "\$DIR/backend" \
              -- -m uvicorn app.main:app --host 127.0.0.1 --port "\$PORT"
            pm2 save
          fi

          sleep 3
          # Проверяем /api/health, а не корень: корень отдаёт index.html с
          # кодом 200 даже при недоступной базе, и доставка объявляла бы
          # успешным заведомо нерабочий контур.
          CODE=\$(curl -s -o /dev/null -w '%{http_code}' \
            "http://127.0.0.1:\$PORT/api/health")
          [ "\$CODE" = "200" ] || { echo "контур ответил \$CODE"; exit 1; }
          echo "доставлено: \$(git rev-parse --short HEAD)"
          EOF
```

Heredoc здесь **без кавычек** вокруг `EOF`: внутрь подставляются
`${{ secrets... }}` и `$SLUG` из окружения Actions. Значит все переменные,
которые должны раскрыться на сервере, экранированы обратным слэшем. Под
`set -u` пропущенный слэш роняет доставку с «unbound variable», и
`bash -n` этого не поймает.

- [ ] **Шаг 2: Коммит**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: доставка на контур со сборкой фронтенда в Actions"
```

---

### Задача 37: Проверка резервных копий

**Files:**
- Create: `.github/workflows/backup.yml`

- [ ] **Шаг 1: Написать `.github/workflows/backup.yml`**

```yaml
name: backup-check

on:
  schedule:
    # 07:00 МСК — копия снимается в 03:17, к утру она обязана быть.
    - cron: "0 4 * * *"
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Проверить свежесть ночной копии
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.DEPLOY_SSH_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -H ${{ secrets.SERVER_HOST }} >> ~/.ssh/known_hosts 2>/dev/null
          ssh deploy@${{ secrets.SERVER_HOST }} 'bash -s' <<'EOF'
          set -euo pipefail
          SLUG=apptemplate
          LATEST=$(ls -t /home/deploy/backups/$SLUG/*.sql.gz 2>/dev/null | head -1 || true)
          [ -n "$LATEST" ] || { echo "копий нет вообще"; exit 1; }
          AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$LATEST") ) / 3600 ))
          SIZE=$(stat -c %s "$LATEST")
          echo "последняя копия: $LATEST, ${AGE_H} ч назад, ${SIZE} байт"
          # Копия старше суток или подозрительно маленькая — это авария:
          # о ней надо узнать до того, как она понадобится.
          [ "$AGE_H" -le 26 ] || { echo "копия устарела"; exit 1; }
          [ "$SIZE" -ge 1024 ] || { echo "копия подозрительно мала"; exit 1; }
          EOF
```

- [ ] **Шаг 2: Коммит**

```bash
git add .github/workflows/backup.yml
git commit -m "ci: ежедневная проверка свежести резервной копии"
```

---

### Задача 38: Правила проекта

**Files:**
- Create: `AGENTS.md`
- Create: `CLAUDE.md`
- Create: `.cursor/rules/project.mdc`

- [ ] **Шаг 1: Написать `AGENTS.md`**

Взять `AGENTS.md` эталона как основу:

```bash
cp /Users/minas/projects/app-template/AGENTS.md AGENTS.md
```

Затем внести правки. **Переносится слово в слово** (не трогать): заголовок и
вводный абзац про единственную копию правил; блок Bootstrap-Only; раздел
«Контур один, и он боевой»; «Что этому приложению нужно»; «Процесс
разработки»; весь раздел «Интерфейс» с Base UI, `render` вместо `asChild`,
группами в меню и запретом raw-цветов; «Языковые конвенции»; «Доставка» с
таблицей команд и таблицей «код и данные откатываются по-разному».

Удалить блок `<!-- BEGIN:nextjs-agent-rules -->…<!-- END -->` целиком: его
дописывал `next dev`, которого здесь нет.

**Переписать раздел «Жёсткие рамки»:**

```markdown
## Жёсткие рамки

- Стек только такой. Бэкенд: Python 3.14 + FastAPI + Pydantic + SQLAlchemy
  (async) + Alembic + PostgreSQL. Фронтенд: Vite + React + TypeScript +
  Tailwind + shadcn/ui на Base UI. Никаких других фреймворков, ORM,
  сборщиков и CSS-подходов.
- Новые зависимости ставятся **без согласований**. Но рамки стека выше
  этого права: другой UI-библиотеки, ORM, сборщика или CSS-подхода в
  проекте не появляется. Сначала посмотри, решается ли задача стандартной
  библиотекой или уже установленным.
- Docker в этом проекте не используется. Контур — pm2 и nginx на общем
  сервере, где живут и соседние приложения; один контейнеризованный проект
  посреди них не упростит ничего, а эксплуатацию разведёт надвое.
- Деплой, миграции, работа с сервером и секретами — обычная работа, не
  «чувствительные операции для разработчика». Разработчика в проекте нет.
```

**Переписать раздел «Структура каталогов»:**

```markdown
## Структура каталогов

- `backend/app/features/<фича>/` — маршруты, правила и таблицы одной фичи.
  Внутри три роли, и они не смешиваются: `router.py` знает только HTTP,
  `service.py` держит правила и транзакцию, `models.py` и `schemas.py` —
  таблицы и формы данных.
- `backend/app/domain/` — чистая логика: расчёты, деньги, даты, агрегации,
  ранги ролей. Без SQLAlchemy, без FastAPI, без I/O. Обязательные
  unit-тесты рядом с кодом.
- `backend/app/core/` — общее для всех фич: конфигурация, сессия базы,
  пароли и токен, зависимости доступа, журнал аудита, конверт ошибки,
  раздача статики.
- `backend/app/core/db.py` — единственная точка доступа к базе в коде
  приложения.
- `backend/app/core/config.py` — единственное место, где читается
  окружение **в коде приложения**. `os.environ` в модулях `app/` не
  используется.

  Обвязка, работающая вне приложения, живёт по другому правилу и читает
  окружение сама: `alembic/env.py`, `playwright.config.ts`. Причина не в
  удобстве: конфигурация проверяет весь набор переменных разом, и
  подготовка тестовой базы, которой нужен только адрес, падала бы из-за
  незаданного `APP_AUTH_SECRET`. Обвязка запускается до того, как
  приложение вообще существует.
- `frontend/src/routes/` — по файлу на экран.
- `frontend/src/components/ui/` — только компоненты shadcn, руками не
  редактируются.
- `frontend/src/components/` (вне `ui/`) — переиспользуемые композиции.
  Данные попадают в них только через пропсы.
- Ширина основного содержимого страницы — только через
  `frontend/src/components/page-main.tsx` (`<PageMain>`), свой `<main>` не
  заводится.
- `frontend/src/lib/design/` — темы оформления. Без React и I/O; ввод-вывод
  держит `frontend/scripts/apply-theme.ts`.
- `frontend/src/lib/format.ts` — показ денег и дат. Разбор ввода живёт на
  бэкенде.
- `backend/tests/unit/` — чистая логика, `backend/tests/api/` — маршруты,
  `frontend/tests/e2e/` — сквозной смоук.

### Границы модулей проверяет линтер

`backend/.importlinter` держит три контракта: `domain` не знает ни про базу,
ни про HTTP, ни про фичи; фичи не лезут друг другу внутрь; `router` не
ходит в модели мимо `service`. Нарушение роняет прогон. Понадобилось
обратиться к чужой фиче — это делается через её `service`, и контракт
меняется руками: изменение обязано быть видно в дифе.
```

**Переписать раздел «Мутации данных»:**

```markdown
## Мутации данных

- Мутации живут в `service.py` фичи. `router.py` только принимает запрос,
  проверяет роль и зовёт сервис.
- Вход разбирается схемой Pydantic, а не чтением полей по месту.
- Ожидаемые ошибки (валидация, отказ по правилу) **не бросаются наружу как
  сбой** — поднимаются как `RuleViolation` и приезжают клиенту единым
  конвертом `{"error": "...", "field": "..."}` со статусом 400. Форма
  ставит сообщение под нужное поле.
- Неожиданные сбои ловит обработчик в `core/errors.py`: наружу уходит
  «Что-то пошло не так», подробности — в лог, который читают через `/logs`.
  Текст исключения наружу не отдаётся никогда: он регулярно содержит кусок
  запроса, путь на диске или адрес базы.
- **Каждая мутация пишет в журнал аудита той же транзакцией**, что и само
  изменение: `write_audit(session, ...)` без commit, а commit делает сервис
  один раз в конце. Отдельный commit для журнала означал бы, что падение
  между двумя коммитами оставляет изменение без следа.
- Проверка роли — зависимостью `require_role` на каждом маршруте, включая
  те, куда интерфейс не ведёт. Ad-hoc проверок нет.

### Клиентский гейт — не защита

Роутер в браузере уводит на `/login`, когда сессии нет, и прячет пункты
меню не по роли. Это удобство: человек видит форму входа вместо пустого
экрана. Запрос можно послать и мимо интерфейса, поэтому решает всегда
бэкенд. Маршрут без `require_role` открыт всем вошедшим, как бы надёжно его
ни прятал интерфейс.

### Типы клиента генерируются

`frontend/src/api/schema.d.ts` собирается из схемы OpenAPI командой
`make openapi`. Руками не правится. Разошлось с бэкендом — перегенерируй, а
не подгоняй: CI сравнивает файл с заново сгенерированным и падает на любом
дифе.
```

**Переписать раздел «База данных»:**

```markdown
## База данных

- Схему меняем только через модели SQLAlchemy + `make revision m=<слаг>`,
  затем `make migrate`. Имена как в Alembic: `revision` создаёт, `migrate`
  применяет.
- **Сгенерированную миграцию читают глазами перед применением.**
  `--autogenerate` не видит переименований: он показывает удаление плюс
  добавление, и данные колонки теряются молча. Он не замечает изменения
  состава значений `enum` — добавили роль в `Role`, миграция вышла пустой,
  и приложение падает на первой же записи с новым значением. Он не всегда
  замечает смену типа и никогда — смену смысла.
- Применённые миграции не редактируются — только новая миграция.
- Обратимость проверяется до коммита:
  `alembic upgrade head && alembic downgrade base && alembic upgrade head`.
  Именно этот прогон ловит забытое удаление типа enum в `downgrade`.
- **Деструктивная миграция** (удаление таблицы или колонки с данными) —
  явно предупреди владельца до применения и отметь это в описании
  изменений. Это единственная по-настоящему опасная авария в проекте:
  откат кода её не отменяет, спасает только резервная копия.
- Даты в базе — `TIMESTAMPTZ`. В интерфейсе — через `formatDate` и
  `formatDateTime` из `frontend/src/lib/format.ts` (московская зона).
- Деньги — всегда целые копейки (`amount_minor: int`). Разбор ввода только
  `parse_money_to_minor` из `app/domain/money.py`. Никаких float для денег.
- Колонка `Integer` — это `int4` в PostgreSQL: предел `MAX_AMOUNT_MINOR`,
  примерно 21,47 млн ₽. Сервис, принимающий сумму, обязан проверить её по
  этой константе и вернуть ошибку формы. Без проверки сумма проходит разбор
  и падает в базе ошибкой драйвера, которую специалисту читать нечем.
```

**Переписать раздел «Тесты»:**

```markdown
## Тесты

- Чистая логика в `backend/app/domain/` — обязательные unit-тесты (pytest),
  файл `tests/unit/test_*.py`. Сначала тест, потом код.
- Маршруты — API-тесты в `backend/tests/api/`: коды ответов, форма ошибки,
  отказ по роли, запись в журнал. Каждый тест идёт в своей транзакции и
  откатывается.
- Ключевые пользовательские сценарии — e2e-смоук в `frontend/tests/e2e/`
  (Playwright). При добавлении фичи добавь или обнови смоук её главного
  сценария. E2e-тесты не зависят от сида — данные создаются внутри теста.
- **Unit-тесты на React-компоненты и страницы запрещены** — их роль
  выполняет e2e.
```

**Переписать раздел «Проверки перед любым коммитом»:**

```markdown
## Проверки перед любым коммитом

    make check

Он прогоняет обе половины: ruff, mypy, границы модулей и pytest на бэкенде,
`tsc`, unit-тесты и сверку сгенерированных типов на фронтенде.

Их же прогоняет CI на feature-ветке — и вместе с ними e2e-смоук, которому
нужна отдельная база и который поэтому локально запускать не обязательно
(`cd frontend && npx playwright test`). Красный прогон останавливает ветку
**до** merge, так что `main` не принимает коммит, который на контур не
поедет.
```

- [ ] **Шаг 2: Написать `CLAUDE.md`**

```markdown
# CLAUDE.md

Правила этого проекта живут в `AGENTS.md` — там единственная копия. Прочитай
его целиком до начала работы.

<!-- BOOTSTRAP_ONLY_START -->
Это свежая установка из шаблона. До любой работы над кодом прочитай
`README.md` и `CHECKLIST.md`, затем проведи установку по
`docs/commands/onboarding.md` — она же доступна как `/onboarding`.

В конце установки удали этот блок и парный ему из `AGENTS.md`.
<!-- BOOTSTRAP_ONLY_END -->
```

- [ ] **Шаг 3: Написать `.cursor/rules/project.mdc`**

```markdown
---
alwaysApply: true
---

Правила этого проекта живут в `AGENTS.md` — там единственная копия.
Прочитай его целиком до начала работы. Копий правил нет: две копии
расходятся, и через полгода никто не знает, какая настоящая.
```

- [ ] **Шаг 4: Коммит**

```bash
git add AGENTS.md CLAUDE.md .cursor/
git commit -m "docs: правила работы над проектом"
```

---

### Задача 39: Команды доставки

**Files:**
- Create: `docs/commands/{onboarding,ship,status,logs,rollback}.md`
- Create: `.claude/commands/{onboarding,ship,status,logs,rollback}.md`
- Create: `.cursor/commands/{onboarding,ship,status,logs,rollback}.md`

- [ ] **Шаг 1: Перенести тексты команд из эталона**

```bash
SRC=/Users/minas/projects/app-template
mkdir -p docs/commands .claude/commands .cursor/commands
cp $SRC/docs/commands/*.md docs/commands/
cp $SRC/.claude/commands/*.md .claude/commands/
cp $SRC/.cursor/commands/*.md .cursor/commands/
```

- [ ] **Шаг 2: Заменить команды стека в `docs/commands/ship.md`**

Найти блок проверок перед доставкой и заменить на:

```bash
make check
```

Проверку миграций в `docs/commands/rollback.md` заменить с
`prisma/migrations/` на `backend/alembic/versions/`:

```
git diff <точка-отката>..origin/main --stat -- backend/alembic/versions/
```

- [ ] **Шаг 3: Переписать `docs/commands/onboarding.md` под Python-стек**

Заменить раздел проверки окружения:

```markdown
## Проверка окружения

Проверь и поставь недостающее:

- `git`, `gh`
- `uv` (он же принесёт Python 3.14): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Node.js 24 — только для сборки фронтенда; в бою его нет
- PostgreSQL 18

Готовность показывает `node scripts/onboarding-check.mjs`.

**Про первый `make check` на macOS.** Он поставит `import-linter`, а тот тянет
`grimp`, у которого нет готового колеса под Python 3.14 на macOS: под обычный
интерпретатор колёс нет, есть только под free-threaded сборку. Установка
скачает тулчейн Rust и соберёт расширение — это порядка двадцати минут, один
раз на машину. Команда в этот момент выглядит зависшей, но она работает; не
прерывай её. Результат кэшируется, повторные запуски мгновенные. На Linux и в
CI колесо есть, и ничего этого не происходит.
```

и раздел первого запуска:

```markdown
## Первый запуск

    createdb <слаг>_dev && createdb <слаг>_e2e
    cp .env.example .env
    # APP_AUTH_SECRET сгенерировать: openssl rand -hex 32
    make install
    make migrate
    make dev

Приложение отвечает на http://127.0.0.1:5173, вход admin / admin.
```

- [ ] **Шаг 4: Коммит**

```bash
git add docs/commands/ .claude/commands/ .cursor/commands/
git commit -m "docs: команды установки, доставки, состояния, логов и отката"
```

---

### Задача 40: Реестр возможностей

**Files:**
- Create: `CHECKLIST.md`

- [ ] **Шаг 1: Перенести структуру из эталона**

```bash
cp /Users/minas/projects/app-template/CHECKLIST.md CHECKLIST.md
```

- [ ] **Шаг 2: Переписать таблицу «Что приложение умеет»**

```markdown
| Возможность | Состояние | Примечание |
|---|---|---|
| Вход по логину и паролю | `included` | scrypt из stdlib, ограничение попыток по логину и по адресу, выровненное время отказа |
| Первая учётная запись из переменных | `included` | `APP_BOOTSTRAP_*`, пара по умолчанию admin / admin; заводится только при пустой таблице. Пара известна всем, у кого есть шаблон, поэтому на боевом контуре под ней не работают: заводят свою учётную запись и отключают эту. Предупреждение висит на первом экране, пока вход идёт под дефолтной парой |
| Смена пароля в приложении | `absent` | сменить пароль своей учётной записи нельзя — только завести новую и отключить старую |
| Роли viewer / editor / admin | `included` | `require_role` на каждом маршруте, отказ пишется в серверный лог |
| Отключение учётной записи | `included` | закрывает вход и отзывает уже выданные сессии; удаления пользователей нет намеренно |
| Журнал аудита | `included` | пишется той же транзакцией, что и мутация; экран для admin |
| Образцовый раздел «Расходы» | `included` | **удалить**, когда появится первая настоящая фича |
| Стартовая страница | `included` | что это за приложение, ссылки на разделы. Когда появится первая настоящая фича — `/` **переписать** под неё. Саму страницу не удалять: маршрут несущий |
| Страница дизайна `/design` | `included` | все установленные компоненты в рабочих состояниях и примерка пяти тем. Удаляется целиком, когда оформление выбрано; `lib/design/` остаётся |
| Готовые темы оформления | `included` | пять тем, применение командой `npm run theme -- <имя>`; по умолчанию синяя |
| Правила и команды в интерфейсе | `included` | маршрут `/docs`, читает файлы репозитория с диска через `/api/meta/docs` |
| Ежедневная резервная копия базы | `included` | cron заводит провижинер при установке: 14 дней плюс по одной на 1-е число месяца |
| Отслеживание ошибок внешним сервисом | `absent` | решено не брать: обработчик в `core/errors.py` и `/logs` |
| Загрузка файлов и медиа | `absent` | **утверждено владельцем**, приедет спекой слоя данных |
| Очередь и фоновые задачи | `absent` | **утверждено владельцем**, приедет спекой слоя данных |
| Расчёты на pandas и scikit-learn | `absent` | **утверждено владельцем**, приедет спекой слоя данных |
| Внешние модели по API | `absent` | **утверждено владельцем**, приедет спекой слоя данных; появится в `lib/integrations/` с режимом mock/fixture |
| Локальные нейросети (torch) | `removed` | решено не брать: 2,5–3 ГБ зависимостей не встают на общий VPS. **Не возвращать** без отдельного сервера и решения владельца |
| Платежи | `absent` | |
| Задачи по расписанию | `absent` | |
| Почтовые уведомления | `absent` | |
```

- [ ] **Шаг 3: Переписать таблицу «Известный технический долг»**

```markdown
| Что | Когда всплывёт |
|---|---|
| Счётчики попыток входа живут в памяти процесса | Перезапуск их обнуляет. Пока воркер один — это и есть счётчик контура; при нескольких понадобится общее хранилище. Вопрос встанет вместе с очередью |
| `audit_log.actor` — логин строкой, без связи с `users` | Появится переименование логинов — журнал разойдётся с реальностью |
| Провижинер общий с `app-template-ts` | Своей копии `scripts/server/` здесь нет намеренно. Понадобится провижинеру разойтись по языкам — он переезжает в отдельный репозиторий, общий для обоих шаблонов |
```

- [ ] **Шаг 4: Переписать «Проверки окружения»**

```markdown
- [ ] `git`, `uv` (Python 3.14), Node.js 24, PostgreSQL 18, `gh` установлены
- [ ] `git remote -v` проверен, шаблонный origin отвязан
- [ ] `.env` создан из `.env.example`, `APP_AUTH_SECRET` сгенерирован
- [ ] Миграции применены, приложение поднимается локально
- [ ] На сервере установлен `uv`
- [ ] Контур отвечает, первый деплой прошёл
```

- [ ] **Шаг 5: Коммит**

```bash
git add CHECKLIST.md
git commit -m "docs: реестр возможностей и технического долга"
```

---

### Задача 41: README, гайд и проверка готовности

**Files:**
- Create: `README.md`
- Create: `ONBOARDING.md`
- Create: `scripts/onboarding-check.mjs`

- [ ] **Шаг 1: Написать `README.md`**

```markdown
# app-template-py

Стартовое приложение на Python: стек, правила для ИИ-агентов и боевой
контур из коробки. Из него делается новое внутреннее приложение.

**Стек:** FastAPI + Pydantic + SQLAlchemy + Alembic + PostgreSQL; интерфейс
— Vite + React + Tailwind + shadcn/ui. Развёртывание — pm2 и nginx на общем
VPS, доставка — GitHub Actions при merge в `main`.

## Когда брать этот шаблон, а когда `app-template-ts`

Шаблона два, и они равноправны.

- **`app-template-py`** — когда приложению нужен Python: расчёты по
  таблицам, классическое ML, работа с моделями по API, библиотеки, которых
  в JS-мире нет. И просто когда команде на Python привычнее.
- **`app-template-ts`** — когда ничего из этого не нужно. Он проще: одна
  экосистема вместо двух, серверный рендеринг из коробки.

Выбор делается до старта проекта: смены шаблона на ходу не предусмотрено.

## Как развернуть новое приложение

### Шаг 1. Владелец создаёт репозиторий

Руками, в профиле `webkoth`: пустой репозиторий с именем будущего
приложения и роль `admin` специалисту. Права `admin` нужны, чтобы установка
сама завела секреты Actions и ключ деплоя.

### Шаг 2. Специалист клонирует шаблон

```bash
git clone https://github.com/webkoth/app-template-py <имя-приложения>
cd <имя-приложения>
```

### Шаг 3. Специалист открывает папку в своём агенте и запускает установку

**Claude Code или Cursor** — слэш-команда:

```
/onboarding
```

**Codex, Claude Desktop и любой другой агент** — вставь этот промпт:

```text
Это свежая установка из шаблона app-template-py. Прочитай README.md,
CHECKLIST.md и AGENTS.md, затем выполни docs/commands/onboarding.md шаг за
шагом, разговаривая со мной по-русски.

Считай это новым проектом, а не работой над шаблоном: проверь git remote,
отвяжи шаблонный origin и добавь мой репозиторий, когда я дам ссылку.
Анкету CHECKLIST.md заполни моими ответами до начала работы над кодом.
После установки удали блоки Bootstrap-Only из AGENTS.md и CLAUDE.md.
```

## Что где лежит

| Файл | Зачем |
|---|---|
| `AGENTS.md` | правила работы — единственная копия |
| `CLAUDE.md`, `.cursor/rules/` | указатели на `AGENTS.md` |
| `CHECKLIST.md` | что нужно этому приложению; реестр возможностей |
| `ONBOARDING.md` | гайд для нового человека в команде |
| `Makefile` | `make check` перед каждым коммитом |
| `backend/` | FastAPI: фичи, домен, ядро, миграции, тесты |
| `frontend/` | Vite + React: экраны, темы, e2e |
| `docs/commands/` | тексты команд `/onboarding`, `/ship`, `/status`, `/logs`, `/rollback` |
| `docs/superpowers/` | спеки, планы, runbooks |

Провижинера здесь нет: `app-provision` установлен на сервере, а его
исходником владеет `app-template-ts`. Копия означала бы два одинаковых
скрипта в двух репозиториях.

## Работа над самим шаблоном

Если ты правишь шаблон, а не устанавливаешь его: `CHECKLIST.md` остаётся
незаполненным — его ответы уехали бы в каждую будущую установку.
Исключение — реестр возможностей: он всегда описывает текущее состояние
шаблона.
```

- [ ] **Шаг 2: Написать `ONBOARDING.md`**

```markdown
# Как здесь работают

Гайд для человека, который первый раз открыл этот репозиторий.

## Что это

Внутреннее приложение. Его развивают доменные специалисты через ИИ-агента,
не разработчики. Поэтому правила жёстче обычного: то, что в другом проекте
держалось бы на опыте, здесь записано в `AGENTS.md` и проверяется линтером.

## Первый запуск

```bash
createdb <слаг>_dev && createdb <слаг>_e2e
cp .env.example .env
# APP_AUTH_SECRET: openssl rand -hex 32
make install
make migrate
make dev
```

Открой http://127.0.0.1:5173, войди под admin / admin.

## Что нужно знать до первой правки

1. **Ветка `main` — это production.** Каждый merge уезжает к живым людям.
   Отдельного контура, где можно ломать бесплатно, нет.
2. **Перед коммитом — `make check`.** Он же стоит в CI и останавливает
   ветку до merge.
3. **Новая функциональность начинается со спеки**, а не с кода. Порядок:
   спека → план → реализация. Спеки живут в `docs/superpowers/specs/`.
4. **Правила читаются целиком**, а не по диагонали: `AGENTS.md`. Почти
   каждый абзац там написан после конкретной поломки.

## Где что искать

| Вопрос | Где ответ |
|---|---|
| Как устроена фича | `backend/app/features/expenses/` — образец |
| Почему так, а не иначе | `AGENTS.md` и спеки в `docs/superpowers/specs/` |
| Что приложение умеет | `CHECKLIST.md`, таблица возможностей |
| Как доставить | `/ship` или `docs/commands/ship.md` |
| Что на контуре | `/status`, `/logs` |
| Как откатить | `/rollback` |
```

- [ ] **Шаг 3: Написать `scripts/onboarding-check.mjs`**

```javascript
#!/usr/bin/env node
/**
 * Проверка готовности установки. Печатает, чего не хватает, и завершается
 * ненулевым кодом, если установка не закончена.
 *
 * Читает окружение сам: запускается до того, как приложение существует.
 */
import { execSync } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"

const checks = []

function check(label, ok, hint = "") {
  checks.push({ label, ok, hint })
}

function version(command) {
  try {
    return execSync(command, { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim()
  } catch {
    return null
  }
}

check("git установлен", version("git --version") !== null)
check("gh установлен", version("gh --version") !== null, "brew install gh")
check(
  "uv установлен",
  version("uv --version") !== null,
  "curl -LsSf https://astral.sh/uv/install.sh | sh"
)
check("node установлен", version("node --version") !== null)
check("psql установлен", version("psql --version") !== null)

check(".env создан", existsSync(".env"), "cp .env.example .env")

if (existsSync(".env")) {
  const env = readFileSync(".env", "utf8")
  const secret = env.match(/^APP_AUTH_SECRET="?([^"\n]*)"?/m)?.[1] ?? ""
  check(
    "APP_AUTH_SECRET задан",
    secret.length >= 32,
    "openssl rand -hex 32 и вписать в .env"
  )
}

const remote = version("git remote get-url origin") ?? ""
check(
  "origin отвязан от шаблона",
  !remote.includes("app-template-py"),
  "git remote set-url origin <адрес своего репозитория>"
)

const bootstrapLeft =
  existsSync("AGENTS.md") &&
  readFileSync("AGENTS.md", "utf8").includes("BOOTSTRAP_ONLY_START")
check(
  "блоки Bootstrap-Only удалены",
  !bootstrapLeft,
  "удалить блок из AGENTS.md и CLAUDE.md — последний шаг установки"
)

const checklistFilled =
  existsSync("CHECKLIST.md") &&
  !readFileSync("CHECKLIST.md", "utf8").includes("_не отвечено_")
check("CHECKLIST.md заполнен", checklistFilled, "ответы владельца на вопросы установки")

let failed = 0
for (const { label, ok, hint } of checks) {
  console.log(`${ok ? "  ок" : "  НЕТ"}  ${label}${!ok && hint ? ` — ${hint}` : ""}`)
  if (!ok) failed += 1
}

console.log("")
console.log(failed === 0 ? "Установка завершена." : `Осталось шагов: ${failed}`)
process.exit(failed === 0 ? 0 : 1)
```

- [ ] **Шаг 4: Коммит**

```bash
git add README.md ONBOARDING.md scripts/onboarding-check.mjs
git commit -m "docs: README, гайд для команды и проверка готовности установки"
```

---

### Задача 42: Runbook сервера и итоговая проверка

**Files:**
- Create: `docs/superpowers/runbooks/server-setup.md`

- [ ] **Шаг 1: Написать `docs/superpowers/runbooks/server-setup.md`**

```markdown
# Контур на общем VPS

Сервер один и общий: на нём живут все приложения обоих шаблонов.

## Что уже стоит на сервере

`app-provision`, `app-deprovision`, `app-deploy-key`, `app-secret` в
`/usr/local/bin`. Их исходником владеет `app-template-ts` — здесь копии нет
намеренно: две копии расходятся.

`app-provision <слаг>` заводит базу и роль, каталог `/var/www/<слаг>`,
`.env` с секретами, `.deploy-env` с портом из диапазона 3020–3099, два
SSH-ключа, vhost в `/etc/nginx/conf.d/`, сертификат, ночной `pg_dump`,
ops-скрипты и права `ops`. Для Python-приложения он используется **без
правок**: vhost остаётся чистым `proxy_pass`, потому что статику раздаёт
сам FastAPI.

## Что нужно доставить один раз перед первым Python-приложением

`uv` под пользователем `deploy` — так же, как когда-то Node:

    ssh deploy@<сервер>
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    uv --version

Node на сервере **не нужен**: фронтенд собирается в GitHub Actions и
приезжает готовой статикой.

## Установка контура

    ssh ops@<сервер> sudo app-provision <слаг>

Скрипт напечатает адрес, порт и публичный ключ для Deploy keys. Дальше:

1. добавить ключ в репозиторий: Settings → Deploy keys (read-only);
2. приватный ключ для Actions забрать конвейером, не показывая на экране:
   `ssh ops@<сервер> sudo app-deploy-key <слаг> | gh secret set DEPLOY_SSH_KEY`
3. `gh secret set SERVER_HOST` — адрес сервера;
4. первый вход — admin / admin. Сменить сразу: контур открыт снаружи, а
   пара известна всем, у кого есть шаблон.

## Чем процесс держится

pm2, а не systemd — потому что вся эксплуатация сервера на нём:
`<слаг>-status` и `<слаг>-logs` зовут `pm2 describe` и `pm2 logs`, права
`ops` выданы под них, автозапуск после ребута идёт через
`pm2-deploy.service`.

Команда запуска, которую ставит доставка:

    pm2 start /var/www/<слаг>/backend/.venv/bin/python --name <слаг> \
      --cwd /var/www/<слаг>/backend \
      -- -m uvicorn app.main:app --host 127.0.0.1 --port <порт>

Воркер один: счётчики попыток входа живут в памяти процесса, и второй
воркер тихо удвоил бы допустимое число попыток.

`pm2 reload` для не-Node процесса — это перезапуск, а не бесшовная замена:
на доставке контур мигает пару секунд. В TS-шаблоне так же.

## Известное расхождение

`<слаг>-status` проверяет корень, а не `/api/health`. Для SPA корень
отдаёт `index.html` с кодом 200 даже при недоступной базе, то есть скрипт
подтверждает меньше, чем кажется. Настоящую проверку делает доставка. Чтобы
исправить, пришлось бы менять общий провижинер — это решение сразу для двух
шаблонов.
```

- [ ] **Шаг 2: Прогнать всё**

```bash
make check
cd frontend && npx playwright test
```

Expected: обе половины зелёные, 8 e2e passed.

- [ ] **Шаг 3: Проверить обратимость миграций начисто**

```bash
cd backend && uv run alembic downgrade base && uv run alembic upgrade head
```

Expected: обе команды проходят.

- [ ] **Шаг 4: Проверить, что контракты границ держатся**

```bash
cd backend && uv run --group lint lint-imports --config .importlinter
```

Expected: три контракта Kept.

- [ ] **Шаг 5: Коммит**

```bash
git add docs/superpowers/runbooks/
git commit -m "docs: runbook установки контура на общем VPS"
```

---

## Что остаётся владельцу после этого плана

Шаблон готов к установке, но сам по себе на контур не едет: репозиторий на
GitHub, провижининг и секреты Actions — это шаги установки конкретного
приложения, а не работы над шаблоном. Их делает `/onboarding`.

Проверка шаблона на живом сервере — отдельная задача, и делать её стоит так
же, как делали для эталона: развернуть пробное приложение `smoke-app-py` и
пройти установку целиком. У TS-шаблона такой прогон нашёл четыре дефекта,
каждый из которых ломал установку у всех.

Следующая спека — слой данных: загрузка файлов, очередь с воркером,
расчёты на pandas и scikit-learn, клиент внешних моделей и образцовая фича
«загрузили таблицу → посчитали в фоне → показали результат».
