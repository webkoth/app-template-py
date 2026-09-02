"""Каждый маршрут приложения проверяет доступ.

`AGENTS.md` обещает `require_role` на каждом маршруте, и до этого файла
обещание не держалось ничем. Маршрут, у которого забыли `= EditorDep`,
проходил ruff, mypy, import-linter и все остальные тесты: это значение
параметра по умолчанию, а не аргумент декоратора, и в дифе его отсутствие
не бросается в глаза. Красным становилась одна сверка типов клиента — а
лечится она командой `make openapi`, после которой прогон зелёный, а
маршрут уезжает на публичный контур открытым. Воспроизведено ревью.

Проверка идёт не по тексту роутеров, а по дереву зависимостей, которое
FastAPI построил на самом деле (`Dependant.dependencies` рекурсивно). Так
считаются обе формы записи — и `_: CurrentUser = ViewerDep` в сигнатуре, и
`dependencies=[Depends(...)]` у декоратора, — и не считается комментарий,
похожий на защиту.

«Совсем открыт» и «нужен вход» — разные вещи, и списка здесь два. Маршрут с
`CurrentUserDep` пускает любого вошедшего, включая `viewer`, но анонима не
пускает. Держи их в одном списке — и тест перестал бы отличать «решили
пускать всех» от «решили пускать всех вошедших»; первое на контуре, открытом
в интернет, означает совсем не то же самое, что второе.
"""

from collections.abc import Iterator, Sequence
from typing import Any, NamedTuple

from starlette.routing import Mount

from app.core.deps import get_current_user, require_role
from app.core.static import DIST
from app.domain.roles import Role
from app.main import app

# Маршруты, открытые СОВСЕМ: ни роли, ни входа. Каждый — по устройству, и
# рядом сказано почему. Пополнять этот список — решение, а не формальность:
# всё, что сюда попало, доступно любому, кто знает адрес контура.
FULLY_OPEN = {
    "GET /api/health": (
        "проверку живости зовут доставка и монитор, сессии у них нет; "
        "закрытая проверка означала бы, что контур некому опросить"
    ),
    "POST /api/auth/login": "выдаёт сессию — требовать сессию нечем",
    "POST /api/auth/logout": (
        "гасить куку надо и тогда, когда она уже недействительна; "
        "закрытый выход оставлял бы человека с мёртвой кукой в браузере"
    ),
}

# Требуют входа, но не роли: пускают любого вошедшего, включая `viewer`.
LOGIN_ONLY = {
    "GET /api/auth/me": (
        "отдаёт данные самого вошедшего; роль здесь и проверять не по чему — "
        "экран узнаёт её именно отсюда"
    ),
    "GET /api/meta/build-info": (
        "версия доставленного кода; анониму знать её незачем, а вошедшему "
        "нужна любому — по ней разбирают, что именно сейчас на контуре"
    ),
    "GET /api/meta/docs/{name}": (
        "правила и тексты команд из репозитория; их читает экран /docs, "
        "открытый всем вошедшим"
    ),
}

# Перехватчик SPA и статика сборки. Оба существуют только при собранном
# фронтенде (`mount_frontend` выходит первой строкой, когда `frontend/dist`
# нет), поэтому ожидание считается по диску, а не задаётся константой: в CI
# бэкенд-тесты идут до `npm run build`, и там этих маршрутов не будет.
SPA_FALLBACK = "GET /{path:path}"
SPA_ASSETS = "/assets"


class Guards(NamedTuple):
    fully_open: set[str]
    login_only: set[str]
    role_guarded: set[str]
    mounts: set[str]
    unknown: set[str]


def _leaves(nodes: Sequence[Any]) -> Iterator[Any]:
    """Разворачивает дерево маршрутизации до листьев.

    `app.routes` — не плоский список. Начиная с FastAPI 0.141 `include_router`
    кладёт туда обёртку над роутером, а не копии маршрутов с готовым путём.
    Обёртка отдаёт свои листья вместе с уже склеенным путём и с
    зависимостями, которые навесил сам `include_router`; склеивать префиксы
    руками значило бы повторять чужую работу и однажды разойтись с ней.

    Наивный `for r in app.routes: if isinstance(r, APIRoute)` здесь не падает,
    а молча находит один маршрут из четырнадцати — перехватчик SPA. Тест на
    таком обходе был бы вечнозелёным. Поэтому ниже списки сверяются на
    равенство в обе стороны: обход, недосчитавшийся маршрутов, даёт красный,
    а не тишину.
    """
    for node in nodes:
        children = getattr(node, "effective_candidates", None)
        if children is None:
            yield node
        else:
            yield from _leaves(children())


def _dependencies(dependant: Any) -> Iterator[Any]:
    """Все зависимости маршрута, включая вложенные.

    Рекурсия обязательна: `require_role` возвращает замыкание, которое само
    зависит от `get_current_user`, и на первом уровне лежит только оно.
    """
    for sub in dependant.dependencies:
        yield sub
        yield from _dependencies(sub)


