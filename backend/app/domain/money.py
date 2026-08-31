"""Деньги.

Всегда целые копейки. Float для денег не используется нигде: 0.1 + 0.2 даёт
0.30000000000000004, и на достаточном числе записей это превращается в
расхождение, которое находят при сверке, а не в коде.
"""

import re
from decimal import Decimal, InvalidOperation

# Предел int4 в PostgreSQL — колонка amount_minor объявлена как Integer.
# Примерно 21,47 млн рублей. Нужны суммы больше — это BigInt в схеме и
# отдельное решение владельца: BigInt требует форматирования на сервере.
MAX_AMOUNT_MINOR = 2_147_483_647

_NUMBER = re.compile(r"-?\d+(\.\d{1,2})?")


def parse_money_to_minor(raw: str) -> int | None:
    """Разбирает пользовательский ввод в копейки. None — не число.

    Единственный допустимый способ прочитать сумму из формы. Прямое
    приведение к числу здесь не работает: float("12,34") падает, а
    float("12.345") молча теряет копейку.
    """
    s = raw.strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not _NUMBER.fullmatch(s):
        return None
    try:
        return int((Decimal(s) * 100).to_integral_value())
    except InvalidOperation:  # pragma: no cover — regexp уже отсеял
        return None


def format_money(minor: int) -> str:
    """Форматирует копейки для показа человеку.

    Используется в текстах ошибок самого бэкенда. Интерфейс форматирует у
    себя через Intl: показ — забота клиента, разбор — забота сервера.
    """
    sign = "-" if minor < 0 else ""
    whole, frac = divmod(abs(minor), 100)
    grouped = f"{whole:,}".replace(",", "\xa0")
    return f"{sign}{grouped},{frac:02d}\xa0₽"
