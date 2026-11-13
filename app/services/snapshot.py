"""Сборка снимка карты для участников. public — без полей visible_to="staff"; staff — полный."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.fields import FIELDS, visible_props
from ..domain.geometry import geometry_adapter
from ..models import Event, Place, PlaceType
from ..schemas import (Snapshot, SnapActivity, SnapContact, SnapFloor, SnapNotice, SnapPlace, SnapType)


def build_snapshot(db: Session, event: Event, rev: int, staff: bool = False) -> Snapshot:
    venue = event.venue
    floors = list(venue.floors)
    places = (db.scalars(select(Place).where(Place.floor_id.in_([f.id for f in floors])).order_by(Place.id)).all()
              if floors else [])
    used = {p.type_id for p in places}
    types = ({t.id: t for t in db.scalars(select(PlaceType).where(PlaceType.id.in_(used)))} if used else {})
    type_fields = {tid: FIELDS.validate_python(t.fields) for tid, t in types.items()}
    act_fields = FIELDS.validate_python(event.activity_fields)
    shown = lambda fields: [f for f in fields if staff or f.visible_to == "public"]  # noqa: E731

    contacts = [c for c in event.contacts if staff or c.visible_to == "public"]
    contact_ids = {c.id for c in contacts}
    return Snapshot(
        rev=rev,
        audience="staff" if staff else "public",
        event={"slug": event.slug, "title": event.title, "description": event.description,
               "starts_at": event.starts_at, "ends_at": event.ends_at},
        venue={"name": venue.name, "address": venue.address, "description": venue.description,
               "timezone": venue.timezone},
        floors=[SnapFloor(id=f.id, level=f.level, name=f.name, image=f.base_url, width=f.base_w, height=f.base_h)
                for f in floors],
        types=[SnapType(id=t.id, name=t.name, geometry_kind=t.geometry_kind, icon=t.icon, color=t.color,
                        layer=t.layer, fields=shown(type_fields[t.id])) for t in types.values()],
        places=[SnapPlace(id=p.id, floor_id=p.floor_id, type_id=p.type_id, name=p.name,
                          geometry=geometry_adapter.validate_python(p.geometry),
                          props=visible_props(type_fields[p.type_id], p.props, staff)) for p in places],
        activity_fields=shown(act_fields),
        activities=[SnapActivity(id=a.id, title=a.title, description=a.description, place_id=a.place_id,
                                 moved_from_id=a.moved_from_id, starts_at=a.starts_at, ends_at=a.ends_at,
                                 status=a.status, props=visible_props(act_fields, a.props, staff),
                                 contact_ids=[c.id for c in a.contacts if c.id in contact_ids])
                    for a in event.activities],
        contacts=[SnapContact.model_validate(c, from_attributes=True) for c in contacts],
        notices=[SnapNotice.model_validate(n, from_attributes=True) for n in event.notices[-20:]],
    )
