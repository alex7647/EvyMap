"""Публикация ревизий и live-перенос активностей."""
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Activity, ChangeLog, Event, Notice, Place, Revision, User
from .bus import bus
from .snapshot import build_snapshot


def log(db: Session, user: User, entity: str, entity_id: int, op: str, payload: Optional[dict] = None) -> None:
    db.add(ChangeLog(org_id=user.org_id, user_id=user.id, entity=entity, entity_id=entity_id,
                     op=op, payload=payload or {}))


def publish(db: Session, event: Event, user: User, note: str = "") -> Revision:
    """Собирает снимок, сохраняет как новую ревизию, двигает head и будит подписчиков SSE."""
    rev = event.head_rev + 1
    snap = build_snapshot(db, event, rev)
    row = Revision(event_id=event.id, rev=rev, snapshot=snap.model_dump(mode="json"), note=note, author_id=user.id)
    event.head_rev = rev
    db.add(row)
    log(db, user, "event", event.id, "publish", {"rev": rev, "note": note})
    db.commit()
    bus.publish(event.slug, {"rev": rev})
    return row


def rollback(db: Session, event: Event, user: User, rev: int) -> Revision:
    """Откат публичной карты: старый снимок публикуется как новая ревизия (черновик не меняется)."""
    old = next((r for r in event.revisions if r.rev == rev), None)
    if old is None:
        raise LookupError("ревизия не найдена")
    new_rev = event.head_rev + 1
    snap = {**old.snapshot, "rev": new_rev}
    row = Revision(event_id=event.id, rev=new_rev, snapshot=snap, note=f"откат к ревизии {rev}", author_id=user.id)
    event.head_rev = new_rev
    db.add(row)
    log(db, user, "event", event.id, "rollback", {"to": rev, "rev": new_rev})
    db.commit()
    bus.publish(event.slug, {"rev": new_rev})
    return row


def move_activity(db: Session, user: User, event: Event, act: Activity, place_id: int,
                  notice: Optional[str], do_publish: bool) -> Activity:
    """«Станция переехала»: меняет место, ставит статус moved, пишет уведомление и (опц.) публикует."""
    if act.place_id != place_id:
        old = db.get(Place, act.place_id) if act.place_id else None
        new = db.get(Place, place_id)
        act.moved_from_id, act.place_id, act.status = act.place_id, place_id, "moved"
        act.version += 1
        text = notice or f"«{act.title}» переехала: {(old.name if old else '') or 'прежнее место'} → {new.name or 'новое место'}"
        db.add(Notice(event_id=event.id, text=text, place_id=place_id))
        log(db, user, "activity", act.id, "move", {"from": act.moved_from_id, "to": place_id})
        db.commit()
        if do_publish:
            publish(db, event, user, note=text)
    return act
