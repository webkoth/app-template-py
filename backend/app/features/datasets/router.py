import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core import storage
from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.datasets import service
from app.features.datasets.schemas import (
    DatasetOut,
    ModelOut,
    PredictRequest,
    TrainRequest,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])

ViewerDep = Depends(require_role(Role.viewer))
EditorDep = Depends(require_role(Role.editor))

# Annotated, а не значение по умолчанию `file: UploadFile = File()`:
# вызов в умолчании ловит ruff (B008), и справедливо — умолчание
# вычисляется один раз при импорте. Здесь же File() — часть ТИПА поля, и
# порядок параметров от него не зависит.
FileDep = Annotated[UploadFile, File()]


@router.get("", response_model=list[DatasetOut])
async def list_datasets(
    session: SessionDep, _: CurrentUser = ViewerDep
) -> list[DatasetOut]:
    datasets = await service.list_datasets(session)
    failures = await service.parse_failures(session, datasets)
    return [
        DatasetOut.model_validate(dataset).model_copy(
            update={"parse_error": failures.get(dataset.id)}
        )
        for dataset in datasets
    ]


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    session: SessionDep,
    file: FileDep,
    actor: CurrentUser = EditorDep,
) -> DatasetOut:
    # Отказ по объявленному размеру — до того, как тело станет байтами в
    # памяти приложения и файлом в каталоге загрузок. Разобрать multipart
    # Starlette к этому моменту уже успел (во временный файл, не в наш
    # каталог), а вот `await file.read()` ниже поднимает всё тело в память
    # разом — и без этой строки за потолок платили бы ровно тем, ради
    # экономии чего он и стоит. Вторая линия — в storage.save, по факту
    # прочитанного: Content-Length клиент может не прислать или соврать.
    storage.check_size(file.size)
    # Дальше тело читается целиком: разбор всё равно держит таблицу в
    # памяти, и потоковая запись на диск экономила бы только на файлах,
    # которые мы и так отказываемся принимать по размеру.
    data = await file.read()
    # Без try: отказы загрузки — это RuleViolation из storage, у него общий
    # обработчик и конверт с полем формы. Разбор таблицы сюда не попадает
    # вовсе: он идёт в фоне, и его отказ человек видит в задаче, а не в
    # ответе на загрузку.
    dataset = await service.create_dataset(
        session, file.filename or "без имени", data, actor.login
    )
    return DatasetOut.model_validate(dataset)


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: uuid.UUID, session: SessionDep, actor: CurrentUser = EditorDep
) -> dict[str, bool]:
    await service.delete_dataset(session, dataset_id, actor.login)
    return {"ok": True}


@router.post("/{dataset_id}/models", status_code=status.HTTP_202_ACCEPTED)
async def start_training(
    dataset_id: uuid.UUID,
    payload: TrainRequest,
    session: SessionDep,
    actor: CurrentUser = EditorDep,
) -> dict[str, str]:
    # 202, а не 201: модели ещё нет, есть поставленная задача. Ответить 201
    # значило бы соврать про то, что уже создано.
    job = await service.start_training(
        session, dataset_id, payload.target_column, actor.login
    )
    return {"job_id": str(job.id)}


@router.get("/{dataset_id}/models", response_model=list[ModelOut])
async def list_models(
    dataset_id: uuid.UUID, session: SessionDep, _: CurrentUser = ViewerDep
) -> list[ModelOut]:
    return [
        ModelOut.model_validate(m)
        for m in await service.list_models(session, dataset_id)
    ]


# Отдельный роутер, а не путь внутри таблицы. Модель принадлежит таблице, но
# предсказание зовут по идентификатору модели, и вкладывать его в путь
# таблицы значило бы требовать от клиента знать оба — а второй он берёт
# ровно из той же записи, что и первый.
models_router = APIRouter(prefix="/models", tags=["datasets"])


@models_router.post("/{model_id}/predict")
async def predict(
    model_id: uuid.UUID,
    payload: PredictRequest,
    session: SessionDep,
    _: CurrentUser = ViewerDep,
) -> dict[str, float]:
    # Предсказание смотрит любой вошедший: оно ничего не меняет, а обучил
    # модель уже editor.
    return {"значение": await service.predict(session, model_id, payload.row)}
