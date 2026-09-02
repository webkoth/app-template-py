"""Ограничения трёх таблиц фичи «Таблицы» — те, что держит база.

Проверяется здесь не ORM, а схема: каждый тест пытается НАРУШИТЬ ограничение
и требует отказа. Обещание, записанное только комментарием, однажды нарушит
код, который писали не глядя на комментарий; обещание, записанное в схеме,
нарушить нельзя.

Файл лежит в `tests/api`, а не в `tests/unit`, по той же причине, что и
тесты очереди: ему нужна живая PostgreSQL. Ни каскадного удаления по
внешнему ключу, ни JSONB, ни отказа по уникальности «на бумаге» не бывает —
это поведение базы, и проверяется оно базой.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.features.datasets.models import Dataset, DatasetRow, ModelArtifact


async def _dataset(session, name: str = "цены") -> Dataset:
    dataset = Dataset(
        name=name,
        file_id=uuid.uuid7(),
        original_name=f"{name}.csv",
        size_bytes=42,
        kind="csv",
        actor="ivan",
    )
    session.add(dataset)
    await session.flush()
    return dataset


async def test_a_row_cannot_point_at_a_missing_dataset(session):
    # Внешний ключ, а не просто колонка с идентификатором. Без него
    # осиротевшие строки копятся молча: на экране их не видно, в сводке они
    # не участвуют, а место занимают — и находят их годы спустя по размеру
    # базы.
    session.add(DatasetRow(dataset_id=uuid.uuid7(), index=0, data={"a": 1}))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_rows_die_with_their_dataset(session):
    # ondelete CASCADE, и удаление идёт ОДНИМ запросом к datasets: связи
    # relationship между моделями нет, то есть подчистить строки в Python
    # некому. Без CASCADE удаление таблицы вообще не состоялось бы — база
    # отказала бы по внешнему ключу.
    kept = await _dataset(session, "остаётся")
    doomed = await _dataset(session, "удаляется")
    session.add_all(
        [
            DatasetRow(dataset_id=kept.id, index=0, data={"город": "А"}),
            DatasetRow(dataset_id=doomed.id, index=0, data={"город": "Б"}),
            DatasetRow(dataset_id=doomed.id, index=1, data={"город": "В"}),
        ]
    )
    await session.commit()

    await session.delete(doomed)
    await session.commit()

    rows = (await session.execute(select(DatasetRow))).scalars().all()
    # Каскад забирает строки удалённой таблицы и не трогает чужие: без
    # второй половины проверки прошло бы и удаление всех строк подряд.
    assert [(r.dataset_id, r.index) for r in rows] == [(kept.id, 0)]


async def test_artifacts_die_with_their_dataset(session):
    # Модель, обученная на данных, которых больше нет, не просто бесполезна:
    # предсказание по ней выглядит рабочим и ничем не отличается от
    # предсказания по живой модели.
    dataset = await _dataset(session)
    session.add(
        ModelArtifact(
            dataset_id=dataset.id,
            target_column="цена",
            feature_columns=["площадь"],
            algorithm="linear",
            metric_name="r2",
            metric_value=0.5,
            payload=b"joblib",
            actor="ivan",
        )
    )
    await session.commit()

    await session.delete(dataset)
    await session.commit()

    assert (await session.execute(select(ModelArtifact))).first() is None


async def test_two_rows_cannot_share_one_place_in_the_table(session):
    # Место строки в таблице — это (таблица, номер), и второй такой же пары
    # быть не может. Держит это база, потому что нарушение здесь молчаливое:
    # разобрав таблицу дважды — задачу вернула отметка живости или её
    # перезапустили руками, — строки удваиваются, сводка остаётся от первого
    # прохода, и расхождение видно только счётом строк.
    dataset = await _dataset(session)
    session.add(DatasetRow(dataset_id=dataset.id, index=0, data={"a": 1}))
    await session.flush()
    session.add(DatasetRow(dataset_id=dataset.id, index=0, data={"a": 2}))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_a_fresh_dataset_has_not_been_counted_yet(session):
    # NULL в сводке означает «ещё не считали»: разбор идёт в фоне, и экран
    # обязан отличать это от «посчитали, и вышло пусто».
    dataset = await _dataset(session)
    await session.commit()
    await session.refresh(dataset)
    assert dataset.summary is None
    assert dataset.rows_count == 0
    assert dataset.created_at is not None


async def test_an_empty_summary_is_not_a_missing_one(session):
    # Обратная сторона предыдущего теста: посчитанная пустая сводка обязана
    # доехать до базы и вернуться оттуда пустой, а не превратиться в NULL —
    # иначе разобранная таблица без колонок навсегда останется «считаем».
    dataset = await _dataset(session)
    dataset.summary = {}
    await session.commit()
    await session.refresh(dataset)
    assert dataset.summary == {}
    assert dataset.summary is not None


async def test_a_model_keeps_its_bytes_exactly(session):
    # Сериализованная модель — двоичное, а не текст. Колонка String приняла
    # бы часть таких значений и отвергла бы остальные: нулевой байт
    # PostgreSQL в тексте не хранит вовсе, а joblib его пишет.
    dataset = await _dataset(session)
    blob = bytes(range(256))
    session.add(
        ModelArtifact(
            dataset_id=dataset.id,
            target_column="цена",
            feature_columns=["площадь"],
            algorithm="linear",
            metric_name="r2",
            metric_value=0.5,
            payload=blob,
            actor="ivan",
        )
    )
    await session.commit()
    artifact = (await session.execute(select(ModelArtifact))).scalar_one()
    await session.refresh(artifact)
    assert artifact.payload == blob


async def test_a_metric_keeps_its_fraction(session):
    # Метрика — дробь от нуля до единицы, и колонка обязана быть дробной.
    # Целочисленная не отказала бы: 0,8125 округлилось бы до 1, и негодная
    # модель выглядела бы безупречной.
    dataset = await _dataset(session)
    session.add(
        ModelArtifact(
            dataset_id=dataset.id,
            target_column="цена",
            feature_columns=["площадь", "комнат"],
            algorithm="linear",
            metric_name="r2",
            metric_value=0.8125,
            payload=b"joblib",
            actor="ivan",
        )
    )
    await session.commit()
    artifact = (await session.execute(select(ModelArtifact))).scalar_one()
    await session.refresh(artifact)
    assert artifact.metric_value == 0.8125
    # Порядок колонок — часть модели: предсказание подаёт значения в том же
    # порядке, и перестановка молча меняет смысл всех предсказаний.
    assert artifact.feature_columns == ["площадь", "комнат"]


async def test_a_row_that_does_not_fit_the_column_is_refused(session):
    # Верхняя граница колонки — тоже ограничение базы, и она короче, чем
    # кажется: имя файла человек приносит какое угодно. Обрезать его — работа
    # сервиса; здесь проверяется, что необрезанное база не примет молча.
    session.add(
        Dataset(
            name="цены",
            file_id=uuid.uuid7(),
            original_name="я" * 256,
            size_bytes=42,
            kind="csv",
            actor="ivan",
        )
    )
    with pytest.raises(DBAPIError):
        await session.flush()
    await session.rollback()
