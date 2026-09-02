"""Служебные маршруты: живость, версия сборки, тексты правил для /docs."""

import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import REPO_ROOT
from app.core.deps import CurrentUserDep, SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta"])

# Корень репозитория берётся из конфигурации, а не считается здесь заново.
# Счёт уровней от файла (parents[N]) верен ровно для одного места в дереве:
# в config.py их три, в этом файле было бы четыре. Два ручных счёта одного и
# того же каталога расходятся молча — при переносе app/ под src/ поиск .env
# и пути документов сломались бы по-разному, и вторую поломку искали бы
# отдельно. Здесь корень нужен как основание для путей документов и маркера
# сборки: они лежат вне backend/, куда смотрит рабочий каталог процесса.
BUILD_INFO_FILE = REPO_ROOT / "build-info.json"

# Значение, которым отвечает версия сборки, когда её негде взять: файла нет
# (обычная разработка) или он испорчен. Честное «неизвестно», а не выдумка.
UNKNOWN_COMMIT = "dev"

DocumentName = Literal[
    "agents", "checklist", "onboarding", "ship", "status", "logs", "rollback"
]

# Список разрешённых документов задан явно, а имя НЕ превращается в путь.
# Любая склейка вида REPO_ROOT / name отдала бы .env с секретом подписи по
# первому же ../ в запросе.
#
# Тип ключа — DocumentName, а не str, намеренно: список имён и таблица путей
# ничем друг с другом не связаны, и разъезжаются они беззвучно. Проверено
# мутацией: имя, добавленное только в Literal, проходило ruff, mypy и
# pytest, уезжало в OpenAPI и в типы клиента как валидное, а в бою давало
# KeyError и пятисотку. С этой аннотацией лишний ключ ловит mypy, лишнее имя
# в Literal — тест на совпадение множеств.
DOCUMENTS: dict[DocumentName, Path] = {
    "agents": REPO_ROOT / "AGENTS.md",
    "checklist": REPO_ROOT / "CHECKLIST.md",
    "onboarding": REPO_ROOT / "docs" / "commands" / "onboarding.md",
    "ship": REPO_ROOT / "docs" / "commands" / "ship.md",
    "status": REPO_ROOT / "docs" / "commands" / "status.md",
    "logs": REPO_ROOT / "docs" / "commands" / "logs.md",
    "rollback": REPO_ROOT / "docs" / "commands" / "rollback.md",
}


class Health(BaseModel):
    status: Literal["ok"]


class BuildInfo(BaseModel):
    commit: str
    built_at: str


class Document(BaseModel):
    name: str
    content: str


