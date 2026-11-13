"""ORM-модели. Площадка (Venue) живёт отдельно от мероприятия (Event): карту этажей строят один раз,
а мероприятия накладываются поверх неё. Место (Place) — статичная зона/точка, активность (Activity) —
что и когда в ней происходит; «станция переехала» = смена Activity.place_id."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column, ForeignKey, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner | editor | live_staff


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(60), default="UTC")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    floors: Mapped[list["Floor"]] = relationship(back_populates="venue", cascade="all, delete-orphan",
                                                 order_by="Floor.level")
    events: Mapped[list["Event"]] = relationship(back_populates="venue", cascade="all, delete-orphan")


class Floor(Base):
    __tablename__ = "floors"
    __table_args__ = (UniqueConstraint("venue_id", "level"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    level: Mapped[int]
    name: Mapped[str] = mapped_column(String(80))
    base_image: Mapped[Optional[str]] = mapped_column(String(300))  # путь внутри public-хранилища
    base_w: Mapped[Optional[int]]
    base_h: Mapped[Optional[int]]
    venue: Mapped[Venue] = relationship(back_populates="floors")
    places: Mapped[list["Place"]] = relationship(back_populates="floor", cascade="all, delete-orphan")

    @property
    def base_url(self) -> Optional[str]:
        return f"/media/{self.base_image}" if self.base_image else None


class PlaceType(Base):
    __tablename__ = "place_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    geometry_kind: Mapped[str] = mapped_column(String(10))
    icon: Mapped[str] = mapped_column(String(40), default="pin")
    color: Mapped[str] = mapped_column(String(9), default="#1f6feb")
    layer: Mapped[str] = mapped_column(String(40), default="default")
    fields: Mapped[list] = mapped_column(JSON, default=list)  # список FieldDef


class Place(Base):
    __tablename__ = "places"
    id: Mapped[int] = mapped_column(primary_key=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("floors.id"), index=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("place_types.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    geometry: Mapped[dict] = mapped_column(JSON)
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    floor: Mapped[Floor] = relationship(back_populates="places")


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id"), index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[Optional[datetime]]
    ends_at: Mapped[Optional[datetime]]
    head_rev: Mapped[int] = mapped_column(default=0)  # последняя опубликованная ревизия
    staff_token: Mapped[str] = mapped_column(String(64))
    activity_fields: Mapped[list] = mapped_column(JSON, default=list)
    venue: Mapped[Venue] = relationship(back_populates="events")
    contacts: Mapped[list["Contact"]] = relationship(cascade="all, delete-orphan", order_by="Contact.id")
    activities: Mapped[list["Activity"]] = relationship(cascade="all, delete-orphan", order_by="Activity.id")
    notices: Mapped[list["Notice"]] = relationship(cascade="all, delete-orphan", order_by="Notice.id")
    revisions: Mapped[list["Revision"]] = relationship(cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    visible_to: Mapped[str] = mapped_column(String(10), default="public")  # public | staff


activity_contacts = Table(
    "activity_contacts", Base.metadata,
    Column("activity_id", ForeignKey("activities.id"), primary_key=True),
    Column("contact_id", ForeignKey("contacts.id"), primary_key=True),
)


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    place_id: Mapped[Optional[int]] = mapped_column(ForeignKey("places.id"))
    moved_from_id: Mapped[Optional[int]]  # откуда переехала (для «призрака» на карте)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[Optional[datetime]]
    ends_at: Mapped[Optional[datetime]]
    status: Mapped[str] = mapped_column(String(12), default="planned")  # planned|live|moved|cancelled|done
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    contacts: Mapped[list[Contact]] = relationship(secondary=activity_contacts)


class Notice(Base):
    __tablename__ = "notices"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    place_id: Mapped[Optional[int]]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Revision(Base):
    """Опубликованный неизменяемый снимок карты для участников."""
    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("event_id", "rev"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    rev: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(300), default="")
    author_id: Mapped[Optional[int]]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ChangeLog(Base):
    """Журнал изменений (аудит)."""
    __tablename__ = "change_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(index=True)
    user_id: Mapped[Optional[int]]
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int]
    op: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
