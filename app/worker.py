import logging
import time

from sqlalchemy import text, update

from app.db.models import CollectionRun
from app.db.session import SessionLocal, engine
from app.services.statistics_collector import (
    claim_next_run,
    collect_run,
    finish_run,
    utc_now,
)


logger = logging.getLogger(__name__)

WORKER_LOCK_ID = 71412027


def recover_interrupted_runs() -> None:
    with SessionLocal.begin() as session:
        session.execute(
            update(CollectionRun)
            .where(CollectionRun.status == "running")
            .values(
                status="interrupted",
                finished_at=utc_now(),
                error=(
                    "Предыдущий worker завершился до окончания сбора."
                ),
            )
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Один worker для этого приложения.
    # Блокировка живёт на отдельном подключении PostgreSQL.
    with engine.connect() as lock_connection:
        acquired = lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": WORKER_LOCK_ID},
        )
        lock_connection.commit()

        if not acquired:
            raise RuntimeError(
                "Worker уже запущен другим процессом."
            )

        try:
            recover_interrupted_runs()
            logger.info("Worker запущен. Ожидаем задания.")

            while True:
                # Проверяем, что подключение блокировки ещё доступно.
                # При потере подключения завершаем процесс.
                lock_connection.execute(text("SELECT 1"))
                lock_connection.commit()

                run_id = claim_next_run()

                if run_id is None:
                    time.sleep(2.0)
                    continue

                logger.info("Начинаем запуск %s", run_id)

                try:
                    collect_run(run_id)

                except KeyboardInterrupt:
                    finish_run(
                        run_id,
                        status="interrupted",
                        error="Worker остановлен пользователем.",
                    )
                    raise

                except Exception as exc:
                    logger.exception(
                        "Необработанная ошибка запуска %s",
                        run_id,
                    )
                    finish_run(
                        run_id,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )

        finally:
            if not lock_connection.invalidated:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": WORKER_LOCK_ID},
                )
                lock_connection.commit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Worker остановлен.")