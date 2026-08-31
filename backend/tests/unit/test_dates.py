from datetime import UTC, datetime

from app.domain.dates import MSK, format_date, format_date_time, parse_date_input_value


class TestParse:
    def test_valid_date(self):
        d = parse_date_input_value("2026-08-31")
        assert d is not None
        assert (d.year, d.month, d.day) == (2026, 8, 31)
        assert d.utcoffset().total_seconds() == 3 * 3600

    def test_impossible_date_rejected(self):
        # 31 февраля проходит проверку формата, но такой даты нет. В JS
        # движок молча переносит её на 3 марта; здесь получаем None.
        assert parse_date_input_value("2026-02-31") is None

    def test_leap_day_valid_in_leap_year(self):
        assert parse_date_input_value("2028-02-29") is not None

    def test_leap_day_invalid_in_common_year(self):
        assert parse_date_input_value("2026-02-29") is None

    def test_wrong_format_rejected(self):
        assert parse_date_input_value("31.08.2026") is None
        assert parse_date_input_value("") is None
        assert parse_date_input_value("вчера") is None
        assert parse_date_input_value("2026-13-01") is None

    def test_basic_iso_format_rejected(self):
        # date.fromisoformat принял бы: с 3.11 он понимает запись без
        # дефисов. Контракт обещает YYYY-MM-DD, шире принимать незачем.
        assert parse_date_input_value("20260831") is None

    def test_iso_week_date_rejected(self):
        # Самый неприятный случай: date.fromisoformat разбирает это в
        # 29 декабря 2025 года — дату другого года.
        assert parse_date_input_value("2026-W01-1") is None

    def test_midnight_moscow_not_utc(self):
        # Начало суток берётся в московской зоне. Взяв полночь UTC, мы бы
        # записали 03:00 по Москве, и запись за 31-е числа попадала бы в
        # выборку за 1-е при фильтре по дате.
        d = parse_date_input_value("2026-08-31")
        assert d.astimezone(UTC).hour == 21
        assert d.astimezone(UTC).day == 30


class TestFormat:
    def test_date(self):
        assert format_date(datetime(2026, 8, 31, 12, 0, tzinfo=MSK)) == "31.08.2026"

    def test_datetime(self):
        v = datetime(2026, 8, 31, 14, 5, tzinfo=MSK)
        assert format_date_time(v) == "31.08.2026 14:05"

    def test_utc_value_shown_in_moscow(self):
        # Из базы значения приходят в UTC. Показывать их надо по Москве.
        v = datetime(2026, 8, 31, 21, 30, tzinfo=UTC)
        assert format_date_time(v) == "01.09.2026 00:30"
