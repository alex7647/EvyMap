import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..domain.fields import FIELDS, validate_props
from ..models import Activity, Floor, Place, PlaceType, User, Venue
from ..schemas import (AlignIn, FloorIn, FloorOut, PlaceIn, PlaceOut, PlaceTypeIn, PlaceTypeOut, PlaceUpdate,
                       VenueIn, VenueOut)
from ..security import EDITOR, current_user
from ..services.images import (ImageError, LocalImageStore, from_jpeg, normalize, render_base, to_jpeg)
from ..services.publisher import log
from .common import check_version, floor_of, place_of, type_of, venue_of

router = APIRouter(prefix="/api", tags=["venues"])
store = LocalImageStore(settings.media_dir)


# ---- площадки
@router.get("/venues", response_model=list[VenueOut])
def list_venues(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.scalars(select(Venue).where(Venue.org_id == user.org_id).order_by(Venue.id)).all()


@router.post("/venues", response_model=VenueOut, status_code=201)
def create_venue(body: VenueIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    v = Venue(org_id=user.org_id, **body.model_dump())
    db.add(v)
    db.flush()
    log(db, user, "venue", v.id, "create", body.model_dump())
    db.commit()
    return v


@router.put("/venues/{vid}", response_model=VenueOut)
def update_venue(vid: int, body: VenueIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    v = venue_of(db, user, vid)
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    log(db, user, "venue", v.id, "update")
    db.commit()
    return v


@router.delete("/venues/{vid}", status_code=204)
def delete_venue(vid: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    v = venue_of(db, user, vid)
    if v.events:
        raise HTTPException(409, "сначала удалите мероприятия площадки")
    log(db, user, "venue", v.id, "delete")
    db.delete(v)
    db.commit()


# ---- этажи и подложки
@router.post("/venues/{vid}/floors", response_model=FloorOut, status_code=201)
def add_floor(vid: int, body: FloorIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    v = venue_of(db, user, vid)
    if any(f.level == body.level for f in v.floors):
        raise HTTPException(409, "этаж с таким номером уже есть")
    f = Floor(venue_id=v.id, **body.model_dump())
    db.add(f)
    db.flush()
    log(db, user, "floor", f.id, "create", body.model_dump())
    db.commit()
    return f


@router.delete("/floors/{fid}", status_code=204)
def delete_floor(fid: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    f = floor_of(db, user, fid)
    place_ids = [p.id for p in f.places]
    if place_ids:
        db.query(Activity).filter(Activity.place_id.in_(place_ids)).update({"place_id": None})
    if f.base_image:
        store.delete("public/" + f.base_image)
    store.delete(f"private/floors/{f.id}.jpg")
    log(db, user, "floor", f.id, "delete")
    db.delete(f)
    db.commit()


def _apply_base(db: Session, user: User, f: Floor, img, corners) -> Floor:
    try:
        data, (w, h) = render_base(img, corners, settings.base_max_px)
    except ImageError as e:
        raise HTTPException(422, str(e))
    rel = f"floors/{f.id}-{hashlib.sha1(data).hexdigest()[:10]}.webp"  # хэш в имени — кэш CDN не мешает обновлению
    store.save("public/" + rel, data)
    if f.base_image and f.base_image != rel:
        store.delete("public/" + f.base_image)
    f.base_image, f.base_w, f.base_h = rel, w, h
    log(db, user, "floor", f.id, "base", {"aligned": bool(corners)})
    db.commit()
    return f


@router.post("/floors/{fid}/base", response_model=FloorOut)
def upload_base(fid: int, file: UploadFile, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    """Загрузка фото плана. Оригинал (без EXIF) хранится приватно для повторного выравнивания."""
    f = floor_of(db, user, fid)
    limit = settings.max_upload_mb * 1024 * 1024
    raw = file.file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(413, f"файл больше {settings.max_upload_mb} МБ")
    try:
        img = normalize(raw)
    except ImageError as e:
        raise HTTPException(422, str(e))
    store.save(f"private/floors/{f.id}.jpg", to_jpeg(img))
    return _apply_base(db, user, f, img, None)


@router.post("/floors/{fid}/base/align", response_model=FloorOut)
def align_base(fid: int, body: AlignIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    f = floor_of(db, user, fid)
    original = store.read(f"private/floors/{f.id}.jpg")
    if original is None:
        raise HTTPException(409, "сначала загрузите фото")
    return _apply_base(db, user, f, from_jpeg(original), body.corners)


@router.get("/floors/{fid}/original")
def original_base(fid: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    """Исходное фото (без EXIF) — только редактору, для выбора углов выравнивания."""
    f = floor_of(db, user, fid)
    data = store.read(f"private/floors/{f.id}.jpg")
    if data is None:
        raise HTTPException(404, "фото не загружено")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


# ---- типы объектов (схема метаданных)
@router.get("/place-types", response_model=list[PlaceTypeOut])
def list_types(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.scalars(select(PlaceType).where(PlaceType.org_id == user.org_id).order_by(PlaceType.id)).all()


@router.post("/place-types", response_model=PlaceTypeOut, status_code=201)
def create_type(body: PlaceTypeIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    t = PlaceType(org_id=user.org_id, **body.model_dump())
    db.add(t)
    db.flush()
    log(db, user, "place_type", t.id, "create")
    db.commit()
    return t


@router.put("/place-types/{tid}", response_model=PlaceTypeOut)
def update_type(tid: int, body: PlaceTypeIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    t = type_of(db, user, tid)
    used = db.scalar(select(func.count()).select_from(Place).where(Place.type_id == t.id))
    if used and body.geometry_kind != t.geometry_kind:
        raise HTTPException(409, "у типа уже есть объекты — вид геометрии менять нельзя")
    for k, val in body.model_dump().items():
        setattr(t, k, val)  # поля можно добавлять и убирать: значения убранных полей просто перестают показываться
    log(db, user, "place_type", t.id, "update")
    db.commit()
    return t


@router.delete("/place-types/{tid}", status_code=204)
def delete_type(tid: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    t = type_of(db, user, tid)
    if db.scalar(select(func.count()).select_from(Place).where(Place.type_id == t.id)):
        raise HTTPException(409, "тип используется объектами")
    log(db, user, "place_type", t.id, "delete")
    db.delete(t)
    db.commit()


# ---- места
def _clean_props(db: Session, user: User, type_id: int, geometry, props: dict) -> dict:
    t = type_of(db, user, type_id)
    if geometry.type != t.geometry_kind:
        raise HTTPException(422, f"тип «{t.name}» требует геометрию «{t.geometry_kind}»")
    return validate_props(FIELDS.validate_python(t.fields), props)


@router.get("/floors/{fid}/places", response_model=list[PlaceOut])
def list_places(fid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return floor_of(db, user, fid).places


@router.post("/floors/{fid}/places", response_model=PlaceOut, status_code=201)
def create_place(fid: int, body: PlaceIn, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    f = floor_of(db, user, fid)
    props = _clean_props(db, user, body.type_id, body.geometry, body.props)
    p = Place(floor_id=f.id, type_id=body.type_id, name=body.name, geometry=body.geometry.model_dump(), props=props)
    db.add(p)
    db.flush()
    log(db, user, "place", p.id, "create")
    db.commit()
    return p


@router.patch("/places/{pid}", response_model=PlaceOut)
def update_place(pid: int, body: PlaceUpdate, if_match: Optional[int] = Header(None),
                 db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    p = place_of(db, user, pid)
    check_version(p.version, if_match)
    data = body.model_dump(exclude_unset=True)
    from ..domain.geometry import geometry_adapter
    geometry = body.geometry or geometry_adapter.validate_python(p.geometry)
    props = _clean_props(db, user, p.type_id, geometry, data["props"] if "props" in data else p.props)
    if "name" in data and data["name"] is not None:
        p.name = data["name"]
    p.geometry, p.props = geometry.model_dump(), props  # новые объекты, чтобы SQLAlchemy заметил изменение JSON
    p.version += 1
    log(db, user, "place", p.id, "update")
    db.commit()
    return p


@router.delete("/places/{pid}", status_code=204)
def delete_place(pid: int, db: Session = Depends(get_db), user: User = Depends(EDITOR)):
    p = place_of(db, user, pid)
    db.query(Activity).filter(Activity.place_id == p.id).update({"place_id": None})
    log(db, user, "place", p.id, "delete")
    db.delete(p)
    db.commit()
