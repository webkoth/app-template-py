"""Конфигурация приложения.

Единственное место в коде приложения, где читается окружение. Значений по
умолчанию почти нигде нет намеренно: молча подставленный секрет на новом
контуре — это боевая система с общеизвестной подписью.
"""

from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Лишние переменные в окружении сервера — норма (их кладёт pm2),
        # и падать из-за них приложение не должно.
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(description="Адрес PostgreSQL")
    app_env: Literal["local", "production"] = "local"
    # validation_alias задан явно: без него pydantic пишет в ошибке валидации
    # питоновское имя поля (app_auth_secret), а не имя переменной окружения
    # (APP_AUTH_SECRET), и сообщение об отсутствующем секрете не помогает
    # понять, какую переменную завести на контуре.
    app_auth_secret: str = Field(min_length=32, validation_alias="APP_AUTH_SECRET")
    cookie_secure: bool = False

    # Отдельная база для e2e: тесты создают и меняют данные, и делать это в
    # рабочей базе нельзя.
    database_url_e2e: str | None = None

    # Первая учётная запись. Значения по умолчанию стоят здесь, а не только в
    # .env.example: контур без этих переменных должен пускать той же парой, а
    # не оставаться без входа вовсе. Проверки силы пароля нет намеренно — она
    # противоречила бы заданному значению.
    #
    # Пустое значение любой из двух переменных выключает bootstrap: это способ
    # отказаться от него, когда учётные записи заводят иначе.
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
    def async_database_url(self) -> str:
        """Адрес для SQLAlchemy с асинхронным драйвером.

        Провижинер пишет в .env обычный postgresql:// — его же читает Alembic
        и psql. Драйвер подставляется здесь, чтобы общий app-provision,
        которым пользуется и TS-шаблон, остался нетронутым.
        """
        _, rest = self.database_url.split("://", 1)
        return f"postgresql+asyncpg://{rest}"


# Обязательные поля (database_url, app_auth_secret) не имеют значений по
# умолчанию — mypy этого не знает и требует их аргументами конструктора,
# хотя pydantic-settings подставит их из окружения. Это штатное расхождение
# между строгим mypy и BaseSettings, а не ошибка в коде.
settings = Settings()  # type: ignore[call-arg]
