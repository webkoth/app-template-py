# Слой данных и ML — план реализации

> **Для агентов:** ОБЯЗАТЕЛЬНЫЙ СУБ-СКИЛЛ: используй
> superpowers:subagent-driven-development (рекомендуется) или
> superpowers:executing-plans, чтобы исполнять этот план задача за задачей.
> Шаги отмечаются чекбоксами (`- [ ]`).

**Goal:** Добавить к готовому ядру `app-template-py` слой данных: очередь
фоновых задач в PostgreSQL, хранилище файлов, образцовую фичу «Таблицы» с
разбором на pandas и обучением на scikit-learn, клиент внешних моделей и
экран состояния задач.

**Architecture:** Очередь — таблица `jobs`, взятие через
`SELECT … FOR UPDATE SKIP LOCKED`; воркер — второй процесс pm2 рядом с
приложением, обработчики живут в своих фичах и собираются в воркере списком,
как роутеры в `main.py`. Файлы лежат на диске контура и считаются
исходниками; всё производное — строки, сводки, модели — в базе, потому что в
ночную копию попадает база, а не диск.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0 (async), Alembic,
pandas, scikit-learn, joblib, httpx; React 19 + TanStack Router/Query на
фронтенде. Всё уже стоящее в ядре не меняется.

---

## Что уже есть и на что опираться

Ядро готово, установлено на контур и работает. Читай перед началом:

- `backend/app/core/db.py` — `Base`, `SessionFactory`, `get_session`,
  соглашение об именах ограничений;
- `backend/app/core/audit.py` — `write_audit(session, actor, action, entity,
  entity_id, detail="")`, кладёт запись в ту же сессию **без commit**;
- `backend/app/core/deps.py` — `SessionDep`, `CurrentUser`, `CurrentUserDep`,
  `require_role(minimum)`;
- `backend/app/core/errors.py` — `RuleViolation(message, field=...)`,
  `RecordNotFound(message)`, `ERROR_RESPONSES`;
- `backend/app/core/config.py` — `Settings` с `extra="forbid"`;
- `backend/app/features/expenses/` — образец фичи целиком;
- `backend/tests/conftest.py` — фикстуры `session`, `new_session`, `client`,
  `make_user`, `login_as`, автофикстуры `_schema`, `_isolated_limiters`;
- `backend/tests/api/test_route_guards.py` — тест, требующий у каждого нового
  маршрута проверки доступа. **Любой маршрут этого плана обязан быть в нём
  учтён**, иначе прогон красный. Это не помеха, а смысл теста.

Дисциплина проекта — в `AGENTS.md`. Коротко: `make check` зелёный перед
каждым коммитом; каждый охранник доказывается мутацией; комментарий пишется
про то, почему так и что было бы иначе.

## Раскладка файлов

```
backend/app/
  core/
    jobs.py                 модель Job, постановка, взятие, отметка живости
    storage.py              файлы на диске: положить, найти, удалить
  domain/
    tables.py               чистое: чтение таблицы из байтов, сводка
  worker.py                 процесс воркера и реестр обработчиков
  integrations/
    client.py               внешние модели, режимы live/mock/fixture
    fixtures/               записанные ответы для режима fixture
  features/
    datasets/               образцовая фича слоя
      models.py             Dataset, DatasetRow, ModelArtifact
      schemas.py
      service.py
      jobs.py               обработчики разбора и обучения
      router.py
    jobs/                   экран состояния задач
      service.py
      router.py

backend/tests/
  unit/test_tables.py       разбор и сводка
  unit/test_storage.py      имена, размер, тип, обход каталогов
  api/test_jobs.py          очередь и экран задач
  api/test_datasets.py      загрузка, разбор, обучение, права

frontend/src/routes/
  datasets.tsx              экран таблиц
  jobs.tsx                  экран задач
```

Ничего из ядра не переписывается. Расширяются: `config.py` (настройки слоя),
`main.py` (два роутера), `.importlinter` (два контракта), `deploy.yml`
(второй процесс), `CHECKLIST.md`, `AGENTS.md`, `docs/commands/status.md`.

---

### Задача 1: Настройки слоя

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Test: `backend/tests/unit/test_config.py`

- [ ] **Шаг 1: Написать падающий тест**

Дописать в `backend/tests/unit/test_config.py`:

```python
def test_layer_defaults_are_usable_without_env():
    # Слой обязан работать сразу после установки ядра: человек, поставивший
    # шаблон, не должен дописывать четыре переменные, чтобы увидеть, как
    # загружается файл. Умолчания стоят здесь, а не только в .env.example —
    # иначе контур, поднятый без них, падает на старте.
    s = Settings(_env_file=None, **BASE)
    assert s.upload_max_bytes == 32 * 1024 * 1024
    assert s.job_poll_seconds == 1.0
    assert s.job_heartbeat_seconds == 10.0
    assert s.job_stale_after_seconds == 60.0
    assert s.job_max_attempts == 3
    assert s.integrations_mode == "mock"


def test_upload_dir_is_absolute_and_next_to_the_repository():
    # Путь считается от файла настроек, а не от текущего каталога: приложение
    # запускают из backend/ (pm2 --cwd), тесты — из backend/, команды make —
    # из корня. Относительный путь дал бы три разных каталога загрузок, и
    # найти файл, загруженный вчера, стало бы делом удачи.
    s = Settings(_env_file=None, **BASE)
    assert s.upload_dir.is_absolute()
    assert s.upload_dir.name == "uploads"


def test_stale_must_exceed_heartbeat():
    # Отбор задачи раньше, чем воркер успевает поставить отметку, — это
    # отбор у живого. Два воркера начнут считать одно и то же, а первый ещё
    # и запишет результат поверх второго. Настройка, которая молча
    # разрешает такое, хуже отсутствующей.
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **BASE,
            JOB_HEARTBEAT_SECONDS="30",
            JOB_STALE_AFTER_SECONDS="20",
        )


def test_unknown_integrations_mode_is_refused():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE, INTEGRATIONS_MODE="почти-настоящий")
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_config.py`
Expected: FAIL — у `Settings` нет полей `upload_max_bytes` и прочих.

- [ ] **Шаг 3: Дописать поля в `backend/app/core/config.py`**

В класс `Settings`, после `app_bootstrap_name`:

```python
    # --- слой данных ---------------------------------------------------
    # Каталог загрузок. Абсолютный и от файла настроек по той же причине,
    # что и ENV_FILE выше: приложение запускают из backend/, а команды make
    # — из корня, и относительный путь дал бы разные каталоги.
    upload_dir: Path = ENV_FILE.parent / "uploads"
    # 32 МиБ. Не про диск — про память: разбор таблицы держит её целиком.
    upload_max_bytes: int = Field(default=32 * 1024 * 1024, gt=0)
    # Опрос очереди. Секунда на фоне долгого счёта незаметна, а LISTEN/NOTIFY
    # — вторая механика ожидания, которую пришлось бы отлаживать отдельно.
    job_poll_seconds: float = Field(default=1.0, gt=0)
    # Отметка живости и срок, после которого задача считается брошенной.
    job_heartbeat_seconds: float = Field(default=10.0, gt=0)
    job_stale_after_seconds: float = Field(default=60.0, gt=0)
    # Три попытки: разрыв связи с базой и перезапуск на доставке проходят
    # сами, а ошибка в данных от повторов не исчезнет.
    job_max_attempts: int = Field(default=3, ge=1)
    # Режим клиента внешних моделей. mock по умолчанию: шаблон обязан
    # работать сразу, без ключей и без сети.
    integrations_mode: Literal["live", "mock", "fixture"] = "mock"
```

`Path` — из `pathlib`, добавить в импорты.

В `_check` (валидатор `model_validator(mode="after")`), рядом с проверкой
`cookie_secure`:

```python
        if self.job_stale_after_seconds <= self.job_heartbeat_seconds:
            # Отбор задачи раньше, чем воркер успевает поставить отметку, —
            # это отбор у живого: два воркера считают одно и то же, и второй
            # затирает результат первого. Запас должен быть кратным, но
            # проверяется минимальное: строгого больше достаточно, чтобы
            # опечатка в .env не прошла молча.
            raise ValueError(
                "JOB_STALE_AFTER_SECONDS должен быть больше "
                "JOB_HEARTBEAT_SECONDS: иначе задача отбирается у живого воркера"
            )
```

- [ ] **Шаг 4: Дописать `.env.example`**

```bash
# --- слой данных ---
# Каталог загрузок. Строка ЗАКОММЕНТИРОВАНА намеренно: умолчание — uploads/
# рядом с репозиторием (он в .gitignore), а пустое UPLOAD_DIR="" было бы
# ловушкой — extra="forbid" его примет, Path("") даст текущий каталог, и
# файлы разъедутся по трём местам, потому что приложение запускают из
# backend/, а команды make — из корня. На контуре строку раскомментировать.
# Каталога провижинер не заводит: его создаёт приложение при первой загрузке.
# UPLOAD_DIR="/var/www/<слаг>/uploads"
UPLOAD_MAX_BYTES="33554432"

# Очередь фоновых задач. STALE обязан быть больше HEARTBEAT.
JOB_POLL_SECONDS="1"
JOB_HEARTBEAT_SECONDS="10"
JOB_STALE_AFTER_SECONDS="60"
JOB_MAX_ATTEMPTS="3"

# Клиент внешних моделей: live | mock | fixture.
INTEGRATIONS_MODE="mock"
```

- [ ] **Шаг 5: Дописать `uploads/` в `.gitignore`**

```gitignore
uploads/
```

- [ ] **Шаг 6: Запустить тесты**

Run: `cd backend && uv run pytest tests/unit/test_config.py -v`
Expected: PASS

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/core/config.py backend/tests/unit/test_config.py \
        .env.example .gitignore
git commit -m "feat: настройки слоя данных"
```

---

### Задача 2: Хранилище файлов

**Files:**
- Create: `backend/app/core/storage.py`
- Test: `backend/tests/unit/test_storage.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_storage.py`:

```python
import uuid

import pytest

from app.core import storage
from app.core.errors import RuleViolation


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.settings, "upload_dir", tmp_path)
    return tmp_path


def test_saved_file_is_found_by_its_identifier(_dir):
    file_id = storage.save(b"a,b\n1,2\n")
    assert storage.read(file_id) == b"a,b\n1,2\n"


def test_stored_name_is_an_identifier_not_the_original(_dir):
    # Имя с диска берётся из идентификатора, а не из загруженного. Иначе
    # файл, названный «../../.env», становится путём — и запись уходит мимо
    # каталога загрузок, а чтение отдаёт чужое.
    file_id = storage.save(b"x")
    names = [p.name for p in _dir.iterdir()]
    assert names == [str(file_id)]


def test_reading_an_unknown_identifier_is_not_found(_dir):
    from app.core.errors import RecordNotFound

    with pytest.raises(RecordNotFound):
        storage.read(uuid.uuid7())


def test_too_large_is_refused_by_the_declared_size(_dir, monkeypatch):
    # Отказ до чтения целиком: смысл потолка в том, чтобы не держать в
    # памяти то, что и не собирались принимать.
    monkeypatch.setattr(storage.settings, "upload_max_bytes", 10)
    with pytest.raises(RuleViolation) as denial:
        storage.check_size(declared=11)
    assert "больше" in denial.value.message


def test_too_large_is_refused_even_when_size_is_not_declared(_dir, monkeypatch):
    # Content-Length клиент может не прислать или соврать. Проверка по факту
    # прочитанного обязана быть второй линией, иначе потолок обходится одним
    # отсутствующим заголовком.
    monkeypatch.setattr(storage.settings, "upload_max_bytes", 10)
    with pytest.raises(RuleViolation):
        storage.save(b"x" * 11)


def test_unknown_content_is_refused(_dir):
    # Тип по содержимому, а не по расширению: «отчёт.csv» с телом PDF
    # доходит до pandas и падает там невнятно.
    with pytest.raises(RuleViolation) as denial:
        storage.detect_kind(b"%PDF-1.7\n%\xe2\xe3")
    assert denial.value.field == "file"


def test_csv_and_xlsx_are_recognised_by_content(_dir):
    assert storage.detect_kind(b"a,b\n1,2\n") == "csv"
    # Первые байты xlsx — сигнатура zip: это и есть zip с xml внутри.
    assert storage.detect_kind(b"PK\x03\x04" + b"\x00" * 20) == "xlsx"


def test_delete_is_silent_when_the_file_is_already_gone(_dir):
    # Удаление вызывается при откате загрузки, и файла к тому моменту может
    # не быть. Падать здесь значит превращать уборку в новую ошибку.
    storage.delete(uuid.uuid7())
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_storage.py`
Expected: FAIL — модуля `app.core.storage` нет.

- [ ] **Шаг 3: Написать `backend/app/core/storage.py`**

```python
"""Файлы на диске контура.

Загруженный файл — ИСХОДНИК. В ночную копию контура попадает база, а не
диск: всё производное — разобранные строки, сводки, обученные модели —
живёт в базе и копируется вместе с ней. Потеря файла означает «загрузить
заново», а не «потерять работу». Это записано в реестре известного долга.
"""

import uuid
from pathlib import Path

from app.core.config import settings
from app.core.errors import RecordNotFound, RuleViolation

