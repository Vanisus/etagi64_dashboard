import json
from dataclasses import dataclass
from pathlib import Path


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Category:
    id: str
    name: str


@dataclass(frozen=True)
class SearchQuery:
    id: str
    category_id: str
    phrase: str
    enabled: bool


@dataclass(frozen=True)
class QueryCatalog:
    version: int
    categories: tuple[Category, ...]
    queries: tuple[SearchQuery, ...]

    def select(self, category_id: str | None = None, query_id: str | None = None,
               include_disabled: bool = False) -> list[SearchQuery]:
        if category_id is not None:
            known_categories = {item.id for item in self.categories}
            if category_id not in known_categories:
                raise CatalogError(f"Category {category_id} not in known categories")
        if query_id is not None:
            known_queries = {item.id for item in self.queries}
            if query_id not in known_queries:
                raise CatalogError(f"Query {query_id} not in known queries")
        return [query for query in self.queries if (include_disabled or query.enabled)
                and (category_id is None or query.category_id == category_id)
                and (query_id is None or query.id == query_id)]


def require_text(data: dict, field: str, location: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{location}: field {field} is required")
    return value.strip()


def load_catalog(path: Path) -> QueryCatalog:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise CatalogError(f"{path}: could not read catalog content: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"JSON Error in {path}: {exc.lineno}, {exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise CatalogError("Invalid catalog content")
    if type(data.get("version")) is not int or data["version"] < 1:
        raise CatalogError("Invalid catalog version")
    raw_categories, raw_queries = data.get("categories"), data.get("queries")
    if not isinstance(raw_categories, list):
        raise CatalogError("Invalid catalog categories")
    if not isinstance(raw_queries, list):
        raise CatalogError("Invalid catalog queries")
    categories, category_ids = [], set()
    for index, item in enumerate(raw_categories):
        location = f"categories[{index}]"
        if not isinstance(item, dict):
            raise CatalogError(f"{location}: Invalid catalog categories")
        category_id, name = require_text(item, "id", location), require_text(item, "name", location)
        if category_id in category_ids:
            raise CatalogError(f"{location}: Category {category_id} already exists")
        category_ids.add(category_id)
        categories.append(Category(id=category_id, name=name))
    queries, query_ids = [], set()
    for index, item in enumerate(raw_queries):
        location = f"queries[{index}]"
        if not isinstance(item, dict):
            raise CatalogError(f"{location}: Invalid catalog queries")
        query_id = require_text(item, "id", location)
        category_id = require_text(item, "category_id", location)
        phrase = require_text(item, "phrase", location)
        enabled = item.get("enabled")
        if type(enabled) is not bool:
            raise CatalogError(f"{location}: Invalid enabled type")
        if query_id in query_ids:
            raise CatalogError(f"{location}: Query {query_id} already exists")
        if category_id not in category_ids:
            raise CatalogError(f"{location}: Category {category_id} does not exist")
        query_ids.add(query_id)
        queries.append(SearchQuery(id=query_id, category_id=category_id, phrase=phrase, enabled=enabled))
    return QueryCatalog(version=data["version"], categories=tuple(categories), queries=tuple(queries))
