import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core import jobs
from app.core.jobs import Job, JobStatus


async def test_enqueue_does_not_commit_by_itself(session):
    # Постановка кладёт строку в ТУ ЖЕ сессию, что и данные, и коммитит их
    # вместе вызывающий. Иначе появляется состояние «задача поставлена, а
    # строки, ради которой она поставлена, нет» — и воркер берёт задачу на
    # данные, которых не существует.
    jobs.enqueue(session, kind="проба", payload={"a": 1}, actor="boss")
    await session.rollback()
    assert (await session.execute(select(Job))).first() is None


async def test_enqueued_job_waits_in_the_queue(session):
    jobs.enqueue(session, kind="проба", payload={"a": 1}, actor="boss")
    await session.commit()
    job = (await session.execute(select(Job))).scalar_one()
    assert job.status is JobStatus.queued
    assert job.attempts == 0
    assert job.progress == 0
    assert job.payload == {"a": 1}


async def test_two_workers_never_take_the_same_job(new_session):
    # Одну задачу берёт ровно один воркер. Гарантирует это БЛОКИРОВКА
    # СТРОКИ — `with_for_update`, — а не наша аккуратность, и проверяется
    # поэтому настоящей одновременностью, на отдельных соединениях.
    #
    # Проверено на живой базе, что бывает без неё: две транзакции читают
    # одну и ту же строку, обе объявляют её своей, а следующая задача так и
    # остаётся ждать. То есть один воркер считает впустую, второй затирает
    # его результат, и очередь при этом кажется движущейся.
    #
    # `skip_locked` к этому отношения не имеет — ему посвящён следующий
    # тест, и охраняет он другое.
    #
    # Прогрев перед гонкой — условие проверки, а не украшение. Без него
    # мутация «убрать with_for_update» тест НЕ роняла: на холодном
    # соединении первый запрос тратит лишние круги на установку связи и
    # подготовку инструкции, второй воркер приходил к строке, которую
    # первый уже успел забрать целиком, и гонки не было вовсе. Замерено на
    # заведомо дырявом коде: без прогрева нарушение ловилось в 1 прогоне из
    # 10, с прогревом — в 20 из 20. Прогревают тем же запросом на пустой
    # очереди: он открывает соединение, готовит инструкцию и заодно
    # проверяет, что пустая очередь — это None.
    async def take(db) -> uuid.UUID | None:
        job = await jobs.claim(db)
        return job.id if job else None

    try:
        async with new_session() as one, new_session() as two:
            assert await jobs.claim(one) is None, "пустая очередь — это None"
            assert await jobs.claim(two) is None

            async with new_session() as setup:
                jobs.enqueue(setup, kind="проба", payload={}, actor="boss")
                await setup.commit()

            first, second = await asyncio.gather(take(one), take(two))

        assert (first, second) != (None, None), "задачу не взял никто"
        assert first is None or second is None, (first, second)
    finally:
        # Уборка в finally: строка тут коммитится по-настоящему, и упавшая
        # проверка иначе оставляет её следующим тестам файла. Первый же
        # разбор на этом и застрял — соседний тест падал на чужой задаче, и
        # причина выглядела как его собственная поломка.
        async with new_session() as cleanup:
            for row in (await cleanup.execute(select(Job))).scalars().all():
                await cleanup.delete(row)
            await cleanup.commit()


async def test_a_locked_row_does_not_hide_the_next_job(new_session):
    # А это смысл SKIP LOCKED, и он ДРУГОЙ, чем кажется. Взятие одной
    # задачи двумя воркерами запрещает блокировка и без него: второй просто
    # ждёт, пока первый отпустит строку, и уходит ни с чем. Разница в том,
    # чего это стоит, и она измерена на живой базе: 0,03 с против 1,15 с,
    # проведённых в ожидании чужого коммита. Всё это время воркер не берёт
    # СЛЕДУЮЩУЮ задачу, хотя она свободна.
    #
    # Поэтому проверка такая: первая строка заперта незакрытой транзакцией,
    # в очереди есть вторая задача, и claim обязан вернуть именно её. Без
    # skip_locked=True он повиснет на запертой строке — не «отработает
    # медленнее», а не вернётся вовсе, пока держат замок. Отсюда wait_for:
    # без него красный тест выглядел бы как зависший прогон.
    async with new_session() as setup:
        jobs.enqueue(setup, kind="первая", payload={}, actor="boss")
        await setup.commit()
        jobs.enqueue(setup, kind="вторая", payload={}, actor="boss")
        await setup.commit()

    try:
        async with new_session() as holder:
            held = (
                await holder.execute(
                    select(Job).order_by(Job.created_at).limit(1).with_for_update()
                )
            ).scalar_one()
            assert held.kind == "первая"
            # Транзакция holder НЕ закрыта: строка заперта до конца блока.

            async with new_session() as second:
                job = await asyncio.wait_for(jobs.claim(second), timeout=5)

            assert job is not None, "запертая строка спрятала свободную задачу"
            assert job.kind == "вторая"
    finally:
        async with new_session() as cleanup:
            for row in (await cleanup.execute(select(Job))).scalars().all():
                await cleanup.delete(row)
            await cleanup.commit()