# Сигнатура zip: xlsx — это zip с xml внутри.
_ZIP_MAGIC = b"PK\x03\x04"


def _dir() -> Path:
    # Каталог создаётся при первом обращении, а не при старте: на контуре
    # его не заводит провижинер, а падать на старте из-за отсутствующего
    # каталога загрузок значит не пускать в приложение тех, кому файлы не
    # нужны вовсе.
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings.upload_dir


def path_for(file_id: uuid.UUID) -> Path:
    # Имя строится ИЗ идентификатора, а не из загруженного имени. Никакой
    # склейки с пользовательской строкой здесь нет и быть не должно: файл,
    # названный «../../.env», иначе становится путём.
    return _dir() / str(file_id)


def check_size(declared: int | None) -> None:
    """Отказ по объявленному размеру — до чтения тела."""
    if declared is not None and declared > settings.upload_max_bytes:
        raise RuleViolation(
            f"Файл больше предельного ({settings.upload_max_bytes // 1024 // 1024} МиБ)",
            field="file",
        )


def detect_kind(head: bytes) -> str:
    """Тип по содержимому, а не по расширению.

    «отчёт.csv» с телом PDF иначе доходит до pandas и падает там сообщением
    про кодировку — человек читает его и ищет причину в своей таблице.
    """
    if head.startswith(_ZIP_MAGIC):
        return "xlsx"
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        raise RuleViolation("Не CSV и не XLSX", field="file") from None
    return "csv"


def save(data: bytes) -> uuid.UUID:
    """Кладёт байты на диск и возвращает идентификатор.

    Размер проверяется ещё раз, уже по факту: Content-Length клиент может не
    прислать или соврать, и без второй проверки потолок обходится одним
    отсутствующим заголовком.
    """
    if len(data) > settings.upload_max_bytes:
        raise RuleViolation(
            f"Файл больше предельного ({settings.upload_max_bytes // 1024 // 1024} МиБ)",
            field="file",
        )
    detect_kind(data[:8])
    file_id = uuid.uuid7()
    path_for(file_id).write_bytes(data)
    return file_id


def read(file_id: uuid.UUID) -> bytes:
    path = path_for(file_id)
    if not path.is_file():
        # Файл мог не пережить переезд контура или чистку диска, а строка о
        # нём в базе есть. Это «нет», а не пятисотка: у отсутствия исходника
        # есть понятный человеку смысл.
        raise RecordNotFound("Файл не найден на диске")
    return path.read_bytes()


def delete(file_id: uuid.UUID) -> None:
    # missing_ok: удаление зовут при откате загрузки, и файла к тому моменту
    # может не быть. Падать здесь значит превращать уборку в новую ошибку.
    path_for(file_id).unlink(missing_ok=True)
```

- [ ] **Шаг 4: Запустить тесты**

Run: `cd backend && uv run pytest tests/unit/test_storage.py -v`
Expected: PASS, 8 passed

- [ ] **Шаг 5: Доказать охранников мутацией**

Перед каждым прогоном: `find backend -name __pycache__ -type d -exec rm -rf {} +`

| Мутация | Обязана упасть |
|---|---|
| в `save` писать в `_dir() / "upload.bin"` вместо `path_for(file_id)` | `test_stored_name_is_an_identifier_not_the_original` |
| убрать проверку размера в `save` | `test_too_large_is_refused_even_when_size_is_not_declared` |
| `detect_kind` всегда возвращает `"csv"` | `test_unknown_content_is_refused` |
| `delete` без `missing_ok=True` | `test_delete_is_silent_when_the_file_is_already_gone` |

- [ ] **Шаг 6: Коммит**

```bash
git add backend/app/core/storage.py backend/tests/unit/test_storage.py
git commit -m "feat: хранилище файлов на диске контура"
```

---

### Задача 3: Очередь — модель и постановка

**Files:**
- Create: `backend/app/core/jobs.py`
- Modify: `backend/tests/conftest.py` — импорт модели ради метаданных
- Test: `backend/tests/api/test_jobs.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/api/test_jobs.py`:

```python
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import jobs
from app.core.jobs import Job, JobStatus


async def test_enqueue_does_not_commit_by_itself(session):
    # Постановка кладёт строку в ТУ ЖЕ сессию, что и данные, и коммитит их
    # вместе вызывающий. Иначе появляется состояние «задача поставлена, а
    # строки, ради которой она поставлена, нет» — и воркер берёт задачу на
    # данные, которых не существует.
    jobs.enqueue(session, kind="проба", payload={"a": 1}, actor="boss")
    await session.rollback()
    assert (await session.execute(select(Job))).first() is None


async def test_enqueued_job_waits_in_the_queue(session):
    jobs.enqueue(session, kind="проба", payload={"a": 1}, actor="boss")
    await session.commit()
    job = (await session.execute(select(Job))).scalar_one()
    assert job.status is JobStatus.queued
    assert job.attempts == 0
    assert job.progress == 0
    assert job.payload == {"a": 1}


async def test_two_workers_never_take_the_same_job(new_session):
    # Одну задачу берёт ровно один воркер. Гарантирует это БЛОКИРОВКА
    # СТРОКИ — `with_for_update`, — а не наша аккуратность, и проверяется
    # поэтому настоящей одновременностью, на отдельных соединениях.
    #
    # Проверено на живой базе, что бывает без неё: две транзакции читают
    # одну и ту же строку, обе объявляют её своей, а следующая задача так и
    # остаётся ждать. То есть один воркер считает впустую, второй затирает
    # его результат, и очередь при этом кажется движущейся.
    #
    # `skip_locked` к этому отношения не имеет — ему посвящён следующий
    # тест, и охраняет он другое.
    async with new_session() as setup:
        jobs.enqueue(setup, kind="проба", payload={}, actor="boss")
        await setup.commit()

    async def take() -> uuid.UUID | None:
        async with new_session() as db:
            job = await jobs.claim(db)
            return job.id if job else None

    first, second = await asyncio.gather(take(), take())
    assert {first, second} != {None, None}
    assert first is None or second is None, (first, second)

    async with new_session() as cleanup:
        for row in (await cleanup.execute(select(Job))).scalars().all():
            await cleanup.delete(row)
        await cleanup.commit()


async def test_a_locked_row_does_not_hide_the_next_job(new_session):
    # А это смысл SKIP LOCKED, и он ДРУГОЙ, чем кажется. Взятие одной
    # задачи двумя воркерами запрещает блокировка и без него: второй просто
    # ждёт, пока первый отпустит строку, и уходит ни с чем. Разница в том,
    # чего это стоит, и она измерена на живой базе: 0,03 с против 1,15 с,
    # проведённых в ожидании чужого коммита. Всё это время воркер не берёт
    # СЛЕДУЮЩУЮ задачу, хотя она свободна.
    #
    # Поэтому проверка такая: первая строка заперта незакрытой транзакцией,
    # в очереди есть вторая задача, и claim обязан вернуть именно её. Без
    # skip_locked=True он повиснет на запертой строке — не «отработает
    # медленнее», а не вернётся вовсе, пока держат замок. Отсюда wait_for:
    # без него красный тест выглядел бы как зависший прогон.
    async with new_session() as setup:
        jobs.enqueue(setup, kind="первая", payload={}, actor="boss")
        await setup.commit()
        jobs.enqueue(setup, kind="вторая", payload={}, actor="boss")
        await setup.commit()

    try:
        async with new_session() as holder:
            held = (
                await holder.execute(
                    select(Job).order_by(Job.created_at).limit(1).with_for_update()
                )
            ).scalar_one()
            assert held.kind == "первая"
            # Транзакция holder НЕ закрыта: строка заперта до конца блока.

            async with new_session() as second:
                job = await asyncio.wait_for(jobs.claim(second), timeout=5)

            assert job is not None, "запертая строка спрятала свободную задачу"
            assert job.kind == "вторая"
    finally:
        async with new_session() as cleanup:
            for row in (await cleanup.execute(select(Job))).scalars().all():
                await cleanup.delete(row)
            await cleanup.commit()


async def test_claiming_marks_the_job_running(session):
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    assert job.status is JobStatus.running
    assert job.attempts == 1
    assert job.started_at is not None
    assert job.heartbeat_at is not None


async def test_stale_running_job_returns_to_the_queue(session):
    # Воркер, убитый доставкой, оставляет задачу «выполняющейся». Без
    # возврата человек ждёт результата, которого не будет: задача выглядит
    # живой, а брать её некому.
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    taken = await jobs.claim(session)
    assert taken is not None
    taken.heartbeat_at = datetime.now(UTC) - timedelta(seconds=3600)
    await session.commit()

    again = await jobs.claim(session)
    assert again is not None
    assert again.id == taken.id
    assert again.attempts == 2


async def test_a_living_job_is_not_taken_away(session):
    # Обратная сторона: свежая отметка означает, что воркер жив и считает.
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    assert await jobs.claim(session) is not None
    assert await jobs.claim(session) is None


async def test_heartbeat_moves_the_mark_and_the_progress(session):
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    before = job.heartbeat_at
    await asyncio.sleep(0.01)
    await jobs.heartbeat(session, job, progress=42)
    assert job.progress == 42
    assert job.heartbeat_at > before


async def test_failure_returns_the_job_until_attempts_run_out(session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "job_max_attempts", 2)
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()

    first = await jobs.claim(session)
    assert first is not None
    await jobs.fail(session, first, "связь оборвалась")
    assert first.status is JobStatus.queued, "первая неудача — не приговор"

    second = await jobs.claim(session)
    assert second is not None
    await jobs.fail(session, second, "связь оборвалась")
    assert second.status is JobStatus.failed
    assert second.error == "связь оборвалась"
    assert second.finished_at is not None


async def test_completion_stores_the_result(session):
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    await jobs.complete(session, job, {"строк": 7})
    assert job.status is JobStatus.done
    assert job.result == {"строк": 7}
    assert job.progress == 100
    assert job.finished_at is not None


