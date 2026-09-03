import uuid

import pytest

from app.core import storage
from app.core.errors import RuleViolation


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.settings, "upload_dir", tmp_path)
    return tmp_path


def test_saved_file_is_found_by_its_identifier(_dir):
    file_id = storage.save(b"a,b\n1,2\n")
    assert storage.read(file_id) == b"a,b\n1,2\n"


def test_stored_name_is_an_identifier_not_the_original(_dir):
    # Имя с диска берётся из идентификатора, а не из загруженного. Иначе
    # файл, названный «../../.env», становится путём — и запись уходит мимо
    # каталога загрузок, а чтение отдаёт чужое.
    file_id = storage.save(b"x")
    names = [p.name for p in _dir.iterdir()]
    assert names == [str(file_id)]


def test_reading_an_unknown_identifier_is_not_found(_dir):
    from app.core.errors import RecordNotFound

    with pytest.raises(RecordNotFound):
        storage.read(uuid.uuid7())


@pytest.mark.parametrize(
    ("limit", "expected"),
    [
        (32 * 1024 * 1024, "32 МиБ"),
        (1024 * 1024, "1 МиБ"),
        # Предел меньше мегабайта — не выдумка: на контуре его задают под
        # client_max_body_size в nginx, где умолчание ровно 1 МиБ. Целое
        # деление на мегабайты давало здесь «0 МиБ» — предел, который
        # невозможно соблюсти.
        (1_000_000, "977 КиБ"),
        (1_500_000, "1.4 МиБ"),
    ],
)
def test_the_limit_is_named_in_units_a_human_reads(_dir, limit, expected):
    assert storage.human_size(limit) == expected


def test_a_sub_megabyte_limit_does_not_refuse_by_zero(_dir, monkeypatch):
    # Отказ «Файл больше предельного (0 МиБ)» человек читает как поломку:
    # ноль соблюсти нельзя. Проверяется целиком текст, а не функция.
    monkeypatch.setattr(storage.settings, "upload_max_bytes", 1_000_000)
    with pytest.raises(RuleViolation) as denial:
        storage.check_size(declared=2_000_000)
    assert "0 МиБ" not in denial.value.message
    assert "977 КиБ" in denial.value.message


def test_too_large_is_refused_by_the_declared_size(_dir, monkeypatch):
    # Отказ до чтения целиком: смысл потолка в том, чтобы не держать в
    # памяти то, что и не собирались принимать.
    monkeypatch.setattr(storage.settings, "upload_max_bytes", 10)
    with pytest.raises(RuleViolation) as denial:
        storage.check_size(declared=11)
    assert "больше" in denial.value.message


def test_too_large_is_refused_even_when_size_is_not_declared(_dir, monkeypatch):
    # Content-Length клиент может не прислать или соврать. Проверка по факту
    # прочитанного обязана быть второй линией, иначе потолок обходится одним
    # отсутствующим заголовком.
    monkeypatch.setattr(storage.settings, "upload_max_bytes", 10)
    with pytest.raises(RuleViolation):
        storage.save(b"x" * 11)


def test_unknown_content_is_refused(_dir):
    # Тип по содержимому, а не по расширению: «отчёт.csv» с телом PDF
    # доходит до pandas и падает там невнятно.
    with pytest.raises(RuleViolation) as denial:
        storage.detect_kind(b"%PDF-1.7\n%\xe2\xe3")
    assert denial.value.field == "file"


def test_csv_and_xlsx_are_recognised_by_content(_dir):
    assert storage.detect_kind(b"a,b\n1,2\n") == "csv"
    # Первые байты xlsx — сигнатура zip: это и есть zip с xml внутри.
    assert storage.detect_kind(b"PK\x03\x04" + b"\x00" * 20) == "xlsx"


def test_delete_is_silent_when_the_file_is_already_gone(_dir):
    # Удаление вызывается при откате загрузки, и файла к тому моменту может
    # не быть. Падать здесь значит превращать уборку в новую ошибку.
    storage.delete(uuid.uuid7())


def test_a_windows_encoded_table_is_accepted(_dir):
    # Загрузка НЕ судит о кодировке. Excel по умолчанию выгружает CSV в
    # cp1251, и правило «голова обязана декодироваться как utf-8»
    # отвергало бы такой файл словами «Не CSV и не XLSX». При этом
    # `domain/tables.py` cp1251 читает намеренно, и на это есть отдельный
    # тест: два слоя противоречили бы друг другу, а человек читал бы отказ
    # в файле, который система умеет разбирать.
    assert storage.detect_kind("Дата,Сумма\nа,1\n".encode("cp1251")) == "csv"


def test_a_head_cut_mid_character_is_still_a_table(_dir):
    # Голова режется по байтам, и многобайтная буква на границе среза
    # приезжает сюда половиной. Отдельная проверка, потому что решается это
    # не тем же, чем cp1251: даже правило «utf-8 или cp1251» роняло бы
    # обрезанный символ, а файл при этом совершенно нормальный.
    assert storage.detect_kind("Дата,Сумма".encode()[:5]) == "csv"


def test_binary_without_a_known_signature_is_refused_by_its_nul_bytes(_dir):
    # Список сигнатур закрыт и коротким останется. Вторая половина правила —
    # нулевой байт, которого в тексте не бывает ни в одной кодировке: она и
    # ловит форматы, которых в списке нет. Нуль поставлен ДАЛЬШЕ восьмого
    # байта намеренно — по короткой голове такой файл прошёл бы как CSV.
    body = b"WHATEVER" + b"\x00\x01\x02" * 100
    with pytest.raises(RuleViolation) as denial:
        storage.detect_kind(body)
    assert denial.value.field == "file"


def test_binary_is_refused_on_save_even_when_it_starts_like_text(_dir):
    # Тело, начинающееся как таблица и продолжающееся двоичным мусором.
    # Проверка ровно про то, СКОЛЬКО байт смотрит сохранение: при короткой
    # голове такой файл проходит, ложится на диск и падает потом в разборе —
    # уже фоновой задачей, где отказ увидит не тот, кто его загрузил.
    # Мутация `_HEAD_BYTES = 8` без этого теста не роняла ничего.
    body = "город,цена\n".encode() + b"\x00\x01\x02" * 100
    with pytest.raises(RuleViolation):
        storage.save(body)


def test_unknown_content_is_refused_on_save_too(_dir):
    # Отдельно от проверки самой detect_kind: сохранение обязано звать её на
    # деле. В первой редакции оно звало её на восьми байтах, и охранник по
    # содержимому на пути сохранения не срабатывал вовсе — а тест выше был
    # зелёным, потому что зовёт detect_kind напрямую с полной головой.
    with pytest.raises(RuleViolation):
        storage.save(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n")
