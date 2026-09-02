"""Правила работы с таблицами. ОБРАЗЕЦ слоя данных."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs, storage
from app.core.audit import write_audit
from app.core.errors import RecordNotFound
from app.features.datasets.jobs import PARSE
from app.features.datasets.models import Dataset

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
