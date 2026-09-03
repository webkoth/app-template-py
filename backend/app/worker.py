"""Процесс воркера: берёт задачу из очереди и зовёт обработчик.

Отдельный процесс, а не фоновая задача внутри приложения. Доставка
перезапускает процессы, и счёт, живущий внутри веб-процесса, она убивала бы
на каждом выкате. Плюс долгий счёт конкурировал бы за процесс с
обслуживанием запросов.

Реестр обработчиков собирается здесь списком — ровно как `main.py` собирает
роутеры. Сами обработчики живут в своих фичах: удаляя фичу, удаляешь и её
фоновую работу, не вспоминая про чужой реестр.

`app.main` отсюда НЕ импортируется, и это проверяется тестом: воркер,
притащивший веб-приложение, наследует и время его старта, и его отказы.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.config import settings
from app.core.db import SessionFactory
from app.core.jobs import Job
from app.features.datasets import jobs as dataset_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, Job], Awaitable[dict[str, Any]]]

HANDLERS: dict[str, Handler] = {
    **dataset_jobs.HANDLERS,
}


async def run_once(session: AsyncSession) -> bool:
    """Один оборот: взять задачу и выполнить. False — брать было нечего."""
    job = await jobs.claim(session)
    if job is None:
        return False

    handler = HANDLERS.get(job.kind)
    if handler is None:
        # Не исключение: задача вида, которого нет в реестре, — это забытая
        # регистрация при выкатке. Уронив на ней воркер, мы остановили бы
        # ВСЮ очередь из-за одной задачи, и причина не была бы видна ни на
        # одном экране.
        await jobs.fail(session, job, f"Неизвестный вид задачи: {job.kind}")
        logger.error("нет обработчика для вида %s", job.kind)
        return True

    try:
        result = await handler(session, job)
    except Exception as failure:
        # Широко намеренно. Обработчик — чужой код фичи, и любой его отказ
        # обязан стать причиной на экране, а не остановкой очереди. Текст
        # уходит человеку, трейсбек — в лог.
        # Откат обязателен ПЕРЕД записью причины: обработчик мог упасть на
        # середине (`datasets.parse` добавляет строки пачками), и без отката
        # commit внутри `jobs.fail` унёс бы в базу мусор недоделанной работы
        # или упал бы на нём сам — задача осталась бы «выполняющейся» без
        # причины в поле error.
        await session.rollback()
        # Но откат ещё и помечает объекты сессии устаревшими, а `jobs.fail`
        # первым делом читает `job.attempts`. Устаревшее поле в async-коде
        # тянет догрузку синхронно и падает MissingGreenlet — то есть
        # причина не записалась бы ВСЁ РАВНО, только теперь из-за самого
        # отката. Обновляем явно, одним асинхронным запросом. Проверено:
        # без этой строки отказ обработчика не доходит до базы вовсе.
        await session.refresh(job)
        await jobs.fail(session, job, str(failure) or failure.__class__.__name__)
        logger.exception("задача %s (%s) не выполнена", job.id, job.kind)
        return True

    await jobs.complete(session, job, result)
    return True


async def loop() -> None:
    logger.info("воркер запущен, обработчиков: %d", len(HANDLERS))
    while True:
        async with SessionFactory() as session:
            try:
                took = await run_once(session)
            except Exception:
                # Сюда попадает только то, что сломалось ВНЕ обработчика:
                # оборвалась связь с базой, не записался результат. Цикл не
                # должен умирать от этого — пауза и следующий оборот.
                logger.exception("оборот воркера не удался")
                took = False
        if not took:
            await asyncio.sleep(settings.job_poll_seconds)


if __name__ == "__main__":
    asyncio.run(loop())
