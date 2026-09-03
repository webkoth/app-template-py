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

# Причина, которую очередь пишет сама, — единственный отказ, о котором
# рассказать некому: воркер умер, не дойдя ни до результата, ни до
# исключения. Текст называет число попыток, потому что «задача не
# выполнилась» без него человек читает как поломку своей таблицы, а дело в
# том, что счёт не переживают.
_ABANDONED = (
    "Задачу брали {attempts} раз(а), и ни разу счёт не дошёл до конца — "
    "воркер не пережил её. Попытки исчерпаны."
)


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


async def _abandoned_or_waiting(session: AsyncSession) -> Job | None:
    """Одна строка-кандидат: ожидающая ИЛИ брошенная. None — нет таких.

    Один запрос делает две вещи разом: берёт ожидающую задачу И
    возвращает брошенную. Отдельного уборщика зависших нет намеренно —
    он был бы вторым местом, где живёт понятие «задача брошена», и эти два
    места однажды разъехались бы.
    """
    stale_before = datetime.now(UTC) - timedelta(
        seconds=settings.job_stale_after_seconds
    )
    return (
        await session.execute(
            select(Job)
            .where(
                or_(
                    Job.status == JobStatus.queued,
                    and_(
                        Job.status == JobStatus.running,
                        or_(
                            # Пустая отметка проверяется ОТДЕЛЬНО, а не
                            # сравнением: `NULL < stale_before` в SQL даёт
                            # NULL, то есть такая строка не «свежая», а
                            # невидимая для отбора — навсегда. Задача
                            # осталась бы «выполняющейся», экран показывал бы
                            # живую работу, и человек ждал бы результата,
                            # которого не будет: ровно тот молчаливый отказ,
                            # ради которого отметка и заведена.
                            #
                            # Раздачей одной задачи всем воркерам подряд это
                            # не оборачивается: claim, забирая её, сразу
                            # ставит отметку, дальше действуют обычные
                            # правила, а число попыток ограничено сверху.
                            #
                            # Строка «running без отметки» появляется только
                            # при ошибке в коде или правке руками. Чинить
                            # такое молчанием — худший из вариантов.
                            Job.heartbeat_at.is_(None),
                            Job.heartbeat_at < stale_before,
                        ),
                    ),
                )
            )
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()


async def claim(session: AsyncSession) -> Job | None:
    """Берёт одну задачу и помечает выполняемой. None — брать нечего.

    Кандидатов подбирает `_abandoned_or_waiting`, а здесь решается, что с
    кандидатом делать: взять или закрыть отказом по исчерпанным попыткам.

    Потолок попыток проверяется ИМЕННО ЗДЕСЬ, а не только в `fail`. `fail`
    зовёт воркер, поймав исключение обработчика, — то есть только тогда,
    когда воркер жив и успел сказать. Отказ, при котором он ничего сказать
    не успевает (OOM, kill -9, перезапуск доставкой посреди счёта), до
    `fail` не доходит вовсе: задача остаётся `running`, протухает, берётся
    снова — и так без конца. Проверено на живой базе: при потолке в 3
    попытки задача доходила до attempts=7 с пустым `error`. Воркер один,
    поэтому вставала вся очередь, а на экране это выглядело идущей работой:
    отметку живости только что поставил сам `claim`, и предупреждение
    «задачи некому взять» не появлялось.

    Просто перестать брать такую задачу нельзя — она стала бы невидимой
    навсегда, то есть тем же молчанием с другой стороны, и заслонила бы
    собой очередь: `claim` берёт самую старую подходящую. Поэтому она
    закрывается отказом с человеческой причиной, и берётся следующая.
    """
    while True:
        job = await _abandoned_or_waiting(session)
        if job is None:
            return None

        if (
            job.status is JobStatus.running
            and job.attempts >= settings.job_max_attempts
        ):
            # Отказ пишется через `fail`, а не своей строкой: «как задача
            # умирает» обязано жить в одном месте — там обрезка текста,
            # отметка времени и решение про статус.
            #
            # Условие смотрит на `running`, а не на любую задачу с
            # исчерпанными попытками. Очередь с `queued` и attempts на
            # потолке появляется только при опущенной на ходу настройке, и
            # в её `error` уже лежит настоящая причина прошлого отказа —
            # затерев её выдуманной, мы потеряли бы единственный текст,
            # который человек прочитает. Такая задача пойдёт обычным путём
            # и закроется по своей причине.
            await fail(session, job, _ABANDONED.format(attempts=job.attempts))
            # Следующий круг: закрытая задача под отбор больше не попадает,
            # поэтому цикл конечен.
            continue

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
