from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.services import daily as service

router = APIRouter(prefix="/api/statistics", tags=["statistics"], dependencies=[Depends(current_admin)])


@router.get("/daily")
async def daily_statistics(
    city_id: str, metric_date: date | None = None,
    region_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    category_id: str | None = None, limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0), session: AsyncSession = Depends(get_async_session),
):
    return await service.daily_statistics(city_id=city_id, metric_date=metric_date, region_id=region_id,
                                          category_id=category_id, limit=limit, offset=offset, session=session)
