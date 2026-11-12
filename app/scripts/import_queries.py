import argparse

from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import APP_DIR
from app.db.models import Category, SearchQuery
from app.db.session import SessionLocal
from app.services.query_catalog import load_catalog
from app.config import setup_logger

logger = setup_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Импорт категорий и фраз из JSON в PostgreSQL."
    )

    parser.add_argument(
        "--catalog",
        type=__import__("pathlib").Path,
        default=APP_DIR / "data" / "queries.json",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Обновить существующие записи значениями из JSON.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        catalog = load_catalog(args.catalog)

        stats = {
            "categories_created": 0,
            "categories_updated": 0,
            "categories_skipped": 0,
            "queries_created": 0,
            "queries_updated": 0,
            "queries_skipped": 0,
        }

        with SessionLocal.begin() as session:
            for item in catalog.categories:
                category = session.get(Category, item.id)

                if category is None:
                    session.add(
                        Category(
                            id=item.id,
                            name=item.name,
                        )
                    )
                    stats["categories_created"] += 1

                elif args.update_existing:
                    category.name = item.name
                    stats["categories_updated"] += 1

                else:
                    stats["categories_skipped"] += 1

            session.flush()

            for item in catalog.queries:
                query = session.get(SearchQuery, item.id)

                if query is None:
                    session.add(
                        SearchQuery(
                            id=item.id,
                            category_id=item.category_id,
                            phrase=item.phrase,
                            enabled=item.enabled,
                        )
                    )
                    stats["queries_created"] += 1

                elif args.update_existing:
                    query.category_id = item.category_id
                    query.phrase = item.phrase
                    query.enabled = item.enabled
                    stats["queries_updated"] += 1

                else:
                    stats["queries_skipped"] += 1

        print("\nИмпорт завершён:")

        for name, value in stats.items():
            print(f"{name}: {value}")

        return 0

    except (ValueError, OSError, SQLAlchemyError) as exc:
        logger.error("Импорт не выполнен: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
