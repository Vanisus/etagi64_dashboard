import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.wordstat_client import WordStatResponseError


def yesterday() -> date:
    return datetime.now(ZoneInfo(os.getenv("REPORTING_TIMEZONE", "Europe/Saratov"))).date() - timedelta(days=1)


def parse_count(value) -> int:
    if type(value) is int:
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        result = int(value)
    else:
        raise ValueError("Ожидалось целое неотрицательное значение частоты.")
    if not 0 <= result <= 9223372036854775807:
        raise ValueError("Частота выходит за пределы BIGINT.")
    return result


def parse_dynamics(response: dict, date_from: date, date_to: date) -> dict[date, int]:
    rows = response.get("results")
    if not isinstance(rows, list):
        raise WordStatResponseError("В dynamics отсутствует массив results.")
    points = {}
    for row in rows:
        try:
            stamp = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0) or stamp.time().isoformat() != "00:00:00":
                raise ValueError("Ожидалось начало дня UTC.")
            day = stamp.date()
            if not date_from <= day <= date_to or day in points:
                raise ValueError("Повторяющаяся дата или дата вне запрошенного периода.")
            points[day] = parse_count(row["count"])
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise WordStatResponseError("Некорректная дневная статистика Wordstat.") from exc
    return points


def comparison(current: int | None, previous: int | None) -> dict:
    if current is None or previous is None:
        return {"delta": None, "delta_percent": None, "trend": "no_data"}
    delta = current - previous
    return {"delta": delta,
            "delta_percent": round(delta * 100 / previous, 2) if previous else (0.0 if current == 0 else None),
            "trend": "up" if delta > 0 else "down" if delta < 0 else "flat"}
