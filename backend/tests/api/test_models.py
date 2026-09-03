"""Обучение модели и предсказание — вторая задача над той же таблицей.

Обучение идёт через очередь и проверяется прямым вызовом обработчика, как и
разбор: воркер общий и живёт отдельно. Предсказание — обычный маршрут, без
очереди, и проверяется по HTTP.
"""

import io

import pytest
from sqlalchemy import select

from app.core import storage
from app.core.audit import AuditLog
from app.core.jobs import Job
from app.domain.roles import Role
from app.features.datasets.models import Dataset, ModelArtifact

# Цена жёстко связана с площадью (цена = 3 × площадь − 20), поэтому метрика
# на этой таблице предсказуема и тест не зависит от того, как лягут строки в
# обучающую и проверочную половины.
TABLE = (
    "площадь,комнат,цена\n"
    + "".join(f"{40 + i},{1 + i % 3},{100 + i * 3}\n" for i in range(40))
).encode()

# Та же таблица, но целью просится текстовая колонка.
TEXT_TABLE = (
    "город,цена\n" + "".join(f"{'АБВ'[i % 3]},{100 + i * 3}\n" for i in range(40))
).encode()

# Та же таблица, но в пяти строках нет площади. Пустые ячейки в настоящей
# выгрузке есть почти всегда.
GAPPY_TABLE = (
    "площадь,комнат,цена\n"
    + "".join(
        f"{'' if i % 8 == 0 else 40 + i},{1 + i % 3},{100 + i * 3}\n" for i in range(40)
    )
).encode()

# Пропусков столько, что учить не на чем.
MOSTLY_GAPS_TABLE = (
    "площадь,комнат,цена\n"
    + "".join(
        f"{'' if i % 4 else 40 + i},{1 + i % 3},{100 + i * 3}\n" for i in range(40)
    )
).encode()

# Меньше, чем MIN_ROWS_TO_TRAIN.
SHORT_TABLE = (
    "площадь,цена\n" + "".join(f"{40 + i},{100 + i * 3}\n" for i in range(5))
).encode()


@pytest.fixture(autouse=True)
def uploads(tmp_path, monkeypatch):
    """Каталог загрузок — временный, свой на каждый тест.

    Без подмены тесты писали бы в рабочий каталог контура и оставляли бы там
    файлы после себя.
    """
    monkeypatch.setattr(storage.settings, "upload_dir", tmp_path)
    return tmp_path


async def prepare(client, session, body: bytes = TABLE) -> Dataset:
    """Загружает таблицу и разбирает её — то есть готовит то, на чём учат."""
    from app.features.datasets import jobs as handlers

    await client.post(
        "/api/datasets",
        files={"file": ("кв.csv", io.BytesIO(body), "text/csv")},
    )
    job = (await session.execute(select(Job))).scalars().first()
    assert job is not None
    await handlers.parse(session, job)
    await session.commit()
    # Строки читаются из базы, а не берутся тёплыми из сессии. Обучение в
    # бою идёт другим процессом и другой сессией, и видит `data` таким,
    # каким его отдаёт JSONB: тот нормализует порядок ключей (сначала по
    # длине, потом побайтно), и «площадь, комнат, цена» приезжает как
    # «цена, комнат, площадь». Замерено: эта фикстура отдаёт нормализованный
    # порядок и без expunge_all — но она живёт с expire_on_commit=False и
    # гасит объекты не так, как настоящая сессия, поэтому зависеть от того,
    # что она решит перечитать, тест не должен.
    session.expunge_all()
    return (await session.execute(select(Dataset))).scalar_one()


async def train_job(session) -> Job:
    return (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).scalar_one()


async def test_gaps_are_dropped_and_counted_not_swallowed(client, session, login_as):
    """Пустая ячейка не должна ронять обучение английским сообщением.

    Из JSONB пропуск приезжает как NaN, и `fit` падает «Input X contains
    NaN» — человек читает это в карточке задачи и идёт искать поломку в
    системе, хотя дело в его таблице.

    Строки с пропусками отбрасываются, но НЕ молча: сколько выброшено,
    уезжает в результат задачи. Молчание здесь хуже отказа — модель,
    обученная на половине таблицы, выглядит обученной на всей.
    """
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session, GAPPY_TABLE)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).scalar_one()

    result = await handlers.train(session, job)
    await session.commit()

    assert result["пропущено"] == 5
    assert result["строк"] == 35
    assert (await session.execute(select(ModelArtifact))).scalar_one() is not None


async def test_a_table_of_mostly_gaps_is_refused_by_what_is_left(
    client, session, login_as
):
    # Отказ называет ОБА числа: сколько осталось и сколько было. «Нужно 20
    # строк, есть 10» о таблице на сорок строк человек читает как ошибку
    # системы — он же видит сорок.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session, MOSTLY_GAPS_TABLE)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).scalar_one()

    with pytest.raises(ValueError) as denial:
        await handlers.train(session, job)
    assert "10 строк из 40" in str(denial.value)


async def test_training_requires_editor(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await login_as(role=Role.viewer, login="петя")
    response = await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    assert response.status_code == 403


async def test_unknown_target_column_is_refused_by_its_name(client, session, login_as):
    # Опечатка в имени колонки — самая частая ошибка при обучении. Отказ
    # обязан назвать поле, чтобы форма подсветила именно его.
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    response = await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цна"}
    )
    assert response.status_code == 400
    assert response.json()["field"] == "target_column"


