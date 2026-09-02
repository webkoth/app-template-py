"""Печать схемы OpenAPI. Из неё генерируются типы клиента.

Запуск: uv run python -m app.openapi > openapi.json
"""

import json

from app.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
