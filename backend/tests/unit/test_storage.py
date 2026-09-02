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


def test_a_head_cut_mid_character_is_still_a_table(_dir):
    # Голова режется по байтам, и многобайтная буква на границе среза
    # приезжает сюда половиной. Это не «не CSV», а обрезанный символ: иначе
    # выгрузка с русским текстом отказывается сообщением «Не CSV и не XLSX»
    # ровно тогда, когда граница попала внутрь буквы, — то есть через раз, и
    # причину человек ищет в своей таблице.
    assert storage.detect_kind("Дата,Сумма".encode()[:5]) == "csv"


def test_unknown_content_is_refused_on_save_too(_dir):
    # Первые байты PDF — «%PDF-1.7», обычный ASCII: по слишком короткой
    # голове тело PDF неотличимо от CSV, и охранник по содержимому на самом
    # пути сохранения не срабатывает вовсе. Двоичный мусор идёт дальше, в
    # первой же строке файла.
    with pytest.raises(RuleViolation):
        storage.save(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n")
