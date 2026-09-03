"""Клиент внешних моделей.

Сети здесь нет ни в одном тесте, включая тесты режима `live`: запрос
уходит в подменённый транспорт. Прогон, ходящий наружу, однажды краснеет не
по вине кода — и первым делом перестают верить прогону, а не поставщику.
"""

import json
import logging
import traceback

import httpx
import pytest

from app.integrations import client

# Ключ и адрес поставщика для режима live. Ключ лежит и в адресе тоже, и это
# не выдумка ради теста: так его принимают распространённые поставщики
# (`?key=...`). Именно поэтому адрес нельзя вставлять в текст отказа — вместе
# с ним уедет и ключ.
SECRET = "sk-tenant-42-do-not-log"
PROVIDER_URL = f"https://provider.invalid/v1/ask?key={SECRET}"


def _refuse_to_go_out(request: httpx.Request) -> httpx.Response:
    # Без адреса целиком: в нём лежит ключ, а этот текст попадает в отчёт
    # прогона.
    raise AssertionError(f"поход в сеть: {request.method} {request.url.host}")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Транспорт по умолчанию — тот, который падает на любом запросе.

    Без этого «без сети» в названиях тестов ниже — обещание, а не проверка:
    режим mock, случайно провалившийся в ветку live, дошёл бы до настоящего
    сокета, а на машине без интернета выглядел бы как отказ поставщика.
    """
    monkeypatch.setattr(client, "TRANSPORT", httpx.MockTransport(_refuse_to_go_out))


@pytest.fixture
def live(monkeypatch):
    """Режим live с заполненными настройками. Возвращает подмену ответа."""
    monkeypatch.setattr(client.settings, "integrations_mode", "live")
    monkeypatch.setattr(client.settings, "integrations_url", PROVIDER_URL)
    monkeypatch.setattr(client.settings, "integrations_api_key", SECRET)

    def _answer_with(handler):
        monkeypatch.setattr(client, "TRANSPORT", httpx.MockTransport(handler))

    return _answer_with


# --- mock ---------------------------------------------------------------


async def test_mock_answers_without_network(monkeypatch):
    # Умолчание — mock: шаблон обязан работать сразу после установки, без
    # ключей и без сети. Прогон, зависящий от чужого тарифа, — прогон,
    # который однажды покраснеет не по вине кода.
    monkeypatch.setattr(client.settings, "integrations_mode", "mock")
    assert await client.ask("сколько будет два и два") == client.MOCK_ANSWER


async def test_mock_is_deterministic(monkeypatch):
    monkeypatch.setattr(client.settings, "integrations_mode", "mock")
    assert await client.ask("а") == await client.ask("б")


# --- fixture ------------------------------------------------------------


async def test_fixture_answers_from_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(client.settings, "integrations_mode", "fixture")
    monkeypatch.setattr(client, "FIXTURES", tmp_path)
    (tmp_path / client.FIXTURE_NAME).write_text(
        json.dumps({"answer": "из записи"}), encoding="utf-8"
    )
    assert await client.ask("что угодно") == "из записи"


async def test_shipped_fixture_is_readable(monkeypatch):
    # Образец едет в репозитории, и режим fixture обязан работать на нём
    # сразу. Файл, потерянный при переносе или сломанный правкой руками, без
    # этой проверки обнаружился бы только у того, кто переключил режим.
    monkeypatch.setattr(client.settings, "integrations_mode", "fixture")
    assert await client.ask("что угодно")


async def test_missing_fixture_says_which_file(monkeypatch, tmp_path):
    # «Файл не найден» без имени отправляет искать по всему каталогу.
    monkeypatch.setattr(client.settings, "integrations_mode", "fixture")
    monkeypatch.setattr(client, "FIXTURES", tmp_path)
    with pytest.raises(RuntimeError) as missing:
        await client.ask("что угодно")
    assert client.FIXTURE_NAME in str(missing.value)


async def test_broken_fixture_says_which_file(monkeypatch, tmp_path):
    # Запись правят руками, и запятая в JSON — самая частая ошибка правки.
    # Голый JSONDecodeError говорит про строку и столбец, но не про то, в
    # каком файле они находятся.
    monkeypatch.setattr(client.settings, "integrations_mode", "fixture")
    monkeypatch.setattr(client, "FIXTURES", tmp_path)
    (tmp_path / client.FIXTURE_NAME).write_text("{это не json}", encoding="utf-8")
    with pytest.raises(RuntimeError) as broken:
        await client.ask("что угодно")
    assert client.FIXTURE_NAME in str(broken.value)


# --- live: настройки ----------------------------------------------------


async def test_live_without_a_key_refuses_loudly(monkeypatch):
    # Ключа нет — значит режим выставлен, а настройка забыта. Тихий возврат
    # к mock означал бы, что приложение отвечает выдумкой, считая это
    # ответом модели.
    #
    # Адрес при этом ЗАПОЛНЕН: с двумя пустыми настройками проверка «нет
    # ключа ИЛИ нет адреса» неотличима от «нет ключа И нет адреса», и
    # ошибочное «И» осталось бы незамеченным.
    monkeypatch.setattr(client.settings, "integrations_mode", "live")
    monkeypatch.setattr(client.settings, "integrations_url", PROVIDER_URL)
    monkeypatch.setattr(client.settings, "integrations_api_key", "")
    with pytest.raises(RuntimeError) as denial:
        await client.ask("вопрос")
    assert "INTEGRATIONS_API_KEY" in str(denial.value)


async def test_live_without_an_address_refuses_loudly(monkeypatch):
    # Вторая половина той же проверки. Без неё запрос ушёл бы на пустой
    # адрес и упал бы внутри httpx сообщением про относительный URL.
    monkeypatch.setattr(client.settings, "integrations_mode", "live")
    monkeypatch.setattr(client.settings, "integrations_url", "")
    monkeypatch.setattr(client.settings, "integrations_api_key", SECRET)
    with pytest.raises(RuntimeError) as denial:
        await client.ask("вопрос")
    assert "INTEGRATIONS_URL" in str(denial.value)


# --- live: запрос -------------------------------------------------------


async def test_request_carries_the_address_key_and_prompt(live):
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json={"answer": "четыре"})

    live(handler)
    assert await client.ask("сколько будет два и два") == "четыре"
    request = seen["request"]
    assert str(request.url) == PROVIDER_URL
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    assert json.loads(request.content) == {"prompt": "сколько будет два и два"}


async def test_request_carries_the_configured_timeout(live, monkeypatch):
    # Ожидание — настройка, и она обязана дойти до запроса. Проверяются все
    # четыре срока: httpx считает их по отдельности, и повисшее соединение
    # держит фоновую задачу ровно так же, как неотвеченный запрос. `None`
    # хотя бы в одном из них — это ожидание навсегда, то есть воркер, занятый
    # одной задачей до перезапуска, и «зависание» на экране без причины.
    monkeypatch.setattr(client.settings, "integrations_timeout_seconds", 7.0)
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["timeout"] = request.extensions["timeout"]
        return httpx.Response(200, json={"answer": "ок"})

    live(handler)
    await client.ask("вопрос")
    assert seen["timeout"] == {
        "connect": 7.0,
        "read": 7.0,
        "write": 7.0,
        "pool": 7.0,
    }


# --- live: отказы -------------------------------------------------------


async def test_provider_refusal_names_the_status(live):
    # Отказ поставщика — не сбой приложения. Человек должен увидеть, ЧТО
    # ответил поставщик: 401 значит «разберись с ключом», 503 — «подожди».
    live(lambda request: httpx.Response(503, text="temporarily unavailable"))
    with pytest.raises(RuntimeError) as refusal:
        await client.ask("вопрос")
    assert "503" in str(refusal.value)


async def test_silence_is_reported_with_the_time_waited(live, monkeypatch):
    monkeypatch.setattr(client.settings, "integrations_timeout_seconds", 7.0)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    live(handler)
    with pytest.raises(RuntimeError) as silence:
        await client.ask("вопрос")
    # Со сроком: без него «модель не ответила» не отличается от «модель
    # ответила отказом», и непонятно, что настройку можно поднять.
    assert "7" in str(silence.value)


async def test_unreachable_provider_is_reported_as_such(live):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    live(handler)
    with pytest.raises(RuntimeError) as unreachable:
        await client.ask("вопрос")
    assert "модел" in str(unreachable.value).lower()


async def test_answer_without_the_expected_field_is_a_clear_error(live):
    # Поставщика выбирает установка, и форма ответа у него своя. Голый
    # KeyError доезжает до экрана задач текстом «'answer'» — по нему не
    # понять ни кто виноват, ни что делать.
    live(lambda request: httpx.Response(200, json={"result": "четыре"}))
    with pytest.raises(RuntimeError) as broken:
        await client.ask("вопрос")
    assert "answer" in str(broken.value)


async def test_answer_that_is_not_a_string_is_refused(live):
    # str() над чужим ответом молча превращает {"text": ...} в строку
    # "{'text': 'четыре'}" — и это уезжает человеку КАК ОТВЕТ МОДЕЛИ.
    # Отказ честнее: ответа в понятном нам виде не пришло.
    live(lambda request: httpx.Response(200, json={"answer": {"text": "четыре"}}))
    with pytest.raises(RuntimeError):
        await client.ask("вопрос")


async def test_answer_that_is_not_json_is_a_clear_error(live):
    # Прокси и балансировщики отвечают HTML-страницей с кодом 200 чаще, чем
    # кажется.
    live(lambda request: httpx.Response(200, text="<html>Bad Gateway</html>"))
    with pytest.raises(RuntimeError) as broken:
        await client.ask("вопрос")
    assert "JSON" in str(broken.value)


# --- live: ключ не уезжает наружу ---------------------------------------


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(
            lambda request: httpx.Response(401, json={"error": "invalid key"}),
            id="отказ по статусу",
        ),
        pytest.param(
            lambda request: httpx.Response(200, text="не json"),
            id="ответ не разобрать",
        ),
    ],
)
async def test_the_key_never_leaves_the_client(live, caplog, handler):
    """Ключ поставщика не уезжает ни в текст отказа, ни в лог, ни в трейсбек.

    Требование проекта, а не пожелание: текст исключения из воркера
    записывается в задачу и показывается на экране, а трейсбек уходит в лог
    контура, который читают через `/logs`.

    Путь утечки здесь не выдуманный: httpx кладёт адрес запроса в текст
    `HTTPStatusError` («Client error '401 Unauthorized' for url ...»), а ключ
    у распространённых поставщиков лежит в адресе. Достаточно передать это
    исключение наружу — или оставить его в цепочке через `raise ... from`, —
    и ключ оказывается в логе целиком.
    """
    live(handler)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError) as failure:
            await client.ask("вопрос")

    printed = "".join(traceback.format_exception(failure.value))
    assert SECRET not in str(failure.value)
    assert SECRET not in printed
    assert SECRET not in caplog.text
