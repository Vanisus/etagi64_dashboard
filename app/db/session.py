import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker


APP_DIR = Path(__file__).resolve().parents[1]

load_dotenv(APP_DIR / ".env", override=False)


def required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or value == "":
        raise ValueError(
            f"Не задана переменная окружения {name}."
        )

    return value


def build_database_url() -> URL:
    try:
        port = int(os.getenv("DB_PORT", "5432"))
    except ValueError as exc:
        raise ValueError("DB_PORT должен быть числом.") from exc

    if not 1 <= port <= 65535:
        raise ValueError("DB_PORT должен быть от 1 до 65535.")

    return URL.create(
        drivername="postgresql+psycopg",
        username=required_env("POSTGRES_USER"),
        password=required_env("POSTGRES_PASSWORD"),
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=port,
        database=required_env("POSTGRES_DB"),
    )


engine = create_engine(
    build_database_url(),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)