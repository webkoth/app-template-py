"""ОБРАЗЕЦ. Удаляется, когда появится первая настоящая фича."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_date", "date"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(255))
    # Целые копейки. Integer — это int4 в PostgreSQL, отсюда предел
    # MAX_AMOUNT_MINOR, который обязан проверять сервис.
    amount_minor: Mapped[int] = mapped_column(Integer)
    # Строка, а не enum базы: список категорий живёт в app/domain/expenses.py
    # и проверяется схемой на записи. Синхронизация только ручная.
    category: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
