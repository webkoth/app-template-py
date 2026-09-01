"""Текст, который набирает человек и потом читает глазами."""

import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

# Управляющие символы: NUL и всё, что ниже пробела, плюс DEL.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def no_control_characters(value: str) -> str:
    """Отвергает управляющие символы. Дороже всего здесь NUL.

    PostgreSQL текст с NUL не принимает вовсе, и без этой проверки он
    доходит до вставки: asyncpg бросает CharacterNotInRepertoireError, это
    не IntegrityError, ветка обработки его не ловит — и запрос отвечает
    пятисоткой. Само по себе плохо, но хуже другое: обработчик пишет
    `logger.exception`, а трейсбек SQLAlchemy содержит параметры запроса —
    то есть только что посчитанный хеш пароля новой учётной записи уезжает
    в лог контура и оттуда в резервные копии. Воспроизведено целиком.

    Прочие управляющие символы не роняют ничего и потому опаснее по-своему:
    имя «Иван\x1b[31m» заводится молча и красит собой вывод в терминале у
    того, кто читает логи или выгрузку.
    """
    if _CONTROL.search(value):
        raise ValueError("Недопустимые символы")
    return value


PlainText = Annotated[
    str,
    # Обрезка ДО проверки длины: строка из одних пробелов иначе проходит и
    # ложится в базу пустой, а в списке выглядит сбоем отрисовки.
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(no_control_characters),
]