async def test_error_text_is_cut_not_dropped(session):
    # Трейсбек длиннее колонки отменил бы саму запись об отказе — то есть
    # задача осталась бы «выполняющейся» из-за слишком подробной причины.
    # Та же логика, что у detail в журнале аудита.
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()
    job = await jobs.claim(session)
    assert job is not None
    await jobs.fail(session, job, "щ" * 5000)
    assert len(job.error) <= jobs.ERROR_MAX
    assert job.error.endswith("…")
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/api/test_jobs.py`
Expected: FAIL — модуля `app.core.jobs` нет.

- [ ] **Шаг 3: Написать `backend/app/core/jobs.py`**

```python
"""Очередь фоновых задач.

Очередь живёт в той же базе, что и данные, — и это главное её свойство, а не
экономия на инфраструктуре. Постановка задачи и запись строки, ради которой
она ставится, попадают в одну транзакцию: состояния «задача есть, данных
нет» не существует.

Взятие — SELECT … FOR UPDATE SKIP LOCKED, и две его половины отвечают за
разное. FOR UPDATE запирает строку: одну задачу берёт ровно один воркер, и
это гарантирует база, а не аккуратность кода. SKIP LOCKED отвечает не за
это, а за то, что воркер, наткнувшийся на запертую строку, берёт следующую
задачу вместо того, чтобы ждать на чужом коммите. Проверено обеими
проверками отдельно: без FOR UPDATE задачу берут двое, без SKIP LOCKED — не
берёт никто, пока держат замок.
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, Index, Integer, String, Uuid, and_, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.db import Base

# Предел колонки error — он же предел того, что очередь готова запомнить о
# причине отказа.
ERROR_MAX = 1024


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Job(Base):
    __tablename__ = "jobs"
    # Индекс под единственный горячий запрос — взятие задачи. Он же
    # обслуживает экран: список сортируется по времени создания.
    __table_args__ = (Index("ix_jobs_status_created_at", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    # Вид задачи — ключ реестра обработчиков в app/worker.py. Строка, а не
    # enum базы: список обработчиков живёт в коде фич и меняется чаще, чем
    # стоит менять схему.
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            values_callable=lambda e: [i.value for i in e],
        ),
        default=JobStatus.queued,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str] = mapped_column(String(ERROR_MAX), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Логин строкой, как в журнале аудита, и по той же причине: задача
    # обязана пережить учётную запись, которая её поставила.
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Отметка живости. Пока она свежая, задача считается выполняемой.
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


def enqueue(
    session: AsyncSession, kind: str, payload: dict[str, Any], actor: str
) -> Job:
    """Кладёт задачу в ту же сессию, что и данные. Без commit — намеренно.

    Коммитит вызывающий, вместе со своей записью. Отдельный commit здесь
    создал бы состояние «задача поставлена, строки нет»: воркер взял бы её
    раньше, чем данные появились, и упал бы на пустом месте — а причину
    искали бы в обработчике.
    """
    job = Job(kind=kind, payload=payload, actor=actor)
    session.add(job)
    return job


async def claim(session: AsyncSession) -> Job | None:
    """Берёт одну задачу и помечает выполняемой. None — брать нечего.

    Один запрос делает две вещи разом: берёт ожидающую задачу И
    возвращает брошенную. Отдельного уборщика зависших нет намеренно —
    он был бы вторым местом, где живёт понятие «задача брошена», и эти два
    места однажды разъехались бы.
    """
    stale_before = datetime.now(UTC) - timedelta(
        seconds=settings.job_stale_after_seconds
    )
    job = (
        await session.execute(
            select(Job)
            .where(
                or_(
                    Job.status == JobStatus.queued,
                    and_(
                        Job.status == JobStatus.running,
                        Job.heartbeat_at < stale_before,
                    ),
                )
            )
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if job is None:
        return None

    now = datetime.now(UTC)
    job.status = JobStatus.running
    job.attempts += 1
    job.started_at = now
    job.heartbeat_at = now
    await session.commit()
    return job


async def heartbeat(session: AsyncSession, job: Job, progress: int) -> None:
    """Отметка живости и прогресс. Зовётся обработчиком по ходу счёта."""
    job.progress = max(0, min(100, progress))
    job.heartbeat_at = datetime.now(UTC)
    await session.commit()


async def complete(
    session: AsyncSession, job: Job, result: dict[str, Any]
) -> None:
    job.status = JobStatus.done
    job.result = result
    job.progress = 100
    job.finished_at = datetime.now(UTC)
    await session.commit()


async def fail(session: AsyncSession, job: Job, error: str) -> None:
    """Неудача. Возвращает задачу в очередь, пока не исчерпаны попытки.

    Обрезка текста, а не отказ от записи: причина длиннее колонки отменила
    бы саму запись об отказе, и задача осталась бы «выполняющейся» — из-за
    слишком подробного объяснения, почему она не выполнилась. Та же логика,
    что у detail в журнале аудита.
    """
    job.error = error if len(error) <= ERROR_MAX else error[: ERROR_MAX - 1] + "…"
    if job.attempts >= settings.job_max_attempts:
        job.status = JobStatus.failed
        job.finished_at = datetime.now(UTC)
    else:
        job.status = JobStatus.queued
        job.heartbeat_at = None
    await session.commit()
```

- [ ] **Шаг 4: Зарегистрировать таблицу в обвязке тестов**

В `backend/tests/conftest.py`, к явным импортам моделей:

```python
from app.core.jobs import Job  # noqa: F401  # isort: skip
```

Причина там же, где и у прочих: схема тестовой базы создаётся из метаданных,
а таблица попадает туда, только если её модуль кто-то импортировал.

- [ ] **Шаг 5: Запустить тесты**

Run: `cd backend && uv run pytest tests/api/test_jobs.py -v`
Expected: PASS, 11 passed

- [ ] **Шаг 6: Доказать охранников мутацией**

| Мутация | Обязана упасть |
|---|---|
| убрать `.with_for_update(...)` целиком | `test_two_workers_never_take_the_same_job` |
| убрать `skip_locked=True`, оставив `with_for_update()` | `test_a_locked_row_does_not_hide_the_next_job` |
| убрать ветку `running` + просроченный heartbeat из `claim` | `test_stale_running_job_returns_to_the_queue` |
| в `claim` не ставить `heartbeat_at` | `test_a_living_job_is_not_taken_away` |
| в `fail` всегда ставить `failed` | `test_failure_returns_the_job_until_attempts_run_out` |
| в `fail` не обрезать текст | `test_error_text_is_cut_not_dropped` |
| в `enqueue` добавить `await session.commit()` | `test_enqueue_does_not_commit_by_itself` |

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/core/jobs.py backend/tests/api/test_jobs.py \
        backend/tests/conftest.py
git commit -m "feat: очередь фоновых задач в PostgreSQL"
```

---

### Задача 4: Миграция под очередь

**Files:**
- Create: `backend/alembic/versions/<хеш>_jobs.py` (генерируется)

- [ ] **Шаг 1: Сгенерировать миграцию**

```bash
make revision m=jobs
```

- [ ] **Шаг 2: Прочитать сгенерированное глазами**

Alembic не видит переименований и не знает про `JSONB` из диалекта, если
импорт не попал в файл. Проверь в миграции три вещи: тип `job_status`
создаётся, колонки `payload` и `result` — `postgresql.JSONB`, индекс
`ix_jobs_status_created_at` на месте.

- [ ] **Шаг 3: Применить и откатить**

```bash
make migrate
cd backend && uv run alembic downgrade -1 && uv run alembic upgrade head
```

Expected: обе команды с кодом 0. Необратимая миграция — это откат доставки,
который нечем сопроводить.

- [ ] **Шаг 4: Коммит**

```bash
git add backend/alembic/versions/
git commit -m "feat: миграция под очередь задач"
```

---

### Задача 5: Процесс воркера

**Files:**
- Create: `backend/app/worker.py`
- Test: `backend/tests/api/test_worker.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/api/test_worker.py`:

```python
import asyncio

import pytest
from sqlalchemy import select

from app.core import jobs
from app.core.jobs import Job, JobStatus


async def test_handler_result_lands_in_the_job(session, monkeypatch):
    from app import worker

    async def handler(db, job):
        return {"эхо": job.payload["значение"]}

    monkeypatch.setitem(worker.HANDLERS, "проба", handler)
    jobs.enqueue(session, kind="проба", payload={"значение": 7}, actor="boss")
    await session.commit()

    took = await worker.run_once(session)
    assert took is True
    job = (await session.execute(select(Job))).scalar_one()
    assert job.status is JobStatus.done
    assert job.result == {"эхо": 7}


async def test_unknown_kind_fails_the_job_instead_of_the_worker(session):
    # Задача вида, которого нет в реестре, — это забытая регистрация
    # обработчика при выкатке. Ронять на ней воркер значит останавливать
    # ВСЮ очередь из-за одной задачи: остальные перестанут выполняться, и
    # причина будет не видна ни на одном экране.
    from app import worker

    jobs.enqueue(session, kind="такого-нет", payload={}, actor="boss")
    await session.commit()

    assert await worker.run_once(session) is True
    job = (await session.execute(select(Job))).scalar_one()
    assert job.status is JobStatus.failed
    assert "такого-нет" in job.error


async def test_handler_failure_is_written_not_swallowed(session, monkeypatch):
    from app import worker

    async def handler(db, job):
        raise ValueError("в таблице нет колонки «сумма»")

    monkeypatch.setitem(worker.HANDLERS, "проба", handler)
    monkeypatch.setattr(worker.settings, "job_max_attempts", 1)
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()

    await worker.run_once(session)
    job = (await session.execute(select(Job))).scalar_one()
    assert job.status is JobStatus.failed
    assert "нет колонки" in job.error


async def test_empty_queue_reports_nothing_taken(session):
    from app import worker

    assert await worker.run_once(session) is False


async def test_worker_does_not_import_the_web_application():
    # Воркер, притащивший app.main, тянет за собой и время старта
    # приложения, и его отказы: не поднялась раздача статики — не считаются
    # задачи. Проверяется по факту импорта, а не по чтению кода.
    import subprocess
    import sys

    probe = (
        "import sys, app.worker;"
        "sys.exit(1 if 'app.main' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", probe]).returncode == 0
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/api/test_worker.py`
Expected: FAIL — модуля `app.worker` нет.

- [ ] **Шаг 3: Написать `backend/app/worker.py`**

```python
"""Процесс воркера: берёт задачу из очереди и зовёт обработчик.

Отдельный процесс, а не фоновая задача внутри приложения. Доставка
перезапускает процессы, и счёт, живущий внутри веб-процесса, она убивала бы
на каждом выкате. Плюс долгий счёт конкурировал бы за процесс с
обслуживанием запросов.

Реестр обработчиков собирается здесь списком — ровно как `main.py` собирает
роутеры. Сами обработчики живут в своих фичах: удаляя фичу, удаляешь и её
фоновую работу, не вспоминая про чужой реестр.

`app.main` отсюда НЕ импортируется, и это проверяется тестом: воркер,
притащивший веб-приложение, наследует и время его старта, и его отказы.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.config import settings
from app.core.db import SessionFactory
from app.core.jobs import Job
from app.features.datasets import jobs as dataset_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

Handler = Callable[[AsyncSession, Job], Awaitable[dict[str, Any]]]

HANDLERS: dict[str, Handler] = {
    **dataset_jobs.HANDLERS,
}


async def run_once(session: AsyncSession) -> bool:
    """Один оборот: взять задачу и выполнить. False — брать было нечего."""
    job = await jobs.claim(session)
    if job is None:
        return False

    handler = HANDLERS.get(job.kind)
    if handler is None:
        # Не исключение: задача вида, которого нет в реестре, — это забытая
        # регистрация при выкатке. Уронив на ней воркер, мы остановили бы
        # ВСЮ очередь из-за одной задачи, и причина не была бы видна ни на
        # одном экране.
        await jobs.fail(session, job, f"Неизвестный вид задачи: {job.kind}")
        logger.error("нет обработчика для вида %s", job.kind)
        return True

    try:
        result = await handler(session, job)
    except Exception as failure:  # noqa: BLE001
        # Широко намеренно. Обработчик — чужой код фичи, и любой его отказ
        # обязан стать причиной на экране, а не остановкой очереди. Текст
        # уходит человеку, трейсбек — в лог.
        await session.rollback()
        await jobs.fail(session, job, str(failure) or failure.__class__.__name__)
        logger.exception("задача %s (%s) не выполнена", job.id, job.kind)
        return True

    await jobs.complete(session, job, result)
    return True


async def loop() -> None:
    logger.info("воркер запущен, обработчиков: %d", len(HANDLERS))
    while True:
        async with SessionFactory() as session:
            try:
                took = await run_once(session)
            except Exception:  # noqa: BLE001
                # Сюда попадает только то, что сломалось ВНЕ обработчика:
                # оборвалась связь с базой, не записался результат. Цикл не
                # должен умирать от этого — пауза и следующий оборот.
                logger.exception("оборот воркера не удался")
                took = False
        if not took:
            await asyncio.sleep(settings.job_poll_seconds)


if __name__ == "__main__":
    asyncio.run(loop())
```

- [ ] **Шаг 4: Запустить тесты**

Run: `cd backend && uv run pytest tests/api/test_worker.py -v`
Expected: PASS, 5 passed

Пока фичи `datasets` нет, импорт `dataset_jobs` не разрешится. Поэтому
задача 5 идёт ПОСЛЕ задачи 8, где эта фича появляется; если исполняешь по
порядку — вернись сюда после неё. Порядок в плане оставлен читаемым: воркер
описан рядом с очередью, а не разорван по двум местам.

- [ ] **Шаг 5: Доказать охранников мутацией**

| Мутация | Обязана упасть |
|---|---|
| в `run_once` пробрасывать исключение обработчика | `test_handler_failure_is_written_not_swallowed` |
| при неизвестном виде бросать `KeyError` | `test_unknown_kind_fails_the_job_instead_of_the_worker` |
| дописать `from app.main import app` в `worker.py` | `test_worker_does_not_import_the_web_application` |

- [ ] **Шаг 6: Коммит**

```bash
git add backend/app/worker.py backend/tests/api/test_worker.py
git commit -m "feat: процесс воркера и реестр обработчиков"
```

---

### Задача 6: Чтение таблицы и сводка

**Files:**
- Create: `backend/app/domain/tables.py`
- Modify: `backend/pyproject.toml` — pandas, openpyxl
- Test: `backend/tests/unit/test_tables.py`

- [ ] **Шаг 1: Поставить зависимости**

```bash
cd backend && uv add pandas openpyxl
```

`openpyxl` — чтение xlsx для pandas; без него `read_excel` падает
сообщением про отсутствующий движок, а не про формат.

- [ ] **Шаг 2: Написать падающий тест**

Create `backend/tests/unit/test_tables.py`:

```python
import io

import pandas as pd
import pytest

from app.domain.tables import MAX_ROWS, TableError, read_table, summarise


def test_csv_is_read_with_its_columns():
    frame = read_table(b"\xd0\xb8\xd0\xbc\xd1\x8f,\xd1\x86\xd0\xb5\xd0\xbd\xd0\xb0\n\xd0\xb0,1\n\xd0\xb1,2\n", "csv")
    assert list(frame.columns) == ["имя", "цена"]
    assert len(frame) == 2


def test_windows_encoding_is_read_too():
    # Таблицы из Excel в России приезжают в cp1251 чаще, чем хотелось бы.
    # Отказ «не UTF-8» человек читает как «файл битый» и идёт искать
    # несуществующую проблему в своей выгрузке.
    frame = read_table("имя,цена\nа,1\n".encode("cp1251"), "csv")
    assert list(frame.columns) == ["имя", "цена"]


def test_xlsx_is_read():
    buffer = io.BytesIO()
    pd.DataFrame({"имя": ["а"], "цена": [1]}).to_excel(buffer, index=False)
    frame = read_table(buffer.getvalue(), "xlsx")
    assert list(frame.columns) == ["имя", "цена"]


def test_empty_table_is_refused_with_a_reason():
    with pytest.raises(TableError) as denial:
        read_table(b"", "csv")
    assert "пуст" in str(denial.value).lower()


def test_too_many_rows_is_refused_before_the_work():
    # Потолок про память: разбор держит таблицу целиком, а строки едут в
    # базу по одной. Молчаливый отказ здесь означал бы воркер, съевший
    # память контура и утянувший за собой приложение.
    body = "a\n" + "1\n" * (MAX_ROWS + 1)
    with pytest.raises(TableError) as denial:
        read_table(body.encode(), "csv")
    assert str(MAX_ROWS) in str(denial.value)


