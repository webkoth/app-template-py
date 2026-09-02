import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core import storage
from app.core.deps import CurrentUser, SessionDep, require_role
from app.domain.roles import Role
from app.features.datasets import service
from app.features.datasets.schemas import DatasetOut

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
    return [DatasetOut.model_validate(d) for d in await service.list_datasets(session)]


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
