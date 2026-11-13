from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.schemas.statistics import CollectionCreate, RunRead
from app.services import statistics as service

router = APIRouter(prefix="/api", tags=["statistics"], dependencies=[Depends(current_admin)])


@router.post("/collections", response_model=RunRead, status_code=202)
async def create_collection(payload: CollectionCreate, session: AsyncSession = Depends(get_async_session)):
    return await service.create_collection(payload=payload, session=session)


@router.get("/collections", response_model=list[RunRead])
async def list_collections(city_id: str | None = None, limit: int = Query(default=20, ge=1, le=100),
                           session: AsyncSession = Depends(get_async_session)):
    return await service.list_collections(city_id=city_id, limit=limit, session=session)


@router.get("/collections/{run_id}", response_model=RunRead)
async def read_collection(run_id: UUID, session: AsyncSession = Depends(get_async_session)):
    return await service.read_collection(run_id=run_id, session=session)


@router.get("/collections/{run_id}/results")
async def read_collection_results(run_id: UUID, include_raw: bool = False,
                                 limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
                                 session: AsyncSession = Depends(get_async_session)):
    return await service.read_collection_results(run_id=run_id, include_raw=include_raw,
                                                 limit=limit, offset=offset, session=session)


@router.get("/statistics/categories")
async def category_statistics(run_id: UUID, session: AsyncSession = Depends(get_async_session)):
    return await service.category_statistics(run_id=run_id, session=session)


@router.get("/dashboard/categories")
async def dashboard_categories(city_id: str,
                               region_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
                               session: AsyncSession = Depends(get_async_session)):
    return await service.dashboard_categories(city_id=city_id, region_id=region_id, session=session)
