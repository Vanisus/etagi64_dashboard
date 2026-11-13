from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, undefer

from app.db.models import Category, City, CollectionRun, QueryResult, SearchQuery
from app.schemas.statistics import CollectionCreate
from app.services.errors import ServiceError


async def require_run(run_id: UUID, session: AsyncSession) -> CollectionRun:
    run = await session.get(CollectionRun, run_id)
    if run is None:
        raise ServiceError(404, "Запуск не найден.")
    return run


async def create_collection(payload: CollectionCreate, session: AsyncSession):
    city = await session.get(City, payload.city_id)
    if city is None:
        raise ServiceError(422, "Город не найден.")
    region_id = payload.region_id or city.yandex_region_id
    if not region_id:
        raise ServiceError(422, "Задайте yandex_region_id города или region_id в запросе.")
    request_key = "|".join((payload.city_id, region_id, payload.method, payload.category_id or "*",
                            str(payload.date_from or ""), str(payload.date_to or ""), str(payload.top_limit)))
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": request_key})
    existing = await session.scalar(select(CollectionRun.id).where(
        CollectionRun.status.in_(["queued", "running"]), CollectionRun.parameters["request_key"].astext == request_key,
    ).limit(1))
    if existing is not None:
        raise ServiceError(409, f"Такой сбор уже выполняется: {existing}")
    if payload.category_id is not None and await session.get(Category, payload.category_id) is None:
        raise ServiceError(422, "Категория не найдена.")
    statement = (select(SearchQuery, Category.name).join(Category, Category.id == SearchQuery.category_id)
                 .where(SearchQuery.enabled.is_(True), SearchQuery.city_id == payload.city_id).order_by(SearchQuery.id))
    if payload.category_id is not None:
        statement = statement.where(SearchQuery.category_id == payload.category_id)
    rows = (await session.execute(statement)).all()
    if not rows:
        raise ServiceError(422, "Нет включённых фраз для выбранного набора.")
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


async def list_collections(city_id: str | None, limit: int, session: AsyncSession):
    statement = select(CollectionRun)
    if city_id is not None:
        statement = statement.where(CollectionRun.parameters["city_id"].astext == city_id)
    return (await session.scalars(statement.order_by(CollectionRun.started_at.desc()).limit(limit))).all()


async def read_collection(run_id: UUID, session: AsyncSession):
    return await require_run(run_id, session)


async def read_collection_results(run_id: UUID, include_raw: bool, limit: int, offset: int, session: AsyncSession):
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


async def category_statistics(run_id: UUID, session: AsyncSession):
    run = await require_run(run_id, session)
    if run.method != "topRequests":
        raise ServiceError(422, "Для dynamics используйте /api/statistics/daily.")
    selection = run.parameters.get("selection")
    if not isinstance(selection, list):
        raise ServiceError(409, "В запуске отсутствует снимок выбранных фраз.")
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


async def dashboard_categories(city_id: str, region_id: str | None, session: AsyncSession):
    city = await session.get(City, city_id)
    if city is None:
        raise ServiceError(404, "Город не найден.")
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
    ).order_by(CollectionRun.started_at.desc(), CollectionRun.id.desc()).limit(1))
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
        items.append({"category_id": category.id, "category_name": category.name,
                      "current_queries": current_counts[category.id],
                      "expected_queries": saved["expected_queries"] if saved else 0,
                      "successful_queries": saved["successful_queries"] if saved else 0,
                      "complete": saved["complete"] if saved else False,
                      "average_frequency": saved["average_frequency"] if saved else None})
    return {**base_response, "has_data": True, "run_id": latest_run.id, "updated_at": latest_run.finished_at,
            "catalog_changed": snapshot_signature != current_signature, "items": items}
