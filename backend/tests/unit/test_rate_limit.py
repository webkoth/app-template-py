import pytest

from app.core.rate_limit import (
    BY_ADDRESS,
    BY_LOGIN,
    SWEEP_AT,
    RateLimiter,
)


@pytest.fixture
def clock():
    class Clock:
        now = 1000.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    return Clock()


def test_thresholds_differ_for_login_and_address():
    # Порог по адресу выше намеренно: за одним адресом стоит офис или VPN, и
    # общий порог означал бы «один человек трижды опечатался — все за этим
    # адресом остались без входа».
    assert BY_LOGIN.max_attempts == 5
    assert BY_ADDRESS.max_attempts == 30


class TestLock:
    def test_allows_until_limit(self, clock):
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for _ in range(BY_LOGIN.max_attempts - 1):
            limiter.register_failure("admin")
            assert limiter.retry_after("admin") == 0
        limiter.register_failure("admin")
        assert limiter.retry_after("admin") > 0

    def test_lock_expires(self, clock):
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for _ in range(BY_LOGIN.max_attempts):
            limiter.register_failure("admin")
        clock.advance(BY_LOGIN.lock_seconds + 1)
        assert limiter.retry_after("admin") == 0

    def test_bot_cannot_extend_lock_forever(self, clock):
        # Главное свойство. Неудача во время блокировки не записывается,
        # иначе бот, стучащий раз в минуту, держит человека запертым
        # бесконечно, и защита превращается в отказ в обслуживании.
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for _ in range(BY_LOGIN.max_attempts):
            limiter.register_failure("жертва")
        for _ in range(int(BY_LOGIN.lock_seconds // 60) + 1):
            clock.advance(60)
            limiter.register_failure("жертва")
        assert limiter.retry_after("жертва") == 0

    def test_retry_after_counts_down(self, clock):
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for _ in range(BY_LOGIN.max_attempts):
            limiter.register_failure("admin")
        first = limiter.retry_after("admin")
        clock.advance(60)
        assert limiter.retry_after("admin") == pytest.approx(first - 60)

    def test_keys_are_independent(self, clock):
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for _ in range(BY_LOGIN.max_attempts):
            limiter.register_failure("admin")
        assert limiter.retry_after("admin") > 0
        assert limiter.retry_after("ivan") == 0

    def test_success_clears_counter(self, clock):
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for _ in range(BY_LOGIN.max_attempts):
            limiter.register_failure("admin")
        limiter.reset("admin")
        assert limiter.retry_after("admin") == 0

    def test_old_attempts_drop_out_of_window(self, clock):
        # Скользящее окно, а не корзина с полным сбросом: пять попыток за час
        # не должны запирать, если четыре из них были час назад.
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for _ in range(BY_LOGIN.max_attempts - 1):
            limiter.register_failure("admin")
        clock.advance(BY_LOGIN.window_seconds + 1)
        limiter.register_failure("admin")
        assert limiter.retry_after("admin") == 0


class TestMemory:
    def test_stale_keys_are_swept(self, clock):
        # Без чистки карта растёт неограниченно: каждый выдуманный логин
        # остаётся в памяти навсегда, и миллион попыток с разными логинами
        # исчерпывает её.
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for i in range(SWEEP_AT + 100):
            limiter.register_failure(f"логин{i}")
        clock.advance(BY_LOGIN.window_seconds + 1)
        limiter.register_failure("свежий")
        assert limiter.size() == 1

    def test_fresh_keys_survive_sweep(self, clock):
        # Чистка выбрасывает только протухшее. Иначе она бы снимала защиту
        # ровно тогда, когда та нужнее всего — под массовым перебором.
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for i in range(SWEEP_AT + 100):
            limiter.register_failure(f"логин{i}")
        assert limiter.size() == SWEEP_AT + 100
