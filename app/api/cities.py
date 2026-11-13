from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.db.models import City
from app.schemas.catalog import DisplayName, RecordId

router = APIRouter(prefix="/api/cities", tags=["cities"], dependencies=[Depends(current_admin)])


class CityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: RecordId
    name: DisplayName
    yandex_region_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")


class CityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: DisplayName | None = None
    yandex_region_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set or ("name" in self.model_fields_set and self.name is None):
            raise ValueError("Передайте изменяемое поле; name не может быть null.")
        return self


class CityRead(CityCreate):
    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[CityRead])
async def list_cities(session: AsyncSession = Depends(get_async_session)):
    return (await session.scalars(select(City).order_by(City.name))).all()


async def save(session):
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Город с таким ID уже существует.") from exc


@router.post("", status_code=201, response_model=CityRead)
async def create_city(payload: CityCreate, session: AsyncSession = Depends(get_async_session)):
    city = City(**payload.model_dump())
    session.add(city)
    await save(session)
    return city


@router.patch("/{city_id}", response_model=CityRead)
async def update_city(city_id: str, payload: CityUpdate, session: AsyncSession = Depends(get_async_session)):
    city = await session.get(City, city_id)
    if city is None:
        raise HTTPException(404, "Город не найден.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(city, key, value)
    await save(session)
    return city
