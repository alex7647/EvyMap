import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain.fields import FIELDS, validate_props
from ..models import Activity, Contact, Event, Notice, Place, User
from ..schemas import (ActivityIn, ActivityOut, ActivityUpdate, ContactIn, ContactOut, EventIn, EventOut,
                       EventUpdate, MoveIn, NoticeIn, NoticeOut, PublishIn, RevisionOut)
from ..security import EDITOR, LIVE, current_user
from ..services import publisher
from .common import (activity_of, check_version, contact_of, event_of, place_of, venue_of)

router = APIRouter(prefix="/api", tags=["events"])


# ---- мероприятия
@router.get("/venues/{vid}/events", response_model=list[EventOut])
def list_events(vid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return venue_of(db, user, vid).events


@router.post("/venues/{vid}/events", response_model=EventOut, status_code=201)
def create_event(vid: int, body: EventIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    v = venue_of(db, user, vid)
    if db.scalar(select(Event).where(Event.slug == body.slug)):
        raise HTTPException(409, "такая ссылка уже занята")
    e = Event(venue_id=v.id, staff_token=secrets.token_urlsafe(12), **body.model_dump())
    db.add(e)
    db.flush()
    publisher.log(db, user, "event", e.id, "create")
    db.commit()
    return e


@router.patch("/events/{eid}", response_model=EventOut)
def update_event(eid: int, body: EventUpdate, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    e = event_of(db, user, eid)
    for k, val in body.model_dump(exclude_unset=True).items():
        if val is not None:
            setattr(e, k, val)
    publisher.log(db, user, "event", e.id, "update")
    db.commit()
    return e


@router.delete("/events/{eid}", status_code=204)
def delete_event(eid: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    e = event_of(db, user, eid)
    publisher.log(db, user, "event", e.id, "delete")
    for a in e.activities:
        a.contacts.clear()
    db.flush()
    db.delete(e)
    db.commit()


# ---- контакты
@router.get("/events/{eid}/contacts", response_model=list[ContactOut])
def list_contacts(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return event_of(db, user, eid).contacts


@router.post("/events/{eid}/contacts", response_model=ContactOut, status_code=201)
def create_contact(eid: int, body: ContactIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    e = event_of(db, user, eid)
    c = Contact(event_id=e.id, **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.delete("/contacts/{cid}", status_code=204)
def delete_contact(cid: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    c = contact_of(db, user, cid)
    for a in db.scalars(select(Activity).where(Activity.event_id == c.event_id)):
        if c in a.contacts:
            a.contacts.remove(c)
    db.delete(c)
    db.commit()


# ---- активности
def _prepare_activity(db: Session, e: Event, place_id: Optional[int], contact_ids: list[int], props: dict):
    if place_id is not None:
        p = db.get(Place, place_id)
        if p is None or p.floor.venue_id != e.venue_id:
            raise HTTPException(422, "место не принадлежит площадке мероприятия")
    contacts = db.scalars(select(Contact).where(Contact.id.in_(contact_ids), Contact.event_id == e.id)).all() \
        if contact_ids else []
    if len(contacts) != len(set(contact_ids)):
        raise HTTPException(422, "неизвестный контакт")
    return contacts, validate_props(FIELDS.validate_python(e.activity_fields), props)


@router.get("/events/{eid}/activities", response_model=list[ActivityOut])
def list_activities(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return event_of(db, user, eid).activities


@router.post("/events/{eid}/activities", response_model=ActivityOut, status_code=201)
def create_activity(eid: int, body: ActivityIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    e = event_of(db, user, eid)
    contacts, props = _prepare_activity(db, e, body.place_id, body.contact_ids, body.props)
    a = Activity(event_id=e.id, **body.model_dump(exclude={"contact_ids", "props"}), props=props)
    a.contacts = list(contacts)
    db.add(a)
    db.flush()
    publisher.log(db, user, "activity", a.id, "create")
    db.commit()
    return a


@router.patch("/activities/{aid}", response_model=ActivityOut)
def update_activity(aid: int, body: ActivityUpdate, if_match: Optional[int] = Header(None),
                    db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    a = activity_of(db, user, aid)
    check_version(a.version, if_match)
    e = event_of(db, user, a.event_id)
    data = body.model_dump(exclude_unset=True)
    contacts, props = _prepare_activity(
        db, e, data.get("place_id", a.place_id),
        data["contact_ids"] if "contact_ids" in data else [c.id for c in a.contacts],
        data["props"] if "props" in data else a.props)
    for k in ("title", "description", "place_id", "starts_at", "ends_at", "status"):
        if k in data and (data[k] is not None or k in ("place_id", "starts_at", "ends_at")):
            setattr(a, k, data[k])
    if "status" in data and data["status"] != "moved":
        a.moved_from_id = None
    a.props, a.contacts = props, list(contacts)
    a.version += 1
    publisher.log(db, user, "activity", a.id, "update")
    db.commit()
    return a


@router.delete("/activities/{aid}", status_code=204)
def delete_activity(aid: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    a = activity_of(db, user, aid)
    a.contacts.clear()
    db.flush()
    db.delete(a)
    db.commit()


@router.post("/activities/{aid}/move", response_model=ActivityOut)
def move_activity(aid: int, body: MoveIn, db: Session = Depends(get_db), user: User = Depends(LIVE)):
    """Live-режим: перенос активности + уведомление + мгновенная публикация (доступно live_staff)."""
    a = activity_of(db, user, aid)
    e = event_of(db, user, a.event_id)
    _prepare_activity(db, e, body.place_id, [], {})
    return publisher.move_activity(db, user, e, a, body.place_id, body.notice, body.publish)


# ---- уведомления и публикация
@router.get("/events/{eid}/notices", response_model=list[NoticeOut])
def list_notices(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return event_of(db, user, eid).notices


@router.post("/events/{eid}/notices", response_model=NoticeOut, status_code=201)
def create_notice(eid: int, body: NoticeIn, db: Session = Depends(get_db), user: User = Depends(LIVE)):
    e = event_of(db, user, eid)
    n = Notice(event_id=e.id, text=body.text, place_id=body.place_id)
    db.add(n)
    db.commit()
    if body.publish:
        publisher.publish(db, e, user, note=body.text)
    return n


@router.post("/events/{eid}/publish", response_model=RevisionOut)
def publish(eid: int, body: PublishIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    return publisher.publish(db, event_of(db, user, eid), user, body.note)


@router.get("/events/{eid}/revisions", response_model=list[RevisionOut])
def revisions(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return sorted(event_of(db, user, eid).revisions, key=lambda r: -r.rev)


@router.post("/events/{eid}/rollback/{rev}", response_model=RevisionOut)
def rollback(eid: int, rev: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    try:
        return publisher.rollback(db, event_of(db, user, eid), user, rev)
    except LookupError as e:
        raise HTTPException(404, str(e))
