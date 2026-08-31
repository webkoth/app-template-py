"""Журнал аудита: пишется при каждой мутации данных."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Предел колонки detail — он же предел того, что журнал готов запомнить.
DETAIL_MAX = 1024


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_ts", "ts"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # Логин строкой, а не связь с users: журнал обязан пережить учётную
    # запись. Работает, пока логины не переименовывают и учётки не удаляют —
    # ни того, ни другого в приложении нет. Появится переименование — журнал
    # разойдётся с реальностью, и решать это придётся здесь.
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(String(1024), default="")


def write_audit(
    session: AsyncSession,
    actor: str,
    action: str,
    entity: str,
    entity_id: str,
    detail: str = "",
) -> None:
    """Кладёт запись в ту же сессию, что и мутация.

    Без commit намеренно: коммитит сервис, одной транзакцией вместе с самим
    изменением. В эталоне запись в журнал шла отдельным вызовом после
    сохранения — падение процесса между ними оставляло изменение без следа,
    а журнал с дырами доверия не заслуживает.

    Длинный detail обрезается, а не роняет запись. Та же общая транзакция
    означает, что строка длиннее колонки отменила бы саму мутацию: расход не
    сохранился бы из-за слишком подробной заметки о нём. Размен плохой, и
    обрезка тут — единственное разумное поведение. Многоточие в конце
    оставляется намеренно, чтобы читающий журнал видел неполноту.
    """
    if len(detail) > DETAIL_MAX:
        detail = detail[: DETAIL_MAX - 1] + "…"

    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail,
        )
    )
