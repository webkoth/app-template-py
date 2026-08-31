"""Даты.

В базе — TIMESTAMPTZ. Человеку — московская зона: приложение внутреннее, и
часовой пояс у него один. Понадобятся другие зоны — это отдельное решение,
а не «добавить параметр».
"""

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

# Ровно YYYY-MM-DD и ничего больше. date.fromisoformat в Python 3.11+
# принимает заметно шире: "20260831" без дефисов и — что хуже —
# "2026-W01-1", недельную нумерацию ISO, которая разбирается в 29 декабря
# 2025 года. Строка, похожая на мусор, молча становится датой другого года.
# Поле type="date" такого не пришлёт, но API принимает произвольную строку,
# и контракт обязан совпадать с обещанием docstring.
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_date_input_value(raw: str) -> datetime | None:
    """Разбирает значение поля type="date" (ISO, YYYY-MM-DD).

    None — строка не является существующей датой этого формата. Проверку
    существования делает date.fromisoformat: он отвергает 2026-02-31, а не
    переносит её на март, как молча делает движок JavaScript.
    """
    if not _ISO_DATE.fullmatch(raw):
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    return datetime.combine(parsed, time.min, tzinfo=MSK)


def format_date(value: datetime) -> str:
    return value.astimezone(MSK).strftime("%d.%m.%Y")


def format_date_time(value: datetime) -> str:
    return value.astimezone(MSK).strftime("%d.%m.%Y %H:%M")
