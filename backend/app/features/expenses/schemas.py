import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.text import PlainText

# Категории перечислены здесь литералами намеренно. Literal[CATEGORIES] из
# переменной в рантайме работает, но mypy такой формы не принимает, и под
# «type: ignore» тип схлопывается в Any — то есть проверка, ради которой
# Literal и нужен, перестаёт существовать.
#
# Расхождение с app/domain/expenses.py ловит тест
# test_schema_categories_match_domain: это дешевле, чем потерять типизацию.
Category = Literal["Аренда", "Софт", "Оборудование", "Услуги", "Прочее"]


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # uuid.UUID, а не str. Pydantic строку из UUID сам не делает — проверено:
    # model_validate падает с «Input should be a valid string». В JSON поле
    # всё равно уезжает строкой, а в схеме OpenAPI получает format: uuid, то
    # есть клиент видит тот же string.
    id: uuid.UUID
    date: datetime
    title: str
    # Сырые копейки: показ форматирует клиент, сортировка и графики требуют
    # числа. Готовая строка сюда не кладётся намеренно.
    amount_minor: int
    category: str
    created_at: datetime


class CreateExpenseRequest(BaseModel):
    # Лишнее поле — ошибка, а не мусор, который молча выбрасывают.
    model_config = ConfigDict(extra="forbid")

    # Дата и сумма приходят строками и разбираются доменом: разбор — правило
    # предметной области, и он обязан быть авторитетным на сервере.
    date: str = Field(min_length=1)
    title: PlainText
    category: Category
    amount: str = Field(min_length=1)


class CategoryTotalOut(BaseModel):
    category: str
    total_minor: int
    share: float
