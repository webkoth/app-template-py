import pytest

from app.domain.expenses import CATEGORIES, CategoryTotal, totals_by_category


def test_categories_are_fixed():
    assert CATEGORIES == ("Аренда", "Софт", "Оборудование", "Услуги", "Прочее")


class TestTotals:
    def test_empty_input(self):
        assert totals_by_category([]) == []

    def test_single_row(self):
        assert totals_by_category([("Софт", 10000)]) == [
            CategoryTotal(category="Софт", total_minor=10000, share=1.0)
        ]

    def test_sums_within_category(self):
        result = totals_by_category([("Софт", 10000), ("Софт", 5000)])
        assert result == [CategoryTotal(category="Софт", total_minor=15000, share=1.0)]

    def test_sorted_by_total_descending(self):
        result = totals_by_category(
            [("Софт", 10000), ("Аренда", 50000), ("Прочее", 2000)]
        )
        assert [r.category for r in result] == ["Аренда", "Софт", "Прочее"]

    def test_equal_totals_ordered_by_name(self):
        # Порядок обязан зависеть только от данных, а не от того, в каком
        # порядке база вернула строки.
        first = totals_by_category([("Софт", 500), ("Аренда", 500), ("Услуги", 500)])
        second = totals_by_category([("Услуги", 500), ("Софт", 500), ("Аренда", 500)])
        assert [r.category for r in first] == ["Аренда", "Софт", "Услуги"]
        assert [r.category for r in first] == [r.category for r in second]

    def test_share_computed(self):
        result = totals_by_category([("Аренда", 75000), ("Софт", 25000)])
        assert result[0].share == 0.75
        assert result[1].share == 0.25

    def test_zero_total_gives_zero_shares(self):
        # Деление на ноль: все суммы могут оказаться нулевыми. Без этой
        # ветки экран сводки падал бы на пустяке.
        #
        # Сравнение со всем списком, а не `all(r.share == 0 for r in ...)`:
        # такая проверка истинна и на пустом списке, поэтому не заметила бы
        # реализацию, которая при нулевом итоге просто возвращает ничего.
        # Проверено мутацией — не заметила.
        assert totals_by_category([("Софт", 0), ("Аренда", 0)]) == [
            CategoryTotal(category="Аренда", total_minor=0, share=0.0),
            CategoryTotal(category="Софт", total_minor=0, share=0.0),
        ]

    def test_negative_amount_rejected(self):
        # Доля от знакопеременного набора перестаёт быть долей: при суммах
        # −5000 и 10000 получаются доли −100 % и 200 %. Коварство в том, что
        # сумма долей при этом остаётся ровно единицей, и проверка «доли
        # сходятся» такую картину пропускает, а круговая диаграмма рисует
        # сектор в 3600 градусов.
        with pytest.raises(ValueError):
            totals_by_category([("Софт", -5000), ("Аренда", 10000)])