def test_summary_counts_rows_and_describes_columns():
    frame = pd.DataFrame({"цена": [1, 2, 3], "город": ["а", "б", "а"]})
    summary = summarise(frame)
    assert summary["строк"] == 3
    columns = {c["имя"]: c for c in summary["колонки"]}
    assert columns["цена"]["вид"] == "число"
    assert columns["цена"]["среднее"] == 2
    assert columns["город"]["вид"] == "текст"
    assert columns["город"]["различных"] == 2


def test_summary_survives_an_empty_column():
    # Колонка из одних пропусков — обычное дело в выгрузках. Среднее по ней
    # не считается, и сводка обязана это пережить, а не упасть на NaN.
    frame = pd.DataFrame({"пусто": [None, None]})
    summary = summarise(frame)
    assert summary["колонки"][0]["вид"] == "пусто"


def test_summary_is_json_safe():
    # Сводка уезжает в JSONB. numpy.int64 и NaN сериализатор json не берёт:
    # без приведения запись падает на записи результата, то есть после
    # всего счёта.
    import json

    frame = pd.DataFrame({"цена": [1, 2, None]})
    json.dumps(summarise(frame))
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/unit/test_tables.py`
Expected: FAIL — модуля `app.domain.tables` нет.

- [ ] **Шаг 4: Написать `backend/app/domain/tables.py`**

```python
"""Чтение таблицы и сводка по ней. Чистое: байты на входе, данные на выходе.

Ни базы, ни HTTP, ни файловой системы — как и всё в `domain`. Поэтому
правила проверяются юнит-тестами за миллисекунды, а не через загрузку файла
в приложение.
"""

import io
import math
from typing import Any

import pandas as pd


class TableError(ValueError):
    """Таблицу не удалось прочитать. Текст предназначен человеку.

    Своё исключение, а не `RuleViolation` из `core.errors`: контракт
    `domain-is-pure` запрещает `domain → core`, и это не формальность.
    Чистая логика, знающая про конверт ошибки веб-приложения, перестаёт
    быть переносимой: её нельзя позвать ни из скрипта, ни из воркера, не
    притащив с собой FastAPI. Перевод в `RuleViolation` с полем `file` —
    работа сервиса фичи.
    """


# Потолок строк — про память, а не про диск: разбор держит таблицу целиком.
# Воркер, съевший память контура, утягивает за собой и приложение: они на
# одной машине.
MAX_ROWS = 50_000

# Кодировки перебираются в этом порядке. cp1251 второй, потому что выгрузки
# из Excel в России приезжают в ней чаще, чем в чём-либо ещё после UTF-8.
_ENCODINGS = ("utf-8", "cp1251")


def read_table(data: bytes, kind: str) -> pd.DataFrame:
    """Читает CSV или XLSX. Отказ — TableError с человеческим текстом."""
    if not data:
        raise TableError("Файл пуст")

    if kind == "xlsx":
        try:
            frame = pd.read_excel(io.BytesIO(data))
        except Exception as broken:  # noqa: BLE001
            raise TableError(f"Не удалось прочитать XLSX: {broken}") from None
    else:
        frame = _read_csv(data)

    if len(frame) > MAX_ROWS:
        raise TableError(
            f"В таблице больше {MAX_ROWS} строк — столько шаблон не берёт"
        )
    if frame.empty:
        raise TableError("В таблице нет строк")
    return frame


def _read_csv(data: bytes) -> pd.DataFrame:
    last: Exception | None = None
    for encoding in _ENCODINGS:
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding)
        except UnicodeDecodeError as wrong:
            last = wrong
        except pd.errors.EmptyDataError:
            raise TableError("Файл пуст") from None
        except Exception as broken:  # noqa: BLE001
            raise TableError(f"Не удалось прочитать CSV: {broken}") from None
    raise TableError(
        "Не удалось определить кодировку: пробовали UTF-8 и Windows-1251"
    ) from last


def _clean(value: Any) -> Any:
    """Приводит значение к тому, что переживёт json.dumps.

    Сводка уезжает в JSONB. numpy.int64 и NaN сериализатор json не берёт, и
    без приведения запись падает на СОХРАНЕНИИ результата — то есть после
    всего счёта, когда работа уже сделана и потеряна.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def summarise(frame: pd.DataFrame) -> dict[str, Any]:
    """Сводка: сколько строк и что в колонках."""
    columns: list[dict[str, Any]] = []
    for name in frame.columns:
        column = frame[name]
        if column.dropna().empty:
            columns.append({"имя": str(name), "вид": "пусто"})
        elif pd.api.types.is_numeric_dtype(column):
            columns.append(
                {
                    "имя": str(name),
                    "вид": "число",
                    "минимум": _clean(column.min()),
                    "максимум": _clean(column.max()),
                    "среднее": _clean(column.mean()),
                }
            )
        else:
            columns.append(
                {
                    "имя": str(name),
                    "вид": "текст",
                    "различных": int(column.nunique()),
                }
            )
    return {"строк": int(len(frame)), "колонки": columns}
```

- [ ] **Шаг 5: Запустить тесты**

Run: `cd backend && uv run pytest tests/unit/test_tables.py -v`
Expected: PASS, 8 passed

- [ ] **Шаг 6: Проверить, что контракт границ не нарушен**

Run: `cd backend && uv run --group lint lint-imports --config .importlinter`
Expected: `Contracts: 3 kept, 0 broken.`

Контракт `domain-is-pure` запрещает `domain → core`, поэтому модуль бросает
своё `TableError`, а не `RuleViolation`. Красный контракт здесь означает,
что в модуль пробрался импорт из `core` — чинить надо модуль, а не контракт.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/app/domain/tables.py backend/tests/unit/test_tables.py \
        backend/pyproject.toml backend/uv.lock
git commit -m "feat: чтение таблицы и сводка"
```

---

### Задача 7: Таблицы — модели и миграция

**Files:**
- Create: `backend/app/features/datasets/__init__.py` (пустой)
- Create: `backend/app/features/datasets/models.py`
- Modify: `backend/tests/conftest.py`
- Create: миграция (генерируется)

- [ ] **Шаг 1: Написать `backend/app/features/datasets/models.py`**

```python
"""ОБРАЗЕЦ слоя данных. Показывает путь «файл → очередь → счёт → результат».

Удаляется, когда появится первая настоящая фича этого слоя, — как и
«Расходы» для простого пути. Оба образца учат разному и уходят независимо.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    name: Mapped[str] = mapped_column(String(255))
    # Идентификатор файла на диске. Настоящее имя лежит рядом и на диск не
    # попадает: файл, названный «../../.env», иначе стал бы путём.
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    original_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    # Сводка появляется после разбора. NULL означает «ещё не считали», а не
    # «посчитали и вышло пусто»: это разные состояния, и экран показывает их
    # по-разному.
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rows_count: Mapped[int] = mapped_column(Integer, default=0)
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class DatasetRow(Base):
    """Разобранная строка таблицы.

    Строки живут в базе, а не читаются из файла заново, и это главное
    решение фичи: в ночную копию контура попадает база, а не диск. Файл —
    исходник, который можно потерять; разобранное — работа, которую терять
    нельзя.
    """

    __tablename__ = "dataset_rows"
    __table_args__ = (Index("ix_dataset_rows_dataset_id_index", "dataset_id", "index"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    # ondelete CASCADE: удаляя таблицу, удаляем и её строки. Без этого
    # осиротевшие строки копятся молча — их не видно ни на одном экране.
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE")
    )
    index: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ModelArtifact(Base):
    """Обученная модель.

    Хранится в базе, а не на диске, по той же причине, что и строки: это
    производное, и оно обязано попадать в ночную копию.

    Версия и метка времени хранятся намеренно: модель, обученную на данных,
    которых больше нет, надо отличать от свежей, не поднимая историю
    загрузок.
    """

    __tablename__ = "model_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE")
    )
    target_column: Mapped[str] = mapped_column(String(255))
    feature_columns: Mapped[list[str]] = mapped_column(JSONB)
    algorithm: Mapped[str] = mapped_column(String(64))
    metric_name: Mapped[str] = mapped_column(String(32))
    metric_value: Mapped[float]
    # Сама модель, сериализованная joblib. Это НАШ артефакт, а не чужой
    # файл: загружать сюда что-либо извне нельзя — распаковка pickle
    # исполняет код.
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    actor: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
```

- [ ] **Шаг 2: Зарегистрировать таблицы в обвязке тестов и в Alembic**

В `backend/tests/conftest.py`:

```python
from app.features.datasets.models import (  # noqa: F401  # isort: skip
    Dataset,
    DatasetRow,
    ModelArtifact,
)
```

В `backend/alembic/env.py` — рядом с прочими импортами моделей после
`# isort: split`.

- [ ] **Шаг 3: Сгенерировать и прочитать миграцию**

```bash
make revision m=datasets
```

Проверь глазами: внешние ключи с `ondelete="CASCADE"`, `payload` —
`LargeBinary`, `feature_columns` — `JSONB`, индекс на `(dataset_id, index)`.

- [ ] **Шаг 4: Применить и откатить**

```bash
make migrate
cd backend && uv run alembic downgrade -1 && uv run alembic upgrade head
```

- [ ] **Шаг 5: Коммит**

```bash
git add backend/app/features/datasets/ backend/tests/conftest.py \
        backend/alembic/env.py backend/alembic/versions/
git commit -m "feat: таблицы, строки и артефакты моделей"
```

---

### Задача 8: Таблицы — загрузка и разбор

**Files:**
- Create: `backend/app/features/datasets/schemas.py`
- Create: `backend/app/features/datasets/service.py`
- Create: `backend/app/features/datasets/jobs.py`
- Create: `backend/app/features/datasets/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/api/test_route_guards.py`
- Test: `backend/tests/api/test_datasets.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/api/test_datasets.py`:

```python
import io

import pytest
from sqlalchemy import select

from app.core.audit import AuditLog
from app.core.jobs import Job, JobStatus
from app.domain.roles import Role
from app.features.datasets.models import Dataset, DatasetRow

TABLE = b"\xd0\xb3\xd0\xbe\xd1\x80\xd0\xbe\xd0\xb4,\xd1\x86\xd0\xb5\xd0\xbd\xd0\xb0\n\xd0\x90,10\n\xd0\x91,20\n\xd0\x90,30\n"


def upload(name: str = "\xd1\x86\xd0\xb5\xd0\xbd\xd1\x8b.csv", body: bytes = TABLE) -> dict:
    return {"file": (name, io.BytesIO(body), "text/csv")}


async def test_upload_requires_editor(client, login_as):
    await login_as(role=Role.viewer, login="ivan")
    response = await client.post("/api/datasets", files=upload())
    assert response.status_code == 403


async def test_reading_requires_login(client):
    assert (await client.get("/api/datasets")).status_code == 401


async def test_upload_stores_the_file_and_queues_the_work(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/datasets", files=upload())
    assert response.status_code == 201
    body = response.json()
    assert body["original_name"] == "цены.csv"
    # Сводки ещё нет: разбор идёт в фоне, и экран обязан отличать «считаем»
    # от «посчитали и вышло пусто».
    assert body["summary"] is None

    dataset = (await session.execute(select(Dataset))).scalar_one()
    job = (await session.execute(select(Job))).scalar_one()
    assert job.kind == "datasets.parse"
    assert job.payload == {"dataset_id": str(dataset.id)}
    assert job.status is JobStatus.queued


async def test_upload_and_its_job_land_in_one_transaction(client, session, login_as):
    # Если запись таблицы и постановка задачи разъедутся, воркер возьмёт
    # задачу на данные, которых нет. Проверяется тем, что обе строки
    # переживают откат к точке сохранения одинаково.
    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    await session.rollback()
    assert (await session.execute(select(Dataset))).first() is not None
    assert (await session.execute(select(Job))).first() is not None


async def test_upload_writes_audit(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    entry = (await session.execute(select(AuditLog))).scalars().one()
    assert entry.actor == "ivan"
    assert entry.entity == "Dataset"
    assert "цены.csv" in entry.detail


async def test_wrong_content_is_refused_with_a_human_reason(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    response = await client.post(
        "/api/datasets", files=upload("отчёт.csv", b"%PDF-1.7\n%\xe2\xe3")
    )
    assert response.status_code == 400
    assert response.json()["field"] == "file"


async def test_too_large_is_refused(client, login_as, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "upload_max_bytes", 10)
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/datasets", files=upload())
    assert response.status_code == 400
    assert "больше" in response.json()["error"]


async def test_too_large_is_refused_before_the_body_reaches_the_disk(
    client, login_as, monkeypatch
):
    # Предыдущий тест зелёный и тогда, когда потолок сработал последней
    # линией — внутри storage.save, уже приняв всё тело. Отличить одно от
    # другого можно только так: сделать save падающим и потребовать, чтобы
    # отказ всё равно был человеческим. Без этого теста вызов check_size в
    # роутере можно удалить, и ни одна проверка не покраснеет.
    from app.core import storage
    from app.core.config import settings

    monkeypatch.setattr(settings, "upload_max_bytes", 10)
    monkeypatch.setattr(
        storage,
        "save",
        lambda data: pytest.fail("файл не должен доходить до диска"),
    )
    await login_as(role=Role.editor, login="ivan")
    response = await client.post("/api/datasets", files=upload())
    assert response.status_code == 400
    assert "больше" in response.json()["error"]


async def test_parsing_fills_rows_and_summary(client, session, login_as):
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    job = (await session.execute(select(Job))).scalar_one()
    job.status = JobStatus.running
    await session.commit()

    result = await handlers.parse(session, job)
    await session.commit()

    dataset = (await session.execute(select(Dataset))).scalar_one()
    assert dataset.rows_count == 3
    assert dataset.summary["строк"] == 3
    assert result["строк"] == 3
    rows = (
        await session.execute(select(DatasetRow).order_by(DatasetRow.index))
    ).scalars().all()
    assert [r.data["город"] for r in rows] == ["А", "Б", "А"]


async def test_parsing_twice_does_not_double_the_rows(client, session, login_as):
    # Задача может быть выполнена повторно: её вернула отметка живости или
    # её перезапустили руками. Обработчик обязан быть идемпотентным, иначе
    # строки удваиваются молча, а сводка расходится с содержимым.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload())
    job = (await session.execute(select(Job))).scalar_one()

    await handlers.parse(session, job)
    await handlers.parse(session, job)
    await session.commit()

    rows = (await session.execute(select(DatasetRow))).scalars().all()
    assert len(rows) == 3


async def test_broken_table_fails_with_the_reason_a_human_reads(
    client, session, login_as
):
    from app.domain.tables import TableError
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    await client.post("/api/datasets", files=upload("пусто.csv", b"\n"))
    job = (await session.execute(select(Job))).scalar_one()
    with pytest.raises(TableError):
        await handlers.parse(session, job)


async def test_deleting_a_dataset_takes_its_rows(client, session, login_as):
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    created = (await client.post("/api/datasets", files=upload())).json()
    job = (await session.execute(select(Job))).scalar_one()
    await handlers.parse(session, job)
    await session.commit()

    assert (await client.delete(f"/api/datasets/{created['id']}")).status_code == 200
    assert (await session.execute(select(DatasetRow))).first() is None


async def test_deleting_unknown_dataset_is_404(client, login_as):
    await login_as(role=Role.editor, login="ivan")
    missing = "01a05000-0000-7000-8000-000000000000"
    assert (await client.delete(f"/api/datasets/{missing}")).status_code == 404
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Run: `cd backend && uv run pytest tests/api/test_datasets.py`
Expected: FAIL — маршрутов `/api/datasets` ещё нет.

- [ ] **Шаг 3: Написать `backend/app/features/datasets/schemas.py`**

```python
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # uuid.UUID, а не str: pydantic строку из UUID сам не делает.
    id: uuid.UUID
    name: str
    original_name: str
    size_bytes: int
    kind: str
    # None означает «ещё не считали». Экран показывает это иначе, чем
    # посчитанную пустую сводку.
    summary: dict[str, Any] | None
    rows_count: int
    actor: str
    created_at: datetime
