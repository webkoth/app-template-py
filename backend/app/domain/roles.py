"""Роли по рангу: viewer < editor < admin."""

from enum import StrEnum


class Role(StrEnum):
    viewer = "viewer"
    editor = "editor"
    admin = "admin"


# Порядок значим: ранг — это позиция в кортеже. Выражать «больше прав»
# сравнением строк пришлось бы заново в каждой проверке.
ROLES: tuple[str, ...] = tuple(r.value for r in Role)


def has_rank(actual: Role, required: Role) -> bool:
    """Хватает ли роли actual, чтобы пройти проверку на required."""
    return ROLES.index(actual.value) >= ROLES.index(required.value)
