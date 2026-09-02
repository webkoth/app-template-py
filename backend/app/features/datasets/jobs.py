"""Фоновая работа фичи «Таблицы».

Обработчики живут здесь, а не в общем реестре: фича владеет своей фоновой
работой целиком, и удаляя фичу, удаляешь её задачи. Воркер собирает словарь
HANDLERS так же, как main.py собирает роутеры.
"""

import math
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs, storage
from app.core.jobs import Job
from app.domain.tables import read_table, summarise
from app.features.datasets.models import Dataset, DatasetRow

# Вид задачи объявлен ЗДЕСЬ, рядом с обработчиком, и импортируется всеми
# остальными. Два места, где написана строка «datasets.parse», разъезжаются
# молча: постановка кладёт один вид, HANDLERS ждёт другой, и задача просто
# не берётся — без ошибки, без записи в логе, навсегда «в очереди».
PARSE = "datasets.parse"

# Отметка живости ставится не на каждой строке, а раз в столько: запись в
# базу на каждой строке стоила бы дороже самого разбора.
_HEARTBEAT_EVERY = 500

# Сколько процентов отдано разбору строк. Остальное — сводка и завершение:
# показать 100 % до того, как результат сохранён, значит соврать экрану.
_ROWS_SHARE = 90


async def parse(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Читает файл, кладёт строки и сводку в базу.

    Отказ наружу не проглатывается и своим не подменяется: тексты
    `TableError` написаны для человека («Файл пуст», «В таблице больше 50000
    строк»), и в задачу их кладёт воркер — оттуда их и читают с экрана. Своё
    «не удалось разобрать» здесь стоило бы ровно той причины, ради которой
    отказ и показывают.
    """
    dataset_id = uuid.UUID(job.payload["dataset_id"])
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        # Таблицу удалили, пока задача ждала. Это не отказ: работы больше
        # нет, и сообщать человеку не о чем.
        return {"строк": 0, "примечание": "таблица удалена"}

    # Вид взят из записи, а не угадан заново: он определён по содержимому при
    # загрузке, и один и тот же файл обязан читаться одинаково при каждом
    # проходе.
    frame = read_table(storage.read(dataset.file_id), dataset.kind)

    # Идемпотентность. Задачу может вернуть отметка живости или перезапуск
    # руками, и повторный разбор обязан давать тот же результат, а не
    # удвоенные строки при сводке от первого прохода. Удаление и вставка идут
    # одной транзакцией, поэтому уникальности (dataset_id, index) это не
    # нарушает: к моменту вставки прежних строк уже нет.
    await session.execute(delete(DatasetRow).where(DatasetRow.dataset_id == dataset.id))

    total = len(frame)
    for index, row in enumerate(frame.to_dict(orient="records")):
        session.add(
            DatasetRow(
                dataset_id=dataset.id,
                index=index,
                data={str(key): _json_safe(value) for key, value in row.items()},
            )
        )
        if index % _HEARTBEAT_EVERY == 0:
            await session.flush()
            await jobs.heartbeat(
                session, job, progress=int(index / total * _ROWS_SHARE)
            )

    dataset.summary = summarise(frame)
    dataset.rows_count = total
    await session.commit()
    return {"строк": total}


def _json_safe(value: Any) -> Any:
    """Приводит значение ячейки к тому, что переживёт JSONB.

    Строки уезжают в JSONB, и негодное значение роняет СОХРАНЕНИЕ — то есть
    после всего разбора, когда работа уже сделана и потеряна. Способов
    уронить три, и все они приезжают из обычных выгрузок:

    NaN и ±inf сериализатор json берёт и печатает как `NaN` и `Infinity` —
    таких литералов в JSON нет, и строку отвергает уже PostgreSQL,
    сообщением про синтаксис json. Пустая ячейка даёт NaN, а `1e400` в
    колонке цен — inf: столько не влезает в double.

    Метку времени (из XLSX дата приезжает именно ею, а не строкой) json не
    берёт вовсе — это TypeError на записи.

    numpy-скаляр — тоже TypeError. pandas 3 при `to_dict` приводит
    большинство таких значений к питоновским сам, но полагаться на это
    нельзя: приведение зависит от dtype колонки.

    Порядок проверок несущий. NaN и NaT не равны сами себе — этим они и
    ловятся оба одной строкой, и стоять она обязана ДО проверки на дату:
    `NaT` — наследник `datetime`, и `isoformat()` у него отдаёт строку
    «NaT», то есть пустая ячейка превратилась бы в текст. `.item()` стоит
    первым по той же причине, что и в сводке: numpy.float32 наследником
    питоновского float не является, и isinstance его не узнаёт.
    """
    if hasattr(value, "item"):
        value = value.item()
    if value != value:
        return None
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime | date):
        return value.isoformat()
    # Всё остальное — строкой. Потерять значение молча хуже, чем показать его
    # текстом: колонка с Decimal или интервалом времени иначе уронила бы
    # запись целиком.
    return str(value)


HANDLERS = {PARSE: parse}
