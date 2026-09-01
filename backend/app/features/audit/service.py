"""Чтение журнала. Записывает в него core/audit.py, читает эта фича."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog

# Верхняя граница жёсткая: журнал растёт неограниченно, и запрос без предела
# однажды выгрузит в память всю историю контура.
MAX_LIMIT = 1000
DEFAULT_LIMIT = 200


async def list_entries(session: AsyncSession, limit: int) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)
    )
    return list(result.scalars().all())
