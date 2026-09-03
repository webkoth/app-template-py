import io
import json

import pandas as pd
import pytest

from app.domain import tables
from app.domain.tables import MAX_ROWS, TableError, read_table, summarise


def test_csv_is_read_with_its_columns():
    frame = read_table("имя,цена\nа,1\nб,2\n".encode(), "csv")
    assert list(frame.columns) == ["имя", "цена"]
    assert len(frame) == 2


def test_windows_encoding_is_read_too():
    # Таблицы из Excel в России приезжают в cp1251 чаще, чем хотелось бы.
    # Отказ «не UTF-8» человек читает как «файл битый» и идёт искать
    # несуществующую проблему в своей выгрузке.
    #
    # Эта проверка — вторая половина решения, принятого в задаче 2:
    # `storage.detect_kind` о кодировке НЕ судит именно для того, чтобы такой
    # файл сюда доехал. Убрав поддержку cp1251 здесь, вернёшь отказ, только
    # уже фоновой задачей — то есть человеку, который увидит его не сразу.
    frame = read_table("имя,цена\nа,1\n".encode("cp1251"), "csv")
    assert list(frame.columns) == ["имя", "цена"]


def test_xlsx_is_read():
    buffer = io.BytesIO()
    pd.DataFrame({"имя": ["а"], "цена": [1]}).to_excel(buffer, index=False)
    frame = read_table(buffer.getvalue(), "xlsx")
    assert list(frame.columns) == ["имя", "цена"]


def test_empty_table_is_refused_with_a_reason():
    with pytest.raises(TableError) as denial:
        read_table(b"", "csv")
    assert "пуст" in str(denial.value).lower()


def test_empty_xlsx_is_refused_with_the_same_reason():
    # Отдельная проверка ровно на пустоту, а не на CSV: у CSV пустые байты
    # ловит ещё и pandas (EmptyDataError), поэтому на нём один охранник
    # прикрывает другого и снятие раннего отказа остаётся незамеченным. У
    # XLSX прикрывать нечем — без раннего отказа человек получает
    # «Не удалось прочитать XLSX: File is not a zip file» вместо «Файл пуст».
    with pytest.raises(TableError) as denial:
        read_table(b"", "xlsx")
    assert "пуст" in str(denial.value).lower()


def test_file_without_columns_is_refused_in_russian():
    # Файл из одного перевода строки (или из пробелов, или из одного BOM —
    # так выглядит «сохранил пустой лист»). Байты есть, колонок нет.
    # Без перехвата EmptyDataError человек читает внутреннее сообщение
    # pandas «No columns to parse from file» — по-английски и не про его файл.
    with pytest.raises(TableError) as denial:
        read_table(b"\n", "csv")
    assert "пуст" in str(denial.value).lower()


def test_table_with_only_a_header_is_refused():
    # Заголовок есть, строк нет. Это не пустой файл, и отказ здесь свой:
    # без него такая таблица уезжает в разбор, доходит до конца и человек
    # видит «готово» на нуле строк — то есть считает работу сделанной.
    with pytest.raises(TableError) as denial:
        read_table("имя,цена\n".encode(), "csv")
    assert "нет строк" in str(denial.value)


def test_too_many_rows_is_refused_before_the_work():
    # Потолок про память: разбор держит таблицу целиком, а строки едут в
    # базу по одной. Молчаливый отказ здесь означал бы воркер, съевший
    # память контура и утянувший за собой приложение.
    body = "a\n" + "1\n" * (MAX_ROWS + 1)
    with pytest.raises(TableError) as denial:
        read_table(body.encode(), "csv")
    assert str(MAX_ROWS) in str(denial.value)


