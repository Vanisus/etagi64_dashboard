from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.backend import (
    auth_backend,
    current_admin,
    fastapi_users,
)
from app.auth.schemas import UserRead
from app.config.auth import get_auth_settings
from app.db.async_session import (
    async_engine,
    get_async_session,
)
from app.db.models import City, User


settings = get_auth_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await async_engine.dispose()


app = FastAPI(
    title="Et agi Dashboard".replace("Et agi", "Etagi"),
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def check_write_origin(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")

        if origin not in settings.allowed_origins:
            return JSONResponse(
                status_code=403,
                content={"detail": "Origin is not allowed"},
            )

    return await call_next(request)


app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/api/auth",
    tags=["auth"],
)


@app.get("/api/health", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get(
    "/api/auth/me",
    response_model=UserRead,
    tags=["auth"],
)
async def read_current_admin(
    user: User = Depends(current_admin),
):
    return user


class CityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


@app.get(
    "/api/cities",
    response_model=list[CityRead],
    dependencies=[Depends(current_admin)],
    tags=["cities"],
)
async def read_cities(
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.scalars(
        select(City).order_by(City.name)
    )
    return result.all()
