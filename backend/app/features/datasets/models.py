"""ОБРАЗЕЦ слоя данных. Показывает путь «файл → очередь → счёт → результат».

Удаляется, когда появится первая настоящая фича этого слоя, — как и
«Расходы» для простого пути. Оба образца учат разному и уходят независимо.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(String(255))
    # Идентификатор файла на диске. Настоящее имя лежит рядом и на диск не
    # попадает: файл, названный «../../.env», иначе стал бы путём.
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    original_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    # Сводка появляется после разбора. NULL означает «ещё не считали», а не
    # «посчитали и вышло пусто»: это разные состояния, и экран показывает их
    # по-разному.
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rows_count: Mapped[int] = mapped_column(Integer, default=0)
    # Логин строкой, как в журнале аудита и в очереди, и по той же причине:
    # запись обязана пережить учётную запись, которая её завела.
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class DatasetRow(Base):
    """Разобранная строка таблицы.

    Строки живут в базе, а не читаются из файла заново, и это главное
    решение фичи: в ночную копию контура попадает база, а не диск. Файл —
    исходник, который можно потерять; разобранное — работа, которую терять
    нельзя.
    """

    __tablename__ = "dataset_rows"
    # Порядок колонок в индексе — под единственный горячий запрос: строки
    # одной таблицы по порядку номеров.
    #
    # unique=True — отступление от плана, и вот зачем. Пара (таблица, номер)
    # — это МЕСТО строки, второго такого места быть не может, и держать это
    # обязана база. Разбор идёт в фоне, задачу возвращает отметка живости
    # или перезапуск руками, а обработчик успевает коммитить частями: без
    # уникальности повторный проход поверх живого даёт удвоенные строки при
    # сводке от первого прохода. Молча — расхождение видно только счётом
    # строк. С уникальностью второй проход падает, задача уходит в отказ и
    # человек видит причину.
    #
    # Идемпотентность обработчика (удалить строки таблицы, потом вставить
    # заново) это не отменяет и ей не мешает: последовательный повтор как
    # проходил, так и проходит.
    __table_args__ = (
        Index("ix_dataset_rows_dataset_id_index", "dataset_id", "index", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    # ondelete CASCADE: удаляя таблицу, удаляем и её строки. Без этого
    # осиротевшие строки копятся молча — их не видно ни на одном экране.
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE")
    )
    index: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ModelArtifact(Base):
    """Обученная модель.

    Хранится в базе, а не на диске, по той же причине, что и строки: это
    производное, и оно обязано попадать в ночную копию.

    Версия и метка времени хранятся намеренно: модель, обученную на данных,
    которых больше нет, надо отличать от свежей, не поднимая историю
    загрузок.
    """

    __tablename__ = "model_artifacts"
    # Одна задача — одна модель, и держит это база. Причина та же, что у
    # уникальности строк таблицы: обучение идёт в фоне, задачу возвращает
    # протухшая отметка живости или перезапуск воркера доставкой между
    # `commit` обработчика и `jobs.complete` — и второй проход без этого
    # кладёт ВТОРУЮ модель. Молча: обе видны на экране моделей, обе
    # выглядят настоящими, и человек выбирает из них, чем предсказывать.
    #
    # Идемпотентность обработчика (удалить прежний артефакт этой задачи,
    # потом вставить) это не отменяет: она делает повтор тихим, а
    # уникальность — обязательным. Разъедутся — второй проход упадёт
    # громко, а не удвоит модели.
    __table_args__ = (Index("ix_model_artifacts_job_id", "job_id", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE")
    )
    # Задача, которая обучила модель. Nullable по двум причинам сразу:
    # артефакты, обученные до появления колонки, своей задачи не знают, а
    # `ondelete=SET NULL` оставляет модель жить, когда старую задачу
    # убирают из очереди — терять обученное вместе с записью о работе
    # нельзя. Уникальному индексу это не мешает: в PostgreSQL NULL не
    # конфликтует с NULL.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    target_column: Mapped[str] = mapped_column(String(255))
    feature_columns: Mapped[list[str]] = mapped_column(JSONB)
    algorithm: Mapped[str] = mapped_column(String(64))
    metric_name: Mapped[str] = mapped_column(String(32))
    # Float назван явно, а не выведен из аннотации. Тип здесь несёт смысл:
    # метрика — дробь, и целочисленная колонка не отказала бы, а округлила
    # бы 0,81 до 1 — то есть негодная модель выглядела бы безупречной.
    metric_value: Mapped[float] = mapped_column(Float)
    # Сама модель, сериализованная joblib. Это НАШ артефакт, а не чужой
    # файл: загружать сюда что-либо извне нельзя — распаковка pickle
    # исполняет код.
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
