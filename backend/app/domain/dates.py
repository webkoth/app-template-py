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


def _in_moscow(value: datetime) -> datetime:
    """Переводит значение в московскую зону, отвергая наивное.

    astimezone на datetime без зоны не падает: Python молча считает его
    временем в зоне процесса. Проверено — один и тот же вызов даёт три
    разные даты при TZ=Europe/Moscow, UTC и America/New_York.

    Для нас это не теория: машина разработчика в Москве, контур на сервере
    почти наверняка в UTC. Локально показ верен, на контуре та же запись
    съезжает на три часа, и расхождение ищут в данных, а не в коде.

    Из базы значения приходят с зоной (TIMESTAMPTZ), поэтому наивное
    значение здесь означает ошибку в коде, и падать надо громко.
    """
    if value.tzinfo is None:
        raise ValueError(
            "datetime без часового пояса: показ зависел бы от зоны сервера"
        )
    return value.astimezone(MSK)


def format_date(value: datetime) -> str:
    return _in_moscow(value).strftime("%d.%m.%Y")


def format_date_time(value: datetime) -> str:
    return _in_moscow(value).strftime("%d.%m.%Y %H:%M")
