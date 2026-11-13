from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


RecordId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    ),
]

Phrase = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=400,
    ),
]

DisplayName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
    ),
]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryCreate(InputModel):
    id: RecordId
    name: DisplayName


class CategoryUpdate(InputModel):
    name: DisplayName


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class QueryCreate(InputModel):
    id: RecordId
    category_id: RecordId
    city_id: RecordId | None = None
    phrase: Phrase
    enabled: bool = True


class QueryUpdate(InputModel):
    category_id: RecordId | None = None
    city_id: RecordId | None = None
    phrase: Phrase | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def check_updates(self):
        if not self.model_fields_set:
            raise ValueError("Передай хотя бы одно изменяемое поле.")

        for field in ("category_id", "phrase", "enabled"):
            if field in self.model_fields_set:
                if getattr(self, field) is None:
                    raise ValueError(
                        f"Поле {field} не может быть null."
                    )

        return self


class QueryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category_id: str
    city_id: str | None
    phrase: str
    enabled: bool


class QueryPage(BaseModel):
    total: int
    items: list[QueryRead]


class CatalogDocument(InputModel):
    version: Literal[1] = 1
    categories: list[CategoryCreate] = Field(max_length=500)
    queries: list[QueryCreate] = Field(max_length=10000)

    @model_validator(mode="after")
    def check_catalog(self):
        category_ids = [item.id for item in self.categories]
        query_ids = [item.id for item in self.queries]

        if len(category_ids) != len(set(category_ids)):
            raise ValueError("Повторяющиеся ID категорий.")

        if len(query_ids) != len(set(query_ids)):
            raise ValueError("Повторяющиеся ID фраз.")

        known_categories = set(category_ids)

        for query in self.queries:
            if query.category_id not in known_categories:
                raise ValueError(
                    f"У фразы {query.id} неизвестная категория "
                    f"{query.category_id}."
                )

        return self


class ImportReport(BaseModel):
    categories_created: int
    categories_updated: int
    categories_skipped: int
    queries_created: int
    queries_updated: int
    queries_skipped: int
