import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.config.settings import load_settings
from app.db.models import CollectionRun, QueryResult
from app.db.session import SessionLocal
from app.services.wordstat_client import (
    WordStatClient,
    WordStatError,
)


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def finish_run(
    run_id: UUID,
    status: str,
    error: str | None = None,
) -> None:
    with SessionLocal.begin() as session:
        run = session.get(CollectionRun, run_id)

        if run is None:
            raise RuntimeError(f"Запуск {run_id} исчез из БД.")

        run.status = status
        run.finished_at = utc_now()
        run.error = error


def collect_run(run_id: UUID) -> None:
    with SessionLocal() as session:
        run = session.get(CollectionRun, run_id)

        if run is None or run.status != "running":
            raise RuntimeError(
                f"Запуск {run_id} не находится в статусе running."
            )

        parameters = dict(run.parameters)

    selection = parameters["selection"]
    settings = load_settings()

    # Не держим транзакцию БД во время запросов к Яндексу.
    with WordStatClient(
        api_key=settings.api_key,
        folder_id=settings.folder_id,
        timeout_seconds=settings.timeout_seconds,
    ) as client:
        for index, query in enumerate(selection):
            if index > 0:
                time.sleep(1.0)

            logger.info(
                "run=%s query=%s phrase=%r",
                run_id,
                query["id"],
                query["phrase"],
            )

            response = None

            try:
                response = client.top_requests(
                    phrase=query["phrase"],
                    limit=parameters["top_limit"],
                )

                raw_count = response.get("totalCount")

                if raw_count is None:
                    raise ValueError(
                        "В ответе Wordstat отсутствует totalCount."
                    )

                total_count = int(raw_count)

                if not 0 <= total_count <= 9223372036854775807:
                    raise ValueError(
                        "totalCount выходит за пределы BIGINT."
                    )

            except (WordStatError, ValueError, TypeError) as exc:
                with SessionLocal.begin() as session:
                    session.add(
                        QueryResult(
                            run_id=run_id,
                            query_id=query["id"],
                            phrase_snapshot=query["phrase"],
                            category_id_snapshot=query["category_id"],
                            city_id_snapshot=query["city_id"],
                            status="error",
                            collected_at=utc_now(),
                            total_count=None,
                            raw_response=response,
                            error=str(exc),
                        )
                    )

                finish_run(
                    run_id,
                    status="failed",
                    error=str(exc),
                )
                return

            with SessionLocal.begin() as session:
                session.add(
                    QueryResult(
                        run_id=run_id,
                        query_id=query["id"],
                        phrase_snapshot=query["phrase"],
                        category_id_snapshot=query["category_id"],
                        city_id_snapshot=query["city_id"],
                        status="ok",
                        collected_at=utc_now(),
                        total_count=total_count,
                        raw_response=response,
                        error=None,
                    )
                )

    finish_run(run_id, status="completed")


def claim_next_run() -> UUID | None:
    with SessionLocal.begin() as session:
        run = session.scalar(
            select(CollectionRun)
            .where(CollectionRun.status == "queued")
            .order_by(CollectionRun.started_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        if run is None:
            return None

        run.status = "running"
        run.error = None

        return run.id
