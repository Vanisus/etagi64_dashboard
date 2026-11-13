from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import current_admin
from app.db.async_session import get_async_session
from app.schemas.cities import CityCreate, CityUpdate, CityRead
from app.services import cities as service

router = APIRouter(prefix="/api/cities", tags=["cities"], dependencies=[Depends(current_admin)])


@router.get("", response_model=list[CityRead])
async def list_cities(session: AsyncSession = Depends(get_async_session)):
    return await service.list_cities(session=session)


@router.post("", status_code=201, response_model=CityRead)
async def create_city(payload: CityCreate, session: AsyncSession = Depends(get_async_session)):
    return await service.create_city(payload=payload, session=session)


@router.patch("/{city_id}", response_model=CityRead)
async def update_city(city_id: str, payload: CityUpdate, session: AsyncSession = Depends(get_async_session)):
    return await service.update_city(city_id=city_id, payload=payload, session=session)
