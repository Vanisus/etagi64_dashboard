from collections import defaultdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.db.models import (
    Category,
    City,
    CollectionRun,
    QueryResult,
    SearchQuery,
)


router = APIRouter(
    prefix="/api",
    tags=["statistics"],
    dependencies=[Depends(current_admin)],
)


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city_id: str
    category_id: str | None = None
    top_limit: Annotated[int, Field(ge=1, le=2000)] = 10


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    method: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    parameters: dict
    error: str | None


async def require_run(
    run_id: UUID,
    session: AsyncSession,
) -> CollectionRun:
    run = await session.get(CollectionRun, run_id)

    if run is None:
        raise HTTPException(404, "Запуск не найден.")

    return run


@router.post(
    "/collections",
    response_model=RunRead,
    status_code=202,
)
async def create_collection(
    payload: CollectionCreate,
    session: AsyncSession = Depends(get_async_session),
):
    city = await session.get(City, payload.city_id)

    if city is None:
        raise HTTPException(422, "Город не найден.")

    if payload.category_id is not None:
        category = await session.get(
            Category, payload.category_id
        )
        if category is None:
            raise HTTPException(422, "Категория не найдена.")

    statement = (
        select(SearchQuery, Category.name)
        .join(Category, Category.id == SearchQuery.category_id)
        .where(
            SearchQuery.enabled.is_(True),
            SearchQuery.city_id == payload.city_id,
        )
        .order_by(SearchQuery.id)
    )

    if payload.category_id is not None:
        statement = statement.where(
            SearchQuery.category_id == payload.category_id
        )

    rows = (await session.execute(statement)).all()

    if not rows:
        raise HTTPException(
            422, "Нет включённых фраз для выбранного набора."
        )

    # Фиксируем состав задания в момент его создания.
    selection = [
        {
            "id": query.id,
            "phrase": query.phrase,
            "category_id": query.category_id,
            "category_name": category_name,
            "city_id": query.city_id,
        }
        for query, category_name in rows
    ]

    run = CollectionRun(
        method="topRequests",
        status="queued",
        parameters={
            "city_id": city.id,
            "city_name": city.name,
            "category_id": payload.category_id,
            "top_limit": payload.top_limit,
            "devices": ["DEVICE_ALL"],
            "region_filter": None,
            "window": "last_30_days",
            "selection": selection,
        },
    )

    session.add(run)
    await session.commit()

    return run


