from sqlalchemy import select

from app.core.audit import AuditLog
from app.core.users import User, UserStatus
from app.domain.roles import Role


async def test_list_requires_admin(client, login_as):
    await login_as(role=Role.editor)
    assert (await client.get("/api/users")).status_code == 403


async def test_create_and_update_require_admin(client, login_as, make_user):
    # Роль проверяется на КАЖДОМ маршруте, а не только на чтении списка.
    # Проверка одного маршрута оставляет мутацию «снять AdminDep с создания»
    # зелёной — а это открытая дверь: любой вошедший заводит себе админа.
    await login_as(role=Role.editor, login="ivan")
    target = await make_user(login="жертва", role=Role.viewer)
    created = await client.post(
        "/api/users",
        json={
            "login": "новый",
            "name": "Новый",
            "role": "admin",
            "password": "длинныйпароль",
        },
    )
    assert created.status_code == 403
    updated = await client.patch(f"/api/users/{target.id}", json={"role": "admin"})
    assert updated.status_code == 403


async def test_admin_sees_list(client, login_as):
    await login_as(role=Role.admin, login="boss")
    response = await client.get("/api/users")
    assert response.status_code == 200
    assert [u["login"] for u in response.json()] == ["boss"]


async def test_create_user(client, session, login_as):
    await login_as(role=Role.admin, login="boss")
    response = await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "editor",
            "password": "длинныйпароль",
        },
    )
    assert response.status_code == 201
    created = (
        await session.execute(select(User).where(User.login == "ivan"))
    ).scalar_one()
    assert created.role is Role.editor


async def test_create_writes_audit_in_same_transaction(client, session, login_as):
    await login_as(role=Role.admin, login="boss")
    await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "viewer",
            "password": "длинныйпароль",
        },
    )
    entries = (await session.execute(select(AuditLog))).scalars().all()
    assert [(e.actor, e.action, e.entity) for e in entries] == [
        ("boss", "create", "User")
    ]


async def test_created_user_can_log_in(client, login_as):
    # Замыкание круга: заведённой записью можно войти. Без этого мутация,
    # кладущая пароль в password_hash как есть, остаётся зелёной — учётные
    # записи создаются, выглядят целыми, и ни одна из них не работает.
    await login_as(role=Role.admin, login="boss")
    await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "viewer",
            "password": "длинныйпароль",
        },
    )
    response = await client.post(
        "/api/auth/login", json={"login": "ivan", "password": "длинныйпароль"}
    )
    assert response.status_code == 200


async def test_password_never_reaches_the_journal(client, session, login_as):
    # В журнал пишет тот же вызов, что и создание, и дописать туда «что
    # завели» — соблазн на одну строку. Журнал читают админы, он переживает
    # учётную запись и уезжает в резервные копии.
    await login_as(role=Role.admin, login="boss")
    await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "viewer",
            "password": "оченьсекретно",
        },
    )
    details = (await session.execute(select(AuditLog.detail))).scalars().all()
    assert all("оченьсекретно" not in (d or "") for d in details), details


async def test_duplicate_login_rejected_with_message(client, login_as):
    await login_as(role=Role.admin, login="boss")
    body = {
        "login": "ivan",
        "name": "Иван",
        "role": "viewer",
        "password": "длинныйпароль",
    }
    assert (await client.post("/api/users", json=body)).status_code == 201
    second = await client.post("/api/users", json=body)
    # Не 500 от нарушения уникальности: это ожидаемая ошибка формы.
    assert second.status_code == 400
    assert second.json()["field"] == "login"


async def test_login_is_stored_lowercase(client, login_as):
    # Регистр приводится схемой, а не только сравнивается при входе: иначе в
    # базе жили бы `Ivan` и `ivan` как разные записи с общим бюджетом попыток.
    await login_as(role=Role.admin, login="boss")
    response = await client.post(
        "/api/users",
        json={
            "login": "IVAN",
            "name": "Иван",
            "role": "viewer",
            "password": "длинныйпароль",
        },
    )
    assert response.status_code == 201
    assert response.json()["login"] == "ivan"
    # И повтор в другом регистре — тот же логин, а не второй.
    second = await client.post(
        "/api/users",
        json={
            "login": "Ivan",
            "name": "Иван",
            "role": "viewer",
            "password": "длинныйпароль",
        },
    )
    assert second.status_code == 400
    assert second.json()["field"] == "login"


