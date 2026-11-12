import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    folder_id: str
    timeout_seconds: float = 60.0

def load_settings() -> Settings:
    load_dotenv(APP_DIR / ".env", override=False)

    api_key = os.getenv("YANDEX_API_KEY", "").strip()
    folder_id = os.getenv("YANDEX_FOLDER_ID", "").strip()

    missing = []

    if not api_key:
        missing.append("YANDEX_API_KEY")

    if not folder_id:
        missing.append("YANDEX_FOLDER_ID")

    if missing:
        raise ValueError(
            "Не заданы переменные: " + ", ".join(missing)
        )

    try:
        timeout = float(
            os.getenv("WORDSTAT_TIMEOUT_SECONDS", "60")
        )
    except ValueError as exc:
        raise ValueError(
            "WORDSTAT_TIMEOUT_SECONDS должен быть числом."
        ) from exc

    if not 0 < timeout <= 300:
        raise ValueError(
            "WORDSTAT_TIMEOUT_SECONDS должен быть больше 0 "
            "и не больше 300."
        )

    return Settings(
        api_key=api_key,
        folder_id=folder_id,
        timeout_seconds=timeout,
    )
