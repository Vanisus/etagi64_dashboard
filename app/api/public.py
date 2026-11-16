from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.async_session import get_async_session
from app.services import cities, daily, statistics

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/cities")
async def public_cities(session: AsyncSession = Depends(get_async_session)):
    records = await cities.list_cities(session=session)
    return [{"id": item.id, "name": item.name} for item in records]


@router.get("/dashboard")
async def public_dashboard(city_id: str, session: AsyncSession = Depends(get_async_session)):
    result = await statistics.dashboard_categories(city_id=city_id, region_id=None, session=session)
    return {key: result[key] for key in ("city_id", "city_name", "has_data", "updated_at", "catalog_changed", "items")}


@router.get("/daily")
async def public_daily(city_id: str, metric_date: date | None = None,
                       session: AsyncSession = Depends(get_async_session)):
    result = await daily.daily_statistics(
        city_id=city_id, metric_date=metric_date, region_id=None, category_id=None,
        limit=1, offset=0, session=session, include_items=False,
    )
    return {key: result[key] for key in (
        "city_id", "current_date", "previous_date", "comparison_status", "categories", "aggregation_note",
    )}
