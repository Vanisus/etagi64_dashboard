from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, undefer

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.db.models import Category, City, CollectionRun, QueryResult, SearchQuery
from app.services.metrics import yesterday

router = APIRouter(prefix="/api", tags=["statistics"], dependencies=[Depends(current_admin)])


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city_id: str
    method: Literal["topRequests", "dynamics"] = "topRequests"
    region_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")
    date_from: date | None = None
    date_to: date | None = None
    category_id: str | None = None
    top_limit: Annotated[int, Field(ge=1, le=2000)] = 10

    @model_validator(mode="after")
    def validate_dates(self):
        if self.method == "topRequests":
            if self.date_from is not None or self.date_to is not None:
                raise ValueError("Даты доступны только для dynamics.")
            return self
        end = self.date_to or yesterday()
        start = self.date_from or end - timedelta(days=1)
        if start > end or end > yesterday() or start < yesterday() - timedelta(days=58):
            raise ValueError("Допустимы завершённые дни за последние 59 дней; date_from <= date_to.")
        self.date_from, self.date_to = start, end
        return self


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    method: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    parameters: dict
    error: str | None


async def require_run(run_id: UUID, session: AsyncSession) -> CollectionRun:
    run = await session.get(CollectionRun, run_id)
    if run is None:
        raise HTTPException(404, "Запуск не найден.")
    return run


@router.post("/collections", response_model=RunRead, status_code=202)
async def create_collection(payload: CollectionCreate, session: AsyncSession = Depends(get_async_session)):
    city = await session.get(City, payload.city_id)
    if city is None:
        raise HTTPException(422, "Город не найден.")
    region_id = payload.region_id or city.yandex_region_id
    if not region_id:
        raise HTTPException(422, "Задайте yandex_region_id города или region_id в запросе.")
    request_key = "|".join((payload.city_id, region_id, payload.method, payload.category_id or "*",
                            str(payload.date_from or ""), str(payload.date_to or ""), str(payload.top_limit)))
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": request_key})
    existing = await session.scalar(select(CollectionRun.id).where(
        CollectionRun.status.in_(["queued", "running"]), CollectionRun.parameters["request_key"].astext == request_key,
    ).limit(1))
    if existing is not None:
        raise HTTPException(409, f"Такой сбор уже выполняется: {existing}")
    if payload.category_id is not None and await session.get(Category, payload.category_id) is None:
        raise HTTPException(422, "Категория не найдена.")
    statement = (select(SearchQuery, Category.name).join(Category, Category.id == SearchQuery.category_id)
                 .where(SearchQuery.enabled.is_(True), SearchQuery.city_id == payload.city_id).order_by(SearchQuery.id))
    if payload.category_id is not None:
        statement = statement.where(SearchQuery.category_id == payload.category_id)
    rows = (await session.execute(statement)).all()
    if not rows:
        raise HTTPException(422, "Нет включённых фраз для выбранного набора.")
    selection = [{"id": query.id, "phrase": query.phrase, "category_id": query.category_id,
                  "category_name": category_name, "city_id": query.city_id} for query, category_name in rows]
    run = CollectionRun(method=payload.method, status="queued", parameters={
        "city_id": city.id, "city_name": city.name, "category_id": payload.category_id,
        "top_limit": payload.top_limit, "devices": ["DEVICE_ALL"], "region_filter": [region_id],
        "window": "calendar_days" if payload.method == "dynamics" else "last_30_days",
        "region_id": region_id, "request_key": request_key,
        "date_from": payload.date_from.isoformat() if payload.date_from else None,
        "date_to": payload.date_to.isoformat() if payload.date_to else None, "selection": selection,
    })
    session.add(run)
    await session.commit()
    return run


@router.get("/collections", response_model=list[RunRead])
async def list_collections(city_id: str | None = None, limit: int = Query(default=20, ge=1, le=100),
                           session: AsyncSession = Depends(get_async_session)):
    statement = select(CollectionRun)
    if city_id is not None:
        statement = statement.where(CollectionRun.parameters["city_id"].astext == city_id)
    return (await session.scalars(statement.order_by(CollectionRun.started_at.desc()).limit(limit))).all()


@router.get("/collections/{run_id}", response_model=RunRead)
async def read_collection(run_id: UUID, session: AsyncSession = Depends(get_async_session)):
    return await require_run(run_id, session)


@router.get("/collections/{run_id}/results")
async def read_collection_results(run_id: UUID, include_raw: bool = False,
                                 limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
                                 session: AsyncSession = Depends(get_async_session)):
    await require_run(run_id, session)
    results = (await session.scalars(select(QueryResult).where(QueryResult.run_id == run_id)
               .options(undefer(QueryResult.raw_response) if include_raw else defer(QueryResult.raw_response))
               .order_by(QueryResult.query_id).limit(limit).offset(offset))).all()
    items = []
    for result in results:
        item = {"query_id": result.query_id, "phrase": result.phrase_snapshot, "city_id": result.city_id_snapshot,
                "category_id": result.category_id_snapshot, "status": result.status, "collected_at": result.collected_at,
                "total_count": result.total_count, "error": result.error}
        if include_raw:
            item["raw_response"] = result.raw_response
        items.append(item)
    total = await session.scalar(select(func.count()).select_from(QueryResult).where(QueryResult.run_id == run_id))
    return {"run_id": run_id, "total": total or 0, "limit": limit, "offset": offset, "items": items}


