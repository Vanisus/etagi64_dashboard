from uuid import UUID

from fastapi import Depends
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
)
from fastapi_users.authentication.strategy.db import (
    AccessTokenDatabase,
    DatabaseStrategy,
)

from app.auth.dependencies import get_access_token_db
from app.auth.manager import get_user_manager
from app.config.auth import get_auth_settings
from app.db.models import AccessToken, User


settings = get_auth_settings()

cookie_transport = CookieTransport(
    cookie_name="etagi_session",
    cookie_max_age=settings.session_lifetime_seconds,
    cookie_path="/api",
    cookie_secure=settings.cookie_secure,
    cookie_httponly=True,
    cookie_samesite="lax",
)


def get_database_strategy(
    access_token_db: AccessTokenDatabase[AccessToken] = Depends(
        get_access_token_db
    ),
):
    return DatabaseStrategy(
        access_token_db,
        lifetime_seconds=settings.session_lifetime_seconds,
    )


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)

fastapi_users = FastAPIUsers[User, UUID](
    get_user_manager,
    [auth_backend],
)

current_admin = fastapi_users.current_user(
    active=True,
    superuser=True,
)