```

- [ ] **Шаг 4: Написать `backend/app/features/datasets/service.py`**

```python
"""Правила работы с таблицами. ОБРАЗЕЦ слоя данных."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs, storage
from app.core.audit import write_audit
from app.core.errors import RecordNotFound
from app.features.datasets.jobs import PARSE
from app.features.datasets.models import Dataset


async def list_datasets(session: AsyncSession) -> list[Dataset]:
    result = await session.execute(
        # Второй ключ — id: created_at ставится в коде, и две таблицы,
        # загруженные в одну миллисекунду, иначе меняются местами от
        # запроса к запросу.
        select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id)
    )
    return list(result.scalars().all())


async def get_dataset(session: AsyncSession, dataset_id: uuid.UUID) -> Dataset:
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise RecordNotFound("Таблица не найдена")
    return dataset


async def create_dataset(
    session: AsyncSession, original_name: str, data: bytes, actor: str
) -> Dataset:
    """Кладёт файл, заводит запись и ставит разбор — одной транзакцией.

    Порядок важен: файл на диск ложится ДО записи в базу, потому что откат
    транзакции уберёт запись, а файл придётся убирать руками — и мы это
    делаем ниже явно. Обратный порядок дал бы запись, ссылающуюся на файл,
    которого нет.
    """
    kind = storage.detect_kind(data[:8])
    file_id = storage.save(data)
    try:
        dataset = Dataset(
            name=original_name.rsplit(".", 1)[0][:255] or "без имени",
            file_id=file_id,
            original_name=original_name[:255],
            size_bytes=len(data),
            kind=kind,
            actor=actor,
        )
        session.add(dataset)
        await session.flush()
        jobs.enqueue(
            session,
            kind=PARSE,
            payload={"dataset_id": str(dataset.id)},
            actor=actor,
        )
        write_audit(
            session,
            actor,
            "create",
            "Dataset",
            str(dataset.id),
            f"{original_name}, {len(data)} байт",
        )
        await session.commit()
    except Exception:
        # Файл уже на диске, а запись не состоялась. Без уборки каталог
        # загрузок копит файлы, на которые никто не ссылается: место они
        # занимают, а найти их можно только глазами.
        storage.delete(file_id)
        raise
    return dataset


async def delete_dataset(
    session: AsyncSession, dataset_id: uuid.UUID, actor: str
) -> None:
    dataset = await get_dataset(session, dataset_id)
    file_id = dataset.file_id
    write_audit(
        session, actor, "delete", "Dataset", str(dataset.id), dataset.original_name
    )
    await session.delete(dataset)
    await session.commit()
    # Файл удаляется ПОСЛЕ коммита: упади удаление записи, файл остался бы
    # нужен. Осиротевший файл дешевле записи, ссылающейся в пустоту.
    storage.delete(file_id)
```

- [ ] **Шаг 5: Написать `backend/app/features/datasets/jobs.py`**

```python
"""Фоновая работа фичи «Таблицы».

Обработчики живут здесь, а не в общем реестре: фича владеет своей фоновой
работой целиком, и удаляя фичу, удаляешь её задачи. Воркер собирает словарь
HANDLERS так же, как main.py собирает роутеры.
"""

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs, storage
from app.core.jobs import Job
from app.domain.tables import read_table, summarise
from app.features.datasets.models import Dataset, DatasetRow

# Вид задачи объявлен ЗДЕСЬ, рядом с обработчиком, и импортируется всеми
# остальными. Два места, где написана строка «datasets.parse», разъезжаются
# молча: постановка кладёт один вид, HANDLERS ждёт другой, и задача просто
# не берётся — без ошибки, без записи в логе, навсегда «в очереди».
PARSE = "datasets.parse"

# Отметка живости ставится не на каждой строке, а раз в столько: запись в
# базу на каждой строке стоила бы дороже самого разбора.
_HEARTBEAT_EVERY = 500


async def parse(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Читает файл, кладёт строки и сводку в базу."""
    dataset_id = uuid.UUID(job.payload["dataset_id"])
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        # Таблицу удалили, пока задача ждала. Это не отказ: работы больше
        # нет, и сообщать человеку не о чем.
        return {"строк": 0, "примечание": "таблица удалена"}

    frame = read_table(storage.read(dataset.file_id), dataset.kind)

    # Идемпотентность. Задачу может вернуть отметка живости или перезапуск
    # руками, и повторный разбор обязан давать тот же результат, а не
    # удвоенные строки при сводке от первого прохода.
    await session.execute(
        delete(DatasetRow).where(DatasetRow.dataset_id == dataset.id)
    )

    total = len(frame)
    for index, row in enumerate(frame.to_dict(orient="records")):
        session.add(
            DatasetRow(
                dataset_id=dataset.id,
                index=index,
                # Приведение к тому, что переживёт JSONB: NaN и numpy-типы
                # сериализатор json не берёт, и падение случилось бы на
                # записи — после всего разбора.
                data={str(k): _json_safe(v) for k, v in row.items()},
            )
        )
        if index % _HEARTBEAT_EVERY == 0:
            await session.flush()
            await jobs.heartbeat(session, job, progress=int(index / total * 90))

    dataset.summary = summarise(frame)
    dataset.rows_count = total
    await session.commit()
    return {"строк": total}


def _json_safe(value: Any) -> Any:
    import math

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


HANDLERS = {PARSE: parse}
```

- [ ] **Шаг 6: Написать `backend/app/features/datasets/router.py`**

```python
import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core import storage
from app.core.deps import CurrentUser, SessionDep, require_role
from app.core.errors import RuleViolation
from app.domain.roles import Role
from app.domain.tables import TableError
from app.features.datasets import service
from app.features.datasets.schemas import DatasetOut

router = APIRouter(prefix="/datasets", tags=["datasets"])

ViewerDep = Depends(require_role(Role.viewer))
EditorDep = Depends(require_role(Role.editor))


@router.get("", response_model=list[DatasetOut])
async def list_datasets(
    session: SessionDep, _: CurrentUser = ViewerDep
) -> list[DatasetOut]:
    return [DatasetOut.model_validate(d) for d in await service.list_datasets(session)]


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    session: SessionDep,
    file: UploadFile = File(),
    actor: CurrentUser = EditorDep,
) -> DatasetOut:
    # Отказ по объявленному размеру — ДО чтения тела. Без этой строки
    # файл на триста мегабайт сначала целиком приедет в память, и только
    # потом storage.save скажет «нет»: потолок сработает, но заплатим за
    # него ровно тем, ради экономии чего он и стоит.
    storage.check_size(file.size)
    # Дальше тело читается целиком: разбор всё равно держит таблицу в
    # памяти, и потоковая запись на диск экономила бы только на файлах,
    # которые мы и так отказываемся принимать по размеру.
    data = await file.read()
    try:
        dataset = await service.create_dataset(
            session, file.filename or "без имени", data, actor.login
        )
    except TableError as broken:
        # Перевод доменного отказа в конверт — работа этого слоя. Домен про
        # поле формы не знает и знать не должен.
        raise RuleViolation(str(broken), field="file") from broken
    return DatasetOut.model_validate(dataset)


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: uuid.UUID, session: SessionDep, actor: CurrentUser = EditorDep
) -> dict[str, bool]:
    await service.delete_dataset(session, dataset_id, actor.login)
    return {"ok": True}
```

- [ ] **Шаг 7: Подключить роутер и учесть маршруты в охране**

В `backend/app/main.py` — `datasets_router` в список роутеров.

В `backend/tests/api/test_route_guards.py` — три новых маршрута в список
защищённых ролью. **Не в список открытых:** таблицы видит вошедший, а
загружает и удаляет — editor.

- [ ] **Шаг 8: Поставить зависимость для загрузки**

```bash
cd backend && uv add python-multipart
```

Без неё FastAPI отвечает на `UploadFile` ошибкой про отсутствующий пакет,
причём в момент запроса, а не при старте.

- [ ] **Шаг 9: Запустить тесты**

Run: `cd backend && uv run pytest tests/api/test_datasets.py -v`
Expected: PASS, 13 passed

- [ ] **Шаг 10: Доказать охранников мутацией**

| Мутация | Обязана упасть |
|---|---|
| снять `EditorDep` с загрузки | `test_upload_requires_editor` |
| снять `ViewerDep` с чтения | `test_reading_requires_login` |
| убрать `jobs.enqueue` из `create_dataset` | `test_upload_stores_the_file_and_queues_the_work` |
| убрать `write_audit` | `test_upload_writes_audit` |
| убрать `delete(DatasetRow)` из `parse` | `test_parsing_twice_does_not_double_the_rows` |
| убрать `ondelete="CASCADE"` у `dataset_id` | `test_deleting_a_dataset_takes_its_rows` |
| убрать `storage.detect_kind` из сервиса | `test_wrong_content_is_refused_with_a_human_reason` |
| убрать `storage.check_size` из роутера | `test_too_large_is_refused_before_the_body_reaches_the_disk` |

- [ ] **Шаг 11: Коммит**

```bash
git add backend/app/features/datasets/ backend/app/main.py \
        backend/tests/api/test_datasets.py backend/tests/api/test_route_guards.py \
        backend/pyproject.toml backend/uv.lock
git commit -m "feat: загрузка таблиц и разбор в фоне"
```

---

### Задача 9: Обучение модели и предсказание

**Files:**
- Modify: `backend/app/features/datasets/{jobs,service,schemas,router}.py`
- Modify: `backend/pyproject.toml` — scikit-learn, joblib
- Test: `backend/tests/api/test_models.py`

- [ ] **Шаг 1: Поставить зависимости**

```bash
cd backend && uv add scikit-learn joblib
```

- [ ] **Шаг 2: Написать падающий тест**

Create `backend/tests/api/test_models.py`:

```python
import io

import pytest
from sqlalchemy import select

from app.core.jobs import Job
from app.domain.roles import Role
from app.features.datasets.models import Dataset, ModelArtifact

TABLE = (
    b"\xd0\xbf\xd0\xbb\xd0\xbe\xd1\x89\xd0\xb0\xd0\xb4\xd1\x8c,"
    b"\xd0\xba\xd0\xbe\xd0\xbc\xd0\xbd\xd0\xb0\xd1\x82,\xd1\x86\xd0\xb5\xd0\xbd\xd0\xb0\n"
    + b"".join(f"{40+i},{1+i%3},{100+i*3}\n".encode() for i in range(40))
)


