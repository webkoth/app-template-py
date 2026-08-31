"""Ограничение попыток входа — единственная защита от подбора пароля.

Устройство взято из app-template-ts не ради единообразия, а потому что там
оно уже пережило три ошибки, каждая из которых превращала защиту в отказ в
обслуживании. Три решения здесь не косметические, и каждое проверено
воспроизведением дефекта на упрощённой версии.

Известный долг остаётся: счётчики живут в памяти процесса, перезапуск их
обнуляет. Пока воркер один — это и есть счётчик контура.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Limit:
    max_attempts: int
    window_seconds: float
    lock_seconds: float


# Два разных порога. По логину строго (5), по адресу мягко (30). За одним
# адресом стоит офис или VPN: при общем пороге пять человек, каждый по разу
# опечатавшийся, оставляют без входа шестого. Воспроизведено.
BY_LOGIN = Limit(max_attempts=5, window_seconds=15 * 60, lock_seconds=15 * 60)
BY_ADDRESS = Limit(max_attempts=30, window_seconds=15 * 60, lock_seconds=15 * 60)
SWEEP_AT = 10_000


class RateLimiter:
    def __init__(self, limit: Limit, now: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._now = now
        self._hits: dict[str, list[float]] = {}

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

    def _sweep(self, now: float) -> None:
        # Чистка при SWEEP_AT ключей. Без неё карта растёт неограниченно:
        # каждый выдуманный логин остаётся в памяти навсегда. Проверено —
        # 50 000 разных логинов дают 50 000 записей, ни одна не
        # освобождается. Чистка выбрасывает только протухшее, поэтому не
        # снимает защиту под массовым перебором.
        if len(self._hits) <= SWEEP_AT:
            return
        for key in list(self._hits):
            self._fresh(key, now)

    def retry_after(self, key: str) -> float:
        now = self._now()
        until = self._locked_until(self._fresh(key, now))
        return until - now if until > now else 0.0

    def register_failure(self, key: str) -> None:
        now = self._now()
        marks = self._fresh(key, now)
        # Неудача во время блокировки не записывается. Иначе бот, стучащий
        # раз в минуту, держит человека запертым бесконечно — скользящее
        # окно никогда не пустеет, и защита от подбора превращается в отказ
        # в обслуживании против того, кого защищает. С этой строкой
        # блокировка истекает через 15 минут независимо от бота.
        if self._locked_until(marks) > now:
            return
        marks.append(now)
        self._hits[key] = marks
        self._sweep(now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def size(self) -> int:
        return len(self._hits)
