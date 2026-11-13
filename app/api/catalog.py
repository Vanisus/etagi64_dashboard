from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.db.models import Category, City, SearchQuery
from app.schemas.catalog import (
    CatalogDocument,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    ImportReport,
    QueryCreate,
    QueryPage,
    QueryRead,
    QueryUpdate,
)


router = APIRouter(
    prefix="/api",
    tags=["catalog"],
    dependencies=[Depends(current_admin)],
)


async def commit_changes(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Конфликт данных. Проверь ID и связанные записи.",
        ) from exc


async def check_references(
    session: AsyncSession,
    category_id: str,
    city_id: str | None,
) -> None:
    if await session.get(Category, category_id) is None:
        raise HTTPException(
            status_code=422,
            detail=f"Категория {category_id} не существует.",
        )

    if city_id is not None:
        if await session.get(City, city_id) is None:
            raise HTTPException(
                status_code=422,
                detail=f"Город {city_id} не существует.",
            )


@router.get(
    "/categories",
    response_model=list[CategoryRead],
)
async def list_categories(
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.scalars(
        select(Category).order_by(Category.name)
    )
    return result.all()


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=201,
)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_async_session),
):
    if await session.get(Category, payload.id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Категория с таким ID уже существует.",
        )

    category = Category(**payload.model_dump())
    session.add(category)

    await commit_changes(session)

    return category


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryRead,
)
async def update_category(
    category_id: str,
    payload: CategoryUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    category = await session.get(Category, category_id)

    if category is None:
        raise HTTPException(404, "Категория не найдена.")

    category.name = payload.name

    await commit_changes(session)

    return category


@router.get(
    "/queries",
    response_model=QueryPage,
)
async def list_queries(
    city_id: str | None = None,
    category_id: str | None = None,
    enabled: bool | None = None,
    unassigned: bool = False,
    search: str | None = Query(
        default=None,
        min_length=1,
        max_length=400,
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    if city_id is not None and unassigned:
        raise HTTPException(
            status_code=422,
            detail="Нельзя одновременно задать city_id и unassigned.",
        )

    filters = []

    if city_id is not None:
        filters.append(SearchQuery.city_id == city_id)

    if category_id is not None:
        filters.append(SearchQuery.category_id == category_id)

    if enabled is not None:
        filters.append(SearchQuery.enabled == enabled)

    if unassigned:
        filters.append(SearchQuery.city_id.is_(None))

    if search is not None:
        normalized = search.strip()

        if not normalized:
            raise HTTPException(422, "Строка поиска пустая.")

        escaped = (
            normalized
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

        filters.append(
            SearchQuery.phrase.ilike(
                f"%{escaped}%",
                escape="\\",
            )
        )

    total = await session.scalar(
        select(func.count())
        .select_from(SearchQuery)
        .where(*filters)
    )

    result = await session.scalars(
        select(SearchQuery)
        .where(*filters)
        .order_by(SearchQuery.id)
        .limit(limit)
        .offset(offset)
    )

    return QueryPage(
        total=total or 0,
        items=[
            QueryRead.model_validate(item)
            for item in result.all()
        ],
    )


@router.get(
    "/queries/{query_id}",
    response_model=QueryRead,
)
async def read_query(
    query_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    query = await session.get(SearchQuery, query_id)

    if query is None:
        raise HTTPException(404, "Фраза не найдена.")

    return query


@router.post(
    "/queries",
    response_model=QueryRead,
    status_code=201,
)
async def create_query(
    payload: QueryCreate,
    session: AsyncSession = Depends(get_async_session),
):
    if await session.get(SearchQuery, payload.id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Фраза с таким ID уже существует.",
        )

    await check_references(
        session,
        category_id=payload.category_id,
        city_id=payload.city_id,
    )

    query = SearchQuery(**payload.model_dump())
    session.add(query)

    await commit_changes(session)

    return query


@router.patch(
    "/queries/{query_id}",
    response_model=QueryRead,
)
async def update_query(
    query_id: str,
    payload: QueryUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    query = await session.get(SearchQuery, query_id)

    if query is None:
        raise HTTPException(404, "Фраза не найдена.")

    changes = payload.model_dump(exclude_unset=True)

    await check_references(
        session,
        category_id=changes.get(
            "category_id", query.category_id
        ),
        city_id=changes.get("city_id", query.city_id),
    )

    for field, value in changes.items():
        setattr(query, field, value)

    await commit_changes(session)

    return query


async def build_catalog(
    session: AsyncSession,
) -> CatalogDocument:
    categories = (
        await session.scalars(
            select(Category).order_by(Category.id)
        )
    ).all()

    queries = (
        await session.scalars(
            select(SearchQuery).order_by(SearchQuery.id)
        )
    ).all()

    return CatalogDocument(
        version=1,
        categories=[
            CategoryCreate(
                id=item.id,
                name=item.name,
            )
            for item in categories
        ],
        queries=[
            QueryCreate(
                id=item.id,
                category_id=item.category_id,
                city_id=item.city_id,
                phrase=item.phrase,
                enabled=item.enabled,
            )
            for item in queries
        ],
    )


@router.get(
    "/catalog",
    response_model=CatalogDocument,
)
async def read_catalog(
    session: AsyncSession = Depends(get_async_session),
):
    return await build_catalog(session)


@router.get("/catalog/export")
async def export_catalog(
    session: AsyncSession = Depends(get_async_session),
):
    document = await build_catalog(session)

    return JSONResponse(
        content=document.model_dump(mode="json"),
        headers={
            "Content-Disposition":
                'attachment; filename="queries.json"'
        },
    )


@router.post(
    "/catalog/import",
    response_model=ImportReport,
)
async def import_catalog(
    payload: CatalogDocument,
    mode: Literal["add_only", "upsert"] = "add_only",
    session: AsyncSession = Depends(get_async_session),
):
    category_rows = (
        await session.scalars(select(Category))
    ).all()

    query_rows = (
        await session.scalars(select(SearchQuery))
    ).all()

    city_ids = set(
        (await session.scalars(select(City.id))).all()
    )

    categories = {
        item.id: item
        for item in category_rows
    }
    queries = {
        item.id: item
        for item in query_rows
    }

    # Проверяем ссылки до начала изменений.
    for item in payload.queries:
        will_write = item.id not in queries or mode == "upsert"

        if not will_write:
            continue

        # Старый JSON без city_id не должен стирать назначенный город.
        if item.city_id is not None and item.city_id not in city_ids:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"У фразы {item.id} неизвестный город "
                    f"{item.city_id}."
                ),
            )

    stats = {
        "categories_created": 0,
        "categories_updated": 0,
        "categories_skipped": 0,
        "queries_created": 0,
        "queries_updated": 0,
        "queries_skipped": 0,
    }

    try:
        for item in payload.categories:
            existing = categories.get(item.id)

            if existing is None:
                session.add(
                    Category(
                        id=item.id,
                        name=item.name,
                    )
                )
                stats["categories_created"] += 1

            elif mode == "upsert":
                existing.name = item.name
                stats["categories_updated"] += 1

            else:
                stats["categories_skipped"] += 1

        await session.flush()

        for item in payload.queries:
            existing = queries.get(item.id)

            if existing is None:
                session.add(
                    SearchQuery(**item.model_dump())
                )
                stats["queries_created"] += 1

            elif mode == "upsert":
                existing.category_id = item.category_id
                existing.phrase = item.phrase
                existing.enabled = item.enabled

                if "city_id" in item.model_fields_set:
                    existing.city_id = item.city_id

                stats["queries_updated"] += 1

            else:
                stats["queries_skipped"] += 1

        await session.commit()

    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Конфликт при импорте. Изменения отменены.",
        ) from exc

    return ImportReport(**stats)
