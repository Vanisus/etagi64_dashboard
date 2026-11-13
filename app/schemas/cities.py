from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.catalog import DisplayName, RecordId


class CityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: RecordId
    name: DisplayName
    yandex_region_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")


class CityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: DisplayName | None = None
    yandex_region_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,18}$")

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set or ("name" in self.model_fields_set and self.name is None):
            raise ValueError("Передайте изменяемое поле; name не может быть null.")
        return self


class CityRead(CityCreate):
    model_config = ConfigDict(from_attributes=True)
