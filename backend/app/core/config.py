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
        return bool(
            self.app_bootstrap_login.strip() and self.app_bootstrap_password.strip()
        )

    @property
    def async_database_url(self) -> str:
        """Адрес для SQLAlchemy с асинхронным драйвером.

        Провижинер пишет в .env обычный postgresql:// — его же читает Alembic
        и psql. Драйвер подставляется здесь, чтобы общий app-provision,
        которым пользуется и TS-шаблон, остался нетронутым.
        """
        return _with_async_driver(self.database_url)

    @property
    def async_database_url_e2e(self) -> str | None:
        """То же для отдельной базы под тесты.

        Тесты создают и удаляют схему целиком, поэтому идти в рабочую базу
        им нельзя ни при каких условиях: после прогона там не осталось бы
        таблиц, а alembic_version продолжал бы показывать head — то есть
        приложение перестало бы стартовать, а миграции считали бы, что
        накатывать нечего.
        """
        if not self.database_url_e2e:
            return None
        return _with_async_driver(self.database_url_e2e)


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


def _with_async_driver(url: str) -> str:
    """Подставляет асинхронный драйвер, сохраняя остальную часть адреса."""
    _, rest = url.split("://", 1)
    return f"postgresql+asyncpg://{rest}"


settings = load_settings()