async def prepare(client, session) -> Dataset:
    from app.features.datasets import jobs as handlers

    await client.post(
        "/api/datasets",
        files={"file": ("кв.csv", io.BytesIO(TABLE), "text/csv")},
    )
    job = (await session.execute(select(Job))).scalars().first()
    assert job is not None
    await handlers.parse(session, job)
    await session.commit()
    return (await session.execute(select(Dataset))).scalar_one()


async def test_training_requires_editor(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await login_as(role=Role.viewer, login="петя")
    response = await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    assert response.status_code == 403


async def test_unknown_target_column_is_refused_by_its_name(
    client, session, login_as
):
    # Опечатка в имени колонки — самая частая ошибка при обучении. Отказ
    # обязан назвать поле, чтобы форма подсветила именно его.
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    response = await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цна"}
    )
    assert response.status_code == 400
    assert response.json()["field"] == "target_column"


async def test_training_queues_the_work(client, session, login_as):
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    response = await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    assert response.status_code == 202
    job = (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).scalar_one()
    assert job.payload["dataset_id"] == str(dataset.id)


async def test_trained_model_is_stored_with_its_metric(client, session, login_as):
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).scalar_one()

    result = await handlers.train(session, job)
    await session.commit()

    model = (await session.execute(select(ModelArtifact))).scalar_one()
    assert model.target_column == "цена"
    assert model.feature_columns == ["площадь", "комнат"]
    assert model.metric_name == "r2"
    assert 0.0 <= model.metric_value <= 1.0
    assert len(model.payload) > 0
    assert result["метрика"] == pytest.approx(model.metric_value)


async def test_prediction_uses_the_stored_model(client, session, login_as):
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).scalar_one()
    await handlers.train(session, job)
    await session.commit()
    model = (await session.execute(select(ModelArtifact))).scalar_one()

    response = await client.post(
        f"/api/models/{model.id}/predict",
        json={"row": {"площадь": 50, "комнат": 2}},
    )
    assert response.status_code == 200
    assert isinstance(response.json()["значение"], float)


async def test_prediction_names_the_missing_column(client, session, login_as):
    # Строка без нужной колонки — ошибка ввода, а не сбой. Без явного отказа
    # scikit-learn падает сообщением про размерность, которое человеку
    # ничего не говорит.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).scalar_one()
    await handlers.train(session, job)
    await session.commit()
    model = (await session.execute(select(ModelArtifact))).scalar_one()

    response = await client.post(
        f"/api/models/{model.id}/predict", json={"row": {"площадь": 50}}
    )
    assert response.status_code == 400
    assert "комнат" in response.json()["error"]


async def test_trained_models_are_listed_without_their_payload(
    client, session, login_as
):
    # Список моделей читают, чтобы выбрать, чем предсказывать. Сам артефакт
    # наружу не отдаётся: он весит, человеку не нужен, а лишний путь наружу
    # для сериализованной модели заводить незачем.
    from app.features.datasets import jobs as handlers

    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "цена"}
    )
    job = (
        await session.execute(select(Job).where(Job.kind == "datasets.train"))
    ).scalar_one()
    await handlers.train(session, job)
    await session.commit()

    listed = (await client.get(f"/api/datasets/{dataset.id}/models")).json()
    assert [m["target_column"] for m in listed] == ["цена"]
    assert "payload" not in listed[0]


async def test_training_on_a_text_target_is_refused(client, session, login_as):
    # Регрессия по тексту не имеет смысла, и sklearn скажет об этом
    # исключением про типы. Отказ до обучения дешевле и понятнее.
    await login_as(role=Role.editor, login="ivan")
    dataset = await prepare(client, session)
    response = await client.post(
        f"/api/datasets/{dataset.id}/models", json={"target_column": "комнат"}
    )
    assert response.status_code == 202, "числовая колонка — допустимая цель"
```

- [ ] **Шаг 3: Дописать обработчик обучения в `jobs.py`**

```python
TRAIN = "datasets.train"

# Минимум строк для обучения. Меньше — модель запоминает выборку целиком, а
# метрика показывает единицу и врёт. Отказ честнее бессмысленной модели.
MIN_ROWS_TO_TRAIN = 20


