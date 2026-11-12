import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


APP_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AuthSettings:
    cookie_secure: bool
    session_lifetime_seconds: int
    allowed_origins: frozenset[str]


@lru_cache
def get_auth_settings() -> AuthSettings:
    load_dotenv(APP_DIR / ".env", override=False)

    secure = os.getenv(
        "AUTH_COOKIE_SECURE", "true"
    ).strip().lower()

    if secure not in {"true", "false"}:
        raise ValueError(
            "AUTH_COOKIE_SECURE должен быть true или false."
        )

    lifetime = int(
        os.getenv("AUTH_SESSION_LIFETIME_SECONDS", "28800")
    )

    if not 60 <= lifetime <= 604800:
        raise ValueError(
            "AUTH_SESSION_LIFETIME_SECONDS должен быть "
            "от 60 до 604800."
        )

    origins = frozenset(
        item.strip()
        for item in os.getenv(
            "AUTH_ALLOWED_ORIGINS", ""
        ).split(",")
        if item.strip()
    )

    if not origins or "*" in origins:
        raise ValueError(
            "Задай конкретные адреса в AUTH_ALLOWED_ORIGINS."
        )

    return AuthSettings(
        cookie_secure=secure == "true",
        session_lifetime_seconds=lifetime,
        allowed_origins=origins,
    )
