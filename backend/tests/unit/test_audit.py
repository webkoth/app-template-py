from app.core.audit import DETAIL_MAX, write_audit


class Recorder:
    """Подставная сессия: write_audit только кладёт объект, больше ничего.

    Настоящая сессия здесь не нужна и мешала бы: проверяется правило, а не
    работа базы.
    """

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


def record(detail: str) -> str:
    recorder = Recorder()
    write_audit(recorder, "boss", "create", "Expense", "id-1", detail)  # type: ignore[arg-type]
    return recorder.added[0].detail  # type: ignore[attr-defined]


def test_short_detail_kept_as_is():
    assert record("Софт, 12000 коп.") == "Софт, 12000 коп."


def test_detail_at_limit_kept_whole():
    assert record("x" * DETAIL_MAX) == "x" * DETAIL_MAX


def test_longer_detail_truncated_and_marked():
    result = record("x" * (DETAIL_MAX + 1))
    assert len(result) == DETAIL_MAX
    assert result.endswith("…")


def test_truncation_counts_characters_not_bytes():
    # VARCHAR(1024) в PostgreSQL считает символы: 1024 кириллических знака
    # занимают 2048 байт и укладываются. Проверено на живой базе.
    result = record("я" * 5000)
    assert len(result) == DETAIL_MAX
