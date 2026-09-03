import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # uuid.UUID, а не str: pydantic строку из UUID сам не делает. В JSON поле
    # всё равно уезжает строкой, а в схеме получает format: uuid.
    id: uuid.UUID
    name: str
    original_name: str
    size_bytes: int
    kind: str
    # None означает «ещё не считали». Экран показывает это иначе, чем
    # посчитанную пустую сводку: первое — работа идёт, второе — работа
    # закончена и в таблице ничего не нашлось.
    summary: dict[str, Any] | None
    # Почему сводки нет. Пустая сводка сама по себе означает и «считаем», и
    # «разбор упал» — на экране это одна и та же строка, и человек ждёт
    # результата, которого не будет.
    #
    # Причина живёт в задаче, но список задач видят только поставивший её и
    # администратор, а список таблиц — каждый вошедший. То есть viewer,
    # глядящий на чужую застрявшую таблицу, причины не увидел бы. Права на
    # очередь при этом ослаблять нельзя: в задачах лежит чужая работа
    # целиком. Поэтому причина приезжает вместе с ТАБЛИЦЕЙ, к которой
    # относится, — тому, кто эту таблицу и так видит.
    # Умолчание None обязательно: поля с таким именем у строки таблицы нет,
    # оно приезжает из очереди и подставляется роутером. Без умолчания
    # model_validate падает на КАЖДОЙ таблице — «поле обязательно».
    parse_error: str | None = None
    rows_count: int
    actor: str
    created_at: datetime


class TrainRequest(BaseModel):
    # Лишнее поле — ошибка, а не мусор, который молча выбрасывают, как и в
    # остальных формах проекта.
    model_config = ConfigDict(extra="forbid")

    target_column: str = Field(min_length=1, max_length=255)


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # dict[str, float], а не dict[str, Any]: признаки у обученной модели
    # только числовые, и разбор строки в число — работа схемы, а не сервиса.
    row: dict[str, float]


class ModelOut(BaseModel):
    """Модель для списка. Без `payload` — намеренно.

    Артефакт весит, человеку не нужен, а лишний путь наружу для
    сериализованной модели заводить незачем: то, что не отдаётся, нельзя и
    подменить обратно.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    target_column: str
    feature_columns: list[str]
    algorithm: str
    metric_name: str
    metric_value: float
    actor: str
    created_at: datetime