@router.get(
    "/collections",
    response_model=list[RunRead],
)
async def list_collections(
    city_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    statement = select(CollectionRun)

    if city_id is not None:
        statement = statement.where(
            CollectionRun.parameters["city_id"].astext == city_id
        )

    result = await session.scalars(
        statement
        .order_by(CollectionRun.started_at.desc())
        .limit(limit)
    )

    return result.all()


@router.get(
    "/collections/{run_id}",
    response_model=RunRead,
)
async def read_collection(
    run_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    return await require_run(run_id, session)


@router.get("/collections/{run_id}/results")
async def read_collection_results(
    run_id: UUID,
    include_raw: bool = False,
    session: AsyncSession = Depends(get_async_session),
):
    await require_run(run_id, session)

    results = (
        await session.scalars(
            select(QueryResult)
            .where(QueryResult.run_id == run_id)
            .order_by(QueryResult.query_id)
        )
    ).all()

    items = []

    for result in results:
        item = {
            "query_id": result.query_id,
            "phrase": result.phrase_snapshot,
            "city_id": result.city_id_snapshot,
            "category_id": result.category_id_snapshot,
            "status": result.status,
            "collected_at": result.collected_at,
            "total_count": result.total_count,
            "error": result.error,
        }

        if include_raw:
            item["raw_response"] = result.raw_response

        items.append(item)

    return {"run_id": run_id, "items": items}


@router.get("/statistics/categories")
async def category_statistics(
    run_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    run = await require_run(run_id, session)

    if run.method != "topRequests":
        raise HTTPException(
            422, "Для этого метода расчёт ещё не реализован."
        )

    selection = run.parameters.get("selection")

    if not isinstance(selection, list):
        raise HTTPException(
            409, "В запуске отсутствует снимок выбранных фраз."
        )

    results = (
        await session.scalars(
            select(QueryResult)
            .where(QueryResult.run_id == run_id)
        )
    ).all()

    results_by_query = {
        result.query_id: result
        for result in results
    }

    groups = defaultdict(list)

    for query in selection:
        groups[query["category_id"]].append(query)

    items = []

    for category_id, queries in sorted(groups.items()):
        values = []
        failed = 0
        pending = 0

        for query in queries:
            result = results_by_query.get(query["id"])

            if result is None:
                pending += 1
            elif result.status == "ok" and result.total_count is not None:
                values.append(result.total_count)
            else:
                failed += 1

        expected = len(queries)
        successful = len(values)

        items.append({
            "category_id": category_id,
            "category_name": queries[0]["category_name"],
            "expected_queries": expected,
            "successful_queries": successful,
            "failed_queries": failed,
            "without_result": pending,
            "complete": successful == expected,
            "average_frequency": (
                round(sum(values) / successful, 2)
                if successful
                else None
            ),
        })

    return {
        "run_id": run.id,
        "run_status": run.status,
        "city_id": run.parameters.get("city_id"),
        "city_name": run.parameters.get("city_name"),
        "method": run.method,
        "window": run.parameters.get("window"),
        "created_at": run.started_at,
        "finished_at": run.finished_at,
        "items": items,
    }

@router.get("/dashboard/categories")
async def dashboard_categories(
    city_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    city = await session.get(City, city_id)

    if city is None:
        raise HTTPException(404, "Город не найден.")

    categories = (
        await session.scalars(
            select(Category).order_by(Category.name)
        )
    ).all()

    current_queries = (
        await session.scalars(
            select(SearchQuery)
            .where(
                SearchQuery.city_id == city_id,
                SearchQuery.enabled.is_(True),
            )
            .order_by(SearchQuery.id)
        )
    ).all()

    current_counts = defaultdict(int)

    for query in current_queries:
        current_counts[query.category_id] += 1

    # Текущая активность — отдельно от сохранённой сводки.
    active_run = await session.scalar(
        select(CollectionRun)
        .where(
            CollectionRun.method == "topRequests",
            CollectionRun.status.in_(["queued", "running"]),
            CollectionRun.parameters["city_id"].astext == city_id,
        )
        .order_by(CollectionRun.started_at.desc())
        .limit(1)
    )

    # Общая сводка строится только по сбору всего города.
    latest_run = await session.scalar(
        select(CollectionRun)
        .where(
            CollectionRun.method == "topRequests",
            CollectionRun.status == "completed",
            CollectionRun.parameters["city_id"].astext == city_id,
            CollectionRun.parameters["category_id"].astext.is_(None),
        )
        .order_by(
            CollectionRun.finished_at.desc(),
            CollectionRun.started_at.desc(),
            CollectionRun.id.desc(),
        )
        .limit(1)
    )

    base_response = {
        "city_id": city.id,
        "city_name": city.name,
        "method": "topRequests",
        "window": "last_30_days",
        "active_run": (
            {
                "id": active_run.id,
                "status": active_run.status,
                "category_id": active_run.parameters.get(
                    "category_id"
                ),
            }
            if active_run is not None
            else None
        ),
    }

    if latest_run is None:
        return {
            **base_response,
            "has_data": False,
            "run_id": None,
            "updated_at": None,
            "catalog_changed": None,
            "items": [
                {
                    "category_id": category.id,
                    "category_name": category.name,
                    "current_enabled_queries": current_counts[
                        category.id
                    ],
                    "expected_queries": 0,
                    "successful_queries": 0,
                    "failed_queries": 0,
                    "without_result": 0,
                    "complete": False,
                    "average_frequency": None,
                }
                for category in categories
            ],
        }

    # Используем уже проверенный расчёт для конкретного запуска.
    statistics = await category_statistics(
        run_id=latest_run.id,
        session=session,
    )

    statistics_by_category = {
        item["category_id"]: item
        for item in statistics["items"]
    }

    selection = latest_run.parameters.get("selection", [])

    snapshot_signature = {
        (
            item["id"],
            item["phrase"],
            item["category_id"],
            item["city_id"],
        )
        for item in selection
    }

    current_signature = {
        (
            query.id,
            query.phrase,
            query.category_id,
            query.city_id,
        )
        for query in current_queries
    }

    items = []

    for category in categories:
        stored = statistics_by_category.get(category.id)

        if stored is None:
            item = {
                "category_id": category.id,
                "category_name": category.name,
                "expected_queries": 0,
                "successful_queries": 0,
                "failed_queries": 0,
                "without_result": 0,
                "complete": False,
                "average_frequency": None,
            }
        else:
            item = dict(stored)

            # Для интерфейса используем актуальное название.
            # Историческое название остаётся в исходном запуске.
            item["category_name"] = category.name

        item["current_enabled_queries"] = current_counts[
            category.id
        ]
        items.append(item)

    return {
        **base_response,
        "has_data": True,
        "run_id": latest_run.id,
        "updated_at": latest_run.finished_at,
        "catalog_changed": (
            snapshot_signature != current_signature
        ),
        "items": items,
    }
