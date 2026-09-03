"""Конфигурация приложения.

Единственное место в коде приложения, где читается окружение. Значений по
умолчанию почти нигде нет намеренно: молча подставленный секрет на новом
контуре — это боевая система с общеизвестной подписью.
"""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator
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
        # inf > 0 истинно, поэтому без этого JOB_STALE_AFTER_SECONDS="1e999"
        # (опечатка в показателе) проходит валидацию — и брошенная задача не
        # возвращается в очередь никогда. Выглядит это как зависший воркер, а
        # не как ошибка в .env, и искать будут в воркере.
        allow_inf_nan=False,
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

    # --- слой данных ---------------------------------------------------
    # Каталог загрузок. Абсолютный и от файла настроек по той же причине,
    # что и ENV_FILE выше: приложение запускают из backend/, а команды make
    # — из корня, и относительный путь дал бы разные каталоги.
    upload_dir: Path = ENV_FILE.parent / "uploads"
    # 32 МиБ. Не про диск — про память: разбор таблицы держит её целиком.
    upload_max_bytes: int = Field(default=32 * 1024 * 1024, gt=0)
    # Опрос очереди. Секунда на фоне долгого счёта незаметна, а LISTEN/NOTIFY
    # — вторая механика ожидания, которую пришлось бы отлаживать отдельно.
    job_poll_seconds: float = Field(default=1.0, gt=0)
    # Отметка живости и срок, после которого задача считается брошенной.
    job_heartbeat_seconds: float = Field(default=10.0, gt=0)
    job_stale_after_seconds: float = Field(default=60.0, gt=0)
    # Три попытки: разрыв связи с базой и перезапуск на доставке проходят
    # сами, а ошибка в данных от повторов не исчезнет. Потолок сверху — про
    # опечатку: JOB_MAX_ATTEMPTS=1000 занимает воркер задачей, которая уже
    # не выполнится, до конца недели.
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    # Режим клиента внешних моделей. mock по умолчанию: шаблон обязан
    # работать сразу, без ключей и без сети.
    integrations_mode: Literal["live", "mock", "fixture"] = "mock"
    # Адрес поставщика и ключ к нему. Пустые умолчания намеренно: в режиме
    # mock они не нужны, а обязательное поле заставило бы заполнять их всех,
    # включая тех, кому внешние модели не нужны вовсе. Пустоту при
    # INTEGRATIONS_MODE=live ловит сам клиент — отказом, а не откатом к mock.
    integrations_url: str = ""
    integrations_api_key: str = ""
    # Сколько ждать ответа. Настройкой, а не числом в коде: у поставщиков
    # разный нрав, и подбирать его придётся на контуре, а не в репозитории.
    #
    # Ожидание касается не только того, кто ждёт. Фоновая задача, стоящая на
    # запросе дольше JOB_STALE_AFTER_SECONDS, считается брошенной, и её
    # берёт второй воркер — запрос уходит поставщику дважды и дважды
    # оплачивается, а первый ответ затирается вторым. Поэтому держи это
    # значение меньше JOB_STALE_AFTER_SECONDS, если внешнюю модель зовут из
    # фоновой задачи. Проверкой это не выражено: клиента зовут и из
    # обработчика запроса, где очереди нет вовсе, и общий запрет мешал бы
    # тем, кого он не касается.
    integrations_timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("upload_dir")
    @classmethod
    def _upload_dir_is_absolute(cls, value: Path) -> Path:
        """Относительный UPLOAD_DIR — три разных каталога вместо одного.

        Ловушка была описана в .env.example и не закрыта ничем: `UPLOAD_DIR=""`
        даёт `Path(".")`, а `uploads` — путь от рабочего каталога процесса.
        Каталогов же три: pm2 запускает приложение с `--cwd .../backend`,
        воркер идёт оттуда же, а команды make — из корня. Файл, загруженный
        минуту назад, оказывается «не найден», и причина не видна ниоткуда.

        Комментарий в образце это не остановит: человек правит свой .env, а
        не образец. Поэтому отказ, и на старте, а не при первой загрузке.
        """
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError(
                "UPLOAD_DIR должен быть абсолютным путём: относительный "
                "считается от рабочего каталога, а у приложения, воркера и "
                "команд make он разный"
            )
        return expanded

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL должна начинаться с postgresql://")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError(
                "на боевом контуре кука сессии обязана быть Secure "
                "(COOKIE_SECURE=true): контур под HTTPS"
            )
        if self.job_stale_after_seconds < 3 * self.job_heartbeat_seconds:
            # Отбор задачи раньше, чем воркер успевает поставить отметку, —
            # это отбор у живого: два воркера считают одно и то же, и второй
            # затирает результат первого.
            #
            # Кратность, а не просто «больше». Проверка «строго больше»
            # пропускала HEARTBEAT=10, STALE=10.001 — то есть ровно ту
            # настройку, от которой поставлена: пропущенная на сборке мусора
            # или на медленной записи отметка отбирает задачу у живого. Запас
            # должен переживать несколько пропусков подряд; в умолчаниях он
            # шестикратный, минимум здесь — трёхкратный.
            raise ValueError(
                "JOB_STALE_AFTER_SECONDS должен быть втрое больше "
                "JOB_HEARTBEAT_SECONDS: иначе задача отбирается у живого "
                "воркера, пропустившего одну отметку"
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
