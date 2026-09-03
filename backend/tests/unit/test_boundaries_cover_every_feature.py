"""Контракты границ не должны отставать от состава фич.

`.importlinter` перечисляет модули руками, и это тот же род списка, что уже
однажды подвёл: состав схемы вёлся вручную в двух местах, разошёлся, и
модель очереди выпала из миграций молча. Здесь цена та же — новая фича
выпадает из правила «фичи не лезут друг другу внутрь», прогон остаётся
зелёным, и правило просто перестаёт на неё распространяться. Заметить это
можно только вычитав конфиг глазами.

Поэтому список сверяется с диском: что лежит в `app/features/`, то и обязано
быть в контракте. Забыть строку теперь нельзя — падает эта проверка и
называет недостающее.
"""

import configparser
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
FEATURES = BACKEND / "app" / "features"

INDEPENDENCE = "importlinter:contract:features-are-independent"
THROUGH_SERVICE = "importlinter:contract:router-goes-through-service"
JOBS_WITHOUT_HTTP = "importlinter:contract:jobs-do-not-know-about-http"


def _listed(section: str, key: str) -> set[str]:
    parser = configparser.ConfigParser()
    parser.read(BACKEND / ".importlinter", encoding="utf-8")
    return set(parser[section][key].split())


def _features() -> set[str]:
    return {
        path.name
        for path in FEATURES.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }


def test_every_feature_is_in_the_independence_contract():
    expected = {f"app.features.{name}" for name in _features()}
    assert expected == _listed(INDEPENDENCE, "modules"), (
        "фича есть на диске, но не в контракте независимости — значит правило "
        "«фичи не лезут друг другу внутрь» на неё не распространяется, и "
        "узнать об этом можно только прочитав .importlinter глазами"
    )


def test_every_router_is_watched_for_going_around_its_service():
    expected = {
        f"app.features.{name}.router"
        for name in _features()
        if (FEATURES / name / "router.py").is_file()
    }
    assert expected == _listed(THROUGH_SERVICE, "source_modules"), (
        "роутер есть, а под наблюдением его нет: он может ходить в модели "
        "мимо сервиса, и контракт этого не заметит"
    )


def test_every_feature_handler_is_watched_for_reaching_into_http():
    expected = {
        f"app.features.{name}.jobs"
        for name in _features()
        if (FEATURES / name / "jobs.py").is_file()
    }
    assert expected == _listed(JOBS_WITHOUT_HTTP, "source_modules"), (
        "обработчик фоновых задач есть, а под наблюдением его нет: он может "
        "импортировать роутеры и FastAPI, и контракт этого не заметит. "
        "Фоновая работа, знающая про UploadFile, не зовётся ни из скрипта, "
        "ни из планировщика — а узнать об этом можно только вычитав "
        ".importlinter глазами"
    )


def test_every_feature_model_is_closed_to_routers():
    expected = {
        f"app.features.{name}.models"
        for name in _features()
        if (FEATURES / name / "models.py").is_file()
    }
    forbidden = _listed(THROUGH_SERVICE, "forbidden_modules")
    assert expected <= forbidden, (
        f"модели фичи не закрыты от роутеров: {sorted(expected - forbidden)}. "
        "Запрет перечисляет цели поимённо, поэтому новая таблица остаётся "
        "открытой, пока её сюда не впишут"
    )
