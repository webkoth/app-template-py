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
        # Деление на ноль: суммы могут в принципе взаимно погаситься.
        # Без этой ветки экран сводки падал бы на пустяке.
        result = totals_by_category([("Софт", 100), ("Аренда", -100)])
        assert all(r.share == 0.0 for r in result)
