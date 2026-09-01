import json
from collections.abc import AsyncIterator
from typing import get_args

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.db import get_session
from app.features.meta import router as meta
from app.main import app


def _logged(caplog):
    """Записи лога от маршрутов meta.

    Именно от них: caplog собирает и чужие — httpx пишет строку на каждый
    запрос, и проверка «ровно одна запись» считала бы её тоже.
    """
    return [record for record in caplog.records if record.name == meta.__name__]


async def test_health_is_open_and_touches_db(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_answers_503_when_database_is_down(client, session, monkeypatch):
    # Ради этой ветки проверка и ходит в базу. Без неё маршрут отвечает 200
    # при недоступной базе, доставка объявляет контур живым, и человек
    # узнаёт правду от первого пользователя.
    #
    # Мутация «убрать session.execute» оставляет тест на счастливый путь
    # зелёным: он подтверждает только то, что процесс жив.
    #
    # Здесь отказ на УЖЕ УСТАНОВЛЕННОМ соединении — форма, которую ловит и
    # узкий except SQLAlchemyError. Настоящий отказ базы выглядит иначе, он
    # проверяется тестом ниже.
    async def broken(*args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", None, Exception("база недоступна"))

    monkeypatch.setattr(session, "execute", broken)
    response = await client.get("/api/health")
    assert response.status_code == 503


async def test_health_answers_503_when_connection_fails(client):
    # Отказ на этапе ПОДКЛЮЧЕНИЯ — то, как база падает в жизни: СУБД не
    # запущена, хост недоступен, базу удалили, роли нет. До SQLAlchemy такой
    # сбой не доходит: замерено — здесь прилетает голый
    # ConnectionRefusedError (OSError), а не SQLAlchemyError, и с узкой
    # ловлей маршрут отвечал 500 с трейсбеком в лог на каждый опрос — то
    # есть ветка 503 срабатывала ровно в том случае, который встречается
    # реже всего.
    #
    # Порт 1 закрыт всегда, поэтому подключение падает сразу и тест не ждёт
    # таймаута.
    dead = create_async_engine("postgresql+asyncpg://nobody@127.0.0.1:1/nothing")

    async def _override() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(bind=dead) as db:
            yield db

    # Фикстура client чистит dependency_overrides на выходе.
    app.dependency_overrides[get_session] = _override
    try:
        response = await client.get("/api/health")
    finally:
        await dead.dispose()
    assert response.status_code == 503


def test_repo_root_points_at_the_repository():
    # Счёт уровней вручную ломается молча: при переезде файла на уровень
    # глубже все документы начинают отвечать «не найден», а искать причину
    # будут в списке разрешённых имён. Счёт теперь один — в config.py, — и
    # эта проверка сторожит именно его.
    assert (meta.REPO_ROOT / "backend" / "pyproject.toml").exists()


async def test_build_info_requires_login(client):
    # Спецификация: /api/health — единственный маршрут без авторизации.
    # Анонимный build-info отдавал точный задеплоенный коммит; потребителей
    # у маршрута нет ни одного, так что закрыть его ничего не стоит.
    response = await client.get("/api/meta/build-info")
    assert response.status_code == 401


async def test_build_info_reads_the_marker_file(
    client, login_as, monkeypatch, tmp_path
):
    # Единственная ветка, работающая на контуре. Локально build-info.json
    # нет, и без подстановки файла тест всегда шёл веткой «файла нет»:
    # мутация «заменить всё тело обработчика на BuildInfo(commit="dev",
    # built_at="")» оставляла прогон зелёным целиком.
    marker = tmp_path / "build-info.json"
    marker.write_text(
        json.dumps({"commit": "abc1234", "built_at": "2026-09-01T10:00:00Z"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(meta, "BUILD_INFO_FILE", marker)
    await login_as()
    response = await client.get("/api/meta/build-info")
    assert response.status_code == 200
    assert response.json() == {"commit": "abc1234", "built_at": "2026-09-01T10:00:00Z"}


async def test_build_info_without_marker_says_dev(
    client, login_as, monkeypatch, tmp_path
):
    monkeypatch.setattr(meta, "BUILD_INFO_FILE", tmp_path / "нет-такого.json")
    await login_as()
    response = await client.get("/api/meta/build-info")
    assert response.status_code == 200
    assert response.json() == {"commit": "dev", "built_at": ""}


@pytest.mark.parametrize(
    "content",
    [
        # Распаковка tar на контуре прервана — кончился диск, оборвалась
        # связь — и файл обрезан. К build-info идут ИМЕННО тогда, когда
        # доставка пошла не так, а он в этот момент отвечал 500.
        '{"commit":"abc12',
        "",
        "﻿{}",
        "null",
        '["a"]',
        "42",
        # Ключ есть, значение null: data.get(key, default) подставляет
        # умолчание, только когда ключа НЕТ, — в модель уезжал None и давал
        # 500 от валидации вместо честного «неизвестно».
        '{"commit": null, "built_at": null}',
    ],
)
async def test_broken_marker_answers_dev_without_traceback(
    client, login_as, monkeypatch, tmp_path, caplog, content
):
    marker = tmp_path / "build-info.json"
    marker.write_text(content, encoding="utf-8")
    monkeypatch.setattr(meta, "BUILD_INFO_FILE", marker)
    await login_as()
    with caplog.at_level("WARNING", logger=meta.__name__):
        response = await client.get("/api/meta/build-info")
    assert response.status_code == 200
    assert response.json()["commit"] == "dev"
    # Одна строка, без трейсбека: маршрут опрашивают часто, и двенадцать
    # тысяч символов трейсбека на запрос топят настоящую ошибку.
    assert [record.exc_info for record in _logged(caplog)] == [None]


async def test_marker_that_is_a_directory_answers_dev(
    client, login_as, monkeypatch, tmp_path
):
    # Каталог вместо файла: read_text даёт IsADirectoryError, то есть 500.
    (tmp_path / "build-info.json").mkdir()
    monkeypatch.setattr(meta, "BUILD_INFO_FILE", tmp_path / "build-info.json")
    await login_as()
    response = await client.get("/api/meta/build-info")
    assert response.status_code == 200
    assert response.json()["commit"] == "dev"


def test_document_names_and_paths_do_not_drift():
    # Два списка, которые ничто не связывало. Мутация: имя, добавленное
    # ТОЛЬКО в Literal, проходило ruff, mypy и pytest, уезжало в OpenAPI и в
    # типы клиента как валидное — и давало KeyError с пятисоткой при первом
    # обращении в бою. Обратный дрейф молчаливее: ключ без имени в Literal
    # недостижим навсегда, при том что запись в исходнике выглядит сделанной.
    #
    # Тест закрывает обе стороны; лишний ключ ловит ещё и mypy — через
    # аннотацию dict[DocumentName, Path].
    assert set(get_args(meta.DocumentName)) == set(meta.DOCUMENTS)


async def test_docs_requires_login(client):
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 401


async def test_docs_returns_markdown(client, login_as, monkeypatch, tmp_path):
    # Файл подставляется временный. Настоящие AGENTS.md и docs/commands/*
    # появляются в задачах 38–39, а чтение документа проверяется здесь — и
    # проверка не должна зависеть от того, что лежит в репозитории сегодня:
    # тест на содержимое чужого файла ломается при первой же его правке и
    # при этом ничего не говорит об этом обработчике.
    document = tmp_path / "AGENTS.md"
    document.write_text("# Правила\n", encoding="utf-8")
    monkeypatch.setitem(meta.DOCUMENTS, "agents", document)
    await login_as()
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 200
    assert response.json()["content"] == "# Правила\n"


async def test_known_name_without_file_is_404(client, login_as, monkeypatch, tmp_path):
    # Имя из списка разрешённых есть, а файла на диске нет: так выглядит
    # документ, который ещё не написан или переименован. Ответ — 404, а не
    # пятисотка от чтения несуществующего пути.
    monkeypatch.setitem(meta.DOCUMENTS, "agents", tmp_path / "нет-такого.md")
    await login_as()
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 404


async def test_directory_instead_of_document_is_404(
    client, login_as, monkeypatch, tmp_path
):
    # exists() истинно и для каталога, и чтение давало IsADirectoryError,
    # то есть 500 вместо внятного «не найден».
    directory = tmp_path / "AGENTS.md"
    directory.mkdir()
    monkeypatch.setitem(meta.DOCUMENTS, "agents", directory)
    await login_as()
    response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 404


async def test_unreadable_document_is_not_404(
    client, login_as, monkeypatch, tmp_path, caplog
):
    # Файл есть, но не в UTF-8. Для шаблона, чей AGENTS.md правят
    # произвольные команды, файл в CP1251 не экзотика. Ответ явный и с
    # записью в лог, но НЕ 404: «не найден» отправил бы человека искать
    # пропавший файл, которого он не терял.
    document = tmp_path / "AGENTS.md"
    document.write_bytes("# Правила\n".encode("cp1251"))
    monkeypatch.setitem(meta.DOCUMENTS, "agents", document)
    await login_as()
    with caplog.at_level("WARNING", logger=meta.__name__):
        response = await client.get("/api/meta/docs/agents")
    assert response.status_code == 500
    assert response.json() == {"error": "Документ не удалось прочитать", "field": None}
    # Одна строка, без трейсбека: HTTPException не доходит до обработчика
    # Exception, который пишет трейсбек на каждый запрос.
    assert [record.exc_info for record in _logged(caplog)] == [None]


@pytest.mark.parametrize(
    "name",
    [
        # Первым — единственное имя, которое различает реализации. Остальные
        # четыре отвергаются по посторонним причинам: `../` схлопывает сам
        # клиент ещё до запроса, имя со слэшем не подходит под сегмент пути,
        # а `secrets` и путь на два уровня вверх просто не существуют на
        # диске. Проверено мутацией: с именем, склеенным в путь, все четыре
        # оставались зелёными — то есть охраняли пустое место.
        #
        # `.env` лежит в корне репозитория и содержит секрет подписи сессий.
        # Со списком разрешённых имён он отвергается до входа в обработчик;
        # со склейкой — читается и уходит в ответ целиком.
        ".env",
        "../../.env",
        "..%2F..%2F.env",
        "secrets",
        "agents/../../.env",
    ],
)
async def test_unknown_document_rejected(client, login_as, name):
    # Имя документа не превращается в путь: список разрешённых задан явно.
    # Иначе первый же ../ отдал бы .env с секретом подписи наружу.
    await login_as()
    response = await client.get(f"/api/meta/docs/{name}")
    assert response.status_code in (404, 400)