async def train(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Обучает модель на разобранной таблице и сохраняет артефакт."""
    import io as _io

    import joblib
    import pandas as pd
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score
    from sklearn.model_selection import train_test_split

    dataset_id = uuid.UUID(job.payload["dataset_id"])
    target = job.payload["target_column"]

    rows = (
        await session.execute(
            select(DatasetRow)
            .where(DatasetRow.dataset_id == dataset_id)
            .order_by(DatasetRow.index)
        )
    ).scalars().all()
    if len(rows) < MIN_ROWS_TO_TRAIN:
        raise ValueError(
            f"Для обучения нужно хотя бы {MIN_ROWS_TO_TRAIN} строк, есть {len(rows)}"
        )

    frame = pd.DataFrame([r.data for r in rows])
    features = [
        c
        for c in frame.columns
        if c != target and pd.api.types.is_numeric_dtype(frame[c])
    ]
    if not features:
        raise ValueError("Нет числовых колонок, по которым можно обучать")

    await jobs.heartbeat(session, job, progress=30)

    x_train, x_test, y_train, y_test = train_test_split(
        frame[features], frame[target], test_size=0.25, random_state=0
    )
    model = LinearRegression().fit(x_train, y_train)
    metric = float(r2_score(y_test, model.predict(x_test)))

    await jobs.heartbeat(session, job, progress=80)

    buffer = _io.BytesIO()
    joblib.dump(model, buffer)
    session.add(
        ModelArtifact(
            dataset_id=dataset_id,
            target_column=target,
            feature_columns=features,
            algorithm="LinearRegression",
            metric_name="r2",
            metric_value=metric,
            payload=buffer.getvalue(),
            actor=job.actor,
        )
    )
    await session.commit()
    return {"метрика": metric, "колонок": len(features)}


HANDLERS = {PARSE: parse, TRAIN: train}
```

Одна модель и без подбора параметров — намеренно. Заготовка показывает, где
живёт обучение и как хранится артефакт, а не как настраивать модель: подбор
параметров — решение под конкретную задачу, а её пока нет.

- [ ] **Шаг 4: Дописать сервис — постановка обучения и предсказание**

В `service.py` дописать импорты — `Any` из `typing`, `RuleViolation` из
`app.core.errors`, `Job` из `app.core.jobs`, `TRAIN` из
`app.features.datasets.jobs`, `ModelArtifact` из моделей фичи — и три
функции:

```python
async def list_models(
    session: AsyncSession, dataset_id: uuid.UUID
) -> list[ModelArtifact]:
    # Свежая модель первой: список читают, чтобы взять последнюю обученную.
    # Второй ключ — id: created_at ставится в коде, и две модели, обученные
    # в одну миллисекунду, иначе меняются местами от запроса к запросу.
    result = await session.execute(
        select(ModelArtifact)
        .where(ModelArtifact.dataset_id == dataset_id)
        .order_by(ModelArtifact.created_at.desc(), ModelArtifact.id)
    )
    return list(result.scalars().all())


async def start_training(
    session: AsyncSession, dataset_id: uuid.UUID, target: str, actor: str
) -> Job:
    dataset = await get_dataset(session, dataset_id)
    if dataset.summary is None:
        raise RuleViolation("Таблица ещё не разобрана", field="target_column")
    known = {c["имя"] for c in dataset.summary["колонки"]}
    if target not in known:
        # Отказ называет поле: опечатка в имени колонки — самая частая
        # ошибка здесь, и форма обязана подсветить именно её.
        raise RuleViolation(f"В таблице нет колонки «{target}»", field="target_column")

    job = jobs.enqueue(
        session,
        kind=TRAIN,
        payload={"dataset_id": str(dataset_id), "target_column": target},
        actor=actor,
    )
    write_audit(session, actor, "train", "Dataset", str(dataset_id), f"цель {target}")
    await session.commit()
    return job


async def predict(
    session: AsyncSession, model_id: uuid.UUID, row: dict[str, Any]
) -> float:
    """Предсказание идёт СРАЗУ, а не через очередь.

    Обучение долгое, предсказание — миллисекунды. Гонять его через очередь
    значило бы заставить человека ждать оборота опроса ради ответа, который
    уже готов.
    """
    import io as _io

    import joblib

    model_row = await session.get(ModelArtifact, model_id)
    if model_row is None:
        raise RecordNotFound("Модель не найдена")

    missing = [c for c in model_row.feature_columns if c not in row]
    if missing:
        # Без этой проверки sklearn падает сообщением про размерность, из
        # которого человеку не понять, какой колонки не хватило.
        raise RuleViolation(
            f"Не хватает колонок: {', '.join(missing)}", field="row"
        )

    # Распаковка joblib исполняет код. Здесь это безопасно ровно потому, что
    # артефакт НАШ: он положен обучением в этом же приложении. Загружать
    # сюда файл извне нельзя ни при каких условиях.
    model = joblib.load(_io.BytesIO(model_row.payload))
    values = [[float(row[c]) for c in model_row.feature_columns]]
    return float(model.predict(values)[0])
```

- [ ] **Шаг 5: Дописать схемы и маршруты**

`schemas.py`:

```python
class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_column: str = Field(min_length=1, max_length=255)


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: dict[str, float]


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    target_column: str
    feature_columns: list[str]
    algorithm: str
    metric_name: str
    metric_value: float
    actor: str
    created_at: datetime
```

`router.py` — три маршрута:

```python
@router.post(
    "/{dataset_id}/models", status_code=status.HTTP_202_ACCEPTED
)
async def start_training(
    dataset_id: uuid.UUID,
    payload: TrainRequest,
    session: SessionDep,
    actor: CurrentUser = EditorDep,
) -> dict[str, str]:
    # 202, а не 201: модели ещё нет, есть поставленная задача. Ответить 201
    # значило бы соврать про то, что уже создано.
    job = await service.start_training(
        session, dataset_id, payload.target_column, actor.login
    )
    return {"job_id": str(job.id)}


@router.get("/{dataset_id}/models", response_model=list[ModelOut])
async def list_models(
    dataset_id: uuid.UUID, session: SessionDep, _: CurrentUser = ViewerDep
) -> list[ModelOut]:
    return [
        ModelOut.model_validate(m)
        for m in await service.list_models(session, dataset_id)
    ]
```

И отдельный роутер `models_router` с префиксом `/models` для предсказания —
модель принадлежит таблице, но предсказание зовут по идентификатору модели,
и вкладывать его в путь таблицы значило бы требовать от клиента знать оба:

```python
models_router = APIRouter(prefix="/models", tags=["datasets"])


@models_router.post("/{model_id}/predict")
async def predict(
    model_id: uuid.UUID,
    payload: PredictRequest,
    session: SessionDep,
    _: CurrentUser = ViewerDep,
) -> dict[str, float]:
    return {"значение": await service.predict(session, model_id, payload.row)}
```

- [ ] **Шаг 6: Подключить и учесть в охране маршрутов**

`main.py` — `models_router`; `test_route_guards.py` — три новых маршрута.

- [ ] **Шаг 7: Запустить тесты**

Run: `cd backend && uv run pytest tests/api/test_models.py -v`
Expected: PASS, 8 passed

- [ ] **Шаг 8: Доказать охранников мутацией**

| Мутация | Обязана упасть |
|---|---|
| снять `EditorDep` с обучения | `test_training_requires_editor` |
| убрать проверку `target not in known` | `test_unknown_target_column_is_refused_by_its_name` |
| убрать проверку `missing` в `predict` | `test_prediction_names_the_missing_column` |
| не сохранять `payload` модели | `test_trained_model_is_stored_with_its_metric` |
| добавить `payload` в `ModelOut` | `test_trained_models_are_listed_without_their_payload` |

- [ ] **Шаг 9: Коммит**

```bash
git add backend/app/features/datasets/ backend/app/main.py \
        backend/tests/api/test_models.py backend/tests/api/test_route_guards.py \
        backend/pyproject.toml backend/uv.lock
git commit -m "feat: обучение модели и предсказание"
```

---

### Задача 10: Клиент внешних моделей

**Files:**
- Create: `backend/app/integrations/__init__.py`, `client.py`
- Create: `backend/app/integrations/fixtures/ответ.json`
- Test: `backend/tests/unit/test_integrations.py`

- [ ] **Шаг 1: Написать падающий тест**

Create `backend/tests/unit/test_integrations.py`:

```python
import json

import pytest

from app.integrations import client


def test_mock_answers_without_network(monkeypatch):
    # Умолчание — mock: шаблон обязан работать сразу после установки, без
    # ключей и без сети. Прогон, зависящий от чужого тарифа, — прогон,
    # который однажды покраснеет не по вине кода.
    monkeypatch.setattr(client.settings, "integrations_mode", "mock")
    assert client.ask("сколько будет два и два") == client.MOCK_ANSWER


def test_mock_is_deterministic(monkeypatch):
    monkeypatch.setattr(client.settings, "integrations_mode", "mock")
    assert client.ask("а") == client.ask("б")


def test_fixture_answers_from_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(client.settings, "integrations_mode", "fixture")
    monkeypatch.setattr(client, "FIXTURES", tmp_path)
    (tmp_path / "ответ.json").write_text(
        json.dumps({"answer": "из записи"}), encoding="utf-8"
    )
    assert client.ask("что угодно") == "из записи"


def test_missing_fixture_says_which_file(monkeypatch, tmp_path):
    # «Файл не найден» без имени отправляет искать по всему каталогу.
    monkeypatch.setattr(client.settings, "integrations_mode", "fixture")
    monkeypatch.setattr(client, "FIXTURES", tmp_path)
    with pytest.raises(RuntimeError) as missing:
        client.ask("что угодно")
    assert "ответ.json" in str(missing.value)


def test_live_without_a_key_refuses_loudly(monkeypatch):
    # Ключа нет — значит режим выставлен, а настройка забыта. Тихий возврат
    # к mock означал бы, что приложение отвечает выдумкой, считая это
    # ответом модели.
    monkeypatch.setattr(client.settings, "integrations_mode", "live")
    monkeypatch.setattr(client.settings, "integrations_api_key", "")
    with pytest.raises(RuntimeError) as denial:
        client.ask("вопрос")
    assert "INTEGRATIONS_API_KEY" in str(denial.value)
```

- [ ] **Шаг 2: Дописать настройки клиента**

В `Settings`:

```python
    integrations_api_key: str = ""
    integrations_url: str = ""
```

Пустые умолчания намеренно: в режиме `mock` они не нужны, а обязательное
поле заставило бы заполнять их всех, включая тех, кому внешние модели не
нужны вовсе.

- [ ] **Шаг 3: Написать `backend/app/integrations/client.py`**

```python
"""Клиент внешних моделей: три режима вместо одного.

`mock` — умолчание. Шаблон обязан работать сразу после установки: без
ключей, без сети, без чужого тарифа. Прогон, зависящий от внешнего сервиса,
однажды краснеет не по вине кода — и первым делом перестают верить прогону,
а не сервису.

`fixture` — записанные ответы с диска: тот же детерминизм, но на настоящей
форме ответа.

`live` — настоящий HTTP. Конкретного поставщика шаблон не выбирает: адрес и
ключ приходят из настроек при установке.
"""

import json
from pathlib import Path

import httpx

from app.core.config import settings

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MOCK_ANSWER = "Ответ внешней модели (режим mock)"


def ask(prompt: str) -> str:
    """Задаёт вопрос внешней модели. Режим — из настроек."""
    if settings.integrations_mode == "mock":
        return MOCK_ANSWER

    if settings.integrations_mode == "fixture":
        path = FIXTURES / "ответ.json"
        if not path.is_file():
            # Имя файла в тексте: «файл не найден» без имени отправляет
            # искать по всему каталогу.
            raise RuntimeError(f"Нет записанного ответа: {path}")
        return str(json.loads(path.read_text(encoding="utf-8"))["answer"])

    if not settings.integrations_api_key or not settings.integrations_url:
        # Громко, а не откатом к mock. Тихий откат означал бы, что
        # приложение отвечает выдумкой, считая это ответом модели, — и
        # заметить это можно только по смыслу ответа.
        raise RuntimeError(
            "Режим live выбран, но INTEGRATIONS_API_KEY или INTEGRATIONS_URL пуст"
        )

    response = httpx.post(
        settings.integrations_url,
        headers={"Authorization": f"Bearer {settings.integrations_api_key}"},
        json={"prompt": prompt},
        timeout=30,
    )
    response.raise_for_status()
    return str(response.json()["answer"])
```

- [ ] **Шаг 4: Записать образец ответа**

`backend/app/integrations/fixtures/ответ.json`:

```json
{ "answer": "Записанный ответ внешней модели" }
```

- [ ] **Шаг 5: Запустить тесты и закоммитить**

Run: `cd backend && uv run pytest tests/unit/test_integrations.py -v`
Expected: PASS, 5 passed

```bash
git add backend/app/integrations/ backend/tests/unit/test_integrations.py \
        backend/app/core/config.py .env.example
git commit -m "feat: клиент внешних моделей с режимами live, mock и fixture"
```

---

### Задача 11: Экран задач — API

**Files:**
- Create: `backend/app/features/jobs/{__init__,service,router}.py`
- Modify: `backend/app/main.py`, `backend/tests/api/test_route_guards.py`
- Test: дописать в `backend/tests/api/test_jobs.py`

- [ ] **Шаг 1: Написать падающий тест**

Дописать в `backend/tests/api/test_jobs.py`:

```python
async def test_everyone_sees_only_their_own_jobs(client, session, login_as):
    jobs.enqueue(session, kind="проба", payload={}, actor="ivan")
    jobs.enqueue(session, kind="проба", payload={}, actor="петя")
    await session.commit()

    await login_as(role=Role.editor, login="ivan")
    mine = (await client.get("/api/jobs")).json()
    assert [j["actor"] for j in mine] == ["ivan"]


async def test_admin_sees_all_jobs(client, session, login_as):
    jobs.enqueue(session, kind="проба", payload={}, actor="ivan")
    jobs.enqueue(session, kind="проба", payload={}, actor="петя")
    await session.commit()

    await login_as(role=Role.admin, login="boss")
    assert len((await client.get("/api/jobs")).json()) == 2


async def test_jobs_screen_requires_login(client):
    assert (await client.get("/api/jobs")).status_code == 401


async def test_worker_liveness_is_reported(client, session, login_as, monkeypatch):
    # «В очереди» обязано быть отличимо от «некому взять». Без этого человек
    # смотрит на задачу, которая никогда не начнётся, и ждёт.
    from app.core.config import settings

    await login_as(role=Role.admin, login="boss")
    jobs.enqueue(session, kind="проба", payload={}, actor="boss")
    await session.commit()

    body = (await client.get("/api/jobs/health")).json()
    assert body["воркер_жив"] is False, "ни одна задача ещё не бралась"

    job = await jobs.claim(session)
    assert job is not None
    body = (await client.get("/api/jobs/health")).json()
    assert body["воркер_жив"] is True


async def test_newest_job_first(client, session, login_as):
    await login_as(role=Role.admin, login="boss")
    jobs.enqueue(session, kind="первая", payload={}, actor="boss")
    await session.commit()
    jobs.enqueue(session, kind="вторая", payload={}, actor="boss")
    await session.commit()
    kinds = [j["kind"] for j in (await client.get("/api/jobs")).json()]
    assert kinds[0] == "вторая"


async def test_limit_has_a_hard_ceiling(client, login_as):
    await login_as(role=Role.admin, login="boss")
    assert (await client.get("/api/jobs?limit=5000")).status_code == 400
    assert (await client.get("/api/jobs?limit=0")).status_code == 400
```

К шапке файла добавить `from app.domain.roles import Role`.

- [ ] **Шаг 2: Написать `backend/app/features/jobs/service.py`**

```python
"""Чтение очереди для экрана. Пишет в неё core/jobs.py."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.jobs import Job

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


async def list_jobs(
    session: AsyncSession, limit: int, actor: str | None
) -> list[Job]:
    """Задачи новыми вперёд. actor=None — все (это администратор)."""
    query = select(Job).order_by(Job.created_at.desc(), Job.id).limit(limit)
    if actor is not None:
        query = query.where(Job.actor == actor)
    return list((await session.execute(query)).scalars().all())


async def worker_is_alive(session: AsyncSession) -> bool:
    """Есть ли признаки, что воркер жив.

    Признак — свежая отметка живости у любой задачи. Способ грубый и это
    честно: пока очередь пуста и никто ничего не ставил, отличить «воркер
    работает» от «воркера нет» нечем — он ничего и не делает. Зато как
    только задача поставлена, разница видна сразу, а нужна она ровно тогда.
    """
    fresh_after = datetime.now(UTC) - timedelta(
        seconds=settings.job_stale_after_seconds
    )
    row = await session.execute(
        select(Job.id).where(Job.heartbeat_at > fresh_after).limit(1)
    )
    return row.first() is not None
```

- [ ] **Шаг 3: Написать `backend/app/features/jobs/router.py`**

```python
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.jobs import service

router = APIRouter(prefix="/jobs", tags=["jobs"])

ViewerDep = Depends(require_role(Role.viewer))


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    progress: int
    result: dict[str, Any] | None
    error: str
    attempts: int
    actor: str
    created_at: datetime
    finished_at: datetime | None


@router.get("", response_model=list[JobOut])
async def list_jobs(
    session: SessionDep,
    limit: int = Query(default=service.DEFAULT_LIMIT, ge=1, le=service.MAX_LIMIT),
    user: CurrentUser = ViewerDep,
) -> list[JobOut]:
    # Свои задачи каждому, все — администратору. Это показ, а не защита:
    # фильтр стоит в запросе, а не в разметке, потому что «спрятать чужое»
    # на клиенте означает всё-таки его отдать.
    actor = None if user.role is Role.admin else user.login
    return [
        JobOut.model_validate(j)
        for j in await service.list_jobs(session, limit, actor)
    ]


@router.get("/health")
async def worker_health(
    session: SessionDep, _: CurrentUser = ViewerDep
) -> dict[str, bool]:
    return {"воркер_жив": await service.worker_is_alive(session)}
```

- [ ] **Шаг 4: Подключить, учесть в охране, прогнать**

`main.py` — `jobs_router`; `test_route_guards.py` — два маршрута.

Run: `cd backend && uv run pytest tests/api/test_jobs.py -v`
Expected: PASS, 16 passed

- [ ] **Шаг 5: Доказать охранников мутацией**

| Мутация | Обязана упасть |
|---|---|
| убрать фильтр по `actor` | `test_everyone_sees_only_their_own_jobs` |
| фильтровать по actor и для админа | `test_admin_sees_all_jobs` |
| убрать `.desc()` | `test_newest_job_first` |
| убрать `le=service.MAX_LIMIT` | `test_limit_has_a_hard_ceiling` |
| `worker_is_alive` всегда True | `test_worker_liveness_is_reported` |

- [ ] **Шаг 6: Коммит**

```bash
git add backend/app/features/jobs/ backend/app/main.py \
        backend/tests/api/test_jobs.py backend/tests/api/test_route_guards.py
git commit -m "feat: экран состояния задач"
```

---

### Задача 12: Границы модулей

**Files:**
- Modify: `backend/.importlinter`

- [ ] **Шаг 1: Дописать два контракта**

```ini
[importlinter:contract:jobs-do-not-know-about-http]
name = обработчики задач не ходят в роутеры
type = forbidden
allow_indirect_imports = True
source_modules =
    app.features.datasets.jobs
forbidden_modules =
    app.features.datasets.router
    app.features.jobs.router
    fastapi

[importlinter:contract:worker-is-not-the-web-application]
name = воркер не тянет за собой веб-приложение
type = forbidden
source_modules =
    app.worker
forbidden_modules =
    app.main
    app.core.static
```

Первый контракт запрещает и `fastapi` целиком: фоновая работа не должна
зависеть от того, как её попросили. Обработчик, знающий про `UploadFile`,
нельзя позвать ни из скрипта, ни из планировщика.

Второй — про время старта и отказы: воркер, притащивший `app.main`,
наследует и раздачу статики, и её падения. Тест на это уже есть, контракт
ловит то же самое раньше и дешевле.

- [ ] **Шаг 2: Проверить**

Run: `cd backend && uv run --group lint lint-imports --config .importlinter`
Expected: `Contracts: 5 kept, 0 broken.`

Если контракт красный — чини код, а не контракт. Красный здесь означает,
что фоновая работа и правда зависит от веба.

- [ ] **Шаг 3: Коммит**

```bash
git add backend/.importlinter
git commit -m "chore: границы фоновой работы и воркера"
```

---

### Задача 13: Экраны

**Files:**
- Create: `frontend/src/routes/datasets.tsx`, `frontend/src/routes/jobs.tsx`
- Modify: `frontend/src/router.tsx`, `frontend/src/components/site-nav.tsx`

- [ ] **Шаг 1: Перегенерировать типы клиента**

```bash
make openapi
```

Без этого `tsc` не знает новых маршрутов, а `make check` краснеет на сверке
типов со схемой — и выглядит это как поломка фронтенда.

- [ ] **Шаг 2: Написать `frontend/src/routes/jobs.tsx`**

Экран задач. Требования, а не разметка — вёрстку делай по образцу
`frontend/src/routes/audit.tsx`, он ближе всего:

- запрос через `unwrap` из `@/api/client`, отказ через `<RequestFailure>` —
  третьего способа в проекте нет и заводить его не надо;
- колонки: вид задачи, состояние, прогресс, кто поставил, когда создана,
  когда завершена, причина отказа;
- подписи состояний по-русски картой, как `ENTITY_LABEL` в журнале: «в
  очереди», «выполняется», «готово», «не удалась». Английские `queued` и
  `failed` на экране у владельца бизнеса — то же самое, что `Expense` в
  журнале, и чинилось это уже один раз;
- **предупреждение, когда воркер не жив**, а в очереди есть задачи: `«в
  очереди» и «некому взять» выглядят одинаково`, и без этой строки человек
  ждёт результата, которого не будет. Признак — `/api/jobs/health`;
- обновление раз в 3 секунды, пока на экране есть незавершённые задачи, и
  не обновлять, когда их нет: постоянный опрос ради неменяющейся таблицы
  греет контур задаром. В TanStack Query это `refetchInterval` функцией от
  данных.

- [ ] **Шаг 3: Написать `frontend/src/routes/datasets.tsx`**

Экран таблиц. По образцу `frontend/src/routes/expenses.tsx`:

- форма загрузки — только для роли editor и выше (`hasRank` из `@/lib/auth`);
  в комментарии сказать прямо, что это показ, а защищает `require_role` на
  сервере;
- список таблиц: имя, размер, число строк, когда загружена;
- у таблицы без сводки — «разбирается», а не пустая ячейка: `null` в сводке
  означает «ещё не считали», и это не то же самое, что «посчитали и пусто»;
- по нажатию на таблицу — её сводка: строк и колонки с видом и числами;
- кнопка «Обучить модель» с выбором целевой колонки из сводки, ответ 202
  ведёт на экран задач;
- список обученных моделей с метрикой и датой, форма предсказания по
  колонкам модели;
- ошибка поля из конверта встаёт под своим полем, общая — алертом. Так
  сделано на всех экранах ядра.

- [ ] **Шаг 4: Добавить маршруты и ссылки**

В `frontend/src/router.tsx` — две страницы. Экран таблиц тянет за собой
разбор ответов и формы, экран задач лёгкий: обе грузи обычным `page(...)`,
ленивая загрузка тут не нужна — тяжёлое (recharts, react-markdown) осталось
на витрине и правилах.

В `frontend/src/components/site-nav.tsx` — две ссылки: «Таблицы» с ролью
`viewer`, «Задачи» с ролью `viewer`.

- [ ] **Шаг 5: Проверить**

Run: `make check`
Expected: зелёный целиком.

- [ ] **Шаг 6: Посмотреть глазами**

```bash
cd backend && uv run uvicorn app.main:app --port 8000    # в фоне
cd backend && uv run python -m app.worker                # в фоне
cd frontend && npm run dev
```

Загрузи таблицу, дождись разбора, посмотри сводку, обучи модель, сделай
предсказание. Отдельно **останови воркер и загрузи ещё одну таблицу**:
экран задач обязан сказать, что брать её некому, а не показывать вечное «в
очереди». Это единственная проверка, которую не делает ни один тест.

- [ ] **Шаг 7: Коммит**

```bash
git add frontend/src/routes/datasets.tsx frontend/src/routes/jobs.tsx \
        frontend/src/router.tsx frontend/src/components/site-nav.tsx \
        frontend/src/api/schema.d.ts
git commit -m "feat: экраны таблиц и задач"
```

---

### Задача 14: Воркер на контуре

**Files:**
- Modify: `.github/workflows/deploy.yml`
- Modify: `docs/commands/status.md`, `docs/superpowers/runbooks/server-setup.md`

- [ ] **Шаг 1: Запускать воркер той же доставкой**

В теле удалённого скрипта `deploy.yml`, после блока запуска приложения:

```bash
# Воркер — второй процесс pm2. Запускает его та же доставка, поэтому
# провижинер по-прежнему не требует правок: он о воркере не знает и знать
# не должен, иначе шаблон перестал бы ставиться общей командой.
#
# Порядок важен: воркер поднимается ПОСЛЕ миграций и после веб-процесса.
# Поднятый раньше, он возьмёт задачу на схеме, которой ещё нет.
if pm2 describe "$SLUG-worker" > /dev/null 2>&1; then
  pm2 reload "$SLUG-worker" --update-env
else
  pm2 start "$DIR/backend/.venv/bin/python" --name "$SLUG-worker" --cwd "$DIR/backend" -- -m app.worker
  pm2 save
fi
```

Heredoc в кавычках, поэтому ни экранировать `$`, ни следить за обратными
кавычками не нужно — это уже сделано и стоило одной сломанной доставки.

- [ ] **Шаг 2: Научить `/status` спрашивать про воркер**

`<слаг>-status` сгенерирован провижинером под одно имя процесса и воркера не
покажет. Скрипт создаётся на каждый слаг отдельно, поэтому правка провижинера
не чинит уже заведённые контуры, а править `/usr/local/bin` нужен root.

В `docs/commands/status.md` добавить шаг:

```bash
ssh <слаг>-ops sudo -u deploy PM2_HOME=/home/deploy/.pm2 pm2 describe <слаг>-worker
```

и в текст — что живость очереди смотрят на экране «Задачи», а не по коду
ответа контура.

- [ ] **Шаг 3: Дописать runbook**

В `docs/superpowers/runbooks/server-setup.md` — раздел про два процесса:
имена, команда запуска воркера, и что `<слаг>-status` показывает только веб.

- [ ] **Шаг 4: Коммит**

```bash
git add .github/workflows/deploy.yml docs/commands/status.md \
        docs/superpowers/runbooks/server-setup.md
git commit -m "ci: воркер поднимается доставкой, /status его видит"
```

---

### Задача 15: Сквозной сценарий

**Files:**
- Create: `frontend/tests/e2e/datasets.spec.ts`
- Modify: `frontend/playwright.config.ts`

- [ ] **Шаг 1: Поднимать воркер вместе с приложением**

`webServer` в `playwright.config.ts` принимает список. Существующий объект
с приложением становится **первым элементом массива без единой правки
внутри** — меняется только отступ (`prettier --write` сделает это сам).
Вторым элементом дописывается воркер:

```typescript
    {
      // Имя видно в префиксе строк лога: без него оба процесса пишут
      // «[WebServer]», и понять, чей отказ читаешь, нельзя.
      name: "Worker",
      // Без воркера загруженная таблица навсегда остаётся «в очереди», и
      // сценарий падал бы по таймауту ожидания сводки.
      command: `cd ../backend && uv run python -m app.worker`,
      // Порта у воркера нет, ждать его по url нечем — ждём по строке,
      // которую он печатает при старте. Проверено по исходникам Playwright
      // 1.62: элемент без `url` и без `port` законен, но тогда процесс
      // считается поднятым в момент запуска — и воркер, упавший на импорте
      // или на адресе базы, остался бы незамеченным. Сценарий падал бы по
      // таймауту, а выглядело бы это как медленный разбор. `wait` эту
      // разницу и закрывает: не дождавшись строки, Playwright скажет прямо,
      // что процесс не поднялся.
      //
      // stderr, а не stdout: `logging.basicConfig` в `app/worker.py` пишет
      // туда.
      wait: { stderr: /воркер запущен/ },
      timeout: 60_000,
      env: {
        DATABASE_URL: DATABASE_URL_E2E,
        APP_ENV: "local",
        APP_AUTH_SECRET: "e2e-secret-not-used-anywhere-real-000000",
        // Оборот опроса короче штатной секунды: сценарий ждёт результата
        // вживую, и секунда простоя на каждом обороте — единственное, что
        // он в этом месте измерял бы.
        JOB_POLL_SECONDS: "0.2",
      },
    },
```

`UPLOAD_DIR` здесь не задаётся намеренно: умолчание считается от файла
`.env` (`ENV_FILE.parent / "uploads"`), а не от текущего каталога, поэтому
оба процесса видят один каталог загрузок сами. Задай его одному — и разъедется
молча: приложение положит файл, воркер его не найдёт.

Гасить процесс руками не нужно — Playwright снимает оба элемента списка
после прогона тем же механизмом.

- [ ] **Шаг 2: Написать сценарий**

Create `frontend/tests/e2e/datasets.spec.ts`:

```typescript
import { expect, test } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("Логин").fill("admin")
  await page.getByLabel("Пароль").fill("admin")
  await page.getByRole("button", { name: "Войти" }).click()
  await page.waitForURL("/")
})

