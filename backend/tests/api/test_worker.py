from sqlalchemy import select

from app.core import jobs
from app.core.jobs import Job, JobStatus


async def test_handler_result_lands_in_the_job(session, monkeypatch):
    from app import worker

    async def handler(db, job):
        return {"эхо": job.payload["значение"]}

    monkeypatch.setitem(worker.HANDLERS, "проба", handler)
    jobs.enqueue(session, kind="проба", payload={"значение": 7}, actor="boss")
    await session.commit()

    took = await worker.run_once(session)
    assert took is True
    job = (await session.execute(select(Job))).scalar_one()
    assert job.status is JobStatus.done
    assert job.result == {"эхо": 7}


async def test_unknown_kind_fails_the_job_instead_of_the_worker(session, monkeypatch):
    # Задача вида, которого нет в реестре, — это забытая регистрация
    # обработчика при выкатке. Ронять на ней воркер значит останавливать
    # ВСЮ очередь из-за одной задачи: остальные перестанут выполняться, и
    # причина будет не видна ни на одном экране.
    #
    # Попытка одна намеренно. Сколько раз повторять неудачу — политика
    # очереди (`jobs.fail`), а не решение воркера: при трёх попытках задача
    # после первого оборота вернулась бы в очередь — с уже записанной
    # причиной, но ещё не в конечном состоянии, и проверять пришлось бы
    # число оборотов вместо самого свойства.
    from app import worker

    monkeypatch.setattr(worker.settings, "job_max_attempts", 1)
    jobs.enqueue(session, kind="такого-нет", payload={}, actor="boss")
    await session.commit()

    assert await worker.run_once(session) is True
    job = (await session.execute(select(Job))).scalar_one()
    assert job.status is JobStatus.failed
    assert "такого-нет" in job.error


async def test_handler_failure_is_written_not_swallowed(session, monkeypatch):
    from app import worker

    async def handler(db, job):
        raise ValueError("в таблице нет колонки «сумма»")

    monkeypatch.setitem(worker.HANDLERS, "проба", handler)
    monkeypatch.setattr(worker.settings, "job_max_attempts", 1)
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()

    await worker.run_once(session)
    job = (await session.execute(select(Job))).scalar_one()
    assert job.status is JobStatus.failed
    assert "нет колонки" in job.error


async def test_empty_queue_reports_nothing_taken(session):
    from app import worker

    assert await worker.run_once(session) is False


def test_worker_does_not_import_the_web_application():
    # Воркер, притащивший app.main, тянет за собой и время старта
    # приложения, и его отказы: не поднялась раздача статики — не считаются
    # задачи. Проверяется по факту импорта, а не по чтению кода.
    import subprocess
    import sys

    probe = "import sys, app.worker;sys.exit(1 if 'app.main' in sys.modules else 0)"
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    # stderr в сообщении: без него несостоявшийся импорт (опечатка, битое
    # окружение) даёт тот же код 1, что и притащенный app.main, и отказ
    # читался бы как нарушение границы.
    assert done.returncode == 0, done.stderr


async def test_a_failed_handler_leaves_neither_rows_nor_silence(
    new_session, monkeypatch
):
    # Охраняет `session.rollback()` ПЕРЕД `jobs.fail`, и без него не падал
    # ни один из тестов выше — проверено мутацией на всём tests/api.
    #
    # Обработчик фичи устроен ровно так: `datasets.parse` добавляет строки
    # пачками и может упасть на середине, оставив сессию с несохранёнными
    # строками. Дальше `jobs.fail` делает commit — и без отката он уносит в
    # базу мусор недоделанной работы, а если тот не лезет в схему, падает
    # сам, и задача остаётся «выполняющейся» без причины в поле error. То
    # есть ровно тем молчаливым отказом, ради которого заведена отметка
    # живости.
    #
    # Сессия здесь настоящая, а не фикстура `session`: та живёт внутри
    # точки сохранения, и её откат — вложенный. Разница не косметическая.
    # Настоящий откат помечает устаревшими ВСЕ объекты сессии, вложенный —
    # только изменённые, а `jobs.fail` сразу после отката читает
    # `job.attempts`. Устаревшее поле в async-коде тянет догрузку синхронно
    # и падает MissingGreenlet — поломка, которой на точке сохранения не
    # видно вовсе, а на контуре она и есть тот самый молчаливый отказ.
    from app import worker

    garbage = "мусор-недоделанной-работы"

    async def handler(db, job):
        db.add(Job(kind=garbage, payload={}, actor="boss"))
        raise ValueError("на середине разбора")

    monkeypatch.setitem(worker.HANDLERS, "проба", handler)
    monkeypatch.setattr(worker.settings, "job_max_attempts", 1)

    try:
        async with new_session() as setup:
            jobs.enqueue(setup, kind="проба", payload={}, actor="boss")
            await setup.commit()

        async with new_session() as db:
            assert await worker.run_once(db) is True

        async with new_session() as check:
            job = (
                await check.execute(select(Job).where(Job.kind == "проба"))
            ).scalar_one()
            assert job.status is JobStatus.failed
            assert "на середине разбора" in job.error
            left = (await check.execute(select(Job).where(Job.kind == garbage))).first()
            assert left is None, "мусор упавшего обработчика уехал в базу"
    finally:
        # Уборка в finally по той же причине, что и в tests/api/test_jobs.py:
        # строки тут коммитятся по-настоящему, и упавшая проверка иначе
        # оставила бы их соседним тестам файла.
        async with new_session() as cleanup:
            for row in (await cleanup.execute(select(Job))).scalars().all():
                await cleanup.delete(row)
            await cleanup.commit()