@router.get("/statistics/categories")
async def category_statistics(run_id: UUID, session: AsyncSession = Depends(get_async_session)):
    run = await require_run(run_id, session)
    if run.method != "topRequests":
        raise HTTPException(422, "Для dynamics используйте /api/statistics/daily.")
    selection = run.parameters.get("selection")
    if not isinstance(selection, list):
        raise HTTPException(409, "В запуске отсутствует снимок выбранных фраз.")
    results = (await session.scalars(select(QueryResult).options(defer(QueryResult.raw_response))
                                   .where(QueryResult.run_id == run_id))).all()
    results_by_query = {result.query_id: result for result in results}
    groups = defaultdict(list)
    for query in selection:
        groups[query["category_id"]].append(query)
    items = []
    for category_id, queries in sorted(groups.items()):
        values, failed, pending = [], 0, 0
        for query in queries:
            result = results_by_query.get(query["id"])
            if result is None:
                pending += 1
            elif result.status == "ok" and result.total_count is not None:
                values.append(result.total_count)
            else:
                failed += 1
        expected, successful = len(queries), len(values)
        items.append({"category_id": category_id, "category_name": queries[0]["category_name"],
                      "expected_queries": expected, "successful_queries": successful, "failed_queries": failed,
                      "without_result": pending, "complete": successful == expected,
                      "average_frequency": round(sum(values) / successful, 2) if successful else None})
    return {"run_id": run.id, "run_status": run.status, "city_id": run.parameters.get("city_id"),
            "city_name": run.parameters.get("city_name"), "method": run.method, "window": run.parameters.get("window"),
            "created_at": run.started_at, "finished_at": run.finished_at, "items": items}


@router.get("/dashboard/categories")
async def dashboard_categories(city_id: str,
                               region_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
                               session: AsyncSession = Depends(get_async_session)):
    city = await session.get(City, city_id)
    if city is None:
        raise HTTPException(404, "Город не найден.")
    region_id = region_id or city.yandex_region_id
    categories = (await session.scalars(select(Category).order_by(Category.name))).all()
    current_queries = (await session.scalars(select(SearchQuery).where(
        SearchQuery.city_id == city_id, SearchQuery.enabled.is_(True)).order_by(SearchQuery.id))).all()
    current_counts = defaultdict(int)
    for query in current_queries:
        current_counts[query.category_id] += 1
    active_run = await session.scalar(select(CollectionRun).where(
        CollectionRun.method == "topRequests", CollectionRun.status.in_(["queued", "running"]),
        CollectionRun.parameters["city_id"].astext == city_id, CollectionRun.parameters["region_id"].astext == region_id,
    ).order_by(CollectionRun.started_at.desc()).limit(1))
    latest_run = await session.scalar(select(CollectionRun).where(
        CollectionRun.method == "topRequests", CollectionRun.status == "completed",
        CollectionRun.parameters["city_id"].astext == city_id, CollectionRun.parameters["region_id"].astext == region_id,
        CollectionRun.parameters["category_id"].astext.is_(None),
    ).order_by(CollectionRun.finished_at.desc(), CollectionRun.started_at.desc(), CollectionRun.id.desc()).limit(1))
    base_response = {
        "city_id": city.id, "city_name": city.name, "region_id": region_id,
        "method": "topRequests", "window": "last_30_days",
        "active_run": {"id": active_run.id, "status": active_run.status,
                       "category_id": active_run.parameters.get("category_id")} if active_run is not None else None,
    }
    if latest_run is None:
        return {**base_response, "has_data": False, "run_id": None, "updated_at": None, "catalog_changed": None,
                "items": [{"category_id": category.id, "category_name": category.name,
                           "current_queries": current_counts[category.id], "expected_queries": 0,
                           "successful_queries": 0, "complete": False, "average_frequency": None}
                          for category in categories]}
    statistics = await category_statistics(latest_run.id, session)
    statistics_by_category = {item["category_id"]: item for item in statistics["items"]}
    snapshot_signature = {(item["id"], item["phrase"], item["category_id"], item.get("city_id"))
                          for item in latest_run.parameters.get("selection", [])}
    current_signature = {(item.id, item.phrase, item.category_id, item.city_id) for item in current_queries}
    items = []
    for category in categories:
        saved = statistics_by_category.get(category.id)
        items.append({
            "category_id": category.id, "category_name": category.name, "current_queries": current_counts[category.id],
            "expected_queries": saved["expected_queries"] if saved else 0,
            "successful_queries": saved["successful_queries"] if saved else 0,
            "complete": saved["complete"] if saved else False,
            "average_frequency": saved["average_frequency"] if saved else None,
        })
    return {**base_response, "has_data": True, "run_id": latest_run.id, "updated_at": latest_run.finished_at,
            "catalog_changed": snapshot_signature != current_signature, "items": items}