async def test_blank_name_rejected(client, login_as):
    # Пробелы проходят проверку длины, если обрезать после неё, и в списке
    # пользователей появляется строка без имени — выглядит как сбой отрисовки.
    await login_as(role=Role.admin, login="boss")
    response = await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "   ",
            "role": "viewer",
            "password": "длинныйпароль",
        },
    )
    assert response.status_code == 400
    assert response.json()["field"] == "name"


async def test_index_gives_the_same_message_as_the_check(
    client, login_as, make_user, monkeypatch
):
    # Проверку до вставки обходят две одновременные заявки с одним логином:
    # между проверкой и вставкой стоит await на scrypt, и обе проходят. Здесь
    # то же самое воспроизводится дёшево — проверка отключается, и заявка
    # упирается прямо в уникальный индекс.
    #
    # Без обработки индекса админ видит «Что-то пошло не так» вместо «логин
    # занят», а в лог уезжает трейсбек с текстом SQL: охранник сработал, а
    # выглядит поломкой.
    from app.features.users import service

    await login_as(role=Role.admin, login="boss")
    await make_user(login="ivan")

    async def never_taken(*args: object, **kwargs: object) -> bool:
        return False

    monkeypatch.setattr(service, "login_taken", never_taken)
    response = await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "viewer",
            "password": "длинныйпароль",
        },
    )
    assert response.status_code == 400
    assert response.json()["field"] == "login"


async def test_all_digit_password_rejected(client, login_as):
    # Восемь цифр проходят по длине, но это дата или телефон — то, что
    # подбирают первым.
    await login_as(role=Role.admin, login="boss")
    response = await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "viewer",
            "password": "20260831",
        },
    )
    assert response.status_code == 400
    assert response.json()["field"] == "password"


async def test_short_password_rejected(client, login_as):
    # Семь символов, а не «123»: короткая строка проходит и при пороге в
    # три, то есть саму восьмёрку такой тест не закрепляет. Ровно на один
    # меньше порога — закрепляет.
    await login_as(role=Role.admin, login="boss")
    response = await client.post(
        "/api/users",
        json={"login": "ivan", "name": "Иван", "role": "viewer", "password": "семьсим"},
    )
    assert response.status_code == 400
    assert response.json()["field"] == "password"


async def test_disable_revokes_sessions(client, session, login_as, make_user):
    await login_as(role=Role.admin, login="boss")
    victim = await make_user(login="ivan", role=Role.viewer)
    response = await client.patch(
        f"/api/users/{victim.id}", json={"status": "disabled"}
    )
    assert response.status_code == 200
    await session.refresh(victim)
    assert victim.status is UserStatus.disabled
    # Отключение обязано отзывать уже выданные сессии: иначе человек
    # продолжает работать до истечения куки.
    assert victim.sessions_valid_from is not None


async def test_change_role(client, session, login_as, make_user):
    await login_as(role=Role.admin, login="boss")
    target = await make_user(login="ivan", role=Role.viewer)
    response = await client.patch(f"/api/users/{target.id}", json={"role": "editor"})
    assert response.status_code == 200
    await session.refresh(target)
    assert target.role is Role.editor


async def test_cannot_disable_self(client, login_as):
    # Отключив себя, администратор запирает контур: войти, чтобы включить
    # обратно, будет некому.
    me = await login_as(role=Role.admin, login="boss")
    response = await client.patch(f"/api/users/{me.id}", json={"status": "disabled"})
    assert response.status_code == 400


async def test_cannot_demote_self(client, session, login_as):
    # Вторая дверь в ту же комнату. Единственный администратор, понизивший
    # себя до editor, запирает контур ровно так же, как отключивший, — а
    # проверка статуса эту дорогу не перекрывает.
    me = await login_as(role=Role.admin, login="boss")
    response = await client.patch(f"/api/users/{me.id}", json={"role": "viewer"})
    assert response.status_code == 400
    assert response.json()["field"] == "role"
    await session.refresh(me)
    assert me.role is Role.admin


async def test_admin_can_promote_someone_else(client, session, login_as, make_user):
    # Обратная сторона запрета: он про себя, а не про роль вообще. Без этой
    # проверки правило «нельзя понижать администратора» прошло бы незамеченным.
    await login_as(role=Role.admin, login="boss")
    other = await make_user(login="ivan", role=Role.admin)
    response = await client.patch(f"/api/users/{other.id}", json={"role": "viewer"})
    assert response.status_code == 200
    await session.refresh(other)
    assert other.role is Role.viewer


async def test_unknown_user_is_404(client, login_as):
    await login_as(role=Role.admin)
    missing = "01a05000-0000-7000-8000-000000000000"
    response = await client.patch(f"/api/users/{missing}", json={"role": "admin"})
    assert response.status_code == 404
