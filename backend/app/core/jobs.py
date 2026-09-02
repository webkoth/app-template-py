"""Очередь фоновых задач.

Очередь живёт в той же базе, что и данные, — и это главное её свойство, а не
экономия на инфраструктуре. Постановка задачи и запись строки, ради которой
она ставится, попадают в одну транзакцию: состояния «задача есть, данных
нет» не существует.

Взятие — SELECT … FOR UPDATE SKIP LOCKED, и две его половины отвечают за
разное. FOR UPDATE запирает строку: одну задачу берёт ровно один воркер, и
это гарантирует база, а не аккуратность кода. SKIP LOCKED отвечает не за
это, а за то, что воркер, наткнувшийся на запертую строку, берёт следующую
задачу вместо того, чтобы ждать на чужом коммите. Проверено обеими
проверками отдельно: без FOR UPDATE задачу берут двое, без SKIP LOCKED — не
берёт никто, пока держат замок.
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, Index, Integer, String, Uuid, and_, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.db import Base

# Предел колонки error — он же предел того, что очередь готова запомнить о
# причине отказа.
ERROR_MAX = 1024


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Job(Base):
    __tablename__ = "jobs"
    # Индекс под единственный горячий запрос — взятие задачи. Он же
    # обслуживает экран: список сортируется по времени создания.
    __table_args__ = (Index("ix_jobs_status_created_at", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    # Вид задачи — ключ реестра обработчиков в app/worker.py. Строка, а не
    # enum базы: список обработчиков живёт в коде фич и меняется чаще, чем
    # стоит менять схему.
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            values_callable=lambda e: [i.value for i in e],
        ),
        default=JobStatus.queued,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str] = mapped_column(String(ERROR_MAX), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Логин строкой, как в журнале аудита, и по той же причине: задача
    # обязана пережить учётную запись, которая её поставила.
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Отметка живости. Пока она свежая, задача считается выполняемой.
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


def enqueue(
    session: AsyncSession, kind: str, payload: dict[str, Any], actor: str
) -> Job:
    """Кладёт задачу в ту же сессию, что и данные. Без commit — намеренно.

    Коммитит вызывающий, вместе со своей записью. Отдельный commit здесь
    создал бы состояние «задача поставлена, строки нет»: воркер взял бы её
    раньше, чем данные появились, и упал бы на пустом месте — а причину
    искали бы в обработчике.
    """
    job = Job(kind=kind, payload=payload, actor=actor)
    session.add(job)
    return job


async def claim(session: AsyncSession) -> Job | None:
    """Берёт одну задачу и помечает выполняемой. None — брать нечего.

    Один запрос делает две вещи разом: берёт ожидающую задачу И
    возвращает брошенную. Отдельного уборщика зависших нет намеренно —
    он был бы вторым местом, где живёт понятие «задача брошена», и эти два
    места однажды разъехались бы.
    """
    stale_before = datetime.now(UTC) - timedelta(
        seconds=settings.job_stale_after_seconds
    )
    job = (
        await session.execute(
            select(Job)
            .where(
                or_(
                    Job.status == JobStatus.queued,
                    and_(
                        Job.status == JobStatus.running,
                        # Пустая отметка сюда НЕ попадает: сравнение с NULL
                        # даёт NULL, и строка не отбирается. Так и нужно —
                        # отметку ставит сам claim, и её отсутствие у
                        # выполняемой задачи означает ошибку в коде, а не
                        # мёртвого воркера. Считать такую строку брошенной
                        # значило бы раздавать одну задачу всем воркерам
                        # подряд, каждому по разу.
                        Job.heartbeat_at < stale_before,
                    ),
                )
            )
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if job is None:
        return None

    now = datetime.now(UTC)
    job.status = JobStatus.running
    job.attempts += 1
    job.started_at = now
    job.heartbeat_at = now
    await session.commit()
    return job


async def heartbeat(session: AsyncSession, job: Job, progress: int) -> None:
    """Отметка живости и прогресс. Зовётся обработчиком по ходу счёта."""
    job.progress = max(0, min(100, progress))
    job.heartbeat_at = datetime.now(UTC)
    await session.commit()


async def complete(session: AsyncSession, job: Job, result: dict[str, Any]) -> None:
    job.status = JobStatus.done
    job.result = result
    job.progress = 100
    job.finished_at = datetime.now(UTC)
    await session.commit()


async def fail(session: AsyncSession, job: Job, error: str) -> None:
    """Неудача. Возвращает задачу в очередь, пока не исчерпаны попытки.

    Обрезка текста, а не отказ от записи: причина длиннее колонки отменила
    бы саму запись об отказе, и задача осталась бы «выполняющейся» — из-за
    слишком подробного объяснения, почему она не выполнилась. Та же логика,
    что у detail в журнале аудита.
    """
    job.error = error if len(error) <= ERROR_MAX else error[: ERROR_MAX - 1] + "…"
    if job.attempts >= settings.job_max_attempts:
        job.status = JobStatus.failed
        job.finished_at = datetime.now(UTC)
    else:
        job.status = JobStatus.queued
        job.heartbeat_at = None
    await session.commit()
