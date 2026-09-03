"""Клиент внешних моделей: три режима вместо одного.

`mock` — умолчание. Шаблон обязан работать сразу после установки: без
ключей, без сети, без чужого тарифа. Прогон, зависящий от внешнего сервиса,
однажды краснеет не по вине кода — и первым делом перестают верить прогону,
а не сервису.

`fixture` — записанные ответы с диска: тот же детерминизм, но на настоящей
форме ответа.

`live` — настоящий HTTP. Конкретного поставщика шаблон не выбирает: адрес и
ключ приходят из настроек при установке. Поэтому и форма ответа проверяется,
а не берётся на веру: `{"answer": "..."}` — это НАШ уговор, а не общий
стандарт, и первый же поставщик, отвечающий иначе, обязан получить внятный
отказ, а не KeyError на экране задач.

Функция одна и она асинхронная: и обработчик запроса, и обработчик фоновой
задачи в этом проекте асинхронные, а синхронный HTTP внутри них держит весь
процесс — все запросы всех пользователей — на время ожидания поставщика.
"""

import json
import logging
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# httpx пишет КАЖДЫЙ свой запрос в лог на уровне INFO и пишет его целиком:
# «HTTP Request: POST https://provider.invalid/v1/ask?key=sk-... "200 OK"».
# У распространённых поставщиков ключ передаётся ровно так — параметром
# адреса, — а приложение и воркер настроены на INFO. То есть ключ уезжал бы
# в лог контура при каждом обращении к модели, а лог читают через /logs.
# Проверено тестом: строка появляется и на успешном ответе, и на отказе.
#
# Уровень поднимается здесь, а не в main.py и worker.py: риск создаёт этот
# модуль, и лечиться он должен там же — иначе один из двух процессов
# однажды заведут без этой строки. Своё сообщение об отказе ниже пишется
# без адреса, так что наблюдаемость не теряется.
#
# Уровень DEBUG эта строка не спасает: на нём httpx и httpcore печатают
# заголовки и адрес независимо от неё. Логи контура идут на INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
# Имя файла — латиницей, как и все имена файлов в проекте. Кириллическое имя
# здесь ещё и переносится хуже: macOS хранит его в одной нормализации
# Unicode, Linux в другой, и файл, найденный на машине разработчика, на
# контуре «не существует».
FIXTURE_NAME = "answer.json"
# Поле ответа — наш уговор с поставщиком, записанный в одном месте: он
# упоминается и в разборе ответа, и в тексте отказа, и в записанном образце.
ANSWER_FIELD = "answer"
MOCK_ANSWER = "Ответ внешней модели (режим mock)"

# Транспорт запроса. None — обычный, сетевой; тесты подменяют его на
# подставной. Это единственная точка подмены: режим live обязан
# проверяться, но проверяться без похода наружу — прогон не должен зависеть
# ни от сети, ни от чужого тарифа.
TRANSPORT: httpx.AsyncBaseTransport | None = None


async def ask(prompt: str) -> str:
    """Задаёт вопрос внешней модели. Режим — из настроек."""
    if settings.integrations_mode == "mock":
        return MOCK_ANSWER

    if settings.integrations_mode == "fixture":
        return _recorded()

    return await _from_provider(prompt)


def _recorded() -> str:
    """Записанный ответ с диска."""
    path = FIXTURES / FIXTURE_NAME
    if not path.is_file():
        # Имя файла в тексте: «файл не найден» без имени отправляет искать
        # по всему каталогу.
        raise RuntimeError(f"Нет записанного ответа: {path}")
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as broken:
        # Запись правят руками, и голый JSONDecodeError называет строку и
        # столбец, но не файл, в котором они находятся.
        raise RuntimeError(
            f"Записанный ответ не разобрать как JSON: {path}"
        ) from broken
    return _answer_in(recorded, f"Записанный ответ {path}")


async def _from_provider(prompt: str) -> str:
    """Настоящий запрос к поставщику."""
    url = settings.integrations_url
    key = settings.integrations_api_key
    if not key or not url:
        # Громко, а не откатом к mock. Тихий откат означал бы, что
        # приложение отвечает выдумкой, считая это ответом модели, — и
        # заметить это можно только по смыслу ответа.
        #
        # В тексте — ИМЕНА переменных, а не значения: он уезжает в лог и на
        # экран задач.
        raise RuntimeError(
            "Режим live выбран, но INTEGRATIONS_API_KEY или INTEGRATIONS_URL пуст"
        )

    waited = settings.integrations_timeout_seconds
    try:
        # Срок ожидания задаётся явно и всегда. У httpx есть своё умолчание,
        # но полагаться на него нельзя: чужое умолчание меняется с версией, а
        # запрос без срока держит фоновую задачу до перезапуска процесса — на
        # экране это выглядит зависанием без причины.
        async with httpx.AsyncClient(transport=TRANSPORT, timeout=waited) as http:
            response = await http.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={"prompt": prompt},
            )
        response.raise_for_status()
    except httpx.TimeoutException:
        logger.warning("внешняя модель не ответила за %s с", waited)
        # Со сроком в тексте: иначе «модель не ответила» неотличимо от
        # «модель ответила отказом», и непонятно, что настройку можно
        # поднять.
        raise RuntimeError(f"Внешняя модель не ответила за {waited:g} с") from None
    except httpx.HTTPStatusError as refusal:
        status = refusal.response.status_code
        logger.warning("внешняя модель ответила отказом: HTTP %s", status)
        # `from None` — не украшение. httpx кладёт адрес запроса в текст
        # HTTPStatusError («Client error '401 Unauthorized' for url ...»), а
        # ключ у распространённых поставщиков лежит в адресе. Оставленная
        # цепочка печатается в трейсбеке целиком, а трейсбек отказа фоновой
        # задачи уходит в лог контура. Проверено тестом.
        raise RuntimeError(f"Внешняя модель ответила отказом: HTTP {status}") from None
    except httpx.HTTPError as failure:
        # Сюда попадает всё остальное транспортное: не разрешилось имя, не
        # установилось соединение, оборвалось на середине. Наружу — род
        # отказа без адреса; в лог — имя класса, по нему причина ищется.
        logger.warning(
            "не удалось обратиться к внешней модели: %s", type(failure).__name__
        )
        raise RuntimeError("Не удалось обратиться к внешней модели") from None

    try:
        payload = response.json()
    except ValueError:
        # Балансировщики и прокси отвечают HTML-страницей с кодом 200 чаще,
        # чем кажется.
        raise RuntimeError("Ответ внешней модели не разобрать как JSON") from None
    return _answer_in(payload, "Ответ внешней модели")


def _answer_in(payload: object, source: str) -> str:
    """Достаёт ответ, проверяя форму.

    Без проверки `str(payload["answer"])` молча превращает вложенный объект
    в строку «{'text': 'четыре'}» и отдаёт её человеку КАК ОТВЕТ МОДЕЛИ, а
    отсутствие поля роняет KeyError, который доезжает до экрана задач
    текстом «'answer'» — по нему не понять ни кто виноват, ни что делать.

    Сам ответ в текст отказа не попадает: он бывает длиной в страницу и
    содержит эхо запроса.
    """
    answer = payload.get(ANSWER_FIELD) if isinstance(payload, dict) else None
    if not isinstance(answer, str):
        raise RuntimeError(f"{source}: нет строкового поля «{ANSWER_FIELD}»")
    return answer
