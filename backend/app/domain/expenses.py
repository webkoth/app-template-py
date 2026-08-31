"""Расходы: категории и сводка.

ОБРАЗЕЦ. Показывает, как выглядит чистый расчёт: без базы, без HTTP, с
обязательными unit-тестами. Удаляется вместе с образцовой фичей.
"""

from dataclasses import dataclass

# Список живёт здесь, а не enum'ом в базе: категории меняются заметно чаще
# схемы. Цена решения — синхронизация ручная: переименуют категорию в коде,
# старые строки останутся с прежней.
CATEGORIES: tuple[str, ...] = ("Аренда", "Софт", "Оборудование", "Услуги", "Прочее")


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    category: str
    total_minor: int
    share: float


def totals_by_category(rows: list[tuple[str, int]]) -> list[CategoryTotal]:
    """Сводка по категориям, от большей суммы к меньшей.

    Принимает пары «категория, копейки» — не модели SQLAlchemy: доменная
    логика не должна знать, откуда пришли данные, иначе её не проверить без
    базы.
    """
    sums: dict[str, int] = {}
    for category, minor in rows:
        sums[category] = sums.get(category, 0) + minor

    total = sum(sums.values())
    return [
        CategoryTotal(
            category=category,
            total_minor=value,
            share=(value / total) if total else 0.0,
        )
        # Разрыв ничьей по названию, а не «как получилось». Без него порядок
        # категорий с равными суммами определяется порядком строк из базы, и
        # на экране сводки они переставляются между обновлениями страницы —
        # выглядит как мерцание, объясняется ничем. Проверено.
        for category, value in sorted(sums.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
