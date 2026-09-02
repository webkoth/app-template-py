import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # uuid.UUID, а не str: pydantic строку из UUID сам не делает. В JSON поле
    # всё равно уезжает строкой, а в схеме получает format: uuid.
    id: uuid.UUID
    name: str
    original_name: str
    size_bytes: int
    kind: str
    # None означает «ещё не считали». Экран показывает это иначе, чем
    # посчитанную пустую сводку: первое — работа идёт, второе — работа
    # закончена и в таблице ничего не нашлось.
    summary: dict[str, Any] | None
    rows_count: int
    actor: str
    created_at: datetime