def test_rows_beyond_the_ceiling_are_not_even_read():
    # «Before the work» из теста выше — не про то, что отказ случается до
    # записи в базу, а про то, что лишние строки не читаются ВООБЩЕ. Иначе
    # потолок памяти сам её и съедает: замерено на узком CSV в 15 МиБ —
    # 122 МиБ пика при полном чтении против 2 МиБ при чтении с потолком, а
    # предел загрузки 32 МиБ.
    #
    # Доказывается сломанной строкой сразу за потолком: прочитанная, она
    # роняет разбор pandas, и человек вместо внятного «строк больше 50000»
    # получает «Не удалось прочитать CSV: Error tokenizing data».
    body = "a\n" + "1\n" * (MAX_ROWS + 1) + "1,2,3\n"
    with pytest.raises(TableError) as denial:
        read_table(body.encode(), "csv")
    assert str(MAX_ROWS) in str(denial.value)


def test_xlsx_is_not_read_past_the_ceiling_either(monkeypatch):
    # xlsx — это сжатый zip: под тем же пределом загрузки в 32 МиБ строк в
    # него влезает больше, чем в CSV, поэтому не читать лишнее здесь важнее,
    # а не наоборот. Проверяется на заниженном пределе: настоящий (50 001
    # строка) потребовал бы файла, который сам собирается секундами на каждом
    # прогоне — плата за ту же самую проверку.
    buffer = io.BytesIO()
    pd.DataFrame({"цена": [1, 2, 3, 4, 5]}).to_excel(buffer, index=False)
    monkeypatch.setattr(tables, "_READ_LIMIT", 2)
    assert len(tables.read_table(buffer.getvalue(), "xlsx")) == 2


def test_summary_counts_rows_and_describes_columns():
    frame = pd.DataFrame({"цена": [1, 2, 3], "город": ["а", "б", "а"]})
    summary = summarise(frame)
    assert summary["строк"] == 3
    columns = {c["имя"]: c for c in summary["колонки"]}
    assert columns["цена"]["вид"] == "число"
    assert columns["цена"]["среднее"] == 2
    assert columns["город"]["вид"] == "текст"
    assert columns["город"]["различных"] == 2


def test_summary_survives_an_empty_column():
    # Колонка из одних пропусков — обычное дело в выгрузках. Среднее по ней
    # не считается, и сводка обязана это пережить, а не упасть на NaN.
    frame = pd.DataFrame({"пусто": [None, None]})
    summary = summarise(frame)
    assert summary["колонки"][0]["вид"] == "пусто"


def test_summary_is_json_safe():
    # Сводка уезжает в JSONB. numpy.int64 сериализатор json не берёт вовсе:
    # без приведения запись падает на записи результата, то есть после
    # всего счёта.
    #
    # Колонка целая намеренно. На float-колонке эта проверка зелена и БЕЗ
    # приведения типов: numpy.float64 — наследник питоновского float, и json
    # его берёт сам. То есть проверка на дробных числах не проверяет ничего.
    json.dumps(summarise(pd.DataFrame({"цена": [1, 2, 3]})), allow_nan=False)
    json.dumps(summarise(pd.DataFrame({"цена": [1, 2, None]})), allow_nan=False)


# Среднее по колонке с +inf и -inf numpy считает с руганью в stderr. Ругань
# по делу, но здесь она ожидаемая часть проверки, и в сводке прогона ей не
# место: предупреждения, которые всегда горят, перестают читать.
@pytest.mark.filterwarnings("ignore:invalid value encountered:RuntimeWarning")
def test_endless_number_does_not_reach_the_summary():
    # 1e400 в double не влезает и становится inf — так приезжает
    # переполнение из чужой выгрузки. min и max тогда бесконечны, среднее —
    # NaN, а в JSON таких литералов нет вовсе: json.dumps печатает Infinity
    # и NaN молча, и отказывает уже PostgreSQL — на СОХРАНЕНИИ результата,
    # когда счёт сделан и потерян. Поэтому allow_nan=False: ровно та
    # строгость, что у JSONB.
    frame = read_table(b"x\n1\n1e400\n-1e400\n", "csv")
    summary = summarise(frame)
    assert summary["колонки"][0]["максимум"] is None
    assert summary["колонки"][0]["среднее"] is None
    json.dumps(summary, allow_nan=False)
