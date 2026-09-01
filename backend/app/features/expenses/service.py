"""Правила работы с расходами. ОБРАЗЕЦ."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import RecordNotFound, RuleViolation
from app.domain.dates import parse_date_input_value
from app.domain.expenses import CategoryTotal, totals_by_category
from app.domain.money import MAX_AMOUNT_MINOR, format_money, parse_money_to_minor
from app.features.expenses.models import Expense
from app.features.expenses.schemas import CreateExpenseRequest


async def list_expenses(session: AsyncSession) -> list[Expense]:
    result = await session.execute(select(Expense).order_by(Expense.date.desc()))
    return list(result.scalars().all())


async def summary(session: AsyncSession) -> list[CategoryTotal]:
    result = await session.execute(select(Expense.category, Expense.amount_minor))
    return totals_by_category([(row[0], row[1]) for row in result.all()])


async def create_expense(
    session: AsyncSession, payload: CreateExpenseRequest, actor: str
) -> Expense:
    date = parse_date_input_value(payload.date)
    if date is None:
        # Введённое эхом в тексте ошибки: поле type="date" не умеет показать
        # невалидную строку — браузер отдаёт пустое значение, и человек видит
        # пустое поле с сообщением, которому нечего пояснять.
        raise RuleViolation(f"Дата «{payload.date}» не похожа на дату", field="date")

    amount_minor = parse_money_to_minor(payload.amount)
    if amount_minor is None:
        raise RuleViolation("Сумма не похожа на число", field="amount")
    if amount_minor <= 0:
        raise RuleViolation("Сумма должна быть больше нуля", field="amount")
    if amount_minor > MAX_AMOUNT_MINOR:
        raise RuleViolation(
            f"Сумма больше предельной ({format_money(MAX_AMOUNT_MINOR)})",
            field="amount",
        )

    expense = Expense(
        date=date,
        # Без .strip(): обрезает схема, и правило живёт в одном месте.
        title=payload.title,
        category=payload.category,
        amount_minor=amount_minor,
        created_at=datetime.now(UTC),
    )
    session.add(expense)
    await session.flush()
    write_audit(
        session,
        actor,
        "create",
        "Expense",
        str(expense.id),
        f"{expense.category}, {expense.amount_minor} коп.",
    )
    await session.commit()
    return expense


async def delete_expense(
    session: AsyncSession, expense_id: uuid.UUID, actor: str
) -> None:
    expense = await session.get(Expense, expense_id)
    if expense is None:
        raise RecordNotFound("Расход не найден")
    write_audit(session, actor, "delete", "Expense", str(expense.id), expense.title)
    await session.delete(expense)
    await session.commit()
