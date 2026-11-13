import logging
from datetime import date, datetime, timezone
from threading import Event
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config.settings import load_settings
from app.db.models import CollectionRun, DailyQueryMetric, QueryResult
from app.db.session import SessionLocal
from app.services.metrics import parse_count, parse_dynamics
from app.services.wordstat_client import WordStatAPIError, WordStatClient, WordStatError

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def finish_run(run_id: UUID, status: str, error: str | None = None) -> None:
    with SessionLocal.begin() as session:
        run = session.get(CollectionRun, run_id)
        if run is None:
            raise RuntimeError(f"Запуск {run_id} исчез из БД.")
        run.status, run.finished_at, run.error = status, utc_now(), error


def collect_run(run_id: UUID, stop_event: Event | None = None, check_lock=None) -> None:
    with SessionLocal() as session:
        run = session.get(CollectionRun, run_id)
        if run is None or run.status != "running":
            raise RuntimeError(f"Запуск {run_id} не находится в статусе running.")
        parameters, method = dict(run.parameters), run.method
    region = parameters.get("region_id")
    if not region:
        finish_run(run_id, "failed", "Задание без региона устарело. Создайте новый сбор.")
        return
    settings = load_settings()
    failures = 0
    with WordStatClient(settings.api_key, settings.folder_id, settings.timeout_seconds) as client:
        for query in parameters["selection"]:
            if stop_event is not None and stop_event.is_set():
                finish_run(run_id, "interrupted", "Worker остановлен.")
                return
            if check_lock is not None:
                check_lock()
            response, count, error, points = None, None, None, {}
            fatal = False
            try:
                if method == "dynamics":
                    date_from = date.fromisoformat(parameters["date_from"])
                    date_to = date.fromisoformat(parameters["date_to"])
                    response = client.dynamics(query["phrase"], date_from, date_to, regions=[region])
                    points = parse_dynamics(response, date_from, date_to)
                    count = points.get(date_to)
                    expected_days = (date_to - date_from).days + 1
                    if len(points) != expected_days:
                        error = "Wordstat вернул неполные дневные данные; пропуски не заменены нулями."
                elif method == "topRequests":
                    response = client.top_requests(query["phrase"], limit=parameters["top_limit"], regions=[region])
                    count = parse_count(response.get("totalCount"))
                else:
                    raise ValueError("Неизвестный метод сбора.")
            except (WordStatError, ValueError, TypeError) as exc:
                error = str(exc)
                fatal = isinstance(exc, WordStatAPIError) and exc.status_code in {401, 403, 429}
            if check_lock is not None:
                check_lock()
            with SessionLocal.begin() as session:
                session.add(QueryResult(
                    run_id=run_id, query_id=query["id"], phrase_snapshot=query["phrase"],
                    category_id_snapshot=query["category_id"], city_id_snapshot=query["city_id"],
                    status="error" if error else "ok", collected_at=utc_now(), total_count=count,
                    raw_response=response, error=error,
                ))
                for day, value in points.items():
                    statement = insert(DailyQueryMetric).values(
                        query_id=query["id"], region_id=region, metric_date=day, run_id=run_id,
                        phrase_snapshot=query["phrase"], city_id_snapshot=query["city_id"],
                        category_id_snapshot=query["category_id"], count=value, collected_at=utc_now(),
                    )
                    session.execute(statement.on_conflict_do_update(
                        index_elements=["query_id", "region_id", "metric_date"],
                        set_={key: getattr(statement.excluded, key) for key in (
                            "run_id", "phrase_snapshot", "city_id_snapshot", "category_id_snapshot", "count", "collected_at"
                        )},
                    ))
            if error:
                failures += 1
                logger.warning("Сбор %s: ошибка фразы %s: %s", run_id, query["id"], error)
            if fatal:
                finish_run(run_id, "failed", error)
                return
    finish_run(run_id, "failed" if failures else "completed", f"Ошибок фраз: {failures}" if failures else None)


def claim_next_run() -> UUID | None:
    with SessionLocal.begin() as session:
        run = session.scalar(select(CollectionRun).where(CollectionRun.status == "queued")
                             .order_by(CollectionRun.started_at, CollectionRun.id)
                             .with_for_update(skip_locked=True).limit(1))
        if run is None:
            return None
        run.status, run.error = "running", None
        return run.id
