import asyncio
from getpass import getpass

from fastapi_users import InvalidPasswordException
from fastapi_users.db import SQLAlchemyUserDatabase
from pydantic import ValidationError
from sqlalchemy import select, text

from app.auth.manager import UserManager
from app.auth.schemas import UserCreate
from app.db.async_session import AsyncSessionLocal, async_engine
from app.db.models import User


async def create_admin() -> None:
    email = input("Email администратора: ").strip()
    password = getpass("Пароль: ")
    confirmation = getpass("Повтори пароль: ")
    if password != confirmation:
        raise ValueError("Пароли не совпадают.")
    user_create = UserCreate(email=email, password=password, is_active=True, is_superuser=True, is_verified=True)
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT pg_advisory_lock(71412026)"))
        try:
            if await session.scalar(select(User.id).limit(1)) is not None:
                raise ValueError("Пользователь уже существует. Этот скрипт предназначен только для первого запуска.")
            manager = UserManager(SQLAlchemyUserDatabase(session, User))
            user = await manager.create(user_create, safe=False)
            print(f"Администратор создан: {user.email}")
        finally:
            await session.execute(text("SELECT pg_advisory_unlock(71412026)"))
            await session.commit()


async def main() -> None:
    try:
        await create_admin()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except InvalidPasswordException as exc:
        print(f"Ошибка пароля: {exc.reason}")
        raise SystemExit(1)
    except (ValueError, ValidationError) as exc:
        print(f"Ошибка: {exc}")
        raise SystemExit(1)
