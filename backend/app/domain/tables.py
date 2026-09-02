"""Чтение таблицы и сводка по ней. Чистое: байты на входе, данные на выходе.

Ни базы, ни HTTP, ни файловой системы — как и всё в `domain`. Поэтому
правила проверяются юнит-тестами за миллисекунды, а не через загрузку файла
в приложение.
"""

import io
import math
from typing import Any

import pandas as pd


class TableError(ValueError):
    """Таблицу не удалось прочитать. Текст предназначен человеку.

    Своё исключение, а не `RuleViolation` из `core.errors`: контракт
    `domain-is-pure` запрещает `domain → core`, и это не формальность.
    Чистая логика, знающая про конверт ошибки веб-приложения, перестаёт
    быть переносимой: её нельзя позвать ни из скрипта, ни из воркера, не
    притащив с собой FastAPI. Перевод в `RuleViolation` с полем `file` —
    работа сервиса фичи.
    """


# Потолок строк — про память, а не про диск: разбор держит таблицу целиком.
# Воркер, съевший память контура, утягивает за собой и приложение: они на
# одной машине.
MAX_ROWS = 50_000

# Читаем на строку больше потолка и не читаем дальше. Одной строки хватает,
# чтобы отличить «ровно потолок» от «больше потолка», а всё, что за ней, для
# отказа не нужно: узкий CSV в 15 МиБ при полном чтении даёт 122 МиБ пика
# против 2 МиБ при чтении с ограничением (замерено tracemalloc), а предел
# загрузки — 32 МиБ. Без ограничения потолок памяти сам её и съедает: сперва
# поднимает в память всю таблицу и только потом отказывает.
_READ_LIMIT = MAX_ROWS + 1

# Кодировки перебираются в этом порядке. cp1251 второй, потому что выгрузки
# из Excel в России приезжают в ней чаще, чем в чём-либо ещё после UTF-8.
_ENCODINGS = ("utf-8", "cp1251")


def read_table(data: bytes, kind: str) -> pd.DataFrame:
    """Читает CSV или XLSX. Отказ — TableError с человеческим текстом."""
    if not data:
        raise TableError("Файл пуст")

    if kind == "xlsx":
        try:
            frame = pd.read_excel(io.BytesIO(data), nrows=_READ_LIMIT)
        except Exception as broken:
            raise TableError(f"Не удалось прочитать XLSX: {broken}") from None
    else:
        frame = _read_csv(data)

    if len(frame) > MAX_ROWS:
        raise TableError(f"В таблице больше {MAX_ROWS} строк — столько шаблон не берёт")
    if frame.empty:
        raise TableError("В таблице нет строк")
    return frame


def _read_csv(data: bytes) -> pd.DataFrame:
    last: Exception | None = None
    for encoding in _ENCODINGS:
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding, nrows=_READ_LIMIT)
        except UnicodeDecodeError as wrong:
            last = wrong
        except pd.errors.EmptyDataError:
            raise TableError("Файл пуст") from None
        except Exception as broken:
            raise TableError(f"Не удалось прочитать CSV: {broken}") from None
    raise TableError(
        "Не удалось определить кодировку: пробовали UTF-8 и Windows-1251"
    ) from last


def _clean(value: Any) -> Any:
    """Приводит значение к тому, что переживёт json.dumps.

    Сводка уезжает в JSONB, и она падает на СОХРАНЕНИИ результата — то есть
    после всего счёта, когда работа уже сделана и потеряна. Падает двумя
    разными способами:

    numpy.int64 сериализатор json не берёт вовсе — это видно сразу, ошибкой
    TypeError. А NaN и ±inf он берёт и печатает как `NaN` и `Infinity`:
    таких литералов в JSON нет, и отвергает такую сводку уже PostgreSQL,
    сообщением про синтаксис json. Поэтому не только NaN: `inf` приезжает
    из обычной выгрузки, где число не влезло в double (1e400), а среднее по
    колонке с +inf и -inf — это NaN.

    Проверка на конечность стоит ПОСЛЕ .item() намеренно: numpy.float32
    наследником питоновского float не является, и isinstance его не узнаёт,
    а .item() приводит любое numpy-число к питоновскому типу.
    """
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def summarise(frame: pd.DataFrame) -> dict[str, Any]:
    """Сводка: сколько строк и что в колонках."""
    columns: list[dict[str, Any]] = []
    for name in frame.columns:
        column = frame[name]
        if column.dropna().empty:
            columns.append({"имя": str(name), "вид": "пусто"})
        elif pd.api.types.is_numeric_dtype(column):
            columns.append(
                {
                    "имя": str(name),
                    "вид": "число",
                    "минимум": _clean(column.min()),
                    "максимум": _clean(column.max()),
                    "среднее": _clean(column.mean()),
                }
            )
        else:
            columns.append(
                {
                    "имя": str(name),
                    "вид": "текст",
                    "различных": int(column.nunique()),
                }
            )
    return {"строк": len(frame), "колонки": columns}
