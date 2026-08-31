import pytest

from app.core.rate_limit import (
    BY_ADDRESS,
    BY_LOGIN,
    MAX_KEYS,
    Limit,
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
    def test_map_is_bounded(self, clock):
        # Без потолка карта растёт неограниченно: каждый выдуманный логин
        # остаётся в памяти навсегда.
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for i in range(MAX_KEYS + 500):
            limiter.register_failure(f"логин{i}")
        assert limiter.size() == MAX_KEYS

    def test_recent_keys_survive_eviction(self, clock):
        # Вытесняются самые давние, а не случайные: иначе защита снималась
        # бы ровно с того, кого сейчас перебирают.
        limiter = RateLimiter(BY_LOGIN, now=clock)
        limiter.register_failure("первый")
        for i in range(MAX_KEYS + 100):
            limiter.register_failure(f"логин{i}")
        limiter.register_failure("последний")
        assert limiter.retry_after("последний") == 0
        assert limiter.size() == MAX_KEYS


class TestKeyNormalization:
    def test_case_and_spaces_share_one_bucket(self, clock):
        # Без приведения `admin`, `Admin` и `admin ` — три разные корзины, и
        # пятибуквенный логин даёт 32 корзины только за счёт регистра, то
        # есть 160 попыток вместо пяти.
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for key in ("admin", "Admin", "ADMIN", " admin", "admin "):
            limiter.register_failure(key)
        assert limiter.retry_after("admin") > 0
        assert limiter.size() == 1

    def test_reset_uses_same_normalization(self, clock):
        limiter = RateLimiter(BY_LOGIN, now=clock)
        for _ in range(BY_LOGIN.max_attempts):
            limiter.register_failure("Admin")
        limiter.reset("admin")
        assert limiter.retry_after("ADMIN") == 0


def test_lock_longer_than_window_is_rejected():
    # Такая настройка молча не работает: отметки выбрасываются по окну, и
    # блокировка снимается вместе с ними. Ручка, крутящаяся только вниз,
    # хуже отсутствующей.
    with pytest.raises(ValueError):
        Limit(max_attempts=5, window_seconds=60, lock_seconds=120)
