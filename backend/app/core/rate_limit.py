"""Ограничение попыток входа.

Единственная защита от подбора пароля — и единственное место, откуда можно
запереть законного пользователя. Ошибка в любую сторону дорога.

ИЗВЕСТНЫЙ ДОЛГ: счётчики живут в памяти процесса, перезапуск их обнуляет.
Пока воркер один — это и есть счётчик контура.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import islice


@dataclass(frozen=True, slots=True)
class Limit:
    max_attempts: int
    window_seconds: float
    lock_seconds: float

    def __post_init__(self) -> None:
        # Блокировка длиннее окна — мёртвая настройка: отметки старше окна
        # выбрасываются, и блокировка снимается вместе с ними, сколько бы ни
        # было указано. Ручка, которая молча крутится только вниз, хуже
        # отсутствующей: её выставят и будут считать, что она работает.
        if self.lock_seconds > self.window_seconds:
            raise ValueError(
                "lock_seconds не может превышать window_seconds: "
                "отметки выбрасываются по окну, и блокировка снимается с ними"
            )


BY_LOGIN = Limit(max_attempts=5, window_seconds=15 * 60, lock_seconds=15 * 60)
BY_ADDRESS = Limit(max_attempts=30, window_seconds=15 * 60, lock_seconds=15 * 60)

# Потолок числа ключей. При 148 байтах на ключ это около 14 МиБ — цена,
# которую контур платит за защиту от перебора по выдуманным логинам.
#
# Раньше здесь была полная чистка карты при превышении порога, как в
# app-template-ts. Она оказалась плохим разменом: память и так не была
# проблемой (миллион ключей — 151 МиБ), а чистка проходила по всем ключам на
# каждой неудачной попытке, потому что под живым перебором все ключи свежие
# и выбрасывать нечего. Замерено: налить 20 000 ключей — 13,7 с процессора
# против 0,01 с, один вызов потом — 1954 мкс против 0,3 мкс. То есть защита
# от перебора превращалась в усилитель нагрузки: атакующий тратил один
# запрос, сервер — миллисекунды счёта.
MAX_KEYS = 100_000


class RateLimiter:
    """Скользящее окно неудачных попыток по ключу.

    Ключ — либо логин, либо адрес. Оба ограничиваются отдельно: по логину,
    чтобы не подбирали пароль к конкретной учётной записи, по адресу — чтобы
    не перебирали логины с одной машины.
    """

    def __init__(self, limit: Limit, now: Callable[[], float] = time.monotonic) -> None:
        # Часы обязаны быть монотонными. При time.time скачок часов назад
        # растягивает блокировку: отметка из «будущего» не выпадает из окна,
        # и человек оказывается заперт на разницу хода.
        self._limit = limit
        self._now = now
        self._hits: dict[str, list[float]] = {}

    @staticmethod
    def _normalize(key: str) -> str:
        """Приводит ключ к одной форме.

        Без этого `admin`, `Admin` и `admin ` — три разные корзины, и
        пятибуквенный логин даёт 32 корзины только за счёт регистра, то есть
        160 попыток вместо пяти. Приведение строго сужает бюджет, новых
        путей для запирания чужой учётной записи не открывает: запереть
        `admin`, ошибаясь в `ADMIN`, ровно так же можно было, ошибаясь в
        самом `admin`.
        """
        return key.strip().casefold()

    def _fresh(self, key: str, now: float) -> list[float]:
        kept = [
            t for t in self._hits.get(key, ()) if now - t < self._limit.window_seconds
        ]
        if kept:
            self._hits[key] = kept
        else:
            self._hits.pop(key, None)
        return kept

    def _locked_until(self, marks: list[float]) -> float:
        if len(marks) < self._limit.max_attempts:
            return 0.0
        return marks[len(marks) - self._limit.max_attempts] + self._limit.lock_seconds

    def _evict_overflow(self) -> None:
        excess = len(self._hits) - MAX_KEYS
        if excess <= 0:
            return
        # Словарь хранит порядок вставки, поэтому первые ключи — самые
        # давние. Вытесняются они, а не случайные: у давнего ключа больше
        # шансов оказаться протухшим.
        #
        # islice, а не срез списка. `list(self._hits)[:excess]`
        # материализует весь словарь, чтобы взять из него один ключ, и под
        # перебором карта стоит ровно на потолке — то есть платится это на
        # каждой неудачной попытке. Замерено: 451 мкс против 1,3 мкс при
        # полной карте. Это тот же дефект, ради которого убрали полную
        # чистку, только слабее — и потому его легко не заметить.
        # Обёртка list обязательна: удаление во время обхода словаря
        # бросает RuntimeError.
        for stale in list(islice(self._hits, excess)):
            del self._hits[stale]

    def retry_after(self, key: str) -> float:
        """Сколько секунд ещё ждать. 0 — попытка допустима."""
        now = self._now()
        until = self._locked_until(self._fresh(self._normalize(key), now))
        return until - now if until > now else 0.0

    def register_failure(self, key: str) -> None:
        now = self._now()
        normalized = self._normalize(key)
        marks = self._fresh(normalized, now)
        # Попытка во время блокировки не записывается: иначе бот продлевает
        # её бесконечно и защита превращается в отказ в обслуживании против
        # того, кого защищает.
        if self._locked_until(marks) > now:
            return
        marks.append(now)
        self._hits[normalized] = marks
        self._evict_overflow()

    def reset(self, key: str) -> None:
        self._hits.pop(self._normalize(key), None)

    def size(self) -> int:
        return len(self._hits)


login_limiter = RateLimiter(BY_LOGIN)
address_limiter = RateLimiter(BY_ADDRESS)
