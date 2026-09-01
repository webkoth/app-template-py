import pytest
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


async def test_user_out_never_carries_the_hash(client, login_as):
    # Состав ответа не проверял ничто, и мутация «отдать password_hash в
    # UserOut» оставалась зелёной. Зеркальный запрет для журнала написан и
    # объяснён — здесь дыра была шире: список учётных записей открыт любому
    # админу и уходит в браузер.
    await login_as(role=Role.admin, login="boss")
    body = (await client.get("/api/users")).json()
    assert body and all("password_hash" not in row for row in body), body
    assert "scrypt" not in (await client.get("/api/users")).text


async def test_user_out_carries_status_and_last_login(client, login_as):
    # Обратная сторона: экран учётных записей показывает, кто отключён и
    # когда заходил. Мутация «убрать эти поля» тоже проходила молча.
    await login_as(role=Role.admin, login="boss")
    row = (await client.get("/api/users")).json()[0]
    assert row["status"] == "active"
    assert "last_login_at" in row


async def test_list_is_ordered_by_creation(client, session, login_as, make_user):
    # Порядок списка не закреплял ничто. Второй ключ — id: created_at
    # ставится в коде, и две записи одной миллисекунды иначе меняются
    # местами от запроса к запросу.
    await login_as(role=Role.admin, login="boss")
    await make_user(login="первый")
    await make_user(login="второй")
    logins = [u["login"] for u in (await client.get("/api/users")).json()]
    assert logins == ["boss", "первый", "второй"]


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


async def test_audit_names_the_account(client, session, login_as, make_user):
    # Запись «boss | create | User | 01a0… | admin» не отвечает на вопрос,
    # КОМУ выдали права: логин читается только сверкой UUID с живой базой.
    # Журнал обещает быть читаемым сам по себе и переживать учётную запись.
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
    created = (await session.execute(select(AuditLog))).scalars().one()
    assert "ivan" in created.detail
    assert "viewer" in created.detail


async def test_update_writes_audit_with_the_previous_value(
    client, session, login_as, make_user
):
    # Аудит ИЗМЕНЕНИЯ не проверял ни один тест — ни что запись есть, ни что
    # она в той же транзакции; для создания обе проверки стояли. И «роль →
    # admin» не отвечает, откуда роль поменяли, а журнал читают спустя
    # месяцы и без базы под рукой.
    await login_as(role=Role.admin, login="boss")
    target = await make_user(login="ivan", role=Role.viewer)
    await client.patch(f"/api/users/{target.id}", json={"role": "editor"})
    entry = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "update")))
        .scalars()
        .one()
    )
    assert entry.entity_id == str(target.id)
    assert "ivan" in entry.detail
    assert "viewer" in entry.detail and "editor" in entry.detail


