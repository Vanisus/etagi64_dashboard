from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.catalog import router as catalog_router
from app.api.cities import router as cities_router
from app.api.daily import router as daily_router
from app.api.statistics import router as statistics_router
from app.auth.backend import auth_backend, current_admin, fastapi_users
from app.auth.schemas import UserRead
from app.config.auth import get_auth_settings
from app.db.async_session import async_engine, get_async_session
from app.db.models import User

settings = get_auth_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await async_engine.dispose()


app = FastAPI(title="Etagi Dashboard", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type"],
)
app.include_router(catalog_router)
app.include_router(statistics_router)
app.include_router(cities_router)
app.include_router(daily_router)


@app.middleware("http")
async def check_write_origin(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin not in settings.allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})
    return await call_next(request)


app.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/api/auth", tags=["auth"])


@app.get("/api/health", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/api/auth/me", response_model=UserRead, tags=["auth"])
async def read_current_admin(user: User = Depends(current_admin)):
    return user


@app.get("/api/ready", tags=["system"])
async def readiness(session: AsyncSession = Depends(get_async_session)):
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