async def test_claiming_marks_the_job_running(session):
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    assert job.status is JobStatus.running
    assert job.attempts == 1
    assert job.started_at is not None
    assert job.heartbeat_at is not None


async def test_stale_running_job_returns_to_the_queue(session):
    # Воркер, убитый доставкой, оставляет задачу «выполняющейся». Без
    # возврата человек ждёт результата, которого не будет: задача выглядит
    # живой, а брать её некому.
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    taken = await jobs.claim(session)
    assert taken is not None
    taken.heartbeat_at = datetime.now(UTC) - timedelta(seconds=3600)
    await session.commit()

    again = await jobs.claim(session)
    assert again is not None
    assert again.id == taken.id
    assert again.attempts == 2


async def test_a_living_job_is_not_taken_away(session):
    # Обратная сторона: свежая отметка означает, что воркер жив и считает.
    #
    # Охраняет тест именно СРОК: мутация «срок протухания ноль» роняет его и
    # только его. Напрашивающаяся мутация «не ставить heartbeat_at в claim»
    # роняет не его, а тесты про взятие и про отметку — и это не изъян, а
    # свойство SQL: сравнение NULL с чем угодно даёт NULL, то есть задача
    # без отметки для claim не протухшая, а неприкасаемая.
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    assert await jobs.claim(session) is not None
    assert await jobs.claim(session) is None


async def test_heartbeat_moves_the_mark_and_the_progress(session):
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    before = job.heartbeat_at
    await asyncio.sleep(0.01)
    await jobs.heartbeat(session, job, progress=42)
    assert job.progress == 42
    assert job.heartbeat_at > before


async def test_failure_returns_the_job_until_attempts_run_out(session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "job_max_attempts", 2)
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()

    first = await jobs.claim(session)
    assert first is not None
    await jobs.fail(session, first, "связь оборвалась")
    assert first.status is JobStatus.queued, "первая неудача — не приговор"

    second = await jobs.claim(session)
    assert second is not None
    await jobs.fail(session, second, "связь оборвалась")
    assert second.status is JobStatus.failed
    assert second.error == "связь оборвалась"
    assert second.finished_at is not None


async def test_a_running_job_without_a_mark_is_not_stuck_forever(session):
    # Обратная сторона протухания, и она не симметрична: сравнение с NULL в
    # SQL даёт NULL, поэтому «выполняется, отметки нет» — это не «свежая
    # задача», а строка, невидимая для отбора навсегда. Экран показывал бы
    # живую работу, человек ждал бы результата, которого не будет.
    #
    # Такая строка появляется только при ошибке в коде или правке руками —
    # и именно поэтому очередь обязана из неё выбираться сама.
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    taken = await jobs.claim(session)
    assert taken is not None
    taken.heartbeat_at = None
    await session.commit()

    again = await jobs.claim(session)
    assert again is not None, "задача без отметки осталась бы running навсегда"
    assert again.id == taken.id


async def test_progress_outside_the_scale_is_clamped(session):
    # Прогресс считает сам обработчик — делением на число строк, — а рисует
    # по нему полосу экран. Пустая таблица, лишняя строка, округление: 101
    # или -1 получить легко. Обрезка не проверялась ничем: мутация
    # `job.progress = progress` не роняла ни одного теста.
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    await jobs.heartbeat(session, job, progress=1000)
    assert job.progress == 100
    await jobs.heartbeat(session, job, progress=-5)
    assert job.progress == 0


async def test_completion_stores_the_result(session):
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    await jobs.complete(session, job, {"строк": 7})
    assert job.status is JobStatus.done
    assert job.result == {"строк": 7}
    assert job.progress == 100
    assert job.finished_at is not None


async def test_error_text_is_cut_not_dropped(session):
    # Трейсбек длиннее колонки отменил бы саму запись об отказе — то есть
    # задача осталась бы «выполняющейся» из-за слишком подробной причины.
    # Та же логика, что у detail в журнале аудита.
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    await jobs.fail(session, job, "щ" * 5000)
    assert len(job.error) <= jobs.ERROR_MAX
    assert job.error.endswith("…")