async def test_training_queues_the_work(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    response = await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    assert response.status_code == 202
    job = await train_job(session)
    assert job.payload["dataset_id"] == str(dataset.id)


async def test_training_writes_audit(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    entry = (
        await session.execute(select(AuditLog).where(AuditLog.action == "train"))
    ).scalar_one()
    assert entry.actor == "ivan"
    assert entry.entity_id == str(dataset.id)
    assert "цена" in entry.detail


async def test_trained_model_is_stored_with_its_metric(client, session, login_as):
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = await train_job(session)

    result = await handlers.train(session, job)
    await session.commit()

    model = (await session.execute(select(ModelArtifact))).scalar_one()
    assert model.target_column == "цена"
    # Порядок — как в самой таблице, а не как лягут ключи в JSONB. Список
    # читает человек, и «комнат, площадь» на таблице «площадь, комнат, цена»
    # выглядит перепутанным, хотя модель от порядка не страдает.
    assert model.feature_columns == ["площадь", "комнат"]
    assert model.metric_name == "r2"
    assert 0.0 <= model.metric_value <= 1.0
    assert len(model.payload) > 0
    assert result["метрика"] == pytest.approx(model.metric_value)


async def test_training_twice_does_not_double_the_models(client, session, login_as):
    # Задачу может быть выполнена повторно: воркер перезапущен доставкой
    # между `session.commit()` в обработчике и `jobs.complete` в воркере.
    # Обработчик обязан быть идемпотентным — ровно как разбор. Без этого
    # после двух проходов ОДНОЙ задачи получаются две модели, обе видны на
    # экране, и человек выбирает из них, чем предсказывать.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = await train_job(session)

    await handlers.train(session, job)
    await handlers.train(session, job)
    await session.commit()

    models = (await session.execute(select(ModelArtifact))).scalars().all()
    assert len(models) == 1, "второй проход дал вторую модель"
    assert models[0].job_id == job.id


async def test_prediction_uses_the_stored_model(client, session, login_as):
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    await handlers.train(session, await train_job(session))
    await session.commit()
    model = (await session.execute(select(ModelArtifact))).scalar_one()

    response = await client.post(
        f"/api/models/{model.id}/predict",
        json={"row": {"площадь": 50, "комнат": 2}},
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["значение"], float)


async def test_prediction_names_the_missing_column(client, session, login_as):
    # Строка без нужной колонки — ошибка ввода, а не сбой. Без явного отказа
    # сборка строки падает KeyError, и человек получает 500 «Что-то пошло не
    # так» — ни поля, ни причины. Проверено мутацией.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    await handlers.train(session, await train_job(session))
    await session.commit()
    model = (await session.execute(select(ModelArtifact))).scalar_one()

    response = await client.post(
        f"/api/models/{model.id}/predict", json={"row": {"площадь": 50}}
    )
    assert response.status_code == 400
    assert "комнат" in response.json()["error"]


async def test_prediction_on_an_unknown_model_is_404(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    missing = "01a05000-0000-7000-8000-000000000000"
    response = await client.post(
        f"/api/models/{missing}/predict", json={"row": {"площадь": 50}}
    )
    assert response.status_code == 404


async def test_trained_models_are_listed_without_their_payload(
    client, session, login_as
):
    # Список моделей читают, чтобы выбрать, чем предсказывать. Сам артефакт
    # наружу не отдаётся: он весит, человеку не нужен, а лишний путь наружу
    # для сериализованной модели заводить незачем.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    await handlers.train(session, await train_job(session))
    await session.commit()

    listed = (await client.get(f"/api/datasets/{dataset.id}/models")).json()
    assert [m["target_column"] for m in listed] == ["цена"]
    assert "payload" not in listed[0]


async def test_training_on_a_text_target_is_refused(client, session, login_as):
    # Регрессия по тексту не имеет смысла, и sklearn скажет об этом
    # исключением про типы — но уже в фоне, и человек увидит его в задаче
    # вместо формы. Отказ до постановки дешевле и понятнее, и он тоже
    # называет поле.
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session, body=TEXT_TABLE)
    response = await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "город"}
    )
    assert response.status_code == 400
    assert response.json()["field"] == "target_column"
    assert (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).first() is None


async def test_training_on_too_few_rows_is_refused_with_a_human_reason(
    client, session, login_as
):
    # Модель, обученную на горстке строк, метрика хвалит незаслуженно: она
    # запоминает выборку целиком. Отказ честнее бессмысленной модели, и
    # причину читает человек в задаче.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session, body=SHORT_TABLE)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    with pytest.raises(ValueError) as refusal:
        await handlers.train(session, await train_job(session))
    assert "строк" in str(refusal.value)


async def test_training_a_dataset_that_is_already_gone_is_not_a_failure(
    client, session, login_as
):
    # Таблицу удалили, пока задача ждала очереди. Работы больше нет, и
    # сообщать человеку не о чем — ровно как в разборе.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = await train_job(session)
    assert (await client.delete(f"/api/datasets/{dataset.id}")).status_code == 200

    assert "примечание" in await handlers.train(session, job)
