"""Загрузка таблицы и разбор в фоне — цепочка целиком.

Форма → файл на диске → запись в базе → задача в очереди → обработчик,
который кладёт строки и сводку. Воркера здесь нет намеренно: он общий и
живёт отдельно, а обработчик проверяется прямым вызовом — так видно, что
делает именно он, а не очередь вокруг него.
"""

import io

import pytest
from sqlalchemy import select

from app.core import storage
from app.core.audit import AuditLog
from app.core.jobs import Job, JobStatus
from app.domain.roles import Role
from app.features.datasets.models import Dataset, DatasetRow

# Тело таблицы в UTF-8. Кодировка здесь существенна: разбор перебирает
# UTF-8 и cp1251, и таблица, записанная байтами «как получилось», проверяла
# бы не то, что нужно.
TABLE = "город,цена\nА,10\nБ,20\nА,30\n".encode()


@pytest.fixture(autouse=True)
def uploads(tmp_path, monkeypatch):
    """Каталог загрузок — временный, свой на каждый тест.

    Без подмены тесты писали бы в рабочий каталог контура и оставляли бы
    там файлы после себя. Заодно каталог становится наблюдаемым: видно, что
    файл лёг и что уборка его забрала.
    """
    monkeypatch.setattr(storage.settings, "upload_dir", tmp_path)
    return tmp_path


def upload(name: str = "цены.csv", body: bytes = TABLE) -> dict:
    return {"file": (name, io.BytesIO(body), "text/csv")}


def xlsx_body() -> bytes:
    """Настоящий XLSX: zip с xml внутри, а не csv с другим расширением."""
    import pandas as pd

    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "город": ["А", "Б"],
            # Дата намеренно: из XLSX она приезжает не строкой, а меткой
            # времени, и в JSONB такое значение само по себе не ложится.
            "дата": pd.to_datetime(["2020-01-01", "2020-02-01"]),
        }
    ).to_excel(buffer, index=False)
    return buffer.getvalue()


async def only_job(session) -> Job:
    return (await session.execute(select(Job))).scalar_one()


async def test_upload_requires_editor(client, login_as):
    await login_as(role=Role.viewer, login="ivan")
    response = await client.post("/api/datasets", files=upload())
    assert response.status_code == 403


async def test_reading_requires_login(client):
    assert (await client.get("/api/datasets")).status_code == 401


async def test_upload_stores_the_file_and_queues_the_work(
    client, session, login_as, uploads
):
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/datasets", files=upload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_name"] == "цены.csv"
    # Сводки ещё нет: разбор идёт в фоне, и экран обязан отличать «считаем»
    # от «посчитали и вышло пусто».
    assert body["summary"] is None

    dataset = (await session.execute(select(Dataset))).scalar_one()
    # Файл лежит на диске под своим идентификатором, а не под именем,
    # которое принёс человек.
    assert storage.path_for(dataset.file_id).read_bytes() == TABLE
    assert [p.name for p in uploads.iterdir()] == [str(dataset.file_id)]

    job = await only_job(session)
    assert job.kind == "datasets.parse"
    assert job.payload == {"dataset_id": str(dataset.id)}
    assert job.status is JobStatus.queued


