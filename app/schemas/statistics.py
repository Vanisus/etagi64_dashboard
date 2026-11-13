from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.metrics import yesterday


class CollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city_id: str
    method: Literal["topRequests", "dynamics"] = "topRequests"
    region_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")
    date_from: date | None = None
    date_to: date | None = None
    category_id: str | None = None
    top_limit: Annotated[int, Field(ge=1, le=2000)] = 10

    @model_validator(mode="after")
    def validate_dates(self):
        if self.method == "topRequests":
            if self.date_from is not None or self.date_to is not None:
                raise ValueError("Даты доступны только для dynamics.")
            return self
        end = self.date_to or yesterday()
        start = self.date_from or end - timedelta(days=1)
        if start > end or end > yesterday() or start < yesterday() - timedelta(days=58):
            raise ValueError("Допустимы завершённые дни за последние 59 дней; date_from <= date_to.")
        self.date_from, self.date_to = start, end
        return self


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    method: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    parameters: dict
    error: str | None