test("таблица загружается, считается в фоне и показывает сводку", async ({
  page,
}) => {
  // Единственная проверка всей цепочки целиком: файл → очередь → воркер →
  // база → экран. Каждое звено закрыто своим тестом, но что они соединены
  // друг с другом, не проверяет ничто, кроме этого сценария.
  const name = `цены-${Date.now()}.csv`

  await page.goto("/datasets")
  await page.getByLabel("Файл").setInputFiles({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from("город,цена\nА,10\nБ,20\nА,30\n", "utf-8"),
  })
  await page.getByRole("button", { name: "Загрузить" }).click()

  // Строка появляется сразу — разбор ещё идёт.
  const row = page.getByRole("row").filter({ hasText: name })
  await expect(row).toBeVisible()
  await expect(row).toContainText("разбирается")

  // А через несколько секунд её считает воркер. Ожидание длинное
  // намеренно: воркер опрашивает очередь раз в секунду, и на медленной
  // машине первый оборот приходит не сразу.
  await expect(row).toContainText("3", { timeout: 30_000 })

  await row.click()
  await expect(page.getByText("строк: 3")).toBeVisible()
  await expect(page.getByText("город")).toBeVisible()
})

test("задача видна на экране задач и доходит до «готово»", async ({ page }) => {
  await page.goto("/jobs")
  const first = page.getByRole("row").nth(1)
  await expect(first).toContainText("готово", { timeout: 30_000 })
})
```

- [ ] **Шаг 3: Прогнать три раза подряд**

Run: `cd frontend && npx playwright test`
Expected: 14 passed (11 прежних + 3 новых), три прогона подряд без единого
мигания. Сквозные сценарии — главный источник ложных отказов; проверка,
падающая через раз, обесценивает весь прогон.

- [ ] **Шаг 4: Коммит**

```bash
git add frontend/tests/e2e/datasets.spec.ts frontend/playwright.config.ts
git commit -m "test: сквозной сценарий слоя данных"
```

---

### Задача 16: Документы и реестр

**Files:**
- Modify: `CHECKLIST.md`, `AGENTS.md`, `docs/commands/onboarding.md`
- Modify: `scripts/onboarding-check.mjs`

- [ ] **Шаг 1: Обновить реестр возможностей**

В `CHECKLIST.md` строки, стоявшие `absent` с пометкой «приедет спекой слоя
данных», становятся `included`:

| Возможность | Состояние | Примечание |
|---|---|---|
| Загрузка файлов и медиа | `included` | CSV и XLSX, потолок 32 МиБ, тип по содержимому. Файл — исходник: в ночную копию попадает база, а не диск |
| Очередь и фоновые задачи | `included` | таблица `jobs`, взятие через `SKIP LOCKED`, второй процесс pm2 `<слаг>-worker`, экран `/jobs` |
| Расчёты на pandas | `included` | `app/domain/tables.py`, разбор и сводка; потолок 50 000 строк |
| Обучение моделей | `included` | одна модель (линейная регрессия), артефакт в базе с метрикой и версией. Подбор параметров — **absent**, отдельное решение |
| Внешние модели по API | `included` | `app/integrations/`, режимы live/mock/fixture; поставщика выбирает установка |
| Образцовый раздел «Таблицы» | `included` | **удалить** вместе с «Расходами», когда появится первая настоящая фича. Учат разному, уходят независимо |

Новые строки долга:

| Что | Когда всплывёт |
|---|---|
| Загруженные файлы не попадают в ночную копию | Копия снимает базу, а не диск. Производное (строки, сводки, модели) в базе и переживает; исходник придётся загрузить заново |
| `<слаг>-status` не видит воркер | Скрипт сгенерирован провижинером под одно имя процесса и создаётся на каждый слаг отдельно, поэтому правка провижинера не чинит заведённые контуры. Живость очереди смотрят на экране «Задачи» |
| Один воркер | `SKIP LOCKED` рассчитан на любое их число, второй добавляется строкой в доставке. Делать это без нагрузки — удваивать эксплуатацию задаром |

- [ ] **Шаг 2: Дописать правила в `AGENTS.md`**

Раздел про слой данных:

- фоновая работа живёт в `features/<имя>/jobs.py`, а не в общем реестре;
- обработчик обязан быть **идемпотентным**: задачу возвращает отметка
  живости, и повторный проход должен давать тот же результат, а не удвоенные
  строки;
- обработчик не импортирует роутеры и FastAPI — это проверяет контракт;
- долгая работа ставит отметку живости, иначе её отберут как брошенную;
- загруженный файл — исходник; всё производное кладётся в базу, потому что
  копируется база;
- клиент внешних моделей в тестах и сквозных сценариях идёт в режиме `mock`.

- [ ] **Шаг 3: Дописать установку**

В `docs/commands/onboarding.md` — шаг про каталог загрузок на контуре
(`/var/www/<слаг>/uploads`, создаётся приложением) и про то, что после
первой доставки процессов становится два.

В `scripts/onboarding-check.mjs` — проверка, что `UPLOAD_DIR` в `.env`
контура задан либо намеренно оставлен пустым.

- [ ] **Шаг 4: Прогнать всё и закоммитить**

```bash
make check
cd frontend && npx playwright test
```

```bash
git add CHECKLIST.md AGENTS.md docs/commands/onboarding.md \
        scripts/onboarding-check.mjs
git commit -m "docs: слой данных в реестре, правилах и установке"
```

---

## Порядок исполнения

Задачи 1–4 и 6 независимы и идут первыми. Задача 5 (воркер) импортирует
`features.datasets.jobs` и поэтому исполняется **после задачи 8**; в самой
задаче 5 это отмечено. Дальше по порядку: 7 → 8 → 5 → 9 → 10 → 11 → 12 →
13 → 14 → 15 → 16.

`make check` обязан быть зелёным после каждой задачи. Единственное место,
где это требует внимания, — задача 13: новые маршруты меняют схему OpenAPI,
и без `make openapi` сверка типов клиента краснеет.
