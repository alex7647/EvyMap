"""Pydantic-схемы API и снимка карты (Snapshot)."""
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domain.fields import FieldDef
from .domain.geometry import Geometry, GeometryKind

Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)]
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{2,60}$")]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Status = Literal["planned", "live", "moved", "cancelled", "done"]
Role = Literal["owner", "editor", "live_staff"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _unique_keys(v):
    keys = [f.key for f in v]
    if len(keys) != len(set(keys)):
        raise ValueError("ключи полей должны быть уникальны")
    return v


# ---- auth
class RegisterIn(BaseModel):
    org_name: str = Field(min_length=1, max_length=120)
    email: Email
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: Email
    password: str


class UserIn(LoginIn):
    role: Role = "editor"


class UserOut(ORM):
    id: int
    email: str
    role: str
    org_id: int


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- venues / floors
class FloorIn(BaseModel):
    level: int
    name: str = Field(min_length=1, max_length=80)


class FloorOut(ORM, FloorIn):
    id: int
    venue_id: int
    base_url: Optional[str] = None
    base_w: Optional[int] = None
    base_h: Optional[int] = None


class AlignIn(BaseModel):
    """4 угла листа на исходном фото, нормализованные 0..1, порядок: лев-верх, пр-верх, пр-низ, лев-низ."""
    corners: Annotated[list[tuple[float, float]], Field(min_length=4, max_length=4)]


class VenueIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field("", max_length=300)
    description: str = ""
    timezone: str = "UTC"


class VenueOut(ORM, VenueIn):
    id: int
    floors: list[FloorOut] = []


# ---- place types / places
class PlaceTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    geometry_kind: GeometryKind
    icon: str = "pin"
    color: Color = "#1f6feb"
    layer: str = "default"
    fields: list[FieldDef] = []
    _uniq = field_validator("fields")(_unique_keys)


class PlaceTypeOut(ORM, PlaceTypeIn):
    id: int


class PlaceIn(BaseModel):
    type_id: int
    name: str = Field("", max_length=200)
    geometry: Geometry
    props: dict[str, Any] = {}


class PlaceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    geometry: Optional[Geometry] = None
    props: Optional[dict[str, Any]] = None


class PlaceOut(ORM):
    id: int
    floor_id: int
    type_id: int
    name: str
    geometry: Geometry
    props: dict[str, Any]
    version: int


# ---- events
class EventIn(BaseModel):
    slug: Slug
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    activity_fields: list[FieldDef] = []
    _uniq = field_validator("activity_fields")(_unique_keys)


class EventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    activity_fields: Optional[list[FieldDef]] = None


class EventOut(ORM, EventIn):
    id: int
    venue_id: int
    head_rev: int
    staff_token: str


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = ""
    phone: str = ""
    email: str = ""
    visible_to: Literal["public", "staff"] = "public"


class ContactOut(ORM, ContactIn):
    id: int


class ActivityIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    place_id: Optional[int] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    status: Status = "planned"
    props: dict[str, Any] = {}
    contact_ids: list[int] = []


class ActivityUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    place_id: Optional[int] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    status: Optional[Status] = None
    props: Optional[dict[str, Any]] = None
    contact_ids: Optional[list[int]] = None


class ActivityOut(ORM):
    id: int
    event_id: int
    title: str
    description: str
    place_id: Optional[int]
    moved_from_id: Optional[int]
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    status: str
    props: dict[str, Any]
    version: int
    contacts: list[ContactOut]


class MoveIn(BaseModel):
    place_id: int
    notice: Optional[str] = Field(None, max_length=500)
    publish: bool = True  # live-режим: сразу опубликовать


class NoticeIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    place_id: Optional[int] = None
    publish: bool = True


class NoticeOut(ORM):
    id: int
    text: str
    place_id: Optional[int]
    created_at: datetime


class PublishIn(BaseModel):
    note: str = Field("", max_length=300)


class RevisionOut(ORM):
    rev: int
    note: str
    created_at: datetime


# ---- снимок карты (то, что получает вьюер)
class SnapFloor(BaseModel):
    id: int
    level: int
    name: str
    image: Optional[str]
    width: Optional[int]
    height: Optional[int]


class SnapType(BaseModel):
    id: int
    name: str
    geometry_kind: str
    icon: str
    color: str
    layer: str
    fields: list[FieldDef]


class SnapPlace(BaseModel):
    id: int
    floor_id: int
    type_id: int
    name: str
    geometry: Geometry
    props: dict[str, Any]


class SnapContact(BaseModel):
    id: int
    name: str
    role: str
    phone: str
    email: str


class SnapActivity(BaseModel):
    id: int
    title: str
    description: str
    place_id: Optional[int]
    moved_from_id: Optional[int]
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    status: str
    props: dict[str, Any]
    contact_ids: list[int]


class SnapNotice(BaseModel):
    id: int
    text: str
    place_id: Optional[int]
    created_at: datetime


class Snapshot(BaseModel):
    rev: int
    audience: Literal["public", "staff"]
    event: dict[str, Any]
    venue: dict[str, Any]
    floors: list[SnapFloor]
    types: list[SnapType]
    places: list[SnapPlace]
    activity_fields: list[FieldDef]
    activities: list[SnapActivity]
    contacts: list[SnapContact]
    notices: list[SnapNotice]
