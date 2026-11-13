from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.db.models import Category, City, DailyQueryMetric, SearchQuery
from app.services.metrics import comparison, yesterday

router = APIRouter(prefix="/api/statistics", tags=["statistics"], dependencies=[Depends(current_admin)])


@router.get("/daily")
async def daily_statistics(
    city_id: str, metric_date: date | None = None,
    region_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    category_id: str | None = None, limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0), session: AsyncSession = Depends(get_async_session),
):
    city = await session.get(City, city_id)
    if city is None:
        raise HTTPException(404, "Город не найден.")
    region_id = region_id or city.yandex_region_id
    if not region_id:
        raise HTTPException(422, "Для города не задан регион.")
    target = metric_date or yesterday()
    if target > yesterday() or target == date.min:
        raise HTTPException(422, "Укажите завершённый день с доступным предыдущим днём.")
    previous_date = target - timedelta(days=1)
    current, previous = aliased(DailyQueryMetric), aliased(DailyQueryMetric)

    def match(metric, day):
        return and_(metric.query_id == SearchQuery.id, metric.region_id == region_id, metric.metric_date == day,
                    metric.phrase_snapshot == SearchQuery.phrase, metric.city_id_snapshot == SearchQuery.city_id,
                    metric.category_id_snapshot == SearchQuery.category_id)

    source = (select(SearchQuery.id.label("query_id"), SearchQuery.phrase, SearchQuery.category_id,
                     Category.name.label("category_name"), current.count.label("current_count"),
                     previous.count.label("previous_count"), current.collected_at.label("collected_at"))
              .join(Category, Category.id == SearchQuery.category_id)
              .outerjoin(current, match(current, target)).outerjoin(previous, match(previous, previous_date))
              .where(SearchQuery.city_id == city_id, SearchQuery.enabled.is_(True)))
    if category_id is not None:
        if await session.get(Category, category_id) is None:
            raise HTTPException(404, "Категория не найдена.")
        source = source.where(SearchQuery.category_id == category_id)
    data = source.subquery()
    comparable = and_(data.c.current_count.is_not(None), data.c.previous_count.is_not(None))
    groups = (await session.execute(select(
        data.c.category_id, data.c.category_name, func.count().label("expected"),
        func.count(data.c.current_count).label("current_available"),
        func.count(data.c.previous_count).label("previous_available"),
        func.count(case((comparable, 1))).label("compared"),
        func.sum(data.c.current_count).label("current_total"),
        func.sum(data.c.previous_count).label("previous_total"),
    ).group_by(data.c.category_id, data.c.category_name).order_by(data.c.category_id))).mappings().all()
    categories, total, compared_count = [], 0, 0
    for group in groups:
        complete = group["compared"] == group["expected"]
        current_total = int(group["current_total"]) if group["current_available"] == group["expected"] else None
        previous_total = int(group["previous_total"]) if group["previous_available"] == group["expected"] else None
        categories.append({
            "category_id": group["category_id"], "category_name": group["category_name"],
            "expected_queries": group["expected"], "compared_queries": group["compared"],
            "complete": complete, "current_total": current_total, "previous_total": previous_total,
            **comparison(current_total, previous_total),
        })
        total += group["expected"]
        compared_count += group["compared"]
    rows = (await session.execute(select(data).order_by(data.c.query_id).limit(limit).offset(offset))).mappings().all()
    return {
        "city_id": city_id, "region_id": region_id, "method": "dynamics", "device": "all",
        "current_date": target, "previous_date": previous_date,
        "comparison_status": "complete" if total and total == compared_count else "partial" if compared_count else "no_data",
        "total": total, "compared_queries": compared_count, "limit": limit, "offset": offset,
        "items": [{**dict(row), **comparison(row["current_count"], row["previous_count"])} for row in rows],
        "categories": categories,
        "aggregation_note": "Сумма частот фраз; пересекающиеся фразы могут учитывать один поиск несколько раз.",
    }
