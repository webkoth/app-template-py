"""Правила работы с таблицами. ОБРАЗЕЦ слоя данных."""

import io
import uuid
from typing import Any

import joblib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs, storage
from app.core.audit import write_audit
from app.core.errors import RecordNotFound, RuleViolation
from app.core.jobs import Job
from app.features.datasets.jobs import NUMERIC_KIND, PARSE, TRAIN
from app.features.datasets.models import Dataset, ModelArtifact

# Сколько байт головы файла нужно, чтобы узнать вид. Подпись формата стоит в
# самом начале, и восьми байт ей хватает с запасом. Голову целиком (4 КиБ)
# смотрит storage.save — он же и отказывает по содержимому; здесь решается
# только «csv или xlsx».
_KIND_HEAD = 8


async def list_datasets(session: AsyncSession) -> list[Dataset]:
    result = await session.execute(
        # Второй ключ — id: created_at ставится в коде, и две таблицы,
        # загруженные в одну миллисекунду, иначе меняются местами от
        # запроса к запросу.
        select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id)
    )
    return list(result.scalars().all())


async def get_dataset(session: AsyncSession, dataset_id: uuid.UUID) -> Dataset:
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise RecordNotFound("Таблица не найдена")
    return dataset


async def create_dataset(
    session: AsyncSession, original_name: str, data: bytes, actor: str
) -> Dataset:
    """Кладёт файл, заводит запись и ставит разбор — одной транзакцией.

    Порядок важен: файл на диск ложится ДО записи в базу, потому что откат
    транзакции уберёт запись, а файл придётся убирать руками — и мы это
    делаем ниже явно. Обратный порядок дал бы запись, ссылающуюся на файл,
    которого нет.
    """
    # Вид — из содержимого, а не из расширения, и решается он ОДИН раз,
    # здесь: разбор потом верит записанному. Выгрузка из Excel регулярно
    # приезжает под именем .csv, и по расширению XLSX уехал бы в чтение CSV,
    # где падает сообщением про кодировку — человек читает его и ищет
    # причину в своей таблице.
    kind = storage.detect_kind(data[:_KIND_HEAD])
    file_id = storage.save(data)
    try:
        dataset = Dataset(
            name=original_name.rsplit(".", 1)[0][:255] or "без имени",
            file_id=file_id,
            original_name=original_name[:255],
            size_bytes=len(data),
            kind=kind,
            actor=actor,
        )
        session.add(dataset)
        await session.flush()
        jobs.enqueue(
            session,
            kind=PARSE,
            payload={"dataset_id": str(dataset.id)},
            actor=actor,
        )
        write_audit(
            session,
            actor,
            "create",
            "Dataset",
            str(dataset.id),
            f"{original_name}, {len(data)} байт",
        )
        await session.commit()
    except Exception:
        # Файл уже на диске, а запись не состоялась. Без уборки каталог
        # загрузок копит файлы, на которые никто не ссылается: место они
        # занимают, а найти их можно только глазами.
        storage.delete(file_id)
        raise
    return dataset


async def delete_dataset(
    session: AsyncSession, dataset_id: uuid.UUID, actor: str
) -> None:
    dataset = await get_dataset(session, dataset_id)
    file_id = dataset.file_id
    write_audit(
        session, actor, "delete", "Dataset", str(dataset.id), dataset.original_name
    )
    await session.delete(dataset)
    await session.commit()
    # Файл удаляется ПОСЛЕ коммита: упади удаление записи, файл остался бы
    # нужен. Осиротевший файл дешевле записи, ссылающейся в пустоту.
    storage.delete(file_id)


async def list_models(
    session: AsyncSession, dataset_id: uuid.UUID
) -> list[ModelArtifact]:
    # Свежая модель первой: список читают, чтобы взять последнюю обученную.
    # Второй ключ — id: created_at ставится в коде, и две модели, обученные
    # в одну миллисекунду, иначе меняются местами от запроса к запросу.
    result = await session.execute(
        select(ModelArtifact)
        .where(ModelArtifact.dataset_id == dataset_id)
        .order_by(ModelArtifact.created_at.desc(), ModelArtifact.id)
    )
    return list(result.scalars().all())


async def start_training(
    session: AsyncSession, dataset_id: uuid.UUID, target: str, actor: str
) -> Job:
    """Ставит обучение в очередь. Проверяет цель ДО постановки.

    Проверки ниже могли бы не существовать: обучение отказало бы и само.
    Но отказало бы оно в фоне — исключением про типы или про отсутствующую
    колонку, — и человек прочитал бы его в карточке задачи, через оборот
    опроса и без подсказки, что чинить. Здесь отказ приезжает формой и
    называет поле.
    """
    dataset = await get_dataset(session, dataset_id)
    if dataset.summary is None:
        # Разбор ещё идёт (или отказал), и состава колонок мы не знаем.
        # Ставить обучение вслепую значило бы завести задачу, которая
        # заведомо упадёт.
        raise RuleViolation("Таблица ещё не разобрана", field="target_column")

    kinds = {str(c["имя"]): str(c["вид"]) for c in dataset.summary["колонки"]}
    if target not in kinds:
        # Отказ называет поле: опечатка в имени колонки — самая частая
        # ошибка здесь, и форма обязана подсветить именно её.
        raise RuleViolation(f"В таблице нет колонки «{target}»", field="target_column")
    if kinds[target] != NUMERIC_KIND:
        # Регрессия по тексту не имеет смысла: предсказывать «город» числом
        # нечем. Пустая колонка — тот же случай, и вид у неё тоже не «число».
        raise RuleViolation(
            f"Колонка «{target}» не числовая — предсказывать по ней нечего",
            field="target_column",
        )

    job = jobs.enqueue(
        session,
        kind=TRAIN,
        payload={"dataset_id": str(dataset_id), "target_column": target},
        actor=actor,
    )
    write_audit(session, actor, "train", "Dataset", str(dataset_id), f"цель {target}")
    await session.commit()
    return job


async def predict(
    session: AsyncSession, model_id: uuid.UUID, row: dict[str, Any]
) -> float:
    """Предсказание идёт СРАЗУ, а не через очередь.

    Обучение долгое, предсказание — миллисекунды. Гонять его через очередь
    значило бы заставить человека ждать оборота опроса ради ответа, который
    уже готов.
    """
    model_row = await session.get(ModelArtifact, model_id)
    if model_row is None:
        raise RecordNotFound("Модель не найдена")

    missing = [c for c in model_row.feature_columns if c not in row]
    if missing:
        # Без этой проверки до sklearn дело даже не доходит: строку собирает
        # выражение ниже, и оно падает KeyError — то есть человек получает
        # 500 «Что-то пошло не так», в котором про недостающую колонку нет
        # ни слова, а причина видна только в логе. Проверено мутацией.
        raise RuleViolation(f"Не хватает колонок: {', '.join(missing)}", field="row")

    # Распаковка joblib исполняет код. Здесь это безопасно ровно потому, что
    # артефакт НАШ: он положен обучением в этом же приложении, в эту же
    # колонку. Загружать сюда файл извне нельзя ни при каких условиях — ни
    # «для проверки», ни «только админу»: чужой артефакт означает
    # выполнение чужого кода в процессе приложения.
    model = joblib.load(io.BytesIO(model_row.payload))
    # Порядок колонок задаёт артефакт, а не словарь из формы: обучение
    # видело именно этот порядок, и переставленные местами значения дали бы
    # не отказ, а тихо неверное число.
    values = [[float(row[c]) for c in model_row.feature_columns]]
    return float(model.predict(values)[0])
