from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.schemas.catalog import (
    CatalogDocument, CategoryCreate, CategoryRead, CategoryUpdate,
    ImportReport, QueryCreate, QueryPage, QueryRead, QueryUpdate,
)
from app.services import catalog as service

router = APIRouter(prefix="/api", tags=["catalog"], dependencies=[Depends(current_admin)])


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(session: AsyncSession = Depends(get_async_session)):
    return await service.list_categories(session=session)


@router.post("/categories", response_model=CategoryRead, status_code=201)
async def create_category(payload: CategoryCreate, session: AsyncSession = Depends(get_async_session)):
    return await service.create_category(payload=payload, session=session)


@router.patch("/categories/{category_id}", response_model=CategoryRead)
async def update_category(category_id: str, payload: CategoryUpdate,
                          session: AsyncSession = Depends(get_async_session)):
    return await service.update_category(category_id=category_id, payload=payload, session=session)


@router.get("/queries", response_model=QueryPage)
async def list_queries(
    city_id: str | None = None, category_id: str | None = None, enabled: bool | None = None,
    unassigned: bool = False, search: str | None = Query(default=None, min_length=1, max_length=400),
    limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    return await service.list_queries(city_id=city_id, category_id=category_id, enabled=enabled,
                                       unassigned=unassigned, search=search, limit=limit, offset=offset, session=session)


@router.get("/queries/{query_id}", response_model=QueryRead)
async def read_query(query_id: str, session: AsyncSession = Depends(get_async_session)):
    return await service.read_query(query_id=query_id, session=session)


@router.post("/queries", response_model=QueryRead, status_code=201)
async def create_query(payload: QueryCreate, session: AsyncSession = Depends(get_async_session)):
    return await service.create_query(payload=payload, session=session)


@router.patch("/queries/{query_id}", response_model=QueryRead)
async def update_query(query_id: str, payload: QueryUpdate, session: AsyncSession = Depends(get_async_session)):
    return await service.update_query(query_id=query_id, payload=payload, session=session)


@router.get("/catalog", response_model=CatalogDocument)
async def read_catalog(session: AsyncSession = Depends(get_async_session)):
    return await service.read_catalog(session=session)


@router.get("/catalog/export")
async def export_catalog(session: AsyncSession = Depends(get_async_session)):
    document = await service.build_catalog(session)
    return JSONResponse(content=document.model_dump(mode="json"),
                        headers={"Content-Disposition": 'attachment; filename="queries.json"'})


@router.post("/catalog/import", response_model=ImportReport)
async def import_catalog(payload: CatalogDocument, mode: Literal["add_only", "upsert"] = "add_only",
                         session: AsyncSession = Depends(get_async_session)):
    return await service.import_catalog(payload=payload, mode=mode, session=session)