@router.get("/health", response_model=Health)
async def health(session: SessionDep) -> Health:
    """Проверка живости. Авторизации не требует.

    Без авторизации живут ровно три маршрута, и каждый по устройству: этот —
    потому что его зовёт доставка и монитор, у которых сессии нет; вход —
    потому что сессию он и выдаёт; выход — потому что гасить куку человеку
    надо и тогда, когда она уже недействительна.

    Ходит в базу намеренно: проверка, которая отвечает 200 при недоступной
    базе, подтверждает только то, что процесс жив, — а доставка на основании
    такой проверки объявляет успешной заведомо нерабочий контур.

    Сбой базы ловится и превращается в 503, а не летит наверх пятисоткой.
    Три причины, и ни одна не про красоту кода. 503 — это «сервис временно
    недоступен», ровно то, что произошло, и балансировщик с монитором
    понимают его без объяснений. Пятисотка же означает «в коде что-то
    сломалось» и тянет за собой трейсбек в лог на КАЖДУЮ проверку живости —
    а ходит она раз в несколько секунд, и настоящая ошибка утонет. И
    третье: ветку отказа можно проверить тестом только если она отвечает, а
    не выбрасывает.

    Ловится Exception, а не SQLAlchemyError. Узкая ловля закрывала только
    сбой на УЖЕ УСТАНОВЛЕННОМ соединении — случай, который в жизни
    встречается реже всего. Отказ на этапе подключения до SQLAlchemy не
    доходит: замерено — незапущенная СУБД даёт голый ConnectionRefusedError,
    недоступный хост socket.gaierror, удалённая база и отсутствующая роль —
    собственные классы asyncpg. Ни один из них не SQLAlchemyError, и все
    четыре отвечали 500 с трейсбеком в двенадцать тысяч символов на каждый
    опрос, то есть ровно тем вредом, ради которого ветка 503 и написана.
    Проверка живости, упавшая по любой причине, обязана сказать «сервис
    недоступен»: 500 отправляет человека искать ошибку в коде, когда лежит
    база.

    В лог — одна строка, а не трейсбек: при опросе раз в несколько секунд
    трейсбек затопил бы лог именно тогда, когда его читают.

    Доставка ждёт ровно 200, так что 503 её по-прежнему останавливает.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception as error:
        logger.warning("проверка живости: база недоступна (%s)", type(error).__name__)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "База данных недоступна"
        ) from error
    return Health(status="ok")


@router.get("/meta/build-info", response_model=BuildInfo)
async def build_info(user: CurrentUserDep) -> BuildInfo:
    """Версия доставленного кода. Пишется при сборке, читается с диска.

    Авторизация обязательна: совсем без неё живут три маршрута — проверка
    живости, вход и выход, — и каждый по своему устройству; список закреплён
    в `tests/api/test_route_guards.py`. Здесь же ничего такого нет: точный
    задеплоенный коммит анониму знать незачем.

    Файл пришёл извне процесса, поэтому и разбирается как испорченный.
    Замерено с настоящим файлом на диске: обрезанный JSON, пустой файл, файл
    с BOM, `null`, `["a"]`, `{"commit": null}` и каталог вместо файла — все
    давали 500. К этому маршруту идут ИМЕННО тогда, когда доставка пошла не
    так (прерванная распаковка tar оставляет обрезанный файл), и ломался он
    ровно в этот момент. Испорченный файл — не повод для пятисотки: версия
    сборки неизвестна, так и надо ответить.
    """
    try:
        raw = json.loads(BUILD_INFO_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # Файла нет — это норма разработки, а не происшествие: молча.
        return BuildInfo(commit=UNKNOWN_COMMIT, built_at="")
    except (OSError, ValueError) as error:
        # OSError — каталог вместо файла, права, сбой чтения; ValueError —
        # и JSONDecodeError, и UnicodeDecodeError. Одна строка, без
        # трейсбека: к маршруту ходят часто.
        logger.warning("build-info.json не прочитан: %s", type(error).__name__)
        return BuildInfo(commit=UNKNOWN_COMMIT, built_at="")
    commit = _text(_value(raw, "commit"), "")
    if not commit:
        # Разобралось, но коммита в этом нет: корнем файла бывает `null`,
        # список или число, а бывает и объект со значением null у ключа.
        logger.warning("build-info.json без коммита: %s", type(raw).__name__)
        return BuildInfo(commit=UNKNOWN_COMMIT, built_at="")
    return BuildInfo(commit=commit, built_at=_text(_value(raw, "built_at"), ""))


@router.get("/meta/docs/{name}", response_model=Document)
async def document(name: DocumentName, user: CurrentUserDep) -> Document:
    """Отдаёт текст правил или команды. Читает файлы репозитория с диска.

    is_file(), а не exists(): exists() истинно и для каталога, и чтение
    такого пути давало IsADirectoryError и пятисотку вместо внятного «не
    найден». Он же отсекает симлинк на каталог. На симлинк-файл проверка не
    влияет — замерено, что AGENTS.md, указывающий на файл со строкой
    APP_AUTH_SECRET, отдавался с кодом 200 вместе с секретом; атакой это не
    является (симлинк надо самому положить в репозиторий), но лишний довод
    против exists().
    """
    path = DOCUMENTS[name]
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        # Файл есть, но не читается — не 404: «не найден» отправил бы
        # человека искать пропавший файл, которого он не терял. Частый
        # случай — не UTF-8: AGENTS.md в шаблоне правят произвольные
        # команды, и файл в CP1251 не экзотика (UnicodeDecodeError — это
        # ValueError). Отказ явный и с записью в лог, но одной строкой:
        # HTTPException не доходит до обработчика Exception, который пишет
        # трейсбек на каждый запрос.
        logger.warning("документ %s не прочитан: %s", name, type(error).__name__)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Документ не удалось прочитать"
        ) from error
    return Document(name=name, content=content)


def _value(raw: object, key: str) -> object:
    """Поле разобранного JSON, если это вообще объект.

    Корнем файла бывает `null`, список или число — тогда полей нет ни
    одного, и .get() на таком значении падал AttributeError.
    """
    return raw.get(key) if isinstance(raw, dict) else None


def _text(value: object, default: str) -> str:
    """Непустая строка или запасное значение.

    Проверка на тип и на пустоту, а не data.get(key, default): умолчание у
    .get() подставляется, только когда ключа НЕТ. При `{"commit": null}`
    ключ есть, значение None — и в модель уезжал None, то есть 500 от
    валидации вместо честного «неизвестно».
    """
    return value if isinstance(value, str) and value else default
