"""Загрузка объектов с проверкой принадлежности организации пользователя."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Activity, Contact, Event, Floor, Place, PlaceType, User, Venue


def _ensure(obj, ok: bool, what: str):
    if obj is None or not ok:
        raise HTTPException(404, f"{what} не найден")
    return obj


def venue_of(db: Session, user: User, vid: int) -> Venue:
    v = db.get(Venue, vid)
    return _ensure(v, v is not None and v.org_id == user.org_id, "площадка")


def floor_of(db: Session, user: User, fid: int) -> Floor:
    f = db.get(Floor, fid)
    return _ensure(f, f is not None and f.venue.org_id == user.org_id, "этаж")


def type_of(db: Session, user: User, tid: int) -> PlaceType:
    t = db.get(PlaceType, tid)
    return _ensure(t, t is not None and t.org_id == user.org_id, "тип")


def place_of(db: Session, user: User, pid: int) -> Place:
    p = db.get(Place, pid)
    return _ensure(p, p is not None and p.floor.venue.org_id == user.org_id, "место")


def event_of(db: Session, user: User, eid: int) -> Event:
    e = db.get(Event, eid)
    return _ensure(e, e is not None and e.venue.org_id == user.org_id, "мероприятие")


def activity_of(db: Session, user: User, aid: int) -> Activity:
    a = db.get(Activity, aid)
    return _ensure(a, a is not None and event_of(db, user, a.event_id) is not None, "активность")


def contact_of(db: Session, user: User, cid: int) -> Contact:
    c = db.get(Contact, cid)
    return _ensure(c, c is not None and event_of(db, user, c.event_id) is not None, "контакт")


def check_version(current: int, if_match) -> None:
    """Оптимистичная блокировка: заголовок If-Match: <version>; при расхождении — 409."""
    if if_match is not None and if_match != current:
        raise HTTPException(409, {"message": "объект уже изменён кем-то другим", "current_version": current})