async def test_repeating_the_same_change_is_not_an_error(client, login_as, make_user):
    # Двойной клик или повтор после обрыва связи. Изменение уже применено, и
    # красное на это человек видеть не должен.
    await login_as(role=Role.admin, login="boss")
    target = await make_user(login="ivan", role=Role.viewer)
    first = await client.patch(f"/api/users/{target.id}", json={"role": "editor"})
    second = await client.patch(f"/api/users/{target.id}", json={"role": "editor"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["role"] == "editor"


async def test_empty_patch_is_rejected(client, login_as, make_user):
    # А вот пустое тело — другое дело: запрос собран неверно, и молчать об
    # этом значит подтверждать несделанную работу.
    await login_as(role=Role.admin, login="boss")
    target = await make_user(login="ivan", role=Role.viewer)
    assert (await client.patch(f"/api/users/{target.id}", json={})).status_code == 400


async def test_extra_field_is_rejected(client, login_as, make_user):
    # Без запрета лишнего заявка с "status" отвечает 201 и заводит запись
    # АКТИВНОЙ: отправитель уверен, что завёл отключённую. Воспроизведено.
    await login_as(role=Role.admin, login="boss")
    created = await client.post(
        "/api/users",
        json={
            "login": "ivan",
            "name": "Иван",
            "role": "viewer",
            "password": "длинныйпароль",
            "status": "disabled",
        },
    )
    assert created.status_code == 400
    target = await make_user(login="петя", role=Role.viewer)
    updated = await client.patch(
        f"/api/users/{target.id}", json={"role": "editor", "name": "Новое"}
    )
    assert updated.status_code == 400


async def test_control_characters_rejected(client, login_as):
    # NUL до вставки не отсеивался, PostgreSQL его не принимает, asyncpg
    # бросает не IntegrityError — и запрос отвечал пятисоткой, а трейсбек с
    # параметрами уносил в лог хеш пароля только что заведённой записи.
    # Воспроизведено. Прочие управляющие символы не роняют ничего и потому
    # опаснее по-своему: имя «Иван\x1b[31m» заводилось молча.
    await login_as(role=Role.admin, login="boss")
    base = {
        "login": "ivan",
        "name": "Иван",
        "role": "viewer",
        "password": "длинныйпароль",
    }
    for field, value in [
        ("name", "Иван\x00Пет"),
        ("name", "Иван\x1b[31m"),
        ("login", "iv\x00an"),
    ]:
        response = await client.post("/api/users", json={**base, field: value})
        assert response.status_code == 400, (field, value, response.text)
        assert response.json()["field"] == field


async def test_digits_with_a_space_are_still_digits(client, login_as):
    # Запрет на цифровой пароль обходился одним пробелом в конце: «20260831 »
    # проходил isdigit() и потом нормально работал при входе. Проверяется
    # обрезанное значение, а хранится исходное — пробел в пароле законен.
    await login_as(role=Role.admin, login="boss")
    for password in ["20260831 ", "        "]:
        response = await client.post(
            "/api/users",
            json={
                "login": "ivan",
                "name": "Иван",
                "role": "viewer",
                "password": password,
            },
        )
        assert response.status_code == 400, password
        assert response.json()["field"] == "password"


async def test_counting_the_remaining_admins(session, make_user):
    # Правило «нельзя убрать последнего активного администратора» существует
    # ради одновременных запросов: два админа, A снимает права с B, B — с A.
    # Оба проходят require_role до чужого commit, строки разные, конфликта
    # нет — и контур остаётся без единого админа. Воспроизведено; вернуть
    # права после этого можно только прямым доступом к базе.
    #
    # Одним запросом ту дорогу не пройти, поэтому здесь проверяется счётчик,
    # на котором правило стоит. Ошибись он в любую сторону — и правило либо
    # не сработает никогда, либо запретит законное понижение.
    from app.features.users import service

    boss = await make_user(login="boss", role=Role.admin)
    assert await service.active_admins_besides(session, boss.id) == 0

    second = await make_user(login="второй", role=Role.admin)
    assert await service.active_admins_besides(session, boss.id) == 1
    assert await service.active_admins_besides(session, second.id) == 1

    # Отключённый администратор не считается: он войти не может.
    await make_user(login="третий", role=Role.admin, status=UserStatus.disabled)
    # Не-администратор тоже.
    await make_user(login="четвёртый", role=Role.editor)
    assert await service.active_admins_besides(session, boss.id) == 1


async def test_internal_failure_is_not_reported_as_missing(
    client, login_as, make_user, monkeypatch
):
    # `except LookupError` в роутере объявлял «не найдено» любой KeyError и
    # IndexError изнутри сервиса и выносил наружу текст чужого исключения.
    # Воспроизведено на строке с ролью, которой ещё нет в коде: 404 с текстом
    # «'owner' is not among the defined enum values…», и ни строки в логе.
    from app.features.users import service

    await login_as(role=Role.admin, login="boss")
    target = await make_user(login="ivan", role=Role.viewer)

    async def boom(*args: object, **kwargs: object) -> None:
        raise KeyError("внутренности")

    monkeypatch.setattr(service, "update_user", boom)
    # Исключение обязано уйти наверх — там его встретит обработчик пятисотки,
    # который пишет в лог и отвечает общим текстом. Обвязка тестов такие
    # исключения пробрасывает, и это ровно то, что здесь и проверяется:
    # раньше на их месте был 404 с текстом чужого исключения в теле.
    with pytest.raises(KeyError):
        await client.patch(f"/api/users/{target.id}", json={"role": "editor"})


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
