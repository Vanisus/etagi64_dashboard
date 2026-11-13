from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import City
from app.schemas.cities import CityCreate, CityUpdate
from app.services.errors import ServiceError


async def list_cities(session: AsyncSession):
    return (await session.scalars(select(City).order_by(City.name))).all()


async def save(session: AsyncSession):
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ServiceError(409, "Город с таким ID уже существует.") from exc


async def create_city(payload: CityCreate, session: AsyncSession):
    city = City(**payload.model_dump())
    session.add(city)
    await save(session)
    return city


async def update_city(city_id: str, payload: CityUpdate, session: AsyncSession):
    city = await session.get(City, city_id)
    if city is None:
        raise ServiceError(404, "Город не найден.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(city, key, value)
    await save(session)
    return city
