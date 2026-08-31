from app.domain.money import MAX_AMOUNT_MINOR, format_money, parse_money_to_minor


class TestParse:
    def test_plain_integer(self):
        assert parse_money_to_minor("100") == 10000

    def test_comma_separator(self):
        assert parse_money_to_minor("12,34") == 1234

    def test_dot_separator(self):
        assert parse_money_to_minor("12.34") == 1234

    def test_spaces_are_thousand_separators(self):
        assert parse_money_to_minor("1 234.50") == 123450

    def test_nbsp_is_also_a_separator(self):
        # Значение, скопированное из интерфейса, приезжает с неразрывным
        # пробелом. Без этой строки человек копирует показанное ему же число
        # и получает «сумма не похожа на число».
        assert parse_money_to_minor("1\xa0234,50") == 123450

    def test_three_decimals_rejected(self):
        # В копейках два знака. Третий означает, что человек ошибся, а не что
        # надо округлить: молча округлив, мы запишем не ту сумму.
        assert parse_money_to_minor("1.234") is None

    def test_garbage_rejected(self):
        assert parse_money_to_minor("сто рублей") is None

    def test_empty_rejected(self):
        assert parse_money_to_minor("") is None
        assert parse_money_to_minor("   ") is None

    def test_negative_parsed(self):
        # Разбор отрицательное пропускает; запрещает его правило в сервисе,
        # потому что «расход не может быть отрицательным» — правило предметной
        # области, а не свойство записи числа.
        assert parse_money_to_minor("-5,00") == -500

    def test_no_float_drift(self):
        # 0.1 + 0.2 в float даёт 0.30000000000000004. Через Decimal — ровно 30.
        assert parse_money_to_minor("839,29") == 83929
        assert parse_money_to_minor("0,29") == 29


class TestFormat:
    @staticmethod
    def fmt(minor: int) -> str:
        # Разделитель разрядов — неразрывный пробел: иначе сумма переносится
        # по строке пополам. В тесте сравниваем с обычным для читаемости.
        return format_money(minor).replace("\xa0", " ")

    def test_basic(self):
        assert self.fmt(123456) == "1 234,56 ₽"

    def test_kopecks_padded(self):
        assert self.fmt(5) == "0,05 ₽"

    def test_zero(self):
        assert self.fmt(0) == "0,00 ₽"

    def test_negative(self):
        assert self.fmt(-500) == "-5,00 ₽"

    def test_limit(self):
        assert self.fmt(MAX_AMOUNT_MINOR) == "21 474 836,47 ₽"


def test_limit_is_int4_max():
    # Не выдуманное число: amount_minor хранится как Integer, а это int4 в
    # PostgreSQL. Без проверки по этой границе сумма пройдёт разбор и упадёт
    # в базе ошибкой драйвера, которую специалисту читать нечем.
    assert MAX_AMOUNT_MINOR == 2_147_483_647
