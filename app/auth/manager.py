from uuid import UUID

from fastapi import Depends
from fastapi_users import (
    BaseUserManager,
    InvalidPasswordException,
    UUIDIDMixin,
)

from app.auth.dependencies import get_user_db
from app.db.models import User


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    async def validate_password(self, password, user) -> None:
        if len(password) < 12:
            raise InvalidPasswordException(
                reason="Пароль должен содержать минимум 12 символов."
            )

        if len(password) > 256:
            raise InvalidPasswordException(
                reason="Пароль не должен превышать 256 символов."
            )

        if user.email.lower() in password.lower():
            raise InvalidPasswordException(
                reason="Пароль не должен содержать email."
            )


async def get_user_manager(
    user_db=Depends(get_user_db),
):
    yield UserManager(user_db)