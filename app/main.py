import argparse
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import setup_logger
from app.config.settings import APP_DIR, load_settings
from app.services.query_catalog import load_catalog
from app.services.wordstat_client import (
    WordStatClient,
    WordStatError,
)


logger = setup_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Сбор статистики Wordstat по JSON-каталогу."
    )

    parser.add_argument(
        "--catalog",
        type=Path,
        default=APP_DIR / "data" / "queries.json",
        help="Путь к JSON-каталогу.",
    )
    parser.add_argument(
        "--category",
        help="Выбрать категорию по ID.",
    )
    parser.add_argument(
        "--query-id",
        help="Выбрать одну фразу по ID.",
    )
    parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="Показать отключённые фразы. Только без --execute.",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        help="Ограничить количество выбранных фраз.",
    )
    parser.add_argument(
        "--top-limit",
        type=int,
        default=10,
        help="Количество результатов topRequests для каждой фразы.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Пауза между запросами в секундах.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Отправить выбранные фразы в API.",
    )

    return parser


def save_json(path: Path, document: dict) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    if args.max_queries is not None and args.max_queries < 1:
        parser.error("--max-queries должен быть больше нуля.")

    if not 1 <= args.top_limit <= 2000:
        parser.error("--top-limit должен быть от 1 до 2000.")

    if not 0 <= args.delay <= 3600:
        parser.error("--delay должен быть от 0 до 3600.")

    if args.execute and args.include_disabled:
        parser.error(
            "--include-disabled разрешён только для просмотра."
        )

    try:
        catalog = load_catalog(args.catalog)

        selected = catalog.select(
            category_id=args.category,
            query_id=args.query_id,
            include_disabled=args.include_disabled,
        )

        if args.max_queries is not None:
            selected = selected[:args.max_queries]

        category_names = {
            category.id: category.name
            for category in catalog.categories
        }

        print(f"Каталог: {args.catalog}")
        print(f"Всего фраз: {len(catalog.queries)}")
        print(f"Выбрано: {len(selected)}")

        for query in selected:
            status = "включён" if query.enabled else "отключён"
            print(
                f"[{query.id}] {query.phrase} "
                f"| {category_names[query.category_id]} "
                f"| {status}"
            )

        if not selected:
            print("\nНет фраз для обработки.")
            return 0

        if not args.execute:
            print("\nРежим просмотра. API не вызывается.")
            print("Для отправки добавь --execute.")
            return 0

        settings = load_settings()

        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid4().hex[:8]
        )
        run_dir = APP_DIR / "output" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        save_json(
            run_dir / "selection.json",
            {
                "catalog_version": catalog.version,
                "categories": [
                    asdict(category)
                    for category in catalog.categories
                ],
                "queries": [asdict(query) for query in selected],
                "method": "topRequests",
                "top_limit": args.top_limit,
                "region_filter": None,
            },
        )

        completed = 0

        with WordStatClient(
            api_key=settings.api_key,
            folder_id=settings.folder_id,
            timeout_seconds=settings.timeout_seconds,
        ) as client:
            for index, query in enumerate(selected, start=1):
                if index > 1:
                    time.sleep(args.delay)

                logger.info(
                    "Сбор %s/%s: %s",
                    index,
                    len(selected),
                    query.phrase,
                )

                try:
                    result = client.top_requests(
                        phrase=query.phrase,
                        limit=args.top_limit,
                    )
                except WordStatError as exc:
                    save_json(
                        run_dir / f"{index:04d}.json",
                        {
                            "query": asdict(query),
                            "collected_at": datetime.now(
                                timezone.utc
                            ).isoformat(),
                            "status": "error",
                            "error": str(exc),
                        },
                    )
                    logger.error(
                        "Сбор остановлен после ошибки: %s", exc
                    )
                    logger.info(
                        "Успешно сохранено: %s. Папка: %s",
                        completed,
                        run_dir,
                    )
                    return 1

                save_json(
                    run_dir / f"{index:04d}.json",
                    {
                        "query": asdict(query),
                        "collected_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "status": "ok",
                        "method": "topRequests",
                        "response": result,
                    },
                )
                completed += 1

        logger.info(
            "Готово. Сохранено: %s. Папка: %s",
            completed,
            run_dir,
        )
        return 0

    except (ValueError, OSError, WordStatError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())