async def test_the_list_shows_what_was_uploaded(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    response = await client.get("/api/datasets")
    assert response.status_code == 200
    assert [d["original_name"] for d in response.json()] == ["цены.csv"]


async def test_upload_and_its_job_land_in_one_transaction(client, session, login_as):
    # Если запись таблицы и постановка задачи разъедутся, воркер возьмёт
    # задачу на данные, которых нет. Проверяется тем, что обе строки
    # переживают откат к точке сохранения одинаково.
    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    await session.rollback()
    assert (await session.execute(select(Dataset))).first() is not None
    assert (await session.execute(select(Job))).first() is not None


async def test_upload_writes_audit(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    entry = (await session.execute(select(AuditLog))).scalars().one()
    assert entry.actor == "ivan"
    assert entry.entity == "Dataset"
    assert "цены.csv" in entry.detail


async def test_wrong_content_is_refused_with_a_human_reason(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    response = await client.post(
        "/api/datasets", files=upload("отчёт.csv", b"%PDF-1.7\n%\xe2\xe3")
    )
    assert response.status_code == 400
    assert response.json()["field"] == "file"


async def test_a_failed_upload_does_not_leave_the_file_behind(
    client, login_as, monkeypatch, uploads
):
    # Файл ложится на диск ДО записи в базу, поэтому откат транзакции его не
    # уберёт — убирать обязан сервис. Без уборки каталог загрузок копит
    # файлы, на которые никто не ссылается: место они занимают, а найти их
    # можно только глазами.
    from app.core import jobs
    from app.features.datasets import service

    def boom(*_args, **_kwargs):
        raise RuntimeError("очередь недоступна")

    monkeypatch.setattr(jobs, "enqueue", boom)
    assert service.jobs is jobs, "сервис зовёт очередь не через модуль"

    await login_as(role=Role.editor, login="ivan")
    with pytest.raises(RuntimeError):
        await client.post("/api/datasets", files=upload())
    assert list(uploads.iterdir()) == []


async def test_too_large_is_refused(client, login_as, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "upload_max_bytes", 10)
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/datasets", files=upload())
    assert response.status_code == 400
    assert "больше" in response.json()["error"]


async def test_too_large_is_refused_before_the_body_reaches_the_disk(
    client, login_as, monkeypatch
):
    # Предыдущий тест зелёный и тогда, когда потолок сработал последней
    # линией — внутри storage.save, уже приняв всё тело. Отличить одно от
    # другого можно только так: сделать save падающим и потребовать, чтобы
    # отказ всё равно был человеческим. Без этого теста вызов check_size в
    # роутере можно удалить, и ни одна проверка не покраснеет.
    from app.core.config import settings

    monkeypatch.setattr(settings, "upload_max_bytes", 10)
    monkeypatch.setattr(
        storage,
        "save",
        lambda data: pytest.fail("файл не должен доходить до диска"),
    )
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/datasets", files=upload())
    assert response.status_code == 400
    assert "больше" in response.json()["error"]


async def test_parsing_fills_rows_and_summary(client, session, login_as):
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    job = await only_job(session)
    job.status = JobStatus.running
    await session.commit()

    result = await handlers.parse(session, job)
    await session.commit()

    dataset = (await session.execute(select(Dataset))).scalar_one()
    assert dataset.rows_count == 3
    assert dataset.summary["строк"] == 3
    assert result["строк"] == 3
    rows = (
        (await session.execute(select(DatasetRow).order_by(DatasetRow.index)))
        .scalars()
        .all()
    )
    assert [r.data["город"] for r in rows] == ["А", "Б", "А"]


async def test_parsing_twice_does_not_double_the_rows(client, session, login_as):
    # Задача может быть выполнена повторно: её вернула отметка живости или
    # её перезапустили руками. Обработчик обязан быть идемпотентным, иначе
    # строки удваиваются молча, а сводка расходится с содержимым.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    job = await only_job(session)

    await handlers.parse(session, job)
    await handlers.parse(session, job)
    await session.commit()

    rows = (await session.execute(select(DatasetRow))).scalars().all()
    assert len(rows) == 3


async def test_kind_is_taken_from_the_content_not_from_the_name(
    client, session, login_as
):
    # Имя файла человек приносит какое угодно: выгрузка из Excel регулярно
    # приезжает под расширением .csv. Вид решает содержимое, и решается он
    # ОДИН раз — при загрузке; разбор потом верит записанному. Возьмись вид
    # из расширения, XLSX уехал бы в чтение CSV и упал бы там сообщением
    # про кодировку, в котором про настоящую причину нет ни слова.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    response = await client.post(
        "/api/datasets", files=upload("выгрузка.csv", xlsx_body())
    )
    assert response.status_code == 201, response.text
    assert response.json()["kind"] == "xlsx"

    await handlers.parse(session, await only_job(session))
    await session.commit()
    rows = (
        (await session.execute(select(DatasetRow).order_by(DatasetRow.index)))
        .scalars()
        .all()
    )
    assert [r.data["город"] for r in rows] == ["А", "Б"]
    # Метка времени из XLSX в JSONB сама не ложится: json её не берёт вовсе,
    # и падение случилось бы на записи — после всего разбора.
    assert rows[0].data["дата"].startswith("2020-01-01")


async def test_a_number_too_big_for_a_double_does_not_break_the_parse(
    client, session, login_as
):
    # 1e400 в выгрузке — обычное дело: столько не влезает в double, и pandas
    # отдаёт inf. json печатает его как Infinity, такого литерала в JSON нет,
    # и отвергает строку уже PostgreSQL — сообщением про синтаксис json,
    # после того как вся таблица разобрана. Ровно та же дыра, что закрыта в
    # сводке, только на строках.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    await client.post(
        "/api/datasets", files=upload("цены.csv", "цена\n1e400\n7\n".encode())
    )
    await handlers.parse(session, await only_job(session))
    await session.commit()

    rows = (
        (await session.execute(select(DatasetRow).order_by(DatasetRow.index)))
        .scalars()
        .all()
    )
    assert [r.data["цена"] for r in rows] == [None, 7.0]


async def test_broken_table_fails_with_the_reason_a_human_reads(
    client, session, login_as
):
    # Отказ обязан быть слышен: причину читает человек, а не только лог.
    # Обработчик её не проглатывает и не подменяет своей — он выпускает
    # доменный отказ наружу, откуда воркер кладёт текст в задачу.
    from app.domain.tables import TableError
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload("пусто.csv", b"\n"))
    with pytest.raises(TableError) as broken:
        await handlers.parse(session, await only_job(session))
    assert "пуст" in str(broken.value)


async def test_parsing_a_dataset_that_is_already_gone_is_not_a_failure(
    client, session, login_as
):
    # Таблицу удалили, пока задача ждала очереди. Работы больше нет, и
    # сообщать человеку не о чем: отказ здесь был бы ложной тревогой.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    created = (await client.post("/api/datasets", files=upload())).json()
    job = await only_job(session)
    assert (await client.delete(f"/api/datasets/{created['id']}")).status_code == 200

    assert (await handlers.parse(session, job))["строк"] == 0


async def test_deleting_a_dataset_takes_its_rows_and_its_file(
    client, session, login_as, uploads
):
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    created = (await client.post("/api/datasets", files=upload())).json()
    await handlers.parse(session, await only_job(session))
    await session.commit()

    assert (await client.delete(f"/api/datasets/{created['id']}")).status_code == 200
    assert (await session.execute(select(DatasetRow))).first() is None
    # Исходник уходит вместе с записью: файл, на который никто не ссылается,
    # найти потом можно только глазами.
    assert list(uploads.iterdir()) == []


async def test_deleting_unknown_dataset_is_404(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    missing = "01a05000-0000-7000-8000-000000000000"
    assert (await client.delete(f"/api/datasets/{missing}")).status_code == 404
