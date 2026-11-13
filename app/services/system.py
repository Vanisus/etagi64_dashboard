from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


async def check_database(session: AsyncSession) -> bool:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
