"""Реестр таблиц не должен отставать от кода.

Проверка идёт в отдельном процессе намеренно. В этом метаданные `Base`
глобальны и уже наполнены: обвязка тестов импортирует `app.main`, тот тянет
роутеры, роутеры — сервисы, сервисы — модели. Сравнивать было бы не с чем,
и проверка была бы зелёной всегда, ничего не охраняя.

В свежем процессе импортируется ТОЛЬКО реестр, состав метаданных
запоминается, и лишь потом обходится весь пакет. Разница между вторым и
первым — таблицы, которые в коде есть, а в реестре нет.
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

PROBE = """
import importlib
import pkgutil

import app
import app.models  # noqa: F401
from app.core.db import Base

listed = set(Base.metadata.tables)

for module in pkgutil.walk_packages(app.__path__, prefix="app."):
    importlib.import_module(module.name)

print(",".join(sorted(set(Base.metadata.tables) - listed)))
"""


def test_every_table_in_the_code_is_listed_in_the_registry():
    probe = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    missing = probe.stdout.strip()
    assert not missing, (
        f"таблицы есть в коде, но не в app/models.py: {missing}. "
        "Без строки в реестре autogenerate выдаст пустую миграцию, "
        "а схема тестовой базы соберётся без этой таблицы — обе поломки молчат."
    )