def _is_role_guard(call: object) -> bool:
    """Зависимость ли это, которую вернул `require_role`.

    Опознаётся по модулю и `__qualname__` замыкания, и оба берутся у самого
    `require_role`, а не выписаны строкой. Переименование внутренней функции
    проверку не ломает; переименование или переезд самого `require_role`
    ломает — и ломает громко, отдельным тестом ниже, а не молчаливым «защиты
    нет ни у кого».
    """
    module = getattr(call, "__module__", None)
    qualname = getattr(call, "__qualname__", "")
    prefix = f"{require_role.__qualname__}.<locals>."
    return module == require_role.__module__ and qualname.startswith(prefix)


def _collect() -> Guards:
    guards = Guards(set(), set(), set(), set(), set())
    for node in _leaves(app.routes):
        if isinstance(node, Mount):
            guards.mounts.add(node.path)
            continue
        if not hasattr(node, "dependant") or not hasattr(node, "methods"):
            guards.unknown.add(repr(node))
            continue

        calls = [sub.call for sub in _dependencies(node.dependant)]
        needs_login = any(call is get_current_user for call in calls)
        needs_role = any(_is_role_guard(call) for call in calls)

        for method in node.methods:
            name = f"{method} {node.path}"
            if needs_role:
                guards.role_guarded.add(name)
            elif needs_login:
                guards.login_only.add(name)
            else:
                guards.fully_open.add(name)
    return guards


def _expected_open() -> set[str]:
    return set(FULLY_OPEN) | ({SPA_FALLBACK} if DIST.exists() else set())


def test_role_guard_is_recognised():
    # Опора всей проверки: если распознавание сломается, красным станет этот
    # тест с понятным именем, а не четырнадцать чужих.
    assert _is_role_guard(require_role(Role.viewer))
    assert not _is_role_guard(get_current_user)


def test_no_route_is_open_by_accident():
    open_routes = _collect().fully_open
    expected = _expected_open()

    unexpected = sorted(open_routes - expected)
    assert not unexpected, (
        f"Маршрут открыт без единой проверки доступа: {', '.join(unexpected)}. "
        "Добавь зависимость роли (`_: CurrentUser = ViewerDep` и подобные). "
        "Если маршрут открыт намеренно — впиши его в FULLY_OPEN этого файла "
        "вместе с объяснением, почему он открыт."
    )

    missing = sorted(expected - open_routes)
    assert not missing, (
        f"Маршруты из FULLY_OPEN не найдены: {', '.join(missing)}. "
        "Либо их переименовали или удалили — тогда поправь список, либо обход "
        "маршрутов перестал их видеть, и тогда проверка ничего не проверяет."
    )


def test_routes_without_role_check_require_at_least_a_login():
    login_only = _collect().login_only
    expected = set(LOGIN_ONLY)

    unexpected = sorted(login_only - expected)
    assert not unexpected, (
        f"Маршрут пускает любого вошедшего, роль не проверяется: "
        f"{', '.join(unexpected)}. Это отдельное решение, а не мелочь: "
        "`viewer` увидит то же, что `admin`. Добавь `require_role` или впиши "
        "маршрут в LOGIN_ONLY с объяснением."
    )

    missing = sorted(expected - login_only)
    assert not missing, (
        f"Маршруты из LOGIN_ONLY не найдены: {', '.join(missing)}. "
        "Проверь, не переименовали ли их и видит ли их обход."
    )


def test_the_rest_of_the_api_is_guarded_by_role():
    guarded = _collect().role_guarded
    # Положительная сторона проверки. Два теста выше запрещают лишнее в двух
    # списках, но оба остались бы зелёными на обходе, который не нашёл ничего.
    # Здесь названы маршруты каждой закрытой фичи: пропал любой — обход сломан
    # или маршрут потерял защиту.
    for name in (
        "GET /api/users",
        "POST /api/users",
        "PATCH /api/users/{user_id}",
        "GET /api/expenses",
        "POST /api/expenses",
        "DELETE /api/expenses/{expense_id}",
        # Таблицы: смотрит их любой вошедший, а загружает и удаляет только
        # editor. В FULLY_OPEN и LOGIN_ONLY им места нет — загруженная
        # таблица это данные приложения, а не общедоступный файл.
        "GET /api/datasets",
        "POST /api/datasets",
        "DELETE /api/datasets/{dataset_id}",
        "GET /api/audit",
    ):
        assert name in guarded, f"{name} больше не проверяет роль"


def test_static_mounts_are_declared():
    # Примонтированный каталог отдаётся без всяких зависимостей: `Depends` к
    # нему не применяется вовсе. Поэтому монтирование — тоже решение о
    # доступе, и новое обязано быть замечено здесь, а не на контуре.
    mounts = _collect().mounts
    expected = {SPA_ASSETS} if DIST.exists() else set()
    assert mounts == expected, (
        f"Список примонтированных каталогов изменился: {sorted(mounts)}. "
        "Всё, что смонтировано, доступно любому без входа — убедись, что там "
        "нет ничего частного, и обнови ожидание."
    )


def test_every_route_kind_is_understood():
    # Страховка обхода: маршрут неизвестного вида не проверен ничем и обязан
    # быть замечен, а не пропущен молча.
    unknown = sorted(_collect().unknown)
    assert not unknown, (
        f"Маршрут неизвестного вида, проверка доступа к нему не считана: "
        f"{', '.join(unknown)}."
    )
