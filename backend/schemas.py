from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from config import get_settings


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: str = Field(min_length=1, max_length=8)
    offer_id: int = Field(gt=0)

    @field_validator("name", "geo")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    geo: str | None = Field(default=None, min_length=1, max_length=8)
    offer_id: int | None = Field(default=None, gt=0)

    @field_validator("name", "geo")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    geo: str
    offer_id: int
    keitaro_id: int | None
    created_at: datetime

    @computed_field
    @property
    def keitaro_campaign_id(self) -> int | None:
        return self.keitaro_id

    @computed_field
    @property
    def view_in_kt_url(self) -> str | None:
        if self.keitaro_id is None:
            return None
        settings = get_settings()
        if settings.keitaro_admin_url:
            base = settings.keitaro_admin_url.strip().split("#", 1)[0].rstrip("/")
        else:
            base = settings.keitaro_api_url.strip().rstrip("/") + "/admin"
        return f"{base}/#!/campaign/{self.keitaro_id}/main"


class CampaignCreateResult(BaseModel):
    success: bool = True
    campaign_id: int


class ErrorBody(BaseModel):
    error: str


class StreamOfferRead(BaseModel):
    id: int | None = None
    offer_id: int
    name: str | None = None
    weight: int = 0
    status: str
    is_pinned: bool = False


class StreamRead(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True, protected_namespaces=())

    id: int
    name: str | None = None
    type: str | None = None
    weight: int | float | None = None
    schema: str | None = None
    action_type: str | None = None
    offers: list[StreamOfferRead] | None = None
    is_dirty: bool | None = None
    keitaro_campaign_id: int | None = None


class StreamDeleteResult(BaseModel):
    success: bool = True
    error: str | None = None


class StreamOffersAdd(BaseModel):
    offer_id: int = Field(gt=0)


class StreamOfferPin(BaseModel):
    is_pinned: bool


class OfferRead(BaseModel):
    id: int
    name: str | None = None
    group_id: int | None = None
    state: str | None = None
